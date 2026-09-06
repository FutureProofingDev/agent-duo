# Agent Duo participation guidance

This file applies when Codex is already participating in a duo run. The received
prompt assigns PLANNER/EXECUTOR or REVIEWER. To start a new run, use `$agent-duo`
or the packaged launcher. Locate the installed skill's `references/protocol.md`
(or this checkout's `skill/references/protocol.md`) and use the actual absolute
controller/run paths supplied in the resolved prompt.

## Shared contract

```
brief/issue → spec review → plan review → implementation → gate → PR review → finalize
```

Run artifacts default to `docs/agent-duo/runs/<run_id>/`. Both agents share the
same dedicated worktree. The Python controller is authoritative for phase,
request identity, artifact hash, reviewer, round/retry limits, gate evidence and
completion. Orca messages are optional notifications around that durable state.

- Start with controller `status`, including after restarts. Process pending work
  even if its creation notification was missed.
- Publish complete files with temporary-write/atomic-rename. Versions become
  immutable on request; accepted spec/plan stay frozen. A revised specification
  needs human scoping and a new run.
- Source names are spec-v1.md, plan-v1.md and prr-123-v1.md. Review names prefix
  `cr-` once, preserving a single .md extension.
- Every review includes exact pending request metadata and five numbered Markdown
  headings with evidence. Only controller `accept` advances the workflow.
- Commit implementation changes before running controller `gate`. A new code SHA
  needs a new gate and PR review. Reviewer checks GitHub's remote head matches the
  request and local commit; controller verifies the local evidence.
- Use bounded `wait` calls and `heartbeat` for real progress. Honor controller
  escalation/deadlines; no agent-side poll counter or self-issued human ruling.
- Keep timestamped notes in your own log-planner.md or log-reviewer.md.

## Roles

The planner implements, publishes sources with `request`, handles findings and
runs gates. The reviewer judges the appropriate spec/plan/PR rubric, publishes a
review and calls `accept`. Retry the same successful submission idempotently if
transport delivery is uncertain; do not create a new content round for delivery.
Style/naming/optional improvements remain non-blocking. Later reviews assess both
the changed content and assumptions affected by it, then verify previous blockers.

The reviewer reads controller `memory` as advisory context and publishes validated,
generalized learning proposals before its final PR acceptance. The planner invokes
`finalize` so the completed-run ledger and memory are committed to local
`refs/agent-duo/learning` independently of approved code. Preserve legacy lesson
files, and do not push the memory ref implicitly.

Both roles stop successfully only after controller status is completed. GitHub
comments do not control completion, and no automatic merge is authorized by this
protocol. Resume uses the saved state; escalation requires a real human ruling
recorded with `resume --reason TEXT`.

Both agents can invoke this local controller and write the worktree. Its checks
prevent lifecycle mistakes; they do not authenticate mutually hostile agents.
External GitHub actions still require the user's authorization and environment
permissions.
