#!/usr/bin/env python3
"""Validate the simple HorseShows.pbix 8-hour refresh installers."""
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
    REPO / "automation" / "Refresh-HorseShowsPbix-Simple.ps1",
    REPO / "automation" / "Run-PbixRefresh.cmd",
    REPO / "automation" / "Run-HorseShowsPbixRefreshAgent.ps1",
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
    agent = (REPO / "automation" / "Run-HorseShowsPbixRefreshAgent.ps1").read_text(
        encoding="utf-8"
    )
    simple = (REPO / "automation" / "Refresh-HorseShowsPbix-Simple.ps1").read_text(
        encoding="utf-8"
    )
    docs = (REPO / ".cursor" / "automations" / "refresh-horseshows-pbix.md").read_text(
        encoding="utf-8"
    )
    run_cmd = (REPO / "automation" / "Run-PbixRefresh.cmd").read_text(encoding="utf-8")

    if "Refresh-HorseShowsPbix-Simple.ps1" not in paste:
        fail("PASTE must copy Refresh-HorseShowsPbix-Simple.ps1")
    if "Copy-Item" not in paste:
        fail("PASTE must Copy-Item the simple script into ResultsAutomation")
    if "Start-ScheduledTask" in paste:
        fail("PASTE must not use Start-ScheduledTask for the immediate run")
    if "& $src" not in paste:
        fail("PASTE must run simple script in-session")

    if not re.search(r"\$RepeatHours\s*=\s*8\b", register):
        fail("scheduled task default is not every 8 hours")
    if "Refresh-HorseShowsPbix-Simple.ps1" not in register or "Copy-Item" not in register:
        fail("Register must copy Refresh-HorseShowsPbix-Simple.ps1")
    if "LogonType Interactive" not in register:
        fail("Register must use interactive logon")
    if "IgnoreNew" not in register:
        fail("Register must IgnoreNew overlapping runs")
    if "Start-ScheduledTask" in register:
        fail("Register must not Start-ScheduledTask for InvokeNow")

    if "Refresh-HorseShowsPbix-Simple.ps1" not in agent:
        fail("agent shim must call Refresh-HorseShowsPbix-Simple.ps1")
    if "Refresh-HorseShowsPbix.ps1" in agent.split("SYNOPSIS", 1)[-1] and "TOM" in agent:
        pass  # description may mention old path
    if "Invoke-DirectRefresh" in agent or "& $refreshScript" in agent:
        fail("agent must not call old TOM refresh")

    for needle in (
        "SetForegroundWindow",
        "Invoke-TomFullRefresh",
        "Install-TomFromNuget",
        "msmdsrv",
        "SendWait",
        "cmd.exe",
        "LastWriteTimeUtc",
        "PBIDesktop",
    ):
        if needle not in simple:
            fail(f"simple refresh missing {needle!r}")

    if "Refresh-HorseShowsPbix-Simple.ps1" not in run_cmd:
        fail("Run-PbixRefresh.cmd must launch the simple script")
    if "Run-PbixRefresh.cmd" not in docs:
        fail("docs must mention Run-PbixRefresh.cmd")

    for ps1_name in (
        "Refresh-HorseShowsPbix-Simple.ps1",
        "Refresh-HorseShowsPbix.ps1",
        "Run-HorseShowsPbixRefreshAgent.ps1",
        "Enable-HorseShowsPbixRefresh.ps1",
        "Register-HorseShowsPbixRefreshTask.ps1",
        "PASTE_TO_INSTALL.ps1",
    ):
        raw = (REPO / "automation" / ps1_name).read_bytes()
        if any(b > 127 for b in raw):
            fail(f"{ps1_name} must be ASCII-only")

    pbix = REPO / "PowerBI" / "HorseShows.pbix"
    first_line = pbix.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    if pbix.stat().st_size < 1024 and first_line.startswith("version https://git-lfs.github.com/"):
        print("NOTE: PowerBI/HorseShows.pbix is a Git LFS pointer in this checkout.")

    print("OK: simple HorseShows.pbix refresh installers are consistent.")
    print("    manual:  automation/Run-PbixRefresh.cmd")
    print("    script:  automation/Refresh-HorseShowsPbix-Simple.ps1")
    print("    task:    ResultsAutomation\\HorseShowsPbixRefresh\\Refresh.ps1")
    print(f"    cwd:     {REPO}")
    print(f"    os:      {os.name}")


if __name__ == "__main__":
    sys.exit(main())
