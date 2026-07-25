# agent-duo

An automated **planner/executor + reviewer** loop. Point it at any work item, a
GitHub issue, a bug report, or a pasted feature idea, and two agents take it
through:

```
brief → SPEC (approved) → PLAN (approved) → execute → gate → PR (approved)
```

with no human in the middle except at escalation points.

## Why it works

- **Decorrelated pair.** The coder and reviewer are different models, so they
  fail differently and the reviewer catches what the coder waves through. Roles
  are flags, not repos: either model can plan or review.
- **Spec before plan.** The spec review asks "is this the right thing to build?";
  the plan review asks "is this the right way to build it?". Collapsing them is
  where scope creep hides.
- **A deterministic gate.** Tests, lint, and build must pass between plan
  approval and PR. LLMs review design; the harness reviews quality.
- **Filesystem as record.** Every artifact is a markdown file with YAML
  frontmatter in a per-run folder, so a run is diffable, committable, and
  debuggable after the fact.

## Requirements

The workflow itself needs no particular IDE. Two capabilities are separate:

| You want | You need |
|---|---|
| The loop (prompts, artifacts, rubrics, gate) | any two agent sessions, nothing else |
| `duo` one-command launch | Orca ADE + its CLI + `jq` |
| Orchestration transport (blocking waits, no polling) | Orca ADE + Settings -> Experimental -> Orchestration |

Without Orca you lose the launcher and the blocking waits, not the workflow.
See "Running it without Orca" below.

## Quick start (with Orca)

```bash
git clone git@github.com:FutureProofingDev/agent-duo.git ~/src/agent-duo
export DUO_HOME=~/src/agent-duo
export DUO_GATE="pnpm test:run && pnpm lint"
ln -s $DUO_HOME/bin/duo.sh /usr/local/bin/duo

duo --task "hide signup in login page" --run-id b
duo --issue https://github.com/org/repo/issues/612 --run-id 612-a
duo --task "..." --run-id c --planner codex --reviewer claude
```

`duo` resets the branch, resolves runtime-scoped terminal handles, fills both
prompt templates, and sends them reviewer-first (the coordinator cannot dispatch
to an agent that is not up yet).

Watch a run:

```bash
orca orchestration task-list --json | jq '.result.tasks[] | select(.task_title | contains("run b"))'
tail -f <worktree>/docs/superpowers/runs/b/log-planner.md
```

## Layout

```
skill/              the portable SKILL.md skill (works in Claude Code, Codex,
  SKILL.md            Cursor, any SKILL.md-aware agent)
  assets/             prompt templates (planner/reviewer x file/orca)
  references/         protocol spec, orchestration mapping, Orca CLI notes
  agents/openai.yaml  Codex invocation policy (explicit-only)
bin/duo.sh          the shell launcher (Orca)
commands/, templates/  sources for the optional Orca slash commands
codex/AGENTS.md     read by a Codex agent that IS a duo agent mid-run
build.sh            packages skill/ and assembles slash commands
dist/               GENERATED, never edit
```

`SKILL.md` is an open standard, not Anthropic-specific, so ONE skill folder
serves every agent. Only the install location differs. `codex/AGENTS.md` is a
different thing: it is what a Codex process reads when it is itself one of the
two running agents, not how a human starts a run.

## Installing the skill

`./build.sh` first, then install the same skill folder wherever you need it:

| Agent | Location |
|---|---|
| Claude app | upload `dist/agent-duo.skill`, click Save skill |
| Claude Code | `cp -r dist/agent-duo ~/.claude/skills/` |
| Codex (personal) | `cp -r dist/agent-duo ~/.agents/skills/` |
| Codex (per-repo, shared) | `cp -r dist/agent-duo .agents/skills/` and commit |

Codex reads skills from `.agents/skills/` (the cross-agent standard path), NOT
`~/.codex/skills/`. In Codex, invoke with `$agent-duo` or browse `/skills`; it is
explicit-only, so a stray prompt never triggers it. Restart the agent after
installing so it loads. Rebuild after editing anything under `skill/`.

## Running it without Orca

Open two agent sessions in the same working directory. This matters: the agents
coordinate through files, so separate checkouts break the handshake with no
error.

1. Copy `prompts/reviewer.md` and `prompts/planner.md`.
2. Replace the `{{PLACEHOLDER}}` values by hand: `{{RUN_ID}}`,
   `{{RUNS_ROOT}}` (e.g. `docs/superpowers/runs/`), `{{GATE_COMMANDS}}`, and
   either the issue fields or `{{WORK_ITEM_TEXT}}`. Each template has two
   commented variants, issue-backed and brief-backed; keep the matching one and
   delete the other. `{{PLANNER_HANDLE}}` / `{{REVIEWER_HANDLE}}` are
   orchestration-only, so ignore them here.
3. Paste the reviewer prompt first and let it settle, then the planner. The
   reviewer must be watching the folder before the first artifact lands, or
   nothing picks it up.

From there it is identical: same artifacts, same rubrics, same gate. The agents
poll the run folder instead of receiving dispatches, and each gives up after 20
empty polls so a stalled run does not burn tokens overnight.

## Slash commands (Orca, one-shot from inside an agent)

If you would rather not use the shell launcher, run the whole thing from inside
Claude Code or Codex:

```
/agent-duo --task "hide signup in login page" --run-id b
```

The command resolves the peer terminal, launches the reviewer there, then adopts
the planner role in the current terminal. Like `duo.sh` it needs the `orca` CLI,
since it still drives a second terminal; the difference is you invoke it from
inside the agent instead of a shell.

Install (run `./build.sh` first):

```bash
cp dist/claude-commands/*.md  <repo>/.claude/commands/    # or ~/.claude/commands/
cp dist/codex-prompts/*.md    ~/.codex/prompts/
```

`agent-duo-review` is a fallback for starting the reviewer by hand if
auto-launch mis-resolves the peer terminal.

## Transport modes

- **file** (default, portable): agents poll the run folder. Works in any IDE.
- **orchestration** (Orca, experimental): coordinator/worker dispatches and
  blocking waits. No polling and no wasted tokens; timeouts become checkpoints
  rather than guesses. See `references/orchestration.md`.

Same protocol and artifacts either way; only the signaling changes.

## Before your first run

1. **Dry-run on a throwaway task.** The weak link is whether the IDE actually
   wakes each agent.
2. **Set real gate commands.** The planner treats whatever is in the gate as the
   ship condition, so a placeholder means shipping unverified code.
3. **Both agents share ONE worktree.** Git worktrees are separate directories,
   so splitting them breaks the artifact handshake and stalls with no error.

## Contributing

The reviewer rubric is the part most worth tuning with real data.
`references/protocol.md` ends with field findings from live runs; add to it. If
you run this, open a PR with what you learned from your run logs: rounds burned,
false blocks, misses.
