"""Read-only committed snapshot visualizations;explicit G axes/metres/height slice."""
from pathlib import Path
import html,json
import numpy as np
from .storage.store import load_episode,decode_arrays,_verify_ref,IntegrityError
from .geometry.core import A,transform_points

def height_plane(reader,height):
    state=reader._graph["geometry_state"];voxel=float(state["voxel_size"])
    origin=float(state["origin_G"][1])
    if height=="auto":
        spatial=[v for v in reader._graph["views"].values()if v.get("T_G_base")is not None]
        requested=float(max(spatial,key=lambda v:v["capture_seq"])["T_G_base"][1][3])+.25 if spatial else origin+.25
    else:requested=float(height)
    if not np.isfinite(requested):raise ValueError("Finite height slice required")
    actual=origin+float(np.rint((requested-origin)/voxel))*voxel
    return requested,actual,voxel

def slice_points(reader,height="auto"):
    requested,actual,voxel=height_plane(reader,height);points=[];states=[]
    for tile_id in sorted(reader._graph.get("tiles",{})):
        tile=reader.get_geometry(tile_id);arrays=tile["arrays"];meta=tile["metadata"]
        free=arrays["free_count"]>0;surface=arrays["surface_count"]>0
        indices=np.argwhere(free|surface)
        if not len(indices):continue
        n=indices*voxel
        local=n@A[:3,:3]
        world=transform_points(local,meta["T_G_L"])
        keep=np.abs(world[:,1]-actual)<=max(voxel*1e-6,1e-8)
        indices=indices[keep];world=world[keep]
        if not len(world):continue
        f=free[tuple(indices.T)];s=surface[tuple(indices.T)]
        points.append(world);states.append(np.where(f&s,3,np.where(s,2,1)))
    return (np.concatenate(points)if points else np.empty((0,3)),
            np.concatenate(states)if states else np.empty(0,int),
            dict(requested_height_m=requested,sampled_height_m=actual,voxel_size_m=voxel,
                 floor_id=None,world_frame="estimated_G_Y_up",unknown="not observed;not walls"))

def _ply(reader,path):
    clouds=[]
    for entity in reader._graph.get("entities",[]):
        if entity["status"]!="active"or entity.get("attributes")is None:continue
        item=entity["attributes"];ref=item["geometry_blob"]
        arrays=decode_arrays(_verify_ref(reader.root,ref),ref["arrays"])
        points=np.asarray(arrays["points"]);colors=np.asarray(arrays["colors"])
        if colors.shape!=points.shape:raise IntegrityError("Object point/color dimensions differ")
        if not np.isfinite(points).all()or not np.isfinite(colors).all():raise IntegrityError("Nonfinite object cloud/color")
        clouds.append((entity["id"],points,np.rint(np.clip(colors,0,1)*255).astype(np.uint8)))
    count=sum(len(x[1])for x in clouds)
    with path.open("x")as f:
        f.write("ply\nformat ascii 1.0\ncomment estimated_G_Y_up metres;not GT\n")
        f.write("element vertex "+str(count)+"\nproperty float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\nproperty int object_id\nend_header\n")
        for identity,points,colors in clouds:
            for p,c in zip(points,colors):f.write(" ".join(map(str,[*p,*c,identity]))+"\n")
    return count

