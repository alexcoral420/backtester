"""
Uso:  python scripts/odte/validar_carga.py 2026-09-25 2026-11-06 --sin 2026-10-20
Opciones de definición del toque (ODTE.md, M2): --paso 25 --tol 2 --desde 10:00 --ventana 30 --margen 5

M4 de ODTE.md ("Diseño fijo de M4"): ¿un nivel con más carga (OI, sin signo) aguanta más el toque?
Por día d, cada múltiplo de 25 que el SPX TOCÓ (src/odte/toques.py, SPX = ES - base MÓVIL) con la carga de su
zona conocida antes de la apertura (src/odte/carga.py):
  MEDIDO   oi_c, oi_p, oi_total, pct_puts, pct_carga_oi      (foto procesada de d: OI al cierre de d-1)
  MODELO   gex_bruto, pct_carga_bruto                         (foto de d-1, sin lo que vence en d)
  SUPUESTO gex_sup, es_wall_sup                               (foto de d-1, signo de la hipótesis nula)

$0, SOLO CACHÉ: nunca descarga ni cotiza. Un día al que le falte la foto de d, la de d-1, el ES 1-min o el
SPX 5m de yfinance se salta y se lista. d1_vieja = la foto previa no es la del día de mercado anterior
(p. ej. 10-21, cuya previa es la del 10-19).

Acumulador: data/validacion/odte_carga.csv (separado de odte_toques.csv y de los CSV de GEX). Cada corrida
reemplaza las filas de sus (fecha, definición). Análisis: python scripts/odte/analizar_carga.py
"""
import argparse
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.carga import carga_dia, unir
from src.odte.precio import ruta_es, ruta_spx_yf, spx_1min
from src.odte.toques import Definicion, toques

RUTA_ACUM = "data/validacion/odte_carga.csv"
PROCESADO = "data/procesado/cadena_SPX+SPXW_horas_{}.parquet"

ap = argparse.ArgumentParser(description="M4: carga sin signo de las zonas tocadas")
ap.add_argument("inicio")
ap.add_argument("fin")
ap.add_argument("--sin", default="", help="fechas a saltar, separadas por coma (sin datos en Databento)")
ap.add_argument("--paso", type=int, default=Definicion.paso)
ap.add_argument("--tol", type=float, default=Definicion.tolerancia)
ap.add_argument("--desde", default=Definicion.desde)
ap.add_argument("--ventana", type=int, default=Definicion.ventana_min)
ap.add_argument("--margen", type=float, default=Definicion.margen)
a = ap.parse_args()
d = Definicion(a.paso, a.tol, a.desde, a.ventana, a.margen)
if d.paso != 25:
    raise SystemExit("M4 usa zonas de 25: con otro paso los toques no coinciden con las zonas de carga")

# Días de mercado reales (para d1_vieja), desde una semana antes para conocer el anterior al primero
desde = (pd.Timestamp(a.inicio) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
hist = yf.Ticker("^GSPC").history(start=desde, end=(pd.Timestamp(a.fin) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
mercado = [x.strftime("%Y-%m-%d") for x in hist.index.tz_localize(None).normalize()]
saltar = {s for s in a.sin.split(",") if s}
fechas = [f for f in mercado if a.inicio <= f <= a.fin and f not in saltar]
if not fechas:
    raise SystemExit(f"Sin días de mercado entre {a.inicio} y {a.fin}")

fotos = {f for f in mercado if os.path.exists(PROCESADO.format(f))}
filas, saltados = [], {}
for f in fechas:
    previas = sorted(x for x in fotos if x < f)
    falta = [n for n, ok in (("foto d", f in fotos), ("foto d-1", bool(previas)), ("ES", os.path.exists(ruta_es(f))),
                             ("SPX 5m", os.path.exists(ruta_spx_yf(f, "5m")))) if not ok]
    if falta:
        saltados[f] = falta
        continue
    previa = previas[-1]
    anterior = mercado[mercado.index(f) - 1]
    foto_d, foto_p = pd.read_parquet(PROCESADO.format(f)), pd.read_parquet(PROCESADO.format(previa))
    S_previo = float(foto_p["S"].iloc[0])
    z = carga_dia(foto_d, foto_p, f, S_previo)

    spx, _ = spx_1min(f, metodo_base="movil")
    tq = toques(spx["spx"], d)
    if tq.empty:
        continue
    r = unir(tq, z)
    r.insert(0, "fecha", f)
    r.insert(1, "definicion", d.etiqueta())
    r["t_toque"] = r["t_toque"].dt.strftime("%H:%M")
    r["S_previo"] = S_previo
    r["dist_cierre_previo"] = r["strike"] - S_previo
    r["d1_vieja"] = previa != anterior
    filas.append(r)

if saltados:
    print(f"[solo caché] días saltados: {saltados}", file=sys.stderr)
if not filas:
    raise SystemExit("Ningún día con toques: nada que acumular.")
t = pd.concat(filas, ignore_index=True)
medidos = sorted(t["fecha"].unique())

os.makedirs(os.path.dirname(RUTA_ACUM), exist_ok=True)
acum = pd.read_csv(RUTA_ACUM, dtype={"fecha": str}) if os.path.exists(RUTA_ACUM) else pd.DataFrame()
if len(acum):
    acum = acum[~((acum["definicion"] == d.etiqueta()) & acum["fecha"].isin(fechas))]
acum = pd.concat([acum, t], ignore_index=True).sort_values(["definicion", "fecha", "strike"])
acum.to_csv(RUTA_ACUM, index=False)
print(f"[acumulado] {len(t)} toques de {len(medidos)} días en {RUTA_ACUM} (total {len(acum)}). "
      f"Análisis: python scripts/odte/analizar_carga.py", file=sys.stderr)

pd.set_option("display.width", 250)
print(f"=== M4 | toques {a.inicio} a {a.fin} | definición {d.etiqueta()} | SPX = ES - base móvil ===")
print("(oi_total y pct_carga_oi MEDIDOS; gex_bruto y pct_carga_bruto MODELO; gex_sup y es_wall_sup SUPUESTOS)")
v = t.assign(oi_k=t["oi_total"] / 1e3, bruto_B=t["gex_bruto"] / 1e9, sup_B_SUPUESTO=t["gex_sup"] / 1e9,
             wall_SUPUESTO=t["es_wall_sup"])
print(v[["fecha", "strike", "clase", "t_toque", "lado", "resultado", "peor_exceso", "oi_k", "pct_carga_oi",
         "bruto_B", "pct_carga_bruto", "sup_B_SUPUESTO", "wall_SUPUESTO", "fuera_radio", "d1_vieja"]]
      .round(1).to_string(index=False))
print(f"\nResultado: {t['resultado'].value_counts().to_dict()}")
