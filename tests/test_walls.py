"""walls.py: la descomposición del ΔGEX es exacta y cada causa cae en su componente."""
import pandas as pd
import pytest

from src.walls import descomponer, evolucion, zonas_dia


def _cadena(filas, S=7700.0):
    """filas: (symbol, tipo, strike, OI, k) -> cadena mínima con gex_contrib = OI · k."""
    c = pd.DataFrame(filas, columns=["symbol", "tipo", "strike", "open_interest", "k"])
    c["gex_contrib"] = c["open_interest"] * c.pop("k")
    c["S"] = S
    return c


AYER = _cadena([("A", "C", 7800.0, 100, 10.0),      # sigue, mismo OI, cambia k  -> solo mercado
                ("B", "P", 7600.0, 200, -5.0),      # sigue, OI sube, mismo k    -> solo posicionamiento
                ("V", "P", 7610.0, 50, -8.0)])      # vence                      -> solo vencidas
HOY = _cadena([("A", "C", 7800.0, 100, 12.0),
               ("B", "P", 7600.0, 260, -5.0),
               ("N", "C", 7790.0, 30, 11.0)])       # nueva                      -> posicionamiento entero


def test_la_suma_cierra_exacta():
    p = descomponer(AYER, HOY)
    assert p[["pos", "mer", "ven"]].to_numpy().sum() == pytest.approx(
        HOY["gex_contrib"].sum() - AYER["gex_contrib"].sum())


def test_cada_causa_en_su_componente():
    p = descomponer(AYER, HOY)
    assert (p.loc["A", "pos"], p.loc["A", "mer"]) == (0, 200)              # 100 · (12 - 10)
    assert (p.loc["B", "pos"], p.loc["B", "mer"], p.loc["B", "doi"]) == (-300, 0, 60)
    assert (p.loc["N", "pos"], p.loc["N", "doi"]) == (330, 30)
    assert (p.loc["V", "ven"], p.loc["V", "oi_venc"], p.loc["V", "doi"]) == (400, 50, 0)


def test_vencer_no_cuenta_como_posicion_cerrada():
    """V (7610) cae en la zona 7600 con B: su salida va a oi_venc, no resta al ΔOI de puts."""
    _, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY})
    fila = z[(z["fecha"] == pd.Timestamp("2026-10-16")) & (z["zona"] == 7600)].iloc[0]
    assert fila["doi_p"] == 60 and fila["oi_venc"] == 50 and fila["ven"] == 400


def test_zonas_dia_mide_carga_y_balance():
    z = zonas_dia(HOY)
    assert (z.loc[7600, "oi_p"], z.loc[7600, "pct_puts"]) == (260, 100)
    assert (z.loc[7800, "oi_c"], z.loc[7800, "gex"]) == (130, 1200 + 330)    # 7790 cae en la zona 7800


def test_evolucion_primer_dia_sin_cambios_y_resumen():
    d, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY})
    assert z.loc[z["fecha"] == pd.Timestamp("2026-10-15"), "pos"].isna().all()
    assert d.loc[pd.Timestamp("2026-10-16"), ["pos", "mer", "ven"]].sum() == pytest.approx(
        d.loc[pd.Timestamp("2026-10-16"), "gex"] - d.loc[pd.Timestamp("2026-10-15"), "gex"])


def test_una_sola_fecha_no_rompe():
    d, z = evolucion({pd.Timestamp("2026-10-15"): AYER})
    assert len(d) == 1 and z["pos"].isna().all()
