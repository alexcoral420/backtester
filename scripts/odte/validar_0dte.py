"""
Uso:  python scripts/odte/validar_0dte.py 2026-09-29 2026-10-19 --solo-cache        ($0: solo días ya en caché)
      python scripts/odte/validar_0dte.py 2026-09-29 2026-11-03 --solo-costo        (cotiza, no descarga)
      python scripts/odte/validar_0dte.py 2026-09-29 2026-11-03 --sin 2026-10-20    (descarga lo que falte)
Opciones de definición (ODTE.md, "M2: definiciones"): --paso 25 --tol 2 --desde 10:00 --ventana 30 --margen 5

M2 de ODTE.md: de días sueltos a una muestra. Por día, cada strike múltiplo de `paso` que el precio TOCÓ
(src/odte/toques.py): ¿aguantó o se cruzó en los `ventana` minutos siguientes?, y el flujo ESTRICTO del
público en ese strike (calls + puts) desde la apertura hasta ANTES del toque, con el veredicto de
src/odte/veredicto.py (peor caso contra lo indeterminado) y su % indeterminado al lado.

Descargas (patrón único de datos.py), como mucho DOS confirmaciones para todo el rango:
  1) catálogo (definition) + ES 1-min de los días que falten           (centavos por día)
  2) tcbbo SOLO de los strikes tocados (se saben recién con el ES)      (lo caro)
--solo-cache: no cotiza ni descarga nada; salta (y lista) los días a los que les falte algo.

M2 está CERRADA (ODTE.md): con la regla de cotización el signo del agresor no es identificable
(|neto| / indet ~0,04 antes del toque). NO se recomienda pagar tcbbo para ampliar esta muestra: solo
confirmaría el "sin evidencia". El lado del precio (src/odte/toques.py) sigue siendo la base de M4.

Acumulador: data/validacion/odte_toques.csv (separado de los de GEX). Cada corrida reemplaza las filas
de sus (fecha, definición). Análisis conjunto, $0: python scripts/odte/analizar_odte.py
"""
import argparse
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src import datos
from src.odte.catalogo import pedidos_definicion, ruta_definicion, seleccionar_0dte
from src.odte.clasificacion import clasificar_trades
from src.odte.precio import pedidos_es, ruta_es, spx_1min
from src.odte.toques import Definicion, flujo_previo, toques
from src.odte.trades import asegurar_tcbbo, leer_tcbbo, plan_tcbbo

RUTA_ACUM = "data/validacion/odte_toques.csv"

ap = argparse.ArgumentParser(description="Muestra 0DTE: toques de strikes y flujo previo (M2)")
ap.add_argument("inicio")
ap.add_argument("fin")
ap.add_argument("--sin", default="", help="fechas a saltar, separadas por coma (sin datos en Databento)")
ap.add_argument("--solo-cache", action="store_true")
ap.add_argument("--solo-costo", action="store_true")
ap.add_argument("--paso", type=int, default=Definicion.paso)
ap.add_argument("--tol", type=float, default=Definicion.tolerancia)
ap.add_argument("--desde", default=Definicion.desde)
ap.add_argument("--ventana", type=int, default=Definicion.ventana_min)
ap.add_argument("--margen", type=float, default=Definicion.margen)
a = ap.parse_args()
if a.solo_cache and a.solo_costo:
    raise SystemExit("--solo-cache y --solo-costo no van juntos")
d = Definicion(a.paso, a.tol, a.desde, a.ventana, a.margen)

