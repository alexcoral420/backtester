"""Parseo de símbolos OSI: la pieza que usan el GEX, el trade sign, el catálogo y los scripts."""
import pandas as pd
import pytest

from src.simbolos import parsear_simbolo, parsear_simbolos


def test_spx_mensual():
    r = parsear_simbolo("SPX   261016C07800000")
    assert r["raiz"] == "SPX"
    assert r["venc_codigo"] == "261016"
    assert r["venc"] == pd.Timestamp("2026-10-16")
    assert r["tipo"] == "C"
    assert r["strike"] == 7800.0


def test_spxw_put():
    r = parsear_simbolo("SPXW  260930P07650000")
    assert r["raiz"] == "SPXW"
    assert r["venc"] == pd.Timestamp("2026-09-30")
    assert r["tipo"] == "P"
    assert r["strike"] == 7650.0


def test_strike_con_decimales():
    """El strike viene x1000: 7812.5 se codifica como 07812500."""
    assert parsear_simbolo("SPXW  261016C07812500")["strike"] == 7812.5


def test_serie_conserva_el_indice():
    """Si el índice se perdiera, al unir con la tabla original los datos se cruzarían."""
    s = pd.Series(["SPX   261016C07800000", "SPXW  261002P07700000"], index=[10, 20])
    r = parsear_simbolos(s)
    assert list(r.index) == [10, 20]
    assert list(r["raiz"]) == ["SPX", "SPXW"]


@pytest.mark.parametrize("malo", [
    "SPX261016C07800000",        # sin espacio entre raíz y código
    "SPX   261016X07800000",     # tipo que no es C ni P
    "SPX   261016C0780000",      # strike con un dígito de menos
    "ES.v.0",                    # no es una opción
])
def test_formato_raro_grita(malo):
    with pytest.raises(ValueError):
        parsear_simbolos(pd.Series(["SPX   261016C07800000", malo]))


def test_coincide_con_el_parseo_viejo():
    """Regresión: el resultado tiene que ser idéntico al de las copias que reemplaza."""
    simbolos = ["SPX   261016C07800000", "SPX   261016P07500000", "SPXW  261002P07695000"]
    nuevo = parsear_simbolos(pd.Series(simbolos))
    for i, sym in enumerate(simbolos):
        codigo = sym.split()[-1]                                     # lógica de gex.py
        assert nuevo["venc"][i] == pd.to_datetime(codigo[:6], format="%y%m%d")
        assert nuevo["tipo"][i] == codigo[6]
        assert nuevo["strike"][i] == int(codigo[7:]) / 1000
        assert nuevo["venc_codigo"][i] == codigo[:6]                 # lógica de trade_sign.py

# --- plazo_anios: T con la hora real de vencimiento de cada raíz ---

def _plazo(fecha, vencs, raices, modo):
    from src.simbolos import plazo_anios
    return plazo_anios(fecha, pd.Series(pd.to_datetime(vencs)), pd.Series(raices), modo)


def test_plazo_dias_es_el_calculo_de_siempre():
    t = _plazo("2026-10-15", ["2026-10-16", "2026-11-20"], ["SPXW", "SPX"], "dias")
    assert list(t) == [1 / 365, 36 / 365]


def test_plazo_horas_am_y_pm():
    """Jueves al cierre: SPXW del viernes = 24 h; SPX AM del viernes = 17,5 h (vence a las 9:30)."""
    t = _plazo("2026-10-15", ["2026-10-16", "2026-10-16"], ["SPXW", "SPX"], "horas")
    assert t.tolist() == pytest.approx([24 / 8760, 17.5 / 8760])


def test_plazo_horas_cruza_el_cambio_de_horario():
    """Viernes 30-oct a lunes 2-nov: el 1-nov termina el horario de verano -> 73 h, no 72."""
    t = _plazo("2026-10-30", ["2026-11-02"], ["SPXW"], "horas")
    assert t.iloc[0] == pytest.approx(73 / 8760)


def test_plazo_vencido_el_mismo_dia_no_es_positivo():
    t = _plazo("2026-10-16", ["2026-10-16", "2026-10-16"], ["SPXW", "SPX"], "horas")
    assert t.iloc[0] == 0 and t.iloc[1] < 0


def test_plazo_raiz_o_modo_desconocidos_gritan():
    with pytest.raises(ValueError, match="Raíz"):
        _plazo("2026-10-15", ["2026-10-16"], ["XSP"], "horas")
    with pytest.raises(ValueError, match="modo"):
        _plazo("2026-10-15", ["2026-10-16"], ["SPX"], "minutos")
