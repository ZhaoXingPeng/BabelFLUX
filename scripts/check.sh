#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$repo_root/backend/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$repo_root/backend/.venv/bin/activate"
fi

if command -v pytest >/dev/null 2>&1; then
  (cd "$repo_root/backend" && pytest)
else
  echo "pytest not found; skip backend tests"
fi

if [ -f "$repo_root/frontend/package.json" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found; cannot build frontend" >&2
    exit 1
  fi

  if [ -f "$repo_root/frontend/package-lock.json" ]; then
    (cd "$repo_root/frontend" && npm ci)
  fi

  (cd "$repo_root/frontend" && npm run build)
fi
