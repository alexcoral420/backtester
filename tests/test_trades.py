"""
Ruta de caché del tcbbo. Si esto se rompe, el proyecto vuelve a PAGAR por datos que ya tiene.
"""
from src.odte.trades import ruta_cache_tcbbo

SIMBOLOS = ["SPXW  261002P07700000", "SPXW  261002P07695000"]


def test_el_orden_de_los_simbolos_no_importa():
    a = ruta_cache_tcbbo("2026-10-02", SIMBOLOS)
    b = ruta_cache_tcbbo("2026-10-02", list(reversed(SIMBOLOS)))
    assert a == b


def test_dia_completo_no_lleva_sufijo():
    """Compatibilidad: los archivos del día completo ya descargados no tienen sufijo de franja."""
    ruta = ruta_cache_tcbbo("2026-10-02", SIMBOLOS)
    assert ruta.endswith(".parquet")
    assert "_0930-1600" not in ruta


def test_franja_lleva_sufijo():
    ruta = ruta_cache_tcbbo("2026-10-02", SIMBOLOS, "09:30", "11:00")
    assert ruta.endswith("_0930-1100.parquet")


def test_simbolos_distintos_rutas_distintas():
    """Si dos listas distintas compartieran archivo, leeríamos datos de OTRAS opciones."""
    a = ruta_cache_tcbbo("2026-10-02", SIMBOLOS)
    b = ruta_cache_tcbbo("2026-10-02", SIMBOLOS[:1])
    assert a != b


def test_fechas_distintas_rutas_distintas():
    assert ruta_cache_tcbbo("2026-10-02", SIMBOLOS) != ruta_cache_tcbbo("2026-09-29", SIMBOLOS)

# ================= caché POR SÍMBOLO (R3 de ODTE.md) =================
# Antes: otra lista de símbolos el mismo día = otro md5 = volver a pagar todo. Ahora solo se pide lo
# que no esté cubierto por algún archivo del día con una franja que contenga la pedida.
import os

import pandas as pd
import pytest

from src import datos
from src.odte import trades
from src.odte.trades import asegurar_tcbbo, leer_tcbbo, plan_tcbbo

DIA = "2026-10-02"
A, B, C, SIN = "SPXW  261002C07700000", "SPXW  261002P07700000", "SPXW  261002C07750000", "SPXW  261002C09999000"


def _filas(simbolos, desde, hasta, cada="10min"):
    """Un trade por símbolo cada `cada` en [desde, hasta), índice NY como los archivos guardados.
    SIN (un strike lejano) nunca tiene trades."""
    idx = pd.date_range(f"{DIA} {desde}", f"{DIA} {hasta}", freq=cada, tz="America/New_York", inclusive="left")
    partes = [pd.DataFrame({"symbol": s, "price": 1.0, "size": 1, "bid_px_00": 0.9, "ask_px_00": 1.1,
                            "bid_sz_00": 1, "ask_sz_00": 1}, index=idx) for s in simbolos if s != SIN]
    df = pd.concat(partes).sort_index(kind="stable") if partes else pd.DataFrame(columns=trades.COLUMNAS)
    df.index.name = "ts_recv"
    return df


class _ClienteTcbbo:
    """get_cost/get_range falsos: anota qué símbolos se pidieron; devuelve trades en UTC."""
    def __init__(self):
        self.pedidos, self.metadata, self.timeseries = [], self, self

    def get_cost(self, **p):
        return 0.01 * len(p["symbols"])

    def get_range(self, **p):
        self.pedidos.append(sorted(p["symbols"]))
        ini, fin = p["start"].tz_convert("America/New_York"), p["end"].tz_convert("America/New_York")
        df = _filas(p["symbols"], ini.strftime("%H:%M:%S"), fin.strftime("%H:%M:%S"))
        df.index = df.index.tz_convert("UTC")

        class R:
            def to_df(self_inner):
                return df
        return R()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cliente = _ClienteTcbbo()
    monkeypatch.setattr(datos, "_cliente", lambda: cliente)
    monkeypatch.setattr(datos, "_confirmar", lambda msg: True)
    return cliente


