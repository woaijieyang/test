"""Actual import provenance, not version labels or directory names."""
import hashlib
import importlib
from pathlib import Path
import sys


def bind(module_name, package_root, expected_sha256=None):
    root = Path(package_root).resolve()
    module = importlib.import_module(module_name)
    path = Path(module.__file__).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError(f"Import escaped active implementation: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise RuntimeError("Actual imported module hash differs from frozen identity")
    return {"module": module_name, "actual_path": str(path), "sha256": digest,
            "python": sys.executable}


def bind_callable(function, expected_implementation, package_root):
    actual = function.__module__ + ":" + function.__name__
    if actual != expected_implementation:
        raise RuntimeError(f"Configured/actual implementation mismatch: {expected_implementation} != {actual}")
    return {"configured": expected_implementation, "actual": actual,
            **bind(function.__module__, package_root)}
