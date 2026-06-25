#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
bench_child.py v4 -- worker DDD unificado.
Testa 1 modelo × 1 método × N perguntas × reasoning ON/OFF.

Camadas:
  Domain:      TestCategory, TestCase, Result, Method
  Application: BenchmarkRunner
  Infrastructure: LlamaCliRunner, LlamaServerRunner, RamGuard
  Presentation: tabela markdown + JSON

Métodos: llamacpp (--reasoning off/auto), llamaserver (API OpenAI compatível)
Regras: R-TRACE, R-NO-SILENT-FAIL, R-IDEMPOTENT, R-KISS, R-PYTHON-FIRST.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

# ═══════════════════════════════════════════════════════════════════
# DOMAIN
# ═══════════════════════════════════════════════════════════════════

class TestCategory(Enum):
    CONHECIMENTO = "conhecimento"
    LOGICA       = "logica"
    CODIGO       = "codigo"
    CRIATIVO     = "criativo"

class Method(Enum):
    LLAMACPP    = "llamacpp"
    LLAMASERVER = "llamaserver"

class Status(Enum):
    OK      = "OK"
    FAIL    = "FAIL"
    TIMEOUT = "TIMEOUT"
    OOM     = "OOM"
    SKIP    = "SKIP"
    BLOCKED = "BLOCKED"

@dataclass(frozen=True)
class TestCase:
    """Uma pergunta de benchmark."""
    id: str
    question: str
    category: TestCategory
    max_tokens: int = 80
    temperature: float = 0.3
    expected_keywords: list = field(default_factory=list, hash=False, compare=False)  # palavras esperadas na resposta

@dataclass
class Result:
    """Resultado de um teste."""
    status: Status
    method: str
    question_id: str
    question_text: str = ""
    category: str = ""
    reasoning: str = "off"  # off / auto
    elapsed_s: float = 0.0
    tokens: int = 0
    tok_s: float = 0.0
    prompt_tok_s: float = 0.0
    gen_tok_s: float = 0.0
    answer: str = ""
    error: str = ""
    trace_id: str = ""
    run_id: str = ""
    # Sweep metadata
    sweep_param: str = ""       # "temperature", "ctx-size", "top-p"
    sweep_value: str = ""       # "0.7", "2048"


# ═══════════════════════════════════════════════════════════════════
# PROMPTS UNIFICADOS (10 perguntas, 4 categorias)
# ═══════════════════════════════════════════════════════════════════

PROMPTS = [
    # ── CONHECIMENTO ──
    TestCase("B1", "Qual eh a capital do Brasil? Responda em portugues em 1 frase curta.",
             TestCategory.CONHECIMENTO, max_tokens=50, temperature=0.3,
             expected_keywords=["Brasília", "brasilia"]),
    TestCase("B2", "Explique o conceito de recursao em programacao em no maximo 2 frases. Portugues.",
             TestCategory.CONHECIMENTO, max_tokens=100, temperature=0.5,
             expected_keywords=["função", "chama", "mesm", "base"]),
    TestCase("B3", "Quanto eh 15% de 340? Responda so o numero.",
             TestCategory.CONHECIMENTO, max_tokens=20, temperature=0.1,
             expected_keywords=["51"]),

    # ── LÓGICA ──
    TestCase("L1", "Se 5 maquinas produzem 5 pecas em 5 minutos, quantas pecas 10 maquinas produzem em 10 minutos? Responda apenas o numero.",
             TestCategory.LOGICA, max_tokens=30, temperature=0.1,
             expected_keywords=["20"]),
    TestCase("L2", "Complete a sequencia: 2, 6, 12, 20, ? Responda apenas o numero.",
             TestCategory.LOGICA, max_tokens=20, temperature=0.1,
             expected_keywords=["30"]),

    # ── CÓDIGO ──
    TestCase("C1", "Escreva uma funcao em Python que recebe uma lista de numeros e retorna a soma dos pares. Apenas codigo, sem explicacao.",
             TestCategory.CODIGO, max_tokens=150, temperature=0.2,
             expected_keywords=["def", "return", "sum", "%"]),
    TestCase("C2", "Escreva uma funcao em Python que verifica se uma string eh palindromo. Apenas codigo, sem explicacao.",
             TestCategory.CODIGO, max_tokens=120, temperature=0.2,
             expected_keywords=["def", "return", "::-1", "palindromo"]),
    TestCase("C3", "Escreva uma funcao em Python que implementa busca binaria em lista ordenada. Apenas codigo, sem explicacao.",
             TestCategory.CODIGO, max_tokens=200, temperature=0.2,
             expected_keywords=["def", "while", "mid", "return"]),

    # ── CRIATIVO ──
    TestCase("R1", "Crie um haiku (poema japones de 3 linhas) sobre programacao. Em portugues.",
             TestCategory.CRIATIVO, max_tokens=80, temperature=0.9),
    TestCase("R2", "Descreva o por do sol em Marte em 2 frases. Em portugues.",
             TestCategory.CRIATIVO, max_tokens=80, temperature=0.8),
]

