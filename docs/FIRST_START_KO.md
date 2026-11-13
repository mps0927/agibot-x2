# 처음 설치하고 로봇 연결하기

Windows PC, Mac, DGX Spark 중 사용할 기기 한 대에서 진행합니다. 그 기기에 프로젝트를 내려받고 Docker와 브라우저를 실행하며, X2도 그 기기의 유선 포트에 연결합니다.

처음 사용하는 PC에서는 **1~8번을 순서대로** 진행합니다. 설치를 마쳤다면 [매일 사용하는 순서](OPERATIONS.md)를 따릅니다.

## 목차

1. [준비물과 명령 창](#terminal)
2. [Git·Docker 설치](#install)
3. [프로젝트 내려받기](#first-start)
4. [`.env` 작성](#env)
5. [로봇 부팅·LAN·유선 IP 설정](#lan)
6. [대시보드 실행](#dashboard-start)
7. [로봇 등록·로그인 확인](#trust)
8. [연결 완료 확인](#operate)
9. [다음부터 시작·종료·업데이트](#daily)
10. [연결 문제 해결](#errors)
11. [선택 설정](#optional)

<a id="terminal"></a>
## 1. 준비물과 명령 창

### 준비물을 확인합니다

| 준비물 | 확인할 내용 |
|---|---|
| 사용할 PC와 인터넷 | Windows, Mac 또는 DGX Spark. 설치·업데이트와 VLM에 인터넷을 사용합니다. |
| LAN 케이블 | PC에 유선 포트가 없으면 USB Ethernet 어댑터를 준비합니다. |
| 저장소 접근 권한 | 사용할 GitHub 계정에서 [저장소](https://github.com/mps0927/agibot-x2)가 열리는지 확인합니다. 초대받았다면 먼저 수락합니다. |
| 로봇 접속 정보 | 로봇 주소, 계정, 로그인 비밀번호, SSH 호스트 키 지문을 장비 담당자에게 확인합니다. 기본 주소·계정은 `10.0.1.41`·`agi`입니다. |
| OpenRouter API 키 | 사진과 글로 AI 명령을 사용할 때 준비합니다. |
| 로봇 지지·정지 수단 | 의자·보조자·리모컨은 [사용 전 준비](USER_GUIDE_KO.md#prepare)를 따릅니다. |

### 명령 창을 엽니다

| 기기 | 여는 방법 |
|---|---|
| Windows | 시작 버튼 → `PowerShell` 검색 → 실행 |
| Mac | `Command+Space` → `터미널` 검색 → 실행 |
| DGX Spark | 앱 목록 → `Terminal` 또는 `터미널` 실행 |

회색 명령 상자의 내용만 한 줄씩 복사해 붙여 넣고 Enter를 누릅니다. 처리가 끝나 다시 입력할 수 있는 줄이 나타나면 다음 명령으로 진행합니다. 비밀번호 입력 중에는 글자나 별표가 보이지 않을 수 있습니다.

<a id="install"></a>
## 2. Git·Docker 설치

Git은 프로젝트를 내려받고 업데이트합니다. Docker는 대시보드와 필요한 실행 환경을 준비합니다. Python과 패키지는 Docker가 함께 준비합니다.

<a id="install-windows"></a>
### 2.1 Windows

1. [Git 다운로드](https://git-scm.com/downloads/win)에서 설치 파일을 받아 설치합니다. 기본 옵션으로 진행합니다.
2. [Docker Desktop 설치](https://docs.docker.com/desktop/setup/install/windows-install/)에서 PC에 맞는 설치 파일을 받습니다. Intel·AMD PC는 x86_64용을 사용합니다.
3. 설치 프로그램을 실행하고 WSL 2 사용 항목은 기본 선택을 유지합니다.
4. 재부팅을 요청하면 재부팅합니다.
5. 시작 메뉴에서 `Docker Desktop`을 실행하고 초기 안내를 마칩니다.
6. WSL 설치·업데이트 안내가 나오면 화면에 표시된 절차를 완료하고 Docker Desktop을 다시 실행합니다.
7. Docker 엔진이 실행될 때까지 기다리고 PowerShell 창을 새로 엽니다.

Docker 메뉴에 `Switch to Linux containers`가 보이면 선택합니다. 이어서 [설치 확인](#install-check)을 진행합니다.

<a id="install-mac"></a>
### 2.2 Mac

1. Apple 메뉴 → `이 Mac에 관하여`에서 칩을 확인합니다. Apple 칩은 Apple silicon용, Intel은 Intel용 설치 파일을 사용합니다.
2. [Docker Desktop 설치](https://docs.docker.com/desktop/setup/install/mac-install/)에서 해당 파일을 받습니다.
3. `.dmg` 파일을 열고 Docker를 `응용 프로그램` 폴더로 옮깁니다.
4. 응용 프로그램에서 Docker를 실행하고 초기 안내를 마칩니다. 엔진이 준비될 때까지 기다립니다.
5. 터미널에서 아래 명령을 실행합니다.

```bash
git --version
```

명령줄 개발 도구 설치 창이 나오면 설치를 마치고 같은 명령을 다시 실행합니다. Git 버전이 나오면 [설치 확인](#install-check)으로 진행합니다.

<a id="install-dgx"></a>
### 2.3 DGX Spark

먼저 [설치 확인](#install-check)의 세 명령을 실행합니다. 기본 설치된 프로그램이 정상으로 확인되면 다음 단계로 진행합니다.

Docker 서비스만 멈춰 있으면 시작합니다.

```bash
sudo systemctl start docker
```

`sudo`가 묻는 비밀번호에는 현재 DGX 사용자 계정의 비밀번호를 입력합니다.

Git 명령이 없으면 설치합니다.

```bash
sudo apt-get update
sudo apt-get install git
```

Compose가 없으면 [Linux Compose 플러그인 설치](https://docs.docker.com/compose/install/linux/), Docker 자체가 없으면 [Ubuntu Docker 설치](https://docs.docker.com/engine/install/ubuntu/)의 순서로 준비합니다. 설치 후 아래 명령을 다시 확인합니다.

<a id="install-check"></a>
### 2.4 설치 확인

```bash
git --version
docker version
docker compose version
```

| 명령 | 다음으로 진행할 기준 | 실패하면 |
|---|---|---|
| `git --version` | `git version ...` 표시 | Git 설치 후 명령 창을 새로 엽니다. |
| `docker version` | `Client`와 `Server` 버전 모두 표시 | Windows·Mac은 Docker Desktop, DGX는 Docker 서비스를 실행합니다. |
| `docker compose version` | 버전 2.30 이상 | Windows·Mac은 Docker Desktop을 업데이트하고, DGX는 Compose 플러그인을 업데이트합니다. |

DGX에서 `permission denied`와 `docker.sock`이 함께 나오면 [Docker 권한 설정](#docker-permission)을 진행합니다.

<a id="first-start"></a>
## 3. 프로젝트 내려받기

### 3.1 저장소를 내려받습니다

명령 창에서 프로젝트를 보관할 폴더로 이동하고 실행합니다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
```

`git clone`은 프로젝트 폴더를 만들고 파일을 내려받습니다. `cd agibot-x2`는 그 폴더 안으로 들어갑니다. GitHub 로그인이 나오면 접근 권한을 받은 계정을 사용합니다. 실패하면 [GitHub 로그인 해결](#github-login)을 확인합니다.

이미 내려받은 `agibot-x2` 폴더가 있으면 다음 방법으로 그 폴더에서 명령 창을 엽니다.

<a id="project-folder"></a>
### 3.2 프로젝트 폴더에서 명령 창을 엽니다

| 기기 | 여는 방법 |
|---|---|
| Windows | 탐색기로 `agibot-x2` 폴더 열기 → 주소창에 `powershell` 입력 → Enter |
| Mac·DGX Spark | 터미널에 `cd ` 입력 → `agibot-x2` 폴더를 터미널로 끌어 놓기 → Enter |

Windows는 `dir`, Mac·DGX는 `ls`를 입력합니다. 파일 목록에 `compose.yaml`과 `README.md`가 보이면 올바른 위치입니다. 이후 이 문서의 명령은 이 폴더에서 실행합니다.

<a id="env"></a>
## 4. `.env` 작성

`.env`는 대시보드가 사용할 로봇 접속 정보와 OpenRouter 키를 저장하는 파일입니다. SSH는 PC에서 로봇에 로그인하는 접속 방식입니다.

### 4.1 설정 파일을 만듭니다

프로젝트 파일 목록에 `.env`가 이미 있으면 그 파일을 사용합니다. 아직 없을 때만 다음을 실행합니다.

```bash
cp .env.example .env
```

Windows의 `dir -Force`, Mac·DGX의 `ls -a`로 숨김 파일까지 확인할 수 있습니다. `.env`와 `.env.example`이 보이면 복사가 끝난 것입니다.

### 4.2 파일을 엽니다

| 기기 | 명령 | 저장 방법 |
|---|---|---|
| Windows | `notepad .env` | 수정 후 `Ctrl+S` |
| Mac | `open -e .env` | 수정 후 `Command+S` |
| DGX Spark | `nano .env` | 수정 후 `Ctrl+O` → Enter → `Ctrl+X` |

Mac 텍스트 편집기는 일반 텍스트로 저장합니다. 필요하면 `포맷 → 일반 텍스트 만들기`를 선택합니다. nano가 없는 DGX에서는 파일 관리자에서 `Ctrl+H`로 숨김 파일을 표시하고 `.env`를 텍스트 편집기로 엽니다.

### 4.3 실제 접속 정보를 입력합니다

다음 줄을 찾아 `=` 오른쪽을 수정합니다.

```dotenv
X2_SSH_HOST=10.0.1.41
X2_SSH_USER=agi
X2_SSH_PASSWORD=
OPENROUTER_API_KEY=
```

| 항목 | 입력할 내용 |
|---|---|
| `X2_SSH_HOST` | 로봇 주소. 기본값 `10.0.1.41` |
| `X2_SSH_USER` | 로봇 로그인 계정. 기본값 `agi` |
| `X2_SSH_PASSWORD` | 장비 담당자가 알려 준 로봇의 `agi` 계정 비밀번호 |
| `OPENROUTER_API_KEY` | VLM을 사용할 때 [OpenRouter 키 관리](https://openrouter.ai/settings/keys)에서 발급한 API 키 |

예를 들어 비밀번호가 `sample123`이라면 다음처럼 적습니다. `sample123`은 설명용 예시이며 실제 입력에는 담당자가 알려 준 값을 사용합니다.

```dotenv
X2_SSH_PASSWORD=sample123
```

값은 따옴표 없이 한 줄에 입력합니다. 비밀번호에 `$`, `#`, `=`가 있으면 그대로 적습니다. UTF-8 일반 텍스트로 저장하고 파일 이름은 정확히 `.env`로 유지합니다. 실제 비밀번호와 API 키가 담긴 파일은 개인 PC에 보관합니다.

Windows 탐색기에서 `보기 → 표시 → 파일 확장명`을 켜면 `.env.txt`로 저장됐는지 확인할 수 있습니다. Mac Finder에서는 `Command+Shift+.`으로 숨김 파일을 표시합니다.

이 단계에서는 파일을 저장하면 됩니다. 대시보드를 실행한 뒤 값을 바꿨다면 [설정 변경 적용](#settings-change)을 진행합니다.

<a id="lan"></a>
## 5. 로봇 부팅·LAN·유선 IP 설정

### 5.1 로봇을 부팅하고 랜선을 꽂습니다

1. [전원 켜기](USER_GUIDE_KO.md#power-on)에 따라 로봇을 의자와 보조자로 지지하고 부팅합니다.
2. LAN 케이블 한쪽을 [X2 등쪽 개발용 RJ45](USER_GUIDE_KO.md#buttons)에 꽂습니다.
3. 반대쪽을 지금 대시보드를 사용할 PC의 유선 포트 또는 USB Ethernet 어댑터에 꽂습니다.
4. 포트 링크 표시등과 PC의 유선 연결 상태를 확인합니다.

어댑터 이름이 여러 개라면 PC 쪽 케이블을 뺐을 때 연결 표시가 사라지는 항목을 찾고 다시 꽂습니다. 이 확인은 로봇이 지지되고 조종을 시작하기 전의 상태에서 진행합니다.

### 5.2 PC 유선 주소와 로봇 주소를 확인합니다

| 주소를 사용하는 곳 | 주소 | 역할 |
|---|---|---|
| PC의 로봇용 Ethernet | `10.0.1.2` | PC 자신의 유선 주소 |
| `.env`의 `X2_SSH_HOST` | `10.0.1.41` | 대시보드가 로그인할 로봇 주소 |
| PC 브라우저 | `http://127.0.0.1:8766` | 이 PC에서 실행하는 대시보드 |

```text
PC 유선 10.0.1.2 ── LAN 케이블 ── X2 10.0.1.41
PC Wi-Fi         ── 공유기      ── 인터넷
```

PC와 로봇이 서로 데이터를 주고받도록 PC의 유선 주소를 같은 대역에 맞춥니다. **로봇 케이블을 연결한 유선 어댑터**에서 처음 한 번 설정합니다. 인터넷용 Wi-Fi는 기존 설정을 유지합니다.

| 설정 항목 | 입력값 |
|---|---|
| IPv4 주소 | `10.0.1.2` |
| 서브넷 마스크 | `255.255.255.0` |
| 프리픽스 길이 | 마스크 대신 이 항목이 나오면 `24` |
| 게이트웨이 / 라우터 | 비워 둡니다. |
| DNS | 비워 둡니다. |

`10.0.1.2`를 다른 장비가 이미 사용 중이면 담당자와 확인해 비어 있는 같은 대역 주소를 사용합니다. 로봇 내부 장비의 `10.0.1.40`, `10.0.1.41`, `10.0.1.42`는 PC 주소로 사용하지 않습니다.

<a id="lan-windows"></a>
### 5.3 Windows

1. 시작 → `설정` → `네트워크 및 인터넷` → `Ethernet`을 엽니다.
2. 로봇 케이블을 연결한 어댑터를 선택합니다.
3. `IP 할당` 옆의 `편집`을 누릅니다.
4. `수동`을 선택하고 `IPv4`를 켭니다.
5. 위 표의 값으로 입력하고 `저장`합니다.
6. Ethernet 세부 정보에서 IPv4 주소가 `10.0.1.2`인지 확인합니다.

어댑터 선택 화면이 다르면 `Windows+R` → `ncpa.cpl` → Enter를 누릅니다. 해당 Ethernet을 오른쪽 클릭 → `속성` → `인터넷 프로토콜 버전 4(TCP/IPv4)` → `속성` → `다음 IP 주소 사용`에서 같은 값을 입력합니다. 관리자 확인이 나오면 이 PC의 관리 권한으로 승인합니다.

<a id="lan-mac"></a>
### 5.4 Mac

1. Apple 메뉴 → `시스템 설정` → `네트워크`를 엽니다.
2. 로봇 케이블을 연결한 `Ethernet` 또는 USB LAN 어댑터를 선택합니다.
3. `세부사항` → `TCP/IP`를 엽니다.
4. `IPv4 구성`을 `수동`으로 바꿉니다.
5. 위 표의 IP 주소와 서브넷 마스크를 입력하고 라우터는 비워 둡니다.
6. `확인`·`적용`으로 저장하고 IPv4 주소가 `10.0.1.2`인지 확인합니다.

Docker나 터미널의 로컬 네트워크 접근 허용 창이 나오면 허용합니다. DNS는 로봇용 연결에 별도로 입력하지 않습니다.

<a id="lan-dgx"></a>
### 5.5 DGX Spark

1. 화면 오른쪽 위 네트워크 메뉴 → `설정` → `네트워크`를 엽니다.
2. 로봇 케이블을 연결한 `유선 연결`의 톱니바퀴를 누릅니다.
3. `IPv4` 탭에서 `수동`을 선택합니다.
4. 주소 `10.0.1.2`, 넷마스크 `255.255.255.0`을 입력하고 게이트웨이는 비워 둡니다.
5. DNS 자동 설정을 끄고 DNS는 비워 둡니다.
6. `적용`을 누르고 해당 유선 연결을 껐다가 켭니다. 세부 정보에서 주소가 `10.0.1.2`인지 확인합니다.

설정을 마치면 아래 6번으로 진행합니다. 로봇용 유선 연결에 `인터넷 없음`이 표시될 수 있습니다. 인터넷은 Wi-Fi로 사용하고, 로봇과의 통신은 다음 단계의 `network-check`로 확인합니다.

같은 PC·같은 어댑터에서는 저장한 주소를 사용 후에도 유지합니다. 새 PC나 새 어댑터를 사용하면 유선 주소를 다시 확인합니다.

<a id="dashboard-start"></a>
## 6. 대시보드 실행

프로젝트 폴더에서 실행합니다.

```bash
docker compose up -d
```

첫 실행에는 인터넷에서 필요한 파일을 내려받고 Docker 이미지를 만듭니다. 컨테이너 시작이 완료되고 다시 명령을 입력할 수 있게 되면 같은 PC의 브라우저에서 다음 주소를 엽니다.

**[http://127.0.0.1:8766](http://127.0.0.1:8766)**

`127.0.0.1`은 지금 사용하는 PC 자체를 뜻합니다. `-d`는 명령 창을 닫아도 대시보드를 계속 실행하는 옵션입니다.

대시보드 화면이 열리면 실행이 완료된 것입니다. `.env`와 로봇이 없어도 화면을 열고 이미지를 업로드할 수 있습니다. 로봇 접속은 설정과 연결이 준비되면 자동으로 재시도합니다.

화면이 안 열리면 확인합니다.

```bash
docker compose ps
docker compose logs --tail 100 x2
```

`x2`가 `Up`이고 잠시 후 `healthy`가 표시되면 웹 서버가 실행 중입니다. 같은 PC에서 주소를 다시 확인합니다. 실패 원인은 [오류 문구별 안내](#errors)를 따릅니다.

<a id="trust"></a>
## 7. 로봇 등록·로그인 확인

### 7.1 유선 연결을 검사합니다

프로젝트 폴더에서 실행합니다.

```bash
docker compose run --rm x2 network-check
```

`접속 가능: 10.0.1.41:22`가 나오면 로봇의 로그인 포트에 도달한 것입니다. 실패하면 전원·랜선·PC 유선 주소·`.env`의 로봇 주소를 확인합니다.

### 7.2 처음 연결한 로봇을 등록합니다

```bash
docker compose run --rm x2 trust-host
```

로봇 주소와 `SHA256:...` 모양의 SSH 호스트 키 지문이 나옵니다. 이 값은 접속한 로봇의 신원을 구별합니다. 장비 담당자가 제공한 지문과 대조해 맞으면 다음을 입력하고 Enter를 누릅니다.

```text
yes
```

`호스트 키를 등록했습니다.` 또는 `등록된 로봇 호스트 키`가 나오면 완료입니다. 같은 로봇과 이 PC의 Docker 저장 공간을 계속 사용하면 등록 정보도 유지됩니다.

### 7.3 로그인과 SDK를 확인합니다

```bash
docker compose run --rm x2 doctor
```

`Robot SDK:` 뒤에 버전 정보가 나오면 로그인과 SDK 조회에 성공한 것입니다. 이어서 센서 진단이 나옵니다.

| 결과 | 확인할 내용 |
|---|---|
| `Robot SDK:` | 로봇 로그인·설치 SDK 조회 성공 |
| `Publisher count: 0` | 이어지는 센서 브리지 결과도 확인 |
| `X2_BRIDGE_RESULT`의 `connected: true`, `frames` 1 이상 | 센서 브리지에서 라이다 점군 수신 |
| 센서 브리지 도구 준비 중 | 대시보드 자동 연결을 기다린 뒤 다시 진단 |

`doctor`가 출력한 SDK 버전이 확인되면 다음 단계에서 대시보드 수신을 확인합니다. 점군이 아직 없다면 [센서 확인](USER_GUIDE_KO.md#lidar)을 따릅니다. 계정·비밀번호·등록 키 오류는 [연결 문제 해결](#errors)을 참고합니다.

<a id="operate"></a>
## 8. 연결 완료 확인

1. 같은 PC에서 [대시보드](http://127.0.0.1:8766)를 엽니다.
2. 상단의 `AGIBOT X2 연결됨` 표시를 확인합니다.
3. 현재 모드와 배터리 잔량이 표시되고 카메라 영상이 갱신되는지 확인합니다.
4. `관절 상태`를 눌러 현재 각도와 상태가 표시되는지 확인합니다.
5. `LiDAR · X2 센서`에서 점군 수신을 확인합니다.

연결과 최신 상태 수신이 확인되면 설치가 완료된 것입니다. 로봇을 움직일 때는 [로봇 제어 준비](USER_GUIDE_KO.md#control-ready)의 자세·지지 확인과 화면 조작을 진행합니다.

VLM을 사용하려면 OpenRouter 준비 표시를 확인하고 `현재 프레임 사용` → 지시 입력 → `계획만 보기`로 분석을 확인합니다. 이 버튼은 실행할 동작을 화면에 표시합니다. 실제 명령 전송은 [VLM 사용 순서](USER_GUIDE_KO.md#vlm)를 따릅니다.

<a id="daily"></a>
## 9. 다음부터 시작·종료·업데이트

매일의 시작·종료는 [현장 사용 순서](OPERATIONS.md)를 따릅니다. 같은 PC와 어댑터에서는 `.env`, 유선 주소와 로봇 키를 계속 사용합니다.

<a id="settings-change"></a>
### 9.1 `.env` 변경 적용

기존 `.env`를 열어 값을 바꾸고 저장합니다. 로봇 조작과 VLM 요청을 마친 뒤 프로젝트 폴더에서 적용합니다.

```bash
docker compose up -d --force-recreate
```

새 설정으로 대시보드가 다시 시작합니다. 연결 표시와 최신 상태를 확인합니다. 사진·VLM 기록과 등록된 로봇 키는 Docker 저장 공간에 유지됩니다.

### 9.2 업데이트

로봇을 의자에 앉히고 힘 해제까지 마친 뒤 진행합니다.

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

`.env`와 Docker의 촬영 기록·등록 키는 유지됩니다. 소스를 직접 수정해 업데이트가 중단되면 변경 파일을 보관하고 담당자에게 확인합니다. 기존 기록의 PC 복사는 [요청 기록 확인](USER_GUIDE_KO.md#records)을 따릅니다.

<a id="errors"></a>
## 10. 연결 문제 해결

<a id="connection-check"></a>
### 10.1 위에서부터 확인합니다

로봇을 지지하고 조종을 멈춘 상태에서 진행합니다. 명령은 프로젝트 폴더에서 실행합니다.

| 순서 | 확인 | 정상 표시 | 실패하면 |
|---|---|---|---|
| 1 | `docker version` | Client·Server 버전 | Docker Desktop 또는 Docker 서비스를 시작합니다. |
| 2 | `docker compose ps` | `x2`의 `Up`, 잠시 후 `healthy` | `docker compose up -d` 후 로그를 봅니다. |
| 3 | `http://127.0.0.1:8766` | 대시보드 화면 | 프로젝트를 실행한 같은 PC에서 주소를 확인합니다. |
| 4 | `docker compose run --rm x2 network-check` | `접속 가능` | 전원 → LAN 링크 → PC 유선 IP → 로봇 주소를 확인합니다. |
| 5 | 최초 연결이면 `docker compose run --rm x2 trust-host` | 키 등록 완료 | 지문과 오류 문구를 확인합니다. |
| 6 | `docker compose run --rm x2 doctor` | `Robot SDK:` 버전 | 로봇 계정·비밀번호·등록 키를 확인합니다. |
| 7 | 대시보드 연결 표시·현재 모드·영상 | 최신 상태 수신 | 로그와 아래 표의 증상을 확인합니다. |

로그를 봅니다.

```bash
docker compose logs --tail 100 x2
```

담당자에게는 운영체제, 실패한 단계와 오류 문구를 전달합니다. 비밀번호·API 키가 있는 `.env`는 개인 PC에 보관합니다.

### 10.2 오류 문구별 안내

| 문구·증상 | 조치 |
|---|---|
| `git`·`docker` 명령을 찾을 수 없음 | 해당 프로그램을 설치한 뒤 명령 창을 새로 엽니다. |
| Docker의 `Server` 정보가 없음 | Docker Desktop 또는 Docker 서비스를 실행하고 준비를 기다립니다. |
| `format`·`env_file` 설정 오류 | Compose를 2.30 이상으로 업데이트합니다. |
| `no configuration file provided` | [프로젝트 폴더](#project-folder)에서 다시 실행합니다. |
| GitHub `Repository not found` | 접근 권한·초대 수락·[로그인 계정](#github-login)을 확인합니다. |
| `destination path ... already exists` | 기존 `agibot-x2` 폴더에서 명령 창을 엽니다. |
| Ethernet에 `인터넷 없음` | 로봇용 연결은 `network-check`로 확인하고 인터넷은 Wi-Fi로 사용합니다. |
| 유선 주소가 `169.254...` | 해당 Ethernet의 주소를 5번의 고정 주소로 설정합니다. |
| `TimeoutError`·`연결 실패` | 로봇 부팅·케이블·PC 유선 주소·로봇 주소를 순서대로 확인합니다. |
| `Connection refused` | 로봇 부팅을 기다린 뒤 다시 검사합니다. 계속되면 로봇 주소·SSH 서비스를 담당자에게 확인합니다. |
| SSH의 `Permission denied`·`PermissionDenied` | `.env`의 로봇 계정·비밀번호를 확인하고 저장한 뒤 `--force-recreate`로 적용합니다. |
| `Host key is not trusted`·접속 키 파일 없음 | 7번의 `trust-host`로 실제 로봇 지문을 확인하고 등록합니다. |
| 기존 호스트 키와 다름 | 연결한 로봇과 등록 정보를 담당자에게 확인합니다. |
| `.env`를 고쳤는데 그대로임 | 파일 이름·UTF-8 저장·프로젝트 위치를 확인하고 [설정 변경 적용](#settings-change)을 진행합니다. |
| `8766` 포트 사용 중 | 같은 프로젝트의 기존 Docker 실행은 `docker compose down`으로 종료합니다. Python으로 직접 켠 서버는 [개발 안내](DEVELOPMENT.md)에 따라 종료합니다. |
| `healthy`인데 영상이 없음 | 로봇의 전원·LAN·로그인·키 등록을 확인합니다. 화면의 연결 표시와 `doctor` 결과를 확인합니다. |
| 직접 SSH는 되는데 Docker 연결 검사만 실패 | Mac의 Docker 로컬 네트워크 접근 허용, VPN의 로컬 LAN 허용, 보안 프로그램의 Docker 접근 규칙을 확인합니다. |

<a id="docker-permission"></a>
### 10.3 DGX의 Docker 권한 설정

`permission denied`와 `/var/run/docker.sock`이 함께 나오면 이 PC를 관리하는 계정에서 실행합니다.

```bash
sudo usermod -aG docker "$USER"
```

Docker 그룹은 시스템 관리 권한을 부여합니다. 로그아웃 후 다시 로그인하고 `docker version`을 확인합니다.

<a id="github-login"></a>
### 10.4 GitHub 로그인 해결

1. 브라우저에서 저장소에 접근할 수 있는 계정으로 로그인합니다.
2. 저장소 초대가 있으면 수락합니다.
3. `git clone`이 여는 로그인 창에서 같은 계정을 사용합니다.
4. 브라우저 로그인이 제공되지 않고 터미널에서 인증을 요구하면 [GitHub CLI](https://cli.github.com/)를 설치하고 실행합니다.

```bash
gh auth login
```

`GitHub.com` → `HTTPS` → Git 인증 질문에 `Y` → 브라우저 로그인을 선택합니다. 화면에 나온 일회용 코드를 브라우저에 입력해 승인한 뒤 `git clone`을 다시 실행합니다.

조종과 버튼에 관한 문제는 [대시보드 문제 해결](USER_GUIDE_KO.md#troubleshooting)을 참고합니다.

<a id="optional"></a>
## 11. 선택 설정

<a id="ssh"></a>
### 11.1 터미널에서 SSH를 직접 확인할 때

로봇 부팅과 유선 설정을 마친 뒤 PC의 명령 창에서 실행합니다.

```bash
ssh agi@10.0.1.41
```

첫 접속에서는 지문을 대조하고 `yes`를 입력합니다. `password:`에는 로봇 비밀번호를 입력합니다. 로봇의 명령 프롬프트가 나오면 로그인에 성공한 것입니다. 다음 명령으로 PC 명령 창으로 돌아옵니다.

```bash
exit
```

Docker의 등록 정보는 7번의 `trust-host`로 별도로 저장합니다. 개인 키 인증을 사용한다면 [개인 키 연결](USER_GUIDE_KO.md#ssh-key)을 따릅니다.

<a id="restore-lan"></a>
### 11.2 같은 랜포트를 일반 인터넷용으로 바꿔 쓸 때

로봇용 랜포트나 USB LAN 어댑터를 **공유기·벽면 인터넷 단자에 연결해 사용할 때만** 진행합니다. 로봇용 어댑터를 유지하고 인터넷은 Wi-Fi로 사용하면 고정 주소도 유지합니다.

로봇 사용을 마치고 케이블을 분리한 뒤 같은 어댑터에서 바꿉니다.

| 기기 | 변경 |
|---|---|
| Windows | Ethernet의 IP 할당과 DNS를 `자동(DHCP)`으로 설정합니다. TCP/IPv4 속성을 사용했다면 IP·DNS 모두 자동으로 바꿉니다. |
| Mac | Ethernet의 TCP/IP에서 IPv4 구성을 `DHCP 사용`으로 바꿉니다. |
| DGX Spark | 유선 연결의 IPv4·DNS를 자동으로 설정하고 적용한 뒤 연결을 다시 켭니다. |

사무실에서 별도 고정 주소를 안내받았다면 해당 주소를 사용합니다. 이 어댑터를 로봇에 다시 연결할 때는 [5번의 고정 주소](#lan)를 설정합니다.

## 참고

- [제조사 X2 유선 연결 안내](https://x2-aimdk.agibot.com/en/dev/quick_start/prerequisites.html#network-connection)
- [Windows 네트워크 설정](https://support.microsoft.com/en-gb/windows/experience/connectivity-networking/essential-network-settings-and-tasks-in-windows), [Mac TCP/IP 설정](https://support.apple.com/en-bw/guide/mac-help/mh14129/mac)
- [Linux Docker 사용자 권한](https://docs.docker.com/engine/install/linux-postinstall/)
- [GitHub 인증 안내](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git)
- [README로 돌아가기](../README.md)