def render_episode(path,*,revision="CURRENT",height_slice="auto",out=None,export_object_cloud=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    reader=load_episode(path,revision)
    out=Path(out)if out else reader.root/"visualizations"/reader.snapshot_id
    out.mkdir(parents=True,exist_ok=False)
    try:
        reader.verify(hashes=True,references=True)
        points,states,slice_info=slice_points(reader,height_slice)
        fig,axis=plt.subplots(figsize=(9,7))
        for state,color,label in ((1,"#71b5cf","Free evidence"),(2,"#ef9d48","Surface evidence"),(3,"#d55050","Conflict")):
            p=points[states==state]
            if len(p):axis.scatter(p[:,0],p[:,2],s=5,c=color,marker="s",label=label,rasterized=True)
        trajectory=[v for v in reader._graph["views"].values()if v.get("position_G")is not None]
        trajectory=sorted(trajectory,key=lambda v:v["capture_seq"])
        if trajectory:
            p=np.asarray([x["position_G"]for x in trajectory])
            axis.plot(p[:,0],p[:,2],color="#273c60",linewidth=.8,label="Recorded camera trace")
        axis.set(xlabel="Estimated G x (m)",ylabel="Estimated G z (m)",
            title=f"Height slice G y={slice_info['sampled_height_m']:.2f}m;floor_id=null\nsnapshot {reader.snapshot_id[:12]} / pose version {reader.versions['pose_map_version']}")
        axis.set_aspect("equal",adjustable="datalim");axis.grid(alpha=.2)
        from matplotlib.patches import Patch
        handles,labels=axis.get_legend_handles_labels()
        handles.append(Patch(facecolor="white",edgecolor="#94a3b8"));labels.append("Unknown / no displayed evidence")
        axis.legend(handles,labels,loc="upper left",bbox_to_anchor=(1.02,1),borderaxespad=0)
        fig.tight_layout();fig.savefig(out/"geometry_bev.png",dpi=150,bbox_inches="tight");plt.close(fig)
        vertices=_ply(reader,out/"objects.ply")if export_object_cloud else None
        views=[]
        for uid,view in sorted(reader._graph["views"].items(),key=lambda item:item[1]["capture_seq"]):
            loaded=reader.get_view(uid,include_images=False)
            ref=loaded["raw_rgb_ref"]
            rgb=None if ref is None else Path(__import__("os").path.relpath(reader.root/ref["path"],out)).as_posix()
            views.append(dict(uid=uid,seq=view["capture_seq"],position=view.get("position_G"),
                geometry_status=view["geometry_status"],room_type_hint=view.get("room_type_hint"),rgb=rgb))
        payload=json.dumps(dict(snapshot_id=reader.snapshot_id,versions=dict(reader.versions),
            views=views,edges=reader._graph.get("edges",[]),slice=slice_info),ensure_ascii=False).replace("<","\\u003c")
        page="""<!doctype html><html lang="zh"><meta charset="utf-8"><title>Committed graph memory</title>
<style>body{font:15px system-ui;margin:24px;background:#f5f7fa;color:#1e293b}main{display:grid;grid-template-columns:2fr 1fr;gap:24px}.panel{background:white;padding:20px;border-radius:12px}img{max-width:100%}button{margin:3px}pre{white-space:pre-wrap;overflow-wrap:anywhere}svg{width:100%;height:360px;background:#edf2f7}.muted{color:#526172}</style>
<h1>可检查的已提交图记忆</h1><p><a href="map.html">查看物体、观测锚点和原图关联</a></p><p id="identity"></p><p class="muted">估计世界 G：X / Y-up / Z，单位米。高度切片不是楼层确认；未知不作墙体。连线只表示记录的时间邻接，不能当作通行捷径。</p>
<main><section class="panel"><img src="geometry_bev.png" alt="Estimated geometry height slice"><a href="map.html"><img src="objects_anchors_bev.png" alt="Estimated objects and observation anchors"></a><svg id="graph"></svg></section>
<section class="panel"><h2>原始观察</h2><div id="buttons"></div><img id="rgb"><pre id="detail"></pre></section></main>
<script>const data=PAYLOAD;document.querySelector('#identity').textContent='snapshot '+data.snapshot_id+' | pose version '+data.versions.pose_map_version;
const svg=document.querySelector('#graph'),ns='http://www.w3.org/2000/svg',valid=data.views.filter(v=>v.position);
let xs=valid.map(v=>v.position[0]),zs=valid.map(v=>v.position[2]);let xmin=Math.min(0,...xs),xmax=Math.max(1,...xs),zmin=Math.min(0,...zs),zmax=Math.max(1,...zs);
const point=v=>[25+(v.position[0]-xmin)/(xmax-xmin)*650,25+(v.position[2]-zmin)/(zmax-zmin)*300];
svg.setAttribute('viewBox','0 0 700 350');const byid=Object.fromEntries(data.views.map(v=>[v.uid,v]));
for(const e of data.edges){const a=byid[e.src],b=byid[e.dst];if(!a?.position||!b?.position)continue;let p=point(a),q=point(b),line=document.createElementNS(ns,'line');for(const [k,v]of Object.entries({x1:p[0],y1:p[1],x2:q[0],y2:q[1],stroke:e.type==='traversed'?'#48866e':'#a7b3c2','stroke-width':1}))line.setAttribute(k,v);svg.append(line);}
function show(v){document.querySelector('#rgb').src=v.rgb||'';document.querySelector('#detail').textContent=JSON.stringify(v,null,2);}
for(const v of data.views){let b=document.createElement('button');b.textContent='Frame '+v.seq;b.onclick=()=>show(v);document.querySelector('#buttons').append(b);
if(v.position){let p=point(v),c=document.createElementNS(ns,'circle');c.setAttribute('cx',p[0]);c.setAttribute('cy',p[1]);c.setAttribute('r',4);c.setAttribute('fill','#2f668a');c.onclick=()=>show(v);svg.append(c);}}
if(data.views.length)show(data.views[0]);</script></html>""".replace("PAYLOAD",payload)
        (out/"graph.html").write_text(page,encoding="utf8")
        (out/"index.html").write_text(page,encoding="utf8")
        report=dict(snapshot_id=reader.snapshot_id,versions=dict(reader.versions),height_slice=slice_info,
            observed_slice_samples=len(points),object_vertices=vertices,views=len(views),
            scope="read-only estimated memory visualization;no GT or navigation decision",
            files=["index.html","graph.html","geometry_bev.png"]+(["objects.ply"]if export_object_cloud else[]))
        report["semantic_layers"]=render_semantic_layers(reader,out,height_slice)
        (out/"render_report.json").write_text(json.dumps(report,indent=2))
        return report
    finally:reader.close()


def box_corners(bounds):
    """Read both public bbox formats without treating an AABB as an OBB."""
    from .storage.store import IntegrityError
    if bounds.get('kind')=='aabb':
        low=np.asarray(bounds['minimum'],float);high=np.asarray(bounds['maximum'],float)
        if low.shape!=(3,)or high.shape!=(3,):raise IntegrityError('Invalid AABB dimensions')
        center=(low+high)/2;extent=high-low;rotation=np.eye(3)
    elif bounds.get('kind')=='obb':
        center=np.asarray(bounds['center'],float);extent=np.asarray(bounds['extent'],float);rotation=np.asarray(bounds['rotation'],float)
    else:raise IntegrityError('Unknown public bbox format')
    if center.shape!=(3,)or extent.shape!=(3,)or rotation.shape!=(3,3):raise IntegrityError('Invalid bbox dimensions')
    if not all(np.isfinite(a).all()for a in (center,extent,rotation))or(extent<0).any():raise IntegrityError('Invalid bbox values')
    if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5,rtol=0)or not np.isclose(np.linalg.det(rotation),1.,atol=1e-5,rtol=0):raise IntegrityError('BBox rotation is not rigid')
    import itertools
    local=np.asarray(list(itertools.product([-.5,.5],repeat=3)))*extent
    return center,local@rotation.T+center

