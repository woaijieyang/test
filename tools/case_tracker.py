#!/usr/bin/env python3
"""Initialize and maintain auditable case-level experiment records."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
RUN_TYPES = ("train", "rollout", "evaluation", "other")
RUN_STATUSES = ("planned", "running", "complete", "partial", "failed")
TASK_STATUSES = {
    "complete": ("完成", "Complete"),
    "partial": ("部分完成", "Partially complete"),
    "failed": ("失败", "Failed"),
}
TASK_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2})-[a-z0-9][a-z0-9-]*\.md$")


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    temp.replace(path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        atomic_write_text(path, text)


def copy_if_missing(source: Path, target: Path) -> None:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"ERROR: JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: Invalid JSON in {path}: {exc}") from exc


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise SystemExit("ERROR: name/slug must contain ASCII letters or digits")
    return slug


def safe_segment(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise SystemExit(
            f"ERROR: {label} must be one path segment containing only "
            "letters, digits, dot, underscore, or hyphen"
        )
    if value in (".", ".."):
        raise SystemExit(f"ERROR: invalid {label}: {value}")
    return value


def resolve_case_root(value: str | None) -> Path:
    if value:
        root = Path(value).expanduser().resolve()
    else:
        script = Path(__file__).resolve()
        candidate = script.parent.parent
        if (candidate / "CASE_MANIFEST.json").is_file():
            root = candidate
        else:
            raise SystemExit("ERROR: --case-root is required outside an initialized case")
    if not (root / "CASE_MANIFEST.json").is_file():
        raise SystemExit(f"ERROR: not an initialized case: {root}")
    return root


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "process" / "task-flow" / "TASK-FLOW-TEMPLATE.md").is_file():
            return parent
    raise SystemExit("ERROR: cannot locate repository root and process/task-flow template")


def template_root() -> Path:
    repo = find_repo_root()
    root = repo / "process" / "case-template"
    if not root.is_dir():
        raise SystemExit(f"ERROR: case template directory is missing: {root}")
    return root


def render_case_readme(manifest: dict[str, Any]) -> str:
    return f"""# {manifest['case_id']}: {manifest['title_zh']}

> English: {manifest['title_en']}

## 目标 / Objective

- 中文：{manifest['objective_zh']}
- English: {manifest['objective_en']}

## 记录入口 / Record entry points

- `CASE_MANIFEST.json`: case身份、范围和当前阶段。
- `WORKFLOW.md`: 该case从数据到结论的完整工作流。
- `EXPERIMENTS.md`: 全部实验总表，由脚本重建。
- `RESULTS.md`: 可比较的实验指标，由脚本重建。
- `runs/`: 每次训练、rollout和评估的独立证据目录。
- `task-flow/`: 对话、实现和实验完成后的不可覆盖工作记录。
- `tools/case_autolog.py`: 普通任务自动记录和漏记巡检。
- `AUTO_RECORDING.md`: 自动记录、实验收尾和巡检命令说明。
- `RECORDING_AUDIT.md`: 当前自动记录门禁结果。

## 使用方式 / Usage

```bash
python3 tools/case_tracker.py start-run --run-type rollout --stage stage1 --version V2 --name smoke-rxr
python3 tools/case_tracker.py finish-run --run-dir <run-directory> --result-json <result.json>
python3 tools/case_tracker.py record-task --evidence-json <task-evidence.json>
python3 tools/case_autolog.py audit --case-root . --strict
python3 tools/case_tracker.py rebuild
python3 tools/case_tracker.py validate
```

所有原始输入保持只读。训练数据只能来自官方 `train` split；验证、测试、
fixed512 和 holdout 数据不得进入训练清单。
"""


def render_case_overview(manifest: dict[str, Any]) -> str:
    return render_case_readme(manifest).replace(
        f"# {manifest['case_id']}:",
        f"# {manifest['case_id']} 实验台账 / Experiment Ledger:",
        1,
    )


def render_workflow(manifest: dict[str, Any]) -> str:
    return f"""# {manifest['case_id']} 工作流 / Case Workflow

## 1. 方法定位 / Method

- 基线版本：
- 改进方法：
- 唯一主要变量：
- 不变量：

## 2. 数据边界 / Data boundary

```text
official train -> rollout -> trainable records -> training
official val_seen -> tuning and development validation
fixed regression subset -> compatibility regression
disjoint holdout -> frozen-configuration check
official val_unseen -> full local evaluation
official test -> trajectory submission only
```

## 3. Rollout数据流 / Rollout data flow

```text
episode manifest
  -> simulator observations and model calls
  -> episodes.jsonl
  -> model_calls.jsonl
  -> events.jsonl
  -> moment_shards/*.safetensors
  -> integrity gate
```

## 4. 训练数据门禁 / Training-data gate

