#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="taxrep-analysis"
LOG="$PROJECT_DIR/results/logs/analysis.log"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION" >&2
  exit 1
fi

tmux new-session -d -s "$SESSION" \
  "cd '$PROJECT_DIR' && uv run taxrep parse && uv run taxrep evaluate && uv run taxrep held-out && uv run taxrep statistics && uv run taxrep targeted analyze && uv run taxrep targeted audit && uv run taxrep figures 2>&1 | tee -a '$LOG'"
