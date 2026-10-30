"""Elevated video producer; the image UI remains at normal integrity for drop/paste."""
import ctypes,json,time,os,sys,subprocess,uuid
from pathlib import Path
import numpy as np
import camera_output as pyvirtualcam
from single_instance import InstanceLock,event
from ipc_files import atomic_json,atomic_bytes,read_json,read_bytes

def atomic(path,data):
    atomic_json(path,data)

def publish_status(path,data):
    # Telemetry contention must never terminate the actual video producer.
    try:atomic_json(path,data,timeout=.15);return True
    except OSError:return False

class Broker:
    def __init__(self,root):
        self.root=root;self.session=root/'ipc'/str(uuid.uuid4());self.session.mkdir(parents=True)
        atomic(self.session/'owner.json',{'pid':os.getpid()})
        if getattr(sys,'frozen',False):exe=sys.executable;args=['--stream-helper',str(self.session)]
        else:exe=sys.executable;args=[str(Path(__file__).with_name('app_dual.py')),'--stream-helper',str(self.session)]
        result=ctypes.windll.shell32.ShellExecuteW(None,'runas',exe,subprocess.list2cmdline(args),str(root),0)
        if result<=32:raise RuntimeError('송출 도우미의 관리자 권한 실행이 취소되거나 실패했습니다.')
    def request(self,role,device,frame,running=True):
        if running:
            raw=self.session/(role+'.rgb');atomic_bytes(raw,frame.tobytes())
            data={'running':True,'device':device,'width':frame.shape[1],'height':frame.shape[0],'revision':time.time_ns()}
        else:data={'running':False}
        atomic(self.session/(role+'.json'),data)
        return data.get('revision')
    def status(self):
        try:return read_json(self.session/'status.json')
        except (OSError,ValueError):return {}
    def close(self):
        try:atomic(self.session/'stop.json',{'stop':True})
        except OSError:pass  # Producer also observes the UI process lifetime.

def run_helper(session,root):
    session=Path(session).resolve();root=Path(root).resolve()
    if not session.is_relative_to(root/'ipc'):raise ValueError('Invalid session directory')
    if not ctypes.windll.shell32.IsUserAnAdmin():raise RuntimeError('Producer must run elevated')
    instance=InstanceLock('Producer')
    if not instance.primary:
        publish_status(session/'status.json',{'pid':os.getpid(),'at':time.time(),'channels':{r:{'running':False,'error':'다른 이미지 카메라 송출 도우미가 이미 실행 중입니다.'} for r in ['upper','lower']}})
        event(root,'duplicate_producer_blocked');return
    owner=read_json(session/'owner.json')['pid']
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint,ctypes.c_bool,ctypes.c_uint];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint)];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,owner)
    if not handle:raise RuntimeError('UI process is no longer available')
    cameras={};frames={};revisions={};counts={};errors={};sizes={};last_status=0;status_failures=0
    try:
        while not (session/'stop.json').exists():
            started=time.monotonic();exit_code=ctypes.c_uint()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) or exit_code.value!=259:break
            for role in ['upper','lower']:
                try:
                    request=read_json(session/(role+'.json'))
                    if not request.get('running'):
                        if role in cameras:cameras.pop(role).close()
                        frames.pop(role,None);continue
                    size=(request['width'],request['height'])
                    if role in cameras and sizes.get(role)!=size:
                        cameras.pop(role).close();revisions.pop(role,None)
                    if role not in cameras:
                        cameras[role]=pyvirtualcam.Camera(width=request['width'],height=request['height'],fps=30,backend='unitycapture',device=request['device'])
                        counts[role]=0;sizes[role]=size
                    if revisions.get(role)!=request['revision']:
                        raw=read_bytes(session/(role+'.rgb'))
                        if len(raw)!=request['width']*request['height']*3:continue
                        frames[role]=np.frombuffer(raw,np.uint8).reshape(request['height'],request['width'],3)
                        revisions[role]=request['revision']
                    if role in frames:
                        cameras[role].send(frames[role]);counts[role]=counts.get(role,0)+1;errors.pop(role,None)
                except FileNotFoundError:pass
                except Exception as e:errors[role]=str(e)
            if started-last_status>0.2:
                if not publish_status(session/'status.json',{'pid':os.getpid(),'elevated':True,'at':time.time(),'status_publish_failures':status_failures,'channels':{r:{'running':r in cameras,'frames':counts.get(r,0),'revision':revisions.get(r),'error':errors.get(r)} for r in ['upper','lower']}}):status_failures+=1
                last_status=started
            time.sleep(max(0,1/30-(time.monotonic()-started)))
    finally:
        for cam in cameras.values():
            try:cam.close()
            except Exception:pass
        kernel.CloseHandle(handle)
        publish_status(session/'status.json',{'stopped':True,'at':time.time(),'channels':{}})
        instance.close()
