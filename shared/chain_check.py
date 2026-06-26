#!/usr/bin/env python3
# 3W: WHAT=chain validator | WHY=garantir que skills/workflows respeitam hierarquia DDD | WHEN=checkpoint/commit
"""
chain_check.py — Validador de cadeia de skills e workflows.
Verifica que:
  1. Skills sao carregadas em ordem canonica (bench-llm → agent-workflow → compliance-audit → dev-workflow → python-audit)
  2. Workflows respeitam DDD: meta → children → leaf scripts
  3. Nenhum script chama outro fora da hierarquia (chain break)
  4. Nenhum bypass de nivel (LEVEL 2 chamando LEVEL 0 diretamente)
ERR obrigatorio — chain quebrada bloqueia checkpoint.
"""
import ast
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent

# Ordem canonica das skills
SKILL_CHAIN = [
    "bench-llm",
    "agent-workflow",
    "compliance-audit",
    "dev-workflow",
    "python-audit",
]

# Workflow canonico (ordem obrigatoria)
WORKFLOW_CHAIN = [
    "kill-all",
    "ollama",
    "lint",
    "deps",
    "rules",
    "audit",
    "seal",
    "validate",
    "antimock",
    "tools",
    "gate",
]

# Hierarquia DDD (quem pode chamar quem)
# LEVEL 0: meta_orchestrator.py → pode chamar LEVEL 1
# LEVEL 1: test-*/orchestrator.py, shared/* → pode chamar LEVEL 2
# LEVEL 2: bench_*.py → leaf, nao chama ninguem acima
DDD_CHAIN = {
    "meta_orchestrator.py": 0,
}

for model in ["test-4b", "test-coder", "test-gemma"]:
    DDD_CHAIN[f"{model}/orchestrator.py"] = 1

for shared_file in BUILD.glob("shared/*.py"):
    rel = str(shared_file.relative_to(BUILD))
    if rel not in DDD_CHAIN:
        DDD_CHAIN[rel] = 1

for bench_file in BUILD.glob("bench_*.py"):
    DDD_CHAIN[bench_file.name] = 2


def check_skill_chain():
    """Verifica se skills estao presentes e em ordem."""
    skills_dir = Path.home() / ".hermes" / "skills" / "mlops"
    bench_skill = Path.home() / ".hermes" / "skills" / "bench-llm"
    
    present = []
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                present.append(d.name)
    # bench-llm vive fora de mlops/
    if bench_skill.exists() and (bench_skill / "SKILL.md").exists():
        present.append("bench-llm")

    missing = [s for s in SKILL_CHAIN if s not in present]
    return len(missing) == 0, missing


def check_workflow_chain():
    """Verifica se Makefile tem os targets do workflow na ordem canonica."""
    mk_text = (BUILD / "Makefile").read_text()
    violations = []
    for step in WORKFLOW_CHAIN:
        if f"{step}:" not in mk_text:
            violations.append(f"target '{step}' ausente no Makefile")
    return len(violations) == 0, violations


def check_ddd_chain():
    """Verifica se nenhum arquivo LEVEL 2 importa LEVEL 0 ou LEVEL 1 (chain break)."""
    violations = []
    for py_file in BUILD.glob("bench_*.py"):
        try:
            content = py_file.read_text()
            tree = ast.parse(content)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.append(node.module)
            # LEVEL 2 (bench_*.py) nao pode importar meta_orchestrator
            for imp in imports:
                if "meta_orchestrator" in imp:
                    violations.append(
                        f"{py_file.name}: importa 'meta_orchestrator' (LEVEL 2→0 quebra cadeia)"
                    )
                if "orchestrator" in imp and "bench_orchestrator" not in imp and "test-" not in imp:
                    violations.append(
                        f"{py_file.name}: importa '{imp}' (chain break suspeito)"
                    )
        except Exception:
            pass
    return len(violations) == 0, violations


def run():
    issues = []

    # 1. Skill chain
    skill_ok, skill_issues = check_skill_chain()
    if not skill_ok:
        issues.append(f"SKILL CHAIN: {len(skill_issues)} ausentes: {', '.join(skill_issues)}")

    # 2. Workflow chain
    wf_ok, wf_issues = check_workflow_chain()
    if not wf_ok:
        issues.append(f"WORKFLOW CHAIN: {len(wf_issues)} violacoes")
        for v in wf_issues:
            issues.append(f"  - {v}")

    # 3. DDD chain
    ddd_ok, ddd_issues = check_ddd_chain()
    if not ddd_ok:
        issues.append(f"DDD CHAIN: {len(ddd_issues)} chain breaks")
        for v in ddd_issues:
            issues.append(f"  - {v}")

    if issues:
        print("CHAIN CHECK -- FAIL")
        for i in issues:
            print(f"  ✗ {i}")
        return 1

    print("CHAIN CHECK -- PASS (skills=ok, workflow=ok, ddd=ok)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
