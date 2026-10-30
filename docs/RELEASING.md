# GitHub Desktop와 Releases

프로젝트 이름은 **`pripara-virtual-camera`**, 현재 버전·태그는 **`1.1.2` / `v1.1.2`**입니다. 이 문서는 로컬 준비 절차이며 실제 원격 저장소 생성·업로드·게시가 완료되었다는 의미는 아닙니다.

## 소스 올리기

1. GitHub Desktop의 **File → Add local repository**에서 준비한 소스 폴더를 선택합니다. Git 저장소가 아니라면 Desktop에서 저장소를 만듭니다.
2. 변경 목록을 검토하고 소스·설치기·빌드 도구·문서·라이선스만 커밋합니다. `build/dist/.tools/.venv/.local-tests`와 개인 이미지·티켓·설정·로그·게임 파일은 넣지 않습니다.
3. **Publish repository**로 본인의 `pripara-virtual-camera` 저장소를 만듭니다. 실제 공개 여부는 사용자가 선택합니다.

GitHub에 소스를 올리는 것과 실행 파일을 Releases에 첨부하는 것은 별도 작업입니다. 빌드 결과는 Git에서 제외하고 아래 첨부 파일로 제공합니다.

## 가장 간단한 방법: Releases에 직접 첨부

[BUILD.md](BUILD.md)의 빌드·검사를 마친 뒤 GitHub 웹사이트의 **Releases → Draft a new release**에서 `v1.1.2` 태그를 지정합니다. `dist/release/v1.1.2/`의 다음 파일을 **모두** 첨부합니다.

| 파일 | 용도 |
| --- | --- |
| `PriParaImageCamera_Setup_1.1.2.exe` | 일반 사용자용 설치 프로그램 |
| `PriParaImageCamera_Complete_1.1.2.zip` | 앱·`_internal`·드라이버·설치기·소스 전체 구성 |
| `PriParaImageCamera_Source_1.1.2.zip` | 독립 소스/재빌드 자료 |
| `PriParaImageCamera_QtSources_6.12.0.zip` | 일치하는 Qt/PySide 원소스5개 아카이브 |
| `SHA256SUMS.txt` | 파일별 SHA-256 확인값 |
| `release-manifest.json` | 버전·구성·검증 결과 |

**QtSources ZIP과 라이선스·소스 교체 안내를 생략하지 마세요.** 앱/드라이버 소스 ZIP과 별개인 원소스 아카이브5개, 약75.4MB를 제공하는 파일입니다. 자세한 구성은 [DEPENDENCY_SOURCES.md](DEPENDENCY_SOURCES.md)에 있습니다.

파일·버전·안내와 검증 범위를 검토한 뒤 Release를 게시합니다. 사용자에게는 Setup EXE를 우선 안내합니다. Complete ZIP은 App 폴더의 `_internal`을 포함해 유지해야 하며, 드라이버 등록은 별도 설치 절차가 필요합니다. Source ZIP은 설치용 ZIP이 아닙니다.

## 태그 워크플로

새 `v1.1.2` 태그를 원격에 push하거나 Actions에서 이미 존재하는 태그를 지정하면 워크플로가 빌드·오프라인 검사 후 **draft Release**를 준비합니다. 같은 태그의 Release가 이미 있으면 임의로 덮어쓰지 않고 중단합니다. 초안을 확인한 뒤 직접 게시합니다.

워크플로의 GitHub 토큰은 Actions가 제공하는 것으로만 사용하며 소스·원격 주소에 계정 토큰이나 비밀번호를 적지 않습니다. 로컬에서 릴리즈 파일을 만드는 것은 GitHub 업로드나 사용자 PC 설치를 수행하는 작업이 아닙니다.

앱3종·네이티브 fixture8개 검사는 격리된 테스트 결과입니다. 현재 패키지의 실제 사용자 PC 설치·카메라 등록·게임 연결 성공은 아직 확인하지 않았으며, 이를 릴리즈에서 실게임 확인 완료로 표시하지 않습니다. 프로젝트 전체 라이선스도 임의로 새로 지정하지 않습니다.