# ═══════════════════════════════════════════════════════════════════
# INFRASTRUCTURE -- Paths & Constantes
# ═══════════════════════════════════════════════════════════════════

LLAMA_CLI    = os.path.expanduser("~/llama.cpp/build/bin/llama-cli")
LLAMA_SERVER = os.path.expanduser("~/llama.cpp/build/bin/llama-server")
LD_CLI       = os.path.expanduser("~/llama.cpp/build/bin")
LD_SERVER    = os.path.expanduser("~/llama.cpp/build/bin")
SERVER_URL   = "http://127.0.0.1:8080"

THREADS  = 6
CTX      = 512
TIMEOUT  = 180
GB       = 1024 * 1024 * 1024

@dataclass
class RunConfig:
    """Configuração de parâmetros de inferência (sobrescreve defaults)."""
    ctx_size: int = CTX
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 80
MIN_FREE_GB = 0.5

def tee(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}", file=sys.stderr, flush=True)

def trace() -> str:
    return str(uuid.uuid4())

# ═══════════════════════════════════════════════════════════════════
# INFRASTRUCTURE -- LlamaCliRunner
# ═══════════════════════════════════════════════════════════════════

class LlamaCliRunner:
    """Executa llama-cli direto (sem servidor HTTP). Suporta --reasoning."""

    @staticmethod
    def run(gguf_path: str, tc: TestCase, reasoning: str = "off",
            config: Optional[RunConfig] = None) -> Result:
        if not os.path.exists(gguf_path):
            return Result(status=Status.SKIP, method="llamacpp", question_id=tc.id,
                          error=f"GGUF ausente: {gguf_path}", trace_id=trace())

        cfg = config or RunConfig()
        tee(f"[llama-cli] {tc.id} | {tc.category.value} | reason={reasoning} | "
            f"ctx={cfg.ctx_size} temp={cfg.temperature} top_p={cfg.top_p} | Carregando...")
        t0 = time.time()

        try:
            cmd = [LLAMA_CLI, "-m", gguf_path, "-p", tc.question,
                   "--ctx-size", str(cfg.ctx_size), "--threads", str(THREADS),
                   "--batch-size", "256", "--temp", str(cfg.temperature),
                   "--top-p", str(cfg.top_p),
                   "-n", str(cfg.max_tokens), "--single-turn", "--no-perf",
                   "--no-display-prompt", "--reasoning", reasoning]

            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = LD_CLI

            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=TIMEOUT, env=env)
            elapsed = time.time() - t0

            output = result.stdout + "\n" + result.stderr

            # Extrai métricas de geração
            prompt_ts, gen_ts = _parse_timing(output)
            tokens, tok_s = _parse_tokens(output, elapsed)

            # Extrai resposta (filtra banners do llama.cpp)
            answer = _extract_answer(output)

            tee(f"[llama-cli] ✓ {elapsed:.1f}s ({tok_s:.1f} tok/s) -- {answer[:80]}")

            return Result(status=Status.OK, method="llamacpp", question_id=tc.id,
                          question_text=tc.question, category=tc.category.value,
                          reasoning=reasoning, elapsed_s=round(elapsed, 1),
                          tokens=tokens, tok_s=round(tok_s, 1),
                          prompt_tok_s=prompt_ts, gen_tok_s=gen_ts,
                          answer=answer, trace_id=trace())

        except subprocess.TimeoutExpired:
            tee(f"[llama-cli] ✗ TIMEOUT ({TIMEOUT}s)")
            return Result(status=Status.TIMEOUT, method="llamacpp", question_id=tc.id,
                          elapsed_s=TIMEOUT, trace_id=trace())
        except Exception as e:
            tee(f"[llama-cli] ✗ FAIL: {e}")
            return Result(status=Status.FAIL, method="llamacpp", question_id=tc.id,
                          error=str(e)[:150], elapsed_s=round(time.time() - t0, 1),
                          trace_id=trace())

