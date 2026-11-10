"""Tests de src/odte/vista.py: lectura SOLO CACHÉ para el panel 0DTE. Un día al que le falta algo no rompe
(SinDatos con el motivo), el inventario lo anuncia, y ninguna función llega a una descarga."""
import numpy as np
import pandas as pd
import pytest

from src import datos
from src.odte import catalogo, precio, trades, vista

NY = "America/New_York"
D1, D2, HUECO, D3 = "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"     # viernes, lunes, (falta), miércoles
CALL, PUT = "SPXW  261019C07700000", "SPXW  261019P07700000"


def _es(fecha, nivel=7700.0, base=50.0):
    idx = pd.date_range(f"{fecha} 09:30", periods=390, freq="1min", tz=NY)
    spx = nivel + np.linspace(0, 30, 390)                       # sube 30 pts en el día
    return pd.DataFrame({"open": spx + base, "high": spx + base, "low": spx + base, "close": spx + base,
                         "volume": 1}, index=idx), pd.Series(spx, index=idx)


def _spx5(spx1):
    idx = spx1.index[::5]
    c = spx1.reindex(idx + pd.Timedelta(minutes=4)).values
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)


def _foto(fecha, venc="2026-11-20"):
    return pd.DataFrame({"symbol": ["a", "b"], "raiz": "SPXW", "vencimiento": pd.to_datetime([venc, venc]),
                         "dte": 30, "tipo": ["C", "P"], "strike": [7700.0, 7650.0], "open_interest": [100, 200],
                         "iv": 0.2, "gamma": 1e-4, "gex_contrib": [1e9, -2e9], "S": 7700.0})


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Caché falsa: fotos de D1, D2 y D3 (HUECO no existe); ES + SPX 5m de D2 y D3; catálogo + tcbbo solo de D2.
    Cualquier intento de descargar o cotizar hace fallar el test."""
    raw, proc = tmp_path / "raw", tmp_path / "procesado"
    raw.mkdir(); proc.mkdir()
    for m in (precio, catalogo, trades):
        monkeypatch.setattr(m, "CARPETA_CACHE", str(raw))
    monkeypatch.setattr(vista, "PROCESADO", str(proc / "cadena_SPX+SPXW_horas_{}.parquet"))

    def prohibido(*a, **k):
        raise AssertionError("vista.py intentó descargar o cotizar")
    monkeypatch.setattr(datos, "asegurar_descargas", prohibido)
    monkeypatch.setattr(datos, "_cliente", prohibido)
    monkeypatch.setattr(precio.yf, "Ticker", prohibido)

    for f in (D1, D2, D3):
        _foto(f).to_parquet(vista.PROCESADO.format(f))
    for f in (D2, D3):
        es, spx1 = _es(f)
        es.to_parquet(precio.ruta_es(f))
        _spx5(spx1).to_parquet(precio.ruta_spx_yf(f, "5m"))
    pd.DataFrame({"raw_symbol": [CALL, PUT], "instrument_class": ["C", "P"], "strike_price": [7700.0, 7700.0],
                  "expiration": pd.Timestamp("2026-10-19", tz="UTC")}).to_parquet(catalogo.ruta_definicion(D2))
    t = pd.DataFrame({"symbol": [CALL, CALL, PUT, PUT], "price": [5.0, 4.0, 3.0, 2.5], "size": [10, 4, 7, 100],
                      "bid_px_00": [4.0, 4.0, 2.0, 2.0], "ask_px_00": [5.0, 5.0, 3.0, 3.0],
                      "bid_sz_00": 1, "ask_sz_00": 1},
                     index=pd.DatetimeIndex(pd.to_datetime([f"{D2} 09:31:10", f"{D2} 09:31:40", f"{D2} 09:33:00",
                                                            f"{D2} 10:00:00"]).tz_localize(NY), name="ts_recv"))
    t["size"] = t["size"].astype("uint32")
    t.to_parquet(trades.ruta_cache_tcbbo(D2, [CALL, PUT]))
    return tmp_path


def test_inventario_lista_el_dia_sin_datos_sin_romper(cache):
    inv = vista.inventario()
    assert list(inv.index) == [D1, D2, HUECO, D3]                # días hábiles, el hueco incluido
    assert inv.loc[HUECO, "falta"].startswith("todo")
    assert not inv.loc[HUECO, ["precio_ok", "carga_ok", "flujo_ok"]].any()
    assert inv.loc[D2, ["precio_ok", "carga_ok", "flujo_ok"]].all()
    assert not inv.loc[D1, "carga_ok"]                           # primera foto: no tiene anterior
    assert inv.loc[D3, "precio_ok"] and not inv.loc[D3, "flujo_ok"]


def test_inventario_con_cache_vacia(tmp_path, monkeypatch):
    for m in (precio, catalogo, trades):
        monkeypatch.setattr(m, "CARPETA_CACHE", str(tmp_path))
    monkeypatch.setattr(vista, "PROCESADO", str(tmp_path / "cadena_{}.parquet"))
    assert vista.inventario().empty


@pytest.mark.parametrize("funcion", [vista.spx_dia, vista.toques_dia, vista.carga_del_dia, vista.flujo_dia])
def test_dia_sin_datos_da_sindatos_con_motivo(cache, funcion):
    with pytest.raises(vista.SinDatos, match=HUECO):
        funcion(HUECO)


def test_spx_dia_es_el_es_menos_la_base(cache):
    spx = vista.spx_dia(D2)
    assert len(spx) == 390 and spx.index.tz is not None
    assert spx.iloc[100] == pytest.approx(7700.0 + 30 * 100 / 389, abs=1e-6)     # la base (50) se descuenta


def test_spx_dia_sesion_incompleta_no_rompe(cache):
    es, spx1 = _es(D3)
    _spx5(spx1).iloc[:40].to_parquet(precio.ruta_spx_yf(D3, "5m"))               # yfinance cortado
    with pytest.raises(vista.SinDatos, match="base"):
        vista.spx_dia(D3)


def test_toques_dia_trae_el_fin_de_la_ventana(cache):
    t = vista.toques_dia(D2)
    assert list(t["strike"]) == [7725]                           # el SPX sube de 7700 a 7730
    assert (t["t_fin"] - t["t_toque"] == pd.Timedelta(minutes=30)).all()


def test_carga_del_dia_marca_la_foto_previa_vieja(cache):
    assert vista.carga_del_dia(D2)["foto_previa"] == D1 and not vista.carga_del_dia(D2)["d1_vieja"]
    c = vista.carga_del_dia(D3)                                  # su previa es D2: se saltó el HUECO
    assert c["foto_previa"] == D2 and c["d1_vieja"]
    assert c["zonas"].loc[7700.0, "oi_total"] == 100


def test_carga_del_dia_sin_foto_anterior(cache):
    with pytest.raises(vista.SinDatos, match="anterior"):
        vista.carga_del_dia(D1)


def test_flujo_dia_regla_estricta_y_cobertura(cache):
    r = vista.flujo_dia(D2)
    # 10 (call) y 7 (put) en el ask = compra; 4 (call) en el bid = venta; 100 (put) en el punto medio = indet.
    assert r["volumen"] == dict(compra=17, venta=4, indet=100)
    assert r["pct_indet"] == pytest.approx(100 * 100 / 121)
    assert r["series_cubiertas"] == 2 and r["series_0dte"] == 2
    assert (r["desde"], r["hasta"], r["sesion_completa"]) == ("09:30", "16:00", True)
    assert r["flujo"]["acum_C"].iloc[-1] == 6 and r["flujo"]["acum_P"].iloc[-1] == 7


def test_flujo_dia_sin_catalogo(cache):
    with pytest.raises(vista.SinDatos, match="catálogo"):
        vista.flujo_dia(D3)


def test_flujo_dia_usa_la_franja_parcial_si_no_hay_sesion_completa(cache):
    import os
    completa = trades.ruta_cache_tcbbo(D2, [CALL, PUT])
    os.replace(completa, trades.ruta_cache_tcbbo(D2, [CALL, PUT], "09:30", "09:45"))
    r = vista.flujo_dia(D2)
    assert (r["desde"], r["hasta"], r["sesion_completa"]) == ("09:30", "09:45", False)
    assert r["volumen"]["indet"] == 0                            # el trade de las 10:00 queda fuera de la franja


def test_acumuladores_ausentes_devuelven_none(tmp_path, monkeypatch):
    monkeypatch.setattr(vista, "RUTA_CARGA", str(tmp_path / "no.csv"))
    monkeypatch.setattr(vista, "RUTA_TOQUES", str(tmp_path / "no.csv"))
    assert vista.leer_carga() is None and vista.leer_toques_m2() is None


def test_leer_carga_rotula_las_filas_viejas(tmp_path, monkeypatch):
    ruta = tmp_path / "c.csv"
    pd.DataFrame({"fecha": ["2026-10-19"], "clase": [100], "strike": [7700]}).to_csv(ruta, index=False)
    monkeypatch.setattr(vista, "RUTA_CARGA", str(ruta))
    t = vista.leer_carga()
    assert t["referencia"].iloc[0] == "radio250" and t["clase"].iloc[0] == "100"


def test_razon_y_partes_del_indeterminado():
    t = pd.DataFrame({"neto": [-50, 10], "indet": [100, 0], "indet_medio": [40, 0], "indet_interior": [50, 0],
                      "indet_fuera": [10, 0], "indet_sin_cotizacion": [0, 0]})
    assert vista.razon_neto_indet(t).iloc[0] == 0.5 and np.isnan(vista.razon_neto_indet(t).iloc[1])
    assert list(vista.partes_indet(t).iloc[0]) == [40.0, 50.0, 10.0, 0.0]


def test_mapa_toques_y_zona_repetida():
    t = pd.DataFrame({"fecha": ["d1", "d1", "d2"], "strike": [7700, 7725, 7700],
                      "resultado": ["aguantó", "cruzó", "cruzó"]})
    m = vista.mapa_toques(t)
    assert m.loc[7700, "d2"] == "cruzó" and pd.isna(m.loc[7725, "d2"])
    with pytest.raises(ValueError):
        vista.mapa_toques(pd.concat([t, t]))


def test_clase_del_panel_grita_si_no_esta_clasificada():
    assert vista.clase("spx") == "medido" and vista.clase("acum_C") == "medido"
    assert vista.clase("gex_bruto") == "modelo" and vista.clase("gex_sup") == "supuesto"   # delega en carga.clase
    assert vista.clase("peor_exceso") == "medido"                # precio observado
    with pytest.raises(ValueError):
        vista.clase("columna_inventada")


def test_el_flujo_del_punto_medio_no_es_medido():
    assert vista.clase_flujo(True) == "medido" and vista.clase_flujo(False) == "inferido"
