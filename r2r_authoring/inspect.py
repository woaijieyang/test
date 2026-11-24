"""Read-only inspection of immutable teaching baselines; no runtime inference."""
from pathlib import Path
import sys, json, subprocess
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PARENT = '081db4b9ea0712ff720c137fe96c240c26f7b15c'
EVALUATED = '9dd24a655a845d59698e835c0326fbf73db5fbb8'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)

def inspect():
    changed = git('diff', '--name-status', EVALUATED, PARENT).splitlines()
    print('DIRECT_DIFFERENCES', json.dumps(changed))
    names = git('ls-tree', '-r', '--name-only', EVALUATED).splitlines()
    for name in names:
        if '/templates/R2R/' not in name or not name.endswith('.json'):
            continue
        row = json.loads(git('show', EVALUATED + ':' + name))
        role = row['role']
        src = (row.get('input') or row['review_input'])['original_instruction']
        candidate = row.get('output') or row['review_input']['candidate']
        item = dict(path=name, id=row['template_id'], source=src, stages=candidate['subtasks'])
        if role == 'reviewer':
            a=row['expected_review']
            item.update(verdict=a['verdict'], coverage=[(c['requirement_id'],c['source_quote'],c['status']) for c in a['source_coverage']], findings=a['findings'])
        print('CARD', json.dumps(item, ensure_ascii=False))
    from host.compile import runtime_review_output, core_library
    from host.template_selector import library
    from host import protocol
    failures=[]
    for role in ('generator','reviewer'):
        for row in core_library(role,'r2r-en') + library(role,'r2r-en'):
            try:
                if role=='generator': protocol.generator(row['input']['original_instruction'],row['output'])
                else: protocol.reviewer(row['review_input']['original_instruction'],row['review_input']['candidate'],runtime_review_output(row))
            except Exception as e: failures.append([row['template_id'],str(e)])
    print('PARENT_PROTOCOL_FAILURES',json.dumps(failures))
if __name__=='__main__': inspect()
