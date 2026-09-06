# Orca orchestration transport

Orca supplies wakeups and task visibility. The Python controller supplies durable
state and approval authority, exactly as in file mode. Keep both agents in one
worktree and retain the run directory after an Orca restart.

## Transport boundaries

| Concern | Authority |
|---|---|
| Current phase/request and accepted result | `duo-state.py status` |
| Source hash, reviewer identity, round/retry limits | controller |
| Review content and five evidence sections | reviewer, validated by controller |
| Gate and commit match | controller; reviewer checks remote PR SHA and publication rechecks it |
| Published verdict and comment URL | controller `publish-review` |
| Terminal handles and task/dispatch IDs | current Orca runtime |
| Wakeups and human-facing task activity | Orca messages |

Read the version-matched Orca orchestration guide before using its commands. The
launcher supplies current `REVIEWER_HANDLE` / `PLANNER_HANDLE` values; these are
runtime identities, not durable run IDs.

## Every review round, including each PR commit

1. Planner publishes a source and calls controller `request`. Save its request ID.
2. Planner creates and dispatches a review task to the assigned reviewer. Include
   the absolute run directory, request ID and this fixed reporting contract:

   > Read controller status and review its current request using your five-item
   > rubric. Publish cr-<source-basename> with all exact metadata and five numbered
   > headings, then run controller accept. Report worker_done with task ID,
   > dispatch ID, report path and the controller outcome. Report operational
   > failures as failures. Delivery retries with the same IDs are allowed.

3. Reviewer confirms the message refers to the current pending request, reads its
   immutable artifact and prerequisites, publishes the review and calls `accept`.
4. Reviewer reports the accepted result or error to the coordinator using the
   active `--task-id`, `--dispatch-id` and `--report-path` when a report exists.
5. Planner reads controller status. A valid `changes_requested` requires a new
   source/version and dispatch; a new PR SHA also requires a new passing gate.

A message subject is a summary. An Orca task marked completed is transport state.
Neither overrides controller acceptance. Inspect message type before acting:
`escalation` and `decision_gate` messages do not carry a review verdict by default.

## Delivery and waiting

Produce one logical result per dispatch. Retry an uncertain or incorrectly tagged
send with the same result and identifiers; do not invent a new content round.
Controller acceptance is idempotent, so an accepted review survives lost messages.
If task closure fails, reconcile delivery for visibility while preserving the
controller result. A transport bookkeeping issue must not reverse an approval or
force a redundant review of unchanged content.

Use native blocking waits bounded to 30 seconds, then inspect controller status.
A timeout is a checkpoint, not a verdict. During actual long work, update the
controller heartbeat and send Orca heartbeats with the active task/dispatch IDs.
Empty waits are not progress; controller time budgets remain in force.

## Restart and human escalation

Use `duo --resume --run-id ID` to reacquire validated terminals and replay saved
resolved prompts only after protocol/version/token/hash preflight. A legacy or
incompatible snapshot needs a new run with imported, revalidated evidence; do not
rewrite the old artifacts to pass validation. The launcher calls controller `resume`; after escalation a
human-approved `resume --reason "<ruling>"` is required first. Never reset the Git
branch or create fresh run state just to resume a pending review.

Orca tasks may disappear on restart. Recreate a transport task only for the
controller's still-pending request, retaining its request ID and source hash.
If that review was accepted before restart, continue the recorded next phase.
The new reviewer reads current assigned identity from controller status.

For unresolved decisions record the facts and positions in escalation.md and
route the question to the human. Asking the coordinator's own terminal does not
create human authority; a timed-out question does not authorize continuation.
Keep the human ruling in the durable resume record.

Before the final approved PR review is accepted, the reviewer publishes learning
proposals. After acceptance, the planner calls `publish-review --repo OWNER/NAME`
to publish the SHA-specific five-section verdict and pending manual checks. An
uncertain publication can be retried idempotently even if its Orca notification
was lost. The planner then finalizes through the controller; both stop only when
state is completed with recorded verdict publication. See [learning.md](learning.md).
