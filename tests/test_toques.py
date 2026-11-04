"""Tests de src/odte/toques.py: toque, lado, resultado (aguantó/cruzó/ventana corta) y flujo previo."""
import pandas as pd
import pytest

from src.odte.toques import AGUANTO, CRUZO, VENTANA_CORTA, Definicion, flujo_previo, niveles, primer_toque, toques

NY = "America/New_York"


def serie(precios, inicio="09:30", fecha="2026-10-14"):
    idx = pd.date_range(f"{fecha} {inicio}", periods=len(precios), freq="1min", tz=NY)
    return pd.Series(precios, index=idx, dtype=float)


def con_relleno(antes, tramo, despues_n=40, valor_despues=None):
    """Precio constante `antes` de 09:30 a 09:59, luego `tramo` desde las 10:00, luego relleno."""
    fin = tramo[-1] if valor_despues is None else valor_despues
    return serie([antes] * 30 + list(tramo) + [fin] * despues_n)


def test_etiqueta_estable():
    assert Definicion().etiqueta() == "p25_t2_d1000_v30_m5"
    assert Definicion(paso=5, tolerancia=1.5).etiqueta() == "p5_t1.5_d1000_v30_m5"


def test_definicion_invalida_grita():
    with pytest.raises(ValueError):
        Definicion(paso=0)


def test_serie_sin_zona_grita():
    s = pd.Series([1.0, 2.0], index=pd.date_range("2026-10-14 09:30", periods=2, freq="1min"))
    with pytest.raises(ValueError):
        toques(s)


def test_niveles_dentro_del_rango_con_tolerancia():
    s = serie([7726.5, 7760.0])
    assert niveles(s, Definicion()) == [7725, 7750]   # 7725 está a 1,5 pts del mínimo


def test_toque_entrando_a_la_banda_desde_arriba():
    s = con_relleno(7710, [7710, 7706, 7701.5, 7704])
    i, lado = primer_toque(s, 7700, Definicion())
    assert s.index[i].strftime("%H:%M") == "10:02" and lado == "arriba"


def test_salto_al_otro_lado_cuenta_como_toque():
    s = con_relleno(7705, [7705, 7694])            # de +5 a -6 sin pasar por la banda
    i, lado = primer_toque(s, 7700, Definicion())
    assert s.index[i].strftime("%H:%M") == "10:01" and lado == "arriba"


def test_antes_de_las_10_no_cuenta():
    s = serie([7710, 7701] + [7710] * 60)          # toca a las 09:31 y nunca más
    assert primer_toque(s, 7700, Definicion()) is None


def test_dentro_de_la_banda_a_las_10_no_cuenta_hasta_reentrar():
    s = con_relleno(7701, [7701, 7701, 7690, 7690, 7699])   # dentro, sale abajo, reentra 10:04
    i, lado = primer_toque(s, 7700, Definicion())
    assert s.index[i].strftime("%H:%M") == "10:04" and lado == "abajo"


def test_aguanto_si_no_pasa_el_margen():
    s = con_relleno(7710, [7710, 7701] + [7696] * 29 + [7680])   # 4 pts abajo durante la ventana; después cae
    t = toques(s).set_index("strike").loc[7700]
    assert t["resultado"] == AGUANTO and t["peor_exceso"] == pytest.approx(4.0)


def test_cruzo_si_pasa_el_margen_dentro_de_la_ventana():
    s = con_relleno(7710, [7710, 7701] + [7698] * 28 + [7694.9])
    t = toques(s).set_index("strike").loc[7700]
    assert t["resultado"] == CRUZO and t["peor_exceso"] == pytest.approx(5.1)


def test_exactamente_el_margen_aguanta():
    s = con_relleno(7710, [7710, 7701] + [7695] * 40)
    assert toques(s).set_index("strike").loc[7700, "resultado"] == AGUANTO


def test_la_barra_del_toque_entra_en_la_ventana():
    s = con_relleno(7710, [7710, 7694, 7710])          # el toque mismo ya pasa 6 pts
    assert toques(s).set_index("strike").loc[7700, "resultado"] == CRUZO


