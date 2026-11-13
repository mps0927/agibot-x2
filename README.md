# AGIBOT X2 Multimodal Pipeline

X2 Ultra t2d5의 영상·배터리·관절·라이다를 확인하고, 일어서기·앉기·프리셋·이동을 조작하는 웹 대시보드입니다. OpenRouter의 이미지 지원 모델을 선택해 사진과 글로 로봇 동작을 요청할 수 있습니다. [Unitree G1 파이프라인](https://github.com/8l4nnk/unitree-g1-pipeline)과 조작 화면 구성을 맞췄습니다.

Windows PC, Mac, DGX Spark 중 **사용할 기기 한 대에서 Docker와 브라우저를 실행**하고, 그 기기에 X2를 LAN으로 직접 연결합니다. 대시보드 주소는 **[http://127.0.0.1:8766](http://127.0.0.1:8766)**입니다. G1의 기본 포트 8765와 함께 사용할 수 있습니다.

## 처음 사용하는 경우

**[처음 설치하고 로봇 연결하기](docs/FIRST_START_KO.md)**를 순서대로 따라 하세요. 명령 창을 여는 방법부터 `.env` 저장, 운영체제별 유선 설정과 SSH 로그인까지 설명합니다.

| 최초 한 번 | 이후 매번 |
|---|---|
| Git·Docker 설치, 저장소 내려받기 | Docker 실행 |
| `.env`에 로봇 로그인 정보 입력 | 로봇 전원 켜기·LAN 연결 |
| 로봇용 유선 어댑터의 IP 설정 | 프로젝트 폴더에서 `docker compose up -d` |
| 로봇 접속 키 등록·연결 확인 | 브라우저 열기·로봇 제어 준비 |

설정은 해당 PC와 유선 어댑터에서 계속 사용합니다. 새 PC나 새 USB LAN 어댑터를 사용할 때는 [최초 설정](docs/FIRST_START_KO.md)을 확인합니다.

## 최초 설치 순서

### 1. Git과 Docker를 준비합니다

Windows·Mac은 Docker Desktop을 실행합니다. DGX Spark는 Docker 서비스를 실행합니다. [설치 방법](docs/FIRST_START_KO.md#install)에 따라 준비한 뒤 확인합니다.

```bash
git --version
docker version
docker compose version
```

Docker의 Client·Server가 모두 나오고 Compose가 **2.30 이상**이면 진행합니다. Python과 대시보드 패키지는 Docker가 준비합니다.

### 2. 프로젝트와 설정 파일을 준비합니다

처음 내려받는 경우 명령을 한 줄씩 실행합니다. [GitHub 로그인 도움말](docs/FIRST_START_KO.md#github-login)을 참고할 수 있습니다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
cp .env.example .env
```

이미 내려받았다면 `agibot-x2` 폴더에서 기존 `.env`를 엽니다.

| 기기 | `.env` 열기 | 저장 |
|---|---|---|
| Windows PowerShell | `notepad .env` | `Ctrl+S` |
| Mac 터미널 | `open -e .env` | `Command+S` |
| DGX 터미널 | `nano .env` | `Ctrl+O` → Enter → `Ctrl+X` |

파일에서 아래 값을 확인하고 실제 로봇 비밀번호를 입력합니다.

```dotenv
X2_SSH_HOST=10.0.1.41
X2_SSH_USER=agi
X2_SSH_PASSWORD=
OPENROUTER_API_KEY=
```

`X2_SSH_PASSWORD=` 뒤에는 장비 담당자가 알려 준 로봇 비밀번호를 입력합니다. VLM을 사용할 때 `OPENROUTER_API_KEY=` 뒤에 OpenRouter 키도 입력합니다. 값은 따옴표 없이 적고 UTF-8로 저장합니다. [설정 파일 작성 방법](docs/FIRST_START_KO.md#env)에 예시가 있습니다.

### 3. 대시보드를 엽니다

```bash
docker compose up -d
```

첫 실행에는 인터넷에서 필요한 파일을 내려받고 이미지를 만듭니다. 완료되면 같은 기기의 브라우저에서 [대시보드](http://127.0.0.1:8766)를 엽니다. `.env`와 로봇이 없어도 화면을 확인할 수 있습니다. `-d`로 실행하면 터미널을 닫아도 대시보드가 유지됩니다.

### 4. 로봇과 유선으로 연결합니다

[전원 켜기](docs/USER_GUIDE_KO.md#power-on)에 따라 로봇을 부팅하고 PC와 X2 뒤쪽 개발용 RJ45를 LAN으로 연결합니다. **로봇용 유선 어댑터**에 아래 주소를 처음 한 번 설정합니다.

| 항목 | 값 |
|---|---|
| PC 유선 IPv4 | `10.0.1.2` |
| 서브넷 마스크 / 프리픽스 | `255.255.255.0` / `24` |
| 게이트웨이·DNS | 비워 둡니다. |
| 로봇 주소 | `10.0.1.41` |

인터넷용 Wi-Fi는 기존 설정을 유지합니다. [Windows·Mac·DGX 설정 화면 안내](docs/FIRST_START_KO.md#lan)에 따라 저장하고 확인합니다. 이미 연결되는 PC는 기존 설정을 사용합니다.

```bash
docker compose run --rm x2 network-check
```

`접속 가능: 10.0.1.41:22`가 나오면 다음으로 진행합니다.

### 5. 로봇을 등록하고 로그인을 확인합니다

```bash
docker compose run --rm x2 trust-host
```

표시되는 호스트 키 지문을 장비 담당자가 제공한 지문과 대조하고 `yes`를 입력합니다. 같은 PC·같은 로봇에서는 처음 한 번 등록합니다. 이어서 로그인과 SDK를 확인합니다.

```bash
docker compose run --rm x2 doctor
```

`Robot SDK:` 뒤에 버전 정보가 나오면 로그인·SDK 조회에 성공한 것입니다. 대시보드가 자동으로 연결될 때까지 기다린 뒤 **연결됨·현재 모드·배터리·영상·점군 수신**을 확인합니다. 출력 해석은 [로봇 등록과 진단](docs/FIRST_START_KO.md#trust)을 참고합니다.

### 6. 화면에서 제어를 준비합니다

[대시보드 사용설명서](docs/USER_GUIDE_KO.md#control-ready)에 따라 **착석 자세 고정 → 일어서기 → 제어 활성화**를 진행합니다. 연결이 끊겼다가 복구되면 현재 자세를 확인하고 제어를 다시 활성화합니다.

## 이후 사용할 때

1. Docker를 실행합니다.
2. 로봇을 부팅하고 같은 PC·유선 어댑터에 LAN을 연결합니다.
3. `agibot-x2` 폴더에서 실행합니다.

```bash
docker compose up -d
```

4. [대시보드](http://127.0.0.1:8766)를 열고 제어 준비를 진행합니다.

매일의 시작·조종·종료는 [현장 사용 순서](docs/OPERATIONS.md)를 따릅니다. 화면만 확인할 때도 같은 명령을 사용합니다. 로봇이 준비되면 백그라운드에서 자동으로 접속합니다.

## 설정 변경·문제 해결·종료

| 할 일 | 명령 또는 안내 |
|---|---|
| 대시보드 실행 상태 확인 | `docker compose ps` |
| 최근 로그 확인 | `docker compose logs --tail 100 x2` |
| 유선 연결 확인 | `docker compose run --rm x2 network-check` |
| 로봇 로그인·SDK·센서 확인 | `docker compose run --rm x2 doctor` |
| `.env` 저장 후 적용 | 조종을 마친 뒤 `docker compose up -d --force-recreate` |
| 대시보드 종료 | 로봇을 앉히고 힘을 해제한 뒤 `docker compose down` |
| 연결 문제 해결 | [단계별 검사와 오류별 조치](docs/FIRST_START_KO.md#connection-check) |

업데이트는 [로봇 종료 준비](docs/USER_GUIDE_KO.md#power-off)를 마친 뒤 진행합니다.

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

`.env`, 등록된 로봇 키와 촬영 기록은 유지됩니다. 촬영 사진·VLM 기록의 PC 복사는 [기록 가져오기](docs/USER_GUIDE_KO.md#records)를 따릅니다.

## 사용설명서

- [처음 설치하고 로봇 연결하기](docs/FIRST_START_KO.md)
- [대시보드로 A to Z](docs/USER_GUIDE_KO.md) — 화면 버튼으로 준비·조종·종료·충전
- [리모컨으로 A to Z](docs/REMOTE_CONTROL_GUIDE_KO.md) — 리모컨 연결·버튼 조합·종료
- [현장 사용 순서](docs/OPERATIONS.md) — 매일 시작하고 끝내는 순서
- [카메라·센서 안내](docs/SENSORS.md)
- [개인 키로 SSH 접속하기](docs/USER_GUIDE_KO.md#ssh-key)

## 주요 기능

- **로봇 제어 준비:** 착석 자세 고정, 의자에서 일어서기, 의자에 앉기, 댐핑·영토크 전환.
- **직접 조종:** 설치 SDK에서 매핑된 프리셋, 이동·회전 버튼과 WASD·Q/E, 이동 정지·제어 해제.
- **로봇 상태:** 상단 배터리 잔량, 관절 각도 슬라이더, 현재 운용 모드.
- **센서:** 카메라·센서 자동 조회, 위치·현재 값·수신 상태, RGB·깊이 영상 선택, RGB 미리보기 30fps 설정, LiDAR 자동 연결·점군 XY 화면·수신 상태. 실제 수신 속도는 장비와 연결 상태에 따라 달라집니다.
- **VLM:** OpenRouter 이미지 지원 모델 검색·선택, 사진과 텍스트 지시, 점군 요약 첨부, 요청별 사진·응답·실행 기록 저장.

카메라와 센서별 데이터는 [카메라·센서 안내](docs/SENSORS.md)를 참고합니다.

## 프로젝트 구성

```text
agibot-x2/
├── Dockerfile / compose.yaml / compose.ssh-key.yaml
├── docker/                 # 실행 준비, 접속 키 등록, 연결 진단
├── .env.example
├── x2_motion/              # 대시보드 서버, 로봇 워커, VLM, 센서, 웹 화면
├── sdk_reference/          # 설치 SDK의 상수·서비스 참조
├── docs/                   # 사용설명서와 개발 안내
└── .github/workflows/      # Python 검사와 AMD64·ARM64 Docker 빌드
```

컨테이너에서 X2 개발 보드 `10.0.1.41`에 SSH로 접속합니다. 로봇에 설치된 ROS 2 Humble과 AIMDK를 사용하며, 대시보드 워커는 `/home/agi/agibot_dashboard`에 배치합니다. 웹 화면·RGB·점군은 같은 대시보드에서 제공합니다.

개발용 `.sh` 실행과 테스트는 [개발 안내](docs/DEVELOPMENT.md), 기능별 SDK 연결은 [SDK 매핑](docs/SDK_MAPPING.md), 점검 결과는 [검증 기록](docs/VERIFICATION.md)에 정리했습니다.
