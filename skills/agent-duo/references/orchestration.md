# Orchestration mode (Orca-native transport)

An alternative transport for the same protocol. Artifacts are unchanged; only the
signaling between agents changes. Requires Orca orchestration enabled under
Settings -> Experimental.

## What changes and what does not

| Concern | File mode | Orchestration mode |
|---|---|---|
| Artifacts (spec, plan, cr, brief) | md files with frontmatter | **unchanged** |
| Status token in frontmatter | `approved` / `changes_requested` | **unchanged** |
| Versioning, spec freeze, rubrics | as documented | **unchanged** |
| "Something new landed" | poll the folder | `dispatch` / `worker_done` messages |
| Waiting | 20-poll circuit breaker | `check --wait --timeout-ms` (blocks) |
| Escalation | write `escalation.md`, human edits it | `orchestration ask` with options |
| Run log | `log.md` | task records + inbox (keep `log.md` too) |
| Stale-run protection | `run_id` in frontmatter | `taskId` + `dispatchId` on every message |

Keep the artifacts. They are the audit trail, they diff, they commit with the
branch, and they are what makes a failed run debuggable. Orchestration state is
runtime-scoped and disappears; files do not.

## Role mapping

The planner is the COORDINATOR. It owns round caps, escalation, and the task
records. The reviewer is a WORKER terminal that receives dispatches and reports
verdicts. This is the same ownership split as file mode, expressed in Orca's model.

## Round shape

Per review round, coordinator side:

```
write spec-v1.md
orca orchestration task-create --task-title "Review spec-v1 (run <run_id>)" \
  --display-name "spec review r1" \
  --spec "Review <abs path>/spec-v1.md per your rubric. Write cr-spec-v1.md with
          frontmatter status approved|changes_requested. Report worker_done with
          the status in the subject and --report-path pointing at your cr file." --json
orca orchestration dispatch --task <taskId> --to <reviewerHandle> --inject --json
orca orchestration check --wait --types worker_done,escalation,decision_gate \
  --timeout-ms 900000 --json
```

Worker side, on completion:

```
orca orchestration send --to <coordinatorHandle> --type worker_done \
  --subject "spec-v1 changes_requested" \
  --body "<short summary of blocking items>" \
  --task-id <taskId> --dispatch-id <dispatchId> \
  --report-path "<run folder>/cr-spec-v1.md" --json
```

Send `worker_done` exactly once per dispatch, even on failure. Send `heartbeat`
during long reviews. Include both `taskId` and `dispatchId` on every message:
completion authority comes from the active dispatch context, so this is what
stops a stale retry from completing the wrong dispatch. It replaces the
stale-file problem that `run_id` solves in file mode.

## Read the verdict from the file, not the message

The `worker_done` subject is a convenience. Authoritative status is the
frontmatter of the cr file at `--report-path`. A message subject is prose and
prose drifts; frontmatter is parsed. If the two disagree, the file wins and the
coordinator logs the discrepancy.

## Timeouts are checkpoints, not failures

A `check --wait` timeout does not mean the worker died. Inspect before concluding:

```
orca orchestration task-list --json
orca terminal read --terminal <reviewerHandle> --json
```

If the worker is still active, wait again. This is strictly better than file
mode's poll budget, which cannot distinguish "stalled" from "still thinking" and
therefore has to guess. Only escalate after the state actually shows no progress.

## Escalation

Replace the `escalation.md` + human-edit loop with a blocking question:

```
orca orchestration ask --to <coordinatorHandle> \
  --question "Round 3 unresolved: <disagreement>" \
  --options "accept-reviewer,accept-planner,revise-spec" \
  --timeout-ms 600000 --json
```

Still write `escalation.md` with both positions before asking, and write the
resolution into it afterwards. The message gets the decision made; the file is
why anyone can reconstruct it next month.

## Terminal handles

Handles are runtime-scoped. If Orca restarts mid-run, reacquire with
`orca terminal list --json`, then continue. The launcher resolves the reviewer
handle at start and substitutes it into the planner prompt, since the coordinator
cannot dispatch without it.

## Still one worktree

Orchestration removes the filesystem dependency for *signaling*, not for
artifacts: the reviewer still has to open `spec-v1.md` and read the code. Keep
both agents in one worktree. Splitting them would require moving the run folder
to an absolute shared path outside both worktrees, which is possible but buys
little and costs the co-location of artifacts with the branch.

## Migration advice

Do not port file mode and orchestration mode at the same time on the same run.
If a run stalls while both are new, the cause is ambiguous between a protocol bug
and an orchestration bug, and you end up debugging two unfamiliar things at once.
Prove one loop, then swap the transport.
