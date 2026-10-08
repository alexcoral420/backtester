"""
Uso:  python scripts/ver_flujo_0dte.py 2026-09-29 7600 7750
Trade sign minuto a minuto de las 0DTE + gráfico (todo desde caché, sin costo).
"""
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cero_dte import (seleccionar_0dte, descargar_tcbbo_0dte, spx_1min,
                          clasificar_trades, flujo_por_minuto)

if len(sys.argv) < 4:
    raise SystemExit("Uso: python scripts/ver_flujo_0dte.py AAAA-MM-DD STRIKE_MIN STRIKE_MAX")

fecha = sys.argv[1]
kmin, kmax = float(sys.argv[2]), float(sys.argv[3])

# --- Datos (todo debería salir de caché) ---
sel = seleccionar_0dte(fecha, kmin, kmax)
trades = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")
spx, _ = spx_1min(fecha)

# --- Clasificar y agrupar ---
flujo = flujo_por_minuto(clasificar_trades(trades))
flujo = flujo.join(spx["spx"], how="left")   # mismo índice: minuto en NY

# Regla estricta (solo agresores limpios en bid/ask), para comparar
flujo_e = flujo_por_minuto(clasificar_trades(trades, estricto=True))
flujo_e = flujo_e.reindex(flujo.index, fill_value=0)

# --- Prueba de hipótesis: ¿calls agresivos en el rebote? ---
minimo = spx["spx"].idxmin()
print(f"\nMínimo del SPX: {spx['spx'].min():.2f} a las {minimo:%H:%M}")

# Horas de corte CON la misma zona horaria del índice (no se puede mezclar con texto sin zona)
zona = flujo.index.tz
h1459 = pd.Timestamp(f"{fecha} 14:59", tz=zona)
h1500 = pd.Timestamp(f"{fecha} 15:00", tz=zona)

cortes = {
    "Caída   (09:30 -> mínimo)": (None, minimo),
    "Rebote  (mínimo -> 15:00)": (minimo, h1459),
    "Cierre  (15:00 -> 16:00) ": (h1500, None),
}

print("\nFlujo neto del PÚBLICO por minuto (+ = compra agresiva, - = venta agresiva)")
print(f"{'':28s} {'--- punto medio ---':>21s}   {'--- estricto ---':>21s}")
print(f"{'Tramo':28s} {'Calls/min':>10s} {'Puts/min':>10s}   {'Calls/min':>10s} {'Puts/min':>10s}  Min")
for nombre, (a, b) in cortes.items():
    t, te = flujo.loc[a:b], flujo_e.loc[a:b]
    n = len(t)
    print(f"{nombre:28s} {t['flujo_C'].sum()/n:>+10,.0f} {t['flujo_P'].sum()/n:>+10,.0f}   "
          f"{te['flujo_C'].sum()/n:>+10,.0f} {te['flujo_P'].sum()/n:>+10,.0f}  {n:>3d}")

print(f"\nTotal día (punto medio): calls {flujo['flujo_C'].sum():+,d} | puts {flujo['flujo_P'].sum():+,d}")
print(f"Total día (estricto):    calls {flujo_e['flujo_C'].sum():+,d} | puts {flujo_e['flujo_P'].sum():+,d}")

# --- La película ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                               gridspec_kw={"height_ratios": [1, 1.2]})
ax1.plot(flujo.index, flujo["spx"], color="black", lw=1)
ax1.axvline(minimo, color="gray", ls="--", lw=0.8)
ax1.set_ylabel("SPX (estimado)")
ax1.set_title(f"0DTE {fecha} — strikes {kmin:.0f}-{kmax:.0f} — flujo del público")

ax2.plot(flujo.index, flujo["acum_C"], color="green", label="Calls (acumulado)")
ax2.plot(flujo.index, flujo["acum_P"], color="red", label="Puts (acumulado)")
ax2.plot(flujo_e.index, flujo_e["flujo_C"].cumsum(), color="green", ls=":", label="Calls (estricto)")
ax2.plot(flujo_e.index, flujo_e["flujo_P"].cumsum(), color="red", ls=":", label="Puts (estricto)")
ax2.axhline(0, color="gray", lw=0.6)
ax2.axvline(minimo, color="gray", ls="--", lw=0.8)
ax2.set_ylabel("Contratos netos comprados")
ax2.legend(loc="upper left")

import matplotlib.dates as mdates
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=flujo.index.tz))
plt.tight_layout()

salida = f"data/flujo_0dte_{fecha}.png"
plt.savefig(salida, dpi=120)
print(f"\n[gráfico] {salida}")
plt.show()