"""Cierre del SPX: una sola función en todo el proyecto, y que grite cuando no hay datos."""
import pandas as pd
import pytest

import src.datos as datos
from src.odte import precio


class _TickerFalso:
    """Reemplaza a yfinance: devuelve un cierre fijo, o nada si la fecha es '2026-10-03' (sábado)."""
    def __init__(self, simbolo):
        self.simbolo = simbolo

    def history(self, start, end):
        if start == "2026-10-03":
            return pd.DataFrame(columns=["Close"])
        return pd.DataFrame({"Close": [7722.72]}, index=[pd.Timestamp(start)])


@pytest.fixture(autouse=True)
def sin_internet(monkeypatch):
    monkeypatch.setattr(datos.yf, "Ticker", _TickerFalso)


def test_devuelve_el_cierre():
    assert datos.precio_spx("2026-10-02") == pytest.approx(7722.72)


def test_sin_datos_grita_con_mensaje_claro():
    with pytest.raises(RuntimeError, match="fin de semana o feriado"):
        datos.precio_spx("2026-10-03")


def test_una_sola_fuente():
    """El alias de odte ES la misma función: no puede volver a divergir."""
    assert precio.cierre_spx is datos.precio_spx