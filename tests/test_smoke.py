import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_thermal_governor():
    from shared import thermal_governor
    gov = thermal_governor.get_governor()
    assert gov is not None
    assert hasattr(gov, 'should_throttle')


def test_dispatch_log():
    from shared import dispatch_log
    dh = dispatch_log.create('test-agent', 'mock-test', model='4b')
    assert len(dh) == 16  # hash hex
    dispatch_log.complete(dh, 'OK', tok_s=10.5)


def test_pipeline_status():
    import json
    status_file = Path(__file__).parent.parent / 'bench_status.json'
    assert status_file.exists()
    d = json.loads(status_file.read_text())
    assert 'phase' in d


def test_ollama_models():
    import subprocess
    r = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
    assert r.returncode == 0
    models = [line for line in r.stdout.split("\n") if line.strip()][1:]
    assert len(models) >= 3
