#!/usr/bin/env bash
# build.sh - assemble the installable Claude skill from canonical sources.
#
# Everything in dist/ is GENERATED. Never edit it: change references/, prompts/,
# bin/, or claude/SKILL.md and rebuild. This is the whole point of the monorepo,
# so that no file exists twice and nothing can drift.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/dist/agent-duo"

command -v zip >/dev/null || { echo "zip not found" >&2; exit 1; }

rm -rf "$ROOT/dist"
mkdir -p "$OUT/references" "$OUT/assets"

cp "$ROOT/claude/SKILL.md"  "$OUT/SKILL.md"
cp "$ROOT/references/"*.md  "$OUT/references/"
cp "$ROOT/prompts/"*.md     "$OUT/assets/"
cp "$ROOT/bin/duo.sh"       "$OUT/assets/duo.sh"
chmod +x "$OUT/assets/duo.sh"

# A .skill file is a zip of the skill folder.
(cd "$ROOT/dist" && zip -qr agent-duo.skill agent-duo)

# Slash commands for Claude Code and Codex.
"$ROOT/build-commands.sh" >/dev/null

echo "built: dist/agent-duo.skill"
echo "       dist/claude-commands/  (agent-duo, agent-duo-review)"
echo "       dist/codex-prompts/"
echo "install: upload it in Claude, or  cp -r dist/agent-duo ~/.claude/skills/"
