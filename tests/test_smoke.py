import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_import_compliance():
    from shared import compliance_check
    assert compliance_check is not None


def test_import_thermal():
    from shared import thermal_governor
    assert thermal_governor is not None


def test_py_check_self():
    from shared import py_check
    assert py_check.run() == 0