# ═══════════════════════════════════════════════════════════════════
# INFRASTRUCTURE -- LlamaServerRunner
# ═══════════════════════════════════════════════════════════════════

class LlamaServerRunner:
    """Conecta a um llama-server já rodando (gerenciado pelo orquestrador).
    
    Se server_url for None, inicia servidor próprio (modo standalone/deprecated).
    """
    
    server_url: str = SERVER_URL

    @classmethod
    def configure(cls, url: str = ""):
        """Define URL do servidor externo. Se vazio, usa default."""
        if url:
            cls.server_url = url
        else:
            cls.server_url = SERVER_URL

    @classmethod
    def run(cls, gguf_path: str, tc: TestCase,
            config: Optional[RunConfig] = None) -> Result:
        if not os.path.exists(gguf_path):
            return Result(status=Status.SKIP, method="llamaserver", question_id=tc.id,
                          error=f"GGUF ausente: {gguf_path}", trace_id=trace())

        cfg = config or RunConfig()
        tee(f"[llama-srv] {tc.id} | {tc.category.value} | "
            f"ctx={cfg.ctx_size} temp={cfg.temperature} | Conectando em {cls.server_url}...")
        t0 = time.time()

        try:
            # Verifica se servidor está vivo
            urllib.request.urlopen(f"{cls.server_url}/health", timeout=5)
        except Exception as e:
            return Result(status=Status.FAIL, method="llamaserver", question_id=tc.id,
                          error=f"Servidor offline: {e}", elapsed_s=round(time.time()-t0, 1),
                          trace_id=trace())

        try:
            t_req = time.time()
            body = json.dumps({
                "messages": [{"role": "user", "content": tc.question}],
                "max_tokens": cfg.max_tokens, "temperature": cfg.temperature
            }).encode()
            req = urllib.request.Request(f"{cls.server_url}/v1/chat/completions",
                                         data=body, headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
            elapsed = time.time() - t0
            req_elapsed = time.time() - t_req

            answer = resp["choices"][0]["message"]["content"][:200]
            usage = resp.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 0)
            tok_s = tokens / req_elapsed if req_elapsed > 0 else 0
            prompt_tok_s = prompt_tokens / (elapsed - req_elapsed) if (elapsed - req_elapsed) > 0 else 0

            tee(f"[llama-srv] ✓ {elapsed:.1f}s ({tok_s:.1f} tok/s) -- {answer[:80]}")

            return Result(status=Status.OK, method="llamaserver", question_id=tc.id,
                          question_text=tc.question, category=tc.category.value,
                          reasoning="n/a", elapsed_s=round(elapsed, 1),
                          tokens=tokens, tok_s=round(tok_s, 1),
                          prompt_tok_s=round(prompt_tok_s, 1),
                          answer=answer, trace_id=trace())

        except Exception as e:
            elapsed = time.time() - t0
            tee(f"[llama-srv] ✗ FAIL: {e}")
            return Result(status=Status.FAIL, method="llamaserver", question_id=tc.id,
                          error=str(e)[:150], elapsed_s=round(elapsed, 1), trace_id=trace())

# ═══════════════════════════════════════════════════════════════════
# INFRASTRUCTURE -- Parsers de output
# ═══════════════════════════════════════════════════════════════════

