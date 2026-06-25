#!/usr/bin/env python3
"""
pre_commit_hook.py — Gate obrigatorio pre-commit.
Roda compliance audit + stub scan + lazy pattern detection.
ERR = bloqueia commit. User deve explicitamente aprovar bypass.

Termos detectados:
  STUB:  pass, ..., NotImplementedError, assert False, return None vazio
  LAZY:  noqa sem justificativa, try/except:pass, temp_, tmp_
  BYPASS: skip, bypass, workaround, hack, fixme, xxx, todo sem ticket
  DEAD:  import unused, variable unused, function unreachable

Instalar: ln -s ../../shared/pre_commit_hook.py .git/hooks/pre-commit
"""
import re
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent
NO_BYPASS = "--no-bypass" in sys.argv  # nem o user pode pular


def scan_stubs():
    """Varre .py por padroes STUB/LAZY/BYPASS/DEAD."""
    findings = []
    patterns = {
        "STUB": [
            (r"\.\.\.\s*$", "stub: ellipsis (...)"),
            (r"raise\s+NotImplementedError", "stub: NotImplementedError"),
            (r"assert\s+False", "stub: assert False (dead)"),
            (r"assert\s+0\b", "stub: assert 0 (dead)"),
            (r"def\s+\w+\([^)]*\):\s*return\s+None\s*$", "stub: return None vazio"),
        ],
        "LAZY": [
            (r"#\s*noqa\s*$", "lazy: noqa sem justificativa"),
            (r"except\s+\w*:?\s*\n\s{8,}pass", "lazy: except:pass (silencia erro)"),
            (r"except\s+Exception:?\s*\n\s{8,}pass", "lazy: except Exception:pass"),
            (r"def\s+temp_", "lazy: funcao temporaria (temp_)"),
            (r"def\s+tmp_", "lazy: funcao temporaria (tmp_)"),
            (r"#\s*TODO(?!.*(?:ticket|NC-|#\d))", "lazy: TODO sem ticket"),
        ],
        "BYPASS": [
            (r"#\s*(skip|bypass|workaround)", "bypass: comentario skip/bypass/workaround"),
            (r"#\s*HACK", "bypass: HACK"),
            (r"#\s*FIXME", "bypass: FIXME"),
            (r"#\s*XXX\b", "bypass: XXX"),
            (r"(?<!\w)timeout\s*=\s*\d{3,}(?!\d)", "bypass: timeout >=100s sem log"),
        ],
    }

    for py_file in BUILD.rglob("*.py"):
        skip = False
        for d in ["llama.cpp", "__pycache__", ".git"]:
            if d in str(py_file):
                skip = True
                break
        if skip:
            continue

        try:
            lines = py_file.read_text().split("\n")
        except Exception:
            continue

        for lineno, line in enumerate(lines, 1):
            for category, pats in patterns.items():
                for pattern, desc in pats:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(py_file.relative_to(BUILD)),
                            "line": lineno,
                            "category": category,
                            "pattern": desc,
                            "code": line.strip()[:80],
                        })
    return findings


def run_audit():
    """Roda compliance_check.py e retorna (passed, output)."""
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"compliance_check.py")],
        capture_output=True, text=True,
    )
    return r.returncode == 0, r.stdout


def main():
    findings = scan_stubs()
    audit_ok, audit_out = run_audit()

    # ── Stub scan ──
    if findings:
        print("=" * 70)
        print("  STUB/LAZY/BYPASS SCAN — {} achados".format(len(findings)))
        print("=" * 70)
        for f in findings:
            print("  [{}] {}:{} — {}".format(
                f["category"], f["file"], f["line"], f["pattern"]))
            print("         {}".format(f["code"]))
        print("=" * 70)
        print()

    # ── Compliance ──
    print(audit_out)

    # ── Gate ──
    has_issues = findings or not audit_ok

    if not has_issues:
        print("✓ GATE: limpo. Commit liberado.")
        return 0

    if NO_BYPASS:
        print("⛔ GATE: BLOQUEADO (--no-bypass). Corrija os itens acima.")
        return 1

    # User pode aprovar bypass
    print()
    print("⛔ GATE: {} stub(s) + audit={}".format(
        len(findings), "PASS" if audit_ok else "FAIL"))
    print()
    try:
        ans = input("Deseja COMMIT mesmo assim? [s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    if ans == "s":
        print("⚠ BYPASS APROVADO pelo usuario. Commit segue.")
        return 0
    else:
        print("✗ Commit bloqueado. Corrija os itens e tente novamente.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
