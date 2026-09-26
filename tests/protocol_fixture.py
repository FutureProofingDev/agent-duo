"""Small valid protocol artifacts shared by behavioral tests."""
import json

SPEC = '''## Observable outcome
AC1: code.txt retains its documented behavior.
## Constraints
Preserve compatibility; no merge or deployment.
## Pending assumptions
None.
## Acceptance evidence
AC1: run the configured gate. Manual VoiceOver is optional and reported separately.
'''


def records(heading, values):
    return '\n## ' + heading + '\n```json\n' + json.dumps(values) + '\n```\n'


def defect():
    return dict(id='F1', category='defect', claim='AC1 fails for empty input',
                criterion='AC1', evidence='code.txt:1; empty-input reproduction fails',
                check='Run the empty-input regression; expect success',
                correction='Handle empty input', blocking=True)
