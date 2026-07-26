# Cross-run learning (per-repo)

A per-repo memory that lets the reviewer improve run over run WITHOUT a human
editing prompts. Scoped to one repo: a lesson from repo A never reaches repo B.
Lessons live in the repo, versioned and PR-reviewable.

## Files

- `docs/agent-duo/lessons.md`         active + dormant lessons (the memory)
- `docs/agent-duo/lessons-pending.md` candidate lessons awaiting a second sighting

Both are committed. `runs/` is gitignored; these two are NOT.

## Lesson shape

```
- id: L3
  pattern: Plans freeze template variables at scheduling-time when the spec requires send-time rendering
  scope: spec | plan | pr
  first_seen: 2026-07-23 (run 514)
  last_confirmed: 2026-07-26 (run 535-a)
  confirmations: 3
  status: active | dormant
```

## The four safeguards (why this learns instead of accumulating noise)

1. **Promotion by repetition.** The reviewer never writes straight to
   lessons.md. It appends a CANDIDATE to lessons-pending.md. A candidate becomes
   `active` in lessons.md only when the SAME pattern is seen in a DIFFERENT run.
   One-time blocks stay pending and never become dogma. This is the core
   noise filter: a lesson must recur to earn authority.

2. **Generality filter.** A lesson must be a transferable pattern of PLANNER
   BEHAVIOR, never a fact about the code. Transferable: "plans skip org-ownership
   validation on new FKs." Not a lesson: "trigger_stage_id needs an org check."
   The first helps the next unrelated feature; the second is just this bug. If
   it names a specific symbol, table, or file, it is too specific to persist.

3. **Advisory, not a gate.** Active lessons are injected into the REVIEWER as a
   "watch for these" checklist, never into the planner as an accusation, and
   never as an automatic block. The reviewer still judges each artifact on its
   own merits; lessons only direct attention. Feeding "you always cut scope" to
   a planner invites overcorrection, so planners never read lessons.

4. **Decay.** When an active lesson is not confirmed for 5 completed runs, the
   reviewer sets it `dormant`. A pattern you fixed (e.g. via a prompt change)
   stops recurring, its counter stalls, and it retires itself. Lessons can die,
   so the memory tracks current reality rather than an ever-growing history.

## Reviewer procedure

At run start (all phases):
- Read lessons.md. Treat entries with `status: active` as an extra checklist of
  where planners have historically erred IN THIS REPO. Do not auto-block on them.

At run end (after the PR is approved, or the run escalates/stops):
- For each distinct pattern you blocked on this run that passes the generality
  filter, check lessons-pending.md and lessons.md:
  - Already `active`: bump `confirmations`, set `last_confirmed` to this run.
  - Present in pending (seen once before, in a different run): PROMOTE it to
    lessons.md as `active`, confirmations: 2.
  - Not seen before: append it to lessons-pending.md as a candidate with this
    run id. Do not add to lessons.md.
- Decay pass: for each `active` lesson whose `last_confirmed` is 5+ completed
  runs old, set `status: dormant`.
- Never delete lessons; dormant is the terminal state, so history is auditable.

## Why per-repo, not global

A planner's failure modes are shaped by the repo's conventions, stack, and prior
decisions. "Cuts scope in this codebase" is often true where a cross-repo
universal would be false. Per-repo keeps lessons honest and lets them travel with
the code they describe. A global store was considered and rejected: it would mix
signal from unrelated codebases and needs conflict resolution that per-repo
avoids entirely.
