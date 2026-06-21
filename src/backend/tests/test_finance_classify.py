"""Tests fuer die Cash-Bucket-Klassifikation der Liquiditaetsprognose.

Prüft `_classify_bank_outflow`: insbesondere die Trennung von Pensionskasse
(BVG, Konten 5720-5729 / 2271-2279) und den uebrigen monatlich wiederkehrenden
Sozialversicherungen (AHV/IV/EO/ALV/FAK/UVG/KTG, Konten 5700-5719 / 5730-5799 /
2270) gemaess Schweizer KMU-Kontenrahmen.
"""

import pytest

from app.routers.finance import _classify_bank_outflow


class TestClassifyBankOutflow:
    """Gegenkonto-basierte Zuordnung zu Liquiditaets-Buckets."""

    @pytest.mark.parametrize("gegen_no", [5720, 5725, 5729, 2271, 2275, 2279])
    def test_pensionskasse_bvg(self, gegen_no):
        """Berufliche Vorsorge (Aufwand 5720-5729, Kontokorrent 2271-2279)."""
        assert _classify_bank_outflow(gegen_no) == "pension"

    @pytest.mark.parametrize("gegen_no", [5700, 5710, 5719, 5730, 5740, 5799, 2270])
    def test_uebrige_sozialversicherungen(self, gegen_no):
        """AHV/IV/EO/ALV/FAK (5700-5719), UVG/KTG (5730-5799), Schuld 2270."""
        assert _classify_bank_outflow(gegen_no) == "social"

    def test_pension_nicht_in_social(self):
        """BVG-Konten duerfen nicht mehr im social-Bucket landen."""
        assert _classify_bank_outflow(5720) != "social"
        assert _classify_bank_outflow(2271) != "social"

    @pytest.mark.parametrize("gegen_no", [5000, 5050, 5099, 5800, 5850, 5899])
    def test_personal(self, gegen_no):
        assert _classify_bank_outflow(gegen_no) == "personnel"

    @pytest.mark.parametrize("gegen_no", [2200, 2206, 8900, 8999])
    def test_steuern(self, gegen_no):
        assert _classify_bank_outflow(gegen_no) == "tax"

    @pytest.mark.parametrize("gegen_no", [2100, 2199, 2261, 2400, 2999])
    def test_finanzierung(self, gegen_no):
        assert _classify_bank_outflow(gegen_no) == "fin"

    @pytest.mark.parametrize("gegen_no", [1500, 1599])
    def test_investitionen(self, gegen_no):
        assert _classify_bank_outflow(gegen_no) == "invest"

    @pytest.mark.parametrize("gegen_no", [2000, 2099, 4000, 6500])
    def test_operativ_rest(self, gegen_no):
        """Kreditoren (2000-2099) und uebriger Aufwand bleiben operativ."""
        assert _classify_bank_outflow(gegen_no) == "op"
