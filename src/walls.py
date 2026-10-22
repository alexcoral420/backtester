"""
walls.py — Evolución de los walls en el tiempo: cuán CARGADOS están y POR QUÉ cambia su GEX.

Por opción, k = gex_contrib / OI = gamma · 100 · S² · 0,01 · signo   ($ de GEX por contrato; gamma nan -> 0)
Entre dos fotos de la cadena (ayer, hoy), el cambio de GEX se parte en tres, y la suma es EXACTA:
  posicionamiento = (OI_hoy - OI_ayer) · k_hoy     contratos abiertos/cerrados (opción nueva: OI_ayer = 0)
  mercado         = OI_ayer · (k_hoy - k_ayer)     mismo OI revaluado: precio, tiempo e IV
  vencidas        = - OI_ayer · k_ayer             estaban ayer y ya no (vencieron)
El ΔOI de posicionamiento NO incluye las vencidas: un vencimiento no es una posición cerrada.

Qué es medido y qué supuesto:
  OI, ΔOI y % de puts           MEDIDOS (sin signo)
  gex, posicionamiento, mercado  usan el signo SUPUESTO (hipótesis nula de gex.py)
Regla de tiempo (inventario.py): el OI del archivo de d es el del cierre de d-1 -> su ΔOI es el flujo de d-1.
"""
import pandas as pd

from src.simbolos import TRAMOS_PLAZO

BANDA = 25
CAMBIOS = ["doi_c", "doi_p", "oi_venc", "pos", "mer", "ven"]

# CONTRATO medido / supuesto: toda columna de datos que sale de este módulo está en UNA de las dos listas
# (lo verifica tests/test_walls.py). Quien muestre estos números (app/, scripts/) elige el estilo y la
# etiqueta según la lista, nunca a mano.
MEDIDAS = ["S", "oi_c", "oi_p", "pct_puts", "doi_c", "doi_p", "oi_venc"]      # sin signo: datos
SUPUESTAS = ["gex", "pos", "mer", "ven"]        # usan el signo de HIPOTESIS_NULA_PUBLICO (gex.py)
CLAVES = ["fecha", "zona", "raiz", "tramo"]     # identifican la fila, no son mediciones


def es_supuesta(columna):
    """True si la columna depende del signo supuesto; ValueError si no está clasificada (grita)."""
    if columna in SUPUESTAS:
        return True
    if columna in MEDIDAS:
        return False
    raise ValueError(f"Columna sin clasificar en el contrato medido/supuesto: {columna!r}")


def _preparar(cadena, banda):
    c = cadena.set_index("symbol") if "symbol" in cadena.columns else cadena
    c = c.copy()
    c["k"] = (c["gex_contrib"] / c["open_interest"]).where(c["open_interest"] > 0).fillna(0.0)
    c["zona"] = (c["strike"] / banda).round() * banda
    return c


def descomponer(ayer, hoy, banda=BANDA):
    """Una fila por opción (vivas hoy + vencidas desde ayer) con zona, tipo y las columnas
    pos, mer, ven ($), doi (contratos, sin vencidas) y oi_venc (contratos que vencieron)."""
    a, h = _preparar(ayer, banda), _preparar(hoy, banda)
    oi_ayer = a["open_interest"].reindex(h.index).fillna(0.0)
    k_ayer = a["k"].reindex(h.index).fillna(0.0)
    vivas = pd.DataFrame({"zona": h["zona"], "tipo": h["tipo"]})
    vivas["doi"] = h["open_interest"] - oi_ayer
    vivas["pos"] = vivas["doi"] * h["k"]
    vivas["mer"] = oi_ayer * (h["k"] - k_ayer)
    vivas["ven"] = vivas["oi_venc"] = 0.0

    idas = a.index.difference(h.index)
    vencidas = pd.DataFrame({"zona": a.loc[idas, "zona"], "tipo": a.loc[idas, "tipo"]})
    vencidas["doi"] = vencidas["pos"] = vencidas["mer"] = 0.0
    vencidas["ven"] = -(a.loc[idas, "open_interest"] * a.loc[idas, "k"])
    vencidas["oi_venc"] = a.loc[idas, "open_interest"]
    return pd.concat([vivas, vencidas])


