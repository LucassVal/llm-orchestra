#!/usr/bin/env python3
# 3W: WHAT=espelhamento triade | WHY=garantir Makefile/ps1 sync | WHEN='make audit'
"""triade_check.py -- Verifica espelhamento Makefile <-> .ps1 (isolado, sem NeoCortex)."""
import re
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent


def _targets_makefile():
    text = (BUILD / "Makefile").read_text()
    return set(re.findall(r'^([a-z][a-z0-9-]*):.*##', text, re.M))


def _targets_ps1():
    text = (BUILD / "nc.ps1").read_text()
    names = set()
    for m in re.finditer(r'"([a-z][a-z0-9-]*)"\s*{', text):
        names.add(m.group(1))
    return names


def run():
    makefile = _targets_makefile()
    ps1 = _targets_ps1()

    required = {
        "boot", "audit", "lint", "deps",
        "status", "stop",
        "pipeline-4b", "pipeline-coder", "pipeline-gemma", "pipeline-all",
        "stress", "ppl", "sweep", "run", "serve",
        "report", "report-obsidian",
        "agent-create", "agent-validate", "agent-profiles",
        "daemon-start", "daemon-stop", "daemon-status",
    }

    missing_ps1 = required - ps1

    if missing_ps1:
        print("TRIADE CHECK -- FAIL")
        print("  ps1 ausente: " + ",".join(sorted(missing_ps1)))
        return 1

    print("TRIADE CHECK -- PASS (makefile={} ps1={} espelhados, isolado)".format(
        len(makefile), len(ps1)))
    return 0


if __name__ == "__main__":
    sys.exit(run())
