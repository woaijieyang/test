"""Verify protected parent -> exec child inheritance on owned fixtures only."""
import os,sys,json,subprocess,hashlib
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION')
R=Path.cwd();output=R/'outputs/verification/runtime-child-inheritance-20261016';output.mkdir(exist_ok=False);target=R/'.rebuild/runtime-inheritance-fixture-20261016.txt';original=target.read_bytes();link=output/'escape.txt';link.symlink_to(target)
code=r"""
import os,json,sys,errno
from pathlib import Path
out=Path(sys.argv[1]);target=Path(sys.argv[2]);checks={}
for name,p in [('direct',target),('symlink',out/'escape.txt')]:
 try:
  with p.open('a') as f:f.write('UNEXPECTED_WRITE')
  checks[name]='UNEXPECTED_ALLOWED'
 except OSError as e:checks[name]={'errno':e.errno,'denied':e.errno in (errno.EACCES,errno.EPERM,errno.EROFS)}
(out/'child-owned-write.txt').write_text('allowed output')
checks['source_view_readonly']=bool(os.statvfs('data/.shared-ro').f_flag & os.ST_RDONLY);checks['protection']=json.loads(os.environ['CASE1_PROTECTION']);checks['no_new_privs']=next(x.split(':')[1].strip() for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('NoNewPrivs:'));print(json.dumps(checks))
"""
p=subprocess.run([sys.executable,'-B','-c',code,str(output),str(target)],capture_output=True,text=True,check=True);r=json.loads(p.stdout);assert target.read_bytes()==original and r['direct']['denied'] and r['symlink']['denied'] and r['no_new_privs']=='1';assert (output/'child-owned-write.txt').read_text()=='allowed output';assert r['protection']['landlock_abi']>0
if r['protection']['readonly_mount']:assert r['source_view_readonly']
report={'status':'PASS_PROTECTED_CHILD_INHERITANCE','checks':r,'fixture_sha256':hashlib.sha256(original).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'limits':'All denied write probes target owned .rebuild fixture; no global asset writes attempted. Direct subprocess exec inherits protections; do not re-enter mount/link initializer inside its private mounted view.'};(output/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
