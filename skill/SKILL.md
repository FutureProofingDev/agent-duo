---
name: agent-duo
description: Set up a paired planner/executor and reviewer workflow for a GitHub issue, bug report or feature brief. Generate or launch the two prompts with a durable Python controller that manages spec, plan, gate and exact-commit PR reviews. Use when the user asks for an agent duo, paired review loop, duo prompts or the agent-duo workflow. Either model can fill either role.
---

# Agent Duo

Two agents take a work item through reviewed spec, reviewed plan, implementation,
checks, exact-commit PR review, published verdict and durable finalization. The agents supply technical
judgment; `duo-state.py` controls the transitions. Brainstorming remains outside
this workflow and can provide its initial brief. Unless explicitly asked for
planning only, continue after plan approval through implementation and published
PR review. Do not infer a planning-only restriction from the word "plan".

## Inputs and defaults

Use information and authorization already provided. Ask once for genuinely missing
work or a gate command; do not generate a runnable prompt containing a fake gate.

- Work item: a GitHub issue URL or a literal pasted description/brainstorm result.
- Role assignment: honor the user's choice. Launcher defaults are planner Claude,
  reviewer Codex; use different models where practical without promising statistical
  independence. Either direction is supported.
- Run ID: a fresh 1–64 character ID, starting with a letter/digit and continuing
  with letters/digits/underscores/hyphens. Suggest `612-a` for an issue or a short
  work slug with a retry suffix. Do not overwrite an existing run to retry.
- Gate: real repository commands from the user, repository instructions or
  `DUO_GATE`, passed through `--gate` when needed. No placeholder is a valid gate.
- Transport: the launcher defaults to `orchestration` in Orca. Use `file` for
  manual portable sessions or when explicitly chosen. Both require macOS/Linux,
  Python 3.9+ and Git. Final verdict publication additionally needs an authorized
  gh CLI session with permission to read the PR and write its comment.
- Run folder root: `docs/agent-duo/runs/`, resolved within the run worktree.

A brief is captured verbatim by the launcher in brief.md. In manual setup create
it before planning. For an issue, both agents read the full source. The spec review
checks that the derived criteria faithfully cover the source without invented scope.

## Prefer the launcher for execution

In a checkout use `bin/duo.sh`; in the installed built skill use `assets/duo.sh`.
Both use the same canonical prompt assets and packaged controller. Locate the
actual executable before invoking it; do not assume the skill is a repository.
Install one complete bundle: `duo-state.py protocol` reports protocol_version 2,
and every canonical template keeps its exact line-2 protocol/role/transport marker.

```bash
/path/to/duo.sh --task 'Hide signup on the login page' --run-id login-a --gate 'pnpm test:run && pnpm lint'
/path/to/duo.sh --issue https://github.com/org/repo/issues/612 --run-id 612-a
/path/to/duo.sh --resume --run-id login-a
```

The launcher performs protocol/version/token/hash preflight, initializes the
durable controller, resolves exact worktree/agent identities, fills prompts once
and saves resolved prompts with hashes. Incompatible legacy resume snapshots are
rejected. Initialize a new run, import old approved artifacts as references and
revalidate; do not rewrite historical evidence to make it look current. It does
not use terminal titles/previews to guess the receiving agent. Ambiguity requires
explicit `--planner-terminal` / `--reviewer-terminal` handles. Failed preflight must
not send a prompt or erase existing work. See [references/orca.md](references/orca.md)
for branch behavior, flags and resume.

## Generating prompts for manual sessions

1. Read [references/protocol.md](references/protocol.md). For Orca also read
   [references/orchestration.md](references/orchestration.md).
2. Resolve one dedicated worktree and absolute run/controller paths. The controller
   is `bin/duo-state.py` in the checkout or `assets/duo-state.py` in the built skill.
   Run `python3 /absolute/path/duo-state.py protocol` without run arguments and
   require protocol_version 2. Create the run directory, exclude it from code commits, and initialize
   once with `init --run-dir PATH --run-id ID --worktree PATH --gate
   COMMAND --reviewer IDENTITY`. In file mode use a stable identity such as reviewer;
   both templates read it from controller status.
