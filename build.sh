#!/usr/bin/env bash
# build.sh - validate the skill and emit installable artifacts.
#
# skill/ is the single source of truth and is itself the portable SKILL.md skill
# (works in Claude Code, Codex, Cursor, and any SKILL.md-aware agent). This script
# packages it as a .skill zip and assembles the optional Orca slash commands.
# Everything under dist/ is GENERATED; never edit it.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
command -v zip >/dev/null || { echo "zip not found" >&2; exit 1; }

# --- validate ---
test -f "$ROOT/skill/SKILL.md" || { echo "skill/SKILL.md missing" >&2; exit 1; }
grep -q '^name:' "$ROOT/skill/SKILL.md" || { echo "SKILL.md needs a name: field" >&2; exit 1; }
grep -q '^description:' "$ROOT/skill/SKILL.md" || { echo "SKILL.md needs a description: field" >&2; exit 1; }
if grep -q '—' "$ROOT/skill/SKILL.md"; then echo "WARN: em dash in SKILL.md (AI tell)"; fi

rm -rf "$ROOT/dist"; mkdir -p "$ROOT/dist"

# --- packaged skill (Claude .skill = zip of the skill folder as agent-duo/) ---
cp -r "$ROOT/skill" "$ROOT/dist/agent-duo"
(cd "$ROOT/dist" && zip -qr agent-duo.skill agent-duo)

# --- Orca slash commands (optional, Claude Code + Codex) ---
"$ROOT/build-commands.sh" >/dev/null

cat <<MSG
built:
  dist/agent-duo.skill          upload in Claude, or unzip into a skills dir
  dist/agent-duo/               the skill folder (copy into ~/.claude/skills/,
                                ~/.agents/skills/, or .agents/skills/ in a repo)
  dist/claude-commands/*.md     -> <repo>/.claude/commands/ or ~/.claude/commands/
  dist/codex-prompts/*.md       -> ~/.codex/prompts/  (deprecated; skill preferred)
MSG
