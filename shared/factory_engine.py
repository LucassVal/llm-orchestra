#!/usr/bin/env python3
# 3W: WHAT=fabrica AST com jinja2 | WHY=gerar codigo Python via templates | WHEN=criar agentes/perfis/testes
"""
factory_engine.py -- Motor de fabricas AST com Jinja2.
Gera codigo Python deterministico a partir de templates modulares.
Substitui string-concat e JSON-dict manual por AST tipado + jinja2 render.
"""
import ast
import uuid
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

BUILD = Path(__file__).parent.parent
TEMPLATES = BUILD / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ═══════════════════════════════════════════════════════════
# Renderizador Jinja2
# ═══════════════════════════════════════════════════════════

def render(template_name: str, **ctx) -> str:
    """Renderiza template jinja2 com contexto."""
    ctx.setdefault("trace", uuid.uuid4().hex[:12])
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**ctx)


# ═══════════════════════════════════════════════════════════
# Construtores AST (type-safe code generation)
# ═══════════════════════════════════════════════════════════

def funcdef(name: str, body: list[ast.stmt], args: list[str] | None = None,
            decorators: list[str] | None = None, returns: str | None = None,
            docstring: str | None = None) -> ast.FunctionDef:
    """Cria definicao de funcao AST."""
    arguments = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=arg) for arg in (args or [])],
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[],
    )
    if docstring:
        body.insert(0, ast.Expr(value=ast.Constant(value=docstring)))
    node = ast.FunctionDef(
        name=name,
        args=arguments,
        body=body,
        decorator_list=[
            ast.Name(id=d, ctx=ast.Load()) for d in (decorators or [])
        ],
        returns=ast.Name(id=returns, ctx=ast.Load()) if returns else None,
    )
    return node


def assign(name: str, value: ast.expr) -> ast.Assign:
    """Cria atribuicao: name = value."""
    return ast.Assign(
        targets=[ast.Name(id=name, ctx=ast.Store())],
        value=value,
    )


def call(func: str, args: list[ast.expr] | None = None,
         keywords: dict[str, ast.expr] | None = None) -> ast.Call:
    """Cria chamada de funcao: func(*args, **kwargs)."""
    return ast.Call(
        func=ast.Name(id=func, ctx=ast.Load()),
        args=args or [],
        keywords=[
            ast.keyword(arg=k, value=v) for k, v in (keywords or {}).items()
        ],
    )


def constant(value: Any) -> ast.Constant:
    """Cria constante AST."""
    return ast.Constant(value=value)


def dict_expr(pairs: dict[str, ast.expr]) -> ast.Dict:
    """Cria expressao de dicionario."""
    return ast.Dict(
        keys=[ast.Constant(value=k) for k in pairs],
        values=list(pairs.values()),
    )


def import_stmt(module: str, names: list[str] | None = None) -> ast.Import | ast.ImportFrom:
    """Cria statement de import."""
    if names:
        return ast.ImportFrom(
            module=module,
            names=[ast.alias(name=n) for n in names],
            level=0,
        )
    return ast.Import(names=[ast.alias(name=module)])


# ═══════════════════════════════════════════════════════════
# Modulo completo (AST -> .py file)
# ═══════════════════════════════════════════════════════════

def build_module(body: list[ast.stmt], shebang: str | None = None,
                 docstring: str | None = None) -> str:
    """Monta modulo Python a partir de AST, retorna codigo fonte."""
    if docstring:
        body.insert(0, ast.Expr(value=ast.Constant(value=docstring)))
    mod = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(mod)
    code = ast.unparse(mod)
    if shebang:
        code = shebang + "\n" + code
    return code


# ═══════════════════════════════════════════════════════════
# Fabrica: Agente (AST + Jinja2)
# ═══════════════════════════════════════════════════════════

def create_agent_module(name: str, profile: str = "agent_default",
                        model: str = "qwen3:4b") -> str:
    """Gera modulo de agente usando jinja2 + AST."""
    ctx = {
        "agent_name": name,
        "profile": profile,
        "model": model,
        "trace": uuid.uuid4().hex[:12],
    }
    return render("agent_module.py.jinja", **ctx)


# ═══════════════════════════════════════════════════════════
# Fabrica: Profile JSON
# ═══════════════════════════════════════════════════════════

def create_profile(name: str, temperature: float = 0.3,
                   max_tokens: int = 512, context: int = 4096,
                   use_cases: list[str] | None = None) -> str:
    """Gera perfil JSON via jinja2."""
    ctx = {
        "name": name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "context": context,
        "use_cases": use_cases or ["general"],
        "trace": uuid.uuid4().hex[:12],
    }
    return render("profile.json.jinja", **ctx)


# ═══════════════════════════════════════════════════════════
# Fabrica: Test file
# ═══════════════════════════════════════════════════════════

def create_test_file(target_module: str, test_name: str,
                     functions: list[str] | None = None) -> str:
    """Gera arquivo de teste via jinja2."""
    ctx = {
        "target_module": target_module,
        "test_name": test_name,
        "functions": functions or [],
        "trace": uuid.uuid4().hex[:12],
    }
    return render("test_bench.py.jinja", **ctx)


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("uso: factory_engine.py <create-agent|create-profile|create-test> [...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "create-agent":
        name = sys.argv[2] if len(sys.argv) > 2 else "worker-default"
        profile = sys.argv[3] if len(sys.argv) > 3 else "agent_default"
        model = sys.argv[4] if len(sys.argv) > 4 else "qwen3:4b"
        code = create_agent_module(name, profile, model)
        dest = BUILD / "agents" / f"{name}.py"
        dest.write_text("# 3W: WHAT=agente gerado | WHY=fabrica AST | WHEN={}\n".format(uuid.uuid4().hex[:8]) + code)
        print(f"✓ Agente criado: {dest}")

    elif cmd == "create-profile":
        name = sys.argv[2] if len(sys.argv) > 2 else "custom"
        temp = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3
        code = create_profile(name, temp)
        print(code)

    elif cmd == "create-test":
        target = sys.argv[2] if len(sys.argv) > 2 else "bench_battery"
        tname = sys.argv[3] if len(sys.argv) > 3 else "test_battery"
        code = create_test_file(target, tname)
        dest = BUILD / "tests" / f"test_{target}.py"
        dest.write_text("# 3W: WHAT=teste gerado | WHY=fabrica AST | WHEN={}\n".format(uuid.uuid4().hex[:8]) + code)
        print(f"✓ Teste criado: {dest}")
