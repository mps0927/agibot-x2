# 검증 범위

2026-11-11 기준 패키징 검증이다. 실제 로봇 동작 결과와 실행기·계약 검증을 구분한다.

| 항목 | 결과 | 근거 |
|---|---|---|
| Python 본체 중복 설치 | 없음 | 기존 Python 3.13.3으로 `.venv` 생성, `system_python_installed=false` |
| 환경 재사용 | 통과 | 두 번째 `setup.sh`에서 `environment=reused`, pip 재실행 없음 |
| Bash 진입점 | 통과 | Git Bash `bash -n`, `preflight.sh --offline --test` 실행 |
| SDK·VLM·실행 제한·기록·프로세스 | 36개 테스트 통과 | `python -m unittest discover -s x2_motion` |
| 단일 서버/포트 관리 | 통과 | 백그라운드 시작→동일 PID 재사용→옵션 충돌 거부→상태→종료 테스트 |
| DGX Linux ARM64 의존성 | 통과 | CPython 3.12/aarch64용 모든 런타임 wheel 다운로드 확인 |
| 기존 X2 UI | 이식 | 준비 단계 상단 배치, 프리셋 상단, 지원 매핑만 표시, G1 공통 스타일 |
| Linux/macOS 실행 | 4개 조합 통과 | GitHub Actions: Ubuntu/macOS × Python 3.10/3.12의 설치·재사용·구문·오프라인 테스트 |
| DGX Spark 실제 연결 | 미실행 | 대상 기기에 배포하지 않음 |
| X2 SDK 실제 동작 재생 | 미실행 | 패키징 중 로봇 명령 전송 없음 |

저장 SDK 기준 `aimdk v1.0.0-ga424add`, 프리셋 17개 매핑, 서비스 스키마 27개 중 12개 실행/조회 연결이다. 실제 연결 시에는 기기의 SDK와 ROS 서비스 준비 상태를 다시 확인한다.

환경·키·기기 사진·기기 로그·SDK 설치본은 Git 대상에서 제외한다. VLM 기록은 실행한 기기의 로컬 `x2_motion/artifacts/`에 남는다.
