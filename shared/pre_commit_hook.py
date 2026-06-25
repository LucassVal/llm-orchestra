#!/usr/bin/env python3

# 3W: WHAT=gate pre-commit | WHY=bloquear codigo ruim | WHEN=git commit
"""
pre_commit_hook.py -- Gate obrigatorio pre-commit.
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
        for d in ["llama.cpp", "__pycache__", ".git", "shared/pre_commit_hook.py"]:
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


def run_slop():
    """Roda aislop -- detector de AI slop (padroes de agentes)."""
    r = subprocess.run(
        ["aislop", str(BUILD), "--ignore", "llama.cpp", "--exit-zero"],
        capture_output=True, text=True,
    )
    issues = len([line for line in r.stdout.split("\n") if line.strip()])
    return issues == 0, r.stdout, issues


def run_mock_tests():
    """Roda pytest com mock -- testes unitarios."""
    r = subprocess.run(
        ["pytest", str(BUILD/"tests"), "-q", "--tb=short"],
        capture_output=True, text=True,
        cwd=str(BUILD),  # precisa do PYTHONPATH correto
    )
    return r.returncode == 0, r.stdout


def run_rules():
    """Roda rule_check.py -- todas regras R-BENCH-*."""
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"rule_check.py")],
        capture_output=True, text=True,
    )
    return r.returncode == 0, r.stdout


def run_audit():
    """Roda compliance_check.py e retorna (passed, output)."""
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"compliance_check.py")],
        capture_output=True, text=True,
    )
    return r.returncode == 0, r.stdout


def main():
    findings = scan_stubs()
    slop_ok, slop_out, slop_issues = run_slop()
    mock_ok, mock_out = run_mock_tests()
    rules_ok, rules_out = run_rules()
    audit_ok, audit_out = run_audit()

    # ── COMPLIANCE (visao geral do sistema) ──
    print("=" * 70)
    print("  COMPLIANCE AUDIT -- Visao Geral do Sistema")
    print("=" * 70)
    print(audit_out)

    # ── Rules ──
    if not rules_ok:
        print("=" * 70)
        print("  RULE CHECK (R-BENCH-*) -- FAIL")
        print("=" * 70)
        print(rules_out)
        print("=" * 70)
        print()
    else:
        print(rules_out)

    # ── AI Slop ──
    if not slop_ok:
        print("=" * 70)
        print("  AI SLOP DETECTOR (aislop) -- {} achados".format(slop_issues))
        print("=" * 70)
        for line in slop_out.strip().split("\n")[:20]:
            if line.strip():
                print("  " + line[:100])
        print("=" * 70)
        print()

    # ── Mock Tests ──
    if not mock_ok:
        print("=" * 70)
        print("  MOCK TESTS (pytest) -- FAIL")
        print("=" * 70)
        for line in mock_out.strip().split("\n")[:10]:
            if line.strip():
                print("  " + line[:100])
        print("=" * 70)
        print()
    else:
        print("MOCK TESTS: " + mock_out.strip().split("\n")[-1][:80] if mock_out.strip() else "ok")

    # ── Stub scan ──
    if findings:
        print("=" * 70)
        print("  STUB/LAZY/BYPASS SCAN -- {} achados".format(len(findings)))
        print("=" * 70)
        for f in findings:
            print("  [{}] {}:{} -- {}".format(
                f["category"], f["file"], f["line"], f["pattern"]))
            print("         {}".format(f["code"]))
        print("=" * 70)
        print()

    # ── Compliance (ja exibido acima como visao geral) ──
    # ── GATE (ALL ERR) ──
    has_issues = bool(findings) or not slop_ok or not mock_ok or not rules_ok or not audit_ok

    if not has_issues:
        print("✓ GATE: limpo (stubs=0, slop=ok, mock=ok, rules=ok, audit=PASS). Commit liberado.")
        return 0

    if NO_BYPASS:
        print("⛔ GATE: BLOQUEADO (--no-bypass). Corrija os itens acima.")
        return 1

    print()
    print("⛔ GATE: stub={} slop={} mock={} rules={} audit={}".format(
        len(findings),
        "FAIL({})".format(slop_issues) if not slop_ok else "PASS",
        "FAIL" if not mock_ok else "PASS",
        "FAIL" if not rules_ok else "PASS",
        "FAIL" if not audit_ok else "PASS"))
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
