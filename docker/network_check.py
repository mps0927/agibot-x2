"""Check the configured robot TCP path without authentication or robot commands."""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'x2_motion'))
from configuration import load_config, ssh_options


def check(host, port=22):
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except OSError:
        print(f'연결 실패: {host}:{port}', flush=True)
        print('로봇 전원과 LAN 케이블을 확인하세요. 처음 연결하는 PC는 유선 주소 설정을 확인하세요.')
        print('설정 방법: docs/FIRST_START_KO.md의 5번 항목')
        return 1
    print(f'접속 가능: {host}:{port} — 현재 네트워크 경로로 접속할 수 있습니다.', flush=True)
    print('다음 단계: .env의 로그인 정보 확인 → 처음 한 번 trust-host → 대시보드 자동 연결')
    print('이 검사는 TCP 연결만 확인합니다. 로봇 로그인과 SDK 확인은 doctor를 사용하세요.')
    return 0


def main():
    load_config()
    return check(ssh_options()['host'])


if __name__ == '__main__':
    sys.exit(main())
