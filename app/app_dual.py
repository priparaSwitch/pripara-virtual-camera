"""Two independent PriPara camera outputs, one image library per channel."""
import sys, time, json, threading, shutil, traceback
from pathlib import Path
import camera_output as pyvirtualcam
import numpy as np
from camera_broker import Broker,run_helper
from single_instance import InstanceLock,notify_primary,listen_for_activation,event
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QTabWidget,QMessageBox
from app import ROOT,Window,configure,atomic_json
from ticket_widgets import TicketWorker,TicketGallery

DEVICES={'upper':'PriPara Upper Camera','lower':'PriPara QR Camera'}

class Stream(QThread):
    status=Signal(str);failed=Signal(str)
    def __init__(self,frame,device,broker,role):
        super().__init__();self._lock=threading.Lock();self._frame=frame;self._generation=1;self._force=False;self.device=device;self.broker=broker;self.role=role;self.stop_event=threading.Event();self.frames=0;self.last_frame_at=0;self.error=None;self.last_revision=None;self.refresh_count=0
    @property
    def frame(self):
        with self._lock:return self._frame
    @frame.setter
    def frame(self,frame):self.submit_frame(frame)
    def submit_frame(self,frame,force=False):
        with self._lock:self._frame=frame;self._generation+=1;self._force=force
    def snapshot(self):
        with self._lock:return self._generation,self._frame,self._force
    def run(self):
        try:
            h,w,_=self.frame.shape;sent=0;announced=False;black_until=None;publish_failed_at=None
            self.status.emit('송출 도우미 연결 중 · '+self.device)
            while not self.stop_event.is_set():
                generation,frame,force=self.snapshot()
                try:
                    if black_until is not None and time.monotonic()>=black_until:
                        self.last_revision=self.broker.request(self.role,self.device,frame);sent=generation;black_until=None
                    elif black_until is None and generation!=sent:
                        if force:
                            self.last_revision=self.broker.request(self.role,self.device,np.zeros_like(frame));black_until=time.monotonic()+.20;self.refresh_count+=1
                        else:self.last_revision=self.broker.request(self.role,self.device,frame);sent=generation
                    publish_failed_at=None
                except OSError:
                    if publish_failed_at is None:publish_failed_at=time.monotonic()
                    if time.monotonic()-publish_failed_at>5:raise
                producer=self.broker.status()
                if producer.get('stopped'):raise RuntimeError('송출 도우미가 종료되었습니다. 이미지 카메라 앱을 다시 실행해 주세요.')
                if producer.get('at') and time.time()-producer['at']>10:raise RuntimeError('송출 도우미의 응답이 멈췄습니다. 이미지 카메라 앱을 다시 실행해 주세요.')
                state=producer.get('channels',{}).get(self.role,{})
                self.frames=state.get('frames',0)
                if state.get('running'):
                    self.last_frame_at=time.time()
                    if not announced:self.status.emit(f'송출 중 · {self.device} · {w}×{h} / 30 fps');announced=True
                if state.get('error'):raise RuntimeError(state['error'])
                self.stop_event.wait(0.05)
        except Exception as e:self.error=str(e);self.failed.emit(str(e))
        finally:
            try:self.broker.request(self.role,self.device,self.frame,running=False)
            except OSError:pass
    def stop(self):self.stop_event.set();self.wait(3000)

class Channel(Window):
    def __init__(self,root,role,broker=None):
        self.role=role;self.device=DEVICES[role];self.broker=broker
        super().__init__(root)
        self.paste_shortcut.setEnabled(False);self.open_shortcut.setEnabled(False)
        if role=='lower':
            self.res.blockSignals(True);self.res.clear();self.res.addItem('640×480');self.res.blockSignals(False)
            self.res.setToolTip('원본 QR 리더 호환: 640×480 YUY2')
        self.setWindowFlags(Qt.WindowType.Widget)
        label='상부 카메라 · 일반 촬영용' if role=='upper' else '하부 카메라 · QR 스캔용'
        self.findChild(QLabel,'title').setText(label)
        self.status.setText('송출 대기 · '+self.device)
    def toggle_camera(self):
        if self.camera:
            self.camera.stop();self.camera=None;self.start.setText('가상 카메라 시작');self.status.setText('송출 중지 · '+self.device);self.res.setEnabled(True)
        else:
            self.camera=Stream(self.output(),self.device,self.broker,self.role);self.camera.status.connect(self.status.setText);self.camera.failed.connect(self.camera_error)
            self.camera.start();self.start.setText('가상 카메라 중지');self.res.setEnabled(False)
    def camera_error(self,message):
        if self.camera:self.camera.wait(1000);self.camera=None
        self.start.setText('가상 카메라 시작');self.res.setEnabled(True);self.status.setText('송출 실패 · '+self.device);self.error(message)

