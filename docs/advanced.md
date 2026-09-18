# Advanced setup and operation

This guide covers runtime guarantees, Orca and manual setup, recovery,
completion and contributing. For installation or updates, follow
[INSTALL.md](../INSTALL.md). Return to the [overview](../README.md) for a
short introduction.

A paired coding workflow for Codex, Claude Code and other agents with local tool
access. **Orca is optional:** the controller and Markdown protocol work with two
sessions in one shared worktree. Orca adds automatic session/worktree setup and
message delivery.

A planner/executor and a reviewer take a GitHub issue or feature brief through:

```
brief → spec review → plan review → implementation → gate → PR review → publish verdict → finalize
```

The agents handle design and review. A small Python controller validates the
artifacts, keeps recoverable run state, executes the configured checks, and accepts
PR review only for the current checked commit. Human intervention is required for
unresolved decisions or permissions that the environment has not already granted.
Plan approval continues to implementation by default. Stop at planning only when
the user explicitly requests that narrower deliverable; the word "plan" alone
does not turn an end-to-end run into a planning-only session.

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
| Portable file workflow | macOS or Linux, Python 3.9+, Git, Bash, two local agent sessions, repository checks |
| One-command launcher | Above, plus Orca ADE/CLI |
| Orca orchestration transport | Experimental orchestration enabled in Orca |
| PR creation and inspection | Authorized GitHub connector or CLI access |
| Verdict publication and finalization | Authorized `gh` CLI session with PR read/comment permission |
| Building the installable bundle | Above local tools, plus `zip` |

The controller uses the Python standard library. Its local checks protect
cooperating agents from mistakes; they are not an authentication boundary against
agents that can edit the same files. The reviewer verifies the remote PR head
through GitHub; the controller checks local HEAD and stored evidence and rechecks
the remote head when publishing the verdict. Planning, gates and local state
commands work offline; publication and finalization need GitHub access. Finalize
rechecks the remote HEAD and the published comment before completing a new run.
The publication command currently targets `github.com`; GitHub Enterprise hosts
are not configurable.

## Quick start with Orca

From the **target application repository**, with Orca connected and its agent CLIs
configured, create a new shared worktree and both role terminals:

```bash
cd /absolute/path/to/target-repository
export DUO_HOME="$HOME/.agents/skills/agent-duo"
export DUO_GATE='pnpm test:run && pnpm lint'
"$DUO_HOME/assets/duo.sh" --task 'Hide signup on the login page' --run-id login-a --new-worktree
```

Or use `--issue https://github.com/org/repo/issues/612 --run-id 612-a` instead of
`--task ... --run-id login-a`. Omit `--new-worktree` only when the current Orca
worktree already has both agent terminals. A Setup shell is not an agent terminal.
To run from source instead, set `DUO_HOME` to the clone and use its `bin/duo.sh`.

Use real gate commands for your repository; supply them via `--gate` or `DUO_GATE`.
There is no project-specific fallback test command. New runs require exactly one
of `--task` or `--issue`. Run IDs contain 1–64 letters/digits/underscores/hyphens
and start with a letter or digit.

