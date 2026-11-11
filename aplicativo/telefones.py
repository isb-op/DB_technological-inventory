"""Cadastro local de aparelhos e linhas; fontes Excel são somente lidas."""
import datetime as dt
import hashlib
import json
import uuid
from contextlib import nullcontext

class DuplicatePhone(ValueError):
    def __init__(self,ids):
        self.ids=sorted(ids)
        super().__init__('Este IMEI já está cadastrado em '+', '.join(f'TEL-{i}' for i in self.ids)+'. Use Entregar / trocar do estoque para utilizar o registro existente, sem copiar os dados para outro aparelho.')

class DuplicateLine(ValueError):
    def __init__(self,ids):
        self.ids=sorted(ids)
        super().__init__('Este número de celular já está cadastrado em '+', '.join(f'TEL-{i}' for i in self.ids)+'. Utilize o registro existente ou transfira a linha pela entrega / troca do estoque. Nenhuma alteração foi salva.')


def digits(value):
    return ''.join(c for c in str(value or '') if c.isdigit())


def phone_number(value):
    number=digits(value)
    return number[2:] if len(number) in (12,13) and number.startswith('55') else number


def imeis(values):
    return {digits(values[i]) for i in (9,10)}-{''}


def validate_device_identity(con,values,record_id=None,strict=False):
    # IMEIs are unique across both slots; blank identifiers are not identities.
    new=imeis(values);number=phone_number(values[8])
    devices=set();lines=set()
    for row in con.execute('SELECT id,dados FROM telefones WHERE excluido=0'):
        if row['id']==record_id:continue
        other=json.loads(row['dados'])
        if new & imeis(other):devices.add(row['id'])
        if number and number==phone_number(other[8]):lines.add(row['id'])
    if devices:raise DuplicatePhone(devices)
    if lines:raise DuplicateLine(lines)

FIELDS=('Base','Cidade','Setor','Nome Completo','Cargo','Matrícula','Marca','Modelo do Telefone','Número de Telefone','IMEI1','IMEI2','Acessórios','Estado de Conservação','Status do Aparelho','Termo de Responsabilidade','Data de cadastro','Observação')
STATUSES=('Estoque','Em uso','Defeito/Parado','Manutenção','Separado','Transferido','Perdido','Roubado','Descartado','Quebrado')
EXTERNAL_FIELDS=('Nome completo','Base','Cidade','Estado','Matrícula','Cargo','Telefone pessoal')
STATES=('AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')

def init(con):
    con.execute('''CREATE TABLE IF NOT EXISTS telefones(
        id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT UNIQUE NOT NULL,
        dados TEXT NOT NULL, colaborador INTEGER REFERENCES colaboradores(id),
        manual INTEGER NOT NULL DEFAULT 0, excluido INTEGER NOT NULL DEFAULT 0)''')
    if 'status_manual' not in [r['name'] for r in con.execute('PRAGMA table_info(telefones)')]:
        con.execute('ALTER TABLE telefones ADD COLUMN status_manual INTEGER NOT NULL DEFAULT 0')
    if 'responsavel_externo' not in [r['name'] for r in con.execute('PRAGMA table_info(telefones)')]:
        con.execute('ALTER TABLE telefones ADD COLUMN responsavel_externo TEXT')
    columns=[r['name'] for r in con.execute('PRAGMA table_info(telefones)')]
    if 'uso_equipes' not in columns:
        con.execute('ALTER TABLE telefones ADD COLUMN uso_equipes INTEGER NOT NULL DEFAULT 0')
    if 'equipes' not in columns:
        con.execute("ALTER TABLE telefones ADD COLUMN equipes TEXT NOT NULL DEFAULT ''")
    if 'estado' not in columns:
        con.execute("ALTER TABLE telefones ADD COLUMN estado TEXT NOT NULL DEFAULT ''")
    if 'data_chegada' not in columns:
        con.execute("ALTER TABLE telefones ADD COLUMN data_chegada TEXT NOT NULL DEFAULT ''")
    if 'cadastro_em' not in columns:
        con.execute("ALTER TABLE telefones ADD COLUMN cadastro_em TEXT NOT NULL DEFAULT ''")
        con.execute('UPDATE telefones SET cadastro_em=?',(dt.date.today().isoformat(),))
    if 'liberacao' not in columns:
        con.execute("ALTER TABLE telefones ADD COLUMN liberacao TEXT NOT NULL DEFAULT ''")

def match(con,values):
    from banco import matricula,norm
    key=matricula(values[5]);name=norm(values[3])
    if key:
        person=con.execute('SELECT * FROM colaboradores WHERE matricula=?',(key,)).fetchone()
        if not person:return None,'Matrícula não encontrada no Dados Flex'
        if name and norm(person['nome'])!=name:return person,'Matrícula encontrada; nome diverge do Dados Flex'
        return person,'Relacionado por matrícula'
    if name:
        people=[p for p in con.execute('SELECT * FROM colaboradores') if norm(p['nome'])==name]
        if len(people)==1:return people[0],'Relacionado por nome exato (sem matrícula)'
        if len(people)>1:return None,'Nome ambíguo; informe a matrícula'
    return None,'Colaborador não encontrado no Dados Flex'

