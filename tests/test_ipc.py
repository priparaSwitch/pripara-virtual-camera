"""Real Windows sharing/replacement on newly-created test files only."""
from pathlib import Path
import ctypes,json,os,sys,tempfile,threading,time,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from ipc_files import atomic_bytes,atomic_json,read_bytes,read_json
class IPC(unittest.TestCase):
 def test_concurrent_atomic_documents(self):
  parent=ROOT/'build/offline-tests';parent.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=parent)as folder:
   assert Path(folder).resolve().is_relative_to(parent.resolve())
   path=Path(folder)/'private-test.json';atomic_json(path,{'i':0,'data':'x'*5000});errors=[]
   def writer():
    try:
     for i in range(80):atomic_json(path,{'i':i,'data':'x'*5000})
    except Exception as error:errors.append(error)
   thread=threading.Thread(target=writer);thread.start()
   while thread.is_alive():
    d=read_json(path);self.assertEqual(d['data'],'x'*5000)
   thread.join();self.assertFalse(errors);self.assertEqual(read_json(path)['i'],79)
 @unittest.skipUnless(os.name=='nt','Windows sharing semantics')
 def test_real_non_delete_shared_handle_retries_then_succeeds(self):
  parent=ROOT/'build/offline-tests';parent.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=parent)as folder:
   assert Path(folder).resolve().is_relative_to(parent.resolve())
   path=Path(folder)/'private-test.bin';path.write_bytes(b'old')
   k=ctypes.WinDLL('kernel32',use_last_error=True)
   k.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p];k.CreateFileW.restype=ctypes.c_void_p
   k.CloseHandle.argtypes=[ctypes.c_void_p]
   handle=k.CreateFileW(str(path),0x80000000,3,None,3,0x80,None);self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
   thread=threading.Thread(target=lambda:(time.sleep(.12),k.CloseHandle(handle)));thread.start()
   started=time.monotonic();atomic_bytes(path,b'new',timeout=1.0);thread.join()
   self.assertGreaterEqual(time.monotonic()-started,.10);self.assertEqual(read_bytes(path),b'new')
if __name__=='__main__':unittest.main()
