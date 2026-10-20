"""Observe frozen search without extra transition calls inside its search loop."""
import argparse, datetime, hashlib, heapq, itertools, json, math, os, resource, sys
from pathlib import Path
from types import SimpleNamespace

args = argparse.ArgumentParser()
args.add_argument('--cpu', type=int, required=True)
args = args.parse_args()
ROOT = Path.cwd()
sys.path[:0] = [str(ROOT/'tests/landmark_diagnostics'), str(ROOT/'scripts'), str(ROOT/'.cache/geometry-tools')]
from workspace import atomic_json, digest
from robust_oracle import RobustOracle
assert os.environ.get('CASE1_PROTECTION')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.sched_setaffinity(0, [args.cpu])
os.nice(15)
import numpy as np, trimesh, habitat_sim
from habitat_sim.utils.common import quat_from_coeffs

out = ROOT/'outputs/landmark-connectivity/D7-search-key-diagnostic-v1'
selection_path = out/'selection.json'
selection = json.loads(selection_path.read_text())
guard = ROOT/'outputs/landmark-connectivity/full-source-guard-D7-tiled-mixed-v1/guarded'
manifest = guard/'manifest.json'
assert digest(manifest) == selection['old_guard_manifest_sha256']
worker_path = ROOT/'tests/landmark_diagnostics/source_guard_tiled_candidate_worker.py'
worker_source = worker_path.read_text()
setup = worker_source[worker_source.index("helper=ROOT/"):worker_source.index("seed_info=m['native_plan_inputs']")]
setup = setup.replace('digest(__file__)', 'digest(worker_path)').replace("Path(__file__).with_name", "worker_path.with_name")
sim_setup = worker_source[worker_source.index('cfg=habitat_sim.SimulatorConfiguration()'):worker_source.index('raw_steps=')]

def packed(state):
    p, q = state
    return {'position': [float(v) for v in p], 'rotation': [float(v) for v in q.imag]+[float(q.real)]}

def unpacked(state):
    return np.array(state['position'], dtype=np.float32), quat_from_coeffs(state['rotation'])

