"""
Uso:  python scripts/comparar_precio_justo.py 2026-09-24

¿Cambia el GEX si reemplazamos el "último trade del día" por el punto medio bid/ask al cierre?
Todo desde la caché (statistics + ohlcv de la cadena SPX). Costo $0. No cambia el proyecto.

  A = original: último trade, solo opciones que se negociaron ese día
  B = punto medio bid/ask, MISMAS opciones que A           (A vs B: efecto del PRECIO)
  C = punto medio bid/ask, TODAS las opciones con OI        (B vs C: efecto del OI invisible)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO
from src.black_scholes import calcular_iv, gamma_opcion
from src.datos import precio_spx
from src.gex import gamma_walls
from src.precio_justo import tabla_cierre

fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
S, r = precio_spx(fecha), TASA_LIBRE_RIESGO

c = tabla_cierre(fecha)
c["mid_valido"] = c["mid"].notna()
c = c[c["T"] > 0].copy()

print(f"=== {fecha} | SPX {S:.2f} | {len(c):,} opciones con OI y T > 0 ===\n")

# ------------------------------------------------------------
# 1) Cobertura del punto medio
# ------------------------------------------------------------
oi_tot = c["open_interest"].sum()
inv = ~c["con_trade"]
print("Punto medio válido:")
print(f"  todas:       {c['mid_valido'].mean():.1%} de las opciones | "
      f"{c.loc[c['mid_valido'], 'open_interest'].sum() / oi_tot:.1%} del OI")
print(f"  invisibles:  {c.loc[inv, 'mid_valido'].mean():.1%} de las opciones | "
      f"{c.loc[inv & c['mid_valido'], 'open_interest'].sum() / c.loc[inv, 'open_interest'].sum():.1%} de su OI")

# ------------------------------------------------------------
# 2) ¿Qué tan viejo/sucio es el último trade? (solo opciones con trade y mid válido)
# ------------------------------------------------------------
t = c[c["con_trade"] & c["mid_valido"]]
fuera = (t["ultimo_trade"] < t["bid"]) | (t["ultimo_trade"] > t["ask"])
dif_rel = ((t["ultimo_trade"] - t["mid"]).abs() / t["mid"])
print(f"\nÚltimo trade contra la cotización de cierre ({len(t):,} opciones con trade):")
print(f"  fuera del bid/ask de cierre: {fuera.mean():.1%}  (precio que ya no era negociable al cierre)")
print(f"  diferencia relativa con el punto medio: mediana {dif_rel.median():.1%} | p90 {dif_rel.quantile(0.9):.1%}")

# ------------------------------------------------------------
# 3) IV y GEX de las tres versiones
# ------------------------------------------------------------
def calcular(df, col_precio):
    d = df.copy()
    d["iv"] = [calcular_iv(p, S, k, T, r, tp) for p, k, T, tp in
               zip(d[col_precio], d["strike"], d["T"], d["tipo"])]
    d["gamma"] = [gamma_opcion(S, k, T, r, v) for k, T, v in zip(d["strike"], d["T"], d["iv"])]
    d["signo"] = np.where(d["tipo"] == "C", 1, -1)
    d["gex_contrib"] = d["gamma"] * d["open_interest"] * d["signo"] * 100 * S**2 * 0.01
    return d


A = calcular(c[c["con_trade"]], "ultimo_trade")
B = calcular(c[c["con_trade"]], "mid")
C = calcular(c, "mid")

print("\nIV que no se pudo calcular (nan):")
for nombre, d in [("A ultimo trade", A), ("B mid, mismas", B), ("C mid, todas", C)]:
    print(f"  {nombre:15s}: {d['iv'].isna().sum():5,d} de {len(d):,} ({d['iv'].isna().mean():.1%})")

print("\nGEX total:")
for nombre, d in [("A ultimo trade", A), ("B mid, mismas", B), ("C mid, todas", C)]:
    print(f"  {nombre:15s}: ${d['gex_contrib'].sum() / 1e9:+.2f}B")

gamma_inv = C.loc[~C["con_trade"], "gex_contrib"].abs().sum()
print(f"\nPeso de las invisibles en C, medido en GAMMA: "
      f"{gamma_inv / C['gex_contrib'].abs().sum():.1%} del |GEX|  "
      f"(en contratos eran {c.loc[inv, 'open_interest'].sum() / oi_tot:.1%} del OI)")

# ------------------------------------------------------------
# 4) ¿Cambian los walls?
# ------------------------------------------------------------
print("\n=== Walls (zonas de 25 pts) ===")
for nombre, d in [("A", A), ("B", B), ("C", C)]:
    arriba, abajo = gamma_walls(d.dropna(subset=["gex_contrib"]), S, n=5)
    print(f"{nombre}  arriba: {[int(x) for x in arriba['nivel']]}   abajo: {[int(x) for x in abajo['nivel']]}")