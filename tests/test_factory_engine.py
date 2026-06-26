#!/usr/bin/env python3
# 3W: WHAT=teste factory_engine | WHY=validar fabrica AST jinja2 | WHEN=commit/checkpoint
"""Testes para factory_engine.py -- Fabrica AST com Jinja2."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.factory_engine import (assign, build_module, call, constant,
                                   create_agent_module, create_profile,
                                   create_test_file, funcdef, import_stmt,
                                   render)


class TestFactoryEngine:
    """Testes da fabrica AST."""

    def test_import(self):
        """Modulo importa sem erro."""
        import shared.factory_engine as fe
        assert fe is not None

    def test_render_template(self):
        """Renderiza template jinja2 basico."""
        result = render("profile.json.jinja", name="test", temperature=0.5,
                        max_tokens=256, context=2048)
        assert '"test"' in result
        assert "0.5" in result

    def test_create_profile(self):
        """Gera perfil JSON valido."""
        import json
        result = create_profile("benchmark", temperature=0.7, max_tokens=512)
        data = json.loads(result)
        assert data["name"] == "benchmark"
        assert data["params"]["temperature"] == 0.7

    def test_create_agent_module(self):
        """Gera modulo de agente."""
        result = create_agent_module("test-agent")
        assert "test-agent" in result
        assert "def init()" in result
        assert "def run" in result

    def test_create_test_file(self):
        """Gera arquivo de teste."""
        result = create_test_file("bench_battery", "test_battery",
                                  functions=["main", "run"])
        assert "bench_battery" in result
        assert "TestTest_battery" in result
        assert "test_main_exists" in result

    def test_funcdef_ast(self):
        """Cria funcao AST valida."""
        import ast
        body = [ast.Pass()]
        node = funcdef("my_func", body, args=["x", "y"], returns="int")
        assert node.name == "my_func"
        assert len(node.args.args) == 2

    def test_assign_ast(self):
        """Cria atribuicao AST."""
        node = assign("x", constant(42))
        assert node.targets[0].id == "x"

    def test_call_ast(self):
        """Cria chamada de funcao AST."""
        node = call("print", [constant("hello")])
        assert node.func.id == "print"

    def test_build_module(self):
        """Monta modulo AST e gera codigo."""
        import ast
        imp = import_stmt("json")
        body = [imp, funcdef("main", [ast.Pass()])]
        code = build_module(body, shebang="#!/usr/bin/env python3")
        assert "#!/usr/bin/env python3" in code
        assert "import json" in code
        assert "def main" in code

    def test_no_silent_fail(self):
        """R-BENCH-NO-SILENT-FAIL: funcoes nao lancam excecao muda."""
        try:
            create_profile("x", temperature=0.0)
        except Exception as e:
            assert False, f"create_profile falhou: {e}"
