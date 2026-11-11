import datetime as dt
from tkinter import ttk,messagebox
from banco import ROOT,backup,effective
from pc_movimentos import current,owner,issue_from_stock


def open_window(app,selected_id=None,origin_editor=None):
    pcs={r['id']:dict(r) for r in app.con.execute('SELECT * FROM computadores WHERE id NOT IN (SELECT computador FROM computadores_excluidos) ORDER BY id')}
    links={key:current(app.con,key) for key in pcs}
    stock=[r for key,r in pcs.items() if r['situacao']=='Estoque' and not links[key]]
    if not stock:
        messagebox.showinfo('Estoque','Não há computador disponível em estoque e sem tutela.',parent=app);return
    selected=pcs.get(selected_id);previous=owner(links.get(selected_id))
    win,body=app.window('Entregar ou trocar computador do estoque');win.geometry('1100x740');win.minsize(1000,700)
    ttk.Label(body,text='Entregar ou trocar computador do estoque',font=('Consolas',14,'bold')).pack(anchor='w',pady=8)
    ttk.Label(body,text='Na substituição, o computador atual é devolvido e o escolhido sai do estoque. Na entrega adicional, o atual permanece com o colaborador.',wraplength=1000).pack(anchor='w',pady=5)
    form=ttk.Frame(body);form.pack(fill='x');form.columnconfigure(0,weight=1);form.columnconfigure(1,weight=1)
    def field(pos,label,value='',options=None):
        cell=ttk.Frame(form,padding=(0,0,12,0));cell.grid(row=pos//2,column=pos%2,sticky='ew')
        return app.field(cell,label,value,options)
    def caption(row):return f'PC-{row["id"]} | Patrimônio {row["patrimonio"] or "não informado"} | {row["modelo"] or "modelo não informado"}'
    stocks={caption(r):r['id'] for r in stock}
    target=field(0,'Computador disponível em estoque',next((k for k,v in stocks.items() if v==selected_id),next(iter(stocks))),list(stocks))
    operation=field(1,'O que será feito?','Substituir computador atual' if previous else 'Entregar computador adicional',['Substituir computador atual','Entregar computador adicional'])
    sources={'Sem computador anterior':None,**{caption(row):key for key,row in pcs.items() if owner(links[key])}}
    source=field(2,'Computador atual (necessário para substituição)',next((k for k,v in sources.items() if previous and v==selected_id),'Sem computador anterior'),list(sources))
    people={'Selecione o responsável':None,**{f'{p["nome"]} — {p["matricula"]}':p['id'] for p in app.con.execute('SELECT * FROM colaboradores ORDER BY nome') if effective(p)=='ATIVO'}}
    def person_label(pid):return next((k for k,v in people.items() if pid and v==pid),'Selecione o responsável')
    person=field(3,'Colaborador ativo que receberá o computador',person_label(previous['id']) if previous else 'Selecione o responsável',list(people))
    day=field(4,'Data da entrega / troca (AAAA-MM-DD)',dt.date.today().isoformat())
    destination=field(5,'Destino do computador antigo (somente na substituição)','Defeito/Parado',['Estoque','Manutenção','Defeito/Parado','Separado'])
    reason=field(6,'Motivo','Defeito' if previous else 'Entrega de computador adicional',['Defeito','Troca solicitada','Entrega de computador adicional','Outro'])
    defect=field(7,'Defeito (obrigatório se o motivo for Defeito)')
    note=field(8,'Complemento do motivo (opcional)')
    components=field(9,'Componentes anexos que serão entregues (opcional)',links[selected_id]['componentes'] if previous else '')
    summary=ttk.Label(body,wraplength=1000,foreground='#79ff87');summary.pack(anchor='w',pady=18)
    ttk.Label(body,text='Confira os componentes anexos: informe somente os itens entregues com o computador escolhido. O novo termo ficará pendente de assinatura.',wraplength=1000).pack(anchor='w',pady=4)
    def controls(*_):
        old=sources[source.get()];replace=operation.get()=='Substituir computador atual'
        summary.configure(text=f'Entregar PC-{stocks[target.get()]} a {person.get()}. '+(f'Devolver PC-{old} para {destination.get()}.' if replace and old else 'O computador atual não será devolvido nesta operação.')+' O ID e o patrimônio do equipamento entregue serão mantidos.')
    def source_changed(*_):
        link=links.get(sources[source.get()]);who=owner(link)
        if who:person.set(person_label(who['id']))
        if operation.get()=='Substituir computador atual':components.set(link['componentes'] if link else '')
        controls()
    def operation_changed(*_):
        replacing=operation.get()=='Substituir computador atual'
        if reason.get() in ('Defeito','Entrega de computador adicional'):reason.set('Defeito' if replacing else 'Entrega de computador adicional')
        link=links.get(sources[source.get()]);components.set(link['componentes'] if replacing and link else '')
        controls()
    source.trace_add('write',source_changed);operation.trace_add('write',operation_changed)
    for var in (target,person,destination):var.trace_add('write',controls)
    controls()
    def commit():
        try:
            pid=people[person.get()]
            if not pid:raise ValueError('Selecione o colaborador responsável.')
            if reason.get()=='Outro' and not note.get().strip():raise ValueError('Descreva o motivo da movimentação.')
            why=reason.get()+(' — '+note.get().strip() if note.get().strip() else '')
            folder=ROOT/'backups';folder.mkdir(exist_ok=True)
            backup(app.con,folder/f'antes_entrega_estoque_PC_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3')
            event=issue_from_stock(app.con,stocks[target.get()],source_id=sources[source.get()],replace=operation.get()=='Substituir computador atual',recipient_id=pid,day=day.get(),reason=why,defect=defect.get(),destination=destination.get(),componentes=components.get(),expected_source_owner=owner(links.get(sources[source.get()])))
        except Exception as e:messagebox.showerror('Verifique a entrega',str(e),parent=win);return
        if origin_editor and origin_editor.winfo_exists():origin_editor.destroy()
        app.refresh();win.destroy()
        messagebox.showinfo('Entrega registrada',f'Movimentação {event} salva. O computador existente saiu do estoque e foi atribuído ao responsável. Confira o novo termo pendente no RH.',parent=app)
    ttk.Button(body,text='Confirmar entrega / troca',command=commit).pack(anchor='e',pady=15)
