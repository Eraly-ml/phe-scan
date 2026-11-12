import time, threading, queue, tkinter as tk
import sqlite3, wave, os, uuid
from pathlib import Path
from tkinter import messagebox
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
  self.record_lock=threading.Lock();self.record_file=None;self.record_patient=None;self.running=False;self.ser=None;self.q=queue.Queue(maxsize=8);self.wave=deque(maxlen=5000);self.threads=[];self.generation=0;self.last_data=0
  self.params={'gain':2.,'cut':500,'gate':0.,'notch':False};self.port=tk.StringVar();self.state=tk.StringVar(value='Не подключено');self.detail=tk.StringVar(value='Подключи ESP32 по USB и выбери порт');self.gainvar=tk.DoubleVar(value=2);self.cutvar=tk.DoubleVar(value=500);self.gatevar=tk.DoubleVar(value=0);self.notchvar=tk.BooleanVar(value=False)
  self.init_store();self.build();self.refresh_ports();root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.draw)
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
  self.button(conn,'Карточки и записи',self.open_records).pack(side='left',padx=8)
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
 def init_store(self):
  self.data_dir=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'PheScan'
  self.data_dir.mkdir(parents=True,exist_ok=True)
  self.db=sqlite3.connect(self.data_dir/'records.sqlite3')
  self.db.executescript("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY, name TEXT NOT NULL, notes TEXT NOT NULL DEFAULT ''); CREATE TABLE IF NOT EXISTS recordings(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, filename TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);")
  self.db.commit()
 def open_records(self):
  if hasattr(self,'records_window') and self.records_window.winfo_exists():self.records_window.lift();return
  w=tk.Toplevel(self.root);self.records_window=w;w.title('Карточки и записи');w.geometry('760x640');w.configure(bg=BG)
  self.label(w,'Карточки и записи',bg=BG,font=('Segoe UI',17,'bold')).pack(anchor='w',padx=20,pady=12)
  self.label(w,'Локальный прототип • не используйте реальные данные пациентов',bg=BG,fg=MUTED).pack(anchor='w',padx=20)
  f=tk.Frame(w,bg=BG);f.pack(fill='x',padx=20,pady=10)
  self.patient_list=ttk.Combobox(f,state='readonly',width=35);self.patient_list.pack(side='left');self.patient_list.bind('<<ComboboxSelected>>',lambda e:self.select_patient())
  self.button(f,'Новая карточка',self.new_patient).pack(side='left',padx=8)
  self.label(w,'Имя или код',bg=BG).pack(anchor='w',padx=20)
  self.patient_name=tk.Entry(w,font=('Segoe UI',11));self.patient_name.pack(fill='x',padx=20,pady=4)
  self.label(w,'Заметки',bg=BG).pack(anchor='w',padx=20)
  self.notes=tk.Text(w,height=5,font=('Segoe UI',10));self.notes.pack(fill='x',padx=20,pady=4)
  f=tk.Frame(w,bg=BG);f.pack(fill='x',padx=20,pady=6)
  self.button(f,'Сохранить карточку',self.save_patient).pack(side='left')
  self.rec_button=self.button(f,'Начать запись',self.toggle_record,True);self.rec_button.pack(side='left',padx=8)
  self.label(w,'Записи выбранной карточки',bg=BG).pack(anchor='w',padx=20,pady=(8,0))
  self.recordings=tk.Listbox(w,height=6);self.recordings.pack(fill='both',expand=True,padx=20,pady=5)
  f=tk.Frame(w,bg=BG);f.pack(fill='x',padx=20,pady=8)
  self.button(f,'Прослушать выбранную',self.play_recording).pack(side='left')
  self.button(f,'Остановить воспроизведение',sd.stop).pack(side='left',padx=8)
  self.label(w,'Для прослушивания записи отключите живой звук. Запись — сырой сигнал до фильтров.',bg=BG,fg=MUTED,wraplength=700).pack(padx=20,pady=8)
  self.patient_id=None;self.load_patients()
 def load_patients(self):
  self.patient_rows=self.db.execute('SELECT id,name FROM patients ORDER BY id DESC').fetchall();self.patient_list['values']=[f'{i} · {name}' for i,name in self.patient_rows]
 def new_patient(self):
  self.patient_id=None;self.patient_list.set('');self.patient_name.delete(0,'end');self.notes.delete('1.0','end');self.recordings.delete(0,'end')
 def select_patient(self):
  idx=self.patient_list.current()
  if idx<0:return
  self.patient_id=self.patient_rows[idx][0];row=self.db.execute('SELECT name,notes FROM patients WHERE id=?',(self.patient_id,)).fetchone();self.patient_name.delete(0,'end');self.patient_name.insert(0,row[0]);self.notes.delete('1.0','end');self.notes.insert('1.0',row[1]);self.load_recordings()
 def save_patient(self):
  name=self.patient_name.get().strip();notes=self.notes.get('1.0','end-1c')
  if not name:messagebox.showerror('Карточка','Укажите имя или код.');return
  if self.patient_id:self.db.execute('UPDATE patients SET name=?,notes=? WHERE id=?',(name,notes,self.patient_id))
  else:self.patient_id=self.db.execute('INSERT INTO patients(name,notes) VALUES (?,?)',(name,notes)).lastrowid
  self.db.commit();self.load_patients();self.patient_list.current(next(i for i,r in enumerate(self.patient_rows) if r[0]==self.patient_id));self.load_recordings()
 def load_recordings(self):
  self.recordings.delete(0,'end');self.record_rows=self.db.execute('SELECT id,filename,created FROM recordings WHERE patient_id=? ORDER BY id DESC',(self.patient_id,)).fetchall() if self.patient_id else []
  for _,_,created in self.record_rows:self.recordings.insert('end',created+' UTC')
 def toggle_record(self):
  if self.record_file is not None:self.stop_recording();return
  if not self.running or not self.last_data:messagebox.showerror('Запись','Сначала подключите плату и дождитесь сигнала.');return
  if not self.patient_id:messagebox.showerror('Запись','Сначала сохраните карточку.');return
  filename=uuid.uuid4().hex+'.wav';path=self.data_dir/filename
  try:
   f=wave.open(str(path),'wb');f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE)
   with self.record_lock:self.record_file=f;self.record_patient=(self.patient_id,filename)
   self.rec_button.configure(text='Остановить запись');self.detail.set('Идёт запись сырого сигнала')
  except OSError as e:messagebox.showerror('Запись',str(e))
 def stop_recording(self):
  with self.record_lock:
   if self.record_file is None:return
   f=self.record_file;patient=self.record_patient;self.record_file=None;self.record_patient=None;f.close()
  self.db.execute('INSERT INTO recordings(patient_id,filename) VALUES (?,?)',patient);self.db.commit()
  if hasattr(self,'records_window') and self.records_window.winfo_exists():self.rec_button.configure(text='Начать запись');self.load_recordings()
 def play_recording(self):
  if self.running:messagebox.showinfo('Прослушивание','Сначала отключите живой звук кнопкой «Отключить».');return
  selection=self.recordings.curselection()
  if not selection:return
  path=self.data_dir/self.record_rows[selection[0]][1]
  try:
   with wave.open(str(path),'rb') as f:data=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float32)/32768
   sd.play(data,RATE)
  except Exception as e:messagebox.showerror('Прослушивание',str(e))
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
  self.stop_recording();self.running=False;self.generation+=1
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
    x=(np.frombuffer(b,dtype=np.uint8).astype(np.float32)-128)/128
    with self.record_lock:
     if self.record_file is not None:self.record_file.writeframesraw((x*32767).astype('<i2').tobytes())
    y,zi=signal.sosfilt(sos,x,zi=zi)
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
 def close(self):self.disconnect();sd.stop();self.db.close();self.root.destroy()

if __name__=='__main__':
 root=tk.Tk();App(root);root.mainloop()

