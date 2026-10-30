# pripara-virtual-camera

프리파라에서 사용할 이미지를 상부 촬영용·하부 QR 스캔용 가상카메라로 보내는 Windows x64 프로그램입니다. 현재 버전은 **1.1.2**입니다. 이미지 열기·붙여넣기, 최근 이미지·슬롯, 마이티켓·우정티켓 보관과 송출 기능을 제공합니다.

## 설치와 사용

1. Releases에서 **`PriParaImageCamera_Setup_1.1.2.exe`**를 받아 실행합니다. 드라이버 등록 시 관리자 권한을 요청합니다.
2. 설치 후 ‘프리파라 이미지 카메라’를 엽니다. **사용자 PC에 Python을 설치할 필요는 없습니다.**
3. 상부·하부 탭에서 이미지를 열거나 `Ctrl+V`로 붙여넣습니다. 필요한 카메라를 시작합니다.
4. 게임에 연결하려면 별도의 **‘게임 연결 설정’** 버튼에서 게임 폴더를 지정합니다. 이 설정은 게임과 QRReader가 하부 QR 카메라를 사용하도록 맞추며, 게임 EXE 패치를 대신하지 않습니다.

| 용도 | 장치명 | ID |
| --- | --- | --- |
| 상부 촬영 | PriPara Upper Camera | `CAFE:0001` |
| 하부 QR 스캔 | PriPara QR Camera | `CAFE:0002` |

앱은 `%LOCALAPPDATA%\PriParaImageCamera`, 드라이버는 `%ProgramFiles%\PriParaImageCameraDriver`에 설치합니다. 앱 UI와 관리자 권한이 필요한 송출 도우미를 분리한 기존 동작을 유지합니다.

**EXE 하나만 따로 복사하지 마세요.** PyInstaller의 폴더형 배포이며 `App/PriParaImageCamera.exe`와 `App/_internal/`이 함께 있어야 합니다. Complete ZIP을 사용할 때도 App 폴더 전체를 유지하고, 드라이버는 설치 프로그램으로 등록해야 합니다. 일반 사용자에게는 Setup EXE를 권장합니다.

마이티켓·우정티켓 탭은 게임이 저장한 BMP를 읽어 보관합니다. 기본 게임 폴더는 `C:\prineohk\game`, 티켓 저장 폴더는 `C:\prineohk\TicketData\MyTicket`입니다. 보관한 티켓을 선택해 하부 QR 카메라에 표시할 수 있습니다. 게임·QRReader 자체는 포함하지 않습니다.

## 릴리즈 파일

- **Setup EXE:** 일반 설치용입니다.
- **Complete ZIP:** App·`_internal`·32/64비트 드라이버4개·설치 도구·앱/드라이버 소스를 담은 전체 구성입니다.
- **Source ZIP:** 개발·재빌드용 소스입니다. 설치 파일과 다릅니다.
- **QtSources ZIP:** 사용한 Qt/PySide 버전의 원소스5개 아카이브입니다. 배포자는 같은 Release에 반드시 함께 첨부합니다.

파일 확인에는 `SHA256SUMS.txt`와 `release-manifest.json`을 사용합니다. GitHub Desktop에서 소스를 올리고 Releases에 파일을 첨부하는 방법은 [릴리즈 안내](docs/RELEASING.md)에 있습니다.

## 개발과 검증 범위

드라이버 소스는 `native/upper`, `native/qr`, 송출 모듈은 독립 WinAPI 구현인 `native/sender`와 `app/camera_output.py`에 있습니다. 현재 출력 경로는 `pyvirtualcam`을 사용하지 않으며, 기존 UI·IPC·티켓 처리 기능을 유지합니다.

앱3종 오프라인 테스트와 분리된 테스트 채널의 네이티브8개 검사를 통과했습니다. **현재 패키지의 실제 PC 설치·가상카메라 등록·게임 연결 성공을 검증한 결과는 아닙니다.**

[빌드 안내](docs/BUILD.md) · [Qt/PySide 원소스와 라이브러리 교체 안내](docs/DEPENDENCY_SOURCES.md) · [구성요소 라이선스 안내](THIRD_PARTY_NOTICES.md)

프로젝트 전체 라이선스는 아직 지정하지 않았습니다. 포함된 구성요소의 기존 라이선스·저작권 안내를 유지하며, 전체 소스에 임의의 새 라이선스를 부여하지 않습니다. 이 준비 작업에서 실제 GitHub 업로드·Releases 게시·사용자 설치를 수행하지 않았습니다.

## 1.1.2 배포 구성

이 버전은 배포 검사에서 특정 PC 정보를 제거한 패키지 수정입니다. 설치기·배포 버전은 1.1.2이며, 카메라 앱 런타임 1.1.1과 네이티브 드라이버·송출 DLL은 기존 검증본을 바이트 단위로 그대로 사용합니다. 앱의 화면·카메라 송출 동작은 변경하지 않았습니다. `release-manifest.json`의 `application_runtime_version`과 `reused_binary_components`에 이 구성을 기록합니다.
