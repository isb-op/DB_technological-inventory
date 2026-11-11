import csv
import datetime as dt
import json
from contextlib import nullcontext

def init(con):
    if 'termo' not in [r['name'] for r in con.execute('PRAGMA table_info(computadores)')]:
        con.execute("ALTER TABLE computadores ADD COLUMN termo TEXT NOT NULL DEFAULT 'Não'")
    con.execute('''CREATE TABLE IF NOT EXISTS movimentos_computadores(
        id INTEGER PRIMARY KEY AUTOINCREMENT, dia TEXT NOT NULL,tipo TEXT NOT NULL,
        aparelho INTEGER REFERENCES computadores(id),substituto INTEGER REFERENCES computadores(id),
        anterior TEXT NOT NULL,novo TEXT,motivo TEXT NOT NULL,defeito TEXT NOT NULL DEFAULT '',destino TEXT NOT NULL,
        snapshot TEXT NOT NULL,rh_concluido INTEGER NOT NULL DEFAULT 0,criado_em TEXT NOT NULL)''')

def current(con,pc_id):
    return con.execute("SELECT e.*,c.nome,c.matricula,c.cargo FROM entregas e LEFT JOIN colaboradores c ON c.id=e.colaborador WHERE e.computador=? AND coalesce(e.devolucao,'')='' ORDER BY e.id DESC LIMIT 1",(pc_id,)).fetchone()

def owner(link):
    if not link or not link['colaborador']:return None
    return {'id':link['colaborador'],'Nome completo':link['nome'],'Matrícula':link['matricula'],'Cargo':link['cargo'],'origem':'Dados Flex'}

def history(con,employee_id=None):
    from movimentacoes import history as phone_history
    rows=[]
    for r in con.execute('SELECT * FROM movimentos_computadores ORDER BY dia DESC,id DESC'):
        row=dict(r)
        for field in ('anterior','novo','snapshot'):row[field]=json.loads(row[field]) if row[field] else None
        if employee_id and not any(p and p.get('id')==employee_id for p in (row['anterior'],row['novo'])):continue
        rows.append(row)
    return rows