- 仅允许 `train` split。
- episode、policy call、event和moment引用必须完整对齐。
- fixed benchmark、validation和test记录必须拒绝。
- counterfactual强标签必须从相同模拟器状态产生。
- 离线真值只能用于标签和评估，不得进入部署输入。
- 训练前冻结数据manifest及SHA-256。

## 5. 训练与评估 / Training and evaluation

```text
weak supervision
  -> action-critical bootstrap
  -> counterfactual labels
  -> memory-only training
  -> val_seen
  -> fixed regression
  -> disjoint holdout
  -> full val_unseen
```

## 6. 决策规则 / Decision rule

- 主要指标：
- 保护指标：
- 失败条件：
- 晋级条件：

## 7. 当前结论 / Current conclusion

- 尚未填写。仅在有真实运行证据后更新。
"""


def init_case(args: argparse.Namespace) -> None:
    root = Path(args.case_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    existing = [entry for entry in root.iterdir()]
    if existing and not args.allow_existing:
        raise SystemExit(
            f"ERROR: target is not empty: {root}; use --allow-existing only after inspection"
        )
    manifest_path = root / "CASE_MANIFEST.json"
    if manifest_path.exists():
        raise SystemExit(f"ERROR: case is already initialized: {manifest_path}")

    created = now_local().isoformat(timespec="seconds")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_id": args.case_id,
        "title_zh": args.title_zh,
        "title_en": args.title_en,
        "objective_zh": args.objective_zh,
        "objective_en": args.objective_en,
        "status": "active",
        "current_stage": args.current_stage,
        "created_at": created,
        "updated_at": created,
        "baseline_version": args.baseline_version,
        "candidate_versions": [],
    }
    for relative in (
        "stage0",
        "stage1/V1/source",
        "runs/train",
        "runs/rollout",
        "runs/evaluation",
        "runs/other",
        "runs/archive",
        "task-flow",
        "templates",
        "tools",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    source_templates = template_root() / "templates"
    for source in source_templates.iterdir():
        if source.is_file():
            copy_if_missing(source, root / "templates" / source.name)
    repo = find_repo_root()
    copy_if_missing(
        repo / "process" / "task-flow" / "TASK-FLOW-TEMPLATE.md",
        root / "task-flow" / "TASK-FLOW-TEMPLATE.md",
    )
    copy_if_missing(Path(__file__).resolve(), root / "tools" / "case_tracker.py")
    copy_if_missing(
        repo / "process" / "script" / "case_autolog.py",
        root / "tools" / "case_autolog.py",
    )
    copy_if_missing(
        repo / "process" / "script" / "create_case_version.py",
        root / "tools" / "create_case_version.py",
    )
    copy_if_missing(
        repo / "process" / "case-template" / "AGENTS.md",
        root / "AGENTS.md",
    )
    copy_if_missing(
        repo / "process" / "CASE-AUTO-RECORDING.md",
        root / "AUTO_RECORDING.md",
    )
    copy_if_missing(
        repo / "process" / "case-template" / "NEXT_VERSION_TEMPLATE.md",
        root / "templates" / "NEXT_VERSION_TEMPLATE.md",
    )
    copy_if_missing(
        repo / "process" / "case-template" / "activate-case.sh",
        root / "config" / "activate-case.sh",
    )

    atomic_write_json(manifest_path, manifest)
    write_text_if_missing(root / "README.md", render_case_readme(manifest))
    write_text_if_missing(root / "CASE_OVERVIEW.md", render_case_overview(manifest))
    write_text_if_missing(root / "WORKFLOW.md", render_workflow(manifest))
    copy_if_missing(
        repo / "process" / "case-template" / "STAGE_LAYOUT.md",
        root / "STAGE_LAYOUT.md",
    )
    copy_if_missing(
        repo / "process" / "case-template" / "DATA_LINKS.md",
        root / "DATA_LINKS.md",
    )
    if manifest["case_id"] != "case0" and not (root / "data").exists():
        (root / "data").symlink_to(repo / "data", target_is_directory=True)
    write_text_if_missing(
        root / "stage0" / "README.md",
        "# stage0: AwareVLN baseline\n\n"
        "本目录直接保存`AwareVLN/`原始基线，不设置V1、V2。"
        "它只用于rollout、推理和后续stage的公平对照。\n",
    )
    write_text_if_missing(
        root / "stage1" / "README.md",
        "# stage1: first improvement direction\n\n"
        "每次迭代使用`V1/source/`、`V2/source/`、`V3/source/`，"
        "每个版本保存完整可运行源码。\n",
    )
    write_text_if_missing(
        root / "task-flow" / "README.md",
        "# Case task-flow\n\n"
        "本目录保存该case内已完成对话、实现和实验的不可覆盖记录。"
        "文件名为`YYYY-MM-DD-NN-slug.md`，每天从`00`开始。\n",
    )
    rebuild_case(root)
    print(root)


def new_run_manifest(args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    created = now_local().isoformat(timespec="seconds")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_type": args.run_type,
        "stage": args.stage,
        "version": args.version,
        "name": args.name,
        "status": "planned",
        "created_at": created,
        "started_at": None,
        "completed_at": None,
        "code": {
            "source_path": args.source_path,
            "source_sha256": args.source_sha256,
            "config_sha256": args.config_sha256,
        },
        "model": {
            "base_model": args.base_model,
            "base_model_sha256": args.base_model_sha256,
            "adapter": args.adapter,
            "adapter_sha256": args.adapter_sha256,
        },
        "data": {
            "dataset": args.dataset,
            "split": args.split,
            "role": args.role,
            "language": args.language,
            "episode_manifest": args.episode_manifest,
            "episode_manifest_sha256": args.episode_manifest_sha256,
            "planned_episodes": args.planned_episodes,
            "completed_episodes": 0,
            "fixed_benchmark": args.fixed_benchmark,
        },
        "rollout": {},
        "training_data": {},
        "training": {},
        "metrics": {},
        "artifacts": [],
        "checks": [],
        "limitations": [],
        "decision": {},
        "summary_zh": "",
        "summary_en": "",
        "training_eligible": False,
    }


def render_experiment_note(run: dict[str, Any]) -> str:
    data = run.get("data", {})
    rollout = run.get("rollout", {})
    training_data = run.get("training_data", {})
    training = run.get("training", {})
    metrics = run.get("metrics", {})
    artifacts = run.get("artifacts", [])
    checks = run.get("checks", [])
    limitations = run.get("limitations", [])

    def metric(name: str) -> str:
        value = metrics.get(name, "")
        return str(value) if value != "" else "未记录 / Not recorded"

    artifact_rows = "\n".join(
        f"| {item.get('name', '')} | `{item.get('path', '')}` | "
        f"{item.get('sha256', '')} | {item.get('note', '')} |"
        for item in artifacts
    ) or "| 无 / None |  |  |  |"
    check_rows = "\n".join(
        f"| {item.get('name', '')} | {item.get('method', '')} | "
        f"{item.get('result', '')} | {item.get('note', '')} |"
        for item in checks
    ) or "| 未记录 / Not recorded |  |  |  |"
    limitation_lines = "\n".join(f"- {item}" for item in limitations) or "- 无记录 / None recorded"

    return f"""# 实验记录：{run['run_id']} / Experiment Record

