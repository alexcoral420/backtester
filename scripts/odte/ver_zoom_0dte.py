"""
Uso:  python scripts/odte/ver_zoom_0dte.py FECHA KMIN KMAX ZOOM_DESDE ZOOM_HASTA [CACHE_DESDE CACHE_HASTA]
      python scripts/odte/ver_zoom_0dte.py 2026-10-02 7695 7775 09:45 10:05 09:30 11:00

Zoom SOLO desde caché (nunca descarga): minuto a minuto + quién vendió/compró los puts
(por tamaño de trade, los trades más grandes y por strike).
CACHE_DESDE/HASTA = la franja con la que se descargó el archivo (por defecto 09:30-16:00).
"""
import os
import sys

import pandas as pd

# scripts/odte/ -> sube 3 niveles hasta la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.constantes import ZONA_NY
from src.odte.catalogo import seleccionar_0dte
from src.odte.precio import spx_1min
from src.odte.trades import ruta_cache_tcbbo
from src.odte.clasificacion import clasificar_trades
from src.odte.flujo import flujo_por_minuto

if len(sys.argv) < 6:
    raise SystemExit(__doc__)

fecha = sys.argv[1]
kmin, kmax = float(sys.argv[2]), float(sys.argv[3])
z_desde, z_hasta = sys.argv[4], sys.argv[5]
c_desde = sys.argv[6] if len(sys.argv) > 6 else "09:30"
c_hasta = sys.argv[7] if len(sys.argv) > 7 else "16:00"

# --- Leer SOLO de caché: si el archivo no existe, abortar (nunca descargar desde aquí) ---
sel = seleccionar_0dte(fecha, kmin, kmax)
ruta = ruta_cache_tcbbo(fecha, sel["raw_symbol"].tolist(), c_desde, c_hasta)
if not os.path.exists(ruta):
    raise SystemExit(f"No existe en caché: {ruta}\n"
                     "Revisa KMIN/KMAX y la franja de la descarga. Este script no descarga nada.")
print(f"[caché] leyendo {ruta}")
trades = pd.read_parquet(ruta)
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")

# --- Recortar al zoom (horas CON zona horaria, siempre NY) ---
ini = pd.Timestamp(f"{fecha} {z_desde}", tz=ZONA_NY)
fin = pd.Timestamp(f"{fecha} {z_hasta}", tz=ZONA_NY)
clas = clasificar_trades(trades, estricto=True).loc[ini:fin].copy()
clas["size"] = clas["size"].astype("int64")

spx, _ = spx_1min(fecha)
spx_z = spx.loc[ini:fin, "spx"]

# ============================================================
# 1) Minuto a minuto
# ============================================================
flujo = flujo_por_minuto(clas).reindex(spx_z.index, fill_value=0)
print(f"\n=== Minuto a minuto {z_desde}-{z_hasta} (regla ESTRICTA) ===")
print(f"{'Min':>5s} {'SPX':>9s} {'Calls':>8s} {'Puts':>8s} {'Neto alc.':>10s}")
for t in flujo.index:
    c, p = int(flujo.at[t, "flujo_C"]), int(flujo.at[t, "flujo_P"])
    marca = "  <- mínimo" if t == spx_z.idxmin() else ""
    print(f"{t:%H:%M} {spx_z[t]:>9.2f} {c:>+8,d} {p:>+8,d} {c - p:>+10,d}{marca}")

# ============================================================
# 2) PUTS: ¿muchos trades chicos o pocas órdenes grandes?
# ============================================================
puts = clas[(clas["instrument_class"] == "P") & (clas["signo"] != 0)]
cortes = [0, 10, 49, 99, float("inf")]
etiquetas = ["1-10 (retail)", "11-49", "50-99", "100+ (bloques)"]
puts = puts.assign(tamano=pd.cut(puts["size"], bins=cortes, labels=etiquetas))

tabla = puts.groupby("tamano", observed=False).agg(
    trades=("size", "size"),
    vendidos=("flujo", lambda f: int(-f[f < 0].sum())),
    comprados=("flujo", lambda f: int(f[f > 0].sum())),
    neto=("flujo", "sum"),
)
tabla["% del neto"] = (tabla["neto"] / tabla["neto"].sum() * 100).round(1)
print(f"\n=== PUTS por tamaño de trade ({z_desde}-{z_hasta}) ===")
print(tabla)

# ============================================================
# 3) Los 10 trades de puts más grandes
# ============================================================
print("\n=== Los 10 trades de PUTS más grandes ===")
top = puts.nlargest(10, "size")
for t, f in top.iterrows():
    lado = "VENTA " if f["signo"] < 0 else "COMPRA"
    print(f"{t:%H:%M:%S}  {lado}  strike {f['strike_price']:.0f}  size {int(f['size']):>5d}  "
          f"precio {f['price']:.2f}  (bid {f['bid_px_00']:.2f} / ask {f['ask_px_00']:.2f})")

# ============================================================
# 4) ¿En qué strikes se movieron los puts?
# ============================================================
por_strike = puts.groupby("strike_price")["flujo"].sum().astype("int64")
por_strike = por_strike[por_strike != 0].sort_values()
print("\n=== Flujo neto de PUTS por strike (- = el público vendió) ===")
print(por_strike.head(10).to_string())