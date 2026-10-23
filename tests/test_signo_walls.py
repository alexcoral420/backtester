"""signo_walls.py: emparejamiento ΔOI ↔ flujo del día anterior, huecos y veredicto por zona y tipo."""
import pandas as pd

from src.signo_walls import comparar, elegir_series, flujo_por_dia, pares_doi

D1, D2, D3, D4 = (pd.Timestamp(f"2026-10-{d}") for d in (15, 16, 19, 21))
MERCADO = [D1, D2, D3, pd.Timestamp("2026-10-20"), D4]          # 10-20 es día de mercado pero sin archivo
NULA = {"C": "vende", "P": "compra"}


def _cadena(filas):
    return pd.DataFrame(filas, columns=["symbol", "tipo", "strike", "open_interest"])


CADENAS = {D1: _cadena([("P1", "P", 7700.0, 1000), ("C1", "C", 7750.0, 500), ("V", "P", 7700.0, 300)]),
           D2: _cadena([("P1", "P", 7700.0, 2000), ("C1", "C", 7750.0, 500)]),                 # V venció
           D3: _cadena([("P1", "P", 7700.0, 2000), ("C1", "C", 7750.0, 1500), ("P2", "P", 7710.0, 50)]),
           D4: _cadena([("P1", "P", 7700.0, 9000), ("C1", "C", 7750.0, 1500), ("P2", "P", 7710.0, 50)])}


def _trades(filas):
    """filas: (symbol, dia, precio, size). bid 1, ask 3: precio 3 = compra, 1 = venta, 2 = indet, 4 = complejo."""
    t = pd.DataFrame(filas, columns=["symbol", "dia", "price", "size"])
    t["bid_px_00"], t["ask_px_00"] = 1.0, 3.0
    from src.odte.clasificacion import clasificar_trades
    return clasificar_trades(t, estricto=True)


def test_pares_usan_el_dia_anterior_y_marcan_huecos():
    p = pares_doi(CADENAS, MERCADO).set_index(["symbol", "fecha"])
    assert (p.loc[("P1", D2), "dia_flujo"], p.loc[("P1", D2), "doi"], p.loc[("P1", D2), "sesiones"]) == (D1, 1000, 1)
    assert p.loc[("P2", D3), "doi"] == 50                                    # nueva: OI_ayer = 0
    assert p.loc[("P1", D4), "sesiones"] == 2                                # 10-19 -> 10-21 salta el 10-20
    assert "V" not in p.index.get_level_values("symbol")                     # vencer no es un par


def test_elegir_series_ignora_huecos_y_cubre_el_umbral():
    e = elegir_series(pares_doi(CADENAS, MERCADO), [7700, 7750])
    assert e["P1"] == (7700, "P") and e["C1"] == (7750, "C")
    assert "P2" not in e                     # P1 (1000) ya cubre > 80% de 1050 (el +7000 del hueco no cuenta)


def test_flujo_por_dia_regla_estricta():
    f = flujo_por_dia(_trades([("P1", D1, 3.0, 10), ("P1", D1, 1.0, 4), ("P1", D1, 2.0, 7), ("P1", D1, 4.0, 2)]))
    fila = f.iloc[0]
    assert (fila["compra"], fila["venta"], fila["indet"], fila["complejo"], fila["neto"]) == (10, 4, 9, 2, 6)


def test_comparar_confirma_contradice_y_no_usa_el_flujo_del_hueco():
    pares = pares_doi(CADENAS, MERCADO)
    tr = _trades([("P1", D1, 3.0, 900),         # público COMPRA puts, ΔOI +1000 -> confirma la nula de puts
                  ("C1", D2, 3.0, 800),         # público COMPRA calls, ΔOI +1000 -> CONTRADICE (nula: vende)
                  ("P1", D3, 1.0, 5000)])       # flujo del par con hueco: no debe contar
    r = comparar(pares, flujo_por_dia(tr), elegir_series(pares, [7700, 7750]), NULA)
    assert r.loc[(7700, "P"), "veredicto"] == "confirma"
    assert r.loc[(7700, "P"), "neto_medido"] == 900 and r.loc[(7700, "P"), "pares_hueco"] == 1
    assert r.loc[(7750, "C"), "veredicto"] == "CONTRADICE"


def test_sin_trades_es_demasiado_chico_no_un_signo():
    pares = pares_doi(CADENAS, MERCADO)
    vacio = flujo_por_dia(_trades([("X", D1, 3.0, 1)]))
    r = comparar(pares, vacio, elegir_series(pares, [7700]), NULA)
    assert r.loc[(7700, "P"), "veredicto"] == "demasiado chico"
    assert r.loc[(7700, "P"), "pct_delta_indet"] == 100
