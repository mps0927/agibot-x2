# AGIBOT X2 대시보드

AGIBOT X2 Ultra의 카메라·라이다·배터리·관절 상태를 확인하고, 화면에서 착석 고정·일어서기·프리셋·이동을 조작합니다. OpenRouter의 이미지 지원 모델을 선택해 사진과 글로 동작을 요청할 수 있습니다.

**Windows PC, Mac, DGX Spark 중 사용할 기기 한 대에서 설치부터 조종까지 진행합니다.** 그 기기에서 Docker와 브라우저를 실행하고, X2를 LAN 케이블로 직접 연결합니다.

- 처음 설치한다면 아래 **1번부터** 진행합니다. 클릭 위치와 저장 방법은 [최초 설치 안내](docs/FIRST_START_KO.md)에 있습니다.
- 설치를 마쳤다면 [다음부터 시작하기](#daily)로 이동합니다.
- 대시보드 주소는 [http://127.0.0.1:8766](http://127.0.0.1:8766)입니다.

<a id="prepare"></a>
## 1. 시작 전 준비

| 준비할 것 | 확인할 내용 |
|---|---|
| 사용할 PC 한 대 | Windows, Mac 또는 DGX Spark. 설치·업데이트와 VLM 사용에 필요한 인터넷 연결 |
| Git·Docker | Git은 프로젝트를 내려받고, Docker는 대시보드와 필요한 프로그램을 실행합니다. Python과 패키지는 Docker가 준비합니다. |
| 저장소 접근 권한 | [GitHub 저장소](https://github.com/mps0927/agibot-x2)가 해당 계정에서 열리는지 확인합니다. |
| LAN 케이블 | PC에 유선 포트가 없으면 USB Ethernet 어댑터도 준비합니다. |
| 로봇 접속 정보 | 기본 주소 `10.0.1.41`, 계정 `agi`, 장비 담당자가 알려 준 로봇 비밀번호와 SSH 호스트 키 지문 |
| 로봇 지지·정지 준비 | [사용 전 준비](docs/USER_GUIDE_KO.md#prepare)에 따라 의자·보조자·리모컨을 준비합니다. |
| OpenRouter API 키 | VLM을 사용할 때 준비합니다. 수동 조종만 사용하면 비워 둡니다. |

처음 한 번은 프로그램 설치, `.env` 작성, 유선 IP 설정과 로봇 키 등록을 진행합니다. 같은 PC·같은 어댑터에서는 설정을 저장해 계속 사용합니다.

<a id="first-setup"></a>
## 2. 처음 한 번 설치하고 연결하기

### 2.1 프로그램을 설치하고 명령 창을 엽니다

[Windows](docs/FIRST_START_KO.md#install-windows), [Mac](docs/FIRST_START_KO.md#install-mac), [DGX Spark](docs/FIRST_START_KO.md#install-dgx) 안내에 따라 Git과 Docker를 준비합니다. Windows에서는 **PowerShell**, Mac·DGX에서는 **터미널**을 엽니다.

Windows·Mac에서는 Docker Desktop을 실행한 뒤, 명령 창에서 한 줄씩 실행합니다.

```bash
git --version
docker version
docker compose version
```

Git 버전, Docker의 `Client`·`Server` 버전, Compose **2.30 이상**이 표시되면 진행합니다. 실패하면 [설치 확인](docs/FIRST_START_KO.md#install-check)을 따릅니다.

### 2.2 프로젝트를 내려받습니다

원하는 작업 폴더에서 실행합니다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
```

명령 창에서 `compose.yaml`과 `README.md`가 있는 폴더에 들어왔으면 완료입니다. 이미 내려받았다면 [프로젝트 폴더에서 명령 창 열기](docs/FIRST_START_KO.md#project-folder)를 따릅니다. 로그인에 실패하면 [GitHub 접속 안내](docs/FIRST_START_KO.md#github-login)를 확인합니다.

### 2.3 `.env`에 접속 정보를 저장합니다

프로젝트 폴더에서 `.env`가 아직 없을 때만 복사합니다. 기존 파일이 있으면 바로 엽니다.

```bash
cp .env.example .env
```

| 기기 | 파일 열기 | 저장 |
|---|---|---|
| Windows | `notepad .env` | `Ctrl+S` |
| Mac | `open -e .env` | `Command+S` |
| DGX Spark | `nano .env` | `Ctrl+O` → Enter → `Ctrl+X` |

아래 줄을 찾아 `=` 오른쪽을 입력하고 UTF-8 일반 텍스트로 저장합니다.

```dotenv
X2_SSH_HOST=10.0.1.41
X2_SSH_USER=agi
X2_SSH_PASSWORD=
OPENROUTER_API_KEY=
```

`X2_SSH_PASSWORD`에 실제 로봇 비밀번호를 입력합니다. VLM을 사용하면 `OPENROUTER_API_KEY`도 입력합니다. 값은 따옴표 없이 적습니다. [파일 작성 예시와 저장 방법](docs/FIRST_START_KO.md#env)을 참고하세요.

### 2.4 로봇을 켜고 유선 주소를 설정합니다

[전원 켜기](docs/USER_GUIDE_KO.md#power-on)에 따라 로봇을 의자와 보조자로 지지하고 부팅합니다. LAN 케이블로 PC와 [X2 뒤쪽 개발용 RJ45 포트](docs/USER_GUIDE_KO.md#buttons)를 연결합니다.

PC에서 로봇 케이블을 꽂은 **유선 어댑터**에 다음 값을 저장합니다. [Windows](docs/FIRST_START_KO.md#lan-windows), [Mac](docs/FIRST_START_KO.md#lan-mac), [DGX Spark](docs/FIRST_START_KO.md#lan-dgx)의 설정 순서를 따릅니다.

| 설정하는 곳 | 값·역할 |
|---|---|
| PC의 Ethernet IPv4 주소 | `10.0.1.2` — PC 자신의 유선 주소 |
| 서브넷 마스크 / 프리픽스 | `255.255.255.0` / `24` |
| 유선 게이트웨이·DNS | 비워 둡니다. 인터넷용 Wi-Fi는 기존 설정을 유지합니다. |
| `.env`의 로봇 주소 | `10.0.1.41` — 대시보드가 접속할 대상 |

```text
PC 유선 10.0.1.2 ── LAN ── X2 10.0.1.41
PC Wi-Fi         ── 공유기 ── 인터넷
```

유선 설정 화면에 `10.0.1.2`가 표시되면 완료입니다. 로봇용 고정 주소는 사용 후에도 유지합니다. 같은 랜포트를 일반 인터넷용으로 바꿔 쓸 때만 [주소 복원](docs/FIRST_START_KO.md#restore-lan)을 진행합니다.

### 2.5 대시보드를 실행합니다

프로젝트 폴더에서 실행합니다.

```bash
docker compose up -d
```

첫 실행에는 필요한 파일을 내려받고 이미지를 만듭니다. 명령이 완료되면 같은 PC의 브라우저에서 [대시보드](http://127.0.0.1:8766)를 엽니다. `-d`로 실행하면 명령 창을 닫아도 유지됩니다. 로봇이 없어도 화면을 열고 이미지를 업로드할 수 있습니다.

화면이 열리지 않으면 [실행 확인](docs/FIRST_START_KO.md#dashboard-start)을 따릅니다.

### 2.6 로봇을 등록하고 연결을 확인합니다

프로젝트 폴더에서 연결을 검사합니다.

```bash
docker compose run --rm x2 network-check
```

`접속 가능: 10.0.1.41:22`가 나오면 로봇의 신원을 확인해 등록합니다.

```bash
docker compose run --rm x2 trust-host
```

표시된 지문을 장비 담당자가 제공한 지문과 대조한 뒤 `yes`를 입력합니다. 등록 완료 문구가 나오면 로그인과 SDK를 확인합니다.

```bash
docker compose run --rm x2 doctor
```

`Robot SDK:` 뒤에 버전이 나오면 로그인·SDK 조회에 성공한 것입니다. 대시보드가 자동으로 접속할 때까지 기다린 뒤 **연결됨 표시, 현재 모드, 배터리, 카메라 영상**이 갱신되는지 확인합니다. [등록·진단 출력 설명](docs/FIRST_START_KO.md#trust)과 [센서 확인](docs/USER_GUIDE_KO.md#lidar)을 참고하세요.

실패하면 [연결 점검 순서](#troubleshooting)로 진행합니다.

<a id="daily"></a>
## 3. 다음부터 시작하기

1. Docker Desktop 또는 Docker 서비스를 실행합니다.
2. 로봇 지지 상태를 준비하고 전원을 켭니다.
3. 같은 PC·유선 어댑터에 로봇 LAN을 연결합니다.
4. 프로젝트 폴더에서 실행합니다.

```bash
docker compose up -d
```

5. [대시보드](http://127.0.0.1:8766)를 열고 최신 상태 수신을 확인합니다.
6. 아래 제어 준비를 진행합니다.

접속 정보·유선 설정·등록 키가 유지되면 전원과 LAN 연결 후 자동으로 접속합니다. 새 PC에서는 [최초 설정](#first-setup)을 진행하고, 새 어댑터에서는 유선 주소를 확인합니다.

<a id="control-ready"></a>
## 4. 대시보드에서 제어 준비하기

상단의 **로봇 제어 준비**를 순서대로 진행합니다. 자세와 지지 조건은 [버튼별 안내](docs/USER_GUIDE_KO.md#control-ready)를 따릅니다.

| 순서 | 화면에서 할 일 | 완료 확인 |
|---|---|---|
| 1 | 의자에 앉은 자세를 지지하고 `착석 자세 고정` 실행 | 실제 자세 유지·`착석 고정` 표시 |
| 2 | 의자·양발·보조자·기립 공간을 확인하고 `일어서기` 실행 | 실제 기립 완료·`안정 서기` 표시 |
| 3 | 현장 확인 항목을 체크하고 `제어 활성화` 클릭 | 버튼이 `제어 해제`로 변경 |

준비를 마치면 [프리셋](docs/USER_GUIDE_KO.md#presets), [이동·회전](docs/USER_GUIDE_KO.md#movement), [VLM 명령](docs/USER_GUIDE_KO.md#vlm)을 사용합니다. 움직임을 멈출 때는 `■ 이동 정지`를 누릅니다. 연결이 끊겼다가 복구되면 실제 자세와 모드를 확인하고 제어를 다시 활성화합니다.

프리셋은 제조사 운동 제어(MC)를 켠 채 실행합니다. 대시보드는 프리셋 실행을 위해 MC를 종료하거나 영토크·댐핑·위치제어 모드로 자동 전환하지 않습니다. 전송 직전 최신 제어 모드를 확인하며, 제조사가 요청을 거부하면 이유를 표시합니다.

오른팔 펀치 관절값은 [punch_right.json](x2_motion/punch_right.json)에 로컬 프리셋으로 등록되어 있습니다. 대시보드의 `펀치 · 오른팔 로컬 프리셋`에서 궤적을 확인할 수 있습니다. 현재 확인한 SDK 1.0에서는 기본 MC를 유지하는 관절 전송 경로가 연결되지 않아 실물 실행은 잠겨 있습니다.

<a id="lidar-vlm"></a>
### VLM에 라이다 정보 함께 보내기

1. `LiDAR · X2 센서`에 `점군 수신 중`이 표시되는지 확인합니다.
2. `VLM에 점군 요약 함께 전달`을 체크합니다.
3. 프레임과 지시를 선택하고 `계획만 보기` 또는 `명령 보내기 · ready면 실행`을 누릅니다.

체크한 요청에는 사진과 함께 **점 개수, 표본 중 최근접 거리, X·Y·Z 좌표 범위, 좌표계·시각·데이터 경과 시간**이 JSON 텍스트로 전달됩니다. 최신 점군이 수신 중일 때 선택할 수 있습니다.

`시스템 프롬프트 · 요청 / 응답`의 `마지막 모델 요청 · system / user 원문`에서 `lidar` 항목을 확인합니다. 모델에 보낸 요약과 표본 좌표는 요청별 실험 기록에도 보관됩니다. 라이다와 RGB는 비동기이며 표본에는 바닥·로봇 몸체가 포함될 수 있습니다.

[전달 값과 기록 확인](docs/SENSORS.md#lidar-vlm)에 상세한 설명이 있습니다.

<a id="shutdown"></a>
## 5. 사용을 마치고 종료하기

1. 동작을 마치고 `■ 이동 정지` → `제어 해제`를 누릅니다.
2. 의자 위치와 보조자 지지를 준비하고, 안정 서기에서 `의자에 앉기`를 실행합니다.
3. 완전히 앉은 뒤 지지를 유지하며 `댐핑` → `영토크 · 힘 해제`로 전환합니다.
4. 프로젝트 폴더에서 대시보드를 종료합니다.

```bash
docker compose down
```

5. 배터리 버튼을 짧게 한 번 누른 뒤 약 5초 길게 누르고 전원 꺼짐을 확인합니다.

[앉히기·힘 해제·전원 끄기](docs/USER_GUIDE_KO.md#power-off)의 상세 절차를 따릅니다. 촬영 기록과 등록 키는 Docker 저장 공간에 유지됩니다. 충전은 [충전 안내](docs/USER_GUIDE_KO.md#charging)를 따릅니다.

<a id="troubleshooting"></a>
## 6. 연결이 안 될 때

위에서부터 확인합니다. 모든 명령은 프로젝트 폴더에서 실행합니다.

| 확인 | 정상 결과 | 안 되면 |
|---|---|---|
| `docker version` | Client·Server 버전 | Docker Desktop 또는 서비스를 실행합니다. |
| `docker compose ps` | `x2`가 `Up`, 잠시 후 `healthy` | `docker compose up -d` 후 로그를 봅니다. |
| `http://127.0.0.1:8766` | 대시보드 화면 | 같은 PC에서 주소와 포트를 확인합니다. |
| `docker compose run --rm x2 network-check` | `접속 가능` | 로봇 부팅·랜선·PC 유선 IP·로봇 주소를 확인합니다. |
| `docker compose run --rm x2 doctor` | `Robot SDK:` 버전 | 로봇 키 등록과 `.env`의 계정·비밀번호를 확인합니다. |

오류 문구별 조치는 [연결 문제 해결](docs/FIRST_START_KO.md#errors)에 있습니다. `healthy`는 웹 서버가 응답한다는 뜻이며, 로봇 연결은 화면의 연결 표시와 최신 영상·상태로 확인합니다.

<a id="system-prompt"></a>
## 7. 실험용 시스템 프롬프트 변경

**실험자는 시스템 프롬프트를 원하는 실험 목적에 맞게 수정할 수 있습니다.** 역할, 장면 해석 기준, 동작 선택 규칙, 설명 방식 등을 바꿔 모델의 응답을 비교할 수 있습니다.

수정할 파일은 [x2_motion/prompts/x2_system_en.txt](x2_motion/prompts/x2_system_en.txt)입니다. UTF-8 텍스트로 편집하고 저장합니다.

| 기기 | 프로젝트 폴더에서 파일 열기 |
|---|---|
| Windows | `notepad x2_motion/prompts/x2_system_en.txt` |
| Mac | `open -e x2_motion/prompts/x2_system_en.txt` |
| DGX Spark | `nano x2_motion/prompts/x2_system_en.txt` |

Docker에서는 프롬프트가 이미지에 포함됩니다. 조종과 VLM 요청을 마친 뒤 수정본으로 다시 빌드해 적용합니다.

```bash
docker compose up -d --build
```

대시보드의 `시스템 프롬프트 · 요청 / 응답`을 펼쳐 반영된 내용을 확인하고, `계획만 보기`로 응답을 비교합니다. 프롬프트 뒤에는 로봇의 동작 목록과 현재 상태가 자동으로 붙습니다. 실행 코드의 명령 형식 검사·속도·시간·권한 조건은 별도로 적용됩니다.

[시스템 프롬프트 실험 안내](docs/SYSTEM_PROMPT_KO.md)에 수정 예시, 적용 확인과 요청 기록 확인 방법이 있습니다.

<a id="maintenance"></a>
## 8. 설정 변경·업데이트

`.env`를 수정했다면 로봇 조작과 VLM 요청을 마친 뒤 적용합니다.

```bash
docker compose up -d --force-recreate
```

업데이트는 로봇을 의자에 지지하고 종료 준비를 마친 뒤 진행합니다.

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

기존 `.env`, 등록 키와 촬영 기록은 유지됩니다. 기록을 PC로 가져오는 방법은 [요청 기록 확인](docs/USER_GUIDE_KO.md#records)을 참고하세요.

## 9. 자세한 사용설명서

| 문서 | 내용 |
|---|---|
| [최초 설치 안내](docs/FIRST_START_KO.md) | 프로그램 설치·파일 저장·운영체제별 유선 설정·SSH 등록·오류 해결 |
| [대시보드 사용설명서](docs/USER_GUIDE_KO.md) | 화면 버튼으로 준비·조종·센서·VLM·종료·충전 |
| [리모컨 사용설명서](docs/REMOTE_CONTROL_GUIDE_KO.md) | 리모컨 연결·버튼 조합·정지·종료 |
| [현장 사용 순서](docs/OPERATIONS.md) | 설치를 마친 뒤 매일 확인할 시작·종료 순서 |
| [카메라·센서 안내](docs/SENSORS.md) | 영상 선택·장치 상태·라이다 확인 |
| [시스템 프롬프트 실험 안내](docs/SYSTEM_PROMPT_KO.md) | 프롬프트 수정·적용·응답 비교·실제 전송 기록 확인 |

개발·Python 직접 실행은 [개발 안내](docs/DEVELOPMENT.md), 기능별 연결은 [SDK 매핑](docs/SDK_MAPPING.md)을 참고합니다. 조작 화면은 [Unitree G1 파이프라인](https://github.com/8l4nnk/unitree-g1-pipeline)과 구성을 맞췄으며, X2는 포트 `8766`을 사용합니다.