def test_ventana_corta_al_final_de_la_sesion():
    s = serie([7710] * 60 + [7701] * 10)               # toque a las 10:30, la sesión termina 10:39
    t = toques(s).set_index("strike").loc[7700]
    assert t["resultado"] == VENTANA_CORTA and pd.isna(t["peor_exceso"])


def test_dist_previa():
    s = serie([7740] * 60 + [7701] * 40)               # toque 10:30; a las 10:00 estaba a 40 pts
    assert toques(s).set_index("strike").loc[7700, "dist_previa"] == pytest.approx(40.0)


def test_strike_no_tocado_no_aparece():
    s = con_relleno(7710, [7710, 7712])
    assert toques(s).empty


def trade(hora, k, tipo, signo, size, precio=None):
    """bid 1.00 / ask 1.20: el precio por defecto es coherente con el signo (ask, bid o medio)."""
    if precio is None:
        precio = {1: 1.20, -1: 1.00, 0: 1.10}[signo]
    return dict(ts_recv=pd.Timestamp(f"2026-10-14 {hora}", tz=NY), strike_price=k, instrument_class=tipo,
                signo=signo, size=size, price=precio, bid_px_00=1.00, ask_px_00=1.20)


def test_flujo_previo_excluye_el_minuto_del_toque_y_otros_strikes():
    s = con_relleno(7710, [7710, 7701] + [7705] * 40)  # toque 10:01
    tq = toques(s)
    tr = pd.DataFrame([trade("10:00:30", 7700, "P", -1, 300), trade("10:00:59", 7700, "C", 1, 50),
                       trade("09:45", 7700, "C", 0, 20),
                       trade("10:01:00", 7700, "P", -1, 9999),     # minuto del toque: fuera
                       trade("10:00:10", 7725, "P", 1, 5000)])     # otro strike
    r = flujo_previo(tq, tr).set_index("strike").loc[7700]
    assert (r["compra"], r["venta"], r["indet"]) == (50, 300, 20)
    assert r["neto"] == -250 and r["neto_puts"] == -300 and r["neto_calls"] == 50
    assert r["dealer_medido"] == "+"                 # público vendió 250 > 200 y > 20 indet
    assert r["pct_indet"] == pytest.approx(5.4)


def test_flujo_previo_sin_trades():
    s = con_relleno(7710, [7710, 7701] + [7705] * 40)
    r = flujo_previo(toques(s), pd.DataFrame([trade("10:30", 7700, "P", 1, 10)])).iloc[0]
    assert r["dealer_medido"] == "sin flujo" and pd.isna(r["pct_indet"])


def test_flujo_previo_sin_clasificar_grita():
    s = con_relleno(7710, [7710, 7701] + [7705] * 40)
    with pytest.raises(ValueError):
        flujo_previo(toques(s), pd.DataFrame([dict(ts_recv=1, strike_price=7700, size=1, price=1, bid_px_00=1, ask_px_00=1)]))


def test_descomposicion_de_lo_indeterminado():
    s = con_relleno(7710, [7710, 7701] + [7705] * 40)
    tr = pd.DataFrame([trade("10:00:01", 7700, "C", 0, 10),               # medio
                       trade("10:00:02", 7700, "C", 0, 30, precio=1.15),  # interior, cerca del ask
                       trade("10:00:03", 7700, "P", 0, 5, precio=1.02),   # interior, cerca del bid
                       trade("10:00:04", 7700, "P", 0, 7, precio=1.50),   # fuera (paquete)
                       trade("10:00:05", 7700, "P", 1, 3)])
    r = flujo_previo(toques(s), tr).iloc[0]
    assert (r["indet_medio"], r["indet_interior"], r["indet_fuera"], r["indet_sin_cotizacion"]) == (10, 35, 7, 0)
    assert r["indet"] == 52 and r["neto_inferido_interior"] == 25


def test_signo_incoherente_con_la_ubicacion_grita():
    """Un trade marcado indeterminado pero impreso en el ask: las partes no suman y debe gritar."""
    s = con_relleno(7710, [7710, 7701] + [7705] * 40)
    tr = pd.DataFrame([trade("10:00:01", 7700, "C", 0, 10, precio=1.20)])
    with pytest.raises(RuntimeError):
        flujo_previo(toques(s), tr)
