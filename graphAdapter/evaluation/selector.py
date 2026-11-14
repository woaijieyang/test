"""Sealed order with locked full annotation identity;no result partitions are read."""
from pathlib import Path
from .registry_binding import sha,load

def canonical_scene(value):
    return "/".join(Path(value).parts[-3:])

def full_member(dataset,row):
    return (dataset,canonical_scene(row["scene_id"]),str(row["episode_id"]),
            str(row["instruction"].get("instruction_id","-")))

def selected_rows(registry,dataset,partition,annotations,limit=None,*,start_offset=0,selection_manifest=None,selection_sha256=None):
    if type(start_offset)is not int or start_offset<0:raise ValueError("Nonnegative sealed offset required")
    if limit is not None and(type(limit)is not int or limit<=0):raise ValueError("Positive integer sealed limit required")
    registry=Path(registry);seal=load(registry/"seal.json");entry=seal["manifests"][dataset][partition]
    member_file=registry/entry["file"]
    if sha(member_file)!=entry["sha256"]:raise ValueError("Sealed member file changed")
    members=load(member_file)["identities"]
    selected=members[start_offset:]if limit is None else members[start_offset:start_offset+limit]
    if start_offset>len(members)or(limit is not None and len(selected)!=limit):raise ValueError("Range exceeds sealed members")
    positions=list(range(start_offset,start_offset+len(selected)));sample=None
    if selection_manifest is not None:
        manifest=Path(selection_manifest)
        if sha(manifest)!=selection_sha256:raise ValueError("Random selection manifest checksum changed")
        sample=load(manifest)
        if (partition!="A"or start_offset!=0 or limit!=16 or sample.get("stage")!="001"
            or sample.get("partition")!="A"or sample.get("total")!=32
            or sample.get("status")!="FROZEN_BEFORE_RANDOM32_EXECUTION"):
            raise ValueError("Only presealed stage001 random32 is supported")
        if (Path(sample["original_registry"]).resolve()!=registry.resolve()
            or sample["original_registry_sha256"]!=sha(registry/"seal.json")):
            raise ValueError("Random selection original registry mismatch")
        entries=sample["selected"][dataset]
        positions=[entry["original_sealed_index"]for entry in entries]
        if (len(entries)!=16 or[entry["sample_index"]for entry in entries]!=list(range(16))
            or any(type(i)is not int or not 0<=i<len(members)for i in positions)
            or positions!=sorted(set(positions))):
            raise ValueError("Random selection indices/order/coverage invalid")
        selected=[members[i]for i in positions]
        if any(entry["registered_identity"]!=member for entry,member in zip(entries,selected)):
            raise ValueError("Random selection differs from original sealed member")
    elif selection_sha256 is not None:raise ValueError("Selection checksum without manifest")
    rows=annotations["episodes"]
    if dataset=="rxr_us":
        rows=[r for r in rows if r["instruction"]["language"]=="en-US"]
    by_id={};by_full={}
    for row in rows:
        full=full_member(dataset,row)
        if full in by_full:raise ValueError("Duplicate full annotation identity")
        by_full[full]=row;by_id.setdefault(str(row["episode_id"]),[]).append(row)
    result=[];seen=set()
    for local_index,registered in enumerate(selected):
        if not isinstance(registered,list):raise ValueError("Sealed identity must be a list")
        if len(registered)==1:
            choices=by_id.get(str(registered[0]),[])
            if len(choices)!=1:raise ValueError("Missing/ambiguous display ID;full identity required")
            row=choices[0]
        elif len(registered)==4:
            key=(str(registered[0]),canonical_scene(registered[1]),str(registered[2]),str(registered[3]))
            if key[0]!=dataset or key not in by_full:raise ValueError("Missing full sealed member")
            row=by_full[key]
        elif len(registered)==6:
            # Standard dataset/split/language/scene/episode/instruction identity.
            if str(registered[0])!=dataset or registered[1]!="val_unseen":raise ValueError("Domain/split binding mismatch")
            language="en-US"if dataset=="rxr_us"else"en"
            if registered[2]!=language:raise ValueError("Language binding mismatch")
            key=(dataset,canonical_scene(registered[3]),str(registered[4]),str(registered[5]))
            if key not in by_full:raise ValueError("Missing complete sealed member")
            row=by_full[key]
        else:raise ValueError("Unsupported sealed identity format")
        full=full_member(dataset,row)
        if full in seen:raise ValueError("Duplicate selected identity")
        seen.add(full)
        if sample is not None and list(full)!=sample["selected"][dataset][local_index]["identity"]:
            raise ValueError("Random selection full annotation identity mismatch")
        result.append(dict(identity=full,registered_identity=registered,row=row,
            sealed_index=positions[local_index],original_sealed_index=positions[local_index],selection_index=local_index))
    return result

def shard(rows,worker_index,worker_count):
    if type(worker_index)is not int or type(worker_count)is not int or not 0<=worker_index<worker_count:
        raise ValueError("Invalid worker assignment")
    return rows[worker_index::worker_count]


def validate_registered_selection(rows,dataset,manifest_path,expected_sha256):
    """Bind collection/report rows back to the predeclared random sample."""
    path=Path(manifest_path)
    if sha(path)!=expected_sha256:raise ValueError("Random selection manifest checksum changed")
    sample=load(path)["selected"][dataset]
    if len(rows)!=len(sample):raise ValueError("Random selected coverage mismatch")
    for index,(actual,expected)in enumerate(zip(rows,sample)):
        if (list(actual["identity"])!=expected["identity"]
            or actual["registered_identity"]!=expected["registered_identity"]
            or actual["sealed_index"]!=expected["original_sealed_index"]
            or actual.get("original_sealed_index")!=expected["original_sealed_index"]
            or actual.get("selection_index")!=index):
            raise ValueError("Registered random selection differs from frozen manifest")
