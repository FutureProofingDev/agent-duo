"""A fake GitHub CLI at the network boundary; Git and the controller stay real."""
import json
import os
from pathlib import Path

FAKE = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
a=sys.argv[1:]
root=Path(os.environ['DUO_TEST_GITHUB']); root.mkdir(exist_ok=True)
config=json.loads((root/'config.json').read_text()) if (root/'config.json').exists() else {}
with (root/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\n')
if config.get('fail'): sys.exit('simulated GitHub failure')
endpoint=next(v for v in a if v.startswith('repos/'))
comments_path=root/'comments.json'
comments=json.loads(comments_path.read_text()) if comments_path.exists() else []
if '/pulls/' in endpoint:
 head=config.get('head') or subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
 print(json.dumps({'head':{'sha':head},'state':'open','html_url':'https://github.com/example/project/pull/123'}))
elif '--method' in a and a[a.index('--method')+1]=='POST':
 payload=json.load(sys.stdin)
 item={'id':len(comments)+1,'html_url':'https://github.com/example/project/pull/123#issuecomment-'+str(len(comments)+1),'body':payload['body']}
 comments.append(item); comments_path.write_text(json.dumps(comments))
 if config.get('uncertain_post'): sys.exit('response lost after server accepted comment')
 print(json.dumps(item))
elif '/issues/comments/' in endpoint:
 print(json.dumps(next(c for c in comments if str(c['id'])==endpoint.rsplit('/',1)[1])))
else:
 print(json.dumps([comments] if '--slurp' in a else comments))
'''


def environment(directory):
    root = Path(directory) / 'github-fixture'
    root.mkdir(exist_ok=True)
    executable = root / 'gh'
    executable.write_text(FAKE)
    executable.chmod(0o755)
    return dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'], DUO_TEST_GITHUB=str(root))


def configure(env, **values):
    (Path(env['DUO_TEST_GITHUB']) / 'config.json').write_text(json.dumps(values))
