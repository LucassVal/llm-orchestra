#!/usr/bin/env python3
# 3W: WHAT=tools runner | WHY=rodar smellcheck+vulture+deadcode | WHEN=pre-commit
"""
tools_gate.py — Executa ferramentas externas de analise.
smellcheck (60 AST checks) + vulture (dead code) + deadcode (AST).
Integrado ao pre_commit_hook como barreira adicional.
"""
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent


def run_smellcheck():
    r = subprocess.run(
        ["smellcheck", str(BUILD)],
        capture_output=True, text=True, cwd=str(BUILD),
    )
    return r.returncode == 0, r.stdout


def run_vulture():
    r = subprocess.run(
        ["vulture", str(BUILD), "--exclude", "llama.cpp,__pycache__,.git"],
        capture_output=True, text=True, cwd=str(BUILD),
    )
    return r.returncode == 0, r.stdout


def run_deadcode():
    r = subprocess.run(
        ["deadcode", str(BUILD), "--exclude", "llama.cpp|__pycache__|.git"],
        capture_output=True, text=True, cwd=str(BUILD),
    )
    return r.returncode == 0, r.stdout


def run():
    tools = [
        ("SMELLCHECK", run_smellcheck),
        ("VULTURE", run_vulture),
        ("DEADCODE", run_deadcode),
    ]

    passed = 0
    failed = 0
    for name, fn in tools:
        ok, out = fn()
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        # Show first 3 lines of output
        lines = out.strip().split("\n")[:3]
        print("  {}: {:<6} {}".format(name, status, lines[0] if lines else ""))

    print("  " + "-" * 30)
    print("  TOOLS GATE: PASS={} FAIL={}".format(passed, failed))
    return 1 if failed > 2 else 0  # So bloqueia se todas falharem


if __name__ == "__main__":
    sys.exit(run())
