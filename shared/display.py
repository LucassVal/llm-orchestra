#!/usr/bin/env python3
# 3W: WHAT=display rico com progress bars | WHY=visibilidade clara ao usuario | WHEN=toda execucao
"""
display.py -- Camada de apresentacao com Rich.
Substitui print/tee simples por:
  - Progress bars com ETA
  - Status panels (PASS/FAIL/WARN)
  - Tabelas formatadas
  - Live display para logs em tempo real
  - Spinner para operacoes longas
"""
from contextlib import contextmanager
from typing import Any

from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, SpinnerColumn, TextColumn,
                           TimeElapsedColumn, TimeRemainingColumn)
from rich.table import Table

console = Console()


# ═══════════════════════════════════════════════════════════
# Progress Bars
# ═══════════════════════════════════════════════════════════

def progress_bar(total: int, description: str = "Processando") -> Progress:
    """Cria barra de progresso com ETA."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console,
    )


@contextmanager
def tracked(description: str, total: int = 100):
    """Context manager: barra de progresso com steps."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(description, total=total)
        yield lambda advance=1: progress.advance(task, advance)


# ═══════════════════════════════════════════════════════════
# Status Panels
# ═══════════════════════════════════════════════════════════

def panel(title: str, content: str, style: str = "bold white") -> None:
    """Exibe painel formatado."""
    console.print(Panel(content, title=title, style=style))


def status_ok(msg: str) -> None:
    console.print(f"  [green]✓[/green] {msg}")


def status_fail(msg: str) -> None:
    console.print(f"  [red]✗[/red] {msg}")


def status_warn(msg: str) -> None:
    console.print(f"  [yellow]⚠[/yellow] {msg}")


def step(emoji: str, label: str, detail: str = "") -> None:
    """Log de etapa com emoji."""
    line = f"{emoji} [bold]{label}[/bold]"
    if detail:
        line += f"  {detail}"
    console.print(line)


# ═══════════════════════════════════════════════════════════
# Tabelas
# ═══════════════════════════════════════════════════════════

def table(headers: list[str], rows: list[list[Any]], title: str = "") -> None:
    """Exibe tabela formatada."""
    t = Table(title=title, box=box.ROUNDED)
    for h in headers:
        t.add_column(h, style="bold cyan")
    for row in rows:
        t.add_row(*[str(c) for c in row])
    console.print(t)


# ═══════════════════════════════════════════════════════════
# Pipeline Status
# ═══════════════════════════════════════════════════════════

def pipeline_header(run_id: str, model: str, steps: list[str]) -> None:
    """Cabecalho do pipeline."""
    console.print()
    console.print(Panel(
        f"[bold]Modelo:[/bold] {model}\n"
        f"[bold]Run ID:[/bold] {run_id}\n"
        f"[bold]Esteira:[/bold] {' -> '.join(steps)}",
        title="⚡ ORQUESTRADOR",
        border_style="cyan",
    ))


def pipeline_step_result(step_name: str, status: str, tok_s: float = 0,
                         elapsed_s: float = 0, detail: str = "") -> None:
    """Resultado de uma etapa do pipeline."""
    if status == "OK":
        icon = "[green]✓[/green]"
    elif status in ("TIMEOUT", "OOM_PROTECT", "ERR"):
        icon = "[red]✗[/red]"
    else:
        icon = "[yellow]?[/yellow]"

    info = f"{step_name:<15} {icon} {status:<12}"
    if tok_s:
        info += f"  {tok_s:.1f} tok/s"
    if elapsed_s:
        info += f"  {elapsed_s:.0f}s"
    if detail:
        info += f"  {detail}"
    console.print(f"  {info}")


# ═══════════════════════════════════════════════════════════
# Live log (para operacoes longas)
# ═══════════════════════════════════════════════════════════

@contextmanager
def live_log(title: str = "Log"):
    """Context manager para log ao vivo."""
    with Live(console=console, refresh_per_second=4) as live:
        lines = []
        def add(line: str):
            lines.append(line)
            live.update(Panel("\n".join(lines[-20:]), title=title))
        yield add


# ═══════════════════════════════════════════════════════════
# Compatibilidade: substitui tee() antigo
# ═══════════════════════════════════════════════════════════

def tee(msg: str) -> None:
    """Substitui a tee() antiga. Loga no console e em arquivo se configurado."""
    console.print(msg)


# ═══════════════════════════════════════════════════════════
# Thermal gauge
# ═══════════════════════════════════════════════════════════

def thermal_gauge(temp_c: float, tier: str, max_tokens: int) -> None:
    """Exibe gauge termico colorido."""
    if temp_c < 70:
        color = "green"
    elif temp_c < 80:
        color = "yellow"
    elif temp_c < 90:
        color = "orange1"
    else:
        color = "red"

    bar_len = min(int(temp_c / 105 * 20), 20)
    bar = "█" * bar_len + "░" * (20 - bar_len)

    console.print(
        f"  🌡  [{color}]{bar}[/{color}] {temp_c:.0f}°C  "
        f"tier=[bold]{tier}[/bold]  "
        f"max_tok={max_tokens}"
    )
