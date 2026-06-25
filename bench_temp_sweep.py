#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
bench_temp_sweep.py v1 -- Varredura de temperatura para LLMs locais.
Testa N temperaturas com prompts de código, lógica, criatividade e factualidade.
Mede: tok/s, diversidade lexical, repetição, factualidade, qualidade de código.
Usa llama-server (deve estar rodando). Output: JSON + log via stderr.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

SERVER_URL = "http://127.0.0.1:8080"
BUILD_DIR = Path(__file__).parent

# Temperaturas para varredura fina
TEMPS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]

# Prompts por categoria
PROMPTS = {
    "codigo": [
        ("soma_pares", "Write a Python function that sums all even numbers in a list. Return only code, no explanation."),
        ("palindromo", "Write a Python function that checks if a string is a palindrome. Return only code."),
        ("binary_search", "Write a Python function for binary search in a sorted list. Return only code."),
    ],
    "logica": [
        ("maquinas", "If 5 machines make 5 parts in 5 minutes, how many parts do 100 machines make in 100 minutes? Answer with just the number."),
        ("sequencia", "What is the next number in the sequence: 2, 6, 12, 20, 30, ? Answer with just the number."),
    ],
    "criativo": [
        ("haiku", "Crie um haiku sobre tecnologia. 3 linhas. Portugues."),
        ("microconto", "Microconto de 2 frases sobre inteligencia artificial. Portugues."),
    ],
    "factual": [
        ("capital", "Qual a capital da Franca? Responda apenas o nome da cidade."),
        ("planeta", "Qual o maior planeta do sistema solar? Responda apenas o nome."),
    ],
}

MAX_TOKENS = {"codigo": 120, "logica": 60, "criativo": 100, "factual": 40}
RUNS_PER_TEMP = 2


def _bar(current, total, width=30):
    pct = current / total if total else 0
    filled = int(width * pct)
    return f"[{'#' * filled}{'.' * (width - filled)}] {current}/{total}"


def lexical_diversity(text):
    words = text.lower().split()
    if len(words) < 3:
        return 0
    return len(set(words)) / len(words)


def repetition_score(text):
    words = text.lower().split()
    if len(words) < 8:
        return 0
    bigrams = [tuple(words[i:i+2]) for i in range(len(words)-1)]
    counts = Counter(bigrams)
    repeated = sum(max(0, c-1) for c in counts.values())
    return round(repeated / max(len(bigrams), 1), 2)


def has_valid_code(text):
    """Verifica se a resposta contém código Python sintaticamente válido."""
    code_indicators = ["def ", "return ", "import ", "class ", "if ", "for ", "while "]
    return any(ind in text for ind in code_indicators)


def factual_check(category, text, expected_hint):
    """Verificação simples de factualidade (case-insensitive + substring)."""
    return expected_hint.lower() in text.lower()