## 1. 实验身份 / Identity

- Stage / Version: `{run['stage']} / {run['version']}`
- Run type: `{run['run_type']}`
- Status: `{run['status']}`
- Created: `{run['created_at']}`
- Completed: `{run.get('completed_at') or ''}`

## 2. 目的与结论 / Objective and conclusion

- 中文：{run.get('summary_zh') or '尚未填写 / Not yet filled'}
- English: {run.get('summary_en') or 'Not yet filled'}

## 3. 代码与模型 / Code and model

- Source: `{run['code'].get('source_path', '')}`
- Source SHA-256: `{run['code'].get('source_sha256', '')}`
- Config SHA-256: `{run['code'].get('config_sha256', '')}`
- Base model: `{run['model'].get('base_model', '')}`
- Adapter: `{run['model'].get('adapter', '')}`

## 4. 数据 / Data

- Dataset / split: `{data.get('dataset', '')} / {data.get('split', '')}`
- Role / language: `{data.get('role', '')} / {data.get('language', '')}`
- Episode manifest: `{data.get('episode_manifest', '')}`
- Planned / completed: `{data.get('planned_episodes', 0)} / {data.get('completed_episodes', 0)}`
- Fixed benchmark: `{data.get('fixed_benchmark', False)}`
- Training eligible: `{run.get('training_eligible', False)}`

## 5. Rollout产物 / Rollout outputs

- Episodes: `{rollout.get('episodes', 0)}`
- Model calls: `{rollout.get('model_calls', 0)}`
- Events: `{rollout.get('events', 0)}`
- Memory moments: `{rollout.get('moments', 0)}`
- Missing/corrupt records: `{rollout.get('invalid_records', 0)}`

## 6. 可训练数据与训练 / Training data and training

- Weak samples: `{training_data.get('weak', 0)}`
- Strong samples: `{training_data.get('strong', 0)}`
- Helpful / harmful / null: `{training_data.get('helpful', 0)} / {training_data.get('harmful', 0)} / {training_data.get('null', 0)}`
- Rejected samples: `{training_data.get('rejected', 0)}`
- Frozen training manifest: `{training_data.get('manifest', '')}`
- Optimizer steps: `{training.get('optimizer_steps', 0)}`
- Trainable parameters: `{training.get('trainable_parameters', 0)}`
- Output checkpoint: `{training.get('checkpoint', '')}`

## 7. 结果 / Results

### 7.1 导航核心指标 / Core navigation

