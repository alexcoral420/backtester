"""
flujo.py — ¿Cómo se acumula el flujo en el tiempo?
Agrega trades ya clasificados por minuto, calls y puts separados.
"""
import pandas as pd


def flujo_por_minuto(clasificados: pd.DataFrame) -> pd.DataFrame:
    """
    Flujo neto del PÚBLICO por minuto, calls y puts separados, más sus acumulados.
    (El dealer tiene el signo contrario.)
    """
    minuto = clasificados.index.floor("1min")
    tabla = (clasificados.groupby([minuto, "instrument_class"])["flujo"]
             .sum()
             .unstack(fill_value=0)
             .rename(columns={"C": "flujo_C", "P": "flujo_P"}))
    tabla.index.name = "minuto"
    tabla["acum_C"] = tabla["flujo_C"].cumsum()
    tabla["acum_P"] = tabla["flujo_P"].cumsum()
    return tabla