"""Hash existing official weights without copying or downloading them."""

import json, os
from workspace import ROOT, atomic_json, digest

if __name__ == "__main__":
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Protected runtime required")
    root = ROOT / "models/awarevln"
    records = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            records.append(
                {
                    "path": str(p.resolve()),
                    "relative": str(p.relative_to(root)),
                    "size": p.stat().st_size,
                    "sha256": digest(p),
                }
            )
    if not records or not any(x["relative"].endswith((".safetensors", ".bin")) for x in records):
        raise ValueError("Missing model weights")
    import hashlib

    source_path = ROOT / "configs/locks/model-source.json"
    source = json.loads(source_path.read_text())
    expected = {item["rfilename"].removeprefix("awarevln/"): item for item in source["files"]}
    if {r["relative"] for r in records} != set(expected):
        raise ValueError("Local model file set does not match the frozen official snapshot")
    for record in records:
        meta = expected[record["relative"]]
        if record["size"] != meta["size"]:
            raise ValueError("Official model file size mismatch")
        if "lfs" in meta:
            if record["sha256"] != meta["lfs"]["sha256"]:
                raise ValueError("Official weight LFS SHA mismatch: " + record["relative"])
        else:
            data = (root / record["relative"]).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob != meta["blobId"]:
                raise ValueError("Official model metadata Git blob mismatch: " + record["relative"])

    identity = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    atomic_json(
        "outputs/preflight/model.json",
        {
            "model": "AwareVLN official",
            "model_sha256": identity,
            "files": records,
            "official_repository": source["repository"],
            "official_revision": source["revision"],
            "source_metadata_sha256": digest(source_path),
            "source_verification": "All files matched official Git/LFS identities",
        },
    )
    print({"files": len(records), "model_sha256": identity})
