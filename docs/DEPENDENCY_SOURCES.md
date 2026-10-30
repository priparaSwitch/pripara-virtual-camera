# 라이브러리 소스와 교체 방법

이 문서는 `PriParaImageCamera 1.1.2`에 포함되는 라이브러리의 대응 소스와 교체 경로를 안내합니다. 실제 GitHub 공개 게시 여부와 설치·실게임 검증 여부는 별개입니다.

## 릴리즈에 함께 첨부할 파일

`dist/release/v1.1.2/`의 아래 파일을 같은 GitHub Release에 첨부합니다.

- `PriParaImageCamera_Setup_1.1.2.exe`: 설치 프로그램.
- `PriParaImageCamera_Complete_1.1.2.zip`: 앱의 `_internal/`, 필터, 설치 도구·소스가 포함된 완전한 패키지.
- `PriParaImageCamera_Source_1.1.2.zip`: 앱·필터·송출 모듈·설치·빌드·시험 소스와 라이선스.
- **`PriParaImageCamera_QtSources_6.12.0.zip`**: 아래 Qt/PySide 원소스 다섯 개와 출처·SHA 정보.
- `SHA256SUMS.txt`, `release-manifest.json`: 파일 검증 정보.

Qt 소스 묶음은 Git 소스 저장소의 대형 바이너리로 커밋하지 않고 **Releases 첨부 파일**로 제공합니다. 설치 EXE만 게시하고 대응 소스·라이선스를 누락하지 마세요. [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)는 파일당 2GiB 미만의 첨부 파일을 지원합니다.

## Qt / PySide 6.12.0 원소스

아카이브는 원래 압축 형식 그대로 제공하며 Qt 라이브러리 소스는 수정하지 않았습니다. 공식 다운로드 메타데이터의 SHA-256과 실제 파일을 대조했습니다. `scripts/fetch_third_party_sources.py`는 같은 버전·크기·SHA를 사용해 다시 준비합니다.

| 파일 | 바이트 | SHA-256 |
| --- | ---: | --- |
| qtbase-everywhere-src-6.12.0.tar.xz | 51,220,268 | `a951bd163c7b80fc6b8c88d7668fb56abf91c152373e13c10666763238131307` |
| qtimageformats-everywhere-src-6.12.0.tar.xz | 1,848,620 | `0943132b5db8de6b6a7f1d162682173e8763c7ed94e80fd39113292845f67762` |
| qtsvg-everywhere-src-6.12.0.tar.xz | 2,341,876 | `e4ab39534ec97987b1b9b60ef7f4d3253d5912a69f8c713a01753174a4029331` |
| qttranslations-everywhere-src-6.12.0.tar.xz | 1,745,884 | `85929c0c30d6f273f23bd879bb69803ea17b010ab73cab2f8abf95357f6f6bbb` |
| pyside-setup-everywhere-src-6.12.0.tar.xz | 18,211,772 | `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751` |

공식 배포 위치:

- [Qt 6.12.0 modules](https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/)
- [PySide/Shiboken 6.12.0 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/)
- [Qt source build guide](https://doc.qt.io/qt-6/build-sources.html)
- [Qt for Python source build guide](https://doc.qt.io/qtforpython-6/building_from_source/index.html)

원본 `PySide6-Essentials==6.12.0` / `shiboken6==6.12.0` wheel을 사용합니다. Qtbase는 Core·Gui·Widgets·Network·OpenGL, QtSvg는 SVG, QtImageFormats는 해당 이미지 플러그인, QtTranslations는 번들 번역의 대응 소스입니다. Qt/PySide 소스를 직접 빌드하려면 각 아카이브의 CMake 설정·원래 빌드 문서와 동일한 Windows x64/CPython ABI에 맞추세요.

## 설치된 동적 라이브러리 교체

1. 앱과 송출 도우미를 정상 종료합니다.
2. 기본 앱 설치 폴더 `%LOCALAPPDATA%\PriParaImageCamera`를 엽니다. 실제 설치 폴더가 다르면 해당 경로를 사용합니다.
3. Qt/PySide 라이브러리는 `_internal\PySide6\`, Shiboken은 `_internal\shiboken6\`에 있습니다. 같은 구조와 호환되는 ABI로 직접 빌드한 DLL·Python 확장·필요 플러그인을 해당 위치에 배치합니다.
4. `_internal\PySide6\plugins\`의 플러그인은 교체한 Qt 버전·ABI와 맞춰 함께 교체합니다. 앱 실행 EXE를 다시 만들지 않고도 설치된 동적 라이브러리를 교체할 수 있습니다.
5. 앱을 다시 실행해 확인합니다. 호환되지 않는 아키텍처나 Python/Qt ABI는 로드되지 않을 수 있습니다.

설치 프로그램의 파일 검사는 설치 자료의 손상을 확인하는 절차입니다. 앱 실행 시 Qt DLL의 원래 해시를 강제하는 기능은 없습니다. LGPL 라이브러리 교체와 그 조합의 수정·디버깅을 제한하지 않습니다. GPL/LGPL 원문은 `licenses/Qt/`에 포함되어 있습니다.

## 앱·필터·송출 모듈 소스

원본 게임이나 설치된 드라이버 DLL을 빌드 입력으로 사용하지 않습니다. `app/`, `native/upper/`, `native/qr/`, `native/sender/`, `installer/`와 빌드 스크립트가 저장소에 포함되어 있습니다. 변경된 하부 필터와 독립 송출 모듈도 같은 소스 묶음에 포함합니다. LLVM-MinGW는 `scripts/toolchain.json`에 고정된 공식 배포본을 SHA 확인 후 사용합니다.

Pillow·NumPy·Python 및 빌드 도구의 출처·라이선스는 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)를 참고하세요. 구성요소 허가문과 이 프로젝트 자체의 라이선스를 구별합니다.
