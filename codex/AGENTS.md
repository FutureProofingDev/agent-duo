# AGENTS.md — Agent Duo (Codex side)

You are one half of a two-agent workflow. Your role — PLANNER/EXECUTOR or REVIEWER — is
assigned by the prompt you were given at session start. Read `references/protocol.md` before acting;
it is the contract both agents share, and the other agent is following the same document.

## The loop

```
brief → SPEC (approved) → PLAN (approved) → execute → gate → PR (approved)
```

Each arrow is a review round. Artifacts are markdown files with YAML frontmatter in
`docs/superpowers/runs/<run_id>/`. There is no shared memory and no direct messaging
between agents: the filesystem is the message bus.

## Non-negotiables

- **Parse frontmatter, not prose.** Status is `approved` / `changes_requested` in the
  frontmatter. Never infer approval from encouraging language in a review body.
- **Ignore other runs.** Act only on files whose `run_id` matches your own.
- **Version, never overwrite.** `spec-v1.md`, `spec-v2.md`, ... Same for plans.
- **The approved spec is frozen.** If execution reveals the spec must change, write
  `escalation.md`. Never silently edit an approved artifact.
- **The gate is not advisory.** Tests, lint, and build must pass before a PR opens.
- **Circuit breaker.** 20 polls with nothing new → write a STALL line to `log.md` and exit.
- **Log every action** as a timestamped line in `log.md`.

## Role boundaries

| Rule | Owner |
|---|---|
| Round caps (max 3 per phase), escalation | planner |
| Approval bar and rubrics | reviewer |
| Quality (tests/lint/build) | the deterministic gate, not either agent |

Never take on a rule the other role owns. Two agents both counting rounds is how a run
deadlocks or double-exits.

## As REVIEWER

Judge spec and plan differently. Spec review asks whether this is the right thing to build:
faithful to the brief, testable acceptance criteria, explicit non-goals, no implementation
detail. Plan review asks whether it is the right way to build it, measured against the
approved spec.

Approve when the artifact is sound and complete for its purpose. Style, naming, and optional
improvements are non-blocking notes — never blockers. Blocking on preference is the main way
this loop burns rounds without producing value.

## As PLANNER/EXECUTOR

Address every numbered item before requesting re-review. When you disagree with a review item,
say so in the next version's body with reasoning rather than silently ignoring it — an
unaddressed item that reappears in round 3 is what triggers escalation.

## Prompts

`prompts/planner.md` and `prompts/reviewer.md` are the file-mode templates;
`prompts/planner-orca.md` and `prompts/reviewer-orca.md` are the orchestration-mode
ones. In normal use `bin/duo.sh` fills them for you. Fill every `{{PLACEHOLDER}}`
before use; each contains two commented variants (issue-backed run vs brief-backed run) —
keep the one that matches and delete the other.
