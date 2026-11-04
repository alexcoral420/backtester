"""
Uso:  python scripts/b2_flujo.py 2026-09-24 2026-10-08

Fase B2: dirección del ΔOI con la regla ESTRICTA, en las series de costo_b2 (niveles 1, 2 y 3).
Descarga el tcbbo con UNA confirmación de costo (las series y días que falten en caché).

Reglas (15-oct):
  - Tres estados, nunca dos: compra confirmada (precio == ask), venta confirmada (== bid),
    indeterminado (interior del spread o paquete fuera del bid/ask). El indeterminado NO se reparte.
  - Regla de tiempo: el ΔOI del archivo de d se compara con el flujo de d-1.
  - Veredicto: src/signo_medido.py (mínimo absoluto 200 contratos y relativo 20% del ΔOI).
  - Las dos fuentes quedan SEPARADAS: el signo supuesto (hipótesis nula) y el flujo medido, lado a lado,
    con un veredicto: confirma / contradice / demasiado chico para opinar. NO se fusionan en un GEX.
  - Test de verticales: trades en patas vecinas en el MISMO segundo y con el mismo tamaño = paquete.
"""
import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import CARPETA_CACHE, ruta_cadena
from src.gex import HIPOTESIS_NULA_PUBLICO
from src.inventario import delta_oi, fecha_flujo, oi_por_fecha
from src.odte.clasificacion import clasificar_trades
from src.odte.trades import asegurar_tcbbo, ruta_cache_tcbbo
from src.signo_medido import veredicto

DESDE, HASTA = "09:30", "16:15"
NIVEL1 = {"strikes": [7650, 7600, 7500, 7400], "vencs": ["2026-10-16", "2026-11-20", "2026-12-18"]}
NIVEL2 = [(7795, 7805), (7845, 7855)]
NIVEL3_ZONAS = [7900, 7850, 7800]
VENC_N2 = "2026-12-18"

if len(sys.argv) < 3:
    raise SystemExit("Uso: python scripts/b2_flujo.py INICIO FIN   (desde la raíz del proyecto)")
inicio, fin = pd.to_datetime(sys.argv[1]), pd.to_datetime(sys.argv[2])
fechas = sorted(os.path.basename(p)[-18:-8] for p in glob.glob(os.path.join(CARPETA_CACHE, "cadena_SPX_statistics_*.parquet")))
fechas = [f for f in fechas if inicio <= pd.to_datetime(f) <= fin and os.path.exists(ruta_cadena("SPX", "ohlcv-1d", f))]
dias = sorted({fecha_flujo(f, fechas).strftime("%Y-%m-%d") for f in fechas[1:]})

# ---------------- las series (misma selección que costo_b2) ----------------
t = delta_oi(oi_por_fecha(fechas))
t["dia_flujo"] = [fecha_flujo(f, fechas).strftime("%Y-%m-%d") if f > pd.to_datetime(fechas[0]) else None
                  for f in t["fecha"]]
puts = t[(t["fecha"] == t["fecha"].max()) & (t["tipo"] == "P")]
sel = lambda ks, vs: set(puts[puts["strike"].isin(ks) & puts["venc"].isin(pd.to_datetime(vs))]["symbol"])
n1 = sel(NIVEL1["strikes"], NIVEL1["vencs"])
n2 = sel([k for p in NIVEL2 for k in p], [VENC_N2])
cam = t[t["delta_oi"].notna() & (t["delta_oi"] != 0) & (t["tipo"] == "P")].copy()
cam["zona"] = (cam["strike"] / 25).round() * 25
n3 = set()
for z in NIVEL3_ZONAS:
    s = cam[cam["zona"] == z].groupby("symbol")["delta_oi"].apply(lambda x: x.abs().sum()).sort_values(ascending=False)
    n3 |= set(s[(s.cumsum() / s.sum()).shift(fill_value=0) < 0.80].index)
n3 -= n2
nivel = {**{s: "1 soporte" for s in n1}, **{s: "2 vertical" for s in n2}, **{s: "3 arriba" for s in n3}}
simbolos = sorted(nivel)

