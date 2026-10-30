# Third-party notices

이 저장소와 릴리즈에는 아래 구성요소가 포함됩니다. 프로젝트 전체에 임의의 MIT/GPL 라이선스를 부여하는 문서가 아니며, 각 구성요소의 원래 저작권·라이선스가 유지됩니다. 원문은 `licenses/` 및 각 소스 헤더에 있습니다.

## UnityCapture / DirectShow 필터

- 원본: [schellingb/UnityCapture](https://github.com/schellingb/UnityCapture), commit `3ed54c325e0ad71afcf4f246c07e5e17b3d7f2d2`.
- 필터는 Bernhard Schelling의 MIT 소스이며 MHD Yamen Saraiji의 UnityCam에 기반합니다. `licenses/UnityCapture-Filter-MIT.txt`와 원본 헤더를 보존합니다.
- 함께 보존한 `UnityCapturePlugin.cpp`는 별도의 zlib 형식 허가문을 사용합니다. `licenses/UnityCapture-Plugin-zlib.txt`를 보존하며 이 플러그인 파일을 필터의 MIT 허가문으로 바꾸지 않습니다.
- `native/upper/`는 상부 필터의 원본 소스입니다. `native/qr/`는 기존 하부 QR 호환 수정본으로, 640×480 YUY2와 카메라 제어 인터페이스를 포함합니다. 빌드 도구는 MinGW용 호환 수정을 기록하고 네 필터 DLL을 소스에서 만듭니다.
- DirectShow base class 파일의 Microsoft 저작권 표시와 Unity 인터페이스 파일의 원래 표시도 제거하지 않습니다.

## 독립 CPU 프레임 송출 모듈

`native/sender/PriParaFrameSender.cpp`와 `app/camera_output.py`는 공개된 UnityCapture 통신 형식을 바탕으로 독립 작성한 모듈입니다. `pyvirtualcam`, 해당 GPL 백엔드, libyuv 코드를 복사하거나 번들하지 않습니다. 기존 개발 환경에 있던 `pyvirtualcam`의 라이선스를 MIT로 표시하지 않으며, 이 릴리즈의 의존성에서도 제외했습니다.

## Qt / Qt for Python 6.12.0

- [Qt for Python](https://doc.qt.io/qtforpython-6/)의 PySide6-Essentials와 Shiboken6를 사용합니다. 이 배포는 관련 라이브러리의 LGPLv3 조건을 따릅니다. 상용 Qt 라이선스를 취득했다고 표시하지 않습니다.
- 실제 허용 DLL은 Qt6Core, Qt6Gui, Qt6Network, Qt6OpenGL, Qt6Svg, Qt6Widgets입니다. PDF/QML/Quick/VirtualKeyboard 등 사용하지 않는 구성요소는 번들에서 제외합니다.
- LGPLv3, GPLv3 및 관련 예외·제3자 허가문은 `licenses/Qt/`에 보존합니다. 배포 파일에도 해당 원문과 이 안내를 포함합니다.
- 대응하는 Qt/PySide 원소스 다섯 개는 `PriParaImageCamera_QtSources_6.12.0.zip`으로 함께 제공합니다. 공식 SHA-256과 URL, 빌드·교체 방법은 [DEPENDENCY_SOURCES.md](docs/DEPENDENCY_SOURCES.md)를 참고하세요.
- Qt 라이브러리는 설치된 앱의 `_internal/`에 교체 가능한 별도 파일로 남습니다. LGPL 라이브러리를 수정·교체하고 그 조합을 디버깅하기 위한 리버스 엔지니어링을 제한하지 않습니다.

## Python / Pillow / NumPy / 빌드 도구

| 구성요소 | 버전 | 원문 위치 |
| --- | --- | --- |
| Python | CPython 3.10 계열 | `licenses/Python-LICENSE.txt` |
| Pillow | 12.3.0 | `licenses/pillow-12.3.0.dist-info/` |
| NumPy | 2.2.6 | `licenses/numpy-2.2.6.dist-info/` |
| PyInstaller | 6.22.3 | `licenses/pyinstaller-6.22.3.dist-info/` — 원문의 배포 예외 포함 |
| LLVM-MinGW 및 런타임 | 20261020 UCRT | `licenses/llvm-mingw-LICENSE.txt` |

이 밖에 실제 수집되는 Python 구성요소의 허가문도 `licenses/`에 보존합니다. NumPy·Pillow 등의 파일에는 함께 제공되는 하위 구성요소의 허가문이 포함되어 있습니다. PyInstaller의 예외를 프로젝트 전체에 GPL을 부여하는 것으로 해석하지 않습니다.

## 배포 범위

사용자가 등록한 이미지·최근 목록·티켓·IPC 프레임·로그, 원본 게임·QRReader EXE·세이브는 이 릴리즈에 포함하지 않습니다. 앱과 필터·설치 소스, 필요한 라이선스, 별도 구성요소 원소스만 배포용으로 준비합니다.
