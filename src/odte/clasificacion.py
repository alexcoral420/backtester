"""
clasificacion.py — ¿Quién agredió en cada trade?
Regla del punto medio (histórica) y regla estricta (vigente).
"""
import numpy as np
import pandas as pd


def clasificar_trades(trades: pd.DataFrame, *, estricto: bool) -> pd.DataFrame:
    """
    `estricto` es OBLIGATORIO y por nombre: antes valía False por defecto (la regla histórica), y un
    script que lo olvidaba usaba la regla vieja sin avisar.

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

UBICACIONES = ("ask", "bid", "fuera", "medio", "interior_ask", "interior_bid", "sin cotización")


def ubicar_trades(trades: pd.DataFrame) -> pd.Series:
    """
    DÓNDE se imprimió cada trade respecto del bid/ask (no quién agredió). Sirve para descomponer lo
    indeterminado de la regla estricta (cierre de M2, ODTE.md):
      'ask' / 'bid'        = los únicos que la regla estricta firma
      'fuera'              = fuera del bid/ask (= complejo: paquetes)
      'medio'              = exactamente en el punto medio: ninguna regla de cotización lo firma
      'interior_ask/_bid'  = dentro del spread, más cerca del ask / del bid. Firmarlos por cercanía es
                             INFERIDO (tipo Lee-Ready), nunca medido: va en columnas aparte.
      'sin cotización'     = bid o ask faltante
    Mismo redondeo a 4 decimales que clasificar_trades.
    """
    precio = trades["price"].round(4)
    bid, ask = trades["bid_px_00"].round(4), trades["ask_px_00"].round(4)
    medio = ((trades["bid_px_00"] + trades["ask_px_00"]) / 2).round(4)
    sin = bid.isna() | ask.isna()
    casos = [sin, precio == ask, precio == bid, (precio < bid) | (precio > ask), precio == medio,
             precio > medio, precio < medio]
    return pd.Series(np.select(casos, ["sin cotización", "ask", "bid", "fuera", "medio", "interior_ask",
                                       "interior_bid"], "sin cotización"), index=trades.index)
