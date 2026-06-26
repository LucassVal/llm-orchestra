---
description: Bench-LLM v5 — Regras de Governanca e Orquestracao de LLMs Locais
always_on: true
canonical: true
trace_id: "d4a1f8c2-9b3e-4721-a06d-5f7e8c9b1a2d"
ticket: "NC-BENCH-LLM-001"
updated_at: "2026-06-25"
parent_rules: "NeoCortex/RULES.md (T0)"
---

# RULES — Bench-LLM v5: Orquestracao de LLMs Locais
**AUTHORITY: T1 (execucao) | SCOPE: benchmark e agentes locais | PARENT: NeoCortex V44 T0**

> Este arquivo e a fonte canonica de regras para o ecossistema bench-llm.
> Deriva do RULES.md do NeoCortex (T0) e especializa para o dominio de LLMs.
> Toda regra aqui e compativel com o lema central: "Automatize localmente
> o maximo possivel sem IA."

---

## R-BENCH-USE — Verificar Antes de Sugerir e Agir

Antes de qualquer acao no ecossistema bench-llm:
1. `make status` — tem pipeline rodando?
2. `free -h` — RAM disponivel?
3. `ollama ps` — modelos carregados?
4. `make daemon-status` — coletor ativo?
5. `cat shared/thermal_status.json` — temperatura atual?

**NUNCA sugerir ou executar sem verificar esses 5 pontos.**

## R-BENCH-VALIDATE — Validar Espelhos

Antes de todo commit:
- `make rules` → R-VALIDATE verifica triade (Makefile ↔ maker ↔ ps1)
- `make audit` → 1_triade check
- Maker CLI deve ter 1:1 com Makefile
- .ps1 deve ter 1:1 com Makefile

**NUNCA commitar com triade dessincronizada.**

## R-BENCH-SEARCH — Ferramentas de Busca

- Pelo menos 1 MCP de busca deve estar configurado (ddg-search)
- Fallback: acesso HTTP a duckduckgo.com
- Ferramentas: `mcp_ddg_search_search`, `mcp_ows_search`, `web_search`
- Todas open-source, zero APIs pagas

**NUNCA depender de API paga para busca.**

## R-BENCH-3W — What, Why, When

Toda nova funcionalidade, script ou alteracao responde:
- **WHAT**: o que faz (1 linha)
- **WHY**: por que e necessario (problema concreto)
- **WHEN**: quando usar (gatilho)

Sem 3W preenchido = nao implementar.

## R-BENCH-KISS — Keep It Simple

- 1 script = 1 responsabilidade
- Nenhuma abstracao sem 2+ usos concretos comprovados
- Python puro, sem frameworks externos
- Bash so para interface de OS (watchdog, cron)
- ASCII apenas — zero unicode em codigo

## R-BENCH-SDD — Spec-Driven Development

`sweep_config.json` e a spec canonica de parametros por modelo.
Nenhum parametro de inferencia e hardcoded — sempre vem da spec.

Formato canonico:
```json
{
  "model": "nome",
  "description": "o que e este modelo",
  "baseline": { "threads": 6, "batch_size": 256, "ctx_size": 512, ... },
  "sweeps": [ { "name": "...", "values": [...], "type": "int|bool" } ],
  "test_prompts": [ ... ],
  "warmup_runs": 1,
  "measure_runs": 2
}
```

## R-BENCH-DDD — Domain-Driven Design

### HIERARQUIA DE FLUXOS

