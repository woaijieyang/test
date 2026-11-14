"""A whole-publication observation map. All reads use the supplied immutable reader."""
from collections import OrderedDict
from copy import deepcopy
from math import atan2, degrees, floor, log10

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..storage.archive import IntegrityError, canonical, digest
from ..visualization import box_corners, height_plane
from .evo_map_image import _traversals, _xz_pose
from .semantic_topology import visible_detection_owners

LEFT, TOP, RIGHT, BOTTOM = 10, 48, 369, 435
INK = '#152e37'
BLUE = '#184f98'
OBJECT = '#944808'


def _hull(points):
    """Monotone chain of the projected corners, retaining no interior box edges."""
    ordered = sorted(set(map(tuple,points)))
    def part(rows):
        result=[]
        for p in rows:
            while len(result)>=2:
                a,b=result[-2:]
                if (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>0:
                    break
                result.pop()
            result.append(p)
        return result
    hull = ordered if len(ordered)<=2 else part(ordered)[:-1]+part(reversed(ordered))[:-1]
    return [list(p) for p in hull]


def _camera(row,version):
    matrix=_xz_pose(row,version,'T_G_cv')
    if matrix is None:
        return None,None
    axis=matrix[[0,2],2]
    length=float(np.linalg.norm(axis))
    return matrix[[0,2],3].tolist(),(axis/length).tolist() if length>1e-8 else None


def _inventory(reader,*,source_labels=False):
    g=reader._graph
    version=reader.versions.get('pose_map_version')
    views=[]
    by_uid={}
    for uid,row in sorted(g['views'].items(),key=lambda it:(it[1]['capture_seq'],it[0])):
        if (row['frame_uid'] != uid or row['capture_seq']>reader.cutoff['capture_seq']
                or row['source_event_seq']>reader.cutoff['event_seq']):
            raise IntegrityError('Global map contains unbound or future view')
        xz,heading=_camera(row,version)
        v=dict(uid=uid,step=row['env_step'],xz=xz,heading_xz=heading,
               caption=f"Observation at step {row['env_step']}"+(' (position unknown)' if xz is None else ''))
        views.append(v)
        by_uid[uid]=v
    scene=g.get('scene_state') or {}
    vsm=g.get('vsm') or {}
    nodes=vsm.get('anchors',{})
    order=scene.get('anchor_keys',[])
    if len(set(order))!=len(order) or set(order)!=set(nodes):
        raise IntegrityError('Global map anchor set differs from published order')
    anchors=[]
    visibility=[]
    for j,uid in enumerate(order,1):
        v=by_uid[uid]
        room=nodes[uid].get('room_type_hint') or 'unknown'
        tag=f"A{v['step']}" if source_labels else f'A{j}'
        heading=v['heading_xz']
        angle=None if heading is None else int(round(degrees(atan2(heading[0],heading[1]))))%360
        heading_label='?' if angle is None else str(angle)
        anchors.append(dict(v,id=tag,room=room,heading_deg=angle,
                            caption=f"{tag}, step {v['step']}, visual room hint: {room}, heading {heading_label} deg clockwise from +Z"))
        owners=visible_detection_owners(reader,uid)
        for oid in nodes[uid]['objects']:
            source=next((k for k in sorted(owners) if owners[k]==oid),None)
            if source is None:
                raise IntegrityError('Global visibility has no source member')
            visibility.append(dict(anchor_uid=uid,object_epoch=scene['epoch'],object_id=oid,
                                   member=f'{uid}:d{source:05d}'))
    if set((e['anchor_uid'],e['object_id']) for e in visibility)!=set(map(tuple,vsm.get('visibility_edges',()))):
        raise IntegrityError('Global map visibility edges disagree')
    objects=[]
    for o in sorted((e for e in g.get('entities',[]) if e['status']=='active'),key=lambda e:(e['epoch'],e['id'])):
        label=o['class_name']
        if source_labels and (type(o['id']) is not int or o['id']<0 or o['epoch']!=scene.get('epoch')):
            raise IntegrityError('Active object is outside the current scene identity')
        tag=f"O{o['id']}" if source_labels else f'O{len(objects)+1}'
        bounds=(o.get('attributes') or {}).get('bbox')
        center,hull=None,None
        if bounds and o.get('pose_map_version')==version and version is not None:
            c,corners=box_corners(bounds)
            if not np.isfinite(corners).all():
                raise IntegrityError('Nonfinite global object bounds')
            center=c[[0,2]].tolist()
            hull=_hull(corners[:,[0,2]])
        objects.append(dict(epoch=o['epoch'],id=o['id'],map_id=tag,label=label,xz=center,
                            footprint_xz=hull,caption=f'{tag}, estimated {label}'+(' (position unknown)' if center is None else '')))
    if source_labels and (len({a['id'] for a in anchors})!=len(anchors)
                          or len({o['map_id'] for o in objects})!=len(objects)):
        raise IntegrityError('Source-derived map label collision')
    return dict(views=views,anchors=anchors,objects=objects),visibility


def _font(size,bold=False):
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',size)
    except OSError:
        return ImageFont.load_default()


class MapTileColumns:
    """Host-episode cache of compact XZ contributions, bounded by the geometry profile."""
    def __init__(self, reader, capacity):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('Positive map tile cache capacity required')
        self.scope=(reader.root.resolve(),reader.identity['episode_uid'])
        self.capacity=capacity
        self.items=OrderedDict()
        self.hits=self.decodes=0

    def read(self, reader, tid, y, voxel):
        from .host_input_compiler import plain
        if (reader.root.resolve(),reader.identity['episode_uid'])!=self.scope:
            raise IntegrityError('Map tile cache crossed episode')
        tile=reader._graph['tiles'][tid]
        revision=reader.versions['pose_map_version']
        if tile['pose_map_version']!=revision:
            raise IntegrityError('Map tile cache crossed pose revision')
        record=tile['record']
        ref=record['blob']
        path=(reader.root/ref['path']).resolve()
        if not path.is_relative_to(self.scope[0]):
            raise IntegrityError('Map tile outside episode')
        def signature():
            try:st=path.stat()
            except FileNotFoundError:
                from ..storage.archive import UnavailableMaterial
                raise UnavailableMaterial('missing_material') from None
            return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        before=signature()
        key=(revision,y,voxel,canonical(plain(record)),before)
        previous=self.items.get(tid)
        if previous is not None and previous[0]==key:
            self.items.move_to_end(tid)
            self.hits+=1
            return previous[1]
        result=_tile_columns(reader,tid,y,voxel)
        if signature()!=before:
            raise IntegrityError('Tile changed during map projection')
        self.decodes+=1
        self.items[tid]=(key,result)
        self.items.move_to_end(tid)
        if len(self.items)>self.capacity:
            self.items.popitem(last=False)
        return result


def _tile_columns(reader,tid,y,voxel):
    from ..geometry.core import A, transform_points
    tile=reader.get_geometry(tid)
    data=tile['arrays']
    free=data['free_count']>0
    surface=data['surface_count']>0
    idx=np.argwhere(free|surface)
    if not len(idx):
        return None
    world=transform_points((idx*voxel)@A[:3,:3],tile['metadata']['T_G_L'])
    if not np.isfinite(world).all():
        raise IntegrityError('Nonfinite world voxel')
    low_y=float(world[:,1].min())
    high_y=float(world[:,1].max())
    source_count=len(idx)
    xz=np.floor(world[:,[0,2]]/voxel+.5).astype(np.int64)
    cells,inverse=np.unique(xz,axis=0,return_inverse=True)
    values=np.full(len(cells),4,dtype=np.uint8)
    mask=np.abs(world[:,1]-y)<=max(voxel*1e-6,1e-8)
    selected=tuple(idx[mask].T)
    flags=free[selected].astype(np.uint8)+2*surface[selected].astype(np.uint8)
    np.bitwise_or.at(values,inverse[mask],flags)
    return cells,values,low_y,high_y,source_count


def _columns(reader, height='auto', cache=None):
    """Accumulate single-slice bits and all-height observed columns from one read per tile."""
    requested,y,voxel=height_plane(reader,height)
    tiles=sorted(reader._graph['tiles'])
    chunks=[]
    source_count=0
    low_y,high_y=np.inf,-np.inf
    for tid in tiles:
        result=_tile_columns(reader,tid,y,voxel) if cache is None else cache.read(reader,tid,y,voxel)
        if result is None:continue
        cells,values,tile_low,tile_high,count=result
        low_y=min(low_y,tile_low)
        high_y=max(high_y,tile_high)
        source_count+=count
        chunks.append((cells,values))
    plane=dict(requested_height_m=requested,sampled_height_m=y,voxel_size_m=voxel,
               floor_id=None,world_frame='estimated_G_Y_up',unknown='no observed voxel at any height in displayed column')
    if not chunks:
        return np.empty((0,2),dtype=np.int64),np.empty(0,dtype=np.uint8),plane,{}
    cells,inverse=np.unique(np.concatenate([c for c,_ in chunks]),axis=0,return_inverse=True)
    flags=np.zeros(len(cells),dtype=np.uint8)
    np.bitwise_or.at(flags,inverse,np.concatenate([f for _,f in chunks]))
    counts=dict(tiles_read=len(tiles),tile_observed_voxels=source_count,observed_height_range_m=[low_y,high_y],
                any_height_cells=len(cells),off_slice_only_cells=int(np.count_nonzero(flags==4)),
                footprint_sha256=digest(cells.astype('<i8').tobytes()))
    return cells,flags,plane,counts


def _raster(cells,flags,voxel,limits):
    x0,z0,x1,z1=limits
    pair=np.dtype([('x','<i8'),('z','<i8')])
    keys=np.ascontiguousarray(cells,dtype='<i8').view(pair).ravel()
    x=np.floor(np.linspace(x0,x1,RIGHT-LEFT+1)/voxel+.5).astype(np.int64)
    z=np.floor(np.linspace(z1,z0,BOTTOM-TOP+1)/voxel+.5).astype(np.int64)
    q=np.empty((len(z),len(x)),dtype=pair)
    q['x'],q['z']=x[None,:],z[:,None]
    i=np.minimum(np.searchsorted(keys,q),len(keys)-1)
    # State 4 is seen at another height only; states 1-3 retain the original slice semantics.
    colors=np.array([[245,245,241],[184,222,215],[225,158,73],[190,88,124],[184,193,214]],dtype=np.uint8)
    state=np.where(flags==4,4,flags&3)
    pixels=np.where(keys[i]==q,state[i],0)
    return Image.fromarray(colors[pixels]),int((x[-1]-x[0]+1)*(z[0]-z[-1]+1))


def _draw(cells,flags,plane,manifest,segments):
    nodes=manifest['nodes']
    camera=manifest['current_camera']
    coords=[cells*plane['voxel_size_m']]
    coords.extend([v['xz']] for v in nodes['views'] if v['xz'] is not None)
    coords.extend(o['footprint_xz'] for o in nodes['objects'] if o['footprint_xz'])
    coords.extend(s for _,s in segments)
    if camera and manifest.get('camera_overlay'):coords.append([camera['xz']])
    coords=np.concatenate(coords)
    lo,hi=coords.min(0),coords.max(0)
    wh=np.array([RIGHT-LEFT,BOTTOM-TOP])
    scale=float(max((hi-lo+2*plane['voxel_size_m'])/(wh-30)))
    center=(hi+lo)/2
    x0,z0=center-wh*scale/2
    x1,z1=center+wh*scale/2
    limits=[float(x0),float(z0),float(x1),float(z1)]
    raster,displayed=_raster(cells,flags,plane['voxel_size_m'],limits)
    used=(flags&3)>0
    states=flags[used]&3
    counts=np.bincount(states,minlength=4)
    gridhash=digest(canonical(dict(cells=digest(cells[used].astype('<i8').tobytes()),states=digest(states.tobytes()))))
    manifest['coverage'].update(displayed_columns=displayed,unknown_columns=displayed-len(cells))
    im=Image.new('RGB',(512,512),'#ffffff')
    im.paste(raster,(LEFT,TOP))
    d=ImageDraw.Draw(im)
    text,small,bold=_font(11),_font(10),_font(12,True)
    def xy(p):
        return round(LEFT+(p[0]-x0)/scale),round(BOTTOM-(p[1]-z0)/scale)
    def mark(p,heading,color,length):
        x,y=xy(p)
        if heading is not None:
            dx,dz=heading
            d.line([(x,y),(x+round(length*dx),y-round(length*dz))],fill=color,width=2)
        d.ellipse((x-2,y-2,x+2,y+2),fill=color)
    d.text((10,4),'Observed scene map',font=_font(18,True),fill=INK)
    d.text((10,29),f"Estimated XZ  /  +X right, +Z up  /  height slice {plane['sampled_height_m']:.2f} m",font=text,fill=INK)
    d.rectangle((LEFT,TOP,RIGHT,BOTTOM),outline='#9aa9ab')
    for _,seg in segments:d.line([xy(p) for p in seg],fill='#28675c',width=3)
    for v in nodes['views']:
        if v['xz'] is not None:
            x,y=xy(v['xz'])
            d.ellipse((x-1,y-1,x+1,y+1),fill='#405e61')
    for o in nodes['objects']:
        hull=o['footprint_xz']
        if hull:
            outline=[xy(p) for p in hull]
            if len(outline)>1:d.line(outline+[outline[0]],fill=OBJECT,width=2)
            else:mark(hull[0],None,OBJECT,1)
    # Reserve nonoverlapping label boxes; leaders keep all displaced labels grounded.
    shown=set()
    occupied=[]
    def place(node,id_key,color,*,inventory_label=True):
        if node['xz'] is None:return
        tag=node[id_key]
        x,y=xy(node['xz'])
        size=d.textbbox((0,0),tag,font=small)
        width,height=size[2]-size[0]+5,size[3]-size[1]+4
        for r in (7,17,29,44,64,85):
            for dx,dy in ((1,-1),(1,1),(-1,-1),(-1,1),(0,-1),(0,1),(1,0),(-1,0)):
                px=x+dx*r-(width if dx<0 else 0)
                py=y+dy*r-(height if dy<0 else 0)
                box=(px,py,px+width,py+height)
                if px<LEFT or py<TOP or box[2]>RIGHT or box[3]>BOTTOM:continue
                if any(px<=b[2]+2 and box[2]>=b[0]-2 and py<=b[3]+2 and box[3]>=b[1]-2 for b in occupied):continue
                d.line([(x,y),(max(px,min(x,box[2])),max(py,min(y,box[3])))],fill=color,width=1)
                d.rectangle(box,fill='white',outline=color)
                d.text((px+2,py+1-size[1]),tag,font=small,fill=color)
                occupied.append(box)
                if inventory_label:shown.add(tag)
                return
    for a in nodes['anchors']:
        if a['xz'] is not None:mark(a['xz'],a['heading_xz'],BLUE,13)
        place(a,'id',BLUE)
    for o in nodes['objects']:place(o,'map_id',OBJECT)
    if camera:
        x,y=xy(camera['xz'])
        if manifest.get('camera_overlay') or manifest.get('node_summary')=='grounded':
            now_step=manifest.get('current_step') if 'current_step' in manifest else manifest['camera_overlay']['step']
            place(dict(xz=camera['xz'],label='Now '+str(now_step)),'label',INK,inventory_label=False)
        d.ellipse((x-5,y-5,x+5,y+5),outline='#12151a',width=2)
        mark(camera['xz'],camera['heading_xz'],'#12151a',20)
        if manifest.get('node_summary')=='grounded' and camera['heading_xz'] is not None:
            dx,dz=camera['heading_xz']
            tip=(x+20*dx,y-20*dz)
            d.polygon([tip,(tip[0]-7*dx+4*dz,tip[1]+7*dz+4*dx),(tip[0]-7*dx-4*dz,tip[1]+7*dz-4*dx)],fill=INK)
    grounded=manifest.get('node_summary')=='grounded'
    legend=[]
    d.text((378,TOP),'View cameras' if grounded else 'Anchor hints',font=bold,fill=BLUE)
    for a in nodes['anchors']:
        angle='?' if a['heading_deg'] is None else str(a['heading_deg'])+'°'
        legend.append((a['id'],angle+' '+a['room'],BLUE))
    legend.append((None,'Object estimates',OBJECT))
    legend.extend((o['map_id'],o['label'],OBJECT) for o in nodes['objects'])
    pos=TOP+20
    listed=[]
    for tag,label,color in legend:
        if pos>BOTTOM-23:break
        if tag is None:
            pos+=4;d.text((378,pos),label,font=bold,fill=color);pos+=19
        else:
            name=f'{tag} {label}'
            while d.textlength(name,font=text)>128:name=name[:-1]
            if name!=f'{tag} {label}':name=name[:-2]+'..'
            d.text((378,pos),name,font=text,fill=color)
            listed.append(tag);pos+=16
    remaining=len(nodes['objects'])+len(nodes['anchors'])-len(listed)
    if remaining:d.text((378,pos),f'+{remaining} in node list',font=small,fill=INK)
    magnitude=10**floor(log10(scale*70))
    length=max(n*magnitude for n in (.1,.2,.5,1,2,5,10) if n*magnitude<=scale*70)
    d.line([(13,453),(13+round(length/scale),453)],fill=INK,width=3)
    d.text((18+round(length/scale),444),f'{length:g} m',font=text,fill=INK)
    d.text((145,444),'Line: recorded travel   /   dots: camera views',font=text,fill=INK)
    for x,state,color in ((10,'unknown','#f5f5f1'),(95,'other heights','#b8c1d6'),(209,'slice free','#b8ded7'),(301,'slice surface','#e19e49'),(411,'conflict','#be587c')):
        d.rectangle((x,466,x+12,477),fill=color,outline='#778987')
        d.text((x+16,464),state,font=text,fill=INK)
    if grounded:
        key='Now: slot 8 camera / arrow: forward' if camera else 'Slot 8 camera: unlocated'
        d.text((10,488),key+'   |   A: past camera   |   O: estimated object',font=small,fill=INK)
    else:
        d.text((10,488),'Boxes span all heights. Camera: '+('known' if camera else 'unknown')+
               '. Anchor rays show observed headings.',font=small,fill=INK)
    manifest.update(world_bounds_xz=limits,metres_per_pixel=scale,plot_rect=[LEFT,TOP,RIGHT,BOTTOM],
                    scale_bar_metres=length,slice_sha256=gridhash,rgb_sha256=digest(im.tobytes()),
                    labels_in_plot=sorted(shown),labels_in_legend=listed)
    manifest['coverage']['slice_cells']=dict(free=int(counts[1]),surface=int(counts[2]),conflict=int(counts[3]))
    return im


def read_current_camera(history, source_pin, uid, decision_event, *, with_right=False):
    """Read only the current observation's camera geometry; keep historical layers on history."""
    from contextlib import closing
    from ..geometry.core import Q
    from ..storage.store import load_episode
    from ...observation_pose.provider_contract import validate_simulator_pose_record
    if source_pin is None or source_pin==history.snapshot_id:return None
    ep=history.identity['episode_uid']
    with closing(load_episode(history.root,revision=source_pin,_history_cache=getattr(history,'history_page_cache',None))) as live:
        seq=live.cutoff['capture_seq']
        if (live.identity['episode_uid']!=ep or uid!=f'{ep}:f{seq:06d}'
                or seq<=history.cutoff['capture_seq'] or type(decision_event) is not int
                or not history.cutoff['event_seq']<live.cutoff['event_seq']<decision_event):
            raise IntegrityError('Camera overlay source crossed the episode, frame or decision cutoff')
        old_seq=history.cutoff['capture_seq']
        old=history.get_camera_pose_view(f'{ep}:f{old_seq:06d}')
        row=live.get_camera_pose_view(uid)
        for item,reader,n in ((old,history,old_seq),(row,live,seq)):
            cap=item['capture']
            if (item['snapshot_id']!=reader.snapshot_id or item['frame_uid']!=cap['frame_uid']
                    or cap['frame_uid']!=f'{ep}:f{n:06d}' or item['capture_seq']!=cap['capture_seq']
                    or cap['capture_seq']!=n or item['env_step']!=cap['env_step'] or cap['env_step']!=n-1
                    or cap['episode_uid']!=ep or cap['event_seq']!=item['source_event_seq']
                    or cap['event_seq']!=reader.cutoff['event_seq'] or cap['pose_provider']!='simulator_ground_truth'):
                raise IntegrityError('Camera overlay capture binding differs')
        cap=row['capture'];prior=old['capture']['pose_record'];pose=cap['pose_record']
        try:frame=validate_simulator_pose_record(pose,cap['T_base_camera'])
        except (TypeError,ValueError) as error:raise IntegrityError('Camera overlay DTO differs from its calibration') from error
        if (not frame.episode_instance or frame.episode_instance!=prior['episode_instance']
                or frame.episode_id!=ep or frame.frame_id!=uid or frame.timestamp_ns!=cap['sensor_timestamp_ns']):
            raise IntegrityError('Camera overlay pose belongs to a different measurement')
        ref=dict(snapshot_id=source_pin,frame_uid=uid,step=seq-1,capture_seq=seq,
                 source_event=cap['event_seq'],sensor_timestamp_ns=frame.timestamp_ns,episode_instance=frame.episode_instance,
                 pose_map_version=frame.map_version,calibration_hash=cap['calibration_hash'])
        if not frame.valid or not prior['valid']:
            return dict(ref,status='unknown',reason='pose_unavailable')
        if history.versions['pose_map_version']!=live.versions['pose_map_version'] or history.versions['pose_map_version']!=frame.map_version:
            return dict(ref,status='unknown',reason='different_pose_revision')
        binding=row.get('pose_binding') or {}
        if (binding.get('episode_instance')!=frame.episode_instance or binding.get('source_frame_uid')!=uid
                or binding.get('pose_map_version')!=frame.map_version or row.get('T_G_cv') is None
                or not np.allclose(row['T_G_cv'],Q@np.asarray(pose['T_map_camera_cv']),rtol=0,atol=1e-9)):
            raise IntegrityError('Camera overlay disagrees with the calibrated camera transform')
        xz,heading=_camera(row,frame.map_version)
        if xz is None:raise IntegrityError('Camera overlay lost the source pose revision')
        if with_right:ref['right_xz']=_ground_right(row['T_G_cv'],heading)
        return dict(ref,status='known',xz=xz,heading_xz=heading)


def describe_map_nodes(info):
    """Describe only witnessed map entities and horizontal displacements from native slot 8."""
    camera=info['current_camera']
    forward=None if camera is None else camera['heading_xz']
    right=None if camera is None else camera.get('right_xz')
    def relative(xz):
        if xz is None:return 'position unknown'
        if forward is None or right is None:return f"map XZ ({xz[0]:.1f}, {xz[1]:.1f}) m"
        delta=np.asarray(xz)-camera['xz']
        lateral=float(delta@right);ahead=float(delta@forward)
        def offset(value,positive,negative):
            if round(abs(value),1)==0:return '0 m lateral' if positive=='right' else '0 m longitudinal'
            return f"{abs(value):.1f} m {positive if value>0 else negative}"
        return offset(lateral,'right','left')+', '+offset(ahead,'ahead','behind')
    anchors={a['uid']:a for a in info['nodes']['anchors']}
    objects={(o['epoch'],o['id']):o for o in info['nodes']['objects']}
    seen={a['uid']:[] for a in anchors.values()}
    sources={k:[] for k in objects}
    for edge in info['relations']['visibility']:
        key=(edge['object_epoch'],edge['object_id'])
        if key not in objects:raise IntegrityError('Visibility relation lacks an active object')
        seen[edge['anchor_uid']].append(objects[key]['map_id'])
        sources[key].append(anchors[edge['anchor_uid']])
    for uid,a in anchors.items():
        heading='' if a['heading_deg'] is None else f", heading {a['heading_deg']} deg"
        refs=', '.join(seen[uid]) or 'none recorded'
        a['caption']=f"{a['id']} camera, step {a['step']}: {relative(a['xz'])}{heading}; visual room hint {a['room']}; saw {refs}"
    for key,o in objects.items():
        observed=', '.join(f"{a['id']} (step {a['step']})" for a in sources[key]) or 'no anchor link'
        o['caption']=f"{o['map_id']} estimated {o['label']} center: {relative(o['xz'])}; historical views: {observed}"
    if camera is None:
        status=(info.get('camera_overlay') or {}).get('reason','no verified pose on this map')
        now=f"Slot 8 camera unlocated ({status})."
    else:
        x,z=camera['xz'];angle='unknown' if forward is None else str(int(round(degrees(atan2(forward[0],forward[1]))))%360)+' deg'
        now=f"Now = current RGB slot 8, step {info['current_step']}, map XZ ({round(x,1) or 0.:.1f}, {round(z,1) or 0.:.1f}) m, heading {angle}."
    info['caption']=(f"Map through step {info['cutoff']['capture_seq']-1}. {now} Map right = +X, up = +Z; headings clockwise from +Z. "
                     "Offsets are horizontal from Now. Room hints describe images; object labels are fused estimates. "
                     "Camera points and recorded travel lines show past observations and motion. "
                     "Unknown = no observed height; other heights = evidence outside this slice. Global map: <image>\n")


def _ground_right(matrix,heading):
    if heading is None:return None
    axis=np.asarray(matrix)[[0,2],0]
    right=np.array([heading[1],-heading[0]])
    sign=float(axis@right)
    return None if abs(sign)<1e-8 else (right*np.sign(sign)).tolist()


def global_map_caption(manifest,style='full'):
    if style=='compact':
        step=manifest['cutoff']['capture_seq']-1
        current=manifest['current_camera']
        if current:
            heading=current['heading_xz']
            angle='unknown' if heading is None else str(int(round(degrees(atan2(heading[0],heading[1]))))%360)+' deg clockwise from +Z'
            camera=f"Now = slot 8, step {manifest.get('current_step',step)}, heading {angle}."
        else:camera="Slot 8 camera unlocated."
        scope=''
        if manifest.get('label_scheme')=='source_identity_v1':
            epoch=manifest['object_epoch'];initial=digest((manifest['episode_uid']+'|initial|0').encode())
            if epoch:scope=' O IDs: '+('initial' if epoch==initial else epoch)+' generation.'
        return (f"Observed map through step {step}. {camera} Map right +X, up +Z. "
                "A: past camera; O: object estimate; lines: past travel; unknown: no observations."
                +scope+" <image>\n")
    if style!='full':raise IntegrityError('Unknown global map caption style')
    if manifest.get('node_summary')=='grounded':return manifest['caption']
    return (manifest['caption']+' Current camera on this map: '+manifest['current_status']+
            '. Coverage is RGB-D observation evidence in the displayed extent; consult the map legend for height. Movement edges are past travel, not suggested actions.'
            +' Node labels refer to this map at this decision. Global map: <image>\n')


def render_global_map(reader,current_uid,*,tile_cache=None,camera_source=None,decision_event=None,grounded=False,source_labels=False):
    """Return a bounded RGB and all eligible node IDs without retaining map history."""
    overlay=read_current_camera(reader,camera_source,current_uid,decision_event,with_right=grounded)
    if source_labels and not grounded:raise ValueError('Source labels require grounded node descriptions')
    key=(reader.snapshot_id,current_uid,camera_source,grounded,source_labels)
    previous=getattr(reader,'_evo_global_map_cache',None)
    if previous and previous[0]==key:
        return previous[1].copy(),deepcopy(previous[2])
    graph=reader._graph
    nodes,visibility=_inventory(reader,source_labels=source_labels)
    views={v['uid']:v for v in nodes['views']}
    ep=reader.identity['episode_uid']
    if current_uid is not None and not current_uid.startswith(ep+':f'):
        raise IntegrityError('Global map current camera crossed episode')
    current=views.get(current_uid)
    if current is not None and graph['views'][current_uid]['capture_seq']!=reader.cutoff['capture_seq']:
        raise IntegrityError('Global map current camera predates publication')
    binding=(graph['views'].get(current_uid) or {}).get('pose_binding') or {}
    camera=None
    if (current and current['xz'] is not None and binding.get('source_frame_uid')==current_uid
            and binding.get('pose_map_version')==reader.versions.get('pose_map_version')):
        camera=dict(uid=current_uid,xz=current['xz'],heading_xz=current['heading_xz'])
    if overlay and overlay['status']=='known':
        camera=dict(uid=current_uid,xz=overlay['xz'],heading_xz=overlay['heading_xz'])
    if grounded and camera:
        camera['right_xz']=overlay['right_xz'] if overlay else _ground_right(graph['views'][current_uid]['T_G_cv'],camera['heading_xz'])
    segments=_traversals(reader)
    traversed=[{k:e[k] for k in ('id','src','dst')} for e in graph['edges'] if e['type']=='traversed']
    coverage=dict(views=len(views),anchors=len(nodes['anchors']),objects=len(nodes['objects']),
                  visibility=len(visibility),traversed=len(traversed),drawn_traversed=len(segments),
                  unlocated_views=sum(v['xz'] is None for v in nodes['views']),
                  unlocated_anchors=sum(a['xz'] is None for a in nodes['anchors']),
                  unlocated_objects=sum(o['xz'] is None for o in nodes['objects']))
    info=dict(schema_version=2,episode_uid=ep,snapshot_id=reader.snapshot_id,cutoff=dict(reader.cutoff),
              pose_map_version=reader.versions.get('pose_map_version'),current_uid=current_uid,
              current_status='known' if camera else 'unknown',current_camera=camera,nodes=nodes,
              relations=dict(visibility=visibility,traversed=traversed),coverage=coverage,height_slice=None,
              caption=f"Historical map through step {reader.cutoff['capture_seq']-1}: {len(views)} observations, "
                      f"{coverage['anchors']} anchors, {coverage['objects']} active objects, "
                      f"{len(traversed)} recorded movement edges. Room labels are visual hints.")
    if overlay:
        info['schema_version']=3
        info['camera_overlay']=overlay
        if camera:info['caption']+=f" The Now marker is the camera at step {overlay['step']}, overlaid on history through step {reader.cutoff['capture_seq']-1}."
    info['unlocated_nodes']=dict(views=[v['uid'] for v in nodes['views'] if v['xz'] is None],
                                 anchors=[a['id'] for a in nodes['anchors'] if a['xz'] is None],
                                 objects=[o['map_id'] for o in nodes['objects'] if o['xz'] is None])
    if graph.get('geometry_state') and graph.get('tiles'):
        cells,flags,plane,column_counts=_columns(reader,cache=tile_cache)
        info['height_slice']=plane
        if len(cells):
            info['coverage'].update(column_counts)
            info['caption']+=' Other heights indicates observed voxels outside the displayed slice. Unknown columns lack evidence at every height.'
            if grounded:
                info.update(schema_version=4,node_summary='grounded',current_step=overlay['step'] if overlay else (current['step'] if current else None))
                describe_map_nodes(info)
                if source_labels:
                    epoch=(graph.get('scene_state') or {}).get('epoch')
                    if not epoch and nodes['objects']:raise IntegrityError('Missing object-map epoch')
                    # The source service derives the first namespace from the episode ID.
                    # Only that exact namespace can use the short, reserved display name.
                    initial=digest((ep+'|initial|0').encode())
                    display='initial' if epoch==initial else epoch
                    info.update(schema_version=5,label_scheme='source_identity_v1',object_epoch=epoch)
                    namespace=(f"O numbers are tracker IDs in object-map generation {display}; "
                               "a new generation resets their meaning." if display else "No object generation recorded.")
                    info['caption']=info['caption'].replace('Global map: <image>',
                        'A numbers are source steps. '+namespace+' Global map: <image>')

            image=_draw(cells,flags,plane,info,segments)
            info.update(status='rendered',reason=None)
            reader._evo_global_map_cache=(key,image.copy(),deepcopy(info))
            return image,info
        reason='no_observed_voxels'
    else:reason='no_geometry'
    return None,dict(info,status='unavailable',reason=reason)
