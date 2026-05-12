"""Playwright E2E Test-Konfiguration.

Tests laufen gegen die Integration- oder Dev-Umgebung.
Credentials: TP_TEST_PASSWORD / TP_OWNER_PASSWORD aus .env.test,
Fallback auf interaktiven getpass-Prompt.

Login wird einmal pro Session durchgefuehrt (storageState-Pattern),
alle Tests teilen den authentifizierten Zustand.
"""

import getpass
import os
import tempfile

import pytest
from playwright.sync_api import Page, Browser, BrowserContext

BASE_URL = os.environ.get("TP_E2E_BASE_URL", "http://localhost:3100")
BACKEND_URL = os.environ.get("TP_E2E_BACKEND_URL", "http://localhost:8100")

OWNER_EMAIL = os.environ.get("TP_TEST_EMAIL") or os.environ.get("TP_OWNER_EMAIL", "")
if not OWNER_EMAIL:
    raise RuntimeError("TP_TEST_EMAIL oder TP_OWNER_EMAIL muss gesetzt sein")
MEMBER_EMAIL = os.environ.get("TP_TEST_MEMBER_EMAIL", "")

_owner_password: str = ""
_member_password: str = ""


def _resolve_password(env_keys: list[str], label: str) -> str:
    """Passwort aus Env-Variablen lesen, Fallback auf getpass."""
    for key in env_keys:
        val = os.environ.get(key, "")
        if val:
            return val
    try:
        return getpass.getpass(f"  {label}: ")
    except (EOFError, OSError):
        return ""


@pytest.fixture(scope="session", autouse=True)
def _resolve_credentials():
    """Credentials einmal pro Session aufloesen."""
    global _owner_password, _member_password

    print(f"\n{'='*60}")
    print(f"  TaskPilot E2E-Tests")
    print(f"  Ziel: {BASE_URL}")
    print(f"{'='*60}\n")

    print(f"  Owner-Email: {OWNER_EMAIL}")
    _owner_password = _resolve_password(
        ["TP_TEST_PASSWORD", "TP_OWNER_PASSWORD"],
        "Owner-Passwort",
    )
    if not _owner_password:
        print("  Kein Owner-Passwort — Owner-Tests werden uebersprungen.")

    if MEMBER_EMAIL:
        print(f"  Member-Email: {MEMBER_EMAIL}")
        _member_password = _resolve_password(
            ["TP_TEST_MEMBER_PASSWORD"],
            "Member-Passwort",
        )
        if not _member_password:
            print("  Kein Member-Passwort — Member-Tests werden uebersprungen.")
    else:
        print("  Kein TP_TEST_MEMBER_EMAIL — Member-Tests werden uebersprungen.")

    print(f"\n{'='*60}\n")


def _login(page: Page, email: str, password: str) -> None:
    """Login ueber die UI mit defensiver Fehlerpruefung."""
    page.goto("/login")
    page.wait_for_selector("input[type='email'], input[name='email']", timeout=10000)

    page.fill("input[type='email'], input[name='email']", email)
    page.fill("input[type='password'], input[name='password']", password)
    page.click("button[type='submit']")

    page.wait_for_timeout(2000)

    error_el = page.locator("[role='alert'], .text-red-500, .text-red-600, .text-destructive").first
    if error_el.count() > 0 and error_el.is_visible():
        msg = error_el.inner_text()
        raise RuntimeError(f"Login fehlgeschlagen: {msg}")

    page.wait_for_url(lambda url: "/login" not in url, timeout=15000)


@pytest.fixture(scope="session")
def _owner_storage_state(browser: Browser) -> str | None:
    """Einmal einloggen, storageState speichern fuer alle Tests."""
    if not _owner_password:
        return None
    ctx = browser.new_context(
        base_url=BASE_URL,
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    pg = ctx.new_page()
    _login(pg, OWNER_EMAIL, _owner_password)
    state_file = tempfile.mktemp(suffix=".json")
    ctx.storage_state(path=state_file)
    pg.close()
    ctx.close()
    return state_file


@pytest.fixture(scope="session")
def browser_context_args(_owner_storage_state) -> dict:
    args: dict = {
        "base_url": BASE_URL,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }
    if _owner_storage_state:
        args["storage_state"] = _owner_storage_state
    return args


@pytest.fixture
def owner_page(page: Page, _owner_storage_state) -> Page:
    """Page mit Owner-Session (via storageState, kein erneuter Login)."""
    if not _owner_storage_state:
        pytest.skip("Kein Owner-Passwort eingegeben")
    return page


@pytest.fixture
def anon_page(browser: Browser) -> Page:
    """Page ohne Authentifizierung (fuer Login-Flow-Tests)."""
    ctx = browser.new_context(
        base_url=BASE_URL,
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    pg = ctx.new_page()
    yield pg
    pg.close()
    ctx.close()


@pytest.fixture
def member_page(browser: Browser) -> Page:
    """Eingeloggte Page als Member (eigener Browser-Context)."""
    if not MEMBER_EMAIL or not _member_password:
        pytest.skip("Kein Member-Account konfiguriert")
    ctx = browser.new_context(
        base_url=BASE_URL,
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    pg = ctx.new_page()
    _login(pg, MEMBER_EMAIL, _member_password)
    yield pg
    pg.close()
    ctx.close()
