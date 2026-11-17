"""Reproduce four historical camera-domain queries, without adopting a mapping.

The three small projection helpers are preserved from Case1's historical
diagnostics; frozen AST fingerprints verify reuse without importing that tree.
Rational distance certificates cross-check the float query construction only.
Camera-domain height/radius are not robot body parameters or a motion protocol.
"""
import ast
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
import os
import sys
from pathlib import Path
import time
import numpy as np

from oracle.common.artifacts import digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity,timestamp
from oracle.verification.contact_certificate import linear_sweep_witness,verify_witness


def segment_closest(p,a,b):
 e=b-a;den=float(e@e);t=min(1,max(0,float((p-a)@e)/den)) if den else 0.;return a+t*e


def triangle_closest(p,t):
 a,b,c=t;ab=b-a;ac=c-a
 if float(np.linalg.norm(np.cross(ab,ac)))<1e-14:return min([segment_closest(p,a,b),segment_closest(p,b,c),segment_closest(p,c,a)],key=lambda q:float((q-p)@(q-p)))
 ap=p-a;d1=float(ab@ap);d2=float(ac@ap)
 if d1<=0 and d2<=0:return a.copy()
 bp=p-b;d3=float(ab@bp);d4=float(ac@bp)
 if d3>=0 and d4<=d3:return b.copy()
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:return a+(d1/(d1-d3))*ab
 cp=p-c;d5=float(ab@cp);d6=float(ac@cp)
 if d6>=0 and d5<=d6:return c.copy()
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:return a+(d2/(d2-d6))*ac
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:return b+((d4-d3)/((d4-d3)+(d5-d6)))*(c-b)
 den=1/(va+vb+vc);return a+ab*(vb*den)+ac*(vc*den)


def clip_y(poly,bound,above):
 result=[]
 if not poly:return result
 for a,b in zip(poly,poly[1:]+poly[:1]):
  aa=a[1]>=bound if above else a[1]<=bound;bb=b[1]>=bound if above else b[1]<=bound
  if aa:result.append(a)
  if aa!=bb:result.append(a+(b-a)*((bound-a[1])/(b[1]-a[1])))
 return result


def inspect_query(query,camera,pf):
    q=np.asarray(query,float);cam=np.asarray(camera,float)
    record={'query_position':[float(x) if math.isfinite(float(x)) else str(x) for x in q],
            'snap_calls':0,'is_navigable_calls':0}
    if not np.isfinite(q).all():return {**record,'primary_reason':'query_nonfinite','failed_checks':['query_nonfinite']}
    snap=np.asarray(pf.snap_point(q),float);record['snap_calls']=1
    record['snapped_position']=[float(x) if math.isfinite(float(x)) else str(x) for x in snap]
    if not np.isfinite(snap).all():return {**record,'primary_reason':'snap_nonfinite','failed_checks':['snap_nonfinite']}
    navigable=bool(pf.is_navigable(snap));record['is_navigable_calls']=1
    residual=float(np.linalg.norm(q-snap));horizontal=math.hypot(snap[0]-cam[0],snap[2]-cam[2]);drop=float(cam[1]-snap[1])
    reasons=[]
    if not navigable:reasons.append('snapped_not_navigable')
    if residual>1e-5:reasons.append('snap_residual')
    if horizontal>=.5:reasons.append('camera_horizontal')
    if not 0<=drop<=2:reasons.append('camera_drop')
    record.update(snapped_is_navigable=navigable,snap_residual_m=residual,horizontal_m=horizontal,drop_m=drop,
                  primary_reason=reasons[0] if reasons else 'accepted',failed_checks=reasons)
    return record


