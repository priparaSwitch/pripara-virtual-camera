# 소스에서 빌드

빌드용 Windows x64, 고정 requirements를 지원하는64비트 Python과 C++ compiler가 필요합니다. 예를 들어 Python3.12 x64의 가상환경을 사용할 수 있습니다. **이는 개발 환경이며, 완성된 Setup EXE를 사용하는 사람에게 Python 설치를 요구하지 않습니다.**

프로젝트 루트에서 다음 순서로 실행합니다. 다운로드 도구는 고정 크기·SHA를 확인하며 compiler와 원소스를 저장소의 무시된 작업 폴더에 준비합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/fetch_toolchain.py
.\.venv\Scripts\python.exe scripts/fetch_third_party_sources.py
.\.venv\Scripts\python.exe scripts/build_native.py
.\.venv\Scripts\python.exe scripts/run_offline_tests.py
.\.venv\Scripts\python.exe scripts/build_app.py
.\.venv\Scripts\python.exe scripts/assemble_release.py --version 1.1.2
.\.venv\Scripts\python.exe scripts/verify_release.py
```

`requirements-build.txt`는 실행 의존성인 `requirements.txt`도 포함합니다. 전체 Visual Studio나 Windows SDK 대신 `fetch_toolchain.py`가 준비한 llvm-mingw compiler를 사용할 수 있습니다. 별도로 준비한 compiler는 다음처럼 지정합니다.

```powershell
.\.venv\Scripts\python.exe scripts/build_native.py --toolchain "D:\tools\llvm-mingw-20261020-ucrt-x86_64"
.\.venv\Scripts\python.exe scripts/run_offline_tests.py --toolchain "D:\tools\llvm-mingw-20261020-ucrt-x86_64"
```

## 출력 구성

- `build/native/`: 상부·하부32/64비트 필터와 독립 송출 DLL
- `build/app-dist/PriParaImageCamera/`: 폴더형 앱 EXE와 필수 `_internal/`
- `build/third_party_sources/`: 해당 Qt/PySide 원소스 아카이브5개와 확인값
- `dist/release/v1.1.2/`: Setup EXE, Complete·Source·QtSources ZIP, 확인표

PyInstaller는 **onedir**로 패키징합니다. EXE만 꺼내 쓰거나 `_internal`을 제거하면 실행할 수 없습니다. `build_app.py`는 소스를 묶을 뿐 카메라 UI·송출을 시작하지 않습니다.

## 오프라인 검사 범위

`run_offline_tests.py`는 앱·티켓·IPC 테스트와 네이티브 송출/수신 fixture8개를 실행합니다. 테스트 채널50/51을 사용하며 설치된 카메라 채널0/1, 실제 카메라, 게임, 실제 드라이버 등록을 사용하지 않습니다. 설치기·릴리즈 구조 검사는 실제 사용자 설치 시험과 별개입니다.

소스3종·네이티브8개 검사의 성공을 실제 게임의 QR 인식 성공으로 표시하지 마세요. 현재 패키지는 실제 PC 설치·게임 시험 전입니다.

## 라이브러리와 소스

Qt/PySide 원소스5개는 약75.4MB이며, 빌드한 바이너리와 같은 버전의 파일을 사용합니다. `fetch_third_party_sources.py`가 정확한 원소스와 SHA를 준비하며, `assemble_release.py`가 별도 QtSources ZIP을 만듭니다. 이 ZIP은 Release에서 생략하지 않습니다.

라이선스 원문, 대응 소스와 재빌드·동적 DLL 교체 방법은 [DEPENDENCY_SOURCES.md](DEPENDENCY_SOURCES.md)와 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)를 따릅니다. 프로젝트 전체의 라이선스는 아직 지정되지 않았습니다.

`build/`, `dist/`, `.tools/`, 가상환경, 테스트 결과·개인 이미지·티켓·로그는 개발용이며 소스 커밋 대상으로 넣지 않습니다.
