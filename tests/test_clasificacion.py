"""
Clasificación de trades. Datos sintéticos: bid 3.30 / ask 3.40, medio 3.35.
Se prueban las FRONTERAS de cada regla, que es donde viven los bugs.
"""
import pandas as pd
import pytest

from src.odte.clasificacion import clasificar_trades


def hacer_trades(precios, size=10):
    """Preparar: un trade por precio, todos con el mismo bid/ask. size en uint32 como Databento."""
    n = len(precios)
    return pd.DataFrame({
        "price": precios,
        "bid_px_00": [3.30] * n,
        "ask_px_00": [3.40] * n,
        # .values: sin índice propio. Una Series se ALINEARÍA por índice con las fechas -> NaN
        "size": pd.Series([size] * n, dtype="uint32").values,
        "instrument_class": ["P"] * n,
    }, index=pd.date_range("2026-10-02 09:50", periods=n, freq="s", tz="America/New_York"))


# ---------------- regla ESTRICTA (vigente) ----------------

@pytest.mark.parametrize("precio, signo_esperado, complejo", [
    (3.40, +1, False),   # exactamente en el ask -> compra limpia
    (3.30, -1, False),   # exactamente en el bid -> venta limpia
    (3.35,  0, False),   # en el medio -> indeterminado
    (3.32,  0, False),   # interior del spread -> indeterminado (patas, mejoras de precio)
    (3.13,  0, True),    # BAJO el bid -> paquete complejo, NO es venta
    (3.50,  0, True),    # SOBRE el ask -> paquete complejo, NO es compra
])
def test_regla_estricta(precio, signo_esperado, complejo):
    r = clasificar_trades(hacer_trades([precio]), estricto=True)
    assert r["signo"].iloc[0] == signo_esperado
    assert bool(r["complejo"].iloc[0]) == complejo


def test_regresion_vertical_2oct():
    """El put 7700 del 2-oct se imprimió a 3.13 con bid 3.30: la versión vieja lo contaba como venta."""
    r = clasificar_trades(hacer_trades([3.13], size=1500), estricto=True)
    assert r["flujo"].iloc[0] == 0


# ---------------- regla del PUNTO MEDIO (histórica) ----------------

@pytest.mark.parametrize("precio, signo_esperado", [
    (3.36, +1),   # sobre el medio
    (3.34, -1),   # bajo el medio
    (3.35,  0),   # exactamente en el medio
])
def test_regla_punto_medio(precio, signo_esperado):
    r = clasificar_trades(hacer_trades([precio]), estricto=False)
    assert r["signo"].iloc[0] == signo_esperado


# ---------------- tipos de dato ----------------

def test_flujo_negativo_no_desborda():
    """size llega como uint32 (sin negativos). Una venta debe dar flujo NEGATIVO, no un número gigante."""
    r = clasificar_trades(hacer_trades([3.30], size=1500), estricto=True)
    assert r["flujo"].iloc[0] == -1500
    assert r["flujo"].dtype == "int64"


def test_la_regla_es_obligatoria():
    """R1 de ODTE.md: sin valor por defecto, olvidar la regla grita en vez de usar la histórica."""
    with pytest.raises(TypeError):
        clasificar_trades(hacer_trades([3.40]))
    with pytest.raises(TypeError):
        clasificar_trades(hacer_trades([3.40]), True)      # tampoco por posición


def test_no_modifica_el_dataframe_original():
    original = hacer_trades([3.40, 3.30])
    clasificar_trades(original, estricto=True)
    assert "signo" not in original.columns