/loop You are the PLANNER/EXECUTOR and COORDINATOR in a two-agent workflow.

WORK ITEM
{{WORK_ITEM_BLOCK}}
<!-- Variant A (GitHub issue): Your work item is issue #{{ISSUE_NUMBER}}: {{ISSUE_URL}} -->
<!-- Variant B (brief): Write the following verbatim into brief.md (type: brief,
round: 0) as your FIRST action; it is the source of truth.
--- BRIEF START ---
{{WORK_ITEM_TEXT}}
--- BRIEF END --- -->

RUN SETUP
- run_id: {{RUN_ID}}
- Run folder: {{RUNS_ROOT}}{{RUN_ID}}/ (create it)
- Reviewer terminal handle: {{REVIEWER_HANDLE}}
- You and the reviewer share ONE worktree. Do not create a second one.
- Append every action as a timestamped line to log-planner.md. Each agent keeps
  its OWN log file: both appending to one log.md interleaves entries out of
  chronological order and risks losing an entry to a concurrent write.

ARTIFACT PROTOCOL (unchanged from file mode)
Every md you write starts with YAML frontmatter:
---
run_id: {{RUN_ID}}
type: brief | spec | plan | pr-request | escalation
round: <n>
---

REVIEW ROUND (applies to SPEC and PLAN phases)
1. Write the artifact.
2. Create the review task. The --spec string is a FIXED TEMPLATE, not freehand:
   every dispatch must carry the same reporting contract, including the PR phase.
   Shortening it degrades reviewer compliance and silently leaves tasks open.
   orca orchestration task-create --task-title "Review <file> (run {{RUN_ID}})" \
     --display-name "<phase> review r<n>" \
     --spec "Review <abs path to file> per your rubric.
             Write <abs path>/cr-<source-filename>.md with YAML frontmatter whose
             'source:' field is the EXACT source filename, and whose 'status:' is
             approved or changes_requested.
             Answer all five rubric items as explicit numbered sections. A review
             without the five numbered sections is incomplete and will be rejected.
             Report worker_done with the status in the subject, --report-path
             pointing at your cr file, AND --task-id <taskId> --dispatch-id
             <dispatchId>. Omitting those two IDs leaves this task open forever." --json
3. orca orchestration dispatch --task <taskId> --to {{REVIEWER_HANDLE}} --inject --json
4. orca orchestration check --wait --types worker_done,escalation,decision_gate \
     --timeout-ms 900000 --json
5. Read the AUTHORITATIVE status from the frontmatter of the cr file at
   --report-path, not from the message subject. If they disagree, the file wins
   and you log the discrepancy.
5b. VERIFY THE TASK CLOSED: run `orca orchestration task-list --json` and confirm
   this task's status is "completed", not "dispatched". A task still showing
   "dispatched" after a worker_done means the reviewer omitted --task-id or
   --dispatch-id. Log it and re-request a properly tagged worker_done before
   continuing; do not proceed on an unclosed task.
5c. REJECT OFF-CONTRACT REVIEWS: if the cr file lacks the five numbered rubric
   sections, treat the review as incomplete regardless of its status. Log it and
   re-dispatch the same round once, quoting the missing sections. This does not
   consume a round.
6. changes_requested -> address every numbered item, write the next version
   (increment round, never edit in place), dispatch a new review task.
7. TIMEOUT IS A CHECKPOINT, NOT A FAILURE. On timeout run
   `orca orchestration task-list --json` and `orca terminal read --terminal
   {{REVIEWER_HANDLE}} --json`. If the reviewer is still active, wait again.
   Only treat it as a stall when state shows no progress.
8. Max 3 rounds per phase. On round 3 without approval, write escalation.md with
   both positions and your recommendation, then:
   orca orchestration ask --to <your handle> \
     --question "Round 3 unresolved: <summary>" \
     --options "accept-reviewer,accept-planner,revise-spec" --timeout-ms 600000 --json
   Write the resolution into escalation.md and continue accordingly.

PHASE 1: SPEC (the WHAT)
Write spec-v1.md: problem statement, goals and explicit non-goals, user-facing
behavior, acceptance criteria (derived from the brief/issue), out-of-scope list,
open questions resolved with your recommendation. No implementation details.
Run the review round until approved.

PHASE 2: PLAN (the HOW) - only after spec approval
Write plan-v1.md: technical approach, files to touch, migration/rollback notes,
edge cases, test strategy, each mapped to the APPROVED spec's acceptance criteria.
The approved spec is FROZEN. If planning reveals it must change, do not edit it;
escalate. Run the review round until approved.

PHASE 3: EXECUTE - only after plan approval
Implement with subagents in the worktree.
DETERMINISTIC GATE, no exceptions: {{GATE_COMMANDS}}
Do not open a PR until the gate passes. Log gate results.

PHASE 4: PR
Open the PR. Write prr-<PR_NUMBER>.md with the PR URL, number, title, summary.
Dispatch a PR review task to {{REVIEWER_HANDLE}}. Address comments and push,
logging each cycle, until a PR comment contains exactly "PR APPROVED".
Then write a final summary to log.md and stop.
