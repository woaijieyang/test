"""Render a decision-time XZ evidence slice directly from a pinned episode reader."""
from copy import deepcopy
from itertools import combinations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..storage.archive import IntegrityError, canonical, digest
from ..visualization import box_corners, slice_points
from .semantic_topology import visible_detection_owners

_SIZE = 512
_RECT = (14, 44, 498, 412)
_PALETTE = np.array([[245,245,241],[184,222,215],[225,158,73],[190,88,124]], dtype=np.uint8)


def _xz_pose(view, version, key):
    pose = view.get(key)
    if pose is None or view.get('pose_map_version') != version:
        return None
    mat = np.asarray(pose, dtype=float)
    if mat.shape != (4,4) or not np.isfinite(mat).all():
        raise IntegrityError('Invalid pinned BEV pose')
    return mat


def _selected(reader, anchors):
    g = reader._graph
    nodes = g['vsm']['anchors']
    epoch = g['scene_state']['epoch']
    entities = {o['id']:o for o in g['entities'] if o['status']=='active' and o['epoch']==epoch}
    version = reader.versions['pose_map_version']
    rows, objects = [], {}
    for j, a in enumerate(anchors):
        uid = a['uid']
        v, node = g['views'][uid], nodes[uid]
        room = node.get('room_type_hint') or 'unknown'
        if (v['capture_seq'] > reader.cutoff['capture_seq'] or v['env_step'] != a['step']
                or room != a['room'] or uid in {r['uid'] for r in rows}):
            raise IntegrityError('BEV anchor identity, step or room differs')
        pose = _xz_pose(v, version, 'T_G_cv')
        rows.append(dict(anchor_index=j, uid=uid, step=a['step'], room=room,
                         xz=None if pose is None else pose[[0,2],3].tolist()))
        owners = visible_detection_owners(reader, uid)
        for c in a['evidence']:
            d, oid = c['index'], c['object_id']
            member = f'{uid}:d{d:05d}'
            if (c['object_epoch'] != epoch or owners.get(d) != oid or c['member'] != member
                    or oid not in entities or c['aggregate_label'] != entities[oid]['class_name']):
                raise IntegrityError('BEV selected crop lacks its pinned visible source')
            o = entities[oid]
            if o.get('pose_map_version') != version or not (o.get('attributes') or {}).get('bbox'):
                continue
            if oid not in objects:
                _, corners = box_corners(o['attributes']['bbox'])
                if corners.shape != (8,3) or not np.isfinite(corners).all():
                    raise IntegrityError('Invalid BEV projected bounds')
                objects[oid] = dict(object_id=oid, object_epoch=epoch, label=o['class_name'],
                                    members=[], corners_xz=corners[:,[0,2]].tolist())
            objects[oid]['members'].append(member)
    return rows, list(objects.values())


def _traversals(reader):
    graph = reader._graph
    edges = {e['id']:e for e in graph['edges'] if e['type']=='traversed'}
    seen, segments = set(), []
    for t in reader.get_trace():
        record = t['motion'].get('traversed')
        if record is None:
            continue
        key = record['id']
        u, v = t['pre'], t['post']
        if (key in seen or key not in edges or edges[key]['src'] != u or edges[key]['dst'] != v
                or record['src'] != u or record['dst'] != v or t['action']['action_id'] != 1
                or t['action']['collision'] is not False):
            raise IntegrityError('BEV traversal disagrees with executed movement')
        seen.add(key)
        pre, post = graph['views'][u], graph['views'][v]
        if post['capture_seq'] != pre['capture_seq']+1 or post['capture_seq'] > reader.cutoff['capture_seq']:
            raise IntegrityError('BEV traversal crosses a gap or cutoff')
        poses = [_xz_pose(view,reader.versions['pose_map_version'],'T_G_base') for view in (pre,post)]
        if all(m is not None for m in poses):
            segments.append((key,[m[[0,2],3].tolist() for m in poses]))
    if seen != set(edges):
        raise IntegrityError('BEV graph contains an unwitnessed traversal')
    return segments


