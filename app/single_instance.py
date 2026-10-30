"""Keep one editor and one elevated producer per Windows logon session."""
import ctypes
import json
import os
import time

class InstanceLock:
    def __init__(self, role):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\PriParaImageCamera.' + role + '.v1')
        error = ctypes.get_last_error()
        if not self.handle:
            raise ctypes.WinError(error)
        self.primary = error != 183  # ERROR_ALREADY_EXISTS
        if not self.primary:
            self.close()

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

def event(root, action, **details):
    try:
        with (root / 'instance_events.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(dict(at=time.time(), pid=os.getpid(), action=action, **details))+'\n')
    except OSError:
        pass

SERVER_NAME = 'PriParaImageCamera.Editor.v1'

def notify_primary():
    from PySide6.QtNetwork import QLocalSocket
    socket = QLocalSocket()
    for _ in range(15):
        socket.abort()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(200):
            socket.write(b'activate\n')
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return True
        time.sleep(0.1)
    return False

def listen_for_activation(window, root):
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    QLocalServer.removeServer(SERVER_NAME)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(SERVER_NAME):
        raise RuntimeError('이미지 카메라 창 연결을 만들지 못했습니다: '+server.errorString())
    def connected():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            window.showNormal()
            window.raise_()
            window.activateWindow()
            event(root, 'primary_activated')
            socket.disconnectFromServer()
            socket.deleteLater()
    server.newConnection.connect(connected)
    return server