def _archivo_viejo(simbolos, desde="09:30", hasta="16:00"):
    """Un archivo como los ya descargados: sin .json, nombre por md5 de la lista exacta."""
    os.makedirs("data/raw", exist_ok=True)
    _filas(simbolos, desde, hasta).to_parquet(ruta_cache_tcbbo(DIA, simbolos, desde, hasta))


def test_superconjunto_solo_pide_lo_nuevo(cache):
    _archivo_viejo([A, B])
    asegurar_tcbbo({DIA: [A, B, C]})
    assert cache.pedidos == [[C]]                       # A y B ya estaban: no se vuelven a pagar
    df = leer_tcbbo(DIA, [A, B, C])
    assert set(df["symbol"]) == {A, B, C}
    assert df["symbol"].value_counts().to_dict() == {A: 39, B: 39, C: 39}   # 09:30-16:00 cada 10 min, sin duplicar
    assert df.index.is_monotonic_increasing


def test_subconjunto_no_descarga(cache):
    _archivo_viejo([A, B, C])
    asegurar_tcbbo({DIA: [B]})
    assert cache.pedidos == []
    assert set(leer_tcbbo(DIA, [B])["symbol"]) == {B}


def test_misma_lista_que_un_archivo_viejo_lee_identico(cache):
    _archivo_viejo([A, B])
    asegurar_tcbbo({DIA: [A, B]})
    assert cache.pedidos == []
    original = pd.read_parquet(ruta_cache_tcbbo(DIA, [A, B]))
    pd.testing.assert_frame_equal(leer_tcbbo(DIA, [A, B]), original)


def test_franja_mas_corta_dentro_de_una_mas_larga_no_descarga(cache):
    _archivo_viejo([A], "09:30", "16:15")
    asegurar_tcbbo({DIA: [A]}, "10:00", "11:00")
    assert cache.pedidos == []
    df = leer_tcbbo(DIA, [A], "10:00", "11:00")
    assert df.index.min().strftime("%H:%M") == "10:00" and df.index.max().strftime("%H:%M") == "10:50"


def test_franja_mas_larga_que_la_cacheada_descarga(cache):
    _archivo_viejo([A], "09:30", "11:00")
    asegurar_tcbbo({DIA: [A]})
    assert cache.pedidos == [[A]]


def test_simbolo_sin_trades_queda_cubierto_por_el_json(cache):
    asegurar_tcbbo({DIA: [A, SIN]})
    assert cache.pedidos == [sorted([A, SIN])]
    asegurar_tcbbo({DIA: [SIN]})
    asegurar_tcbbo({DIA: [A, SIN]})
    assert cache.pedidos == [sorted([A, SIN])]          # no se volvió a pedir
    assert leer_tcbbo(DIA, [SIN]).empty


def test_archivo_viejo_con_simbolo_sin_trades(cache):
    """Pedido EXACTO: cubierto por el md5. Dentro de otra lista: SIN se vuelve a pedir (cuesta ~$0)."""
    _archivo_viejo([A, SIN])
    asegurar_tcbbo({DIA: [A, SIN]})
    assert cache.pedidos == []
    asegurar_tcbbo({DIA: [A, B, SIN]})
    assert cache.pedidos == [sorted([B, SIN])]


def test_un_simbolo_sale_de_un_solo_archivo(cache):
    """A está en dos archivos: debe leerse una sola vez (sin trades duplicados)."""
    _archivo_viejo([A, B])
    _archivo_viejo([A, C])
    df = leer_tcbbo(DIA, [A, B, C])
    assert (df["symbol"] == A).sum() == len(_filas([A], "09:30", "16:00"))
    asignacion, faltan = plan_tcbbo(DIA, [A, B, C])
    assert faltan == [] and sum(len(v) for v in asignacion.values()) == 3


def test_leer_sin_cache_grita(cache):
    _archivo_viejo([A])
    with pytest.raises(RuntimeError, match="sin caché"):
        leer_tcbbo(DIA, [A, B])


def test_solo_costo_cotiza_solo_lo_que_falta(cache):
    _archivo_viejo([A, B])
    assert asegurar_tcbbo({DIA: [A, B, C]}, solo_costo=True) == pytest.approx(0.01)
    assert cache.pedidos == []
