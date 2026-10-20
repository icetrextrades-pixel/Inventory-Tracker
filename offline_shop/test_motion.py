import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import App,blend_color

class Controller:
    def __init__(self):
        self._animations={};self.pending={};self.cancelled=[];self.counter=0;self.reduced=False
        self.reduce_motion=type('Setting',(),{'get':lambda setting:self.reduced})()
    def after(self,ms,callback):
        self.counter+=1;key=str(self.counter);self.pending[key]=callback;return key
    def after_cancel(self,key):self.cancelled.append(key);self.pending.pop(key,None)
    def animate(self,*args):return App.animate(self,*args)

class MotionTests(unittest.TestCase):
    def test_rapid_replacement_cancels_stale_callbacks(self):
        controller=Controller();clock=[0.0];old=[];new=[]
        with patch('time.perf_counter',side_effect=lambda:clock[0]):
            controller.animate('page',100,old.append)
            stale=controller.pending['1']
            controller.animate('page',100,new.append)
            stale()
            self.assertEqual(old,[0.0])
            self.assertIn('1',controller.cancelled)
            clock[0]=.2
            controller.pending['2']()
        self.assertEqual(new[-1],1.0)
        self.assertEqual(controller._animations,{})
    def test_reduce_motion_finishes_without_background_frames(self):
        controller=Controller();controller.reduced=True;steps=[]
        controller.animate('hero',650,steps.append)
        self.assertEqual(steps,[1.0]);self.assertEqual(controller.pending,{})
    def test_toggling_reduce_motion_finishes_pending_and_persists(self):
        controller=Controller();steps=[]
        controller.animate('hero',650,steps.append);controller.reduced=True
        with tempfile.TemporaryDirectory() as folder,patch('app.DATA',Path(folder)):
            App.toggle_motion(controller)
            self.assertEqual(json.loads((Path(folder)/'motion-settings.json').read_text()),{'reduce_motion':True})
        self.assertEqual(steps[-1],1.0)
        self.assertEqual(controller.pending,{})
        self.assertEqual(controller._animations,{})
    def test_colours_finish_at_exact_endpoints(self):
        self.assertEqual(blend_color('#000000','#ffffff',0),'#000000')
        self.assertEqual(blend_color('#000000','#ffffff',1),'#ffffff')
        self.assertEqual(blend_color('#142d32','#28545b',5),'#28545b')

if __name__=='__main__':unittest.main()
