"""Tests de src/perfil_gamma.py: la gamma recalculada es la de black_scholes, reproduce la foto en su propio
spot, y la prueba contra la realidad da error 0 cuando el mundo cumple el supuesto (vol fija)."""
import numpy as np
import pandas as pd
import pytest

from src import perfil_gamma as pg
from src.black_scholes import delta_opcion, gamma_opcion, precio_bs

S, R, Q = 7500.0, 0.047, 0.012
NY = "America/New_York"


def _cadena(S=S, dias=(1, 8, 40), strikes=range(7300, 7701, 25), iv=0.18, fecha="2026-11-09"):
    """Foto fabricada con las columnas de data/procesado más q, T y r (lo que agrega insumos)."""
    filas = []
    for d in dias:
        T = d / 365
        for k in strikes:
            for tipo in ("C", "P"):
                vol = iv + 0.0002 * abs(k - 7500) / 25
                filas.append(dict(symbol=f"SPXW {d:03d}{tipo}{k}", raiz="SPXW",
                                  vencimiento=pd.Timestamp(fecha) + pd.Timedelta(days=d), dte=d, tipo=tipo,
                                  strike=float(k), open_interest=1000 + (k % 100 == 0) * 4000, iv=vol,
                                  gamma=gamma_opcion(S, k, T, R, vol, Q), S=S, q=Q, T=T, r=R))
    c = pd.DataFrame(filas)
    c["gex_contrib"] = c["gamma"] * c["open_interest"] * 100 * S**2 * 0.01
    return c


def test_gamma_vec_es_la_de_black_scholes():
    K, T, v = np.array([7000.0, 7500.0, 8000.0]), np.array([0.01, 0.1, 1.0]), np.array([0.3, 0.15, 0.2])
    esperado = [gamma_opcion(S, k, t, R, s, Q) for k, t, s in zip(K, T, v)]
    assert pg.gamma_vec(S, K, T, R, v, Q) == pytest.approx(esperado, rel=1e-12)


def test_gamma_vec_bordes_dan_nan():
    g = pg.gamma_vec(S, np.array([7500.0] * 4), np.array([0.0, -0.1, 0.1, 0.1]), R, np.array([0.2, 0.2, np.nan, 0.0]))
    assert np.isnan(g).all()


@pytest.mark.parametrize("K,T,vol", [(7500, 1 / 365, 0.15), (7300, 30 / 365, 0.22), (7800, 0.5, 0.18)])
def test_gamma_es_la_segunda_derivada_del_precio_y_la_derivada_del_delta(K, T, vol):
    """Chequeo independiente de la fórmula: diferencias numéricas del precio y del delta, calls y puts."""
    h = 0.5
    g = float(pg.gamma_vec(S, K, T, R, vol, Q))
    for tipo in ("C", "P"):
        segunda = (precio_bs(S + h, K, T, R, vol, tipo, Q) - 2 * precio_bs(S, K, T, R, vol, tipo, Q)
                   + precio_bs(S - h, K, T, R, vol, tipo, Q)) / h**2
        derivada = (delta_opcion(S + h, K, T, R, vol, tipo, Q) - delta_opcion(S - h, K, T, R, vol, tipo, Q)) / (2 * h)
        assert g == pytest.approx(segunda, rel=1e-3)
        assert g == pytest.approx(derivada, rel=1e-4)


def test_identidad_reproduce_la_foto_y_grita_si_no():
    c = _cadena()
    assert pg.verificar_identidad(c) < 1e-12
    mala = c.copy()
    mala.loc[0, "gamma"] *= 1.001
    with pytest.raises(ValueError, match="identidad"):
        pg.verificar_identidad(mala)
    sin = c.copy()
    sin.loc[0, "gamma"] = np.nan                       # la foto dice "sin gamma" y el recálculo sí la tiene
    with pytest.raises(ValueError, match="identidad"):
        pg.verificar_identidad(sin)


def test_perfil_en_el_spot_de_la_foto_es_el_bruto_de_la_foto():
    c = _cadena()
    p = pg.perfil(c, [S]).set_index("zona")
    esperado = c.groupby("strike")["gex_contrib"].sum()
    assert p["gex_bruto"].to_numpy() == pytest.approx(esperado.to_numpy(), rel=1e-12)
    assert (p["gex_bruto_c"] + p["gex_bruto_p"]).to_numpy() == pytest.approx(p["gex_bruto"].to_numpy())
    # neto SUPUESTO: calls y puts del mismo strike tienen la misma gamma y el mismo OI -> se cancelan
    assert np.abs(p["gex_sup"]).max() < 1e-6 * p["gex_bruto"].max()


def test_la_gamma_sigue_al_precio():
    """Al mover el spot, la zona con más gamma de corto plazo se mueve con él."""
    c = _cadena(dias=(1,), strikes=range(7300, 7701, 25))
    c["open_interest"] = 1000
    for S2 in (7350.0, 7500.0, 7650.0):
        p = pg.perfil(c, [S2]).set_index("zona")["gex_bruto"]
        assert abs(p.idxmax() - S2) <= 25


def test_avance_saca_lo_vencido_y_no_inventa():
    c = _cadena(dias=(1, 8))
    antes = pg.gex_bruto_en(c, S)
    despues = pg.gex_bruto_en(c, S, avance=2 / 365)
    assert (despues[c["dte"] == 1] == 0).all()                         # venció: sale del libro
    assert (despues[c["dte"] == 8] > 0).all() and antes.notna().all()
    sin_vol = c.copy()
    sin_vol.loc[0, "iv"] = np.nan
    assert np.isnan(pg.gex_bruto_en(sin_vol, S).iloc[0])               # sin volatilidad: nan, no 0


