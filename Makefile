# Makefile — Bench-LLM v5: Orquestracao de benchmarks locais
# Meta-orquestrador com status em tempo real e autoridade de parada
# DDD: orquestrador DONO do servidor, children clientes puros
# SDD: sweep_config.json como spec canonica de parametros
# Harness: ProcessRegistry + decay_shutdown preventivo

.DEFAULT_GOAL := quick-test
#
# ORDEM CANONICA (enforced):
#   1. CHECKPOINT: lint → deps → rules → audit → gate
#   2. ACTIONS:    pipeline, run, agent-create, etc.
#   Regra: checkpoint MUST pass before any action.

BUILD := $(HOME)/build
ENV_MK := $(BUILD)/.env.make

# Carrega env vars (Ollama) para todos os targets (syntax make)
-include $(ENV_MK)
export OLLAMA_KEEP_ALIVE
export OLLAMA_MAX_LOADED_MODELS
export OLLAMA_KV_CACHE_TYPE
export OLLAMA_FLASH_ATTENTION
export OLLAMA_MAX_QUEUE
export OLLAMA_CONTEXT_LENGTH

.PHONY: help checkpoint boot audit clean test install gate rules hook-install lint types deps \
        pipeline-4b pipeline-coder pipeline-gemma pipeline-all stress ppl sweep run serve \
        report report-obsidian report-watch agent-create agent-validate agent-profiles multi \
        daemon-start daemon-stop daemon-status


# ═══════════════════════════════════════════════════════════════
# CHECKPOINT — obrigatorio antes de qualquer acao
# ═══════════════════════════════════════════════════════════════

checkpoint: kill-all ollama lint deps rules audit seal validate antimock tools
	@echo ""
	@echo "✓ CHECKPOINT: kill-all + ollama + lint + deps + rules + audit + seal + validate + antimock + tools — todos PASS"
	@echo ""

ollama: ## [0/8] Ollama gate (6 envs, binary, modelos, .env)
	@cd $(BUILD) && python3 shared/ollama_gate.py

lint: ## [1/6] Ruff + isort + py_check (0 erros obrigatorio)
	@cd $(BUILD) && ruff check . --exclude llama.cpp && \
	 isort --check-only --diff . --skip llama.cpp --skip __pycache__ && \
	 python3 shared/py_check.py

deps: ## [2/5] Circularity check (import cycles, 0 obrigatorio)
	@cd $(BUILD) && python3 shared/circularity_check.py

rules: ## [3/5] Rule check (13 R-BENCH-*, todas ERR exceto RAM+Thermal)
	@cd $(BUILD) && python3 shared/rule_check.py

audit: ## [4/5] Compliance audit (chain + system + code + arch + factory + triade)
	@cd $(BUILD) && python3 shared/compliance_check.py

gate: ## [5/5] Pre-commit gate (kill-all + rich + stub + slop + mock + rules + audit)
	@cd $(BUILD) && python3 shared/pre_commit_hook.py

seal: ## [5/6] Selo de integridade (hash SHA256 de arquivos criticos)
	@cd $(BUILD) && python3 shared/seal_check.py

seal-reset: ## Reseta o selo (apos mudanca intencional)
	@cd $(BUILD) && python3 shared/seal_check.py --reset

validate: ## [6/8] Validacao completa (funcoes, stubs, orfaos, contratos)
	@cd $(BUILD) && python3 shared/system_validate.py

antimock: ## [7/9] Anti-mock scan (cache-stale, silent-except)
	@cd $(BUILD) && python3 shared/anti_mock_scan.py

tools: ## [8/9] Ferramentas externas (smellcheck + vulture + deadcode)
	@cd $(BUILD) && python3 shared/tools_gate.py


# ═══════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════

