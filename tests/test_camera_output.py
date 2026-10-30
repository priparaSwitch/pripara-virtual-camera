"""No installed camera, game, driver registration or existing IPC is accessed.

Set PPF_TEST_DLL/PPF_FIXTURE_DLL to test builds. The sender test build accepts
only capture 50/51; the fixture rejects installed camera channels 0/1.
"""
import ctypes
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import camera_output as output


class FakeNative:
    def __init__(self):
        self.closed = []
    def create(self, channel, width, height):
        self.created = (channel, width, height)
        return 7
    def send(self, handle, frame):
        self.sent = (handle, frame.copy())
        return 2
    def close(self, handle):
        self.closed.append(handle)


class PythonApiTests(unittest.TestCase):
    def test_valid_rgb_context_and_inactive_receiver(self):
        native = FakeNative()
        with patch.object(output, "_Native", return_value=native):
            with output.Camera(width=4, height=2, fps=30) as cam:
                frame = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
                cam.send(frame)
                self.assertEqual(native.created, (1, 4, 2))
                self.assertEqual(cam.device, "PriPara QR Camera")
                self.assertEqual(cam.last_send_status, 2)
                self.assertEqual(cam.frames_sent, 1)
                np.testing.assert_array_equal(native.sent[1], frame)
            cam.close()
            self.assertEqual(native.closed, [7])
            with self.assertRaises(RuntimeError): cam.send(frame)

    def test_invalid_options_rejected_before_loading_any_native_file(self):
        invalid = [dict(width=0), dict(width=True), dict(height=2161),
                   dict(fps=0), dict(fps=float("inf")), dict(backend="obs"),
                   dict(device="Other camera"), dict(fmt="BGR")]
        for override in invalid:
            with self.subTest(override=override), patch.object(output, "_Native") as load:
                options = dict(width=4, height=2, fps=30)
                options.update(override)
                with self.assertRaises(ValueError): output.Camera(**options)
                load.assert_not_called()

    def test_frame_validation_and_closed_idempotence(self):
        with patch.object(output, "_Native", return_value=FakeNative()):
            cam = output.Camera(width=4, height=2, fps=30,
                                device="PriPara Upper Camera")
            for frame in [np.zeros((2, 4, 3), np.float32),
                          np.zeros((4, 2, 3), np.uint8),
                          np.zeros((2, 8, 3), np.uint8)[:, ::2], b"bad"]:
                with self.subTest(shape=getattr(frame, "shape", None)):
                    with self.assertRaises(ValueError): cam.send(frame)
            cam.close()
            cam.close()

    def test_native_error_and_frame_clock(self):
        native = FakeNative()
        native.send = lambda *_: -4
        with patch.object(output, "_Native", return_value=native):
            with output.Camera(width=4, height=2, fps=30) as cam:
                with self.assertRaises(RuntimeError): cam.send(np.zeros((2,4,3),np.uint8))
                with patch.object(output.time, "sleep") as sleep:
                    cam.sleep_until_next_frame()
                    self.assertTrue(sleep.called)


@unittest.skipUnless(os.environ.get("PPF_TEST_DLL") and os.environ.get("PPF_FIXTURE_DLL"),
                     "native fixtures were not configured")
class NativeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sender = output._Native(os.environ["PPF_TEST_DLL"])
        cls.fixture = ctypes.CDLL(os.environ["PPF_FIXTURE_DLL"], winmode=0x100|0x800)
        cls.fixture.PPFT_Start.argtypes = [ctypes.c_int]
        cls.fixture.PPFT_Start.restype = ctypes.c_void_p
        cls.fixture.PPFT_Frame.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_uint64, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint64)]
        cls.fixture.PPFT_Frame.restype = ctypes.c_int
        cls.fixture.PPFT_Stop.argtypes = [ctypes.c_void_p]
        cls.fixture.PPFT_Stop.restype = None
        for name in ("PPFT_Pause", "PPFT_Resume"):
            getattr(cls.fixture, name).argtypes = [ctypes.c_void_p]
            getattr(cls.fixture, name).restype = None

    def read_until(self, receiver, rgb, sender, expected=None):
        expected = rgb if expected is None else expected
        deadline = time.monotonic()+4
        header = (ctypes.c_int32*8)()
        sequence = ctypes.c_uint64()
        pixels = np.zeros((rgb.shape[0], rgb.shape[1], 4), np.uint8)
        while time.monotonic()<deadline:
            code = self.sender.send(sender, rgb)
            self.assertIn(code, (0,1,2))
            count = self.fixture.PPFT_Frame(receiver, pixels.ctypes.data,
                pixels.nbytes, header, ctypes.byref(sequence))
            if count == pixels.nbytes and np.array_equal(pixels[::-1,:,:3], expected):
                self.assertEqual(list(header)[1:], [rgb.shape[1],rgb.shape[0],rgb.shape[1],0,0,0,1000])
                self.assertTrue(np.all(pixels[:,:,3] == 255))
                return
            time.sleep(.015)
        self.fail("Original UnityCapture receiver did not receive the expected frame")

    def test_production_channels_are_blocked_in_isolated_test_binary(self):
        for channel in (0,1,2,49,52,-1):
            handle = ctypes.c_uint64(999)
            self.assertEqual(self.sender.dll.PPF_Create(channel,4,2,1000,ctypes.byref(handle)), -1)
            self.assertEqual(handle.value, 0)
            self.assertFalse(self.fixture.PPFT_Start(channel))

    def test_original_receive_two_independent_channels_orientation_reopen(self):
        frames = [np.array([[[255,0,0],[0,255,0],[0,0,255],[1,2,3]],
                            [[0,255,255],[255,0,255],[255,255,0],[250,128,7]]], np.uint8),
                  np.arange(24, dtype=np.uint8).reshape(2,4,3)]
        receivers=[]; senders=[]
        try:
            for channel in (50,51):
                senders.append(self.sender.create(channel,4,2))
            # No original receiver exists yet; this must be a normal skip.
            for handle,frame in zip(senders,frames):
                self.assertEqual(self.sender.send(handle,frame), 2)
            for channel in (50,51):
                receiver=self.fixture.PPFT_Start(channel)
                self.assertTrue(receiver,"Test channel was already in use; refusing to reuse it")
                receivers.append(receiver)
            for receiver,handle,frame in zip(receivers,senders,frames):
                self.read_until(receiver,frame,handle)
            # The original receiver closes/reopens its mapping while senders
            # stay alive. A stopped receiver is a frame skip, never a fatal UI
            # error. No installed filter or registered camera is involved.
            for receiver in receivers:self.fixture.PPFT_Pause(receiver)
            for handle,frame in zip(senders,frames):
                for _ in range(3):self.assertIn(self.sender.send(handle,frame),(0,1,2))
            for receiver in receivers:self.fixture.PPFT_Resume(receiver)
            for receiver,handle,frame in zip(receivers,senders,frames):
                self.read_until(receiver,frame,handle)
            for i in range(2):
                self.sender.close(senders[i]); senders[i]=self.sender.create(50+i,4,2)
                self.read_until(receivers[i],frames[i],senders[i])
            # Close both ends, remove all named objects, and recreate receivers.
            for handle in senders:self.sender.close(handle)
            senders=[]
            for receiver in receivers:self.fixture.PPFT_Stop(receiver)
            receivers=[]
            for channel in (50,51):
                receiver=self.fixture.PPFT_Start(channel);self.assertTrue(receiver)
                receivers.append(receiver);senders.append(self.sender.create(channel,4,2))
            for receiver,handle,frame in zip(receivers,senders,frames):
                self.read_until(receiver,frame,handle)
        finally:
            for handle in senders:self.sender.close(handle)
            for receiver in receivers:self.fixture.PPFT_Stop(receiver)

    def test_native_boundary_and_duplicate_handles(self):
        dll=self.sender.dll
        for width,height,timeout in [(0,2,1000),(3841,2,1000),(4,2161,1000),(4,2,-1),(4,2,60001)]:
            h=ctypes.c_uint64()
            self.assertEqual(dll.PPF_Create(50,width,height,timeout,ctypes.byref(h)),-1)
        handle=self.sender.create(50,4,2)
        try:
            h=ctypes.c_uint64()
            self.assertEqual(dll.PPF_Create(50,4,2,1000,ctypes.byref(h)),-2)
            frame=np.zeros((2,4,3),np.uint8)
            self.assertEqual(dll.PPF_SendRgb(handle,frame.ctypes.data,frame.nbytes-1,12),-1)
            self.assertEqual(dll.PPF_SendRgb(handle,None,frame.nbytes,12),-1)
            self.assertEqual(dll.PPF_SendRgb(handle,frame.ctypes.data,frame.nbytes,11),-1)
        finally:self.sender.close(handle)
        self.assertEqual(dll.PPF_SendRgb(handle,None,0,0),-1)
        self.assertEqual(dll.PPF_Close(handle),-1)

    def test_full_size_python_api_to_original_receiver(self):
        native = self.sender
        class IsolatedTransport:
            # Python's production device names are mapped to test channels
            # before calling the test-only DLL. No native 0/1 call is made.
            def create(self, channel, width, height):
                return native.create(50+channel, width, height)
            def send(self, handle, frame):
                return native.send(handle, frame)
            def close(self, handle):
                native.close(handle)
        receiver = self.fixture.PPFT_Start(50)
        self.assertTrue(receiver)
        try:
            with patch.object(output, "_Native", return_value=IsolatedTransport()):
                with output.Camera(width=640,height=480,fps=30,
                                   device="PriPara Upper Camera") as cam:
                    yy,xx=np.indices((480,640))
                    frame=np.stack((xx%256,yy%256,(xx+yy)%256),axis=2).astype(np.uint8)
                    cam.send(frame)
                    self.read_until(receiver,frame,cam._handle)
                    self.assertEqual(cam.frames_sent,1)
        finally:
            self.fixture.PPFT_Stop(receiver)


if __name__ == "__main__":
    unittest.main(verbosity=2)
