#!/usr/bin/env bash
# duo --task "hide signup" --run-id signup
# duo --issue https://github.com/org/repo/issues/612 --run-id 612-a --new-worktree
# duo --resume --run-id signup
# Python owns argv, JSON and literal template values; no user text is shell code.
set -euo pipefail
exec python3 - "$0" "$@" <<'PY'
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPT = Path(sys.argv[1]).resolve()
RUNS_ROOT = Path('docs/agent-duo/runs')
TOKEN = re.compile(r'\{\{([A-Z_]+)\}\}')
KEYS = {'RUN_ID', 'RUNS_ROOT', 'GATE_COMMANDS', 'WORK_ITEM_BLOCK',
        'SOURCE_OF_TRUTH_BLOCK', 'RUBRIC_ITEM_1', 'ISSUE_NUMBER', 'ISSUE_URL',
        'WORK_ITEM_TEXT', 'PLANNER_AGENT', 'REVIEWER_AGENT', 'PLANNER_HANDLE',
        'REVIEWER_HANDLE', 'CONTROLLER'}


def fail(message):
    raise RuntimeError(message)


def command(argv, cwd=None, check=True):
    result = subprocess.run([str(v) for v in argv], cwd=cwd, text=True,
                            capture_output=True)
    if check and result.returncode:
        fail(f'{argv[0]} {argv[1]} failed: {result.stderr.strip() or result.stdout.strip()}')
    return result


def git(wt, *args, check=True):
    return command(['git', '-C', wt, *args], check=check)


def orca(*args):
    result = command([ORCA, *args, '--json'])
    data = json.loads(result.stdout)
    if data.get('ok') is not True:
        fail(f'Orca {args[0]} failed: {data.get("error", data)}')
    return data['result']


def templates(home, mode):
    suffix = '-orca' if mode == 'orchestration' else ''
    found = {}
    for role in ('planner', 'reviewer'):
        paths = [home / 'skill/assets', home / 'assets', home]
        path = next((p / f'{role}{suffix}.md' for p in paths
                     if (p / f'{role}{suffix}.md').is_file()), None)
        if path is None:
            fail(f'{role} template not found under DUO_HOME={home}')
        text = re.sub(r'<!--.*?-->', '', path.read_text(encoding='utf-8'), flags=re.S)
        unknown = set(TOKEN.findall(text)) - KEYS
        if unknown:
            fail(f'Unknown template placeholders in {path}: {", ".join(sorted(unknown))}')
        found[role] = text
    return found


def terminals(selector, wt):
    result = orca('terminal', 'list', '--worktree', selector)
    if result.get('truncated'):
        fail('Terminal list is truncated; narrow the worktree or close unused sessions.')
    return [t for t in result['terminals']
            if Path(t.get('worktreePath', '')).resolve() == wt]


def select_terminal(terms, agent, explicit, role):
    eligible = [t for t in terms if t.get('agentIdentity') == agent
                and t.get('connected') is True and t.get('writable') is True
                and not t.get('orphaned')]
    if explicit:
        eligible = [t for t in eligible if t['handle'] == explicit]
    if len(eligible) != 1:
        fail(f'Cannot identify one connected {agent} {role} terminal in this worktree. '
             f'Pass --{role}-terminal with a verified agent handle; shells are not agents.')
    return eligible[0]['handle']


def check_clean(wt):
    dirty = git(wt, 'status', '--porcelain', '--untracked-files=normal', '--', '.',
                f':(exclude){RUNS_ROOT}').stdout.strip()
    if dirty:
        fail('Worktree has uncommitted changes; commit or stash them before starting a run.\n' + dirty)
    for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        path = Path(git(wt, 'rev-parse', '--git-path', name).stdout.strip())
        if not path.is_absolute():
            path = wt / path
        if path.exists():
            fail(f'Finish the existing Git operation ({name}) before starting a run.')


