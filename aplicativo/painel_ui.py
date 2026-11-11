from selecoes import SearchCombobox
import datetime as dt
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from painel import overview,export_pending,normalized

class DashboardUI:
    def build_dashboard(self):
        page=ttk.Frame(self.tabs,padding=12);self.tabs.add(page,text='Início')
        self.dashboard_page=page;self.dashboard_details={}
        cards=ttk.Frame(page);cards.pack(fill='x')
        self.dashboard_cards={}
        fields=(('ativos','Colaboradores ativos'),('com_celular','Com celular / linha'),('com_linha','Com linha informada'),('com_computador','Com computador'),('regularizados','Todos os termos em dia'),('pendentes','Com termos / vínculo pendente'))
        for column,(key,label) in enumerate(fields):
            cards.columnconfigure(column,weight=1,uniform='cards')
            cell=ttk.Frame(cards,padding=8);cell.grid(row=0,column=column,sticky='nsew')
            value=ttk.Label(cell,text='0',font=('Consolas',24,'bold'),foreground='#ff49c8' if key=='pendentes' else '#79ff87');value.pack(anchor='w')
            ttk.Label(cell,text=label,wraplength=135).pack(anchor='w')
            self.dashboard_cards[key]=value
        graphs=ttk.Frame(page);graphs.pack(fill='x',pady=6)
        self.dashboard_charts=[]
        for i in range(2):
            graphs.columnconfigure(i,weight=1,uniform='graphs')
            canvas=tk.Canvas(graphs,height=170,background='#0b0b13',highlightthickness=0)
            canvas.grid(row=0,column=i,sticky='ew',padx=(0,10) if i==0 else (0,0))
            canvas.bind('<Configure>',lambda event:self.draw_dashboard())
            self.dashboard_charts.append(canvas)
        self.dashboard_other=ttk.Label(page,wraplength=1100);self.dashboard_other.pack(anchor='w',pady=4)
        ttk.Label(page,text='Indicadores principais: pessoas únicas e ativas do Dados Flex. Termo assinado = campo marcado Sim; gerar o documento não confirma assinatura.',wraplength=1100).pack(anchor='w',pady=4)
        tools=ttk.Frame(page);tools.pack(fill='x',pady=7)
        ttk.Label(tools,text='Acompanhar:').pack(side='left')
        self.dashboard_filter=tk.StringVar(value='Com pendências')
        SearchCombobox(tools,textvariable=self.dashboard_filter,state='readonly',values=['Com pendências','Todos com equipamentos','Regularizados','Ativos do Dados Flex','Outras bases','Desligados','Sem tutela identificada'],width=24).pack(side='left',padx=6)
        self.dashboard_query=tk.StringVar();ttk.Label(tools,text='Pesquisar:').pack(side='left')
        ttk.Entry(tools,textvariable=self.dashboard_query,width=25).pack(side='left',padx=6)
        ttk.Button(tools,text='Ver equipamentos',command=self.open_dashboard_person).pack(side='right')
        ttk.Button(tools,text='Baixar pendências CSV',command=self.dashboard_export).pack(side='right',padx=6)
        area=ttk.Frame(page);area.pack(fill='both',expand=True)
        cols=('Nome','Matrícula','Grupo','Celulares / linhas','Computadores','Termos Sim','Termos pendentes','Conferir vínculo')
        tree=ttk.Treeview(area,columns=cols,show='headings',selectmode='browse');tree.grid(row=0,column=0,sticky='nsew')
        for column in cols:tree.heading(column,text=column);tree.column(column,width=150,minwidth=95)
        tree.column('Nome',width=310)
        vs=ttk.Scrollbar(area,command=tree.yview);vs.grid(row=0,column=1,sticky='ns')
        hs=ttk.Scrollbar(area,orient='horizontal',command=tree.xview);hs.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);area.rowconfigure(0,weight=1);area.columnconfigure(0,weight=1)
        tree.bind('<Double-1>',lambda e:self.open_dashboard_person())
        self.dashboard_tree=tree;self.dashboard_count=ttk.Label(page);self.dashboard_count.pack(anchor='w',pady=(5,0))
        for var in (self.dashboard_filter,self.dashboard_query):var.trace_add('write',lambda *_:self.filter_dashboard())

    def refresh_dashboard(self):
        self.dashboard_data=overview(self.con)
        for key,label in self.dashboard_cards.items():label.configure(text=str(self.dashboard_data['metrics'][key]))
        m=self.dashboard_data['metrics']
        self.dashboard_other.configure(text=f'Outras bases: {m["externos"]} responsáveis, {m["externos_pendentes"]} com pendências. Desligados com equipamentos: {m["desligados"]}. Equipamentos sem tutela confirmada: {m["sem_tutela"]}.')
        self.filter_dashboard();self.draw_dashboard()
        for win,refresh in list(self.dashboard_details.items()):
            if win.winfo_exists():refresh()
            else:self.dashboard_details.pop(win,None)

    def draw_dashboard(self):
        if not hasattr(self,'dashboard_data'):return
        m=self.dashboard_data['metrics']
        datasets=[('Cobertura de equipamentos dos ativos',[('Ativos',m['ativos'],'#79ff87'),('Com celular / linha',m['com_celular'],'#49d783'),('Com linha informada',m['com_linha'],'#ff49c8'),('Com computador',m['com_computador'],'#c67dff')]),
                  ('Situação dos termos dos ativos',[('Todos os termos em dia',m['regularizados'],'#79ff87'),('Com pendência',m['pendentes'],'#ff49c8'),('Sem equipamento vinculado',m['sem_equipamento'],'#62786b')])]
        for canvas,(title,rows) in zip(self.dashboard_charts,datasets):
            canvas.delete('all');width=max(canvas.winfo_width(),350)
            canvas.create_text(12,16,text=title,anchor='w',font=('Consolas',11,'bold'),fill='#79ff87')
            maximum=max([v for _,v,_ in rows]+[1]);available=max(width-255,45)
            for i,(label,value,color) in enumerate(rows):
                y=47+i*29
                canvas.create_text(12,y+8,text=label,anchor='w',font=('Consolas',9),fill='#a7b4ad')
                canvas.create_rectangle(193,y,193+available,y+17,fill='#1b2920',outline='')
                if value:canvas.create_rectangle(193,y,193+available*value/maximum,y+17,fill=color,outline='')
                canvas.create_text(203+available,y+8,text=str(value),anchor='w',font=('Consolas',10,'bold'),fill='#79ff87')

    def filter_dashboard(self):
        if not hasattr(self,'dashboard_data'):return
        query=normalized(self.dashboard_query.get());mode=self.dashboard_filter.get();self.dashboard_visible=[]
        for g in self.dashboard_data['groups']:
            if mode=='Com pendências' and g['regular']:continue
            if mode=='Regularizados' and not g['regular']:continue
            group={'Ativos do Dados Flex':'Ativo','Outras bases':'Outra base','Desligados':'Desligado','Sem tutela identificada':'Sem tutela'}.get(mode)
            if group and g['grupo']!=group:continue
            searchable=' '.join([g['nome'],g['matricula'],g['grupo']]+[str(v or '') for a in g['assets'] for v in (a['registro'],a['identificacao'],a['modelo'],a['base'],a['cidade'])])
            if query and query not in normalized(searchable):continue
            self.dashboard_visible.append(g)
        tree=self.dashboard_tree;selection=tree.selection();tree.delete(*tree.get_children())
        for g in self.dashboard_visible:tree.insert('','end',iid=g['key'],values=(g['nome'],g['matricula'],g['grupo'],g['celulares'],g['computadores'],g['assinados'],g['pendentes'],g['conferir']),tags=() if g['regular'] else ('pending',))
        if selection and tree.exists(selection[0]):tree.selection_set(selection[0])
        self.dashboard_count.configure(text=f'{len(self.dashboard_visible)} registros de acompanhamento. Sem tutela: uma linha por equipamento. Quem não tem equipamento não é classificado como pendente.')

    def dashboard_export(self):
        self.refresh_dashboard()
        assets=[a for g in self.dashboard_visible for a in g['assets'] if not a['signed'] or a['issue']]
        path=filedialog.asksaveasfilename(title='Salvar acompanhamento de termos pendentes',defaultextension='.csv',initialfile=f'Termos_pendentes_{dt.date.today()}.csv')
        if path:
            try:export_pending(path,assets)
            except Exception as e:messagebox.showerror('Exportação',str(e));return
            messagebox.showinfo('Relatório salvo',f'{len(assets)} pendências exportadas conforme o filtro da página inicial.')

    def dashboard_asset(self,asset,generate=False):
        name='Computadores' if asset['kind']=='computador' else 'Aparelhos e Linhas telefônicas'
        v=self.views[name];v['query'].set('');v['filter'].set('Todos');self.refresh_view(name)
        key=str(asset['id'])
        if not v['tree'].exists(key):messagebox.showinfo('Cadastro atualizado','O equipamento não está mais disponível. Atualize o painel.');return
        self.tabs.select(v['frame']);v['tree'].selection_set(key);v['tree'].see(key)
        if generate:self.generate_term()
        else:self.open_row(name)

    def open_dashboard_person(self):
        selected=self.dashboard_tree.selection()
        if not selected:return
        owner_key=selected[0];g=next(g for g in self.dashboard_data['groups'] if g['key']==owner_key)
        win,body=self.window('Acompanhamento de termos — '+g['nome']);win.geometry('1080x650')
        ttk.Label(body,text=g['nome'],font=('Consolas',14,'bold')).pack(anchor='w')
        ttk.Label(body,text='Abra o cadastro para registrar Sim somente depois de receber o termo assinado. Gerar o termo mantém a pendência.',wraplength=1000).pack(anchor='w',pady=8)
        area=ttk.Frame(body);area.pack(fill='both',expand=True)
        cols=('Registro','Tipo','Linha / Patrimônio','Modelo','Situação','Termo','Acompanhamento')
        tree=ttk.Treeview(area,columns=cols,show='headings',selectmode='browse');tree.grid(row=0,column=0,sticky='nsew')
        for c in cols:tree.heading(c,text=c);tree.column(c,width=155)
        tree.column('Acompanhamento',width=320)
        vs=ttk.Scrollbar(area,command=tree.yview);vs.grid(row=0,column=1,sticky='ns')
        hs=ttk.Scrollbar(area,orient='horizontal',command=tree.xview);hs.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);area.rowconfigure(0,weight=1);area.columnconfigure(0,weight=1)
        assets={}
        def refresh():
            selection=tree.selection();tree.delete(*tree.get_children());assets.clear()
            group=next((g for g in self.dashboard_data['groups'] if g['key']==owner_key),None)
            for a in group['assets'] if group else []:
                assets[a['registro']]=a
                tree.insert('','end',iid=a['registro'],values=(a['registro'],a['kind'],a['identificacao'],a['modelo'],a['status'],a['termo'],a['issue'] or ('Em dia' if a['signed'] else 'Obter termo assinado')))
            if selection and tree.exists(selection[0]):tree.selection_set(selection[0])
        def action(generate=False):
            selected=tree.selection()
            if selected:self.dashboard_asset(assets[selected[0]],generate)
        actions=ttk.Frame(body);actions.pack(fill='x',pady=10)
        ttk.Button(actions,text='Abrir cadastro / atualizar termo',command=action).pack(side='left')
        if self.term_generation_available:
            ttk.Button(actions,text='Gerar termo para impressão',command=lambda:action(True)).pack(side='left',padx=8)
        tree.bind('<Double-1>',lambda e:action())
        self.dashboard_details[win]=refresh;refresh()
