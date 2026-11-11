"""Conferência de identidade e destaque exclusivo da célula do ID."""
import base64
import io
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from banco import norm,matricula


def identity_diff(name,registration,person_name,person_registration):
    # Ausência de um campo não contradiz um dado conhecido.
    return bool((norm(name) and norm(person_name) and norm(name)!=norm(person_name)) or
                (str(registration or '').strip() and str(person_registration or '').strip() and
                 (matricula(registration) or norm(registration))!=(matricula(person_registration) or norm(person_registration))))


def phone_identity_issue(row):
    values=row['values'];person=row.get('person');external=row.get('external')
    if external:
        return identity_diff(values[3],values[5],external.get('Nome completo'),external.get('Matrícula'))
    if person:
        return identity_diff(values[3],values[5],person.get('nome'),person.get('matricula'))
    if norm(values[13])=='ESTOQUE':return False
    return bool(norm(values[3]) or str(values[5] or '').strip() or norm(values[13])=='EM USO')


def computer_identity_issue(con,computer_id):
    links=con.execute("SELECT e.*,c.nome nome_atual,c.matricula matricula_atual FROM entregas e LEFT JOIN colaboradores c ON c.id=e.colaborador WHERE e.computador=? AND coalesce(e.devolucao,'')=''",(computer_id,)).fetchall()
    for link in links:
        if not link['nome_atual']:
            if link['nome_origem'] or link['matricula_origem']:return True
        elif identity_diff(link['nome_origem'],link['matricula_origem'],link['nome_atual'],link['matricula_atual']):return True
    return False


class IdAlertTree(ttk.Treeview):
    """A coluna nativa #0 desenha o ID; as colunas de dados mantêm a cor padrão."""
    def __init__(self,master,**kwargs):
        columns=kwargs['columns']
        kwargs.update(show='tree headings',displaycolumns=columns[1:])
        super().__init__(master,**kwargs)
        self.heading('#0',text=columns[0])
        self.column('#0',width=180,minwidth=100,stretch=False)
        self._id_images={}

    def set_id_alert(self,iid,label,alert):
        if not alert:
            self.item(iid,text=label,image='')
            return
        if label not in self._id_images:
            from PIL import Image,ImageDraw,ImageFont
            size=max(10,round(10*float(self.tk.call('tk','scaling'))))
            path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'consola.ttf'
            font=ImageFont.truetype(str(path),size=size)
            bounds=font.getbbox(label)
            image=Image.new('RGBA',(int(font.getlength(label))+2,bounds[3]-bounds[1]+2))
            ImageDraw.Draw(image).text((0,1-bounds[1]),label,font=font,fill='#c62828')
            stream=io.BytesIO();image.save(stream,format='PNG')
            self._id_images[label]=tk.PhotoImage(master=self,data=base64.b64encode(stream.getvalue()).decode('ascii'))
        self.item(iid,text='',image=self._id_images[label])
