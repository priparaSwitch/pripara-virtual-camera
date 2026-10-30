# A portable onedir bundle; native and Qt libraries remain replaceable files.
from pathlib import Path
ROOT = Path(SPECPATH)
a = Analysis(
    [str(ROOT/'app/app_dual.py')],
    pathex=[str(ROOT/'app')],
    binaries=[(str(ROOT/'app/native/PriParaFrameSender64.dll'),'native')],
    datas=[], hiddenimports=['camera_output','PySide6.QtNetwork'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pyvirtualcam','cv2','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets',
              'PySide6.QtQml','PySide6.QtQuick','PySide6.QtQuickWidgets','PySide6.QtQuickControls2',
              'PySide6.QtPdf','PySide6.QtPdfWidgets','PySide6.QtCharts','PySide6.QtGraphs',
              'PySide6.QtDataVisualization','PySide6.QtVirtualKeyboard','PySide6.QtTest'],
    noarchive=False, optimize=0,
)
# Preserve the working Qt6.12 Windows-system-ICU configuration. Avoid unrelated
# copies discovered on the build machine's PATH, and unused PDF/QML plugins.
skip={'icuuc.dll','icudt78.dll','qpdf.dll','qt6pdf.dll','qt6pdfwidgets.dll'}
allowed_qt={'qt6core.dll','qt6gui.dll','qt6network.dll','qt6opengl.dll','qt6svg.dll','qt6widgets.dll'}
a.binaries=[b for b in a.binaries if Path(b[0]).name.lower() not in skip
            and 'virtualkeyboard'not in b[0].lower()
            and not (Path(b[0]).name.lower().startswith('qt6')and Path(b[0]).name.lower()not in allowed_qt)]
a.datas=[d for d in a.datas if 'virtualkeyboard'not in d[0].lower()and not d[0].lower().endswith('.qml')]
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='PriParaImageCamera',
          debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
          console=False,disable_windowed_traceback=False,
          version=str(ROOT/'scripts/app_version.txt'))
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='PriParaImageCamera')
