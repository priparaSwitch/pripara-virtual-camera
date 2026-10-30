import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import io,json,re,tempfile,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QMimeData,QUrl,Qt,QEvent
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog
from ticket_capture import TicketCapture
from app_dual import DualWindow

ROOT=Path(__file__).parent
def pump(app,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.01)

class Recorder:
    def __init__(self):self.requests=[];self.revision=0
    def request(self,role,device,frame,running=True):
        self.revision+=1;self.requests.append((role,frame.copy(),running,time.monotonic()));return self.revision
    def status(self):return {'at':time.time(),'channels':{r:{'running':True,'frames':10} for r in ('upper','lower')}}
    def close(self):pass

def test():
    app=QApplication([]);checks=[]
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        root=Path(directory);source=root/'game';dest=root/'TicketData/MyTicket';source.mkdir()
        Image.new('RGB',(1548,756),'white').save(source/'existing.bmp')
        capture=TicketCapture(source,dest,settle=.1)
        assert not capture.poll(0) and not list(dest.glob('*.png'));checks.append('startup ignores existing BMP')
        pixels=np.zeros((756,1548,3),np.uint8);pixels[:,:]=(230,240,250);pixels[:300,:400]=(255,0,0);pixels[500:,1000:]=(0,0,255)
        encoded=io.BytesIO();Image.fromarray(pixels).save(encoded,'BMP');blob=encoded.getvalue();path=source/'new.bmp'
        path.write_bytes(blob[:100]);capture.poll(1);assert not capture.poll(1.2);assert not list(dest.glob('*.png'))
        path.write_bytes(blob);capture.poll(2);saved=capture.poll(2.2);assert len(saved)==1
        item=saved[0];assert re.fullmatch(r'myticket_\d{4}-\d{2}-\d{2}_\d{6}\.png',Path(item['full']).name)
        expected=np.rot90(pixels)
        with Image.open(item['full']) as full:assert full.size==(756,1548) and np.array_equal(np.asarray(full),expected)
        with Image.open(item['tomo']) as top:assert top.size==(756,508) and np.array_equal(np.asarray(top),expected[:508])
        with Image.open(item['my']) as bottom:assert bottom.size==(756,1040) and np.array_equal(np.asarray(bottom),expected[508:])
        assert path.read_bytes()==blob;checks+=['partial BMP waits for full write','exact CCW rotation and 508 split','source preserved and filenames exact']
        capture.close();capture=TicketCapture(source,dest,settle=.1);assert not capture.poll(3);assert len(list(dest.glob('*.png')))==3
        checks.append('restart does not duplicate completed captures')
        second=source/'second.BMP';second.write_bytes(blob);capture.poll(4);another=capture.poll(4.2);assert len(another)==1 and another[0]['stamp']!=item['stamp']
        checks.append('uppercase BMP and same-second collision preserve all six files')
        # Recover a capture whose journal committed but publishing was interrupted.
        third=source/'third.bmp';third.write_bytes(blob);capture.poll(5)
        import ticket_capture
        original=ticket_capture.publish_new;calls=[]
        def interrupted(destination,data):
            calls.append(destination)
            if len(calls)==2:raise OSError('simulated interrupted publication')
            original(destination,data)
        ticket_capture.publish_new=interrupted
        try:assert not capture.poll(5.2)
        finally:ticket_capture.publish_new=original
        assert capture.db.execute("SELECT count(*) FROM captures WHERE state='pending'").fetchone()[0]==1
        capture.close();capture=TicketCapture(source,dest,settle=.1);capture.poll(6);recovered=capture.poll(6.2);assert len(recovered)==1
        assert len(list(dest.glob('*.png')))==9;checks.append('interrupted triple publication recovers without duplicates')
        capture.close()
        # A new file created while the app is closed is imported on restart.
        fourth=source/'offline.bmp';fourth.write_bytes(blob);capture=TicketCapture(source,dest,settle=.1);capture.poll(7);assert len(capture.poll(7.2))==1;capture.close()
        checks.append('new files created while closed are caught after restart')
        ui=root/'ui';ui.mkdir();(ui/'ticket_settings.json').write_text(json.dumps({'input_dir':str(source),'output_dir':str(dest)}))
        recorder=Recorder();window=DualWindow(ui,recorder);window.show();window.activateWindow();pump(app,.2)
        assert [window.tabs.tabText(i) for i in range(window.tabs.count())]==['상부 · 촬영','하부 · QR 스캔','마이티켓','우정티켓']
        assert window.galleries['my'].files.count()==4 and window.galleries['tomo'].files.count()==4
        checks.append('two ticket galleries list only their respective split images')
        channel=window.channels['lower'];channel.error=lambda message:(_ for _ in ()).throw(AssertionError(message));channel.toggle_camera();pump(app,.1)
        red=root/'red.png';blue=root/'blue.png';Image.new('RGB',(640,480),'red').save(red);Image.new('RGB',(640,480),'blue').save(blue)
        picker=QFileDialog.getOpenFileName;QFileDialog.getOpenFileName=lambda *a,**k:(str(red),'')
        try:channel.open_file()
        finally:QFileDialog.getOpenFileName=picker
        pump(app,.4);assert tuple(channel.output()[240,320])==(255,0,0)
        assert any(not frame.any() for role,frame,running,_ in recorder.requests if role=='lower' and running)
        qi=QImage(640,480,QImage.Format.Format_RGB888);qi.fill(0x00ff00);app.clipboard().setImage(qi)
        window.tabs.setCurrentWidget(channel);channel.preview.setFocus();pump(app,.05);QTest.keyClick(channel,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier);pump(app,.4)
        assert tuple(channel.output()[240,320])==(0,255,0)
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(blue))]);mime.setImageData(qi);app.clipboard().setMimeData(mime);channel.paste();pump(app,.4)
        assert tuple(channel.output()[240,320])==(0,0,255)
        before=channel.camera.refresh_count;channel.read_path(blue);pump(app,.4);assert channel.camera.refresh_count>before
        for path in (red,blue,red,blue):channel.read_path(path)
        pump(app,.4);assert tuple(recorder.requests[-1][1][240,320])==(0,0,255)
        checks+=['file picker refreshes preview and stream','one Ctrl+V shortcut updates active channel','clipboard file URL takes precedence over thumbnail','same image forces black pulse and resends','rapid selection finishes with latest image']
        window.galleries['my'].send_selected('lower');pump(app,.3);assert window.tabs.currentWidget()==channel
        checks.append('ticket gallery selection loads lower camera')
        app.clipboard().clear();window.close();window.deleteLater();pump(app,.1);app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    report={'passed':True,'checks':checks,'game_tested':False}
    (ROOT.parent/'build/offline-tests/ticket_feature_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True));app.quit()

if __name__=='__main__':test()
