# Agent Duo participation guidance

This file applies when Codex is already participating in a duo run. The received
prompt assigns PLANNER/EXECUTOR or REVIEWER. To start a new run, use `$agent-duo`
or the packaged launcher. Locate the installed skill's `references/protocol.md`
(or this checkout's `skill/references/protocol.md`) and use the actual absolute
controller/run paths supplied in the resolved prompt.

## Shared contract

```
brief/issue → spec review → plan review → implementation → gate → PR review → publish verdict → finalize
```

Run artifacts default to `docs/agent-duo/runs/<run_id>/`. Both agents share the
same dedicated worktree. The Python controller is authoritative for phase,
request identity, artifact hash, reviewer, round/retry limits, gate evidence and
completion. Orca messages are optional notifications around that durable state.
Continue through implementation after plan approval unless the user explicitly
requested planning only; "plan" alone is not a stopping instruction.

- Require protocol 2 from `python3 /absolute/path/duo-state.py protocol` and the
  matching line-2 role/transport marker in the saved template. Resolved instructions
  omit HTML comments. The launcher checks
  template tokens and saved hashes. Legacy/incompatible runs need a new run with
  imported, revalidated evidence; preserve the original historical records.
- Start with controller `status`, including after restarts. Process pending work
  even if its creation notification was missed.
- Publish complete files with temporary-write/atomic-rename. Versions become
  immutable on request; accepted spec/plan stay frozen. A revised specification
  needs human scoping and a new run.
- Frontmatter belongs to the run's protocol artifacts, not README.md or
  application documentation. Preserve those files' native format.
- Source names are spec-v1.md, plan-v1.md and prr-123-v1.md. Review names prefix
  `cr-` once, preserving a single .md extension.
- Every review includes exact pending request metadata and five numbered Markdown
  headings with evidence. Only controller `accept` advances the workflow.
- Commit implementation changes before running controller `gate`. A new code SHA
  needs a new gate and PR review. Reviewer checks GitHub's remote head matches the
  request and local commit; controller verifies the local evidence. Record the
  current GitHub base SHA and head SHA and derive the diff from that actual base.
- Final PR reviews contain `## Pending manual checks`, listing untested acceptance
  checks/limitations or `None.`. Publish those limitations rather than silently
  treating approximations or unavailable device checks as passes.
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
`publish-review --repo OWNER/NAME` after acceptance, then `finalize`. Publication
requires authorized gh CLI access, checks the remote HEAD, posts the accepted
five-section verdict with SHA/evidence/pending manual checks and records its URL.
Retries are idempotent. Finalization commits the completed-run ledger and memory to local
`refs/agent-duo/learning` independently of approved code. Preserve legacy lesson
files, and do not push the memory ref implicitly.

Both roles stop successfully only after controller status is completed with a
recorded verdict publication URL, which belongs in the final summary. Arbitrary
GitHub comment text cannot grant approval, and publication is not native
self-approval. No automatic merge is authorized by this
protocol. Resume uses the saved state; escalation requires a real human ruling
recorded with `resume --reason TEXT`.

Both agents can invoke this local controller and write the worktree. Its checks
prevent lifecycle mistakes; they do not authenticate mutually hostile agents.
External GitHub actions still require the user's authorization and environment
permissions.
