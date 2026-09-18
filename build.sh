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
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }

# Validate inputs and explicit package-local references before replacing dist.
# Plain prose and shell expressions are not interpreted as file references.
python3 - "$ROOT" <<'PY'
from pathlib import Path
import json
import os
import posixpath
import re
import subprocess
import sys

root = Path(sys.argv[1])
skill = root / "skill"

def fail(message):
    raise SystemExit(message)

for relative in (
    "LICENSE", "skill/SKILL.md", "bin/duo.sh", "bin/duo-state.py",
    "commands/agent-duo.md", "commands/agent-duo-review.md",
):
    if not (root / relative).is_file():
        fail(relative + " missing")
for relative in ("bin/duo.sh", "bin/duo-state.py"):
    if not os.access(root / relative, os.X_OK):
        fail(relative + " must be executable")

protocol_version = 2
try:
    controller = subprocess.run(
        [sys.executable, str(root / "bin/duo-state.py"), "protocol"],
        text=True, capture_output=True, check=True, timeout=10,
    )
    protocol = json.loads(controller.stdout)
except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
    fail("bin/duo-state.py: cannot read controller protocol: " + str(error))
if not isinstance(protocol, dict) or protocol.get("protocol_version") != protocol_version:
    fail("bin/duo-state.py: controller must support protocol " + str(protocol_version))

for role in ("planner", "reviewer"):
    for suffix, transport in (("", "file"), ("-orca", "orchestration")):
        relative = "skill/assets/" + role + suffix + ".md"
        template = root / relative
        if not template.is_file():
            fail(relative + " missing")
        text = template.read_text()
        marker = (
            "<!-- agent-duo: protocol=" + str(protocol_version)
            + " role=" + role + " transport=" + transport + " -->"
        )
        lines = text.splitlines()
        markers = re.findall(r"<!--\s*agent-duo:.*?-->", text, re.S)
        if len(lines) < 2 or lines[1] != marker or markers != [marker]:
            fail(relative + ": needs one matching protocol marker on line 2: " + marker)
        if "{{CONTROLLER}}" not in text:
            fail(relative + ": missing {{CONTROLLER}} placeholder")

metadata = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", (skill / "SKILL.md").read_text(), re.S)
if not metadata:
    fail("SKILL.md needs YAML frontmatter")
for field in ("name", "description"):
    if not re.search(r"^" + field + r":[ \t]*\S", metadata[1], re.M):
        fail("SKILL.md needs a " + field + ": field")

packaged = {path.relative_to(skill).as_posix() for path in skill.rglob("*") if path.is_file()}
packaged.update(("assets/duo.sh", "assets/duo-state.py"))
for document in skill.rglob("*.md"):
    text = document.read_text()
    references = set()
    # An inline code span naming an assets/ or references/ file is relative to
    # the skill root. Only literal filenames count; ${...} and globs do not.
    for target in re.findall(r"`((?:assets|references)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`", text):
        references.add(target)
    # Markdown links are relative to their containing document.
    for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", text):
        target = target.strip("<>")
        if target.startswith(("#", "/")) or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if target:
            references.add(posixpath.normpath(str(document.parent.relative_to(skill) / target)))
    for target in sorted(references):
        if target not in packaged:
            fail(str(document.relative_to(root)) + ": missing package reference " + target)
PY

rm -rf "$ROOT/dist"
mkdir -p "$ROOT/dist"

# --- packaged skill (Claude .skill = zip of the skill folder as agent-duo/) ---
cp -r "$ROOT/skill" "$ROOT/dist/agent-duo"
install -m 644 "$ROOT/LICENSE" "$ROOT/dist/agent-duo/LICENSE"
install -m 755 "$ROOT/bin/duo.sh" "$ROOT/dist/agent-duo/assets/duo.sh"
install -m 755 "$ROOT/bin/duo-state.py" "$ROOT/dist/agent-duo/assets/duo-state.py"
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
