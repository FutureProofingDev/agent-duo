#!/usr/bin/env bash
# Assemble slash-command files for Claude Code and Codex from the canonical
# planner/reviewer templates. Generated output goes under dist/; never edit it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Claude Code: project command at .claude/commands/agent-duo.md
mkdir -p "$ROOT/dist/claude-commands"
awk -v body="$ROOT/templates/planner-body-orca.md" '
  /<!-- PLANNER_BODY -->/ { while ((getline line < body) > 0) print line; next }
  { print }
' "$ROOT/commands/agent-duo.md" > "$ROOT/dist/claude-commands/agent-duo.md"

# Codex: prompt file. Same content, Codex reads $ARGUMENTS the same way; the
# only real difference is install location, so we emit an identically-filled file.
mkdir -p "$ROOT/dist/codex-prompts"
cp "$ROOT/dist/claude-commands/agent-duo.md" "$ROOT/dist/codex-prompts/agent-duo.md"

echo "built:"
echo "  dist/claude-commands/agent-duo.md  -> copy to <repo>/.claude/commands/ or ~/.claude/commands/"
echo "  dist/codex-prompts/agent-duo.md    -> copy to ~/.codex/prompts/"

# Reviewer command (fallback / manual start)
for dest in claude-commands codex-prompts; do
  awk -v body="$ROOT/templates/reviewer-body-orca.md" '
    /<!-- REVIEWER_BODY -->/ { while ((getline line < body) > 0) print line; next }
    { print }
  ' "$ROOT/commands/agent-duo-review.md" > "$ROOT/dist/$dest/agent-duo-review.md"
done
echo "  + agent-duo-review.md in both"
