"""
Trade sign: clasifica el flujo de operaciones para inferir el lado del dealer.
Compara el precio de cada trade contra el punto medio del spread.
"""
import os
import hashlib
import numpy as np
import pandas as pd
from src.datos import descargar_cadena, descargar_trades


def elegir_atm(fecha, precio_spx, vencimiento, n_strikes=3):
    """Elige los strikes ATM que REALMENTE existen, de un vencimiento dado.
    vencimiento: código tipo '261016'. Devuelve lista de símbolos."""
    precios, _ = descargar_cadena(fecha)
    p = precios.copy()
    p["codigo"] = p["symbol"].str.split().str[-1]
    p["venc"] = p["codigo"].str[:6]
    p["strike"] = p["codigo"].str[7:].astype(int) / 1000
    p = p[p["venc"] == vencimiento].copy()
    p["dist"] = (p["strike"] - precio_spx).abs()
    return p.nsmallest(n_strikes * 2, "dist")["symbol"].tolist()


def simbolos_de_wall(precios, strike, vencimiento):
    """Devuelve los símbolos del call y put de un strike/vencimiento.
    Recibe la cadena ya descargada (precios), no la re-descarga."""
    p = precios.copy()
    p["codigo"] = p["symbol"].str.split().str[-1]
    p["venc"] = p["codigo"].str[:6]
    p["strike"] = p["codigo"].str[7:].astype(int) / 1000
    sel = p[(p["venc"] == vencimiento) & (p["strike"] == strike)]
    return sel["symbol"].tolist()


def clasificar_flujo(fecha_inicio, fecha_fin, simbolos):
    """Descarga (o carga de caché) los trades y los clasifica por punto medio.
    El caché depende de las fechas Y de los símbolos (para no mezclar)."""
    # Hash único de los símbolos → cada set de opciones tiene su propio caché
    id_sim = hashlib.md5("".join(sorted(simbolos)).encode()).hexdigest()[:8]
    ruta_cache = f"data/raw/trades_{fecha_inicio}_{fecha_fin}_{id_sim}.parquet"

    if os.path.exists(ruta_cache):
        t = pd.read_parquet(ruta_cache)
    else:
        t = descargar_trades(simbolos, fecha_inicio, fecha_fin)
        t.to_parquet(ruta_cache)

    # Clasificar con la regla del punto medio
    t["size"] = t["size"].astype("int64")          # evita el overflow de uint64
    t["punto_medio"] = (t["bid_px_00"] + t["ask_px_00"]) / 2
    t["clasif"] = np.where(t["price"] > t["punto_medio"], "COMPRA",
                  np.where(t["price"] < t["punto_medio"], "VENTA", "INDET"))
    t["dia"] = t["ts_recv"].dt.strftime("%Y-%m-%d")
    t["tipo"] = t["symbol"].str.split().str[-1].str[6]
    return t


def flujo_neto(sub):
    """Flujo neto de un subconjunto: compras menos ventas (dealer short si positivo)."""
    compras = int(sub[sub["clasif"] == "COMPRA"]["size"].sum())
    ventas = int(sub[sub["clasif"] == "VENTA"]["size"].sum())
    return compras - ventas