def infer(prompt, temp, max_tok=80, server_url=SERVER_URL):
    body = json.dumps({"prompt": prompt, "max_tokens": max_tok,
                       "temperature": temp}).encode()
    req = urllib.request.Request(f"{server_url}/v1/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return resp["choices"][0]["text"]


def main():
    ap = argparse.ArgumentParser(description="Temperature sweep for local LLMs")
    ap.add_argument("--model-name", required=True, help="Nome do modelo")
    ap.add_argument("--gguf", required=True, help="Caminho do GGUF (verifica existência)")
    ap.add_argument("--model-size-gb", type=float, default=0)
    ap.add_argument("--server-url", default=SERVER_URL)
    ap.add_argument("--temps", type=str, default=None,
                    help="Temperaturas: '0.0,0.5,1.0' (default: 13 valores)")
    ap.add_argument("--output", type=str, default=None,
                    help="Arquivo de saída JSON (default: stdout)")
    args = ap.parse_args()

    if not os.path.exists(args.gguf):
        result = {"model": args.model_name, "status": "SKIP", "error": "GGUF ausente"}
        _emit(result, args.output)
        return

    # Health check
    try:
        urllib.request.urlopen(f"{args.server_url}/health", timeout=5)
    except Exception:
        result = {"model": args.model_name, "status": "SERVER_OFFLINE"}
        _emit(result, args.output)
        return

    temps = [float(t) for t in args.temps.split(",")] if args.temps else TEMPS

    # Conta total de iterações
    total_prompts = sum(len(v) for v in PROMPTS.values())
    total_iter = len(temps) * total_prompts * RUNS_PER_TEMP
    iter_idx = 0
    results = []
    t_start = time.time()
    trace_id = str(uuid.uuid4())

    print(f"[temp_sweep] ▶ {args.model_name}  |  {len(temps)} temps × {total_prompts} prompts × {RUNS_PER_TEMP}"
          f" runs = {total_iter} iterações", file=sys.stderr)
    print(f"[temp_sweep]   temps: {temps}", file=sys.stderr)

    for temp in temps:
        t_temp = time.time()
        temp_results = []

        for cat, prompts in PROMPTS.items():
            for prompt_id, prompt_text in prompts:
                responses = []
                tok_s_vals = []
                for run_i in range(RUNS_PER_TEMP):
                    iter_idx += 1
                    t0 = time.time()
                    try:
                        text = infer(prompt_text, temp, max_tok=MAX_TOKENS[cat],
                                     server_url=args.server_url)
                        elapsed = time.time() - t0
                        tok_count = len(text.split())
                        tok_s = tok_count / elapsed if elapsed > 0 else 0
                        responses.append(text)
                        tok_s_vals.append(tok_s)
                        status = "OK"
                    except Exception:
                        responses.append("")
                        tok_s_vals.append(0)
                        status = "ERR"

                    print(f"[temp_sweep] {_bar(iter_idx, total_iter)}  "
                          f"T={temp} {cat}/{prompt_id} r{run_i+1}  "
                          f"{status}  {tok_s_vals[-1]:.1f}tok/s",
                          file=sys.stderr, flush=True)

                avg_text = responses[0] if responses and responses[0] else ""
                avg_tok_s = sum(tok_s_vals) / max(len(tok_s_vals), 1)
                lex_div = lexical_diversity(avg_text)
                rep = repetition_score(avg_text)
                sample = avg_text[:60].replace("\n", " / ")
                has_code = has_valid_code(avg_text) if cat == "codigo" else None

                # Factual check
                factual_expected = {
                    "capital": "paris",
                    "planeta": "júpiter",
                }
                fact_ok = None
                if cat == "factual":
                    fact_ok = factual_check(cat, avg_text, factual_expected.get(prompt_id, ""))

                temp_results.append({
                    "temp": temp,
                    "category": cat,
                    "prompt_id": prompt_id,
                    "avg_tok_s": round(avg_tok_s, 1),
                    "lexical_diversity": round(lex_div, 2),
                    "repetition": rep,
                    "has_code": has_code,
                    "factual_ok": fact_ok,
                    "length": len(avg_text),
                    "sample": sample,
                })

        elapsed_temp = time.time() - t_temp
        avg_t = sum(r["avg_tok_s"] for r in temp_results) / len(temp_results)
        print(f"[temp_sweep]   T={temp} ✓  avg={avg_t:.1f}tok/s  ({elapsed_temp:.1f}s)",
              file=sys.stderr, flush=True)
        results.extend(temp_results)

    # Sumário
    summary = {}
    for temp in temps:
        subset = [r for r in results if r["temp"] == temp]
        if subset:
            avg_tok = sum(r["avg_tok_s"] for r in subset) / len(subset)
            avg_lex = sum(r["lexical_diversity"] for r in subset) / len(subset)
            avg_rep = sum(r["repetition"] for r in subset) / len(subset)
            code_ok = sum(1 for r in subset if r.get("has_code") is True)
            code_total = sum(1 for r in subset if r.get("has_code") is not None)
            fact_ok = sum(1 for r in subset if r.get("factual_ok") is True)
            fact_total = sum(1 for r in subset if r.get("factual_ok") is not None)

            # Melhor temperatura = max tok/s + max diversidade - repetição
            score = avg_tok + (avg_lex * 10) - (avg_rep * 5)
            summary[str(temp)] = {
                "avg_tok_s": round(avg_tok, 1),
                "lexical_diversity": round(avg_lex, 2),
                "repetition": round(avg_rep, 2),
                "code_ok": f"{code_ok}/{code_total}" if code_total else "N/A",
                "factual_ok": f"{fact_ok}/{fact_total}" if fact_total else "N/A",
                "score": round(score, 1),
            }

    # Melhor temperatura geral
    best = max(summary.items(), key=lambda x: x[1]["score"]) if summary else (None, {})

    output = {
        "trace_id": trace_id,
        "model": args.model_name,
        "gb": args.model_size_gb,
        "status": "OK",
        "elapsed_s": round(time.time() - t_start, 1),
        "best_temp": best[0],
        "best_score": best[1].get("score"),
        "summary": summary,
        "results": results,
    }
    _emit(output, args.output)
    print(f"[temp_sweep] ◀ concluído  |  best T={best[0]} score={best[1].get('score')}  "
          f"({time.time() - t_start:.1f}s)", file=sys.stderr, flush=True)


def _emit(data, output_path):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text)
        print(f"[temp_sweep] salvo → {output_path}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
