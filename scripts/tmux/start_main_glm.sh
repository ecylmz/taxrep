#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="taxrep-main-glm"
LOG="$PROJECT_DIR/results/logs/main-glm-5.2.log"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION" >&2
  exit 1
fi

tmux new-session -d -s "$SESSION" \
  "cd '$PROJECT_DIR' && uv run taxrep infer --config configs/main.yaml --model glm-5.2 2>&1 | tee -a '$LOG'"
