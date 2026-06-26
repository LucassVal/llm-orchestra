# nc.ps1 — Bench-LLM v5: PowerShell mirror do Makefile (completo)
# Espelho 1:1 do ~/build/Makefile para Windows
# Autoridade: T2 (interface) | Parent: build/RULES.md (T1)

param(
    [Parameter(Position=0)]
    [string]$Command = "help",

    [string]$Modelo = "4b",
    [string]$Prompt = "",
    [string]$Perfil = "agent_default",
    [string]$Contract = ""
)

$BUILD = "$HOME\build"

function boot { Push-Location $BUILD; python shared/compliance_check.py; Pop-Location }
function clean { Push-Location $BUILD; rm -r -Force logs/*.log,__pycache__,*/\__pycache__,.pytest_cache 2>$null; Write-Host "limpo" }
function test { Push-Location $BUILD; pytest tests/ -v; Pop-Location }
function install { pip install -q ruff isort pytest mock aislop; Push-Location $BUILD; make hook-install; Pop-Location; Write-Host "instalado" }
function lint { Push-Location $BUILD; ruff check . --exclude llama.cpp; isort --check-only --diff . --skip llama.cpp --skip __pycache__; Pop-Location }
function gate { Push-Location $BUILD; python shared/pre_commit_hook.py; Pop-Location }
function rules { Push-Location $BUILD; python shared/rule_check.py; Pop-Location }
function antimock { Push-Location $BUILD; python shared/anti_mock_scan.py; Pop-Location }
function validate { Push-Location $BUILD; python shared/system_validate.py; Pop-Location }
function tools { Push-Location $BUILD; python shared/tools_gate.py; Pop-Location }
function dispatch { Push-Location $BUILD; python shared/dispatch_log.py list; Pop-Location }

function status { Push-Location $BUILD; python meta_orchestrator.py --status; Pop-Location }
function stop { Push-Location $BUILD; python meta_orchestrator.py --stop; Pop-Location }
function pipeline-4b { Push-Location $BUILD; python test-4b/orchestrator.py; Pop-Location }
function pipeline-coder { Push-Location $BUILD; python test-coder/orchestrator.py; Pop-Location }
function pipeline-gemma { Push-Location $BUILD; python test-gemma/orchestrator.py; Pop-Location }
function pipeline-all { Push-Location $BUILD; python meta_orchestrator.py; Pop-Location }
function stress { Push-Location $BUILD; python bench_orchestrator.py --discover --stress --model $Modelo; Pop-Location }
function ppl { Push-Location $BUILD; python bench_orchestrator.py --discover --ppl-only --model $Modelo; Pop-Location }
function sweep { Push-Location $BUILD; python bench_sweep.py --model-name $Modelo --config $BUILD\test-4b\sweep_config.json; Pop-Location }
function run { Push-Location $BUILD; python meta_orchestrator.py --run $Prompt --model $Modelo --profile $Perfil; Pop-Location }
function serve { Push-Location $BUILD; python meta_orchestrator.py --serve --model $Modelo; Pop-Location }
function report { Push-Location $BUILD; python meta_orchestrator.py --report; Pop-Location }
function report-obsidian { Push-Location $BUILD; python meta_orchestrator.py --report --obsidian; Pop-Location }
function agent-profiles { Push-Location $BUILD; python shared/agent_factory.py list-profiles; Pop-Location }
function agent-validate { Push-Location $BUILD; python shared/agent_factory.py validate --contract $Contract; Pop-Location }
function agent-create { Push-Location $BUILD; python shared/agent_factory.py create --contract $Contract; Pop-Location }
function daemon-start { Push-Location $BUILD; python meta_orchestrator.py --daemon start; Pop-Location }
function daemon-stop { Push-Location $BUILD; python meta_orchestrator.py --daemon stop; Pop-Location }
function daemon-status { Push-Location $BUILD; python meta_orchestrator.py --daemon status; Pop-Location }

switch ($Command) {
    "boot" { boot }
    "clean" { clean }
    "test" { test }
    "install" { install }
    "audit" { audit }
    "lint" { lint }
    "deps" { deps }
    "gate" { gate }
    "rules" { rules }
    "antimock" { antimock }
    "validate" { validate }
    "tools" { tools }
    "dispatch" { dispatch }
    "status" { status }
    "stop" { stop }
    "pipeline-4b" { pipeline-4b }
    "pipeline-coder" { pipeline-coder }
    "pipeline-gemma" { pipeline-gemma }
    "pipeline-all" { pipeline-all }
    "stress" { stress }
    "ppl" { ppl }
    "sweep" { sweep }
    "run" { run }
    "serve" { serve }
    "report" { report }
    "report-obsidian" { report-obsidian }
    "agent-profiles" { agent-profiles }
    "agent-validate" { agent-validate }
    "agent-create" { agent-create }
    "daemon-start" { daemon-start }
    "daemon-stop" { daemon-stop }
    "daemon-status" { daemon-status }
    default { Write-Host "Bench-LLM v5 | boot status stop pipeline-4b pipeline-coder pipeline-gemma pipeline-all stress ppl run report report-obsidian agent-profiles agent-validate agent-create daemon-start daemon-stop daemon-status" }
}