| SR | SPL | nDTW | sDTW | NE | Oracle SR | Steps | Path length | Timeout rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| {metric('sr')} | {metric('spl')} | {metric('ndtw')} | {metric('sdtw')} | {metric('ne')} | {metric('oracle_sr')} | {metric('steps')} | {metric('path_length')} | {metric('timeout_rate')} |

### 7.2 行为与安全 / Behavior and safety

| REASON rate | ACT rate | Stop rate | Collision rate | Turn decisions | Max turn run | Stuck rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| {metric('reason_rate')} | {metric('act_rate')} | {metric('stop_rate')} | {metric('collision_rate')} | {metric('turn_decisions')} | {metric('max_consecutive_turns')} | {metric('stuck_rate')} |

### 7.3 记忆模块 / Memory module

| Read prob. | Effective read rate | Write prob. | Write rate | Memory items | Effective alpha | Mode-lock rate | Fallback count |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| {metric('read_probability_mean')} | {metric('effective_read_rate')} | {metric('write_probability_mean')} | {metric('write_rate')} | {metric('memory_items_mean')} | {metric('effective_alpha_mean')} | {metric('mode_lock_rate')} | {metric('fallback_count')} |

### 7.4 配对统计与效率 / Paired statistics and efficiency

| Candidate only | Baseline only | Ties | Paired p-value | Delta SR | Delta SPL | Delta nDTW |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| {metric('candidate_only')} | {metric('baseline_only')} | {metric('ties')} | {metric('paired_p_value')} | {metric('delta_sr')} | {metric('delta_spl')} | {metric('delta_ndtw')} |

| Wall time (s) | Seconds/episode | GPU hours | Peak VRAM (GB) | Model calls/episode |
| ---: | ---: | ---: | ---: | ---: |
| {metric('wall_time_seconds')} | {metric('seconds_per_episode')} | {metric('gpu_hours')} | {metric('peak_vram_gb')} | {metric('model_calls_per_episode')} |

## 8. 产物与验证 / Artifacts and validation

| Artifact | Path | SHA-256 | Note |
| --- | --- | --- | --- |
{artifact_rows}

| Check | Method | Result | Note |
| --- | --- | --- | --- |
{check_rows}

## 9. 限制与决定 / Limitations and decision

{limitation_lines}

