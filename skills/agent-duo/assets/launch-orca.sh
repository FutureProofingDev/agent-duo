#!/usr/bin/env bash
# launch-orca.sh - start the agent duo in ORCHESTRATION mode for run {{RUN_ID}}
#
# Requires:
#   - Orca CLI registered:      Settings -> Experimental -> CLI
#   - Orchestration enabled:    Settings -> Experimental -> Orchestration
#   - jq
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

# ONE worktree for the run. Orchestration handles signaling, but the reviewer
# still has to READ spec files and code, so the shared filesystem stays.
# Create the worktree. Both agents live here: separate worktrees are separate
# directories, which silently breaks the artifact handshake.
orca worktree create --name "${WT_NAME}" --agent "${REVIEWER_AGENT}" --json >/dev/null

# worktreePath is the absolute path on disk. The run folder MUST live inside it,
# so derive it here rather than assuming a relative path from the main checkout.
WT_PATH=$(orca terminal list --worktree active --json \
          | jq -r '.result.terminals[0].worktreePath')
RUN_DIR="${WT_PATH}/{{RUNS_ROOT}}${RUN_ID}"
mkdir -p "$RUN_DIR"

# Select by title, not index: a worktree also contains plain shells such as
# "Setup", and list order is not guaranteed.
REV=$(orca terminal list --worktree active --json \
      | jq -r --arg n "$WT_NAME" '.result.terminals[] | select(.title | test($n)) | .handle' | head -1)
orca terminal wait --terminal "$REV" --for tui-idle --timeout-ms 120000 --json >/dev/null

# Planner terminal in the SAME worktree.
PLN=$(orca terminal split --terminal "$REV" --direction horizontal --command "${PLANNER_AGENT}" --json \
      | jq -r '.result.terminal.handle')
orca terminal wait --terminal "$PLN" --for tui-idle --timeout-ms 120000 --json >/dev/null

# Each agent must address the other, so handles are resolved here and injected
# into the prompts. This is the one thing that cannot be templated ahead of time:
# handles are runtime-scoped and only exist once the terminals do.
sed -e "s|{{REVIEWER_HANDLE}}|${REV}|g" "${RUN_DIR}/planner.txt"  > "${RUN_DIR}/planner.resolved.txt"
sed -e "s|{{PLANNER_HANDLE}}|${PLN}|g"  "${RUN_DIR}/reviewer.txt" > "${RUN_DIR}/reviewer.resolved.txt"

# Reviewer first: it must be idle and listening before the coordinator dispatches.
orca terminal send --terminal "$REV" --text "$(cat "${RUN_DIR}/reviewer.resolved.txt")" --enter --json >/dev/null
orca terminal wait --terminal "$REV" --for tui-idle --timeout-ms 120000 --json >/dev/null

orca terminal send --terminal "$PLN" --text "$(cat "${RUN_DIR}/planner.resolved.txt")" --enter --json >/dev/null

echo "Duo running in orchestration mode, worktree ${WT_PATH}"
echo "  coordinator (planner): ${PLN}"
echo "  worker (reviewer):     ${REV}"
echo
echo "Watch:"
echo "  orca orchestration task-list --json"
echo "  orca orchestration inbox --limit 20 --json"
echo "  tail -f ${RUN_DIR}/log.md"
echo
echo "If Orca restarts mid-run, handles go stale. Reacquire with:"
echo "  orca terminal list --worktree active --json"
