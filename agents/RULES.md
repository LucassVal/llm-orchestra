# RULES.md -- Manifesto dos Agentes
# Autoridade: RULES.md (T1) > manifestos locais
# Pasta: definicoes JSON de agentes, fabrica em shared/agent_factory.py

## R-AGENT-CONTRACT
- Contrato JSON obrigatorio (12 secoes)
- Validacao via agent_factory.py validate
- Skills injetadas na criacao

## R-AGENT-LIFECYCLE
- Criacao: maker bench agent-create
- Validacao: maker bench agent-validate
- Listagem: maker bench agent-profiles

## R-AGENT-DDD
- Agentes sao definicoes (JSON), nao processos
- Execucao via meta_orchestrator --run
- Nunca bypassar o meta
