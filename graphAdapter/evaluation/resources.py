"""Admission checks for the existing full-GPU model execution contract."""
import subprocess

def validate_snapshot(text,gpu_id,minimum_free_mib):
    rows={}
    for line in text.splitlines():
        index,uuid,total,used,free=[value.strip() for value in line.split(",")]
        rows[int(index)]=dict(index=int(index),uuid=uuid,total_mib=int(total),used_mib=int(used),free_mib=int(free))
    if gpu_id not in rows:
        raise RuntimeError("Requested physical GPU is absent")
    row=rows[gpu_id]
    if row["free_mib"]<minimum_free_mib or row["used_mib"]>1024:
        raise RuntimeError("GPU admission rejected: physical GPU "+str(gpu_id)+
            " has "+str(row["free_mib"])+" MiB free and "+str(row["used_mib"])+" MiB used")
    return row

def admit(gpu_id,minimum_free_mib):
    text=subprocess.check_output(["nvidia-smi","--query-gpu=index,uuid,memory.total,memory.used,memory.free",
                                  "--format=csv,noheader,nounits"],text=True)
    return validate_snapshot(text,gpu_id,minimum_free_mib)
