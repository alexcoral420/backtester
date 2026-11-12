"""Tests de src/rango_implicito.py: el straddle ATM sale de precios fabricados con Black-Scholes (se sabe
cuánto debe dar) y las comparaciones nunca miran el día que predicen."""
import numpy as np
import pandas as pd
import pytest

from src import rango_implicito as ri
from src.black_scholes import precio_bs

S, R, SIGMA = 7500.0, 0.047, 0.20
T1 = 22.5 / (365 * 24)                       # cierre -> 16:00 del día siguiente, en años
VENC1, VENC2 = pd.Timestamp("2026-11-10"), pd.Timestamp("2026-11-11")


def _tabla(vencs=((VENC1, T1), (VENC2, T1 * 2)), raiz="SPXW", strikes=range(7400, 7601, 5), ancho=0.4):
    filas = []
    for venc, T in vencs:
        for k in strikes:
            for tipo in ("C", "P"):
                p = precio_bs(S, k, T, R, SIGMA, tipo)
                filas.append(dict(raiz=raiz, venc=venc, T=T, tipo=tipo, strike=float(k),
                                  bid=p - ancho / 2, ask=p + ancho / 2, mid=p))
    return pd.DataFrame(filas)


def test_straddle_es_call_mas_put_del_strike_mas_cercano_al_forward():
    m = ri.straddle_atm(_tabla(), S, R)
    F = S * np.exp(R * T1)
    assert m["venc"] == VENC1                                  # el primer vencimiento, no el segundo
    assert m["forward"] == pytest.approx(F, abs=0.01)
    assert m["K"] == 7500.0 and m["dist_FK"] == pytest.approx(abs(F - 7500), abs=0.01)
    esperado = precio_bs(S, 7500, T1, R, SIGMA, "C") + precio_bs(S, 7500, T1, R, SIGMA, "P")
    assert m["straddle"] == pytest.approx(esperado)
    assert m["straddle"] == pytest.approx(m["call"] + m["put"])
    assert m["ancho"] == pytest.approx(0.8)                    # los dos bid/ask sumados


def test_straddle_atm_vale_el_movimiento_absoluto_esperado():
    """Chequeo independiente del modelo: straddle ATM ≈ S·σ·√T·√(2/π)."""
    m = ri.straddle_atm(_tabla(), S, R)
    assert m["straddle"] == pytest.approx(S * SIGMA * np.sqrt(T1) * np.sqrt(2 / np.pi), rel=0.01)


def test_ignora_la_raiz_spx_y_lo_ya_vencido():
    t = pd.concat([_tabla(), _tabla(vencs=((pd.Timestamp("2026-11-09"), 0.5 * T1),), raiz="SPX"),
                   _tabla(vencs=((pd.Timestamp("2026-11-09"), 0.0),))], ignore_index=True)
    assert ri.straddle_atm(t, S, R)["venc"] == VENC1


def test_grita_sin_spxw():
    with pytest.raises(ValueError, match="SPXW"):
        ri.straddle_atm(_tabla(raiz="SPX"), S, R)


def test_salta_el_strike_sin_cotizacion_valida():
    t = _tabla()
    t.loc[(t["strike"] == 7500) & (t["tipo"] == "P") & (t["venc"] == VENC1), "mid"] = np.nan
    assert ri.straddle_atm(t, S, R)["K"] in (7495.0, 7505.0)


def test_escala_sin_mirar_no_usa_el_propio_dia():
    pred = pd.Series([1.0, 1.0, 1.0, 1.0])
    obj = pd.Series([2.0, 2.0, 2.0, 100.0])
    assert ri.escala_sin_mirar(pred, obj).tolist() == [2.0, 2.0, 2.0, 2.0]      # el 100 no se predice a sí mismo
    with pytest.raises(ValueError):
        ri.escala_sin_mirar(pd.Series([1.0, -1.0, 1.0]), obj[:3])


def test_comparar_predictor_perfecto_e_inutil():
    t = pd.DataFrame(dict(obj=[1.0, 2.0, 3.0, 4.0, 5.0], bueno=[0.5, 1.0, 1.5, 2.0, 2.5],
                          malo=[3.0, 1.0, 2.0, 1.0, 3.0], con_signo=[-1.0, 2.0, -3.0, 4.0, 5.0]))
    c = ri.comparar(t, "obj", ["bueno", "malo", "con_signo"])
    assert c.at["bueno", "spearman"] == pytest.approx(1.0) and c.at["bueno", "error_medio"] == pytest.approx(0.0)
    assert c.at["malo", "error_medio"] > 0.5
    assert np.isnan(c.at["con_signo", "error_medio"])                           # con signo no se escala


def test_episodios_rachas_y_hueco():
    t = pd.DataFrame(dict(fecha=["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-20", "2026-10-21"],
                          obj=[1.0, 1.0, 5.0, 5.0, 5.0, 1.0]))
    assert ri.episodios(t, "obj").tolist() == [1, 1, 2, 2, 3, 4]                # el hueco del 06 al 20 corta
    with pytest.raises(ValueError):
        ri.episodios(t.iloc[::-1], "obj")


def test_duelo_por_episodio_cuenta_episodios_no_dias():
    t = pd.DataFrame(dict(fecha=pd.date_range("2026-10-01", periods=6).strftime("%Y-%m-%d"),
                          obj=[1.0, 1.0, 1.0, 4.0, 4.0, 4.0], pred=[1.0, 1.0, 1.0, 4.0, 4.0, 4.0],
                          ing=[2.0, 2.0, 2.0, 2.0, 2.0, 2.0]))
    e = ri.duelo_por_episodio(t, "obj", "pred", "ing")
    assert len(e) == 2 and e["dias"].tolist() == [3, 3] and (e["gana"] == "pred").all()


def test_calibracion():
    t = pd.DataFrame(dict(pago_sig_pct=[0.5, 1.0, 3.0, 0.5], impl_pct=[1.0, 1.0, 1.0, 1.0]))
    c = ri.calibracion(t)
    assert c == dict(n=4, razon_media=1.25, razon_mediana=0.75, pct_dentro=50.0)


def test_comparar_da_el_error_mediano_al_lado_del_medio():
    """Un día enorme mueve el error medio y no el mediano: los dos van siempre juntos."""
    t = pd.DataFrame(dict(obj=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 20.0], casi_plano=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.001]))
    c = ri.comparar(t, "obj", ["casi_plano"])
    assert c.at["casi_plano", "error_mediano"] == pytest.approx(0.0, abs=0.01) and c.at["casi_plano", "error_medio"] > 2


def test_robustez_muestra_si_la_ventaja_es_de_pocos_dias():
    fechas = pd.date_range("2026-10-01", periods=12).strftime("%Y-%m-%d")
    obj = [1.0, 1.1, 0.9, 1.0, 1.2, 0.8, 1.0, 1.1, 0.9, 1.0, 9.0, 8.0]
    t = pd.DataFrame(dict(fecha=fechas, obj=obj, pred=[1.0] * 10 + [9.0, 8.0], ing=[1.0, 1.1, 0.9, 1.0, 1.2, 0.8] * 2))
    r = ri.robustez(t, "obj", "pred", "ing")
    assert list(r.index) == ["todo", "sin los 2 días de mayor objetivo", "primera mitad", "segunda mitad"]
    assert r["dias"].tolist() == [12, 10, 6, 6]
    assert r.at["todo", "medio_pred"] < r.at["todo", "medio_ing"]                    # con los dos días grandes gana
    sin = r.loc["sin los 2 días de mayor objetivo"]
    assert sin["medio_pred"] >= sin["medio_ing"]                                     # sin ellos, ya no
