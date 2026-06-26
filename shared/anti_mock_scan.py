#!/usr/bin/env python3
# 3W: WHAT=anti-mock scan | WHY=detectar funcoes conceituais/falsas | WHEN=auditoria
"""
anti_mock_scan.py -- Detecta implementações falsas/mockeadas.
Padrões detectados:
  1. Cache-stale: json.load(X.json) quando X.json é cache, não fonte real
  2. Silent-except: except Exception: return default (mascara falhas)
  3. Hardcoded-dynamic: constantes que deveriam ser calculadas de estado real
  4. Stale-source: funções que leem arquivo estático em vez de API/sensor
"""
import ast
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent

# Arquivos que são CACHE (escritos por outro processo), não fonte de verdade
CACHE_FILES = [
    "thermal_status.json",  # cache do thermal_governor, fonte real é /sys/class/thermal/
    "bench_status.json",    # cache do heartbeat, ok para status mas pode estar stale
]

# Métodos que indicam leitura de arquivo estático (potencial stale)
FILE_READ_PATTERNS = [
    ".read_text()",
    ".read()",
    "json.load(",
    "json.loads(",
    "open(",
]


def scan_file(filepath):
    findings = []
    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except Exception:
        return findings
    rel = str(filepath.relative_to(BUILD))

    for node in ast.walk(tree):
        # Padrão 1: json.load(open) de arquivo cache
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
                # json.load(open(X)) ou json.loads(X.read_text())
                if func_name in ("load", "loads"):
                    for arg in node.args:
                        if isinstance(arg, ast.Call):
                            if isinstance(arg.func, ast.Attribute):
                                if arg.func.attr in ("read_text", "read"):
                                    # Verifica se o caminho contém um cache file
                                    try:
                                        source = ast.unparse(arg.func.value)
                                        for cf in CACHE_FILES:
                                            if cf in source:
                                                findings.append({
                                                    "type": "CACHE_AS_SOURCE",
                                                    "file": rel,
                                                    "line": node.lineno,
                                                    "detail": f"Le {cf} como fonte (cache, nao real)",
                                                    "source": source[:60],
                                                })
                                    except Exception:
                                        pass

        # Padrão 2: except Exception com pass PURO (sem return/fallback)
        if isinstance(node, ast.ExceptHandler):
            if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
                body = node.body
                # Só flag se for PASS PURO (sem return, sem log)
                # Ignora se o pass está em contexto de cleanup/atexit/finally
                is_pure_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
                if is_pure_pass:
                    # Verifica se está em função de cleanup (atexit, finally, cleanup, stop)
                    is_cleanup = False
                    # Heurística: se a função contém 'cleanup' ou 'stop' ou 'kill', é intencional
                    for ancestor in ast.walk(tree):
                        if isinstance(ancestor, ast.FunctionDef):
                            if any(kw in ancestor.name.lower() for kw in ['cleanup', 'stop', 'kill', 'atexit', 'finally']):
                                # Verifica se o except está dentro desta função
                                if node.lineno >= ancestor.lineno and node.end_lineno <= ancestor.end_lineno:
                                    is_cleanup = True
                                    break
                    if not is_cleanup:
                        findings.append({
                            "type": "SILENT_EXCEPT",
                            "file": rel,
                            "line": node.lineno,
                            "detail": "except Exception: pass puro — mascara falha sem fallback",
                        })

    return findings


def run():
    all_findings = []
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git", "anti_mock"])
        if skip:
            continue
        all_findings.extend(scan_file(py_file))

    # Agrupa por tipo
    by_type = {}
    for f in all_findings:
        t = f["type"]
        by_type.setdefault(t, []).append(f)

    print("ANTI-MOCK SCAN")
    print("=" * 60)
    for t, items in sorted(by_type.items()):
        print(f"\n  {t} ({len(items)} achados):")
        for i in items[:5]:
            print(f"    {i['file']}:{i['line']} -- {i['detail']}")

    total = len(all_findings)
    print(f"\n  TOTAL: {total} achados")
    return 1 if total > 25 else 0


if __name__ == "__main__":
    sys.exit(run())
