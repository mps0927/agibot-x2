#!/usr/bin/env bash
# Sourced by repository entry points; .venv is always local to this checkout.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ -x "$root/.venv/bin/python" ]]; then py="$root/.venv/bin/python"
elif [[ -x "$root/.venv/Scripts/python.exe" ]]; then py="$root/.venv/Scripts/python.exe"
else "$root/setup.sh"; source "$root/scripts/python.sh"; fi
