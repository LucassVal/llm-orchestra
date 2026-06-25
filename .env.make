# Build/.env — Ollama global (servidor unico, afeta TODOS os modelos)
# Valores seguros para o pior caso (gemma 9.6GB).
# Perfis por modelo em test-*/profiles/ controlam inferencia.

# ── GLOBAL (servidor) ──
OLLAMA_MAX_LOADED_MODELS := 1     # [4B+coder+gemma] 10GB RAM, so 1 por vez
OLLAMA_KEEP_ALIVE := 60s          # [4B+coder] recarga rapida | [gemma] libera RAM
OLLAMA_KV_CACHE_TYPE := q8_0      # [4B+coder+gemma] metade RAM do cache, seguro
OLLAMA_FLASH_ATTENTION := 1       # [4B+coder+gemma] requerido p/ KV cache q8_0
OLLAMA_MAX_QUEUE := 1             # [todos] rejeita, sem fila fantasma
OLLAMA_CONTEXT_LENGTH := 4096     # [todos] seguro, perfis podem reduzir

# ── POR MODELO (inferencia, em test-*/profiles/*.json) ──
# 4B:    temp=0.0-0.7  tok=64-512   ctx=512-4096  (leve, rapido)
# coder: temp=0.1-0.3  tok=256-512  ctx=2048-4096 (medio, deterministico)
# gemma: temp=0.3-0.5  tok=256-512  ctx=2048-4096 (pesado, chain-of-thought)

# ── NOTAS ──
# KEEP_ALIVE=60s: 4B recarrega em ~6s, gemma ~15s. Se gemma for usada
#   frequentemente, subir pra 120s. Se so 4B, pode baixar pra 30s.
# KV_CACHE=q8_0: seguro p/ todas arquiteturas (Gemma, Qwen). q4_0 existe
#   mas tem perda mensuravel de qualidade. Nao usar f16 (default, 2x RAM).
