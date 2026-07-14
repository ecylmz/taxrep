#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="taxrep-t3-repeat-recovery"
LOG_DIR="$PROJECT_DIR/results/logs/targeted_t3_repeat_recovery"
LOG="$LOG_DIR/inference.log"
CONFIG="experiment/targeted_t3_repeat_recovery.yaml"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION" >&2
  exit 1
fi

if compgen -G "$PROJECT_DIR/results/run_manifests/targeted-t3-repeat-*.lock" >/dev/null; then
  echo "targeted extension run lock already exists" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
tmux new-session -d -s "$SESSION" \
  "cd '$PROJECT_DIR' && uv run taxrep infer --config '$CONFIG' 2>&1 | tee -a '$LOG'"

echo "started $SESSION"
echo "log: $LOG"
echo "monitor: tmux attach -t $SESSION"
