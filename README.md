# LLM-Orchestra

Hub completo para orquestracao local de LLMs no Android/Termux.
Benchmarks, agentes, fabrica de agentes, metricas em tempo real, governanca DDD.

> "Automatize localmente o maximo possivel sem IA. Use a IA apenas para ajustar
> ferramentas, criar processos e integrar o que ja existe."

## O que faz

- **Benchmark pipeline**: stress → battery → creative → temp_sweep → sweep → ppl → analyze
- **Meta-orquestrador**: hub unico para 3 LLMs (4B worker leve, coder pesado, gemma cerebro)
- **Fabrica de agentes**: contratos JSON (12 secoes) → agentes completos com identidade, limites, ferramentas
- **Metricas em tempo real**: daemon 5s → Obsidian vault + CSV historico
- **Governador termico**: throttle por temperatura (nunca bloqueia, sempre degrada)
- **Compliance audit**: 12 checks automatizados (triade, perfis, DDD, orphans, dependencias)
- **Triade**: Makefile (22 targets) ↔ maker CLI (20 comandos) ↔ PowerShell (23 comandos)

## Arquitetura

```
LEVEL 0: meta_orchestrator.py (hub unico)
  ├── test-4b/    (worker leve padrao, qwen3:4b 2.5GB, 15-17 tok/s)
  ├── test-coder/ (worker pesado, qwen2.5-coder 4.7GB)
  ├── test-gemma/ (orquestrador/cerebro, gemma4:e4b 9.6GB)
  └── shared/     (thermal_governor, metrics_daemon, agent_factory, compliance)

LEVEL 1: bench_orchestrator.py → bench_*.py (stress, battery, creative, ppl, etc.)

agents/ → definicoes de agentes (contratos JSON, fora do motor)
```

## Quick Start

```bash
make boot     # health check
make audit    # compliance (12 checks)
make pipeline-4b  # benchmark completo no worker leve
make run PROMPT="Ola" MODELO=4b PERFIL=agent_default  # agente
make agent-create CONTRACT=~/agents/worker-4b-default.json  # fabrica
```

## Stack

Python 3.13 | Ollama | llama.cpp | Termux | Android 16
Ruff 0 | isort ✓ | pytest ✓ | Mock 5.2 | Mypy (WIP)
