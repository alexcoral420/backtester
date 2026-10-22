"""
precio_justo.py — Precio de cada opción al cierre: punto medio del bid/ask de cierre.

Por qué: el "último trade del día" (ohlcv close) era viejo en el 74% de las opciones
(fuera del bid/ask de cierre) y no existe para las que no se negociaron (25% del OI).
El bid/ask de cierre viene en el statistics que ya se descarga con la cadena
(stat_type 8 = HIGHEST_BID, 7 = LOWEST_OFFER), así que no cuesta nada extra.
"""
import numpy as np
import pandas as pd

from src.datos import descargar_cadena, ruta_cadena
from src.simbolos import parsear_simbolos, plazo_anios

STAT_BID, STAT_ASK = 8, 7


def punto_medio(bid, ask):
    """Punto medio solo si la cotización tiene sentido: bid > 0, ask > 0 y ask >= bid.
    Si no, nan (una cotización de 0 o cruzada no es un precio)."""
    bid, ask = np.asarray(bid, dtype=float), np.asarray(ask, dtype=float)
    valido = (bid > 0) & (ask > 0) & (ask >= bid)
    return np.where(valido, (bid + ask) / 2, np.nan)


def _ultima(stats, stat_type, columna):
    g = stats[stats["stat_type"] == stat_type].sort_values("ts_event", kind="stable")
    return g.drop_duplicates("symbol", keep="last").set_index("symbol")[columna]


def tabla_cierre(fecha, raices=("SPX",), plazo="dias"):
    """
    Una fila por opción con OI. Columnas:
      open_interest, bid, ask, mid (nan si la cotización no sirve), ultimo_trade (nan si no operó),
      con_trade, raiz, venc, tipo, strike, T (años, simbolos.plazo_anios con 'plazo', como gex.py)
    Usa la caché de la cadena (la descarga con confirmación de costo si falta).
    """
    precios, oi = descargar_cadena(fecha, raices)
    stats = pd.concat([pd.read_parquet(ruta_cadena(r, "statistics", fecha)) for r in raices],
                      ignore_index=True)

    t = oi.set_index("symbol")[["open_interest"]].copy()
    t["bid"] = _ultima(stats, STAT_BID, "price")
    t["ask"] = _ultima(stats, STAT_ASK, "price")
    t["mid"] = punto_medio(t["bid"], t["ask"])
    t["ultimo_trade"] = precios.set_index("symbol")["precio_opcion"]
    t["con_trade"] = t["ultimo_trade"].notna()

    info = parsear_simbolos(pd.Series(t.index, index=t.index))
    t = t.join(info[["raiz", "venc", "tipo", "strike"]])
    t["T"] = plazo_anios(fecha, t["venc"], t["raiz"], plazo)
    return t