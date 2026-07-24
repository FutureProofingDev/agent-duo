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

## Quick start

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
bin/duo.sh          the launcher (one script, both agents, both transports)
prompts/            prompt templates: planner/reviewer x file/orchestration mode
references/         protocol spec, orchestration mapping, Orca CLI notes
claude/SKILL.md     Claude skill instructions
codex/AGENTS.md     what a Codex agent reads on session start
build.sh            assembles dist/agent-duo.skill from the above
dist/               GENERATED, never edit
```

Single source of truth per file. Claude and Codex read instructions from
different places, which is why `claude/` and `codex/` both exist, but they point
at the same `references/` and `prompts/`.

## Installing the Claude skill

```bash
./build.sh
cp -r dist/agent-duo ~/.claude/skills/     # Claude Code
```

Or upload `dist/agent-duo.skill` in the Claude app and click Save skill. Rebuild
after changing anything under `references/`, `prompts/`, `bin/`, or
`claude/SKILL.md`.

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