def log(con,kind,pc_id,replacement,previous,after,reason,defect,destination,snapshot,day=None):
    from banco import registration_date,dumps,audit
    if not reason.strip():raise ValueError('Informe o motivo da movimentação.')
    day=registration_date(day)
    cursor=con.execute('''INSERT INTO movimentos_computadores(dia,tipo,aparelho,substituto,anterior,novo,motivo,defeito,destino,snapshot,criado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                       (day,kind,pc_id,replacement,dumps(previous),dumps(after) if after else None,reason,defect,destination,dumps(snapshot),dt.datetime.now().isoformat()))
    audit(con,'movimento_computador',cursor.lastrowid,{}, {'computador':pc_id,'tipo':kind,'motivo':reason})
    return cursor.lastrowid

def register(con,kind,pc_id,replacement_id=None,*,day=None,reason='',defect='',destination='Estoque',recipient_id=None,componentes=None,_commit=True):
    from banco import update_computer,registration_date
    day=registration_date(day)
    if kind not in ('Devolução','Troca de computador','Troca de tutela'):raise ValueError('Operação inválida.')
    if not reason.strip():raise ValueError('Informe o motivo.')
    if reason.split(' — ')[0]=='Defeito' and not defect.strip():raise ValueError('Informe o defeito.')
    if destination not in ('Estoque','Manutenção','Defeito/Parado','Separado'):raise ValueError('Destino inválido.')
    with con if _commit else nullcontext():
        pc=con.execute('SELECT * FROM computadores WHERE id=? AND id NOT IN (SELECT computador FROM computadores_excluidos)',(pc_id,)).fetchone()
        if not pc:raise ValueError('Computador não encontrado.')
        previous=owner(current(con,pc_id))
        if not previous:raise ValueError('O computador não tem uma tutela atual para encerrar.')
        old=json.loads(pc['dados'])
        target=pc
        if kind=='Troca de computador':
            target=con.execute('SELECT * FROM computadores WHERE id=? AND id NOT IN (SELECT computador FROM computadores_excluidos)',(replacement_id,)).fetchone()
            if not target or replacement_id==pc_id or current(con,replacement_id) or target['situacao']!='Estoque':raise ValueError('Selecione outro computador disponível em estoque.')
            recipient_id=recipient_id or previous['id']
        if kind=='Troca de tutela' and recipient_id==previous['id']:raise ValueError('Selecione outro responsável.')
        if kind!='Devolução' and not recipient_id:raise ValueError('Selecione o novo responsável.')
        snapshot={'devolvido':old,'entregue':json.loads(target['dados']) if kind!='Devolução' else None,'termo_anterior':pc['termo'],'componentes_anteriores':current(con,pc_id)['componentes'],'componentes_novos':(componentes or '').strip() if kind!='Devolução' else ''}
        if kind!='Troca de tutela':
            values=old[1:15];values[9]=destination
            update_computer(con,pc_id,values,termo='Não',movement_day=day,movement_reason=reason,movement_defect=defect,_commit=False,_movement=False)
        after=None
        if kind!='Devolução':
            values=json.loads(target['dados'])[1:15];values[9]='Em uso'
            update_computer(con,target['id'],values,recipient_id,termo='Não',data_entrega=day,movement_day=day,movement_reason=reason,_commit=False,_movement=False,componentes=componentes)
            after=owner(current(con,target['id']))
        return log(con,kind,pc_id,replacement_id if kind=='Troca de computador' else None,previous,after,reason,defect,destination if kind!='Troca de tutela' else 'Em uso',snapshot,day)


def issue_from_stock(con,stock_id,*,source_id=None,replace=False,recipient_id=None,day=None,reason='',defect='',destination='Estoque',componentes='',expected_source_owner=None):
    from banco import update_computer,registration_date,dumps
    day=registration_date(day)
    if not reason.strip():raise ValueError('Informe o motivo da entrega ou troca.')
    if reason.split(' — ')[0]=='Defeito' and not defect.strip():raise ValueError('Informe o defeito do computador atual.')
    with con:
        pcs={r['id']:r for r in con.execute('SELECT * FROM computadores WHERE id NOT IN (SELECT computador FROM computadores_excluidos)')}
        target=pcs.get(stock_id);source=pcs.get(source_id)
        if not target or target['situacao']!='Estoque' or current(con,stock_id):raise ValueError('O computador escolhido não está mais disponível em estoque. Atualize a lista.')
        if source_id is not None and not source:raise ValueError('O computador atual não foi encontrado ou foi excluído.')
        previous=owner(current(con,source_id)) if source else None
        if expected_source_owner is not None and previous!=expected_source_owner:raise ValueError('A tutela do computador atual mudou. Reabra a operação para conferir os dados.')
        if replace and (not source or source_id==stock_id or not previous):raise ValueError('Selecione o computador atual do colaborador para registrar a substituição.')
        recipient_id=recipient_id or (previous['id'] if previous else None)
        if not recipient_id:raise ValueError('Selecione o colaborador que receberá o computador.')
        if replace:
            event=register(con,'Troca de computador',source_id,stock_id,day=day,reason=reason,defect=defect,destination=destination,recipient_id=recipient_id,componentes=componentes,_commit=False)
            snapshot=json.loads(con.execute('SELECT snapshot FROM movimentos_computadores WHERE id=?',(event,)).fetchone()[0])
        else:
            before=json.loads(target['dados']);values=before[1:15];values[9]='Em uso'
            update_computer(con,stock_id,values,recipient_id,termo='Não',data_entrega=day,movement_day=day,movement_reason=reason,componentes=componentes,_commit=False,_movement=False)
            snapshot={'devolvido':before,'entregue':None,'sem_termo_anterior':True,'termo_anterior':'','componentes_anteriores':'','componentes_novos':componentes.strip()}
            event=log(con,'Entrega de estoque',stock_id,None,{},owner(current(con,stock_id)),reason,defect,'Em uso',snapshot,day)
        snapshot['entregue']=json.loads(con.execute('SELECT dados FROM computadores WHERE id=?',(stock_id,)).fetchone()[0])
        con.execute('UPDATE movimentos_computadores SET snapshot=? WHERE id=?',(dumps(snapshot),event))
        return event


def export_csv(path,rows):
    def safe(value):
        text=str(value or '');return "'"+text if text.startswith(('=','+','-','@')) else text
    with open(path,'w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';')
        writer.writerow(('Movimento','Data','Operação','Nome anterior','Matrícula anterior','Novo responsável','Matrícula nova','Computador','Patrimônio anterior','Modelo anterior','Substituto','Patrimônio novo','Modelo novo','Motivo','Defeito','Destino','Termo anterior','Ação termo antigo','Ação novo termo','RH concluído','Componentes anteriores','Componentes novos'))
        for r in rows:
            old_action='Sem termo anterior nesta entrega' if r['snapshot'].get('sem_termo_anterior') else 'Eliminar termo antigo impresso'
            old=r['snapshot']['devolvido'];new=r['snapshot'].get('entregue') or ['']*15;p=r['anterior'];n=r['novo'] or {}
            writer.writerow([safe(v) for v in (r['id'],r['dia'],r['tipo'],p.get('Nome completo'),p.get('Matrícula'),n.get('Nome completo'),n.get('Matrícula'),f'PC-{r["aparelho"]}',old[1],old[5],f'PC-{r["substituto"]}' if r['substituto'] else '',new[1],new[5],r['motivo'],r['defeito'],r['destino'],r['snapshot'].get('termo_anterior',''),old_action,'Elaborar novo termo de responsabilidade' if n else 'Elaborar termo de devolução','Sim' if r['rh_concluido'] else 'Não',r['snapshot'].get('componentes_anteriores',''),r['snapshot'].get('componentes_novos',''))])
