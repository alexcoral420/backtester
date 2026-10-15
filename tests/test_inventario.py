"""Inventario B1: el ΔOI se calcula contra el día anterior de la serie, por opción, sin inventar nada."""
import numpy as np
import pandas as pd

import pytest

from src.inventario import delta_oi, fecha_flujo, por_zona


def _tabla():
    f1, f2, f3 = pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"])
    return pd.DataFrame([
        # symbol, fecha, oi, tipo, strike
        ("A", f1, 100, "C", 7800.0), ("A", f2, 130, "C", 7800.0), ("A", f3, 120, "C", 7800.0),
        ("B", f1, 50, "P", 7500.0), ("B", f2, 50, "P", 7500.0), ("B", f3, 80, "P", 7500.0),
        ("C", f2, 40, "C", 7810.0), ("C", f3, 45, "C", 7810.0),         # aparece el día 2
    ], columns=["symbol", "fecha", "oi", "tipo", "strike"])


def test_delta_contra_el_dia_anterior_de_la_serie():
    t = delta_oi(_tabla()).set_index(["symbol", "fecha"])
    assert np.isnan(t.loc[("A", pd.Timestamp("2026-10-01")), "delta_oi"])       # primer día: sin delta
    assert t.loc[("A", pd.Timestamp("2026-10-02")), "delta_oi"] == 30
    assert t.loc[("A", pd.Timestamp("2026-10-05")), "delta_oi"] == -10          # fin de semana: contra el 2
    assert t.loc[("B", pd.Timestamp("2026-10-05")), "delta_oi"] == 30


def test_opcion_nueva_se_marca_y_no_inventa_delta():
    t = delta_oi(_tabla()).set_index(["symbol", "fecha"])
    fila = t.loc[("C", pd.Timestamp("2026-10-02"))]
    assert bool(fila["nueva"]) and np.isnan(fila["delta_oi"])
    assert t.loc[("C", pd.Timestamp("2026-10-05")), "delta_oi"] == 5


def test_por_zona_suma_strikes_cercanos_por_tipo():
    z = por_zona(delta_oi(_tabla()), banda=25)
    fila = z[(z["fecha"] == pd.Timestamp("2026-10-05")) & (z["zona"] == 7800) & (z["tipo"] == "C")].iloc[0]
    assert fila["oi"] == 165 and fila["delta_oi"] == -5                         # A (-10) + C (+5)


DIAS = ["2026-09-30", "2026-10-01", "2026-10-02", "2026-10-05"]


def test_delta_oi_de_d_se_empareja_con_flujo_de_d_menos_1():
    """Regla de tiempo confirmada el 15-oct: el OI del archivo de d = cierre de d-1."""
    assert fecha_flujo("2026-10-02", DIAS) == pd.Timestamp("2026-10-01")


def test_lunes_se_empareja_con_el_viernes():
    assert fecha_flujo("2026-10-05", DIAS) == pd.Timestamp("2026-10-02")


def test_sin_dia_anterior_falla_fuerte():
    with pytest.raises(ValueError):
        fecha_flujo("2026-09-30", DIAS)