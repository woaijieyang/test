"""Pure paired summary. No causal claim, no exclusion of failed/fallback episodes."""
from __future__ import annotations
from contracts.common import require

def paired(rows: list[dict]) -> dict:
    require(bool(rows),'empty evaluation')
    ids=[x['task_key'] for x in rows];require(len(ids)==len(set(ids)),'duplicate task identities')
    for x in rows:require(x['baseline_sr'] in [0,1] and x['candidate_sr'] in [0,1],'binary SR required')
    base=sum(x['baseline_sr'] for x in rows);new=sum(x['candidate_sr'] for x in rows)
    gain=sum(x['baseline_sr']==0 and x['candidate_sr']==1 for x in rows)
    loss=sum(x['baseline_sr']==1 and x['candidate_sr']==0 for x in rows)
    return {'n':len(rows),'baseline_successes':base,'candidate_successes':new,'recoveries':gain,'regressions':loss,
            'net':gain-loss,'delta_sr_pp':100*(new-base)/len(rows),'harm_given_baseline_success':loss/base if base else None,
            'recovery_given_baseline_failure':gain/(len(rows)-base) if base<len(rows) else None,
            'fallback_count':sum(bool(x.get('fallback',False)) for x in rows),
            'scope':'Descriptive paired outcomes; not proof of semantic correctness, causal attribution or zero regression.'}

def paired_from_results(expected_keys: list[str], baseline: list[dict], candidate: list[dict]) -> dict:
    """Join actually measured navigation results; never silently drop missing rows.
    Each input row requires task_key and measured sr. A pipeline decision without
    a navigation result is NOT a success/failure measurement.
    """
    require(expected_keys and len(expected_keys)==len(set(expected_keys)),'Expected record keys must be explicit and unique')
    def index(rows):
        keys=[r['task_key'] for r in rows]
        require(len(keys)==len(set(keys)) and set(keys)==set(expected_keys),'Missing/extra/duplicate measured results; denominator cannot be silently reduced')
        for r in rows:
            require('sr' in r and r.get('navigation_evaluated',True) is not False,'Actual navigation SR missing; pipeline output is not an evaluation')
        return {r['task_key']:r for r in rows}
    b,c=index(baseline),index(candidate)
    return paired([{'task_key':k,'baseline_sr':b[k]['sr'],'candidate_sr':c[k]['sr'],'fallback':str(c[k].get('state','')).startswith('fallback_')} for k in expected_keys])
