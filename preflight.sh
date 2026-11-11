#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
"$root/setup.sh"
source "$root/scripts/python.sh"
exec "$py" "$root/x2_motion/preflight.py" "$@"
