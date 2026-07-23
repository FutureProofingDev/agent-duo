# Agent Duo Protocol Reference

The filesystem is the message bus. Every artifact is a markdown file with YAML
frontmatter in the run folder: `{{RUNS_ROOT}}{{RUN_ID}}/`.

## Frontmatter schema

```yaml
---
run_id: <run_id>          # required on every file; agents ignore other run_ids
type: brief | spec | plan | review | pr-request | escalation
round: <n>                # review round this artifact belongs to
status: approved | changes_requested   # reviews only
source: <filename>        # reviews only: the file being reviewed
---
```

Agents parse frontmatter, never prose, to decide state. Prose is for humans
and for the substance of reviews/plans.

## Filenames

| Artifact            | Name                          | Written by |
|---------------------|-------------------------------|------------|
| Brief (no-issue runs) | `brief.md` (verbatim work statement) | planner |
| Spec (versioned)    | `spec-v<N>.md`                | planner    |
| Spec review         | `cr-spec-v<N>.md`             | reviewer   |
| Plan (versioned)    | `plan-v<N>.md`                | planner    |
| Plan review         | `cr-plan-v<N>.md`             | reviewer   |
| PR request          | `prr-<PR_NUMBER>.md`          | planner    |
| Escalation          | `escalation.md`               | planner    |
| Run log             | `log.md` (append-only)        | both       |

Plans are never edited in place; a new round means a new version file.

## Status tokens (exact strings)

- Frontmatter: `status: approved` / `status: changes_requested`
- PR sign-off: a GitHub PR comment containing exactly `PR APPROVED`

## State machine

```
[human brainstorm → brief]
SPEC v1 → review ↔ revise (max 3 rounds) → approved (spec now FROZEN)
PLAN v1 → review ↔ revise (max 3 rounds) → approved
GATE (tests+lint+build) → PR → prr file
PR → reviewer comments ↔ planner fixes/pushes → "PR APPROVED" comment → done
any phase at round 3 unapproved → escalation.md → exit (resume on human ruling)
spec change needed after freeze → escalation.md, never a silent edit
```

Escalation resume: human edits `escalation.md` with a ruling; planner detects
the modification and resumes applying it.

## Ownership (one owner per rule)

| Rule                        | Owner    |
|-----------------------------|----------|
| Round caps (max 3 per phase), escalation | planner |
| Approval bar, rubric        | reviewer |
| Quality (tests/lint/build)  | deterministic gate, not an LLM |
| Stall breaker (20 polls)    | each agent for itself |

Never give both agents a counting rule — off-by-one between them deadlocks
or double-exits the run.

## Reviewer rubrics

Spec reviews judge the WHAT (faithful to brief/issue, testable criteria,
explicit non-goals, no implementation details). Plan reviews judge the HOW
against the approved, frozen spec. Full rubrics live in the reviewer prompt
template.

### Plan review rubric (reference)

Answer each explicitly, one section per item:

1. Issue runs: does the plan address every acceptance criterion of the issue?
   Brief runs: are the derived acceptance criteria a faithful, complete reading
   of brief.md, and does the plan address all of them?
2. Does it touch anything outside stated scope? Flag it.
3. Migration/rollback concerns handled?
4. Are edge cases named and covered?
5. Any technical unsoundness (race conditions, security, data loss)?

Approval bar: technically sound + criteria covered. Style, naming, and
optional improvements are non-blocking notes, never blockers. On round n+1,
verify previous numbered items were addressed and re-review only the diff.

## Why these choices (context for customization)

- **Frontmatter over magic strings in prose**: one paraphrase away from a
  stall otherwise; parsing structured fields is deterministic.
- **Deterministic gate between approval and PR**: converts the reviewer's job
  from "find every bug" to "find design problems", which is what LLM review is
  good at. The harness catches "tests didn't run".
- **run_id everywhere**: kills stale-file bugs from previous runs for free and
  enables parallel runs.
- **Append-only log.md**: single file to read when a run stalls at 3am; also
  data for tuning the rubric after a few runs.
- **Worktree per RUN, not per agent**: two runs sharing one checkout is an
  incident waiting to happen, but two agents in separate worktrees is worse.
  Git worktrees are separate directories, so split agents cannot see each
  other's artifacts and the handshake stalls with no error. One worktree per
  run, both agents inside it, one terminal each.
- **Poll budget**: polling loops fail expensive, not loud. A stalled run that
  exits after 20 polls costs cents.

## Work item sources

The protocol is source-agnostic. Two variants:

- **Issue run**: source of truth is the GitHub issue. No brief.md.
- **Brief run**: no issue exists. Planner's first action is writing the user's
  work statement verbatim into brief.md (type: brief, round: 0). The planner
  derives acceptance criteria in plan-v1; the reviewer reviews the criteria
  themselves as rubric item 1. This closes the loop that normally a human
  closes by writing the issue: the derived criteria are an artifact under
  review, not an assumption.

## Role assignment

Roles are defined entirely by which prompt a model receives. Any decorrelated
pair works in either direction (Opus plans + Sol reviews, Sol plans + Opus
reviews). When generating, label each prompt with the target MODEL explicitly;
pasting them into the wrong agents is the most common setup error.
