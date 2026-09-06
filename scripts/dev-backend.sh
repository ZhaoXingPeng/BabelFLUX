#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"

python_bin="python3"

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python_bin="python"
elif python3 -m venv .venv; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python_bin="python"
else
  echo "python venv is unavailable; falling back to current python environment"
fi

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -e ".[dev]"
"$python_bin" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
