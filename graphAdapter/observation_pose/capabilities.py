"""File identity and runtime measurement are independent capability levels."""
import importlib.util
import json
import os
import shutil
from pathlib import Path

def inspect(root):
    from poseAdapter.frontend_profile import verify_profile
    from poseAdapter.backend_profile import verify_profile as verify_backend
    result = dict(scope="deployment_files_only", measured_tracking="NOT_RUN",
                  bwrap=shutil.which("bwrap"), cpu_affinity=sorted(os.sched_getaffinity(0)),
                  cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
                  imports={name:importlib.util.find_spec(name).origin for name in ("poseAdapter","graphAdapter")})
    for name, call in [("frontend", lambda:verify_profile("rgbd_metric_precision_v4")),
                       ("backend", lambda:verify_backend("rgbd_icp_reference_v2"))]:
        try:
            result[name] = dict(status="VERIFIED_FILES", identity=call())
        except Exception as error:
            result[name] = dict(status="BLOCKED", error=repr(error))
    result["protected_runtime"] = json.loads(os.environ.get("CASE1_PROTECTION", "{}"))
    return result
