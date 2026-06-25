#!/usr/bin/env python3

# 3W: WHAT=detector ciclos | WHY=evitar imports circulares | WHEN='make deps'
"""
circularity_check.py -- Detecta dependencias ciclicas entre modulos Python.
Varre imports e constroi grafo. Ciclo = FAIL bloqueante.
"""
import ast
import sys
from collections import defaultdict
from pathlib import Path

BUILD = Path(__file__).parent.parent
SKIP_DIRS = {"llama.cpp", "__pycache__", ".git", "logs"}


def extract_imports(filepath):
    """Extrai nomes de modulos importados de um arquivo .py."""
    try:
        tree = ast.parse(filepath.read_text())
    except Exception:
        return set()
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def build_graph():
    """Constroi grafo de dependencias entre modulos."""
    graph = defaultdict(set)
    for py_file in BUILD.rglob("*.py"):
        skip = False
        for d in SKIP_DIRS:
            if d in str(py_file):
                skip = True
                break
        if skip:
            continue
        name = py_file.stem
        imports = extract_imports(py_file)
        for imp in imports:
            # So conta se o modulo importado existe no projeto
            if (BUILD / (imp + ".py")).exists() or (BUILD / imp / "__init__.py").exists():
                graph[name].add(imp)
    return graph


def find_cycles(graph):
    """DFS para detectar ciclos. Retorna lista de ciclos encontrados."""
    cycles = []
    visited = set()
    stack = []

    def dfs(node):
        if node in stack:
            cycle_start = stack.index(node)
            cycles.append(stack[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for neighbor in graph.get(node, set()):
            dfs(neighbor)
        stack.pop()

    for node in graph:
        dfs(node)
    return cycles


def run():
    graph = build_graph()
    cycles = find_cycles(graph)

    if cycles:
        print("CIRCULARITY CHECK -- FAIL")
        for c in cycles:
            print("  ciclo: " + " → ".join(c))
        return 1
    else:
        mods = len(graph)
        edges = sum(len(v) for v in graph.values())
        print("CIRCULARITY CHECK -- PASS ({} modulos, {} arestas, 0 ciclos)".format(mods, edges))
        return 0


if __name__ == "__main__":
    sys.exit(run())
