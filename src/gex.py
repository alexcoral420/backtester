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


def construir_cadena(fecha, precio_spx, metodo="mid_forward"):
    """Descarga la cadena, la procesa (IV, gamma) y devuelve la tabla completa.

    metodo:
      "mid_forward"  (DEFAULT): precio = punto medio bid/ask de cierre, TODAS las opciones con OI,
                     y q por vencimiento medido con la paridad call-put.
      "ultimo_trade" (el original, se conserva para comparar): último trade del día, solo opciones
                     que operaron ese día, sin dividendos (q = 0).

    POR QUÉ mid_forward es el default (oct-2026): por VALUACIÓN, no por predicción.
      - el libro del dealer incluye el OI que no operó ese día (~25% del OI): hay que contarlo
      - sin forward las calls ITM daban IV nan y se tiraban -> inventaban walls (caso 7000, 24-sep)
      - el último trade estaba fuera del bid/ask de cierre en el 74% de los casos
    La predicción del rango siguiente (validar_gex, 25 días en 3 regímenes) salió PAREJA entre
    métodos: no es la razón del cambio, y una ventana donde el viejo prediga mejor no la invalida.
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


MIN_ABS_NIVEL = 200      # contratos netos medidos por zona para opinar (mismo piso que signo_medido.MIN_ABS)


def niveles_gamma(cadena, precio_spx, n=10, banda=25, medido=None, min_abs=MIN_ABS_NIVEL):
    """Niveles de gamma SIN interpretar: ranking por magnitud, con signo y posición como columnas.

    A diferencia de gamma_walls, no decide de antemano que 'abajo = soporte (gamma -)' y
    'arriba = resistencia (gamma +)'. Un pin de gamma + debajo del precio (7800 el 12-oct) aparece.

    Columnas por zona:
      nivel, distancia (nivel - spot), posicion ('arriba' / 'abajo' / 'en precio' = la zona del spot)
      gex_calls, gex_puts, gex_neto      ($ por 1% de movimiento, signo de la HIPÓTESIS NULA)
      pct_abs                            % de la suma de |gex_neto| de todas las zonas
      dominante                          'calls' o 'puts' (la pata de mayor |gex|)
      signo_supuesto                     '+' / '-' de gex_neto: SUPUESTO, no medido
      neto_publico, signo_medido         solo si se pasa 'medido' (ver abajo)

    medido: Serie opcional strike -> contratos netos del PÚBLICO con regla estricta (compra - venta,
      calls + puts). Sumar calls y puts del mismo strike es válido porque tienen la MISMA gamma (BS).
      Que el público compre (calls o puts) deja al dealer CORTO de gamma => signo_medido = '-'.
      |neto| < min_abs -> 'sin evidencia'. Zona sin flujo -> 'no medido'. Nunca se mezcla con gex_neto.
    """
    c = cadena.dropna(subset=["gex_contrib"]).copy()
    c["zona"] = (c["strike"] / banda).round() * banda
    p = c.pivot_table(index="zona", columns="tipo", values="gex_contrib", aggfunc="sum", fill_value=0.0)
    p = p.reindex(columns=["C", "P"], fill_value=0.0).rename(columns={"C": "gex_calls", "P": "gex_puts"})
    p["gex_neto"] = p["gex_calls"] + p["gex_puts"]
    p = p.reset_index().rename(columns={"zona": "nivel"})

    zona_spot = round(precio_spx / banda) * banda
    p["distancia"] = p["nivel"] - precio_spx
    p["posicion"] = np.where(p["nivel"] == zona_spot, "en precio",
                             np.where(p["nivel"] > precio_spx, "arriba", "abajo"))
    total = p["gex_neto"].abs().sum()
    p["pct_abs"] = p["gex_neto"].abs() / total * 100 if total else np.nan
    p["dominante"] = np.where(p["gex_calls"].abs() >= p["gex_puts"].abs(), "calls", "puts")
    p["signo_supuesto"] = np.where(p["gex_neto"] >= 0, "+", "-")

    cols = ["nivel", "distancia", "posicion", "gex_neto", "pct_abs", "signo_supuesto",
            "dominante", "gex_calls", "gex_puts"]
    if medido is not None:
        m = pd.Series(medido, dtype="float64")
        m = m.groupby((m.index.astype(float) / banda).round() * banda).sum()
        p["neto_publico"] = p["nivel"].map(m)
        p["signo_medido"] = [("no medido" if pd.isna(x) else "sin evidencia" if abs(x) < min_abs
                              else "-" if x > 0 else "+") for x in p["neto_publico"]]
        cols += ["neto_publico", "signo_medido"]

    orden = p["gex_neto"].abs().sort_values(ascending=False).index[:n]
    return p.loc[orden, cols].reset_index(drop=True)