"""
Uso:  python scripts/ver_giro_0dte.py 2026-09-29 7600 7750 [ventana_min] [bloque_min]
Zoom alrededor del mínimo del día: flujo ESTRICTO en bloques de pocos minutos,
para ver si el flujo se ADELANTA al giro o lo PERSIGUE. Todo desde caché.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cero_dte import (seleccionar_0dte, descargar_tcbbo_0dte, spx_1min,
                          clasificar_trades, flujo_por_minuto)

if len(sys.argv) < 4:
    raise SystemExit("Uso: python scripts/ver_giro_0dte.py AAAA-MM-DD STRIKE_MIN STRIKE_MAX [ventana] [bloque]")

fecha = sys.argv[1]
kmin, kmax = float(sys.argv[2]), float(sys.argv[3])
ventana = int(sys.argv[4]) if len(sys.argv) > 4 else 40   # minutos antes y después del mínimo
bloque = int(sys.argv[5]) if len(sys.argv) > 5 else 5     # tamaño de cada bloque

sel = seleccionar_0dte(fecha, kmin, kmax)
trades = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")
spx, _ = spx_1min(fecha)

flujo = flujo_por_minuto(clasificar_trades(trades, estricto=True))
flujo = flujo.join(spx["spx"], how="left")

minimo = spx["spx"].idxmin()
desde = minimo - pd.Timedelta(minutes=ventana)
hasta = minimo + pd.Timedelta(minutes=ventana)
zoom = flujo.loc[desde:hasta]

# Bloques: suma de flujo y último precio de cada bloque
bloques = zoom.resample(f"{bloque}min").agg({"flujo_C": "sum", "flujo_P": "sum", "spx": "last"})
bloques["neto_alcista"] = bloques["flujo_C"] - bloques["flujo_P"]   # comprar calls + vender puts

print(f"\nMínimo del SPX: {spx['spx'].min():.2f} a las {minimo:%H:%M}  "
      f"(regla ESTRICTA, bloques de {bloque} min)")
print(f"neto_alcista = calls comprados - puts comprados  (+ = flujo alcista del público)\n")
print(f"{'Bloque':>6s} {'SPX':>9s} {'Calls':>8s} {'Puts':>8s} {'Neto alc.':>10s}")
for t, f in bloques.iterrows():
    marca = "  <- mínimo" if t <= minimo < t + pd.Timedelta(minutes=bloque) else ""
    # iterrows convierte la fila entera a float (porque 'spx' es float) -> volvemos a int
    print(f"{t:%H:%M} {f['spx']:>9.2f} {int(f['flujo_C']):>+8,d} {int(f['flujo_P']):>+8,d} "
          f"{int(f['neto_alcista']):>+10,d}{marca}")

antes = bloques.loc[:minimo - pd.Timedelta(minutes=1), "neto_alcista"].sum()
despues = bloques.loc[minimo:, "neto_alcista"].sum()
print(f"\nNeto alcista ANTES del mínimo ({ventana} min):   {antes:+,d}")
print(f"Neto alcista DESPUÉS del mínimo ({ventana} min): {despues:+,d}")