# Agent Duo protocol

Two agents produce Markdown evidence. `duo-state.py`, a Python 3 standard-library
controller, owns the state machine. Both agents and both transports use the same
controller and one dedicated Git worktree per run. The current contract is
protocol 3: `python3 /absolute/path/duo-state.py protocol` takes no run arguments
and returns `{"protocol_version": 3}`. Canonical prompts carry a protocol/role/transport
HTML marker on line 2; the launcher validates it, required tokens and saved hashes
before delivery. Use one coherent installed bundle, never mixed legacy assets.

## Decision contract and evidence boundary

Protocol 3 adds required decision sections, code-state fingerprints and typed
findings to the existing lifecycle. It intentionally cannot resume protocol 1/2
runs: keep the old run and its matching bundle as historical evidence, or start a
new scoped run and revalidate imported references. Never rewrite a version field
to bypass this boundary. No installed bundle is upgraded by changing this checkout.

A spec must have exactly one nonempty level-two section for each of:

- `## Observable outcome`: measurable behavior with acceptance IDs, such as AC1.
- `## Constraints`: scope, non-goals and user/environment restrictions.
- `## Pending assumptions`: unresolved assumptions, owners and resolving checks,
  or `None.`. Material product decisions require a human ruling.
- `## Acceptance evidence`: the checks/evidence for each acceptance ID, including
  which missing checks prevent acceptance and any explicitly optional checks.

The controller validates presence, not the semantic truth of prose. The reviewer
checks that the contract matches the brief, is testable and states an honest
policy for uncertainty. Approved spec and plan still freeze their source hashes.

Every handoff now includes `code_state`: `head_sha`, `index_sha256`,
`worktree_sha256` and combined `state_sha256`. It hashes index entries, tracked
file bytes/deletions/executable bits/symlink targets, non-ignored untracked files
and initialized submodule code states. Untracked artifacts inside the run folder
and ignored files are excluded. Keep run folders ignored and never track them.
The index hash reflects staged content separately from the working files. Git
skip-worktree/assume-unchanged flags are rejected because they can hide changes
from clean-HEAD checks. `snapshot` reports this same fingerprint without a transition.

Spec/plan handoffs may capture dirty code. The pending fingerprint must still
match on retry and acceptance, and each review must echo `code_state_sha256` in
frontmatter. Gate results include their own fingerprint and compare before/after
execution; PR review/publication/finalization retain clean-commit requirements.
Fingerprinting is not an atomic filesystem snapshot or an authentication boundary.
Stop all cooperating code writers before capturing or checking it. Changes made
and reverted between observations cannot be detected; ignored runtime inputs and
external services need appropriate acceptance checks.

`status.write_ownership` states who may write code, sources, reviews, state and
separate logs. Only planner owns code/sources between handoffs; neither agent owns
code while review/gate is pending, after approval awaiting publication, or while
escalated/completed. Reviewer owns the pending review, its proposals and own log;
controller owns state/gate records. Ownership is a cooperative contract, not OS
permissions. Stop delegated writers before handing off.

To retire stale evidence, coordinate stopping its reviewer, then
`withdraw --reason TEXT`. It records the old request/fingerprint and reason,
returns ownership to the planner and consumes the round. Use the next source
version. At the round limit it escalates. It cannot withdraw an accepted review
or grant approval. If escalated, first record a real human ruling with resume.

## Hypotheses and targeted convergence

The five existing rubric sections remain. Every review additionally contains
`## Findings` with exactly one JSON fenced list (empty `[]` is valid):

```json
[{"id":"F1","category":"defect","claim":"Empty input violates AC1","criterion":"AC1","evidence":"src/input.py:12; empty-input regression fails","check":"Run regression; expect no exception","correction":"Handle empty input before indexing","blocking":true}]
```

All fields shown are required. Categories are `defect` (reproduction/direct code
proof), `uncertainty` (missing information plus consequence and resolving check),
and `preference` (optional improvement). IDs are unique within a review and stable
for continuing issues. Preferences cannot block. An uncertainty may block only
under the acceptance policy; the reviewer, not a text parser, judges this relevance.
`changes_requested` requires a blocking finding; `approved` requires none.
Uncertainty and unavailable manual checks must never be described as passed.

After changes_requested, the next source contains `## Resolutions` with one JSON
fenced list covering exactly every `open_findings` ID:

```json
[{"id":"F1","disposition":"fixed","evidence":"src/input.py:12; regression passes"}]
```

Disposition is `fixed` or `disputed`; both require concrete evidence. The next
review checks corrections/counterevidence and affected assumptions, preserving IDs
for unresolved issues. A planner's claim never clears a blocker by itself. Limit
changes to supported defects/required decisions; preferences never force extra
rounds. The existing three content rounds, two invalid deliveries and time budgets
remain authoritative. Exhaustion leaves phase escalated, preserves open_findings
and history, and cannot publish or finalize an approval. Report missing evidence
and the human decision needed. Resume records the human ruling and grants the
existing bounded extension; no agent may invent its own ruling.

## Authority and lifecycle

```
brief/issue → spec review → plan review → implementation → gate → PR review
                ↖ revise       ↖ revise                    ↖ fix + new gate
                                                            ↓
                                                 publish-review → finalize → completed
```

An encouraging message, a frontmatter field alone, a closed Orca task or a GitHub
approval comment cannot advance a run. `accept` validates the complete review and
current request. After local PR approval, `publish-review` records its public
verdict comment; finalization requires that publication and persists memory before
marking completion. End-to-end work continues after plan approval. Planning-only
is a scoped stopping point only when the user explicitly requests it; it is not a
completed end-to-end run, and the word "plan" alone never changes the lifecycle.

