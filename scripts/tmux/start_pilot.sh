#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="taxrep-pilot"
LOG="$PROJECT_DIR/results/logs/pilot.log"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION" >&2
  exit 1
fi

tmux new-session -d -s "$SESSION" \
  "cd '$PROJECT_DIR' && uv run taxrep pilot --config configs/pilot.yaml 2>&1 | tee -a '$LOG'"
