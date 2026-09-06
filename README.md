# agent-duo

A planner/executor and a reviewer take a GitHub issue or feature brief through:

```
brief → spec review → plan review → implementation → gate → PR review → finalize
```

The agents handle design and review. A small Python controller validates the
artifacts, keeps recoverable run state, executes the configured checks, and accepts
PR review only for the current checked commit. Human intervention is required for
unresolved decisions or permissions that the environment has not already granted.

## What it preserves

- Separate spec and plan reviews keep scope and implementation decisions explicit.
- Any supported model can take either role; using different models can bring
  different perspectives without guaranteeing independent errors.
- Markdown reviews contain five criteria with evidence. Style and optional
  improvements do not block approval.
- Immutable versions, exact source hashes and per-run worktrees prevent accidental
  reuse of old artifacts. Both agents share the worktree for their run.
- Gate and PR approval are bound to one commit. Every code correction needs new
  gate evidence and review; a comment containing an approval phrase cannot finish it.

## Requirements

| Capability | Requirements |
|---|---|
| Portable file workflow | macOS or Linux, Python 3.9+, Git, two local agent sessions, repository checks |
| One-command launcher | Above, plus Bash and Orca ADE/CLI |
| Orca orchestration transport | Experimental orchestration enabled in Orca |
| PR comments and creation | Authorized GitHub connector or CLI access |

The controller uses the Python standard library. Its local checks protect
cooperating agents from mistakes; they are not an authentication boundary against
agents that can edit the same files. The reviewer verifies the remote PR head
through GitHub, while the controller checks local HEAD and stored evidence.

## Quick start with Orca

```bash
git clone https://github.com/FutureProofingDev/agent-duo.git /path/to/agent-duo
export DUO_HOME=/path/to/agent-duo
export DUO_GATE='pnpm test:run && pnpm lint'
/path/to/agent-duo/bin/duo.sh --task 'Hide signup on the login page' --run-id login-a
/path/to/agent-duo/bin/duo.sh --issue https://github.com/org/repo/issues/612 --run-id 612-a
```

Use real gate commands for your repository; supply them via `--gate` or `DUO_GATE`.
There is no project-specific fallback test command. New runs require exactly one
of `--task` or `--issue`. Run IDs contain 1–64 letters/digits/underscores/hyphens
and start with a letter or digit.

The launcher validates the worktree and structured agent identities before sending
anything, initializes run state, saves resolved prompts and preserves the literal
brief. Default roles are planner Claude and reviewer Codex; switch them with
`--planner codex --reviewer claude`. `--mode orchestration` is the default;
`--mode file` uses the same controller without native task signaling.

