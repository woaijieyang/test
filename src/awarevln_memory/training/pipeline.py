"""Auditable staged CLI. Commands never guess server paths or fabricate data."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .artifacts import (read_records,write_json,write_jsonl,identity,digest,
                        training_path,new_run_dir,budget,B_ROOTS)


def load_json(path):return json.loads(Path(path).read_text())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('init');p.add_argument('--workspace',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('select-checkpoint');p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('audit');p.add_argument('--source',required=True);p.add_argument('--dataset',choices=['r2r','rxr'],required=True)
    p.add_argument('--guide-source');p.add_argument('--events');p.add_argument('--output',required=True)
    p=sub.add_parser('extract-rollout');p.add_argument('--source',required=True);p.add_argument('--routes',required=True);p.add_argument('--mapping',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('audit-observations');p.add_argument('--events',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('select');p.add_argument('--routes',nargs='+',required=True);p.add_argument('--events',required=True);p.add_argument('--output',required=True)
    p.add_argument('--total',type=int,default=1500);p.add_argument('--seed',type=int,default=42);p.add_argument('--pilot',action='store_true')
    p=sub.add_parser('windows');p.add_argument('--routes',required=True);p.add_argument('--events',required=True);p.add_argument('--output',required=True);p.add_argument('--max-anchors',type=int,default=12)
    p=sub.add_parser('inventory');p.add_argument('--preflight',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('cache-prompts');p.add_argument('--config',required=True);p.add_argument('--events',required=True);p.add_argument('--triplets',required=True);p.add_argument('--windows',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('cache-moments');p.add_argument('--config',required=True);p.add_argument('--events',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('audit-cache');p.add_argument('--config',required=True);p.add_argument('--output',required=True);p.add_argument('--mask-missing-past',action='store_true')
    p=sub.add_parser('label-router');p.add_argument('--anchors',required=True);p.add_argument('--branches',required=True);p.add_argument('--reader',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('cache-router');p.add_argument('--config',required=True);p.add_argument('--labels',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('train');p.add_argument('--config',required=True);p.add_argument('--dry-run',action='store_true');p.add_argument('--diagnostic',action='store_true');p.add_argument('--resume');p.add_argument('--cpu',action='store_true')
    p=sub.add_parser('export');p.add_argument('--checkpoint',required=True);p.add_argument('--inventory',required=True);p.add_argument('--protocol',required=True);p.add_argument('--output',required=True);p.add_argument('--use-router',action='store_true')
    p=sub.add_parser('b-index');p.add_argument('--dataset',choices=['r2r','rxr'],required=True);p.add_argument('--annotations',required=True);p.add_argument('--b1',required=True);p.add_argument('--b2',required=True);p.add_argument('--b3',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('b-aggregate');p.add_argument('--expected',required=True);p.add_argument('--results',nargs='+',required=True);p.add_argument('--checkpoint-sha',required=True);p.add_argument('--protocol-sha',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('b-convert-results');p.add_argument('--expected',required=True);p.add_argument('--run',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('b-select');p.add_argument('--baseline',required=True);p.add_argument('--candidates',required=True);p.add_argument('--stage',choices=['reader','final'],required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('budget');p.add_argument('--samples',type=int,required=True);p.add_argument('--epochs',type=float,required=True);p.add_argument('--batch',type=int,default=1);p.add_argument('--world-size',type=int,default=2);p.add_argument('--accumulation',type=int,default=8);p.add_argument('--cap',type=int,default=5000)
    args=parser.parse_args(argv)
    if args.command=='init':
        from .bootstrap import initialize
        report=initialize(args.workspace,args.output)
    elif args.command=='select-checkpoint':
        from .bootstrap import select_checkpoint
        report=select_checkpoint(args.source,args.output)
    elif args.command=='audit':
        from .data import ingest,attach_events
        rows,rejected=ingest(args.source,args.dataset,'train',args.guide_source)
        if args.events:rows=attach_events(rows,read_records(training_path(args.events)))
        root=new_run_dir(args.output);write_jsonl(root/'candidates.jsonl',rows);write_jsonl(root/'rejected.jsonl',rejected)
        report={'accepted':len(rows),'rejected':len(rejected),'capabilities':{k:sum(r['capabilities'][k] for r in rows) for k in ('observation','act','reason','replay')}}
        write_json(root/'data_funnel.json',report)
    elif args.command=='extract-rollout':
        from .rollouts import extract_rollout
        rows,rejected=extract_rollout(args.source,read_records(training_path(args.routes)),load_json(args.mapping))
        root=new_run_dir(args.output);write_jsonl(root/'events.jsonl',rows);write_jsonl(root/'repair_queue.jsonl',rejected)
        report={'events':len(rows),'repairable':len(rejected)}
    elif args.command=='audit-observations':
        from .observations import audit_observations
        ready,repairs,files,report=audit_observations(read_records(training_path(args.events)))
        root=new_run_dir(args.output)
        for name,rows in [('ready_events.jsonl',ready),('repair_queue.jsonl',repairs),('files.jsonl',files)]:write_jsonl(root/name,rows)
        write_json(root/'report.json',report)
    elif args.command=='select':
        from .data import attach_events,select_routes
        routes=[r for path in args.routes for r in read_records(training_path(path))]
        events=read_records(training_path(args.events));routes=attach_events(routes,events)
        rows,report=select_routes(routes,total=args.total,seed=args.seed,pilot=args.pilot)
        root=new_run_dir(args.output);write_jsonl(root/'selected.jsonl',rows)
        for partition,name in [('train','train_routes.jsonl'),('memory-dev','memory_dev_routes.jsonl')]:write_jsonl(root/name,[r for r in rows if r['partition']==partition])
        write_json(root/'selected.lock.json',dict(report,rows_sha256=digest(root/'selected.jsonl'),events_sha256=digest(args.events)))
    elif args.command=='windows':
        from .data import build_windows,route_key
        from .datasets import validate_events,validate_partitions,tcl_triplets
        routes=read_records(training_path(args.routes));validate_partitions(routes);keys={route_key(r) for r in routes}
        raw=read_records(training_path(args.events));raw=[e for e in raw if e.get('route_key') in keys]
        events=validate_events(routes,raw)
        rows,excluded=build_windows(routes,list(events.values()),args.max_anchors)
        pairs,rejected=tcl_triplets(events,per_route=args.max_anchors)
        root=new_run_dir(args.output)
        for name,values in [('windows.jsonl',rows),('tcl.jsonl',pairs),('events.jsonl',list(events.values())),('excluded_windows.jsonl',excluded),('excluded_tcl.jsonl',rejected)]:write_jsonl(root/name,values)
        from collections import Counter
        report={'windows':len(rows),'triplets':len(pairs),'events':len(events),
                'tcl_negative_types':dict(Counter(x.get('negative_type','unknown') for x in pairs)),
                'tcl_rejections':dict(Counter(x['reason'] for x in rejected)),
                'source_sha256':digest(args.routes)}
        write_json(root/'dataset_bundle.json',report)
    elif args.command=='inventory':
        from .checkpoints import file_inventory
        native=load_json(args.preflight)
        entries=native.get('files')
        if not entries:raise ValueError('reuse existing outputs/preflight/model.json; do not guess weight files')
        for row in entries:
            if digest(row['path'])!=row['sha256']:raise ValueError('native model preflight drift')
        report=file_inventory([r['path'] for r in entries]);write_json(args.output,report)
    elif args.command in ('cache-prompts','cache-moments','cache-router'):
        from .runner import load_config,open_store,load_llm
        from .cache import FeatureStore
        from .checkpoints import load_modules,check_files
        cfg=load_config(args.config);inventory=load_json(cfg['base_inventory']);check_files(inventory)
        protocol=load_json(cfg['protocol']);contract={'base_identity':inventory['sha256'],'protocol_identity':identity(protocol),
                  'clean_encoding_dtype':protocol.get('clean_encoding_dtype')}
        if args.command=='cache-prompts':
            from .preprocess import build_prompt_cache,select_cache_events
            from llava.model.builder import load_pretrained_model
            events=read_records(training_path(args.events));triplets=read_records(training_path(args.triplets))
            windows=read_records(training_path(args.windows))
            planned=select_cache_events(events,triplets,windows)
            contract['source_identity']=identity([digest(args.events),digest(args.triplets),digest(args.windows)])
            if any(not e.get('protocol_identity') for e in events):raise ValueError('capture protocol identity missing')
            # Old policy/source identity may differ: re-encode raw observed pixels
            # under the NEW locked input contract, retaining both provenance IDs.
            # Never reuse hidden states from the old policy as current embeddings.
            base=str(Path(cfg['base_model']).resolve())
            tokenizer,model,processor,_=load_pretrained_model(base,Path(base).name)
            model.eval().requires_grad_(False)
            actual=str(next(model.get_llm().parameters()).dtype).removeprefix('torch.')
            if actual!=contract['clean_encoding_dtype']:raise ValueError('native model precision differs from protocol lock')
            for mode in ('reason','act'):
                text=protocol[mode+'_token'];idx=tokenizer.convert_tokens_to_ids(text)
                if idx is None or idx==tokenizer.unk_token_id:raise ValueError('missing native mode token')
                setattr(model.config,mode+'_token_id',idx)
            store=FeatureStore(args.output,contract,create=True)
            report=build_prompt_cache(model,tokenizer,processor,planned,store,triplets)
            report.update(input_events=len(events),planned_events=len(planned))
            failures={r['event_id'] for r in report['failures']}
            write_jsonl(Path(args.output)/'cached_events.jsonl',[e for key,e in planned.items() if key not in failures])
        elif args.command=='cache-moments':
            from .preprocess import build_moment_cache
            modules,doc=load_modules(cfg['parent'],stage='tcl',expected_base=inventory['sha256'],expected_protocol=identity(protocol))
            prompts=open_store(cfg['prompt_cache']);contract['source_identity']=identity(prompts.contract)
            contract['moment_checkpoint_sha256']=doc['checkpoint_sha256']
            llm=load_llm(cfg,cpu=not __import__('torch').cuda.is_available(),clean_encoding=True)
            if __import__('torch').cuda.is_available():llm.cuda();modules.cuda()
            keys=[e['event_id'] for e in read_records(training_path(args.events))]
            # Invalid/absent prompt features must fail BEFORE creating the
            # immutable output cache. No partial directory on preflight error.
            for key in keys:prompts.get(key)
            store=FeatureStore(args.output,contract,create=True)
            report=build_moment_cache(llm,modules,keys,prompts,store)
        else:
            from .counterfactual import cache_router_features
            modules,doc=load_modules(cfg['parent'],stage='reader',expected_base=inventory['sha256'],expected_protocol=identity(protocol))
            prompts=open_store(cfg['prompt_cache']);moments=open_store(cfg['moment_cache'])
            if moments.contract.get('moment_checkpoint_sha256')!=doc['parent_sha256']:raise ValueError('Reader and Moment cache do not share a parent')
            labels=read_records(training_path(args.labels));contract['source_identity']=digest(args.labels)
            contract['reader_checkpoint_sha256']=doc['checkpoint_sha256']
            store=FeatureStore(args.output,contract,create=True)
            rows,rejected=cache_router_features(labels,prompts,moments,modules,store,doc['checkpoint_sha256'])
            write_jsonl(Path(args.output)/'rows.jsonl',rows);report={'rows':len(rows),'rejected':rejected}
        write_json(Path(args.output)/'report.json',report)
    elif args.command=='audit-cache':
        from .runner import load_config,open_store
        from .preprocess import audit_cache_coverage
        cfg=load_config(args.config);rows=read_records(training_path(cfg['rows']))
        store=open_store(cfg['router_cache'] if cfg['stage']=='router' else cfg['prompt_cache'])
        moments=open_store(cfg['moment_cache']) if cfg['stage']=='reader' else None
        accepted,rejected=audit_cache_coverage(rows,store,cfg['stage'],moments,mask_missing_past=args.mask_missing_past)
        root=new_run_dir(args.output);write_jsonl(root/'accepted.jsonl',accepted);write_jsonl(root/'repair_queue.jsonl',rejected)
        report={'accepted':len(accepted),'repairable':len(rejected),
                'masked_past_windows':sum(bool(r.get('missing_past_repairs')) for r in accepted),
                'source_sha256':digest(cfg['rows'])};write_json(root/'report.json',report)
    elif args.command=='label-router':
        from .counterfactual import label_anchor
        from .checkpoints import read_identity
        reader=read_identity(args.reader)
        if reader['stage']!='reader':raise ValueError('fixed Reader checkpoint required')
        anchors=read_records(training_path(args.anchors));branches=read_records(training_path(args.branches));rows=[];rejected=[]
        for anchor in anchors:
            try:rows.append(label_anchor(anchor,[b for b in branches if b.get('anchor_id')==anchor['anchor_id']],reader['checkpoint_sha256']))
            except (OSError,ValueError,KeyError) as exc:rejected.append({'anchor_id':anchor.get('anchor_id'),'reason':str(exc)})
        root=new_run_dir(args.output);write_jsonl(root/'labels.jsonl',rows);write_jsonl(root/'uncertain.jsonl',rejected)
        report={'labelled':len(rows),'uncertain':len(rejected),'reader':reader['checkpoint_sha256']}
    elif args.command=='train':
        from .runner import load_config,run
        report=run(load_config(args.config),dry_run=args.dry_run,diagnostic=args.diagnostic,resume=args.resume,cpu=args.cpu)
    elif args.command=='export':
        from .checkpoints import export_bundle
        report=export_bundle(args.checkpoint,args.output,base_inventory=load_json(args.inventory),protocol=load_json(args.protocol),use_router=args.use_router)
    elif args.command=='b-index':
        from .evaluation import canonical_eval_rows,cumulative_sets
        annotations=read_records(args.annotations)
        groups=[canonical_eval_rows(read_records(p),args.dataset,annotations) for p in (args.b1,args.b2,args.b3)]
        sets,mode=cumulative_sets(*groups);root=new_run_dir(args.output)
        for name,rows in sets.items():
            write_jsonl(root/(name+'.jsonl'),rows);write_json(root/(name+'.ids.json'),[r['episode_id'] for r in rows])
        report={'mode':mode,'dataset':args.dataset,'counts':{k:len(v) for k,v in sets.items()},
                'source_files':[{ 'path':p,'sha256':digest(p)} for p in (args.annotations,args.b1,args.b2,args.b3)],'user_root':str(B_ROOTS[args.dataset])}
        write_json(root/'eval.lock.json',report)
    elif args.command=='b-aggregate':
        from .evaluation import aggregate
        expected=read_records(args.expected);results=[r for p in args.results for r in read_records(p)]
        report=aggregate(expected,results,args.checkpoint_sha,args.protocol_sha);write_json(args.output,report)
    elif args.command=='b-convert-results':
        from .evaluation import convert_native_results
        rows,report=convert_native_results(args.run,read_records(args.expected))
        write_jsonl(args.output,rows)
    elif args.command=='b-select':
        from .evaluation import choose_candidate
        report=choose_candidate(load_json(args.baseline),load_json(args.candidates),stage=args.stage)
        write_json(args.output,report)
    else:report=budget(args.samples,args.epochs,args.batch,args.world_size,args.accumulation,args.cap)
    print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    return report


if __name__=='__main__':main()