def _parse_timing(output: str) -> tuple:
    """Extrai prompt eval time e generation eval time do output llama-cli."""
    import re
    prompt_ts = 0.0
    gen_ts = 0.0
    m = re.search(r'llama_perf_sampler_print:\s+prompt eval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s*tokens.*?(\d+\.?\d*)\s*tokens per second', output)
    if m:
        gen_ts = float(m.group(2))
    # Fallback: grep por linhas de timing antigas
    for line in output.split("\n"):
        if "Prompt:" in line:
            with suppress(Exception):
                prompt_ts = float(re.search(r'[\d.]+', line.split("Prompt:")[-1]).group())
        if "Generation:" in line:
            with suppress(Exception):
                gen_ts = float(re.search(r'[\d.]+', line.split("Generation:")[-1]).group())
    return round(prompt_ts, 1), round(gen_ts, 1)

def _parse_tokens(output: str, elapsed: float) -> tuple:
    """Conta tokens aproximados do output."""
    import re

    # Tenta extrair do output de debug do llama-cli
    m = re.search(r'llama_perf_sampler_print:.*?(\d+)\s*tokens.*?(\d+\.?\d*)\s*tokens per second', output)
    if m:
        tokens = int(m.group(1))
        tok_s = float(m.group(2))
        return tokens, tok_s
    return 0, 0.0

def _extract_answer(output: str) -> str:
    """Extrai resposta limpa do output do llama-cli."""
    system_patterns = [
        "llama_model_loader:", "llama_model_load:", "llama_init_from",
        "system_info:", "main:", "srv ", "Available commands:", "Available:",
        "/regen", "/clear", "/read", "/glob", "/exit",
        "Prompt:", "[ Prompt:", "build =", "n_threads", "n_batch", "n_ubatch",
        "modalities:", "model size", "llama_perf_", "[Start thinking]",
        "Exiting", "Okay,", "First,", "I need", "Let me", "The user",
    ]
    lines = []
    for line in output.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if any(x in stripped for x in system_patterns):
            continue
        lines.append(stripped)

    if not lines:
        raw_preview = output.strip()[:200].replace("\n", "\\n")
        tee(f"[llama-cli] DEBUG raw output: {raw_preview}")

    # Remove thinking tags (modelos reasoning)
    import re
    text = " ".join(lines[-5:])
    text = re.sub(r'<\|im_start\|>.*?<\|im_end\|>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Start thinking\].*?\[End thinking\]', '', text, flags=re.DOTALL)
    return text.strip()[:200] if lines else "(sem output)"

# ═══════════════════════════════════════════════════════════════════
# APPLICATION -- BenchmarkRunner
# ═══════════════════════════════════════════════════════════════════

