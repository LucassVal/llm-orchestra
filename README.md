# LLM-Orchestra 🎻

Hub completo para orquestração local de LLMs no Android/Termux.
Benchmarks, agentes, fábrica de agentes, métricas em tempo real, governança DDD.

> "Automatize localmente o máximo possível sem IA. Use a IA apenas para ajustar
> ferramentas, criar processos e integrar o que já existe."

## O que faz

- **Benchmark pipeline**: stress → battery → creative → temp_sweep → sweep → ppl → analyze (7 etapas)
- **Meta-orquestrador**: hub único para 3 LLMs (4B worker leve, coder pesado, gemma cérebro)
- **Fábrica de agentes**: contratos JSON (12 seções) → agentes completos com identidade, limites, ferramentas
- **Métricas em tempo real**: daemon 5s → Obsidian vault + CSV histórico (4 arquivos)
- **Governador térmico**: throttle por temperatura (nunca bloqueia, sempre degrada — 5 tiers)
- **Compliance audit**: 19 checks automatizados (triade, perfis, DDD, orphans, dependências, rules)
- **Pre-commit gate**: 5 barreiras (stub + slop + mock + rules + audit) — todas ERR
- **Rule check**: 10 regras R-BENCH-* como verificadores Python (ERR exceto RAM+Thermal)
- **Triade**: Makefile (29 targets) ↔ maker CLI (22 comandos) ↔ PowerShell (25 funções)
- **Dev workflow**: lint → deps → rules → audit → gate (5 gates encadeados)

## Stack

Python 3.13 | Ollama | llama.cpp | Termux | Android 16 | Obsidian
Ruff 0 | isort ✓ | py_check ✓ | pytest ✓ | mock 5.2 | aislop 0.12

## Quick Start

```bash
make boot          # health check + compliance
make audit         # 19 checks
make pipeline-4b   # benchmark no worker leve
make run PROMPT="Olá" MODELO=4b PERFIL=agent_default  # agente
make agent-create CONTRACT=~/agents/worker-4b-default.json  # fábrica
make gate           # pre-commit (stub+slop+mock+rules+audit)
```

## Arquitetura

```
LEVEL 0 — META (meta_orchestrator.py)
  ├── --pipeline        → test-*/orchestrator.py (3 LLMs)
  ├── --run --profile   → agente com governador térmico + perfil JSON
  ├── --serve           → servidor seguro
  ├── --report          → métricas (terminal + Obsidian)
  └── --daemon          → controle do coletor persistente

LEVEL 1 — ORCHESTRADORES
  test-4b/    worker leve (qwen3:4b 2.5GB, 15-17 tok/s, 6 perfis)
  test-coder/ worker pesado (qwen2.5-coder 4.7GB, 3 perfis)
  test-gemma/ cérebro (gemma4:e4b 9.6GB, 3 perfis)

INFRA — shared/
  thermal_governor.py  → monitor + throttle (5s)
  metrics_daemon.py    → Obsidian + CSV (5s loop)
  agent_factory.py     → fábrica de agentes (contrato JSON)
  compliance_check.py  → 19 checks
  pre_commit_hook.py   → 5 barreiras
  rule_check.py        → 10 regras R-BENCH-*
  circularity_check.py → dependências circulares
  triade_check.py      → espelhamento Makefile↔maker↔ps1
  py_check.py          → syntax validator nativo

AGENTS — ~/agents/
  Contratos JSON (12 seções) → identidade, perfil, limites, ferramentas
```

## Comandos (Triade)

| Área | make | maker bench | .ps1 |
|------|------|-------------|------|
| boot | ✓ | ✓ | ✓ |
| audit | ✓ | ✓ | ✓ |
| gate | ✓ | ✓ | ✓ |
| rules | ✓ | ✓ | ✓ |
| lint | ✓ | ✓ | ✓ |
| deps | ✓ | ✓ | ✓ |
| pipeline-* | ✓ | ✓ | ✓ |
| run | ✓ | ✓ | ✓ |
| report | ✓ | ✓ | ✓ |
| daemon | ✓ | ✓ | ✓ |
| agent-* | ✓ | ✓ | ✓ |