class DualWindow(QMainWindow):
    def __init__(self,root=ROOT,broker=None):
        super().__init__();self.root=root;self.broker=broker;self.setWindowTitle('프리파라 듀얼 이미지 카메라')
        center=QWidget();self.setCentralWidget(center);layout=QVBoxLayout(center)
        top=QHBoxLayout();layout.addLayout(top)
        text=QLabel('상부 촬영 / 하부 QR · 서로 다른 이미지를 독립적으로 송출합니다.');top.addWidget(text)
        start=QPushButton('두 카메라 시작');start.clicked.connect(self.start_both);top.addWidget(start)
        stop=QPushButton('두 카메라 중지');stop.clicked.connect(self.stop_both);top.addWidget(stop)
        self.tabs=QTabWidget();layout.addWidget(self.tabs);self.channels={}
        for role,label in [('upper','상부 · 촬영'),('lower','하부 · QR 스캔')]:
            channel_root=root/'channels'/role
            if not (channel_root/'data/library.json').exists() and (root/'data/library.json').exists():
                shutil.copytree(root/'data',channel_root/'data',dirs_exist_ok=True)
            channel=Channel(channel_root,role,broker);self.channels[role]=channel;self.tabs.addTab(channel,label)
        self.tabs.setCurrentIndex(1)
        self.galleries={}
        for kind,label in [('my','마이티켓'),('tomo','우정티켓')]:
            gallery=TicketGallery(root,kind);gallery.send_image.connect(self.show_ticket);self.galleries[kind]=gallery;self.tabs.addTab(gallery,label)
        self.paste_shortcut=QShortcut(QKeySequence.StandardKey.Paste,self,activated=lambda:self.active_channel().paste())
        self.open_shortcut=QShortcut(QKeySequence.StandardKey.Open,self,activated=lambda:self.active_channel().open_file())
        self.ticket_status=QLabel('티켓 감시 시작 중');self.ticket_status.setWordWrap(True);layout.addWidget(self.ticket_status)
        self.ticket_state={};self.ticket_worker=TicketWorker(root);self.ticket_worker.status.connect(self.update_ticket_status);self.ticket_worker.saved.connect(self.ticket_saved);self.ticket_worker.start()
        self.timer=QTimer(self);self.timer.timeout.connect(self.write_status);self.timer.start(1000)
        self.resize(975,950)
    def active_channel(self):
        current=self.tabs.currentWidget()
        return current if isinstance(current,Channel) else self.channels['lower']
    def show_ticket(self,path,role):
        channel=self.channels[role];channel.read_path(path);self.tabs.setCurrentWidget(channel)
    def ticket_saved(self,entry):
        for gallery in self.galleries.values():gallery.reload()
        self.ticket_status.setText('티켓 저장 완료 · '+Path(entry['full']).name)
    def update_ticket_status(self,state):
        self.ticket_state=state
        if state.get('error'):text='티켓 처리 대기 · '+state['error']
        elif not state.get('running'):text='티켓 감시 폴더 대기 · '+state.get('input_dir','')
        else:text='BMP 자동 저장 · '+state.get('input_dir','')+' → '+state.get('output_dir','')
        self.ticket_status.setText(text)
    def start_both(self):
        for channel in self.channels.values():
            if not channel.camera:channel.toggle_camera()
    def stop_both(self):
        for channel in self.channels.values():
            if channel.camera:channel.toggle_camera()
        self.write_status()
    def write_status(self):
        data={'timestamp':time.time(),'ui_pid':__import__('os').getpid(),'single_instance':True,'tickets':self.ticket_state,'channels':{},'producer':self.broker.status() if self.broker else {},'ui_elevated':bool(__import__('ctypes').windll.shell32.IsUserAnAdmin())}
        for role,c in self.channels.items():
            cam=c.camera
            data['channels'][role]={'device':c.device,'running':bool(cam and cam.isRunning()),'frames_sent':cam.frames if cam else 0,'last_frame_at':cam.last_frame_at if cam else None,'requested_revision':cam.last_revision if cam else None,'refresh_count':cam.refresh_count if cam else 0,'size':list(c.output().shape[:2][::-1]),'fit':c.mode.currentText(),'mirror':c.mirror.isChecked(),'rotation':c.rotation.currentIndex(),'error':cam.error if cam else None}
        try:atomic_json(self.root/'dual_status.json',data)
        except OSError:pass  # Optional status file must not stop the UI/streams.
    def closeEvent(self,event):
        self.ticket_worker.stop()
        self.stop_both()
        if self.broker:self.broker.close()
        event.accept()

def main():
    if len(sys.argv)==3 and sys.argv[1]=='--offline-self-test':
        from offline_check import run
        run(Path(sys.argv[2]));return
    if len(sys.argv)>=3 and sys.argv[1]=='--stream-helper':
        run_helper(sys.argv[2],ROOT);return
    instance=InstanceLock('Editor')
    app=QApplication(sys.argv);configure(app)
    if not instance.primary:
        activated=notify_primary();event(ROOT,'duplicate_editor_blocked',activated=activated);return
    try:
        broker=Broker(ROOT);win=DualWindow(broker=broker);server=listen_for_activation(win,ROOT)
        event(ROOT,'editor_started');win.show();QTimer.singleShot(300,win.start_both);sys.exit(app.exec())
    except Exception:
        (ROOT/'error.log').write_text(traceback.format_exc(),encoding='utf-8');QMessageBox.critical(None,'듀얼 카메라 시작 오류',traceback.format_exc())
    finally:instance.close()

if __name__=='__main__':main()
