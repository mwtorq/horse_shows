#!/usr/bin/env python3
"""Validate the simple HorseShows.pbix 8-hour refresh installers.

Does not refresh the pbix (needs Windows + Power BI Desktop). Checks that
paste/register wiring stays consistent: ResultsAutomation Refresh.ps1 + Run.cmd,
interactive scheduled task, no OneDrive -File, in-session InvokeNow.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED = [
    REPO / "PowerBI" / "HorseShows.pbix",
    REPO / "automation" / "PASTE_TO_INSTALL.ps1",
    REPO / "automation" / "Register-HorseShowsPbixRefreshTask.ps1",
    REPO / "automation" / "Register-HorseShowsPbixRefreshTask.cmd",
    REPO / "automation" / "Enable-HorseShowsPbixRefresh.ps1",
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

    paste = (REPO / "automation" / "PASTE_TO_INSTALL.ps1").read_text(encoding="utf-8")
    register = (REPO / "automation" / "Register-HorseShowsPbixRefreshTask.ps1").read_text(
        encoding="utf-8"
    )
    enable = (REPO / "automation" / "Enable-HorseShowsPbixRefresh.ps1").read_text(encoding="utf-8")
    docs = (REPO / ".cursor" / "automations" / "refresh-horseshows-pbix.md").read_text(
        encoding="utf-8"
    )

    for label, text in (("PASTE", paste), ("Register", register)):
        if "ResultsAutomation" not in text or "Refresh.ps1" not in text:
            fail(f"{label} must install ResultsAutomation\\HorseShowsPbixRefresh\\Refresh.ps1")
        if "Run.cmd" not in text:
            fail(f"{label} must install Run.cmd")
        if "SendWait" not in text and "SendKeys" not in text:
            fail(f"{label} must drive Power BI via SendKeys")
        if "cmd.exe" not in text or "start" not in text.lower():
            fail(f"{label} must open the pbix via cmd start")
        if "LogonType Interactive" not in text:
            fail(f"{label} must register an interactive logon task")
        if "IgnoreNew" not in text:
            fail(f"{label} must IgnoreNew overlapping runs")
        # Manual run must execute in-session; Start-ScheduledTask breaks SendKeys.
        if re.search(r"if\s*\(\$?InvokeNow\)[\s\S]*Start-ScheduledTask", text) or (
            label == "PASTE" and "Start-ScheduledTask" in text
        ):
            fail(f"{label} must not use Start-ScheduledTask for the immediate run")
        if "& $refreshPath" not in text and "& $refresh" not in text:
            fail(f"{label} must invoke Refresh.ps1 in-session for run-now")

    if not re.search(r"\$RepeatHours\s*=\s*8\b", register):
        fail("scheduled task default is not every 8 hours")
    if "DryRun.ps1" in enable or "Run.ps1" in enable:
        fail("Enable must not reference removed DryRun.ps1 / Run.ps1")
    if "Refresh.ps1" not in enable or "Run.cmd" not in enable:
        fail("Enable must point at Refresh.ps1 / Run.cmd")
    if "Run.cmd" not in docs or "Refresh.ps1" not in docs:
        fail("automation doc must document Run.cmd and Refresh.ps1")

    pbix = REPO / "PowerBI" / "HorseShows.pbix"
    first_line = pbix.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    if pbix.stat().st_size < 1024 and first_line.startswith("version https://git-lfs.github.com/"):
        print("NOTE: PowerBI/HorseShows.pbix is a Git LFS pointer in this checkout.")
        print('      On the Windows machine run: git lfs pull --include="PowerBI/HorseShows.pbix"')

    print("OK: simple HorseShows.pbix refresh installers are consistent.")
    print("    interval: 8 hours")
    print("    launcher: ResultsAutomation\\HorseShowsPbixRefresh\\Refresh.ps1")
    print("    run now:  ResultsAutomation\\HorseShowsPbixRefresh\\Run.cmd")
    print(f"    cwd:      {REPO}")
    print(f"    os:       {os.name}")


if __name__ == "__main__":
    sys.exit(main())
