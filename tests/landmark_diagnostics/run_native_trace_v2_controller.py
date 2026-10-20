import subprocess,pathlib,json,datetime,os
R=pathlib.Path('/data/zy/vln/case1');os.chdir(R);O=R/'outputs/landmark-connectivity'
def note(status,**kw):(O/'native-stage-trace-xc-v2-controller.json').write_text(json.dumps({'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':os.getpid(),'start_ticks':pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],**kw},indent=2))
try:
 for name in ['build_native_stage_trace_v2.py','run_native_stage_trace_v2.py']:
  note('RUNNING',step=name)
  with (O/('native-stage-trace-xc-v2-'+name+'.log')).open('xb') as log:subprocess.run(['bash','scripts/with_runtime.sh','runtime/awarevln/bin/python','tests/landmark_diagnostics/'+name],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True)
 note('COMPLETE_NATIVE_DIAGNOSIS_NOT_ACCEPTANCE')
except Exception as e:note('FAILED',error=repr(e));raise
