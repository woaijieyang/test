"""Pair exact keys without filtering out fallbacks. Supplied metrics are per-episode, 0–1."""
import argparse,json
from shared.identity import need

def summarize(rows, expected_keys=None):
    need(rows and len({q['task_key'] for q in rows})==len(rows),'Duplicate or empty episode set')
    if expected_keys is not None:
        need(len(expected_keys)==len(set(expected_keys)) and set(expected_keys)=={r['task_key'] for r in rows},'Missing/unexpected keys versus frozen roster')
    n=len(rows);out={};pairs=[]
    for r in rows:
        a,b=r['base'],r['candidate'];need(a['sr'] in (0,1) and b['sr'] in (0,1),'Missing/bad SR');pairs.append((a,b))
    for k in ('sr','spl','ndtw','ne','steps','calls','input_tokens','output_tokens'):
        if not all(k in a and k in b for a,b in pairs):continue
        aa=[a[k] for a,b in pairs];bb=[b[k] for a,b in pairs];total=k in ('steps','calls','input_tokens','output_tokens');div=1 if total else n;out[k]={'baseline':sum(aa)/div,'candidate':sum(bb)/div,'difference':(sum(bb)-sum(aa))/div,'aggregation':'total' if total else 'mean'}
    recovered=sum(a['sr']==0 and b['sr']==1 for a,b in pairs);lost=sum(a['sr']==1 and b['sr']==0 for a,b in pairs);common=[(a,b) for a,b in pairs if a['sr'] and b['sr']]
    return {'n':n,'recoveries':recovered,'regressions':lost,'sr_delta_pp':100*(recovered-lost)/n,'metrics':out,'common_success_n':len(common),'common_success_mean_path_delta_m':sum(b['path_length_m']-a['path_length_m'] for a,b in common)/len(common) if common and all('path_length_m' in a and 'path_length_m' in b for a,b in common) else None,'dispositions':{k:sum(r['disposition']==k for r in rows) for k in sorted({r['disposition'] for r in rows})}}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('jsonl');p.add_argument('--expected-keys',required=True,help='JSON array of frozen task keys');a=p.parse_args();print(json.dumps(summarize([json.loads(l) for l in open(a.jsonl,encoding='utf-8') if l.strip()],json.load(open(a.expected_keys,encoding='utf-8'))),indent=2))
