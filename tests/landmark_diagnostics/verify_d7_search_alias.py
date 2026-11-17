"""Fresh native replay of observed key aliases, with independent sweep traversal."""
from pathlib import Path
import ast
inspector_path = Path.cwd()/'tests/landmark_diagnostics/inspect_d7_search_alias.py'
prefix = inspector_path.read_text().split('rows = []\n', 1)[0]
exec(compile(prefix, str(inspector_path)+':setup-only', 'exec'), globals())
output = out/'independent-replay.json'
assert not output.exists()
initial_state = json.loads((out/'state.json').read_text())
assert initial_state['status'] == 'COMPLETE_DIAGNOSTIC'
assert digest(inspector_path) == initial_state['inspector_sha256']
reports = []
for selected in selection['tasks']:
    key = selected['task_key']
    observed_path = out/(key.replace(':','-')+'.json')
    observation = json.loads(observed_path.read_text())
    assert observation['inspector_sha256'] == digest(inspector_path)
    pairs = [p for p in observation['alias_pairs'] if p['discarded_only_legal_sequences']]
    if not pairs:
        continue
    old = json.loads(Path(selected['result_path']).read_text())
    assert digest(selected['result_path']) == selected['result_sha256']
    input_path = guard/'inputs'/(hashlib.sha256(key.encode()).hexdigest()[:24]+'.json')
    _args = SimpleNamespace(manifest=str(manifest), task_file=str(input_path))
    exec(compile(setup, str(worker_path)+':frozen-setup', 'exec'), globals())
    exec(compile(sim_setup, str(worker_path)+':frozen-sim-setup', 'exec'), globals())
    independent_helper = ROOT/'tests/landmark_diagnostics/audit_prb_step_interpretations.py'
    binding = json.loads((ROOT/'outputs/landmark-connectivity/pRb-original-trace-step-interpretation-v1/validation.json').read_text())
    assert digest(independent_helper) == binding['script_sha256']
    nodes = [n for n in ast.parse(independent_helper.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'sweep']
    assert len(nodes) == 1
    cache = {}; regions = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(independent_helper), 'exec'), globals())
    oracle = BodyOracle(sim, planner, observation['target'], radius=.25, max_nodes=5000)
    for pair in pairs:
        states = {}
        replay_error = 0.
        sequences = {}
        for label in ('retained','discarded'):
            initial = habitat_sim.AgentState()
            initial.position = task['targets'][0]
            initial.rotation = quat_from_coeffs(old['rotation'])
            sim.initialize_agent(0, initial)
            previous = sim.get_agent(0).get_state().position.copy()
            assert not sweep(previous, previous)
            for action in old['actions']+pair[label+'_path']:
                sim.step(action)
                current = sim.get_agent(0).get_state().position.copy()
                assert sim.pathfinder.is_navigable(current) and abs(float(current[1]-previous[1])) <= .5
                assert not sweep(current, current) and not sweep(previous, current)
                previous = current
            end = oracle.snapshot(sim)
            saved = pair[label]
            replay_error = max(replay_error, math.dist(end[0], saved['position']))
            q = packed(end)['rotation']
            assert abs(abs(float(np.dot(q, saved['rotation'])))-1) <= 1e-6
            assert list(oracle.key(end)) == pair['key']
            states[label] = end
            signature = {}
            for a1 in (1,2,3):
                first = oracle.transition(end,a1)
                second = oracle.transition(first,1) if first is not None else None
                signature[f'{a1}1'] = second is not None
                if second is not None:
                    assert not sweep(end[0],first[0]) and not sweep(first[0],second[0])
            sequences[label] = signature
        assert replay_error <= 1e-5
        difference = [s for s in sequences['discarded'] if sequences['discarded'][s] and not sequences['retained'][s]]
        assert difference == pair['discarded_only_legal_sequences']
        new_keys = {label:list(oracle.key(st))+[int(sequences[label][f'{a}1']) for a in (1,2,3)] for label,st in states.items()}
        assert new_keys['retained'] != new_keys['discarded']
        reports.append({'task_key':key,'observation_sha256':digest(observed_path),'old_key':pair['key'],
                        'separation_m':pair['separation_m'],'candidate_only_legal':difference,
                        'retained':pair['retained'],'discarded':pair['discarded'],
                        'prefix_action_counts':{l:len(old['actions'])+len(pair[l+'_path']) for l in states},
                        'replay_error':replay_error,'actual_and_swept_contact_count':0,
                        'refined_keys':new_keys})
    for s in sims:
        s.close()
assert len(reports) == sum(r['discarded_only_legal_pair_count'] for r in initial_state['rows'])
atomic_json(output, {'status':'PASS_ALIAS_COUNTEREXAMPLES_NOT_ROUTE_REPAIR','witnesses':reports,
                    'witness_count':len(reports),'selection_sha256':digest(selection_path),
                    'inspector_sha256':digest(inspector_path),'verifier_sha256':digest(__file__),
                    'independent_sweep_traversal_sha256':digest(independent_helper),
                    'limits':'State-key equivalence is refuted; full task recovery and budget efficacy remain unproven.'})
print('VERIFIED_ALIAS_PAIRS',len(reports),flush=True)

