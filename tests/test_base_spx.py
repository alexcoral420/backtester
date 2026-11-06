"""Base ES - SPX: caché del SPX intradía de yfinance y base móvil (duda 3 de M4 en ODTE.md).
Sin red: yfinance se reemplaza por un falso."""
import os

import numpy as np
import pandas as pd
import pytest

from src.odte import precio

NY = "America/New_York"


def _es_falso(fecha="2026-10-14", base=lambda i: 50.0 + 0.01 * i):
    """ES de 1 min (390 barras) con un SPX conocido y una base conocida que deriva en el día."""
    idx = pd.date_range(f"{fecha} 09:30", periods=390, freq="1min", tz=NY)
    spx = 7700 + np.sin(np.arange(390) / 20) * 10
    b = np.array([base(i) for i in range(390)])
    return pd.DataFrame({"close": spx + b}, index=idx), pd.Series(spx, index=idx), pd.Series(b, index=idx)


def _spx5_de(spx1):
    """Barras de 5 min (inicio t) cuyo cierre es el SPX del minuto t+4."""
    idx = spx1.index[::5]
    return pd.DataFrame({"close": spx1.reindex(idx + pd.Timedelta(minutes=4)).values}, index=idx)


def test_base_movil_recupera_una_base_que_deriva():
    es, spx1, b = _es_falso()
    base = precio.base_movil(es, _spx5_de(spx1))
    assert base.index.equals(es.index)
    # deriva lineal: la interpolación la recupera exacta desde la primera medición (09:34)
    assert np.allclose(base.loc["2026-10-14 09:34":], b.loc["2026-10-14 09:34":])
    # antes de la primera medición se repite la más cercana
    assert np.allclose(base.loc[:"2026-10-14 09:33"], b.loc["2026-10-14 09:34"])


def test_base_movil_grita_si_al_es_le_faltan_barras():
    es, spx1, _ = _es_falso()
    spx5 = _spx5_de(spx1)
    es = es.drop(spx5.index[:20] + pd.Timedelta(minutes=4))    # 20 de 78 mediciones sin ES
    with pytest.raises(ValueError, match="mediciones tienen barra del ES"):
        precio.base_movil(es, spx5)


def test_barras_esperadas_dia_normal_y_cierre_temprano():
    assert precio.barras_esperadas("2026-10-14", "1m") == 390
    assert precio.barras_esperadas("2026-10-14", "5m") == 78
    assert precio.barras_esperadas("2026-11-27", "1m") == 210     # cierre 13:00
    assert precio.barras_esperadas("2026-11-27", "5m") == 42


def test_intervalo_desconocido_grita():
    with pytest.raises(ValueError, match="no soportado"):
        precio.ruta_spx_yf("2026-10-14", "15m")


def test_metodo_base_desconocido_grita():
    with pytest.raises(ValueError, match="metodo_base"):
        precio.spx_1min("2026-10-14", metodo_base="mediana")


class _TickerFalso:
    """history(): 5m de un día completo con barras de pre y post mercado; vacío el 2026-10-17 (sábado)."""
    llamadas = 0

    def __init__(self, simbolo):
        assert simbolo == "^GSPC"

    def history(self, start, end, interval):
        _TickerFalso.llamadas += 1
        if start == "2026-10-17":
            return pd.DataFrame()
        idx = pd.date_range(f"{start} 09:00", f"{start} 16:30", freq="5min", tz=NY, inclusive="left")
        return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 0}, index=idx)


@pytest.fixture
def cache_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(precio, "CARPETA_CACHE", str(tmp_path))
    monkeypatch.setattr(precio.yf, "Ticker", _TickerFalso)
    _TickerFalso.llamadas = 0
    return tmp_path


def test_cachear_guarda_solo_la_sesion_y_no_repite(cache_temporal):
    t = precio.cachear_spx_intradia(["2026-10-14"], intervalos=("5m",))
    assert t.iloc[0]["estado"] == "bajado" and t.iloc[0]["barras"] == 78 == t.iloc[0]["esperadas"]
    df = precio.leer_spx_yf("2026-10-14", "5m")
    assert df.index.min().strftime("%H:%M") == "09:30" and df.index.max().strftime("%H:%M") == "15:55"
    assert str(df.index.tz) == NY
    t2 = precio.cachear_spx_intradia(["2026-10-14"], intervalos=("5m",))
    assert t2.iloc[0]["estado"] == "caché" and _TickerFalso.llamadas == 1


def test_sin_datos_no_guarda_nada(cache_temporal):
    t = precio.cachear_spx_intradia(["2026-10-17"], intervalos=("5m",))
    assert t.iloc[0]["estado"] == "sin datos"
    assert not os.listdir(cache_temporal)


def test_leer_grita_si_falta_o_esta_incompleto(cache_temporal):
    with pytest.raises(RuntimeError, match="cachear_spx_intradia"):
        precio.leer_spx_yf("2026-10-14", "5m")
    idx = pd.date_range("2026-10-14 09:30", periods=70, freq="5min", tz=NY)
    pd.DataFrame({"close": 1.0}, index=idx).to_parquet(precio.ruta_spx_yf("2026-10-14", "5m"))
    with pytest.raises(ValueError, match="70 barras, se esperaban 78"):
        precio.leer_spx_yf("2026-10-14", "5m")
