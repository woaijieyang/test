#!/usr/bin/env python3
"""Automatically record case work and detect missing experiment records."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXCLUDED_SNAPSHOT_DIRS = {
    ".case-ledger",
    ".git",
    "__pycache__",
    "imports",
    "runs",
    "shared",
    "task-flow",
}


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(value, encoding="utf-8", newline="\n")
    temp.replace(path)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise SystemExit("ERROR: slug must contain ASCII letters or digits")
    return slug


def case_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not (root / "CASE_MANIFEST.json").is_file():
        raise SystemExit(f"ERROR: not an initialized case: {root}")
    return root


def ledger_root(root: Path) -> Path:
    return root / ".case-ledger"


def recorded_state_path(root: Path) -> Path:
    return ledger_root(root) / "recorded_state.json"


def snapshot(root: Path) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        if relative_dir == Path("."):
            dirs[:] = [
                name for name in dirs if name not in EXCLUDED_SNAPSHOT_DIRS
            ]
        else:
            dirs[:] = [
                name
                for name in dirs
                if name not in {".git", "__pycache__", ".case-ledger"}
            ]
        for name in files:
            if relative_dir == Path(".") and name == "RECORDING_AUDIT.md":
                continue
            path = current_path / name
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            relative = path.relative_to(root).as_posix()
            result[relative] = [stat.st_mtime_ns, stat.st_size]
    return result


def changed_paths(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_keys = set(before)
    after_keys = set(after)
    added = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    modified = sorted(
        key for key in before_keys & after_keys if before[key] != after[key]
    )
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "counts": {
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
        },
    }


def start_session(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    root = case_root(args.case_root)
    session_id = (
        f"{now().strftime('%Y%m%d-%H%M%S')}-{slugify(args.slug)}"
    )
    path = ledger_root(root) / "open" / f"{session_id}.json"
    if path.exists():
        raise SystemExit(f"ERROR: session already exists: {path}")
    session = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "case_root": str(root),
        "title_zh": args.title_zh,
        "title_en": args.title_en,
        "slug": slugify(args.slug),
        "objective_zh": args.objective_zh or args.title_zh,
        "objective_en": args.objective_en or args.title_en,
        "scope_zh": args.scope_zh or f"仅限{root.name}，不修改其他case。",
        "scope_en": args.scope_en or f"Limited to {root.name}; other cases are unchanged.",
        "started_at": now().isoformat(timespec="seconds"),
        "before": snapshot(root),
        "command": None,
    }
    atomic_json(path, session)
    return path, session


def resolve_session(root: Path, value: str) -> Path:
    direct = Path(value).expanduser()
    if direct.is_file():
        path = direct.resolve()
    else:
        name = value if value.endswith(".json") else f"{value}.json"
        path = (ledger_root(root) / "open" / name).resolve()
    if not path.is_file() or ledger_root(root).resolve() not in path.parents:
        raise SystemExit(f"ERROR: open session not found: {value}")
    return path


def summarize_changes(changes: dict[str, Any], limit: int = 40) -> str:
    entries = []
    for kind in ("added", "modified", "deleted"):
        entries.extend(f"{kind}:{path}" for path in changes[kind])
    shown = entries[:limit]
    suffix = f"; plus {len(entries) - limit} more" if len(entries) > limit else ""
    return ", ".join(shown) + suffix if shown else "no tracked file changes"


def build_task_evidence(
    root: Path,
    session: dict[str, Any],
    args: argparse.Namespace,
    changes: dict[str, Any],
) -> dict[str, Any]:
    status = args.status
    summary_zh = args.summary_zh or (
        f"自动记录本次工作；状态为{status}，文件变化为{changes['counts']}。"
    )
    summary_en = args.summary_en or (
        f"Automatically recorded this task; status={status}, changes={changes['counts']}."
    )
    command = session.get("command")
    command_text = " ".join(command) if command else "multi-turn conversation or manual work"
    deliverables = []
    for path_value in args.deliverable:
        path = Path(path_value)
        if not path.is_absolute():
            path = root / path
        deliverables.append(
            {
                "name": path.name,
                "path": str(path),
                "outcome": "本次工作明确登记的产物。",
                "verification": "存在" if path.exists() else "路径已记录但当前不存在",
            }
        )
    if not deliverables:
        deliverables.append(
            {
                "name": "自动记录证据 / Automatic work evidence",
                "path": str(ledger_root(root) / "archive" / f"{session['session_id']}.json"),
                "outcome": "保存命令、退出状态和文件变化。",
                "verification": f"status={status}",
            }
        )
    return {
        "title_zh": session["title_zh"],
        "title_en": session["title_en"],
        "slug": session["slug"],
        "status": status,
        "objective_zh": session["objective_zh"],
        "objective_en": session["objective_en"],
        "scope_zh": session["scope_zh"],
        "scope_en": session["scope_en"],
        "steps": [
            {
                "name_zh": "建立自动记录会话",
                "name_en": "Open automatic recording session",
                "purpose": "防止对话或命令执行后漏记。",
                "method": "工作开始前保存case内可编辑文件快照。",
                "tools": "case_autolog.py begin/run",
                "result": f"session={session['session_id']}",
            },
            {
                "name_zh": "执行并采集证据",
                "name_en": "Execute and collect evidence",
                "purpose": "记录实际命令及文件变化。",
                "method": command_text,
                "tools": "case_autolog.py",
                "result": summarize_changes(changes),
            },
            {
                "name_zh": "收尾并写入task-flow",
                "name_en": "Finalize and append task-flow",
                "purpose": "将完成、部分完成或失败状态写入不可覆盖记录。",
                "method": "生成结构化evidence并调用case_tracker.py record-task。",
                "tools": "case_autolog.py finish",
                "result": summary_zh,
            },
        ],
        "deliverables": deliverables,
        "conclusion_zh": summary_zh,
        "conclusion_en": summary_en,
        "limits_zh": args.limits_zh or "自动记录不能推断未写入文件且未开启会话的纯对话内容。",
        "limits_en": args.limits_en or (
            "Automation cannot infer a conversation that changed no files and never opened a session."
        ),
        "checks": [
            {
                "name": "case recording session",
                "method": "before/after snapshot and command exit status",
                "result": status,
                "note": str(changes["counts"]),
            }
        ],
        "lessons": [
            {
                "symptom": "工作完成但task-flow没有记录。",
                "cause": "执行者绕过case台账入口。",
                "fix": "用case_autolog.py run包裹命令，或在多轮任务中使用begin/finish。",
                "rule": "结束回复前必须执行audit --strict并关闭当前session。",
            }
        ],
        "fastest_path": [
            "开始工作时运行case_autolog.py begin，保存session ID。",
            "实验仍使用case_tracker.py start-run和finish-run。",
            "结束前运行case_autolog.py finish和audit --strict。",
        ],
        "references": [
            str(root / "CASE_MANIFEST.json"),
            str(ledger_root(root) / "archive" / f"{session['session_id']}.json"),
        ],
    }


def finish_session(args: argparse.Namespace) -> Path:
    root = case_root(args.case_root)
    session_path = resolve_session(root, args.session)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    changes = changed_paths(session["before"], snapshot(root))
    evidence = build_task_evidence(root, session, args, changes)
    archive_path = ledger_root(root) / "archive" / session_path.name
    evidence_path = ledger_root(root) / "evidence" / session_path.name
    session["finished_at"] = now().isoformat(timespec="seconds")
    session["status"] = args.status
    session["summary_zh"] = evidence["conclusion_zh"]
    session["summary_en"] = evidence["conclusion_en"]
    session["changes"] = changes
    atomic_json(archive_path, session)
    atomic_json(evidence_path, evidence)
    tracker = root / "tools" / "case_tracker.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(tracker),
            "record-task",
            "--case-root",
            str(root),
            "--evidence-json",
            str(evidence_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"ERROR: task-flow recording failed:\n{completed.stdout}{completed.stderr}"
        )
    session_path.unlink()
    atomic_json(
        recorded_state_path(root),
        {
            "schema_version": SCHEMA_VERSION,
            "recorded_at": now().isoformat(timespec="seconds"),
            "session_id": session["session_id"],
            "snapshot": snapshot(root),
        },
    )
    print(completed.stdout.strip())
    return archive_path


def command_run(args: argparse.Namespace) -> None:
    if not args.command:
        raise SystemExit("ERROR: run requires a command after --")
    session_path, session = start_session(args)
    root = case_root(args.case_root)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    session["command"] = command
    atomic_json(session_path, session)
    log_path = ledger_root(root) / "logs" / f"{session['session_id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            cwd=root,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
    args.session = session["session_id"]
    args.status = "complete" if completed.returncode == 0 else "failed"
    args.deliverable = list(args.deliverable) + [str(log_path)]
    if not args.summary_zh:
        args.summary_zh = f"命令执行结束，exit_code={completed.returncode}。"
    if not args.summary_en:
        args.summary_en = f"Command finished with exit_code={completed.returncode}."
    finish_session(args)
    raise SystemExit(completed.returncode)


def run_has_outputs(run_dir: Path) -> bool:
    for relative in ("logs", "rollouts", "results"):
        directory = run_dir / relative
        if directory.is_dir() and any(path.is_file() for path in directory.rglob("*")):
            return True
    return False


def recording_gaps(root: Path, stale_minutes: int) -> list[str]:
    gaps = []
    cutoff = now() - dt.timedelta(minutes=stale_minutes)
    for path in sorted((ledger_root(root) / "open").glob("*.json")):
        session = json.loads(path.read_text(encoding="utf-8"))
        started = dt.datetime.fromisoformat(session["started_at"])
        age = now() - started
        label = "stale" if started < cutoff else "open"
        gaps.append(
            f"{label} autolog session: {session['session_id']} "
            f"({int(age.total_seconds() // 60)} min)"
        )
    for manifest_path in sorted((root / "runs").glob("**/run_manifest.json")):
        run = json.loads(manifest_path.read_text(encoding="utf-8"))
        if run.get("status") in {"planned", "running"} and run_has_outputs(
            manifest_path.parent
        ):
            gaps.append(
                f"run has outputs but is not finalized: "
                f"{run.get('run_id', manifest_path.parent.name)} "
                f"status={run.get('status')}"
            )
    for status_path in sorted((root / "runs").glob("**/status.json")):
        if not (status_path.parent / "run_manifest.json").is_file():
            gaps.append(f"orphan run status without manifest: {status_path.parent}")
    state_path = recorded_state_path(root)
    if not state_path.is_file():
        gaps.append(
            "recorded file baseline is missing; run one autolog begin/finish or run session"
        )
    else:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        changes = changed_paths(state.get("snapshot", {}), snapshot(root))
        total = sum(changes["counts"].values())
        if total:
            gaps.append(
                "tracked files changed outside the last finalized record: "
                f"{changes['counts']}; {summarize_changes(changes, limit=12)}"
            )
    return gaps


def audit(args: argparse.Namespace) -> None:
    root = case_root(args.case_root)
    gaps = recording_gaps(root, args.stale_minutes)
    lines = [
        "# 自动记录巡检 / Automatic Recording Audit",
        "",
        f"- Case: `{root}`",
        f"- Checked at: `{now().isoformat(timespec='seconds')}`",
        f"- Open or missing-finalization items: `{len(gaps)}`",
        "",
    ]
    if gaps:
        lines.extend(f"- {item}" for item in gaps)
    else:
        lines.append("- OK: no open sessions or unfinalized runs with outputs.")
    report = root / "RECORDING_AUDIT.md"
    atomic_text(report, "\n".join(lines) + "\n")
    print(report)
    for gap in gaps:
        print(f"GAP: {gap}", file=sys.stderr)
    if gaps and args.strict:
        raise SystemExit(1)


def add_session_metadata(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-root", required=True)
    parser.add_argument("--title-zh", required=True)
    parser.add_argument("--title-en", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--objective-zh", default="")
    parser.add_argument("--objective-en", default="")
    parser.add_argument("--scope-zh", default="")
    parser.add_argument("--scope-en", default="")


def add_finish_metadata(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--summary-zh", default="")
    parser.add_argument("--summary-en", default="")
    parser.add_argument("--limits-zh", default="")
    parser.add_argument("--limits-en", default="")
    parser.add_argument("--deliverable", action="append", default=[])


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command_name", required=True)

    begin = sub.add_parser("begin", help="Open a multi-turn recording session")
    add_session_metadata(begin)
    begin.set_defaults(func=lambda args: print(start_session(args)[1]["session_id"]))

    finish = sub.add_parser("finish", help="Close a session and append task-flow")
    finish.add_argument("--case-root", required=True)
    finish.add_argument("--session", required=True)
    finish.add_argument(
        "--status", choices=("complete", "partial", "failed"), required=True
    )
    add_finish_metadata(finish)
    finish.set_defaults(func=finish_session)

    run = sub.add_parser("run", help="Run a command and always append task-flow")
    add_session_metadata(run)
    add_finish_metadata(run)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    audit_parser = sub.add_parser("audit", help="Detect recording gaps")
    audit_parser.add_argument("--case-root", required=True)
    audit_parser.add_argument("--stale-minutes", type=int, default=60)
    audit_parser.add_argument("--strict", action="store_true")
    audit_parser.set_defaults(func=audit)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