class BenchmarkRunner:
    """Coordena o benchmark de 1 modelo em 1 ou 2 métodos."""

    def __init__(self, model_name: str, gguf_path: str, model_size_gb: float,
                 methods: list, questions: list, reasoning_modes: list):
        self.model_name = model_name
        self.gguf_path = gguf_path
        self.model_size_gb = model_size_gb
        self.methods = methods
        self.questions = questions
        self.reasoning_modes = reasoning_modes
        self.results: list = []
        self.run_id = trace()

    def _run_one(self, tc: TestCase, method: str, reasoning: str,
                 config: Optional[RunConfig] = None) -> Optional[Result]:
        """Executa 1 teste. Retorna Result ou None se bloqueado."""
        cfg = config or RunConfig()
        tid = trace()

        sweep_tag = ""
        if config:
            if config.temperature != RunConfig().temperature:
                sweep_tag = f"temp={config.temperature}"
            elif config.ctx_size != RunConfig().ctx_size:
                sweep_tag = f"ctx={config.ctx_size}"
            elif config.top_p != RunConfig().top_p:
                sweep_tag = f"top_p={config.top_p}"

        tee(f"▶ {method:15s} | {tc.id:4s} | {tc.category.value:14s} | "
            f"reason={reasoning:4s} {sweep_tag} | trace={tid[:8]}")

        if method == "llamacpp":
            r = LlamaCliRunner.run(self.gguf_path, tc, reasoning, cfg)
        elif method == "llamaserver":
            r = LlamaServerRunner.run(self.gguf_path, tc, cfg)
        else:
            return None

        r.run_id = self.run_id
        r.question_text = tc.question
        if config:
            r.sweep_param = self._sweep_param_name(config)
            r.sweep_value = self._sweep_value(config)
        return r

    def _sweep_param_name(self, config: RunConfig) -> str:
        default = RunConfig()
        if config.temperature != default.temperature:
            return "temperature"
        if config.ctx_size != default.ctx_size:
            return "ctx-size"
        if config.top_p != default.top_p:
            return "top-p"
        return ""

    def _sweep_value(self, config: RunConfig) -> str:
        default = RunConfig()
        if config.temperature != default.temperature:
            return str(config.temperature)
        if config.ctx_size != default.ctx_size:
            return str(config.ctx_size)
        if config.top_p != default.top_p:
            return str(config.top_p)
        return ""

    def execute(self) -> list:
        """Benchmark normal: perguntas × métodos × reasoning."""
        return self._execute_loop(
            label="BENCHMARK",
            get_configs=lambda: [RunConfig()])

    def execute_stress(self) -> dict:
        """Stress test: 3 fases (cold → sustained → stress). Usa só llamaserver."""
        if self.model_size_gb <= 0 and os.path.exists(self.gguf_path):
            self.model_size_gb = os.path.getsize(self.gguf_path) / GB

        tee(f"╔══ STRESS: {self.model_name} ({self.model_size_gb:.1f}GB) ══╗")
        tee(f"║ run_id: {self.run_id}")
        tee(f"╚{'═'*40}╝")

        phases_result = {}
        for phase_name, prompts, max_tok, temp, runs in [
            ("COLD",     ["Hello. 1 word response."], 20, 0.1, 1),
            ("SUSTAINED", [
                "Write a Python function: sum of list. Code only.",
                "What is 15% of 340? Number only.",
                "List 3 colors. Comma separated.",
                "Write haiku about code. 3 lines.",
                "Translate to French: Hello world.",
            ], 50, 0.3, 5),
            ("STRESS",   ["Explain step by step how a CPU executes a program, from fetch to retire. Be thorough and detailed."],
             200, 0.3, 1),
        ]:
            phase_toks = []
            phase_ttft = []
            phase_ms = []
            phase_temp = []

            for i in range(runs):
                prompt = prompts[i] if i < len(prompts) else prompts[-1]
                tc = TestCase(id=f"{phase_name}_{i}", question=prompt,
                             category=TestCategory.CONHECIMENTO,
                             max_tokens=max_tok, temperature=temp)

                tee(f"▶ {phase_name} run {i+1}/{runs} | max_tok={max_tok} temp={temp}")
                r = LlamaServerRunner.run(self.gguf_path, tc,
                                          RunConfig(max_tokens=max_tok, temperature=temp))
                phase_toks.append(r.tok_s)
                phase_ttft.append(r.prompt_tok_s)
                phase_ms.append(r.elapsed_s * 1000)
                phase_temp.append(0)

                self.results.append(r)
                time.sleep(0.5)

            avg_tok = sum(phase_toks) / max(len(phase_toks), 1)
            avg_ttft = sum(phase_ttft) / max(len(phase_ttft), 1)
            max_temp = max(phase_temp) if phase_temp else 0

            thermal = "🔥" if max_temp > 70 else ("🌡" if max_temp > 60 else "❄")
            tee(f"  {phase_name:<12} {runs} runs | {avg_tok:>5.1f} tok/s | TTFT {avg_ttft:>4.0f}ms | {max_temp}°C {thermal}")

            phases_result[phase_name] = {
                "avg_tok_s": round(avg_tok, 1),
                "avg_ttft_ms": round(avg_ttft, 0),
                "max_temp_c": max_temp,
                "runs": runs,
                "status": "OK",
            }

        return {"model": self.model_name, "gb": self.model_size_gb,
                "phases": phases_result, "status": "OK",
                "child_elapsed_s": 0}

    def execute_sweep(self, param: str, values: list) -> list:
        """Benchmark paramétrico: varia 1 parâmetro, mantém perguntas fixas."""
        configs = []
        for val in values:
            cfg = RunConfig()
            if param == "ctx-size":
                cfg.ctx_size = int(val)
            elif param == "temperature":
                cfg.temperature = float(val)
            elif param == "top-p":
                cfg.top_p = float(val)
            configs.append(cfg)

        return self._execute_loop(
            label=f"SWEEP {param}",
            get_configs=lambda: configs)

    def _execute_loop(self, label: str, get_configs) -> list:
        """Loop principal: para cada config, executa perguntas × métodos × reasoning."""
        if self.model_size_gb <= 0 and os.path.exists(self.gguf_path):
            self.model_size_gb = os.path.getsize(self.gguf_path) / GB
            tee(f"[AUTO] Tamanho detectado: {self.model_size_gb:.1f} GB")

        configs = get_configs()

        tee(f"╔══ {label}: {self.model_name} ══╗")
        tee(f"║ Metodos: {', '.join(self.methods)}")
        tee(f"║ Perguntas: {len(self.questions)} ({', '.join(q.id for q in self.questions)})")
        tee(f"║ Reasoning: {', '.join(self.reasoning_modes)}")
        tee(f"║ Tamanho: {self.model_size_gb:.1f} GB")
        tee(f"║ Variantes: {len(configs)}")
        tee(f"║ run_id: {self.run_id}")
        tee(f"╚{'═'*40}╝")

        for cfg in configs:
            for tc in self.questions:
                for method in self.methods:
                    modes = self.reasoning_modes if method == "llamacpp" else ["n/a"]
                    for reasoning in modes:
                        r = self._run_one(tc, method, reasoning, cfg)
                        if r is None:
                            continue
                        self.results.append(r)

                        if r.status in (Status.OOM, Status.BLOCKED):
                            tee(f"  💀 {r.status.value}. Pulando metodos restantes.")
                            break
                    time.sleep(0.3)

        tee(f"✓ {self.model_name}: {len(self.results)} resultados")
        return self.results

