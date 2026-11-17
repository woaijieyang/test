"""Resume private linking after discovering three ordered nav archive occurrences."""
import os,sys,json,shlex,subprocess,hashlib,datetime
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import digest,atomic_json
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
B=R/'upstream/habitat-sim/build';old=R/'outputs/connectivity/pathfinder-height-boundary-binding-v1'
previous=json.loads((old/'state.json').read_text());assert previous['status']=='FAILED' and previous['changed_archive_members']==['PathFinder.cpp.o']
assert all(digest(p)==sha for p,sha in previous['originals_before'].items())
C1=R/'.cache/pathfinder-height-boundary-binding-v1';C=R/'.cache/pathfinder-height-boundary-binding-v2';O=R/'outputs/connectivity/pathfinder-height-boundary-binding-v2'
C.mkdir(exist_ok=False);O.mkdir(exist_ok=False)
record={'status':'LINKING','prior_failed_state_sha256':digest(old/'state.json'),'script_sha256':digest(__file__)}
try:
    target='lib.linux-x86_64-cpython-310/habitat_sim/_ext/habitat_sim_bindings.cpython-310-x86_64-linux-gnu.so'
    source=B/target;installed=R/'runtime/awarevln/lib/python3.10/site-packages/habitat_sim'
    control=C1/'control/habitat_sim/_ext'/source.name
    assert digest(control)==digest(source)==digest(installed/'_ext'/source.name)
    record['control_binding_sha256']=digest(control)
    text=(B/'build.ninja').read_text();i=text.index('build '+target+':');block=text[i:text.find('\n\n',i)].splitlines()
    variables=dict(x.strip().split(' = ',1) for x in block[1:] if ' = ' in x)
    absolute=lambda args:[str((B/x).resolve()) if not x.startswith('-') and not x.startswith('/') and (B/x).exists() else x for x in args]
    objects=absolute(block[0].split(': ',1)[1].split(' ',1)[1].split(' | ',1)[0].split())
    libs=absolute(shlex.split(variables['LINK_LIBRARIES']))
    archive=B/'esp/nav/libnav.a';private=C1/'libnav.a'
    members=subprocess.check_output(['/usr/bin/ar','t',str(archive)],text=True).splitlines()
    assert members==subprocess.check_output(['/usr/bin/ar','t',str(private)],text=True).splitlines()
    changed=[name for name in members if hashlib.sha256(subprocess.check_output(['/usr/bin/ar','p',str(archive),name])).digest()!=hashlib.sha256(subprocess.check_output(['/usr/bin/ar','p',str(private),name])).digest()]
    assert changed==['PathFinder.cpp.o']
    occurrences=[i for i,v in enumerate(libs) if v==str(archive)];assert occurrences==[6,14,23]
    patched_libs=[str(private) if v==str(archive) else v for v in libs]
    assert len(patched_libs)==len(libs) and [i for i,(a,b) in enumerate(zip(libs,patched_libs)) if a!=b]==occurrences
    package=C/'patched/habitat_sim';package.mkdir(parents=True);(package/'_ext').mkdir()
    for p in installed.iterdir():
        if p.name not in ['_ext','__pycache__']:(package/p.name).symlink_to(p,target_is_directory=p.is_dir())
    dest=package/'_ext'/source.name
    command=['/usr/bin/c++','-fPIC',*shlex.split(variables['LANGUAGE_COMPILE_FLAGS']),'-shared','-o',str(dest),*objects,*patched_libs]
    record.update(command=command,replaced_archive_occurrences=occurrences,changed_archive_members=changed,private_archive_sha256=digest(private),patched_source_sha256=digest(C1/'PathFinder.cpp'),originals_before=previous['originals_before'])
    atomic_json(O/'state.json',record)
    with (O/'link.log').open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    env={**os.environ,'PYTHONPATH':str(package.parent),'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''}
    probe=json.loads(subprocess.check_output([sys.executable,'-c','import habitat_sim,json;import habitat_sim._ext.habitat_sim_bindings as b;print(json.dumps({"binding":b.__file__}))'],env=env,text=True))
    assert Path(probe['binding']).resolve()==dest
    assert all(digest(p)==h for p,h in previous['originals_before'].items())
    record.update(status='PASS_ISOLATED_BINARY_CONTROL_AND_IMPORT',patched_binding_sha256=digest(dest),patched_import=probe,originals_unchanged=True,time=datetime.datetime.now().astimezone().isoformat(),limits='Native movement/source acceptance still pending. Original source/build/install unchanged; link order and all three nav occurrences preserved.')
    atomic_json(O/'validation.json',record);atomic_json(O/'state.json',record)
except Exception as error:
    record.update(status='FAILED',error=repr(error));atomic_json(O/'state.json',record);raise

