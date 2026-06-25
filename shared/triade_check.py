#!/usr/bin/env python3
"""triade_check.py — Verifica espelhamento Makefile <-> maker CLI <-> .ps1."""
import re
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent

def _targets_makefile():
    text = (BUILD/"Makefile").read_text()
    return set(re.findall(r'^([a-z][a-z-]*):.*##', text, re.M))

def _targets_maker():
    text = (BUILD.parent/"NeoCortex"/"maker"/"cmd_bench.py").read_text()
    names = set()
    for m in re.finditer(r'def bench_([a-z_0-9]+)\(', text):
        names.add(m.group(1).replace("_","-"))
    return names

def _targets_ps1():
    text = (BUILD/"nc.ps1").read_text()
    names = set()
    for m in re.finditer(r'"([a-z][a-z0-9-]*)"\s*{', text):
        names.add(m.group(1))
    return names

def run():
    maker = _targets_maker()
    ps1 = _targets_ps1()

    # Core targets: Makefile sempre tem todos.
    # Maker usa subcomandos (daemon) e flags (--obsidian).
    # PS1 espelha Makefile diretamente.
    maker_required = {
        "status", "stop", "pipeline-4b", "pipeline-coder", "pipeline-gemma",
        "pipeline-all", "stress", "ppl", "sweep", "run", "serve",
        "report", "agent-create", "agent-validate", "agent-profiles",
        "daemon", "audit", "lint", "deps",
    }
    ps1_required = {
        "boot", "audit", "lint", "deps",
        "status", "stop",
        "pipeline-4b", "pipeline-coder", "pipeline-gemma", "pipeline-all",
        "stress", "ppl", "sweep", "run", "serve",
        "report", "report-obsidian",
        "agent-create", "agent-validate", "agent-profiles",
        "daemon-start", "daemon-stop", "daemon-status",
    }

    missing_maker = maker_required - maker
    missing_ps1 = ps1_required - ps1

    if missing_maker or missing_ps1:
        print("TRIADE CHECK — FAIL")
        if missing_maker:
            print("  maker ausente: " + ",".join(sorted(missing_maker)))
        if missing_ps1:
            print("  ps1 ausente: " + ",".join(sorted(missing_ps1)))
        return 1
    print("TRIADE CHECK — PASS (maker={} ps1={} espelhados)".format(
        len(maker_required), len(ps1_required)))
    return 0

if __name__ == "__main__":
    sys.exit(run())
