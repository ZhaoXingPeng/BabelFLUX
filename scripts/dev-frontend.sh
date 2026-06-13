#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../frontend"

if command -v pnpm >/dev/null 2>&1; then
  pnpm install
  pnpm dev
else
  npm install
  npm run dev
fi
