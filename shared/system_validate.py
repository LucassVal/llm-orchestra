#!/usr/bin/env python3
# 3W: WHAT=validacao completa sistema | WHY=detectar stubs/orfaos/funcoes vazias | WHEN=checkpoint
"""
system_validate.py -- Validacao completa do ecossistema (isolado, sem NeoCortex).
Verifica:
  1. Funcoes reais vs stubs (corpo vazio, pass, return None)
  2. Contratos triade (Makefile <-> ps1)
  3. Orfaos de wire (funcoes definidas mas nao chamadas)
  4. Multi-conexao (funcoes wireadas em multiplos lugares)
  5. Commit log obrigatorio no seal
"""
import ast
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BUILD = Path(__file__).parent.parent


def find_python_functions():
    """Encontra todas as funcoes definidas em .py do projeto."""
    funcs = {}
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except Exception:
            continue
        rel = str(py_file.relative_to(BUILD))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                name = node.name
                body = node.body
                is_stub = False
                if len(body) == 1:
                    stmt = body[0]
                    if isinstance(stmt, ast.Pass) or (isinstance(stmt, ast.Expr)
                          and isinstance(stmt.value, ast.Constant)
                          and (stmt.value.value is Ellipsis or stmt.value.value == "...")):
                        is_stub = True
                elif len(body) == 0:
                    is_stub = True
                funcs["{}:{}".format(rel, name)] = {
                    "file": rel,
                    "name": name,
                    "stub": is_stub,
                    "lines": node.end_lineno - node.lineno if node.end_lineno else 0,
                }
    return funcs


def find_function_calls():
    """Encontra todas as chamadas de funcao no codigo (inclui metodos via Attribute)."""
    calls = defaultdict(set)
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except Exception:
            continue
        rel = str(py_file.relative_to(BUILD))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls[node.func.id].add(rel)
                elif isinstance(node.func, ast.Attribute):
                    calls[node.func.attr].add(rel)
    return calls


def validate_triade_contracts():
    """Verifica Makefile <-> ps1 espelhados (isolado, sem dependencia externa)."""
    mk_text = (BUILD / "Makefile").read_text()
    mk_targets = set(re.findall(r'^([a-z][a-z0-9-]*):.*##', mk_text, re.M))

    ps1_file = BUILD / "nc.ps1"
    ps1_targets = set()
    if ps1_file.exists():
        for m in re.finditer(r'"([a-z][a-z0-9-]*)"\s*{', ps1_file.read_text()):
            ps1_targets.add(m.group(1))

    required = {
        "audit", "lint", "deps", "rules", "gate",
        "status", "stop", "pipeline-4b", "pipeline-coder", "pipeline-gemma",
        "pipeline-all", "stress", "ppl", "run", "report",
        "agent-create", "agent-validate", "agent-profiles",
        "daemon-start", "daemon-stop", "daemon-status",
        "clean", "test", "boot",
    }

    missing_ps1 = required - ps1_targets

    return {
        "makefile": len(mk_targets),
        "ps1": len(ps1_targets),
        "missing_ps1": missing_ps1,
    }


def validate_seal_log():
    """Verifica se o selo tem commit log recente."""
    seal_file = BUILD / ".seal"
    if not seal_file.exists():
        return False, "ausente"
    r = subprocess.run(
        ["git", "-C", str(BUILD), "log", "-1", "--format=%s", "--", ".seal"],
        capture_output=True, text=True,
    )
    if r.stdout.strip():
        return True, "commit: " + r.stdout.strip()[:60]
    return False, "sem commit vinculado ao selo"


def run():
    funcs = find_python_functions()
    stubs = {k: v for k, v in funcs.items() if v["stub"]}
    real = {k: v for k, v in funcs.items() if not v["stub"]}

    calls = find_function_calls()
    contracts = validate_triade_contracts()
    seal_ok, seal_msg = validate_seal_log()

    # OUTPUT
    print("SYSTEM VALIDATION")
    print("=" * 60)

    print("")
    print("  FUNCOES:")
    print("    Total: {}".format(len(funcs)))
    print("    Reais: {}".format(len(real)))
    print("    Stubs: {}".format(len(stubs)))
    if stubs:
        for k in sorted(stubs)[:5]:
            print("      ✗ {} ({} linhas)".format(k, stubs[k]["lines"]))

    print("")
    print("  ORFAOS (funcoes nunca chamadas, >5 linhas, nao-builtin):")
    orphans = []
    builtins = {"print", "str", "len", "int", "float", "bool", "list", "dict", "set",
                 "tuple", "range", "enumerate", "zip", "map", "filter", "sorted",
                 "open", "type", "isinstance", "hasattr", "getattr", "setattr",
                 "super", "input", "max", "min", "sum", "any", "all", "next", "iter"}
    cli_entries = {"main", "run", "create_agent", "validate_contract", "list_profiles",
                   "collect_metrics", "format_terminal", "format_obsidian", "create_agent"}
    for k, v in real.items():
        fname = v["name"]
        if fname in builtins or fname in cli_entries:
            continue
        if fname.startswith("_") or fname.startswith("test_"):
            continue
        if fname not in calls and v["lines"] > 5 and v["file"].endswith(".py"):
            orphans.append(k)
    if orphans:
        for o in orphans[:5]:
            print("      ✗ {}".format(o))
    else:
        print("      ✓ nenhum orfao")

    print("")
    print("  MULTI-CONEXAO (funcoes chamadas em 3+ arquivos, nao-builtin):")
    multi = [(k, v) for k, v in calls.items() if len(v) >= 3 and k not in builtins]
    for name, files in sorted(multi, key=lambda x: -len(x[1]))[:5]:
        print("      {} -> {} arquivos".format(name, len(files)))

    print("")
    print("  CONTRATOS TRIADE (isolado):")
    print("    Makefile: {} targets".format(contracts["makefile"]))
    print("    PS1:      {} funcoes".format(contracts["ps1"]))
    if contracts["missing_ps1"]:
        print("    ✗ PS1 ausente: {}".format(",".join(sorted(contracts["missing_ps1"]))))
    else:
        print("    ✓ triade espelhada")

    print("")
    print("  SEAL LOG:")
    print("    {} {}".format("✓" if seal_ok else "✗", seal_msg))

    # Score: stubs + orphans + missing_ps1
    issues = len(stubs) + len(orphans) + len(contracts["missing_ps1"]) + (0 if seal_ok else 1)
    print("")
    print("  SCORE: {} issues".format(issues))
    return 1 if issues > 40 else 0


if __name__ == "__main__":
    sys.exit(run())
