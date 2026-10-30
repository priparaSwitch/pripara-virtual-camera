"""PriPara image camera. All user data lives alongside the executable."""
import sys, os, json, hashlib, threading, time, traceback, subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from ipc_files import atomic_json as write_atomic_json
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal
from PySide6.QtGui import QImage, QPixmap, QIcon, QKeySequence, QShortcut, QFontDatabase, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QSpinBox, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QLineEdit, QGroupBox)

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent

def atomic_json(path, data):
    write_atomic_json(path,data,ensure_ascii=False,indent=2)

class Library:
    def __init__(self, root):
        self.root = Path(root); self.images = self.root / 'images'
        self.images.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'library.json'
        self.data = {'recent': [], 'slots': {}, 'current': None}
        if self.path.exists():
            # Never silently overwrite a damaged library.
            self.data.update(json.loads(self.path.read_text(encoding='utf-8')))

    def save(self): atomic_json(self.path, self.data)

    def import_image(self, image, name):
        image = ImageOps.exif_transpose(image).convert('RGBA')
        image.load()
        digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        dest = self.images / (digest + '.png')
        if not dest.exists():
            tmp = dest.with_suffix('.tmp'); image.save(tmp, 'PNG'); os.replace(tmp, dest)
        entry = {'id': digest, 'name': name}
        self.touch(entry)
        return entry

    def touch(self, entry):
        self.data['recent'] = [entry] + [e for e in self.data['recent'] if e['id'] != entry['id']][:9]
        self.data['current'] = entry; self.save()

    def load(self, entry):
        with Image.open(self.images / (entry['id'] + '.png')) as im:
            return im.convert('RGBA')

    def slot(self, number, entry):
        if not 1 <= number <= 1000: raise ValueError('슬롯은 1~1000입니다.')
        self.data['slots'][str(number)] = dict(entry); self.save()

    def clear_slot(self, number):
        self.data['slots'].pop(str(number), None); self.save()

