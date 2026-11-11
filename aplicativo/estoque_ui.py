import datetime as dt
import tkinter as tk
from tkinter import ttk,messagebox
from telefones import records
from movimentacoes import custodian,issue_from_stock
from banco import ROOT,backup,effective

class StockIssueUI:
    def stock_phone_window(self,row=None,stock_id=None,origin_editor=None):
        phones=records(self.con);by_id={r['id']:r for r in phones}
        stock=[r for r in phones if r['values'][13].strip().casefold()=='estoque' and not custodian(r)]
        if not stock:
            messagebox.showinfo('Estoque','Não há aparelho disponível em estoque e sem tutela.');return
        if row:row=by_id.get(row['id'])
        win,body=self.window('Entregar ou trocar aparelho do estoque');win.geometry('1100x730');win.minsize(1000,680)
        ttk.Label(body,text='Use o registro do estoque — sem copiar os dados do aparelho',font=('Consolas',14,'bold')).pack(anchor='w',pady=8)
        ttk.Label(body,text='Na substituição, o aparelho atual é devolvido e o escolhido sai do estoque. Na entrega adicional, o atual permanece com o colaborador.',wraplength=1000).pack(anchor='w',pady=5)
        form=ttk.Frame(body);form.pack(fill='x');form.columnconfigure(0,weight=1);form.columnconfigure(1,weight=1)
        def field(pos,label,value='',options=None):
            cell=ttk.Frame(form,padding=(0,0,12,0));cell.grid(row=pos//2,column=pos%2,sticky='ew')
            return self.field(cell,label,value,options)
        def caption(r):return f'TEL-{r["id"]} | {r["values"][6]} {r["values"][7]} | IMEI {r["values"][9] or r["values"][10] or "não informado"} | Linha {r["values"][8] or "não informada"}'
        stocks={caption(r):r['id'] for r in stock}
        preferred=stock_id or (row['id'] if row and row in stock else None)
        selected_stock=field(0,'Aparelho disponível em estoque',next((k for k,v in stocks.items() if v==preferred),next(iter(stocks))),list(stocks))
        replacing=bool(row and custodian(row))
        operation=field(1,'O que será feito?','Substituir aparelho atual' if replacing else 'Entregar aparelho adicional',['Substituir aparelho atual','Entregar aparelho adicional'])
        sources={'Sem aparelho anterior':None,**{caption(r):r['id'] for r in phones if custodian(r)}}
        selected_source=field(2,'Aparelho atual (necessário para substituição)',next((k for k,v in sources.items() if replacing and v==row['id']),'Sem aparelho anterior'),list(sources))
        recipients={'Selecione o responsável':None}
        for p in self.con.execute('SELECT * FROM colaboradores ORDER BY nome'):
            if effective(p)=='ATIVO':recipients[f'{p["nome"]} — {p["matricula"]}']={'id':p['id']}
        for r in phones:
            if r['external']:
                ext=r['external'];recipients[f'{ext["Nome completo"]} — {ext["Base"]} (outra base)']=ext
        def recipient_label(source):
            who=custodian(source) if source else None
            if who:
                for label,value in recipients.items():
                    if value and ((who.get('id') and value.get('id')==who['id']) or (source['external'] and value==source['external'])):return label
            return 'Selecione o responsável'
        recipient=field(3,'Colaborador que receberá o aparelho',recipient_label(row) if replacing else 'Selecione o responsável',list(recipients))
        day=field(4,'Data da entrega / troca (AAAA-MM-DD)',dt.date.today().isoformat())
        destination=field(5,'Destino do aparelho antigo (somente na substituição)','Quebrado',['Estoque','Quebrado','Manutenção'])
        reason=field(6,'Motivo','Defeito' if replacing else 'Entrega de aparelho adicional',['Defeito','Troca solicitada','Entrega de aparelho adicional','Outro'])
        defect=field(7,'Defeito (obrigatório se o motivo for Defeito)')
        note=field(8,'Complemento do motivo (opcional)')
        line_frame=ttk.Frame(form);line_frame.grid(row=4,column=1,sticky='ew')
        move_line=tk.BooleanVar(value=False)
        check=ttk.Checkbutton(line_frame,text='Transferir a linha atual para o aparelho entregue',variable=move_line);check.pack(anchor='w',pady=24)
        summary=ttk.Label(body,wraplength=1000,foreground='#79ff87');summary.pack(anchor='w',pady=14)
        def controls(*_):
            old=by_id.get(sources[selected_source.get()]);target=by_id[stocks[selected_stock.get()]]
            replace=operation.get()=='Substituir aparelho atual'
            available=replace and old and any(c.isdigit() for c in old['values'][8])
            check.configure(state='normal' if available else 'disabled')
            move_line.set(bool(available and not any(c.isdigit() for c in target['values'][8])))
            summary.configure(text=f'Entregar TEL-{target["id"]} a {recipient.get()}. '+(f'Devolver TEL-{old["id"]} para {destination.get()}.' if replace and old else 'O aparelho atual não será devolvido nesta operação.')+' O ID do aparelho entregue será mantido e o novo termo ficará pendente.')
        def source_changed(*_):
            old=by_id.get(sources[selected_source.get()])
            if old:recipient.set(recipient_label(old))
            controls()
        selected_source.trace_add('write',source_changed)
        for var in (selected_stock,operation):var.trace_add('write',controls)
        for var in (recipient,destination):var.trace_add('write',lambda *_:summary.configure(text=f'Entregar {selected_stock.get()} a {recipient.get()}. Destino do antigo: {destination.get()} (apenas substituição).'))
        controls()
        ttk.Label(body,text='A transferência do chip não duplica a linha: ela sai do registro antigo. Se o aparelho do estoque já tiver outra linha, a troca exigirá conferência.',wraplength=1000).pack(anchor='w',pady=4)
        def commit():
            try:
                rec=recipients[recipient.get()];old=by_id.get(sources[selected_source.get()])
                if not rec:raise ValueError('Selecione o colaborador responsável.')
                why=reason.get()+(' — '+note.get().strip() if note.get().strip() else '')
                if reason.get()=='Outro' and not note.get().strip():raise ValueError('Descreva o motivo da movimentação.')
                folder=ROOT/'backups';folder.mkdir(exist_ok=True)
                backup(self.con,folder/f'antes_entrega_estoque_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3')
                rid=issue_from_stock(self.con,stocks[selected_stock.get()],source_id=sources[selected_source.get()],replace=operation.get()=='Substituir aparelho atual',recipient_id=rec.get('id'),recipient_external=rec if not rec.get('id') else None,day=day.get(),reason=why,defect=defect.get(),destination=destination.get(),move_line=move_line.get(),expected_source_owner=custodian(old) if old else None)
            except Exception as e:messagebox.showerror('Verifique a entrega',str(e),parent=win);return
            if origin_editor and origin_editor.winfo_exists():origin_editor.destroy()
            self.refresh();win.destroy()
            messagebox.showinfo('Entrega registrada',f'Movimentação {rid} salva. O registro existente saiu do estoque e foi atribuído ao responsável, sem duplicação. Confira o novo termo pendente no RH.')
        ttk.Button(body,text='Confirmar entrega / troca',command=commit).pack(anchor='e',pady=15)
