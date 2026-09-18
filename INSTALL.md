# Installation instructions for coding agents

Follow this guide when a user asks you to install or update Agent Duo. Carry out
the local steps yourself using the access they have granted. Give the user a
short result and the next action; do not hand them this guide as homework.

Installation does not start a coding run, modify an application repository,
publish a PR or authenticate on the user's behalf. Runtime setup is described in
[the advanced guide](docs/advanced.md).

## 1. Resolve the destination and prerequisites

- Infer Codex, Claude Code or both from the user's request and your current app.
  If that context is unavailable, ask which app they use. Do not install into
  other applications merely because their directories exist.
- Use a user-global installation unless the user explicitly requests a
  project-local or custom path. Codex uses `~/.agents/skills/agent-duo` and the
  compatible `${CODEX_HOME:-$HOME/.codex}/skills/agent-duo` location. Claude Code's
  default is `~/.claude/skills/agent-duo`. Honor an explicitly configured custom
  skill path instead of guessing a new one.
- Check macOS/Linux, Python 3.9+, Git, Bash and `zip`. Report missing prerequisites
  plainly and use the user's normal installation mechanism when authorized.
  Do not claim a native Windows installation is supported.
- GitHub publication later requires `gh` authenticated to `github.com`. Check
  availability/authentication and report missing setup separately; this need not
  prevent installing the skill. Let the user complete any interactive login.
  Do not expose credentials in output.
- Orca is optional. Do not install it as a prerequisite for the portable skill.

Inspect any existing installation, `DUO_HOME` setting and project-local override
for the requested app. Preserve custom files in a backup; report overrides that
would keep loading an old copy. Do not silently replace project-local copies or
historical run prompts during a global update.

## 2. Obtain and build one complete version

Use `https://github.com/FutureProofingDev/agent-duo.git`. If the repository needs
authentication, use the user's authorized GitHub access. An access error is not
evidence that the repository is missing.

Clone into a suitable local tools/cache directory outside the user's application
repository, or reuse a clean clone of this exact origin. Use current `main`
unless the user requested another revision. For an existing clean clone on main,
`git pull --ff-only origin main` updates without rewriting local history, but
can also succeed when local main has extra unpublished commits. Preserve and use
a separate clone whenever local commits are absent from `origin/main`, or the
checkout contains unrelated changes or another branch. Do not stash, reset or
discard the user's work.

For the default main installation, verify the selected HEAD against the freshly
fetched upstream before building:

```bash
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

A mismatch means this checkout is not the selected upstream version; preserve it
and use a fresh clone. For an explicitly requested revision, verify HEAD against
that revision instead. Do not continue after a failed version check.

From the resolved clone, run:

```bash
./build.sh
git rev-parse HEAD
python3 dist/agent-duo/assets/duo-state.py protocol
```

Record the source commit. Require a successful build and protocol output
`{"protocol_version": 2}` before replacing an installation. The build checks all
four canonical prompts and packages the executables with them.

**Install `dist/agent-duo/` as a complete directory.** Do not install only
`skill/SKILL.md`, copy raw `skill/`, or use a generic skill-folder installer on
that source folder: the build adds `assets/duo.sh` and `assets/duo-state.py`.
The generated `dist/agent-duo.skill` is a ZIP of the same directory, not a
separately published release asset.

## 3. Stage, back up and replace the selected installations

Run the following with Bash from the clone **after a successful build**. Set
`DUO_INSTALL_FOR` to `codex`, `claude` or `both` according to step 1. This is a
parameter for you, not a question the user needs to answer in shell syntax.
For an explicitly requested custom destination, use that path in `duo_targets`
and retain the same staging, backup and verification procedure.

```bash
(
  set -eu
  case "${DUO_INSTALL_FOR:?Choose codex, claude, or both from the user context}" in
    codex) duo_targets=("$HOME/.agents/skills/agent-duo" "${CODEX_HOME:-$HOME/.codex}/skills/agent-duo") ;;
    claude) duo_targets=("$HOME/.claude/skills/agent-duo") ;;
    both) duo_targets=("$HOME/.agents/skills/agent-duo" "${CODEX_HOME:-$HOME/.codex}/skills/agent-duo" "$HOME/.claude/skills/agent-duo") ;;
    *) echo "Unsupported DUO_INSTALL_FOR" >&2; exit 1 ;;
  esac
  duo_bundle="$PWD/dist/agent-duo"
  test -f "$duo_bundle/SKILL.md"
  python3 "$duo_bundle/assets/duo-state.py" protocol
  mkdir -p "$HOME/.local/share/agent-duo/backups"
  duo_backup="$(mktemp -d "$HOME/.local/share/agent-duo/backups/update.XXXXXX")"
  echo "Backups: $duo_backup"
  duo_index=0
  for duo_target in "${duo_targets[@]}"; do
    duo_index=$((duo_index + 1))
    duo_previous="$duo_backup/$duo_index"
    duo_parent="$(dirname "$duo_target")"
    mkdir -p "$duo_parent"
    duo_stage="$(mktemp -d "$duo_parent/.agent-duo.XXXXXX")"
    cp -R "$duo_bundle" "$duo_stage/agent-duo"
    chmod +x "$duo_stage/agent-duo/assets/duo.sh" "$duo_stage/agent-duo/assets/duo-state.py"
    python3 "$duo_stage/agent-duo/assets/duo-state.py" protocol
    printf '%s\n' "$duo_target" > "$duo_backup/$duo_index.path"
    if [ -e "$duo_target" ] || [ -L "$duo_target" ]; then
      mv "$duo_target" "$duo_previous"
    fi
    if ! mv "$duo_stage/agent-duo" "$duo_target"; then
      if [ -e "$duo_previous" ] || [ -L "$duo_previous" ]; then
        mv "$duo_previous" "$duo_target"
      fi
      exit 1
    fi
    rmdir "$duo_stage"
    echo "Installed: $duo_target"
  done
)
```

Each existing target is backed up separately with its original path recorded.
Replacement removes stale active files and leaves other skills alone. If a later
destination fails, earlier successful replacements and all backups remain; report
which destinations succeeded instead of claiming an all-or-nothing update.

## 4. Verify and hand off

For each selected installation:

1. Compare its complete file contents to `dist/agent-duo/` from this build. Check
   that both scripts in `assets/` are executable and that the four canonical
   prompt files exist.
2. Run its own `python3 /installed/path/assets/duo-state.py protocol`; require
   `{"protocol_version": 2}`. This checks the installed controller, not merely
   the copy in your source checkout.
3. If `DUO_HOME` is already configured, make it point to the chosen complete
   bundle when updating that configuration is authorized. Otherwise report the
   stale setting. The skill can locate its own assets; a new user does not need
   to edit a shell startup file just to invoke the skill. Direct/legacy launcher
   commands have additional setup in [the advanced guide](docs/advanced.md).

If verification fails, restore the affected destination from its backup and
explain the specific failure. Keep backup paths available for recovery.
Do not launch agents, create a test PR or alter existing run evidence merely to
verify installation. Do not say the app has loaded the new skill until its
discovery can actually be observed; a new session may be required.

Finish with the app(s) updated, installed source commit, verification result,
backup location and any missing runtime prerequisite. Ask the user to open a
new session, then give one example: **"Use Agent Duo to implement [my change]
and leave a reviewed pull request."** Codex can select `$agent-duo`; Claude Code
can select `/agent-duo`.

Outside Orca, two sessions still need to be opened on the shared workspace. The
skill can prepare their prompts and explain the next step; installing it does
not add a portable automatic session launcher.
