#!/usr/bin/env python3
"""Validate the HorseShows.pbix local Cursor agent automation files.

This does not refresh the pbix (that needs Windows + Power BI Desktop). It checks
that the scheduled-agent wiring is complete and internally consistent.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED = [
    REPO / "PowerBI" / "HorseShows.pbix",
    REPO / "automation" / "Refresh-HorseShowsPbix.ps1",
    REPO / "automation" / "Run-HorseShowsPbixRefreshAgent.ps1",
    REPO / "automation" / "Register-HorseShowsPbixRefreshTask.ps1",
    REPO / "automation" / "Register-HorseShowsPbixRefreshTask.cmd",
    REPO / "automation" / "HorseShowsPbixRefresh.prompt.txt",
    REPO / ".cursor" / "skills" / "refresh-horseshows-pbix" / "SKILL.md",
    REPO / ".cursor" / "automations" / "refresh-horseshows-pbix.md",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    for path in REQUIRED:
        if not path.is_file():
            fail(f"missing {path.relative_to(REPO)}")
        if path.stat().st_size == 0:
            fail(f"empty {path.relative_to(REPO)}")

    skill = (REPO / ".cursor" / "skills" / "refresh-horseshows-pbix" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    if not skill.startswith("---\n"):
        fail("skill is missing YAML frontmatter")
    if "name: refresh-horseshows-pbix" not in skill.split("---", 2)[1]:
        fail("skill name does not match folder")
    if "Refresh-HorseShowsPbix.ps1" not in skill:
        fail("skill does not tell the agent to run Refresh-HorseShowsPbix.ps1")
    if "commit" not in skill.lower() or "HorseShows.pbix" not in skill:
        fail("skill must mention HorseShows.pbix and forbid committing it")

    prompt = (REPO / "automation" / "HorseShowsPbixRefresh.prompt.txt").read_text(encoding="utf-8")
    for needle in (
        "Refresh-HorseShowsPbix.ps1",
        "Do not commit HorseShows.pbix",
        "Do not open a pull request",
        "refresh-horseshows-pbix",
    ):
        if needle not in prompt:
            fail(f"prompt is missing {needle!r}")

    register = (REPO / "automation" / "Register-HorseShowsPbixRefreshTask.ps1").read_text(
        encoding="utf-8"
    )
    if not re.search(r"\$RepeatHours\s*=\s*8\b", register):
        fail("scheduled task default is not every 8 hours")
    if "Run-HorseShowsPbixRefreshAgent.ps1" not in register:
        fail("scheduled task does not launch the Cursor agent runner")
    if "-Command" not in register or "& '" not in register.replace('`', ''):
        fail("scheduled task must use -Command with a single-quoted path (Task Scheduler strips -File quotes)")
    if "LogonType Interactive" not in register:
        fail("scheduled task must use an interactive logon for Power BI Desktop")
    if "IgnoreNew" not in register:
        fail("scheduled task must IgnoreNew overlapping runs")

    runner = (REPO / "automation" / "Run-HorseShowsPbixRefreshAgent.ps1").read_text(encoding="utf-8")
    if "HorseShowsPbixRefresh.prompt.txt" not in runner:
        fail("agent runner does not load the prompt file")
    if "--force" not in runner or "--trust" not in runner:
        fail("agent runner is missing headless Cursor CLI flags")
    if "Refresh-HorseShowsPbix.ps1" not in runner:
        fail("agent runner has no script fallback")

    refresh = (REPO / "automation" / "Refresh-HorseShowsPbix.ps1").read_text(encoding="utf-8")
    for needle in (
        "TMSL",
        "PBIDesktop",
        "msmdsrv.port.txt",
        "SendWait",
        "git-lfs.github.com",
        "DryRun",
    ):
        if needle not in refresh:
            fail(f"refresh script is missing {needle!r}")

    pbix = REPO / "PowerBI" / "HorseShows.pbix"
    first_line = pbix.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    if pbix.stat().st_size < 1024 and first_line.startswith("version https://git-lfs.github.com/"):
        print("NOTE: PowerBI/HorseShows.pbix is a Git LFS pointer in this checkout.")
        print("      On the Windows machine run: git lfs pull --include=\"PowerBI/HorseShows.pbix\"")

    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh:
        cmd = [
            pwsh,
            "-NoProfile",
            "-File",
            str(REPO / "automation" / "Refresh-HorseShowsPbix.ps1"),
            "-DryRun",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            fail(f"DryRun exited {proc.returncode}:\n{output}")
        if "Dry run: paths resolved, no refresh started" not in output:
            fail("DryRun did not print the expected confirmation")
        print("OK: Refresh-HorseShowsPbix.ps1 -DryRun")

        cmd = [
            pwsh,
            "-NoProfile",
            "-File",
            str(REPO / "automation" / "Run-HorseShowsPbixRefreshAgent.ps1"),
            "-DryRun",
            "-SkipAgent",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            fail(f"agent DryRun exited {proc.returncode}:\n{output}")
        print("OK: Run-HorseShowsPbixRefreshAgent.ps1 -DryRun -SkipAgent")
    else:
        print("NOTE: pwsh not on PATH; skipped script DryRun")

    print("OK: HorseShows.pbix Cursor agent automation files are consistent.")
    print(f"    interval: 8 hours")
    print(f"    prompt:   automation/HorseShowsPbixRefresh.prompt.txt")
    print(f"    skill:    .cursor/skills/refresh-horseshows-pbix/SKILL.md")
    print(f"    task:     Register-HorseShowsPbixRefreshTask.ps1")
    print(f"    cwd:      {REPO}")
    print(f"    os:       {os.name}")


if __name__ == "__main__":
    sys.exit(main())
