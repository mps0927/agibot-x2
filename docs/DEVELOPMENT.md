# 개발 안내

일반 사용은 [Docker 사용설명서](USER_GUIDE_KO.md#dashboard)를 따릅니다. 이 문서는 Python에서 직접 실행하거나 소스를 수정할 때 사용합니다.

## Python으로 직접 실행

Python 3.10 이상과 Git, Bash를 준비합니다. Windows에서는 Git Bash, Linux·macOS에서는 터미널을 사용합니다. 같은 포트의 Docker 대시보드를 사용 중이면 먼저 `docker compose down`으로 종료합니다.

저장소 폴더에서 `.env.example`을 참고해 `.env`를 준비하고 실행합니다. 기존 `.env`는 그대로 사용합니다.

```bash
./setup.sh
```

기존 Python으로 `.venv`를 만들고 이후 같은 환경을 재사용합니다. 특정 Python을 사용하려면 최초 실행 시 `PYTHON_BIN=/path/to/python3 ./setup.sh`를 지정합니다.

실물 연결은 PC에서 로봇에 LAN으로 직접 접속합니다. `.env`에 SSH 접속 정보를 입력하고, `X2_SSH_KNOWN_HOSTS`를 PC의 키 등록 파일로 지정합니다. 기본값은 `~/.ssh/known_hosts`입니다. 개인 키 인증은 `X2_SSH_KEY`에 PC의 키 파일 경로를 입력합니다.

```bash
ssh agi@10.0.1.41
```

처음 접속할 때 로봇의 키 지문을 확인해 등록하고, 접속되면 `exit`로 PC 터미널에 돌아옵니다.

```bash
./start_field.sh
./status.sh
```

같은 PC에서 [대시보드](http://127.0.0.1:8766)를 엽니다. `start_field.sh`는 실행 전에 실물 접속을 확인합니다. `.env` 경로를 지정하려면 `./start_field.sh --env-file /path/to/.env`를 사용합니다.

| 개발 작업 | 명령 |
|---|---|
| 제어 기능을 포함한 실물 실행 | `./start_field.sh` |
| 실물 상태만 조회 | `./run.sh --field` |
| 로봇 없이 UI·이미지 분석 개발 | `./run.sh --offline` |
| 저장 자료로 화면 재현 | `./run.sh --offline --replay /path/to/robot_snapshot` |
| 실물 접속·SDK 확인 | `./preflight.sh --field` |
| 서버 상태·종료 | `./status.sh` / `./stop.sh` |

직접 실행 시 로그는 `.runtime/dashboard.log`, 사진·VLM 기록은 `x2_motion/artifacts/`에 저장됩니다. Docker 실행 기록은 `/data/artifacts/`에 저장됩니다. 설정은 실행한 PC의 `.env`에서 읽으며, 환경변수로 지정한 값이 우선합니다.

## 저장소 관리

- 루트에는 Docker 설정과 실행 진입점을 둡니다.
- 사용설명서·SDK 안내·[검증 기록](VERIFICATION.md)은 `docs/`에서 관리합니다.
- `.sh` 파일은 Python 직접 실행과 Ubuntu·macOS CI에서 사용합니다.
- `sdk_reference/`는 SDK 매핑 회귀 검사의 기준 자료입니다.
- `x2_motion/test_*.py`는 GitHub에서 유지하며 Docker 이미지에서는 제외합니다.
- 실제 비밀번호·접속 키·촬영 기록·로봇 로그는 Git에 올리지 않습니다.

## 소스 수정과 검사

소스를 수정하면 무결성 목록을 갱신한 뒤 검사합니다.

```bash
python refresh_checksums.py
./preflight.sh --offline --test
python refresh_checksums.py --check
```

`python` 대신 설치된 `python3` 명령을 사용해도 됩니다. 단위 테스트만 실행하려면 프로젝트 가상환경에서 `python -m unittest discover -s x2_motion`을 실행합니다.

Docker 이미지에 변경 사항을 반영합니다.

```bash
docker compose up -d --build
```

GitHub Actions는 Ubuntu·macOS의 Python 3.10/3.12 조합과 Docker의 Linux AMD64·ARM64 빌드를 검사합니다. Docker 런타임 테스트는 외부 네트워크가 없는 컨테이너에서 모의 SSH 서버로 권한 전환과 인증을 확인합니다. `docker/test_compose.py`는 새 체크아웃 복사본에서 `.env` 없는 시작, 설정 반영, 비밀번호 특수문자, 이미지 유지와 볼륨 보존을 확인합니다. 테스트 이미지를 준비한 뒤 `python docker/test_compose.py`로 실행하며 기본 이미지 이름은 `agibot-x2:runtime-test`입니다.

## 센서·기록 관련 파일

| 파일 | 역할 |
|---|---|
| `docker/entrypoint.py` | 설정 파일 준비, 실행 사용자 전환, 서버·진단 명령 실행 |
| `docker/doctor.py` | 로봇 SSH·SDK·점군 토픽 조회 |
| `x2_motion/dashboard_base.py` | 연결 재시도, 화면 API, 이미지·VLM 요청 |
| `x2_motion/app.py` | X2 연결과 센서 상태·점군 API |
| `x2_motion/sensor_bridge.py` | 로봇 내부의 기존 센서 브리지 읽기 전용 구독 |
| `x2_motion/sensor_cdr.py` | SDK 미포함 상태 메시지의 제한된 CDR1 해석 |
| `x2_motion/sensors.py` | 센서 분류·상태 요약·카메라 변환 |
| `x2_motion/lidar.py` | PointCloud2 해석, 표본 추출, 최신 점군 관리 |
| `x2_motion/x2_worker.py` | 로봇 SDK 호출, 카메라·라이다 구독 |
| `x2_motion/vlm_recording.py` | 요청 사진·응답·피드백 저장 |

라이다 점군은 기존 SSH 연결로 전달합니다. 화면용 점군은 최대 3,000점·5Hz이며, 요청 이후 받은 점군만 사용합니다. 1.5초가 지난 점군은 VLM 입력에서 제외합니다. 실제 로봇에서 발행되는 토픽·좌표계·수신 상태는 연결 후 확인합니다.
