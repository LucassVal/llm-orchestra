# test-gemma/ -- Manifesto Local
# Orquestrador/cerebro. gemma4:e4b (9.6GB).
# Autoridade: T2 (modelo) | Parent: build/RULES.md (T1)

## Perfis
  profiles/agent_default.json      -- equilibrado (temp=0.3, tok=256)
  profiles/chain_of_thought.json   -- raciocinio profundo (temp=0.5, tok=512)
  profiles/benchmark.json          -- baseline para benchmarks

## Regras
- Cerebro para chain-of-thought, planejamento, decisoes complexas
- 9.6GB -- usar com cautela (MAX_LOADED_MODELS=1 obrigatorio)
- Ollama-only
- Server: OLLAMA_SERVER_BIN + OLLAMA_LD_PATH
- Pipeline via bench_orchestrator.py --discover --pipeline
