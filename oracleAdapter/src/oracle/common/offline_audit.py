"""Startup identity for read-only source audits, with no navigation privileges."""
import datetime
import hashlib
import os
from pathlib import Path
import sys


def identity():
    root=Path(__file__).resolve().parents[1]
    modules={}
    for name,module in tuple(sys.modules.items()):
        value=getattr(module,'__file__',None)
        if not value or not (name=='oracle' or name.startswith('oracle.')):continue
        path=Path(value).resolve()
        if not path.is_relative_to(root):raise ValueError('Oracle import escapes unique active module')
        modules[name]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    entry=root.parents[1]/'run.py'
    return dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),
        python=sys.executable,python_version=sys.version,actual_entry=str(entry),
        entry_sha256=hashlib.sha256(entry.read_bytes()).hexdigest(),modules=modules,
        method_category='read_only_source_identity_and_topology_audit',
        task_contract='preserve IDs and ordered occurrences; do not produce motion or modify targets',
        privileged_information=['original_graph','published_adapted_graph','annotation_identity_and_paths'],
        native_actions=0,gpu_devices=[],processes=1,
        environment_limit='Host CPU JSON audit only; not a Habitat environment or physics acceptance')
