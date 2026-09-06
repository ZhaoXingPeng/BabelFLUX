#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$repo_root/backend/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$repo_root/backend/.venv/bin/activate"
fi

python_cmd="${PYTHON:-python3}"
if ! command -v "$python_cmd" >/dev/null 2>&1; then
  echo "${python_cmd} not found; install Python 3.11+ before running checks" >&2
  exit 1
fi

(cd "$repo_root/backend" && "$python_cmd" -m pytest -q)

if ! command -v ruff >/dev/null 2>&1; then
  echo "ruff not found; install backend development dependencies before running checks" >&2
  exit 1
fi
(cd "$repo_root/backend" && ruff check .)

if [ -f "$repo_root/frontend/package.json" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found; cannot build frontend" >&2
    exit 1
  fi

  if [ -f "$repo_root/frontend/package-lock.json" ]; then
    (cd "$repo_root/frontend" && npm ci)
  fi

  (cd "$repo_root/frontend" && npm run test)
  (cd "$repo_root/frontend" && npm run build)
fi

if [ -f "$repo_root/desktop/package.json" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found; cannot build desktop" >&2
    exit 1
  fi

  if [ -f "$repo_root/desktop/package-lock.json" ]; then
    (cd "$repo_root/desktop" && npm ci)
  fi

  (cd "$repo_root/desktop" && npm run build)
fi