def _geometry(points, states, voxel, limits):
    x0,z0,x1,z1 = limits
    left,top,right,bottom = _RECT
    # World-aligned voxel bins: coincident free/surface observations yield conflict.
    # Sample only display-sized arrays even when the observed world spans distant tiles.
    cells = np.floor(points[:,[0,2]]/voxel+.5).astype(np.int64)
    keys, inverse = np.unique(cells, axis=0, return_inverse=True)
    values = np.zeros(len(keys), dtype=np.uint8)
    np.bitwise_or.at(values,inverse,states.astype(np.uint8))
    x = np.floor(np.linspace(x0,x1,right-left+1)/voxel+.5).astype(np.int64)
    z = np.floor(np.linspace(z1,z0,bottom-top+1)/voxel+.5).astype(np.int64)
    # Structured search avoids allocating a dense grid over the world extent.
    pair = np.dtype([('x','<i8'),('z','<i8')])
    key = np.ascontiguousarray(keys,dtype='<i8').view(pair).ravel()
    q = np.empty((len(z),len(x)),dtype=pair)
    q['x'],q['z'] = x[None,:],z[:,None]
    i = np.searchsorted(key,q)
    i = np.minimum(i,len(key)-1)
    pixels = np.where(key[i]==q,values[i],0)
    return Image.fromarray(_PALETTE[pixels]), np.bincount(values,minlength=4).tolist(), digest(canonical(
        dict(cells=digest(keys.astype('<i8').tobytes()),states=digest(values.tobytes()))))