def records(con):
    from banco import effective
    out=[]
    for record in con.execute('SELECT * FROM telefones WHERE excluido=0 ORDER BY id'):
        row=dict(record);values=json.loads(row['dados'])
        external=json.loads(row['responsavel_externo']) if row['responsavel_externo'] else None
        if external:
            person=None
            reason='Tutela de colaborador de outra base (fora do Dados Flex)'
        elif row['manual']:
            person=con.execute('SELECT * FROM colaboradores WHERE id=?',(row['colaborador'],)).fetchone() if row['colaborador'] else None
            reason='Atribuição manual' if person else 'Sem colaborador atribuído'
        else:person,reason=match(con,values)
        if not person and not external and values[13].strip().casefold()=='estoque':
            reason='Em estoque — sem tutela'
        row.update(values=values,person=dict(person) if person else None,external=external,conferencia=reason,
                   situacao_colaborador='Outra base' if external else (effective(person) if person else 'Não encontrado'))
        out.append(row)
    return out

def import_file(con,path):
    import openpyxl
    from banco import dumps,audit,norm
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    source=con.execute('SELECT * FROM fontes WHERE arquivo=?',(path.name,)).fetchone()
    if source and source['hash']==digest:return 'sem alterações'
    wb=openpyxl.load_workbook(path,data_only=True)
    try:
        sheet=wb['Inventário'] if 'Inventário' in wb.sheetnames else wb.active
        rows=list(sheet.values)
        headers=[norm(v) for v in rows[0]]
        indices=[]
        for field in FIELDS:
            if norm(field) not in headers:raise ValueError(f'Telefones: coluna ausente: {field}')
            indices.append(headers.index(norm(field)))
        seen={}
        for r in rows[1:]:
            if not any(v is not None for v in r):continue
            data=[str(r[i]) if r[i] is not None else '' for i in indices]
            def identifier(value):
                return ''.join(c for c in value if c.isdigit())
            identity=next((prefix+identifier(data[i]) for prefix,i in [('imei:',9),('imei:',10),('linha:',8)] if identifier(data[i])),None)
            identity=identity or 'dados:'+uuid.uuid5(uuid.NAMESPACE_URL,dumps(data)).hex
            seen[identity]=seen.get(identity,0)+1
            key=f'{identity}:{seen[identity]}'
            if not data[14].strip():data[14]='Não'
            existing=con.execute('SELECT id,dados,status_manual,manual,excluido FROM telefones WHERE chave=?',(key,)).fetchone()
            if existing and existing['status_manual']:
                data[13]=json.loads(existing['dados'])[13]
            if not existing or (not existing['manual'] and not existing['excluido']):
                validate_device_identity(con,data,existing['id'] if existing else None)
            con.execute('''INSERT INTO telefones(chave,dados,cadastro_em) VALUES(?,?,?) ON CONFLICT(chave)
                DO UPDATE SET dados=excluded.dados WHERE telefones.manual=0 AND telefones.excluido=0''',(key,dumps(data),dt.date.today().isoformat()))
        con.execute('INSERT INTO fontes(arquivo,hash,importado) VALUES(?,?,?) ON CONFLICT(arquivo) DO UPDATE SET hash=excluded.hash,importado=excluded.importado',(path.name,digest,dt.datetime.now().isoformat()))
        audit(con,'importacao_telefones',path.name,{}, {'registros_lidos':sum(seen.values())})
        return f'{sum(seen.values())} registros lidos'
    finally:wb.close()

