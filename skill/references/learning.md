# Cross-run learning

Memory is per repository and advisory. The reviewer reads it to direct attention;
the planner does not use it as an accusation or preemptive checklist. Review each
artifact on its evidence and keep style/preferences non-blocking.

## Durable store

The controller stores a completed-run ledger and lessons in the local Git ref
`refs/agent-duo/learning`, including readable `lessons.md` and
`lessons-pending.md`. Read it with:

```bash
python3 /absolute/path/duo-state.py memory --run-dir /absolute/run/directory
```

`memory` returns JSON `{runs, lessons}`; filter lessons by `status: active` for the
review checklist. Git worktrees in the same repository share this ref, so memory
survives branch changes and completed-run cleanup. It is committed independently
of the code branch; finalization does not dirty or amend the code already reviewed.
The run itself still needs its run directory for resume and detailed evidence.

Memory is local unless explicitly shared. It is not included in the code PR and
is not implicitly pushed. For intentional cross-machine sharing, a user can push
`refs/agent-duo/learning:refs/agent-duo/learning` to an appropriate remote; preserve
and reconcile divergent histories rather than force-pushing over another machine.
Legacy `docs/agent-duo/lessons.md` and `lessons-pending.md` remain reference material;
do not delete them or silently treat them as the new writable store.

## Optional Jev lesson suggestions

The reviewer calls `suggest-lessons` before each review. Selection is off by
default. Enable it only when the user authorizes sending the run's **brief and
active lesson patterns/scopes** to classifier.dev, whose fast tier uses TypeSafe's
Jev. No code diff, evidence files, confirmation history or GitHub credentials are
sent. Briefs and generalized lessons can still contain sensitive project details.

From the application repository:

```bash
git config --local agentduo.lessonSelector classifier
python3 /absolute/path/duo-state.py suggest-lessons --run-dir /absolute/run/directory
```

Use `git config --global agentduo.lessonSelector classifier` only for an explicitly
authorized personal default across repositories. A repository can override that
default with `git config --local agentduo.lessonSelector off`.

The public, keyless MCP endpoint is `https://classifier.dev/mcp`. The command uses
`classify_texts`, fast tier, Jev model, and returns at most three suggestions with
positive-label scores of at least 0.70. Scores are relative model preferences,
not verified correctness or approval. Only active learned lessons participate;
an empty repository memory sends no request and does not import synthetic lessons.
The complete memory remains accessible through `memory` and is never filtered or
rewritten by selection. The reviewer must still perform the full review rubric.

`lesson-suggestions.json` in the ignored run directory records an input hash,
timestamp, model, scores and shortlist. Repeated calls and resume reuse the same
selection while the brief, active catalog and selection rules are unchanged.
The actual returned model is recorded because the Jev alias can change.
Use `suggest-lessons --refresh` for an intentional retry or reevaluation; do not
poll the service during ordinary waiting. Failed selections are cached too.

Disabled, empty or unavailable selection returns a named status and no shortlist;
the reviewer continues with local memory. HTTP requests have a five-second timeout
and no automatic retries. Invalid/missing scores, service errors and excessive
input sizes make the whole selection unavailable, rather than quietly omitting
unknown lessons. Selection does not hold the controller lock during network I/O,
change the phase, approve evidence or update the learned-memory ref. Existing
saved role prompts are preserved during resume; new runs receive this instruction.

The feature requires only the packaged Python standard-library helper
`assets/duo_lessons.py`; no global MCP registration, Node package or API key is
needed. See [classifier MCP documentation](https://classifier.dev/mcp-setup).

## Proposals and finalization

Before submitting the final approved PR review, the reviewer atomically publishes
`lessons-proposals.json` in the run folder. Write `[]` if there are no lessons.
Otherwise use a list with this shape:

```json
[
  {
    "pattern": "Plans omit ownership validation for new relationships",
    "scope": "plan",
    "evidence": ["cr-plan-v1.md", "plan-v2.md"],
    "resolution": "verified"
  }
]
```

`scope` identifies a phase or area, such as `spec`, `plan`, `pr` or `API`. Evidence paths are relative to this run folder
and must exist. `resolution` is `accepted` or `verified`; an unaccepted allegation
or reviewer preference is not a lesson. The reviewer supplies substantive evidence
of the finding and its resolution; checking path existence cannot establish that
the reasoning is true. Generalize the behavior, avoiding specific symbols/tables.

After controller acceptance of the final PR review, the planner publishes its
verdict and pending manual checks, then finalizes the run:

```bash
python3 /absolute/path/duo-state.py publish-review --run-dir /absolute/run/directory --repo OWNER/NAME
python3 /absolute/path/duo-state.py finalize --run-dir /absolute/run/directory --lessons /absolute/run/directory/lessons-proposals.json
```

New protocol-2 runs require a recorded verdict publication before finalization.
The publication command uses an authorized gh CLI session; storing memory itself
remains local. The controller validates and persists proposals, records this completed run once,
and only then marks it completed. A retry is idempotent. Both agents wait for that
state instead of stopping when a GitHub comment appears. Escalated or stopped runs
may preserve proposals for inspection, but do not count as completed observations.

## Promotion, decay and recurrence

- A first accepted/verified observation is pending. Two distinct completed runs
  confirming the same pattern make it active; repeated phases or retries in one
  run count once.
- Confirmation updates the lesson against the durable sequence of completed runs,
  not dates, alphabetical run IDs, poll counts or number of attempted runs.
- Five completed runs without confirmation make an active lesson dormant.
- A later confirmed recurrence reactivates a dormant lesson while retaining history.
- Never turn active lessons into automatic rejection rules or copy them across
  unrelated repositories.

A per-repository Git ref provides one durable update point for concurrent runs.
The controller owns serialization and ledger deduplication; agents propose findings
rather than editing counters or racing to rewrite shared memory files.