def zonas_dia(cadena, banda=BANDA):
    """Por zona: oi_c, oi_p (contratos), gex ($) y pct_puts (% del OI que es put)."""
    c = _preparar(cadena, banda)
    z = c.pivot_table(index="zona", columns="tipo", values="open_interest", aggfunc="sum", fill_value=0).astype(float)
    z = z.reindex(columns=["C", "P"], fill_value=0.0).rename(columns={"C": "oi_c", "P": "oi_p"})
    z["gex"] = c.groupby("zona")["gex_contrib"].sum()
    total = z["oi_c"] + z["oi_p"]
    z["pct_puts"] = (z["oi_p"] / total * 100).where(total > 0)
    return z


def zonas_por_tramo(cadena, banda=BANDA):
    """Como zonas_dia, pero partido por raíz y tramo de plazo (simbolos.TRAMOS_PLAZO).
    Una fila por (zona, raiz, tramo) con oi_c, oi_p y gex. Para filtrar el perfil de un día."""
    c = _preparar(cadena, banda)
    bordes, nombres = TRAMOS_PLAZO
    c["tramo"] = pd.cut(c["dte"], bordes, labels=nombres).astype(str)
    c["oi_c"] = c["open_interest"].where(c["tipo"] == "C", 0.0)
    c["oi_p"] = c["open_interest"].where(c["tipo"] == "P", 0.0)
    return (c.groupby(["zona", "raiz", "tramo"], as_index=False)
            .agg(oi_c=("oi_c", "sum"), oi_p=("oi_p", "sum"), gex=("gex_contrib", "sum")))


def evolucion(cadenas, banda=BANDA):
    """cadenas: {fecha: cadena de construir_cadena (con columna S)}, en orden de fecha.
    Devuelve (dias, zonas):
      dias:  por fecha, S, gex y la descomposición del cambio contra la fecha anterior (pos, mer, ven)
      zonas: por fecha y zona, oi_c, oi_p, pct_puts, gex, y contra la fecha anterior doi_c, doi_p,
             oi_venc, pos, mer, ven (nan el primer día)."""
    fechas = sorted(cadenas)
    filas_dia, filas_zona = [], []
    for i, f in enumerate(fechas):
        hoy = cadenas[f]
        z = zonas_dia(hoy, banda)
        d = dict(fecha=f, S=float(hoy["S"].iloc[0]), gex=hoy["gex_contrib"].sum())
        if i > 0:
            p = descomponer(cadenas[fechas[i - 1]], hoy, banda)
            g = p.groupby("zona")[["pos", "mer", "ven", "oi_venc"]].sum()
            for t in "CP":
                g["doi_" + t.lower()] = p[p["tipo"] == t].groupby("zona")["doi"].sum()
            z = z.join(g, how="outer")
            d.update(p[["pos", "mer", "ven"]].sum().to_dict())
        z["fecha"] = f
        filas_zona.append(z.reset_index())
        filas_dia.append(d)
    zonas = pd.concat(filas_zona, ignore_index=True).reindex(
        columns=["fecha", "zona", "oi_c", "oi_p", "pct_puts", "gex"] + CAMBIOS)
    zonas[["oi_c", "oi_p"]] = zonas[["oi_c", "oi_p"]].fillna(0.0)       # zona que solo tenía vencidas
    no_primero = zonas["fecha"] != fechas[0]                            # el primer día no tiene contra qué
    zonas.loc[no_primero, CAMBIOS] = zonas.loc[no_primero, CAMBIOS].fillna(0.0)
    return pd.DataFrame(filas_dia).set_index("fecha"), zonas
