"""Execute the actual host's pure activation guard without importing GPU models."""
import ast,builtins
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[4]
HOST=ROOT/'src/vlnce_baselines/awarevln_trainer.py'

def guard():
    tree=ast.parse(HOST.read_text())
    from case1_runtime.observations import resolve_graph_hook_switch
    return resolve_graph_hook_switch, tree

def test_explicit_off_ignores_stale_profile_and_brokers_without_io():
    resolve,_=guard()
    env=dict(CASE2_HOOK_MODE='off',CASE2_POSE_PROFILE='nonexistent-profile.json',POSEADAPTER_BROKER='stale',
             POSEADAPTER_BROKER_PID='0',GRAPH_MEMORY_BROKER='stale',GRAPH_MEMORY_BROKER_PID='0',MODEL_UNRELATED='keep')
    path,receipt=resolve(env)
    assert path is None and receipt['effective_mode']=='off'
    assert receipt['ignored_graph_environment_keys']
    assert env=={'CASE2_HOOK_MODE':'off','MODEL_UNRELATED':'keep'}

def test_default_is_off_and_on_requires_explicit_profile():
    resolve,_=guard()
    assert resolve({'CASE2_POSE_PROFILE':'stale'})[0] is None
    with pytest.raises(ValueError):resolve({'CASE2_HOOK_MODE':'on'})
    with pytest.raises(ValueError):resolve({'CASE2_HOOK_MODE':'invalid'})
    assert resolve({'CASE2_HOOK_MODE':'on','CASE2_POSE_PROFILE':'declared.json'})[0]=='declared.json'

def test_actual_host_off_block_does_not_import_adapter_or_read_profile():
    resolve,tree=guard()
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='_eval_checkpoint')
    start=next(i for i,n in enumerate(method.body)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='resolve_graph_hook_switch')
    # The host now decides activation before loading its checkpoint, then attaches
    # the hook after resetting the environment. Execute both real optional blocks.
    optional = [n for n in method.body if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == 'graph_profile_path']
    assert len(optional) == 2 and method.body[start + 1] is optional[0]
    init = method.body[method.body.index(optional[1]) - 1]
    assert isinstance(init, ast.Assign) and isinstance(init.targets[0], ast.Name)
    assert init.targets[0].id == 'graph_hook' and isinstance(init.value, ast.Constant) and init.value.value is None
    protected = {id(n) for block in optional for n in ast.walk(block)}
    for node in ast.walk(ast.Module(body=method.body[:method.body.index(optional[1])+1], type_ignores=[])):
        if isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in {'graphAdapter','SimulatorAdapter','poseAdapter'}:
            assert id(node) in protected
        if isinstance(node, ast.Import) and any(alias.name.split('.')[0] in {'graphAdapter','SimulatorAdapter','poseAdapter'} for alias in node.names):
            assert id(node) in protected
    statements = [method.body[start], optional[0], init, optional[1]]
    def forbidden_import(*args,**kwargs):raise AssertionError('Disabled path imported a module')
    namespace=dict(resolve_graph_hook_switch=resolve,os=SimpleNamespace(environ={'CASE2_HOOK_MODE':'off','CASE2_POSE_PROFILE':'missing'}),__builtins__=dict(vars(builtins),__import__=forbidden_import))
    exec(compile(ast.Module(body=statements,type_ignores=[]),str(HOST),'exec'),namespace)
    assert namespace['graph_hook'] is None
