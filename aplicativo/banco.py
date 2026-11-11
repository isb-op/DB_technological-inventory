"""Persistência local. Fontes Excel são somente lidas, nunca alteradas."""
import datetime as dt
import hashlib
import json
import sqlite3
import unicodedata
import uuid
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'dados' / 'gestao.sqlite3'
COMPUTER_FIELDS = ('ID do equipamento','Nº patrimônio','Nome do Dispositivo','Tipo','Marca','Modelo','Processador','Memória RAM','Armazenamento','Sistema Operacional Edição','Situação','Condição','Base/unidade','Localização física','Observação')
COMPUTER_STATUSES = ('Estoque','Em uso','Defeito/Parado','Manutenção','Separado','Transferido')

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '').strip().upper()) if not unicodedata.combining(c))

def matricula(value):
    text = str(value or '').strip()
    if text.endswith('.0'): text = text[:-2]
    return text.lstrip('0') if text.isdigit() else ''

def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str)

def connect(path=DB):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS fontes(id INTEGER PRIMARY KEY, arquivo TEXT UNIQUE, hash TEXT, importado TEXT);
    CREATE TABLE IF NOT EXISTS originais(id INTEGER PRIMARY KEY, fonte INTEGER REFERENCES fontes(id), aba TEXT, linha INTEGER, dados TEXT, UNIQUE(fonte,aba,linha));
    CREATE TABLE IF NOT EXISTS colaboradores(id INTEGER PRIMARY KEY, matricula TEXT UNIQUE NOT NULL, nome TEXT NOT NULL, cargo TEXT, localidade TEXT, situacao_fonte TEXT, desligamento TEXT, situacao_manual TEXT, dados TEXT);
    CREATE TABLE IF NOT EXISTS computadores(id INTEGER PRIMARY KEY, codigo TEXT UNIQUE NOT NULL, patrimonio TEXT, modelo TEXT, situacao TEXT, localidade TEXT, dados TEXT);
    CREATE TABLE IF NOT EXISTS entregas(id INTEGER PRIMARY KEY, chave TEXT UNIQUE, computador INTEGER REFERENCES computadores(id), colaborador INTEGER REFERENCES colaboradores(id), nome_origem TEXT, matricula_origem TEXT, devolucao TEXT, alerta TEXT, dados TEXT);
    CREATE TABLE IF NOT EXISTS sancoes(id INTEGER PRIMARY KEY, numero TEXT UNIQUE NOT NULL, referencia TEXT, area TEXT, processo TEXT, status TEXT, valor REAL, prazo TEXT, detalhes TEXT, dados TEXT);
    CREATE TABLE IF NOT EXISTS respostas(sancao INTEGER PRIMARY KEY REFERENCES sancoes(id), colaborador INTEGER REFERENCES colaboradores(id), andamento TEXT NOT NULL DEFAULT 'Pendente', prazo TEXT, resposta TEXT, atualizado TEXT);
    CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY, data TEXT, entidade TEXT, registro TEXT, antes TEXT, depois TEXT);
    CREATE TABLE IF NOT EXISTS computadores_excluidos(computador INTEGER PRIMARY KEY REFERENCES computadores(id), data TEXT NOT NULL);
    ''')
    if 'registro_id' not in [r['name'] for r in con.execute('PRAGMA table_info(originais)')]:
        con.execute('ALTER TABLE originais ADD COLUMN registro_id TEXT')
    for row in con.execute('SELECT id FROM originais WHERE registro_id IS NULL').fetchall():
        con.execute('UPDATE originais SET registro_id=? WHERE id=?',('REG-'+uuid.uuid4().hex,row['id']))
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS originais_registro_id ON originais(registro_id)')
    from telefones import init
    init(con)
    from movimentacoes import init as init_movements
    init_movements(con)
    from pc_movimentos import init as init_pc_movements
    init_pc_movements(con)
    if 'componentes' not in [r['name'] for r in con.execute('PRAGMA table_info(entregas)')]:
        con.execute("ALTER TABLE entregas ADD COLUMN componentes TEXT NOT NULL DEFAULT ''")
    if 'cadastro_em' not in [r['name'] for r in con.execute('PRAGMA table_info(computadores)')]:
        con.execute("ALTER TABLE computadores ADD COLUMN cadastro_em TEXT NOT NULL DEFAULT ''")
        con.execute('UPDATE computadores SET cadastro_em=?',(dt.date.today().isoformat(),))
    con.commit()
    return con

def effective(row):
    if row['situacao_manual']: return row['situacao_manual']
    return 'DESLIGADO' if row['desligamento'] not in ('', '-', None) else row['situacao_fonte']

def audit(con, entity, key, before, after):
    con.execute('INSERT INTO auditoria(data,entidade,registro,antes,depois) VALUES(?,?,?,?,?)', (dt.datetime.now().isoformat(timespec='seconds'), entity, str(key), dumps(before), dumps(after)))

def import_sources(con, root=ROOT):
    import openpyxl
    counts = {}
    with con:
        patterns=[('DADOS*.xlsx','pessoas'), ('Inventário*.xlsx','computadores')]
        if not (Path(root)/'Telefones.xlsx').exists():patterns += [('Levantamento*.xlsx','anexo'), ('Sistema*.xlsx','sancoes')]
        for pattern, kind in patterns:
            paths = list(Path(root).glob(pattern))
            if len(paths) != 1: raise ValueError(f'Esperado um arquivo {pattern}; encontrados {len(paths)}.')
            path = paths[0]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            previous = con.execute('SELECT * FROM fontes WHERE arquivo=?',(path.name,)).fetchone()
            if previous and previous['hash'] == digest:
                counts[kind] = 'sem alterações'
                continue
            wb = openpyxl.load_workbook(path, data_only=True)
            con.execute('INSERT INTO fontes(arquivo,hash,importado) VALUES(?,?,?) ON CONFLICT(arquivo) DO UPDATE SET hash=excluded.hash,importado=excluded.importado', (path.name,digest,dt.datetime.now().isoformat(timespec='seconds')))
            fid = con.execute('SELECT id FROM fontes WHERE arquivo=?',(path.name,)).fetchone()[0]
            # Registros idênticos conservam o ID mesmo se a ordem das linhas mudar.
            previous_ids = {}
            for old in con.execute('SELECT aba,dados,registro_id FROM originais WHERE fonte=? ORDER BY linha',(fid,)):
                previous_ids.setdefault((old['aba'],old['dados']), []).append(old['registro_id'])
            con.execute('DELETE FROM originais WHERE fonte=?',(fid,))
            sheets = {}
            for sheet in wb:
                if kind == 'computadores' and norm(sheet.title) == 'RESPONSAVEL':
                    continue
                rows = list(sheet.values)
                sheets[norm(sheet.title)] = rows
                for n, values in enumerate(rows,1):
                    if any(v is not None for v in values):
                        raw=dumps(values)
                        candidates=previous_ids.get((sheet.title,raw),[])
                        rid=candidates.pop(0) if candidates else 'REG-'+uuid.uuid4().hex
                        con.execute('INSERT INTO originais(fonte,aba,linha,dados,registro_id) VALUES(?,?,?,?,?)',(fid,sheet.title,n,raw,rid))
            if kind == 'pessoas':
                for r in next(iter(sheets.values()))[1:]:
                    key = matricula(r[0])
                    if not key: continue
                    con.execute('''INSERT INTO colaboradores(matricula,nome,cargo,localidade,situacao_fonte,desligamento,dados) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(matricula) DO UPDATE SET nome=excluded.nome,cargo=excluded.cargo,localidade=excluded.localidade,situacao_fonte=excluded.situacao_fonte,desligamento=excluded.desligamento,dados=excluded.dados''', (key,r[1],r[21],r[17],r[8],str(r[10] or ''),dumps(r)))
            elif kind == 'computadores':
                inventory=sheets['IDENTIFICACAO&CONFIGURACAO']
                has_code=norm(inventory[0][0])=='ID DO EQUIPAMENTO'
                for source_row in inventory[1:]:
                    if not any(v is not None for v in source_row): continue
                    r=list(source_row)
                    if not has_code:
                        matches=con.execute('SELECT codigo FROM computadores WHERE patrimonio=?',(str(r[0] or ''),)).fetchall() if r[0] else []
                        code=matches[0]['codigo'] if len(matches)==1 else 'INV-'+uuid.uuid5(uuid.NAMESPACE_URL,dumps(r[0]) if r[0] else dumps(r)).hex
                        r=[code]+r
                    r=(r+[None]*15)[:15]
                    if not r[0]: continue
                    manual = con.execute("SELECT 1 FROM computadores p JOIN auditoria a ON a.registro=CAST(p.id AS TEXT) AND a.entidade='computador_manual' WHERE p.codigo=? COLLATE NOCASE",(str(r[0]),)).fetchone()
                    if manual: continue
                    con.execute('''INSERT INTO computadores(codigo,patrimonio,modelo,situacao,localidade,dados) VALUES(?,?,?,?,?,?) ON CONFLICT(codigo) DO UPDATE SET patrimonio=excluded.patrimonio,modelo=excluded.modelo,situacao=excluded.situacao,localidade=excluded.localidade,dados=excluded.dados''',(str(r[0]),str(r[1] or ''),r[5],r[10],r[13],dumps(r)))
            elif kind == 'sancoes':
                for r in next(iter(sheets.values()))[1:]:
                    if not r[4]: continue
                    con.execute('''INSERT INTO sancoes(numero,referencia,area,processo,status,valor,prazo,detalhes,dados) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(numero) DO UPDATE SET referencia=excluded.referencia,area=excluded.area,processo=excluded.processo,status=excluded.status,valor=excluded.valor,prazo=excluded.prazo,detalhes=excluded.detalhes,dados=excluded.dados''',(str(r[4]),r[3],r[11],r[20],r[5],r[17] if isinstance(r[17],(int,float)) else None,str(r[19] or ''),r[22],dumps(r)))
            counts[kind] = 'importado'
            wb.close()
        if (Path(root)/'Telefones.xlsx').exists():
            from telefones import import_file
            counts['telefones']=import_file(con,Path(root)/'Telefones.xlsx')
        con.execute("UPDATE computadores SET cadastro_em=? WHERE cadastro_em=''",(dt.date.today().isoformat(),))
        audit(con,'importacao','fontes',{},counts)
    return counts

def backup(con, destination):
    target = sqlite3.connect(destination)
    try: con.backup(target)
    finally: target.close()

def registration_date(value=None):
    if value is None:return dt.date.today().isoformat()
    try:return dt.date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:raise ValueError('Informe a data de cadastro na base como AAAA-MM-DD.')

def create_computer(con, values, employee_id=None,cadastro_em=None,termo='Não',data_entrega=None,data_conferencia='',componentes=''):
    if len(values) != len(COMPUTER_FIELDS)-1: raise ValueError('Preencha o formulário completo do equipamento.')
    values = ['AUTO-'+uuid.uuid4().hex]+[str(v or '').strip() for v in values]
    if values[10] not in COMPUTER_STATUSES: raise ValueError('Selecione a situação do equipamento.')
    registered=registration_date(cadastro_em)
    if termo not in ('Sim','Não'):raise ValueError('Selecione Sim ou Não para o termo.')
    delivered=registration_date(data_entrega)
    if data_conferencia:registration_date(data_conferencia)
    with con:
        in_use = values[10] == 'Em uso'
        person = con.execute('SELECT * FROM colaboradores WHERE id=?',(employee_id,)).fetchone() if employee_id else None
        if in_use and (person is None or effective(person) != 'ATIVO'):
            raise ValueError('Para a situação Em uso, selecione um colaborador ativo.')
        if not in_use and employee_id:
            raise ValueError('A destinação a um colaborador exige a situação Em uso.')
        if componentes.strip() and not person:raise ValueError('Selecione o colaborador para associar os componentes anexos.')
        cursor=con.execute('INSERT INTO computadores(codigo,patrimonio,modelo,situacao,localidade,dados) VALUES(?,?,?,?,?,?)',
                           (values[0],values[1],values[5],values[10],values[13],dumps(values)))
        pc_id=cursor.lastrowid
        generated=f'PC-{pc_id}'
        if not con.execute('SELECT 1 FROM computadores WHERE codigo=? COLLATE NOCASE',(generated,)).fetchone():
            values[0]=generated
        con.execute('UPDATE computadores SET codigo=?,dados=?,cadastro_em=? WHERE id=?',(values[0],dumps(values),registered,pc_id))
        con.execute('UPDATE computadores SET termo=? WHERE id=?',(termo,pc_id))
        audit(con,'computador_manual',pc_id,{},dict(zip(COMPUTER_FIELDS,values),cadastro_em=registered))
        if in_use:
            delivery = [values[0],values[1],values[12],values[13],'',person['nome'],person['cargo'],person['matricula'],'',delivered,'',data_conferencia,termo]
            cursor=con.execute('INSERT INTO entregas(chave,computador,colaborador,nome_origem,matricula_origem,devolucao,alerta,dados) VALUES(?,?,?,?,?,?,?,?)',
                              ('manual:'+uuid.uuid4().hex,pc_id,person['id'],person['nome'],person['matricula'],'','',dumps(delivery)))
            con.execute('UPDATE entregas SET componentes=? WHERE id=?',(componentes.strip(),cursor.lastrowid))
            audit(con,'entrega',cursor.lastrowid,{}, {'computador':pc_id,'colaborador':person['id'],'componentes':componentes.strip()})
    return pc_id

def employee_links(con, employee_id):
    """Consulta vínculos explícitos e telefonia por matrícula, sem alterar o anexo."""
    person = con.execute('SELECT * FROM colaboradores WHERE id=?', (employee_id,)).fetchone()
    if person is None: raise ValueError('Colaborador não encontrado.')
    computers = [dict(r) for r in con.execute('''SELECT e.*,p.codigo,p.patrimonio,p.modelo,p.situacao,p.cadastro_em cadastro_na_base
        FROM entregas e LEFT JOIN computadores p ON p.id=e.computador
        WHERE e.colaborador=? AND p.id NOT IN (SELECT computador FROM computadores_excluidos) ORDER BY p.codigo,e.id''', (employee_id,))]
    sanctions = [dict(r) for r in con.execute('''SELECT s.*,r.andamento,r.prazo prazo_interno,r.resposta
        FROM respostas r JOIN sancoes s ON s.id=r.sancao
        WHERE r.colaborador=? ORDER BY s.numero DESC''', (employee_id,))]
    phones = []
    headers = {}
    for r in con.execute('''SELECT o.*,f.arquivo FROM originais o JOIN fontes f ON f.id=o.fonte
        WHERE f.arquivo LIKE 'Levantamento%' ORDER BY o.fonte,o.aba,o.linha'''):
        values = json.loads(r['dados'])
        sheet = (r['fonte'], r['aba'])
        normalized = [norm(v) for v in values]
        if 'MATRICULA' in normalized:
            headers[sheet] = (values, normalized.index('MATRICULA'))
            continue
        if sheet not in headers: continue
        labels, index = headers[sheet]
        if index >= len(values) or not matricula(values[index]): continue
        if matricula(values[index]) != matricula(person['matricula']): continue
        phones.append({'arquivo':r['arquivo'], 'aba':r['aba'], 'linha':r['linha'], 'registro_id':r['registro_id'],
                       'campos':[(str(label), values[i] if i < len(values) else None)
                                 for i,label in enumerate(labels) if label is not None]})
    if con.execute("SELECT 1 FROM fontes WHERE arquivo='Telefones.xlsx'").fetchone():
        from telefones import records,FIELDS
        phones=[{'registro_id':f'TEL-{r["id"]}','aba':'Telefones','linha':r['id'],'campos':list(zip(FIELDS,r['values']))+[('Utilização','Por equipes' if r['uso_equipes'] else 'Individual'),('Equipe(s)',r['equipes']),('Data de cadastro na base',r['cadastro_em'])]}
                for r in records(con) if r['person'] and r['person']['id']==person['id']]
    return {'computadores': computers, 'celulares': phones, 'sancoes': sanctions}

def update_computer(con, pc_id, values, employee_id=None,cadastro_em=None,termo=None,data_entrega=None,data_conferencia=None,movement_day=None,movement_reason='Alteração de tutela ou situação no cadastro',movement_defect='',_commit=True,_movement=True,componentes=None):
    if len(values)!=len(COMPUTER_FIELDS)-1: raise ValueError('Formulário incompleto.')
    with con if _commit else nullcontext():
        old=con.execute('SELECT * FROM computadores WHERE id=? AND id NOT IN (SELECT computador FROM computadores_excluidos)',(pc_id,)).fetchone()
        if not old: raise ValueError('Computador não encontrado ou excluído.')
        from pc_movimentos import current,owner,log
        previous=owner(current(con,pc_id))
        previous_components=current(con,pc_id)['componentes'] if current(con,pc_id) else ''
        day=registration_date(movement_day)
        signed=termo if termo is not None else old['termo']
        if signed not in ('Sim','Não'):raise ValueError('Selecione Sim ou Não para o termo.')
        if data_entrega:registration_date(data_entrega)
        if data_conferencia:registration_date(data_conferencia)
        changed=(previous['id'] if previous else None)!=employee_id
        if previous and changed:signed='Não'
        registered=registration_date(cadastro_em if cadastro_em is not None else old['cadastro_em'] or None)
        values=[old['codigo']]+[str(v or '').strip() for v in values]
        if values[10] not in COMPUTER_STATUSES: raise ValueError('Selecione a situação do equipamento.')
        person=con.execute('SELECT * FROM colaboradores WHERE id=?',(employee_id,)).fetchone() if employee_id else None
        if values[10]=='Em uso' and (not person or effective(person)!='ATIVO'):
            raise ValueError('Selecione um colaborador ativo para o equipamento Em uso.')
        if values[10]!='Em uso' and employee_id: raise ValueError('A destinação exige a situação Em uso.')
        if componentes and componentes.strip() and not person:raise ValueError('Selecione o colaborador para associar os componentes anexos.')
        con.execute('UPDATE computadores SET patrimonio=?,modelo=?,situacao=?,localidade=?,dados=? WHERE id=?',(values[1],values[5],values[10],values[13],dumps(values),pc_id))
        con.execute('UPDATE computadores SET cadastro_em=? WHERE id=?',(registered,pc_id))
        con.execute('UPDATE computadores SET termo=? WHERE id=?',(signed,pc_id))
        audit(con,'computador_manual',pc_id,dict(old),dict(zip(COMPUTER_FIELDS,values),cadastro_em=registered))
        active=list(con.execute("SELECT * FROM entregas WHERE computador=? AND coalesce(devolucao,'')='' ORDER BY id DESC",(pc_id,)))
        kept=False
        for link in active:
            if person and link['colaborador']==person['id'] and not kept:
                kept=True
                raw=(json.loads(link['dados']) if link['dados'] else [])+['']*13
                raw=raw[:13]
                if data_entrega is not None:raw[9]=data_entrega
                if data_conferencia is not None:raw[11]=data_conferencia
                raw[12]=signed
                con.execute('UPDATE entregas SET dados=? WHERE id=?',(dumps(raw),link['id']))
                if componentes is not None:
                    con.execute('UPDATE entregas SET componentes=? WHERE id=?',(componentes.strip(),link['id']))
                    if componentes.strip()!=link['componentes']:audit(con,'entrega_componentes',link['id'],{'componentes':link['componentes']},{'componentes':componentes.strip()})
                continue
            raw=(json.loads(link['dados']) if link['dados'] else [])+['']*13;raw=raw[:13];raw[10]=day
            con.execute('UPDATE entregas SET devolucao=?,dados=? WHERE id=?',(day,dumps(raw),link['id']))
            audit(con,'entrega',link['id'],dict(link),{'devolucao':day,'motivo':movement_reason})
        if person and not kept:
            delivery=[values[0],values[1],values[12],values[13],'',person['nome'],person['cargo'],person['matricula'],'',data_entrega or day,'',data_conferencia or '',signed]
            cursor=con.execute('INSERT INTO entregas(chave,computador,colaborador,nome_origem,matricula_origem,devolucao,alerta,dados) VALUES(?,?,?,?,?,?,?,?)',('manual:'+uuid.uuid4().hex,pc_id,person['id'],person['nome'],person['matricula'],'','',dumps(delivery)))
            con.execute('UPDATE entregas SET componentes=? WHERE id=?',((componentes or '').strip(),cursor.lastrowid))
            audit(con,'entrega',cursor.lastrowid,{}, {'computador':pc_id,'colaborador':person['id'],'componentes':(componentes or '').strip()})
        if previous and changed and _movement:
            after=owner(current(con,pc_id))
            log(con,'Troca de tutela' if after else 'Devolução',pc_id,None,previous,after,movement_reason,movement_defect,values[10],{'devolvido':json.loads(old['dados']),'entregue':values if after else None,'termo_anterior':old['termo'],'componentes_anteriores':previous_components,'componentes_novos':(componentes or '').strip()},day)

def delete_computer(con, pc_id):
    with con:
        old=con.execute('SELECT * FROM computadores WHERE id=?',(pc_id,)).fetchone()
        if not old: raise ValueError('Computador não encontrado.')
        con.execute('INSERT OR IGNORE INTO computadores_excluidos VALUES(?,?)',(pc_id,dt.datetime.now().isoformat()))
        for link in con.execute("SELECT * FROM entregas WHERE computador=? AND coalesce(devolucao,'')=''",(pc_id,)).fetchall():
            con.execute('UPDATE entregas SET devolucao=? WHERE id=?',(dt.date.today().isoformat(),link['id']))
            audit(con,'entrega',link['id'],dict(link),{'motivo':'Exclusão do computador','devolucao':dt.date.today().isoformat()})
        audit(con,'computador_manual',pc_id,dict(old),{'excluido':True})

def save_response(con, sid, person, status, deadline, response):
    if deadline:
        try: dt.date.fromisoformat(deadline)
        except ValueError: raise ValueError('Informe o prazo como AAAA-MM-DD ou deixe vazio.')
    before = con.execute('SELECT * FROM respostas WHERE sancao=?',(sid,)).fetchone()
    if person:
        row = con.execute('SELECT * FROM colaboradores WHERE id=?',(person,)).fetchone()
        if not row or effective(row) != 'ATIVO':
            if not before or before['colaborador'] != person: raise ValueError('Selecione um colaborador ativo para uma nova atribuição.')
    if status == 'Respondida' and (not person or not response.strip()): raise ValueError('Para marcar como respondida, informe responsável e resposta.')
    with con:
        values = (sid,person,status,deadline,response,dt.datetime.now().isoformat(timespec='seconds'))
        con.execute('INSERT INTO respostas VALUES(?,?,?,?,?,?) ON CONFLICT(sancao) DO UPDATE SET colaborador=excluded.colaborador,andamento=excluded.andamento,prazo=excluded.prazo,resposta=excluded.resposta,atualizado=excluded.atualizado',values)
        audit(con,'resposta',sid,dict(before) if before else {},values)
