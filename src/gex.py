"""
Cálculo del GEX (Gamma Exposure) y los gamma walls a partir de la cadena.
Conecta los datos crudos con la matemática de Black-Scholes.
"""
import pandas as pd
import numpy as np
from config import TASA_LIBRE_RIESGO
from src.black_scholes import calcular_iv, gamma_opcion
from src.datos import descargar_cadena
from src.odte.dealer import posicion_dealer
from src.simbolos import parsear_simbolos

# ------------------------------------------------------------------------------------------------
# HIPÓTESIS NULA del signo del dealer. NO es una regla ni una verdad: es un SUPUESTO POR DEFECTO.
#   Qué dice: el público VENDE calls (overwriting) y COMPRA puts (coberturas)
#             => el dealer está largo de calls (gamma +) y corto de puts (gamma -).
#   Para qué existe: es el punto de partida contra el cual la fase B MIDE desviaciones.
#   Lo que esperamos ver contradicho: los walls anómalos (box spreads del 8000, el bull put
#   institucional del 2-oct, el 42% de veredictos que cambiaron en la reverificación de walls).
#   Todo GEX calculado con esto descansa en un signo ASUMIDO, no medido.
# ------------------------------------------------------------------------------------------------
HIPOTESIS_NULA_PUBLICO = {"C": "vende", "P": "compra"}


def signo_gamma_supuesto(tipos):
    """Signo de la gamma del dealer por opción BAJO LA HIPÓTESIS NULA (+1 calls, -1 puts).
    Se deriva de la tabla de signos (src/odte/dealer.py), no se escribe a mano."""
    mapa = {t: posicion_dealer(HIPOTESIS_NULA_PUBLICO[t], t)["gamma"] for t in HIPOTESIS_NULA_PUBLICO}
    return pd.Series(tipos).map(mapa).values


METODOS = ("ultimo_trade", "mid_forward")


def construir_cadena(fecha, precio_spx, metodo="ultimo_trade"):
    """Descarga la cadena, la procesa (IV, gamma) y devuelve la tabla completa.

    metodo:
      "ultimo_trade" (default, el original): precio = último trade del día, solo opciones que
                     operaron ese día, sin dividendos (q = 0).
      "mid_forward"  (versión C validada el 24-sep): precio = punto medio bid/ask de cierre,
                     TODAS las opciones con OI, y q por vencimiento medido con la paridad call-put.
    """
    if metodo not in METODOS:
        raise ValueError(f"metodo debe ser uno de {METODOS}, no {metodo!r}")
    if metodo == "mid_forward":
        return _cadena_mid_forward(fecha, precio_spx)

    precios, oi = descargar_cadena(fecha)
    c = precios.merge(oi, on="symbol", how="inner")
    info = parsear_simbolos(c["symbol"])
    c["vencimiento"] = info["venc"]
    c["tipo"] = info["tipo"]
    c["strike"] = info["strike"]
    c["T"] = (c["vencimiento"] - pd.to_datetime(fecha)).dt.days / 365
    c = c[c["T"] > 0].copy()

    S, r = precio_spx, TASA_LIBRE_RIESGO
    c["iv"] = c.apply(lambda f: calcular_iv(f["precio_opcion"], S, f["strike"], f["T"], r, f["tipo"]), axis=1)
    c["gamma"] = c.apply(lambda f: gamma_opcion(S, f["strike"], f["T"], r, f["iv"]), axis=1)
    c["signo"] = signo_gamma_supuesto(c["tipo"])           # ASUMIDO (hipótesis nula), no medido
    c["gex_contrib"] = c["gamma"] * c["open_interest"] * c["signo"] * 100 * (S**2) * 0.01
    return c


def _cadena_mid_forward(fecha, precio_spx):
    """Versión C con forward medido. Mismas columnas que la original, más 'q' y 'con_trade'."""
    from src.forward import forward_por_vencimiento, q_por_opcion
    from src.precio_justo import tabla_cierre

    S, r = precio_spx, TASA_LIBRE_RIESGO
    c = tabla_cierre(fecha)
    c = c[c["T"] > 0].copy()
    c["q"] = q_por_opcion(c, forward_por_vencimiento(c, S, r))
    c = c.rename(columns={"venc": "vencimiento"}).reset_index()
    c["precio_opcion"] = c["mid"]
    c["iv"] = [calcular_iv(p, S, k, T, r, tp, q) for p, k, T, tp, q in
               zip(c["precio_opcion"], c["strike"], c["T"], c["tipo"], c["q"])]
    c["gamma"] = [gamma_opcion(S, k, T, r, v, q) for k, T, v, q in
                  zip(c["strike"], c["T"], c["iv"], c["q"])]
    c["signo"] = signo_gamma_supuesto(c["tipo"])           # ASUMIDO (hipótesis nula), no medido
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