def rational_camera_distance(triangle,camera):
    # This is the original camera search slab, NOT a changed robot body.
    foot=[float(camera[0]),float(camera[1])-2.,float(camera[2])]
    assert F(foot[1])+2==F(float(camera[1]))
    witness=linear_sweep_witness(triangle,foot,foot,height=2.,foot_epsilon=0.)
    if witness is None:return dict(no_height_slice=True,lower_bound_verified=True)
    inside=verify_witness(triangle,foot,foot,witness,radius=.5,height=2.,foot_epsilon=0.)
    tri=[[F(float(x)) for x in p] for p in triangle];low,high=F(foot[1]),F(float(camera[1]))
    clipped=[p for p in tri if low<=p[1]<=high]
    for a,b in itertools.combinations(tri,2):
        for plane in (low,high):
            if (a[1]-plane)*(b[1]-plane)<0:
                t=(plane-a[1])/(b[1]-a[1]);clipped.append([a[k]+t*(b[k]-a[k]) for k in range(3)])
    weights=[F(*x) for x in witness['exact_barycentric']]
    point=[sum(weights[i]*tri[i][k] for i in range(3)) for k in range(3)]
    q=[point[k]-F(float(camera[k])) for k in [0,2]];d2=q[0]**2+q[1]**2
    assert d2==F(*witness['exact_distance_squared'])
    # Projection theorem supplies a checkable lower bound for every point in
    # this height-clipped triangle, not merely one positive contact witness.
    lower=all(sum(q[i]*(p[k]-F(float(camera[k]))) for i,k in enumerate([0,2]))>=d2 for p in clipped)
    if not lower:raise ValueError('Independent supporting-plane lower bound failed')
    return dict(distance_m=math.sqrt(float(d2)),exact_distance_squared=[d2.numerator,d2.denominator],
                inside_camera_horizontal=inside,lower_bound_verified=True,witness=witness,
                scope='This current native triangle in the closed camera-height slab; not whole-scene physical reachability')


def verify_historical_helpers(cfg):
    if list(sys.version_info[:2])!=cfg['historical_ast_python']:
        raise ValueError('Historical AST fingerprints require the declared frozen Python version')
    functions={x.name:x for x in ast.parse(Path(__file__).read_text()).body if isinstance(x,ast.FunctionDef)}
    for name,value in cfg['historical_helper_ast_sha256'].items():
        if hashlib.sha256(ast.dump(functions[name],include_attributes=False).encode()).hexdigest()!=value:
            raise ValueError('Historical projection helper semantics differ')


