# AGIBOT X2 Multimodal Pipeline

X2 Ultra t2d5의 영상·배터리·관절·라이다를 확인하고, 일어서기·앉기·프리셋·이동을 조작하는 웹 대시보드입니다. OpenRouter의 이미지 지원 모델을 선택해 사진과 글로 로봇 동작을 요청할 수 있습니다. [Unitree G1 파이프라인](https://github.com/8l4nnk/unitree-g1-pipeline)과 조작 화면 구성을 맞췄습니다.

Windows PC, DGX Spark, Mac에서 **각 기기 자체로 Docker를 실행**하고 같은 기기의 브라우저로 사용합니다. 로봇을 사용할 때는 해당 기기에 X2를 LAN으로 직접 연결합니다. **대시보드 포트는 8766 하나**이며 G1의 기본 포트 8765와 함께 사용할 수 있습니다.

## 사용설명서

- **[처음 설치하고 로봇 연결하기](docs/FIRST_START_KO.md)** — 프로그램 설치 화면, 명령 창 열기, `.env` 수정, SSH 비밀번호 입력, Windows·Mac·DGX의 LAN 주소 설정부터 시작합니다.

- **[대시보드로 A to Z](docs/USER_GUIDE_KO.md)** — Docker 설치·실행, 전원 켜기, LAN 연결, 화면에서 착석 고정·기립·조종·종료·충전까지.
- **[리모컨으로 A to Z](docs/REMOTE_CONTROL_GUIDE_KO.md)** — 리모컨 연결과 버튼 조합으로 준비·조종·종료하기.
- **[현장 사용 순서](docs/OPERATIONS.md)** — 설치를 마친 뒤 매일 사용할 순서.

## Docker로 실행

Git과 Docker Compose **2.30 이상**을 준비합니다. Windows와 Mac에서는 Docker Desktop을 실행하고, DGX Spark에서는 Docker 서비스를 실행합니다. Docker가 Python과 대시보드 패키지를 함께 준비합니다.

Windows PowerShell, Mac·DGX 터미널에서 같은 명령을 사용합니다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
docker compose up -d
```

첫 실행에는 필요한 파일을 내려받고 이미지를 만듭니다. 완료되면 같은 기기의 브라우저에서 **[대시보드 열기](http://127.0.0.1:8766)**를 누릅니다. `.env`와 로봇이 없어도 화면이 열립니다. `-d`로 실행하면 터미널을 닫아도 대시보드가 유지됩니다.

### 로봇과 VLM을 처음 연결할 때

1. `.env` 파일이 아직 없다면 프로젝트 폴더에서 다음 명령으로 설정 파일을 만듭니다.

```bash
cp .env.example .env
```

2. 파일을 엽니다. Windows는 `notepad .env`, Mac은 `open -e .env`, DGX는 `nano .env`를 사용합니다. 아래 항목의 `=` 오른쪽에 실제 값을 입력하고 저장합니다.

```dotenv
X2_SSH_HOST=10.0.1.41
X2_SSH_USER=agi
X2_SSH_PASSWORD=로봇의_agi_계정_비밀번호
OPENROUTER_API_KEY=발급받은_OpenRouter_키
```

`X2_SSH_HOST`는 로봇 주소, `X2_SSH_USER`는 로봇 계정, `X2_SSH_PASSWORD`는 그 계정의 로그인 비밀번호입니다. 비밀번호는 장비 담당자에게 확인합니다. 값은 따옴표 없이 입력합니다. VLM을 사용할 때는 OpenRouter 키도 입력합니다. 파일을 여는 방법과 저장 키는 [접속 정보 입력하기](docs/FIRST_START_KO.md#env)를 참고합니다.

3. 이미 켜 둔 대시보드에 저장한 설정을 적용합니다.

```bash
docker compose up -d --force-recreate
```

4. [전원 켜기](docs/USER_GUIDE_KO.md#power-on)에 따라 로봇을 부팅합니다. 해당 PC와 X2를 LAN으로 연결하고 [유선 주소 설정](docs/FIRST_START_KO.md#lan)을 진행합니다. 기본 예시는 PC `10.0.1.2`, 로봇 `10.0.1.41`입니다.
5. 로봇을 처음 연결한 기기에서 접속 키를 등록하고 로그인을 확인합니다. 표시된 지문을 장비 담당자가 제공한 지문과 대조한 뒤 `yes`를 입력합니다.

```bash
docker compose run --rm x2 trust-host
docker compose run --rm x2 doctor
```

[처음 로봇 등록하기](docs/FIRST_START_KO.md#trust)에 출력 내용과 확인 방법을 설명했습니다. 키는 Docker 볼륨에 저장되므로 같은 기기·같은 로봇에서는 처음 한 번 진행합니다. 개인 키 인증은 [개인 키 연결 방법](docs/USER_GUIDE_KO.md#ssh-key)을 따릅니다.

6. 대시보드의 **AGIBOT X2 연결됨**, RGB 영상과 현재 모드를 확인하고 **착석 자세 고정 → 일어서기 → 제어 활성화** 순서로 진행합니다.

이후 사용에는 `docker compose up -d`로 시작하고 전원·LAN을 연결하면 자동으로 접속합니다. 연결이 끊기면 재접속을 시도합니다. 기기마다 처음에 프로그램 설치·로봇 로그인·LAN 주소를 준비하며, 실행 명령은 Windows·Mac·DGX에서 같습니다.

### 상태 확인·종료·업데이트

| 할 일 | 명령 |
|---|---|
| 백그라운드 실행 | `docker compose up -d` |
| 대시보드 실행 상태 확인 | `docker compose ps` |
| 최근 로그 확인 | `docker compose logs --tail 100 x2` |
| 로봇 연결·SDK·라이다 토픽 진단 | `docker compose run --rm x2 doctor` |
| `.env` 변경 적용 | `docker compose up -d --force-recreate` |
| 대시보드 종료 | `docker compose down` |

로봇을 사용했다면 [의자에 앉히고 힘 해제하기](docs/USER_GUIDE_KO.md#power-off)를 마친 뒤 대시보드를 종료합니다. `docker compose up`으로 실행한 터미널에서는 `Ctrl+C`로도 대시보드를 중지할 수 있습니다.

소스를 업데이트할 때는 조작을 마치고 실행합니다.

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

`.env`와 Docker 볼륨의 기록은 유지됩니다. 촬영 사진과 VLM 기록은 컨테이너의 `/data/artifacts/`에 저장되며, PC 폴더로 복사하는 방법은 [요청 사진과 응답 확인](docs/USER_GUIDE_KO.md#records)을 참고합니다.

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

개발용 `.sh` 실행과 테스트는 [개발 안내](docs/DEVELOPMENT.md), 기능별 SDK 연결은 [SDK 매핑](docs/SDK_MAPPING.md), 점검 결과는 [검증 기록](VERIFICATION.md)에 정리했습니다.
