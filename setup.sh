#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
die(){ printf 'setup: %s\n' "$*" >&2; exit 1; }
if [[ -x "$root/.venv/bin/python" ]]; then py="$root/.venv/bin/python"
elif [[ -x "$root/.venv/Scripts/python.exe" ]]; then py="$root/.venv/Scripts/python.exe"
else
  py="${PYTHON_BIN:-}"
  if [[ -z "$py" ]]; then
    for candidate in python3 python; do
      if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys;sys.exit(sys.version_info<(3,10))' 2>/dev/null; then py="$candidate"; break; fi
    done
  fi
  [[ -n "$py" ]] || die 'Python 3.10+ is required. Install it separately or set PYTHON_BIN. No system Python will be installed.'
  "$py" -c 'import sys;assert sys.version_info >= (3,10), "Python 3.10+ required"'
  "$py" -m venv "$root/.venv" || die 'venv creation failed. On Ubuntu, install the python3-venv package and retry.'
  if [[ -x "$root/.venv/bin/python" ]]; then py="$root/.venv/bin/python"; else py="$root/.venv/Scripts/python.exe"; fi
fi
"$py" "$root/scripts/setup_dependencies.py"
