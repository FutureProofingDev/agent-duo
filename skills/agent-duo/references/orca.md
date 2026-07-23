# Running the duo in Orca ADE

Orca-specific notes. The protocol itself is IDE-agnostic; this covers how it maps
onto Orca's model and CLI.

## The worktree constraint (read this first)

Orca worktrees are separate directories. Both agents MUST run in the SAME worktree,
in two terminals, because the file handshake requires a shared filesystem.

Giving each agent its own worktree is the single most likely way to break a run,
and it fails silently: the planner writes `spec-v1.md` into its directory, the
reviewer polls a different one, neither errors, both eventually hit their poll
budget and exit. Run isolation is per-run, not per-agent.

## Prerequisites

Register the CLI under Settings -> Experimental -> CLI, then confirm the runtime
is reachable with `orca status --json` (start it with `orca open --json` if not).

## Commands the launcher relies on

| Purpose | Command |
|---|---|
| Create worktree + launch first agent | `orca worktree create --name <n> --agent <claude\|codex> --json` |
| Get terminal handles | `orca terminal list --worktree id:<id> --json` |
| Block until an agent is ready | `orca terminal wait --terminal <h> --for tui-idle --timeout-ms <ms> --json` |
| Send a prompt | `orca terminal send --terminal <h> --text "..." --enter --json` |
| Second agent, same worktree | `orca terminal split --terminal <h> --direction horizontal --command <agent> --json` |

`--agent` launches the selected agent in the first terminal and `--prompt` sends
it initial work, so a single-agent run can be one command. The duo needs the
split because the second agent must land in the same worktree.

Terminal handles are runtime-scoped. If Orca restarts or a command reports a
stale handle, reacquire with `orca terminal list --json`.

## Ordering constraint

Reviewer first, then planner. The reviewer must be watching the folder before any
artifact lands in it. If the planner starts first, `spec-v1.md` can appear while
the reviewer is still booting, so nothing picks it up and the planner burns poll
budget against an agent that was never listening. `terminal wait --for tui-idle`
between the two starts is what enforces this.

## Response shapes (verified)

Every response is wrapped:

```json
{ "id": "...", "ok": true, "result": { ... }, "_meta": { "runtimeId": "..." } }
```

So selectors start at `.result`, e.g. `.result.terminals[0].handle`.

Three things that bite:

1. **`worktreeId` is compound**, not a bare UUID:
   `<runtime-uuid>::<absolute worktree path>`. Do not pass it where a plain id is
   expected. Use `--worktree active`, or match on `worktreePath`.
2. **`worktreePath`** is the absolute path on disk. The run folder must live
   inside it, so derive the run folder from this rather than assuming a relative
   path from the main checkout. A worktree is a fresh directory: uncommitted
   files from your main checkout are not in it.
3. **Do not index terminals by position.** A worktree also holds plain shells
   (e.g. a "Setup" terminal) and list order is not guaranteed. Select by title:
   `.result.terminals[] | select(.title | test($name)) | .handle`.

Handle format is `term_<uuid>`. Handles are runtime-scoped: after an Orca restart,
reacquire with `orca terminal list --worktree active --json`.

## Orchestration layer (alternative design)

Orca ships an experimental orchestration layer that overlaps heavily with this
protocol: a shared inbox, task records, dispatches, worker completion messages,
and decision gates. Enable it under Settings -> Experimental.

Where it would replace hand-rolled machinery:

| Our mechanism | Orca native |
|---|---|
| Poll folder + 20-poll circuit breaker | `orchestration check --wait --types ... --timeout-ms` (blocks, heartbeats every 15s) |
| `escalation.md` + human edits it | `orchestration ask` with options, or explicit decision gates |
| `log.md` | task records + inbox |
| Round tracking in prose | task status: pending/ready/dispatched/completed/failed/blocked |

Real tradeoff. Native blocking waits are strictly better than polling: no wasted
tokens, no poll budget, no stall-vs-slow ambiguity. But the orchestration layer is
experimental and Orca-only, so a protocol built on it stops being portable to
other IDEs and stops working the moment either agent runs somewhere else.

Recommended path: run the file-based protocol first since it works everywhere and
is easy to debug, then port the waiting and escalation mechanics to orchestration
once the loop itself is proven. Do not port both at once, or a stall becomes
ambiguous between a protocol bug and an orchestration bug.
