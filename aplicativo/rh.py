"""Histórico e exportação conjunta de telefonia e computadores."""
import csv
import json
from banco import audit
from movimentacoes import history as phone_history
from pc_movimentos import history as computer_history

TABLES={'TEL':'movimentos_telefones','PC':'movimentos_computadores'}


def history(con):
    result=[]
    for prefix,reader,kind in (('TEL',phone_history,'Celular / linha'),('PC',computer_history,'Computador')):
        for row in reader(con):
            result.append({**row,'prefix':prefix,'equipment':kind,'key':f'{prefix}-MOV-{row["id"]}'})
    return sorted(result,key=lambda r:(r['dia'],r.get('criado_em',''),r['key']),reverse=True)


def mark_completed(con,key):
    prefix,sep,value=key.partition('-MOV-')
    if not sep or prefix not in TABLES or not value.isdigit():raise ValueError('Movimentação inválida.')
    table=TABLES[prefix]
    with con:
        row=con.execute(f'SELECT rh_concluido FROM {table} WHERE id=?',(int(value),)).fetchone()
        if not row:raise ValueError('Movimentação não encontrada.')
        con.execute(f'UPDATE {table} SET rh_concluido=1 WHERE id=?',(int(value),))
        audit(con,'rh_movimento_'+prefix,value,{'concluido':bool(row[0])},{'concluido':True})


ASSET_FIELDS=('Patrimônio','Linha','Marca','Modelo','Nome do dispositivo','Tipo','IMEI1','IMEI2','Processador','Memória RAM','Armazenamento','Sistema operacional','Estado de conservação','Situação','Termo','Acessórios','Base','Cidade / Localização','Setor','Observações','Data de cadastro na origem')
PERSON_FIELDS=('Nome completo','Matrícula','Cargo','Base','Cidade','Estado','Telefone pessoal','origem')
HEADERS=('Movimento','Data','Equipamento','Operação','Registro anterior','Registro entregue','Motivo','Defeito','Destino','RH concluído','Ação termo antigo','Ação novo termo')+tuple('Responsável anterior: '+k for k in PERSON_FIELDS)+tuple('Novo responsável: '+k for k in PERSON_FIELDS)+tuple('Anterior: '+k for k in ASSET_FIELDS)+tuple('Entregue: '+k for k in ASSET_FIELDS)+('Componentes anteriores','Componentes entregues','Data de registro do movimento','Dados históricos completos')


def asset(values,prefix):
    if not values:return ['']*len(ASSET_FIELDS)
    v=list(values)+['']*21
    if prefix=='TEL':
        d={'Linha':v[8],'Marca':v[6],'Modelo':v[7],'IMEI1':v[9],'IMEI2':v[10],'Estado de conservação':v[12],'Situação':v[13],'Termo':v[14],'Acessórios':v[11],'Base':v[0],'Cidade / Localização':v[1],'Setor':v[2],'Observações':v[16],'Data de cadastro na origem':v[15]}
    else:
        d={'Patrimônio':v[1],'Nome do dispositivo':v[2],'Tipo':v[3],'Marca':v[4],'Modelo':v[5],'Processador':v[6],'Memória RAM':v[7],'Armazenamento':v[8],'Sistema operacional':v[9],'Situação':v[10],'Estado de conservação':v[11],'Base':v[12],'Cidade / Localização':v[13],'Observações':v[14]}
    return [d.get(k,'') for k in ASSET_FIELDS]


def report_values(row):
    snapshot=row['snapshot'];before=row['anterior'] or {};after=row['novo'] or {};prefix=row['prefix']
    no_old=snapshot.get('sem_termo_anterior',False)
    previous=asset(snapshot.get('devolvido'),prefix);delivered=asset(snapshot.get('entregue'),prefix)
    if after:
        delivered[ASSET_FIELDS.index('Situação')]='Em uso'
        delivered[ASSET_FIELDS.index('Termo')]='Não'
    if prefix=='PC':
        previous[ASSET_FIELDS.index('Termo')]=snapshot.get('termo_anterior','')
        if after:delivered[ASSET_FIELDS.index('Termo')]='Não'
    return [row['key'],row['dia'],row['equipment'],row['tipo'],f'{prefix}-{row["aparelho"]}',f'{prefix}-{row["substituto"]}' if row.get('substituto') else (f'{prefix}-{row["aparelho"]}' if after else ''),row['motivo'],row['defeito'],row['destino'],'Sim' if row['rh_concluido'] else 'Não','Sem termo anterior nesta entrega' if no_old else 'Eliminar termo antigo impresso','Elaborar novo termo de responsabilidade' if after else 'Elaborar termo de devolução']+[before.get(k,'') for k in PERSON_FIELDS]+[after.get(k,'') for k in PERSON_FIELDS]+previous+delivered+[snapshot.get('componentes_anteriores',''),snapshot.get('componentes_novos',''),row.get('criado_em',''),json.dumps(snapshot,ensure_ascii=False)]


def export_csv(path,rows):
    def safe(value):
        text=str(value if value is not None else '')
        return "'"+text if text.startswith(('=','+','-','@')) else text
    with open(path,'w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';');writer.writerow(HEADERS)
        for row in rows:writer.writerow([safe(value) for value in report_values(row)])
