---
description: Start or resume agent-duo through its deterministic launcher.
argument-hint: --run-id ID --task "..." --planner-terminal HANDLE --reviewer-terminal HANDLE [launcher options]
---

Start the run by invoking the installed agent-duo launcher with `$ARGUMENTS`.
The launcher owns argument validation, terminal selection, worktree checks,
protocol/version/token/hash preflight, prompt rendering, controller initialization,
and startup delivery. Use the complete protocol-2 bundle. Planning-only is a
restriction only when explicitly requested; otherwise plan approval continues
through implementation, published PR verdict and finalization.

1. Parse `$ARGUMENTS` into an argument list, preserving quoted task and gate
   strings. Accept the launcher's options, including `--issue` instead of
   `--task`, or `--resume --run-id ID` for an existing run. Pass the arguments
   as individually quoted shell arguments; never evaluate them as shell code.
2. Resolve one launcher. If `DUO_HOME` is set, use the executable
   `$DUO_HOME/bin/duo.sh` for a source checkout or `$DUO_HOME/assets/duo.sh` for an
   installed skill. If it is unset, use `duo` from PATH. If no launcher is
   available, stop with its installation requirement: install the complete
   skill package and set `DUO_HOME` to its root, or put the repository launcher
   on PATH as `duo`.
3. With `--new-worktree`, let the launcher create and select the new terminals;
   do not add current-terminal handles. Otherwise, when invoked in the intended
   planner terminal, pass its actual terminal
   handle as `--planner-terminal`; pass the intended peer's actual handle as
   `--reviewer-terminal`. Use handles supplied in the arguments when present.
   Never infer a terminal handle from preview text or array position. If the
   current terminal handle is unavailable and no planner handle was supplied,
   report that `--planner-terminal` is required for this slash-command entry.
4. Execute the resolved launcher once. On failure, report the error and stop.
   Incompatible legacy resume snapshots require a new run with imported and
   revalidated artifacts; never rewrite old evidence to bypass version/hash checks.
   On success, report the run directory it returns and finish this command.
   The launcher queues the resolved planner prompt in the selected terminal;
   allow that prompt to drive the run. Do not start a second planner loop or
   wait for the invoking planner terminal to become idle inside this command.

The complete role protocols live in `skill/assets/` in a checkout and `assets/`
in an installed skill. The launcher supplies the absolute controller path and
all run-specific values; this command does not maintain another protocol body.
End-to-end completion includes `publish-review --repo OWNER/NAME` through an
authorized gh CLI session before finalize, with SHA, review evidence and pending
manual checks visible in the recorded GitHub comment.
