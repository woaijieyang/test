"""Unified research CLI. This module never starts a formal model evaluation."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile

from oracle.registry import describe
from oracle.verification.binding import bind, bind_callable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["describe", "self-test", "audit-graph-lineage", "audit-raw-graph-paths", "audit-reference-lineage", "audit-landmark-protocol-readiness", "audit-landmark-identities", "audit-source-connectors", "audit-original-rxr-identities", "audit-continuous-assets", "audit-heading-conventions", "audit-landmark-heading-lineage", "audit-capability-ablation", "audit-execution-evidence", "audit-unified-inputs", "probe-native-aliases", "fetch-rxr-guides", "prepare-route-study", "prepare-official-study", "prepare-portfolio-study", "prepare-search-ablation", "prepare-execution-gate", "run-route-study", "route-worker", "route-audit", "report-route-study", "classify-official-study", "diagnose-official-contacts", "prepare-full-validation", "prepare-full-gate", "run-full-validation", "full-phase-worker", "review-full-validation", "report-full-validation", "review-completed-endpoints", "compare-endpoint-history", "audit-geometry-catalog", "prepare-full-continuation", "review-full-lineage", "audit-query-cache", "prepare-progress-study", "prepare-dense-mapping", "audit-dense-mapping", "prepare-mapping-factorial", "run-mapping-factorial", "audit-existing-bounded-mapping", "prepare-reused-mapping-motion", "run-reused-mapping-motion", "prepare-global-bounded-mapping", "audit-global-bounded-mapping", "prepare-global-landmark-validation", "run-global-landmark-validation", "prepare-priority-study", "run-priority-study", "diagnose-camera-surface", "probe-same-id-static", "probe-initial-state", "prepare-actuation-safe-starts", "prepare-start-scene-validation", "run-start-scene-validation", "probe-search-space", "prepare-soft-priority-study", "run-soft-priority-study", "audit-contact-surface", "diagnose-native-height", "diagnose-detail-mesh", "prepare-detail-scene", "run-detail-scene", "diagnose-prb-plans"])
    parser.add_argument("--case-root")
    parser.add_argument("--source-case-root")
    parser.add_argument("--output")
    parser.add_argument("--manifest")
    parser.add_argument("--task-file")
    parser.add_argument("--method")
    parser.add_argument("--input")
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--max-new-tasks", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    binding = bind("oracle.entrypoints", root)
    if args.command=='diagnose-prb-plans':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output:
            raise RuntimeError('Protected Case1 runtime and fresh output required')
        from oracle.research.counterfactual_plan import run,worker
        if args.method:
            if not args.manifest or not args.task_file or args.cpu is None:raise ValueError('Frozen worker inputs required')
            worker(args.case_root,args.manifest,args.task_file,args.output,args.cpu,args.method)
        else:
            result=run(args.case_root,args.output)
            print(json.dumps({'status':result['status'],'tasks':result['tasks'],'results':result['results']}))
        return
    if args.command in {'prepare-detail-scene','run-detail-scene'}:
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root:
            raise RuntimeError('Protected Case1 runtime required')
        from oracle.research.detail_scene_validation import prepare,run_with_review
        if args.command=='prepare-detail-scene':
            if not args.output or args.cpu is None:raise ValueError('Fresh output and observed idle CPU required')
            result=prepare(args.case_root,args.output,args.cpu)
            print(json.dumps({k:v for k,v in result.items() if k in ['status','task_count','regressions']}))
        else:
            if not args.manifest:raise ValueError('Frozen manifest required')
            run_with_review(args.case_root,args.manifest)
        return
    if args.command=='diagnose-detail-mesh':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output:
            raise RuntimeError('Protected runtime and fresh owned output required')
        from oracle.research.detail_mesh_study import run
        result=run(args.case_root,args.output)
        print(json.dumps({'status':result['status'],'scenes':[{'scene':x['scene'],'point_passes':x['point_passes']} for x in result['scenes']]}))
        return
    if args.command=='diagnose-native-height':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output:
            raise RuntimeError('Protected runtime and fresh owned output required')
        from oracle.verification.native_height_projection import run
        result=run(args.case_root,args.output)
        print(json.dumps({k:result[k] for k in ['status','records','point_check_passes','covered_occurrences_with_point_pass','whole_route_passes']}))
        return
    if args.command=='audit-contact-surface':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output:
            raise RuntimeError('Protected source access and fresh owned output required')
        from oracle.verification.contact_surface_geometry import run
        if args.method not in (None,'all209'):raise ValueError('Only fixed7 or full209 existing contact scopes supported')
        result=run(args.case_root,args.output,all209=args.method=='all209')
        print(json.dumps({k:result[k] for k in ['status','records','native_movement_actions','targets_modified']}))
        return
    if args.command in {'prepare-soft-priority-study','run-soft-priority-study'}:
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root:
            raise RuntimeError('Protected Case1 runtime required')
        if args.command=='prepare-soft-priority-study':
            from oracle.research.soft_priority_study import prepare
            if not args.output:raise ValueError('Fresh output required')
            result=prepare(args.case_root,args.output)
            print(json.dumps({k:result[k] for k in ['status','expected_tasks','expected_executions']}))
        else:
            from oracle.research.priority_study import run_study
            if not args.manifest:raise ValueError('Frozen manifest required')
            run_study(args.case_root,args.manifest)
        return
    if args.command=='probe-search-space':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output:
            raise RuntimeError('Protected runtime and fresh owned output required')
        from oracle.research.search_space_probe import run
        print(json.dumps(run(args.case_root,args.output)))
        return
    if args.command in {'prepare-start-scene-validation','run-start-scene-validation'}:
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root:
            raise RuntimeError('Protected runtime and owned case root required')
        from oracle.research.start_scene_validation import prepare,run_with_review
        if args.command=='prepare-start-scene-validation':
            if not args.output or args.cpu is None:raise ValueError('Fresh output and observed idle CPU required')
            result=prepare(args.case_root,args.output,args.cpu)
            print(json.dumps({k:result[k] for k in ['status','task_count','changed_initials','unchanged_controls']}))
        else:
            if not args.manifest:raise ValueError('Frozen manifest required')
            run_with_review(args.case_root,args.manifest)
        return
    if args.command=='prepare-actuation-safe-starts':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError('Protected runtime, owned output and observed idle CPU required')
        os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
        from oracle.research.start_pose_proposals import run
        result=run(args.case_root,args.output,args.cpu)
        print(json.dumps({k:result[k] for k in ['status','tasks','proposed','unresolved','unique_proposed_starts','native_actions','adopted_mappings']}))
        return
    if args.command=='probe-initial-state':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError('Protected runtime, owned output and observed idle CPU required')
        os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
        from oracle.verification.initial_state_probe import run
        result=run(args.case_root,args.output,args.cpu)
        print(json.dumps({k:result[k] for k in ['status','tasks','primitive_executions','all_direct_actions_rejected_tasks','pose_model_admission_disagreement_tasks','navigation_tasks_recovered']}))
        return
    if args.command=='probe-same-id-static':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError('Protected runtime, owned output and observed idle CPU required')
        os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
        from oracle.research.same_id_static import run
        result=run(args.case_root,args.output,args.cpu)
        print(json.dumps({k:result[k] for k in ['status','scope_records','native_queried_tasks','counts','native_actions','adopted_mappings']}))
        return
    if args.command=='diagnose-camera-surface':
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError('Protected runtime, owned output and observed idle CPU required')
        os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
        from oracle.verification.camera_surface_diagnostic import run
        result=run(args.case_root,args.output,args.cpu)
        print(json.dumps({k:result[k] for k in ['status','queries','triangles','primary_reasons','native_actions','adopted_mappings']}))
        return
    if args.command in {'prepare-priority-study','run-priority-study'}:
        if not os.environ.get('CASE1_PROTECTION') or not args.case_root:
            raise RuntimeError('Protected Case1 runtime required')
        from oracle.research.priority_study import prepare,run_study
        if args.command=='prepare-priority-study':
            if not args.output:raise ValueError('Fresh output required')
            result=prepare(args.case_root,args.output)
            print(json.dumps({k:result[k] for k in ['status','expected_tasks','expected_executions']}))
        else:
            if not args.manifest:raise ValueError('Frozen manifest required')
            run_study(args.case_root,args.manifest)
        return
    if args.command in {"prepare-global-landmark-validation","run-global-landmark-validation"}:
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root:raise RuntimeError("Protected Case1 runtime required")
        from oracle.research.global_validation import prepare,run_with_review
        if args.command == "prepare-global-landmark-validation":
            if not args.output:raise ValueError("Fresh output required")
            m=prepare(args.case_root,args.output)
            print(json.dumps({k:m[k] for k in ('status','task_count','datasets','splits','information_mapping_groups','changed_targets_tasks','prior_full_charge_seconds')}))
        else:
            if not args.manifest:raise ValueError("Frozen global manifest required")
            run_with_review(args.case_root,args.manifest)
        return
    if args.command == "audit-global-bounded-mapping":
        if not os.environ.get("CASE1_PROTECTION") or not all((args.case_root,args.input,args.output)) or args.cpu is None:
            raise RuntimeError("Protected runtime, complete producer, fresh output and idle CPU required")
        from oracle.verification.global_bounded_mapping import audit
        r=audit(args.case_root,args.input,args.output,args.cpu)
        print(json.dumps({k:r[k] for k in ('status','records','counts','native_movement_actions')}))
        return
    if args.command == "run-reused-mapping-motion":
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.manifest:
            raise RuntimeError("Protected runtime and frozen run required")
        from oracle.research.reused_mapping_motion import run_with_review
        run_with_review(args.case_root,args.manifest)
        return
    if args.command == "prepare-reused-mapping-motion":
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output:
            raise RuntimeError("Protected runtime and fresh output required")
        from oracle.research.reused_mapping_motion import prepare
        m=prepare(args.case_root,args.output)
        print(json.dumps({k:m[k] for k in ('status','task_count','datasets','overlap_with_dense93')}))
        return
    if args.command == "audit-existing-bounded-mapping":
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError("Protected runtime, fresh output and observed-idle CPU required")
        from oracle.verification.existing_bounded_mapping import audit
        r=audit(args.case_root,args.output,args.cpu)
        print(json.dumps({k:r[k] for k in ('status','full_scene_records','counts','potential_strict_endpoint_repair','native_movement_actions')}))
        return
    if args.command in {"prepare-mapping-factorial","run-mapping-factorial"}:
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root:raise RuntimeError("Protected Case1 required")
        from oracle.research.mapping_factorial import prepare,run_matrix
        if args.command == "prepare-mapping-factorial":
            if not args.output:raise ValueError("Fresh output required")
            m=prepare(args.case_root,args.output)
            print(json.dumps({k:m[k] for k in ('status','affected_tasks','expected_executions','global_landmark_denominator')}))
        else:
            if not args.manifest:raise ValueError("Frozen matrix required")
            run_matrix(args.case_root,args.manifest)
        return
    if args.command == "audit-dense-mapping":
        if not os.environ.get("CASE1_PROTECTION") or not all((args.case_root,args.input,args.output)) or args.cpu is None:
            raise RuntimeError("Protected runtime, frozen producer, new output and CPU required")
        from oracle.verification.dense_mapping import audit
        result=audit(args.case_root,args.input,args.output,args.cpu)
        print(json.dumps({k:result[k] for k in ('status','full_records','selected_proposals','results','native_movement_actions')}))
        return
    if args.command in {"prepare-dense-mapping","prepare-global-bounded-mapping"}:
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError("Protected runtime, fresh output and CPU required")
        if args.command == "prepare-dense-mapping":
            from oracle.research.dense_reference_mapping import prepare
        else:
            from oracle.research.global_bounded_mapping import prepare
        from oracle.common.artifacts import owned_output,write_json
        output=owned_output(args.case_root,args.output)
        if output.exists():raise FileExistsError(output)
        try:
            result=prepare(args.case_root,args.output,args.cpu)
            print(json.dumps({k:result[k] for k in ('status','records','source_available_blockers','proposal_counts','original_blockers','counts','native_movement_actions') if k in result}))
        except Exception as error:
            if output.exists() and (output/'source-freeze.json').exists():
                write_json(output/'failure.json',{'error':repr(error),'type':type(error).__name__})
                write_json(output/'state.json',{'status':'FAILED_CANDIDATE_PREPARATION_PRESERVED','error':repr(error)},immutable=False)
                write_json(output/'source-freeze.json',{'status':'CLOSED_AFTER_FAILURE'},immutable=False)
            raise
        return
    if args.command == "prepare-progress-study":
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output:
            raise RuntimeError("Protected runtime and fresh output required")
        from oracle.research.progress_development import prepare
        m=prepare(args.case_root,args.output)
        print(json.dumps({k:m[k] for k in ('status','expected_tasks','expected_executions')}))
        return
    if args.command == "audit-query-cache":
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output or args.cpu is None:
            raise RuntimeError("Protected runtime/output/CPU required")
        os.sched_setaffinity(0,{args.cpu});os.nice(15)
        from oracle.research.cache_equivalence import audit
        print(json.dumps(audit(args.case_root,args.output)))
        return
    if args.command == "review-full-lineage":
        from oracle.research.lineage_review import review
        if not all((args.case_root,args.input,args.manifest,args.output)):raise ValueError("Continuation, independent review and new output required")
        result=review(args.case_root,args.input,args.manifest,args.output)
        print(json.dumps({k:result[k] for k in ("status","datasets","records","revisions","all_navigation_gates_passed")}))
        return
    if args.command == "audit-geometry-catalog":
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output:raise RuntimeError("Protected case runtime and output required")
        from oracle.research.geometry_catalog_audit import audit
        result=audit(args.case_root,args.output)
        print(json.dumps({k:result[k] for k in ("status","scenes","schemas","native_actions")}))
        return
    if args.command == "prepare-full-continuation":
        if not os.environ.get("CASE1_PROTECTION") or not all((args.case_root,args.input,args.manifest,args.output)):raise RuntimeError("Protected runtime, parent, geometry audit and new output required")
        from oracle.research.continuation import prepare
        result=prepare(args.case_root,args.input,args.manifest,args.output)
        print(json.dumps({k:result[k] for k in ("status","task_count","datasets","continuation")}))
        return
    if args.command == "compare-endpoint-history":
        from oracle.research.history_overlap import compare
        if not args.case_root or not args.output:raise ValueError("Case root and output required")
        result=compare(args.case_root,args.output)
        print(json.dumps({k:result[k] for k in ("status","records","groups","identity_mismatches")}))
        return
    if args.command == "review-completed-endpoints":
        from oracle.research.cohort_review import review
        if not all((args.case_root,args.input,args.output)):raise ValueError("Snapshot and output required")
        result=review(args.case_root,args.input,args.output)
        print(json.dumps({k:result[k] for k in ("status","datasets","records","groups","failure_classes","actual_actions","independently_replayed_actions","max_replay_position_error_m","max_replay_orientation_error_rad","all_selected_navigation_gates_passed")}))
        return
    if args.command == "report-full-validation":
        from oracle.research.full_report import report
        if not all((args.case_root,args.input,args.manifest,args.output)):raise ValueError("Run, completed review and output required")
        result=report(args.case_root,args.input,args.manifest,args.output,args.source_case_root)
        print(json.dumps({k:result[k] for k in ("status","records","all_navigation_gates_passed","phase_costs_including_failed_attempts","controller_sessions","controller_reserved_cpu_seconds")}))
        return
    if args.command == "audit-landmark-protocol-readiness":
        from oracle.adapters.landmark_rxr.protocol_readiness import audit
        if not args.case_root or not args.output:raise ValueError("Explicit case root and output required")
        result=audit(args.case_root,args.output)
        print(json.dumps({k:result[k] for k in ("status","counts","total_subpaths","source_long_segment_records","native_actions")}))
        return
    if args.command == "audit-reference-lineage":
        from oracle.adapters.landmark_rxr.reference_lineage import audit
        if not args.case_root or not args.output:raise ValueError("Explicit case root and output required")
        result=audit(args.case_root,args.output)
        print(json.dumps({k:v for k,v in result.items() if k not in ("startup","raw_sources","ce_sources","inputs_sha256","outputs_sha256","limits")}))
        return
    if args.command == "audit-raw-graph-paths":
        from oracle.adapters.landmark_rxr.graph_path_audit import audit
        if not args.case_root or not args.output:raise ValueError("Explicit case root and output required")
        result=audit(args.case_root,args.output)
        print(json.dumps({k:result[k] for k in ("status","records","required_viewpoints","missing_published_viewpoints","original_counts","published_counts","known_edge")}))
        return
    if args.command == "audit-graph-lineage":
        from oracle.adapters.landmark_rxr.graph_lineage import audit
        if not args.case_root or not args.output:
            raise ValueError('Explicit case root and new output required')
        # Read-only JSON/ZIP provenance audit, no simulator or shared asset writes.
        print(json.dumps(audit(args.case_root,root/'configs/experiments/graph_lineage.json',args.output)))
        return
    if args.command in {"prepare-full-validation","prepare-full-gate","run-full-validation","full-phase-worker","review-full-validation"}:
        from oracle.research.full_run import dispatch
        config=json.loads((root/'configs/experiments/full_validation.json').read_text())
        bind_callable(dispatch,config['implementation'],root)
        if args.max_new_tasks is not None and args.max_new_tasks<1:raise ValueError('Positive dispatch cap required')
        return dispatch(args)
    if args.command in {"report-route-study", "classify-official-study", "diagnose-official-contacts"}:
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.input or not args.output:
            raise RuntimeError("Protected runtime and explicit input/output required")
        config = json.loads((root / "configs/experiments/route_report.json").read_text())
        if args.command == "diagnose-official-contacts":
            from oracle.verification.contact_causes import diagnose as report
            expected = config["contact_diagnoser"]
        elif args.command == "classify-official-study":
            from oracle.research.official_classification import classify as report
            expected = config["official_classifier"]
        else:
            from oracle.research.report import report
            expected = config["implementation"]
        bind_callable(report, expected, root)
        result = report(args.case_root, args.input, args.output)
        print(json.dumps({"status": result["status"], "records": result.get("records", result.get("source_records", result.get("failed_tasks"))),
                          "native_actions_or_replayed": result.get("actual_actions_replayed", result.get("actual_actions", result.get("native_actions")))}))
        return
    if args.command in {"prepare-route-study", "prepare-official-study", "prepare-portfolio-study", "prepare-search-ablation", "prepare-execution-gate", "run-route-study", "route-worker", "route-audit"}:
        from oracle.research.route_study import dispatch
        prepare_configs = {"prepare-route-study": "route_development_v1.json", "prepare-official-study": "official_reexecution.json", "prepare-portfolio-study": "guarded_portfolio.json", "prepare-search-ablation": "search_ablation.json", "prepare-execution-gate": "execution_gate.json"}
        config = (json.loads((root / "configs/experiments" / prepare_configs[args.command]).read_text())
                  if args.command.startswith("prepare-") else json.loads(Path(args.manifest).read_text())["config"])
        expected = config["implementation"]
        bind_callable(dispatch, expected, root)
        return dispatch(args)
    if args.command == "describe":
        print(json.dumps({"entrypoint": binding, "methods": describe(),
                          "scope": "capability inventory, not navigation acceptance"},
                         ensure_ascii=False, indent=2))
    elif args.command == "self-test":
        import unittest
        import tempfile
        temporary_root = (root.parents[2] / ".cache/oracle-self-tests").resolve()
        temporary_root.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(temporary_root)
        suite = unittest.defaultTestLoader.discover(str(root / "tests"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
    elif args.command in {"audit-landmark-identities", "audit-source-connectors", "audit-original-rxr-identities", "audit-continuous-assets", "audit-heading-conventions", "audit-landmark-heading-lineage", "audit-capability-ablation", "audit-execution-evidence", "audit-unified-inputs", "probe-native-aliases", "fetch-rxr-guides"}:
        if not os.environ.get("CASE1_PROTECTION") or not args.case_root or not args.output:
            raise RuntimeError("Protected runtime and explicit case root/output required")
        mapping_audit = args.command in {"audit-landmark-identities", "audit-source-connectors", "audit-original-rxr-identities", "audit-continuous-assets", "audit-heading-conventions", "audit-landmark-heading-lineage", "audit-capability-ablation", "audit-execution-evidence", "audit-unified-inputs"}
        acquisition = args.command == "fetch-rxr-guides"
        if args.command == "audit-landmark-identities":
            from oracle.adapters.landmark_rxr.ledger import audit
            config_path = root / "configs/tasks/landmark_inventory.json"
        elif args.command == "audit-source-connectors":
            from oracle.adapters.landmark_rxr.connector_audit import audit
            config_path = root / "configs/tasks/landmark_connectors.json"
        elif args.command == "audit-original-rxr-identities":
            from oracle.adapters.rxr.original_identity import audit
            config_path = root / "configs/tasks/original_rxr_identity.json"
        elif args.command == "audit-continuous-assets":
            from oracle.adapters.rxr.continuous_assets import audit
            config_path = root / "configs/tasks/continuous_assets.json"
        elif args.command == "audit-heading-conventions":
            from oracle.adapters.rxr.coordinate_audit import audit
            config_path = root / "configs/tasks/coordinate_audit.json"
        elif args.command == "audit-landmark-heading-lineage":
            from oracle.adapters.landmark_rxr.heading_lineage import audit
            config_path = root / "configs/tasks/landmark_heading_lineage.json"
        elif args.command == "audit-capability-ablation":
            from oracle.research.capability_ablation import audit
            config_path = root / "configs/experiments/capability_ablation.json"
        elif args.command == "audit-execution-evidence":
            from oracle.verification.retrospective_evidence import audit
            config_path = root / "configs/experiments/retrospective_evidence.json"
        elif args.command == "audit-unified-inputs":
            from oracle.adapters.unified_inventory import audit
            config_path = root / "configs/tasks/unified_inventory.json"
        elif acquisition:
            from oracle.adapters.rxr.reference_sources import fetch
            config_path = root / "configs/sources/rxr_original_guides.json"
        else:
            from oracle.verification.alias_probe import run
            config_path = root / "configs/experiments/alias_probe.json"
        config = json.loads(config_path.read_text())
        handler = fetch if acquisition else audit if mapping_audit else run
        handler_binding = bind_callable(handler, config["implementation"], root)
        output = Path(args.output).resolve()
        case_root = Path(args.case_root).resolve()
        if not output.is_relative_to(case_root / "outputs/oracleAdapter"):
            raise RuntimeError("Output escapes isolated research evidence")
        import psutil
        usage = psutil.cpu_percent(interval=1, percpu=True)
        idle = [i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i] < 10]
        if not idle:
            raise RuntimeError("No idle CPU available; do not displace other jobs")
        os.sched_setaffinity(0, [min(idle, key=lambda i: usage[i])])
        os.nice(10)
        sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob("*")) if p.is_file()
                   and p.suffix in {".py", ".json"} and p.relative_to(root).parts[:2] != ("configs", "local")}
        actual_imports = [bind(name, root) for name in sorted(sys.modules)
                          if name == "oracle" or name.startswith("oracle.")]
        startup = {"status": "FROZEN_BEFORE_IDENTITY_AUDIT", "command": sys.argv,
                   "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "entrypoint": binding, "actual_imports": actual_imports,
                   "selected_implementation": handler_binding,
                   "process": {"pid": os.getpid(), "creation_time": psutil.Process().create_time(),
                               "start_ticks": Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19] if Path("/proc/self/stat").exists() else None},
                   "sources": sources, "effective_configuration": config,
                   "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                   "task_objective": config.get("task_objective", "acquire_missing_public_reference_bytes" if acquisition else "identity_and_order_accounting_not_navigation" if mapping_audit else "isolated_native_transition_counterexamples_not_whole_routes"),
                   "privileges": config.get("privileges", ["public_official_guide_annotations"] if acquisition else ["landmark_annotations", "official_continuous_annotations"] if mapping_audit else ["true_pose", "navigation_mesh", "goal", "reference_path", "source_geometry"]),
                   "resources": {"gpu": [], "cpu_processes": 1,
                                 "cpu_affinity": sorted(os.sched_getaffinity(0))},
                   "budget": {"network_bytes": config["maximum_total_bytes"], "wall_seconds": config["wall_seconds"], "navigation_actions": 0} if acquisition else {"source_passes": 1, "navigation_actions": 0} if mapping_audit else {"native_calls_including_replay": config["max_native_calls"], "wall_seconds": config["max_wall_seconds"]},
                   "original_model_runtime_modified": False}
        output.parent.mkdir(parents=True, exist_ok=True)
        launch_path = output.with_name(output.name + ".launch.json")
        with launch_path.open("x", encoding="utf-8") as stream:
            json.dump(startup, stream, ensure_ascii=False, indent=2)
        archive = output.with_name(output.name + ".source.zip")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as snapshot:
            for relative in sources:
                snapshot.write(root / relative, relative)
        started = time.perf_counter()
        try:
            result = fetch(args.case_root, config, args.output) if acquisition else audit(args.case_root, config, args.output) if mapping_audit else run(args.case_root, config, root, args.output)
        except Exception as error:
            output.mkdir(parents=True, exist_ok=True)
            with (output / "failure.json").open("x", encoding="utf-8") as stream:
                json.dump({"status": "FAILED_PRESERVED", "error": repr(error),
                           "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, stream, indent=2)
            raise
        if any(hashlib.sha256((root / name).read_bytes()).hexdigest() != value
               for name, value in sources.items()):
            raise RuntimeError("Active source drift during identity audit")
        (output / "run_manifest.json").write_bytes(launch_path.read_bytes())
        evidence_binding = {"status": "SOURCE_AND_OUTPUT_BINDING_ONLY",
                            "run_manifest_sha256": hashlib.sha256(launch_path.read_bytes()).hexdigest(),
                            "validation_sha256": hashlib.sha256((output / "validation.json").read_bytes()).hexdigest(),
                            "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                            "source_unchanged_during_run": True}
        (output / "evidence_binding.json").write_text(json.dumps(evidence_binding, indent=2))
        (output / "cost.json").write_text(json.dumps({"wall_seconds": time.perf_counter() - started,
                                                     "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k not in {"sources", "outputs", "legacy_receipts"} and not isinstance(v, list)},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
