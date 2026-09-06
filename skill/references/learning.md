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

After controller acceptance of the final PR review, the planner calls:

```bash
python3 /absolute/path/duo-state.py finalize --run-dir /absolute/run/directory --lessons /absolute/run/directory/lessons-proposals.json
```

The controller validates and persists proposals, records this completed run once,
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
