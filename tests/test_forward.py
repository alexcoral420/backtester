"""Forward implícito: recupera un q conocido de precios fabricados, resiste ruido lejos del dinero."""
import numpy as np
import pandas as pd
import pytest

from src.black_scholes import precio_bs
from src.forward import forward_por_vencimiento, q_por_opcion

S, R = 7700.0, 0.04


def _cadena(vencs, q, strikes=range(7400, 8001, 25), vol=0.15):
    """Cadena sintética: precios Black-Scholes con un q conocido por vencimiento."""
    filas = []
    for venc, T in vencs.items():
        for k in strikes:
            for tipo in "CP":
                filas.append(dict(venc=pd.Timestamp(venc), T=T, tipo=tipo, strike=float(k),
                                  mid=precio_bs(S, k, T, R, vol, tipo, q=q[venc])))
    return pd.DataFrame(filas)


def test_recupera_el_q_conocido():
    vencs = {"2026-10-16": 22 / 365, "2026-12-18": 85 / 365}
    q = {"2026-10-16": 0.013, "2026-12-18": 0.012}
    fw = forward_por_vencimiento(_cadena(vencs, q), S, R)
    for v in vencs:
        assert fw.at[pd.Timestamp(v), "q"] == pytest.approx(q[v], abs=1e-9)
        assert fw.at[pd.Timestamp(v), "origen"] == "medido"
        assert fw.at[pd.Timestamp(v), "dispersion"] == pytest.approx(0, abs=1e-6)


def test_ruido_lejos_del_dinero_no_contamina():
    """Un mid absurdo en un strike deep ITM no entra: solo se usan los cercanos al dinero."""
    t = _cadena({"2026-10-16": 22 / 365}, {"2026-10-16": 0.013})
    t.loc[(t["strike"] == 7400) & (t["tipo"] == "C"), "mid"] += 50
    fw = forward_por_vencimiento(t, S, R)
    assert fw["q"].iloc[0] == pytest.approx(0.013, abs=1e-9)


def test_dispersion_delata_un_mid_incoherente():
    """Un strike cercano roto: la mediana aguanta, pero la dispersión lo muestra."""
    t = _cadena({"2026-10-16": 22 / 365}, {"2026-10-16": 0.013})
    t.loc[(t["strike"] == 7700) & (t["tipo"] == "C"), "mid"] += 10
    fw = forward_por_vencimiento(t, S, R)
    assert fw["q"].iloc[0] == pytest.approx(0.013, abs=1e-9)
    assert fw["dispersion"].iloc[0] > 9


def test_vencimiento_sin_pares_hereda_del_mas_cercano():
    vencs = {"2026-10-16": 22 / 365, "2026-12-18": 85 / 365, "2027-12-17": 449 / 365}
    q = {v: 0.013 for v in vencs}
    q["2026-12-18"] = 0.011
    t = _cadena(vencs, q)
    t = t[~((t["venc"] == pd.Timestamp("2027-12-17")) & (t["tipo"] == "P"))]   # sin puts: no hay paridad
    fw = forward_por_vencimiento(t, S, R)
    lejano = fw.loc[pd.Timestamp("2027-12-17")]
    assert lejano["origen"] == "heredado"
    assert lejano["q"] == pytest.approx(0.011, abs=1e-9)                        # el de diciembre, el más cercano
    assert q_por_opcion(t, fw).notna().all()


def test_plazo_largo_se_centra_en_el_forward():
    """5 años: F ~ S + 1.500. Un strike roto cerca de S no debe entrar; uno cerca de F sí se ve."""
    T, q = 5.0, 0.003
    t = _cadena({"2031-12-19": T}, {"2031-12-19": q}, strikes=range(7000, 10001, 50))
    t.loc[(t["strike"] == 7700) & (t["tipo"] == "C"), "mid"] += 40     # ruido cerca del SPOT
    fw = forward_por_vencimiento(t, S, R)
    assert fw["q"].iloc[0] == pytest.approx(q, abs=1e-9)
    assert fw["dispersion"].iloc[0] == pytest.approx(0, abs=1e-6)


def _dos_raices():
    """Tercer viernes: SPX (AM) y SPXW (PM) con el MISMO venc y strikes, y q distintos a propósito."""
    am = _cadena({"2026-10-16": 22 / 365}, {"2026-10-16": 0.013}).assign(raiz="SPX")
    pm = _cadena({"2026-10-16": 22.27 / 365}, {"2026-10-16": 0.009}).assign(raiz="SPXW")
    return pd.concat([am, pm], ignore_index=True)


def test_mezclar_raices_grita():
    with pytest.raises(ValueError, match="UNA raíz"):
        forward_por_vencimiento(_dos_raices(), S, R)


def test_q_por_raiz_mide_cada_raiz_por_separado():
    from src.forward import q_por_raiz
    t = _dos_raices()
    q = q_por_raiz(t, S, R)
    assert q.index.equals(t.index)
    assert q[t["raiz"] == "SPX"].to_numpy() == pytest.approx(0.013, abs=1e-9)
    assert q[t["raiz"] == "SPXW"].to_numpy() == pytest.approx(0.009, abs=1e-9)


def test_q_por_raiz_sin_columna_raiz_es_lo_de_siempre():
    from src.forward import q_por_raiz
    t = _cadena({"2026-10-16": 22 / 365}, {"2026-10-16": 0.013})
    assert q_por_raiz(t, S, R).equals(q_por_opcion(t, forward_por_vencimiento(t, S, R)))