rows = []
for selected in selection['tasks']:
    key = selected['task_key']
    result_out = out/(key.replace(':', '-')+'.json')
    assert not result_out.exists(), 'Immutable diagnostic already exists'
    old_path = Path(selected['result_path'])
    assert digest(old_path) == selected['result_sha256']
    old = json.loads(old_path.read_text())
    input_path = guard/'inputs'/(hashlib.sha256(key.encode()).hexdigest()[:24]+'.json')
    _args = SimpleNamespace(manifest=str(manifest), task_file=str(input_path))
    exec(compile(setup, str(worker_path)+':frozen-setup', 'exec'), globals())
    assert digest(m['candidate_tasks_path']) == m['candidate_tasks_sha256']
    assert next(t for t in json.loads(Path(m['candidate_tasks_path']).read_text())['tasks'] if t['task_key']==key) == task
    assert old['targets'] == task['targets'] and old['guard_manifest_sha256'] == digest(manifest)
    exec(compile(sim_setup, str(worker_path)+':frozen-sim-setup', 'exec'), globals())
    assert rotation == old['rotation']
    prefix_error = math.dist(sim.get_agent(0).get_state().position, old['positions'][0])
    for i, action in enumerate(old['actions']):
        previous = sim.get_agent(0).get_state().position.copy()
        sim.step(action)
        current = sim.get_agent(0).get_state().position.copy()
        prefix_error = max(prefix_error, math.dist(current, old['positions'][i+1]))
        assert safe(current) and continuous_clear(previous, current)
    assert prefix_error <= 1e-5
    target_index = len(old['boundaries'])+1
    oracle = BodyOracle(sim, planner, task['targets'][target_index], radius=.25, max_nodes=5000)
    start = oracle.snapshot(sim)
    counter = itertools.count()
    queue = [(oracle.distance(start[0])/.25, 0., next(counter), start, [])]
    first_key = oracle.key(start)
    best = {first_key: 0.}
    representatives = {first_key: (start, [])}
    expanded = 0
    duplicates = 0
    distinct_duplicates = 0
    alias_heap = []
    alias_serial = itertools.count()
    alias_seen = set()
    found = None
    started = datetime.datetime.now().astimezone().isoformat()
    while queue and expanded < oracle.max_nodes:
        _, cost, _, state, path = heapq.heappop(queue)
        state_key = oracle.key(state)
        if cost > best.get(state_key, math.inf)+1e-9:
            continue
        if oracle.distance(state[0]) <= oracle.radius:
            found = path
            break
        expanded += 1
        for action in (1, 2, 3):
            new = oracle.transition(state, action)
            if new is None:
                continue
            k = oracle.key(new)
            g = cost+(1. if action == 1 else .15)
            if g >= best.get(k, math.inf)-1e-9:
                duplicates += 1
                retained, retained_path = representatives[k]
                separation = math.dist(retained[0], new[0])
                if separation > 1e-5:
                    distinct_duplicates += 1
                    pair_key = (tuple(retained[0]), tuple(new[0]), k)
                    if pair_key not in alias_seen:
                        alias_seen.add(pair_key)
                        pair = {'key': list(k), 'retained': packed(retained), 'discarded': packed(new),
                                'retained_cost': best[k], 'discarded_cost': g,
                                'retained_path': retained_path, 'discarded_path': path+[action],
                                'separation_m': separation}
                        item = (separation, next(alias_serial), pair)
                        if len(alias_heap) < 64:
                            heapq.heappush(alias_heap, item)
                        elif separation > alias_heap[0][0]:
                            heapq.heapreplace(alias_heap, item)
                continue
            best[k] = g
            representatives[k] = (new, path+[action])
            heapq.heappush(queue, (g+oracle.distance(new[0])/.25, g, next(counter), new, path+[action]))
    search_stats = dict(stats)
    pairs = []
    # Search is now terminal. Additional transition probes cannot alter its queue/history.
    for _, _, pair in sorted(alias_heap, reverse=True):
        signatures = {}
        for label in ('retained', 'discarded'):
            st = unpacked(pair[label])
            assert list(oracle.key(st)) == pair['key']
            signature = {}
            for a1 in (1, 2, 3):
                for a2 in (1, 2, 3):
                    n1 = oracle.transition(st, a1)
                    n2 = oracle.transition(n1, a2) if n1 is not None else None
                    signature[f'{a1}{a2}'] = None if n2 is None else packed(n2)
            signatures[label] = signature
        pair['two_step_signatures'] = signatures
        pair['discarded_only_legal_sequences'] = [s for s in signatures['discarded'] if signatures['discarded'][s] is not None and signatures['retained'][s] is None]
        pair['retained_only_legal_sequences'] = [s for s in signatures['retained'] if signatures['retained'][s] is not None and signatures['discarded'][s] is None]
        pairs.append(pair)
    for s in sims:
        s.close()
    row = {'task_key': key, 'started': started, 'finished': datetime.datetime.now().astimezone().isoformat(),
           'status': 'SEARCH_OBSERVATION_ONLY', 'search_outcome': 'FOUND_PATH' if found is not None else 'BUDGET_EXHAUSTED' if queue else 'FRONTIER_EXHAUSTED',
           'expanded': expanded, 'queue_remaining': len(queue), 'found_actions': found,
           'duplicates': duplicates, 'distinct_position_duplicates': distinct_duplicates,
           'recording_policy': 'largest position separation, at most64; no extra transition calls during search',
           'alias_pairs': pairs, 'discarded_only_legal_pair_count': sum(bool(p['discarded_only_legal_sequences']) for p in pairs),
           'prefix_replay_error': prefix_error, 'target_index': target_index, 'target': task['targets'][target_index],
           'start': packed(start), 'search_stats': search_stats, 'selection_sha256': digest(selection_path),
           'old_result_path': str(old_path), 'old_result_sha256': digest(old_path), 'guard_manifest_sha256': digest(manifest),
           'inspector_sha256': digest(__file__), 'frozen_worker_sha256': digest(worker_path),
           'setup_adaptation': 'Only worker file identity expressions refer to original worker_path; algorithm and predicates unchanged',
           'max_nodes': 5000, 'limits': 'A key alias witness is not a repaired route or physical unreachability proof.'}
    atomic_json(result_out, row)
    rows.append({k: row[k] for k in ['task_key', 'search_outcome', 'expanded', 'discarded_only_legal_pair_count', 'prefix_replay_error']})
    atomic_json(out/'state.json', {'status':'RUNNING', 'completed':len(rows), 'rows':rows})
    print(rows[-1], flush=True)
atomic_json(out/'state.json', {'status':'COMPLETE_DIAGNOSTIC', 'completed':len(rows), 'rows':rows, 'inspector_sha256':digest(__file__)})

