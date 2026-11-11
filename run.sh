#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
mode="${1:---offline}"
case "$mode" in
  --offline|--field) shift || true ;;
  --help|-h) printf 'Usage: ./run.sh [--offline|--field] [--background] [dashboard options]\nX2 always defaults to port 8766. Use ./start_field.sh for the complete field controls.\n'; exit 0 ;;
  *) printf 'First argument must be --offline or --field.\n' >&2; exit 2 ;;
esac
"$root/setup.sh"
source "$root/scripts/python.sh"
"$py" "$root/x2_motion/preflight.py" "$mode" "$@"
exec "$py" "$root/x2_motion/dashboard_service.py" launch "$mode" "$@"
