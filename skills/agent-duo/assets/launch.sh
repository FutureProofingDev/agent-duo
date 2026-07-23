#!/usr/bin/env bash
# launch.sh - start the agent duo for run {{RUN_ID}} in Orca ADE
#
# Requires: Orca CLI registered under Settings -> Experimental -> CLI, and jq.
#
# JQ PATHS: verified against real Orca output. Responses are wrapped in .result
# and worktreeId is a compound "<uuid>::<absolute path>" string, not a bare UUID,
# so terminals are selected by title and paths come from .worktreePath.

set -euo pipefail

RUN_ID="{{RUN_ID}}"
WT_NAME="duo-${RUN_ID}"
PLANNER_AGENT="{{PLANNER_AGENT}}"     # claude | codex
REVIEWER_AGENT="{{REVIEWER_AGENT}}"   # codex | claude

orca status --json >/dev/null || { echo "Orca runtime not reachable. Run: orca open --json"; exit 1; }

# ONE worktree for the whole run. Both agents share this filesystem on purpose:
# the file handshake only works if they see the same directory. Do NOT give the
# reviewer its own worktree.
# Create the worktree. Both agents live here: separate worktrees are separate
# directories, which silently breaks the artifact handshake.
orca worktree create --name "${WT_NAME}" --agent "${REVIEWER_AGENT}" --json >/dev/null

# worktreePath is the absolute path on disk. The run folder MUST live inside it,
# so derive it here rather than assuming a relative path from the main checkout.
WT_PATH=$(orca terminal list --worktree active --json \
          | jq -r '.result.terminals[0].worktreePath')
RUN_DIR="${WT_PATH}/{{RUNS_ROOT}}${RUN_ID}"
mkdir -p "$RUN_DIR"

# Reviewer occupies the first terminal of the new worktree.
# Select by title, not index: a worktree also contains plain shells such as
# "Setup", and list order is not guaranteed.
REV=$(orca terminal list --worktree active --json \
      | jq -r --arg n "$WT_NAME" '.result.terminals[] | select(.title | test($n)) | .handle' | head -1)
orca terminal wait --terminal "$REV" --for tui-idle --timeout-ms 120000 --json >/dev/null

# Reviewer goes up FIRST so it is already watching before any artifact lands.
# Starting the planner first lets spec-v1.md appear during reviewer boot, and
# nobody picks it up.
orca terminal send --terminal "$REV" --text "$(cat "${RUN_DIR}/reviewer.txt")" --enter --json >/dev/null

# Planner in a second terminal, same worktree.
PLN=$(orca terminal split --terminal "$REV" --direction horizontal --command "${PLANNER_AGENT}" --json \
      | jq -r '.result.terminal.handle')
orca terminal wait --terminal "$PLN" --for tui-idle --timeout-ms 120000 --json >/dev/null
orca terminal send --terminal "$PLN" --text "$(cat "${RUN_DIR}/planner.txt")" --enter --json >/dev/null

echo "Duo running in worktree ${WT_PATH}"
echo "  reviewer terminal: ${REV}"
echo "  planner terminal:  ${PLN}"
echo "  watch:             tail -f ${RUN_DIR}/log.md"
