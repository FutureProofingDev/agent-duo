#!/usr/bin/env bash
# launch-orca.sh - start the agent duo in ORCHESTRATION mode for run {{RUN_ID}}
#
# Requires:
#   - Orca CLI registered:      Settings -> Experimental -> CLI
#   - Orchestration enabled:    Settings -> Experimental -> Orchestration
#   - jq
#
# NOTE ON JQ PATHS: the Orca docs specify command shapes but not response bodies.
# The selectors below are the expected shape. Run each command once with --json,
# confirm the real field names, and adjust. Do this during the dry run.

set -euo pipefail

RUN_ID="{{RUN_ID}}"
RUN_DIR="{{RUNS_ROOT}}{{RUN_ID}}"
PLANNER_AGENT="{{PLANNER_AGENT}}"     # claude | codex
REVIEWER_AGENT="{{REVIEWER_AGENT}}"   # codex | claude

orca status --json >/dev/null || { echo "Orca runtime not reachable. Run: orca open --json"; exit 1; }

# ONE worktree for the run. Orchestration handles signaling, but the reviewer
# still has to READ spec files and code, so the shared filesystem stays.
WT=$(orca worktree create --name "duo-${RUN_ID}" --agent "${REVIEWER_AGENT}" --json \
     | jq -r '.worktree.id')

REV=$(orca terminal list --worktree "id:${WT}" --json | jq -r '.terminals[0].handle')
orca terminal wait --terminal "$REV" --for tui-idle --timeout-ms 120000 --json >/dev/null

# Planner terminal in the SAME worktree.
PLN=$(orca terminal split --terminal "$REV" --direction horizontal --command "${PLANNER_AGENT}" --json \
      | jq -r '.terminal.handle')
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

echo "Duo running in orchestration mode, worktree ${WT}"
echo "  coordinator (planner): ${PLN}"
echo "  worker (reviewer):     ${REV}"
echo
echo "Watch:"
echo "  orca orchestration task-list --json"
echo "  orca orchestration inbox --limit 20 --json"
echo "  tail -f ${RUN_DIR}/log.md"
echo
echo "If Orca restarts mid-run, handles go stale. Reacquire with:"
echo "  orca terminal list --worktree id:${WT} --json"
