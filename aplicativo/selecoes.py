"""Navegação por letras nas caixas de seleção, abertas ou fechadas."""
import time
from tkinter import ttk
from banco import norm


class LetterSearch:
    def __init__(self):
        self.prefix='';self.last=0

    def match(self,values,current,char,now=None):
        if not char or len(char)!=1 or not char.isalnum():return None
        now=time.monotonic() if now is None else now
        char=norm(char)
        previous=self.prefix if now-self.last<1.2 else ''
        cycle=previous==char
        self.prefix=char if cycle else previous+char
        self.last=now
        start=current+1 if cycle or not previous else max(current,0)
        for offset in range(len(values)):
            index=(start+offset)%len(values)
            if norm(values[index]).startswith(self.prefix):return index
        return None


class SearchCombobox(ttk.Combobox):
    def __init__(self,master=None,**kwargs):
        super().__init__(master,**kwargs)
        self._letter_search=LetterSearch()
        self.bind('<KeyPress>',self._typed,add='+')
        self.bind('<FocusOut>',lambda event:self._reset_search(),add='+')
        # O menu é uma Listbox Tcl nativa; manter suas teclas Enter/Escape/setas.
        popdown=self.tk.call('ttk::combobox::PopdownWindow',str(self))
        self._choices=str(popdown)+'.f.l'
        self._bind(('bind',self._choices),'<KeyPress>',self._typed_in_list,True)
        self._bind(('bind',self._choices),'<Unmap>',lambda event:self._reset_search(),True)

    def _reset_search(self):
        self._letter_search=LetterSearch()

    def _typed(self,event):
        return self._navigate(event,False)

    def _typed_in_list(self,event):
        return self._navigate(event,True)

    def _navigate(self,event,opened):
        if self.instate(('disabled',)) or event.state & (0x4|0x8|0x20000):return
        char=event.char
        if not char or len(char)!=1 or not char.isalnum():return
        values=self.cget('values')
        if opened:
            selection=self.tk.call(self._choices,'curselection')
            current=int(selection[0]) if selection else -1
        else:current=self.current()
        index=self._letter_search.match(values,current,char)
        if index is not None:
            if opened:
                self.tk.call(self._choices,'selection','clear',0,'end')
                self.tk.call(self._choices,'selection','set',index)
                self.tk.call(self._choices,'activate',index)
                self.tk.call(self._choices,'see',index)
            else:
                self.current(index)
                self.event_generate('<<ComboboxSelected>>',when='tail')
        return 'break'
