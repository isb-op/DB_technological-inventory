from visual import apply_theme,AnimatedCat,BG,GREEN,PINK
from selecoes import SearchCombobox
from busca import build_search_index,matches
import csv
import datetime as dt
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from banco import ROOT, DB, connect, import_sources, effective, audit, backup, save_response, norm, employee_links, COMPUTER_FIELDS, COMPUTER_STATUSES, create_computer, update_computer, delete_computer

from telefones import FIELDS as PHONE_FIELDS, STATUSES as PHONE_STATUSES, records as phone_records, save as save_phone, delete as delete_phone
from telefones import EXTERNAL_FIELDS, STATES
from movimentacoes_ui import MovementUI
from painel_ui import DashboardUI
from estoque_ui import StockIssueUI
from telefones import DuplicatePhone
from destaques import IdAlertTree,phone_identity_issue,computer_identity_issue

PHONE_TAB='Aparelhos e Linhas telefônicas'

class App(StockIssueUI,DashboardUI,MovementUI,tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Inventário Tecnológico')
        self.geometry('1280x780'); self.minsize(1000,620)
        self.term_generation_available=(ROOT/'aplicativo'/'termos.py').is_file() and (ROOT/'modelos'/'Ficha_de_Controle_Individual_Equipamentos.docx').is_file()
        self.con = connect()
        self.protocol('WM_DELETE_WINDOW',self.close)
        style = ttk.Style(self); style.theme_use('clam')
        style.configure('Treeview',rowheight=29,font=('Consolas',10))
        style.configure('Treeview.Heading',font=('Consolas',10,'bold'),background='#e6edf5')
        style.configure('TButton',padding=8); style.configure('TLabel',font=('Consolas',10))
        apply_theme(self)
        head = tk.Frame(self,bg='#000000',padx=24,pady=18); head.pack(fill='x')
        tk.Label(head,text='INVENTÁRIO TECNOLÓGICO',bg='#000000',fg='#ff49c8',font=('Consolas',21,'bold')).pack(anchor='w')
        tk.Label(head,text='Colaboradores, computadores, aparelhos e linhas telefônicas',bg='#000000',fg='#79ff87',font=('Consolas',11)).pack(anchor='w')
        bar=ttk.Frame(self,padding=10); bar.pack(fill='x')
        ttk.Button(bar,text='Atualizar das planilhas',command=self.import_data).pack(side='left')
        ttk.Button(bar,text='Criar backup',command=self.make_backup).pack(side='left',padx=8)
        ttk.Button(bar,text='Exportar consulta CSV',command=self.export).pack(side='left')
        ttk.Button(bar,text='Histórico / RH',command=self.movements_window).pack(side='left',padx=8)
        if self.term_generation_available:
            ttk.Button(bar,text='Gerar termo',command=self.generate_term).pack(side='left')
        self.summary=ttk.Label(bar); self.summary.pack(side='right')
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill='both',expand=True,padx=12,pady=4)
        self.views={}
        self.build_dashboard()
        specs=[('Colaboradores',('Matrícula','Nome','Cargo','Localidade','Situação')),('Computadores',('Patrimônio','Nome do dispositivo','Tipo','Marca','Modelo','Processador','Memória RAM','Armazenamento','Sistema operacional','Situação','Termo de responsabilidade')),(PHONE_TAB,('Número de Telefone','Marca','Modelo do Telefone','IMEI1','IMEI2','Estado de conservação','Termo de responsabilidade','Status do aparelho'))]
        for name,cols in specs:
            frame=ttk.Frame(self.tabs,padding=8); self.tabs.add(frame,text=name)
            toolbar=ttk.Frame(frame); toolbar.pack(fill='x',pady=(0,8))
            ttk.Label(toolbar,text='Pesquisar em todos os dados:').pack(side='left')
            query=tk.StringVar(); entry=ttk.Entry(toolbar,textvariable=query,width=40); entry.pack(side='left',padx=6)
            filt=tk.StringVar(value='ATIVO' if name=='Colaboradores' else 'Todos')
            if name=='Colaboradores': options=['Todos','ATIVO','DESLIGADO','Situação divergente']
            elif name==PHONE_TAB: options=['Todos']+list(PHONE_STATUSES)+['Sem correspondência','Relacionados','DESLIGADO']
            elif name=='Computadores': options=['Todos']+list(COMPUTER_STATUSES)
            elif name=='Sanções': options=['Todos','Sem responsável','Pendente','Em análise','Respondida','Vencidas']
            else: options=['Todos']
            combo=SearchCombobox(toolbar,textvariable=filt,values=options,state='readonly',width=23);combo.pack(side='left')
            query.trace_add('write',lambda *_,n=name:self.refresh_view(n));combo.bind('<<ComboboxSelected>>',lambda e,n=name:self.refresh_view(n))
            actions=ttk.Frame(frame);actions.pack(fill='x',pady=(0,8))
            ttk.Button(actions,text='Abrir / editar selecionado',command=lambda n=name:self.open_row(n)).pack(side='right')
            if name=='Vínculos e pendências':
                ttk.Button(actions,text='Novo vínculo',command=self.new_assignment).pack(side='right',padx=6)
            if name=='Computadores':
                ttk.Button(actions,text='Novo computador',command=self.new_computer).pack(side='left')
                ttk.Button(actions,text='Entregar / trocar computador',command=self.issue_selected_computer).pack(side='left',padx=6)
            if name==PHONE_TAB:
                ttk.Button(actions,text='Novo aparelho / linha',command=self.phone_editor).pack(side='left')
                ttk.Button(actions,text='Entregar / trocar aparelho',command=self.issue_selected_phone).pack(side='left',padx=6)
            area=ttk.Frame(frame); area.pack(fill='both',expand=True)
            cols=('ID do registro',)+cols
            tree=IdAlertTree(area,columns=cols,selectmode='browse')
            vs=ttk.Scrollbar(area,orient='vertical',command=tree.yview); hs=ttk.Scrollbar(area,orient='horizontal',command=tree.xview)
            tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
            tree.grid(row=0,column=0,sticky='nsew');vs.grid(row=0,column=1,sticky='ns');hs.grid(row=1,column=0,sticky='ew');area.rowconfigure(0,weight=1);area.columnconfigure(0,weight=1)
            for col in cols:tree.heading(col,text=col);tree.column(col,width=180 if col not in ('Nome','Responsável','Conferência') else 300,minwidth=100)
            tree.bind('<Double-1>',lambda e,n=name:self.open_row(n))
            count=ttk.Label(frame);count.pack(anchor='w',pady=6)
            self.views[name]={'frame':frame,'tree':tree,'query':query,'filter':filt,'count':count,'rows':{}}
        footer=ttk.Frame(self,padding=(14,4),height=88)
        footer.pack(side='bottom',fill='x',before=self.tabs)
        footer.pack_propagate(False)
        self.cat=AnimatedCat(footer,ROOT/'aplicativo'/'assets'/'gatinho.gif');self.cat.pack(side='right',anchor='se',padx=(8,0),pady=4)
        ttk.Label(footer,text='Dados locais • Duplo clique para editar • Planilhas preservadas',wraplength=720).pack(side='left',anchor='w')
        if not self.con.execute('SELECT 1 FROM fontes').fetchone(): self.after(150,self.import_data)
        self.refresh()
        self.tabs.bind('<<NotebookTabChanged>>',lambda e:self.refresh_dashboard() if self.tabs.tab(self.tabs.select(),'text')=='Início' else None)

    def close(self): self.con.close();self.destroy()

    def generate_term(self):
        if not self.term_generation_available:
            messagebox.showinfo('Termos','A geração de termos não está disponível nesta versão.');return
        from termos import payload,generate
        name=self.tabs.tab(self.tabs.select(),'text')
        if name not in ('Computadores',PHONE_TAB):
            messagebox.showinfo('Gerar termo','Selecione um computador ou aparelho / linha na aba correspondente.');return
        selection=self.views[name]['tree'].selection()
        if not selection:
            messagebox.showinfo('Gerar termo','Selecione o equipamento para gerar o termo.');return
        kind='computador' if name=='Computadores' else 'celular';key=int(selection[0])
        try:data=payload(self.con,kind,key)
        except Exception as e:messagebox.showerror('Gerar termo',str(e));return
        day=simpledialog.askstring('Data de entrega','Data de entrega para o termo (AAAA-MM-DD). As datas de assinatura permanecerão em branco.',initialvalue=dt.date.today().isoformat(),parent=self)
        if day is None:return
        folder=ROOT/'termos_gerados';folder.mkdir(exist_ok=True)
        path=filedialog.asksaveasfilename(title='Salvar termo para impressão',initialdir=folder,initialfile=f'Termo_{data["id"]}_{dt.date.today()}.docx',defaultextension='.docx',filetypes=[('Documento Word','*.docx')])
        if not path:return
        try:generate(self.con,kind,key,path,day)
        except Exception as e:messagebox.showerror('Gerar termo',str(e));return
        messagebox.showinfo('Termo gerado','Termo salvo com assinaturas e vistos em branco. Abra no Word para conferir e imprimir. A geração não altera a confirmação de termo assinado.')
        try:os.startfile(path)
        except OSError:pass

    def refresh(self):
        people=list(self.con.execute('SELECT * FROM colaboradores'))
        active=sum(effective(p)=='ATIVO' for p in people)
        self.summary.config(text=f'{active} ativos   /   {len(self.records(PHONE_TAB))} aparelhos e linhas')
        for name in self.views:self.refresh_view(name)
        self.refresh_dashboard()

    def records(self,name):
        if name==PHONE_TAB:
            return [(r['id'],[r['values'][i] for i in (8,6,7,9,10,12,14,13)],r) for r in phone_records(self.con)]
        if name=='Colaboradores':
            return [(r['id'],[r['matricula'],r['nome'],r['cargo'],r['localidade'],effective(r)],dict(r)) for r in self.con.execute('SELECT * FROM colaboradores ORDER BY nome')]
        if name=='Computadores':
            rows=[]
            for r in self.con.execute('SELECT * FROM computadores WHERE id NOT IN (SELECT computador FROM computadores_excluidos) ORDER BY id'):
                data=(json.loads(r['dados']) if r['dados'] else [])+[None]*15
                values=[r['patrimonio'],data[2],data[3],data[4],r['modelo'],data[6],data[7],data[8],data[9],r['situacao'],r['termo']]
                rows.append((r['id'],values,dict(r)))
            return rows
        if name=='Vínculos e pendências':
            out=[]
            for r in self.con.execute('SELECT e.*,p.codigo,c.nome,c.situacao_fonte,c.situacao_manual,c.desligamento FROM entregas e LEFT JOIN computadores p ON p.id=e.computador LEFT JOIN colaboradores c ON c.id=e.colaborador WHERE p.id NOT IN (SELECT computador FROM computadores_excluidos) ORDER BY p.codigo'):
                alert=r['alerta'] or ''
                if r['colaborador'] and effective(r)=='DESLIGADO' and not r['devolucao']: alert+='; Desligado com devolução pendente'
                out.append((r['id'],[r['codigo'],r['nome'] or r['nome_origem'],r['matricula_origem'],r['devolucao'],alert.strip('; ')],dict(r)))
            return out
        if name=='Sanções':
            return [(r['id'],[r['numero'],r['area'],r['processo'],r['status'],f'{r["valor"]:,.2f}' if r['valor'] is not None else '',r['nome'] or '',r['andamento'] or 'Pendente',r['prazo_interno'] or ''],dict(r)) for r in self.con.execute('SELECT s.*,r.colaborador,r.andamento,r.prazo prazo_interno,r.resposta,c.nome FROM sancoes s LEFT JOIN respostas r ON r.sancao=s.id LEFT JOIN colaboradores c ON c.id=r.colaborador ORDER BY s.numero DESC')]
        return [(f'{r["fonte"]}:{r["aba"]}',[r['arquivo'],r['aba'],r['total']],dict(r)) for r in self.con.execute('SELECT f.arquivo,o.fonte,o.aba,count(*) total FROM originais o JOIN fontes f ON f.id=o.fonte GROUP BY o.fonte,o.aba ORDER BY f.arquivo,o.aba')]

    def refresh_view(self,name):
        if name not in self.views:return
        v=self.views[name]; tree=v['tree'];tree.delete(*tree.get_children()); v['rows']={}
        q=norm(v['query'].get()); f=v['filter'].get()
        search_index=build_search_index(self.con).get(name,{}) if q else {}
        for key,values,row in self.records(name):
            record_id=self.record_id(name,key)
            if q and not matches(q,search_index.get(key, norm(' '.join(str(x or '') for x in [record_id]+values)))):continue
            if name==PHONE_TAB:
                if f in PHONE_STATUSES and norm(row['values'][13])!=norm(f):continue
                if f=='Sem correspondência' and (row['person'] or row.get('external')):continue
                if f=='Relacionados' and not (row['person'] or row.get('external')):continue
                if f=='DESLIGADO' and row['situacao_colaborador']!='DESLIGADO':continue
            if name=='Computadores' and f in COMPUTER_STATUSES and norm(row['situacao'])!=norm(f):continue
            if name=='Colaboradores':
                if f in ('ATIVO','DESLIGADO') and effective(row)!=f:continue
                if f=='Situação divergente' and norm(row['situacao_fonte'])==norm(effective(row)):continue
            if name=='Vínculos e pendências' and f=='Com pendência' and not values[-1]:continue
            if name=='Sanções':
                if f=='Sem responsável' and row['colaborador']:continue
                if f in ('Pendente','Em análise','Respondida') and values[6]!=f:continue
                if f=='Vencidas' and not (values[7] and values[7]<dt.date.today().isoformat() and values[6]!='Respondida'):continue
            v['rows'][str(key)]=(values,row)
            alert=(name==PHONE_TAB and phone_identity_issue(row)) or (name=='Computadores' and computer_identity_issue(self.con,key))
            tree.insert('', 'end',iid=str(key),values=[record_id]+[x if x is not None else '' for x in values])
            tree.set_id_alert(str(key),record_id,alert)
        v['count'].config(text=f'{len(v["rows"])} registros exibidos')

    def record_id(self,name,key):
        prefix={'Colaboradores':'COL','Computadores':'PC','Vínculos e pendências':'VIN','Sanções':'SAN','Anexos':'ABA',PHONE_TAB:'TEL'}[name]
        return f'{prefix}-{key}'

    def import_data(self):
        try:
            if self.con.execute('SELECT 1 FROM fontes').fetchone():
                folder=ROOT/'backups';folder.mkdir(exist_ok=True)
                backup(self.con,folder/f'antes_importacao_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3')
            result=import_sources(self.con);self.refresh()
            messagebox.showinfo('Importação concluída','\n'.join(f'{k}: {v}' for k,v in result.items())+'\n\nSituações manuais e respostas foram preservadas. Registros ausentes nas novas fontes continuam no histórico.')
        except Exception as e:messagebox.showerror('Não foi possível importar',str(e))

    def make_backup(self):
        path=filedialog.asksaveasfilename(title='Salvar backup',defaultextension='.sqlite3',initialfile=f'gestao_{dt.date.today()}.sqlite3')
        if path:
            try:
                if os.path.abspath(path)==str(DB.resolve()):raise ValueError('Escolha um arquivo diferente do banco em uso.')
                backup(self.con,path);messagebox.showinfo('Backup','Backup criado com sucesso.')
            except Exception as e:messagebox.showerror('Backup',str(e))

    def export(self):
        name=self.tabs.tab(self.tabs.select(),'text')
        if name=='Início':return self.dashboard_export()
        v=self.views[name]
        path=filedialog.asksaveasfilename(defaultextension='.csv',initialfile=f'{name}.csv')
        if path:
            try:
                with open(path,'w',encoding='utf-8-sig',newline='') as file:
                    writer=csv.writer(file,delimiter=';');writer.writerow(v['tree']['columns'])
                    for key,(values,_) in v['rows'].items():writer.writerow([self.record_id(name,key)]+["'"+str(x) if str(x or '').startswith(('=','+','-','@')) else x for x in values])
                messagebox.showinfo('Exportação','Consulta exportada.')
            except Exception as e:messagebox.showerror('Exportação',str(e))

    def window(self,title):
        win=tk.Toplevel(self);win.configure(background=BG);win.title(title);win.geometry('920x700');win.transient(self)
        body=ttk.Frame(win,padding=18);body.pack(fill='both',expand=True)
        return win,body

    def field(self,parent,label,value='',options=None):
        ttk.Label(parent,text=label).pack(anchor='w',pady=(8,3));var=tk.StringVar(value=value or '')
        widget=SearchCombobox(parent,textvariable=var,values=options,state='readonly') if options is not None else ttk.Entry(parent,textvariable=var)
        widget.pack(fill='x');return var

    def detail(self,parent,text,height=13):
        area=ttk.Frame(parent);area.pack(fill='both',expand=True,pady=8)
        box=tk.Text(area,background=BG,foreground=GREEN,insertbackground=PINK,selectbackground='#38203e',wrap='word',font=('Consolas',10),height=height);scroll=ttk.Scrollbar(area,command=box.yview)
        box.configure(yscrollcommand=scroll.set);box.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y');box.insert('1.0',text);box.configure(state='disabled')

    def source_detail(self,row,table):
        if not row.get('dados'):return ''
        data=json.loads(row['dados'])
        pattern={'colaboradores':'DADOS%','computadores':'Inventário%','sancoes':'Sistema%','entregas':'Inventário%'}[table]
        sheet={'colaboradores':'Sheet1','computadores':'Identificação&Configuração','sancoes':'Sheet1','entregas':'Responsável'}[table]
        header=self.con.execute('SELECT o.dados FROM originais o JOIN fontes f ON f.id=o.fonte WHERE f.arquivo LIKE ? AND o.aba=? AND o.linha=1',(pattern,sheet)).fetchone()
        labels=list(COMPUTER_FIELDS) if table=='computadores' else (json.loads(header[0]) if header else [])
        return '\n\n'.join(f'{labels[i] if i<len(labels) and labels[i] else "Campo "+str(i+1)}: {value if value is not None else ""}' for i,value in enumerate(data))

    def open_row(self,name):
        selected=self.views[name]['tree'].selection()
        if not selected:return
        key=selected[0];values,row=self.views[name]['rows'][key]
        win,body=self.window(f'{name} — {values[0]}')
        if name=='Colaboradores':
            ttk.Label(body,text=f'{row["nome"]} — Matrícula {row["matricula"]}',font=('Consolas',13,'bold')).pack(anchor='w')
            state=self.field(body,'Situação manual (Automático usa situação e data de desligamento da fonte)',row['situacao_manual'] or 'Automático',['Automático','ATIVO','DESLIGADO'])
            self.employee_notebook(body,row)
            def save():
                value=None if state.get()=='Automático' else state.get()
                with self.con:
                    self.con.execute('UPDATE colaboradores SET situacao_manual=? WHERE id=?',(value,key));audit(self.con,'colaborador',key,row,{'situacao_manual':value})
                win.destroy();self.refresh()
            ttk.Button(body,text='Salvar situação',command=save).pack(anchor='e')
        elif name=='Sanções':self.sanction_editor(win,body,key,row)
        elif name=='Vínculos e pendências':self.assignment_editor(win,body,key,row)
        elif name=='Computadores': self.new_computer(row,win,body)
        elif name==PHONE_TAB:self.phone_editor(row,win,body)
        else:
            if row['arquivo'].startswith('Levantamento'):
                ttk.Label(body,text='Telefonia mantida como anexo, sem vínculos automáticos com colaboradores.').pack(anchor='w')
            ttk.Button(body,text='Abrir planilha original',command=lambda:os.startfile(ROOT/row['arquivo'])).pack(anchor='w')
            rows=self.con.execute('SELECT linha,dados FROM originais WHERE fonte=? AND aba=? ORDER BY linha',(row['fonte'],row['aba'])).fetchall()
            ids={r['linha']:r['registro_id'] for r in self.con.execute('SELECT linha,registro_id FROM originais WHERE fonte=? AND aba=?',(row['fonte'],row['aba']))}
            self.detail(body,'\n\n'.join(f'ID {ids[r[0]]} — Linha {r[0]}: '+ ' | '.join(str(x or '') for x in json.loads(r[1])) for r in rows))

    def employee_notebook(self,body,row):
        links=employee_links(self.con,row['id'])
        ttk.Label(body,text=f'{len(links["computadores"])} vínculos de computadores  |  {len(links["celulares"])} registros de telefonia').pack(anchor='w',pady=10)
        tabs=ttk.Notebook(body);tabs.pack(fill='both',expand=True,pady=8)
        def tab(title,text):
            frame=ttk.Frame(tabs,padding=8);tabs.add(frame,text=title);self.detail(frame,text)
        tab('Cadastro',self.source_detail(row,'colaboradores'))
        computers=[]
        for pc in links['computadores']:
            data=json.loads(pc['dados']) if pc['dados'] else []
            computers.append('\n'.join([
                f'Equipamento: {pc["codigo"] or "Não encontrado"} | Patrimônio: {pc["patrimonio"] or "Não informado"}',
                f'Modelo: {pc["modelo"] or "Não informado"} | Situação do equipamento: {pc["situacao"] or "Não informada"}',
                f'Data de cadastro na base: {pc["cadastro_na_base"] or "Não informada"}',
                f'Termo de responsabilidade deste vínculo: {data[12] if len(data)>12 else "Não informado"}',
                f'Componentes anexos: {pc["componentes"] or "Nenhum informado"}',
                f'Entrega: {data[9] if len(data)>9 and data[9] else "Não informada"}',
                f'Devolução: {pc["devolucao"] or "Não registrada — vínculo em aberto"}',
                f'Conferência: {pc["alerta"] or "Sem pendências registradas"}',
                'Desligado com devolução pendente' if effective(row)=='DESLIGADO' and not pc['devolucao'] else ''
            ]))
        tab(f'Computadores ({len(computers)})','\n\n────────────────────\n\n'.join(computers) or 'Nenhum computador vinculado a este colaborador.')
        from pc_movimentos import history as pc_history
        pc_events=pc_history(self.con,row['id'])
        tab(f'Histórico de computadores ({len(pc_events)})','\n\n'.join(f'{m["dia"]} — {m["tipo"]} | PC-{m["aparelho"]}\nMotivo: {m["motivo"]}\nDefeito: {m["defeito"] or "Não se aplica"}\nDestino: {m["destino"]}' for m in pc_events) or 'Nenhuma movimentação registrada.')
        phones=[]
        for phone in links['celulares']:
            phones.append(f'ID {phone["registro_id"]} — {phone["aba"]} — linha {phone["linha"]}\n'+ '\n'.join(f'{label}: {value if value is not None else "Não informado"}' for label,value in phone['campos']))
        tab(f'Celulares ({len(phones)})','Consulta de Telefones por matrícula ou nome exato único.\nRegistros de devolução e avarias são históricos; não representam necessariamente posse atual.\n\n'+ ('\n\n────────────────────\n\n'.join(phones) or 'Nenhum registro de telefonia com esta matrícula. Registros sem matrícula não são associados automaticamente.'))
        from movimentacoes import history
        movements=history(self.con,row['id'])
        text='\n\n'.join(f'{m["dia"]} — {m["tipo"]}\nAparelho: TEL-{m["aparelho"]} | Substituto: {m["substituto"] or "Não houve"}\nMotivo: {m["motivo"]}\nDefeito: {m["defeito"] or "Não informado / não se aplica"}\nRH: {"Tratado" if m["rh_concluido"] else "Pendente"}' for m in movements)
        tab(f'Histórico de telefonia ({len(movements)})',text or 'Nenhuma troca, devolução ou transferência registrada.')
    def issue_selected_computer(self):
        from estoque_computadores_ui import open_window
        selected=self.views['Computadores']['tree'].selection()
        open_window(self,int(selected[0]) if selected else None)

    def issue_selected_phone(self):
        selected=self.views[PHONE_TAB]['tree'].selection()
        row=next((r for r in phone_records(self.con) if selected and str(r['id'])==selected[0]),None)
        self.stock_phone_window(row)

    def phone_editor(self,row=None,win=None,body=None):
        if win is None:win,body=self.window('Novo aparelho / linha')
        win.geometry('960x760');win.minsize(920,700)
        ttk.Label(body,text=f'Editar TEL-{row["id"]}' if row else 'Novo aparelho / linha',font=('Consolas',15,'bold')).pack(anchor='w')
        shortcut=ttk.Frame(body);shortcut.pack(fill='x',pady=5)
        ttk.Button(shortcut,text='Entregar / trocar aparelho do estoque',command=lambda:self.stock_phone_window(row,origin_editor=win)).pack(side='left')
        ttk.Label(shortcut,text='Para trocar de aparelho, selecione o registro do estoque.').pack(side='left',padx=8)
        data=row['values'] if row else ['']*len(PHONE_FIELDS)
        current=row['person']['id'] if row and row['person'] else None
        mode=self.field(body,'Tipo de responsável','Colaborador de outra base' if row and row.get('external') else 'Colaborador cadastrado',['Colaborador cadastrado','Colaborador de outra base'])
        options=self.people_options(current)
        person_frame=ttk.Frame(body);person_frame.pack(fill='x')
        person=self.field(person_frame,'Colaborador responsável (novas atribuições somente para ativos)',next((k for k,v in options.items() if v==current),'Sem responsável'),list(options))
        person_widget=person_frame.winfo_children()[-1]
        conference=ttk.Label(body,text=row['conferencia'] if row else 'ID do registro gerado automaticamente ao salvar.',foreground='#79ff87')
        conference.pack(anchor='w',pady=8)
        tabs=ttk.Notebook(body);tabs.pack(fill='both',expand=True,pady=8)
        variables={}
        for title,indices in [('Aparelho e linha',list(range(6,17))),('Base e dados de origem',list(range(6)))]:
            page=ttk.Frame(tabs,padding=10);tabs.add(page,text=title)
            page.columnconfigure(0,weight=1);page.columnconfigure(1,weight=1)
            for position,index in enumerate(indices):
                cell=ttk.Frame(page,padding=(0,0,12,0));cell.grid(row=position//2,column=position%2,sticky='ew')
                choices=None
                if index==6:choices=['Samsung','Apple','Motorola','Xiaomi','Realme']
                if index==13:choices=list(dict.fromkeys(['']+list(PHONE_STATUSES)+[data[index]]))
                if index==14:choices=['','Sim','Não']
                variables[index]=self.field(cell,'Data de cadastro na planilha de origem' if index==15 else PHONE_FIELDS[index],data[index],choices)
            if title=='Base e dados de origem':
                cell=ttk.Frame(page,padding=(0,0,12,0));cell.grid(row=3,column=0,sticky='ew')
                state=self.field(cell,'Estado (UF) do aparelho',row.get('estado','') if row else '',['']+list(STATES))
                cell=ttk.Frame(page,padding=(0,0,12,0));cell.grid(row=3,column=1,sticky='ew')
                arrival=self.field(cell,'Data de chegada (AAAA-MM-DD)',row.get('data_chegada','') if row else '')
                cell=ttk.Frame(page,padding=(0,0,12,0));cell.grid(row=4,column=0,sticky='ew')
                registered=self.field(cell,'Data de cadastro na base (AAAA-MM-DD)',row.get('cadastro_em') if row else dt.date.today().isoformat())
                cell=ttk.Frame(page,padding=(0,0,12,0));cell.grid(row=4,column=1,sticky='ew')
                released=self.field(cell,'Data de liberação (AAAA-MM-DD)',row.get('liberacao','') if row else '')
        external_page=ttk.Frame(tabs,padding=10)
        tabs.add(external_page,text='Colaborador de outra base')
        external_data=row.get('external') or {} if row else {}
        external_vars={}
        external_page.columnconfigure(0,weight=1);external_page.columnconfigure(1,weight=1)
        for position,field in enumerate(EXTERNAL_FIELDS):
            cell=ttk.Frame(external_page,padding=(0,0,12,0));cell.grid(row=position//2,column=position%2,sticky='ew')
            external_vars[field]=self.field(cell,field,external_data.get(field,''),list(STATES) if field=='Estado' else None)
        pending_matricula=tk.BooleanVar(value=bool(external_data.get('Matrícula pendente')))
        ttk.Checkbutton(external_page,text='Matrícula ainda não informada',variable=pending_matricula).grid(row=4,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(external_page,text='Telefone pessoal deve incluir DDD. Complete a matrícula quando estiver disponível.').grid(row=5,column=0,columnspan=2,sticky='w',pady=6)
        def change_mode(*_):
            outside=mode.get()=='Colaborador de outra base'
            person_widget.configure(state='disabled' if outside else 'readonly')
            if outside:
                person_frame.pack_forget()
                tabs.add(external_page,text='Colaborador de outra base');tabs.select(external_page)
            else:
                person_frame.pack(fill='x',before=conference)
                tabs.hide(external_page)
        mode.trace_add('write',change_mode);change_mode()
        team_page=ttk.Frame(tabs,padding=12);tabs.add(team_page,text='Uso e equipes')
        ttk.Label(team_page,text='O responsável selecionado mantém a tutela. O aparelho / linha pode ser utilizado por equipes.',wraplength=820).pack(anchor='w',pady=8)
        use=self.field(team_page,'Utilização','Por equipes' if row and row.get('uso_equipes') else 'Individual',['Individual','Por equipes'])
        teams=self.field(team_page,'Equipe(s) que utilizam o aparelho / linha (opcional)',row.get('equipes','') if row else '')
        team_widget=team_page.winfo_children()[-1]
        def change_use(*_):team_widget.configure(state='normal' if use.get()=='Por equipes' else 'disabled')
        use.trace_add('write',change_use);change_use()
        ttk.Label(team_page,text='Você pode atribuir vários aparelhos e linhas ao mesmo responsável. Registre aqui as equipes de cada um.',wraplength=820).pack(anchor='w',pady=12)
        move_page=ttk.Frame(tabs,padding=12);tabs.add(move_page,text='Alteração de tutela')
        ttk.Label(move_page,text='Preencha ao mudar ou retirar o responsável. Para substituir o aparelho, use Entregar / trocar aparelho. O histórico fica disponível em Histórico / RH.',wraplength=800).pack(anchor='w')
        move_day=self.field(move_page,'Data da alteração (AAAA-MM-DD)',dt.date.today().isoformat())
        move_reason=self.field(move_page,'Motivo da mudança de tutela / devolução')
        move_defect=self.field(move_page,'Defeito, se houver')
        if row:
            from movimentacoes import history
            events=[m for m in history(self.con) if row['id'] in (m['aparelho'],m['substituto'])]
            history_page=ttk.Frame(tabs,padding=10);tabs.add(history_page,text='Histórico do aparelho')
            text='\n\n'.join(f'{m["dia"]} — {m["tipo"]}\nResponsável anterior: {m["anterior"].get("Nome completo", "")}\nNovo responsável: {(m["novo"] or {}).get("Nome completo", "Sem nova tutela")}\nMotivo: {m["motivo"]}\nDefeito: {m["defeito"] or "Não informado / não se aplica"}\nDestino: {m["destino"]}' for m in events)
            self.detail(history_page,text or 'Nenhuma movimentação registrada para este aparelho.')
        actions=ttk.Frame(body);actions.pack(fill='x',pady=8)
        def save():
            try:
                outside=mode.get()=='Colaborador de outra base'
                if row and (row['person'] or row.get('external')):
                    changed=(outside and not row.get('external')) or (not outside and bool(row.get('external'))) or (not outside and options[person.get()]!=current)
                    if outside and row.get('external'):
                        changed=any(external_vars[k].get().strip()!=row['external'].get(k,'') for k in ('Nome completo','Matrícula','Base'))
                    if changed and not move_reason.get().strip():raise ValueError('Informe o motivo na aba Alteração de tutela.')
                save_phone(self.con,[variables[i].get() for i in range(len(PHONE_FIELDS))],None if outside else options[person.get()],row['id'] if row else None,
                           external={**{key:var.get() for key,var in external_vars.items()},'Matrícula pendente':pending_matricula.get()} if outside else None,
                           uso_equipes=use.get()=='Por equipes',equipes=teams.get(),estado=state.get(),data_chegada=arrival.get(),cadastro_em=registered.get(),liberacao=released.get(),movement_day=move_day.get(),movement_reason=move_reason.get() or 'Alteração de tutela no cadastro',movement_defect=move_defect.get())
            except DuplicatePhone as e:
                if messagebox.askyesno('Aparelho já cadastrado',str(e)+'\n\nOs dados digitados não foram salvos. Deseja abrir a entrega / troca usando o estoque?',parent=win):
                    self.stock_phone_window(row,e.ids[0] if len(e.ids)==1 else None,origin_editor=win)
                return
            except Exception as e:messagebox.showerror('Verifique os campos',str(e),parent=win);return
            win.destroy();self.refresh()
        ttk.Button(actions,text='Salvar alterações' if row else 'Salvar aparelho / linha',command=save).pack(side='right')
        if row:
            def remove():
                if not messagebox.askyesno('Excluir aparelho / linha',f'Excluir TEL-{row["id"]} das consultas?',parent=win):return
                try:
                    folder=ROOT/'backups';folder.mkdir(exist_ok=True)
                    backup(self.con,folder/f'antes_excluir_TEL-{row["id"]}_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3')
                    delete_phone(self.con,row['id'])
                except Exception as e:messagebox.showerror('Exclusão',str(e),parent=win);return
                win.destroy();self.refresh()
            ttk.Button(actions,text='Excluir aparelho / linha',command=remove).pack(side='left')

    def people_options(self,current=None):
        people=list(self.con.execute('SELECT * FROM colaboradores ORDER BY nome'))
        return {'Sem responsável':None,**{f'{p["nome"]} — {p["matricula"]} ({effective(p)})':p['id'] for p in people if effective(p)=='ATIVO' or p['id']==current}}

    def sanction_editor(self,win,body,key,row):
        options=self.people_options(row['colaborador']);selected=next((k for k,v in options.items() if v==row['colaborador']),'Sem responsável')
        person=self.field(body,'Responsável pela resposta',selected,list(options))
        status=self.field(body,'Andamento interno',row['andamento'] or 'Pendente',['Pendente','Em análise','Respondida'])
        deadline=self.field(body,'Prazo interno (AAAA-MM-DD)',row['prazo_interno'])
        notebook=ttk.Notebook(body);notebook.pack(fill='both',expand=True,pady=10)
        response_tab=ttk.Frame(notebook);notebook.add(response_tab,text='Resposta / acompanhamento')
        text=tk.Text(response_tab,wrap='word',font=('Consolas',11));text.pack(fill='both',expand=True);text.insert('1.0',row['resposta'] or '')
        source=ttk.Frame(notebook);notebook.add(source,text='Dados da sanção');self.detail(source,self.source_detail(row,'sancoes'))
        def save():
            try:save_response(self.con,key,options[person.get()],status.get(),deadline.get().strip(),text.get('1.0','end-1c'))
            except Exception as e:messagebox.showerror('Verifique os campos',str(e),parent=win);return
            win.destroy();self.refresh()
        ttk.Button(body,text='Salvar acompanhamento',command=save).pack(anchor='e')

    def new_computer(self,row=None,win=None,body=None):
        if win is None:win,body=self.window('Cadastrar novo computador')
        win.geometry('960x760');win.minsize(920,740)
        ttk.Label(body,text=f'Editar computador PC-{row["id"]}' if row else 'Novo computador',font=('Consolas',15,'bold')).pack(anchor='w')
        ttk.Label(body,text=f'ID do registro: PC-{row["id"]} (fixo). Altere os campos e selecione o responsável.' if row else 'ID do registro: gerado automaticamente ao salvar. Selecione a situação e preencha os demais campos disponíveis.').pack(anchor='w',pady=6)
        datebar=ttk.Frame(body);datebar.pack(fill='x',pady=4)
        ttk.Label(datebar,text='Data de cadastro na base (AAAA-MM-DD):').pack(side='left')
        registered=tk.StringVar(value=row.get('cadastro_em') if row else dt.date.today().isoformat())
        ttk.Entry(datebar,textvariable=registered,width=16).pack(side='left',padx=8)
        ttk.Label(datebar,text='Termo de responsabilidade:').pack(side='left',padx=6)
        signed=tk.StringVar(value=row.get('termo','Não') if row else 'Não')
        SearchCombobox(datebar,textvariable=signed,values=['Sim','Não'],state='readonly',width=7).pack(side='left')
        link=self.con.execute("SELECT dados,alerta,componentes FROM entregas WHERE computador=? AND coalesce(devolucao,'')='' ORDER BY id DESC LIMIT 1",(row['id'],)).fetchone() if row else None
        link_data=(json.loads(link[0]) if link and link[0] else [])+['']*13
        if link and link[1]:ttk.Label(body,text='Conferência pendente: '+link[1],foreground='#79ff87',wraplength=870).pack(anchor='w',pady=4)
        meta=ttk.Frame(body);meta.pack(fill='x',pady=4)
        ttk.Label(meta,text='Entrega (AAAA-MM-DD):').pack(side='left')
        delivered=tk.StringVar(value=str(link_data[9])[:10] or dt.date.today().isoformat())
        ttk.Entry(meta,textvariable=delivered,width=14).pack(side='left',padx=8)
        ttk.Label(meta,text='Última conferência (AAAA-MM-DD):').pack(side='left')
        checked=tk.StringVar(value=str(link_data[11])[:10])
        ttk.Entry(meta,textvariable=checked,width=14).pack(side='left',padx=8)
        form=ttk.Frame(body);form.pack(fill='x')
        form.columnconfigure(0,weight=1);form.columnconfigure(1,weight=1)
        data=json.loads(row['dados']) if row and row.get('dados') else ['']*15
        variables=[]
        for index,label in enumerate(COMPUTER_FIELDS[1:],1):
            cell=ttk.Frame(form,padding=(0,0,14,0));cell.grid(row=(index-1)//2,column=(index-1)%2,sticky='ew')
            options=None
            if index==3:options=['Notebook','Desktop']
            if index==4:options=['Lenovo','HP','Dell']
            if index==7:options=['8,0 GB','12,0 GB','16,0 GB']
            if index==8:options=['240 GB','447 GB']
            if index==9:options=['Windows 10 Pro','Windows 11 Pro']
            if index==10:options=list(COMPUTER_STATUSES)
            variables.append(self.field(cell,label,data[index] if row else ('Estoque' if index==10 else ''),options))
        destination=ttk.Frame(body);destination.pack(fill='x',pady=8)
        current=self.con.execute("SELECT colaborador FROM entregas WHERE computador=? AND coalesce(devolucao,'')='' ORDER BY id DESC LIMIT 1",(row['id'],)).fetchone() if row else None
        options=self.people_options(current[0] if current else None)
        ttk.Label(destination,text='Destinar a colaborador ativo (obrigatório quando Em uso)').pack(anchor='w')
        person=tk.StringVar(value=next((label for label,pid in options.items() if current and pid==current[0]),'Sem responsável'))
        combo=SearchCombobox(destination,textvariable=person,values=list(options),state='disabled',width=80);combo.pack(fill='x',pady=4)
        components=self.field(destination,'Componentes anexos (ex.: 1 monitor Dell patrimônio 123; 1 teclado; 1 mouse)',link[2] if link else '')
        components_widget=destination.winfo_children()[-1]
        def situation_changed(*_):
            in_use=variables[9].get()=='Em uso'
            combo.configure(state='readonly' if in_use else 'disabled')
            components_widget.configure(state='normal' if in_use else 'disabled')
            if not in_use:
                person.set('Sem responsável');components.set('')
        variables[9].trace_add('write',situation_changed)
        situation_changed()
        def save():
            try:
                why='Alteração de tutela ou situação no cadastro';when=dt.date.today().isoformat()
                if row and current and current[0]!=options[person.get()]:
                    why=simpledialog.askstring('Motivo','Informe o motivo da devolução ou troca de tutela:',parent=win)
                    if not why:return
                    when=simpledialog.askstring('Data da movimentação','Informe a data (AAAA-MM-DD):',initialvalue=dt.date.today().isoformat(),parent=win)
                    if when is None:return
                if row:update_computer(self.con,row['id'],[v.get() for v in variables],options[person.get()],cadastro_em=registered.get(),termo=signed.get(),data_entrega=delivered.get(),data_conferencia=checked.get(),movement_reason=why,movement_day=when,componentes=components.get())
                else:create_computer(self.con,[v.get() for v in variables],options[person.get()],cadastro_em=registered.get(),termo=signed.get(),data_entrega=delivered.get(),data_conferencia=checked.get(),componentes=components.get())
            except Exception as e:messagebox.showerror('Verifique os campos',str(e),parent=win);return
            win.destroy();self.refresh()
        actions=ttk.Frame(body);actions.pack(fill='x',pady=8)
        ttk.Button(actions,text='Salvar alterações' if row else 'Salvar computador',command=save).pack(side='right')
        if row:
            def remove():
                if not messagebox.askyesno('Excluir computador',f'Excluir PC-{row["id"]} do cadastro e encerrar suas destinações? O histórico será preservado.',parent=win):return
                try:
                    folder=ROOT/'backups';folder.mkdir(exist_ok=True)
                    backup(self.con,folder/f'antes_excluir_PC-{row["id"]}_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3')
                    delete_computer(self.con,row['id'])
                except Exception as e:messagebox.showerror('Exclusão',str(e),parent=win);return
                win.destroy();self.refresh()
            ttk.Button(actions,text='Excluir computador',command=remove).pack(side='left')

    def new_assignment(self):
        win,body=self.window('Novo vínculo de computador')
        self.assignment_editor(win,body,None,{'colaborador':None,'computador':None,'devolucao':'','alerta':'','dados':None})

    def assignment_editor(self,win,body,key,row):
        options=self.people_options(row['colaborador']);selected=next((k for k,v in options.items() if v==row['colaborador']),'Sem responsável')
        person=self.field(body,'Colaborador vinculado',selected,list(options))
        pcs={f'{p["codigo"]} — patrimônio {p["patrimonio"]}':p['id'] for p in self.con.execute('SELECT * FROM computadores WHERE id NOT IN (SELECT computador FROM computadores_excluidos) ORDER BY codigo')}
        pcs={'Sem equipamento':None,**pcs}
        pc=self.field(body,'Equipamento',next((k for k,v in pcs.items() if v==row['computador']),'Sem equipamento'),list(pcs))
        returned=self.field(body,'Data de devolução (AAAA-MM-DD; vazio se ainda em uso)',row['devolucao'][:10] if row['devolucao'] else '')
        note=self.field(body,'Pendência / nota de conferência',row['alerta'])
        self.detail(body,self.source_detail(row,'entregas'))
        def save():
            try:
                date=returned.get().strip()
                if date:dt.date.fromisoformat(date)
                if key is None and (not pcs[pc.get()] or not options[person.get()]):
                    raise ValueError('Selecione o equipamento e o colaborador para criar o vínculo.')
                with self.con:
                    record_key=key
                    if key is None:
                        from uuid import uuid4
                        cursor=self.con.execute('INSERT INTO entregas(chave,computador,colaborador,devolucao,alerta) VALUES(?,?,?,?,?)',('manual:'+uuid4().hex,pcs[pc.get()],options[person.get()],date,note.get()))
                        record_key=cursor.lastrowid
                    else:
                        self.con.execute('UPDATE entregas SET computador=?,colaborador=?,devolucao=?,alerta=? WHERE id=?',(pcs[pc.get()],options[person.get()],date,note.get(),key))
                    audit(self.con,'entrega',record_key,row,{'computador':pcs[pc.get()],'colaborador':options[person.get()],'devolucao':date,'alerta':note.get()})
            except Exception as e:messagebox.showerror('Verifique os campos',str(e),parent=win);return
            win.destroy();self.refresh()
        ttk.Button(body,text='Salvar vínculo e conferência',command=save).pack(anchor='e')

if __name__=='__main__':
    App().mainloop()
