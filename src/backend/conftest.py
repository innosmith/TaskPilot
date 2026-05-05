"""Pytest-Konfiguration für das Backend."""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: Tests die echte externe Dienste aufrufen (LLM, APIs)"
    )