# Días de mercado (yfinance salta feriados y fines de semana), menos los pedidos con --sin
hist = yf.Ticker("^GSPC").history(start=a.inicio, end=(pd.Timestamp(a.fin) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
saltar = {s for s in a.sin.split(",") if s}
fechas = [x.strftime("%Y-%m-%d") for x in hist.index.tz_localize(None).normalize()
          if x.strftime("%Y-%m-%d") not in saltar]
if not fechas:
    raise SystemExit(f"Sin días de mercado entre {a.inicio} y {a.fin}")

# Paso 1: catálogo + ES (UNA confirmación)
if a.solo_cache:
    sin_base = [f for f in fechas if not (os.path.exists(ruta_es(f)) and os.path.exists(ruta_definicion(f)))]
    fechas = [f for f in fechas if f not in sin_base]
else:
    sin_base = []
    costo = datos.asegurar_descargas(pedidos_definicion(fechas) + pedidos_es(fechas),
                                     f"0DTE catálogo + ES, {len(fechas)} días", solo_costo=a.solo_costo)
    if a.solo_costo and costo > 0:
        print(f"Paso 1 (catálogo + ES): ${costo:.4f}. El tcbbo se cotiza recién con el ES en caché "
              f"(los strikes tocados salen del precio): bajar el paso 1 y volver a correr --solo-costo.")
        raise SystemExit(0)

# Toques por día (solo precio) y los símbolos 0DTE de los strikes tocados
dias, simbolos, catalogos = {}, {}, {}
for f in fechas:
    spx, _ = spx_1min(f)
    tq = toques(spx["spx"], d)
    if tq.empty:
        dias[f], simbolos[f] = tq, []
        continue
    sel = seleccionar_0dte(f, tq["strike"].min(), tq["strike"].max())
    sel = sel[sel["strike_price"].isin(tq["strike"])]
    sin_serie = sorted(set(tq["strike"]) - set(sel["strike_price"]))
    if sin_serie:
        raise RuntimeError(f"{f}: strikes tocados sin serie 0DTE en el catálogo: {sin_serie}")
    dias[f], simbolos[f], catalogos[f] = tq, sel["raw_symbol"].tolist(), sel

# Paso 2: tcbbo de los strikes tocados (UNA confirmación)
sin_tcbbo = []
if a.solo_cache:
    sin_tcbbo = [f for f in fechas if simbolos[f] and plan_tcbbo(f, simbolos[f])[1]]
else:
    costo = asegurar_tcbbo({f: s for f, s in simbolos.items() if s}, solo_costo=a.solo_costo)
    if a.solo_costo:
        print(f"Paso 2 (tcbbo de {sum(len(s) for s in simbolos.values())} series en {len(fechas)} días): "
              f"${costo:.4f} pendiente. No se descargó nada.")
        raise SystemExit(0)

# Medición
filas = []
for f in fechas:
    if f in sin_tcbbo:
        continue
    tq = dias[f]
    if tq.empty:
        continue
    tr = leer_tcbbo(f, simbolos[f]).reset_index()
    tr = tr.merge(catalogos[f][["raw_symbol", "instrument_class", "strike_price"]],
                  left_on="symbol", right_on="raw_symbol", how="left")
    if tr["strike_price"].isna().any():
        raise RuntimeError(f"{f}: trades con símbolo fuera del catálogo")
    tr = clasificar_trades(tr, estricto=True)
    r = flujo_previo(tq, tr)
    r.insert(0, "fecha", f)
    r.insert(1, "definicion", d.etiqueta())
    r["min_antes"] = ((r["t_toque"] - r["t_toque"].dt.normalize()).dt.total_seconds() // 60 - 570).astype(int)
    r["t_toque"] = r["t_toque"].dt.strftime("%H:%M")
    filas.append(r)

if sin_base or sin_tcbbo:
    print(f"[solo caché] días saltados: sin catálogo/ES {sin_base or '-'} | sin tcbbo de los strikes "
          f"tocados {sin_tcbbo or '-'}")
medidos = [f for f in fechas if f not in sin_tcbbo]
if not filas:
    raise SystemExit("Ningún día con toques medidos: nada que acumular.")
t = pd.concat(filas, ignore_index=True)

# Acumulador: reemplaza las filas de los (fecha, definición) medidos en esta corrida
os.makedirs(os.path.dirname(RUTA_ACUM), exist_ok=True)
acum = pd.read_csv(RUTA_ACUM, dtype={"fecha": str}) if os.path.exists(RUTA_ACUM) else pd.DataFrame()
if len(acum):
    acum = acum[~((acum["definicion"] == d.etiqueta()) & acum["fecha"].isin(medidos))]
acum = pd.concat([acum, t], ignore_index=True).sort_values(["definicion", "fecha", "strike"])
acum.to_csv(RUTA_ACUM, index=False)
print(f"[acumulado] {len(t)} toques de {t['fecha'].nunique()} días en {RUTA_ACUM} "
      f"(total {len(acum)}). Análisis: python scripts/odte/analizar_odte.py")

pd.set_option("display.width", 220)
print(f"\n=== Toques 0DTE | {a.inicio} a {a.fin} | definición {d.etiqueta()} ===")
print("(flujo ESTRICTO del público ANTES del toque, calls + puts; neto + = el público compró |")
print(" dealer_medido: + largo de gamma, - corto, o por qué no hay signo; MEDIDO, sin hipótesis nula)\n")
print(t[["fecha", "strike", "t_toque", "lado", "dist_previa", "peor_exceso", "resultado", "neto",
         "neto_calls", "neto_puts", "pct_indet", "dealer_medido"]].round(1).to_string(index=False))
print(f"\nResultado: {t['resultado'].value_counts().to_dict()}")
print(f"Signo del dealer medido: {t['dealer_medido'].value_counts().to_dict()}")
