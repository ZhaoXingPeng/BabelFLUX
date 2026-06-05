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

if [ -d "$repo_root/frontend/node_modules" ]; then
  (cd "$repo_root/frontend" && npm run build)
else
  echo "frontend/node_modules not found; skip frontend build"
fi
