#!/usr/bin/env python3
# 3W: WHAT=teste display/rich | WHY=validar camada de apresentacao | WHEN=commit/checkpoint
"""Testes para display.py -- Camada Rich de apresentacao."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDisplay:
    """Testes do modulo display (rich)."""

    def test_import(self):
        """Rich disponivel e display importa."""
        from shared.display import console
        assert console is not None

    def test_tee_output(self):
        """tee() escreve sem erro."""
        from shared.display import tee
        tee("test message")

    def test_status_ok(self):
        """status_ok nao quebra."""
        from shared.display import status_ok
        status_ok("test passed")

    def test_status_fail(self):
        """status_fail nao quebra."""
        from shared.display import status_fail
        status_fail("test failed")

    def test_thermal_gauge(self):
        """thermal_gauge renderiza sem erro."""
        from shared.display import thermal_gauge
        thermal_gauge(45.0, "full", 512)
        thermal_gauge(75.0, "eco", 256)
        thermal_gauge(85.0, "low", 128)
        thermal_gauge(95.0, "idle", 16)

    def test_panel(self):
        """panel renderiza sem erro."""
        from shared.display import panel
        panel("TEST", "conteudo de teste")

    def test_pipeline_header(self):
        """pipeline_header renderiza sem erro."""
        from shared.display import pipeline_header
        pipeline_header("abc123", "qwen3:4b", ["stress", "battery", "creative"])

    def test_pipeline_step_result(self):
        """pipeline_step_result renderiza sem erro."""
        from shared.display import pipeline_step_result
        pipeline_step_result("stress", "OK", tok_s=14.5, elapsed_s=30)
        pipeline_step_result("sweep", "TIMEOUT", elapsed_s=1800)

    def test_table(self):
        """table renderiza sem erro."""
        from shared.display import table
        table(
            headers=["Nome", "Valor", "Status"],
            rows=[["test", "42", "OK"], ["bench", "3.14", "WARN"]],
            title="Tabela Teste",
        )

    def test_no_silent_fail(self):
        """R-BENCH-NO-SILENT-FAIL: display nao lanca excecao muda."""
        from shared.display import status_warn, step
        status_warn("warning test")
        step("▶", "step test", "detail aqui")
