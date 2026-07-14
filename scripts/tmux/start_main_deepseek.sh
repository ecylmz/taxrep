#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="taxrep-main-ds"
LOG="$PROJECT_DIR/results/logs/main-deepseek-v4-flash.log"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION" >&2
  exit 1
fi

tmux new-session -d -s "$SESSION" \
  "cd '$PROJECT_DIR' && uv run taxrep infer --config configs/main.yaml --model deepseek-v4-flash 2>&1 | tee -a '$LOG'"
