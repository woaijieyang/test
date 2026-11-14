"""Enforce protected assets and owned caches before executing runtime commands."""

import argparse, glob, json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0,"/data/zy/vln/case2/scripts")
from workspace import ROOT, owned
from setup_data_links import check_links
from landlock import restrict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mounted", action="store_true")
    p.add_argument("--candidate-code-root",type=Path)
    p.add_argument("--pose-broker", action="store_true")
    p.add_argument("--memory-broker",action="store_true")
    p.add_argument("--storage-run",type=Path)
    p.add_argument("--pose-package-parent", type=Path)
    p.add_argument("--results-write", action="store_true")
    p.add_argument("--prepare-configs", action="store_true")
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        raise SystemExit("Provide executable and arguments after --")
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-72:])
    check_links()
    if not a.mounted:
        probe = subprocess.run(
            ["unshare", "--user", "--map-root-user", "--mount", "true"], capture_output=True
        )
        if probe.returncode == 0:
            os.execvp(
                "unshare",
                [
                    "unshare",
                    "--user",
                    "--map-root-user",
                    "--mount",
                    "--propagation",
                    "private",
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--mounted",
                    *(["--pose-broker"] if a.pose_broker else []),
                    *(["--memory-broker"] if a.memory_broker else []),
                    *(["--candidate-code-root",str(a.candidate_code_root)] if a.candidate_code_root else []),
                    *(['--storage-run',str(a.storage_run)]if a.storage_run else []),
                    *(["--pose-package-parent",str(a.pose_package_parent)] if a.pose_package_parent else []),
                    *(["--results-write"] if a.results_write else []),
                    *(["--prepare-configs"] if a.prepare_configs else []),
                    "--",
                    *command,
                ],
            )
    if a.mounted:
        for source, target in [
            ("/data/zy/vln/data", ROOT / "data/.shared-ro"),
            ("/data/zy/vln/model/upstream", ROOT / "models/.shared-ro"),
        ]:
            if target.is_symlink() or target.resolve() != target:
                raise RuntimeError("Mount destination must be owned real directory")
            subprocess.run(["mount", "--bind", source, str(target)], check=True)
            subprocess.run(["mount", "-o", "remount,bind,ro", str(target)], check=True)
            if not os.statvfs(target).f_flag & os.ST_RDONLY:
                raise RuntimeError("Mount is not read-only")
    if a.candidate_code_root is not None:
        # Candidate-only extension: preserve all existing model/data mounts,
        # broker-before-confinement ordering and Landlock rules unchanged.
        # Refuse any overlay unless this launcher owns a private mount namespace.
        if not a.mounted:raise RuntimeError("Candidate code overlay requires the normal private mount namespace")
        import hashlib
        code=a.candidate_code_root.absolute()
        if code.resolve()!=code or not code.is_relative_to(ROOT/'outputs/graph_memory'):
            raise ValueError("Candidate code must be a real owned graph-memory directory")
        lock=json.loads((code/'SOURCE_LOCK.json').read_bytes())
        for rel,expected in lock.items():
            item=code/rel
            if not item.resolve().is_relative_to(code) or not item.is_file():
                raise ValueError("Candidate source lock escapes release")
            if hashlib.sha256(item.read_bytes()).hexdigest()!=expected:
                raise RuntimeError("Candidate source lock changed: "+rel)
        for name in ('graphAdapter','poseAdapter','SimulatorAdapter'):
            source=code/'src'/name;target=ROOT/'src'/name
            if source.resolve()!=source or target.resolve()!=target:
                raise ValueError("Source package overlay cannot follow symlinks")
            subprocess.run(['mount','--bind',str(source),str(target)],check=True)
            subprocess.run(['mount','-o','remount,bind,ro',str(target)],check=True)
            if not os.statvfs(target).f_flag & os.ST_RDONLY:
                raise RuntimeError("Candidate code overlay is not read-only")
        host_files=['vlnce_baselines/awarevln_trainer.py','vlnce_baselines/common/environments.py','evaluate_worker.py']
        if 'src/graphAdapter/runtime/host_integration/case1_runtime/observations.py' in lock:
            host_files.append('case1_runtime/observations.py')
        for rel in host_files:
            source=code/'src/graphAdapter/runtime/host_integration'/rel
            target=ROOT/'scripts'/rel if rel=='evaluate_worker.py' else ROOT/'src'/rel
            if not source.is_file() or source.resolve()!=source or target.resolve()!=target:
                raise ValueError('Host integration overlay must use declared real source files')
            subprocess.run(['mount','--bind',str(source),str(target)],check=True)
            subprocess.run(['mount','-o','remount,bind,ro',str(target)],check=True)
            if not os.statvfs(target).f_flag & os.ST_RDONLY:raise RuntimeError('Host overlay is not readonly')
    storage_root=None;process_scope=None
    if a.storage_run:
        sys.path.insert(0,str(ROOT/'src'))
        from graphAdapter.map_memory.storage.routing import load_run,create_process_scope,bind_process_scope
        from graphAdapter.map_memory.storage.lifecycle import process_identity
        storage_root,storage_identity=load_run(a.storage_run)
        import uuid
        process_scope=create_process_scope(storage_root,storage_root/'processes'/uuid.uuid4().hex,'host_runtime')
        bind_process_scope(storage_root,process_scope,process_identity(os.getpid()))
    writable = []
    for rel in ("runtime", ".cache", "outputs", "logs", "data/derived", "configs/local"):
        d = owned(ROOT / rel)
        d.mkdir(parents=True, exist_ok=True)
        writable.append(d)
    if a.results_write:
        directory = owned(ROOT / "results-show")
        directory.mkdir(parents=True, exist_ok=True)
        writable.append(directory)
    if a.prepare_configs:
        for relative in ("configs/locks", "configs/diagnostics"):
            directory = owned(ROOT / relative)
            directory.mkdir(parents=True, exist_ok=True)
            writable.append(directory)
    for d in (
        ".cache/tmp",
        ".cache/huggingface",
        ".cache/torch",
        ".cache/xdg",
        ".cache/matplotlib",
    ):
        (ROOT / d).mkdir(exist_ok=True)
    os.environ.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(ROOT / ".cache/tmp"),
            "HF_HOME": str(ROOT / ".cache/huggingface"),
            "HF_HUB_CACHE": str(ROOT / ".cache/huggingface/hub"),
            "HUGGINGFACE_HUB_CACHE": str(ROOT / ".cache/huggingface/hub"),
            "TRANSFORMERS_CACHE": str(ROOT / ".cache/huggingface/transformers"),
            "TORCH_HOME": str(ROOT / ".cache/torch"),
            "TORCH_EXTENSIONS_DIR": str(ROOT / ".cache/torch_extensions"),
            "TRITON_CACHE_DIR": str(ROOT / ".cache/triton"),
            "CUDA_CACHE_PATH": str(ROOT / ".cache/cuda"),
            "NUMBA_CACHE_DIR": str(ROOT / ".cache/numba"),
            "__GL_SHADER_DISK_CACHE_PATH": str(ROOT / ".cache/nvidia"),
            "XDG_CACHE_HOME": str(ROOT / ".cache/xdg"),
            "XDG_CONFIG_HOME": str(ROOT / ".cache/xdg-config"),
            "MPLCONFIGDIR": str(ROOT / ".cache/matplotlib"),
            "TOKENIZERS_PARALLELISM": "false",
            "TF_NUM_INTRAOP_THREADS": "1",
            "TF_NUM_INTEROP_THREADS": "1",
            "PYTHONPATH": str(ROOT / "src"),
            "PATH": str(ROOT / "runtime/awarevln/bin") + ":" + os.environ.get("PATH", ""),
            "AWAREVLN_ROOT": str(ROOT),
            "POSEADAPTER_WORKSPACE": str(ROOT),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    if a.pose_package_parent:
        package_parent=owned(a.pose_package_parent)
        package=package_parent/"poseAdapter"
        if (not package_parent.resolve().is_relative_to(ROOT/"runtime/pose") or
                not package.is_dir() or package.is_symlink() or
                not (package/"__init__.py").is_file()):
            raise ValueError("Installed pose package must be an owned runtime/pose directory")
        os.environ["PYTHONPATH"]=str(package_parent)+":"+os.environ["PYTHONPATH"]
    if process_scope is not None:
        cache_map={'TMPDIR':'tmp','HF_HOME':'cache/huggingface','HF_HUB_CACHE':'cache/huggingface/hub',
            'HUGGINGFACE_HUB_CACHE':'cache/huggingface/hub','TRANSFORMERS_CACHE':'cache/huggingface/transformers',
            'TORCH_HOME':'cache/torch','TORCH_EXTENSIONS_DIR':'cache/torch_extensions','TRITON_CACHE_DIR':'cache/triton',
            'CUDA_CACHE_PATH':'cache/cuda','NUMBA_CACHE_DIR':'cache/numba','__GL_SHADER_DISK_CACHE_PATH':'cache/nvidia',
            'XDG_CACHE_HOME':'cache/xdg','XDG_CONFIG_HOME':'cache/xdg-config','MPLCONFIGDIR':'cache/matplotlib'}
        for key,relative in cache_map.items():
            path=process_scope/relative;path.mkdir(parents=True,exist_ok=True);os.environ[key]=str(path)
        os.environ['CASE2_STORAGE_RUN']=str(a.storage_run.absolute())
    os.environ.pop("DISPLAY", None)
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("LD_PRELOAD", None)
    # Device I/O and POSIX shared memory; no additional ordinary filesystem roots.

    for pattern in (
        "/dev/nvidia*",
        "/dev/dri",
        "/dev/shm",
        "/dev/null",
        "/dev/zero",
        "/dev/urandom",
    ):
        writable.extend(Path(x) for x in glob.glob(pattern))
    if a.pose_broker:
        import uuid
        import time
        directory=owned(ROOT/"runtime/pose/brokers"/uuid.uuid4().hex)
        if storage_root is not None:create_process_scope(storage_root,directory,'pose_broker')
        else:directory.mkdir(parents=True,mode=0o700)
        log=(directory/"broker.log").open("x")
        broker=subprocess.Popen([str(ROOT/"runtime/pose/env/bin/python"),"-B",
            "-m","poseAdapter.launch_broker","--directory",str(directory),"--parent-pid",str(os.getpid())],
            env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        for _ in range(300):
            if (directory/"ready.json").exists():
                identity=json.loads((directory/"ready.json").read_text())
                actual_start=Path(f"/proc/{broker.pid}/stat").read_text().split()[21]
                if identity["pid"]!=broker.pid or identity["starttime"]!=actual_start:
                    raise RuntimeError("Pose broker process identity mismatch")
                break
            if broker.poll() is not None:
                raise RuntimeError("Pose broker startup failed: "+str(directory/"broker.log"))
            time.sleep(.1)
        else:
            broker.terminate()
            broker.wait(timeout=10)
            raise RuntimeError("Pose broker startup timed out")
        if storage_root is not None:bind_process_scope(storage_root,directory,process_identity(broker.pid))
        os.environ["POSEADAPTER_BROKER"]=str(directory/"broker.sock")
        os.environ["POSEADAPTER_BROKER_PID"]=str(broker.pid)
        log.close()
    if a.memory_broker:
        import uuid,time
        directory=owned(ROOT/"runtime/graph_memory/brokers"/uuid.uuid4().hex)
        if storage_root is not None:create_process_scope(storage_root,directory,'memory_broker')
        else:directory.mkdir(parents=True,mode=0o700)
        log=(directory/"broker.log").open("x")
        broker=subprocess.Popen(["/usr/bin/python3","-B",str(ROOT/"src/graphAdapter/map_memory/worker.py"),
            "broker","--directory",str(directory),"--parent-pid",str(os.getpid())],
            env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        for _ in range(300):
            if (directory/"ready.json").exists():
                identity=json.loads((directory/"ready.json").read_text())
                actual_start=Path(f"/proc/{broker.pid}/stat").read_text().split()[21]
                if identity["pid"]!=broker.pid or identity["starttime"]!=actual_start:
                    raise RuntimeError("Memory broker identity mismatch")
                break
            if broker.poll()is not None:raise RuntimeError("Memory broker startup failed")
            time.sleep(.1)
        else:raise RuntimeError("Memory broker startup deadline")
        if storage_root is not None:bind_process_scope(storage_root,directory,process_identity(broker.pid))
        os.environ["GRAPH_MEMORY_BROKER"]=str(directory/"broker.sock")
        os.environ["GRAPH_MEMORY_BROKER_PID"]=str(broker.pid)
    abi = restrict(writable)
    os.environ["CASE1_PROTECTION"] = json.dumps(
        {
            "landlock_abi": abi,
            "readonly_mount": a.mounted,
            "results_write": a.results_write,
            "prepare_configs": a.prepare_configs,
        }
    )
    os.chdir(ROOT)
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
