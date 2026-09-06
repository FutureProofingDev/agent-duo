# Agent Duo protocol

Two agents produce Markdown evidence. `duo-state.py`, a Python 3 standard-library
controller, owns the state machine. Both agents and both transports use the same
controller and one dedicated Git worktree per run.

## Authority and lifecycle

```
brief/issue → spec review → plan review → implementation → gate → PR review
                ↖ revise       ↖ revise                    ↖ fix + new gate
                                                            ↓
                                                       finalize → completed
```

An encouraging message, a frontmatter field alone, a closed Orca task or a GitHub
approval comment cannot advance a run. `accept` validates the complete review and
current request. Finalization persists memory before marking completion.

The planner owns implementation and addresses review findings. The reviewer owns
the substantive verdict and evidence. The controller owns request identity,
source immutability, phase ordering, three content rounds per phase (including PR),
a separate maximum of two malformed-review retries, time budgets, gate execution
and completion. Neither agent implements its own counters.

This is a reliability boundary for cooperating local agents. Both can write the
same files and invoke the controller, so reviewer metadata is not authentication
against a malicious agent. GitHub may prevent native approval when both agents use
the same account; a local validated review still records the assigned reviewer.

## Files and publication

All run files live in `docs/agent-duo/runs/<run_id>/` by default. Run artifacts and
controller state are local audit records, normally gitignored; they do not become
part of the code PR automatically. Preserve the run directory for recovery.

| Artifact | Filename | Writer |
|---|---|---|
| Verbatim work statement | `brief.md` | launcher, or planner during manual setup |
| Spec | `spec-v1.md`, `spec-v2.md`, … | planner |
| Plan | `plan-v1.md`, `plan-v2.md`, … | planner |
| PR request | `prr-123-v1.md`, `prr-123-v2.md`, … | planner |
| Review | `cr-` plus the source filename, e.g. `cr-spec-v1.md` | reviewer |
| Human decision context | `escalation.md` | planner |
| Learning proposals | `lessons-proposals.json` | reviewer |
| Agent logs | `log-planner.md`, `log-reviewer.md` | respective agent |

Create a temporary file in the run directory, finish writing it, then atomically
rename it to the final filename. Request a review only after publication. Do the
same for reviews before calling `accept`. A requested source is immutable; a
content revision needs the next version. Accepted spec and plan remain frozen.
A human-authorized specification change starts a new run with the revised brief.

## Strict frontmatter

The supported YAML subset is a flat mapping of scalar fields. Do not use nested
structures, duplicate keys or inline comments. Required source fields:

```yaml
---
run_id: example-a
type: spec
round: 1
---
```

Types are `spec`, `plan` and `pr-request`. PR source filenames include the PR number
and round, and their frontmatter additionally contains `head_sha` (full Git commit
ID) and `pr_number`. `request` returns `request_id` and `source_sha256`; use those
exact values in the review, along with the assigned reviewer from `status`:

```yaml
---
run_id: example-a
type: review
round: 1
source: spec-v1.md
source_sha256: <hash returned by request>
request_id: <request ID returned by request>
reviewer: <current assigned reviewer>
status: approved
---
```

The other verdict is `changes_requested`. PR reviews also require `head_sha`.
Every review contains five Markdown headings `## 1. <criterion>` through
`## 5. <criterion>`, each with evidence. The canonical five-item spec, plan and PR
rubrics are in both reviewer assets. Style and optional improvements never block.
On later rounds, assess the diff and assumptions it affects, and verify prior
blockers; an unchanged file can still be affected by a change elsewhere.

## Controller CLI

Every subcommand takes `--run-dir <absolute run directory>`:

| Command | Purpose |
|---|---|
| `init --run-id ID --worktree PATH --gate COMMAND --reviewer IDENTITY` | Initialize a new run once; the launcher does this |
| `status` | JSON state including revision, phase and pending request |
| `request --source BASENAME` | Validate and register the next immutable source |
| `accept --review BASENAME` | Validate review identity, content and evidence; advance state |
| `gate [--timeout SECONDS]` | Execute the configured gate for the current clean HEAD |
| `heartbeat` | Record meaningful progress during long work |
| `wait --after REVISION --timeout 30` | Wait outside the LLM for state change or a checkpoint |
| `resume [--reviewer IDENTITY] [--reason TEXT]` | Recover persistent state; a human ruling is required after escalation |
| `finalize [--lessons PATH.json]` | Persist the completed-run ledger and lessons, then complete |
| `memory` | Read JSON `{runs, lessons}` from the local learning ref |

Example:

```bash
python3 /absolute/path/duo-state.py status --run-dir /worktree/docs/agent-duo/runs/example-a
python3 /absolute/path/duo-state.py request --run-dir /worktree/docs/agent-duo/runs/example-a --source spec-v1.md
python3 /absolute/path/duo-state.py accept --run-dir /worktree/docs/agent-duo/runs/example-a --review cr-spec-v1.md
```

The reviewer calls `accept` after publication. The planner can repeat the same
successful submission if delivery is uncertain: acceptance is idempotent. A
malformed review is corrected for its pending request within the retry limit;
content changes use new rounds. Errors do not imply approval.

## Gate and exact-commit PR review

Commit implementation changes and make the tracked worktree clean before `gate`.
The controller runs the configured commands and records their exit status and
commit. Failure, timeout or worktree/HEAD changes invalidate the result. Choose
real repository checks; the controller cannot make a trivial command meaningful.

Open or update a PR only after a passing gate. The reviewer verifies GitHub's
current head matches the local commit and `head_sha` in the PR request, including
immediately before submitting the review. The controller validates local HEAD,
request hash, assigned reviewer and gate evidence. It does not query GitHub, so
remote-head verification remains an explicit reviewer duty.

After every code fix: commit, gate again, push, verify the remote head and request
a new PR review with an incremented filename/round. Completion requires:

```
reviewed SHA = gate SHA = request SHA = current local HEAD
```

Human-facing GitHub comments should name that SHA. They do not determine local
state. Approval is followed by `finalize`; only `phase: completed` is success.
This workflow does not merge PRs automatically.

## Waiting, escalation and recovery

Start by reading `status` and existing pending work. Notifications are hints, so
starting the reviewer late cannot lose a published artifact. Wait in bounded
30-second calls and emit heartbeats for actual progress; repeated empty waits do
not extend a run. The controller applies elapsed-time/progress budgets, avoiding
both an arbitrary poll count and unbounded spinning.

When escalated, preserve the run and explain the unresolved findings. A human
ruling is recorded via `resume --reason TEXT`; elapsed time and edited prose are
not rulings. Resume restores the saved phase/request instead of starting over.
In Orca, use `duo --resume --run-id ID` to refresh terminal identities and reconcile
pending work. Runtime task loss does not discard an accepted controller result.
See [orchestration.md](orchestration.md) for transport recovery and
[learning.md](learning.md) for durable finalization.

## Field lessons retained

The first live run exposed reporting-contract drift, missing dispatch IDs,
incomplete rubrics and conflicting log writes. Preserve exact request metadata,
five evidence sections, retryable tagged delivery, and one log per agent.
Push/PR permissions still come from the agent environment and user authorization;
the controller does not bypass them.
