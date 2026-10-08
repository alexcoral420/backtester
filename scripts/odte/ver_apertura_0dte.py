"""
Uso:  python scripts/odte/ver_apertura_0dte.py 2026-10-02 7695 7775 [desde] [hasta] [bloque_min]
      python scripts/odte/ver_apertura_0dte.py 2026-10-02 7695 7775 09:30 11:00 5

Flujo 0DTE en una FRANJA del día (pensado para la apertura después de una noticia).
- Gap de apertura vs cierre anterior (cómo recibió el mercado la noticia)
- Flujo ESTRICTO (solo agresores en bid/ask) en bloques, con el SPX de cada bloque
- Gráfico: SPX arriba, acumulados estrictos de calls y puts abajo
"""
import os
import sys
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

# scripts/odte/ -> sube 3 niveles hasta la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.precio import spx_1min
from src.odte.trades import descargar_tcbbo_0dte
from src.odte.clasificacion import clasificar_trades
from src.odte.flujo import flujo_por_minuto

if len(sys.argv) < 4:
    raise SystemExit("Uso: python scripts/odte/ver_apertura_0dte.py AAAA-MM-DD KMIN KMAX [desde] [hasta] [bloque]")

fecha = sys.argv[1]
kmin, kmax = float(sys.argv[2]), float(sys.argv[3])
desde = sys.argv[4] if len(sys.argv) > 4 else "09:30"
hasta = sys.argv[5] if len(sys.argv) > 5 else "11:00"
bloque = int(sys.argv[6]) if len(sys.argv) > 6 else 5

# --- Gap de apertura: cierre oficial del día hábil anterior vs apertura estimada ---
ini = (datetime.strptime(fecha, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
hist = yf.Ticker("^GSPC").history(start=ini, end=fecha)     # end exclusivo -> solo días anteriores
cierre_prev = float(hist["Close"].iloc[-1]) if not hist.empty else None

spx, base = spx_1min(fecha)
apertura = float(spx["spx"].iloc[0])
if cierre_prev:
    gap = apertura - cierre_prev
    print(f"\nCierre anterior ({hist.index[-1]:%Y-%m-%d}): {cierre_prev:.2f}")
    print(f"Apertura estimada 09:30:          {apertura:.2f}")
    print(f"GAP:                              {gap:+.2f} pts ({gap / cierre_prev:+.2%})")

# --- Trades de la franja (con confirmación de costo si no está en caché) ---
sel = seleccionar_0dte(fecha, kmin, kmax)
trades = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist(), desde, hasta)
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")

# Control de calidad: qué fracción quedó en el interior del spread (descartada por la regla estricta)
interior = ((trades["price"] > trades["bid_px_00"]) & (trades["price"] < trades["ask_px_00"])).mean()
print(f"\nTrades en la franja: {len(trades):,}  |  en el interior del spread: {interior:.1%}")

# --- Flujo estricto por minuto, alineado con el SPX de la franja ---
spx_f = spx.between_time(desde, hasta)
flujo = flujo_por_minuto(clasificar_trades(trades, estricto=True))
flujo = flujo.reindex(spx_f.index, fill_value=0)
flujo["spx"] = spx_f["spx"]

bloques = flujo.resample(f"{bloque}min").agg({"flujo_C": "sum", "flujo_P": "sum", "spx": "last"})
bloques["neto_alc"] = bloques["flujo_C"] - bloques["flujo_P"]

print(f"\nFlujo ESTRICTO del público, bloques de {bloque} min "
      f"(neto_alc = calls comprados - puts comprados)\n")
print(f"{'Bloque':>6s} {'SPX':>9s} {'Calls':>8s} {'Puts':>8s} {'Neto alc.':>10s}")
for t, f in bloques.iterrows():
    print(f"{t:%H:%M} {f['spx']:>9.2f} {int(f['flujo_C']):>+8,d} {int(f['flujo_P']):>+8,d} "
          f"{int(f['neto_alc']):>+10,d}")

print(f"\nTotal franja: calls {int(flujo['flujo_C'].sum()):+,d} | "
      f"puts {int(flujo['flujo_P'].sum()):+,d}")
print(f"SPX: abre {spx_f['spx'].iloc[0]:.2f} -> cierra franja {spx_f['spx'].iloc[-1]:.2f} | "
      f"mín {spx_f['spx'].min():.2f} ({spx_f['spx'].idxmin():%H:%M}) | "
      f"máx {spx_f['spx'].max():.2f} ({spx_f['spx'].idxmax():%H:%M})")

# --- Gráfico ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                               gridspec_kw={"height_ratios": [1, 1.2]})
ax1.plot(flujo.index, flujo["spx"], color="black", lw=1)
ax1.set_ylabel("SPX (estimado)")
ax1.set_title(f"0DTE {fecha} {desde}-{hasta} — strikes {kmin:.0f}-{kmax:.0f} — flujo estricto")
ax2.plot(flujo.index, flujo["flujo_C"].cumsum(), color="green", label="Calls (acumulado)")
ax2.plot(flujo.index, flujo["flujo_P"].cumsum(), color="red", label="Puts (acumulado)")
ax2.axhline(0, color="gray", lw=0.6)
ax2.set_ylabel("Contratos netos comprados")
ax2.legend(loc="upper left")
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=flujo.index.tz))
plt.tight_layout()

salida = f"data/apertura_0dte_{fecha}_{desde.replace(':', '')}-{hasta.replace(':', '')}.png"
plt.savefig(salida, dpi=120)
print(f"\n[gráfico] {salida}")
plt.show()