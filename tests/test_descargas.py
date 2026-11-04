"""
Descargas 0DTE (M3): caché primero, costo total, UNA confirmación por paso, y cierres tempranos.
Sin red: el cliente de Databento es falso y cuenta lo que se le pide. Cada test corre en una carpeta
temporal (la caché data/raw es relativa al directorio de trabajo).
"""
import os

import pandas as pd
import pytest

from src import datos
from src.odte import calendario
from src.odte.catalogo import filtrar_0dte
from src.odte.descargas import asegurar_odte
from src.odte.precio import horario_regular
from src.odte.trades import asegurar_tcbbo, ruta_cache_tcbbo

UTC = "UTC"


class _Respuesta:
    def __init__(self, df):
        self._df = df

    def to_df(self):
        return self._df


class ClienteFalso:
    """Imita metadata.get_cost y timeseries.get_range. Devuelve datos según el schema."""
    def __init__(self, costo=0.25):
        self.costo, self.cotizados, self.bajados = costo, [], []
        self.metadata, self.timeseries = self, self

    def get_cost(self, **p):
        self.cotizados.append(p["schema"])
        return self.costo

    def get_range(self, **p):
        self.bajados.append(p["schema"])
        inicio = pd.Timestamp(p["start"])          # 'AAAA-MM-DD' (definition, ES) o UTC (tcbbo)
        if inicio.tzinfo is not None:
            inicio = inicio.tz_convert("America/New_York").tz_localize(None)
        dia = inicio.normalize()
        if p["schema"] == "definition":
            cod = dia.strftime("%y%m%d")
            return _Respuesta(pd.DataFrame({
                "raw_symbol": [f"SPXW  {cod}C07700000", f"SPXW  {cod}P07700000"],
                "instrument_class": ["C", "P"], "strike_price": [7700.0, 7700.0],
                "expiration": pd.to_datetime([dia + pd.Timedelta(days=1)] * 2, utc=True),
            }))
        idx = pd.date_range(f"{dia:%Y-%m-%d} 09:00", f"{dia:%Y-%m-%d} 17:00", freq="1min",
                            tz="America/New_York").tz_convert(UTC)
        if p["schema"] == "ohlcv-1m":
            return _Respuesta(pd.DataFrame({c: 1.0 for c in ["open", "high", "low", "close", "volume"]}, index=idx))
        return _Respuesta(pd.DataFrame({"symbol": "x", "price": 1.0, "size": 1, "bid_px_00": 0.9, "ask_px_00": 1.1,
                                        "bid_sz_00": 1, "ask_sz_00": 1, "otra": 0}, index=idx[:3]))


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Carpeta temporal + cliente falso + confirmaciones contadas (responde 's')."""
    monkeypatch.chdir(tmp_path)
    cliente = ClienteFalso()
    monkeypatch.setattr(datos, "_cliente", lambda: cliente)
    preguntas = []
    monkeypatch.setattr(datos, "_confirmar", lambda msg: preguntas.append(msg) or True)
    return cliente, preguntas


DIAS = ["2026-10-13", "2026-10-14", "2026-10-15"]
SIMB = ["SPXW  261014C07700000"]


# ---------------- patrón único: asegurar_descargas / asegurar_tcbbo ----------------

def test_varios_dias_una_sola_confirmacion(entorno):
    cliente, preguntas = entorno
    costo = asegurar_tcbbo({d: SIMB for d in DIAS})
    assert len(preguntas) == 1                      # UNA, no una por día
    assert costo == pytest.approx(0.75)             # costo TOTAL de los 3 días
    assert "0.7500" in preguntas[0]
    assert cliente.bajados == ["tcbbo"] * 3


def test_cache_completa_no_cotiza_ni_pregunta(entorno):
    cliente, preguntas = entorno
    asegurar_tcbbo({d: SIMB for d in DIAS})
    cliente.cotizados.clear(), preguntas.clear()
    assert asegurar_tcbbo({d: SIMB for d in DIAS}) == 0.0
    assert cliente.cotizados == [] and preguntas == []


def test_solo_cotiza_lo_que_falta(entorno):
    cliente, preguntas = entorno
    asegurar_tcbbo({DIAS[0]: SIMB})
    cliente.cotizados.clear()
    asegurar_tcbbo({d: SIMB for d in DIAS})
    assert len(cliente.cotizados) == 2              # el día en caché cuesta $0


def test_solo_costo_no_pregunta_ni_descarga(entorno):
    cliente, preguntas = entorno
    assert asegurar_tcbbo({d: SIMB for d in DIAS}, solo_costo=True) == pytest.approx(0.75)
    assert preguntas == [] and cliente.bajados == []


def test_cancelar_no_guarda_nada(entorno, monkeypatch):
    cliente, _ = entorno
    monkeypatch.setattr(datos, "_confirmar", lambda msg: False)
    with pytest.raises(SystemExit):
        asegurar_tcbbo({DIAS[0]: SIMB})
    assert cliente.bajados == []
    assert not os.path.exists(ruta_cache_tcbbo(DIAS[0], SIMB))


def test_tcbbo_se_guarda_en_nueva_york_con_las_columnas_de_siempre(entorno):
    """Mismo formato que los archivos ya descargados (si cambia, los scripts leen otra cosa)."""
    asegurar_tcbbo({DIAS[0]: SIMB})
    df = pd.read_parquet(ruta_cache_tcbbo(DIAS[0], SIMB))
    assert str(df.index.tz) == "America/New_York"
    assert list(df.columns) == ["symbol", "price", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]


# ---------------- rango 0DTE completo: como mucho DOS confirmaciones ----------------

def test_asegurar_odte_rango_dos_confirmaciones(entorno):
    cliente, preguntas = entorno
    asegurar_odte({d: (7600, 7800) for d in DIAS})
    assert len(preguntas) == 2                      # 1) catálogo + ES   2) tcbbo
    assert sorted(set(cliente.bajados)) == ["definition", "ohlcv-1m", "tcbbo"]
    assert cliente.bajados.count("tcbbo") == 3


def test_asegurar_odte_ventana_sin_opciones_grita(entorno):
    with pytest.raises(RuntimeError, match="Sin opciones 0DTE"):
        asegurar_odte({DIAS[0]: (5000, 5100)})


def test_asegurar_odte_solo_costo_sin_catalogo_no_cotiza_tcbbo(entorno):
    cliente, preguntas = entorno
    asegurar_odte({d: (7600, 7800) for d in DIAS}, solo_costo=True)
    assert "tcbbo" not in cliente.cotizados and cliente.bajados == [] and preguntas == []


# ---------------- cierres tempranos (R2) ----------------

def test_hora_cierre():
    assert calendario.hora_cierre("2026-10-14") == "16:00"
    assert calendario.hora_cierre("2026-11-27") == "13:00"     # día después de Acción de Gracias
    assert calendario.hora_cierre("2026-12-24") == "13:00"
    assert calendario.ultima_barra("2026-11-27") == "12:59"


def test_anio_sin_tabla_grita():
    with pytest.raises(ValueError, match="2027"):
        calendario.hora_cierre("2027-01-05")


def test_vencimiento_en_cierre_temprano_es_13h():
    cat = pd.DataFrame({"raw_symbol": ["SPXW  261127C07700000"], "instrument_class": ["C"],
                        "strike_price": [7700.0], "expiration": pd.to_datetime(["2026-11-28"], utc=True)})
    r = filtrar_0dte(cat, "2026-11-27")
    assert r["venc_ny"].iloc[0] == pd.Timestamp("2026-11-27 13:00", tz="America/New_York")


def test_es_en_cierre_temprano_corta_en_12_59():
    """La base sale de la última barra: con 16:00 fijo habría salido de una barra sin sesión."""
    idx = pd.date_range("2026-11-27 09:00", "2026-11-27 17:00", freq="1min", tz="America/New_York").tz_convert(UTC)
    es = pd.DataFrame({c: 1.0 for c in ["open", "high", "low", "close", "volume"]}, index=idx)
    r = horario_regular(es, "2026-11-27")
    assert r.index[0].strftime("%H:%M") == "09:30"
    assert r.index[-1].strftime("%H:%M") == "12:59"
    normal = horario_regular(es.set_axis(es.index - pd.Timedelta(days=44)), "2026-10-14")
    assert normal.index[-1].strftime("%H:%M") == "15:59"