boot: checkpoint ## Health check completo (checkpoint + overview)
	@echo ""
	@echo "=== BOOT: LLM-Orchestra ==="
	@echo "  Ollama: $$(ollama list 2>/dev/null | tail -n+2 | wc -l) modelos"
	@echo "  RAM: $$(free -h | awk '/Mem:/{print $$4}') livre"
	@echo "  Daemon: $$(kill -0 $$(cat $(BUILD)/.metrics_daemon.pid 2>/dev/null) 2>/dev/null && echo rodando || echo parado)"
	@echo ""

clean: ## Limpa logs, cache, temp
	@cd $(BUILD) && rm -rf logs/*.log __pycache__ */__pycache__ .pytest_cache && echo "limpo"

kill-all: ## Mata processos orfaos (llama-server, bench, ollama) — ERR obrigatorio
	@cd $(BUILD) && python3 shared/kill_all.py

test: ## Roda todos os testes (pytest + smoke)
	@cd $(BUILD) && pytest tests/ -v

quick-test: checkpoint ## Teste rapido padrao — stress test 3 fases (~2min, thermal control)
	@cd $(BUILD) && python3 bench_orchestrator.py --discover --stress --model Qwen_Qwen3-4B-Q4_K_M --timeout 300

install: checkpoint ## Setup automatizado do ecossistema
	@echo "=== INSTALL: LLM-Orchestra ==="
	@pip install -q ruff isort pytest mock aislop 2>/dev/null
	@cd $(BUILD) && make hook-install
	@cd $(BUILD) && make daemon-start 2>/dev/null || true
	@echo "✓ Instalado."

hook-install: ## Instala pre-commit hook no .git/hooks/
	@ln -sf ../../shared/pre_commit_hook.py $(BUILD)/.git/hooks/pre-commit && \
	 chmod +x $(BUILD)/.git/hooks/pre-commit && \
	 echo "hook instalado + executavel"


# ═══════════════════════════════════════════════════════════════
# PIPELINE (requer checkpoint)
# ═══════════════════════════════════════════════════════════════

pipeline-4b: checkpoint ## Pipeline completo na 4B (worker leve padrao)
	@cd $(BUILD) && python3 test-4b/orchestrator.py

pipeline-coder: checkpoint ## Pipeline completo no coder (worker pesado)
	@cd $(BUILD) && python3 test-coder/orchestrator.py

pipeline-gemma: checkpoint ## Pipeline completo na gemma (cerebro)
	@cd $(BUILD) && python3 test-gemma/orchestrator.py

pipeline-all: checkpoint ## Meta: 4B > coder > gemma
	@cd $(BUILD) && python3 meta_orchestrator.py


# ═══════════════════════════════════════════════════════════════
# TESTES INDIVIDUAIS (requer checkpoint)
# ═══════════════════════════════════════════════════════════════

stress: checkpoint ## Stress test em 1 modelo (MODELO=qwen3:4b)
	@cd $(BUILD) && python3 bench_orchestrator.py --discover --stress --model $(MODELO)

ppl: checkpoint ## PPL em 1 modelo (MODELO=qwen3:4b)
	@cd $(BUILD) && python3 bench_orchestrator.py --discover --ppl-only --model $(MODELO)

sweep: checkpoint ## Sweep parametrico em 1 modelo (MODELO=qwen3:4b)
	@cd $(BUILD) && python3 bench_sweep.py --model-name $(MODELO) --config test-4b/sweep_config.json


# ═══════════════════════════════════════════════════════════════
# AGENTE (requer checkpoint)
# ═══════════════════════════════════════════════════════════════

run: checkpoint ## Executa 1 inferencia com perfil (PROMPT="..." MODELO=4b PERFIL=agent_default)
	@cd $(BUILD) && python3 meta_orchestrator.py --run "$(PROMPT)" --model $(MODELO) --profile $(PERFIL)

serve: checkpoint ## Sobe servidor seguro para agentes (MODELO=4b)
	@cd $(BUILD) && python3 meta_orchestrator.py --serve --model $(MODELO)