A new run normally gets branch `duo/<run_id>` from the resolved default base
(origin's configured remote HEAD, otherwise current HEAD), or a base explicitly supplied with `--base REF`. No develop
branch is assumed. `--new-worktree` creates a separate Orca worktree and retains
its feature branch. `--no-reset` preserves the current branch and cannot be combined
with `--base` or `--new-worktree`. Dirty/ambiguous state must be resolved instead of
discarded. Explicit `--planner-terminal HANDLE` and `--reviewer-terminal HANDLE`
resolve terminal ambiguity and are still checked for the correct agent/worktree.

## Progress and recovery

```bash
python3 /path/to/agent-duo/bin/duo-state.py status --run-dir /worktree/docs/agent-duo/runs/login-a
/path/to/agent-duo/bin/duo.sh --resume --run-id login-a
```

The run directory keeps controller state, source/review artifacts, gate results,
resolved prompts and separate log-planner.md / log-reviewer.md files. Run artifacts
are normally gitignored and do not automatically join the code PR. Preserve this
directory when you need to resume or inspect evidence.

Resume refreshes runtime terminal handles and continues the saved phase. It does
not reset the branch or overwrite the run. After escalation first record the human
ruling with controller `resume --reason 'the approved recovery decision'`; a timeout
or an edited comment is not approval. Sources already requested are immutable and
approved spec/plan stay frozen. A revised specification starts a new scoped run.

Agents use bounded controller waits and meaningful progress heartbeats. There is
no 20-poll exit during a healthy long implementation. State and elapsed-time budgets
provide the stopping conditions; missed notifications do not erase pending work.

## Running without Orca

Use two agent sessions in the same dedicated worktree. Resolve absolute paths and
initialize a new run once:

```bash
mkdir -p /worktree/docs/agent-duo/runs/login-a
python3 /path/to/agent-duo/bin/duo-state.py init   --run-dir /worktree/docs/agent-duo/runs/login-a --run-id login-a   --worktree /worktree --gate 'your test, lint and build commands' --reviewer reviewer
```

Capture the work statement verbatim in the run's brief.md. Fill
[skill/assets/planner.md](skill/assets/planner.md) and
[skill/assets/reviewer.md](skill/assets/reviewer.md): `RUN_ID`, absolute `RUNS_ROOT`
with a trailing slash, absolute `CONTROLLER`, actual `GATE_COMMANDS`,
`WORK_ITEM_BLOCK` and `SOURCE_OF_TRUTH_BLOCK`. Preserve literal work text rather
than recursively replacing braces inside it. Save the resolved prompts beside the
run state and give each to its assigned session. Both begin by reading `status`,
so correctness does not depend on which session starts first.

The reviewer atomically publishes a review and calls `accept`. The planner reads
the controller's new phase, implements corrections and requests the next round.
The full CLI/schema is in [the protocol reference](skill/references/protocol.md).

Keep `docs/agent-duo/runs/` out of code commits. Add that path to the target
repository's `.gitignore` or local `.git/info/exclude` before staging changes.

## Completion and learning

After final PR review acceptance, `finalize` persists the completed-run ledger and
reviewer proposals in local Git ref `refs/agent-duo/learning`. Only then is the run
completed. The memory commit is separate from the reviewed code, so it does not
create an unreviewed code change or dirty the worktree after approval. No automatic
PR merge or remote push of the memory ref is performed.

Read memory with controller `memory`. Lessons remain advisory: two distinct
completed runs confirm a pattern, five completed runs without confirmation make it
dormant, and a later confirmation reactivates it. Retain legacy tracked lesson
files as reference. Local memory is not included in the code PR; cross-machine
sharing of the ref is an explicit operation. See
[the learning reference](skill/references/learning.md).

## Install the skill and commands

Run `./build.sh`, then install the resulting skill folder:

| Agent | Installation |
|---|---|
| Claude app | Upload `dist/agent-duo.skill` |
| Claude Code | Copy `dist/agent-duo` to `~/.claude/skills/` |
| Codex personal | Copy `dist/agent-duo` to `~/.agents/skills/` |
| Codex repository | Copy `dist/agent-duo` to `.agents/skills/` and commit |

In Codex invoke `$agent-duo`; the skill's invocation policy is explicit-only.
Reload the agent after installing. The built skill includes executable
`assets/duo.sh` and `assets/duo-state.py` as well as all four canonical prompts.

Optional slash-command installations after building:

```bash
cp dist/claude-commands/*.md /path/to/repo/.claude/commands/
cp dist/codex-prompts/*.md ~/.codex/prompts/
```

`/agent-duo` delegates to the same deterministic launcher; it does not implement a
second launch protocol. The reviewer fallback loads the run's existing
reviewer.resolved.txt rather than reconstructing another version of its contract.

## Repository layout and contributing

```
skill/assets/       canonical planner/reviewer prompts for file and Orca modes
skill/references/   protocol, transport, launcher and learning documentation
skill/SKILL.md      skill entrypoint
bin/duo.sh          validated Orca launcher and literal renderer
bin/duo-state.py    durable standard-library controller
commands/          optional slash-command sources
codex/AGENTS.md     guidance for Codex while participating in a run
build*.sh          package the skill and command artifacts
tests/             controller, launcher and packaging regression tests
dist/              generated installation artifacts
```

Edit canonical assets and rebuild; do not maintain copied reviewer bodies in
parallel template trees. Run `python3 -m unittest discover -s tests` and `./build.sh`
after implementation changes. Regression tests use disposable Git repositories
and mocked Orca boundaries; they do not launch real agents or publish PRs.
Before adopting a new Orca/IDE version, verify a throwaway handshake in that
specific environment. Useful field findings include stale evidence, false blocks,
missing criteria, timeouts and recovery behavior.
