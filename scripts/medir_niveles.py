"""
Uso:  python scripts/medir_niveles.py 2026-10-14          (top 12 zonas de ver_niveles)
      python scripts/medir_niveles.py 2026-10-14 8

Signo MEDIDO (sin hipótesis nula) de los niveles de gamma del mapa, con el flujo de ESE día.
  1. Toma las top N zonas de niveles_gamma (cadena del día, ya en caché).
  2. En cada zona elige las series que suman el 80% de su |gamma| (no todas: costo).
  3. get_cost del tcbbo de esas series ese día -> UNA confirmación -> descarga y caché.
  4. Regla ESTRICTA (ask = compra, bid = venta, resto indeterminado, no se reparte).

Por zona, lado a lado y SIN fusionar:
  gex_supuesto     gamma de TODO el OI con el signo de la hipótesis nula ($B por 1%)
  gex_flujo_medido gamma que el dealer TOMÓ ese día por el flujo con signo medido
                   (público compra -> dealer corto -> gamma -). Mismas unidades.
  % cubierto       |gex_flujo_medido| / gamma BRUTA de la zona: cuánto del nivel dice algo medido.
El resto del OI (posiciones de días anteriores) sigue con signo SUPUESTO: la medición de un día
solo describe el cambio de ese día, no el inventario.
Nota de tiempo: el flujo del día d cambia el OI que aparece en el archivo de d+1 (regla confirmada).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import precio_spx
from src.gex import construir_cadena, niveles_gamma
from src.odte.clasificacion import clasificar_trades
from src.odte.trades import asegurar_tcbbo, leer_tcbbo
from src.signo_medido import MIN_ABS

DESDE, HASTA, BANDA, CUBRIR = "09:30", "16:15", 25, 0.80

if len(sys.argv) < 2:
    raise SystemExit("Uso: python scripts/medir_niveles.py AAAA-MM-DD [N]")
fecha, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 12

S = precio_spx(fecha)
c = construir_cadena(fecha, S).dropna(subset=["gex_contrib"])
c = c[c["open_interest"] > 0].copy()
c["zona"] = (c["strike"] / BANDA).round() * BANDA
niv = niveles_gamma(c, S, n=n, banda=BANDA)

# ---------------- series que explican el 80% de la |gamma| de cada zona ----------------
sel = []
for z in niv["nivel"]:
    g = c[c["zona"] == z].assign(a=lambda x: x["gex_contrib"].abs()).sort_values("a", ascending=False)
    sel.append(g[(g["a"].cumsum() / g["a"].sum()).shift(fill_value=0) < CUBRIR])
sel = pd.concat(sel)
simbolos = sorted(sel["symbol"].unique())
print(f"{fecha} | SPX {S:.2f} | {len(niv)} zonas | {len(simbolos)} series (80% de la |gamma| de cada zona)")

# ---------------- costo y descarga con UNA confirmación ----------------
asegurar_tcbbo({fecha: simbolos}, DESDE, HASTA)

tr = clasificar_trades(leer_tcbbo(fecha, simbolos, DESDE, HASTA), estricto=True)
tr["size"] = tr["size"].astype("int64")

# ---------------- por serie: neto medido y la gamma que tomó el dealer ----------------
f = tr.assign(c=np.where(tr["signo"] == 1, tr["size"], 0), v=np.where(tr["signo"] == -1, tr["size"], 0),
              i=np.where(tr["signo"] == 0, tr["size"], 0)).groupby("symbol")[["c", "v", "i"]].sum()
s = sel.set_index("symbol")[["zona", "tipo", "gamma", "open_interest"]].join(f).fillna({"c": 0, "v": 0, "i": 0})
s["neto"] = s["c"] - s["v"]                                       # + = el público compró
s["gex_flujo"] = -s["neto"] * s["gamma"] * 100 * S ** 2 * 0.01    # dealer: signo contrario

z = s.groupby("zona").agg(series=("tipo", "size"), oi=("open_interest", "sum"), compra=("c", "sum"),
                          venta=("v", "sum"), indet=("i", "sum"), neto=("neto", "sum"),
                          gex_flujo=("gex_flujo", "sum"))
r = niv.set_index("nivel").join(z)
r["bruto"] = r["gex_calls"].abs() + r["gex_puts"].abs()
r["% vol indet"] = (r["indet"] / (r["compra"] + r["venta"] + r["indet"]) * 100).round(0)
r["% cubierto"] = (r["gex_flujo"].abs() / r["bruto"] * 100).round(2)
r["signo_medido"] = ["sin evidencia" if abs(x) < MIN_ABS else ("-" if x > 0 else "+") for x in r["neto"]]

out = r.reset_index()[["nivel", "posicion", "gex_neto", "signo_supuesto", "series", "oi", "neto",
                       "% vol indet", "gex_flujo", "signo_medido", "% cubierto"]]
out["nivel"] = out["nivel"].astype(int)
out["gex_neto"] = (out["gex_neto"] / 1e9).round(2)
out["gex_flujo"] = (out["gex_flujo"] / 1e9).round(3)
out = out.rename(columns={"gex_neto": "gex_supuesto $B", "gex_flujo": "gex_flujo_medido $B",
                          "neto": "neto_publico"})
pd.set_option("display.width", 220)
print(f"\n=== {fecha}: signo SUPUESTO (todo el OI) vs MEDIDO (flujo del día) por nivel ===")
print("(neto_publico + = el público compró -> dealer corto -> signo medido '-')\n")
print(out.to_string(index=False))
print(f"\nVolumen total: {tr['size'].sum():,} | indeterminado "
      f"{tr.loc[tr['signo'] == 0, 'size'].sum() / tr['size'].sum():.0%} | "
      f"complejo {tr.loc[tr['complejo'], 'size'].sum() / tr['size'].sum():.0%}")
coinc = (out["signo_medido"] == out["signo_supuesto"]).sum()
med = (out["signo_medido"] != "sin evidencia").sum()
print(f"Zonas con signo medido: {med} de {len(out)} | coinciden con la nula: {coinc} de {med}")