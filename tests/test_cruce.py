"""
Corte del primer cruce / máxima aproximación. Regla de tiempo: solo cuenta el flujo ANTERIOR a que
el precio llegara al strike, y el minuto del cruce queda fuera.
"""
import pandas as pd
import pytest

from src.odte.cruce import corte_strike


def sesion(precios, inicio="2026-10-14 09:30"):
    idx = pd.date_range(inicio, periods=len(precios), freq="1min", tz="America/New_York")
    return pd.Series(precios, index=idx, dtype=float)


def test_cruce_hacia_abajo():
    dia = sesion([7710, 7706, 7704, 7699, 7702])          # strike 7700: cruza en la 4ª barra (09:33)
    t0, etiqueta = corte_strike(dia, 7700)
    assert t0 == pd.Timestamp("2026-10-14 09:33", tz="America/New_York")
    assert etiqueta == "09:33"


def test_cruce_hacia_arriba():
    dia = sesion([7690, 7695, 7701, 7698])
    t0, etiqueta = corte_strike(dia, 7700)
    assert etiqueta == "09:32"


def test_tocar_el_strike_no_es_cruzarlo_desde_abajo():
    """'Arriba' es estrictamente > strike: quedarse en 7700 exacto sigue siendo 'abajo'."""
    dia = sesion([7695, 7700, 7700, 7699])
    t0, etiqueta = corte_strike(dia, 7700)
    assert etiqueta.startswith("nunca")


def test_nunca_cruzado_strike_debajo_corta_en_el_minimo():
    """Caso 7690 del 14-oct: el precio bajó hasta 14:01 y rebotó sin cruzar. Corte = el mínimo."""
    dia = sesion([7720, 7710, 7695, 7705, 7730])
    t0, etiqueta = corte_strike(dia, 7690)
    assert t0 == dia.idxmin()
    assert etiqueta == "nunca (aprox 09:32)"


def test_nunca_cruzado_strike_encima_corta_en_el_maximo():
    dia = sesion([7700, 7720, 7780, 7750])
    t0, etiqueta = corte_strike(dia, 7790)
    assert t0 == dia.idxmax()
    assert etiqueta == "nunca (aprox 09:32)"


def test_serie_vacia_grita():
    with pytest.raises(ValueError, match="vacía"):
        corte_strike(pd.Series([], dtype=float), 7700)


def test_serie_desordenada_grita():
    dia = sesion([7710, 7699, 7705]).iloc[[2, 0, 1]]
    with pytest.raises(ValueError, match="ordenada"):
        corte_strike(dia, 7700)
