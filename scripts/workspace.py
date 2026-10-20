"""Workspace-owned paths; resolving a symlink never grants write permission."""

from pathlib import Path
import hashlib, json, os, tempfile

ROOT = Path(__file__).resolve().parents[1]


def owned(path, root=ROOT):
    root = Path(root).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    resolved = p.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("Output escapes workspace: " + str(p))
    for part in [p, *p.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Output traverses a symlink: " + str(part))
    if resolved.relative_to(root).parts[0] in ("backup", "upstream", "models"):
        raise ValueError("Read-only asset output: " + str(p))
    if any(part == ".shared-ro" for part in p.parts):
        raise ValueError("Shared view is not writable")
    return p


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, value):
    path = owned(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
