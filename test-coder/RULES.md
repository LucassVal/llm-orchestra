# test-coder/ — Manifesto Local
# Worker pesado. qwen2.5-coder (4.7GB).
# Autoridade: T2 (modelo) | Parent: build/RULES.md (T1)

## Perfis
  profiles/agent_default.json  — equilibrado (temp=0.3, tok=256)
  profiles/code.json           — deterministico (temp=0.1, tok=512)
  profiles/benchmark.json      — baseline para benchmarks

## Regras
- Worker para codigo, debug, refatoracao, tarefas pesadas
- Ollama-only (sem GGUF solto)
- Server: OLLAMA_SERVER_BIN + OLLAMA_LD_PATH
- Pipeline via bench_orchestrator.py --discover --pipeline
