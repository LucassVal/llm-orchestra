# test-4b/ -- Manifesto Local
# Worker leve padrao. Qwen3-4B Q4_K_M (2.5GB).
# Autoridade: T2 (modelo) | Parent: build/RULES.md (T1)

## Perfis
  profiles/agent_default.json  -- equilibrado (temp=0.3, tok=256)
  profiles/code.json           -- deterministico (temp=0.1, tok=512)
  profiles/creative.json       -- criativo (temp=0.7, tok=512)
  profiles/fast.json           -- ultra-rapido (temp=0.0, tok=64)
  profiles/benchmark.json      -- baseline para benchmarks

## Regras
- Modelo padrao para qqr agente -- 15-17 tok/s sustentado
- GGUF: ~/build/Qwen_Qwen3-4B-Q4_K_M.gguf
- Server: OLLAMA_SERVER_BIN + OLLAMA_LD_PATH
- Pipeline via bench_orchestrator.py --discover --pipeline