def render_evo_map(reader, anchors, current_uid):
    """Return (512px RGB, JSON provenance), or (None, provenance with reason).

    One immutable rendered result per reader is retained. Keys bind the pin,
    selected groups and current UID. Returned images and records are caller-owned.
    """
    requested = [dict(uid=a['uid'],step=a['step'],room=a['room'],evidence=[
        {k:c[k] for k in ('member','index','object_id','object_epoch','aggregate_label')} for c in a['evidence']])
                 for a in anchors]
    key = digest(canonical([reader.snapshot_id,requested,current_uid]))
    cache = getattr(reader,'_evo_bev_cache',None)
    if cache is not None and cache[0]==key:
        return cache[1].copy(),deepcopy(cache[2])
    graph = reader._graph
    info = dict(schema_version=1,snapshot_id=reader.snapshot_id,episode_uid=reader.identity['episode_uid'],
                pose_map_version=reader.versions.get('pose_map_version'),current_uid=current_uid,
                cutoff=dict(reader.cutoff),status='unavailable')
    if not requested:
        return None,dict(info,reason='no_selected_anchors')
    if not graph.get('geometry_state') or not graph.get('tiles'):
        return None,dict(info,reason='no_geometry')
    points,states,plane = slice_points(reader,'auto')
    if len(points)==0:
        return None,dict(info,reason='empty_geometry_slice',height_slice=plane)
    if not np.isfinite(points).all() or not np.isin(states,[1,2,3]).all():
        raise IntegrityError('Invalid BEV slice evidence')
    rows,objects = _selected(reader,requested)
    segments = _traversals(reader)
    if current_uid is not None and not current_uid.startswith(info['episode_uid']+':f'):
        raise IntegrityError('BEV current UID crossed episode')
    view = graph['views'].get(current_uid)
    if view is not None and view['capture_seq'] != reader.cutoff['capture_seq']:
        raise IntegrityError('Requested current camera predates the pinned frontier')
    current = None if view is None else _xz_pose(view,info['pose_map_version'],'T_G_cv')
    binding = (view or {}).get('pose_binding') or {}
    if binding.get('source_frame_uid') != current_uid or binding.get('pose_map_version') != info['pose_map_version']:
        current = None
    camera = None
    if current is not None:
        forward = current[[0,2],2]
        norm = float(np.linalg.norm(forward))
        camera = dict(xz=current[[0,2],3].tolist(),forward_xz=(forward/norm).tolist() if norm>1e-8 else None)
    scene = [points[:,[0,2]]]
    scene.extend(np.asarray([a['xz']]) for a in rows if a['xz'] is not None)
    scene.extend(np.asarray(o['corners_xz']) for o in objects)
    scene.extend(np.asarray(seg) for _,seg in segments)
    if camera:scene.append(np.asarray([camera['xz']]))
    samples = np.concatenate(scene)
    lo,hi = samples.min(0),samples.max(0)
    left,top,right,bottom = _RECT
    voxel = plane['voxel_size_m']
    scale = max((hi[0]-lo[0]+2*voxel)/(right-left-20),(hi[1]-lo[1]+2*voxel)/(bottom-top-20))
    mid = (hi+lo)/2
    extent = np.array([right-left,bottom-top])*scale/2
    x0,z0 = mid-extent
    x1,z1 = mid+extent
    limits = [float(t) for t in (x0,z0,x1,z1)]
    raster,counts,grid_hash = _geometry(points,states,voxel,limits)
    image = Image.new('RGB',(_SIZE,_SIZE),'white')
    image.paste(raster,(left,top))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    def xy(p):
        return (round(left+(p[0]-x0)/scale),round(bottom-(p[1]-z0)/scale))
    draw.rectangle(_RECT,outline='#617077')
    draw.text((14,5),'Historical map | estimated XZ (metres)',font=font,fill='#172831')
    draw.text((14,22),f"+X right, +Z up | slice y={plane['sampled_height_m']:.2f} m | boxes: all heights",font=font,fill='#263b43')
    for _,segment in segments:
        draw.line([xy(p) for p in segment],fill='#26495a',width=3)
    for o in objects:
        corners = o['corners_xz']
        for i,j in combinations(range(8),2):
            if (i^j) in (1,2,4):
                draw.line([xy(corners[i]),xy(corners[j])],fill='#985224',width=2)
        center = xy(np.mean(corners,axis=0))
        label = o['label']
        lx = min(max(left,center[0]+3),right-draw.textlength(label,font=font)-2)
        ly = min(max(top,center[1]+2),bottom-13)
        draw.text((lx,ly),label,font=font,fill='#78310f',stroke_width=1,stroke_fill='white')
    # Give coincident viewpoints separate labels in the legend, sharing the true point.
    labelled = {}
    for a in rows:
        if a['xz'] is not None:
            labelled.setdefault(xy(a['xz']),[]).append(str(a['anchor_index']))
    for (x,y),indices in labelled.items():
        draw.ellipse((x-4,y-4,x+4,y+4),fill='#375292',outline='white')
        draw.text((x+4,y-12),'A'+','.join(indices),font=font,fill='#162956',stroke_width=1,stroke_fill='white')
    if camera:
        x,y = xy(camera['xz'])
        draw.ellipse((x-5,y-5,x+5,y+5),fill='#1a2024',outline='white')
        if camera['forward_xz'] is not None:
            dx,dz = camera['forward_xz']
            tip = (x+round(17*dx), y-round(17*dz))
            draw.line([(x,y),tip],fill='#141719',width=3)
            draw.polygon([tip,(tip[0]-7*dx-4*dz,tip[1]+7*dz-4*dx),
                              (tip[0]-7*dx+4*dz,tip[1]+7*dz+4*dx)],fill='#141719')
    for i,label in enumerate(('unknown','free','surface','conflict')):
        x=14+i*88
        draw.rectangle((x,421,x+10,431),fill=tuple(_PALETTE[i]),outline='#617077')
        draw.text((x+14,420),label,font=font,fill='#172831')
    camera_label = ('unknown' if camera is None else ('heading unknown' if camera['forward_xz'] is None else 'known'))
    draw.text((14,438),'Dark line: traversed | brown box: selected object | camera: '+camera_label,
              font=font,fill='#172831')
    words = [f"A{a['anchor_index']} {a['room']} (s{a['step']})" for a in rows]
    lines = ['']
    for word in words:
        trial = (lines[-1]+'   '+word).strip()
        if draw.textlength(trial,font=font)>480 and lines[-1]:
            lines.append(word)
        else:lines[-1]=trial
    for j,line in enumerate(lines):
        draw.text((14,456+j*14),line,font=font,fill='#263b43')
    info.update(status='rendered', reason=None,height_slice=plane,world_bounds_xz=limits,
                metres_per_pixel=scale,plot_rect=list(_RECT),current_status='known' if camera else 'unknown',
                current_camera=camera,current_heading_status='known' if camera and camera['forward_xz'] is not None else 'unknown',
                anchors=rows,objects=objects,
                traversed_edges=len(segments),traversed_ids_sha256=digest(canonical(sorted(k for k,_ in segments))),
                slice_cells=dict(free=counts[1],surface=counts[2],conflict=counts[3]),
                slice_sha256=grid_hash,rgb_sha256=digest(image.tobytes()))
    reader._evo_bev_cache = (key,image.copy(),deepcopy(info))
    return image,info
