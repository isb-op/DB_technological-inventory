"""Histórico de telefonia e controle de termos do RH."""
import csv
import datetime as dt
import json
from contextlib import nullcontext

def init(con):
    con.execute('''CREATE TABLE IF NOT EXISTS movimentos_telefones(
        id INTEGER PRIMARY KEY AUTOINCREMENT, dia TEXT NOT NULL, tipo TEXT NOT NULL,
        aparelho INTEGER REFERENCES telefones(id), substituto INTEGER REFERENCES telefones(id),
        anterior TEXT NOT NULL, novo TEXT, motivo TEXT NOT NULL, defeito TEXT NOT NULL DEFAULT '',
        destino TEXT NOT NULL, snapshot TEXT NOT NULL, rh_concluido INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT NOT NULL)''')

def custodian(row):
    if row.get('external'):return {'origem':'Outra base',**row['external']}
    p=row.get('person')
    if p:return {'id':p['id'],'Nome completo':p['nome'],'Matrícula':p['matricula'],'Cargo':p.get('cargo',''),'origem':'Dados Flex'}
    return None

def history(con,employee_id=None):
    rows=[]
    for r in con.execute('SELECT * FROM movimentos_telefones ORDER BY dia DESC,id DESC'):
        row=dict(r);row['anterior']=json.loads(row['anterior']);row['novo']=json.loads(row['novo']) if row['novo'] else None
        row['snapshot']=json.loads(row['snapshot'])
        if employee_id and not any(p and p.get('id')==employee_id for p in (row['anterior'],row['novo'])):continue
        rows.append(row)
    return rows

