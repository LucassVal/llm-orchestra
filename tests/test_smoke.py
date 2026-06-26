import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_import_thermal():
    from shared import thermal_governor
    assert thermal_governor is not None


def test_import_dispatch():
    from shared import dispatch_log
    assert dispatch_log is not None


def test_import_circularity():
    from shared import circularity_check
    assert circularity_check is not None


def test_py_check_self():
    from shared import py_check
    result = py_check.check_file(Path(__file__).parent.parent / "shared" / "dispatch_log.py")
    assert result[0] is True  # (bool, error_msg)
