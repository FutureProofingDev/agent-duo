#!/usr/bin/env bash
# duo - start an agent duo run in Orca ADE with one command.
#
#   duo --task "hide signup in login page" --run-id b
#   duo --issue https://github.com/org/repo/issues/612 --run-id 612-a
#   duo --task "..." --run-id c --new-worktree
#
# Reuses the current worktree's terminals by default. Prompt generation is pure
# templating, so no LLM call is involved and runs are byte-for-byte reproducible.

set -euo pipefail

# ---------------------------------------------------------------- defaults ---
DUO_HOME="${DUO_HOME:-$HOME/src/agent-duo}"   # either clone, either layout
MODE="orchestration"          # orchestration | file
PLANNER_AGENT="claude"
REVIEWER_AGENT="codex"
GATE="${DUO_GATE:-pnpm test:run && pnpm lint}"
RUNS_ROOT="docs/agent-duo/runs"
BASE_BRANCH="develop"
NEW_WORKTREE=0
RESET_BRANCH=1
TASK="" ; ISSUE="" ; RUN_ID="" ; REV="" ; PLN=""

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)          TASK="$2"; shift 2 ;;
    --issue)         ISSUE="$2"; shift 2 ;;
    --run-id)        RUN_ID="$2"; shift 2 ;;
    --gate)          GATE="$2"; shift 2 ;;
    --planner)       PLANNER_AGENT="$2"; shift 2 ;;
    --reviewer)      REVIEWER_AGENT="$2"; shift 2 ;;
    --mode)          MODE="$2"; shift 2 ;;
    --base)          BASE_BRANCH="$2"; shift 2 ;;
    --new-worktree)  NEW_WORKTREE=1; shift ;;
    --no-reset)      RESET_BRANCH=0; shift ;;
    --reviewer-terminal) REV="$2"; shift 2 ;;
    --planner-terminal)  PLN="$2"; shift 2 ;;
    -h|--help)       usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

