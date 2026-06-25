# Makefile — Bench-LLM v5: Orquestracao de benchmarks locais
# Meta-orquestrador com status em tempo real e autoridade de parada
# DDD: orquestrador DONO do servidor, children clientes puros
# SDD: sweep_config.json como spec canônica de parâmetros
# Harness: ProcessRegistry + decay_shutdown preventivo

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

.PHONY: help status stop pipeline-4b pipeline-coder pipeline-gemma pipeline-all

help: ## Mostra todos os targets
	@echo "Bench-LLM v5 — Orquestracao de LLMs locais + Motor de Agente"
	@echo ""
	@echo "BOOT:"
	@echo "  make boot          — Health check completo (paths, envs, daemon, ruff)"

boot: ## Health check completo + compliance audit
	@cd $(BUILD) && python3 shared/compliance_check.py

audit: ## Compliance audit (triade mirror, profiles, rules, daemon, ollama, ruff, env, skills)
	@cd $(BUILD) && python3 shared/compliance_check.py

gate: ## Pre-commit gate (audit + stub scan + bypass detection)
	@cd $(BUILD) && python3 shared/pre_commit_hook.py

hook-install: ## Instala pre-commit hook no .git/hooks/
	@ln -sf ../../shared/pre_commit_hook.py $(BUILD)/.git/hooks/pre-commit && echo "hook instalado"

lint: ## Ruff + isort (0 erros obrigatorio)
	@cd $(BUILD) && ruff check . --exclude llama.cpp && isort --check-only --diff . --skip llama.cpp --skip __pycache__

types: ## Mypy type checking (TBT no Termux)
	@cd $(BUILD) && mypy . --ignore-missing-imports || true

deps: ## Circularity check (import cycles)
	@cd $(BUILD) && python3 shared/circularity_check.py
	@echo ""
	@echo "PIPELINE POR LLM:"
	@echo "  make pipeline-4b   — Pipeline completo no Qwen3-4B (worker leve padrao)"
	@echo "  make pipeline-coder— Pipeline completo no qwen2.5-coder (worker pesado)"
	@echo "  make pipeline-gemma— Pipeline completo no gemma4:e4b (orquestrador/cerebro)"
	@echo ""
	@echo "META (todos em sequencia):"
	@echo "  make pipeline-all  — 4B > coder > gemma (meta-orquestrador)"
	@echo ""
	@echo "TESTES INDIVIDUAIS:"
	@echo "  make stress MODELO=qwen3:4b  — Stress test 3 fases"
	@echo "  make ppl    MODELO=qwen3:4b  — Perplexidade 10 frases"
	@echo "  make sweep  MODELO=qwen3:4b  — Sweep parametrico (via sweep_config.json)"

status: ## Status em tempo real do pipeline
	@cd $(BUILD) && python3 meta_orchestrator.py --status

stop: ## Para o pipeline ativo
	@cd $(BUILD) && python3 meta_orchestrator.py --stop

pipeline-4b: ## Pipeline completo no worker leve (4B)
	@cd $(BUILD) && python3 test-4b/orchestrator.py

pipeline-coder: ## Pipeline completo no worker pesado (coder)
	@cd $(BUILD) && python3 test-coder/orchestrator.py

pipeline-gemma: ## Pipeline completo no orquestrador (gemma)
	@cd $(BUILD) && python3 test-gemma/orchestrator.py

pipeline-all: ## Meta: 4B > coder > gemma
	@cd $(BUILD) && python3 meta_orchestrator.py

stress: ## Stress test em 1 modelo (MODELO=...)
	@cd $(BUILD) && python3 bench_orchestrator.py --discover --stress --model $(MODELO)

ppl: ## PPL em 1 modelo (MODELO=...)
	@cd $(BUILD) && python3 bench_orchestrator.py --discover --ppl-only --model $(MODELO)

sweep: ## Sweep parametrico em 1 modelo (MODELO=...)
	@cd $(BUILD) && python3 bench_sweep.py --model-name $(MODELO) --config $(BUILD)/test-*/sweep_config.json

run: ## Executa 1 inferencia com perfil (PROMPT="..." MODELO=4b PERFIL=agent_default)
	@cd $(BUILD) && python3 meta_orchestrator.py --run "$(PROMPT)" --model $(MODELO) --profile $(PERFIL)

serve: ## Sobe servidor seguro para agentes (MODELO=4b)
	@cd $(BUILD) && python3 meta_orchestrator.py --serve --model $(MODELO)

report: ## Relatorio de metricas (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --report

report-obsidian: ## Relatorio + Obsidian vault (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --report --obsidian

report-watch: ## Loop 5s de metricas (Ctrl+C p/ sair)
	@cd $(BUILD) && python3 shared/metrics_reporter.py --obsidian --watch

agent-create: ## Cria agente via contrato (CONTRACT=~/agents/meu_agente.json)
	@cd $(BUILD) && python3 shared/agent_factory.py create --contract $(CONTRACT)

agent-validate: ## Valida contrato de agente (CONTRACT=~/agents/meu_agente.json)
	@cd $(BUILD) && python3 shared/agent_factory.py validate --contract $(CONTRACT)

agent-profiles: ## Lista perfis disponiveis por LLM
	@cd $(BUILD) && python3 shared/agent_factory.py list-profiles

daemon-start: ## Inicia metrics_daemon (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --daemon start

daemon-stop: ## Para metrics_daemon (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --daemon stop

daemon-status: ## Verifica metrics_daemon (via meta)
	@cd $(BUILD) && python3 meta_orchestrator.py --daemon status
