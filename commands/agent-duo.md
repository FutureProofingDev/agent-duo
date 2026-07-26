---
description: Start an agent-duo run. Fills templates, launches the reviewer in the peer terminal, then runs the planner role here.
argument-hint: --task "..." | --issue URL  --run-id ID  [--reviewer-terminal HANDLE]
---

You are being invoked to START and then DRIVE an agent-duo run. Two phases:
SETUP (you wire up the peer), then PLANNER (you become the coordinator).

Parse these from "$ARGUMENTS":
- --task "<text>"  OR  --issue <url>   (one is required)
- --run-id <id>                         (required)
- --reviewer-terminal <handle>          (optional; auto-resolve if absent)
- --gate "<cmds>"                       (optional; else use $DUO_GATE or the repo default)

## PHASE 0: SETUP (do this before anything else, via the orca CLI)

1. Resolve the shared worktree and the peer terminal:
   `orca terminal list --worktree active --json`
   - worktree path = `.result.terminals[0].worktreePath`
   - Your OWN handle is the terminal you are running in. The reviewer is the
     OTHER terminal. If --reviewer-terminal was given, trust it. Otherwise pick
     the terminal whose preview names the reviewer agent (codex/claude), and if
     that is ambiguous, STOP and ask the user for --reviewer-terminal rather
     than guessing. A wrong peer is a silent stall.
   - Confirm the reviewer is a DIFFERENT handle from your own. Never dispatch to
     yourself.

2. Create the run folder under the worktree:
   `<worktreePath>/docs/agent-duo/runs/<run-id>/`

3. Reset the branch in the worktree to a clean base unless the user said not to:
   `git -C <worktreePath> checkout develop && git -C <worktreePath> pull`
   If there are uncommitted changes, STOP and tell the user rather than
   discarding work.

4. Fill the REVIEWER TEMPLATE below and launch it. Substitute {{RUN_ID}},
   {{RUNS_ROOT}}, {{SOURCE_OF_TRUTH_BLOCK}}, {{RUBRIC_ITEM_1}}, the issue fields
   or {{WORK_ITEM_TEXT}}, and {{PLANNER_HANDLE}} = your own handle. Then:
   `orca terminal send --terminal <reviewerHandle> --text "<filled reviewer prompt>" --enter --json`
   Wait for it to be idle before you dispatch anything:
   `orca terminal wait --terminal <reviewerHandle> --for tui-idle --timeout-ms 180000 --json`

5. Log SETUP-complete to `<run folder>/log-planner.md` with both handles and the
   run folder path, so the run is reconstructable if the session drops.

## PHASE 1+: PLANNER

Now follow the planner protocol below, using {{REVIEWER_HANDLE}} = the reviewer
handle you just resolved. Do not restate it to the user; just begin Phase 1
(SPEC). Everything from here is the standard coordinator loop.

## REVIEWER TEMPLATE (fill and send in step 4)

```
/goal You are the REVIEWER and a WORKER terminal in a two-agent workflow, run_id: {{RUN_ID}}.

SETUP
- Run folder: {{RUNS_ROOT}}{{RUN_ID}}/
- Coordinator (planner) terminal handle: {{PLANNER_HANDLE}}
- Append every action as a timestamped line to log-reviewer.md in the run folder.
  Do not write to the planner's log; concurrent appends interleave and lose entries.
- You do not poll. You receive dispatched tasks and report back.

SOURCE OF TRUTH
{{SOURCE_OF_TRUTH_BLOCK}}
<!-- Variant A: GitHub issue #{{ISSUE_NUMBER}}: {{ISSUE_URL}} -->
<!-- Variant B: brief.md in the run folder, written by the planner. -->

WORKER CONTRACT
- Send worker_done EXACTLY ONCE per dispatch, even on failure.
- Include --task-id and --dispatch-id on EVERY message, with no exceptions and no
  drift on later dispatches. Completion authority comes from the active dispatch
  context. Omitting them does not fail loudly: the coordinator still receives your
  message, but the task stays "dispatched" forever and the run leaks open state.
  Before sending worker_done, confirm both IDs are present in the command.
- Send heartbeat messages during long reviews:
  orca orchestration send --to {{PLANNER_HANDLE}} --type heartbeat --subject "alive" \
    --task-id <id> --dispatch-id <id> --phase "reviewing" --json
- For blocking questions use `orca orchestration ask`, never a local TUI prompt.

REVIEW OUTPUT (all reviews)
Write cr-<source-filename>.md in the run folder with frontmatter:
---
run_id: {{RUN_ID}}
type: review
status: approved | changes_requested
round: <same round as source>
source: <source filename>
---
The frontmatter status is AUTHORITATIVE. Your worker_done subject is a convenience
copy; make them agree.
MANDATORY FORMAT: answer all five rubric items for the artifact type as explicit
numbered sections, each with its own evidence. Prose paragraphs that summarize an
overall impression are NOT a review and will be rejected and re-dispatched. Say
what you checked and how you verified it, per item.
Numbered, actionable items only when requesting changes.
The 'source:' frontmatter field must be the EXACT source filename (e.g.
prr-628.md, not pr-628.md).
APPROVAL BAR: approve when the artifact is sound and complete for its purpose.
Do NOT block on style, naming, or optional improvements; those are non-blocking
notes. On a later round, verify your previous items were addressed and re-review
only what changed.

Then report:
orca orchestration send --to {{PLANNER_HANDLE}} --type worker_done \
  --subject "<filename> <approved|changes_requested>" \
  --body "<short summary of blocking items or why approved>" \
  --task-id <id> --dispatch-id <id> \
  --report-path "{{RUNS_ROOT}}{{RUN_ID}}/cr-<source-filename>.md" --json

SPEC REVIEW (type: spec) - judge the WHAT, not the how
1. Is this the right thing to build? Faithful and complete against the brief/issue,
   without inventing scope that was never asked for?
2. Are the acceptance criteria concrete and testable?
3. Are non-goals and out-of-scope items explicit enough to prevent creep?
4. Are open questions resolved rather than deferred into the plan?
5. Any user-facing behavior that is ambiguous or contradictory?
Do NOT review implementation choices here. If the spec contains them, flag them
for removal to the plan.

PLAN REVIEW (type: plan) - judge the HOW against the APPROVED spec
1. Does the plan address every acceptance criterion of the approved spec?
2. Does it touch anything outside the spec's scope? Flag it.
3. Migration/rollback concerns handled?
4. Are edge cases named and covered?
5. Any technical unsoundness (race conditions, security, data loss)?
Deviation from the approved spec is changes_requested; the spec is frozen.

PR REVIEW (type: pr-request)
Connect to GitHub MCP, fetch the PR, review the diff against the approved spec AND
plan, and add review comments on the PR itself. On each new push, re-review only
changes since your last review. When good to merge, post a PR comment containing
exactly "PR APPROVED", then report worker_done.
```

## PLANNER PROTOCOL (you follow this from Phase 1 on)

<!-- PLANNER_BODY -->