def test_error_prediccion_es_cero_si_la_vol_no_cambia():
    hoy = _cadena(dias=(2, 9, 41))
    S2 = 7420.0
    manana = _cadena(S=S2, dias=(1, 8, 40), fecha="2026-11-10")
    manana["symbol"] = hoy["symbol"].to_numpy()                        # las mismas series, un día después
    e = pg.error_prediccion(hoy, manana)
    assert e["err_recalculada"] == pytest.approx(0.0, abs=1e-9)
    assert e["err_vieja"] > 5 and e["pct_cubierto"] == pytest.approx(100.0)
    assert e["zonas"]["recalculada"].to_numpy() == pytest.approx(e["zonas"]["real"].to_numpy())


def test_error_prediccion_mide_el_cambio_de_vol():
    hoy = _cadena(dias=(2, 9, 41))
    manana = _cadena(S=7420.0, dias=(1, 8, 40), iv=0.25, fecha="2026-11-10")
    manana["symbol"] = hoy["symbol"].to_numpy()
    e = pg.error_prediccion(hoy, manana)
    assert e["err_recalculada"] > 5 and e["sesgo_recalculada"] > 0     # subió la vol: la real es MENOR


def test_envejecimiento():
    c = _cadena()
    igual = pg.envejecimiento(c, S)
    assert igual["spearman"] == pytest.approx(1.0) and igual["top_comunes"] == 5
    assert igual["bruto_nuevo"] == pytest.approx(igual["bruto_viejo"])
    lejos = pg.envejecimiento(c, S - 150)
    assert lejos["spearman"] < 1.0 and lejos["zonas"] > 0


def test_serie_intradia_sin_lo_que_vence_hoy_y_con_el_plazo_que_queda():
    c = _cadena(dias=(1, 8), fecha="2026-11-09")
    cierre = pd.Timestamp("2026-11-09 16:00", tz=NY)
    t = pd.Timestamp("2026-11-10 12:00", tz=NY)
    s = pg.serie_intradia(c, pd.Series([7480.0], index=[t]), "2026-11-10", cierre)
    queda = c[c["dte"] == 8]                                            # lo de dte=1 vence el 11-10: fuera
    T = queda["T"] - 20 / (365 * 24)
    esperado = sum(gamma_opcion(7480.0, k, tt, R, v, Q) * oi * 100 * 7480.0**2 * 0.01
                   for k, tt, v, oi in zip(queda["strike"], T, queda["iv"], queda["open_interest"]))
    assert s["gex_bruto"].iloc[0] == pytest.approx(esperado, rel=1e-10)
    assert 0 < s["gex_bruto_local"].iloc[0] < s["gex_bruto"].iloc[0]
    with pytest.raises(ValueError):
        pg.serie_intradia(c, pd.Series([7480.0], index=[t.tz_localize(None)]), "2026-11-10", cierre)
    with pytest.raises(ValueError):
        pg.serie_intradia(c, pd.Series([7480.0], index=[cierre]), "2026-11-10", cierre)


def test_bloques_no_miran_al_futuro():
    idx = pd.date_range("2026-11-10 09:30", "2026-11-10 15:59", freq="1min", tz=NY)
    spx = pd.Series(7500.0 + np.arange(len(idx)) * 0.1, index=idx)
    b = pg.bloques(spx)
    assert b["t"].iloc[0] == pd.Timestamp("2026-11-10 10:00", tz=NY) and len(b) == 12
    assert b["spx"].iloc[0] == pytest.approx(spx[pd.Timestamp("2026-11-10 09:59", tz=NY)])   # último cierre previo
    assert b["rango_prev_pct"].iloc[0] == pytest.approx(100 * 2.9 / b["spx"].iloc[0])
    assert b["rango_sig_pct"].iloc[0] == pytest.approx(100 * 2.9 / b["spx"].iloc[0])


def test_relacion_por_grupo():
    t = pd.DataFrame(dict(g=["a"] * 5 + ["b"] * 5 + ["c"] * 2, x=[1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2],
                          y=[1, 2, 3, 4, 5, 5, 4, 3, 2, 1, 1, 2]))
    r = pg.relacion_por_grupo(t, "g", "x", "y")
    assert r.to_dict() == pytest.approx({"a": 1.0, "b": -1.0})          # "c" tiene menos de 5 filas


def test_toda_columna_esta_clasificada():
    c = _cadena()
    for col in pg.perfil(c, [S]).columns.drop(["zona", "spot"]):
        assert pg.clase(col) in ("modelo", "supuesto")
    assert pg.clase("gex_sup") == "supuesto"
    with pytest.raises(ValueError):
        pg.clase("columna_nueva")


def test_tabla_por_dia_cuenta_cada_dia_una_sola_vez():
    filas = []
    for i in range(8):                                   # 8 días × 3 bloques
        for j in range(3):
            filas.append(dict(fecha=f"2026-10-{i + 1:02d}", gex_bruto_B=float(i), spx=float(i % 2),
                              rango_sig_pct=1.0 - 0.1 * i + 0.01 * j))
    x = pg.tabla_por_dia(pd.DataFrame(filas), "spx")
    assert int(x[["dias_pred_alto", "dias_pred_bajo"]].sum().sum()) == 8             # días, no bloques
    assert (x["objetivo_pred_alto"] < x["objetivo_pred_bajo"]).all()                 # más gamma, menos rango
    with pytest.raises(ValueError):
        pg.tabla_por_dia(pd.DataFrame(filas[:6]), "spx")