# ---------------- descarga con UNA confirmación ----------------
asegurar_tcbbo({d: simbolos for d in dias}, DESDE, HASTA)

tr = pd.concat([pd.read_parquet(ruta_cache_tcbbo(d, simbolos, DESDE, HASTA)).assign(dia=d) for d in dias])
tr = clasificar_trades(tr, estricto=True)
tr["estado"] = tr["signo"].map({1: "compra", -1: "venta", 0: "indet"})
tr["size"] = tr["size"].astype("int64")

# ---------------- por serie: flujo medido vs ΔOI y vs la hipótesis nula ----------------
f = tr.pivot_table(index="symbol", columns="estado", values="size", aggfunc="sum", fill_value=0)
for c in ["compra", "venta", "indet"]:
    f[c] = f.get(c, 0)
f["complejo"] = tr[tr["complejo"]].groupby("symbol")["size"].sum()
f = f.fillna(0)
d_oi = t[t["dia_flujo"].isin(dias)].groupby("symbol")["delta_oi"].sum()
r = pd.DataFrame(index=simbolos)
r["nivel"] = pd.Series(nivel)
r[["compra", "venta", "indet", "complejo"]] = f.reindex(simbolos)[["compra", "venta", "indet", "complejo"]].fillna(0)
r["total"] = r[["compra", "venta", "indet"]].sum(axis=1)
r["pct_indet"] = (r["indet"] / r["total"] * 100).round(0)
r["neto_medido"] = r["compra"] - r["venta"]                   # + = el público COMPRÓ (en contratos)
r["delta_oi"] = d_oi.reindex(simbolos).fillna(0)
supuesto = HIPOTESIS_NULA_PUBLICO["P"]                          # 'compra' para puts


r["veredicto"] = [veredicto(n, d, supuesto) for n, d in zip(r["neto_medido"], r["delta_oi"])]
r["medido/ΔOI %"] = (r["neto_medido"] / r["delta_oi"].abs() * 100).round(0)
os.makedirs("data/b2", exist_ok=True)
r.to_csv("data/b2/flujo_series.csv", index_label="symbol")

pd.set_option("display.width", 230)
print(f"\n=== B2: flujo estricto (días de flujo {dias[0]} a {dias[-1]}) vs ΔOI y vs la hipótesis nula ===")
print(f"Hipótesis nula para puts: el público '{supuesto}' -> dealer corto de puts (gamma -)")
cols = ["nivel", "delta_oi", "compra", "venta", "indet", "pct_indet", "complejo", "neto_medido", "medido/ΔOI %", "veredicto"]
for niv, g in r.groupby("nivel"):
    print(f"\n--- nivel {niv} ---")
    print(g[cols[1:]].astype({c: "int64" for c in ["delta_oi", "compra", "venta", "indet", "complejo", "neto_medido"]})
          .to_string())
print("\nVeredictos por nivel (series):")
print(r.groupby(["nivel", "veredicto"]).size().unstack(fill_value=0).to_string())

# ---------------- test de verticales ----------------
print("\n=== Test de verticales: ¿las patas vecinas se negociaron juntas? ===")
tr["seg"] = tr.index.floor("s")
for a, b in NIVEL2:
    sa = [s for s in n2 if f"P{a * 1000:08d}" in s]
    sb = [s for s in n2 if f"P{b * 1000:08d}" in s]
    if not sa or not sb:
        continue
    ta, tb = tr[tr["symbol"] == sa[0]], tr[tr["symbol"] == sb[0]]
    pares = ta.reset_index().merge(tb.reset_index(), on=["seg", "size"], suffixes=("_a", "_b"))
    vol_a = ta["size"].sum()
    print(f"  {a}/{b}P dic: {len(pares)} coincidencias (mismo segundo y tamaño) | "
          f"{pares['size'].sum():,} de {vol_a:,} contratos de la pata {a} ({pares['size'].sum() / vol_a:.0%} si >0)"
          if vol_a else f"  {a}/{b}P dic: sin trades")
print("\nNada se fusionó en un GEX: el signo supuesto y el flujo medido quedan lado a lado (B3 los compara).")