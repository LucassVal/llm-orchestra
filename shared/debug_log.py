#!/usr/bin/env python3
# 3W: WHAT=debug logger centralizado | WHY=auditar except blocks | WHEN=todo except silencioso
"""
debug_log.py -- Logger centralizado para except blocks.
Substitui pass-puro por log.debug() mantendo comportamento.
Nivel DEBUG so aparece se BENCH_DEBUG=1 no ambiente.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

BUILD = Path(__file__).parent.parent
DEBUG_FILE = BUILD / "logs" / "debug.log"
DEBUG = os.environ.get("BENCH_DEBUG", "0") == "1"


def log(msg: str, level: str = "DEBUG"):
    """Loga mensagem de debug. So escreve se BENCH_DEBUG=1."""
    if not DEBUG:
        return
    ts = datetime.now().strftime("%H:%M:%S.%f")[:15]
    line = "[{}] {} {}\n".format(ts, level, msg)
    with open(DEBUG_FILE, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def except_pass(module: str, func: str, error: str, detail: str = ""):
    """Substitui 'except Exception: pass' por log auditavel."""
    msg = "{}:{} -- {} -- {}".format(module, func, error, detail) if detail else "{}:{} -- {}".format(module, func, error)
    log(msg, "EXCEPT")
