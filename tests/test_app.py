import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile, json
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QMimeData,QUrl
from PySide6.QtGui import QImage,QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from app import Library,render,Window

def test():
    app=QApplication([])
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
        root=Path(tmp);lib=Library(root/'data')
        for i in range(12):lib.import_image(Image.new('RGB',(20,30),(i,0,0)),str(i))
        assert len(lib.data['recent'])==10
        assert lib.data['recent'][0]['name']=='11'
        entry=lib.data['recent'][0]
        lib.slot(1,entry);lib.slot(1000,entry)
        for bad in (0,1001):
            try:lib.slot(bad,entry);raise AssertionError('boundary')
            except ValueError:pass
        lib=Library(root/'data');assert len(lib.data['slots'])==2
        frame=render(Image.new('RGB',(20,40),'red'),(640,480))
        assert frame.shape==(480,640,3) and tuple(frame[0,0])==(255,255,255)
        assert tuple(frame[240,320])==(255,0,0)
        assert tuple(render(Image.new('RGB',(20,40),'red'),(640,480),'화면 채우기')[0,0])==(255,0,0)
        im=Image.new('RGB',(2,1),'red');im.putpixel((1,0),(0,0,255))
        assert tuple(render(im,(2,1),mirror=True)[0,0])==(0,0,255)
        win=Window(root);assert win.slots.count()==1000
        qi=QImage(31,17,QImage.Format.Format_RGB888);qi.fill(0xff00ff)
        app.clipboard().setImage(qi);win.paste();assert win.image.size==(31,17)
        win.number.setValue(999);win.save_slot();assert '999' in win.lib.data['slots']
        win.search.setText('0999');assert win.slots.count()==1
        file=root/'drop.png';Image.new('RGB',(45,60),'blue').save(file)
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(file))])
        class Event:
            accepted=False
            def mimeData(self):return mime
            def acceptProposedAction(self):self.accepted=True
        event=Event();win.dragEnterEvent(event);assert event.accepted
        win.dropEvent(event);assert win.image.size==(45,60)
        file.unlink();win.load_slot();assert win.image.size==(31,17)
        win.close();win=Window(root);assert win.image.size==(31,17)
        win.close()
    result={'passed':True,'checks':['recent limit/dedup','slot boundaries 1/1000','persistent slots','fit/crop/mirror RGB frames','1000-slot GUI','clipboard bitmap','slot save/load','slot search','drag/drop file','source deletion independence','last image restart'],'game_tested':False}
    (Path(__file__).resolve().parents[1]/'build/offline-tests/app_ui_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':test()
