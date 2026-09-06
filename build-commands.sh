#!/usr/bin/env bash
# Package the thin slash-command entry points. Role protocols are rendered by
# duo.sh from skill/assets/ (or assets/ in an installation), never embedded here.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

for dest in claude-commands codex-prompts; do
  mkdir -p "$ROOT/dist/$dest"
  cp "$ROOT/commands/agent-duo.md" "$ROOT/dist/$dest/agent-duo.md"
  cp "$ROOT/commands/agent-duo-review.md" "$ROOT/dist/$dest/agent-duo-review.md"
done
echo "built: agent-duo.md and agent-duo-review.md in dist/claude-commands/ and dist/codex-prompts/"
