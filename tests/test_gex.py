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