[[ -n "$RUN_ID" ]] || { echo "--run-id is required" >&2; exit 1; }
[[ -n "$TASK" || -n "$ISSUE" ]] || { echo "--task or --issue is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }
orca status --json >/dev/null 2>&1 || { echo "Orca unreachable. Run: orca open --json" >&2; exit 1; }

TPL_SUFFIX=""; [[ "$MODE" == "orchestration" ]] && TPL_SUFFIX="-orca"

# Canonical location is prompts/ in the repo root. The other candidates let the
# script also run from a built/installed skill folder, where templates land in
# assets/.
resolve_tpl() {
  local role="$1" c
  for c in \
    "$DUO_HOME/prompts/${role}${TPL_SUFFIX}.md" \
    "$DUO_HOME/assets/${role}${TPL_SUFFIX}.md" \
    "$DUO_HOME/dist/agent-duo/assets/${role}${TPL_SUFFIX}.md" ; do
    [[ -f "$c" ]] && { echo "$c"; return 0; }
  done
  return 1
}
PLANNER_TPL=$(resolve_tpl planner)  || { echo "planner template not found under DUO_HOME=$DUO_HOME" >&2; exit 1; }
REVIEWER_TPL=$(resolve_tpl reviewer) || { echo "reviewer template not found under DUO_HOME=$DUO_HOME" >&2; exit 1; }

# ------------------------------------------------------- terminals & paths ---
if [[ $NEW_WORKTREE -eq 1 ]]; then
  orca worktree create --name "duo-${RUN_ID}" --agent "$REVIEWER_AGENT" --json >/dev/null
  sleep 2
fi

TERMS=$(orca terminal list --worktree active --json)
WT_PATH=$(jq -r '.result.terminals[0].worktreePath' <<<"$TERMS")

# Handles are runtime-scoped, so resolve them fresh unless explicitly pinned.
if [[ -z "$REV" ]]; then
  REV=$(jq -r --arg a "$REVIEWER_AGENT" \
        '.result.terminals[] | select(.preview // "" | ascii_downcase | contains($a)) | .handle' \
        <<<"$TERMS" | head -1)
fi
if [[ -z "$PLN" ]]; then
  PLN=$(jq -r --arg r "$REV" '.result.terminals[] | select(.handle != $r) | .handle' \
        <<<"$TERMS" | head -1)
fi
[[ -n "$REV" && -n "$PLN" && "$REV" != "$PLN" ]] || {
  echo "Could not resolve two distinct terminals. Pass --reviewer-terminal / --planner-terminal." >&2
  jq -r '.result.terminals[] | "  \(.handle)  \(.title)"' <<<"$TERMS" >&2
  exit 1
}

RUN_DIR="${WT_PATH}/${RUNS_ROOT}/${RUN_ID}"
[[ -e "$RUN_DIR" ]] && { echo "run folder already exists: $RUN_DIR" >&2; exit 1; }
mkdir -p "$RUN_DIR"

# A worktree carries the branch it was created on. Without a reset, a new run
# stacks on top of the previous run's feature branch and its PR inherits it.
if [[ $RESET_BRANCH -eq 1 ]]; then
  git -C "$WT_PATH" checkout "$BASE_BRANCH" --quiet 2>/dev/null
  git -C "$WT_PATH" pull --quiet >/dev/null 2>&1 || true
fi

# -------------------------------------------------------------- templating ---
if [[ -n "$ISSUE" ]]; then
  ISSUE_NUMBER="${ISSUE##*/}"
  WORK_ITEM_BLOCK="Your work item is GitHub issue #${ISSUE_NUMBER}: ${ISSUE}
Read it fully before speccing. It is the source of truth."
  SOURCE_BLOCK="The work item is GitHub issue #${ISSUE_NUMBER}: ${ISSUE}. Read it before your first review."
  RUBRIC_1="Does the plan address every acceptance criterion of issue #${ISSUE_NUMBER}?"
else
  ISSUE_NUMBER="n/a"
  WORK_ITEM_BLOCK="Your work item is the following brief. As your FIRST action, write it
verbatim into brief.md (type: brief, round: 0) in the run folder; it is the
source of truth.
--- BRIEF START ---
${TASK}
--- BRIEF END ---"
  SOURCE_BLOCK="The work item is brief.md in the run folder, written by the planner. Read it before your first review."
  RUBRIC_1="Are the derived acceptance criteria a faithful, complete reading of brief.md, and does the plan address all of them?"
fi

fill() {  # fill <template> <output>
  RUN_ID="$RUN_ID" RUNS_ROOT="${WT_PATH}/${RUNS_ROOT}/" GATE="$GATE" \
  WORK_ITEM_BLOCK="$WORK_ITEM_BLOCK" SOURCE_BLOCK="$SOURCE_BLOCK" \
  RUBRIC_1="$RUBRIC_1" ISSUE_NUMBER="$ISSUE_NUMBER" ISSUE="$ISSUE" \
  TASK="$TASK" PLANNER_AGENT="$PLANNER_AGENT" REVIEWER_AGENT="$REVIEWER_AGENT" \
  python3 - "$1" "$2" <<'PY'
import os, re, sys
src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()
# Drop the human-facing variant comments; the script supplies the real block.
t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
m = {
  '{{RUN_ID}}': os.environ['RUN_ID'],
  '{{RUNS_ROOT}}': os.environ['RUNS_ROOT'],
  '{{GATE_COMMANDS}}': os.environ['GATE'],
  '{{WORK_ITEM_BLOCK}}': os.environ['WORK_ITEM_BLOCK'],
  '{{SOURCE_OF_TRUTH_BLOCK}}': os.environ['SOURCE_BLOCK'],
  '{{RUBRIC_ITEM_1}}': os.environ['RUBRIC_1'],
  '{{ISSUE_NUMBER}}': os.environ['ISSUE_NUMBER'],
  '{{ISSUE_URL}}': os.environ['ISSUE'],
  '{{WORK_ITEM_TEXT}}': os.environ['TASK'],
  '{{PLANNER_AGENT}}': os.environ['PLANNER_AGENT'],
  '{{REVIEWER_AGENT}}': os.environ['REVIEWER_AGENT'],
}
for k, v in m.items():
    t = t.replace(k, v)
t = re.sub(r'\n{3,}', '\n\n', t)
open(dst, 'w').write(t)
left = set(re.findall(r'\{\{[A-Z_]+\}\}', t)) - {'{{PLANNER_HANDLE}}', '{{REVIEWER_HANDLE}}'}
if left:
    sys.exit("unfilled placeholders in %s: %s" % (dst, ', '.join(sorted(left))))
PY
}

fill "$PLANNER_TPL"  "$RUN_DIR/planner.txt"
fill "$REVIEWER_TPL" "$RUN_DIR/reviewer.txt"

# Handles only exist once the terminals do, so they are substituted last.
sed "s|{{PLANNER_HANDLE}}|${PLN}|g"  "$RUN_DIR/reviewer.txt" > "$RUN_DIR/reviewer.resolved.txt"
sed "s|{{REVIEWER_HANDLE}}|${REV}|g" "$RUN_DIR/planner.txt"  > "$RUN_DIR/planner.resolved.txt"

# ------------------------------------------------------------------ launch ---
# Reviewer first: the coordinator cannot dispatch to an agent that is not up.
orca terminal send --terminal "$REV" --text "$(cat "$RUN_DIR/reviewer.resolved.txt")" --enter --json >/dev/null
orca terminal wait --terminal "$REV" --for tui-idle --timeout-ms 180000 --json >/dev/null
orca terminal send --terminal "$PLN" --text "$(cat "$RUN_DIR/planner.resolved.txt")" --enter --json >/dev/null

cat <<EOF

duo run '${RUN_ID}' started (${MODE} mode)
  worktree : ${WT_PATH}
  branch   : $(git -C "$WT_PATH" rev-parse --abbrev-ref HEAD)
  planner  : ${PLANNER_AGENT}  ${PLN}
  reviewer : ${REVIEWER_AGENT}  ${REV}
  run dir  : ${RUN_DIR}

watch:
  orca orchestration task-list --json | jq '.result.tasks[] | select(.task_title | contains("run ${RUN_ID}"))'
  tail -f ${RUN_DIR}/log-planner.md ${RUN_DIR}/log-reviewer.md
EOF
