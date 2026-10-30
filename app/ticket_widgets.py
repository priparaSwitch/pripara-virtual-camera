"""Ticket watcher worker and two galleries integrated in the camera window."""
import json,sqlite3,threading,time
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QTimer,QSize,QUrl
from PySide6.QtGui import QIcon,QPixmap,QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QAbstractItemView
from ticket_capture import TicketCapture,DEFAULT_INPUT,DEFAULT_OUTPUT

def settings(root):
    try:
        data=json.loads((Path(root)/'ticket_settings.json').read_text(encoding='utf-8-sig'))
        return Path(data.get('input_dir',DEFAULT_INPUT)),Path(data.get('output_dir',DEFAULT_OUTPUT))
    except (OSError,ValueError,TypeError):return DEFAULT_INPUT,DEFAULT_OUTPUT

class TicketWorker(QThread):
    saved=Signal(dict);status=Signal(dict)
    def __init__(self,root):
        super().__init__();self.root=Path(root);self.stop_event=threading.Event()
    def run(self):
        capture=None;current=None;last_status=0
        try:
            while not self.stop_event.is_set():
                desired=settings(self.root)
                if current!=desired:
                    if capture:capture.close();capture=None
                    try:capture=TicketCapture(*desired);current=desired
                    except (OSError,ValueError,sqlite3.Error) as error:
                        self.status.emit({'running':False,'input_dir':str(desired[0]),'output_dir':str(desired[1]),'error':str(error)})
                        self.stop_event.wait(2);continue
                for entry in capture.poll(stop_requested=self.stop_event.is_set):self.saved.emit(entry)
                if time.monotonic()-last_status>1:
                    self.status.emit({'running':capture.input_dir.is_dir(),'input_dir':str(current[0]),'output_dir':str(current[1]),'saved':capture.saved_count,'pending':len(capture.pending),'error':capture.last_error})
                    last_status=time.monotonic()
                self.stop_event.wait(.25)
        except Exception as error:self.status.emit({'running':False,'error':str(error)})
        finally:
            if capture:capture.close()
    def stop(self):self.stop_event.set();self.wait(10000)

class TicketGallery(QWidget):
    send_image=Signal(str,str)
    def __init__(self,root,kind):
        super().__init__();self.root=Path(root);self.kind=kind;self.selected_path=None;self.signature=None
        layout=QVBoxLayout(self)
        row=QHBoxLayout();layout.addLayout(row)
        self.location=QLabel();self.location.setWordWrap(True);row.addWidget(self.location,1)
        refresh=QPushButton('새로고침');refresh.clicked.connect(self.reload);row.addWidget(refresh)
        folder=QPushButton('저장 폴더 열기');folder.clicked.connect(self.open_folder);row.addWidget(folder)
        body=QHBoxLayout();layout.addLayout(body,1)
        self.files=QListWidget();self.files.setMinimumWidth(280);self.files.setIconSize(QSize(90,120));self.files.setUniformItemSizes(True);self.files.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.files.itemSelectionChanged.connect(self.show_selected);body.addWidget(self.files,1)
        self.files.itemDoubleClicked.connect(lambda _:self.send_selected('lower'))
        right=QVBoxLayout();body.addLayout(right)
        self.preview=QLabel('저장된 티켓을 선택하세요');self.preview.setFixedSize(600,600);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setObjectName('preview');right.addWidget(self.preview)
        self.caption=QLabel('');self.caption.setWordWrap(True);right.addWidget(self.caption)
        actions=QHBoxLayout();right.addLayout(actions)
        for role,text in [('lower','하부 QR 카메라에 표시'),('upper','상부 카메라에 표시')]:
            button=QPushButton(text);button.clicked.connect(lambda checked=False,r=role:self.send_selected(r));actions.addWidget(button)
        self.count=QLabel();layout.addWidget(self.count)
        self.timer=QTimer(self);self.timer.timeout.connect(self.reload);self.timer.start(2000);self.reload()
    def reload(self):
        _,directory=settings(self.root);self.location.setText(str(directory))
        try:
            paths=sorted(directory.glob('myticket_*_'+self.kind+'.png'),reverse=True)
            sig=[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
        except OSError:paths=[];sig=[]
        if self.signature==sig:return
        self.signature=sig;previous=self.selected_path
        self.files.blockSignals(True);self.files.clear()
        selected=None
        for path in paths:
            item=QListWidgetItem(path.name);item.setData(Qt.ItemDataRole.UserRole,str(path));item.setIcon(QIcon(str(path)));self.files.addItem(item)
            if str(path)==previous:selected=item
        self.files.blockSignals(False)
        if selected:self.files.setCurrentItem(selected)
        elif self.files.count():self.files.setCurrentRow(0)
        else:self.selected_path=None;self.preview.clear();self.preview.setText('아직 저장된 티켓이 없습니다');self.caption.clear()
        self.count.setText(f'{"마이티켓" if self.kind=="my" else "우정티켓"} {len(paths)}장 · 두 번 클릭하면 하부 QR 카메라에 표시합니다.')
    def show_selected(self):
        item=self.files.currentItem()
        if not item:return
        self.selected_path=item.data(Qt.ItemDataRole.UserRole);image=QPixmap(self.selected_path)
        if image.isNull():self.caption.setText('이미지를 불러오는 중입니다. 잠시 후 새로고침하세요.');return
        self.preview.setPixmap(image.scaled(600,600,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.caption.setText(Path(self.selected_path).name+f' · {image.width()}×{image.height()}')
    def send_selected(self,role='lower'):
        if self.selected_path:self.send_image.emit(self.selected_path,role)
    def open_folder(self):
        _,directory=settings(self.root)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
