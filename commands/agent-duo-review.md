---
description: Resume the saved agent-duo reviewer prompt in its existing terminal.
argument-hint: --run-dir ABSOLUTE_PATH
---

Parse `--run-dir ABSOLUTE_PATH` from `$ARGUMENTS`. This fallback is for a run
already initialized by `duo.sh`, when the intended reviewer terminal needs its
saved prompt loaded manually.

1. Require an absolute run directory containing `launcher.json` and
   `reviewer.resolved.txt`. Read the saved launch metadata and confirm this is
   the selected reviewer terminal in the run's worktree. Do not guess a handle
   from terminal preview text or list ordering.
2. If a session restarted, a handle changed, or the run needs recovery, use the
   launcher with `--resume --run-id ID` first so it can validate the worktree and
   regenerate prompt values. Do not reuse saved prompts with stale handles.
3. Read `reviewer.resolved.txt` in full and adopt that reviewer protocol here.
   Its initial `/goal` is the role-start directive, not a request to send the
   prompt to another terminal. If the file is missing, stop and report that the
   launcher must regenerate it. Preserve literal user text, including braces;
   the launcher validates template tokens before inserting user content.

This saved prompt is rendered from the canonical reviewer asset, including the
controller path and cross-run learning instructions. Do not reconstruct it,
fill tokens by hand, or dispatch another reviewer.
