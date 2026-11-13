# 처음 설치하고 로봇 연결하기

이 설명서는 Windows PC, Mac, DGX Spark 중 실제로 사용할 기기에서 진행합니다. 그 기기에 프로젝트를 내려받고, 그 기기에서 대시보드와 브라우저를 실행합니다. 로봇도 그 기기의 LAN 포트에 연결합니다.

처음에는 화면부터 열고, 이어서 로봇을 연결합니다. 준비를 마친 다음부터는 저장소 폴더에서 아래 명령으로 시작합니다.

```bash
docker compose up -d
```

## 목차

1. [명령을 입력할 창 열기](#terminal)
2. [Git과 Docker 준비하기](#install)
3. [프로젝트 내려받고 화면 열기](#first-start)
4. [로봇 접속 정보 입력하기](#env)
5. [로봇과 PC를 LAN으로 연결하기](#lan)
6. [처음 연결하는 로봇 등록하기](#trust)
7. [대시보드에서 조종 시작하기](#operate)
8. [SSH 접속을 직접 확인하기](#ssh)
9. [다음 날 시작·종료·업데이트하기](#daily)
10. [오류 문구별 해결 방법](#errors)

<a id="terminal"></a>
## 1. 명령을 입력할 창 열기

설명서의 회색 명령 상자 안에 있는 내용을 한 줄씩 복사하고, 아래 프로그램에 붙여 넣은 뒤 Enter를 누릅니다. `$`, `PS C:\...>` 같은 표시가 창에 보이면 그 표시 뒤에 입력합니다. 명령 상자에는 입력할 내용만 적었습니다.

| 사용하는 기기 | 여는 방법 |
|---|---|
| Windows | 시작 버튼을 누르고 `PowerShell`을 검색해 실행합니다. |
| Mac | `Command + Space`를 누르고 `터미널`을 검색해 실행합니다. |
| DGX Spark | DGX 화면의 앱 목록에서 `Terminal` 또는 `터미널`을 엽니다. |

명령을 입력한 뒤 글자가 여러 줄 나올 수 있습니다. 처리가 끝나 다시 입력할 수 있는 줄이 나타나면 다음 명령으로 진행합니다.

<a id="install"></a>
## 2. Git과 Docker 준비하기

Git은 프로젝트를 내려받고 업데이트하는 프로그램입니다. Docker는 대시보드와 실행에 필요한 프로그램을 함께 준비합니다.

### 2.1 Windows

1. [Git 다운로드](https://git-scm.com/downloads/win) 페이지에서 설치 파일을 받아 실행합니다. 설치 안내에 따라 진행합니다.
2. [Docker Desktop 설치](https://docs.docker.com/desktop/setup/install/windows-install/) 페이지에서 PC에 맞는 Windows 설치 파일을 받습니다. 일반적인 Intel·AMD PC는 x86_64를 선택합니다.
3. 설치 프로그램을 실행합니다. WSL 2 사용 항목이 나오면 기본 선택을 유지합니다.
4. 설치 프로그램이 재부팅을 요청하면 재부팅합니다.
5. 시작 메뉴에서 **Docker Desktop**을 실행합니다. 이용 약관과 초기 안내를 마치고 엔진이 실행될 때까지 기다립니다.
6. WSL 설치·업데이트 안내가 나오면 Docker가 표시한 안내에 따라 완료한 뒤 Docker Desktop을 다시 실행합니다.
7. PowerShell 창을 새로 열고 아래 확인 명령을 실행합니다.

Docker는 Linux 컨테이너로 사용합니다. Docker 메뉴에 **Switch to Linux containers**가 보이면 선택합니다.

### 2.2 Mac

1. Apple 메뉴 → **이 Mac에 관하여**에서 칩 정보를 확인합니다. M1·M2·M3 등 Apple 칩이면 Apple silicon용, Intel이면 Intel용 설치 파일을 사용합니다.
2. [Docker Desktop 설치](https://docs.docker.com/desktop/setup/install/mac-install/) 페이지에서 해당 파일을 받습니다.
3. 내려받은 `.dmg` 파일을 열고 Docker를 **응용 프로그램** 폴더로 옮깁니다.
4. 응용 프로그램에서 Docker를 실행하고 초기 안내를 마칩니다. 엔진이 실행될 때까지 기다립니다.
5. 터미널을 열어 `git --version`을 실행합니다. 명령줄 개발 도구 설치 창이 나오면 설치를 완료합니다.

### 2.3 DGX Spark

DGX Spark에는 Docker 관련 도구가 기본 제공되므로 아래 확인 명령부터 실행합니다. Docker Compose가 없으면 [Compose 플러그인 설치 안내](https://docs.docker.com/compose/install/linux/)에 따라 설치합니다. Docker 자체가 없으면 [Ubuntu Docker 설치 안내](https://docs.docker.com/engine/install/ubuntu/)를 따릅니다.

Docker 서비스가 멈춰 있다면 다음 명령으로 시작합니다.

```bash
sudo systemctl start docker
```

`sudo`에서 비밀번호를 물으면 현재 DGX 사용자 계정의 비밀번호를 입력합니다. 입력 중 화면에는 글자나 별표가 표시되지 않습니다.

### 2.4 설치 결과 확인

모든 기기에서 같은 명령으로 확인합니다.

```bash
git --version
docker version
docker compose version
```

| 확인할 것 | 정상일 때 보이는 내용 |
|---|---|
| Git | `git version ...` |
| Docker | `Client`와 `Server` 각각의 버전 정보 |
| Compose | `Docker Compose version v2.30.0` 이상 또는 v5 등 더 높은 버전 |

Compose가 2.30보다 낮으면 업데이트합니다. Windows·Mac에서는 Docker Desktop의 업데이트 기능을 사용합니다. Linux에서는 설치한 Docker 저장소의 Compose 플러그인을 업데이트합니다.

DGX에서 `permission denied`와 `docker.sock`이 함께 나오면 [오류 해결](#errors)을 참고합니다.

<a id="first-start"></a>
## 3. 프로젝트 내려받고 화면 열기

### 3.1 프로젝트를 내려받습니다

원하는 작업 폴더에서 다음 명령을 실행합니다.

```bash
git clone https://github.com/mps0927/agibot-x2.git
cd agibot-x2
```

GitHub 로그인이 나오면 저장소 사용 권한을 받은 계정으로 로그인합니다. `cd agibot-x2`는 내려받은 프로젝트 폴더 안으로 들어가는 명령입니다.

이미 프로젝트를 내려받았다면 해당 폴더에서 명령 창을 엽니다. Windows에서는 탐색기로 `agibot-x2` 폴더를 열고 주소창에 `powershell`을 입력한 뒤 Enter를 누르면 됩니다. Mac·DGX에서는 터미널에 `cd `를 입력한 다음 폴더를 터미널로 끌어 놓고 Enter를 누릅니다.

현재 폴더 안에 `compose.yaml`과 `README.md`가 보이는지 확인합니다. Windows에서는 `dir`, Mac·DGX에서는 `ls`를 입력하면 파일 목록이 나옵니다.

### 3.2 대시보드를 시작합니다

```bash
docker compose up -d
```

처음에는 필요한 파일을 인터넷에서 내려받고 Docker 이미지를 만듭니다. 여러 줄의 빌드 로그가 출력되므로 완료될 때까지 기다립니다. 컨테이너가 시작됐다는 메시지가 나오면 브라우저 주소창에 다음 주소를 입력합니다.

**[http://127.0.0.1:8766](http://127.0.0.1:8766)**

`127.0.0.1`은 지금 사용 중인 기기 자체를 가리킵니다. `8766`은 이 대시보드에 사용하는 번호입니다. 프로젝트를 실행한 기기에서 Chrome·Safari·Edge 등의 브라우저로 엽니다.

`.env` 파일과 로봇이 없어도 이 단계에서 대시보드가 열립니다. 로봇을 연결하기 전에는 화면을 확인하고 이미지를 업로드할 수 있습니다. VLM 분석을 사용하려면 다음 단계에서 OpenRouter 키를 입력합니다.

`-d`는 창을 닫아도 백그라운드에서 실행을 유지하는 옵션입니다.

<a id="env"></a>
## 4. 로봇 접속 정보 입력하기

### 4.1 필요한 정보를 준비합니다

대시보드는 SSH라는 접속 방식으로 로봇 개발 보드에 로그인합니다. 프로젝트에 SSH 접속 프로그램이 포함되어 있습니다. 사용자는 다음 세 가지 정보를 입력합니다.

| 필요한 정보 | 이 X2의 기본값 또는 확인 방법 |
|---|---|
| 로봇 주소 | 기본값 `10.0.1.41`을 사용합니다. 납품 후 주소가 바뀌었다면 장비 담당자에게 확인합니다. |
| 로봇 계정 | 기본값 `agi`를 사용합니다. |
| 로봇 비밀번호 | 납품 접속 안내 또는 장비 담당자가 알려 준 **로봇의 `agi` 계정 비밀번호**를 사용합니다. |

비밀번호를 모르면 장비 담당자에게 “X2 개발 보드 `10.0.1.41`의 `agi` 계정 SSH 비밀번호”를 요청합니다.

### 4.2 설정 파일을 만듭니다

프로젝트 폴더에 `.env` 파일이 아직 없을 때 다음 명령을 한 번 실행합니다.

```bash
cp .env.example .env
```

`.env.example`은 빈 설정 예시이고, `.env`는 실제 접속 정보를 적는 파일입니다. 기존 `.env`가 있으면 그 파일을 열어 사용합니다.

### 4.3 설정 파일을 엽니다

**Windows PowerShell:**

```powershell
notepad .env
```

메모장이 열리면 아래 4.4의 항목을 수정하고 `Ctrl+S`로 저장합니다. 이미 만든 `.env`를 열었으므로 파일 이름은 그대로 유지합니다.

**Mac 터미널:**

```bash
open -e .env
```

텍스트 편집기가 열리면 내용을 수정하고 `Command+S`로 저장합니다.

**DGX 터미널:**

```bash
nano .env
```

내용을 수정한 뒤 `Ctrl+O` → Enter로 저장하고 `Ctrl+X`로 나옵니다. nano가 없으면 파일 관리자로 프로젝트 폴더를 열고 `Ctrl+H`로 숨김 파일을 표시한 뒤 `.env`를 텍스트 편집기로 엽니다.

### 4.4 주소·계정·비밀번호를 입력합니다

파일 안에서 다음 이름의 줄을 찾습니다. `=` 오른쪽의 값만 수정합니다.

```dotenv
X2_SSH_HOST=10.0.1.41
X2_SSH_USER=agi
X2_SSH_PASSWORD=
OPENROUTER_API_KEY=
```

예를 들어 담당자가 알려 준 로봇 비밀번호가 `sample123`이라면 비밀번호 줄은 다음 모양이 됩니다. `sample123`은 설명용 예시입니다.

```dotenv
X2_SSH_PASSWORD=sample123
```

`OPENROUTER_API_KEY=` 뒤에는 발급받은 OpenRouter 키를 입력합니다. 수동 조종만 사용한다면 이 값은 비워 두어도 됩니다. 실제 비밀번호와 API 키는 따옴표 없이 한 줄에 그대로 입력합니다. `$`, `#`, `=` 같은 문자가 포함돼 있어도 그대로 입력합니다. 파일은 UTF-8로 저장합니다.

### 4.5 저장한 설정을 대시보드에 적용합니다

이미 대시보드를 실행했다면 다음 명령을 입력합니다.

```bash
docker compose up -d --force-recreate
```

이 명령은 새 설정으로 대시보드 컨테이너를 다시 만듭니다. 사진·VLM 기록과 등록된 로봇 접속 키는 Docker 볼륨에 유지됩니다.

첫 실행 전에 `.env`를 준비했다면 `docker compose up -d`로 시작하면 됩니다.

<a id="lan"></a>
## 5. 로봇과 PC를 LAN으로 연결하기

### 5.1 로봇을 부팅하고 LAN을 꽂습니다

1. [전원 켜기](USER_GUIDE_KO.md#power-on)에 따라 로봇을 의자에 지지하고 부팅합니다.
2. LAN 케이블 한쪽을 X2 등쪽 RJ45 포트에 연결합니다. [포트 위치 그림](USER_GUIDE_KO.md#buttons)을 참고합니다.
3. 반대쪽을 지금 대시보드를 실행한 PC·Mac·DGX의 유선 LAN 포트에 연결합니다. 포트가 없으면 USB Ethernet 어댑터를 사용합니다.

### 5.2 PC의 로봇용 LAN 주소를 입력합니다

먼저 프로젝트 폴더의 명령 창에서 연결을 확인합니다.

```bash
docker compose run --rm x2 network-check
```

`접속 가능`이면 아래 주소 설정을 건너뛰고 로봇 등록·로그인을 진행합니다. `연결 실패`이면 로봇 부팅과 케이블을 확인한 뒤 아래 설정을 진행합니다. 같은 PC와 유선 어댑터에서는 저장된 설정을 계속 사용합니다.


PC와 로봇이 서로 통신하도록 PC의 유선 연결 주소를 맞춥니다. 케이블을 연결한 유선 어댑터에 다음 값을 입력합니다.

| 설정 항목 | 입력값 |
|---|---|
| IPv4 주소 / IP address | `10.0.1.2` |
| 서브넷 마스크 / Subnet mask | `255.255.255.0` |
| 프리픽스 길이 / Prefix | 위 마스크 대신 이 항목이 나오면 `24` |
| 게이트웨이 / Router | 비워 둡니다. |
| DNS | 로봇 전용 연결에서는 비워 둡니다. |

로봇 주소는 `10.0.1.41`, PC 주소는 `10.0.1.2`로 서로 다르게 설정합니다. `10.0.1.2`가 이미 다른 장비에 쓰이고 있으면 `10.0.1.3` 등 비어 있는 같은 대역 주소를 사용합니다. 인터넷용 Wi-Fi는 유지하고, 로봇 케이블을 꽂은 어댑터만 수정합니다.

**Windows:**

1. 시작 → **설정** → **네트워크 및 인터넷** → **Ethernet**을 엽니다.
2. 로봇 케이블이 연결된 어댑터를 선택합니다. USB 어댑터라면 제조사 이름이나 `USB Ethernet`으로 표시될 수 있습니다.
3. **IP 할당** 옆의 **편집**을 누릅니다.
4. **수동**을 선택하고 **IPv4**를 켭니다.
5. 위 표의 주소와 마스크 또는 프리픽스를 입력하고 **저장**합니다.

**Mac:**

1. Apple 메뉴 → **시스템 설정** → **네트워크**를 엽니다.
2. 로봇 케이블을 꽂은 **Ethernet** 또는 USB LAN 어댑터를 선택합니다.
3. **세부사항** → **TCP/IP**를 엽니다.
4. **IPv4 구성**을 **수동**으로 바꿉니다.
5. IP 주소와 서브넷 마스크를 입력하고 라우터는 비워 둡니다. **확인·적용**으로 저장합니다.
6. Docker나 터미널의 로컬 네트워크 접근 허용 창이 나오면 로봇 LAN에 접근할 수 있도록 허용합니다.

**DGX Spark:**

1. 화면 오른쪽 위의 네트워크 메뉴 → **설정** → **네트워크**를 엽니다.
2. 로봇 케이블을 꽂은 **유선 연결**의 톱니바퀴를 누릅니다.
3. **IPv4** 탭 → **수동**을 선택합니다.
4. 주소 `10.0.1.2`, 넷마스크 `255.255.255.0`을 입력합니다. 게이트웨이는 비워 둡니다.
5. **적용**을 누르고 해당 유선 연결을 껐다가 다시 켭니다.

<a id="trust"></a>
## 6. 처음 연결하는 로봇 등록하기

주소·계정·비밀번호를 저장하고 LAN 설정까지 마쳤으면 프로젝트 폴더의 명령 창에서 실행합니다.

```bash
docker compose run --rm x2 trust-host
```

로봇 주소와 `SHA256:...` 모양의 긴 문자열이 표시됩니다. 이 문자열을 **호스트 키 지문**이라고 하며, 접속한 로봇을 구별하는 값입니다. 장비 담당자가 제공한 지문과 대조해 맞으면 다음을 입력하고 Enter를 누릅니다.

```text
yes
```

`호스트 키를 등록했습니다.` 또는 `등록된 로봇 호스트 키`가 나오면 완료입니다. 등록 정보는 이 PC의 Docker 볼륨에 저장됩니다. 같은 PC와 같은 로봇으로 다시 사용할 때는 이 과정을 반복하지 않습니다.

이어서 다음 명령을 실행합니다.

```bash
docker compose run --rm x2 doctor
```

`Robot SDK:` 뒤에 버전 정보가 나오면 SSH 로그인과 SDK 확인이 된 것입니다. 이어서 LiDAR·PointCloud2 토픽 목록을 확인합니다. 접속·인증 오류가 나오면 [오류 해결](#errors)을 참고합니다.

실행 중인 대시보드는 다음 접속 시도에서 자동으로 연결됩니다.

<a id="operate"></a>
## 7. 대시보드에서 조종 시작하기

1. 같은 기기에서 [대시보드](http://127.0.0.1:8766)를 엽니다.
2. 상단의 **AGIBOT X2 연결됨** 표시와 RGB 영상·현재 모드·배터리 잔량을 확인합니다.
3. 화면 상단에서 **착석 자세 고정 → 일어서기 → 제어 활성화** 순서로 진행합니다.
4. 프리셋 버튼이나 이동 버튼을 사용합니다.

각 버튼에서 확인할 자세와 체크 항목은 [로봇 제어 준비](USER_GUIDE_KO.md#control-ready)를 따릅니다. 대시보드를 시작하거나 로봇을 연결한 직후에는 제어 준비를 진행한 뒤 움직임을 요청합니다.

<a id="ssh"></a>
## 8. SSH 접속을 직접 확인하기

접속에 문제가 있을 때 PC의 터미널에서 로봇 로그인을 직접 확인할 수 있습니다.

```bash
ssh agi@10.0.1.41
```

`agi`는 로그인 계정, `10.0.1.41`은 접속할 로봇 주소입니다. 주소나 계정이 변경된 로봇이라면 실제 값을 사용합니다.

1. 처음 접속하여 지문 확인 문구가 나오면 담당자가 제공한 로봇 지문과 대조합니다. 맞으면 `yes`를 입력합니다.
2. `password:`가 나오면 로봇의 SSH 비밀번호를 입력하고 Enter를 누릅니다. 입력 중 글자가 표시되지 않아도 정상입니다.
3. 로봇의 로그인 안내와 명령 프롬프트가 나타나면 접속에 성공한 것입니다.
4. 아래 명령으로 로봇 접속을 끝내고 PC 터미널로 돌아옵니다.

```bash
exit
```

Docker에서 사용하는 접속 키는 6번의 등록 명령으로 Docker 볼륨에 저장합니다. PC 터미널 접속을 확인했어도 처음 사용하는 Docker 볼륨에서는 6번을 진행합니다.

<a id="daily"></a>
## 9. 다음 날 시작·종료·업데이트하기

### 시작

1. Windows·Mac은 Docker Desktop을 실행합니다. DGX에서는 Docker 서비스 실행 상태를 확인합니다.
2. 로봇 전원을 켜고, 프로젝트를 실행할 기기에 LAN을 연결합니다.
3. 프로젝트 폴더의 명령 창에서 실행합니다.

```bash
docker compose up -d
```

4. 같은 기기에서 [대시보드](http://127.0.0.1:8766)를 열고 제어 준비를 진행합니다.

### 종료

1. [앉히고 전원 끄기](USER_GUIDE_KO.md#power-off)에 따라 로봇을 의자에 앉히고 댐핑·영토크로 전환합니다.
2. 프로젝트 폴더에서 대시보드를 종료합니다.

```bash
docker compose down
```

3. 사용설명서에 따라 배터리 전원을 끕니다.

### 업데이트

로봇 조작을 마친 뒤 프로젝트 폴더에서 실행합니다.

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

<a id="errors"></a>
## 10. 오류 문구별 해결 방법

| 보이는 문구·증상 | 할 일 |
|---|---|
| `git` 또는 `docker` 명령을 찾을 수 없음 | 해당 프로그램을 설치하고 명령 창을 새로 엽니다. |
| Docker의 `Server` 정보가 안 나옴 | Windows·Mac은 Docker Desktop을 실행하고 엔진 준비를 기다립니다. DGX는 Docker 서비스를 확인합니다. |
| `format`을 지원하지 않거나 `env_file` 설정 오류 | `docker compose version`을 확인하고 2.30 이상으로 업데이트합니다. |
| `no configuration file provided` | `compose.yaml`이 있는 `agibot-x2` 폴더로 들어와 실행합니다. |
| GitHub `Repository not found` | 저장소 접근 권한이 있는 계정으로 로그인합니다. |
| `X2 연결 대기: TimeoutError` | 로봇 없이 화면을 확인 중이면 계속 사용합니다. 로봇을 연결하려면 전원·LAN·PC 유선 주소를 확인합니다. |
| `Permission denied` 또는 `PermissionDenied`로 SSH 인증 실패 | `.env`의 계정·비밀번호를 확인하고 저장한 뒤 `docker compose up -d --force-recreate`를 실행합니다. |
| `Host key is not trusted` | 6번의 `trust-host`로 로봇 키를 등록합니다. |
| 기존 호스트 키와 다르다는 문구 | 연결한 로봇과 등록된 지문을 장비 담당자에게 확인합니다. |
| `.env`를 고쳤는데 그대로임 | 파일이 정확히 `.env`인지 확인하고 저장한 뒤 `docker compose up -d --force-recreate`를 실행합니다. |
| `8766` 포트 사용 중 | 기존 대시보드의 `docker compose down`을 실행합니다. Python 스크립트로 켠 이전 서버가 있으면 해당 폴더에서 `./stop.sh`로 종료합니다. |
| 페이지가 안 열림 | `docker compose ps`로 실행 상태를, `docker compose logs --tail 100 x2`로 오류를 확인합니다. 같은 기기에서 `http://127.0.0.1:8766`을 엽니다. |
| Docker는 `healthy`인데 영상이 없음 | `healthy`는 웹 서버 상태입니다. 로봇의 전원·LAN·로그인·키 등록을 확인하고 `doctor`를 실행합니다. |

DGX에서 `permission denied`와 `/var/run/docker.sock`이 함께 나오면 현재 사용자에게 Docker 사용 권한을 설정합니다.

```bash
sudo usermod -aG docker "$USER"
```

로그아웃한 뒤 다시 로그인하고 `docker version`을 확인합니다. Docker 그룹은 시스템 관리 권한을 주므로 장비를 관리하는 계정에서 진행합니다.

더 자세한 운용 오류는 [사용설명서의 문제 해결](USER_GUIDE_KO.md#troubleshooting)을 참고합니다.

## 참고

- [Windows Docker 설치](https://docs.docker.com/desktop/setup/install/windows-install/), [Mac Docker 설치](https://docs.docker.com/desktop/setup/install/mac-install/)
- [DGX Spark 소프트웨어](https://docs.nvidia.com/dgx/dgx-spark/software.html), [Ubuntu Docker 설치](https://docs.docker.com/engine/install/ubuntu/)
- [Compose 설정 파일 형식](https://docs.docker.com/reference/compose-file/services/#env_file)
- [Windows 네트워크 설정](https://support.microsoft.com/en-gb/windows/experience/connectivity-networking/essential-network-settings-and-tasks-in-windows), [Mac TCP/IP 설정](https://support.apple.com/en-bw/guide/mac-help/mh14129/mac)
