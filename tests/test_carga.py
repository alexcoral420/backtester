"""Tests de src/odte/carga.py (M4): carga sin mirar al futuro, percentil dentro de la clase, wall SUPUESTO
aparte, contrato de columnas y análisis (celdas, diferencia, voto por zona, dejar una fuera, predictores)."""
import numpy as np
import pandas as pd
import pytest

from src.odte import carga as cg
from src.odte.toques import AGUANTO, CRUZO

FECHA = "2026-11-05"


def foto(filas, S=7700.0):
    """filas: (symbol, tipo, strike, OI, gex_contrib, vencimiento) -> foto procesada mínima."""
    c = pd.DataFrame(filas, columns=["symbol", "tipo", "strike", "open_interest", "gex_contrib", "vencimiento"])
    c["vencimiento"] = pd.to_datetime(c["vencimiento"])
    c["S"] = S
    return c


# Foto de d (OI medido, 06:30 de d): nada vence el 11-05.
FOTO_D = foto([
    ("a", "C", 7700, 500, 9e9, "2026-11-20"), ("b", "P", 7700, 100, -9e9, "2026-11-20"),   # 100: carga 600
    ("c", "C", 7800, 50, 1e8, "2026-11-20"),                                               # 100: carga 50
    ("d", "P", 7750, 300, -2e8, "2026-11-20"),                                             # 50:  carga 300
    ("e", "P", 7650, 30, -1e8, "2026-11-20"),                                              # 50:  carga 30
    ("f", "C", 7725, 80, 1e8, "2026-11-20"), ("g", "P", 7675, 20, -1e8, "2026-11-20"),     # 25
    ("h", "P", 7300, 999, -1e8, "2026-11-20"),                                             # 100 fuera del radio
])
# Foto de d-1: la gamma (MODELO) y el signo (SUPUESTO). La serie "x" vence en d: NO debe entrar.
FOTO_PREVIA = foto([
    ("a", "C", 7700, 400, 5e9, "2026-11-20"), ("b", "P", 7700, 100, -1e9, "2026-11-20"),
    ("c", "C", 7800, 50, 1e8, "2026-11-20"),
    ("d", "P", 7750, 300, -2e9, "2026-11-20"), ("e", "P", 7650, 30, -1e8, "2026-11-20"),
    ("f", "C", 7725, 80, 1e8, "2026-11-20"), ("g", "P", 7675, 20, -1e8, "2026-11-20"),
    ("x", "C", 7800, 10_000, 7e10, FECHA),
])


@pytest.fixture
def z():
    return cg.carga_dia(FOTO_D, FOTO_PREVIA, FECHA, S_previo=7700.0)


def test_clase_redondez():
    assert [cg.clase_redondez(k) for k in (7700, 7750, 7725, 8000.0)] == ["100", "50", "25", "100"]
    with pytest.raises(ValueError):
        cg.clase_redondez(7710)


def test_oi_sale_de_la_foto_de_d(z):
    assert (z.loc[7700, "oi_c"], z.loc[7700, "oi_p"], z.loc[7700, "oi_total"]) == (500, 100, 600)


def test_lo_que_vence_en_d_no_entra_al_modelo_ni_al_supuesto(z):
    """La serie x (vence el 11-05, gex 7e10) no puede aparecer en gex_bruto ni en gex_sup de 7800."""
    assert z.loc[7800, "gex_bruto"] == pytest.approx(1e8)
    assert z.loc[7800, "gex_sup"] == pytest.approx(1e8)


def test_gamma_sale_de_la_foto_previa(z):
    assert z.loc[7700, "gex_bruto"] == pytest.approx(6e9)        # |5e9| + |-1e9| de d-1, no los 18e9 de d
    assert z.loc[7700, "gex_sup"] == pytest.approx(4e9)


def test_foto_de_d_con_vencimiento_del_dia_grita():
    mala = foto([("x", "C", 7700, 10, 1e8, FECHA)])
    with pytest.raises(ValueError, match="vencen"):
        cg.carga_dia(mala, FOTO_PREVIA, FECHA, S_previo=7700.0)


def test_percentil_dentro_de_la_clase(z):
    """7700 (600) es la mayor de su clase entre las de referencia; 7800 (50), la menor. La 7300 está fuera
    del radio: no entra a la referencia, aunque tenga más OI."""
    assert z.loc[7700, "pct_carga_oi"] == 75.0        # contra {600, 50}: 50 debajo + empate consigo
    assert z.loc[7800, "pct_carga_oi"] == 25.0
    assert z.loc[7750, "pct_carga_oi"] == 75.0 and z.loc[7650, "pct_carga_oi"] == 25.0   # clase 50 aparte


def test_zona_fuera_del_radio_se_compara_contra_la_referencia(z):
    assert bool(z.loc[7300, "fuera_radio"]) and not bool(z.loc[7700, "fuera_radio"])
    assert z.loc[7300, "pct_carga_oi"] == 100.0       # 999 > {600, 50}


