"""
Veredicto del signo medido: un signo solo si |neto| >= MIN_ABS Y lo indeterminado no alcanza para
invertirlo (peor caso). Se prueban las FRONTERAS de cada prueba.
"""
import math

import pandas as pd
import pytest

from src.gex import HIPOTESIS_NULA_PUBLICO
from src.odte.veredicto import pct_indet, signo_dealer, volumenes, vs_nula
from src.signo_medido import MIN_ABS


# ---------------- signo del dealer ----------------

@pytest.mark.parametrize("compra, venta, indet, esperado", [
    (0, 0, 0, "sin flujo"),
    (MIN_ABS - 1, 0, 0, "sin evidencia"),        # 199 limpios no son evidencia
    (MIN_ABS, 0, 0, "-"),                        # 200 limpios: el público compró -> dealer corto
    (0, MIN_ABS, 0, "+"),                        # el público vendió -> dealer largo
    (1000, 0, 1000, "indet. domina"),            # empate: lo indeterminado lo puede anular
    (1000, 0, 999, "-"),                         # 1 contrato de margen: sobrevive al peor caso
    (5000, 4000, 2000, "indet. domina"),         # neto +1000 con 2000 sin firmar
    (100, 400, 0, "+"),                          # neto -300
])
def test_signo_dealer_fronteras(compra, venta, indet, esperado):
    assert signo_dealer(compra, venta, indet) == esperado


def test_signo_con_mucho_volumen_indeterminado_no_opina():
    """El caso que motivó M1: 90% indeterminado. Con la regla vieja (solo MIN_ABS) daba un signo."""
    assert signo_dealer(compra=1000, venta=0, indet=9000) == "indet. domina"


def test_signo_sale_de_la_tabla_del_dealer():
    """Público compra -> dealer short -> gamma -, sea call o put (dealer.py)."""
    assert signo_dealer(1000, 0, 0) == "-"
    assert signo_dealer(0, 1000, 0) == "+"


def test_volumen_negativo_grita():
    with pytest.raises(ValueError):
        signo_dealer(-1, 0, 0)
    with pytest.raises(ValueError):
        pct_indet(0, 0, -5)


# ---------------- % indeterminado ----------------

def test_pct_indet():
    assert pct_indet(30, 20, 50) == pytest.approx(50.0)
    assert pct_indet(10, 0, 0) == 0.0


def test_pct_indet_sin_volumen_es_nan():
    assert math.isnan(pct_indet(0, 0, 0))


# ---------------- contra la hipótesis nula ----------------

def test_vs_nula_calls_y_puts():
    """Nula: el público vende calls y compra puts. Se lee de src/gex, no se escribe a mano."""
    assert vs_nula(0, 1000, 0, HIPOTESIS_NULA_PUBLICO["C"]) == "confirma"
    assert vs_nula(1000, 0, 0, HIPOTESIS_NULA_PUBLICO["C"]) == "CONTRADICE"
    assert vs_nula(1000, 0, 0, HIPOTESIS_NULA_PUBLICO["P"]) == "confirma"
    assert vs_nula(0, 1000, 0, HIPOTESIS_NULA_PUBLICO["P"]) == "CONTRADICE"


def test_vs_nula_usa_las_mismas_pruebas():
    assert vs_nula(0, 0, 0, "vende") == "sin flujo"
    assert vs_nula(0, 150, 0, "vende") == "sin evidencia"
    assert vs_nula(0, 1000, 1500, "vende") == "indet. domina"


def test_vs_nula_accion_invalida_grita():
    with pytest.raises(ValueError):
        vs_nula(0, 1000, 0, "vendió")


# ---------------- agregación desde trades clasificados ----------------

def test_volumenes_por_strike():
    clasificados = pd.DataFrame({
        "strike_price": [7700, 7700, 7700, 7705],
        "signo": [1, -1, 0, 1],
        "size": pd.Series([10, 4, 7, 3], dtype="uint32").values,
    })
    v = volumenes(clasificados, "strike_price")
    assert list(v.columns) == ["compra", "venta", "indet"]
    assert v.loc[7700].tolist() == [10, 4, 7]
    assert v.loc[7705].tolist() == [3, 0, 0]      # estados ausentes -> 0, no NaN


def test_volumenes_vacio_no_rompe():
    vacio = pd.DataFrame({"strike_price": [], "signo": [], "size": []})
    v = volumenes(vacio, "strike_price").reindex([7700], fill_value=0)
    assert v.loc[7700].tolist() == [0, 0, 0]
    assert signo_dealer(*v.loc[7700]) == "sin flujo"


def test_volumenes_sin_clasificar_grita():
    with pytest.raises(ValueError, match="signo"):
        volumenes(pd.DataFrame({"strike_price": [7700], "size": [1]}), "strike_price")