def run(case_root,output,cpu):
    import resource
    import signal
    from collections import Counter
    from oracle.research.full_worker import process_identity
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected Case1 runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/camera_surface_rejections_v1.json').read_text())
    verify_historical_helpers(cfg)
    previous=root/cfg['paired_study'];pv=json.loads((previous/'validation.json').read_text());pm=json.loads((previous/'manifest.json').read_text())
    if digest(previous/'manifest.json')!=cfg['paired_manifest_sha256'] or json.loads((previous/'source-freeze.json').read_text())['status']!='CLOSED':
        raise ValueError('Prior paired study is not the closed frozen run')
    spent=pv['charged_cpu_upper_bound_seconds']+pm['retained_failed_charge_seconds']
    if spent+cfg['camera_cpu_seconds_cap']+cfg['cpu_checks_reserved_seconds']>cfg['stage_cpu_seconds_cap']:
        raise ValueError('Same finite-stage budget exhausted')
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside authorized64')
    os.sched_setaffinity(0,{cpu});os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
    failure=json.loads((root/cfg['retained_prelaunch_failure']).read_text())
    if failure['native_queries']!=0 or failure['conservative_cpu_charge_seconds']!=cfg['retained_prelaunch_cpu_charge_seconds']:
        raise ValueError('Retained prelaunch failure charge differs')
    phase_cap=cfg['camera_cpu_seconds_cap']-cfg['retained_prelaunch_cpu_charge_seconds']-5
    if phase_cap<=0:raise ValueError('Camera allocation exhausted')
    resource.setrlimit(resource.RLIMIT_CPU,(phase_cap,phase_cap+5))
    def expired(*_):raise TimeoutError('Fixed camera diagnostic wall allocation')
    signal.signal(signal.SIGALRM,expired);signal.alarm(phase_cap)
    old_path=root/cfg['old_receipt'];old=json.loads(old_path.read_text())
    if digest(old_path)!=cfg['old_receipt_sha256']:raise ValueError('Historical camera receipt drift')
    profile_path=root/cfg['profile'];profile=json.loads(profile_path.read_text())
    if digest(profile_path)!=old['profile_sha256'] or profile['agent']!={'height':1.5,'radius':.1}:
        raise ValueError('Original profile/body changed')
    lookup={(x['scene'],x['node']):x for x in old['rows']}
    selected=[lookup[(x['scene'],x['node'])] for x in cfg['contexts']]
    if len(selected)!=4 or sum(x['point_queries'] for x in selected)!=33:raise ValueError('Fixed query scope differs')
    out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity())
    write_json(out/'source-freeze.json',dict(status='OPEN'))
    start=time.perf_counter();all_rows=[];triangles=[];scene_rows=[]
    try:
        import habitat_sim
        for original in selected:
            scene=original['scene'];cam=np.asarray(original['raw_camera_position'],float)
            asset=profile['assets'][f'mp3d/{scene}/{scene}.glb']
            if digest(asset['navmesh_path'])!=original['mesh_sha256']:raise ValueError('Native mesh drift')
            pf=habitat_sim.PathFinder()
            if not pf.load_nav_mesh(asset['navmesh_path']):raise RuntimeError('Original mesh load failed')
            vertices=np.asarray(pf.build_navmesh_vertices(),float);indices=np.asarray(pf.build_navmesh_vertex_indices(),int).reshape(-1,3)
            tri=vertices[indices];lo=tri.min(axis=1);hi=tri.max(axis=1)
            delta=np.maximum(np.maximum(lo[:,[0,2]]-cam[[0,2]],cam[[0,2]]-hi[:,[0,2]]),0)
            ids=np.flatnonzero((np.sum(delta**2,axis=1)<.25)&(lo[:,1]<=cam[1])&(hi[:,1]>=cam[1]-2))
            if len(ids)!=original['triangles_considered']:raise ValueError('Historical broadphase no longer matches')
            rows=[];degenerate=0
            def consider(q,index,method):
                rows.append(dict(inspect_query(q,cam,pf),scene=scene,node=original['node'],
                                 triangle=int(index),query_kind=method,query_index=len(rows)))
            for index in ids:
                triangle=tri[index]
                triangles.append(dict(scene=scene,node=original['node'],triangle_index=int(index),vertices=triangle.tolist(),
                                      camera=cam.tolist(),independent_geometry=rational_camera_distance(triangle,cam)))
                poly=clip_y(clip_y(list(triangle),cam[1]-2,True),cam[1],False)
                if len(poly)<3:continue
                for j in range(1,len(poly)-1):
                    face=np.array([poly[0],poly[j],poly[j+1]]);flat=face.copy();flat[:,1]=0
                    qflat=triangle_closest(np.array([cam[0],0,cam[2]]),flat)
                    E=np.column_stack((flat[1]-flat[0],flat[2]-flat[0]));uv,res,rank,sv=np.linalg.lstsq(E,qflat-flat[0],rcond=None)
                    if rank<2:degenerate+=1;continue
                    q=face[0]+uv[0]*(face[1]-face[0])+uv[1]*(face[2]-face[0])
                    consider(q,index,'closest_horizontal_point_on_height_clipped_native_triangle')
                    consider(q+1e-4*(face.mean(axis=0)-q),index,'interior_witness')
                for q in poly:consider(q,index,'clipped_vertex')
            if len(rows)!=original['point_queries'] or degenerate!=original['degenerate_projected_triangles_not_classified']:
                raise ValueError('Original finite query sequence count changed')
            all_rows.extend(rows);scene_rows.append(dict(scene=scene,node=original['node'],queries=len(rows),
                reasons=dict(Counter(x['primary_reason'] for x in rows)),old_new_seed_count=0,
                accepted_queries=sum(x['primary_reason']=='accepted' for x in rows),mesh_sha256=original['mesh_sha256']))
            del pf
        write_json(out/'queries33.json',all_rows);write_json(out/'triangles6.json',triangles)
        result=dict(status='COMPLETE_FIXED_CAMERA_REJECTION_DIAGNOSTIC_NOT_MAPPING_REPAIR',time=timestamp(),
                    contexts=scene_rows,queries=len(all_rows),triangles=len(triangles),
                    primary_reasons=dict(Counter(x['primary_reason'] for x in all_rows)),
                    native_snap_calls=sum(x['snap_calls'] for x in all_rows),native_navigability_calls=sum(x['is_navigable_calls'] for x in all_rows),
                    native_actions=0,adopted_mappings=0,process_cpu_seconds=time.process_time(),wall_seconds=time.perf_counter()-start,
                    prior_stage_charged_cpu_seconds=spent,camera_reserved_cpu_seconds=cfg['camera_cpu_seconds_cap'],
                    retained_prelaunch_cpu_charge_seconds=cfg['retained_prelaunch_cpu_charge_seconds'],
                    native_environment=runtime_identity(),source_hashes={str(old_path):digest(old_path),str(profile_path):digest(profile_path)},
                    queries_sha256=digest(out/'queries33.json'),triangles_sha256=digest(out/'triangles6.json'),
                    limits='Only fixed original33query positions and six current-navmesh triangles. Body/source-support/full-route/actual-motion gates not run. Rational slab certificate is a diagnostic cross-check, not a new robot body or whole-scene impossibility theorem.')
        write_json(out/'validation.json',result);return result
    except BaseException as error:
        write_json(out/'failure.json',dict(error=repr(error),completed_queries=len(all_rows),time=timestamp()));raise
    finally:
        signal.alarm(0);write_json(out/'source-freeze.json',dict(status='CLOSED',live_phase_receipts=[]),immutable=False)
