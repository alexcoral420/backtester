"""
signo_walls.py — Paso 1 de "hacer menos supuesta la base": MEDIR el signo en los walls donde el supuesto
más pesa (zona de transición 7700-7775 y walls balanceados como 8000), con SPX+SPXW y calls Y puts.

Es B2/B3 (b2_flujo.py, signo_medido.py) aplicado a las cadenas procesadas de walls_tiempo (data/procesado).
Solo funciones puras: la descarga del tcbbo y la confirmación de costo están en scripts/signo_walls.py.

Emparejamiento (regla de tiempo de inventario.py): el ΔOI del archivo de d se explica con el flujo del día
de mercado anterior. Cada par es (opción, día de flujo):
  - ΔOI solo de opciones vivas en los dos archivos o nuevas (una que vence no es una posición cerrada).
  - Si entre los dos archivos hay MÁS de una sesión (hueco, p. ej. 10-20 sin datos), el par queda
    marcado 'hueco' y no recibe veredicto: el flujo de una sola sesión no explica el ΔOI de dos.
  - Trades de una opción en un día sin par (p. ej. el día que vence) no se cuentan.
El veredicto es el de signo_medido.veredicto, por tipo, contra HIPOTESIS_NULA_PUBLICO de ese tipo.
Nada de esto se fusiona con el GEX: el signo medido queda en columnas propias, al lado del supuesto.
"""
import pandas as pd

from src.signo_medido import pct_delta_indet, veredicto

UMBRAL_COBERTURA = 0.80     # por zona y tipo: series que cubren el 80% del |ΔOI| de la ventana (como b2 nivel 3)


def pares_doi(cadenas, mercado, banda=25):
    """cadenas: {fecha: cadena con symbol, tipo, strike, open_interest}. mercado: días de mercado reales.
    Una fila por (symbol, día de flujo) con: fecha (archivo), dia_flujo, sesiones, zona, tipo, doi."""
    mercado = sorted(pd.to_datetime(list(mercado)))
    fechas = sorted(cadenas)
    filas = []
    for previa, f in zip(fechas, fechas[1:]):
        a = cadenas[previa].set_index("symbol")["open_interest"]
        h = cadenas[f].set_index("symbol")
        p = pd.DataFrame({"tipo": h["tipo"], "zona": (h["strike"] / banda).round() * banda,
                          "doi": h["open_interest"] - a.reindex(h.index).fillna(0.0)})
        p["fecha"] = pd.Timestamp(f)
        p["dia_flujo"] = pd.Timestamp(previa)
        p["sesiones"] = mercado.index(pd.Timestamp(f)) - mercado.index(pd.Timestamp(previa))
        filas.append(p.reset_index())
    return pd.concat(filas, ignore_index=True)


def elegir_series(pares, zonas, cobertura=UMBRAL_COBERTURA):
    """Por zona y tipo, las series que juntas cubren `cobertura` del |ΔOI| de la ventana (sin pares con hueco).
    Devuelve {symbol: (zona, tipo)}."""
    p = pares[pares["zona"].isin(zonas) & (pares["sesiones"] == 1)]
    elegidas = {}
    for (z, t), g in p.groupby(["zona", "tipo"]):
        s = g.groupby("symbol")["doi"].apply(lambda x: x.abs().sum()).sort_values(ascending=False)
        s = s[s > 0]
        if s.empty:
            continue
        for sym in s[(s.cumsum() / s.sum()).shift(fill_value=0) < cobertura].index:
            elegidas[sym] = (z, t)
    return elegidas


def flujo_por_dia(trades):
    """trades clasificados con regla ESTRICTA (clasificacion.clasificar_trades(estricto=True)) y columna 'dia'.
    Una fila por (symbol, dia_flujo): compra, venta, indet, complejo (contratos), total y neto (compra - venta)."""
    t = trades.assign(estado=trades["signo"].map({1: "compra", -1: "venta", 0: "indet"}),
                      size=trades["size"].astype("int64"))
    f = t.pivot_table(index=["symbol", "dia"], columns="estado", values="size", aggfunc="sum", fill_value=0)
    f = f.reindex(columns=["compra", "venta", "indet"], fill_value=0)
    f["complejo"] = t[t["complejo"]].groupby(["symbol", "dia"])["size"].sum()
    f = f.fillna(0).astype("int64")
    f["total"] = f[["compra", "venta", "indet"]].sum(axis=1)
    f["neto"] = f["compra"] - f["venta"]
    f.index = f.index.set_names(["symbol", "dia_flujo"])
    return f.reset_index()


def comparar(pares, flujo, elegidas, accion_supuesta):
    """Por zona y tipo: ΔOI de las series elegidas (sin huecos) frente al neto medido del día de flujo de cada par.
    accion_supuesta: {'C': 'vende', 'P': 'compra'} (HIPOTESIS_NULA_PUBLICO).
    Columnas: series, pares, delta_oi, compra, venta, indet, complejo, pct_indet, neto_medido,
    pct_delta_indet, veredicto, y pares_hueco (pares excluidos por hueco)."""
    p = pares[pares["symbol"].isin(list(elegidas))].copy()
    hueco = p[p["sesiones"] != 1].groupby(["zona", "tipo"]).size()
    p = p[p["sesiones"] == 1].merge(flujo, on=["symbol", "dia_flujo"], how="left")
    cols = ["compra", "venta", "indet", "complejo", "total", "neto"]
    p[cols] = p[cols].fillna(0)
    r = p.groupby(["zona", "tipo"]).agg(series=("symbol", "nunique"), pares=("symbol", "size"),
                                         delta_oi=("doi", "sum"), compra=("compra", "sum"),
                                         venta=("venta", "sum"), indet=("indet", "sum"),
                                         complejo=("complejo", "sum"), total=("total", "sum"),
                                         neto_medido=("neto", "sum"))
    r["pct_indet"] = (r["indet"] / r["total"] * 100).where(r["total"] > 0)
    r["pct_delta_indet"] = [pct_delta_indet(n, d) for n, d in zip(r["neto_medido"], r["delta_oi"])]
    r["accion_supuesta"] = [accion_supuesta[t] for _, t in r.index]
    r["veredicto"] = [veredicto(n, d, a) for n, d, a in zip(r["neto_medido"], r["delta_oi"], r["accion_supuesta"])]
    r["pares_hueco"] = hueco.reindex(r.index).fillna(0).astype("int64")
    return r.drop(columns="total")
