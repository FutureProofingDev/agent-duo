#!/usr/bin/env bash
# launch.sh - start the agent duo for run {{RUN_ID}} in Orca ADE
#
# Requires: Orca CLI registered under Settings -> Experimental -> CLI, and jq.
#
# NOTE ON JQ PATHS: the Orca docs show command shapes but not response bodies.
# The jq selectors below are the expected shape. Run each command once with
# --json, check the actual field names, and adjust if they differ. Do this
# during your dry run, not during a real run.

set -euo pipefail

RUN_ID="{{RUN_ID}}"
RUN_DIR="{{RUNS_ROOT}}{{RUN_ID}}"
PLANNER_AGENT="{{PLANNER_AGENT}}"     # claude | codex
REVIEWER_AGENT="{{REVIEWER_AGENT}}"   # codex | claude

orca status --json >/dev/null || { echo "Orca runtime not reachable. Run: orca open --json"; exit 1; }

# ONE worktree for the whole run. Both agents share this filesystem on purpose:
# the file handshake only works if they see the same directory. Do NOT give the
# reviewer its own worktree.
WT=$(orca worktree create --name "duo-${RUN_ID}" --agent "${REVIEWER_AGENT}" --json \
     | jq -r '.worktree.id')

# Reviewer occupies the first terminal of the new worktree.
REV=$(orca terminal list --worktree "id:${WT}" --json | jq -r '.terminals[0].handle')
orca terminal wait --terminal "$REV" --for tui-idle --timeout-ms 120000 --json >/dev/null

# Reviewer goes up FIRST so it is already watching before any artifact lands.
# Starting the planner first lets spec-v1.md appear during reviewer boot, and
# nobody picks it up.
orca terminal send --terminal "$REV" --text "$(cat "${RUN_DIR}/reviewer.txt")" --enter --json >/dev/null

# Planner in a second terminal, same worktree.
PLN=$(orca terminal split --terminal "$REV" --direction horizontal --command "${PLANNER_AGENT}" --json \
      | jq -r '.terminal.handle')
orca terminal wait --terminal "$PLN" --for tui-idle --timeout-ms 120000 --json >/dev/null
orca terminal send --terminal "$PLN" --text "$(cat "${RUN_DIR}/planner.txt")" --enter --json >/dev/null

echo "Duo running in worktree ${WT}"
echo "  reviewer terminal: ${REV}"
echo "  planner terminal:  ${PLN}"
echo "  watch:             tail -f ${RUN_DIR}/log.md"
