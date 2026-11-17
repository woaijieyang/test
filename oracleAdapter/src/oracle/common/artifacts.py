"""Immutable owned artifacts and full package identities for research runs."""
import datetime
import hashlib
import importlib
import json
from pathlib import Path
import sys
import zipfile


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def content_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_json(path, value, immutable=True):
    path = Path(path)
    if immutable and path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def package_sources():
    root = Path(__file__).resolve().parents[1]
    return root, {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*"))
                  if p.is_file() and p.suffix in {".py", ".json"}
                  and p.relative_to(root).parts[:2] != ("configs", "local")}


def require_sources(sources):
    root, current = package_sources()
    if current != sources:
        raise RuntimeError("Frozen module source/configuration set changed")
    return root


def owned_output(case_root, value):
    root, path = Path(case_root).resolve(), Path(value).resolve()
    if not path.is_relative_to(root / "outputs/oracleAdapter"):
        raise ValueError("Research output escapes case1")
    return path


def freeze_sources(output, sources):
    root = require_sources(sources)
    with zipfile.ZipFile(Path(output) / "source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sources:
            archive.write(root / relative, relative)


def runtime_identity():
    """Hash actual imported native/Python components; no shared installation edits."""
    import habitat_sim
    from habitat_sim.utils import common  # Ensure quaternion conversion is loaded.
    import numpy
    prefixes = ("habitat_sim", "magnum", "quaternion")
    files = {}
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename and name.startswith(prefixes):
            path = Path(filename).resolve()
            if path.is_file():
                files[str(path)] = digest(path)
    return {"python": sys.executable, "python_version": sys.version,
            "habitat_sim": habitat_sim.__version__, "numpy": numpy.__version__,
            "native_and_wrapper_files": files,
            "limits": "Owned imported components are hashed; global OS/driver binaries are not a mathematical equivalence proof."}


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
