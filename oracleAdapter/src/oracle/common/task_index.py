"""Per-record frozen membership: workers need not reread a 37016-row index."""
import hashlib
import json


def leaf(record):
    return hashlib.sha256(b'\x00'+json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).digest()


def parent(left,right):return hashlib.sha256(b'\x01'+left+right).digest()


def merkle_index(records):
    if not records:raise ValueError('Empty task index')
    levels=[[leaf(r) for r in records]]
    while len(levels[-1])>1:
        old=levels[-1];levels.append([parent(old[i],old[min(i+1,len(old)-1)]) for i in range(0,len(old),2)])
    entries=[]
    for i,record in enumerate(records):
        position=i;proof=[]
        for level in levels[:-1]:
            proof.append(level[position^1 if position^1<len(level) else position].hex());position//=2
        entries.append({'index':i,'record':record,'proof':proof})
    return levels[-1][0].hex(),entries


def verify_entry(entry,root,count):
    i=entry['index'];size=count;depth=0
    while size>1:size=(size+1)//2;depth+=1
    if type(i) is not int or not 0<=i<count or len(entry['proof'])!=depth:raise ValueError('Invalid index membership shape')
    value=leaf(entry['record'])
    for sibling in entry['proof']:
        other=bytes.fromhex(sibling)
        if len(other)!=32:raise ValueError('Invalid sibling digest')
        value=parent(other,value) if i%2 else parent(value,other);i//=2
    if value.hex()!=root:raise ValueError('Task does not belong to frozen manifest')
    return entry['record']
