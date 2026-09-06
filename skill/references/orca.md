# Launching and resuming in Orca

The one launcher is `bin/duo.sh` in a checkout or `assets/duo.sh` in the built
skill. It uses Bash, Python 3.9+, Git and the Orca CLI on macOS/Linux. Enable experimental orchestration
in Orca for orchestration mode; `--mode file` uses controller-backed file signaling.
Read the current Orca CLI guide for your installed version before manual commands.
Publishing the final verdict additionally needs an authorized gh CLI session with
PR read/comment permission; the local controller operations do not.

## Isolation and identity

Both agents use the same run worktree, with a separate terminal for each role.
Runs use distinct directories and branches. The launcher checks the exact worktree
and structured agent identity, plus terminal writability/connectivity; it does not
select a terminal by position, title or preview. Explicit terminal handles are
still validated. An ambiguous selection needs `--planner-terminal HANDLE` and/or
`--reviewer-terminal HANDLE` rather than guessing.

Terminal handles are runtime-scoped. On restart use `--resume --run-id ID` to
refresh identities and use durable controller state. Do not manually replace a
handle in an old review: read the assigned reviewer in current controller status.

## Git behavior

A new run normally uses `duo/<run_id>` from a resolved base (`--base REF` overrides
origin's configured remote HEAD, otherwise current HEAD); no branch named develop is assumed. The
launcher refuses unsafe/dirty state before sending prompts. `--new-worktree`
creates a new Orca worktree and retains its created feature branch.
`--no-reset` preserves the existing branch; combine it with neither `--base` nor
`--new-worktree`. Existing work and unrelated run folders must not be discarded.
A resume does not reset the branch or silently overwrite an existing run.

## Examples

```bash
export DUO_GATE='pnpm test:run && pnpm lint'
duo --task 'Hide signup on the login page' --run-id login-a
duo --issue https://github.com/org/repo/issues/612 --run-id 612-a
duo --task '...' --run-id login-b --planner codex --reviewer claude
duo --task '...' --run-id login-c --mode file --no-reset
duo --resume --run-id login-a
```

The gate must be an explicit real command (`--gate` or `DUO_GATE`) appropriate to
the target repository. Run IDs are 1–64 characters: start with a letter/digit,
then letters, digits, underscores or hyphens. Select work with exactly one of
`--task` or `--issue` for a new run; a resume reuses saved work and configuration.

## Startup, artifacts and recovery

The launcher resolves paths and performs protocol and Git/runtime preflight
before delivery. `duo-state.py protocol` must report protocol_version 2; all four
canonical templates keep their exact protocol/role/transport marker on line 2.
Required template tokens and saved hashes are validated to reject mixed or modified
bundles. The launcher initializes the controller, writes the literal brief if
needed, renders canonical templates and sends them to validated agents. Resolved prompts and launcher metadata stay with
the run, alongside controller state and separate agent logs. User text is data:
braces and line breaks must not be interpreted as template instructions.

Reviewer-first startup is convenient, but correctness does not depend on observing
a file's creation event. Each agent begins with `status` and processes pending
work, even when its notification was missed. Controller `wait` blocks outside the
LLM in bounded calls and heartbeat records real progress.

After escalation, record a human ruling with controller `resume --reason TEXT`,
then use the launcher resume to restore live sessions if necessary. A mere terminal
restart does not erase an unresolved decision. A legacy or incompatible saved
snapshot cannot resume: initialize a new run, import the approved artifacts as
references and revalidate them under the current protocol. Preserve the original
evidence rather than rewriting its provenance. For a compatible run, recreate
runtime tasks for pending controller requests; do not restart at spec-v1.

`log-planner.md` and `log-reviewer.md` are agent notes. Controller state and gate
records are the source for accepted transitions. No log prose or magic PR comment
is a substitute for a successful controller action. End-to-end runs continue
after plan approval through `publish-review --repo OWNER/NAME` and `finalize`.
The published GitHub comment contains the accepted SHA, review evidence and pending
manual checks; completion requires its recorded URL. A planning-only stop requires
an explicit user request and is reported as that narrower deliverable.