def render(image, size, mode='전체 보기', mirror=False, rotation=0):
    w, h = size
    bg = Image.new('RGB', size, 'white')
    if image is None: return np.asarray(bg).copy()
    im = image.convert('RGBA')
    base = Image.new('RGBA', im.size, 'white'); base.alpha_composite(im)
    im = base.convert('RGB')
    if rotation: im = im.rotate(rotation, expand=True)
    if mirror: im = ImageOps.mirror(im)
    if mode == '화면 채우기': return np.asarray(ImageOps.fit(im, size, method=Image.Resampling.LANCZOS)).copy()
    im = ImageOps.contain(im, size, method=Image.Resampling.LANCZOS)
    bg.paste(im, ((w-im.width)//2, (h-im.height)//2))
    return np.asarray(bg).copy()

def pixmap(frame):
    h, w, _ = frame.shape
    return QPixmap.fromImage(QImage(frame.data, w, h, w*3, QImage.Format.Format_RGB888).copy())

class Camera(QThread):
    status = Signal(str); failed = Signal(str)
    def __init__(self, frame):
        super().__init__(); self.frame = frame; self.stop_event = threading.Event()
    def run(self):
        try:
            import camera_output as pyvirtualcam
            h,w,_ = self.frame.shape
            with pyvirtualcam.Camera(width=w, height=h, fps=30, backend='unitycapture',device='PriPara Upper Camera', fmt=pyvirtualcam.PixelFormat.RGB) as cam:
                self.status.emit(f'송출 중 · {cam.device} · {w}×{h} / 30 fps')
                while not self.stop_event.is_set():
                    cam.send(self.frame); cam.sleep_until_next_frame()
        except Exception as e: self.failed.emit(str(e))
    def stop(self): self.stop_event.set(); self.wait(3000)

class Window(QMainWindow):
    def __init__(self, root=ROOT):
        super().__init__(); self.setWindowTitle('프리파라 이미지 카메라')
        self.lib = Library(root / 'data'); self.image = None; self.entry = None; self.camera = None
        self.setAcceptDrops(True)
        host = QWidget(); self.setCentralWidget(host); outer = QVBoxLayout(host)
        title = QLabel('PRIPARA  /  IMAGE CAMERA'); title.setObjectName('title'); outer.addWidget(title)
        tools = QHBoxLayout(); outer.addLayout(tools)
        self.button(tools, '이미지 열기', self.open_file)
        self.button(tools, '붙여넣기  Ctrl+V', self.paste)
        self.button(tools, '이미지 내보내기', self.export)
        self.button(tools, '다시 송출', lambda:self.refresh(force=True))
        body = QHBoxLayout(); outer.addLayout(body)
        left = QVBoxLayout(); body.addLayout(left)
        self.preview = QLabel('이미지를 놓거나 Ctrl+V로 붙여넣으세요'); self.preview.setFixedSize(600,600)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setObjectName('preview'); left.addWidget(self.preview)
        self.caption = QLabel('이미지가 없습니다'); self.caption.setWordWrap(True); left.addWidget(self.caption)
        opts = QHBoxLayout(); left.addLayout(opts)
        self.mode = QComboBox(); self.mode.addItems(['전체 보기', '화면 채우기']); opts.addWidget(self.mode)
        self.mirror = QCheckBox('좌우 반전'); opts.addWidget(self.mirror)
        self.rotation = QComboBox(); self.rotation.addItems(['회전 없음','왼쪽 90°','180°','오른쪽 90°']); opts.addWidget(self.rotation)
        self.res = QComboBox(); self.res.addItems(['640×480', '600×600', '1280×720']); opts.addWidget(self.res)
        for control in [self.mode,self.rotation]: control.currentIndexChanged.connect(self.refresh)
        self.mirror.toggled.connect(self.refresh); self.res.currentIndexChanged.connect(self.resolution_changed)
        camera_row=QHBoxLayout(); left.addLayout(camera_row)
        self.start = self.button(camera_row, '가상 카메라 시작', self.toggle_camera)
        self.button(camera_row, '게임 연결 설정', self.game_setup)
        self.status = QLabel('송출 대기 · 프리파라 가상 카메라'); self.status.setWordWrap(True); left.addWidget(self.status)
        side = QVBoxLayout(); body.addLayout(side)
        side.addWidget(QLabel('최근 이미지 · 최대 10개'))
        self.recent = QListWidget(); self.recent.setIconSize(QSize(48,48)); self.recent.setFixedWidth(280); self.recent.setMaximumHeight(220)
        self.recent.itemClicked.connect(lambda item:self.select(item.data(Qt.ItemDataRole.UserRole))); side.addWidget(self.recent)
        side.addWidget(QLabel('보관함 · 1,000개 슬롯'))
        self.search = QLineEdit(); self.search.setPlaceholderText('슬롯 번호 또는 이름 검색'); self.search.textChanged.connect(self.populate_slots); side.addWidget(self.search)
        self.slots = QListWidget(); self.slots.setIconSize(QSize(40,40)); self.slots.itemDoubleClicked.connect(self.load_slot); side.addWidget(self.slots)
        row = QHBoxLayout(); side.addLayout(row); row.addWidget(QLabel('슬롯 번호'))
        self.number = QSpinBox(); self.number.setRange(1,1000); row.addWidget(self.number)
        self.slots.itemClicked.connect(lambda item:self.number.setValue(item.data(Qt.ItemDataRole.UserRole)))
        row=QHBoxLayout(); side.addLayout(row)
        self.button(row,'저장',self.save_slot); self.button(row,'불러오기',self.load_slot); self.button(row,'비우기',self.delete_slot)
        hint=QLabel('슬롯을 더블클릭하면 즉시 표시합니다.\n원본 파일을 옮겨도 보관한 이미지는 유지됩니다.'); hint.setWordWrap(True); side.addWidget(hint)
        self.paste_shortcut=QShortcut(QKeySequence.StandardKey.Paste,self,activated=self.paste)
        self.open_shortcut=QShortcut(QKeySequence.StandardKey.Open,self,activated=self.open_file)
        for shortcut in (self.paste_shortcut,self.open_shortcut):shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.populate_recent(); self.populate_slots()
        if self.lib.data['current']:
            self.select(self.lib.data['current'])
        self.resize(940,850)

    def button(self, layout, text, callback):
        b=QPushButton(text); b.clicked.connect(callback); layout.addWidget(b); return b
    def error(self, error): QMessageBox.warning(self,'이미지 카메라',str(error))
    def read_path(self,path):
        try:
            with Image.open(path) as im: entry=self.lib.import_image(im,Path(path).name)
            self.select(entry)
        except Exception as e: self.error(e)
    def open_file(self):
        p,_=QFileDialog.getOpenFileName(self,'이미지 열기','','이미지 (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tif *.tiff);;모든 파일 (*)')
        if p:self.read_path(p)
    def paste(self):
        try:
            cb=QApplication.clipboard(); mime=cb.mimeData()
            # Explorer may offer both file URLs and a thumbnail bitmap.
            # Use the actual file, rather than its clipboard thumbnail.
            files=[url.toLocalFile() for url in mime.urls() if url.isLocalFile()] if mime.hasUrls() else []
            if files:self.read_path(files[0])
            elif mime.hasImage():
                qi=cb.image().convertToFormat(QImage.Format.Format_RGBA8888)
                if qi.isNull():raise ValueError('클립보드 이미지를 읽을 수 없습니다.')
                raw=np.frombuffer(qi.constBits(),dtype=np.uint8).reshape(qi.height(),qi.bytesPerLine())[:,:qi.width()*4].copy()
                self.select(self.lib.import_image(Image.fromarray(raw.reshape(qi.height(),qi.width(),4)), '붙여넣기 '+time.strftime('%m-%d %H:%M:%S')))
            else:
                p=cb.text().strip().strip('"')
                if Path(p).is_file():self.read_path(p)
                else:self.error('클립보드에 이미지 또는 이미지 파일이 없습니다.')
        except Exception as e:self.error(e)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():event.acceptProposedAction()
    def dropEvent(self,event):
        if event.mimeData().hasUrls():
            self.read_path(event.mimeData().urls()[0].toLocalFile());event.acceptProposedAction()
    def select(self,entry):
        try:
            self.image=self.lib.load(entry);self.entry=entry;self.lib.touch(entry)
            self.caption.setText(f"{entry['name']} · 원본 {self.image.width}×{self.image.height}")
            self.refresh(force=True);self.populate_recent()
        except Exception as e:self.error(e)
    def output(self):
        size=[(640,480),(600,600),(1280,720)][self.res.currentIndex()]
        return render(self.image,size,self.mode.currentText(),self.mirror.isChecked(),[0,90,180,270][self.rotation.currentIndex()])
    def refresh(self,*_,force=False):
        frame=self.output();self.preview.setPixmap(pixmap(frame).scaled(600,600,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        if self.camera:
            if hasattr(self.camera,'submit_frame'):self.camera.submit_frame(frame,force=force)
            else:self.camera.frame=frame
    def resolution_changed(self):
        if self.camera:self.toggle_camera()
        self.refresh()
    def populate_recent(self):
        self.recent.clear()
        for e in self.lib.data['recent']:
            item=QListWidgetItem(e['name']);item.setData(Qt.ItemDataRole.UserRole,e)
            item.setIcon(QIcon(str(self.lib.images/(e['id']+'.png'))));self.recent.addItem(item)
    def populate_slots(self,*_):
        self.slots.clear();query=self.search.text().casefold()
        for n in range(1,1001):
            e=self.lib.data['slots'].get(str(n));label=f"{n:04d}  ·  {e['name'] if e else '빈 슬롯'}"
            if query and query not in label.casefold():continue
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,n)
            if e:item.setIcon(QIcon(str(self.lib.images/(e['id']+'.png'))))
            self.slots.addItem(item)
    def save_slot(self):
        if not self.entry:return self.error('먼저 이미지를 불러오세요.')
        n=self.number.value()
        if str(n) in self.lib.data['slots'] and QMessageBox.question(self,'슬롯 덮어쓰기',f'{n:04d}번 이미지를 바꿀까요?')!=QMessageBox.StandardButton.Yes:return
        self.lib.slot(n,self.entry);self.populate_slots();self.status.setText(f'{n:04d}번 슬롯에 저장했습니다.')
    def load_slot(self,*_):
        e=self.lib.data['slots'].get(str(self.number.value()))
        if e:self.select(e)
        else:self.error('빈 슬롯입니다.')
    def delete_slot(self):
        n=self.number.value()
        if str(n) not in self.lib.data['slots']:return
        if QMessageBox.question(self,'슬롯 비우기',f'{n:04d}번 슬롯을 비울까요?')==QMessageBox.StandardButton.Yes:
            self.lib.clear_slot(n);self.populate_slots()
    def export(self):
        if self.image is None:return
        p,_=QFileDialog.getSaveFileName(self,'현재 송출 이미지 저장','camera.png','PNG (*.png)')
        if p:
            try:Image.fromarray(self.output()).save(p,'PNG')
            except Exception as e:self.error(e)
    def toggle_camera(self):
        if self.camera:
            self.camera.stop();self.camera=None;self.start.setText('가상 카메라 시작');self.status.setText('송출 중지');self.res.setEnabled(True)
        else:
            self.camera=Camera(self.output());self.camera.status.connect(self.status.setText);self.camera.failed.connect(self.camera_error)
            self.camera.start();self.start.setText('가상 카메라 중지');self.res.setEnabled(False)
    def camera_error(self,message):
        if self.camera:self.camera.wait(1000);self.camera=None
        self.start.setText('가상 카메라 시작');self.res.setEnabled(True)
        self.status.setText('송출 실패 · 프리파라 가상 카메라 설치와 중복 실행을 확인하세요.');self.error(message)
    def game_setup(self):
        import ctypes
        script=ROOT/'game_camera_setup.ps1'
        if not script.exists():return self.error('실행 파일 옆에 game_camera_setup.ps1이 필요합니다.')
        result=ctypes.windll.shell32.ShellExecuteW(None,'runas','powershell.exe',f'-NoProfile -ExecutionPolicy Bypass -File "{script}"',str(ROOT),1)
        if result<=32:self.error('게임 연결 설정을 실행하지 못했습니다.')
    def closeEvent(self,event):
        if self.camera:self.camera.stop()
        event.accept()

def configure(app):
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/malgun.ttf'
    if font.exists():QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Malgun Gothic',9));app.setStyle('Fusion')
    app.setStyleSheet('QWidget{font-family:"Malgun Gothic";font-size:12px;} QMainWindow{background:#f6f4fa;} QPushButton{padding:9px;background:#fff;border:1px solid #d9d1e8;border-radius:6px;} QPushButton:hover{background:#eee5fa;} #title{font-size:18px;font-weight:bold;color:#7748a3;padding:7px;} #preview{background:#e8e5ed;border:1px solid #d4ccdf;} QListWidget{background:white;border:1px solid #ddd5e8;border-radius:5px;} QLineEdit{padding:7px;}')

def main():
    app=QApplication(sys.argv);configure(app)
    try:win=Window();win.show();sys.exit(app.exec())
    except Exception:
        (ROOT/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        QMessageBox.critical(None,'앱 시작 오류',traceback.format_exc())

if __name__=='__main__':main()
