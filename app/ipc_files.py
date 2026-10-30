"""Atomic local IPC with Windows delete-sharing and bounded sharing retries."""
import ctypes
import json
import os
import time
import uuid
from pathlib import Path

def read_bytes(path):
    path=Path(path)
    if os.name!='nt':return path.read_bytes()
    import msvcrt
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p]
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    # Reads must permit an atomic replacement while this old handle is open.
    handle=kernel.CreateFileW(str(path),0x80000000,1|2|4,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle);raise
    with os.fdopen(fd,'rb') as stream:return stream.read()

def read_json(path):return json.loads(read_bytes(path).decode('utf-8-sig'))

def atomic_bytes(path,data,timeout=1.0):
    path=Path(path)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:stream.write(data)
        deadline=time.monotonic()+timeout
        while True:
            try:
                os.replace(temporary,path);return
            except OSError as error:
                if getattr(error,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
                time.sleep(min(.02,max(0,deadline-time.monotonic())))
    finally:
        try:temporary.unlink(missing_ok=True)
        except OSError:pass

def atomic_json(path,data,timeout=1.0,**options):
    atomic_bytes(path,json.dumps(data,**options).encode('utf-8'),timeout)
