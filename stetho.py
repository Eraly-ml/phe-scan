import time, threading, queue, tkinter as tk
from tkinter import ttk
from collections import deque
import numpy as np
import serial
from serial.tools import list_ports
import sounddevice as sd
from scipy import signal

RATE=4000; BLOCK=128
BG='#101a25'; PANEL='#192835'; EDGE='#293d4a'; TEXT='#e8f2f1'; MUTED='#91a7ad'; TEAL='#71e1c4'; BLUE='#263d48'
CODE='''import machine,time,sys\na=machine.ADC(machine.Pin(34))\na.atten(machine.ADC.ATTN_11DB)\nb=bytearray(128)\nt=time.ticks_us()\nwhile True:\n for i in range(128):\n  t=time.ticks_add(t,250)\n  while time.ticks_diff(t,time.ticks_us())>0: pass\n  b[i]=a.read_u16()>>8\n sys.stdout.buffer.write(b)\n'''

class App:
 def __init__(self,root):
  self.root=root;root.title('Stetho • живой звук');root.geometry('1060x740');root.minsize(860,680);root.configure(bg=BG)
  self.running=False;self.ser=None;self.q=queue.Queue(maxsize=8);self.wave=deque(maxlen=5000);self.threads=[];self.generation=0;self.last_data=0
  self.params={'gain':2.,'cut':500,'gate':0.,'notch':False};self.port=tk.StringVar();self.state=tk.StringVar(value='Не подключено');self.detail=tk.StringVar(value='Подключи ESP32 по USB и выбери порт');self.gainvar=tk.DoubleVar(value=2);self.cutvar=tk.DoubleVar(value=500);self.gatevar=tk.DoubleVar(value=0);self.notchvar=tk.BooleanVar(value=False)
  self.build();self.refresh_ports();root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.draw)
 def label(self,parent,text,**kw):
  return tk.Label(parent,text=text,bg=kw.pop('bg',PANEL),fg=kw.pop('fg',TEXT),font=kw.pop('font',('Segoe UI',10)),**kw)
 def button(self,parent,text,cmd,primary=False):
  return tk.Button(parent,text=text,command=cmd,bg=TEAL if primary else BLUE,fg=BG if primary else TEXT,activebackground='#a3ecd9' if primary else '#36515d',activeforeground=BG if primary else TEXT,bd=0,cursor='hand2',font=('Segoe UI',10,'bold'),padx=16,pady=9)
 def build(self):
  shell=tk.Frame(self.root,bg=BG);shell.pack(fill='both',expand=True,padx=28,pady=20)
  top=tk.Frame(shell,bg=BG);top.pack(fill='x')
  tk.Label(top,text='◉  stetho',font=('Segoe UI',20,'bold'),fg=TEAL,bg=BG).pack(side='left')
  tk.Label(top,text='СЛУШАТЬ  /  НАБЛЮДАТЬ',font=('Segoe UI',9,'bold'),fg=MUTED,bg=BG).pack(side='left',padx=22)
  self.badge=tk.Label(top,textvariable=self.state,bg=BLUE,fg=TEAL,font=('Segoe UI',10,'bold'),padx=14,pady=7);self.badge.pack(side='right')
  self.label(shell,'Звук тела, в реальном времени',bg=BG,font=('Segoe UI',17,'bold')).pack(anchor='w',pady=(18,2))
  self.label(shell,'Подключи стетоскоп и настрой звук под себя',bg=BG,fg=MUTED).pack(anchor='w')
  conn=tk.Frame(shell,bg=PANEL,padx=16,pady=12);conn.pack(fill='x',pady=(18,12))
  self.label(conn,'ПОРТ УСТРОЙСТВА',fg=MUTED,font=('Segoe UI',9,'bold')).pack(side='left',padx=(0,12))
  self.combo=ttk.Combobox(conn,textvariable=self.port,state='readonly',width=14);self.combo.pack(side='left')
  self.button(conn,'Обновить',self.refresh_ports).pack(side='left',padx=8)
  self.connect_btn=self.button(conn,'Подключить',self.connect,True);self.connect_btn.pack(side='right')
  graph=tk.Frame(shell,bg=PANEL,padx=18,pady=15);graph.pack(fill='both',expand=True)
  gh=tk.Frame(graph,bg=PANEL);gh.pack(fill='x');self.label(gh,'Звуковая волна',font=('Segoe UI',12,'bold')).pack(side='left');self.label(gh,'ПОСЛЕДНИЕ 5 СЕКУНД',fg=MUTED,font=('Segoe UI',9,'bold')).pack(side='right')
  self.canvas=tk.Canvas(graph,bg='#111d27',highlightthickness=0,height=170);self.canvas.pack(fill='both',expand=True,pady=(12,8))
  tk.Label(graph,textvariable=self.detail,bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(fill='x')
  controls=tk.Frame(shell,bg=PANEL,padx=18,pady=14);controls.pack(fill='x',pady=(12,0))
  header=tk.Frame(controls,bg=PANEL);header.pack(fill='x');self.label(header,'Настройки звука',font=('Segoe UI',12,'bold')).pack(side='left');self.button(header,'Сердце',lambda:self.preset('heart')).pack(side='right',padx=(8,0));self.button(header,'Дыхание',lambda:self.preset('breath')).pack(side='right')
  row=tk.Frame(controls,bg=PANEL);row.pack(fill='x',pady=(8,0));self.slider(row,'Усиление',self.gainvar,0,5,.1,'gain',0);self.slider(row,'Верхняя частота, Гц',self.cutvar,40,1500,10,'cut',1);self.slider(row,'Подавление тишины',self.gatevar,0,.1,.005,'gate',2)
  checks=tk.Frame(controls,bg=PANEL);checks.pack(fill='x',pady=(3,0));tk.Checkbutton(checks,text='Убрать гул 50 Гц',variable=self.notchvar,command=self.changed,bg=PANEL,fg=TEXT,activebackground=PANEL,activeforeground=TEXT,selectcolor=BG,font=('Segoe UI',10)).pack(side='left')
  self.label(checks,'Сильное подавление может скрыть тихие звуки',fg=MUTED,font=('Segoe UI',9)).pack(side='right')
  self.label(shell,'Учебный инструмент: график показывает звук, а не ЭКГ.',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(10,0))
 def slider(self,parent,title,var,lo,hi,step,key,col):
  parent.grid_columnconfigure(col,weight=1,uniform='c');f=tk.Frame(parent,bg=PANEL);f.grid(row=0,column=col,sticky='ew',padx=(0,16));self.label(f,title,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w')
  tk.Scale(f,variable=var,from_=lo,to=hi,resolution=step,orient='horizontal',showvalue=True,command=lambda _:self.changed(),bg=PANEL,fg=TEXT,highlightthickness=0,troughcolor=EDGE,activebackground=TEAL,sliderrelief='flat',font=('Segoe UI',9)).pack(fill='x')
 def changed(self): self.params.update(gain=float(self.gainvar.get()),cut=int(self.cutvar.get()),gate=float(self.gatevar.get()),notch=bool(self.notchvar.get()))
 def preset(self,kind):
  if kind=='heart': self.cutvar.set(80);self.gainvar.set(2);self.notchvar.set(False)
  else: self.cutvar.set(500);self.gainvar.set(2);self.notchvar.set(False)
  self.gatevar.set(0);self.changed()
 def refresh_ports(self):
  ports=list(list_ports.comports());names=[p.device for p in ports];self.combo['values']=names
  preferred=next((p.device for p in ports if p.vid==0x10c4 and p.pid==0xea60),None)
  if self.port.get() not in names:self.port.set(preferred or '')
  if not names:self.detail.set('ESP32 не найдена. Подключи USB и нажми «Обновить».')
 def ui(self,fn):
  try:self.root.after(0,fn)
  except RuntimeError:pass
 def connect(self):
  if self.running:self.disconnect();return
  if not self.port.get():self.refresh_ports();self.detail.set('Сначала подключи ESP32 и выбери COM-порт.');return
  self.running=True;self.generation+=1;gen=self.generation;self.wave.clear();self.q=queue.Queue(maxsize=8);self.last_data=0;self.state.set('Подключение');self.detail.set('Запускаем передачу с ESP32…');self.connect_btn.configure(text='Отключить');threading.Thread(target=self.worker,args=(gen,self.port.get()),daemon=True).start()
 def disconnect(self):
  self.running=False;self.generation+=1
  if self.ser:
   try:self.ser.write(b'\x03');self.ser.close()
   except Exception:pass
  self.ser=None;self.state.set('Отключено');self.detail.set('Выбери порт и нажми «Подключить»');self.connect_btn.configure(text='Подключить')
 def failure(self,gen,msg):
  def show():
   if self.generation==gen:self.disconnect();self.state.set('Ошибка');self.detail.set(msg)
  self.ui(show)
 def worker(self,gen,port):
  ser=None
  try:
   ser=serial.Serial(port,115200,timeout=1);self.ser=ser;time.sleep(3);ser.write(b'\x03\x03\r\n');time.sleep(.6);ser.read_all();ser.write(b'\x01');time.sleep(.4);reply=ser.read_all()
   if b'raw REPL' not in reply: raise RuntimeError('ESP32 не ответила. Нажми EN/RST на плате и попробуй снова.')
   ser.write(CODE.encode()+b'\x04');time.sleep(.4);reply=ser.read(2)
   if reply!=b'OK':raise RuntimeError('Не удалось запустить поток на ESP32. Проверь прошивку.')
   if not self.running or gen!=self.generation:return
   self.ui(lambda:self.state.set('Подключено'));self.ui(lambda:self.detail.set('Слушаем GPIO34  •  фильтрованная звуковая волна'))
   threading.Thread(target=self.play,args=(gen,),daemon=True).start()
   last=None;zi=None;gate_gain=1.
   while self.running and gen==self.generation:
    b=ser.read(BLOCK)
    if len(b)!=BLOCK:continue
    self.last_data=time.monotonic();p=self.params.copy();settings=(p['cut'],p['notch'])
    if settings!=last:
     sos=signal.butter(4,[20,settings[0]],btype='bandpass',fs=RATE,output='sos')
     if settings[1]:
      bn,an=signal.iirnotch(50,12,fs=RATE);sos=np.vstack((sos,signal.tf2sos(bn,an)))
     zi=signal.sosfilt_zi(sos)*((b[0]-128)/128);last=settings
    x=(np.frombuffer(b,dtype=np.uint8).astype(np.float32)-128)/128;y,zi=signal.sosfilt(sos,x,zi=zi)
    level=float(np.sqrt(np.mean(y*y)));target=1. if p['gate']<=0 else .12+.88*min(1.,(level/p['gate'])**2);gate_gain+=.18*(target-gate_gain)
    out=np.clip(y*p['gain']*gate_gain,-.75,.75).astype(np.float32);self.wave.extend(out[::4].tolist())
    try:self.q.put_nowait(out)
    except queue.Full:
     try:self.q.get_nowait();self.q.put_nowait(out)
     except queue.Empty:pass
  except Exception as e:self.failure(gen,str(e))
  finally:
   if ser:
    try:ser.close()
    except Exception:pass
 def play(self,gen):
  try:
   with sd.OutputStream(samplerate=RATE,channels=1,dtype='float32',blocksize=BLOCK) as stream:
    while self.running and gen==self.generation:
     try:a=self.q.get(timeout=.2)
     except queue.Empty:a=np.zeros(BLOCK,dtype=np.float32)
     stream.write(a.reshape(-1,1))
  except Exception as e:self.failure(gen,'Ошибка аудиоустройства: '+str(e))
 def draw(self):
  c=self.canvas;c.delete('all');w=max(c.winfo_width(),1);h=max(c.winfo_height(),1)
  for j in range(1,5):c.create_line(j*w/5,0,j*w/5,h,fill='#213440')
  for j in range(1,4):c.create_line(0,j*h/4,w,j*h/4,fill='#213440')
  values=list(self.wave)[-5000::4]
  if len(values)>1:
   pts=[]
   for i,v in enumerate(values):pts.extend((i*w/1250,h/2-max(-1,min(1,v))*h*.43))
   c.create_line(*pts,fill=TEAL,width=1.3)
  if self.running and self.last_data and time.monotonic()-self.last_data>3:self.detail.set('Нет данных с платы. Проверь подключение и попробуй переподключиться.')
  self.root.after(100,self.draw)
 def close(self):self.disconnect();self.root.destroy()

if __name__=='__main__':
 root=tk.Tk();App(root);root.mainloop()