The planner owns implementation and addresses review findings. The reviewer owns
the substantive verdict and evidence. The controller owns request identity,
source immutability, phase ordering, three content rounds per phase (including PR),
a separate maximum of two malformed-review retries, time budgets, gate execution
and completion. Neither agent implements its own counters.

This is a reliability boundary for cooperating local agents. Both can write the
same files and invoke the controller, so reviewer metadata is not authentication
against a malicious agent. GitHub may prevent native approval when both agents use
the same account; a local validated review still records the assigned reviewer.
`publish-review` posts an ordinary comment rather than attempting self-approval.

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
| Optional advisory selection cache | `lesson-suggestions.json` | `suggest-lessons` command |
| Agent logs | `log-planner.md`, `log-reviewer.md` | respective agent |

Create a temporary file in the run directory, finish writing it, then atomically
rename it to the final filename. Request a review only after publication. Do the
same for reviews before calling `accept`. A requested source is immutable; a
content revision needs the next version. Accepted spec and plan remain frozen.
A human-authorized specification change starts a new run with the revised brief.

## Strict frontmatter

This schema applies to protocol sources and reviews inside the run directory.
It does not apply to README.md, application documentation or arbitrary Markdown
edited for the feature; preserve those files' native format.

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
code_state_sha256: <pending code_state.state_sha256>
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
Every final PR review also includes `## Pending manual checks`, listing untested
acceptance checks and limitations, or `None.`. Record unavailable checks as pending
under the approved acceptance policy; do not silently waive them or call viewport
approximations a real-device/zoom/screen-reader pass. Publication includes this text.

## Controller CLI

`protocol` takes no arguments and reports the supported protocol version.
All other subcommands take `--run-dir <absolute run directory>`:

| Command | Purpose |
|---|---|
| `protocol` | Report `{protocol_version: 3}` without a run directory |
| `init --run-id ID --worktree PATH --gate COMMAND --reviewer IDENTITY` | Initialize a new protocol-3 run once; the launcher does this |
| `snapshot` | Read current code-state fingerprint without changing phase |
| `withdraw --reason TEXT` | Retire a pending handoff with its evidence; consume the round |
| `status` | JSON state including revision, phase and pending request |
| `request --source BASENAME` | Validate and register the next immutable source |
| `accept --review BASENAME` | Validate review identity, content and evidence; advance state |
| `gate [--timeout SECONDS]` | Execute the configured gate for the current clean HEAD |
| `heartbeat` | Record meaningful progress during long work |
| `wait --after REVISION --timeout 30` | Wait outside the LLM for state change or a checkpoint |
| `resume [--reviewer IDENTITY] [--reason TEXT]` | Recover persistent state; a human ruling is required after escalation |
| `publish-review --repo OWNER/NAME` | Verify the accepted PR's remote HEAD, publish its verdict comment idempotently and record the URL |
| `finalize [--lessons PATH.json]` | Require the recorded verdict publication, persist the completed-run ledger and lessons, then complete |
| `memory` | Read JSON `{runs, lessons}` from the local learning ref |
| `suggest-lessons [--refresh]` | Return optional cached Jev suggestions; no protocol transition or memory mutation |

Example:

```bash
python3 /absolute/path/duo-state.py protocol
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

Open or update a PR only after a passing gate. Fetch GitHub's current `base.sha`
and `head.sha`; record both full SHAs and OWNER/NAME in the PR request body. Derive
the diff from the actual PR base, never an assumed local main. The reviewer verifies
the remote head matches the local commit and `head_sha` in the PR request, including
immediately before submitting the review. `accept` validates local HEAD, request
hash, assigned reviewer and gate evidence. `publish-review` additionally checks
the live remote HEAD before publishing the accepted verdict.

After every code fix: commit, gate again, push, verify the remote head and request
a new PR review with an incremented filename/round. Completion requires:

```
reviewed SHA = gate SHA = request SHA = current local HEAD
reviewed code-state = gate code-state = request code-state = current code-state
```

After acceptance the planner runs `publish-review --repo OWNER/NAME`. It uses an
authorized `gh` CLI session to post a human-readable comment containing the reviewed
SHA, accepted five-section review, evidence and pending manual checks, then records
the URL. The reviewer can retry the same command during coordinated recovery.
Identical publication retries are idempotent; missing comment permission or failed
publication is a blocker, not permission to claim local-only completion.

The core controller remains standard-library Python with no GitHub dependency for
local operations. Only publication needs `gh` and permission to read the PR and
write its comment. It does not require native GitHub self-approval. Arbitrary comment
text cannot grant approval; the recorded publication makes the accepted local
verdict visible. New protocol-3 runs require that record before `finalize`. Success
is `phase: completed` with the verdict URL included in the final summary. No
automatic merge is part of the workflow.

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
pending work. Resume first validates the saved protocol markers and hashes; a
legacy or incompatible snapshot is rejected rather than silently replayed. Start
a new run, import old approved artifacts as references and revalidate them under
the current contract. Never rewrite historical evidence to make a legacy run look
current. Runtime task loss does not discard an accepted controller result.
See [orchestration.md](orchestration.md) for transport recovery and
[learning.md](learning.md) for durable finalization.

## Field lessons retained

The first live run exposed reporting-contract drift, missing dispatch IDs,
incomplete rubrics and conflicting log writes. Preserve exact request metadata,
five evidence sections, retryable tagged delivery, and one log per agent.
Push/PR permissions still come from the agent environment and user authorization;
the controller does not bypass them.
