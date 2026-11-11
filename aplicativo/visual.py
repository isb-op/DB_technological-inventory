"""Tema de terminal e decoração animada da aplicação local."""
import tkinter as tk
from tkinter import ttk
from PIL import Image,ImageTk,ImageSequence

BG='#000000'
PANEL='#0b0b13'
GREEN='#79ff87'
PINK='#ff49c8'
MUTED='#a7b4ad'
BORDER='#283b30'
FONT=('Consolas',10)


def apply_theme(root):
    root.configure(background=BG)
    for option,value in (('*Font',FONT),('*Background',BG),('*Foreground',GREEN),('*insertBackground',PINK),('*selectBackground','#38203e'),('*selectForeground',PINK),('*TCombobox*Listbox.background',PANEL),('*TCombobox*Listbox.foreground',GREEN),('*TCombobox*Listbox.selectBackground','#38203e'),('*TCombobox*Listbox.selectForeground',PINK),('*TCombobox*Listbox.font',FONT)):
        root.option_add(option,value)
    style=ttk.Style(root)
    style.configure('.',background=BG,foreground=GREEN,font=FONT,bordercolor=BORDER,lightcolor=BORDER,darkcolor=BG)
    for name in ('TFrame','TLabel','TCheckbutton','TRadiobutton','TLabelframe'):
        style.configure(name,background=BG,foreground=GREEN)
    style.configure('TLabelframe.Label',background=BG,foreground=PINK)
    style.configure('TButton',background=PANEL,foreground=PINK,padding=(10,8),bordercolor='#56304e',focusthickness=1,focuscolor=PINK)
    style.map('TButton',background=[('active','#251526'),('pressed','#38203e')],foreground=[('disabled','#637166'),('active',GREEN)])
    for name in ('TEntry','TCombobox','TSpinbox'):
        style.configure(name,fieldbackground=PANEL,background=PANEL,foreground=GREEN,insertcolor=PINK,arrowcolor=PINK,bordercolor=BORDER,selectbackground='#38203e',selectforeground=PINK,padding=5)
        style.map(name,fieldbackground=[('disabled','#131416'),('readonly',PANEL)],foreground=[('disabled','#728078'),('readonly',GREEN)],selectforeground=[('!disabled',PINK)],selectbackground=[('!disabled','#38203e')],bordercolor=[('focus',PINK)])
    style.configure('TNotebook',background=BG,borderwidth=0)
    style.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,padding=(12,8))
    style.map('TNotebook.Tab',background=[('selected','#201122'),('active','#142018')],foreground=[('selected',PINK),('active',GREEN)])
    style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=GREEN,font=FONT,rowheight=31,bordercolor=BORDER)
    style.map('Treeview',background=[('selected','#33213d')],foreground=[('selected',PINK)])
    style.configure('Treeview.Heading',background='#131a15',foreground=PINK,font=('Consolas',10,'bold'),padding=7,bordercolor=BORDER)
    style.map('Treeview.Heading',background=[('active','#263729')],foreground=[('active',GREEN)])
    for name in ('Vertical.TScrollbar','Horizontal.TScrollbar'):
        style.configure(name,background='#223328',troughcolor=BG,arrowcolor=GREEN,bordercolor=BORDER)
        style.map(name,background=[('active','#426f4b')])
    style.map('TCheckbutton',background=[('active',BG)],foreground=[('active',PINK),('disabled','#728078')])


class AnimatedCat(tk.Label):
    def __init__(self,master,path):
        super().__init__(master,bg=BG,borderwidth=0,highlightthickness=0)
        self.frames=[];self.durations=[];self._job=None;self.frame_index=0
        with Image.open(path) as gif:
            for frame in ImageSequence.Iterator(gif):
                image=frame.convert('RGBA');image.thumbnail((142,72),Image.Resampling.NEAREST)
                self.frames.append(ImageTk.PhotoImage(image,master=self))
                self.durations.append(max(40,int(frame.info.get('duration',100))))
        self.bind('<Destroy>',self._stop,add='+')
        self._animate()

    def _animate(self):
        if not self.frames:return
        self.configure(image=self.frames[self.frame_index])
        delay=self.durations[self.frame_index]
        self.frame_index=(self.frame_index+1)%len(self.frames)
        self._job=self.after(delay,self._animate)

    def _stop(self,event):
        if event.widget==self and self._job:
            self.after_cancel(self._job);self._job=None
