"""Coverage-complete identity comparisons; this is not a geometry or motion validator."""
CLEAR='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC'
ALLOWED={CLEAR,'SOURCE_FAILURE_PRESERVED','ACTUAL_POSE_SOURCE_CONTACT','UNRESOLVED_CONTINUOUS_SOURCE_CONTACT','STEP_REALIZATION_EXISTS_PROTOCOL_REVIEW_REQUIRED','STATIC_BLOCKED_PRESERVED','SOURCE_CANDIDATE_BLOCKED_PRESERVED'}
def compare(expected_keys,baselines,candidate_rows):
 expected=list(expected_keys)
 if len(expected)!=len(set(expected)):raise ValueError('duplicate expected identity')
 wanted=set(expected);keys=[r['task_key'] for r in candidate_rows]
 if len(keys)!=len(set(keys)):raise ValueError('duplicate candidate identity')
 if set(keys)!=wanted:raise ValueError('candidate coverage differs from full denominator')
 if any(r['status'] not in ALLOWED for r in candidate_rows):raise ValueError('unrecognized or weaker proof status')
 passed={r['task_key'] for r in candidate_rows if r['status']==CLEAR};comparisons={}
 for label,old in baselines.items():
  old=set(old)
  if not old<=wanted:raise ValueError('baseline contains foreign identity')
  comparisons[label]={'baseline_passed':len(old),'preserved':len(old&passed),'recovered':sorted(passed-old),'regressed':sorted(old-passed),'nonregression':old<=passed}
 return {'denominator':len(wanted),'candidate_strict_passed':len(passed),'candidate_unresolved':sorted(wanted-passed),'comparisons':comparisons,'all_baselines_preserved':all(v['nonregression'] for v in comparisons.values()),'all_tasks_strict':passed==wanted,'limits':'Identity/status comparison only. Source binding and real independent motion/geometry evidence must be checked separately; this never grants publication.'}