def base_commit(wt, explicit):
    # Fetch updates remote refs only: no hidden merge/rebase in the user's checkout.
    if explicit:
        ref = explicit
        if ref.startswith('-'):
            fail('--base must be a Git ref, not an option.')
        git(wt, 'rev-parse', '--verify', f'{ref}^{{commit}}')
    else:
        ref = git(wt, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD', check=False).stdout.strip()
        ref = ref or 'HEAD'
    if ref.startswith('refs/remotes/'):
        remote = ref.split('/')[2]
        git(wt, 'fetch', '--quiet', remote)
    elif explicit and '/' in ref and ref.split('/')[0] in git(wt, 'remote').stdout.splitlines():
        git(wt, 'fetch', '--quiet', ref.split('/')[0])
    return git(wt, 'rev-parse', '--verify', f'{ref}^{{commit}}').stdout.strip()


def render(originals, values):
    # Match only the original templates. Inserted values are never reparsed.
    return {role: TOKEN.sub(lambda match: values[match.group(1)], text)
            for role, text in originals.items()}


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def run_path(wt, run_id):
    path = wt / RUNS_ROOT / run_id
    if wt not in path.resolve().parents:
        fail('Run directory must remain inside its worktree; check artifact symlinks.')
    return path


def controller(action, run, args):
    command([sys.executable, CONTROLLER, action, '--run-dir', run, *args])


def main():
    global ORCA, CONTROLLER
    parser = argparse.ArgumentParser(prog='duo', description='Start or resume two verified agents in one worktree.')
    parser.add_argument('--run-id', required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--task')
    source.add_argument('--issue')
    parser.add_argument('--gate')
    parser.add_argument('--planner', choices=('claude', 'codex'))
    parser.add_argument('--reviewer', choices=('claude', 'codex'))
    parser.add_argument('--mode', choices=('orchestration', 'file'))
    parser.add_argument('--base')
    parser.add_argument('--new-worktree', action='store_true')
    parser.add_argument('--no-reset', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--reviewer-terminal')
    parser.add_argument('--planner-terminal')
    args = parser.parse_args(sys.argv[2:])
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.run_id):
        parser.error('--run-id must be 1–64 letters, digits, underscores or hyphens, starting with a letter or digit.')
    if args.resume:
        if any((args.task is not None, args.issue, args.base, args.new_worktree, args.no_reset,
                args.mode, args.gate is not None, args.planner, args.reviewer)):
            parser.error('--resume uses saved parameters; supply only --run-id and optional terminal handles.')
    elif not args.task and not args.issue:
        parser.error('--task or --issue is required for a new run.')
    if not args.resume:
        gate = args.gate if args.gate is not None else os.environ.get('DUO_GATE')
        if gate is None or not gate.strip():
            parser.error('Provide a nonempty --gate command or DUO_GATE for a new run.')
    if args.no_reset and (args.base or args.new_worktree):
        parser.error('--no-reset cannot be combined with --base or --new-worktree.')
    if args.new_worktree and (args.reviewer_terminal or args.planner_terminal):
        parser.error('--new-worktree creates its own agent terminals; omit terminal overrides.')
    if args.issue and not re.fullmatch(r'https://[^/\s]+/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*', args.issue):
        parser.error('--issue must be an HTTPS GitHub issue URL ending in /issues/NUMBER.')
    if args.base and args.base.startswith('-'):
        parser.error('--base must be a Git ref, not an option.')

    home = Path(os.environ['DUO_HOME']).expanduser().resolve() if os.environ.get('DUO_HOME') else SCRIPT.parent.parent
    CONTROLLER = SCRIPT.with_name('duo-state.py')
    if not CONTROLLER.is_file():
        fail(f'Controller is missing: {CONTROLLER}. Reinstall the complete skill.')
    ORCA = os.environ.get('ORCA_CLI_COMMAND') or ('orca-dev' if os.environ.get('ORCA_DEV_REPO_ROOT') else 'orca-ide' if sys.platform.startswith('linux') else 'orca')
    wt = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').stdout.strip()).resolve()
    selector = f'path:{wt}'
    run = run_path(wt, args.run_id)
    if args.resume:
        saved = json.loads((run / 'launcher.json').read_text(encoding='utf-8'))
        if Path(saved['worktree']).resolve() != wt:
            fail('Saved run belongs to a different worktree.')
        originals, values = saved['templates'], saved['values']
        planner_agent, reviewer_agent = values['PLANNER_AGENT'], values['REVIEWER_AGENT']
    else:
        planner_agent, reviewer_agent = args.planner or 'claude', args.reviewer or 'codex'
        originals = templates(home, args.mode or 'orchestration')
        values = {}
        if not args.new_worktree and run.exists():
            fail(f'Run folder already exists: {run}; use --resume --run-id {args.run_id}.')
        check_clean(wt)

    orca('status')
    commit = None
    if not args.resume and not args.no_reset:
        commit = base_commit(wt, args.base)
    rev, pln = args.reviewer_terminal, args.planner_terminal
    if args.new_worktree:
        created = orca('worktree', 'create', '--name', f'duo-{args.run_id}', '--no-parent',
                       '--base-branch', commit, '--agent', reviewer_agent)
        identity = created['worktree']['id']
        if '::' not in identity or not Path(identity.split('::', 1)[1]).is_absolute():
            fail('Orca returned an invalid compound worktree ID.')
        wt = Path(identity.split('::', 1)[1]).resolve()
        selector = 'id:' + identity
        run = run_path(wt, args.run_id)
        if run.exists():
            fail(f'Run folder already exists: {run}')
        rev = created.get('agentTerminalHandle') or (created.get('startupTerminal') or {}).get('handle')
        made = orca('terminal', 'create', '--worktree', selector, '--command', planner_agent,
                    '--title', f'duo-{args.run_id}-planner')
        pln = made['terminal']['handle']
        # A newly created TUI must be ready before agentIdentity can be verified.
        for handle in (rev, pln):
            if handle:
                orca('terminal', 'wait', '--terminal', handle, '--for', 'tui-idle', '--timeout-ms', '180000')
        check_clean(wt)
    terms = terminals(selector, wt)
    rev = select_terminal(terms, reviewer_agent, rev, 'reviewer')
    pln = select_terminal(terms, planner_agent, pln, 'planner')
    if rev == pln:
        fail('Planner and reviewer must use two distinct terminals.')
    if not args.new_worktree:
        orca('terminal', 'wait', '--terminal', rev, '--for', 'tui-idle', '--timeout-ms', '180000')

    if not args.resume:
        issue_number = args.issue.rsplit('/', 1)[1] if args.issue else 'n/a'
        brief = args.task if args.task is not None else f'GitHub issue #{issue_number}: {args.issue}\nRead the issue in full; it is the source of truth.\n'
        if args.issue:
            block = f'Your work item is GitHub issue #{issue_number}: {args.issue}. Read it fully before speccing.'
            source_block = block
        else:
            block = ('The launcher saved the following brief verbatim in brief.md. Read it; do not rewrite it.\n'
                     '--- BRIEF START ---\n' + brief + '\n--- BRIEF END ---')
            source_block = 'The source of truth is the existing brief.md in the run folder, saved by the launcher. Read it before review.'
        values = dict(RUN_ID=args.run_id, RUNS_ROOT=str(wt / RUNS_ROOT) + '/',
                      GATE_COMMANDS=gate, WORK_ITEM_BLOCK=block,
                      SOURCE_OF_TRUTH_BLOCK=source_block,
                      RUBRIC_ITEM_1='Does the plan address every acceptance criterion of the approved spec?',
                      ISSUE_NUMBER=issue_number, ISSUE_URL=args.issue or '', WORK_ITEM_TEXT=brief,
                      PLANNER_AGENT=planner_agent, REVIEWER_AGENT=reviewer_agent)
    values.update(PLANNER_HANDLE=pln, REVIEWER_HANDLE=rev, CONTROLLER=str(CONTROLLER))
    prompts = render(originals, values)
    saved = dict(worktree=str(wt), templates=originals, values=values)
    runs = wt / RUNS_ROOT
    runs.mkdir(parents=True, exist_ok=True)
    lock = runs / f'.{args.run_id}.launch-lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        fail(f'Another launcher holds {lock}; check that process before removing its lock.')
    os.close(fd)
    stage = None
    try:
        if args.resume:
            controller('resume', run, ['--reviewer', rev])
            # Keep accepted artifacts and state. Only runtime prompt addresses change.
            for role, text in prompts.items():
                tmp = run / f'.{role}.resolved.tmp'
                tmp.write_text(text, encoding='utf-8')
                tmp.replace(run / f'{role}.resolved.txt')
            save_json(run / 'launcher.json', saved)
        else:
            if run.exists():
                fail(f'Run folder already exists: {run}')
            stage = Path(tempfile.mkdtemp(prefix=f'.{args.run_id}.', dir=runs))
            for role, text in prompts.items():
                (stage / f'{role}.resolved.txt').write_text(text, encoding='utf-8')
            save_json(stage / 'launcher.json', saved)
            (stage / 'brief.md').write_bytes((f'---\nrun_id: {args.run_id}\ntype: brief\nround: 0\n---\n').encode() + brief.encode('utf-8'))
            previous = None
            if not args.new_worktree and not args.no_reset:
                previous = git(wt, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False).stdout.strip()
                previous_sha = git(wt, 'rev-parse', 'HEAD').stdout.strip()
                git(wt, 'switch', '--quiet', '-c', f'duo/{args.run_id}', commit)
            stage.rename(run)
            stage = None
            try:
                controller('init', run, ['--run-id', args.run_id, '--worktree', wt,
                                       '--gate', values['GATE_COMMANDS'], '--reviewer', rev])
            except Exception:
                shutil.rmtree(run)
                if previous is not None:
                    restore = ['switch', '--quiet', previous] if previous else ['switch', '--quiet', '--detach', previous_sha]
                    git(wt, *restore)
                    git(wt, 'branch', '-D', f'duo/{args.run_id}')
                raise
        # Reused planner can be executing /agent-duo itself: queue its prompt.
        # Durable state queues reviews while the reviewer starts. Its worker loop
        # waits for the planner, so waiting for reviewer idle here would deadlock.
        orca('terminal', 'send', '--terminal', rev, '--text', prompts['reviewer'], '--enter')
        orca('terminal', 'send', '--terminal', pln, '--text', prompts['planner'], '--enter')
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.unlink()
    print(f"duo run '{args.run_id}' {'resumed' if args.resume else 'started'}\n"
          f'  worktree: {wt}\n  branch: {git(wt, "branch", "--show-current").stdout.strip()}\n'
          f'  planner: {planner_agent} {pln}\n  reviewer: {reviewer_agent} {rev}\n  run dir: {run}')


try:
    main()
except (RuntimeError, OSError, ValueError, KeyError) as error:
    print(f'duo: {error}', file=sys.stderr)
    sys.exit(1)
PY
