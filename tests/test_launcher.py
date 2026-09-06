"""Launcher regressions: real shell/Python/Git, Orca isolated at its CLI boundary."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
MOCK_ORCA = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
a = sys.argv[1:]
p = Path(os.environ['ORCA_FIXTURE'])
d = json.loads(p.read_text())
with open(os.environ['ORCA_LOG'], 'a') as f:
    f.write(json.dumps(a) + '\n')
def arg(n): return a[a.index(n) + 1]
def emit(x): print(json.dumps({'ok': True, 'result': x}))
if a[:2] == ['worktree', 'create']:
    emit({'worktree': {'id': 'repo::' + d['new'], 'path': d['new']}, 'agentTerminalHandle': 'term_new_codex'})
elif a[:2] == ['terminal', 'create']:
    assert arg('--worktree') == 'id:repo::' + d['new']
    t = {'handle': 'term_new_claude', 'worktreePath': d['new'], 'agentIdentity': arg('--command'), 'connected': True, 'writable': True, 'orphaned': False}
    d['new_terms'].append(t)
    p.write_text(json.dumps(d))
    emit({'terminal': t})
elif a[:2] == ['terminal', 'list']:
    selector = arg('--worktree')
    ts = d['new_terms'] if selector == 'id:repo::' + d.get('new', '') else d['terms']
    emit({'terminals': ts, 'truncated': False, 'totalCount': len(ts)})
elif a[:2] == ['terminal', 'wait'] and d.get('wait_failure'):
    print('not ready', file=sys.stderr); sys.exit(1)
else:
    emit({})
'''

STUB_CONTROLLER = r'''import json, os, sys
from pathlib import Path
a = sys.argv[1:]
def arg(n): return a[a.index(n) + 1]
if a == ['protocol']:
    print(json.dumps({'protocol_version': int(os.environ.get('CONTROLLER_PROTOCOL', '2'))}))
    sys.exit(0)
with open(os.environ['CONTROLLER_LOG'], 'a') as f:
    f.write(json.dumps(a) + '\n')
run = Path(arg('--run-dir'))
p = run / 'state.json'
if a[0] == 'init':
    if os.environ.get('FAIL_CONTROLLER_INIT'):
        sys.exit('simulated initialization failure')
    assert (run / 'brief.md').exists()
    p.write_text(json.dumps({'phase': 'spec', 'reviewer': arg('--reviewer')}))
elif a[0] == 'resume':
    d = json.loads(p.read_text()); d['reviewer'] = arg('--reviewer'); p.write_text(json.dumps(d))
'''


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='duo-launcher-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'duo'
        (self.home / 'bin').mkdir(parents=True)
        (self.home / 'assets').mkdir()
        self.launcher = self.home / 'bin/duo.sh'
        shutil.copy2(REPO / 'bin/duo.sh', self.launcher)
        (self.home / 'bin/duo-state.py').write_text(STUB_CONTROLLER)
        for suffix, mode in (('', 'file'), ('-orca', 'orchestration')):
            for role, body in (
                ('planner', '{{WORK_ITEM_BLOCK}}\nrun={{RUN_ID}}\npeer={{REVIEWER_HANDLE}}\ngate={{GATE_COMMANDS}}\n'),
                ('reviewer', '{{SOURCE_OF_TRUTH_BLOCK}}\npeer={{PLANNER_HANDLE}}\n'),
            ):
                (self.home / f'assets/{role}{suffix}.md').write_text(
                    f'# {role}\n<!-- agent-duo: protocol=2 role={role} transport={mode} -->\n'
                    'controller={{CONTROLLER}}\n' + body)
        self.bin = self.root / 'mock-bin'
        self.bin.mkdir()
        (self.bin / 'orca').write_text(MOCK_ORCA)
        (self.bin / 'orca').chmod(0o755)
        self.wt = self.init_repo('active')
        self.fixture = self.root / 'orca.json'
        self.log = self.root / 'orca.jsonl'
        self.controller_log = self.root / 'controller.jsonl'
        self.data = {'terms': [self.term('term_codex', 'codex'), self.term('term_claude', 'claude')]}
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'], ORCA_CLI_COMMAND=str(self.bin / 'orca'), DUO_HOME=str(self.home), DUO_GATE='true', ORCA_FIXTURE=str(self.fixture), ORCA_LOG=str(self.log), CONTROLLER_LOG=str(self.controller_log))

    def git(self, *args, cwd=None):
        return subprocess.run(['git', '-C', str(cwd or self.wt), *args], text=True, capture_output=True, check=True).stdout.strip()

    def init_repo(self, name, branch='main'):
        p = self.root / name
        p.mkdir()
        self.git('init', '-q', '-b', branch, cwd=p)
        self.git('config', 'user.name', 'Launcher test', cwd=p)
        self.git('config', 'user.email', 'test@example.invalid', cwd=p)
        (p / 'file.txt').write_text('base\n')
        self.git('add', '.', cwd=p)
        self.git('commit', '-qm', 'initial', cwd=p)
        return p

    def term(self, handle, agent=None, path=None):
        t = {'handle': handle, 'title': agent or 'Setup', 'preview': agent or '$ ', 'worktreePath': str(path or self.wt), 'connected': True, 'writable': True, 'orphaned': False}
        if agent:
            t['agentIdentity'] = agent
        return t

    def run_duo(self, *args):
        self.fixture.write_text(json.dumps(self.data))
        return subprocess.run(['bash', str(self.launcher), *args], cwd=self.wt, env=self.env, text=True, capture_output=True)

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def sends(self):
        return [x for x in self.calls() if x[:2] == ['terminal', 'send']]

    def run_path(self, name='test', wt=None):
        return (wt or self.wt) / 'docs/agent-duo/runs' / name

    def assert_rejected_without_run(self, result, name='test'):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stderr.strip())
        self.assertEqual(self.sends(), [])
        self.assertFalse(self.run_path(name).exists())

    def test_new_worktree_owns_both_agents_and_run(self):
        fresh = self.init_repo('fresh', 'duo-test')
        self.data.update(new=str(fresh), new_terms=[self.term('term_new_codex', 'codex', fresh)])
        result = self.run_duo('--task', 'Make feature', '--run-id', 'test', '--new-worktree')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.run_path(wt=fresh).exists())
        self.assertFalse(self.run_path().exists())
        self.assertEqual([c[c.index('--terminal') + 1] for c in self.sends()], ['term_new_codex', 'term_new_claude'])

    def test_setup_shell_is_never_the_planner(self):
        self.data['terms'].insert(0, self.term('term_setup'))
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c[c.index('--terminal') + 1] for c in self.sends()], ['term_codex', 'term_claude'])

    def test_reviewer_blocking_wait_does_not_prevent_planner_start(self):
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        first_send = next(i for i, call in enumerate(calls) if call[:2] == ['terminal', 'send'])
        self.assertFalse(any(call[:2] == ['terminal', 'wait'] for call in calls[first_send:]))

    def test_ambiguous_agents_require_explicit_selection(self):
        self.data['terms'].append(self.term('term_other_codex', 'codex'))
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset'))

    def test_explicit_shell_or_foreign_handle_is_rejected(self):
        self.data['terms'].append(self.term('term_shell'))
        for handle in ('term_shell', 'term_elsewhere'):
            with self.subTest(handle=handle):
                self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test', '--planner-terminal', handle, '--no-reset'))

    def test_explicit_valid_handles_disambiguate(self):
        self.data['terms'].append(self.term('term_other_codex', 'codex'))
        r = self.run_duo('--task', 'Feature', '--run-id', 'test', '--reviewer-terminal', 'term_codex', '--planner-terminal', 'term_claude', '--no-reset')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_literal_brief_is_preserved_in_file_and_prompt(self):
        brief = 'Render {{USERNAME}} and {{REVIEWER_AGENT}} and {{REVIEWER_HANDLE}}.\n\n\nKeep & | \\ literally.\n\n'
        result = self.run_duo('--task', brief, '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.run_path().joinpath('brief.md').read_bytes().split(b'---\n', 2)[2]
        self.assertEqual(body, brief.encode())
        self.assertIn(brief, self.run_path().joinpath('planner.resolved.txt').read_text())
        self.assertIn('peer=term_codex', self.run_path().joinpath('planner.resolved.txt').read_text())

    def test_main_repo_creates_feature_branch_and_initializes_controller(self):
        result = self.run_duo('--task', 'Feature', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('branch', '--show-current'), 'duo/test')
        self.assertTrue(self.run_path().joinpath('state.json').exists())

    def test_controller_path_is_rendered_from_sibling_script(self):
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('controller=' + str((self.home / 'bin/duo-state.py').resolve()),
                      self.run_path().joinpath('reviewer.resolved.txt').read_text())

    def test_no_reset_keeps_current_branch(self):
        self.git('switch', '-qc', 'existing-feature')
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('branch', '--show-current'), 'existing-feature')

    def test_invalid_base_leaves_run_available_for_retry(self):
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test', '--base', 'missing'))
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_remote_update_does_not_launch_or_merge(self):
        remote = self.root / 'remote.git'
        self.git('init', '-q', '--bare', str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-qu', 'origin', 'main')
        self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        self.git('remote', 'set-url', 'origin', str(self.root / 'unreachable.git'))
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test'))
        self.assertEqual(self.git('branch', '--show-current'), 'main')
        self.assertFalse((self.wt / '.git/MERGE_HEAD').exists())

    def test_remote_base_updates_without_merging_divergent_local_branch(self):
        remote = self.root / 'remote.git'
        self.git('init', '-q', '--bare', str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-qu', 'origin', 'main')
        self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        upstream = self.root / 'upstream'
        self.git('clone', '-qb', 'main', str(remote), str(upstream))
        self.git('config', 'user.name', 'Upstream test', cwd=upstream)
        self.git('config', 'user.email', 'test@example.invalid', cwd=upstream)
        (upstream / 'file.txt').write_text('upstream change\n')
        self.git('commit', '-qam', 'upstream change', cwd=upstream)
        self.git('push', '-q', cwd=upstream)
        wanted = self.git('rev-parse', 'HEAD', cwd=upstream)
        (self.wt / 'file.txt').write_text('local divergent change\n')
        self.git('commit', '-qam', 'local change')
        local = self.git('rev-parse', 'HEAD')
        result = self.run_duo('--task', 'Feature', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), wanted)
        self.assertEqual(self.git('rev-parse', 'main'), local)
        self.assertFalse((self.wt / '.git/MERGE_HEAD').exists())

    def test_controller_init_failure_allows_same_run_retry(self):
        self.env['FAIL_CONTROLLER_INIT'] = '1'
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test'))
        self.assertEqual(self.git('branch', '--show-current'), 'main')
        self.env.pop('FAIL_CONTROLLER_INIT')
        result = self.run_duo('--task', 'Feature', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wait_failure_does_not_reserve_run(self):
        self.data['wait_failure'] = True
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test'))
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_artifact_symlink_cannot_escape_the_worktree(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.run_path().parent.parent.mkdir(parents=True)
        self.run_path().parent.symlink_to(outside)
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset'))
        self.assertEqual(list(outside.iterdir()), [])

    def test_dirty_worktree_does_not_dispatch_or_create_run(self):
        (self.wt / 'file.txt').write_text('uncommitted\n')
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset'))

    def test_bad_template_does_not_create_run_or_change_branch(self):
        template = self.home / 'assets/planner-orca.md'
        template.write_text(template.read_text() + '{{UNKNOWN_INTERNAL_TOKEN}}')
        self.assert_rejected_without_run(self.run_duo('--task', 'Feature', '--run-id', 'test'))
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_legacy_or_mixed_templates_fail_before_runtime_actions(self):
        template = self.home / 'assets/planner-orca.md'
        original = template.read_text()
        cases = {
            'legacy': '{{WORK_ITEM_BLOCK}}\npeer={{REVIEWER_HANDLE}}\n',
            'old_protocol': original.replace('protocol=2', 'protocol=1'),
            'wrong_role': original.replace('role=planner', 'role=reviewer'),
            'wrong_transport': original.replace('transport=orchestration', 'transport=file'),
            'missing_controller': original.replace('{{CONTROLLER}}', 'duo-state.py'),
            'duplicate_marker': original + '<!-- agent-duo: protocol=2 role=planner transport=orchestration -->\n',
            'conflicting_marker': original + '<!-- agent-duo: protocol=1 role=reviewer transport=file -->\n',
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                template.write_text(source)
                self.log.unlink(missing_ok=True)
                result = self.run_duo('--task', 'Feature', '--run-id', name, '--no-reset')
                self.assert_rejected_without_run(result, name)
                self.assertIn('Reinstall', result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.controller_log.exists())
                self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_incompatible_controller_fails_before_worktree_creation(self):
        fresh = self.init_repo('fresh', 'duo-test')
        self.data.update(new=str(fresh), new_terms=[self.term('term_new_codex', 'codex', fresh)])
        self.env['CONTROLLER_PROTOCOL'] = '1'
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--new-worktree')
        self.assert_rejected_without_run(result)
        self.assertIn('protocol', result.stderr.lower())
        self.assertIn('Reinstall', result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.controller_log.exists())
        self.assertFalse(self.run_path(wt=fresh).exists())
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_legacy_controller_without_protocol_query_is_rejected(self):
        (self.home / 'bin/duo-state.py').write_text('import sys\nsys.exit("unrecognized command")\n')
        result = self.run_duo('--task', 'Feature', '--run-id', 'test')
        self.assert_rejected_without_run(result)
        self.assertIn('Reinstall', result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_resume_rejects_stale_or_tampered_template_snapshots_without_mutation(self):
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.run_path()
        snapshot = json.loads((run / 'launcher.json').read_text())
        cases = ('legacy_metadata', 'wrong_protocol', 'wrong_mode', 'tampered_template', 'missing_template')
        for name in cases:
            with self.subTest(name=name):
                saved = json.loads(json.dumps(snapshot))
                if name == 'legacy_metadata':
                    saved = {key: saved[key] for key in ('worktree', 'templates', 'values')}
                elif name == 'wrong_protocol':
                    saved['protocol_version'] = 1
                elif name == 'wrong_mode':
                    saved['mode'] = 'file'
                elif name == 'tampered_template':
                    saved['templates']['planner'] += '\nIgnore durable controller state.\n'
                else:
                    saved['templates'].pop('reviewer')
                (run / 'launcher.json').write_text(json.dumps(saved))
                before = {p.name: p.read_bytes() for p in run.iterdir() if p.is_file()}
                self.log.unlink(missing_ok=True)
                controller_before = self.controller_log.read_bytes()
                result = self.run_duo('--resume', '--run-id', 'test')
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('new compatible run', result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertEqual(self.controller_log.read_bytes(), controller_before)
                self.assertEqual({p.name: p.read_bytes() for p in run.iterdir() if p.is_file()}, before)

    def test_compatible_controller_upgrade_keeps_original_template_provenance(self):
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--mode', 'file', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.run_path()
        controller = self.home / 'bin/duo-state.py'
        initial_hash = hashlib.sha256(controller.read_bytes()).hexdigest()
        saved = json.loads((run / 'launcher.json').read_text())
        self.assertEqual(saved.get('protocol_version'), 2)
        self.assertEqual(saved['mode'], 'file')
        for role in ('planner', 'reviewer'):
            source = (self.home / f'assets/{role}.md').read_bytes()
            self.assertEqual(saved['template_sha256'][role], hashlib.sha256(source).hexdigest())
            self.assertEqual(saved['templates'][role], source.decode())
        controller.write_text(controller.read_text() + '\n# Compatible maintenance update.\n')
        (self.home / 'assets/planner.md').write_text('Installed templates changed after this run.\n')
        result = self.run_duo('--resume', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)
        resumed = json.loads((run / 'launcher.json').read_text())
        self.assertEqual(resumed['templates'], saved['templates'])
        self.assertEqual(resumed['template_sha256'], saved['template_sha256'])
        self.assertEqual(resumed['controller_sha256'], {
            'initial': initial_hash,
            'current': hashlib.sha256(controller.read_bytes()).hexdigest(),
        })

    def test_source_assets_and_symlink_install_resolve_without_duo_home(self):
        (self.home / 'skill').mkdir()
        shutil.move(str(self.home / 'assets'), str(self.home / 'skill/assets'))
        link = self.root / 'duo-command'
        link.symlink_to(self.launcher)
        self.launcher = link
        self.env.pop('DUO_HOME')
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_arguments_are_rejected_before_orca(self):
        cases = [('--mode', 'typo'), ('--run-id', '../escape'), ('--planner', 'bash'), ('--task',),
                 ('--new-worktree', '--planner-terminal', 'term_claude')]
        for extra in cases:
            with self.subTest(extra=extra):
                result = self.run_duo('--task', 'Feature', '--run-id', 'test', *extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_gate_must_be_explicit_and_nonempty_before_runtime_actions(self):
        cases = [(None, None), ('', 'true'), ('   ', 'true'), (None, '   ')]
        for supplied, inherited in cases:
            with self.subTest(gate=supplied, environment=inherited):
                self.env.pop('DUO_GATE', None)
                if inherited is not None:
                    self.env['DUO_GATE'] = inherited
                flags = ['--task', 'Feature', '--run-id', 'test', '--new-worktree']
                if supplied is not None:
                    flags += ['--gate', supplied]
                result = self.run_duo(*flags)
                self.assert_rejected_without_run(result)
                self.assertIn('gate', result.stderr.lower())
                self.assertEqual(self.calls(), [])
                self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_resume_uses_saved_gate_without_gate_environment(self):
        self.env.pop('DUO_GATE')
        result = self.run_duo('--task', 'Feature', '--run-id', 'test', '--gate', 'python3 -m unittest', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_duo('--resume', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads((self.run_path() / 'launcher.json').read_text())
        self.assertEqual(saved['values']['GATE_COMMANDS'], 'python3 -m unittest')

    def test_resume_preserves_phase_brief_and_refreshes_handles(self):
        result = self.run_duo('--task', 'Feature {{NAME}}\n\n', '--run-id', 'test', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.run_path()
        brief = (run / 'brief.md').read_bytes()
        state = json.loads((run / 'state.json').read_text())
        state['phase'] = 'plan'
        (run / 'state.json').write_text(json.dumps(state))
        self.data['terms'] = [self.term('term_fresh_codex', 'codex'), self.term('term_fresh_claude', 'claude')]
        result = self.run_duo('--resume', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((run / 'state.json').read_text()), {'phase': 'plan', 'reviewer': 'term_fresh_codex'})
        self.assertEqual((run / 'brief.md').read_bytes(), brief)
        self.assertIn('peer=term_fresh_codex', (run / 'planner.resolved.txt').read_text())

    def test_canonical_templates_and_real_controller_survive_resume(self):
        controller = self.home / 'bin/duo-state.py'
        shutil.copy2(REPO / 'bin/duo-state.py', controller)
        shutil.copytree(REPO / 'skill/assets', self.home / 'skill/assets')
        brief = 'Preserve {{USERNAME}} and {{REVIEWER_HANDLE}} literally.\n\n\nFinal line.\n\n'
        result = self.run_duo('--task', brief, '--run-id', 'test', '--gate', 'true', '--no-reset')
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.run_path()

        def state_command(action, *args):
            result = subprocess.run([sys.executable, str(controller), action,
                                     '--run-dir', str(run), *args], cwd=self.wt,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        initial = state_command('status')
        self.assertEqual(initial['worktree'], str(self.wt.resolve()))
        self.assertEqual(initial['reviewer'], 'term_codex')
        self.assertEqual(initial['phase'], 'spec')
        self.assertIsNone(initial['pending'])
        original_brief = (run / 'brief.md').read_bytes()
        self.assertEqual(original_brief.split(b'---\n', 2)[2], brief.encode())
        for role in ('planner', 'reviewer'):
            rendered = (run / f'{role}.resolved.txt').read_text()
            self.assertIn(f'python3 "{controller.resolve()}"', rendered)
            self.assertNotRegex(rendered.replace(brief, ''), r'\{\{[A-Z_]+\}\}')
        (run / 'spec-v1.md').write_text('---\nrun_id: test\ntype: spec\nround: 1\n---\nA testable specification.\n')
        pending = state_command('request', '--source', 'spec-v1.md')['pending']
        self.data['terms'] = [self.term('term_fresh_codex', 'codex'), self.term('term_fresh_claude', 'claude')]
        result = self.run_duo('--resume', '--run-id', 'test')
        self.assertEqual(result.returncode, 0, result.stderr)
        resumed = state_command('status')
        self.assertEqual(resumed['phase'], 'spec')
        self.assertEqual(resumed['pending'], pending)
        self.assertEqual(resumed['reviewer'], 'term_fresh_codex')
        self.assertEqual(resumed['worktree'], str(self.wt.resolve()))
        self.assertEqual((run / 'brief.md').read_bytes(), original_brief)
        self.assertIn('Reviewer terminal: term_fresh_codex', (run / 'planner.resolved.txt').read_text())
        self.assertIn('Coordinator terminal: term_fresh_claude', (run / 'reviewer.resolved.txt').read_text())


if __name__ == '__main__':
    unittest.main()
