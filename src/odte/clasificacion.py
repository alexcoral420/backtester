"""
clasificacion.py — ¿Quién agredió en cada trade?
Regla del punto medio (histórica) y regla estricta (vigente).
"""
import pandas as pd


def clasificar_trades(trades: pd.DataFrame, estricto: bool = False) -> pd.DataFrame:
    """
    estricto=False (regla del punto medio):
      precio > medio -> +1 (el público COMPRA, dealer queda short esa opción)
      precio < medio -> -1 (el público VENDE, dealer queda long)
      precio = medio ->  0 (indeterminado, no suma)
    estricto=True (solo agresores limpios):
      precio == ask -> +1 | precio == bid -> -1 | todo lo demás -> 0
      - interior del spread: patas de spreads y mejoras de precio
      - FUERA del bid/ask: huella de órdenes complejas (paquetes de varias patas)
      Columna 'complejo' = True si el trade se imprimió fuera del bid/ask.
    'flujo' = signo x size, en int64 (size viene uint32 y no admite negativos).
    """
    df = trades.copy()
    precio = df["price"].round(4)
    bid, ask = df["bid_px_00"].round(4), df["ask_px_00"].round(4)
    df["complejo"] = (precio < bid) | (precio > ask)
    df["signo"] = 0
    if estricto:
        df.loc[precio == ask, "signo"] = 1
        df.loc[precio == bid, "signo"] = -1
    else:
        medio = ((df["bid_px_00"] + df["ask_px_00"]) / 2).round(4)
        df.loc[precio > medio, "signo"] = 1
        df.loc[precio < medio, "signo"] = -1
    df["flujo"] = df["signo"].astype("int64") * df["size"].astype("int64")
    return df