"""Tests fuer die reine Diff-Logik des Self-Learning-Service.

Prueft die signal-relevanten Hilfsfunktionen ohne DB/LLM:
- html_to_text: HTML -> Plaintext
- strip_quoted_history: zitierten Original-Thread abschneiden
- compute_draft_diff: "saubere" Freigabe vs. echter Stil-Edit erkennen
"""

from app.services.learning import (
    compute_draft_diff,
    extract_salutation_signature,
    html_to_text,
    strip_quoted_history,
)


class TestExtractSalutationSignature:
    def test_informal_du_greeting_and_closing(self):
        body = "Hallo Peter,\n\nDanke dir für die Rückmeldung. Ich melde mich.\n\nLG Anthony"
        out = extract_salutation_signature(body)
        assert out["greeting"] == "Hallo Peter"
        assert out["register"] == "du"
        assert out["closing"].lower().startswith("lg")

    def test_formal_sie_greeting(self):
        body = (
            "Sehr geehrter Herr Müller,\n\nBesten Dank für Ihre Anfrage.\n\n"
            "Freundliche Grüsse\nAnthony Smith"
        )
        out = extract_salutation_signature(body)
        assert out["greeting"].startswith("Sehr geehrter Herr Müller")
        assert out["register"] == "sie"
        assert "grüsse" in out["closing"].lower()

    def test_no_signals_returns_empty(self):
        assert extract_salutation_signature("") == {}
        assert "greeting" not in extract_salutation_signature("Text ohne Anrede.")


class TestHtmlToText:
    def test_strips_tags_and_entities(self):
        html = "<p>Hallo&nbsp;Welt</p><br><div>Gr&uuml;sse</div>"
        out = html_to_text(html)
        assert "Hallo Welt" in out
        assert "<" not in out and ">" not in out

    def test_empty(self):
        assert html_to_text(None) == ""
        assert html_to_text("") == ""


class TestStripQuotedHistory:
    def test_cuts_at_von_marker(self):
        body = "Mein neuer Text.\nVon: chef@firma.ch\nGesendet: gestern\nAlter Inhalt"
        out = strip_quoted_history(body)
        assert out == "Mein neuer Text."

    def test_cuts_at_underscore_separator(self):
        body = "Antwort hier.\n______________\nOriginalnachricht"
        out = strip_quoted_history(body)
        assert out == "Antwort hier."

    def test_no_marker_keeps_all(self):
        body = "Nur ein kurzer Text ohne Zitat."
        assert strip_quoted_history(body) == body


class TestComputeDraftDiff:
    def test_identical_is_clean(self):
        html = "<p>Danke fuer Ihre Nachricht. Ich melde mich morgen.</p>"
        diff, is_clean = compute_draft_diff(html, html)
        assert is_clean is True
        assert diff == ""

    def test_whitespace_only_change_is_clean(self):
        a = "<p>Danke   fuer  Ihre Nachricht.</p>"
        b = "<p>Danke fuer Ihre Nachricht.</p>"
        _, is_clean = compute_draft_diff(a, b)
        assert is_clean is True

    def test_real_edit_detected(self):
        a = "<p>Danke fuer Ihre Nachricht. Ich melde mich morgen.</p>"
        b = "<p>Besten Dank fuer Ihre Mail. Ich melde mich naechste Woche.</p>"
        diff, is_clean = compute_draft_diff(a, b)
        assert is_clean is False
        assert diff  # nicht leer

    def test_only_quoted_history_differs_is_clean(self):
        # Gleicher neuer Text, aber unterschiedlich zitierter Verlauf -> sauber.
        a = "<p>Passt, danke!</p><p>Von: a@x.ch</p><p>Alte Mail A</p>"
        b = "<p>Passt, danke!</p><p>Von: a@x.ch</p><p>Komplett andere alte Mail B</p>"
        _, is_clean = compute_draft_diff(a, b)
        assert is_clean is True
