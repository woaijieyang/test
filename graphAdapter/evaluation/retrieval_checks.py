"""Run stage 002 CPU contracts by suite and publish JUnit-linked evidence."""
import json,os,subprocess,xml.etree.ElementTree as ET
from pathlib import Path

SUITES={
 'queries':('test_query_adapter','test_query_encoder','test_feature_reader','test_candidates','test_evo_material','test_evo_context'),
 'bundles':('test_bundles_selector','test_native_slots','test_evo_events','test_semantic_topology','test_historical_approach','test_context_edge_witness','test_evo_global_map','test_evo_map_image'),
 'input_audit':('test_host_input_compiler','test_input_audit','test_additional_evidence','test_context_evidence','test_session','test_visual_attachment','test_dynamic_context','test_unavailable_wire','test_evo_host','test_evo_read_header','test_attachment_features','test_episode_rgb_reuse'),
 'behavior':('test_behavior',),
}

def run(root,suites,output):
    root=Path(root).resolve();out=Path(output).resolve()
    if root/'outputs/graph_memory' not in out.parents:raise ValueError('Output must be in the project graph-memory run directory')
    if not suites or len(set(suites))!=len(suites)or set(suites)-SUITES.keys():raise ValueError('Unknown, missing, or duplicate retrieval suite')
    out.mkdir(parents=True,exist_ok=False)
    paths=[str(root/'src/graphAdapter/map_memory/retrieval/tests'/(f+'.py')) for s in suites for f in SUITES[s]]
    if 'input_audit' in suites:
        paths.extend(str(root/'src/graphAdapter/tests'/name) for name in ('test_async_retrieval.py','test_retrieval_worker_contract.py'))
        paths.append(str(root/'src/graphAdapter/evaluation/tests/test_language_prefill.py'))
        paths.append(str(root/'src/graphAdapter/map_memory/tests/test_evo_reads.py'))
        paths.append(str(root/'src/graphAdapter/evaluation/tests/test_read_latency.py'))
    if 'behavior' in suites:
        paths.extend(str(root/'src/graphAdapter/evaluation/tests'/name) for name in
                     ('test_paired_prefix.py','test_reasoning_chain.py','test_cohort_members.py'))
    cmd=[str(root/'runtime/graph_memory/perception/bin/python'),'-B','-m','pytest','-q','-p','no:cacheprovider',
          '--junitxml',str(out/'junit.xml'),*paths]
    with (out/'pytest.log').open('x')as log:
        res=subprocess.run(cmd,cwd=root,env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1'),stdout=log,stderr=subprocess.STDOUT)
    rows=[]
    if (out/'junit.xml').exists():
        for test in ET.parse(out/'junit.xml').findall('.//testcase'):
            problem=next((child for child in test if child.tag in ('failure','error','skipped')),None)
            rows.append(dict(id=test.get('classname')+'.'+test.get('name'),
                expected='Assertions in named component test pass',actual='Assertions satisfied' if problem is None else problem.get('message'),
                status='PASS' if problem is None else problem.tag.upper()))
    result=dict(scope='CPU retrieval and behavior accounting contracts',suites=suites,exit_code=res.returncode,tests=rows,
                successful=bool(rows) and res.returncode==0 and all(v['status']=='PASS'for v in rows),navigation_tested=False)
    (out/'test_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(successful=result['successful'],tests=len(rows),scope=result['scope'],report=str(out/'test_results.json'))))
    return result['successful']

