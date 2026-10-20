"""Apply documented upstream replacements solely to the independent environment."""

import shutil, site, sys
from pathlib import Path
from workspace import ROOT, atomic_json, digest


def main():
    prefix = Path(sys.prefix).resolve()
    if prefix != ROOT / "runtime/awarevln":
        raise RuntimeError("Wrong Python environment")
    site_dir = Path(site.getsitepackages()[0]).resolve()
    if prefix not in site_dir.parents:
        raise RuntimeError("Site-packages escapes independent environment")
    records = []
    for source_name, target_name in [
        ("transformers_replace", "transformers"),
        ("deepspeed_replace", "deepspeed"),
    ]:
        source = ROOT / "src/llava/train" / source_name
        if not source.is_dir():
            raise RuntimeError("Missing official replacement tree")
        for p in source.rglob("*"):
            if not p.is_file() or p.suffix == ".pyc":
                continue
            target = site_dir / target_name / p.relative_to(source)
            before = digest(target) if target.exists() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            records.append(
                {
                    "source": str(p.relative_to(ROOT)),
                    "target": str(target.relative_to(ROOT)),
                    "before_sha256": before,
                    "after_sha256": digest(target),
                }
            )
    for target in (site_dir/'habitat_sim/utils/common.py', ROOT/'upstream/habitat-lab/habitat/tasks/nav/nav.py'):
        before=digest(target)
        text=target.read_text()
        updated=text.replace('np.float)', 'float)').replace('dtype=np.float)', 'dtype=float)')
        if text!=updated:
            target.write_text(updated)
        records.append({'target':str(target.relative_to(ROOT)), 'before_sha256':before,'after_sha256':digest(target),'reason':'NumPy removed np.float alias; builtin float is identical old alias'})
    atomic_json(ROOT / "outputs/setup/official-replacements.json", records)


if __name__ == "__main__":
    main()
