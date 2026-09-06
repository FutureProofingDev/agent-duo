"""Behavioral controller tests using real Git and isolated run artifacts."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest
import github_fixture

SCRIPT = Path(__file__).resolve().parents[1] / 'bin' / 'duo-state.py'


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.env = github_fixture.environment(self.repo)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Duo tests')
        self.git('config', 'user.email', 'duo@example.invalid')
        (self.repo / 'code.txt').write_text('baseline\n')
        (self.repo / '.gitignore').write_text('docs/agent-duo/runs/\ngithub-fixture/\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.run = self.repo / 'docs/agent-duo/runs/test-run'
        self.run.mkdir(parents=True)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def cli(self, command, *args, ok=True):
        self.assertTrue(SCRIPT.is_file(), 'deterministic controller is not implemented')
        result = subprocess.run([sys.executable, str(SCRIPT), command, '--run-dir', str(self.run), *map(str, args)], text=True, capture_output=True, env=self.env)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def init(self, gate='true', *args):
        return self.cli('init', '--run-id', 'test-run', '--worktree', self.repo, '--gate', gate, '--reviewer', 'reviewer-1', *args)

    def artifact(self, name, fields, body='content\n'):
        text = '---\n' + ''.join(f'{k}: {json.dumps(v)}\n' for k, v in fields.items()) + '---\n' + body
        (self.run / name).write_text(text)
        return name

    def source(self, kind, round=1, **extra):
        name = f'{kind}-v{round}.md' if kind != 'pr-request' else f'prr-123-v{round}.md'
        return self.artifact(name, dict(run_id='test-run', type=kind, round=round, **extra), 'https://github.com/example/project/pull/123\n' if kind == 'pr-request' else 'content\n')

    def review(self, pending, status='approved', **extra):
        fields = dict(run_id='test-run', type='review', round=pending['round'], source=pending['source'], source_sha256=pending['source_sha256'], request_id=pending['request_id'], reviewer='reviewer-1', status=status)
        if pending.get('head_sha'):
            fields['head_sha'] = pending['head_sha']
        fields.update(extra)
        return self.artifact('cr-' + pending['source'], fields, ''.join(f'## {n}. Criterion\nEvidence and decision.\n' for n in range(1, 6)) + '\n## Pending manual checks\nVoiceOver pending.\n')

    def approve(self, source):
        pending = self.cli('request', '--source', source)['pending']
        state = self.cli('accept', '--review', self.review(pending))
        if pending['kind'] == 'pr':
            state = self.cli('publish-review', '--repo', 'example/project')
        return state

    def executing(self, gate='true'):
        self.init(gate)
        self.approve(self.source('spec'))
        self.approve(self.source('plan'))

    def pr(self):
        self.cli('gate')
        return self.source('pr-request', head_sha=self.git('rev-parse', 'HEAD'), pr_number=123)

    def test_ordered_rounds_and_idempotent_review(self):
        self.init()
        self.cli('request', '--source', self.source('plan'), ok=False)
        spec = self.source('spec')
        pending = self.cli('request', '--source', spec)['pending']
        again = self.cli('request', '--source', spec)['pending']
        self.assertEqual(again, pending)
        review = self.review(pending)
        self.assertEqual(self.cli('accept', '--review', review)['phase'], 'plan')
        self.assertEqual(self.cli('accept', '--review', review)['phase'], 'plan')

    def test_wrong_run_reviewer_and_source_hash_cannot_approve(self):
        self.init()
        pending = self.cli('request', '--source', self.source('spec'))['pending']
        self.cli('accept', '--review', self.review(pending, run_id='other'), ok=False)
        self.cli('accept', '--review', self.review(pending, reviewer='other'), ok=False)
        self.assertEqual(self.cli('status')['phase'], 'escalated')
        self.cli('resume', '--reason', 'Correct the reviewer contract')
        self.cli('accept', '--review', self.review(pending, source_sha256='0' * 64), ok=False)
        self.assertNotEqual(self.cli('status')['phase'], 'plan')

    def test_changed_source_cannot_reuse_pending_approval(self):
        self.init()
        source = self.source('spec')
        pending = self.cli('request', '--source', source)['pending']
        with (self.run / source).open('a') as out:
            out.write('Changed after dispatch\n')
        self.cli('accept', '--review', self.review(pending), ok=False)
        self.assertNotEqual(self.cli('status')['phase'], 'plan')

    def test_frozen_spec_is_checked_before_execution(self):
        self.executing()
        (self.run / 'spec-v1.md').write_text('changed')
        self.cli('gate', ok=False)

    def test_failed_gate_records_failure_and_prevents_pr(self):
        self.executing('exit 7')
        self.cli('gate', ok=False)
        state = self.cli('status')
        self.assertEqual(state['gate_result']['exit_code'], 7)
        self.cli('request', '--source', self.source('pr-request', head_sha=self.git('rev-parse', 'HEAD'), pr_number=123), ok=False)

    def test_untracked_code_and_dirty_worktree_reject_gate(self):
        self.executing()
        (self.repo / 'new-code.py').write_text('broken')
        self.cli('gate', ok=False)
        (self.repo / 'new-code.py').unlink()
        (self.repo / 'code.txt').write_text('modified')
        self.cli('gate', ok=False)

    def test_new_commit_invalidates_gate(self):
        self.executing()
        self.cli('gate')
        (self.repo / 'code.txt').write_text('new version')
        self.git('add', 'code.txt')
        self.git('commit', '-qm', 'change')
        self.cli('request', '--source', self.source('pr-request', head_sha=self.git('rev-parse', 'HEAD'), pr_number=123), ok=False)

    def test_new_commit_invalidates_pr_approval(self):
        self.executing()
        pending = self.cli('request', '--source', self.pr())['pending']
        (self.repo / 'code.txt').write_text('new version')
        self.git('add', 'code.txt')
        self.git('commit', '-qm', 'change')
        self.cli('accept', '--review', self.review(pending), ok=False)

    def test_changes_requested_require_new_version_and_gate(self):
        self.executing()
        pending = self.cli('request', '--source', self.pr())['pending']
        self.assertEqual(self.cli('accept', '--review', self.review(pending, 'changes_requested'))['phase'], 'executing')
        self.cli('request', '--source', pending['source'], ok=False)
        source = self.source('pr-request', 2, head_sha=self.git('rev-parse', 'HEAD'), pr_number=123)
        self.cli('request', '--source', source, ok=False)
        self.cli('gate')
        self.assertEqual(self.cli('request', '--source', source)['pending']['round'], 2)

    def test_round_limit_escalates(self):
        self.init()
        for round in range(1, 4):
            pending = self.cli('request', '--source', self.source('spec', round))['pending']
            self.cli('accept', '--review', self.review(pending, 'changes_requested'))
        self.assertEqual(self.cli('status')['phase'], 'escalated')

    def test_memory_finalization_is_committed_idempotent_and_preserves_code_head(self):
        self.executing()
        self.approve(self.pr())
        before = self.git('rev-parse', 'HEAD')
        proposal = self.run / 'proposals.json'
        proposal.write_text(json.dumps([dict(pattern='Check null input', scope='API', evidence=['cr-spec-v1.md'], resolution='verified')]))
        self.assertEqual(self.cli('finalize', '--lessons', proposal)['phase'], 'completed')
        self.assertEqual(self.cli('finalize', '--lessons', proposal)['phase'], 'completed')
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        ledger = json.loads(self.git('show', 'refs/agent-duo/learning:learning.json'))
        self.assertEqual(len(ledger['runs']), 1)
        self.assertEqual(len(ledger['lessons']), 1)
        self.assertEqual(ledger['lessons'][0]['status'], 'pending')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_finalize_rechecks_current_head(self):
        self.executing()
        self.approve(self.pr())
        self.git('commit', '--allow-empty', '-qm', 'new head')
        self.cli('finalize', ok=False)
        self.assertNotEqual(self.cli('status')['phase'], 'completed')

    def test_missing_learning_evidence_cannot_be_committed(self):
        self.executing()
        self.approve(self.pr())
        proposal = self.run / 'proposals.json'
        proposal.write_text(json.dumps([dict(pattern='Claim', scope='API', evidence=['missing.md'], resolution='verified')]))
        self.cli('finalize', '--lessons', proposal, ok=False)

    def test_resume_recovers_pending_and_refreshes_reviewer(self):
        self.init()
        pending = self.cli('request', '--source', self.source('spec'))['pending']
        state = self.cli('resume', '--reviewer', 'reviewer-2')
        self.assertEqual(state['pending'], pending)
        self.cli('accept', '--review', self.review(pending, reviewer='reviewer-2'))

    def test_timeout_requires_explicit_resume_reason(self):
        self.init('true', '--idle-timeout', '0.001')
        self.assertEqual(self.cli('status')['phase'], 'escalated')
        self.cli('resume', ok=False)
        self.assertEqual(self.cli('resume', '--reason', 'Human resumes timed out work')['phase'], 'spec')

    def test_wait_uses_time_not_poll_count(self):
        self.init()
        revision = self.cli('status')['revision']
        state = self.cli('wait', '--after', revision, '--timeout', '0.02')
        self.assertTrue(state['timed_out'])
        self.assertEqual(state['phase'], 'spec')

    def test_gate_timeout_is_recorded(self):
        self.executing('sleep 30')
        self.cli('gate', '--timeout', '0.02', ok=False)
        self.assertEqual(self.cli('status')['gate_result']['exit_code'], 124)

    def test_resume_clears_an_interrupted_gate_without_trusting_its_result(self):
        self.executing()
        state = self.cli('status')
        state['gate_running'] = dict(token='interrupted', owner_pid=999999999,
                                     deadline=0, head_sha=self.git('rev-parse', 'HEAD'))
        (self.run / 'state.json').write_text(json.dumps(state))
        recovered = self.cli('resume')
        self.assertNotIn('gate_running', recovered)
        self.assertIsNone(recovered['gate_result'])
        self.cli('gate')

    def test_resume_does_not_signal_a_reused_process_id(self):
        self.executing()
        unrelated = subprocess.Popen(['sleep', '30'], start_new_session=True)
        self.addCleanup(lambda: unrelated.wait(timeout=3))
        self.addCleanup(lambda: unrelated.terminate() if unrelated.poll() is None else None)
        state = self.cli('status')
        state['gate_running'] = dict(token='old-run', owner_pid=999999999,
                                     owner_identity='old-owner', child_pid=unrelated.pid,
                                     child_identity='old-child', deadline=0,
                                     head_sha=self.git('rev-parse', 'HEAD'))
        (self.run / 'state.json').write_text(json.dumps(state))
        self.assertNotIn('gate_running', self.cli('resume'))
        time.sleep(0.05)
        self.assertIsNone(unrelated.poll(), 'resume killed a process from a different lifetime')

    def test_malformed_frontmatter_counts_toward_delivery_budget(self):
        self.init()
        self.cli('request', '--source', self.source('spec'))
        (self.run / 'bad.md').write_text('not a review')
        self.cli('accept', '--review', 'bad.md', ok=False)
        self.cli('accept', '--review', 'bad.md', ok=False)
        self.assertEqual(self.cli('status')['phase'], 'escalated')

    def test_new_commit_can_restart_pr_after_prior_approval(self):
        self.executing()
        self.approve(self.pr())
        self.git('commit', '--allow-empty', '-qm', 'new HEAD')
        self.cli('gate')
        self.approve(self.source('pr-request', 2, head_sha=self.git('rev-parse', 'HEAD'), pr_number=123))
        self.assertEqual(self.cli('finalize')['phase'], 'completed')

    def test_committed_completion_recovers_after_state_write_was_interrupted(self):
        self.executing()
        self.approve(self.pr())
        before = self.cli('status')
        completed = self.cli('finalize')
        # Simulate a crash after committing the ledger, before saving state.json.
        (self.run / 'state.json').write_text(json.dumps(before))
        self.git('commit', '--allow-empty', '-qm', 'later work')
        restored = self.cli('resume')
        self.assertEqual(restored['phase'], 'completed')
        self.assertEqual(restored['completed_at'], completed['completed_at'])
        self.assertEqual(len(self.cli('memory')['runs']), 1)

    def test_gate_sigterm_stops_its_process_group_and_invalidates_result(self):
        self.executing('sleep 30')
        process = subprocess.Popen([sys.executable, str(SCRIPT), 'gate', '--run-dir', str(self.run)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = json.loads((self.run / 'state.json').read_text())
            if (state.get('gate_running') or {}).get('child_pid'):
                child = state['gate_running']['child_pid']
                def stop_orphan():
                    try:
                        os.killpg(child, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.addCleanup(stop_orphan)
                break
            time.sleep(0.02)
        else:
            self.fail('gate process never became ready')
        process.terminate()
        process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        state = self.cli('status')
        self.assertNotIn('gate_running', state)
        self.assertNotEqual(state['gate_result']['exit_code'], 0)


if __name__ == '__main__':
    unittest.main()
