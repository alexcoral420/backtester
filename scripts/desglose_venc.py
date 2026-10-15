"""
Uso:  python scripts/desglose_venc.py 2026-09-24 2026-10-08

Antes de comprar un solo tcbbo (B2): ¿qué SERIES (strike + vencimiento) concentran el ΔOI de los walls?
Solo caché: costo $0.

Prioridad (definida el 15-oct): la pregunta operativa es "¿el soporte es barrera o trampolín?"
  PRIMARIA:   puts de los soportes (debajo del precio)
  SECUNDARIA: puts ITM de arriba (curiosidad de microestructura; solo si sobra presupuesto)
Para cada zona se listan las series que suman >= 80% del |ΔOI| acumulado, con los DÍAS DE FLUJO que
habría que comprar (regla de tiempo: ΔOI del archivo de d <- flujo de d-1).
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import CARPETA_CACHE, ruta_cadena
from src.inventario import delta_oi, fecha_flujo, oi_por_fecha

PRIMARIA = [("P", 7500), ("P", 7600), ("P", 7400), ("P", 7300), ("P", 7650)]
SECUNDARIA = [("P", 7900), ("P", 7850), ("P", 7800)]
BANDA, CUBRIR = 25, 0.80

if len(sys.argv) < 3:
    raise SystemExit("Uso: python scripts/desglose_venc.py INICIO FIN   (desde la raíz del proyecto)")
inicio, fin = pd.to_datetime(sys.argv[1]), pd.to_datetime(sys.argv[2])
fechas = sorted(os.path.basename(p)[-18:-8] for p in glob.glob(os.path.join(CARPETA_CACHE, "cadena_SPX_statistics_*.parquet")))
fechas = [f for f in fechas if inicio <= pd.to_datetime(f) <= fin and os.path.exists(ruta_cadena("SPX", "ohlcv-1d", f))]

t = delta_oi(oi_por_fecha(fechas))
t["zona"] = (t["strike"] / BANDA).round() * BANDA
t = t[t["delta_oi"].notna() & (t["delta_oi"] != 0)]
t["dia_flujo"] = [fecha_flujo(f, fechas) for f in t["fecha"]]

pd.set_option("display.width", 220)
plan = []
for prioridad, zonas in [("PRIMARIA", PRIMARIA), ("SECUNDARIA", SECUNDARIA)]:
    print(f"\n######## {prioridad} ########")
    for tipo, zona in zonas:
        z = t[(t["tipo"] == tipo) & (t["zona"] == zona)]
        if z.empty:
            print(f"\n{zona}{tipo}: sin cambios de OI en el período")
            continue
        s = z.groupby(["symbol", "strike", "venc"]).agg(
            delta_acum=("delta_oi", "sum"), abs_delta=("delta_oi", lambda x: x.abs().sum()),
            dias_con_cambio=("delta_oi", "size"), oi_fin=("oi", "last"),
            dias_flujo=("dia_flujo", lambda x: ",".join(sorted({d.strftime("%m-%d") for d in x})))
        ).sort_values("abs_delta", ascending=False).reset_index()
        s["% del |ΔOI| zona"] = s["abs_delta"] / s["abs_delta"].sum() * 100
        s["acumulado %"] = s["% del |ΔOI| zona"].cumsum()
        elegidas = s[s["acumulado %"].shift(fill_value=0) < CUBRIR * 100]
        s["venc"] = s["venc"].dt.strftime("%Y-%m-%d")
        print(f"\n{zona}{tipo}: ΔOI neto {z['delta_oi'].sum():+,.0f} | {len(s)} series con cambios | "
              f"{len(elegidas)} cubren el {CUBRIR:.0%}")
        print(s.head(max(len(elegidas), 3))[["strike", "venc", "delta_acum", "abs_delta", "% del |ΔOI| zona",
                                             "acumulado %", "oi_fin", "dias_con_cambio", "dias_flujo"]]
              .round(1).to_string(index=False))
        for _, e in elegidas.iterrows():
            plan.append(dict(prioridad=prioridad, symbol=e["symbol"], dias=e["dias_con_cambio"]))

p = pd.DataFrame(plan)
print("\n######## PLAN DE COMPRA tcbbo (series x días de flujo) ########")
for prio, g in p.groupby("prioridad", sort=False):
    print(f"  {prio:10s}: {g['symbol'].nunique()} series | {int(g['dias'].sum())} serie-días")
print("  El costo real se consulta con get_cost (y confirmación) ANTES de comprar: no se estima a ojo.")