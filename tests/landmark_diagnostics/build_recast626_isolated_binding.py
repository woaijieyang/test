"""Isolated relink of cached Habitat binding; original build and install remain read-only."""
import os,sys,json,shlex,subprocess,shutil,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
import psutil
usage=psutil.cpu_percent(interval=1,percpu=True);cpu=min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i]);os.sched_setaffinity(0,[cpu])
B=ROOT/'upstream/habitat-sim/build';O=ROOT/'outputs/landmark-connectivity/recast626-isolated-binding-v1';C=ROOT/'.cache/recast626-isolated-binding-v1';O.mkdir(exist_ok=False);C.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':cpu})
record={'status':'BUILDING','script_sha256':digest(__file__),'commands':[]}
def save():atomic_json(O/'state.json',record)
def run(args):
 record['commands'].append(args);save()
 with (O/'build.log').open('ab') as f:subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
def absolute_args(args):
 return [str((B/x).resolve()) if not x.startswith('-') and not x.startswith('/') and (B/x).exists() else x for x in args]
try:
 target='lib.linux-x86_64-cpython-310/habitat_sim/_ext/habitat_sim_bindings.cpython-310-x86_64-linux-gnu.so';installed=ROOT/'runtime/awarevln/lib/python3.10/site-packages/habitat_sim';original=B/target;archive=B/'deps/recastnavigation/Recast/libRecast.a';source=ROOT/'upstream/habitat-sim/src/deps/recastnavigation/Recast/Source/RecastFilter.cpp';binding=installed/'_ext'/original.name
 originals=[original,archive,source,binding,B/'build.ninja',B/'CMakeFiles/rules.ninja',B/'compile_commands.json'];before={str(p):digest(p) for p in originals};record['originals_before']=before;assert before[str(original)]==before[str(binding)]
 ninja=(B/'build.ninja').read_text();i=ninja.index('build '+target+':');block=ninja[i:ninja.find('\n\n',i)];lines=block.splitlines();objects=lines[0].split(': ',1)[1].split(' ',1)[1].split(' | ',1)[0].split();variables=dict(x.strip().split(' = ',1) for x in lines[1:] if ' = ' in x);flags=shlex.split(variables['LANGUAGE_COMPILE_FLAGS']);libs=absolute_args(shlex.split(variables['LINK_LIBRARIES']));objects=absolute_args(objects)
 assert all(Path(x).is_file() for x in objects)
 for label in ['control','patched']:
  pkg=C/label/'habitat_sim';pkg.mkdir(parents=True);(pkg/'_ext').mkdir()
  for p in installed.iterdir():
   if p.name not in ['_ext','__pycache__']: (pkg/p.name).symlink_to(p,target_is_directory=p.is_dir())
  dest=pkg/'_ext'/original.name;linklibs=list(libs)
  if label=='patched':
   patched=C/'RecastFilter.cpp';text=source.read_text();needle='if ((top - bot) <= walkableHeight)';assert text.count(needle)==1;patched.write_text(text.replace(needle,'if ((top - bot) < walkableHeight)'))
   item=next(x for x in json.loads((B/'compile_commands.json').read_text()) if x['file']==str(source));args=shlex.split(item['command']);obj=C/'RecastFilter.cpp.o';args[args.index('-o')+1]=str(obj);args[args.index('-c')+1]=str(patched);run(args)
   private=C/'libRecast.a';shutil.copy2(archive,private);run(['/usr/bin/ar','r',str(private),str(obj)]);run(['/usr/bin/ranlib',str(private)])
   original_members=subprocess.check_output(['/usr/bin/ar','t',str(archive)],text=True).splitlines();assert original_members==subprocess.check_output(['/usr/bin/ar','t',str(private)],text=True).splitlines();assert original_members.count('RecastFilter.cpp.o')==1
   import hashlib
   changed=[]
   for name in original_members:
    a=subprocess.check_output(['/usr/bin/ar','p',str(archive),name]);b=subprocess.check_output(['/usr/bin/ar','p',str(private),name])
    if hashlib.sha256(a).digest()!=hashlib.sha256(b).digest():changed.append(name)
   assert changed==['RecastFilter.cpp.o'];record['changed_archive_members']=changed;linklibs=[str(private) if x==str(archive) else x for x in libs];assert linklibs.count(str(private))==1
  run(['/usr/bin/c++','-fPIC',*flags,'-shared','-o',str(dest),*objects,*linklibs])
  record[label+'_binding_sha256']=digest(dest)
  if label=='control':assert digest(dest)==digest(original),'unpatched binding byte control mismatch'
  env={**os.environ,'PYTHONPATH':str(pkg.parent),'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''};probe=json.loads(subprocess.check_output([str(ROOT/'runtime/awarevln/bin/python'),'-c','import habitat_sim,json; import habitat_sim._ext.habitat_sim_bindings as b; print(json.dumps({"package":habitat_sim.__file__,"binding":b.__file__}))'],cwd=ROOT,env=env,text=True));assert Path(probe['binding']).resolve()==dest;record[label+'_import']=probe;save()
 assert before=={str(p):digest(p) for p in originals};record.update(status='PASS_ISOLATED_BINARY_CONTROL_AND_IMPORT',originals_unchanged=True,completed=datetime.datetime.now(datetime.timezone.utc).isoformat(),limits='Binding control only. No patched scene mesh or motion acceptance yet. Existing runtime and original build were not modified.');atomic_json(O/'validation.json',record);save()
except Exception as e:
 record.update(status='FAILED',error=repr(e));save();raise
