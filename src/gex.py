"""
Cálculo del GEX (Gamma Exposure) y los gamma walls a partir de la cadena.
Conecta los datos crudos con la matemática de Black-Scholes.
"""
import pandas as pd
import numpy as np
from config import TASA_LIBRE_RIESGO
from src.black_scholes import calcular_iv, gamma_opcion
from src.datos import descargar_cadena


def _parsear_simbolo(sym):
    """Extrae vencimiento, tipo (C/P) y strike del símbolo codificado."""
    codigo = sym.split()[-1]
    venc = pd.to_datetime(codigo[:6], format="%y%m%d")
    tipo = codigo[6]
    strike = int(codigo[7:]) / 1000
    return pd.Series([venc, tipo, strike])


def construir_cadena(fecha, precio_spx):
    """Descarga la cadena, la procesa (IV, gamma) y devuelve la tabla completa."""
    precios, oi = descargar_cadena(fecha)
    c = precios.merge(oi, on="symbol", how="inner")
    c[["vencimiento", "tipo", "strike"]] = c["symbol"].apply(_parsear_simbolo)
    c["T"] = (c["vencimiento"] - pd.to_datetime(fecha)).dt.days / 365
    c = c[c["T"] > 0].copy()

    S, r = precio_spx, TASA_LIBRE_RIESGO
    c["iv"] = c.apply(lambda f: calcular_iv(f["precio_opcion"], S, f["strike"], f["T"], r, f["tipo"]), axis=1)
    c["gamma"] = c.apply(lambda f: gamma_opcion(S, f["strike"], f["T"], r, f["iv"]), axis=1)
    c["signo"] = np.where(c["tipo"] == "C", 1, -1)
    c["gex_contrib"] = c["gamma"] * c["open_interest"] * c["signo"] * 100 * (S**2) * 0.01
    return c


def gex_total(cadena):
    """Suma todas las contribuciones: el GEX total del día."""
    return cadena["gex_contrib"].sum()


def gamma_walls(cadena, precio_spx, n=5, banda=25):
    """Agrupa la gamma en bandas de precio (zonas) en vez de strikes exactos.
    Devuelve los n walls de resistencia (arriba) y soporte (abajo).
    banda: tamaño de la zona en puntos (ej: 25)."""
    c = cadena.copy()
    # Asignar cada strike a una banda (redondear al múltiplo de 'banda' más cercano)
    c["zona"] = (c["strike"] / banda).round() * banda
    # Sumar la gamma por zona (consolida strikes cercanos)
    perfil = c.groupby("zona")["gex_contrib"].sum().reset_index()
    perfil = perfil.rename(columns={"zona": "nivel"})

    arriba = perfil[perfil["nivel"] > precio_spx].nlargest(n, "gex_contrib")
    abajo = perfil[perfil["nivel"] < precio_spx].nsmallest(n, "gex_contrib")
    return arriba, abajo