```
LEVEL 0 — META (meta_orchestrator.py) .................... HUB UNICO
  │
  ├── CONTROLE:
  │   --pipeline              → executa todos LLMs em sequencia
  │   --status                → progresso em tempo real (5s pings)
  │   --stop                  → SIGTERM autoritativo
  │   --run "prompt" --model  → agente com governador termico
  │   --serve --model         → servidor seguro para agentes
  │   --report [--obsidian]   → relatorio de metricas
  │   --daemon start|stop|status → controle do coletor persistente
  │
  ├── CHILDREN LEVEL 1 (orquestradores por modelo):
  │   │
  │   ├── test-4b/orchestrator.py
  │   │   └── bench_orchestrator.py --discover --pipeline --model Qwen3-4B
  │   │       └── ServerManager(OLLAMA_BIN, OLLAMA_LD)
  │   │           └── stress → battery → creative → temp_sweep → sweep → ppl → analyze
  │   │
  │   ├── test-coder/orchestrator.py
  │   │   └── bench_orchestrator.py --discover --pipeline --model qwen2.5-coder
  │   │
  │   └── test-gemma/orchestrator.py
  │       └── bench_orchestrator.py --discover --pipeline --model gemma4:e4b
  │
  └── INFRA LEVEL 1 (shared/):
      ├── thermal_governor.py  → thermal_status.json (5s)
      ├── metrics_reporter.py  → collect_metrics() (unificado)
      ├── metrics_daemon.py    → Obsidian + CSV (5s loop)
      └── watchdog_metrics.sh  → keep-alive (cron 1min, no_agent)
```

### REGRA DDD FUNDAMENTAL

**Todo componente se comunica APENAS com seu orquestrador do mesmo nivel.**
- Children nunca chamam outros children diretamente
- Children nunca acessam arquivos de outros children
- Infra shared e acessivel por import, mas SEMPRE via meta
- Nenhum script solto na raiz build/ — tudo em sua pasta hierarquica

### PARENT → CHILDREN (comando)
```
meta --pipeline
  → test-4b/orchestrator.py
    → bench_orchestrator.py
      → bench_child.py --stress
      → bench_battery.py
      → bench_creative.py
      → bench_temp_sweep.py
      → bench_sweep.py
      → bench_ppl.py
      → bench_analyze.py
```

### CHILDREN → PARENT (dados)
```
thermal_governor.py  → thermal_status.json ─┐
bench_orchestrator.py → bench_status.json ───┤
test-4b/results.json ────────────────────────┤
test-coder/results.json ─────────────────────┼──→ metrics_reporter.collect_metrics()
test-gemma/results.json ─────────────────────┤         ↑
                                              │    meta --report
                                              │    daemon (5s)
                                              ↓
                                         Obsidian vault
                                         CSV historico
```

## R-BENCH-PARETO — 80/20

Fatores que impactam performance (ordem de prioridade):
1. **Binario** (40%): sempre usar Ollama (`/data/data/com.termux/files/usr/lib/ollama/`)
2. **RAM/swap** (25%): OLLAMA_MAX_LOADED_MODELS=1 + KEEP_ALIVE=60s
3. **Termico** (20%): governador termico (throttle, nunca bloqueia)
4. **Modelo** (10%): tamanho/quantizacao
5. **TTFT** (5%): prompt processing

## R-BENCH-AUDIT — Imutabilidade de Logs

**Regra absoluta: logs NUNCA apagam, NUNCA sobrescrevem.**

- `results.json` → substituído por `logs/benchmark_YYYYMMDD_HHMMSS.json` (timestamp)
- `bench_run.log` → sempre append (`"a"`), nunca truncar (`"w"`)
- `benchmark_latest.json` → symlink para o mais recente
- Violação de log = violação de auditoria = FAIL bloqueante no hook
- Deleção de log é detectada pelo seal (hash SHA256)

**NUNCA `rm results.json`. NUNCA `open(log, "w")`.**

## R-BENCH-RCA — Root Cause Analysis

Metodologia de diagnostico de falhas:
1. **Log**: ultima linha de `logs/bench_run.log`
2. **Status**: `bench_status.json` (phase, step, elapsed)
3. **Termico**: `shared/thermal_status.json` (temp, tier, RAM)
4. **Ollama**: `ollama ps` (modelos carregados)
5. **Kernel**: `dmesg | tail -20` (OOM killer?)