3. Fill [assets/planner.md](assets/planner.md) and
   [assets/reviewer.md](assets/reviewer.md) for file mode, or the corresponding
   `planner-orca.md` / `reviewer-orca.md` for orchestration. Fill `RUN_ID`, `RUNS_ROOT`
   (absolute path with trailing slash), `CONTROLLER` (absolute path), `GATE_COMMANDS`,
   `WORK_ITEM_BLOCK` and `SOURCE_OF_TRUTH_BLOCK`. The last two describe the actual
   issue or existing brief. Orca templates additionally need current terminal handles.
   Preserve the exact line-2 marker and literal work text; do not perform
   recursive substitution in user text. Do not mix template/controller versions.
4. Save planner.resolved.txt and reviewer.resolved.txt in the run directory and
   present the two prompts labeled by role and model. Current Codex and Claude Code
   both use `/goal`, with a 4,000-character objective limit. Give each a short goal
   that names its saved instructions and requires controller completion with the
   published verdict URL, or the explicitly requested planning-only deliverable.
   Require reading the file in full; do not paste the full protocol into `/goal`
   or use `/loop`, which schedules repetition in Claude Code. For other clients,
   use their supported continued-task mechanism. Both roles begin with controller
   status, so already-published work remains discoverable.
5. When asked to launch, carry out the available authorized launch steps rather
   than merely printing prompts. When asked only for prompts, stop after supplying
   them with the initialization command and concrete paths.

There are no separate launch.sh / launch-orca.sh templates. Do not invent missing
assets or duplicate the launcher logic in a slash-command body.

## Invariants

- One run, one worktree shared by both agents. Existing versions are immutable.
- Spec precedes plan; accepted spec/plan remain frozen. A changed specification
  needs human scoping and a new run.
- Run metadata/frontmatter applies to protocol artifacts in the run directory,
  not README.md or application documentation. Preserve their native format.
- Publish sources/reviews atomically. `request` records source hash and request ID;
  `accept` validates those plus run, round, reviewer and five numbered sections.
- Every artifact type has five explicit review criteria, including PR. Evidence
  and technical completeness determine the verdict; style and optional work do not.
- Gate execution is controller-owned and bound to clean HEAD. Each code change
  requires a new commit, gate and PR review for the new SHA. Record GitHub's
  current base SHA and head SHA; review against that base rather than stale local
  main. The reviewer checks remote HEAD; publication checks it again.
- Final PR reviews include `## Pending manual checks` with untested acceptance
  checks/limitations or `None.`. Follow the approved acceptance policy and disclose
  these pending checks in the published GitHub verdict.
- Messages and GitHub comments convey information. Only accepted controller state
  advances the workflow. Successful delivery retries are idempotent.
- Controller deadlines replace poll-count exits. Start with status, wait in bounded
  calls and heartbeat real progress. Preserve state for resume and human rulings.
- Reviewer publishes learning proposals before its final PR acceptance. Planner
  calls `publish-review --repo OWNER/NAME`, then finalize. Publication is an
  idempotent SHA-specific comment, not native self-approval or magic approval text.
  New protocol-2 runs finish only when status reports completed with a recorded
  publication URL; include that link in the final summary.

## Learning and limits

[references/learning.md](references/learning.md) describes the local Git ref
`refs/agent-duo/learning`: evidence-backed proposals, confirmation in two distinct
completed runs, decay after five unconfirmed completed runs, and reactivation.
The durable ledger is per repository and advisory. It does not dirty approved code
or silently join its PR, and it is not pushed remotely without explicit intent.
Keep legacy lesson files as reference material.

This controller protects cooperating agents from stale evidence and lifecycle
mistakes; it does not authenticate agents sharing filesystem permissions. A gate
is only as meaningful as the commands configured. External pushes, GitHub comments
and PR creation still follow user authorization and environment permissions.

Run a throwaway handshake before relying on a new IDE/Orca version. Customize the
rubric with real evidence, and change controller behavior/tests together when
changing lifecycle rules; deleting a prompt phase cannot bypass controller order.
