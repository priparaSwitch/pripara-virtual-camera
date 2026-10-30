"""Local RGB sender using our C ABI and the published UnityCapture protocol.

This module does not import pyvirtualcam or use its native backends. Importing
this module does not load a DLL, touch a device, or request administrator rights.
"""
import ctypes
import math
from pathlib import Path
import sys
import threading
import time
from enum import Enum

import numpy as np


class PixelFormat(Enum):
    RGB = "RGB"


_DEVICES = {"PriPara Upper Camera": 0, "PriPara QR Camera": 1}
_ERRORS = {
    -1: "송출 영상의 형식이나 크기가 올바르지 않습니다.",
    -2: "이 프로세스에서 해당 카메라를 이미 사용 중입니다.",
    -3: "송출 영상의 메모리를 준비하지 못했습니다.",
    -4: "가상카메라의 공유 영상 형식이 맞지 않습니다.",
    -5: "가상카메라 영상 잠금 시간이 초과되었습니다.",
    -6: "가상카메라의 로컬 영상 연결에 실패했습니다.",
}


def _dll_path():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "native" / "PriParaFrameSender64.dll"


class _Native:
    def __init__(self, path=None):
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("가상카메라 송출은 64비트 Windows용입니다.")
        path = Path(path) if path is not None else _dll_path()
        if not path.is_file():
            raise RuntimeError("카메라 송출 파일이 없습니다: " + str(path))
        self.dll = ctypes.CDLL(str(path), winmode=0x100 | 0x800)
        self.dll.PPF_Version.argtypes = []
        self.dll.PPF_Version.restype = ctypes.c_uint32
        self.dll.PPF_Create.argtypes = [ctypes.c_int32, ctypes.c_int32,
            ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint64)]
        self.dll.PPF_Create.restype = ctypes.c_int32
        self.dll.PPF_SendRgb.argtypes = [ctypes.c_uint64, ctypes.c_void_p,
                                        ctypes.c_uint64, ctypes.c_int32]
        self.dll.PPF_SendRgb.restype = ctypes.c_int32
        self.dll.PPF_Close.argtypes = [ctypes.c_uint64]
        self.dll.PPF_Close.restype = ctypes.c_int32
        if self.dll.PPF_Version() != 0x00010000:
            raise RuntimeError("카메라 송출 파일의 버전이 맞지 않습니다.")

    def create(self, channel, width, height):
        handle = ctypes.c_uint64()
        code = self.dll.PPF_Create(channel, width, height, 1000, ctypes.byref(handle))
        if code < 0:
            raise RuntimeError(_ERRORS.get(code, "가상카메라를 준비하지 못했습니다."))
        return handle.value

    def send(self, handle, frame):
        return self.dll.PPF_SendRgb(handle, frame.ctypes.data, frame.nbytes,
                                    frame.strides[0])

    def close(self, handle):
        self.dll.PPF_Close(handle)


class Camera:
    """The RGB-only API used by this application's image producer.

    send() accepts uint8 C-contiguous arrays shaped (height, width, 3).
    No active receiver is a normal state; the latest image can be sent again.
    """
    def __init__(self, *, width, height, fps, backend="unitycapture",
                 device=None, fmt=PixelFormat.RGB):
        if (isinstance(width, bool) or not isinstance(width, int) or
                not 1 <= width <= 3840 or isinstance(height, bool) or
                not isinstance(height, int) or not 1 <= height <= 2160):
            raise ValueError("width/height must be positive supported integers")
        if (isinstance(fps, bool) or not isinstance(fps, (float, int)) or
                not math.isfinite(fps) or not 0 < fps <= 240):
            raise ValueError("fps must be finite and between 0 and 240")
        if backend != "unitycapture":
            raise ValueError("Only the PriPara unitycapture backend is supported")
        if fmt != PixelFormat.RGB:
            raise ValueError("Only RGB uint8 frames are supported")
        device = "PriPara QR Camera" if device is None else device
        if device not in _DEVICES:
            raise ValueError("Unknown PriPara camera device")
        self.width, self.height, self.fps = width, height, float(fps)
        self.device = device
        self.frames_sent = 0
        self.last_send_status = None
        self._next_frame = time.monotonic()
        self._lock = threading.Lock()
        self._handle = 0
        self._native = _Native()
        self._handle = self._native.create(_DEVICES[device], width, height)

    def send(self, frame):
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or
                frame.shape != (self.height, self.width, 3) or
                not frame.flags.c_contiguous):
            raise ValueError("Expected a C-contiguous RGB uint8 frame of the configured size")
        with self._lock:
            if not self._handle:
                raise RuntimeError("카메라 송출이 이미 종료되었습니다.")
            code = self._native.send(self._handle, frame)
            if code < 0:
                raise RuntimeError(_ERRORS.get(code, "가상카메라 영상 송출에 실패했습니다."))
            self.last_send_status = code
            self.frames_sent += 1

    def sleep_until_next_frame(self):
        now = time.monotonic()
        self._next_frame = max(self._next_frame + 1.0 / self.fps, now)
        delay = self._next_frame - now
        if delay > 0:
            time.sleep(delay)

    def close(self):
        with self._lock:
            if self._handle:
                self._native.close(self._handle)
                self._handle = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