def log(con,kind,phone,replacement,before,after,reason,defect,destination,snapshot,day=None):
    from banco import dumps,registration_date,audit
    day=registration_date(day)
    cursor=con.execute('''INSERT INTO movimentos_telefones(dia,tipo,aparelho,substituto,anterior,novo,motivo,defeito,destino,snapshot,criado_em)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(day,kind,phone,replacement,dumps(before),dumps(after) if after else None,reason,defect,destination,dumps(snapshot),dt.datetime.now().isoformat()))
    audit(con,'movimento_telefone',cursor.lastrowid,{}, {'tipo':kind,'aparelho':phone,'anterior':before,'novo':after})
    return cursor.lastrowid

def register(con,kind,phone_id=None,replacement_id=None,*,day=None,reason='',defect='',destination='Estoque',recipient_id=None,recipient_external=None,returned_by=None,unknown=None,_commit=True):
    from telefones import records,save,validate_device_identity,phone_number
    from banco import registration_date,dumps,audit
    if kind not in ('Devolução','Troca de aparelho','Troca de tutela'):raise ValueError('Selecione o tipo de movimentação.')
    day=registration_date(day)
    if not reason.strip():raise ValueError('Informe o motivo da movimentação.')
    if reason.split(' — ')[0]=='Defeito' and not defect.strip():raise ValueError('Descreva o defeito do aparelho.')
    if destination not in ('Estoque','Quebrado','Manutenção'):raise ValueError('Selecione o destino do aparelho devolvido.')
    with con if _commit else nullcontext():
        phones={r['id']:r for r in records(con)}
        source=phones.get(phone_id)
        if phone_id and not source:raise ValueError('Aparelho não encontrado ou excluído.')
        if kind=='Troca de tutela' and not source:raise ValueError('Cadastre ou selecione o aparelho antes de trocar sua tutela.')
        previous=custodian(source) if source else None
        previous=previous or returned_by
        if not previous or not previous.get('Nome completo','').strip():raise ValueError('Informe quem está devolvendo ou transferindo o aparelho.')
        if not source:
            values=['']*17
            for i,value in (unknown or {}).items():values[int(i)]=str(value or '').strip()
            # O ID local permite cadastrar o aparelho mesmo sem modelo, linha ou IMEI.
            validate_device_identity(con,values)
            import uuid
            values[13]=destination;values[14]='Não'
            phone_id=con.execute('INSERT INTO telefones(chave,dados,manual,cadastro_em) VALUES(?,?,1,?)',('devolucao:'+uuid.uuid4().hex,dumps(values),dt.date.today().isoformat())).lastrowid
            source=next(r for r in records(con) if r['id']==phone_id)
        target=phones.get(replacement_id) if kind=='Troca de aparelho' else source
        if kind=='Troca de aparelho':
            if not target or replacement_id==phone_id:raise ValueError('Selecione outro aparelho para entregar ao colaborador.')
            if custodian(target) or target['values'][13] not in ('Estoque',''):raise ValueError('O substituto deve estar disponível em estoque, sem tutela.')
            if not recipient_id and not recipient_external:
                recipient_id=previous.get('id');recipient_external=previous if previous.get('origem')=='Outra base' else None
        if kind!='Devolução' and not recipient_id and not recipient_external:raise ValueError('Selecione quem receberá o aparelho.')
        snapshot={'devolvido':source['values'][:], 'entregue':target['values'][:] if kind!='Devolução' else None}
        if kind!='Troca de tutela':
            values=source['values'][:]
            values[3]=values[4]=values[5]='';values[13]=destination;values[14]='Não'
            con.execute('UPDATE telefones SET dados=?,colaborador=NULL,responsavel_externo=NULL,uso_equipes=0,equipes=\'\',manual=1 WHERE id=?',(dumps(values),phone_id))
            audit(con,'telefone',phone_id,source,{'devolucao':True,'destino':destination})
        after=None
        if kind!='Devolução':
            values=target['values'][:];values[13]='Em uso';values[14]='Não'
            save(con,values,recipient_id,target['id'],external=recipient_external,_commit=False,_movement=False)
            updated=next(r for r in records(con) if r['id']==target['id'])
            after=custodian(updated)
            if kind=='Troca de tutela' and previous==after:raise ValueError('Selecione um responsável diferente do atual.')
        return log(con,kind,phone_id,replacement_id if kind=='Troca de aparelho' else None,previous,after,reason.strip(),defect.strip(),destination if kind!='Troca de tutela' else 'Em uso',snapshot,day)

def issue_from_stock(con,stock_id,*,source_id=None,replace=False,recipient_id=None,recipient_external=None,day=None,reason='',defect='',destination='Estoque',move_line=False,expected_source_owner=None):
    from banco import registration_date,dumps,audit
    from telefones import records,save,validate_device_identity,phone_number
    day=registration_date(day)
    if not reason.strip():raise ValueError('Informe o motivo da entrega ou troca.')
    if reason.split(' — ')[0]=='Defeito' and not defect.strip():raise ValueError('Descreva o defeito do aparelho atual.')
    with con:
        phones={r['id']:r for r in records(con)}
        target=phones.get(stock_id);source=phones.get(source_id)
        if not target or target['values'][13].strip().casefold()!='estoque' or custodian(target):raise ValueError('O aparelho escolhido não está mais disponível em estoque. Atualize a seleção.')
        validate_device_identity(con,target['values'],stock_id,strict=True)
        previous=custodian(source) if source else None
        if expected_source_owner is not None and previous!=expected_source_owner:raise ValueError('A tutela do aparelho atual mudou. Reabra a operação para conferir os dados atualizados.')
        if not recipient_id and not recipient_external and previous:
            recipient_id=previous.get('id');recipient_external=source['external']
        if not recipient_id and not recipient_external:raise ValueError('Selecione o colaborador que receberá o aparelho.')
        if replace and (not source or source_id==stock_id or not previous):raise ValueError('Selecione o aparelho atual do colaborador para registrar a substituição.')
        if move_line and not replace:raise ValueError('A transferência de linha está disponível na substituição do aparelho atual.')
        def digits(value):return ''.join(c for c in str(value or '') if c.isdigit())
        source_line=source['values'][8] if source else ''
        target_line=target['values'][8]
        if move_line:
            if not digits(source_line):raise ValueError('O aparelho atual não possui número de linha informado.')
            if digits(target_line) and phone_number(target_line)!=phone_number(source_line):raise ValueError('O aparelho de estoque já possui outra linha. Desmarque a transferência ou regularize essa linha antes da troca.')
            conflicts=[r['id'] for r in phones.values() if r['id'] not in (source_id,stock_id) and phone_number(r['values'][8])==phone_number(source_line)]
            if conflicts:raise ValueError('A linha também consta em '+', '.join(f'TEL-{i}' for i in conflicts)+'. Confira esses vínculos antes de transferir o chip.')
        if replace:
            event=register(con,'Troca de aparelho',source_id,stock_id,day=day,reason=reason,defect=defect,destination=destination,recipient_id=recipient_id,recipient_external=recipient_external,_commit=False)
        else:
            values=target['values'][:];values[13]='Em uso';values[14]='Não'
            save(con,values,recipient_id,stock_id,external=recipient_external,_commit=False,_movement=False)
            updated=next(r for r in records(con) if r['id']==stock_id)
            event=log(con,'Entrega de estoque',stock_id,None,{},custodian(updated),reason,defect,'Em uso',{'devolvido':target['values'],'entregue':updated['values'],'sem_termo_anterior':True},day)
        if move_line:
            old=json.loads(con.execute('SELECT dados FROM telefones WHERE id=?',(source_id,)).fetchone()[0]);new=json.loads(con.execute('SELECT dados FROM telefones WHERE id=?',(stock_id,)).fetchone()[0])
            old[8]='';new[8]=source_line
            con.execute('UPDATE telefones SET dados=?,manual=1 WHERE id=?',(dumps(old),source_id))
            validate_device_identity(con,new,stock_id)
            con.execute('UPDATE telefones SET dados=?,manual=1 WHERE id=?',(dumps(new),stock_id))
            snapshot=json.loads(con.execute('SELECT snapshot FROM movimentos_telefones WHERE id=?',(event,)).fetchone()[0])
            snapshot['entregue']=new;snapshot['linha_transferida']=source_line
            con.execute('UPDATE movimentos_telefones SET snapshot=? WHERE id=?',(dumps(snapshot),event))
            audit(con,'transferencia_linha',event,{'aparelho':source_id,'linha':source_line},{'aparelho':stock_id,'linha':source_line})
        shared=bool(source['uso_equipes']) if replace else False
        teams=source['equipes'] if shared else ''
        con.execute('UPDATE telefones SET uso_equipes=?,equipes=? WHERE id=?',(int(shared),teams,stock_id))
        con.execute('UPDATE telefones SET liberacao=? WHERE id=?',(day,stock_id))
        return event

HEADERS=('Movimento','Data','Operação','Nome anterior','Matrícula anterior','Base anterior','Novo responsável','Matrícula nova','Aparelho devolvido / transferido','Modelo anterior','Linha anterior','IMEI1 anterior','IMEI2 anterior','Aparelho substituto','Modelo novo','Linha nova','IMEI1 novo','IMEI2 novo','Motivo','Defeito','Destino','Ação RH termo antigo','Ação novo termo','RH concluído')

def export_csv(path,rows):
    def safe(value):
        text=str(value or '')
        return "'"+text if text.startswith(('=','+','-','@')) else text
    with open(path,'w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';');writer.writerow(HEADERS)
        for r in rows:
            old_action='Sem termo anterior nesta entrega' if r['snapshot'].get('sem_termo_anterior') else 'Eliminar termo antigo impresso'
            p=r['anterior'];n=r['novo'] or {};old=r['snapshot']['devolvido'];new=r['snapshot'].get('entregue') or ['']*17
            writer.writerow([safe(v) for v in (r['id'],r['dia'],r['tipo'],p.get('Nome completo'),p.get('Matrícula'),p.get('Base'),n.get('Nome completo'),n.get('Matrícula'),f'TEL-{r["aparelho"]}',old[7],old[8],old[9],old[10],f'TEL-{r["substituto"]}' if r['substituto'] else '',new[7],new[8],new[9],new[10],r['motivo'],r['defeito'],r['destino'],old_action,'Elaborar novo termo para responsável atual' if n else 'Elaborar termo de devolução','Sim' if r['rh_concluido'] else 'Não')])
