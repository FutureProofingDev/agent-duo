---
name: agent-duo
description: Generate paired prompts for an automated two-agent planner/reviewer workflow in Orca ADE (or any multi-agent IDE) that takes any work item — a GitHub issue, a pasted bug report, a feature description, or a brand-new feature idea — from spec to approved PR with zero human intervention between checkpoints. One agent plans and executes, a second decorrelated agent reviews plans and PRs; either model can take either role (Opus planning + Sol reviewing, Sol planning + Opus reviewing, any pair). Coordination happens through frontmatter-tagged markdown files in a per-run folder. Use this skill whenever the user wants to set up an agent duo, agent pair, planner/reviewer loop, automated code review loop, multi-agent workflow for an issue/bug/feature, or says things like "arma el duo para esto", "generate the duo prompts", "run the two-agent loop", or mentions cr-*.md / prr-*.md handshake files.
---

# Agent Duo: Planner + Reviewer Loop

Generates the two prompts that drive an automated planner/executor + reviewer
pair working any work item through spec → plan → execute → approved PR.
The spec phase judges the WHAT (right thing to build), the plan phase judges
the HOW (right way to build it) — each is a separately reviewed and approved
artifact. Brainstorming stays outside the duo: it is human-driven and
divergent; its output becomes the brief that seeds the run. The agents coordinate
through markdown files with YAML frontmatter in a per-run folder. No shared
memory, no direct messaging: the filesystem is the protocol.

## What the user must provide

Collect these before generating. If any are missing, ask once, concisely:

1. **Work item** — any ONE of:
   - A GitHub issue URL
   - A pasted description of a bug, problem, or feature
   - A rough idea for a brand-new feature ("we need X")
   See "Work item handling" below for how each shapes the prompts.
2. **Role assignment** — which model is PLANNER/EXECUTOR and which is REVIEWER.
   The roles are model-agnostic: Opus planning + Sol reviewing works, and so
   does the inverse. If the user doesn't say, ask — never assume a default
   direction. The only requirement worth stating: the pair should be
   decorrelated (different vendors/training) so their failure modes differ.
3. **run_id** — default: `<issue-number>-a` when there's an issue, otherwise a
   short kebab slug of the work item + `-a` (e.g. `email-dedup-a`).
   Increment the letter for retries.
4. **Runs folder root** — default: `docs/superpowers/runs/`
5. **Deterministic gate command(s)** — the test/lint/build commands that must
   pass before a PR opens. If unspecified, insert a placeholder
   `<GATE: tests + lint + build commands here>` and tell the user to fill it in.

## Work item handling

The protocol is identical in all cases; only the source of truth changes.

- **GitHub issue**: the issue is the source of truth. The planner reads it;
  the reviewer's rubric checks the plan against the issue's acceptance criteria.
- **Pasted description / new feature (no issue)**: capture the user's text
  verbatim into a `brief.md` (type: brief) that the generated planner prompt
  instructs the agent to write as its first action, quoting the work statement
  exactly. The planner derives explicit acceptance criteria in the SPEC phase,
  and the spec review's first rubric item judges whether those criteria are a
  faithful, complete reading of the brief without invented scope. This makes
  the criteria themselves a reviewed artifact — crucial when no human wrote
  them. A brainstorm transcript or its conclusions pasted as the work item is
  a normal brief run.

## How to generate

1. Read `references/protocol.md` for the full artifact protocol (frontmatter
   schema, filenames, status tokens, ownership rules). Follow it exactly —
   both prompts must agree on every filename and token or the handshake stalls.
2. Fill the two templates in `assets/`:
   - `assets/planner-prompt.md` → the `/loop` prompt for the planner/executor agent
   - `assets/reviewer-prompt.md` → the `/goal` prompt for the reviewer agent
   Replace every `{{PLACEHOLDER}}` with the collected values. The templates
   contain `{{WORK_ITEM_BLOCK}}` / `{{RUBRIC_ITEM_1}}` slots whose content
   depends on the work item type — both variants are given inline in each
   template; pick the matching one and delete the other.
3. Write both prompts to the run folder as `planner.txt` and `reviewer.txt`.
   This keeps the exact prompt text next to `log.md` and the artifacts it
   produced, so a run is reproducible and a stall is diagnosable later.
4. Output both prompts in separate fenced code blocks, planner first, each
   ready to paste into its agent. Label clearly which MODEL gets which prompt
   (e.g. "→ paste into the Sol agent"), since roles are swappable and mixing
   them up is the easiest way to break the run.
5. If the user runs Orca ADE, also fill `assets/launch.sh` and write it to the
   run folder so the whole duo starts with one command. See
   `references/orca.md` for the CLI specifics and the ordering constraint.
   For other IDEs, skip the launcher and let them paste manually.
6. After the prompts, remind the user of the two operational checks (below).

## Invariants — never violate these when customizing

- **Spec before plan, always.** spec-v*.md (what) must be approved before
  plan-v*.md (how) is written. After approval the spec is FROZEN: if planning
  or execution reveals it must change, the planner escalates, never silently
  edits. Skipping the spec phase is only acceptable if the user explicitly
  asks for it (e.g. trivial bugfix with an issue that already is the spec).
- **One owner per rule.** The planner owns the round caps (max 3 per phase) and escalation.
  The reviewer owns the approval bar. The deterministic gate owns quality.
  Never duplicate a rule into both prompts.
- **Roles are defined by the prompt, not the model.** Everything role-specific
  lives in the prompt text; nothing assumes a particular vendor's behavior.
- **Plans are versioned, never edited in place.** `plan-v1.md`, `plan-v2.md`, ...
- **Status lives in frontmatter**, not prose. Exact tokens: `approved`,
  `changes_requested`. PR sign-off is a PR comment containing exactly `PR APPROVED`.
- **Run isolation, NOT agent isolation.** All artifacts carry `run_id`; agents
  ignore files from other runs. Each run gets its own folder and ONE git worktree
  shared by both agents. Never give each agent its own worktree: git worktrees are
  separate directories, so the file handshake would break and the run would stall
  silently with no error.
- **Circuit breaker.** Both agents: 20 empty polls → write STALL to log.md → exit.
- **Re-review only what changed** between rounds (both sides).
- **Reviewer never blocks on style.** Style/naming/optional improvements go in
  non-blocking notes.

## Operational checks to relay to the user

1. **Dry-run the handshake first** on a throwaway work item. The weak link is
   whether the IDE's polling actually wakes each agent on file changes. Watch
   `log.md` from both sides during the dry run. If using the Orca launcher,
   also verify the jq field paths against real `--json` output on this run.
2. **The gate placeholder must be real commands** before a production run —
   the planner will treat whatever is there as the ship condition.

## Customizations users commonly ask for

- Different round cap → change it in the planner prompt only.
- Extra rubric items (security, performance budgets) → add to the reviewer's
  rubric section; keep items answerable yes/no with evidence.
- Parallel runs → one run_id + folder + worktree per work item; nothing else changes.
- Human-in-the-loop checkpoint before execution → add to the planner: after
  approval, write `ready.md` and wait for the human to edit it with `go`.
- Skip the spec phase (trivial bugfix) → remove Phase 1 from the planner and
  the spec rubric from the reviewer; the issue serves as the spec.
- No PR at all (spike/prototype) → drop Phase 4 from the planner and the PR
  section from the reviewer; the run ends at the gate.
