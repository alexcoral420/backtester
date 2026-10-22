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


def _cadena_pin():
    """Spot 7820. Pin de calls en 7800 (DEBAJO del precio, gamma +), puts en 7650, calls en 7900."""
    return pd.DataFrame({
        "strike": [7800.0, 7800.0, 7650.0, 7900.0, 7700.0],
        "tipo": ["C", "P", "P", "C", "P"],
        "gex_contrib": [9e8, -2e8, -4e8, 3e8, float("nan")],
    })


def test_niveles_muestra_pin_positivo_debajo_del_precio():
    """Regresión del 12/13-oct: gamma_walls no podía mostrar un nivel + debajo del spot."""
    from src.gex import niveles_gamma
    _, abajo = gamma_walls(_cadena_pin(), 7820.0, n=1)
    assert list(abajo["nivel"]) == [7650]           # gamma_walls rankea 'abajo' por lo MÁS NEGATIVO: el pin no sale
    v = niveles_gamma(_cadena_pin(), 7820.0)
    top = v.iloc[0]
    assert top["nivel"] == 7800 and top["signo_supuesto"] == "+" and top["posicion"] == "abajo"
    assert top["gex_neto"] == 7e8 and top["dominante"] == "calls"


def test_niveles_ordena_por_magnitud_sin_importar_el_lado():
    from src.gex import niveles_gamma
    v = niveles_gamma(_cadena_pin(), 7820.0)
    assert list(v["nivel"]) == [7800, 7650, 7900]                # 7700 (nan) no aparece
    assert v["pct_abs"].sum() == pytest.approx(100)
    assert list(v["posicion"]) == ["abajo", "abajo", "arriba"]


def test_niveles_marca_la_zona_del_spot():
    from src.gex import niveles_gamma
    v = niveles_gamma(_cadena_pin(), 7805.0)        # 7805 cae en la zona 7800
    assert v.set_index("nivel").loc[7800, "posicion"] == "en precio"


def test_niveles_signo_medido_separado_del_supuesto():
    """El público COMPRÓ en 7650 -> dealer corto (-). En 7900 vendió poco -> sin evidencia."""
    from src.gex import niveles_gamma
    medido = pd.Series({7650.0: 1500, 7655.0: 300, 7900.0: -150})
    v = niveles_gamma(_cadena_pin(), 7820.0, medido=medido).set_index("nivel")
    assert v.loc[7650, "neto_publico"] == 1800 and v.loc[7650, "signo_medido"] == "-"
    assert v.loc[7900, "signo_medido"] == "sin evidencia"
    assert v.loc[7800, "signo_medido"] == "no medido"
    assert v.loc[7800, "signo_supuesto"] == "+"                 # el supuesto no se toca


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

def test_plazo_desconocido_falla_antes_de_descargar():
    with pytest.raises(ValueError, match="plazo"):
        construir_cadena("2026-09-24", 7700.0, plazo="semanas")


def test_gex_por_plazo_desglosa_y_suma_el_total():
    from src.gex import gex_por_plazo, gex_total
    c = pd.DataFrame({"raiz": ["SPXW", "SPXW", "SPX", "SPX"], "dte": [1, 3, 22, 60],
                      "gex_contrib": [4e8, -1e8, 2e8, float("nan")]})
    p = gex_por_plazo(c)
    assert p.loc["SPXW", "1-3d"] == 3e8 and p.loc["SPX", "8-35d"] == 2e8
    assert p.loc["SPX", ">35d"] == 0 and p.loc["SPXW", "4-7d"] == 0
    assert p.to_numpy().sum() == pytest.approx(gex_total(c))
