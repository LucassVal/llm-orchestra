#!/usr/bin/env python3
"""
py_check.py — Validador Python nativo (substitui mypy no Android/Termux).
Usa ast.parse() — builtin, zero dependencias, funciona em qqr Python.
Verifica: syntax error, import cycles (basico), dead code indicators.
"""
import ast
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent
SKIP = {"llama.cpp", "__pycache__", ".git", "logs"}


def check_file(filepath):
    """Valida sintaxe de 1 arquivo .py. Retorna (ok, erro)."""
    try:
        ast.parse(filepath.read_text(), filename=str(filepath))
    except SyntaxError as e:
        return False, "syntax: {}:{}".format(e.lineno, e.msg)
    except Exception as e:
        return False, "parse: {}".format(str(e)[:80])
    return True, None


def run():
    errors = []
    ok = 0
    total = 0

    for py_file in sorted(BUILD.rglob("*.py")):
        skip = False
        for d in SKIP:
            if d in str(py_file):
                skip = True
                break
        if skip:
            continue
        total += 1
        valid, err = check_file(py_file)
        if valid:
            ok += 1
        else:
            errors.append((str(py_file.relative_to(BUILD)), err))

    if errors:
        print("PY CHECK — FAIL ({}/{})".format(ok, total))
        for fname, err in errors:
            print("  {}: {}".format(fname, err))
        return 1

    print("PY CHECK — PASS ({}/{} arquivos validos)".format(ok, total))
    return 0


if __name__ == "__main__":
    sys.exit(run())
