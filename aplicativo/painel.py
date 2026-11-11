"""Indicadores de tutelas atuais; consultas sem alteração de dados."""
import csv
import json
from banco import effective,norm,matricula
from telefones import records as phone_records

def normalized(value):return ' '.join(norm(value).split())

def overview(con):
    people={p['id']:dict(p) for p in con.execute('SELECT * FROM colaboradores')}
    active={key for key,p in people.items() if effective(p)=='ATIVO'}
    phones=phone_records(con)
    known_external_ids={}
    for row in phones:
        ext=row['external']
        if ext:
            key=(normalized(ext.get('Base')),normalized(ext.get('Nome completo')))
            number=matricula(ext.get('Matrícula')) or normalized(ext.get('Matrícula'))
            if number:known_external_ids.setdefault(key,set()).add(number)
    groups={};assets=[]
    def add(kind,record,values,person=None,external=None,issue=''):
        rid=record['id'];status=values[13] if kind=='celular' else record['situacao']
        if not person and not external and normalized(status) not in ('EM USO','TRANSFERIDO'):return
        if person:
            owner_key=f'interno:{person["id"]}';category='Ativo' if person['id'] in active else 'Desligado' if effective(person)=='DESLIGADO' else 'Outro vínculo RH'
            name=person['nome'];mat=person['matricula']
        elif external:
            base=normalized(external.get('Base'));name=normalized(external.get('Nome completo'))
            number=matricula(external.get('Matrícula')) or normalized(external.get('Matrícula'))
            known=known_external_ids.get((base,name),set())
            if not number and len(known)==1:number=next(iter(known))
            identity=(base,number or name)
            owner_key='externo:'+repr(identity);category='Outra base';name=external['Nome completo'];mat=external.get('Matrícula','')
        else:
            owner_key=f'sem_tutela:{kind}:{rid}';category='Sem tutela';name=values[3] if kind=='celular' else ''
            name=name or 'Responsável não identificado';mat=values[5] if kind=='celular' else ''
            issue=issue or 'Identificar / confirmar o responsável pela tutela'
        if normalized(status) in ('ESTOQUE','DESCARTADO') and (person or external):issue='Conferir situação do equipamento com tutela ativa'
        term=values[14] if kind=='celular' else record['termo'];signed=normalized(term)=='SIM'
        g=groups.setdefault(owner_key,{'key':owner_key,'nome':name,'matricula':mat,'grupo':category,'person_id':person['id'] if person else None,'assets':[]})
        asset={'kind':kind,'id':rid,'registro':('TEL-' if kind=='celular' else 'PC-')+str(rid),'responsavel':name,'matricula':mat,'grupo':category,'owner_key':owner_key,
               'identificacao':values[8] if kind=='celular' else record['patrimonio'], 'modelo':values[7] if kind=='celular' else record['modelo'],
               'base':values[0] if kind=='celular' else values[12], 'cidade':values[1] if kind=='celular' else record['localidade'],
               'status':status,'termo':term or 'Não informado','signed':signed,'issue':issue}
        g['assets'].append(asset);assets.append(asset)
    for row in phones:add('celular',row,row['values'],row['person'],row['external'])
    links={}
    for row in con.execute("SELECT * FROM entregas WHERE coalesce(devolucao,'')='' "):links.setdefault(row['computador'],[]).append(row)
    for row in con.execute('SELECT * FROM computadores WHERE id NOT IN (SELECT computador FROM computadores_excluidos)'):
        v=(json.loads(row['dados']) if row['dados'] else [])+['']*15;delivery=links.get(row['id'],[])
        person=people.get(delivery[0]['colaborador']) if len(delivery)==1 else None
        add('computador',row,v,person,issue='Múltiplas tutelas ativas; conferir vínculo' if len(delivery)>1 else '')
    for g in groups.values():
        g['celulares']=sum(a['kind']=='celular' for a in g['assets'])
        g['computadores']=sum(a['kind']=='computador' for a in g['assets'])
        g['assinados']=sum(a['signed'] for a in g['assets'])
        g['pendentes']=sum(not a['signed'] for a in g['assets'])
        g['conferir']=sum(bool(a['issue']) for a in g['assets'])
        g['regular']=g['pendentes']==0 and g['conferir']==0
    internal=[g for g in groups.values() if g['grupo']=='Ativo']
    with_phone={g['person_id'] for g in internal if g['celulares']}
    with_line={g['person_id'] for g in internal if any(a['kind']=='celular' and any(c.isdigit() for c in str(a['identificacao'] or '')) for a in g['assets'])}
    with_pc={g['person_id'] for g in internal if g['computadores']}
    covered={g['person_id'] for g in internal}
    metrics={'ativos':len(active),'com_celular':len(with_phone),'com_linha':len(with_line),'com_computador':len(with_pc),
             'regularizados':sum(g['regular'] for g in internal),'pendentes':sum(not g['regular'] for g in internal),'sem_equipamento':len(active-covered),
             'externos':sum(g['grupo']=='Outra base' for g in groups.values()),'externos_pendentes':sum(g['grupo']=='Outra base' and not g['regular'] for g in groups.values()),
             'desligados':sum(g['grupo']=='Desligado' for g in groups.values()),'sem_tutela':sum(g['grupo']=='Sem tutela' for g in groups.values()),
             'termos_pendentes':sum(not a['signed'] for a in assets)}
    assert metrics['regularizados']+metrics['pendentes']+metrics['sem_equipamento']==metrics['ativos']
    return {'metrics':metrics,'groups':sorted(groups.values(),key=lambda g:(g['regular'],normalized(g['nome']))),'assets':assets}

def export_pending(path,assets):
    columns=('Responsável','Matrícula','Grupo','Registro','Tipo','Linha / Patrimônio','Modelo','Base','Cidade','Situação','Termo','Acompanhamento')
    def safe(value):
        s=str(value or '');return "'"+s if s.startswith(('=','+','-','@')) else s
    with open(path,'w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';');writer.writerow(columns)
        for a in assets:
            if a['signed'] and not a['issue']:continue
            writer.writerow([safe(v) for v in (a['responsavel'],a['matricula'],a['grupo'],a['registro'],a['kind'],a['identificacao'],a['modelo'],a['base'],a['cidade'],a['status'],a['termo'],a['issue'] or 'Obter e registrar termo assinado')])
