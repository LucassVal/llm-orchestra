def test_audit_imports():
    import shared.compliance_check  # noqa: F401 — smoke test
    assert True
