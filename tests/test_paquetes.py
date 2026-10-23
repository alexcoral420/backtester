"""paquetes.py: combos C+P del mismo strike, sintético vs straddle por el lado de cada pata."""
import pandas as pd

from src.paquetes import combos_cp, lado_pata, resumen_combos

T0 = pd.Timestamp("2026-10-15 10:00:00", tz="America/New_York")
C, P = "SPXW  261016C07750000", "SPXW  261016P07750000"
P2 = "SPXW  261016P07700000"


def _tr(filas):
    """filas: (ms desde T0, symbol, precio, size). bid 9, ask 11 (medio 10)."""
    t = pd.DataFrame([dict(ts=T0 + pd.Timedelta(milliseconds=ms), symbol=s, price=px, size=sz,
                           bid_px_00=9.0, ask_px_00=11.0) for ms, s, px, sz in filas]).set_index("ts")
    return t


def test_lado_de_la_pata():
    t = _tr([(0, C, 10.5, 1), (1, C, 9.5, 1), (2, C, 10.0, 1)])
    t.loc[t.index[2], "bid_px_00"] = 0            # sin cotización -> 0
    assert list(lado_pata(t)) == [1, -1, 0]


def test_sintetico_straddle_y_lo_que_no_es_combo():
    t = _tr([(0, C, 10.5, 50), (0, P, 9.5, 50),       # sintético: C arriba, P abajo
             (5, C, 10.5, 20), (5, P, 10.6, 20),       # straddle comprado
             (9, C, 9.2, 30), (9, P, 9.4, 30),         # straddle vendido
             (20, C, 10.5, 10), (20, P, 9.5, 11),      # tamaños distintos -> no es combo
             (30, C, 10.5, 10), (30, P2, 9.5, 10),     # strikes distintos -> no es combo
             (40, C, 10.5, 10), (41, P, 9.5, 10)])     # otro milisegundo -> no es combo
    r = combos_cp(t).set_index("size")
    assert len(r) == 3
    assert r.loc[50, "forma"] == "sintetico" and r.loc[50, "publico"] == ""
    assert (r.loc[20, "forma"], r.loc[20, "publico"]) == ("straddle", "compra")
    assert (r.loc[30, "forma"], r.loc[30, "publico"]) == ("straddle", "vende")


def test_resumen_por_zona():
    r = resumen_combos(combos_cp(_tr([(0, C, 10.5, 50), (0, P, 9.5, 50), (5, C, 10.5, 20), (5, P, 10.6, 20)])),
                       pd.Series({7750.0: 400}))
    f = r.loc[7750]
    assert (f["sintetico"], f["straddle"], f["en_combos"], f["straddle_neto"]) == (50, 20, 140, 20)
    assert f["pct_en_combos"] == 35 and round(f["pct_sintetico"], 1) == 71.4
