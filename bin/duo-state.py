#!/usr/bin/env python3
"""Deterministic, local controller for two cooperative agents (Python stdlib only)."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

MEMORY_REF = 'refs/agent-duo/learning'
PROTOCOL_VERSION = 2


class InvalidRun(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InvalidRun(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manual_checks(body):
    sections = re.findall(r'^## Pending manual checks[ \t]*\n(.*?)(?=^#{1,6}[ \t]|\Z)', body, re.M | re.S)
    require(len(sections) == 1 and sections[0].strip(), 'PR review must explicitly list Pending manual checks or None.')


def process_identity(pid):
    if not pid:
        return None
    # A persisted PID alone is unsafe after a delayed resume or reboot. ps works
    # on both supported Unix platforms; normalize locale/timezone for comparison.
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], text=True,
                            capture_output=True, env=dict(os.environ, LC_ALL='C', TZ='UTC'))
    return result.stdout.strip() or None


def atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def git(repo, *args, input=None, env=None, check=True):
    result = subprocess.run(['git', '-C', str(repo), *args], input=input, text=True,
                            capture_output=True, env=env)
    if check and result.returncode:
        raise InvalidRun(result.stderr.strip() or 'git command failed')
    return result.stdout.strip() if check else result


def artifact(run, filename):
    require(Path(filename).name == filename and filename not in ('.', '..'), 'artifact must be a basename inside the run')
    path = run / filename
    require(path.resolve().parent == run.resolve(), 'artifact escapes the run directory')
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise InvalidRun(f'cannot read artifact {filename}: {error}') from error
    text = raw.decode('utf-8')
    lines = text.splitlines()
    require(lines and lines[0] == '---', 'artifact needs flat YAML frontmatter')
    require('---' in lines[1:], 'unterminated frontmatter')
    end = lines.index('---', 1)
    fields = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        match = re.fullmatch(r'([a-z_][a-z0-9_]*):\s*(.+)', line)
        require(match is not None, 'frontmatter supports key: scalar values only')
        key, value = match.groups()
        require(key not in fields, f'duplicate frontmatter field: {key}')
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            else:
                require(not value.startswith(('"', '[', '{', '&', '*', '!', '|', '>')), 'use a plain or JSON-quoted scalar')
        require(type(value) in (str, int), 'frontmatter values must be strings or integers')
        fields[key] = value
    return fields, '\n'.join(lines[end + 1:]), digest(raw)


class Controller:
    def __init__(self, run):
        self.run = Path(run).resolve()
        require(self.run.is_dir(), 'run directory does not exist')
        self.path = self.run / 'state.json'

    @contextmanager
    def lock(self):
        with (self.run / '.state.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def load(self):
        require(self.path.is_file(), 'run is not initialized; use init')
        return json.loads(self.path.read_text())

    def save(self, state, progress=True):
        state['revision'] += 1
        state['updated_at'] = time.time()
        if progress:
            state['last_progress_at'] = state['updated_at']
        atomic_write(self.path, json.dumps(state, indent=2) + '\n')
        return state

    def init(self, args):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', args.run_id), 'invalid run ID')
        require(args.gate.strip(), 'gate command cannot be empty')
        repo = Path(git(args.worktree, 'rev-parse', '--show-toplevel')).resolve()
        require(repo == Path(args.worktree).resolve(), 'worktree must be the repository root')
        require(self.run.is_relative_to(repo) and self.run != repo, 'run must be inside its worktree')
        if self.path.exists():
            old = self.load()
            require(all(old[key] == value for key, value in dict(run_id=args.run_id, worktree=str(repo), gate=args.gate, reviewer=args.reviewer).items()), 'run already initialized with different settings')
            return old
        now = time.time()
        state = dict(schema_version=1, protocol_version=PROTOCOL_VERSION, run_id=args.run_id, instance_id=digest(os.urandom(32)), worktree=str(repo), reviewer=args.reviewer,
                     gate=args.gate, phase='spec', revision=0, pending=None, approved={}, history=[],
                     rounds=dict(spec=0, plan=0, pr=0), round_limits=dict(spec=3, plan=3, pr=3),
                     review_errors=0, gate_result=None, started_at=now, budget_started_at=now,
                     last_progress_at=now, updated_at=now, idle_timeout=args.idle_timeout,
                     run_timeout=args.run_timeout)
        return self.save(state)

    def escalate(self, state, reason):
        if state['phase'] != 'escalated':
            state['resume_phase'] = state['phase']
            state['phase'] = 'escalated'
            state['escalation_reason'] = reason
            self.save(state, progress=False)
        return state

    def deadlines(self, state):
        if state['phase'] in ('completed', 'escalated'):
            return state
        now = time.time()
        if now - state['budget_started_at'] > state['run_timeout']:
            return self.escalate(state, 'run time budget exhausted')
        running = state.get('gate_running')
        if not running or now > running['deadline']:
            if now - state['last_progress_at'] > state['idle_timeout']:
                return self.escalate(state, 'no progress within the idle time budget')
        return state

    def active(self, state):
        self.deadlines(state)
        require(state['phase'] not in ('completed', 'escalated'), 'run stopped; inspect status and explicitly resume if escalated')

    def frozen(self, state):
        for kind in ('spec', 'plan'):
            approved = state['approved'].get(kind)
            if approved:
                _, _, current = artifact(self.run, approved['source'])
                require(current == approved['source_sha256'], f'approved {kind} changed; restore it or start a new run')

    def clean_head(self, state):
        repo = state['worktree']
        require(not git(repo, 'ls-files', '--unmerged'), 'worktree has unresolved merge conflicts')
        require(not git(repo, 'diff', '--name-only', 'HEAD'), 'commit tracked changes before running the gate')
        untracked = git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
        for path in filter(None, untracked):
            require((Path(repo) / path).resolve().is_relative_to(self.run), f'commit or ignore untracked file before gate: {path}')
        return git(repo, 'rev-parse', 'HEAD')

    def valid_gate(self, state):
        head = self.clean_head(state)
        gate = state.get('gate_result') or {}
        require(gate.get('exit_code') == 0 and gate.get('head_sha') == head and gate.get('command') == state['gate'], 'run the gate successfully on the current HEAD first')
        return head

    def request(self, state, args):
        self.active(state)
        self.frozen(state)
        fields, _, source_hash = artifact(self.run, args.source)
        kind = {'spec': 'spec', 'plan': 'plan', 'pr-request': 'pr'}.get(fields.get('type'))
        require(kind is not None and fields.get('run_id') == state['run_id'], 'source type or run ID does not match')
        require(type(fields.get('round')) is int and fields['round'] > 0, 'source round must be a positive integer')
        pending = state['pending']
        if pending and pending['source'] == args.source and pending['source_sha256'] == source_hash:
            if kind == 'pr':
                require(pending['head_sha'] == self.valid_gate(state), 'pending review is for an old HEAD; rerun gate and request the next round')
            return state
        require(pending is None, 'a review is pending; finish it before requesting another')
        require(state['phase'] == ('executing' if kind == 'pr' else kind), f'cannot request {kind} during {state["phase"]}')
        round = state['rounds'][kind] + 1
        require(fields['round'] == round, f'next {kind} round must be {round}')
        if round > state['round_limits'][kind]:
            self.escalate(state, f'{kind} round budget exhausted')
            raise InvalidRun('round budget exhausted; resume with a human decision')
        head = None
        if kind == 'pr':
            head = self.valid_gate(state)
            require(fields.get('head_sha') == head, 'PR request head_sha must equal current checked HEAD')
            require(type(fields.get('pr_number')) is int and fields['pr_number'] > 0, 'PR request needs a positive pr_number')
            previous = state.get('pr_number')
            require(previous in (None, fields['pr_number']), 'PR number cannot change within a run')
            state['pr_number'] = fields['pr_number']
            expected = f'prr-{fields["pr_number"]}-v{round}.md'
        else:
            expected = f'{kind}-v{round}.md'
        require(args.source == expected, f'source filename must be {expected}')
        request_id = digest(f'{state["run_id"]}:{kind}:{round}:{source_hash}:{head}'.encode())
        state['pending'] = dict(source=args.source, source_sha256=source_hash, request_id=request_id, kind=kind, round=round, head_sha=head)
        state['rounds'][kind] = round
        state['review_errors'] = 0
        state['phase'] = kind
        return self.save(state)

    def invalid_delivery(self, state):
        if state['pending'] and state['phase'] not in ('completed', 'escalated'):
            state['review_errors'] += 1
            self.save(state, progress=False)
            if state['review_errors'] >= 2:
                self.escalate(state, 'two invalid review deliveries; correct the contract before resuming')

    def accept(self, state, args):
        try:
            fields, body, review_hash = artifact(self.run, args.review)
        except (InvalidRun, UnicodeError):
            self.invalid_delivery(state)
            raise
        for item in state['history']:
            if item['review'] == args.review and item['review_sha256'] == review_hash:
                return state
        self.active(state)
        self.frozen(state)
        pending = state['pending']
        require(pending is not None, 'no pending review request')
        try:
            expected = dict(run_id=state['run_id'], type='review', round=pending['round'],
                            source=pending['source'], source_sha256=pending['source_sha256'],
                            request_id=pending['request_id'], reviewer=state['reviewer'])
            require(all(fields.get(key) == value for key, value in expected.items()), 'review run/source/hash/round/request/reviewer does not match the pending request')
            require(fields.get('status') in ('approved', 'changes_requested'), 'review status must be approved or changes_requested')
            sections = re.findall(r'^#{1,6}\s+([1-5])[.)]\s+.+$', body, flags=re.M)
            require(sections == ['1', '2', '3', '4', '5'], 'review must contain exactly five numbered headings in order')
            _, _, current_hash = artifact(self.run, pending['source'])
            require(current_hash == pending['source_sha256'], 'source changed after review request')
            if pending['kind'] == 'pr':
                head = self.valid_gate(state)
                require(fields.get('head_sha') == pending['head_sha'] == head, 'review must approve the current checked HEAD')
                if state.get('protocol_version') == PROTOCOL_VERSION:
                    manual_checks(body)
        except InvalidRun:
            self.invalid_delivery(state)
            raise
        kind = pending['kind']
        state['history'].append(dict(**pending, review=args.review, review_sha256=review_hash, status=fields['status']))
        state['pending'] = None
        if fields['status'] == 'approved':
            state['approved'][kind] = pending
            state['phase'] = {'spec': 'plan', 'plan': 'executing', 'pr': 'finalizing'}[kind]
        else:
            state['phase'] = 'executing' if kind == 'pr' else kind
            if kind == 'pr':
                state['gate_result'] = None
            if state['rounds'][kind] >= state['round_limits'][kind]:
                self.save(state)
                return self.escalate(state, f'{kind} round budget exhausted')
        return self.save(state)

    def resume(self, state, args):
        require(state['phase'] != 'completed', 'completed runs cannot be resumed')
        restored = self.restore_completion(state)
        if restored:
            return restored
        running = state.get('gate_running')
        if running and (not running.get('owner_identity') or process_identity(running.get('owner_pid')) != running['owner_identity']):
            child = running.get('child_pid')
            if running.get('child_identity') and process_identity(child) == running['child_identity']:
                # The saved child owns its process group. Abort an orphaned gate
                # before another invocation can overlap with it.
                try:
                    if os.getpgid(child) == child:
                        os.killpg(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            state.pop('gate_running')
            state['gate_result'] = None
        if state['phase'] == 'escalated':
            require(args.reason and args.reason.strip(), 'resuming an escalation requires --reason with the human decision')
            state.setdefault('resumptions', []).append(dict(reason=args.reason, at=time.time()))
            state['phase'] = state.pop('resume_phase')
            state.pop('escalation_reason', None)
            for kind in state['rounds']:
                if state['rounds'][kind] >= state['round_limits'][kind]:
                    state['round_limits'][kind] += 3
            state['review_errors'] = 0
            state['budget_started_at'] = time.time()
        if args.reviewer:
            state['reviewer'] = args.reviewer
        return self.save(state)

    def gate(self, args):
        with self.lock():
            state = self.load()
            self.active(state)
            self.frozen(state)
            require(state['phase'] in ('executing', 'pr', 'finalizing'), 'gate requires an approved plan')
            require(not state.get('gate_running'), 'gate already running; inspect status before retrying')
            head = self.clean_head(state)
            # A changed commit starts another PR round, never inherits an approval.
            if state['phase'] in ('pr', 'finalizing'):
                previous = state['pending'] or state['approved'].get('pr')
                require(previous and previous['head_sha'] != head, 'current PR review must finish before rerunning the gate')
                state['pending'] = None
                state['approved'].pop('pr', None)
                state['phase'] = 'executing'
            state['gate_result'] = None
            now = time.time()
            timeout = min(args.timeout, state['run_timeout'] - (now - state['budget_started_at']))
            require(timeout > 0, 'run time budget exhausted')
            token = digest(f'{head}:{now}'.encode())
            owner_identity = process_identity(os.getpid())
            require(owner_identity, 'cannot identify the gate controller process')
            state['gate_running'] = dict(token=token, head_sha=head, deadline=now + timeout + 5, owner_pid=os.getpid(), owner_identity=owner_identity)
            self.save(state)
        log = self.run / f'gate-{token[:16]}.log'
        code = 125
        try:
            with log.open('w') as output:
                # Do not execute checks until the child group is recoverable in
                # state. A crash before the handshake closes stdin and exits it.
                process = subprocess.Popen(['bash', '-c', 'IFS= read -r start || exit 125; exec bash -o pipefail -c "$1"', 'duo-gate', state['gate']], cwd=state['worktree'], stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    with self.lock():
                        current = self.load()
                        current['gate_running']['child_pid'] = process.pid
                        current['gate_running']['child_identity'] = process_identity(process.pid)
                        require(current['gate_running']['child_identity'], 'cannot identify the gate child process')
                        self.save(current)
                    process.stdin.write(b'start\n')
                    process.stdin.close()
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    code = 124
                except BaseException:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                    raise
                finally:
                    process.stdin.close()
        finally:
            with self.lock():
                current = self.load()
                require((current.get('gate_running') or {}).get('token') == token, 'gate state changed while command was running')
                current.pop('gate_running', None)
                try:
                    unchanged = self.clean_head(current) == head
                    self.frozen(current)
                except InvalidRun:
                    unchanged = False
                current['gate_result'] = dict(head_sha=head, command=state['gate'], exit_code=code if unchanged else 125, log=log.name, finished_at=time.time())
                self.save(current)
        require(current['gate_result']['exit_code'] == 0, f'gate failed (exit {current["gate_result"]["exit_code"]}); see {log}')
        return current

    def github(self, state, endpoint, payload=None, pages=False):
        command = ['gh', 'api', '--hostname', 'github.com', endpoint]
        if pages:
            command += ['--paginate', '--slurp']
        if payload is not None:
            command += ['--method', 'POST', '--input', '-']
        try:
            result = subprocess.run(command, cwd=state['worktree'], text=True, capture_output=True,
                                    input=json.dumps(payload) if payload is not None else None, timeout=30)
        except FileNotFoundError as error:
            raise InvalidRun('GitHub publication requires gh on PATH and gh auth login') from error
        except subprocess.TimeoutExpired as error:
            raise InvalidRun('GitHub request timed out; retry publish-review to reconcile any accepted comment') from error
        require(result.returncode == 0, result.stderr.strip() or 'GitHub request failed; retry safely')
        return json.loads(result.stdout)

    def publication_evidence(self, state, repo):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), 'repository must be OWNER/NAME')
        self.frozen(state)
        head = self.valid_gate(state)
        approved = state['approved'].get('pr')
        require(approved and approved['head_sha'] == head, 'PR must approve the current checked HEAD')
        _, source_body, source_hash = artifact(self.run, approved['source'])
        require(source_hash == approved['source_sha256'], 'approved PR request changed')
        url = f'https://github.com/{repo}/pull/{state["pr_number"]}'
        require(re.search(re.escape(url) + r'(?=$|[\s)<>])', source_body), 'repository/PR URL must appear in the approved PR request')
        review = next(item for item in reversed(state['history']) if item['request_id'] == approved['request_id'] and item['status'] == 'approved')
        _, review_body, review_hash = artifact(self.run, review['review'])
        require(review_hash == review['review_sha256'], 'accepted PR review changed')
        manual_checks(review_body)
        marker = f'<!-- agent-duo-verdict:{state["instance_id"]}:{approved["request_id"]} -->'
        body = (f'{marker}\n## Agent Duo review: approved\n\n'
                f'Commit: `{head}`\nRun: `{state["run_id"]}`\n'
                f'Review SHA256: `{review_hash}`\n\n'
                f'Local gate passed on this commit (exit 0):\n\n```text\n{state["gate"]}\n```\n\n'
                'This publishes the agent review. It is not a GitHub approving review, a merge, or a claim that pending manual checks passed.\n\n'
                + review_body.strip() + '\n')
        require(len(body.encode('utf-8')) <= 65000, 'verdict exceeds GitHub comment limit; shorten and re-review it')
        return approved, review_hash, marker, body

    def remote_head(self, state, repo, head):
        pr = self.github(state, f'repos/{repo}/pulls/{state["pr_number"]}')
        require(pr.get('state') == 'open' and pr.get('head', {}).get('sha') == head, 'GitHub PR must be open at the approved HEAD')

    def publish_review(self, state, args):
        require(state['phase'] in ('finalizing', 'completed'), 'accept the PR before publishing its verdict')
        if state['phase'] != 'completed':
            self.active(state)
        approved, review_hash, marker, body = self.publication_evidence(state, args.repo)
        self.remote_head(state, args.repo, approved['head_sha'])
        pages = self.github(state, f'repos/{args.repo}/issues/{state["pr_number"]}/comments', pages=True)
        comments = [comment for page in pages for comment in page]
        matches = [comment for comment in comments if marker in comment.get('body', '')]
        require(len(matches) <= 1, 'duplicate verdict markers; reconcile the PR discussion before finalization')
        if matches:
            comment = matches[0]
            require(comment.get('body') == body, 'existing verdict was edited; do not overwrite it automatically')
        else:
            comment = self.github(state, f'repos/{args.repo}/issues/{state["pr_number"]}/comments', {'body': body})
            require(comment.get('body') == body, 'GitHub did not return the expected verdict')
        # A push while the request was in flight leaves historical evidence only.
        self.publication_evidence(state, args.repo)
        self.remote_head(state, args.repo, approved['head_sha'])
        publication = dict(repo=args.repo, pr_number=state['pr_number'], head_sha=approved['head_sha'],
                           request_id=approved['request_id'], review_sha256=review_hash,
                           comment_id=comment['id'], url=comment['html_url'], body_sha256=digest(body.encode()))
        if state.get('publication') == publication:
            return state
        state['publication'] = publication
        return self.save(state)

    def published(self, state):
        if state.get('protocol_version', 1) < PROTOCOL_VERSION:
            return  # Historical protocol-1 runs retain their original contract.
        publication = state.get('publication')
        require(publication, 'publish-review must succeed before finalization')
        approved, review_hash, _, body = self.publication_evidence(state, publication['repo'])
        require(publication['head_sha'] == approved['head_sha'] and publication['request_id'] == approved['request_id']
                and publication['review_sha256'] == review_hash and publication['body_sha256'] == digest(body.encode()), 'published verdict is obsolete')
        self.remote_head(state, publication['repo'], approved['head_sha'])
        comment = self.github(state, f'repos/{publication["repo"]}/issues/comments/{publication["comment_id"]}')
        require(comment.get('body') == body, 'published verdict is missing or changed')

    def memory(self, state, commit=None):
        if commit is None:
            result = git(state['worktree'], 'rev-parse', '--verify', MEMORY_REF, check=False)
            commit = result.stdout.strip() if result.returncode == 0 else ''
        if not commit:
            return dict(schema_version=1, runs=[], lessons=[])
        return json.loads(git(state['worktree'], 'show', f'{commit}:learning.json'))

    def restore_completion(self, state):
        if not state['approved'].get('pr'):
            return None
        result = git(state['worktree'], 'rev-parse', '--verify', MEMORY_REF, check=False)
        commit = result.stdout.strip() if result.returncode == 0 else ''
        entry = next((run for run in self.memory(state, commit)['runs']
                      if run.get('instance_id') == state['instance_id']), None)
        if entry:
            require(entry['head_sha'] == state['approved']['pr']['head_sha'], 'committed completion conflicts with approved evidence')
            # The ledger commit is the completion point. Later code changes do
            # not undo that historical result after an interrupted state write.
            state.update(phase='completed', completed_at=entry['completed_at'], memory_commit=commit)
            state.pop('escalation_reason', None)
            state.pop('resume_phase', None)
            return self.save(state)
        return None

    def finalize(self, state, args):
        if state['phase'] == 'completed':
            return state
        restored = self.restore_completion(state)
        if restored:
            return restored
        self.active(state)
        self.frozen(state)
        require(state['phase'] == 'finalizing', 'PR must be accepted before finalization')
        head = self.valid_gate(state)
        require(state['approved']['pr']['head_sha'] == head, 'approved commit no longer matches HEAD')
        self.published(state)
        proposals = json.loads(Path(args.lessons).read_text()) if args.lessons else []
        require(isinstance(proposals, list), 'lessons proposals must be a JSON list')
        for proposal in proposals:
            require(isinstance(proposal, dict) and all(isinstance(proposal.get(k), str) and proposal[k].strip() for k in ('pattern', 'scope')), 'each lesson needs pattern and scope')
            require(proposal.get('resolution') in ('accepted', 'verified'), 'lessons require an accepted or verified resolution')
            evidence = proposal.get('evidence')
            require(isinstance(evidence, list) and evidence, 'lessons require run artifact evidence')
            require(all(isinstance(name, str) for name in evidence), 'evidence entries must be artifact basenames')
            for name in evidence:
                fields, _, _ = artifact(self.run, name)
                require(fields.get('run_id') == state['run_id'], 'lesson evidence belongs to another run')
        repo = state['worktree']
        common = Path(git(repo, 'rev-parse', '--git-common-dir'))
        if not common.is_absolute():
            common = Path(repo) / common
        # Separate Git ref: durable across worktrees, never dirties approved code.
        with (common / 'agent-duo-learning.lock').open('a') as memory_lock:
            fcntl.flock(memory_lock, fcntl.LOCK_EX)
            self.active(state)
            self.frozen(state)
            require(self.valid_gate(state) == head, 'HEAD changed while waiting for finalization')
            prior = git(repo, 'rev-parse', '--verify', MEMORY_REF, check=False)
            previous_commit = prior.stdout.strip() if prior.returncode == 0 else ''
            memory = self.memory(state, previous_commit)
            existing = next((run for run in memory['runs'] if run['run_id'] == state['run_id']), None)
            if existing:
                require(existing.get('instance_id') == state['instance_id'] and existing['head_sha'] == head, 'run ID already finalized by another run instance')
                commit = previous_commit
                completed_at = existing['completed_at']
            else:
                sequence = len(memory['runs']) + 1
                completed_at = time.time()
                memory['runs'].append(dict(run_id=state['run_id'], instance_id=state['instance_id'], head_sha=head, sequence=sequence, completed_at=completed_at))
                confirmed = set()
                for proposal in proposals:
                    identity = digest((proposal['scope'].strip().casefold() + '\0' + proposal['pattern'].strip().casefold()).encode())
                    if identity in confirmed:
                        continue
                    confirmed.add(identity)
                    lesson = next((item for item in memory['lessons'] if item['id'] == identity), None)
                    if lesson is None:
                        lesson = dict(id=identity, pattern=proposal['pattern'], scope=proposal['scope'], confirmations=[], status='pending')
                        memory['lessons'].append(lesson)
                    evidence = [dict(source=name, sha256=artifact(self.run, name)[2]) for name in proposal['evidence']]
                    lesson['confirmations'].append(dict(run_id=state['run_id'], evidence=evidence, resolution=proposal['resolution']))
                    lesson['last_confirmed_sequence'] = sequence
                    lesson['status'] = 'active' if len(lesson['confirmations']) >= 2 else 'pending'
                for lesson in memory['lessons']:
                    if lesson['status'] == 'active' and sequence - lesson['last_confirmed_sequence'] >= 5:
                        lesson['status'] = 'dormant'
                files = {'learning.json': json.dumps(memory, indent=2) + '\n'}
                for filename, statuses in [('lessons.md', ('active', 'dormant')), ('lessons-pending.md', ('pending',))]:
                    files[filename] = '\n'.join(f'- [{item["status"]}] {item["scope"]}: {item["pattern"]}' for item in memory['lessons'] if item['status'] in statuses) + '\n'
                tree_lines = []
                for name, content in sorted(files.items()):
                    blob = git(repo, 'hash-object', '-w', '--stdin', input=content)
                    tree_lines.append(f'100644 blob {blob}\t{name}\n')
                tree = git(repo, 'mktree', input=''.join(tree_lines))
                parents = ['-p', previous_commit] if previous_commit else []
                env = dict(os.environ, GIT_AUTHOR_NAME='Agent Duo', GIT_AUTHOR_EMAIL='agent-duo@localhost', GIT_COMMITTER_NAME='Agent Duo', GIT_COMMITTER_EMAIL='agent-duo@localhost')
                commit = git(repo, 'commit-tree', tree, *parents, input=f'Finalize agent-duo run {state["run_id"]}\n', env=env)
                self.active(state)
                self.frozen(state)
                require(self.valid_gate(state) == head, 'HEAD changed during finalization')
                self.published(state)
                git(repo, 'update-ref', MEMORY_REF, commit, previous_commit or '0' * len(head))
            state.update(memory_commit=commit, completed_at=completed_at, phase='completed')
            return self.save(state)

    def execute(self, args):
        if args.command == 'gate':
            return self.gate(args)
        if args.command == 'wait':
            deadline = time.monotonic() + args.timeout
            while True:
                with self.lock():
                    state = self.deadlines(self.load())
                if state['revision'] != args.after or state['phase'] in ('completed', 'escalated'):
                    return dict(state, timed_out=False)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return dict(state, timed_out=True)
                time.sleep(min(0.2, remaining))
        with self.lock():
            if args.command == 'init':
                return self.init(args)
            state = self.deadlines(self.load())
            if args.command == 'status':
                return state
            if args.command == 'memory':
                return self.memory(state)
            if args.command == 'heartbeat':
                self.active(state)
                return self.save(state)
            return getattr(self, args.command.replace('-', '_'))(state, args)


def positive(value):
    parsed = float(value)
    if not 0 < parsed < float('inf'):
        raise argparse.ArgumentTypeError('must be a finite positive number')
    return parsed


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('protocol')
    for name in ('init', 'status', 'request', 'accept', 'gate', 'heartbeat', 'wait', 'resume', 'finalize', 'memory', 'publish-review'):
        command = commands.add_parser(name)
        command.add_argument('--run-dir', required=True)
        if name == 'init':
            for key in ('run-id', 'worktree', 'gate', 'reviewer'):
                command.add_argument('--' + key, required=True)
            command.add_argument('--idle-timeout', type=positive, default=1800)
            command.add_argument('--run-timeout', type=positive, default=14400)
        elif name == 'request':
            command.add_argument('--source', required=True)
        elif name == 'accept':
            command.add_argument('--review', required=True)
        elif name == 'gate':
            command.add_argument('--timeout', type=positive, default=900)
        elif name == 'wait':
            command.add_argument('--after', required=True, type=int)
            command.add_argument('--timeout', type=positive, default=30)
        elif name == 'resume':
            command.add_argument('--reason')
            command.add_argument('--reviewer')
        elif name == 'finalize':
            command.add_argument('--lessons')
        elif name == 'publish-review':
            command.add_argument('--repo', required=True)
    return root


def main():
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    args = parser().parse_args()
    if args.command == 'protocol':
        print(json.dumps(dict(protocol_version=PROTOCOL_VERSION)))
        return 0
    if args.command == 'wait' and args.timeout > 60:
        parser().error('wait timeout must be at most 60 seconds')
    try:
        result = Controller(args.run_dir).execute(args)
        print(json.dumps(result, indent=2))
        return 0
    except (InvalidRun, OSError, ValueError, UnicodeError) as error:
        print(f'duo-state: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('duo-state: interrupted; inspect status before resuming', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
