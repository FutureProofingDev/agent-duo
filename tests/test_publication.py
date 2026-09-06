"""Publication is SHA-bound, recoverable and required before completion."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_state
import github_fixture


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.case = test_state.ControllerTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.executing()
        source = self.case.pr()
        pending = self.case.cli('request', '--source', source)['pending']
        self.case.cli('accept', '--review', self.case.review(pending))

    def publish(self, ok=True):
        return self.case.cli('publish-review', '--repo', 'example/project', ok=ok)

    def comments(self):
        p = Path(self.case.env['DUO_TEST_GITHUB']) / 'comments.json'
        return json.loads(p.read_text()) if p.exists() else []

    def test_publication_required_and_preserves_manual_limits(self):
        self.case.cli('finalize', ok=False)
        state = self.publish()
        self.assertEqual(state['phase'], 'finalizing')
        self.assertEqual(state['publication']['head_sha'], self.case.git('rev-parse', 'HEAD'))
        self.assertIn('VoiceOver pending', self.comments()[0]['body'])
        self.assertIn('## 5. Criterion', self.comments()[0]['body'])
        self.assertEqual(self.case.cli('finalize')['phase'], 'completed')

    def test_retry_and_lost_response_do_not_duplicate_comment(self):
        github_fixture.configure(self.case.env, uncertain_post=True)
        self.publish(ok=False)
        self.assertEqual(len(self.comments()), 1)
        github_fixture.configure(self.case.env)
        self.publish()
        self.publish()
        self.assertEqual(len(self.comments()), 1)

    def test_wrong_remote_head_cannot_publish_or_finalize(self):
        github_fixture.configure(self.case.env, head='a' * 40)
        self.publish(ok=False)
        self.assertEqual(self.comments(), [])
        github_fixture.configure(self.case.env)
        self.publish()
        github_fixture.configure(self.case.env, head='b' * 40)
        self.case.cli('finalize', ok=False)

    def test_changed_review_cannot_be_published(self):
        with (self.case.run / 'cr-prr-123-v1.md').open('a') as f:
            f.write('Unreviewed amendment\n')
        self.publish(ok=False)
        self.assertEqual(self.comments(), [])

    def test_modified_or_deleted_remote_comment_blocks_finalization(self):
        self.publish()
        p = Path(self.case.env['DUO_TEST_GITHUB']) / 'comments.json'
        comments = self.comments(); comments[0]['body'] = 'Different verdict'
        p.write_text(json.dumps(comments))
        self.case.cli('finalize', ok=False)

    def test_other_repository_cannot_receive_approval(self):
        self.case.cli('publish-review', '--repo', 'other/project', ok=False)
        self.assertEqual(self.comments(), [])

    def test_empty_manual_checks_section_cannot_approve(self):
        self.case.git('commit', '--allow-empty', '-qm', 'next revision')
        self.case.cli('gate')
        source = self.case.source('pr-request', round=2, head_sha=self.case.git('rev-parse', 'HEAD'), pr_number=123)
        pending = self.case.cli('request', '--source', source)['pending']
        name = self.case.review(pending)
        path = self.case.run / name
        path.write_text(path.read_text().replace('VoiceOver pending.', '\n## References\nGate passed.'))
        self.case.cli('accept', '--review', name, ok=False)
        self.assertEqual(self.case.cli('status')['phase'], 'pr')

    def test_protocol_probe_needs_no_repository_or_run(self):
        result = subprocess.run([sys.executable, str(test_state.SCRIPT), 'protocol'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['protocol_version'], 2)
