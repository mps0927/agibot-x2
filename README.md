# AGIBOT X2 Multimodal Pipeline

브라우저에서 X2 Ultra t2d5의 카메라와 상태를 확인하고, 일어서기·앉기·손 흔들기·이동을 조작하는 프로젝트다. 사진과 글로 쓴 지시를 AI에 보내 동작을 요청할 수도 있다. [Unitree G1 파이프라인](https://github.com/8l4nnk/unitree-g1-pipeline)과 같은 실행 스크립트 구조와 조작 화면을 사용한다.

## 사용설명서

- **[대시보드로 A to Z](docs/USER_GUIDE_KO.md)** — 전원 켜기 → PC 연결 → 화면에서 착석 고정·일어서기·제어 활성화 → 프리셋·이동·VLM → 화면에서 앉기·댐핑·영토크 → 전원 끄기·충전.
- **[리모컨으로 A to Z](docs/REMOTE_CONTROL_GUIDE_KO.md)** — 전원 켜기 → 리모컨 연결 → 버튼 조합으로 착석 고정·일어서기 → 조이스틱·팔 동작 → 앉기·댐핑·영토크 → 전원 끄기·충전.

**대시보드 포트는 8766 하나다.** G1의 기본 포트 8765와 겹치지 않는다. 실물 연결과 로봇 없는 개발은 같은 대시보드의 실행 옵션이며 동시에 두 서버를 띄우지 않는다.

## 실행 구성

로봇을 사용할 PC에 프로젝트를 설치하고 X2를 LAN 케이블로 직접 연결한다. 대시보드 실행과 브라우저 조작은 모두 이 PC에서 진행한다.

Windows, Linux(DGX Spark 포함), macOS에서 **같은 스크립트 `./start_field.sh`**를 사용한다. 명령을 입력할 프로그램은 다음과 같다.

| 운영체제 | 명령을 입력할 프로그램 |
|---|---|
| Windows | Git Bash |
| Linux · DGX Spark | 터미널 |
| macOS | 터미널 |

프로젝트의 Python 실행 환경(`.venv`), 연결 설정(`.env`), 로봇 접속 정보와 기록은 실행한 PC에 저장한다. AI 요청도 이 PC에서 OpenRouter로 보낸다.

## 빠른 시작

처음 사용하는 경우 [대시보드 사용설명서](docs/USER_GUIDE_KO.md)의 전원 켜기와 LAN 연결부터 진행한다. 아래 명령은 로봇을 사용할 PC에서 실행한다.

Python 3.10 이상과 Git, Bash가 필요하다. Windows에서는 Git Bash를 연다. 기존 Python으로 프로젝트 전용 `.venv`를 만들고, 이후에는 같은 환경과 패키지를 재사용한다. 명령은 한 줄씩 복사해 붙여 넣고 Enter를 누른다.

처음 설치할 때 프로젝트를 내려받는다. 이미 `agibot-x2` 폴더가 있으면 그 폴더에서 터미널을 열어 연결 설정을 확인한다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
cp .env.example .env
./setup.sh
```

`.env`는 연결 설정 파일이다. 텍스트 편집기로 열고 아래 비밀번호와 키 안내를 실제 값으로 바꿔 저장한다. Windows에서는 Git Bash에서 `notepad .env`로 열 수 있다. 수동 조종만 사용할 때 OpenRouter 키는 비워 둔다. 항목별 설명은 [설치와 실행](docs/USER_GUIDE_KO.md#dashboard)을 참고한다.

```dotenv
X2_SSH_HOST=10.0.1.41
X2_SSH_USER=agi
X2_SSH_PASSWORD=로봇의_SSH_비밀번호
X2_SSH_KNOWN_HOSTS=~/.ssh/known_hosts
OPENROUTER_API_KEY=발급받은_키
```

개발 PC와 X2 개발 보드가 같은 LAN에 있어야 한다. 기본 X2 주소는 `10.0.1.41/24`이며 PC에는 사용 중이지 않은 같은 대역 주소를 설정한다. 처음 연결할 PC에서는 다음 명령으로 로봇의 호스트 키를 확인하고 등록한다.

```bash
ssh agi@10.0.1.41
```

로봇에 접속되면 `exit`를 입력해 PC 터미널로 돌아온다. 이어서 PC의 `agibot-x2` 폴더에서 실행한다.

```bash
exit
./start_field.sh
./status.sh
```

대시보드를 실행한 **같은 PC의 브라우저**에서 [대시보드 열기](http://127.0.0.1:8766)를 누른다. 주소창에 `http://127.0.0.1:8766`을 입력해도 된다. `start_field.sh`로 시작하면 터미널을 닫아도 실행이 유지된다. 다음 날에도 프로젝트 폴더에서 같은 명령을 사용한다.

화면 상단의 **착석 자세 고정 → 일어서기 → 제어 활성화** 순서로 준비한다. 직접 조종 영역에서 프리셋 버튼이나 WASD·Q/E를 사용한다. 프리셋은 SDK 응답을 받으면 다음 요청을 할 수 있다. 실제 동작이 끝나는 것을 보고 다음 프리셋을 선택한다.

종료할 때는 [의자에 앉히고 전원 끄기](docs/USER_GUIDE_KO.md#power-off) 순서로 로봇을 앉히고 힘을 해제한 뒤 `./stop.sh`를 실행한다. 프로그램 오류는 [자주 발생하는 문제](docs/USER_GUIDE_KO.md#troubleshooting)를 참고한다.

## 실행 방식

| 목적 | 명령 | 하드웨어 연결 | 기본 주소 |
|---|---|---|---|
| 실물 조종 전체 | `./start_field.sh` | X2 SDK, 카메라, 수동 기립·착석, 이동·프리셋 | `http://127.0.0.1:8766` |
| 실물 상태 조회 | `./run.sh --field` | SSH·센서 조회, 제어 읽기 전용 | 동일 |
| 로봇 없이 개발 | `./run.sh --offline` | 없음, 이미지 업로드·VLM·화면 확인 | 동일 |
| 실행 전 확인 | `./preflight.sh --field` | SDK 설치 상태만 조회 | 서버 시작 없음 |
| 로봇 없이 검사 | `./preflight.sh --offline --test` | 없음 | 서버 시작 없음 |
| 상태·종료 | `./status.sh` / `./stop.sh` | 로컬 서버 관리 | 추가 포트 없음 |

최초 환경 준비는 `run.sh`에서도 자동 수행한다. 특정 Python을 사용하려면 최초 실행 전에 `PYTHON_BIN=/path/to/python3 ./setup.sh`를 사용한다. `.venv`는 실행할 PC에서 `./setup.sh`로 준비한다. 이미 환경변수로 지정한 설정값은 `.env`보다 우선하며 `.env`는 Git에서 제외된다.

다른 `.env` 경로는 `./start_field.sh --env-file /path/to/.env`로 지정한다. OpenRouter 키가 없어도 실제 영상·상태·수동 제어는 사용할 수 있다. 오프라인 모드에서는 업로드 이미지로 VLM을 확인할 수 있다. 이전 캡처 자료가 있다면 `./run.sh --offline --replay /path/to/robot_snapshot`으로 불러올 수 있다. 개인 사진·기기 로그는 저장소에 포함하지 않는다.

## 구조와 통신

```text
agibot-x2/
├── run.sh / start_field.sh / setup.sh / preflight.sh
├── status.sh / stop.sh
├── .env.example / FILE_SHA256SUMS.txt / VERIFICATION.md
├── x2_motion/
│   ├── dashboard.py / app.py / dashboard_service.py
│   ├── x2_worker.py / worker_deploy.py / preflight.py
│   ├── capabilities.py / control_policy.py / posture_actions.py
│   ├── pipeline.py / vlm_recording.py / sdk_interfaces.json
│   ├── web/ / prompts/ / test_*.py
├── sdk_reference/
└── docs/
```

대시보드가 실행되는 PC에서 AsyncSSH로 X2 개발 보드에 직접 접속한다. 로봇에 이미 설치된 ROS 2 Humble과 AIMDK를 사용해 전용 워커를 실행한다. 워커 파일은 `/home/agi/agibot_dashboard`에 동기화한다. PC에는 대시보드 패키지를 설치하고, 로봇의 SDK·ROS·펌웨어는 기존 설치본을 사용한다. 로봇 통신은 SSH 포트 22, 웹 대시보드는 8766을 사용한다.

운동 보드 `10.0.1.40`을 직접 조종하거나 MC 앱을 중지하는 실행기는 포함하지 않는다. 기본 개발 보드 `10.0.1.41`의 공식 ROS SDK 서비스를 호출한다. 설치 SDK 관측 버전은 `aimdk v1.0.0-ga424add`이며 연결 시 해당 기기의 상수·서비스 준비 상태를 다시 조회한다.

## 제어와 VLM

- 프리셋은 문서 ID·제어 영역과 설치 SDK 상수가 정확히 맞는 항목만 UI/VLM에 제공한다. 기준 설치본에서 17개가 매핑되며 재생 성공을 확인한 목록과는 구분한다.
- `↑+×`는 `SIT_JOINT_DEFAULT`, 의자 기립 `↑+□`는 `SIT_UP_DEFAULT`, 의자 착석 `L2+←`는 `SIT_DOWN_DEFAULT`로 매핑한다.
- 이동은 6방향 속도 명령이며 각 축 절댓값 0.30 이하, 기본 전후 속도는 0.20 m/s, 수동 누름 기본 1초·최대 5초다. 정확한 보 수·거리 제어는 제공하지 않는다.
- 매 VLM 요청의 입력 사진·지시·요청·응답·실행 피드백은 로컬 `x2_motion/artifacts/vlm_runs/`에 저장한다. API 키는 기록하지 않는다.
- OpenRouter에서 이미지 입력을 지원하는 실시간 채팅 모델을 불러와 검색·선택할 수 있다. 선택은 같은 브라우저에 유지되며 다음 VLM 요청에 적용된다.
- 전면 RGB 미리보기는 30fps 고정이며 실제 수신 속도는 환경에 따라 달라진다.
- 직접 관절 목표는 미리보기까지 제공한다. LiDAR 표준 점군 수신은 아직 검증하지 않았다.

상세 매핑과 조건은 [SDK_MAPPING.md](docs/SDK_MAPPING.md), 현장 실행 순서는 [OPERATIONS.md](docs/OPERATIONS.md), 검증 범위는 [VERIFICATION.md](VERIFICATION.md)를 참고한다.

## 검증과 변경

```bash
./preflight.sh --offline --test
python3 refresh_checksums.py --check
```

소스를 수정했으면 `python3 refresh_checksums.py`로 무결성 목록을 갱신한다. GitHub Actions는 Linux와 macOS의 Python 3.10/3.12에서 설치·Bash 구문·오프라인 검사를 수행한다. 실제 DGX·X2 연결과 동작 검증은 별도 현장 확인이 필요하다.
