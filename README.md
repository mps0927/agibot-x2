# AGIBOT X2 Multimodal Pipeline

X2 Ultra t2d5의 실제 RGB 카메라·상태 조회, 직접 조종, SDK 프리셋, 의자 기립·착석과 VLM 명령 변환을 제공한다. [Unitree G1 파이프라인](https://github.com/8l4nnk/unitree-g1-pipeline)과 같은 루트 실행 스크립트 구조와 조작 화면을 사용한다.

**대시보드 포트는 8766 하나다.** G1의 기본 포트 8765와 겹치지 않는다. 실물 연결과 로봇 없는 개발은 같은 대시보드의 실행 옵션이며 동시에 두 서버를 띄우지 않는다.

## 빠른 시작 — DGX Spark / Linux / macOS

Python 3.10 이상과 Bash, Git이 필요하다. 기존 Python을 사용하고 프로젝트 `.venv`에만 패키지를 설치한다. Python 본체·CUDA·ROS를 개발 PC에 새로 설치하지 않는다. `.venv`는 재사용하며 의존성 목록이 바뀌거나 패키지가 빠진 경우에만 pip를 실행한다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
cp .env.example .env
./setup.sh
```

`.env`에 로봇 SSH 비밀번호 또는 키 경로와 OpenRouter 키를 입력한다. 이미 환경변수로 설정한 값이 우선한다. `.env`는 Git에서 제외된다.

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
# 연결 확인 후 exit
./start_field.sh
./status.sh
```

브라우저에서 **http://127.0.0.1:8766**을 연다. `start_field.sh`는 백그라운드로 실행되어 터미널을 닫아도 유지된다. 같은 옵션으로 재실행하면 기존 서버를 사용한다. 다른 옵션으로 바꾸려면 `./stop.sh` 후 다시 실행한다.

화면 상단의 **착석 자세 고정 → 일어서기 → 제어 활성화** 순서로 준비하고, 직접 조종 패널 상단의 프리셋 또는 WASD·Q/E를 사용한다. SDK 요청 수락과 실제 동작 종료는 구분하며 프리셋은 한 번에 한 개씩 요청한다.

## 실행 방식

| 목적 | 명령 | 하드웨어 연결 | 기본 주소 |
|---|---|---|---|
| 실물 조종 전체 | `./start_field.sh` | X2 SDK, 카메라, 수동 기립·착석, 이동·프리셋 | `http://127.0.0.1:8766` |
| 실물 상태 조회 | `./run.sh --field` | SSH·센서 조회, 제어 읽기 전용 | 동일 |
| 로봇 없이 개발 | `./run.sh --offline` | 없음, 이미지 업로드·VLM·화면 확인 | 동일 |
| 실행 전 확인 | `./preflight.sh --field` | SDK 설치 상태만 조회 | 서버 시작 없음 |
| 로봇 없이 검사 | `./preflight.sh --offline --test` | 없음 | 서버 시작 없음 |
| 상태·종료 | `./status.sh` / `./stop.sh` | 로컬 서버 관리 | 추가 포트 없음 |

최초 환경 준비는 `run.sh`에서도 자동 수행한다. 별도 Python을 선택하려면 최초 실행 전에 `PYTHON_BIN=/path/to/python3 ./setup.sh`를 사용한다. 가상환경은 각 기기에서 새로 만들며 Windows의 `.venv`를 DGX나 Mac에 복사하지 않는다.

다른 `.env` 경로는 `./start_field.sh --env-file /path/to/.env`로 지정한다. OpenRouter 키가 없어도 실제 영상·상태·수동 제어는 사용할 수 있다. 오프라인 모드에서는 업로드 이미지로 VLM을 확인할 수 있다. 이전 캡처 자료가 있다면 `./run.sh --offline --replay /path/to/robot_snapshot`으로 불러올 수 있다. 개인 사진·기기 로그는 저장소에 포함하지 않는다.

DGX에서 실행한 화면을 노트북에서 보려면 노트북에서 같은 포트로 터널을 연다.

```bash
ssh -L 8766:127.0.0.1:8766 user@dgx-spark
```

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

개발 PC의 대시보드는 AsyncSSH로 X2 개발 보드에 접속한다. 로봇에 이미 설치된 ROS 2 Humble과 AIMDK를 사용해 전용 워커를 실행한다. 워커 파일은 `/home/agi/agibot_dashboard`에 동기화하며 SDK·펌웨어를 다시 설치하지 않는다. 개발 PC에는 SDK ARM64 바이너리나 ROS 설치가 필요하지 않다. 실제 통신은 SSH 포트 22를 이용하고 웹 대시보드는 8766 하나를 사용한다.

운동 보드 `10.0.1.40`을 직접 조종하거나 MC 앱을 중지하는 실행기는 포함하지 않는다. 기본 개발 보드 `10.0.1.41`의 공식 ROS SDK 서비스를 호출한다. 설치 SDK 관측 버전은 `aimdk v1.0.0-ga424add`이며 연결 시 해당 기기의 상수·서비스 준비 상태를 다시 조회한다.

## 제어와 VLM

- 프리셋은 문서 ID·제어 영역과 설치 SDK 상수가 정확히 맞는 항목만 UI/VLM에 제공한다. 기준 설치본에서 17개가 매핑되며 재생 성공을 확인한 목록과는 구분한다.
- `↑+×`는 `SIT_JOINT_DEFAULT`, 의자 기립 `↑+□`는 `SIT_UP_DEFAULT`, 의자 착석 `L2+←`는 `SIT_DOWN_DEFAULT`로 매핑한다.
- 이동은 6방향 속도 명령이며 각 축 절댓값 0.30 이하, 수동 누름 기본 1초·최대 5초다. 정확한 보 수·거리 제어는 제공하지 않는다.
- 매 VLM 요청의 입력 사진·지시·요청·응답·실행 피드백은 로컬 `x2_motion/artifacts/vlm_runs/`에 저장한다. API 키는 기록하지 않는다.
- 전면 RGB 미리보기는 30fps 고정이며 실제 수신 속도는 환경에 따라 달라진다.
- 직접 관절 목표는 미리보기까지 제공한다. LiDAR 표준 점군 수신은 아직 검증하지 않았다.

상세 매핑과 조건은 [SDK_MAPPING.md](docs/SDK_MAPPING.md), 현장 실행 순서는 [OPERATIONS.md](docs/OPERATIONS.md), 검증 범위는 [VERIFICATION.md](VERIFICATION.md)를 참고한다.

## 검증과 변경

```bash
./preflight.sh --offline --test
python3 refresh_checksums.py --check
```

소스를 수정했으면 `python3 refresh_checksums.py`로 무결성 목록을 갱신한다. GitHub Actions는 Linux와 macOS의 Python 3.10/3.12에서 설치·Bash 구문·오프라인 검사를 수행한다. 실제 DGX·X2 연결과 동작 검증은 별도 현장 확인이 필요하다.
