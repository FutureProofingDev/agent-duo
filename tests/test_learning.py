"""Learning lifecycle tests through the real CLI and shared Git worktree storage."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import github_fixture

SCRIPT = Path(__file__).resolve().parents[1] / 'bin' / 'duo-state.py'
MEMORY_REF = 'refs/agent-duo/learning'
PATTERN = 'Plans omit ownership validation for new relationships'


class Run:
    """A completed code review prepared through public controller transitions."""

    def __init__(self, case, repo, run_id):
        self.case = case
        self.repo = repo
        self.run_id = run_id
        self.path = repo / 'docs/agent-duo/runs' / run_id
        self.path.mkdir(parents=True)
        self.cli('init', '--run-id', run_id, '--worktree', repo,
                 '--gate', 'true', '--reviewer', 'reviewer')
        self.approve('spec-v1.md', type='spec', round=1)
        self.approve('plan-v1.md', type='plan', round=1)
        self.cli('gate')
        head = case.git(repo, 'rev-parse', 'HEAD')
        self.approve('prr-123-v1.md', type='pr-request', round=1,
                     pr_number=123, head_sha=head)
        case.assertEqual(self.cli('status')['phase'], 'finalizing')

    def command(self, action, *args):
        return [sys.executable, str(SCRIPT), action, '--run-dir', str(self.path),
                *map(str, args)]

    def cli(self, action, *args):
        result = subprocess.run(self.command(action, *args), text=True,
                                capture_output=True, timeout=15)
        self.case.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def artifact(self, name, fields, body):
        text = '---\n' + ''.join(f'{key}: {json.dumps(value)}\n'
                                  for key, value in fields.items()) + '---\n' + body
        (self.path / name).write_text(text)

    def approve(self, source, **fields):
        self.artifact(source, dict(run_id=self.run_id, **fields), 'https://github.com/example/project/pull/123\n' if fields['type'] == 'pr-request' else 'Reviewable evidence.\n')
        pending = self.cli('request', '--source', source)['pending']
        review = dict(run_id=self.run_id, type='review', round=pending['round'],
                      source=source, source_sha256=pending['source_sha256'],
                      request_id=pending['request_id'], reviewer='reviewer', status='approved')
        if pending.get('head_sha'):
            review['head_sha'] = pending['head_sha']
        name = 'cr-' + source
        self.artifact(name, review, ''.join(f'## {number}. Criterion\nEvidence checked.\n'
                                          for number in range(1, 6)) + '\n## Pending manual checks\nNone.\n')
        self.cli('accept', '--review', name)
        if pending['kind'] == 'pr':
            self.cli('publish-review', '--repo', 'example/project')

    def proposals(self, values):
        path = self.path / 'lessons-proposals.json'
        path.write_text(json.dumps(values))
        return path

    def finalize(self, values=()):
        result = self.cli('finalize', '--lessons', self.proposals(list(values)))
        self.case.assertEqual(result['phase'], 'completed')
        return result


def proposal(pattern=PATTERN, scope='plan'):
    return dict(pattern=pattern, scope=scope, evidence=['cr-plan-v1.md'],
                resolution='verified')


class LearningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        environment = patch.dict(os.environ, github_fixture.environment(self.directory))
        environment.start()
        self.addCleanup(environment.stop)
        self.repo = self.directory / 'repo'
        self.repo.mkdir()
        self.git(self.repo, 'init', '-q')
        self.git(self.repo, 'config', 'user.name', 'Duo learning tests')
        self.git(self.repo, 'config', 'user.email', 'duo@example.invalid')
        (self.repo / 'code.txt').write_text('baseline\n')
        (self.repo / '.gitignore').write_text('docs/agent-duo/runs/\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-qm', 'baseline')

    @staticmethod
    def git(repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args],
                                       text=True).strip()

    def memory(self):
        return json.loads(self.git(self.repo, 'show', MEMORY_REF + ':learning.json'))

    def completed(self, run_id, proposals=()):
        run = Run(self, self.repo, run_id)
        run.finalize(proposals)
        return run

    def test_promotion_requires_two_distinct_completed_runs(self):
        first = self.completed('first', [proposal()])
        memory = first.cli('memory')
        self.assertEqual([run['run_id'] for run in memory['runs']], ['first'])
        self.assertEqual(memory['lessons'][0]['status'], 'pending')

        second = Run(self, self.repo, 'second')
        self.assertEqual(second.cli('memory')['lessons'][0]['status'], 'pending')
        self.assertEqual(len(second.cli('memory')['runs']), 1,
                         'a reviewed but unfinalized run must not count')
        second.finalize([proposal()])
        memory = self.memory()
        self.assertEqual(memory['lessons'][0]['status'], 'active')
        self.assertEqual([item['run_id'] for item in memory['lessons'][0]['confirmations']],
                         ['first', 'second'])
        self.assertEqual([item['sequence'] for item in memory['runs']], [1, 2])
        self.assertEqual(second.cli('memory'), memory)

    def test_duplicate_proposals_and_finalize_retries_count_once(self):
        run = self.completed('dedup', [proposal(), proposal(PATTERN.upper(), ' PLAN ')])
        before = self.git(self.repo, 'rev-parse', MEMORY_REF)
        run.finalize([proposal(), proposal('A later retry must not add a lesson')])
        memory = self.memory()
        self.assertEqual(self.git(self.repo, 'rev-parse', MEMORY_REF), before,
                         'idempotent finalization should not create another memory commit')
        self.assertEqual(len(memory['runs']), 1)
        self.assertEqual(len(memory['lessons']), 1)
        self.assertEqual(len(memory['lessons'][0]['confirmations']), 1)
        self.assertEqual(memory['lessons'][0]['status'], 'pending')
        evidence = memory['lessons'][0]['confirmations'][0]['evidence']
        self.assertEqual(evidence[0]['source'], 'cr-plan-v1.md')
        self.assertEqual(len(evidence[0]['sha256']), 64)

    def test_five_unconfirmed_completions_cause_decay_and_recurrence_reactivates(self):
        self.completed('sighting-one', [proposal()])
        self.completed('sighting-two', [proposal()])
        for number in range(1, 5):
            with self.subTest(unconfirmed_completions=number):
                self.completed(f'quiet-{number}')
                self.assertEqual(self.memory()['lessons'][0]['status'], 'active')
        self.completed('quiet-5')
        dormant = self.memory()['lessons'][0]
        self.assertEqual(dormant['status'], 'dormant')
        self.assertEqual(dormant['last_confirmed_sequence'], 2)
        self.assertEqual(len(dormant['confirmations']), 2)
        self.completed('recurrence', [proposal()])
        memory = self.memory()
        active = memory['lessons'][0]
        self.assertEqual(active['id'], dormant['id'], 'reactivate the original lesson')
        self.assertEqual(active['status'], 'active')
        self.assertEqual(active['last_confirmed_sequence'], 8)
        self.assertEqual([item['run_id'] for item in active['confirmations']],
                         ['sighting-one', 'sighting-two', 'recurrence'])
        self.assertEqual(len(memory['runs']), 8)

    def test_concurrent_finalizations_share_a_lossless_ledger_across_worktrees(self):
        worktrees = [self.directory / 'left', self.directory / 'right']
        for index, path in enumerate(worktrees):
            self.git(self.repo, 'worktree', 'add', '-qb', f'work-{index}', str(path), 'HEAD')
        runs = [Run(self, path, name) for path, name in zip(worktrees, ['left', 'right'])]
        before_heads = [self.git(path, 'rev-parse', 'HEAD') for path in worktrees]
        common = Path(self.git(self.repo, 'rev-parse', '--git-common-dir'))
        if not common.is_absolute():
            common = self.repo / common
        processes = []
        try:
            # Hold the actual repository lock so both independent CLI processes
            # overlap in finalization before either can publish the shared ref.
            with (common / 'agent-duo-learning.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                for run in runs:
                    processes.append(subprocess.Popen(
                        run.command('finalize', '--lessons', run.proposals([proposal()])),
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                deadline = time.monotonic() + 10
                while True:
                    held = []
                    for run in runs:
                        with (run.path / '.state.lock').open('a') as state_lock:
                            try:
                                fcntl.flock(state_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except BlockingIOError:
                                held.append(True)
                            else:
                                held.append(False)
                                fcntl.flock(state_lock, fcntl.LOCK_UN)
                    if all(held):
                        break
                    self.assertLess(time.monotonic(), deadline,
                                    'both finalizers should reach their run locks')
                    for process in processes:
                        self.assertIsNone(process.poll(), 'finalizer exited before lock release')
                    time.sleep(0.01)
                self.assertTrue(all(process.poll() is None for process in processes))
                fcntl.flock(lock, fcntl.LOCK_UN)
            for process in processes:
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertEqual(json.loads(stdout)['phase'], 'completed')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()

        memory = self.memory()
        self.assertEqual({run['run_id'] for run in memory['runs']}, {'left', 'right'})
        self.assertEqual(sorted(run['sequence'] for run in memory['runs']), [1, 2])
        self.assertEqual(len(memory['lessons']), 1)
        self.assertEqual(memory['lessons'][0]['status'], 'active')
        self.assertEqual({item['run_id'] for item in memory['lessons'][0]['confirmations']},
                         {'left', 'right'})
        self.assertEqual(self.git(self.repo, 'rev-list', '--count', MEMORY_REF), '2')
        for run, path, before in zip(runs, worktrees, before_heads):
            self.assertEqual(run.cli('memory'), memory)
            self.assertEqual(self.git(path, 'rev-parse', 'HEAD'), before)
            self.assertEqual(self.git(path, 'status', '--porcelain'), '')

    def test_head_change_after_initial_validation_cannot_finalize(self):
        run = Run(self, self.repo, 'stale-during-finalize')
        proposals = run.proposals([proposal()])
        spec = importlib.util.spec_from_file_location('learning_barrier_controller', SCRIPT)
        controller_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller_module)
        original_valid_gate = controller_module.Controller.valid_gate
        initial_checked = threading.Event()
        continue_finalization = threading.Event()
        outcome = {}

        def barrier_after_initial_check(controller, state):
            head = original_valid_gate(controller, state)
            if not initial_checked.is_set():
                initial_checked.set()
                if not continue_finalization.wait(10):
                    raise AssertionError('test did not release finalization barrier')
            return head

        # Instrument timing only: every gate validation and memory operation is
        # real. The barrier proves the old HEAD already passed the first check,
        # unlike merely observing the run lock before that check may have run.
        controller_module.Controller.valid_gate = barrier_after_initial_check
        args = controller_module.parser().parse_args(
            ['finalize', '--run-dir', str(run.path), '--lessons', str(proposals)])

        def finalize():
            try:
                outcome['state'] = controller_module.Controller(run.path).execute(args)
            except Exception as error:
                outcome['error'] = error

        common = Path(self.git(self.repo, 'rev-parse', '--git-common-dir'))
        if not common.is_absolute():
            common = self.repo / common
        worker = threading.Thread(target=finalize, daemon=True)
        try:
            with (common / 'agent-duo-learning.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                worker.start()
                self.assertTrue(initial_checked.wait(10), repr(outcome))
                (self.repo / 'code.txt').write_text('new code after initial approval validation\n')
                self.git(self.repo, 'add', 'code.txt')
                self.git(self.repo, 'commit', '-qm', 'change while finalizer waits')
                continue_finalization.set()
                fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            continue_finalization.set()
            worker.join(timeout=15)
        self.assertFalse(worker.is_alive(), 'finalizer did not finish after lock release')
        self.assertNotIn('state', outcome, 'stale approval must not publish completion')
        self.assertIsInstance(outcome.get('error'), controller_module.InvalidRun)
        self.assertIn('current HEAD', str(outcome['error']))
        state = run.cli('status')
        self.assertEqual(state['phase'], 'finalizing')
        self.assertNotIn('completed_at', state)
        self.assertNotIn('memory_commit', state)
        self.assertEqual(run.cli('memory')['runs'], [])


if __name__ == '__main__':
    unittest.main()
