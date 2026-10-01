import importlib

import pytest

MODULES = ["ingestion", "canonical", "setpieces", "metrics", "recs", "models", "reports"]


@pytest.mark.parametrize("name", MODULES)
def test_modules_import(name: str) -> None:
    module = importlib.import_module(f"kurgu_analytics.{name}")
    assert module.__doc__