The launcher validates protocol version, template role/transport markers, required
tokens, worktree and structured agent identities before sending anything. Protocol 2
comes from `duo-state.py protocol`; each canonical prompt has its HTML marker on
line 2. Keep the launcher, controller and templates from one bundle. New runs save
the original templates, their hashes, controller provenance and resolved prompts
alongside state, preserving the literal brief. Hashes cover the original template
snapshots; resume regenerates resolved prompts from those snapshots. The renderer
removes HTML comments, so resolved launcher output does not retain the marker.
Default roles are planner Claude and reviewer Codex; switch them with
`--planner codex --reviewer claude`. `--mode orchestration` is the default;
`--mode file` uses the same controller without native task signaling. **The
launcher still requires Orca in file mode** to find terminals and deliver prompts.
For two sessions outside Orca, use [the manual setup](#running-without-orca).

A new run normally gets branch `duo/<run_id>` from the resolved default base
(origin's configured remote HEAD, otherwise current HEAD), or a base explicitly supplied with `--base REF`. No develop
branch is assumed. `--new-worktree` creates a separate Orca worktree and retains
its feature branch. `--no-reset` preserves the current branch and cannot be combined
with `--base` or `--new-worktree`. Dirty/ambiguous state must be resolved instead of
discarded. Explicit `--planner-terminal HANDLE` and `--reviewer-terminal HANDLE`
resolve terminal ambiguity and are still checked for the correct agent/worktree.

## Progress and recovery

```bash
cd /absolute/path/to/the-run-worktree
export DUO_HOME="$HOME/.agents/skills/agent-duo"
python3 "$DUO_HOME/assets/duo-state.py" status --run-dir "$PWD/docs/agent-duo/runs/login-a"
"$DUO_HOME/assets/duo.sh" --resume --run-id login-a
```

The run directory keeps controller state, source/review artifacts, gate results,
resolved prompts and separate log-planner.md / log-reviewer.md files. Run artifacts
are normally gitignored and do not automatically join the code PR. Preserve this
directory when you need to resume or inspect evidence. Frontmatter is for the
run's protocol artifacts; do not add run metadata to README.md or application docs.

Resume refreshes runtime terminal handles and continues the saved phase. It does
not reset the branch or overwrite the run. It looks in the current worktree, so
resume from the worktree printed when the run was created. After escalation first
record the actual human ruling:

```bash
python3 "$DUO_HOME/assets/duo-state.py" resume \
  --run-dir "$PWD/docs/agent-duo/runs/login-a" \
  --reason 'the approved recovery decision'
```

A timeout or an edited comment is not approval. Sources already requested are immutable and
approved spec/plan stay frozen. A revised specification starts a new scoped run.
Resume also checks saved protocol markers and hashes. Incompatible legacy snapshots
are rejected: create a new run, import the old approved artifacts as references and
revalidate them. Preserve the original evidence instead of rewriting it to appear
current.

Manual runs do not have the launcher's `launcher.json`. For those runs, use
controller `status` and, when necessary, `resume --reason ...`, then give the saved
file-mode prompts to the two sessions again. Do not use `duo.sh --resume` for a
manually initialized run. Launcher resume keeps the saved gate, mode and roles;
it cannot change them through new launch flags.

Agents use bounded controller waits and meaningful progress heartbeats. There is
no 20-poll exit during a healthy long implementation. State and elapsed-time budgets
provide the stopping conditions; missed notifications do not erase pending work.

## Running without Orca

Use two agent sessions with shell/filesystem access in the same dedicated Git
worktree. Installation alone does not open either session. Ask `$agent-duo` or the
installed skill to prepare the file-mode prompts using that worktree and a real
gate; preparation outside Orca is manual, with no `duo prepare` command.

For explicit setup, resolve absolute paths and initialize a new run once:

```bash
cd /absolute/path/to/the-dedicated-worktree
export DUO_HOME="$HOME/.agents/skills/agent-duo"
duo_run="$PWD/docs/agent-duo/runs/login-a"
python3 "$DUO_HOME/assets/duo-state.py" protocol  # requires protocol_version 2
mkdir -p "$duo_run"
python3 "$DUO_HOME/assets/duo-state.py" init \
  --run-dir "$duo_run" --run-id login-a --worktree "$PWD" \
  --gate 'pnpm test:run && pnpm lint' --reviewer reviewer
```

Replace the example gate with your project's actual checks. Capture the work
statement verbatim in the run's brief.md. Fill
[skill/assets/planner.md](../skill/assets/planner.md) and
[skill/assets/reviewer.md](../skill/assets/reviewer.md): `RUN_ID`, absolute `RUNS_ROOT`
with a trailing slash, absolute `CONTROLLER`, actual `GATE_COMMANDS`,
`WORK_ITEM_BLOCK` and `SOURCE_OF_TRUTH_BLOCK`. Preserve literal work text rather
than recursively replacing braces inside it. Preserve each line-2 marker and
use matching protocol-2 templates and controller. Save the resolved prompts beside the
run state and give each to its assigned session. Both begin by reading `status`,
so correctness does not depend on which session starts first. Installed templates
are under `$DUO_HOME/assets/`; their controller is
`$DUO_HOME/assets/duo-state.py`. The leading `/loop` and `/goal` are session-specific
wrappers; use your agent's equivalent continued-task mechanism if it does not
support those commands, while retaining the role instructions and protocol marker.

The reviewer atomically publishes a review and calls `accept`. The planner reads
the controller's new phase, implements corrections and requests the next round.
The full CLI/schema is in [the protocol reference](../skill/references/protocol.md).

Keep `docs/agent-duo/runs/` out of code commits. Add that path to the target
repository's `.gitignore` or local `.git/info/exclude` before staging changes.

## Completion and learning

The PR request and review record GitHub's current base SHA and head SHA; use that
actual base for the diff instead of an assumed or stale local main. The final review
includes five evidence sections and `## Pending manual checks`, listing untested
acceptance checks or `None.`. Record device/zoom/screen-reader limitations honestly
and follow the approved acceptance policy for pending checks.
The PR request body must contain its complete URL, for example
`https://github.com/OWNER/NAME/pull/123`; publication checks it against `--repo` and
the recorded PR number.

After local PR review acceptance, publish the verdict and then finalize:

```bash
duo_run="$PWD/docs/agent-duo/runs/login-a"
python3 "$DUO_HOME/assets/duo-state.py" publish-review \
  --run-dir "$duo_run" --repo OWNER/NAME
python3 "$DUO_HOME/assets/duo-state.py" finalize \
  --run-dir "$duo_run" --lessons "$duo_run/lessons-proposals.json"
```

Publication verifies the live remote HEAD and uses gh to post the accepted review,
SHA, evidence and pending manual checks as a readable comment. It records the URL
and is idempotent on retry. It does not attempt native GitHub self-approval, and
arbitrary comment text cannot grant approval. A publication failure leaves the
run unfinished. New protocol-2 runs require recorded publication before `finalize`.

Finalization persists the completed-run ledger and reviewer proposals in local Git
ref `refs/agent-duo/learning`. Only then is the run completed; the final summary
links its published verdict. The memory commit is separate from the reviewed code, so it does not
create an unreviewed code change or dirty the worktree after approval. No automatic
PR merge or remote push of the memory ref is performed.

Read memory with controller `memory`. Lessons remain advisory: two distinct
completed runs confirm a pattern, five completed runs without confirmation make it
dormant, and a later confirmation reactivates it. Retain legacy tracked lesson
files as reference. Local memory is not included in the code PR; cross-machine
sharing of the ref is an explicit operation. See
[the learning reference](../skill/references/learning.md).

## Optional command wrappers

The [skill installation](../INSTALL.md) is sufficient. If you also use legacy slash-command
files, refresh them from the agent-duo clone after building so an old wrapper
cannot shadow the skill:

```bash
mkdir -p /path/to/repo/.claude/commands "$HOME/.codex/prompts"
cp dist/claude-commands/*.md /path/to/repo/.claude/commands/
cp dist/codex-prompts/*.md ~/.codex/prompts/
```

`/agent-duo` delegates to the same deterministic launcher; it does not implement a
second launch protocol. The reviewer fallback loads the run's existing
reviewer.resolved.txt only after checking its protocol and saved hashes, rather
than reconstructing another version of its contract.

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
and mocked Orca/GitHub boundaries; they do not launch real agents or publish PRs.
Before adopting a new Orca/IDE version, verify a throwaway handshake in that
specific environment. Useful field findings include stale evidence, false blocks,
missing criteria, timeouts and recovery behavior.