def save(con,values,employee_id=None,record_id=None,external=None,uso_equipes=None,equipes=None,estado=None,data_chegada=None,cadastro_em=None,liberacao=None,_commit=True,_movement=True,movement_day=None,movement_reason='Alteração de tutela no cadastro',movement_defect=''):
    from banco import effective,audit,dumps,norm,registration_date
    if len(values)!=len(FIELDS):raise ValueError('Formulário incompleto.')
    values=[str(v or '').strip() for v in values]
    if not record_id and not any(values[i] for i in (7,8,9,10)):raise ValueError('Informe modelo, número da linha ou IMEI. Para devoluções sem dados, use Movimentações.')
    if external is not None:
        pending_matricula=bool(external.get('Matrícula pendente',False))
        external={field:str(external.get(field) or '').strip() for field in EXTERNAL_FIELDS}
        if pending_matricula and not external['Matrícula']:external['Matrícula pendente']=True
        for field in EXTERNAL_FIELDS:
            if field=='Matrícula' and external.get('Matrícula pendente'):continue
            if not external[field]:raise ValueError(f'Informe {field.lower()} do colaborador de outra base.')
        external['Estado']=external['Estado'].upper()
        if external['Estado'] not in STATES:raise ValueError('Selecione uma UF válida para o estado.')
        digits=''.join(c for c in external['Telefone pessoal'] if c.isdigit())
        if len(digits) not in (10,11):raise ValueError('Informe telefone pessoal com DDD (10 ou 11 dígitos).')
        if employee_id:raise ValueError('Escolha apenas um tipo de responsável.')
    with con if _commit else nullcontext():
        old=con.execute('SELECT * FROM telefones WHERE id=? AND excluido=0',(record_id,)).fetchone() if record_id else None
        if record_id and not old:raise ValueError('Registro não encontrado.')
        validate_device_identity(con,values,record_id)
        registered=registration_date(cadastro_em if cadastro_em is not None else (old['cadastro_em'] or None) if old else None)
        state=str(estado or '').strip().upper() if estado is not None else old['estado'] if old else ''
        arrival=str(data_chegada or '').strip() if data_chegada is not None else old['data_chegada'] if old else ''
        released=str(liberacao or '').strip() if liberacao is not None else old['liberacao'] if old else ''
        if state and state not in STATES:raise ValueError('Selecione uma UF válida para o aparelho.')
        if arrival:
            try:dt.date.fromisoformat(arrival)
            except ValueError:raise ValueError('Informe a data de chegada como AAAA-MM-DD.')
        if released:
            try:dt.date.fromisoformat(released)
            except ValueError:raise ValueError('Informe a data de liberação como AAAA-MM-DD.')
        shared=bool(uso_equipes) if uso_equipes is not None else bool(old['uso_equipes']) if old else False
        team=str(equipes or '').strip() if equipes is not None else old['equipes'] if old else ''
        if not shared:team=''
        person=con.execute('SELECT * FROM colaboradores WHERE id=?',(employee_id,)).fetchone() if employee_id else None
        old_row=next((r for r in records(con) if r['id']==record_id),None) if old else None
        old_person=old_row['person'] if old_row else None
        if employee_id and (not person or (effective(person)!='ATIVO' and (not old_person or old_person['id']!=employee_id))):
            raise ValueError('Selecione um colaborador ativo para uma nova atribuição.')
        if norm(values[13])=='EM USO' and not person and not external:raise ValueError('Selecione um colaborador ou informe os dados do responsável de outra base.')
        if shared and not person and not external:raise ValueError('Selecione o responsável pela tutela do aparelho usado por equipes.')
        if external:
            values[0]=external['Base']
            values[3],values[4],values[5]=external['Nome completo'],external['Cargo'],external['Matrícula']
        elif person:values[3],values[4],values[5]=person['nome'],person['cargo'] or '',person['matricula']
        elif old_person or (old and old['responsavel_externo']):
            values[3]=values[4]=values[5]=''
        from movimentacoes import custodian,log
        previous=custodian(old_row) if old_row else None
        after=custodian({'person':dict(person) if person else None,'external':external})
        def identity(p):
            return ('interno',p['id']) if p and p.get('id') else ('externo',p.get('Nome completo'),p.get('Matrícula'),p.get('Base')) if p else None
        changed=identity(previous)!=identity(after)
        if changed and old:values[14]='Não'
        if old:
            con.execute('UPDATE telefones SET dados=?,colaborador=?,manual=1 WHERE id=?',(dumps(values),employee_id,record_id))
        else:
            record_id=con.execute('INSERT INTO telefones(chave,dados,colaborador,manual) VALUES(?,?,?,1)',('manual:'+uuid.uuid4().hex,dumps(values),employee_id)).lastrowid
        con.execute('UPDATE telefones SET responsavel_externo=? WHERE id=?',(dumps(external) if external else None,record_id))
        con.execute('UPDATE telefones SET uso_equipes=?,equipes=? WHERE id=?',(int(shared),team,record_id))
        con.execute('UPDATE telefones SET estado=?,data_chegada=? WHERE id=?',(state,arrival,record_id))
        con.execute('UPDATE telefones SET cadastro_em=? WHERE id=?',(registered,record_id))
        con.execute('UPDATE telefones SET liberacao=? WHERE id=?',(released,record_id))
        audit(con,'telefone',record_id,dict(old) if old else {},{'dados':values,'colaborador':employee_id,'responsavel_externo':external,'uso_equipes':shared,'equipes':team,'estado':state,'data_chegada':arrival,'cadastro_em':registered,'liberacao':released})
        if _movement and previous and changed:
            log(con,'Troca de tutela' if after else 'Devolução',record_id,None,previous,after,movement_reason,movement_defect,values[13],{'devolvido':old_row['values'],'entregue':values if after else None},movement_day)
    return record_id

def delete(con,record_id):
    from banco import audit
    with con:
        old=con.execute('SELECT * FROM telefones WHERE id=? AND excluido=0',(record_id,)).fetchone()
        if not old:raise ValueError('Registro não encontrado.')
        con.execute('UPDATE telefones SET excluido=1,manual=1 WHERE id=?',(record_id,))
        audit(con,'telefone',record_id,dict(old),{'excluido':True})
