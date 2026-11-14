"""Structural guard for the newly introduced simulator pose boundary."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def attributes(path):
    tree=ast.parse(path.read_text())
    return tree,{node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}

def test_consumers_do_not_access_simulator_api():
    paths=list((ROOT/'graphAdapter/interfaces/pose').glob('*.py'))
    paths += [ROOT/'graphAdapter'/name for name in ['observation_packet.py','observation_pose/provider_contract.py','observation_pose/pose_bridge.py','observation_pose/aware_hook.py','map_memory/service.py','map_memory/worker.py']]
    paths += list((ROOT/'graphAdapter/map_memory/retrieval').glob('*.py'))
    denied={'get_agent_state','get_agent','get_rigid_state','get_sensor_observations','semantic_scene','pathfinder','geodesic_distance','get_semantic_annotations'}
    for path in paths:
        tree,accesses=attributes(path)
        assert not accesses&denied,(path,accesses&denied)
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):assert all(not a.name.startswith(('habitat_sim','SimulatorAdapter')) for a in node.names),path
            if isinstance(node,ast.ImportFrom):assert not (node.module or '').startswith(('habitat_sim','SimulatorAdapter')),path

def test_simulator_runtime_only_reads_position_rotation_and_never_steps():
    for name in ('pose.py','host_bridge.py'):
        path=ROOT/'SimulatorAdapter'/name
        tree,accesses=attributes(path)
        assert not accesses&{'step','set_state','get_sensor_observations','semantic_scene','pathfinder','geodesic_distance','sensor_states','get_semantic_annotations'},path
        fields={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='state'}
        assert fields==({'position','rotation'} if name=='pose.py' else set()),path
        if name=='host_bridge.py':
            assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='simulator_base_transform' for n in ast.walk(tree)),path
