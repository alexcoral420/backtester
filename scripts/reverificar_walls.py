"""
Uso:  python scripts/reverificar_walls.py

Re-verifica los veredictos BARRERA / TRAMPOLÍN de ver_walls.py con la regla ESTRICTA.
SOLO lee los trades_*.parquet que ya están en data/raw (nunca descarga, costo $0).

Para cada día y cada wall (strike) muestra:
  - dónde se imprimieron los trades (interior del spread, fuera del bid/ask, fuera de horario)
  - flujo neto del público con la regla del PUNTO MEDIO (la que usaba ver_walls.py)
  - flujo neto con la regla ESTRICTA (solo agresores en el bid o en el ask)
  - si el veredicto cambia
"""
import glob
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.odte.clasificacion import clasificar_trades
from src.odte.constantes import CARPETA_CACHE, ZONA_NY


def parsear(simbolos: pd.Series) -> pd.DataFrame:
    """'SPX   261016C07800000' -> venc '261016', tipo 'C', strike 7800.0"""
    codigo = simbolos.str.split().str[-1]
    return pd.DataFrame({
        "venc": codigo.str[:6],
        "tipo": codigo.str[6],
        "strike": codigo.str[7:].astype(int) / 1000,
    }, index=simbolos.index)


def veredicto(neto: int) -> str:
    """Público compra neto (cualquier tipo) -> dealer short gamma -> TRAMPOLÍN."""
    if neto > 0:
        return "TRAMPOLÍN"
    if neto < 0:
        return "BARRERA"
    return "NEUTRO"


filas = []
for ruta in sorted(glob.glob(os.path.join(CARPETA_CACHE, "trades_*.parquet"))):
    nombre = os.path.basename(ruta)
    m = re.match(r"trades_(\d{4}-\d{2}-\d{2})_", nombre)
    if not m:
        continue
    dia = m.group(1)

    t = pd.read_parquet(ruta)
    if t.empty:
        continue
    t = t.join(parsear(t["symbol"]))

    # Hora en Nueva York (el caché viejo guarda ts_recv en UTC)
    hora_ny = pd.to_datetime(t["ts_recv"], utc=True).dt.tz_convert(ZONA_NY)
    t["en_rth"] = (hora_ny.dt.strftime("%Y-%m-%d") == dia) & \
                  (hora_ny.dt.strftime("%H:%M") >= "09:30") & \
                  (hora_ny.dt.strftime("%H:%M") < "16:00")

    medio = clasificar_trades(t, estricto=False)
    estricta = clasificar_trades(t, estricto=True)
    precio, bid, ask = t["price"].round(4), t["bid_px_00"].round(4), t["ask_px_00"].round(4)
    interior = (precio > bid) & (precio < ask)

    for strike, idx in t.groupby("strike").groups.items():
        sub = t.loc[idx]
        def neto(df, tipo):
            return int(df.loc[idx][df.loc[idx, "tipo"] == tipo]["flujo"].sum())
        c_pm, p_pm = neto(medio, "C"), neto(medio, "P")
        c_es, p_es = neto(estricta, "C"), neto(estricta, "P")
        filas.append({
            "dia": dia, "strike": strike, "venc": sub["venc"].iloc[0],
            "trades": len(sub),
            "%interior": interior.loc[idx].mean() * 100,
            "%complejo": medio.loc[idx, "complejo"].mean() * 100,
            "%fuera_rth": (~sub["en_rth"]).mean() * 100,
            "C_pm": c_pm, "P_pm": p_pm, "neto_pm": c_pm + p_pm,
            "C_es": c_es, "P_es": p_es, "neto_es": c_es + p_es,
            "archivo": (re.search(r"_([0-9a-f]{8})\.parquet$", nombre) or [None, "(sin hash)"])[1],
        })

if not filas:
    raise SystemExit(f"No hay archivos trades_*.parquet en {CARPETA_CACHE}")

r = pd.DataFrame(filas).sort_values(["dia", "strike"])
r["ver_pm"] = r["neto_pm"].apply(veredicto)
r["ver_es"] = r["neto_es"].apply(veredicto)
r["cambia"] = (r["ver_pm"] != r["ver_es"]).map({True: "<-- CAMBIA", False: ""})

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 200)
pd.set_option("display.float_format", "{:.0f}".format)

print("\n=== Calidad de los datos por wall ===")
print(r[["dia", "strike", "venc", "trades", "%interior", "%complejo", "%fuera_rth", "archivo"]]
      .to_string(index=False))

print("\n=== Veredicto: punto medio (pm) contra estricta (es) ===")
print(r[["dia", "strike", "C_pm", "P_pm", "neto_pm", "ver_pm",
         "C_es", "P_es", "neto_es", "ver_es", "cambia"]].to_string(index=False))

n = len(r)
cambios = (r["ver_pm"] != r["ver_es"]).sum()
print(f"\nWalls-día evaluados: {n}  |  veredictos que cambian: {cambios} ({cambios / n:.0%})")
print(f"Trades en el interior del spread (promedio): {r['%interior'].mean():.0f}%")
print(f"Trades fuera del horario regular (promedio): {r['%fuera_rth'].mean():.0f}%")

print("\n=== Evolución de cada wall con la regla estricta (neto del público por día) ===")
print(r.pivot_table(index="strike", columns="dia", values="neto_es", aggfunc="sum")
      .sort_index(ascending=False).to_string())