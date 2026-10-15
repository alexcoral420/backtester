"""
Uso:  python scripts/inventario_oi.py 2026-09-24 2026-10-08

Fase B1: inventario de OI en los walls y su cambio, SIN dirección (neutral respecto al signo).
Usa solo las cadenas que YA están en caché dentro del rango: costo $0, no descarga nada.

  1) Verificación de tiempo: ¿el OI del archivo del día d refleja las operaciones de d o de d-1?
  2) Para los walls del último día (método por defecto): OI de calls y puts al inicio y al final,
     ΔOI acumulado, y qué fracción del OI final es "nueva" en el período.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import CARPETA_CACHE, precio_spx, ruta_cadena
from src.gex import construir_cadena, gamma_walls
from src.inventario import delta_oi, oi_por_fecha, por_zona

if len(sys.argv) < 3:
    raise SystemExit("Uso: python scripts/inventario_oi.py INICIO FIN   (desde la raíz del proyecto)")
inicio, fin = pd.to_datetime(sys.argv[1]), pd.to_datetime(sys.argv[2])

fechas = sorted(os.path.basename(p)[-18:-8] for p in glob.glob(os.path.join(CARPETA_CACHE, "cadena_SPX_statistics_*.parquet")))
fechas = [f for f in fechas if inicio <= pd.to_datetime(f) <= fin and os.path.exists(ruta_cadena("SPX", "ohlcv-1d", f))]
if len(fechas) < 2:
    raise SystemExit(f"Hacen falta al menos 2 días en caché entre {sys.argv[1]} y {sys.argv[2]} (hay {len(fechas)}).")
print(f"=== Inventario B1 | {len(fechas)} días en caché: {fechas[0]} a {fechas[-1]} ===")
huecos = [b for a, b in zip(fechas, fechas[1:]) if np.busday_count(a, b) > 1]
if huecos:
    print(f"  ojo: faltan días de mercado antes de {huecos} -> ese ΔOI acumula varios días")

t = delta_oi(oi_por_fecha(fechas))

# ------------------------------------------------------------
# 1) ¿El OI del día d refleja d o d-1?  |ΔOI(d)| contra el volumen de cada opción en d y en d-1
# ------------------------------------------------------------
vol = pd.concat([pd.read_parquet(ruta_cadena("SPX", "ohlcv-1d", f))[["symbol", "volume"]].assign(fecha=pd.to_datetime(f))
                 for f in fechas], ignore_index=True).drop_duplicates(["symbol", "fecha"], keep="last")
x = t[t["delta_oi"].notna()].merge(vol, on=["symbol", "fecha"], how="left")
prev = dict(zip(pd.to_datetime(fechas[1:]), pd.to_datetime(fechas[:-1])))
x["fecha_prev"] = x["fecha"].map(prev)
x = x.merge(vol.rename(columns={"fecha": "fecha_prev", "volume": "volume_prev"}), on=["symbol", "fecha_prev"], how="left")
x[["volume", "volume_prev"]] = x[["volume", "volume_prev"]].fillna(0)
mov = x[x["delta_oi"] != 0]
print("\n=== 1) ¿A qué día corresponde el OI del archivo? (Spearman |ΔOI| vs volumen, opciones con ΔOI≠0) ===")
print(f"  |ΔOI(d)| vs volumen del MISMO día d : {mov['delta_oi'].abs().corr(mov['volume'], method='spearman'):+.2f}")
print(f"  |ΔOI(d)| vs volumen del día ANTERIOR: {mov['delta_oi'].abs().corr(mov['volume_prev'], method='spearman'):+.2f}")
sin_vol = (x["delta_oi"] != 0) & (x["volume"] == 0)
print(f"  opciones con ΔOI≠0 y CERO volumen el mismo día: {sin_vol.sum():,} de {(x['delta_oi'] != 0).sum():,}")
print("  (el día que más correlaciona es el que refleja el OI; si es el anterior, B2 empareja ΔOI(d) con el flujo de d-1)")

# ------------------------------------------------------------
# 2) Los walls del último día y su inventario
# ------------------------------------------------------------
ultimo = fechas[-1]
S = precio_spx(ultimo)
arriba, abajo = gamma_walls(construir_cadena(ultimo, S).dropna(subset=["gex_contrib"]), S, n=5)
walls = pd.concat([arriba.assign(lado="arriba"), abajo.assign(lado="abajo")])

z = por_zona(t)
f0, f1 = pd.to_datetime(fechas[0]), pd.to_datetime(fechas[-1])
filas = []
for _, w in walls.iterrows():
    for tipo in ["C", "P"]:
        g = z[(z["zona"] == w["nivel"]) & (z["tipo"] == tipo)].set_index("fecha")
        if g.empty:
            continue
        oi0 = g["oi"].get(f0, np.nan)
        oi1 = g["oi"].get(f1, np.nan)
        acum = g.loc[g.index > f0, "delta_oi"].sum()
        filas.append(dict(lado=w["lado"], wall=int(w["nivel"]), tipo=tipo, oi_inicio=oi0, oi_fin=oi1,
                          delta_acum=acum, pct_del_fin=acum / oi1 * 100 if oi1 else np.nan,
                          max_dia=g.loc[g.index > f0, "delta_oi"].abs().max()))
r = pd.DataFrame(filas)
pd.set_option("display.width", 200)
print(f"\n=== 2) Walls del {ultimo} (SPX {S:.2f}) y su inventario entre {fechas[0]} y {ultimo} ===")
print(r.round(1).to_string(index=False))
print("\n  pct_del_fin = qué parte del OI final se abrió (o cerró, si es negativo) dentro del período.")
print("  Sin dirección: un ΔOI de +3.000 dice cuánto se abrió, no quién quedó largo (eso es B2).")