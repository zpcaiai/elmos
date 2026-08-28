from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from etgb.discovery import load_surface, surface_coverage_report
from etgb.io import package_root


def _sdk_module():
    path = package_root() / "integrations/harness/full_product_adapter_sdk.py"
    spec = importlib.util.spec_from_file_location("full_product_adapter_sdk", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_product_surface_manifest_has_no_undeclared_features() -> None:
    root = package_root()
    report = surface_coverage_report(root, load_surface(root / "examples/product-surface.yaml"))
    assert report["complete"] is True, report
    assert report["implemented_surface_count"] == 5
    assert report["mapped_feature_count"] == 5


def test_product_surface_audit_rejects_unknown_feature() -> None:
    root = package_root()
    surface = load_surface(root / "examples/product-surface.yaml")
    surface["jobs"] = [{"id": "unknown-job", "feature_id": "unknown-domain.unknown-feature"}]
    report = surface_coverage_report(root, surface)
    assert report["complete"] is False
    assert any("undeclared feature" in error for error in report["errors"])


def test_adapter_registry_fails_closed_when_adapter_missing() -> None:
    sdk = _sdk_module()
    registry = sdk.AdapterRegistry()
    try:
        registry.resolve("external-payment-sandbox-harness")
    except sdk.AdapterUnavailableError:
        pass
    else:
        raise AssertionError("missing adapter did not fail closed")
