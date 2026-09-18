---
description: Resume the saved agent-duo reviewer prompt in its existing terminal.
argument-hint: --run-dir ABSOLUTE_PATH
---

Parse `--run-dir ABSOLUTE_PATH` from `$ARGUMENTS`. This fallback is for a run
already initialized by `duo.sh`, when the intended reviewer terminal needs its
saved prompt loaded manually.

1. Require an absolute run directory containing `launcher.json` and
   `reviewer.resolved.txt`. Read the saved launch metadata and confirm this is
   the selected reviewer terminal in the run's worktree. Require protocol 2 from
   the saved controller's `protocol` command, the matching reviewer/transport marker
   on line 2 of the saved reviewer template, and matching saved hashes in launch metadata. If validation
   cannot be established, use launcher recovery rather than adopting the prompt.
   Do not guess a handle
   from terminal preview text or list ordering.
2. If a session restarted, a handle changed, or the run needs recovery, use the
   launcher with `--resume --run-id ID` first so it can validate the worktree and
   regenerate compatible prompt values. Let the launcher deliver them rather
   than also adopting a second reviewer here. Do not reuse stale handles.
   Legacy/incompatible snapshots need a new run with imported, revalidated
   artifacts; never rewrite old evidence or reconstruct a current prompt by hand.
3. Read `reviewer.resolved.txt` in full and adopt that reviewer protocol here.
   Current resolved files contain instructions, not a slash command to dispatch.
   Treat any leading `/loop` or `/goal` in an older file as a legacy wrapper,
   not a request to send a command to another terminal. If the file is missing, report that the
   launcher must regenerate it. Preserve literal user text, including braces;
   the launcher validates template tokens before inserting user content.

This saved prompt is rendered from the canonical reviewer asset, including the
controller path and cross-run learning instructions. Do not reconstruct it,
fill tokens by hand, or dispatch another reviewer. Final PR reviews disclose
`## Pending manual checks`; the planner publishes the accepted SHA-specific verdict
with `publish-review --repo OWNER/NAME` before finalize. Stop successfully only at
controller completion with the recorded publication URL, except for an explicitly
requested planning-only deliverable.
