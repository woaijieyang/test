"""Original task paths versus both graphs; topology evidence is not motion proof."""
from collections import Counter, deque
import gzip
import hashlib
import json
from pathlib import Path
import zipfile
from .graph_lineage import graph_index
from oracle.common.offline_audit import identity


def edges_for_published(graph):
    pairs=set()
    for edge in graph['edges'].values():
        a,b=edge['nodes']
        if a not in graph['nodes'] or b not in graph['nodes']:
            raise ValueError('Published edge endpoint absent')
        pairs.update(((a,b),(b,a)))
    return pairs


def classify_path(path, nodes, pairs):
    missing=[dict(occurrence=i,viewpoint=n) for i,n in enumerate(path) if n not in nodes]
    absent=[dict(start_occurrence=i,end_occurrence=i+1,nodes=[a,b])
            for i,(a,b) in enumerate(zip(path,path[1:]))
            if a in nodes and b in nodes and a!=b and (a,b) not in pairs]
    return dict(status='MISSING_IDENTITY' if missing else 'MISSING_ADJACENCY' if absent else 'GRAPH_PATH_EXISTS',
                missing_nodes=missing,missing_edges=absent,
                repeated_consecutive_occurrences=sum(a==b for a,b in zip(path,path[1:])))


def hop_path(start,goal,nodes,pairs):
    if start not in nodes or goal not in nodes:return None
    neighbors={n:[] for n in nodes}
    for a,b in sorted(pairs):neighbors[a].append(b)
    queue=deque([start]);parent={start:None}
    while queue:
        cur=queue.popleft()
        if cur==goal:
            path=[]
            while cur is not None:path.append(cur);cur=parent[cur]
            return path[::-1]
        for other in neighbors[cur]:
            if other not in parent:parent[other]=cur;queue.append(other)
    return None


def audit(case_root,output):
    startup=identity()
    root=Path(case_root).resolve();output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(root/'outputs/oracleAdapter'):
        raise ValueError('New case-owned evidence directory required')
    base=root/'outputs/oracleAdapter/reference-cache'
    config_path=Path(__file__).parents[2]/'configs/experiments/graph_lineage.json'
    config=json.loads(config_path.read_bytes())
    receipt_path=root/config['fetch_receipt'];receipt=json.loads(receipt_path.read_bytes())
    archive_path=root/config['published_archive']
    if hashlib.sha256(archive_path.read_bytes()).hexdigest()!=config['published_archive_sha256']:
        raise ValueError('Published graph identity changed')
    if receipt['commit']!=config['original_commit']:raise ValueError('Original commit differs')
    original={};published={};source_hashes={}
    with zipfile.ZipFile(archive_path) as z:
        for rec in receipt['records']:
            p=root/config['original_cache']/rec['file'];raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=rec['sha256']:raise ValueError('Original graph identity changed')
            sc=rec['scene'];idx=graph_index(json.loads(raw))
            nodes={n for n,r in idx.items() if r['included']}
            pairs={(n,other) for n,r in idx.items() if n in nodes for other in r['included_neighbors']}
            original[sc]=(nodes,pairs)
            g=json.loads(z.read('habitat_mp3d_connectivity_graphs/'+sc+'.json'))
            published[sc]=(set(g['nodes']),edges_for_published(g));source_hashes[sc]=rec['sha256']
    raw_path=base/'graph-audit-inputs/raw-landmark-paths.json.gz'
    raw=json.loads(gzip.decompress(raw_path.read_bytes()));rows=raw['records']
    if len(rows)!=33954:raise ValueError('Landmark denominator changed')
    known=config['known_edge'];known_pair=set(known['nodes']);required=set();keys=set();records=[];edge_tasks=[]
    for row in rows:
        key=row['split']+':'+str(row['instruction_id'])
        if key in keys:raise ValueError('Duplicate task')
        keys.add(key);sc=row['scan'];path=row['path'];required.update((sc,n) for n in path)
        if sc not in original:raise ValueError('Scene missing')
        orig=classify_path(path,*original[sc]);pub=classify_path(path,*published[sc])
        rec=dict(task_key=key,scene=sc,path_id=row['path_id'],language=row['language'],original=orig,published=pub,
                 source_occurrences=len(path),subpaths=len(row['sub_paths']))
        records.append(rec)
        if sc==known['scene']:
            occurrences=[i for i,(a,b) in enumerate(zip(path,path[1:])) if {a,b}==known_pair]
            edge_tasks.append(dict(task_key=key,path=path,known_edge_occurrences=occurrences,
                contains_both_endpoints=known_pair.issubset(path)))
    missing=sorted((sc,n) for sc,n in required if n not in published[sc][0])
    previous=json.loads((root/config['missing_ledger']).read_bytes())
    old={(r['scene'],r['source_viewpoint_id']) for r in previous}
    if set(missing)!=old:raise ValueError('Raw source required IDs contradict old 461 ledger')
    sc=known['scene'];a,b=known['nodes'];on,oe=original[sc];pn,pe=published[sc]
    all_changes=[]
    for scene,(nodes,pairs) in original.items():
        pnodes,ppairs=published[scene]
        comparable={(a,b) for a,b in pairs if a in pnodes and b in pnodes and a!=b}
        published_same_ids={(a,b) for a,b in ppairs if a in nodes and b in nodes and a!=b}
        all_changes.append(dict(scene=scene,original_nodes=len(nodes),published_nodes=len(pnodes),
            published_only_ids=sorted(pnodes-nodes),original_only_ids=sorted(nodes-pnodes),
            removed_edges_among_retained_ids=[list(e) for e in sorted(comparable-published_same_ids) if e[0]<e[1]],
            added_edges_among_original_ids=[list(e) for e in sorted(published_same_ids-comparable) if e[0]<e[1]]))
    edge=dict(scene=sc,nodes=[a,b],original_direct=(a,b) in oe,published_direct=(a,b) in pe,
        original_minimum_hop_path=hop_path(a,b,on,oe),source_scene_tasks=len(edge_tasks),
        source_tasks_using_direct_edge=sum(bool(r['known_edge_occurrences']) for r in edge_tasks),
        source_tasks_containing_both=sum(r['contains_both_endpoints'] for r in edge_tasks),
        interpretation='Hop path is a source graph relation, not a replacement continuous route or a physical certificate')
    summary=dict(status='RAW_PATH_GRAPH_AUDIT_COMPLETE_NOT_PAPER_A_OR_CONTINUOUS_MOTION_ACCEPTANCE',startup=startup,
        records=len(records),required_viewpoints=len(required),missing_published_viewpoints=len(missing),
        original_counts=dict(Counter(r['original']['status'] for r in records)),
        published_counts=dict(Counter(r['published']['status'] for r in records)),known_edge=edge,
        raw_sources=raw['sources'],raw_projection_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        graph_sources_sha256=source_hashes,implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        graph_helper_sha256=hashlib.sha256(Path(__file__).with_name('graph_lineage.py').read_bytes()).hexdigest(),
        limits=['No FOV, headings, 10-step allowance or reinitialization simulation: not paper A evaluation.',
                'Undirected published topology does not prove native body clearance or motion.',
                'Repeated occurrences retained; graph shortcuts not substituted into any task.',
                'No active full run input, code, mapping or gate changed.'])
    output.mkdir(parents=True)
    for name,data in [('all33954.json',records),('known-edge.json',edge),('known-scene-tasks.json',edge_tasks),('graph-differences.json',all_changes)]:
        (output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    summary['outputs_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.json')}
    (output/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary
