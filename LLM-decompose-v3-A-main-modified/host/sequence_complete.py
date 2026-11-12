from pathlib import Path
import subprocess,sys,time
root=Path('outputs/subtaskAdapter')
b=root/'r2r-v3-A-complete-B-20261109-r0'
r=root/'r2r-v3-A-complete-Remaining-20261109-r0'
while len(list((b/'records').glob('*/done.json')))!=612:
 time.sleep(30)
with (r/'dispatch.log').open('w',encoding='utf8') as log,(r/'dispatch.err').open('w',encoding='utf8') as err:
 subprocess.run([sys.executable,'-X','utf8','-u',str(r/'dispatch_original.py'),str(r)],stdout=log,stderr=err,check=True)
