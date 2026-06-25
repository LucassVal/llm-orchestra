#!/usr/bin/env python3
"""
bench_ppl.py — Mede perplexidade (PPL) de modelos locais.
Usa llama-server com logprobs em corpus pt-BR.

PPL = exp(-1/N * sum(log P(token_i | contexto)))
Quanto menor, melhor — modelo "menos surpreso" pelo texto.

Regras: R-TRACE, R-NO-SILENT-FAIL, R-KISS.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from math import exp

# ═══════════════════════════════════════════════════════════════════
# CORPUS PT-BR (~40 frases, domínios variados)
# ═══════════════════════════════════════════════════════════════════

CORPUS = [
    # Notícias / factual
    "O presidente anunciou novas medidas econômicas durante entrevista coletiva.",
    "A temperatura máxima hoje deve chegar a trinta e cinco graus na capital.",
    "Cientistas descobriram uma nova espécie de planta na Amazônia.",
    "O mercado financeiro fechou em alta após divulgação de dados de emprego.",
    "As chuvas causaram alagamentos em várias regiões da cidade ontem.",

    # Técnico / programação
    "A função recursiva deve ter um caso base para evitar loop infinito.",
    "O banco de dados utiliza índices para acelerar consultas complexas.",
    "Python é uma linguagem interpretada com tipagem dinâmica e forte.",
    "O algoritmo de ordenação quicksort tem complexidade média n log n.",
    "A memória cache armazena dados frequentemente acessados pelo processador.",

    # Cotidiano / casual
    "Acordei cedo hoje para fazer exercícios antes do trabalho.",
    "Preciso comprar pão, leite e ovos no mercado depois do almoço.",
    "O filme era tão chato que dormi no meio da sessão.",
    "Minha avó faz o melhor bolo de chocolate que já provei.",
    "Esqueci as chaves dentro do carro e tive que chamar o chaveiro.",

    # Literatura / descritivo
    "O vento soprava forte entre as árvores centenárias do parque.",
    "As ondas quebravam suavemente na praia deserta ao entardecer.",
    "O gato preto dormia tranquilamente no sofá da sala vazia.",
    "As estrelas brilhavam intensamente naquela noite sem lua.",
    "O cheiro de café recém-passado invadia toda a cozinha.",

    # Instrução / procedimental
    "Para instalar o programa, execute o comando de instalação e aguarde.",
    "Misture os ingredientes secos antes de adicionar os ovos batidos.",
    "Configure o endereço de rede manualmente nas configurações do sistema.",
    "Pressione o botão ligar por três segundos para iniciar o dispositivo.",
    "Salve o documento antes de fechar o editor para não perder alterações.",

    # Abstrato / filosófico
    "A felicidade não é um destino, mas uma forma de viajar.",
    "O conhecimento é a única riqueza que ninguém pode nos tirar.",
    "Toda grande jornada começa com um simples primeiro passo.",
    "A paciência é a arte de esperar sem perder a esperança.",
    "O silêncio às vezes diz mais do que mil palavras.",

    # Diálogo / coloquial
    "Você viu o que aconteceu na festa do João no sábado passado?",
    "Não acredito que você terminou o projeto tão rápido assim.",
    "Me avisa quando chegar em casa para eu ficar tranquilo.",
    "Vamos marcar um café qualquer dia desses para colocar o papo em dia.",
    "Desculpa a demora, o trânsito estava impossível hoje de manhã.",
]

# ═══════════════════════════════════════════════════════════════════
# INFRA
# ═══════════════════════════════════════════════════════════════════

SERVER_URL   = "http://127.0.0.1:8080"
TIMEOUT      = 60

def tee(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}", file=sys.stderr, flush=True)

def trace() -> str:
    return str(uuid.uuid4())

# ═══════════════════════════════════════════════════════════════════
# PPL Runner
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PplResult:
    model_name: str
    ppl: float
    avg_logprob: float
    total_tokens: int
    sentences_tested: int
    sentences_failed: int
    elapsed_s: float
    trace_id: str = ""
    details: list = field(default_factory=list)

class PplRunner:
    """Mede PPL de 1 modelo usando llama-server + logprobs."""

    @classmethod
    def run(cls, gguf_path: str, model_name: str, corpus: list = None,
            server_url: str = SERVER_URL) -> PplResult:
        if not os.path.exists(gguf_path):
            return PplResult(model_name=model_name, ppl=0, avg_logprob=0,
                            total_tokens=0, sentences_tested=0, sentences_failed=0,
                            elapsed_s=0, trace_id=trace())

        corpus = corpus or CORPUS
        tid = trace()
        t0 = time.time()

        tee(f"[PPL] {model_name} | {len(corpus)} frases | Conectando em {server_url}...")

        # Verifica servidor
        try:
            urllib.request.urlopen(f"{server_url}/health", timeout=5)
        except Exception:
            return PplResult(model_name=model_name, ppl=0, avg_logprob=0,
                            total_tokens=0, sentences_tested=0, sentences_failed=len(corpus),
                            elapsed_s=0, trace_id=tid)

        try:
            total_logprob = 0.0
            total_tokens = 0
            failed = 0
            details = []

            for i, sentence in enumerate(corpus):
                try:
                    tokens, logprob_sum = cls._measure_sentence(sentence, server_url)
                    total_tokens += tokens
                    total_logprob += logprob_sum
                    details.append({"sentence": sentence[:80], "tokens": tokens,
                                   "avg_logprob": round(logprob_sum/max(tokens,1), 4)})
                except Exception as e:
                    failed += 1
                    details.append({"sentence": sentence[:80], "error": str(e)[:100]})

                if (i + 1) % 10 == 0:
                    tee(f"[PPL] {i+1}/{len(corpus)} frases...")

            elapsed = time.time() - t0
            avg_logprob = total_logprob / max(total_tokens, 1)
            ppl = round(exp(-avg_logprob), 2)

            tee(f"[PPL] ✓ PPL={ppl} | {total_tokens} tokens | {len(corpus)-failed}/{len(corpus)} frases | {elapsed:.1f}s")

            return PplResult(model_name=model_name, ppl=ppl, avg_logprob=round(avg_logprob, 4),
                           total_tokens=total_tokens, sentences_tested=len(corpus),
                           sentences_failed=failed, elapsed_s=round(elapsed, 1),
                           trace_id=tid, details=details)

        except Exception as e:
            tee(f"[PPL] ✗ FAIL: {e}")
            return PplResult(model_name=model_name, ppl=0, avg_logprob=0,
                           total_tokens=0, sentences_tested=0, sentences_failed=len(corpus),
                           elapsed_s=round(time.time()-t0, 1), trace_id=tid)

    @classmethod
    def _measure_sentence(cls, text: str, server_url: str = SERVER_URL) -> tuple:
        """Retorna (num_tokens, soma_logprobs) para uma frase usando echo completion."""
        body = json.dumps({
            "prompt": text,
            "max_tokens": 0,
            "temperature": 0,
            "echo": True,
            "logprobs": 1,
        }).encode()

        req = urllib.request.Request(
            f"{server_url}/v1/completions",
            data=body, headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())

        # Extrai logprobs do prompt
        logprobs_data = resp["choices"][0].get("logprobs", {})
        token_logprobs = logprobs_data.get("token_logprobs", [])

        if not token_logprobs:
            return cls._measure_sentence_chat(text, server_url)

        total = sum(lp for lp in token_logprobs if lp is not None)
        count = len([lp for lp in token_logprobs if lp is not None])

        return count, total

    @classmethod
    def _measure_sentence_chat(cls, text: str, server_url: str = SERVER_URL) -> tuple:
        """Fallback: usa chat completions com logprobs no conteúdo gerado."""
        body = json.dumps({
            "messages": [{"role": "user", "content": text}],
            "max_tokens": 5,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": 1,
        }).encode()

        req = urllib.request.Request(
            f"{server_url}/v1/chat/completions",
            data=body, headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())

        logprobs_content = resp["choices"][0].get("logprobs", {}).get("content", [])
        if not logprobs_content:
            return 0, 0.0

        total = sum(t.get("logprob", 0) for t in logprobs_content)
        return len(logprobs_content), total

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Benchmark PPL (perplexidade)")
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--corpus-size", type=int, default=0,
                    help="Limitar a N frases (0=todas)")
    ap.add_argument("--server-url", default="http://127.0.0.1:8080",
                    help="URL do llama-server já rodando")
    args = ap.parse_args()

    corpus = CORPUS[:args.corpus_size] if args.corpus_size > 0 else CORPUS

    result = PplRunner.run(args.gguf, args.model_name, corpus, server_url=args.server_url)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
