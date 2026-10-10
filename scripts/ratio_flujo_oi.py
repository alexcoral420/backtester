"""
Uso:  python scripts/ratio_flujo_oi.py

¿Puede el flujo de UN día mover la posición del dealer en un wall?
Compara, por día y por opción, el flujo contra el open interest (OI) de ese strike.

  techo   = volumen total del día / OI   -> máximo posible, sin importar la regla de clasificación
  estricta= |flujo neto estricto| / OI
  medio   = |flujo neto punto medio| / OI

Umbrales fijados ANTES de ver los datos:
  < 1%   el flujo diario no puede reposicionar al dealer: manda el inventario
  1-5%   zona ambigua: refinar a gamma
  > 5%   el flujo diario sí puede mover la posición

Trades: de los trades_*.parquet que ya están en data/raw (costo $0).
OI: se descarga SOLO para los símbolos de esos archivos (schema statistics, stat_type 9),
con get_cost y confirmación antes, y queda en caché (data/raw/oi_FECHA_HASH.parquet).
"""
import glob
import hashlib
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.odte.clasificacion import clasificar_trades
from src.odte.constantes import CARPETA_CACHE, DATASET
from src.simbolos import parsear_simbolos

STAT_OI = 9


def parametros_oi(dia: str, simbolos: list[str]) -> dict:
    fin = (pd.Timestamp(dia) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return dict(dataset=DATASET, symbols=sorted(simbolos), stype_in="raw_symbol",
                schema="statistics", start=dia, end=fin)


def ruta_oi(dia: str, simbolos: list[str]) -> str:
    huella = hashlib.md5("|".join(sorted(simbolos)).encode()).hexdigest()[:8]
    return os.path.join(CARPETA_CACHE, f"oi_{dia}_{huella}.parquet")


def limpiar_oi(stats: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Se queda con el OI (stat_type 9), UNA fila por símbolo (la última publicada).
    Devuelve también cuántos registros repetidos había (el posible doble conteo de gex.py)."""
    oi = stats[stats["stat_type"] == STAT_OI].copy()
    repetidos = int(oi.duplicated("symbol").sum())
    orden = "ts_event" if "ts_event" in oi.columns else oi.columns[0]
    oi = oi.sort_values(orden).drop_duplicates("symbol", keep="last")
    return oi[["symbol", "quantity"]].rename(columns={"quantity": "oi"}), repetidos


# ------------------------------------------------------------
# 1) Trades en caché: qué símbolos hay por día
# ------------------------------------------------------------
trades_por_dia: dict[str, list[pd.DataFrame]] = {}
for ruta in sorted(glob.glob(os.path.join(CARPETA_CACHE, "trades_*.parquet"))):
    nombre = os.path.basename(ruta)
    m = re.match(r"trades_(\d{4}-\d{2}-\d{2})_\d{4}-\d{2}-\d{2}_[0-9a-f]{8}\.parquet$", nombre)
    if not m:            # el archivo viejo sin hash (pruebas ATM) no es un wall
        continue
    t = pd.read_parquet(ruta)
    if not t.empty:
        trades_por_dia.setdefault(m.group(1), []).append(t)

if not trades_por_dia:
    raise SystemExit(f"No hay archivos trades_*_HASH.parquet en {CARPETA_CACHE}")

simbolos_por_dia = {d: sorted(pd.concat(ts)["symbol"].unique()) for d, ts in trades_por_dia.items()}

# ------------------------------------------------------------
# 2) OI: costo total primero, una sola confirmación
# ------------------------------------------------------------
faltan = {d: s for d, s in simbolos_por_dia.items() if not os.path.exists(ruta_oi(d, s))}
if faltan:
    import databento as db
    from config import DATABENTO_KEY
    cliente = db.Historical(DATABENTO_KEY)
    costo = sum(cliente.metadata.get_cost(**parametros_oi(d, s)) for d, s in faltan.items())
    n_sim = sum(len(s) for s in faltan.values())
    print(f"OI a descargar: {len(faltan)} días, {n_sim} símbolos. Costo estimado: ${costo:.4f}")
    if input("¿Descargar? (s/n): ").strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    for d, s in faltan.items():
        try:
            stats = cliente.timeseries.get_range(**parametros_oi(d, s)).to_df().reset_index()
        except Exception as e:
            raise RuntimeError(f"Falló la descarga del OI de {d}: {e}")
        stats.to_parquet(ruta_oi(d, s))
        print(f"[guardado] {ruta_oi(d, s)} ({len(stats)} filas)")

# ------------------------------------------------------------
# 3) Ratio flujo / OI por día y opción
# ------------------------------------------------------------
filas, total_repetidos = [], 0
for dia, ts in sorted(trades_por_dia.items()):
    t = pd.concat(ts, ignore_index=True)
    oi, repetidos = limpiar_oi(pd.read_parquet(ruta_oi(dia, simbolos_por_dia[dia])))
    total_repetidos += repetidos

    t["size"] = t["size"].astype("int64")
    medio = clasificar_trades(t, estricto=False)
    estricta = clasificar_trades(t, estricto=True)
    agg = pd.DataFrame({
        "volumen": t.groupby("symbol")["size"].sum(),
        "neto_medio": medio.groupby("symbol")["flujo"].sum(),
        "neto_estricto": estricta.groupby("symbol")["flujo"].sum(),
    }).reset_index().merge(oi, on="symbol", how="left")

    info = parsear_simbolos(agg["symbol"])
    agg["dia"] = dia
    agg["tipo"] = info["tipo"]
    agg["strike"] = info["strike"]
    filas.append(agg)

r = pd.concat(filas, ignore_index=True)
sin_oi = r["oi"].isna() | (r["oi"] <= 0)
if sin_oi.any():
    print(f"\nAviso: {int(sin_oi.sum())} opciones sin OI (se excluyen del ratio):")
    print(r.loc[sin_oi, ["dia", "symbol", "volumen"]].to_string(index=False))
r = r[~sin_oi].copy()

r["techo_%"] = r["volumen"] / r["oi"] * 100
r["estricta_%"] = r["neto_estricto"].abs() / r["oi"] * 100
r["medio_%"] = r["neto_medio"].abs() / r["oi"] * 100

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 300)
print("\n=== Flujo del día contra OI, por opción ===")
print(r[["dia", "strike", "tipo", "oi", "volumen", "neto_medio", "neto_estricto",
         "techo_%", "medio_%", "estricta_%"]]
      .sort_values(["dia", "strike", "tipo"]).round(2).to_string(index=False))


def zona(x: float) -> str:
    return "<1% (inventario)" if x < 1 else ("1-5% (ambigua)" if x <= 5 else ">5% (flujo)")


print("\n=== Resumen: ¿en qué zona cae cada opción-día? ===")
resumen = pd.DataFrame({
    col: r[col].apply(zona).value_counts().reindex(
        ["<1% (inventario)", "1-5% (ambigua)", ">5% (flujo)"], fill_value=0)
    for col in ["techo_%", "medio_%", "estricta_%"]
})
print(resumen.to_string())
print("\nMedianas:  techo {:.2f}%  |  punto medio {:.2f}%  |  estricta {:.2f}%".format(
    r["techo_%"].median(), r["medio_%"].median(), r["estricta_%"].median()))
print(f"Registros de OI repetidos encontrados (y descartados): {total_repetidos}")