# ═══════════════════════════════════════════════════════════════════
# PRESENTATION -- Tabela Markdown
# ═══════════════════════════════════════════════════════════════════

def render_markdown(results: list, model_name: str) -> str:
    """Gera tabela markdown dos resultados."""
    if not results:
        return f"## {model_name}\n\n*Sem resultados.*\n"

    lines = [f"## {model_name}", ""]
    lines.append("| # | Método | Reason | Cat | Status | t(s) | tok/s | Resposta |")
    lines.append("|---|--------|--------|-----|--------|------|-------|----------|")

    icon = {"OK": "✅", "FAIL": "❌", "TIMEOUT": "⏰", "OOM": "💀", "SKIP": "→", "BLOCKED": "⛔"}

    for i, r in enumerate(results, 1):
        answer = (r.answer or r.error or "")[:60].replace("|", "\\|").replace("\n", " ")
        st = icon.get(r.status.value, "?")

        lines.append(f"| {i} | {r.method} | {r.reasoning} | {r.category} | {st} {r.status.value} | "
                     f"{r.elapsed_s}s | {r.tok_s} | {answer} |")

    # Resumo
    total = len(results)
    ok = sum(1 for r in results if r.status == Status.OK)
    lines.append("")
    lines.append(f"**Total:** {total} | **OK:** {ok} | **Falhas:** {total - ok}")
    return "\n".join(lines)


