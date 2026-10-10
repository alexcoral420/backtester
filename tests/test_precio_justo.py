"""Punto medio de cierre: cuándo una cotización es un precio y cuándo no."""
import numpy as np
import pytest

from src.precio_justo import punto_medio


def test_cotizacion_normal():
    assert punto_medio(4.80, 4.90) == pytest.approx(4.85)


@pytest.mark.parametrize("bid, ask", [
    (0.0, 0.05),     # sin bid: no hay quien compre, no es un precio
    (4.9, 4.8),      # cotización cruzada (ask < bid)
    (0.0, 0.0),      # sin cotización (Databento usa 0 como "sin dato" en CLOSE_PRICE)
    (np.nan, 5.0),   # falta el dato
])
def test_cotizacion_invalida_es_nan(bid, ask):
    assert np.isnan(punto_medio(bid, ask))


def test_trabaja_con_series():
    r = punto_medio([1.0, 0.0, 3.0], [1.2, 0.1, 3.4])
    assert r[0] == pytest.approx(1.1)
    assert np.isnan(r[1])
    assert r[2] == pytest.approx(3.2)