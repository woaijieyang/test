"""Paper A source/data readiness only; does not simulate or change protocol B."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from oracle.common.offline_audit import identity
from oracle.common.artifacts import content_digest,write_json


def inspect(rows,config):
    counts=defaultdict(Counter);long_segments=[];task_keys=set()
    for raw in rows:
        split=raw['split'];key=split+':'+str(raw['instruction_id'])
        if key in task_keys:raise ValueError('Duplicate source task')
        task_keys.add(key);subpaths=raw['sub_paths'];headings=raw['headings']
        if len(headings)!=len(subpaths):raise ValueError('Source subpath headings differ in cardinality')
        c=counts[split];c['complete_tasks']+=1;c['subpaths']+=len(subpaths)
        c['task_heading_differs_from_first_subheading']+=raw['heading']!=headings[0]
        for i,path in enumerate(subpaths):
            if not path:raise ValueError('Empty source subpath')
            edges=len(path)-1;c['source_edges']+=edges
            c['maximum_source_subpath_edges']=max(c['maximum_source_subpath_edges'],edges)
            c['same_source_start_end_subpaths']+=path[0]==path[-1]
            if edges>config['maximum_subtrajectory_steps']:
                c['subpaths_longer_than_paper_action_budget']+=1
                long_segments.append(dict(task_key=key,subpath_index=i,path=path,source_edges=edges,
                    result='NOT_A_FAILURE_VERDICT',reason='Policy budget and success-region semantics differ from exact source-path length'))
    result={}
    for split,c in sorted(counts.items()):
        result[split]={**dict(c),
            'complete_task_delta_vs_paper':c['complete_tasks']-config['reported_complete_tasks'][split],
            'subinstruction_delta_vs_paper':c['subpaths']-config['reported_subinstructions'][split]}
    return result,long_segments


def audit(case_root,output):
    startup=identity();root=Path(case_root).resolve();output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(root/'outputs/oracleAdapter'):
        raise ValueError('Fresh owned output required')
    config_path=Path(__file__).parents[2]/'configs/protocols/landmark_paper_a_evidence.json'
    config=json.loads(config_path.read_bytes())
    if config['execution_adopted']:raise ValueError('This audit does not authorize original-protocol execution')
    source_path=root/'outputs/oracleAdapter/reference-cache/graph-audit-inputs/raw-landmark-paths.json.gz'
    source=json.loads(gzip.decompress(source_path.read_bytes()))
    counts,segments=inspect(source['records'],config)
    if sum(r['complete_tasks'] for r in counts.values())!=33954:raise ValueError('Source denominator changed')
    summary=dict(status='PAPER_A_READINESS_AUDITED_EXECUTION_NOT_REPRODUCED',startup=startup,
        counts=counts,total_subpaths=sum(r['subpaths'] for r in counts.values()),
        source_long_segment_records=len(segments),native_actions=0,
        source_files=source['sources'],source_projection_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        protocol_evidence=config,protocol_evidence_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        current_b_status='Independent frozen continuous run; no resets or action-budget/threshold replacement',
        conclusion='Report original graph/source structure and remaining protocol gaps; do not claim SA/SSA/LN or paper A reproduction')
    output.mkdir(parents=True);write_json(output/'long-source-subpaths.json',segments)
    summary['long_subpaths_sha256']=hashlib.sha256((output/'long-source-subpaths.json').read_bytes()).hexdigest()
    write_json(output/'validation.json',summary)
    return summary