# ═══════════════════════════════════════════════════════════════
# METRICAS (nao requer checkpoint — leitura apenas)
# ═══════════════════════════════════════════════════════════════

report: ## Relatorio de metricas (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --report

report-obsidian: ## Relatorio + Obsidian vault
	@cd $(BUILD) && python3 meta_orchestrator.py --report --obsidian

report-watch: ## Loop 5s de metricas (Ctrl+C p/ sair)
	@cd $(BUILD) && python3 shared/metrics_reporter.py --obsidian --watch

status: ## Status pipeline em tempo real
	@cd $(BUILD) && python3 meta_orchestrator.py --status

stop: ## Para o pipeline ativo
	@cd $(BUILD) && python3 meta_orchestrator.py --stop


# ═══════════════════════════════════════════════════════════════
# FABRICA DE AGENTES (requer checkpoint)
# ═══════════════════════════════════════════════════════════════

agent-create: checkpoint ## Cria agente via contrato (CONTRACT=~/agents/x.json)
	@cd $(BUILD) && python3 shared/agent_factory.py create --contract $(CONTRACT)

agent-validate: ## Valida contrato (nao requer checkpoint)
	@cd $(BUILD) && python3 shared/agent_factory.py validate --contract $(CONTRACT)

agent-profiles: ## Lista perfis disponiveis por LLM
	@cd $(BUILD) && python3 shared/agent_factory.py list-profiles

multi: checkpoint ## Orquestrador multi-agente (ARGS="list")
	@cd $(BUILD) && python3 shared/multi_agent.py $(ARGS)

dispatch-list: ## Lista ultimos disparos (JSON dispatch log)
	@cd $(BUILD) && python3 shared/dispatch_log.py list


# ═══════════════════════════════════════════════════════════════
# DAEMON (nao requer checkpoint — controle operacional)
# ═══════════════════════════════════════════════════════════════

daemon-start: ## Inicia metrics_daemon (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --daemon start

daemon-stop: ## Para metrics_daemon (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --daemon stop

daemon-status: ## Verifica metrics_daemon (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --daemon status

types: ## Mypy type checking (TBT no Termux)
	@cd $(BUILD) && mypy . --ignore-missing-imports || true


# ═══════════════════════════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════════════════════════

help: ## Mostra todos os targets
	@echo "LLM-Orchestra v5 — Orquestracao de LLMs Locais + Motor de Agente"
	@echo ""
	@echo "⚠ ORDEM CANONICA (pre-commit requer checkpoint):"
	@echo "  make checkpoint   — [1]lint [2]deps [3]rules [4]audit [5]gate"
	@echo "  make lint         — ruff + isort + py_check"
	@echo "  make deps         — circularity check"
	@echo "  make rules        — 13 regras R-BENCH-*"
	@echo "  make audit        — compliance (21 checks)"
	@echo "  make gate         — stub + slop + mock + rules + audit"
	@echo ""
	@echo "PIPELINE (requer checkpoint):"
	@echo "  make pipeline-4b  — Qwen3-4B (worker leve padrao)"
	@echo "  make pipeline-coder — qwen2.5-coder (worker pesado)"
	@echo "  make pipeline-gemma — gemma4:e4b (cerebro)"
	@echo "  make pipeline-all — 4B > coder > gemma"
	@echo ""
	@echo "AGENTE (requer checkpoint):"
	@echo "  make run PROMPT=\"...\" MODELO=4b PERFIL=agent_default"
	@echo "  make serve MODELO=4b"
	@echo ""
	@echo "FABRICA (requer checkpoint):"
	@echo "  make agent-create CONTRACT=~/agents/x.json"
	@echo "  make multi ARGS=\"list\""
	@echo ""
	@echo "METRICAS (leitura, nao requer checkpoint):"
	@echo "  make report / report-obsidian / status / stop"
	@echo ""
	@echo "DAEMON: make daemon-start / daemon-stop / daemon-status"
	@echo "SETUP: make boot / install / clean / test / hook-install"