- Decision: `{run.get('decision', {})}`
"""


def start_run(args: argparse.Namespace) -> None:
    root = resolve_case_root(args.case_root)
    timestamp = now_local().strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}-{slugify(args.name)}"
    stage = safe_segment(args.stage, "stage")
    version = safe_segment(args.version, "version")
    run_dir = root / "runs" / args.run_type / stage / version / run_id
    if run_dir.exists():
        raise SystemExit(f"ERROR: run directory already exists: {run_dir}")
    for relative in ("logs", "rollouts", "results"):
        (run_dir / relative).mkdir(parents=True, exist_ok=False)
    manifest = new_run_manifest(args, run_id)
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    atomic_write_json(
        run_dir / "status.json",
        {"run_id": run_id, "status": "planned", "updated_at": manifest["created_at"]},
    )
    atomic_write_json(
        run_dir / "data_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "inputs": [],
            "outputs": [],
            "training_exclusions": ["val_seen", "val_unseen", "test", "test_challenge", "fixed512"],
        },
    )
    atomic_write_text(
        run_dir / "config.env",
        "# Record the exact effective environment here. Do not store credentials.\n",
    )
    atomic_write_text(run_dir / "EXPERIMENT_NOTE.md", render_experiment_note(manifest))
    rebuild_case(root)
    print(run_dir)


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def training_eligibility(run: dict[str, Any]) -> tuple[bool, str]:
    data = run.get("data", {})
    if data.get("split") != "train":
        return False, "source split is not train"
    if data.get("fixed_benchmark"):
        return False, "fixed benchmark data is never trainable"
    rollout = run.get("rollout", {})
    if int(rollout.get("invalid_records", 0) or 0) > 0:
        return False, "rollout contains invalid records"
    manifest = run.get("training_data", {}).get("manifest")
    if not manifest:
        return False, "frozen training manifest is missing"
    return True, "train split and frozen training manifest passed"


def finish_run(args: argparse.Namespace) -> None:
    root = resolve_case_root(args.case_root)
    run_dir = Path(args.run_dir).expanduser().resolve()
    if root not in run_dir.parents:
        raise SystemExit(f"ERROR: run directory is outside case root: {run_dir}")
    manifest_path = run_dir / "run_manifest.json"
    manifest = load_json(manifest_path)
    result = load_json(Path(args.result_json).expanduser().resolve())
    immutable = {"run_id", "run_type", "stage", "version", "created_at", "code", "model"}
    overwritten = sorted(immutable.intersection(result))
    if overwritten:
        raise SystemExit(
            "ERROR: result evidence cannot overwrite run identity: "
            + ", ".join(overwritten)
        )
    unexpected_data = sorted(set(result.get("data", {})) - {"completed_episodes"})
    if unexpected_data:
        raise SystemExit(
            "ERROR: result evidence can only update data.completed_episodes; "
            "unexpected keys: " + ", ".join(unexpected_data)
        )
    status = result.get("status")
    if status not in ("complete", "partial", "failed"):
        raise SystemExit("ERROR: result status must be complete, partial, or failed")
    merged = deep_merge(manifest, result)
    merged["status"] = status
    merged["completed_at"] = now_local().isoformat(timespec="seconds")
    eligible, reason = training_eligibility(merged)
    merged["training_eligible"] = eligible
    merged.setdefault("training_data", {})["eligibility_reason"] = reason
    atomic_write_json(manifest_path, merged)
    atomic_write_json(
        run_dir / "status.json",
        {
            "run_id": merged["run_id"],
            "status": status,
            "updated_at": merged["completed_at"],
        },
    )
    atomic_write_text(run_dir / "EXPERIMENT_NOTE.md", render_experiment_note(merged))
    rebuild_case(root)
    if not args.no_task_flow:
        evidence = task_evidence_from_run(merged, run_dir, root)
        path = record_task_flow(root, evidence)
        print(path)
    print(run_dir)


def task_evidence_from_run(
    run: dict[str, Any], run_dir: Path, root: Path
) -> dict[str, Any]:
    status = run["status"]
    task_status = status if status in TASK_STATUSES else "partial"
    metrics = run.get("metrics", {})
    metric_text = ", ".join(
        f"{key}={value}" for key, value in metrics.items() if value not in ("", None)
    ) or "no metrics recorded"
    return {
        "title_zh": f"完成实验 {run['run_id']}",
        "title_en": f"Complete experiment {run['run_id']}",
        "slug": f"finish-{slugify(run['name'])}",
        "status": task_status,
        "objective_zh": run.get("summary_zh") or f"完成并归档实验{run['run_id']}。",
        "objective_en": run.get("summary_en") or f"Complete and archive {run['run_id']}.",
        "scope_zh": f"范围限于{root.name}中的{run['run_type']}实验；未修改其他case。",
        "scope_en": f"Scope is limited to the {run['run_type']} run in {root.name}; other cases were not modified.",
        "steps": [
            {
                "name_zh": "执行并收集运行证据",
                "name_en": "Execute and collect run evidence",
                "purpose": "产生可追溯的真实实验记录。",
                "method": f"按run manifest执行{run['run_type']}并保存独立输出。",
                "tools": f"Run directory: {run_dir}",
                "result": f"状态={status}，完成episode={run.get('data', {}).get('completed_episodes', 0)}。",
            },
            {
                "name_zh": "整理数据和指标",
                "name_en": "Consolidate data and metrics",
                "purpose": "确认数据是否可训练并记录结果。",
                "method": "核对split、frozen manifest、无效记录和评估指标。",
                "tools": "run_manifest.json and result evidence JSON",
                "result": f"training_eligible={run.get('training_eligible')}; {metric_text}",
            },
            {
                "name_zh": "更新case总账",
                "name_en": "Update case ledger",
                "purpose": "使该实验进入case级比较。",
                "method": "重建EXPERIMENTS.md和RESULTS.md并写入本记录。",
                "tools": "case_tracker.py finish-run",
                "result": "run明细和case总表已同步。",
            },
        ],
        "deliverables": [
            {
                "name": "实验记录 / Experiment record",
                "path": str(run_dir / "EXPERIMENT_NOTE.md"),
                "outcome": "保存本次实验配置、数据、训练和指标。",
                "verification": f"run status={status}",
            },
            {
                "name": "Run manifest",
                "path": str(run_dir / "run_manifest.json"),
                "outcome": "机器可读的实验来源和结果。",
                "verification": "JSON已解析并用于重建总表。",
            },
        ],
        "conclusion_zh": run.get("summary_zh") or f"实验状态为{status}。",
        "conclusion_en": run.get("summary_en") or f"Run status is {status}.",
        "limits_zh": "；".join(run.get("limitations", [])) or "无额外记录。",
        "limits_en": "See the experiment note for limitations.",
        "checks": run.get("checks", []),
        "lessons": [
            {
                "symptom": "实验结果可能被误用或与其他版本混淆。",
                "cause": "缺少唯一run目录、manifest或数据来源记录。",
                "fix": "使用独立run目录、哈希和case总账。",
                "rule": "不得复用结果目录；训练前必须冻结数据manifest。",
            }
        ],
        "fastest_path": [
            "核对代码、模型、数据split和episode manifest。",
            "在唯一run目录执行实验并保存完整证据。",
            "运行finish-run、validate并检查case总表。",
        ],
        "references": [str(run_dir)],
    }


def next_task_path(task_dir: Path, date: str, slug: str) -> Path:
    numbers = []
    for path in task_dir.iterdir():
        match = TASK_FILE_RE.match(path.name)
        if match and match.group(1) == date:
            numbers.append(int(match.group(2)))
    number = max(numbers, default=-1) + 1
    if number > 99:
        raise SystemExit(f"ERROR: task-flow sequence exhausted for {date}")
    path = task_dir / f"{date}-{number:02d}-{slugify(slug)}.md"
    if path.exists():
        raise SystemExit(f"ERROR: refusing to overwrite task-flow record: {path}")
    return path


def render_task_flow(evidence: dict[str, Any], path: Path) -> str:
    status_key = evidence.get("status")
    if status_key not in TASK_STATUSES:
        raise SystemExit("ERROR: task evidence status must be complete, partial, or failed")
    status_zh, status_en = TASK_STATUSES[status_key]
    steps = evidence.get("steps") or []
    deliverables = evidence.get("deliverables") or []
    if not steps or not deliverables:
        raise SystemExit("ERROR: task evidence requires non-empty steps and deliverables")

    step_text = []
    for index, step in enumerate(steps, start=1):
        step_text.append(
            f"""### Step {index} — {step.get('name_zh', '')} / {step.get('name_en', '')}

