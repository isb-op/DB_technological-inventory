import datetime as dt
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from banco import norm
from rh import history,export_csv,mark_completed,HEADERS,report_values


class MovementUI:
    def movements_window(self):
        win,body=self.window('Histórico e relatório RH — computadores e celulares')
        win.geometry('1180x740');win.minsize(1000,680)
        ttk.Label(body,text='HISTÓRICO E RELATÓRIO RH',font=('Consolas',15,'bold')).pack(anchor='w',pady=(0,8))
        ttk.Label(body,text='Computadores e celulares no mesmo histórico. Filtre as informações e baixe um único relatório.',wraplength=1050).pack(anchor='w',pady=(0,10))
        self.movement_report(body,win)

    def movement_report(self,page,win,equipment=None):
        filters=ttk.Frame(page);filters.pack(fill='x')
        variables=[]
        for column,label in enumerate(('De (AAAA-MM-DD)','Até (AAAA-MM-DD)','Pesquisar')):
            cell=ttk.Frame(filters,padding=(0,0,12,0));cell.grid(row=0,column=column,sticky='ew');filters.columnconfigure(column,weight=1)
            variables.append(self.field(cell,label))
        tools=ttk.Frame(page);tools.pack(fill='x',pady=8)
        kind=self.field(tools,'Equipamento','Todos',['Todos','Computadores','Celulares / linhas'])
        pending=tk.BooleanVar(value=False)
        options=ttk.Frame(page);options.pack(fill='x')
        ttk.Checkbutton(options,text='Somente pendentes RH',variable=pending).pack(side='left')
        cols=('Movimento','Data','Equipamento','Operação','Responsável anterior','Novo responsável','Registro','Substituto','Motivo','Defeito','RH concluído')
        area=ttk.Frame(page);area.pack(fill='both',expand=True,pady=12)
        tree=ttk.Treeview(area,columns=cols,show='headings',selectmode='browse');tree.grid(row=0,column=0,sticky='nsew')
        for col in cols:tree.heading(col,text=col);tree.column(col,width=190)
        vs=ttk.Scrollbar(area,command=tree.yview);vs.grid(row=0,column=1,sticky='ns')
        hs=ttk.Scrollbar(area,orient='horizontal',command=tree.xview);hs.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);area.rowconfigure(0,weight=1);area.columnconfigure(0,weight=1)
        visible=[];count=ttk.Label(page);count.pack(anchor='w')
        def refresh():
            try:
                start,end,query=[v.get().strip() for v in variables]
                for day in (start,end):
                    if day:dt.date.fromisoformat(day)
                if start and end and start>end:raise ValueError('A data inicial deve ser anterior à final.')
            except ValueError as error:messagebox.showerror('Período inválido',str(error),parent=win);return False
            visible.clear()
            for row in history(self.con):
                if start and row['dia']<start or end and row['dia']>end:continue
                if pending.get() and row['rh_concluido']:continue
                if kind.get()=='Computadores' and row['prefix']!='PC':continue
                if kind.get()=='Celulares / linhas' and row['prefix']!='TEL':continue
                if norm(query) not in norm(' '.join(str(v or '') for v in report_values(row))):continue
                visible.append(row)
            tree.delete(*tree.get_children())
            for row in visible:
                prefix=row['prefix']
                tree.insert('','end',iid=row['key'],values=(row['key'],row['dia'],row['equipment'],row['tipo'],row['anterior'].get('Nome completo',''),(row['novo'] or {}).get('Nome completo',''),f'{prefix}-{row["aparelho"]}',f'{prefix}-{row["substituto"]}' if row['substituto'] else '',row['motivo'],row['defeito'],'Sim' if row['rh_concluido'] else 'Não'))
            count.configure(text=f'{len(visible)} movimentações exibidas. O relatório exporta todos os campos históricos de computadores e celulares.')
            return True
        ttk.Button(options,text='Filtrar',command=refresh).pack(side='right')
        actions=ttk.Frame(page);actions.pack(fill='x',pady=(8,0))
        def export():
            if not refresh():return
            path=filedialog.asksaveasfilename(parent=win,defaultextension='.csv',initialfile=f'Historico_RH_computadores_celulares_{dt.date.today()}.csv',filetypes=[('Relatório CSV','*.csv')])
            if not path:return
            try:export_csv(path,visible)
            except Exception as error:messagebox.showerror('Exportação',str(error),parent=win);return
            messagebox.showinfo('Relatório salvo',f'{len(visible)} movimentações exportadas em um único arquivo.',parent=win)
        def complete():
            selected=tree.selection()
            if not selected:return
            if not messagebox.askyesno('Confirmar tratamento pelo RH','O RH já tratou os termos desta movimentação, quando aplicável?',parent=win):return
            try:mark_completed(self.con,selected[0])
            except Exception as error:messagebox.showerror('Histórico RH',str(error),parent=win);return
            refresh()
        ttk.Button(actions,text='Baixar relatório RH unificado (CSV)',command=export).pack(side='left')
        ttk.Button(actions,text='Marcar selecionado como tratado pelo RH',command=complete).pack(side='left',padx=8)
        def details(event):
            selected=tree.selection()
            if not selected:return
            row=next(r for r in visible if r['key']==selected[0])
            _,body=self.window(row['key']+' — '+row['equipment'])
            values=report_values(row)
            self.detail(body,'\n\n'.join(f'{label}: {value}' for label,value in zip(HEADERS,values) if value and label!='Dados históricos completos'))
        tree.bind('<Double-1>',details);refresh()
