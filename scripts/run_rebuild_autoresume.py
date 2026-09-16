"""
Supervise HSO-first rebuild: if progress stalls, kill and auto-resume with skips.

Uses merge_rebuild_snapshots/rebuild_heartbeat.txt (updated each classdetail row)
plus "Reattached judges N:" log lines to know which shows are safely done.

Archives stay enabled (default rebuild behavior).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEARTBEAT = REPO / "merge_rebuild_snapshots" / "rebuild_heartbeat.txt"
SKIP_STATE = REPO / "merge_rebuild_snapshots" / "rebuild_autoresume_skips.txt"
LOG_DIR = REPO / "merge_rebuild_snapshots"
REBUILD = REPO / "scripts" / "rebuild_merged_show_hso_first.py"

RE_REATTACHED = re.compile(r"Reattached judges (\d+):")
RE_REBUILD_SHOW = re.compile(r"Rebuild ShowListID=(\d+)")


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] [AUTOREUME] {msg}", flush=True)


def load_skips(path: Path) -> list[int]:
    if not path.exists():
        return []
    out: list[int] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(int(line))
        except ValueError:
            continue
    return sorted(set(out))


def save_skips(path: Path, skips: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(str(i) for i in sorted(set(skips))) + "\n", encoding="utf-8")


def heartbeat_age_sec() -> float | None:
    if not HEARTBEAT.exists():
        return None
    return time.time() - HEARTBEAT.stat().st_mtime


def kill_rebuild_tree() -> None:
    # Kill python rebuild + chromedriver
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.CommandLine -and ($_.CommandLine -match 'rebuild_merged_show_hso_first') } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
                    "Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as e:
        log(f"kill warning: {e}")


def harvest_completed_from_log(log_path: Path, skips: list[int]) -> list[int]:
    if not log_path.exists():
        return skips
    found = set(skips)
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return skips
    for m in RE_REATTACHED.finditer(text):
        found.add(int(m.group(1)))
    return sorted(found)


def build_cmd(skips: list[int], extra: list[str]) -> list[str]:
    cmd = [sys.executable, str(REBUILD), "--apply-all"]
    for s in skips:
        cmd.extend(["--skip-show-list-id", str(s)])
    cmd.extend(extra)
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-resume stalled HSO rebuild")
    parser.add_argument(
        "--stall-seconds",
        type=int,
        default=int(os.environ.get("HSO_STALL_SECONDS", "600")),
        help="No heartbeat progress for this many seconds => stall (default 600)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="How often to check heartbeat",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=500,
        help="Safety cap on auto-restarts",
    )
    parser.add_argument(
        "--skip-show-list-id",
        type=int,
        action="append",
        default=[],
        help="Initial skips (also merged with skip-state file)",
    )
    parser.add_argument(
        "rebuild_args",
        nargs="*",
        help="Extra args passed through to rebuild script",
    )
    args = parser.parse_args()

    skips = load_skips(SKIP_STATE)
    skips = sorted(set(skips) | set(args.skip_show_list_id or []))
    save_skips(SKIP_STATE, skips)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    restarts = 0

    while True:
        run_log = LOG_DIR / f"rebuild_autoresume_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        cmd = build_cmd(skips, args.rebuild_args)
        log(f"starting rebuild (skips={len(skips)}) log={run_log.name}")
        log(f"cmd: {' '.join(cmd)}")

        # Fresh heartbeat so we don't immediately treat old file as live
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(f"{ts()} supervisor_start\n", encoding="utf-8")

        with open(run_log, "w", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO),
                stdout=lf,
                stderr=subprocess.STDOUT,
                text=True,
            )

        stalled = False
        rc = None
        while True:
            rc = proc.poll()
            if rc is not None:
                log(f"rebuild exited rc={rc}")
                break

            age = heartbeat_age_sec()
            if age is not None and age > args.stall_seconds:
                log(
                    f"STALL detected: heartbeat age {age:.0f}s > {args.stall_seconds}s — killing and resuming"
                )
                stalled = True
                try:
                    proc.kill()
                except Exception:
                    pass
                kill_rebuild_tree()
                time.sleep(3)
                break

            time.sleep(args.poll_seconds)

        # Harvest completed shows from this run's log
        skips = harvest_completed_from_log(run_log, skips)
        save_skips(SKIP_STATE, skips)
        log(f"skip list now has {len(skips)} shows")

        if not stalled:
            # Clean exit (success or hard error without stall)
            if rc == 0:
                log("rebuild completed successfully")
                return 0
            # Non-zero without stall: still try resume a few times unless maxed
            restarts += 1
            if restarts > args.max_restarts:
                log("max restarts reached after non-zero exits")
                return rc or 1
            log(f"non-zero exit; auto-resume attempt {restarts}")
            kill_rebuild_tree()
            time.sleep(2)
            continue

        restarts += 1
        if restarts > args.max_restarts:
            log("max restarts reached after stalls")
            return 2
        log(f"auto-resume after stall (restart #{restarts})")
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