def render_sweep_markdown(results: list, model_name: str, sweep_param: str) -> str:
    """Gera tabela markdown para sweep paramétrico."""
    if not results:
        return f"## {model_name} -- Sweep {sweep_param}\n\n*Sem resultados.*\n"

    lines = [f"## {model_name} -- Sweep `{sweep_param}`", ""]

    # Agrupa por valor do sweep
    from collections import defaultdict
    by_value = defaultdict(list)
    for r in results:
        by_value[r.sweep_value or "default"].append(r)

    for val in sorted(by_value.keys(), key=lambda v: float(v) if v.replace('.','').isdigit() else 0):
        subset = by_value[val]
        ok = sum(1 for r in subset if r.status == Status.OK)
        avg_tok = sum(r.tok_s for r in subset if r.tok_s > 0) / max(ok, 1)
        avg_time = sum(r.elapsed_s for r in subset) / max(len(subset), 1)
        lines.append(f"### {sweep_param} = {val}  →  {ok}/{len(subset)} OK | {avg_tok:.1f} tok/s | {avg_time:.1f}s")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Benchmark child worker v4 (DDD)")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--gguf", required=True, help="Caminho do GGUF/blob")
    parser.add_argument("--model-size-gb", type=float, default=0)
    parser.add_argument("--methods", default="llamacpp,llamaserver",
                        help="Metodos: llamacpp,llamaserver")
    parser.add_argument("--questions", default="all",
                        help="all | B1,B2,C1,C2 (IDs especificos) | conhecimento,logica,codigo,criativo (categorias)")
    parser.add_argument("--reasoning", default="off",
                        help="off | auto | off,auto (so para llamacpp)")
    parser.add_argument("--sweep", default="",
                        help="Sweep parametrico: ctx-size:512,1024,2048 | temperature:0.1,0.5,0.9 | top-p:0.5,0.7,0.9")
    parser.add_argument("--markdown", action="store_true", help="Output em markdown alem do JSON")
    parser.add_argument("--stress", action="store_true", help="Modo stress test: 3 fases (cold → sustained → stress)")
    parser.add_argument("--server-url", default="", help="URL do llama-server já rodando (orquestrador gerencia)")
    args = parser.parse_args()

    # Configura server URL se fornecido pelo orquestrador
    if args.server_url:
        LlamaServerRunner.configure(args.server_url)

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]

    # Seleciona perguntas
    if args.questions == "all":
        questions = list(PROMPTS)
    else:
        selected = set()
        for token in args.questions.split(","):
            token = token.strip()
            # Por ID
            for tc in PROMPTS:
                if tc.id == token:
                    selected.add(tc)
            # Por categoria
            try:
                cat = TestCategory(token.lower())
                for tc in PROMPTS:
                    if tc.category == cat:
                        selected.add(tc)
            except ValueError:
                pass
        questions = sorted(selected, key=lambda tc: PROMPTS.index(tc) if tc in PROMPTS else 99)

    reasoning_modes = [r.strip() for r in args.reasoning.split(",") if r.strip()]

    # Executa
    runner = BenchmarkRunner(
        model_name=args.model_name,
        gguf_path=args.gguf,
        model_size_gb=args.model_size_gb,
        methods=methods,
        questions=questions,
        reasoning_modes=reasoning_modes,
    )

    if args.sweep:
        # Modo sweep: --sweep temperature:0.1,0.5,0.9
        param, _, values_str = args.sweep.partition(":")
        if not values_str:
            tee("ERRO: --sweep requer formato PARAM:val1,val2,... (ex: temperature:0.1,0.5,0.9)")
            sys.exit(1)
        values = [v.strip() for v in values_str.split(",") if v.strip()]
        tee(f"[SWEEP] Param: {param} | Valores: {values}")
        results = runner.execute_sweep(param, values)
        sweep_param = param
    elif args.stress:
        # Modo stress: 3 fases (cold → sustained → stress)
        result = runner.execute_stress()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    else:
        results = runner.execute()
        sweep_param = ""

    # Output
    output = {
        "run_id": runner.run_id,
        "model": args.model_name,
        "results": [asdict(r) for r in results],
    }
    # Converte enums para string no JSON
    for r in output["results"]:
        r["status"] = r["status"].value if isinstance(r["status"], Status) else r["status"]

    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.markdown:
        print("\n--- MARKDOWN ---\n")
        if sweep_param:
            print(render_sweep_markdown(results, args.model_name, sweep_param))
        else:
            print(render_markdown(results, args.model_name))


if __name__ == "__main__":
    main()
