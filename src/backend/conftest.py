"""Pytest-Konfiguration für das Backend."""

import os

os.environ["TP_ENV"] = "test"
os.environ.setdefault("TP_DB_NAME", "taskpilot_test")
os.environ.setdefault("TP_DB_HOST", "localhost")
os.environ.setdefault("TP_DB_PORT", "5435")
os.environ.setdefault("TP_DB_USER", "taskpilot")
os.environ.setdefault("TP_DB_PASSWORD", "taskpilot_test_2026")
os.environ.setdefault("TP_SECRET_KEY", "test-secret-change-in-production")
os.environ.setdefault("TP_OWNER_EMAIL", "test-owner@innosmith.ai")
os.environ.setdefault("TP_OWNER_PASSWORD", "test-owner-pass-2026")
os.environ.setdefault("TP_OWNER_DISPLAY_NAME", "Test Owner")
os.environ.setdefault("TP_DEBUG", "false")

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: Tests die echte externe Dienste aufrufen (LLM, APIs)"
    )
    config.addinivalue_line(
        "markers", "db: Tests die eine echte PostgreSQL-Verbindung brauchen"
    )