- 目的 / Purpose: {step.get('purpose', '')}
- 方法与处理方式 / Method and handling: {step.get('method', '')}
- 使用的工具、命令或依据 / Tools, commands, or rationale: {step.get('tools', '')}
- 结果与证据 / Result and evidence: {step.get('result', '')}
"""
        )
    deliverable_rows = "\n".join(
        f"| {item.get('name', '')} | `{item.get('path', '')}` | "
        f"{item.get('outcome', '')} | {item.get('verification', '')} |"
        for item in deliverables
    )
    checks = evidence.get("checks") or []
    check_rows = "\n".join(
        f"| {item.get('name', '')} | {item.get('method', '')} | "
        f"{item.get('result', '')} | {item.get('note', '')} |"
        for item in checks
    ) or "| 未执行额外检查 / No additional check | 未提供 / Not provided | 未验证 / Not verified | 见限制 / See limits |"
    lessons = evidence.get("lessons") or []
    lesson_text = "\n\n".join(
        f"""### 失败或风险点 / Failure or risk

- 现象与触发条件 / Symptom and trigger: {item.get('symptom', '')}
- 根因 / Root cause: {item.get('cause', '')}
- 修正或缓解措施 / Fix or mitigation: {item.get('fix', '')}
- 可复现的避坑规则 / Reusable pitfall-avoidance rule: {item.get('rule', '')}"""
        for item in lessons
    ) or "未遇到 / None encountered"
    fastest = "\n".join(
        f"{index}. {item}" for index, item in enumerate(evidence.get("fastest_path") or [], start=1)
    )
    references = "\n".join(f"- {item}" for item in evidence.get("references") or []) or "- 无 / None"
    date = path.name[:10]
    text = f"""# 工作记录：{evidence.get('title_zh', '')} / Task Record: {evidence.get('title_en', '')}

> 文件名 / Filename: `{path.name}`\x20\x20
> 存放目录 / Storage location: `{path.parent}`\x20\x20
> 完成日期 / Completion date: `{date}`\x20\x20
> 状态 / Status: `{status_zh} / {status_en}`

## 1. 工作目的 / Objective

- 中文：{evidence.get('objective_zh', '')}
- English: {evidence.get('objective_en', '')}

## 2. 工作范围与前提 / Scope and prerequisites

- 中文：{evidence.get('scope_zh', '')}
- English: {evidence.get('scope_en', '')}

## 3. 完成步骤 / Steps performed

{''.join(step_text)}
## 4. 最终产物与处理结果 / Deliverables and outcomes

| 产物 / Deliverable | 路径或位置 / Path or location | 处理结果与用途 / Outcome and use | 验证证据 / Verification |
| --- | --- | --- | --- |
{deliverable_rows}

### 最终结论 / Final conclusion

- 中文：{evidence.get('conclusion_zh', '')}
- English: {evidence.get('conclusion_en', '')}

### 已知限制与后续事项 / Known limits and follow-ups

- 中文：{evidence.get('limits_zh', '')}
- English: {evidence.get('limits_en', '')}

## 5. 验证与质量检查 / Validation and quality checks

| 检查项 / Check | 方法 / Method | 结果 / Result | 备注 / Notes |
| --- | --- | --- | --- |
{check_rows}

## 6. 失败经验与避坑 / Failure lessons and pitfalls

{lesson_text}

## 7. 最快成功路径 / Fastest reliable path

{fastest or '1. 未提供 / Not provided'}

## 8. 参考信息 / References

