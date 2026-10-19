#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -x .venv/bin/python ]]; then
    python_executable=.venv/bin/python
else
    python_executable=python3
fi
exec "$python_executable" -m scripts.verify_acceptance "$@"
