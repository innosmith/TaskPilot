"""Zentrale Logik für die einstellbaren Parameter der Cashflow-Prognose.

Liest die finanzbezogenen Owner-Settings (default_hourly_rate, Pipeline-Gewicht,
Auffüll-Horizont, MwSt-Satz) mit sinnvollen Fallbacks. Die Werte sind bewusst
einstellbar (UI: Settings-Tab «Finanzen») und nicht hartkodiert.
"""

from dataclasses import dataclass

# Fallbacks (nur greifen, wenn der Owner nichts konfiguriert hat)
FALLBACK_DEFAULT_HOURLY_RATE = 240.0   # CHF/h, exkl. MwSt
FALLBACK_PIPELINE_WEIGHT = 0.75        # Wahrscheinlichkeit für vorläufige Projekte
FALLBACK_FILL_HORIZON_MONTHS = 4       # ab wann Auffüllung auf Baseline voll greift
FALLBACK_VAT_RATE = 0.081              # CH-Normalsatz (Fakturierungssatz)
FALLBACK_VAT_METHOD = "saldo"          # CH-Standard für KMU-Dienstleister
FALLBACK_VAT_SALDO_RATE = 0.062        # Saldosteuersatz Beratung/Dienstleistung
FALLBACK_ANNUAL_REVENUE_GOAL = 0.0     # 0 = kein Ziel gesetzt
FALLBACK_MIN_LIQUIDITY = 0.0           # 0 = keine Schwelle gesetzt
FALLBACK_TAX_CANTON = ""               # leer = kein Kanton hinterlegt
FALLBACK_CIVIL_STATUS = ""             # leer = kein Zivilstand hinterlegt

# Erlaubte MWST-Methoden
VAT_METHODS = ("saldo", "effektiv", "none")


@dataclass
class ForecastSettings:
    """Aufgelöste Prognose-Parameter."""

    default_hourly_rate: float = FALLBACK_DEFAULT_HOURLY_RATE
    pipeline_weight: float = FALLBACK_PIPELINE_WEIGHT
    fill_horizon_months: int = FALLBACK_FILL_HORIZON_MONTHS
    vat_rate: float = FALLBACK_VAT_RATE
    vat_method: str = FALLBACK_VAT_METHOD
    vat_saldo_rate: float = FALLBACK_VAT_SALDO_RATE
    annual_revenue_goal: float = FALLBACK_ANNUAL_REVENUE_GOAL
    min_liquidity: float = FALLBACK_MIN_LIQUIDITY
    tax_canton: str = FALLBACK_TAX_CANTON
    civil_status: str = FALLBACK_CIVIL_STATUS

    def net_revenue(self, gross: float) -> float:
        """Nettoumsatz aus Bruttoumsatz gemäss gewählter MWST-Methode.

        - ``saldo``: Bei der Saldosteuersatz-Methode wird auf der Rechnung der
          Normalsatz fakturiert, an die ESTV aber nur der (tiefere) Saldosteuersatz
          abgeliefert. Oekonomisch einbehalten = brutto * (1 - Saldosteuersatz).
        - ``effektiv``: brutto / (1 + Normalsatz) -- klassischer Netto-Abzug.
        - ``none``: kein MWST-Abzug (brutto = netto).
        """
        if gross is None:
            return 0.0
        if self.vat_method == "none":
            return round(gross, 2)
        if self.vat_method == "effektiv":
            return round(gross / (1 + self.vat_rate), 2)
        # Default: Saldosteuersatz-Methode
        return round(gross * (1 - self.vat_saldo_rate), 2)


def _to_float(value, fallback: float) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_int(value, fallback: int) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def get_forecast_settings_from_settings(settings: dict | None) -> ForecastSettings:
    """Prognose-Parameter aus bereits geladenem User-Settings-Dict ableiten."""
    s = settings or {}
    rate = _to_float(s.get("default_hourly_rate"), FALLBACK_DEFAULT_HOURLY_RATE)
    weight = _to_float(s.get("forecast_pipeline_weight"), FALLBACK_PIPELINE_WEIGHT)
    horizon = _to_int(s.get("forecast_fill_horizon_months"), FALLBACK_FILL_HORIZON_MONTHS)
    vat = _to_float(s.get("forecast_vat_rate"), FALLBACK_VAT_RATE)
    method = str(s.get("vat_method") or FALLBACK_VAT_METHOD).lower()
    saldo = _to_float(s.get("vat_saldo_rate"), FALLBACK_VAT_SALDO_RATE)
    goal = _to_float(s.get("annual_revenue_goal"), FALLBACK_ANNUAL_REVENUE_GOAL)
    min_liq = _to_float(s.get("min_liquidity"), FALLBACK_MIN_LIQUIDITY)
    canton = str(s.get("tax_canton") or FALLBACK_TAX_CANTON).strip()
    civil = str(s.get("civil_status") or FALLBACK_CIVIL_STATUS).strip()

    # Plausibilitäts-Grenzen
    if rate <= 0:
        rate = FALLBACK_DEFAULT_HOURLY_RATE
    weight = min(max(weight, 0.0), 1.0)
    horizon = max(horizon, 1)
    if vat < 0:
        vat = FALLBACK_VAT_RATE
    if method not in VAT_METHODS:
        method = FALLBACK_VAT_METHOD
    if saldo < 0 or saldo >= 1:
        saldo = FALLBACK_VAT_SALDO_RATE
    goal = max(goal, 0.0)
    min_liq = max(min_liq, 0.0)

    return ForecastSettings(
        default_hourly_rate=rate,
        pipeline_weight=weight,
        fill_horizon_months=horizon,
        vat_rate=vat,
        vat_method=method,
        vat_saldo_rate=saldo,
        annual_revenue_goal=goal,
        min_liquidity=min_liq,
        tax_canton=canton,
        civil_status=civil,
    )