{references}
"""
    if re.search(r"<[^>\n]+>", text) or "<!--" in text:
        raise SystemExit("ERROR: rendered task-flow still contains placeholders")
    return text


def record_task_flow(root: Path, evidence: dict[str, Any]) -> Path:
    date = evidence.get("date") or now_local().date().isoformat()
    try:
        dt.date.fromisoformat(date)
    except ValueError as exc:
        raise SystemExit(f"ERROR: invalid task-flow date: {date}") from exc
    task_dir = root / "task-flow"
    path = next_task_path(task_dir, date, evidence.get("slug", "task"))
    atomic_write_text(path, render_task_flow(evidence, path))
    return path


def record_task(args: argparse.Namespace) -> None:
    root = resolve_case_root(args.case_root)
    evidence = load_json(Path(args.evidence_json).expanduser().resolve())
    path = record_task_flow(root, evidence)
    print(path)


def collect_runs(root: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted((root / "runs").glob("**/run_manifest.json")):
        run = load_json(path)
        run["_manifest_path"] = str(path)
        runs.append(run)
    return runs


def table_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def rebuild_case(root: Path) -> None:
    runs = collect_runs(root)
    experiment_rows = []
    result_rows = []
    for run in runs:
        data = run.get("data", {})
        metrics = run.get("metrics", {})
        experiment_rows.append(
            "| {run_id} | {run_type} | {stage} | {version} | {dataset}/{split} | "
            "{status} | {episodes} |".format(
                run_id=run.get("run_id", ""),
                run_type=run.get("run_type", ""),
                stage=run.get("stage", ""),
                version=run.get("version", ""),
                dataset=data.get("dataset", ""),
                split=data.get("split", ""),
                status=run.get("status", ""),
                episodes=data.get("completed_episodes", 0),
            )
        )
        if any(value not in ("", None) for value in metrics.values()):
            result_rows.append(
                "| {run_id} | {stage} | {version} | {dataset}/{split} | {episodes} | {sr} | "
                "{spl} | {ndtw} | {sdtw} | {ne} | {oracle_sr} | {timeout_rate} |".format(
                    run_id=run.get("run_id", ""),
                    stage=run.get("stage", ""),
                    version=run.get("version", ""),
                    dataset=data.get("dataset", ""),
                    split=data.get("split", ""),
                    episodes=data.get("completed_episodes", 0),
                    sr=table_value(metrics.get("sr")),
                    spl=table_value(metrics.get("spl")),
                    ndtw=table_value(metrics.get("ndtw")),
                    sdtw=table_value(metrics.get("sdtw")),
                    ne=table_value(metrics.get("ne")),
                    oracle_sr=table_value(metrics.get("oracle_sr")),
                    timeout_rate=table_value(metrics.get("timeout_rate")),
                )
            )
    experiments = """# 实验总账 / Experiment Ledger

> 本文件由`case_tracker.py rebuild`生成。不要手工填写实验结果。

| Run ID | Type | Stage | Version | Dataset/Split | Status | Episodes |
| --- | --- | --- | --- | --- | --- | ---: |
""" + ("\n".join(experiment_rows) if experiment_rows else "| 暂无实验 / No runs | | | | | | |") + "\n"
    results = """# 结果比较 / Result Comparison

> 只比较数据集、split、role、language和episode manifest一致的实验。

| Run ID | Stage | Version | Dataset/Split | Episodes | SR | SPL | nDTW | sDTW | NE | Oracle SR | Timeout rate |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
""" + ("\n".join(result_rows) if result_rows else "| 暂无结果 / No results | | | | | | | | | | | |") + "\n"
    atomic_write_text(root / "EXPERIMENTS.md", experiments)
    atomic_write_text(root / "RESULTS.md", results)
    manifest = load_json(root / "CASE_MANIFEST.json")
    manifest["updated_at"] = now_local().isoformat(timespec="seconds")
    atomic_write_json(root / "CASE_MANIFEST.json", manifest)


def rebuild(args: argparse.Namespace) -> None:
    root = resolve_case_root(args.case_root)
    rebuild_case(root)
    print(root / "EXPERIMENTS.md")
    print(root / "RESULTS.md")


def validate_case(root: Path) -> list[str]:
    errors: list[str] = []
    required = (
        "CASE_MANIFEST.json",
        "CASE_OVERVIEW.md",
        "WORKFLOW.md",
        "EXPERIMENTS.md",
        "RESULTS.md",
        "task-flow/TASK-FLOW-TEMPLATE.md",
    )
    for relative in required:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")
    run_ids = set()
    for run in collect_runs(root):
        run_id = run.get("run_id")
        if not run_id:
            errors.append(f"run without run_id: {run.get('_manifest_path')}")
        elif run_id in run_ids:
            errors.append(f"duplicate run_id: {run_id}")
        run_ids.add(run_id)
        if run.get("status") not in RUN_STATUSES:
            errors.append(f"invalid run status: {run_id}")
        if run.get("training_eligible") and run.get("data", {}).get("split") != "train":
            errors.append(f"non-train run marked training eligible: {run_id}")
    for path in (root / "task-flow").glob("*.md"):
        if path.name in ("README.md", "TASK-FLOW-TEMPLATE.md"):
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"<[^>\n]+>", text) or "<!--" in text:
            errors.append(f"task-flow contains placeholder: {path.name}")
    return errors


def validate(args: argparse.Namespace) -> None:
    root = resolve_case_root(args.case_root)
    errors = validate_case(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: {root}")


def compare_cases(args: argparse.Namespace) -> None:
    parent = Path(args.cases_root).expanduser().resolve()
    rows = []
    for root in sorted(parent.glob(args.pattern)):
        if not (root / "CASE_MANIFEST.json").is_file():
            continue
        case = load_json(root / "CASE_MANIFEST.json")
        for run in collect_runs(root):
            metrics = run.get("metrics", {})
            if not metrics:
                continue
            data = run.get("data", {})
            rows.append(
                "| {case_id} | {run_id} | {stage} | {version} | {dataset}/{split} | {episodes} | "
                "{sr} | {spl} | {ndtw} | {sdtw} | {ne} | {timeout_rate} |".format(
                    case_id=case.get("case_id", root.name),
                    run_id=run.get("run_id", ""),
                    stage=run.get("stage", ""),
                    version=run.get("version", ""),
                    dataset=data.get("dataset", ""),
                    split=data.get("split", ""),
                    episodes=data.get("completed_episodes", 0),
                    sr=table_value(metrics.get("sr")),
                    spl=table_value(metrics.get("spl")),
                    ndtw=table_value(metrics.get("ndtw")),
                    sdtw=table_value(metrics.get("sdtw")),
                    ne=table_value(metrics.get("ne")),
                    timeout_rate=table_value(metrics.get("timeout_rate")),
                )
            )
    text = """# Case Comparison

