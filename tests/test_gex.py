"""gex.py: el método se elige explícitamente y uno inventado falla fuerte (error que grita)."""
import pandas as pd
import pytest

from src.gex import construir_cadena, gamma_walls


def test_metodo_desconocido_falla():
    with pytest.raises(ValueError, match="metodo"):
        construir_cadena("2026-09-24", 7700.0, metodo="mid")


def test_gamma_walls_ignora_opciones_sin_gamma():
    """Con el método nuevo pueden quedar opciones con IV nan: no deben romper ni sumar."""
    c = pd.DataFrame({"strike": [7800.0, 7800.0, 7600.0, 7600.0],
                      "gex_contrib": [5e8, float("nan"), -3e8, float("nan")]})
    arriba, abajo = gamma_walls(c, 7700.0, n=1)
    assert arriba["nivel"].iloc[0] == 7800 and arriba["gex_contrib"].iloc[0] == 5e8
    assert abajo["nivel"].iloc[0] == 7600 and abajo["gex_contrib"].iloc[0] == -3e8


def test_default_es_mid_forward():
    """El default es una decisión documentada (valuación): cambiarlo debe ser explícito."""
    import inspect
    assert inspect.signature(construir_cadena).parameters["metodo"].default == "mid_forward"


def test_hipotesis_nula_de_signos():
    """Fija el PUNTO DE PARTIDA de la fase B, no una verdad: público vende calls y compra puts
    => dealer gamma +1 en calls, -1 en puts. Si este test cambia, cambió el supuesto de todo el GEX."""
    from src.gex import HIPOTESIS_NULA_PUBLICO, signo_gamma_supuesto
    assert HIPOTESIS_NULA_PUBLICO == {"C": "vende", "P": "compra"}
    assert list(signo_gamma_supuesto(["C", "P", "C"])) == [1, -1, 1]


def test_hipotesis_nula_sale_de_la_tabla_de_signos():
    """Una sola fuente de verdad: el signo supuesto se deriva de posicion_dealer, no se duplica."""
    from src.gex import HIPOTESIS_NULA_PUBLICO, signo_gamma_supuesto
    from src.odte.dealer import posicion_dealer
    for t, accion in HIPOTESIS_NULA_PUBLICO.items():
        assert signo_gamma_supuesto([t])[0] == posicion_dealer(accion, t)["gamma"]