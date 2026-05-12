"""Playwright E2E Test-Konfiguration.

Tests laufen gegen die Integration- oder Dev-Umgebung.
Passwoerter werden bei jedem Testlauf interaktiv abgefragt (getpass) —
sie landen nie in Dateien, Logs oder Umgebungsvariablen.
"""

import getpass
import os
import sys

import pytest
from playwright.sync_api import Page, BrowserContext


BASE_URL = os.environ.get("TP_E2E_BASE_URL", "http://localhost:3100")
BACKEND_URL = os.environ.get("TP_E2E_BACKEND_URL", "http://localhost:8100")

OWNER_EMAIL = os.environ.get("TP_TEST_EMAIL") or os.environ.get("TP_OWNER_EMAIL", "")
if not OWNER_EMAIL:
    raise RuntimeError("TP_TEST_EMAIL oder TP_OWNER_EMAIL muss gesetzt sein")
MEMBER_EMAIL = os.environ.get("TP_TEST_MEMBER_EMAIL", "")

# Passwoerter: werden INTERAKTIV abgefragt, nie aus Dateien gelesen
_owner_password: str | None = None
_member_password: str | None = None


def _prompt_credentials():
    """Fragt Passwoerter einmal pro Session interaktiv ab."""
    global _owner_password, _member_password

    if _owner_password is not None:
        return

    print(f"\n{'='*60}")
    print(f"  TaskPilot E2E-Tests — Credential-Eingabe")
    print(f"  Ziel: {BASE_URL}")
    print(f"{'='*60}\n")

    print(f"  Owner-Email: {OWNER_EMAIL}")
    _owner_password = getpass.getpass(f"  Owner-Passwort: ")

    if not _owner_password:
        print("\n  Kein Owner-Passwort eingegeben — Owner-Tests werden uebersprungen.")
        _owner_password = ""

    if MEMBER_EMAIL:
        print(f"\n  Member-Email: {MEMBER_EMAIL}")
        _member_password = getpass.getpass(f"  Member-Passwort: ")
        if not _member_password:
            print("  Kein Member-Passwort — Member-Tests werden uebersprungen.")
            _member_password = ""
    else:
        print("\n  Kein TP_TEST_MEMBER_EMAIL gesetzt — Member-Tests werden uebersprungen.")
        _member_password = ""

    print(f"\n{'='*60}\n")


@pytest.fixture(scope="session", autouse=True)
def prompt_credentials_once():
    """Fragt Credentials einmal zu Beginn der Session ab."""
    _prompt_credentials()


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "base_url": BASE_URL,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }


def _login(page: Page, email: str, password: str) -> None:
    """Fuehrt den Login-Flow auf der Login-Seite durch."""
    page.goto("/login")
    page.wait_for_selector("input[type='email'], input[name='email']", timeout=10000)

    page.fill("input[type='email'], input[name='email']", email)
    page.fill("input[type='password'], input[name='password']", password)
    page.click("button[type='submit']")

    page.wait_for_url(lambda url: "/login" not in url, timeout=15000)


@pytest.fixture
def owner_page(page: Page) -> Page:
    """Eingeloggte Page als Owner."""
    if not _owner_password:
        pytest.skip("Kein Owner-Passwort eingegeben")
    _login(page, OWNER_EMAIL, _owner_password)
    return page


@pytest.fixture
def member_page(context: BrowserContext) -> Page:
    """Eingeloggte Page als Member (eigener Browser-Context)."""
    if not MEMBER_EMAIL or not _member_password:
        pytest.skip("Kein Member-Account konfiguriert")
    pg = context.new_page()
    _login(pg, MEMBER_EMAIL, _member_password)
    return pg
