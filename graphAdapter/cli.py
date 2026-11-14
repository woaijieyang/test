"""Stage-scoped command entry point. Unsupported stages fail explicitly."""
import argparse
import json
import os
from pathlib import Path
import sys

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    check=sub.add_parser("check")
    check.add_argument("--bindings",required=True)
    check.add_argument("--feature",choices=["observation_pose","map_memory","retrieval"],required=True)
    check.add_argument("--suite",required=True)
    check.add_argument("--out",required=True)
    evaluate=sub.add_parser("eval")
    for name in ("bindings","profile","registry","partition","datasets","out"):
        evaluate.add_argument("--"+name,required=True)
    evaluate.add_argument("--limit-per-dataset",type=int)
    evaluate.add_argument("--selection-manifest")
    evaluate.add_argument("--cohort-plan",help="Explicit registered member plan in active storage run")
    evaluate.add_argument("--execution-segment")
    evaluate.add_argument("--preflight-only",action="store_true")
    evaluate.add_argument("--start-offset",type=int,default=0)
    evaluate.add_argument("--hook-mode",choices=["on","off"],default="on")
    evaluate.add_argument("--attempt-id",default="attempt0")
    evaluate.add_argument("--worker-index",type=int,default=0)
    evaluate.add_argument("--worker-count",type=int,default=1)
    inspect=sub.add_parser("inspect")
    inspect.add_argument("--bindings",required=True);inspect.add_argument("--episode",required=True)
    inspect.add_argument("--revision",default="CURRENT")
    inspect.add_argument("--verify-hashes",action="store_true");inspect.add_argument("--verify-references",action="store_true")
    render=sub.add_parser("render")
    for name in ("bindings","episode","out"):render.add_argument("--"+name,required=True)
    render.add_argument("--revision",default="CURRENT");render.add_argument("--height-slice",default="auto")
    report=sub.add_parser("report")
    report.add_argument("--run",required=True);report.add_argument("--control",required=True)
    report.add_argument("--paired",action="store_true");report.add_argument("--out")
    report.add_argument("--include-input-audit",action="store_true")
    report.add_argument("--include-behavior",action="store_true")
    retain=sub.add_parser("retain-episode")
    for name in ("run","plan-sha256","key","side","attempt","request"):
        retain.add_argument("--"+name,required=True)
    paired_retained=sub.add_parser("pair-retained")
    for name in ("run","plan-sha256","key","control-attempt","shadow-attempt"):
        paired_retained.add_argument("--"+name,required=True)
    retained_report=sub.add_parser('report-retained')
    retained_report.add_argument('--root',required=True);retained_report.add_argument('--out',required=True)
    route_prepare=sub.add_parser('prepare-storage-run')
    for name in('root','plan','profile'):route_prepare.add_argument('--'+name,required=True)
    route_release=sub.add_parser('release-run-processes');route_release.add_argument('--root',required=True)
    args=parser.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        parser.error("Use scripts/with_runtime.sh")
    if args.command=='prepare-storage-run':
        from graphAdapter.map_memory.storage.routing import prepare_production_run
        result=prepare_production_run(args.root,json.loads(Path(args.plan).read_bytes()),args.profile)
        print(json.dumps(result,indent=2));return 0
    if args.command=='release-run-processes':
        from graphAdapter.map_memory.storage.routing import release_process_scopes
        result=release_process_scopes(args.root);print(json.dumps(result,indent=2));return 0 if not result['pending']else 1
    if args.command=='report-retained':
        from graphAdapter.evaluation.retained import report_retained
        result=report_retained(args.root,args.out)
        print(json.dumps(result,indent=2));return 0 if result['status']=='PASS_RETAINED_NATIVE_AUDIT'else 1
    if args.command in ("retain-episode","pair-retained"):
        from graphAdapter.map_memory.storage.lifecycle import EpisodeLifecycle,audit_pair
        if args.command=="retain-episode":
            from graphAdapter.evaluation.runner import finalize_retained_episode
            episode=EpisodeLifecycle(args.run,args.key,args.side,args.attempt,plan_sha256=args.plan_sha256)
            request=json.loads(Path(args.request).read_bytes())
            result=finalize_retained_episode(episode,request)
            print(json.dumps(result,indent=2));return 0
        left=EpisodeLifecycle(args.run,args.key,"control",args.control_attempt,plan_sha256=args.plan_sha256)
        right=EpisodeLifecycle(args.run,args.key,"shadow",args.shadow_attempt,plan_sha256=args.plan_sha256)
        result=audit_pair(left,right)
        print(json.dumps(result,indent=2));return 0 if result['complete_execution_equivalent']else 1
    if args.command=="report":
        if args.include_input_audit or args.include_behavior:
            if not (args.paired and args.include_input_audit and args.include_behavior):
                parser.error("002 paired reporting requires both input and behavior auditing")
            from graphAdapter.evaluation.retrieval_report import report
            return 0 if report(args.run,args.control,args.out) else 1
        from graphAdapter.evaluation.report import report as paired_report
        result=paired_report(args.run,args.control,out=args.out,paired=args.paired)
        print(json.dumps(result,indent=2));return 0 if result["status"]=="PASS_ENGINEERING"else 1
    bindings=json.loads(Path(args.bindings).read_text())
    if Path(bindings["project_root"]).resolve()!=Path(__file__).resolve().parents[2]:
        parser.error("Binding project root mismatch")
    if args.command in ("inspect","render"):
        episode=Path(args.episode).resolve()
        if Path(bindings["project_root"])/"outputs/graph_memory" not in episode.parents or "evaluation_private"in episode.parts:
            parser.error("Only owned public memory episode directories are accepted")
        if args.command=="inspect":
            from graphAdapter.map_memory.storage.store import load_episode
            reader=load_episode(episode,args.revision)
            try:result=reader.verify(hashes=args.verify_hashes,references=args.verify_references)
            finally:reader.close()
        else:
            from graphAdapter.map_memory.visualization import render_episode
            result=render_episode(episode,revision=args.revision,height_slice=args.height_slice,out=args.out)
        print(json.dumps(result,indent=2));return 0
    if args.command=="check":
        if args.feature=="retrieval":
            from graphAdapter.evaluation.retrieval_checks import SUITES,run
            suites=args.suite.split(',')
            if len(set(suites))!=len(suites) or set(suites)-SUITES.keys():
                parser.error("Unknown or duplicate retrieval suite")
            return 0 if run(bindings['project_root'],suites,args.out) else 1
        if args.feature=="map_memory":
            if set(args.suite.split(","))!={"geometry","archive","correction","causality"}:
                parser.error("Stage001 CPU check requires geometry,archive,correction,causality")
            from graphAdapter.map_memory.validation import run_cpu
            result=run_cpu(args.out)
            return 0 if result["successful"]else 1
        suites=args.suite.split(",")
        if set(suites)!={"alignment","clock","pose_protocol"}:
            parser.error("Stage 000 check requires alignment,clock,pose_protocol")
        from graphAdapter.observation_pose.tests.suite import run_suite
        result=run_suite(args.out)
        return 0 if result.wasSuccessful() else 1
    if not args.cohort_plan:
        profile=json.loads(Path(args.profile).read_bytes())
        if profile.get('stage')=='002':
            if args.selection_manifest or args.execution_segment or args.start_offset or args.worker_index or args.worker_count!=1:
                parser.error('Stage002 registered eval supports ordered A prefixes; use an explicit cohort for other registered members')
            route=os.environ.get('CASE2_STORAGE_RUN')
            if not route:parser.error('Stage002 eval needs its prepared output storage run via --storage-run')
            from graphAdapter.evaluation.cohort_runner import evaluate_cohort
            results=evaluate_cohort(bindings,args.profile,args.registry,args.partition,args.datasets.split(','),args.out,
                cohort_plan=Path(route).parent/'retention_plan.json',hook_mode=args.hook_mode,attempt_id=args.attempt_id,
                preflight_only=args.preflight_only,registered_limit=args.limit_per_dataset,exact_registered=True)
            print(json.dumps(results,indent=2))
            return 0 if all(row['status'] in ('execution_complete_pending_audit','preflight_verified')for row in results)else 1
    if args.cohort_plan:
        if args.limit_per_dataset is not None or args.selection_manifest or args.execution_segment or args.start_offset or args.worker_index or args.worker_count!=1:
            parser.error('Explicit cohort cannot be mixed with legacy range/shard selection')
        from graphAdapter.evaluation.cohort_runner import evaluate_cohort
        results=evaluate_cohort(bindings,args.profile,args.registry,args.partition,args.datasets.split(','),args.out,
            cohort_plan=args.cohort_plan,hook_mode=args.hook_mode,attempt_id=args.attempt_id,preflight_only=args.preflight_only)
        print(json.dumps(results,indent=2))
        return 0 if all(row['status']in ('execution_complete_pending_audit','preflight_verified')for row in results)else 1
    from graphAdapter.evaluation.runner import evaluate as run_eval
    results=run_eval(bindings,args.profile,args.registry,args.partition,args.datasets.split(","),
                     args.limit_per_dataset,args.out,start_offset=args.start_offset,hook_mode=args.hook_mode,attempt_id=args.attempt_id,worker_index=args.worker_index,worker_count=args.worker_count,selection_manifest=args.selection_manifest,execution_segment=args.execution_segment,preflight_only=args.preflight_only)
    return 0 if all(row["status"]=="execution_complete_pending_audit" for row in results) else 1

if __name__=="__main__":
    sys.exit(main())