def test_wall_supuesto_es_top_por_valor_absoluto(z):
    w = cg.carga_dia(FOTO_D, FOTO_PREVIA, FECHA, S_previo=7700.0, top=2)
    assert set(w.index[w["es_wall_sup"]]) == {7700.0, 7750.0}    # |4e9| y |-2e9|


def test_unir_grita_si_falta_la_zona(z):
    tq = pd.DataFrame({"strike": [7700, 7825]})
    with pytest.raises(ValueError, match="7825"):
        cg.unir(tq, z)


def test_contrato_clasifica_todas_las_columnas(z):
    tq = pd.DataFrame({"strike": [7700], "t_toque": ["10:30"], "lado": ["arriba"], "dist_previa": [9.0],
                       "peor_exceso": [1.0], "resultado": [AGUANTO]})
    r = cg.unir(tq, z).assign(fecha=FECHA, definicion="p25", S_previo=7700.0, dist_cierre_previo=0.0,
                              d1_vieja=False)
    clases = {c: cg.clase(c) for c in r.columns}
    assert clases["gex_sup"] == clases["es_wall_sup"] == "supuesto"
    assert clases["gex_bruto"] == "modelo" and clases["oi_total"] == "medido"
    with pytest.raises(ValueError):
        cg.clase("columna_nueva")


# ---------------- análisis ----------------
def muestra(filas):
    """filas: (fecha, strike, clase, pct_carga, resultado)"""
    t = pd.DataFrame(filas, columns=["fecha", "strike", "clase", "pct_carga_oi", "resultado"])
    t["pct_carga_bruto"] = t["pct_carga_oi"]
    t["dist_previa"] = np.arange(len(t), dtype=float)
    t["es_wall_sup"] = False
    return t


T = muestra([("d1", 7700, "100", 90, AGUANTO), ("d2", 7700, "100", 80, AGUANTO),
             ("d3", 7600, "100", 20, CRUZO), ("d1", 7650, "50", 70, CRUZO),
             ("d2", 7550, "50", 10, CRUZO), ("d3", 7675, "25", 60, AGUANTO)])


def test_diferencia_alta_menos_baja():
    # alta: 7700, 7700, 7650, 7675 -> 3 de 4 aguantan (75%); baja: 7600, 7550 -> 0%
    assert cg.diferencia(T) == pytest.approx(75.0)


def test_alta_grita_con_nan():
    with pytest.raises(ValueError):
        cg.alta(T.assign(pct_carga_oi=np.nan))


def test_celdas_cuentan_dias_y_marcan_evidencia():
    c = cg.celdas(T)
    assert c.loc[("100", "alta"), "toques"] == 2 and c.loc[("100", "alta"), "dias"] == 2
    assert c.loc[("100", "alta"), "zonas"] == 1
    assert c["evidencia"].str.startswith("NO").all()          # ninguna celda llega a 10 días


def test_voto_por_zona_cuenta_cada_zona_una_vez():
    v = cg.voto_por_zona(T)
    # zonas alta: 7700 (1.0), 7650 (0), 7675 (1.0) -> 66.7%; baja: 7600 (0), 7550 (0) -> 0
    assert v["zonas"] == 5 and v["alta"] == 3 and v["diferencia"] == pytest.approx(200 / 3)


def test_dejar_una_fuera_detecta_dependencia_de_una_zona():
    t = muestra([("d1", 7700, "100", 90, AGUANTO), ("d2", 7700, "100", 90, AGUANTO),
                 ("d3", 7700, "100", 90, AGUANTO), ("d1", 7650, "50", 70, CRUZO),
                 ("d2", 7550, "50", 10, AGUANTO), ("d3", 7600, "100", 10, CRUZO)])
    d = cg.dejar_una_fuera(t).set_index("zona")
    assert cg.diferencia(t) > 0
    assert bool(d.loc[7700, "cambia_signo"])                 # sin 7700 la alta es solo 7650 (cruzó)
    assert not bool(d.loc[7550, "cambia_signo"])


def test_predicciones_sobre_los_mismos_toques():
    p = cg.predicciones(T)
    assert list(p.columns) == ["base", "mult100", "distancia", "carga_oi", "carga_bruto", "wall_sup"]
    assert (p["mult100"] == np.where(T["clase"] == "100", AGUANTO, CRUZO)).all()
    assert (p["wall_sup"] == CRUZO).all()
    a = cg.aciertos(T)
    assert a["carga_oi"] == pytest.approx(100 * 5 / 6)       # solo 7650 (alta, cruzó) falla


def test_contables_saca_ventana_corta():
    t = muestra([("d1", 7700, "100", 90, AGUANTO), ("d1", 7600, "100", 10, "ventana corta")])
    assert len(cg.contables(t)) == 1
