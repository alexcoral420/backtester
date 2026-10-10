"""
Uso:  python scripts/verificar_forward.py 2026-09-24

Mide el forward implícito por vencimiento (paridad call-put en los strikes cercanos al dinero)
y responde tres preguntas. Todo desde la caché. Costo $0. No cambia el proyecto.
  1) ¿El q implícito es razonable (~1-1,5% para el SPX) y estable entre vencimientos?
  2) ¿La dispersión entre strikes es baja? (= el bid/ask de cierre es una foto coherente)
  3) Guarda: ¿cuánto del |GEX| descansa sobre q HEREDADO y no medido?
El forward de diciembre (AM, liquida igual que el ES de diciembre) queda impreso para el cruce con la base ES.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO
from src.black_scholes import calcular_iv, gamma_opcion
from src.datos import precio_spx
from src.forward import forward_por_vencimiento, q_por_opcion
from src.precio_justo import tabla_cierre

fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
S, r = precio_spx(fecha), TASA_LIBRE_RIESGO

c = tabla_cierre(fecha)
c = c[c["T"] > 0].copy()
fw = forward_por_vencimiento(c, S, r)

print(f"=== {fecha} | SPX {S:.2f} | r = {r:.2%} | {len(fw)} vencimientos ===\n")
v = fw.copy()
v["días"] = (v["T"] * 365).round().astype(int)
v["F - S"] = v["forward"] - S
v["carry q %"] = v["q"] * 100
v.index = v.index.strftime("%Y-%m-%d")
pd.set_option("display.width", 200)
print(v[["días", "n_strikes", "forward", "F - S", "dispersion", "carry q %", "origen"]].round(2).to_string())

med = fw[fw["origen"] == "medido"]
print("\n(q = carry implícito: dividendo + diferencia entre la r plana de config y la tasa real del plazo."
      "\n El modelo solo usa r - q, que ES el forward medido: no leer q como dividendo puro.)")
print(f"q medido: mediana {med['q'].median():.2%} | rango {med['q'].min():.2%} a {med['q'].max():.2%}")
print(f"Dispersión entre strikes (pts): mediana {med['dispersion'].median():.2f} | máx {med['dispersion'].max():.2f}")

# ------------------------------------------------------------
# Guarda: peso en |GEX| de las opciones con q heredado (versión C con q)
# ------------------------------------------------------------
c["q"] = q_por_opcion(c, fw)
c["origen"] = c["venc"].map(fw["origen"])
c["iv"] = [calcular_iv(p, S, k, T, r, tp, q) for p, k, T, tp, q in
           zip(c["mid"], c["strike"], c["T"], c["tipo"], c["q"])]
c["gamma"] = [gamma_opcion(S, k, T, r, s, q) for k, T, s, q in zip(c["strike"], c["T"], c["iv"], c["q"])]
c["gex"] = c["gamma"] * c["open_interest"] * np.where(c["tipo"] == "C", 1, -1) * 100 * S**2 * 0.01

abs_tot = c["gex"].abs().sum()
print("\n=== Guarda: ¿sobre qué q descansa el GEX? ===")
for o, g in c.groupby("origen"):
    print(f"  q {o:9s}: {g['gex'].abs().sum() / abs_tot:6.1%} del |GEX| | GEX neto ${g['gex'].sum() / 1e9:+.2f}B")

dic = [x for x in fw.index if x.month == 12 and x.year == pd.to_datetime(fecha).year]
for x in dic:
    print(f"\nForward {x:%Y-%m-%d} (para cruzar con el ES de diciembre): {fw.at[x, 'forward']:.2f} "
          f"| F - S = {fw.at[x, 'forward'] - S:+.2f} pts ({fw.at[x, 'origen']})")