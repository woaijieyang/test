import copy,hashlib
from pathlib import Path
import pytest
import poseAdapter.interfaces.mapping.channel as channel
from poseAdapter.interfaces.mapping import mapping_contract_identity,require_mapping_contract


def test_loaded_public_mapping_identity_covers_its_validation_dependencies():
    value=mapping_contract_identity();root=Path(channel.__file__).resolve().parents[2]
    assert value['schema_version']==1 and len(value['files'])==4
    for name,sha in value['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha
    require_mapping_contract(value,copy.deepcopy(value))
    bad=copy.deepcopy(value);bad['files']['interfaces/mapping/channel.py']='0'*64
    with pytest.raises(RuntimeError,match='differs'):require_mapping_contract(value,bad)
    with pytest.raises(RuntimeError,match='differs'):require_mapping_contract(value,None)
    with pytest.raises(ValueError):require_mapping_contract(None,None)


def test_private_worker_mounts_full_source_pose_package(tmp_path,monkeypatch):
    from graphAdapter.map_memory import worker
    root=tmp_path/'project';root.mkdir()
    for rel in ('runtime/awarevln','runtime/graph_memory/perception','runtime/graph_memory/borrowed_base',
                'runtime/graph_memory/package_root','runtime/graph_memory/model-cache','src/poseAdapter',
                'src/graphAdapter','src/pose_interfaces','vendor_sources/EvoMemNav','models/graph001'):
        (root/rel).mkdir(parents=True,exist_ok=True)
    session=root/'runtime/graph_memory/sessions/test';session.mkdir(parents=True)
    source=root/'outputs/graph_memory/input/observation_pose';source.mkdir(parents=True)
    output=root/'outputs/graph_memory/output';output.mkdir()
    monkeypatch.setattr(worker,'ROOT',root)
    command=worker.isolated_command(session,source,output)
    triples=list(zip(command,command[1:],command[2:]))
    assert ('--ro-bind',str(root/'src/poseAdapter'),str(root/'src/poseAdapter')) in triples
    assert ('--ro-bind',str(root/'src/pose_interfaces'),str(root/'src/pose_interfaces')) in triples
    assert not any('SimulatorAdapter' in str(x) for x in command)
    assert not any('standalone-site' in str(x) for x in command)
    assert ('--setenv','OPENBLAS_NUM_THREADS','1') in triples
    assert ('--setenv','MKL_NUM_THREADS','1') in triples


@pytest.mark.parametrize('failure',['recv','descriptor_count','invalid_json','status','metadata','initialize'])
def test_partial_client_construction_closes_all_received_fds(tmp_path,monkeypatch,failure):
    import os,json,struct,socket
    from graphAdapter.map_memory import worker
    from graphAdapter.map_memory.storage import routing
    root=tmp_path/'project';root.mkdir();monkeypatch.setattr(worker,'ROOT',root)
    monkeypatch.setenv('GRAPH_MEMORY_BROKER','/unused-unit-broker')
    monkeypatch.setattr(routing,'from_environment',lambda:None)
    descriptors=[];owned_inodes={}
    if failure!='recv':
        for _ in range(2 if failure=='descriptor_count' else 1):
            a,b=os.pipe();os.close(b);descriptors.append(a);owned_inodes[a]=os.fstat(a).st_ino
    class FakeSocket:
        def __init__(self,descriptor=None):self.descriptor=descriptor;self.closed=False
        def settimeout(self,*a):pass
        def connect(self,*a):pass
        def send(self,*a):return 1
        def recvmsg(self,*a):
            if failure=='recv':raise OSError('injected receive')
            body=b'bad-json' if failure=='invalid_json' else json.dumps(dict(status='error' if failure=='status' else 'spawned',pid=123,starttime='1')).encode()
            return body,[(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack('i'*len(descriptors),*descriptors))],0,None
        def close(self):
            if not self.closed and self.descriptor is not None:os.close(self.descriptor)
            self.closed=True
    control=FakeSocket();opened=[control]
    def socket_factory(*a,**kw):
        if 'fileno' not in kw:return control
        channel=FakeSocket(kw['fileno']);opened.append(channel);return channel
    monkeypatch.setattr(worker.socket,'socket',socket_factory)
    original_write=Path.write_text
    def write(path,*a,**kw):
        if failure=='metadata' and path.name=='process.json':raise OSError('injected metadata')
        return original_write(path,*a,**kw)
    monkeypatch.setattr(Path,'write_text',write)
    def call(*a,**kw):raise RuntimeError('injected initialize')
    monkeypatch.setattr(worker.MemoryWorkerClient,'call',call)
    try:
        with pytest.raises((OSError,RuntimeError,ValueError)):
            worker.MemoryWorkerClient(root/'source',root/'output',{})
        assert all(s.closed for s in opened)
        for fd in descriptors:
            with pytest.raises(OSError):os.fstat(fd)
    finally:
        for fd in descriptors:
            try:
                if os.fstat(fd).st_ino==owned_inodes[fd]:os.close(fd)
            except OSError:pass
