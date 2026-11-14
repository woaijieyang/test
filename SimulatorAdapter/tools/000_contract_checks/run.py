"""Run the maintained CPU contract suite in the protected project runtime."""
import argparse,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
root=Path('/data/zy/vln/case2');out=Path(a.out).absolute()
if not out.is_relative_to(root/'outputs/graph_memory'):raise ValueError('Validation output must stay in owned graph output')
out.mkdir(parents=True,exist_ok=False)
targets=['src/SimulatorAdapter/tests']
with(out/'pytest.log').open('x')as log:
 result=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(out/'scratch'),*targets],cwd=root,stdout=log,stderr=subprocess.STDOUT)
print('exit_code',result.returncode,'log',out/'pytest.log');sys.exit(result.returncode)
