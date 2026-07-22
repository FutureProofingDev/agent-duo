# agent-duo

A Claude skill that generates paired prompts for an automated **planner/executor + reviewer**
workflow. Point it at any work item — a GitHub issue, a bug report, a pasted feature idea —
and it produces two prompts you drop into two agents. They then run:

```
brief → SPEC (approved) → PLAN (approved) → execute → gate → PR (approved)
```

with no human in the middle except at escalation points.

## Why it works

- **Decorrelated pair.** The coder and reviewer are different models (different vendors,
  different training), so they fail differently. The reviewer catches what the coder waves
  through. Roles are swappable: Opus plans + Sol reviews, or the inverse.
- **Spec before plan.** The spec review asks "is this the right thing to build?"; the plan
  review asks "is this the right way to build it?". Collapsing them is where scope creep hides.
- **A deterministic gate.** Tests, lint, and build must pass between plan approval and PR.
  LLMs review design; the harness reviews quality.
- **Filesystem as protocol.** No shared memory or direct messaging. Agents coordinate through
  markdown files with YAML frontmatter in a per-run folder.

## Install

**Claude.ai / desktop:** download `agent-duo.skill`, upload it into any chat, click
"Save skill" (or add it from Settings → Skills).

**Claude Code:** copy the skill folder into your skills directory.

```bash
cp -r skills/agent-duo ~/.claude/skills/          # user-level
cp -r skills/agent-duo .claude/skills/            # project-level
```

## Use

Ask Claude in plain language:

```
generate the duo prompts for issue #612
arma el duo: Sol planifica, Opus revisa. El feature es: <descripción>
```

It collects what's missing (role assignment, run_id, gate commands) and outputs both prompts
ready to paste into your agents.

## Before your first real run

1. **Dry-run the handshake** on a throwaway task. The weak link is whether your IDE's polling
   actually wakes each agent on file changes. Watch `log.md` from both sides.
2. **Set real gate commands.** The planner treats whatever is in the gate as the ship condition.

## Repo layout

```
skills/agent-duo/
  SKILL.md                    triggering + generation workflow
  references/protocol.md      artifact protocol (frontmatter, filenames, state machine)
  assets/planner-prompt.md    planner/executor template
  assets/reviewer-prompt.md   reviewer template
agent-duo.skill               packaged, installable bundle
```

## Codex side

The equivalent for Codex-driven agents lives in
[`agent-duo-codex`](https://github.com/FutureProofingDev/agent-duo-codex).
Both repos implement the **same protocol** — see `references/protocol.md` here and
`PROTOCOL.md` there. If you change the protocol, change it in both, or the handshake breaks.

## Contributing

The reviewer rubric is the part most worth tuning with real data. If you run this, open a PR
with what you learned from your `log.md` (rounds burned, false blocks, missed issues).
