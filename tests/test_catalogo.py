"""
Filtrado de 0DTE. Regresión del primer bug del proyecto: la columna `expiration`
de Databento es medianoche UTC, y en Nueva York eso cae el DÍA ANTERIOR.
"""
import pandas as pd

from src.odte.catalogo import filtrar_0dte


def hacer_catalogo():
    """Tres opciones: dos vencen el 30-sep y una el 1-oct, con `expiration` como la da Databento."""
    return pd.DataFrame({
        "raw_symbol": ["SPXW  260930C07700000", "SPXW  260930P07650000", "SPXW  261001P03400000"],
        "expiration": pd.to_datetime(["2026-10-01 00:00", "2026-10-01 00:00", "2026-10-02 00:00"], utc=True),
        "instrument_class": ["C", "P", "P"],
        "strike_price": [7700.0, 7650.0, 3400.0],
    })


def test_toma_la_fecha_del_simbolo_no_de_expiration():
    r = filtrar_0dte(hacer_catalogo(), "2026-09-30")
    assert sorted(r["raw_symbol"]) == ["SPXW  260930C07700000", "SPXW  260930P07650000"]


def test_no_mezcla_el_dia_siguiente():
    """La opción del 1-oct tiene expiration = 1-oct 00:00 UTC = 30-sep 20:00 NY. NO debe colarse."""
    r = filtrar_0dte(hacer_catalogo(), "2026-09-30")
    assert "SPXW  261001P03400000" not in set(r["raw_symbol"])


def test_vencimiento_real_es_16h_nueva_york():
    r = filtrar_0dte(hacer_catalogo(), "2026-09-30")
    venc = r["venc_ny"].iloc[0]
    assert venc == pd.Timestamp("2026-09-30 16:00", tz="America/New_York")


def test_dia_sin_0dte_devuelve_vacio():
    r = filtrar_0dte(hacer_catalogo(), "2026-10-05")
    assert r.empty