#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec "$root/run.sh" --field --background --allow-control --allow-posture-actions "$@"
