"""
Uso:  python scripts/ver_niveles.py 2026-10-13            (top 12 zonas)
      python scripts/ver_niveles.py 2026-10-13 20         (top 20)
      python scripts/ver_niveles.py 2026-10-13 12 --b2    (+ signo medido de data/b2/flujo_series.csv)

Niveles de gamma por MAGNITUD, sin convención soporte/resistencia (src/gex.niveles_gamma).
Cadena en caché: $0. La lectura (pin, soporte, acelerador) la hace el trader, no la herramienta.

OJO con --b2: el flujo de B2 mezcla vencimientos (oct/nov/dic) con gammas distintas, y su %
indeterminado fue 85-100%. Sirve para ver que casi todo dice 'sin evidencia' o 'no medido', no para operar.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import precio_spx
from src.gex import construir_cadena, gex_total, niveles_gamma

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    raise SystemExit("Uso: python scripts/ver_niveles.py AAAA-MM-DD [N] [--b2]")
fecha, n = args[0], int(args[1]) if len(args) > 1 else 12

medido = None
if "--b2" in sys.argv:
    from src.simbolos import parsear_simbolos
    b2 = pd.read_csv("data/b2/flujo_series.csv")
    b2["strike"] = parsear_simbolos(b2["symbol"])["strike"].values
    medido = b2.groupby("strike")["neto_medido"].sum()

S = precio_spx(fecha)
c = construir_cadena(fecha, S)
v = niveles_gamma(c, S, n=n, medido=medido)
for col in ["gex_neto", "gex_calls", "gex_puts"]:
    v[col] = (v[col] / 1e9).round(2)
v["distancia"] = v["distancia"].round(0).astype(int)
v["pct_abs"] = v["pct_abs"].round(1)
v["nivel"] = v["nivel"].astype(int)

pd.set_option("display.width", 200)
print(f"\n=== {fecha} | SPX {S:.2f} | GEX total ${gex_total(c) / 1e9:+.2f}B | top {n} zonas por |gamma| ===")
print("(gex en $B por 1%; signo_supuesto = HIPÓTESIS NULA, no medido)\n")
print(v.to_string(index=False))
d = v.groupby(["posicion", "signo_supuesto"]).size()
print("\nZonas por posición y signo:", ", ".join(f"{p} {s}: {k}" for (p, s), k in d.items()))