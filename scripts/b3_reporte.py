"""
Uso:  python scripts/b3_reporte.py

Fase B3 — cierre de la fase B. Lee data/b2/flujo_series.csv (de b2_flujo.py) y la cadena del último día
en caché. Costo $0, no descarga nada.

Por cada wall de puts: el signo SUPUESTO (hipótesis nula) y el flujo MEDIDO lado a lado, y la columna
que resume toda la fase B:

    % ΔOI INDETERMINADO = qué parte del cambio de inventario del período tiene signo supuesto, no medido.

Nada se fusiona en un GEX "corregido".
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import CARPETA_CACHE, descargar_cadena
from src.gex import HIPOTESIS_NULA_PUBLICO
from src.signo_medido import pct_delta_indet, pct_oi_supuesto, veredicto
from src.simbolos import parsear_simbolos

RUTA = "data/b2/flujo_series.csv"
if not os.path.exists(RUTA):
    raise SystemExit(f"No existe {RUTA}: corre primero scripts/b2_flujo.py")
r = pd.read_csv(RUTA)
info = parsear_simbolos(r["symbol"])
r["strike"], r["venc"] = info["strike"].values, info["venc"].dt.strftime("%Y-%m-%d").values

ultimo = sorted(os.path.basename(p)[-18:-8] for p in glob.glob(os.path.join(CARPETA_CACHE, "cadena_SPX_statistics_*.parquet")))[-1]
_, oi = descargar_cadena(ultimo)
r["oi_final"] = r["symbol"].map(oi.set_index("symbol")["open_interest"]).fillna(0)

supuesto = HIPOTESIS_NULA_PUBLICO["P"]
r["wall"] = (r["strike"] / 25).round() * 25
r["lado"] = np.where(r["nivel"].str.startswith("1"), "soporte", "arriba")

w = r.groupby(["lado", "wall"]).agg(series=("symbol", "size"), oi_final=("oi_final", "sum"),
                                    delta_oi=("delta_oi", "sum"), compra=("compra", "sum"),
                                    venta=("venta", "sum"), indet=("indet", "sum")).reset_index()
w["neto_medido"] = w["compra"] - w["venta"]
w["% vol indet"] = (w["indet"] / (w["compra"] + w["venta"] + w["indet"]) * 100).round(0)
w["% ΔOI INDETERMINADO"] = [round(pct_delta_indet(n, d), 0) for n, d in zip(w["neto_medido"], w["delta_oi"])]
w["% OI supuesto"] = [round(pct_oi_supuesto(n, o), 1) for n, o in zip(w["neto_medido"], w["oi_final"])]
w["veredicto"] = [veredicto(n, d, supuesto) for n, d in zip(w["neto_medido"], w["delta_oi"])]
w = w.sort_values(["lado", "wall"], ascending=[False, False])

pd.set_option("display.width", 220)
print(f"=== FASE B3: signo de los walls de PUTS (series de B2, OI al {ultimo}) ===")
print(f"Hipótesis nula: el público '{supuesto}' puts -> dealer corto, gamma - (el soporte AMPLIFICARÍA)\n")
cols = ["lado", "wall", "series", "oi_final", "delta_oi", "neto_medido", "% vol indet",
        "% ΔOI INDETERMINADO", "% OI supuesto", "veredicto"]
print(w[cols].astype({"wall": int, "oi_final": int, "delta_oi": int, "neto_medido": int}).to_string(index=False))

print("\n=== En una línea por wall ===")
for _, x in w.iterrows():
    print(f"  {x['lado']:7s} {int(x['wall'])}P: {x['% ΔOI INDETERMINADO']:.0f}% del cambio del período es SUPUESTO "
          f"| {x['% OI supuesto']:.1f}% del OI total es SUPUESTO | {x['veredicto']}")

print("\n=== Detalle por serie (las que tienen veredicto) ===")
r["veredicto"] = [veredicto(n, d, supuesto) for n, d in zip(r["neto_medido"], r["delta_oi"])]
d = r[~r["veredicto"].isin(["demasiado chico", "sin ΔOI"])]
print(d[["symbol", "nivel", "delta_oi", "neto_medido", "veredicto"]].to_string(index=False) if len(d) else "  ninguna")
print("\nLectura: con datos de cierre + tcbbo de una serie, el signo de estos walls es casi enteramente SUPUESTO.")
print("Medirlo exige el flujo intradía (siguiente fase), no más datos de cierre.")