Padrao de crash: se `bench_run.log` corta no meio sem `◀ PIPELINE: concluido`,
o OOM killer matou o processo. Verificar `dmesg` para `Out of memory`.

## R-BENCH-THRESHOLDS — Limiares do Sistema

| Métrica | Full | Eco | Low | Minimal | Idle |
|---------|------|-----|-----|---------|------|
| Temp (°C) | <70 | 70-80 | 80-85 | 85-90 | >90 |
| Max tokens | 512 | 256 | 128 | 64 | 16 |
| Temperature | 0.7 | 0.5 | 0.3 | 0.1 | 0.0 |
| RAM (MB) | >2048 | 1024-2048 | 512-1024 | <512 | — |
| Contexto | 100% | 50% | 25% | 12.5% | — |

**Regra absoluta: NUNCA bloquear. Sempre degradar.**

## R-BENCH-ENV — Variaveis Obrigatorias

Devem estar em `~/.bashrc`:
```bash
export OLLAMA_KEEP_ALIVE=60s
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_MAX_QUEUE=1
export OLLAMA_CONTEXT_LENGTH=4096
```

## R-BENCH-LINT — Qualidade de Codigo

- `ruff check . --exclude llama.cpp` → 0 erros obrigatorio
- `isort --check-only --diff .` → imports ordenados
- `mypy . --ignore-missing-imports` → TBT (quebrado no Termux)
- `pytest --co -q` → TBT (sem suite ainda)
- `python3 -c "import ast; ast.parse(...)"` → toda alteracao
- Progress bar + log stderr para qualquer script com +10 iteracoes
- ASCII apenas — zero unicode, zero em-dash

**Skills:** `python-audit` (ruff+mypy+pytest+isort+mock), `compliance-audit` (triade+ecosystem).

## R-BENCH-ORCHESTRATOR — Regra do Orquestrador

1. **Estender, nunca criar scripts paralelos.** Nova funcionalidade entra na lista
   `TESTS` do `bench_orchestrator.py`, nao em arquivo novo.
2. **Orquestrador e DONO do servidor.** Children sao clientes HTTP puros.
3. **ServerManager e unico.** Nenhum child inicia/para llama-server.
4. **Binario Ollama e o padrao.** So usar compilado manual se comprovadamente
   mais rapido com flags `-mcpu=native+dotprod+i8mm+sve+sme`.

## R-BENCH-MODEL — Modelos e Papeis

| Modelo | Pasta | RAM | Papel | Tok/s |
|--------|-------|-----|-------|-------|
| qwen3:4b | test-4b/ | 2.5GB | worker leve padrao (agentes) | 15-17 |
| qwen2.5-coder | test-coder/ | 4.7GB | worker pesado (codigo/debug) | — |
| gemma4:e4b | test-gemma/ | 9.6GB | orquestrador/cerebro (chain) | — |

### Matriz de Configs (quais vars afetam quais LLMs)

| Config | 4B | Coder | Gemma | Tipo |
|--------|:----:|:-----:|:-----:|------|
| MAX_LOADED_MODELS=1 | ✓ | ✓ | ✓ | servidor |
| KEEP_ALIVE=60s | ✓ | ✓ | ✓ | servidor |
| KV_CACHE_TYPE=q8_0 | ✓ | ✓ | ✓ | servidor |
| FLASH_ATTENTION=1 | ✓ | ✓ | ✓ | servidor |
| MAX_QUEUE=1 | ✓ | ✓ | ✓ | servidor |
| CONTEXT_LENGTH=4096 | ✓ | ✓ | ✓ | servidor |
| temperature | perfil | perfil | perfil | inferencia |
| max_tokens | perfil | perfil | perfil | inferencia |
| ctx_size | perfil | perfil | perfil | inferencia |
| threads=6 | ✓ | ✓ | ✓ | inferencia |
| batch_size=256 | ✓ | ✓ | Ollama ignora | inferencia |
| ngl | 0-10 | 0-10 | 0-10 | GPU |
| mlock | off/on | off/on | off (9.6GB!) | RAM |

**Regra:** servidor = `.env` / `.env.make`. inferencia = `test-*/profiles/*.json`.
Nao existe variavel Ollama por modelo — o servidor e unico.
Perfis injetados no agente compensam essa limitacao.

## R-BENCH-COMMANDS — Comandos Unificados

```
make status              → progresso pipeline (5s pings)
make stop                → parar pipeline
make pipeline-4b         → worker leve (agentes)
make pipeline-all        → 4B → coder → gemma
make run PROMPT="..."    → agente com perfil
make report              → metricas (terminal)
make report-obsidian     → metricas + vault
make daemon-start|stop   → controle do coletor

make agent-profiles      → listar perfis por LLM
make agent-validate CONTRACT=~/agents/x.json  → validar contrato
make agent-create CONTRACT=~/agents/x.json    → criar agente

maker bench *            → idem via NeoCortex CLI
```

## R-BENCH-FILES — Estrutura de Arquivos

```
~/                                ← HOME
├── agents/                       ← definicoes de agentes (fora do meta)
│   ├── agent_contract_template.json  ← spec canonica (11 secoes)
│   ├── worker-4b-default/            ← exemplo criado
│   │   ├── AGENT.md                  ← identidade + regras
│   │   └── contract.json             ← contrato canonico
│   └── profiles/                     ← perfis compartilhados entre agentes
│
├── build/                        ← motor de orquestracao (meta)
│   ├── RULES.md                  ← este arquivo (T1)
│   ├── meta_orchestrator.py      ← hub unico (LEVEL 0)
│   ├── Makefile                  ← CLI unificada
│   ├── pyproject.toml            ← ruff config
│   │
│   ├── bench_orchestrator.py     ← pipeline + ServerManager
│   ├── bench_*.py (10)           ← ferramentas compartilhadas
│   │
│   ├── test-4b/                  ← worker leve (modelos + perfis)
│   │   ├── orchestrator.py
│   │   ├── profiles/             ← perfis de ajuste por funcao
│   │   │   ├── agent_default.json
│   │   │   ├── code.json
│   │   │   ├── creative.json
│   │   │   ├── fast.json
│   │   │   └── benchmark.json
│   │   ├── results.json
│   │   ├── temp_sweep_results.json
│   │   └── sweep_results.json
│   ├── test-coder/               ← worker pesado
│   │   ├── orchestrator.py
│   │   └── profiles/
│   │       ├── agent_default.json
│   │       ├── code.json
│   │       └── benchmark.json
│   ├── test-gemma/               ← orquestrador/cerebro
│   │   ├── orchestrator.py
│   │   └── profiles/
│   │       ├── agent_default.json
│   │       ├── chain_of_thought.json
│   │       └── benchmark.json
│   │
│   ├── shared/                   ← infra (LEVEL 1)
│   │   ├── thermal_governor.py
│   │   ├── metrics_reporter.py
│   │   ├── metrics_daemon.py
│   │   ├── agent_factory.py
│   │   └── watchdog_metrics.sh
│   │
│   └── logs/                     ← historico
│
└── NeoCortex/                    ← governanca (T0)
    └── RULES.md                  ← fonte canonica suprema
```

## R-BENCH-CHECKLIST — Pre-Flight

Antes de qualquer pipeline:
- [ ] `ruff check . --exclude llama.cpp` → 0 erros
- [ ] `ollama list` → 3 modelos presentes
- [ ] `echo $OLLAMA_KEEP_ALIVE` → 60s
- [ ] `make daemon-status` → rodando
- [ ] `free -h` → >2GB disponivel
- [ ] `cat shared/thermal_status.json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['thermal_c'])"` → <90°C
