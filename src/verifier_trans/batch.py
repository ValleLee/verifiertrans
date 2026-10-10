#!/usr/bin/env python3
"""Run prepared conversion workspaces with a bounded level of concurrency."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


from .paths import DEFAULT_CONFIG, DEFAULT_ENV, DEFAULT_RUNS_ROOT, PROJECT_ROOT


def run_one(workspace: Path, credentials: Path, config: Path, log_dir: Path) -> dict:
    from .paths import attempt_from_path

    attempt = attempt_from_path(workspace)
    log_path = log_dir / f"{attempt.root.parent.parent.parent.name}-{attempt.root.name}.log"
    started = datetime.now(timezone.utc).isoformat()
    command = [
        sys.executable,
        "-u",
        "-m",
        "verifier_trans",
        "run",
        "--workspace",
        str(attempt.root),
        "--env-file",
        str(credentials),
        "--config",
        str(config),
        "--allow-external-model-data",
    ]
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    report_path = attempt.control / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return {
        "workspace": str(attempt.root),
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "returncode": result.returncode,
        "status": report.get("status", "NO_REPORT"),
        "report": str(report_path),
        "log": str(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", action="append", type=Path, required=True)
    parser.add_argument(
        "--credentials", "--env-file", dest="credentials", type=Path, default=DEFAULT_ENV
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--summary", type=Path, default=DEFAULT_RUNS_ROOT / "batch_summary.json")
    args = parser.parse_args()

    workspaces = [path.resolve() for path in args.workspace]
    if len(set(workspaces)) != len(workspaces):
        raise SystemExit("duplicate workspace supplied")
    if not 1 <= args.max_workers <= len(workspaces):
        raise SystemExit("max-workers must be between 1 and the number of workspaces")
    from .paths import attempt_from_path

    missing = []
    for path in workspaces:
        try:
            prepared = (attempt_from_path(path).prepare / "metadata.json").is_file()
        except ValueError:
            prepared = False
        if not prepared:
            missing.append(str(path))
    if missing:
        raise SystemExit("unprepared workspaces: " + ", ".join(missing))

    log_dir = args.summary.parent / "batch_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=args.max_workers)
    futures = {}
    try:
        futures = {
            pool.submit(run_one, workspace, args.credentials.resolve(), args.config.resolve(), log_dir): workspace
            for workspace in workspaces
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)

    results.sort(key=lambda item: item["workspace"])
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested": len(workspaces),
        "max_workers": args.max_workers,
        "results": results,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(item["status"] == "VERIFIED" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
