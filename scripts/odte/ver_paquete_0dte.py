"""
Uso:  python scripts/odte/ver_paquete_0dte.py FECHA HH:MM:SS KMIN KMAX [seg_antes] [seg_despues] [size_min]
      python scripts/odte/ver_paquete_0dte.py 2026-10-02 09:50:57 7500 7900

Busca TODAS las patas de una orden compleja: baja el tcbbo de todas las 0DTE
(calls y puts) en [KMIN, KMAX], pero solo unos segundos alrededor de HH:MM:SS.
Ventana tan corta => costo de centavos (se confirma antes de descargar).
"""
import os
import sys

import pandas as pd

# scripts/odte/ -> sube 3 niveles hasta la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.trades import descargar_tcbbo_0dte

if len(sys.argv) < 5:
    raise SystemExit(__doc__)

fecha, hora = sys.argv[1], sys.argv[2]
kmin, kmax = float(sys.argv[3]), float(sys.argv[4])
antes = int(sys.argv[5]) if len(sys.argv) > 5 else 2
despues = int(sys.argv[6]) if len(sys.argv) > 6 else 3
size_min = int(sys.argv[7]) if len(sys.argv) > 7 else 100

centro = pd.Timestamp(f"{fecha} {hora}")
desde = (centro - pd.Timedelta(seconds=antes)).strftime("%H:%M:%S")
hasta = (centro + pd.Timedelta(seconds=despues)).strftime("%H:%M:%S")

sel = seleccionar_0dte(fecha, kmin, kmax)
print(f"Buscando en {len(sel)} opciones 0DTE ({kmin:.0f}-{kmax:.0f}), {desde} a {hasta} NY")
trades = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist(), desde, hasta)
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")
trades["size"] = trades["size"].astype("int64")


def ubicacion(f) -> str:
    p, b, a = round(f["price"], 4), round(f["bid_px_00"], 4), round(f["ask_px_00"], 4)
    if p < b:  return "BAJO el bid"
    if p == b: return "en el bid"
    if p < a:  return "interior"
    if p == a: return "en el ask"
    return "SOBRE el ask"


grandes = trades[trades["size"] >= size_min].copy()
grandes["ubic"] = grandes.apply(ubicacion, axis=1)

print(f"\nTrades totales en la ventana: {len(trades):,}  |  de {size_min}+ contratos: {len(grandes)}")

# --- 1) Cada trade grande, en orden de tiempo ---
print(f"\n=== Trades de {size_min}+ contratos (orden cronológico) ===")
for t, f in grandes.sort_index().iterrows():
    print(f"{t:%H:%M:%S.%f}"[:-3] +
          f"  {f['instrument_class']} {f['strike_price']:.0f}  size {int(f['size']):>5d}  "
          f"precio {f['price']:>6.2f}  (bid {f['bid_px_00']:.2f} / ask {f['ask_px_00']:.2f})  {f['ubic']}")

# --- 2) Las patas: contratos por (tipo, strike) ---
print("\n=== Patas del paquete (contratos grandes por tipo y strike) ===")
patas = grandes.groupby(["instrument_class", "strike_price"]).agg(
    contratos=("size", "sum"),
    trades=("size", "size"),
    precio_prom=("price", "mean"),
    medio_prom=("bid_px_00", lambda s: ((s + grandes.loc[s.index, "ask_px_00"]) / 2).mean()),
)
patas["vs_medio"] = (patas["precio_prom"] - patas["medio_prom"]).round(2)
print(patas.round(2).to_string())
print("\nvs_medio: - = se imprimió bajo el medio (sugiere pata VENDIDA), "
      "+ = sobre el medio (sugiere pata COMPRADA)")