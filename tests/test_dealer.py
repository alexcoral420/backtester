"""
La tabla de signos del dealer. Cada fila de la tabla de la master class es un caso.
`parametrize` corre el MISMO test con distintos datos: una fila = un test.
"""
import pytest

from src.odte.dealer import posicion_dealer


@pytest.mark.parametrize("publico, tipo, lado, delta, gamma, cobertura, efecto", [
    ("compra", "C", "short", -1, -1, "compra índice", "amplifica"),
    ("vende",  "C", "long",  +1, +1, "vende índice",  "frena"),
    ("compra", "P", "short", +1, -1, "vende índice",  "amplifica"),
    ("vende",  "P", "long",  -1, +1, "compra índice", "frena"),
])
def test_tabla_de_signos(publico, tipo, lado, delta, gamma, cobertura, efecto):
    r = posicion_dealer(publico, tipo)
    assert r["lado"] == lado
    assert r["delta"] == delta
    assert r["gamma"] == gamma
    assert r["cobertura"] == cobertura
    assert r["efecto"] == efecto


def test_gamma_no_depende_del_delta():
    """Regresión de un error de razonamiento: long puts = delta NEGATIVO y gamma POSITIVO."""
    r = posicion_dealer("vende", "P")
    assert r["delta"] < 0
    assert r["gamma"] > 0


def test_entrada_invalida_falla_ruidosamente():
    """Mejor un error que grita que un resultado que susurra."""
    with pytest.raises(ValueError):
        posicion_dealer("compro", "C")
    with pytest.raises(ValueError):
        posicion_dealer("compra", "X")