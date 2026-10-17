import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app import App,scroll_target

class View:
    def __init__(self,master=None,limits=(0,1),kind='Frame'):
        self.master=master;self.limits=limits;self.kind=kind;self.moves=[]
    def yview(self):return self.limits
    def xview(self):return self.limits
    def yview_scroll(self,n,units):self.moves.append(('y',n))
    def xview_scroll(self,n,units):self.moves.append(('x',n))
    def winfo_class(self):return self.kind

class ScrollTests(unittest.TestCase):
    def test_child_cards_route_to_page_and_table_bubbles_at_edge(self):
        canvas=View(limits=(0,.6));inner=View(master=canvas);card=View(master=inner);label=View(master=card)
        parents={inner:canvas,canvas:canvas}
        self.assertIs(scroll_target(label,'y',3,parents),canvas)
        table=View(master=card,limits=(.4,1))
        self.assertIs(scroll_target(table,'y',3,parents),canvas)
        self.assertIs(scroll_target(table,'y',-3,parents),table)
        self.assertIsNone(scroll_target(label,'y',-3,parents))
    def controller(self,widget):
        return SimpleNamespace(scroll_widget=lambda e:widget,_wheel_remainder={},_scroll_parents={},_drag_scroll=None)
    def test_precision_wheel_accumulates_and_returns_break(self):
        table=View(limits=(.2,.8),kind='Treeview');controller=self.controller(table)
        event=SimpleNamespace(delta=-20,state=0,num=None)
        with patch('app.sys.platform','win32'):
            self.assertEqual(App.scroll_wheel(controller,event),'break')
            self.assertEqual(table.moves,[])
            App.scroll_wheel(controller,event)
        self.assertEqual(table.moves,[('y',1)])
    def test_horizontal_scroll_and_entries_keep_native_behaviour(self):
        view=View(limits=(.2,.8),kind='Text');controller=self.controller(view)
        with patch('app.sys.platform','win32'):App.scroll_wheel(controller,SimpleNamespace(delta=-120,state=1,num=None))
        self.assertEqual(view.moves,[('x',3)])
        entry=View(limits=(.2,.8),kind='TEntry')
        self.assertIsNone(App.scroll_wheel(self.controller(entry),SimpleNamespace(delta=-120,state=0,num=None)))
        self.assertEqual(entry.moves,[])
    def test_drag_threshold_and_button_clicks_are_preserved(self):
        view=View(limits=(.2,.8),kind='Treeview');controller=self.controller(view)
        App.scroll_press(controller,SimpleNamespace(x_root=20,y_root=100))
        self.assertIsNone(App.scroll_drag(controller,SimpleNamespace(x_root=20,y_root=96)))
        self.assertEqual(view.moves,[])
        self.assertEqual(App.scroll_drag(controller,SimpleNamespace(x_root=20,y_root=50)),'break')
        self.assertEqual(view.moves,[('y',2)])
        self.assertEqual(App.scroll_release(controller,None),'break')
        button=View(limits=(.2,.8),kind='TButton');controller=self.controller(button)
        App.scroll_press(controller,SimpleNamespace(x_root=20,y_root=100))
        self.assertIsNone(controller._drag_scroll)

if __name__=='__main__':unittest.main()
