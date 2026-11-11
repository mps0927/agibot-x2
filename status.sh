#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$root/scripts/python.sh"
exec "$py" "$root/x2_motion/dashboard_service.py" status
