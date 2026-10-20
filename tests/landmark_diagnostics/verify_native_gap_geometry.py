"""Independent source identity/coverage and saved point-contact witness audit, not all negatives."""
import os,sys,json,struct,math,time,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import psutil
O=R/"outputs/landmark-connectivity/native-gap-geometry-v1";assert not (O/"audit-process.json").exists();atomic_json(O/"audit-process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
try:
 while not (O/"validation.json").exists():
  p=json.loads((O/"process.json").read_text());stat=Path("/proc")/str(p["pid"])/"stat";s=stat.read_text().rsplit(")",1)[1].split() if stat.exists() else [];assert s and s[19]==str(p["start_ticks"]) and s[0] not in "ZX","Controller ended without validation";time.sleep(30)
 u=psutil.cpu_percent(interval=1,percpu=True);used=set(json.loads((O/"execution.json").read_text())["cpus"]);available=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in used];os.sched_setaffinity(0,[min(available,key=lambda i:u[i])])
 m=json.loads((O/"input.json").read_text());v=json.loads((O/"validation.json").read_text());assert v["input_sha256"]==digest(O/"input.json");reports={r["scene"]:r for r in v["scenes"]};assert len(reports)==len(m["scenes"])==39
 checked=0;pairs=points=edges=0;missing=0;max_residual=0.;rows=[]
 def dot(a,b):return sum(x*y for x,y in zip(a,b))
 def sub(a,b):return [x-y for x,y in zip(a,b)]
 for row in m["scenes"]:
  scene=row["scene"];f=O/"scenes"/(scene+".json");assert digest(f)==reports[scene]["report_sha256"];d=json.loads(f.read_text());assert digest(row["input_path"])==row["input_sha256"]==d["input_sha256"];old=json.loads(Path(row["input_path"]).read_text());ng=row["native_geometry"];assert digest(ng["native_geometry_path"])==ng["native_geometry_sha256"]==d["native_geometry_sha256"]
  raw=Path(ng["native_geometry_path"]).read_bytes();nv,nt=struct.unpack_from("<ii",raw);assert len(raw)==8+12*nv+12*nt
  assert len(d["pairs"])==len(old["pairs"])==row["pairs"]
  for now,prior in zip(d["pairs"],old["pairs"]):
   assert now["component_pair"]==prior["component_pair"] and now["nodes"]==prior["nodes"] and now["vertex_gap"]==prior["vertex_gap"]
   assert len(now["samples"])==len(prior["samples"]) and len(now["edges"])==len(now["samples"])-1
   heights=[]
   for sample,expected in zip(now["samples"],prior["samples"]):
    assert sample["position"]==expected["position"] and sample["fraction"]==expected["fraction"]
    assert sample["count"]==len(sample["contacts"]);foot=sample["position"];assert all(math.isfinite(x) for x in foot)
    for h in sample["contacts"]:
     assert 0<=h["triangle"]<nt and math.isfinite(h["radial_distance"]) and h["radial_distance"]<.1-1e-6
     w=h.get("height_range")
     if w is None:missing+=1;continue
     ids=struct.unpack_from("<iii",raw,8+12*nv+12*h["triangle"]);a,b,c=[struct.unpack_from("<fff",raw,8+12*i) for i in ids];u=sub(b,a);z=sub(c,a);den=dot(u,u)*dot(z,z)-dot(u,z)**2;assert den>0
     for label in ["minimum","maximum"]:
      x=w[label+"_point"];q=sub(x,a);alpha=(dot(z,z)*dot(q,u)-dot(u,z)*dot(q,z))/den;beta=(dot(u,u)*dot(q,z)-dot(u,z)*dot(q,u))/den;residual=math.sqrt(sum((a[k]+alpha*u[k]+beta*z[k]-x[k])**2 for k in range(3)));max_residual=max(max_residual,residual)
      assert min(alpha,beta,1-alpha-beta)>=-1e-7 and residual<=1e-7
      assert math.hypot(x[0]-foot[0],x[2]-foot[2])<=.1-1e-6+1e-8 and 1e-5-1e-8<=x[1]-foot[1]<=1.5+1e-8
      assert abs((x[1]-foot[1])-w[label+"_height"])<=1e-10;checked+=1
     heights.append(w["maximum_height"])
   for edge,a,b in zip(now["edges"],now["samples"],now["samples"][1:]):
    assert edge["start"]==a["position"] and edge["end"]==b["position"] and edge["count"]==len(edge["contacts"])
    assert len({h["triangle"] for h in edge["contacts"]})==edge["count"]
    for h in edge["contacts"]:assert 0<=h["triangle"]<nt and math.isfinite(h["radial_distance"]) and h["radial_distance"]<.1-1e-6
   assert now["maximum_actual_point_contact_height"]==(max(heights) if heights else None)
   assert now["point_contact_over_0point3m"]==any(h>.3 for h in heights)
   assert now["contact_samples"]==sum(s["count"]>0 for s in now["samples"]) and now["contact_edges"]==sum(e["count"]>0 for e in now["edges"])
   pairs+=1;points+=len(now["samples"]);edges+=len(now["edges"])
  rows.append({"scene":scene,"pairs":len(d["pairs"]),"point_contact_pairs":sum(p["contact_samples"]>0 for p in d["pairs"]),"swept_contact_pairs":sum(p["contact_edges"]>0 for p in d["pairs"]),"high_contact_pairs":sum(p["point_contact_over_0point3m"] for p in d["pairs"]),"legacy_high_pairs":sum(p["legacy_samples_with_high_contact"]>0 for p in d["pairs"])})
 assert pairs==86 and points==1645 and edges==1559 and missing==0
 atomic_json(O/"independent-coverage.json",{"status":"PASS_COVERAGE_IDENTITY_AND_SAVED_POINT_WITNESSES","scenes":rows,"scene_count":39,"pairs":pairs,"point_occurrences":points,"edge_occurrences":edges,"saved_point_witness_extrema_checked":checked,"missing_height_witnesses":missing,"maximum_triangle_residual_m":max_residual,"input_sha256":digest(O/"input.json"),"validation_sha256":digest(O/"validation.json"),"script_sha256":digest(__file__),"limits":"Scalar native triangle/barycentric/body verification of saved positive point extrema plus full input/sequence/count identities. Not independent exhaustive negative geometry or swept-edge collision computation, no actual motion or physical-unreachability proof.","time":datetime.datetime.now().isoformat()});atomic_json(O/"audit-state.json",{"status":"COMPLETE"})
except Exception as e:atomic_json(O/"audit-state.json",{"status":"FAILED","error":repr(e)});raise
