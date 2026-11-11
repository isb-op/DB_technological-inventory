"""Busca nos campos cadastrados e nos vínculos atuais, sem alterar a base."""
import json
from collections import defaultdict
from banco import norm,effective
from telefones import records as phone_records

PHONE_TAB='Aparelhos e Linhas telefônicas'


def values_from_json(value):
    if not value:return []
    try:return json.loads(value)
    except (ValueError,TypeError):return [value]


def flatten(value):
    if isinstance(value,dict):
        for item in value.values():yield from flatten(item)
    elif isinstance(value,(list,tuple)):
        for item in value:yield from flatten(item)
    elif value is not None:yield str(value)


def searchable(parts):
    result=[]
    for item in flatten(parts):
        result.append(norm(item))
        # Números formatados também podem ser buscados só com dígitos.
        if any(c.isdigit() for c in item) and not any(c.isalpha() for c in item):
            result.append(''.join(c for c in item if c.isdigit()))
    return ' '.join(' '.join(result).split())


def matches(query,content):
    query=' '.join(norm(query).split())
    if not query:return True
    if any(c.isdigit() for c in query) and not any(c.isalpha() for c in query):
        return ''.join(c for c in query if c.isdigit()) in content
    return all(part in content for part in query.split())


def build_search_index(con):
    people={r['id']:dict(r) for r in con.execute('SELECT * FROM colaboradores')}
    computers={r['id']:dict(r) for r in con.execute('SELECT * FROM computadores WHERE id NOT IN (SELECT computador FROM computadores_excluidos)')}
    phones=phone_records(con)
    own_people={key:[f'COL-{key}',*[p.get(k) for k in ('matricula','nome','cargo','localidade','situacao_fonte','situacao_manual','desligamento')],effective(p),values_from_json(p.get('dados'))] for key,p in people.items()}
    own_pc={key:[f'PC-{key}',*[p.get(k) for k in ('codigo','patrimonio','modelo','situacao','localidade','termo','cadastro_em')],values_from_json(p.get('dados'))] for key,p in computers.items()}
    own_phone={r['id']:[f'TEL-{r["id"]}',r['values'],r.get('external'),*[r.get(k) for k in ('equipes','estado','data_chegada','cadastro_em','liberacao','conferencia','situacao_colaborador')],'Por equipes' if r['uso_equipes'] else 'Individual'] for r in phones}
    # Uma pessoa pode ter vários aparelhos. Só os vínculos vigentes participam.
    groups={('interno',key):[parts] for key,parts in own_people.items()}
    phone_group={};pc_groups=defaultdict(list)
    for row in phones:
        key=row['id'];person=row.get('person');external=row.get('external')
        if person:group=('interno',person['id'])
        elif external:group=('externo',*(norm(external.get(k)) for k in ('Nome completo','Matrícula','Base','Cidade','Estado')))
        else:continue
        phone_group[key]=group;groups.setdefault(group,[]).append(own_phone[key])
    for row in con.execute("SELECT * FROM entregas WHERE coalesce(devolucao,'')='' ORDER BY id"):
        key=row['computador'];owner=row['colaborador']
        if key not in own_pc:continue
        delivery=[row['nome_origem'],row['matricula_origem'],row['componentes'],values_from_json(row['dados'])]
        own_pc[key].append(delivery)
        group=('interno',owner)
        if owner in people:
            pc_groups[key].append(group);groups[group].append(own_pc[key])
    texts={key:searchable(parts) for key,parts in groups.items()}
    return {
        'Colaboradores':{key:texts[('interno',key)] for key in own_people},
        'Computadores':{key:searchable(parts)+' '+ ' '.join(texts[g] for g in dict.fromkeys(pc_groups[key])) for key,parts in own_pc.items()},
        PHONE_TAB:{key:searchable(parts)+' '+texts.get(phone_group.get(key),'') for key,parts in own_phone.items()},
    }