> 仅应比较相同数据集、split、role、language、episode manifest和评估配置。

| Case | Run ID | Stage | Version | Dataset/Split | Episodes | SR | SPL | nDTW | sDTW | NE | Timeout rate |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
""" + ("\n".join(rows) if rows else "| No comparable results | | | | | | | | | | | |") + "\n"
    output = Path(args.output).expanduser().resolve()
    atomic_write_text(output, text)
    print(output)


def add_case_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-root", help="Initialized case root; optional inside case/tools")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-case", help="Initialize an independent case ledger")
    init.add_argument("--case-root", required=True)
    init.add_argument("--case-id", required=True)
    init.add_argument("--title-zh", required=True)
    init.add_argument("--title-en", required=True)
    init.add_argument("--objective-zh", required=True)
    init.add_argument("--objective-en", required=True)
    init.add_argument("--current-stage", default="stage1")
    init.add_argument("--baseline-version", default="V1")
    init.add_argument("--allow-existing", action="store_true")
    init.set_defaults(func=init_case)

    start = sub.add_parser("start-run", help="Create a unique run evidence directory")
    add_case_root_argument(start)
    start.add_argument("--run-type", choices=RUN_TYPES, required=True)
    start.add_argument("--stage", required=True)
    start.add_argument("--version", required=True)
    start.add_argument("--name", required=True)
    start.add_argument("--dataset", default="")
    start.add_argument("--split", default="")
    start.add_argument("--role", default="")
    start.add_argument("--language", default="")
    start.add_argument("--planned-episodes", type=int, default=0)
    start.add_argument("--episode-manifest", default="")
    start.add_argument("--episode-manifest-sha256", default="")
    start.add_argument("--fixed-benchmark", action="store_true")
    start.add_argument("--source-path", default="")
    start.add_argument("--source-sha256", default="")
    start.add_argument("--config-sha256", default="")
    start.add_argument("--base-model", default="")
    start.add_argument("--base-model-sha256", default="")
    start.add_argument("--adapter", default="")
    start.add_argument("--adapter-sha256", default="")
    start.set_defaults(func=start_run)

    finish = sub.add_parser("finish-run", help="Finalize a run from result evidence")
    add_case_root_argument(finish)
    finish.add_argument("--run-dir", required=True)
    finish.add_argument("--result-json", required=True)
    finish.add_argument("--no-task-flow", action="store_true")
    finish.set_defaults(func=finish_run)

    task = sub.add_parser("record-task", help="Append a conversation/task-flow record")
    add_case_root_argument(task)
    task.add_argument("--evidence-json", required=True)
    task.set_defaults(func=record_task)

    rebuild_parser = sub.add_parser("rebuild", help="Rebuild case experiment and result tables")
    add_case_root_argument(rebuild_parser)
    rebuild_parser.set_defaults(func=rebuild)

    validate_parser = sub.add_parser("validate", help="Validate the case ledger")
    add_case_root_argument(validate_parser)
    validate_parser.set_defaults(func=validate)

    compare = sub.add_parser("compare-cases", help="Build a cross-case result table")
    compare.add_argument("--cases-root", required=True)
    compare.add_argument("--pattern", default="case*")
    compare.add_argument("--output", required=True)
    compare.set_defaults(func=compare_cases)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
