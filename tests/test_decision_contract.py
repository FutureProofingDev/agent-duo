"""Contract, evidence, ownership and bounded correction regressions via real Git."""
import json
import subprocess
import unittest
import test_state
from protocol_fixture import records, defect


class DecisionContractTests(unittest.TestCase):
    def setUp(self):
        self.c = test_state.ControllerTests()
        self.c.setUp()
        self.addCleanup(self.c.doCleanups)

    def request(self):
        self.c.init()
        return self.c.cli('request', '--source', self.c.source('spec'))['pending']

    def findings_review(self, pending, findings, status='approved'):
        name = self.c.review(pending, status)
        path = self.c.run / name
        body = path.read_text().split('\n## Findings\n')[0]
        path.write_text(body + records('Findings', findings))
        return name

    def test_spec_requires_all_four_nonempty_contract_sections(self):
        self.c.init()
        name = self.c.source('spec')
        path = self.c.run / name
        full = path.read_text()
        for heading in ('Observable outcome', 'Constraints', 'Pending assumptions', 'Acceptance evidence'):
            with self.subTest(heading=heading):
                path.write_text(full.replace('## ' + heading, '## Missing'))
                self.c.cli('request', '--source', name, ok=False)
        path.write_text(full)
        self.assertIsNotNone(self.c.cli('request', '--source', name)['pending'])

    def test_dirty_handoff_is_reviewable_but_changed_bytes_cannot_be_accepted(self):
        (self.c.repo / 'code.txt').write_text('uncommitted implementation')
        (self.c.repo / 'new file.txt').write_text('untracked implementation')
        pending = self.request()
        self.assertIn('code_state', pending)
        name = self.c.review(pending)
        (self.c.repo / 'new file.txt').write_text('different uncommitted implementation')
        self.c.cli('accept', '--review', name, ok=False)
        self.assertNotIn('spec', self.c.cli('status')['approved'])

    def test_snapshot_distinguishes_index_content_deletion_mode_and_symlink(self):
        self.c.init()
        def snapshot():
            return self.c.cli('snapshot')['state_sha256']
        before = snapshot()
        (self.c.repo / 'code.txt').write_text('changed')
        changed = snapshot()
        self.assertNotEqual(before, changed)
        self.c.git('add', 'code.txt')
        self.assertNotEqual(changed, snapshot())
        before = snapshot()
        (self.c.repo / 'code.txt').chmod(0o755)
        self.assertNotEqual(before, snapshot())
        before = snapshot()
        (self.c.repo / 'code.txt').unlink()
        self.assertNotEqual(before, snapshot())
        (self.c.repo / 'link').symlink_to('one')
        before = snapshot()
        (self.c.repo / 'link').unlink()
        (self.c.repo / 'link').symlink_to('two')
        self.assertNotEqual(before, snapshot())

    def test_unchanged_dirty_handoff_accepts_and_run_logs_do_not_change_snapshot(self):
        (self.c.repo / 'code.txt').write_text('dirty baseline')
        pending = self.request()
        (self.c.run / 'log-reviewer.md').write_text('inspection')
        self.assertEqual(self.c.cli('accept', '--review', self.c.review(pending))['phase'], 'plan')

    def test_reviewer_must_echo_the_reviewed_code_state(self):
        pending = self.request()
        self.c.cli('accept', '--review', self.c.review(pending, code_state_sha256='0' * 64), ok=False)
        self.assertIsNotNone(self.c.cli('status')['pending'])

    def test_writer_ownership_transfers_without_giving_reviewer_code_write_access(self):
        state = self.c.init()
        self.assertEqual(state['write_ownership']['code'], 'planner')
        pending = self.c.cli('request', '--source', self.c.source('spec'))['pending']
        owners = self.c.cli('status')['write_ownership']
        self.assertIsNone(owners['code'])
        self.assertEqual(owners['review'], 'reviewer-1')
        state = self.c.cli('accept', '--review', self.c.review(pending))
        self.assertEqual(state['write_ownership']['code'], 'planner')

    def test_preference_cannot_block_and_defect_needs_evidence(self):
        pending = self.request()
        finding = defect()
        finding['category'] = 'preference'
        self.c.cli('accept', '--review', self.findings_review(pending, [finding], 'changes_requested'), ok=False)
        finding['category'] = 'defect'
        finding['evidence'] = ''
        self.c.cli('accept', '--review', self.findings_review(pending, [finding], 'changes_requested'), ok=False)
        self.assertNotIn('spec', self.c.cli('status')['approved'])

    def test_relevant_uncertainty_blocks_without_claiming_a_demonstrated_defect(self):
        pending = self.request()
        finding = dict(defect(), category='uncertainty', evidence='Device unavailable',
                       claim='AC1 behavior on the target device is unknown')
        state = self.c.cli('accept', '--review', self.findings_review(pending, [finding], 'changes_requested'))
        self.assertEqual(state['open_findings'][0]['category'], 'uncertainty')
        self.assertNotIn('spec', state['approved'])

    def test_nonblocking_preferences_allow_approval(self):
        pending = self.request()
        finding = dict(defect(), category='preference', blocking=False)
        self.assertEqual(self.c.cli('accept', '--review', self.findings_review(pending, [finding]))['phase'], 'plan')

    def test_approval_cannot_hide_a_blocker(self):
        pending = self.request()
        self.c.cli('accept', '--review', self.findings_review(pending, [defect()]), ok=False)
        self.assertNotIn('spec', self.c.cli('status')['approved'])

    def test_next_round_requires_targeted_resolution_for_previous_blocker(self):
        pending = self.request()
        self.c.cli('accept', '--review', self.findings_review(pending, [defect()], 'changes_requested'))
        name = self.c.source('spec', 2)
        path = self.c.run / name
        path.write_text(path.read_text().split('\n## Resolutions\n')[0])
        self.c.cli('request', '--source', name, ok=False)
        path.write_text(path.read_text() + records('Resolutions', [dict(id='F1', disposition='disputed', evidence='AC1 excludes empty input; spec-v1.md Constraints')]))
        pending = self.c.cli('request', '--source', name)['pending']
        self.assertEqual(self.c.cli('accept', '--review', self.findings_review(pending, []))['phase'], 'plan')

    def test_exhaustion_retains_findings_and_never_finalizes(self):
        self.c.init()
        for round in range(1, 4):
            pending = self.c.cli('request', '--source', self.c.source('spec', round))['pending']
            state = self.c.cli('accept', '--review', self.findings_review(pending, [defect()], 'changes_requested'))
        self.assertEqual(state['phase'], 'escalated')
        self.assertEqual(state['open_findings'][0]['id'], 'F1')
        self.assertIsNone(state['write_ownership']['code'])
        self.c.cli('finalize', ok=False)
        self.assertNotIn('completed_at', self.c.cli('status'))

    def test_withdrawal_preserves_snapshot_and_consumes_the_round(self):
        pending = self.request()
        (self.c.repo / 'code.txt').write_text('new evidence')
        state = self.c.cli('withdraw', '--reason', 'Code changed during handoff')
        self.assertEqual(state['withdrawals'][0]['request'], pending)
        self.assertEqual(state['rounds']['spec'], 1)
        self.assertIsNone(state['pending'])
        self.assertEqual(state['write_ownership']['code'], 'planner')
        self.assertEqual(self.c.cli('request', '--source', self.c.source('spec', 2))['pending']['round'], 2)

    def test_legacy_state_cannot_be_silently_upgraded(self):
        self.c.init()
        path = self.c.run / 'state.json'
        state = json.loads(path.read_text())
        state['protocol_version'] = 2
        path.write_text(json.dumps(state))
        original = path.read_bytes()
        self.c.cli('resume', ok=False)
        self.assertEqual(path.read_bytes(), original)

    def test_gate_rejects_staged_change_even_if_working_file_matches_head(self):
        self.c.executing()
        (self.c.repo / 'code.txt').write_text('staged change')
        self.c.git('add', 'code.txt')
        (self.c.repo / 'code.txt').write_text('baseline\n')
        self.c.cli('gate', ok=False)
        self.assertIsNone(self.c.cli('status')['gate_result'])

    def test_hidden_git_changes_cannot_receive_gate_evidence(self):
        self.c.executing()
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                self.c.git('update-index', '--' + flag, 'code.txt')
                (self.c.repo / 'code.txt').write_text('hidden change')
                self.c.cli('gate', ok=False)
                self.c.git('update-index', '--no-' + flag, 'code.txt')
                (self.c.repo / 'code.txt').write_text('baseline\n')
        self.assertIsNone(self.c.cli('status')['gate_result'])

    def test_gate_that_modifies_code_cannot_succeed(self):
        self.c.executing("printf changed > code.txt")
        self.c.cli('gate', ok=False)
        self.assertEqual(self.c.cli('status')['gate_result']['exit_code'], 125)

    def test_dirty_submodule_content_invalidates_a_handoff(self):
        child = self.c.repo / 'module'
        child.mkdir()
        def git(*args):
            subprocess.run(['git', '-C', str(child), *args], check=True, capture_output=True)
        git('init', '-q')
        git('config', 'user.name', 'Duo tests')
        git('config', 'user.email', 'duo@example.invalid')
        (child / 'child.txt').write_text('baseline')
        git('add', '.')
        git('commit', '-qm', 'child')
        self.c.git('add', 'module')
        self.c.git('commit', '-qm', 'gitlink')
        pending = self.request()
        (child / 'child.txt').write_text('dirty child')
        self.c.cli('accept', '--review', self.c.review(pending), ok=False)
        self.assertNotIn('spec', self.c.cli('status')['approved'])

    def test_repeated_withdrawals_cannot_reset_round_budget(self):
        self.c.init()
        for round in range(1, 4):
            self.c.cli('request', '--source', self.c.source('spec', round))
            state = self.c.cli('withdraw', '--reason', 'Need revised evidence')
        self.assertEqual(state['phase'], 'escalated')
        self.assertEqual(len(state['withdrawals']), 3)
        self.c.cli('request', '--source', self.c.source('spec', 4), ok=False)
        self.c.cli('finalize', ok=False)

    def test_changes_requested_without_a_blocker_is_not_a_valid_review(self):
        pending = self.request()
        name = self.findings_review(pending, [], 'changes_requested')
        self.c.cli('accept', '--review', name, ok=False)
        self.assertEqual(self.c.cli('status')['pending']['request_id'], pending['request_id'])

    def test_gate_preserves_changed_pending_pr_until_explicit_withdrawal(self):
        self.c.executing()
        pending = self.c.cli('request', '--source', self.c.pr())['pending']
        self.c.git('commit', '--allow-empty', '-qm', 'changed code state')
        self.c.cli('gate', ok=False)
        self.assertEqual(self.c.cli('status')['pending'], pending)
        self.c.cli('withdraw', '--reason', 'External commit changed reviewed code')
        self.c.cli('gate')
        state = self.c.cli('status')
        self.assertEqual(state['withdrawals'][0]['request'], pending)
        self.assertEqual(state['rounds']['pr'], 1)

    def test_submodule_ignore_configuration_cannot_hide_dirty_gate_input(self):
        child = self.c.repo / 'module'
        child.mkdir()
        def git(*args):
            subprocess.run(['git', '-C', str(child), *args], check=True, capture_output=True)
        git('init', '-q')
        git('config', 'user.name', 'Duo tests')
        git('config', 'user.email', 'duo@example.invalid')
        (child / 'child.txt').write_text('baseline')
        git('add', '.')
        git('commit', '-qm', 'child')
        self.c.git('add', 'module')
        self.c.git('commit', '-qm', 'gitlink')
        self.c.executing()
        self.c.git('config', 'diff.ignoreSubmodules', 'all')
        (child / 'child.txt').write_text('uncommitted implementation')
        self.c.cli('gate', ok=False)
        self.assertIsNone(self.c.cli('status')['gate_result'])
