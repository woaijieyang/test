"""Generate same-ID stage comparisons; never call an incomplete stage a full score."""
from pathlib import Path
import json,hashlib,math,sys
ROOT=Path(__file__).resolve().parents[1]
SUITE=ROOT/'outputs/hamlet-abc-20261031-v2'
DATA=Path('/data/zy/vln/data/checkpoint-choice/VLN-awareVLN')
DEST=ROOT/'result-show'
STAGES=['A','B','Remaining']
METRICS=['sr','spl','ndtw','ne','oracle_sr']
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.read_text().splitlines() if l]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mean(records,ids):
    if not set(ids)<=set(records):return None
    values=[records[x] for x in ids]
    for row in values:
        if any(not isinstance(row[k],(int,float)) or not math.isfinite(row[k]) for k in METRICS):raise ValueError('Invalid metric')
    return {k:sum(row[k] for row in values)/len(values) for k in METRICS}
def publish(path,text):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8');tmp.replace(path)
def main():
    DEST.mkdir(exist_ok=True)
    material=read(DATA/'audit/materialization.json');state=read(SUITE/'state.json') if (SUITE/'state.json').exists() else {'status':'PREPARED'}
    report={'suite_status':state.get('status'),'stage':state.get('stage'),'partition_sha256':digest(DATA/'audit/materialization.json'),'datasets':{}}
    text=['# Case2 HAMLET：A → B → Remaining 分阶段测评与对照','','本表由机器记录生成。仅已完整通过数据流、动作和独立指标审计的阶段填入新成绩；实时完成数不等于阶段验收。SR/SPL/nDTW/Oracle SR 为百分比，NE 为米，Δ 为新减旧（比例指标按百分点）。','',f"套件状态：`{state.get('status')}`；当前阶段：`{state.get('stage','见逐数据集状态')}`。GPU 仅4–7；CPU24–95（末72个逻辑核心）。",'']
    for ds in ['r2r','rxr']:
        leaves=material['leaves'][ds];scopes={**leaves,'A':sum((leaves[x] for x in ['A1','A2','A3']),[]),'B':sum((leaves[x] for x in ['B1','B2','B3']),[])}
        scopes['A+B']=scopes['A']+scopes['B'];scopes['Full']=scopes['A+B']+scopes['Remaining']
        source=ROOT/f'outputs/comparison-sources/baseline-{ds}';base_rows=rows(source/'results.jsonl');baseline={r['task_key'].split('|')[-2]:r['metrics'] for r in base_rows}
        if len(baseline)!=len(base_rows):raise ValueError('Ambiguous baseline IDs')
        valid=read(source/'validation.json')
        if valid['receipts']['results.jsonl']!=digest(source/'results.jsonl'):raise ValueError('Baseline evidence drift')
        historical={}
        if ds=='r2r':
            raw=read(ROOT/'outputs/comparison-sources/historical-hamlet-r2r/episode_metrics.json');mapping={'sr':'success','spl':'spl','ndtw':'ndtw','ne':'distance_to_goal','oracle_sr':'oracle_success'};historical={i:{k:v[mapping[k]] for k in METRICS} for i,v in raw.items()}
        current={};audited_stage=None;snap=None
        for stage in STAGES:
            path=SUITE/f'{stage}-{ds}-audited-results.json'
            if path.exists():
                snap=read(path)
                if snap['status']!='PASS':raise ValueError('Failed stage snapshot')
                current={r['task_key'].split('|')[-2]:r['metrics'] for r in snap['results']};audited_stage=stage
        run=ROOT/'outputs'/f'case2-hamlet-abc-20261031-v2-{ds}';progress=read(run/'progress.json') if (run/'progress.json').exists() else {}
        text += ['## '+('R2R' if ds=='r2r' else 'RxR-US'),'',f"已审计阶段：`{audited_stage or '尚无'}`；运行进度：{progress.get('completed',0)}/{progress.get('expected',len(scopes['Full']))}。",'','| Scope | N | 新HAMLET状态 | 新SR% | baseline SR% | 历史HAMLET SR% | 新SPL% | 新nDTW% | 新NE m | ΔSR vs baseline pp | ΔSPL vs baseline pp | ΔSR vs 原版 pp |','|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        dsrecord={'audited_stage':audited_stage,'progress':progress,'rows':{},'baseline_source':str(source),'historical_comparison':'same episode IDs; protocol differences, descriptive only' if historical else 'not available for this exact historical candidate','memory_counts':snap['memory_counts'] if snap else None}
        for label in ['A1','A2','A3','A','B1','B2','B3','B','A+B','Remaining','Full']:
            ids=scopes[label];new=mean(current,ids);base=mean(baseline,ids);old=mean(historical,ids) if historical else None
            delta={k:new[k]-base[k] for k in METRICS} if new else None;old_delta={k:new[k]-old[k] for k in METRICS} if new and old else None
            dsrecord['rows'][label]={'episodes':len(ids),'status':'audited_complete' if new else 'pending','new_hamlet':new,'baseline':base,'historical_hamlet':old,'new_minus_baseline':delta,'new_minus_historical':old_delta}
            def f(v,k):return '—' if v is None else f"{v[k]*(1 if k=='ne' else 100):.4f}"
            text.append(f"| {label} | {len(ids)} | {'已审计' if new else '待完成'} | {f(new,'sr')} | {f(base,'sr')} | {f(old,'sr')} | {f(new,'spl')} | {f(new,'ndtw')} | {f(new,'ne')} | {f(delta,'sr')} | {f(delta,'spl')} | {f(old_delta,'sr')} |")
        text += ['','### 完整指标与差值','','| Scope | 来源 | SR % | SPL % | nDTW % | NE m | Oracle SR % |','|---|---|---:|---:|---:|---:|---:|']
        for label,record in dsrecord['rows'].items():
            for title,key in [('baseline','baseline'),('历史HAMLET','historical_hamlet'),('本次HAMLET','new_hamlet'),('本次−baseline（pp/m）','new_minus_baseline'),('本次−历史（pp/m）','new_minus_historical')]:
                values=record[key]
                if values is not None:text.append('| '+label+' | '+title+' | '+' | '.join(f(values,k) for k in METRICS)+' |')
        if snap:text+=['',f"已审计记忆数据流计数：`{json.dumps(snap['memory_counts'])}`。",'']
        report['datasets'][ds]=dsrecord
    text+=['## 比较边界','','baseline 使用 case1 已发布固定划分完整运行的逐任务原始记录，已核验数据/GT、task集合及逐场景网格内容哈希。case2 改变模型（加入HAMLET）以及调度资源，因此不声明环境或整个源码身份完全相同。新结果来自重新推理，baseline 行属于历史原始结果重新分组。','','截图旧 HAMLET 只找到 R2R 完整候选，RxR 不编造对照。旧版的 parser、episode-reset、环境/网格协议与本次适配版本存在已记录差异；同 ID 的数值差仅为描述性差异，不能归因为某一个改动。旧 R2R 的独立严格几何限制及当前101条GT轨迹离网问题保留。','','阶段按 A、B、Remaining 严格推进，A/B 内保留原 A1–A3/B1–B3。Full 只有全部1839/1223完成并通过独立审计才展示本次分数。普通导航失败保留，失败/中断尝试不混入新协议。']
    publish(DEST/'model_results.md','\n'.join(text)+'\n');publish(DEST/'model_results.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'REPORT_GENERATED','suite_status':state.get('status'),'audited':{ds:r['audited_stage'] for ds,r in report['datasets'].items()}}))
if __name__=='__main__':main()