def render_semantic_layers(reader, out, height_slice="auto"):
    from .storage.archive import canonical
    import itertools,os
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root = reader.root
    out = Path(out)
    graph = reader._graph
    objects = graph.get('scene_state', {}).get('objects', [])
    vsm = graph.get('vsm', {})
    anchors = vsm.get('anchors', {})
    points, states, slice_info = slice_points(reader, height_slice)
    fig, ax = plt.subplots(figsize=(11, 9))
    for state, color, label in [(1, '#b8dce9', 'Observed free evidence'), (2, '#e9b477', 'Surface evidence'), (3, '#d65b5b', 'Free/surface conflict')]:
        x = points[states == state]
        if len(x):
            ax.scatter(x[:, 0], x[:, 2], s=4, color=color, marker='s', label=label, rasterized=True)
    views = sorted(graph['views'].values(), key=lambda v: v['capture_seq'])
    poses = np.asarray([v['position_G'] for v in views if v.get('position_G') is not None])
    if len(poses):
        ax.plot(poses[:, 0], poses[:, 2], color='#36465d', linewidth=0.8, label='Recorded camera trace')
    object_rows = []
    for obj in objects:
        center,corners=box_corners(obj['bbox'])
        for a, b in itertools.combinations(range(8), 2):
            if bin(a ^ b).count("1") == 1:
                ax.plot(corners[[a, b], 0], corners[[a, b], 2], color='#a55a28', alpha=0.5, linewidth=0.7)
        ax.scatter(center[0], center[2], s=30, color='#a55a28', marker='o')
        ax.annotate(str(obj['id']), (center[0], center[2]), fontsize=8, xytext=(3, 3), textcoords='offset points')
        object_rows.append(dict(id=obj['id'], class_name=obj['class_name'], bbox=obj['bbox'], num_detections=obj['num_detections'], anchor_view_uid=obj.get('image'), confidence=obj.get('conf'), geometry_blob=obj['geometry_blob']))
    anchor_rows = []
    for uid, node in anchors.items():
        pos = node.get('position')
        view = reader.get_view(uid, include_images=False)
        ref = view['raw_rgb_ref']
        image = None if ref is None else os.path.relpath(root / ref['path'], out)
        row = dict(uid=uid, sequence=graph['views'][uid]['capture_seq'], position=pos, objects=node['objects'], room_type_hint=node.get('room_type_hint'), rgb=image)
        anchor_rows.append(row)
        if pos is not None:
            ax.scatter(pos[0], pos[2], s=26, marker='^', color='#1c5784')
            ax.annotate('A' + str(row['sequence']), (pos[0], pos[2]), fontsize=7, xytext=(3, -9), textcoords='offset points', color='#1c5784')
    ax.scatter([], [], s=30, color='#a55a28', label='Active object ID / estimated box')
    ax.scatter([], [], s=26, marker='^', color='#1c5784', label='Anchor / observed frame')
    ax.set(xlabel='Estimated G x (m)', ylabel='Estimated G z (m)', title='Objects and observation anchors over geometric evidence\nObject boxes project all heights; geometry is one height slice; unknown remains unknown')
    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(alpha=0.15)
    ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1))
    fig.tight_layout()
    fig.savefig(out / 'objects_anchors_bev.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    payload = dict(snapshot_id=reader.snapshot_id, versions=dict(reader.versions), objects=object_rows, anchors=anchor_rows, visibility_edges=vsm.get('visibility_edges', []), room_type_index=vsm.get('room_type_index', {}), aliases=graph.get('aliases', []), edges=graph.get('edges', []), slice=slice_info)
    (out / 'semantic_map.json').write_bytes(canonical(payload))
    data = json.dumps(payload, ensure_ascii=False).replace('<', chr(92) + 'u003c')
    page = r"""<!doctype html>
<html lang="zh">
<meta charset="utf-8">
<title>最终地图：物体与观测锚点</title>
<style>body{font:15px system-ui;margin:24px;color:#172b3c;background:#f5f7fa}main{display:grid;grid-template-columns:3fr 2fr;gap:24px}.panel{background:white;padding:20px;border-radius:10px}img{max-width:100%}table{border-collapse:collapse;width:100%}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left}button{padding:6px;margin:3px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.muted{color:#526172}</style>
<h1>最终地图：物体、几何与观测锚点</h1>
<p id="identity">
</p>
<p class="muted">坐标 G：Y 向上，单位米。物体类别与房间类型来自观测模型，未经人工确认为真值；观测锚点表示可回看的视角。物体框为三维对象的俯视投影，不代表所有对象处于同一高度。空白区域是未知区域；未识别不等于不存在。连线仅表示实际记录的时序或有向行进，不表示导航捷径。</p>
<main>
<section class="panel">
<img src="objects_anchors_bev.png">
<p>
<a href="graph.html">查看全部观察与有向轨迹</a>
</p>
<h2>活动物体</h2>
<table>
<thead>
<tr>
<th>ID</th>
<th>观测类别</th>
<th>支持检测数</th>
<th>锚点</th>
</tr>
</thead>
<tbody id="objects">
</tbody>
</table>
</section>
<section class="panel">
<h2>锚点与原始观察</h2>
<div id="anchors">
</div>
<div id="related">
</div>
<img id="rgb">
<pre id="detail">
</pre>
<h2>已观察的房间类型提示</h2>
<pre id="rooms">
</pre>
</section>
</main>
<script>
const data=PAYLOAD;
const qs=s=>document.querySelector(s);
qs('#identity').textContent='snapshot '+data.snapshot_id+' | pose version '+data.versions.pose_map_version;
qs('#rooms').textContent=JSON.stringify(data.room_type_index,null,2);
function showObject(o){let links=data.visibility_edges.filter(e=>e[1]===o.id).map(e=>data.anchors.find(a=>a.uid===e[0])).filter(Boolean);
qs('#related').replaceChildren();
for(const a of links){let b=document.createElement('button');
b.textContent='物体 '+o.id+' 的观测 A'+a.sequence;
b.onclick=()=>show({...a,selected_object:o});
qs('#related').append(b)}let a=data.anchors.find(x=>x.uid===o.anchor_view_uid)||links[0];
if(a)show({...a,selected_object:o})}function show(a){qs('#rgb').src=a.rgb||'';
qs('#detail').textContent=JSON.stringify(a,null,2)}for(const a of data.anchors){let b=document.createElement('button');
b.textContent='A'+a.sequence+' '+(a.room_type_hint||'未识别');
b.onclick=()=>show(a);
qs('#anchors').append(b)}for(const o of data.objects){let tr=document.createElement('tr');
for(const v of [o.id,o.class_name,o.num_detections,o.anchor_view_uid?'查看原图':'无锚点']){let td=document.createElement('td');
td.textContent=v;
tr.append(td)}tr.onclick=()=>showObject(o);
qs('#objects').append(tr)}if(!data.objects.length){let tr=document.createElement('tr'),td=document.createElement('td');
td.colSpan=4;
td.textContent='本快照没有活动物体；可回看全部原始观测。';
tr.append(td);
qs('#objects').append(tr)}if(data.anchors.length)show(data.anchors[0]);
else qs('#anchors').textContent='本快照没有观测锚点；全部原始观测仍可从总览查看。';

</script>
</html>"""
    page = page.replace('PAYLOAD',data)
    (out / 'map.html').write_text(page, encoding='utf-8')
    counts = {str(s): int((states == s).sum()) for s in [1, 2, 3]}
    report = dict(objects=len(objects), anchors=len(anchors), visibility_edges=len(payload['visibility_edges']), slice_sample_states=counts, scope='Counts of actual geometry samples, not global occupancy accuracy; no ground-truth labels invented')
    (out / 'final_render_report.json').write_bytes(canonical(report))
    return report
