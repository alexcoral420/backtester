"""
Uso:  python scripts/signo_walls.py --solo-costo               (consulta el costo, NO descarga: $0)
      python scripts/signo_walls.py                            (descarga lo que falte con UNA confirmación)
      opciones: --zonas 7700 7725 7750 7775 8000   zonas de 25 puntos a medir (default: transición + 8000)
                --cobertura 0.8                    por zona y tipo, series que cubren ese % del |ΔOI|

MIDE el signo en los walls donde el supuesto pesa más: la transición 7700-7775 (OI ~50% puts) y 8000
(~2M contratos, 46% puts). SPX+SPXW, calls y puts, regla ESTRICTA (compra = ask, venta = bid, resto indet).
Lee las cadenas ya procesadas por walls_tiempo.py (data/procesado, $0); solo el tcbbo cuesta.

Por zona y tipo: ΔOI (medido) frente al neto del público medido el día de flujo (regla de tiempo: d-1),
y el veredicto contra la hipótesis nula de ese tipo (src/signo_walls.py, src/signo_medido.py).
Los pares que cruzan un hueco (10-19 -> 10-21) no reciben veredicto. Nada se fusiona con el GEX.
Salida: data/b2/signo_walls.csv
"""
import argparse
import glob
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import _cliente
from src.gex import HIPOTESIS_NULA_PUBLICO
from src.odte.clasificacion import clasificar_trades
from src.odte.trades import _parametros_tcbbo, ruta_cache_tcbbo
from src.signo_walls import UMBRAL_COBERTURA, comparar, elegir_series, flujo_por_dia, pares_doi

DESDE, HASTA = "09:30", "16:15"
PATRON = "data/procesado/cadena_SPX+SPXW_horas_*.parquet"

ap = argparse.ArgumentParser()
ap.add_argument("--zonas", nargs="+", type=float, default=[7700, 7725, 7750, 7775, 8000])
ap.add_argument("--cobertura", type=float, default=UMBRAL_COBERTURA)
ap.add_argument("--solo-costo", action="store_true")
args = ap.parse_args()

rutas = sorted(glob.glob(PATRON))
if len(rutas) < 2:
    raise SystemExit(f"Faltan cadenas procesadas ({PATRON}): corre antes scripts/walls_tiempo.py.")
cadenas = {pd.Timestamp(r[-18:-8]): pd.read_parquet(r, columns=["symbol", "tipo", "strike", "open_interest"])
           for r in rutas}
fechas = sorted(cadenas)
hist = yf.Ticker("^GSPC").history(start=fechas[0].strftime("%Y-%m-%d"),
                                  end=(fechas[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
mercado = list(hist.index.tz_localize(None).normalize())

pares = pares_doi(cadenas, mercado)
elegidas = elegir_series(pares, args.zonas, args.cobertura)
usados = pares[pares["symbol"].isin(list(elegidas)) & (pares["sesiones"] == 1)]
por_dia = {d.strftime("%Y-%m-%d"): sorted(g["symbol"].unique()) for d, g in usados.groupby("dia_flujo")}

print(f"Archivos {fechas[0]:%m-%d}..{fechas[-1]:%m-%d} | zonas {[int(z) for z in args.zonas]} | "
      f"cobertura {args.cobertura:.0%} del |ΔOI| por zona y tipo")
sel = pd.DataFrame.from_dict(elegidas, orient="index", columns=["zona", "tipo"])
print(sel.groupby(["zona", "tipo"]).size().unstack(fill_value=0).rename(index=int).to_string())
print(f"Días de flujo: {len(por_dia)} ({', '.join(d[5:] for d in por_dia)}) | series distintas: {len(elegidas)}")
huecos = pares.loc[pares["sesiones"] != 1, "fecha"].dt.strftime("%m-%d").unique()
if len(huecos):
    print(f"Sin veredicto por hueco de sesiones: archivo(s) {', '.join(huecos)}")

# ---------------- costo y descarga con UNA confirmación ----------------
pendientes = {d: s for d, s in por_dia.items() if not os.path.exists(ruta_cache_tcbbo(d, s, DESDE, HASTA))}
if pendientes:
    cliente = _cliente()
    costos = {d: cliente.metadata.get_cost(**_parametros_tcbbo(d, s, DESDE, HASTA)) for d, s in pendientes.items()}
    print("\nCosto tcbbo por día sin caché (get_cost, no descarga):")
    for d, c in costos.items():
        print(f"  {d}: {len(pendientes[d]):4d} series  ${c:.4f}")
    total = sum(costos.values())
    if args.solo_costo:
        raise SystemExit(f"TOTAL ${total:.4f} ({len(pendientes)} días). Solo costo: no se descargó nada.")
    print(f"TOTAL ${total:.4f}. ¿Descargar todo? (s/n): ", end="", flush=True)
    if sys.stdin.readline().strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")
    for d, s in pendientes.items():
        df = cliente.timeseries.get_range(**_parametros_tcbbo(d, s, DESDE, HASTA)).to_df()
        df.index = df.index.tz_convert("America/New_York")
        df = df[["symbol", "price", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]]
        df.to_parquet(ruta_cache_tcbbo(d, s, DESDE, HASTA))
        print(f"[guardado] {d}: {len(df)} trades", file=sys.stderr)
elif args.solo_costo:
    raise SystemExit("Todo en caché: costo $0.")

# ---------------- medición ----------------
tr = pd.concat([pd.read_parquet(ruta_cache_tcbbo(d, s, DESDE, HASTA)).assign(dia=pd.Timestamp(d))
                for d, s in por_dia.items()])
r = comparar(pares, flujo_por_dia(clasificar_trades(tr, estricto=True)), elegidas, HIPOTESIS_NULA_PUBLICO)
os.makedirs("data/b2", exist_ok=True)
r.to_csv("data/b2/signo_walls.csv")

pd.set_option("display.width", 230)
print(f"\n=== Signo MEDIDO (regla estricta) vs SUPUESTO (hipótesis nula) por zona y tipo ===")
print("MEDIDO: delta_oi, compra, venta, indet, complejo, neto_medido (+ = el público compró), pct_*")
print("SUPUESTO: accion_supuesta (lo que la nula dice que hace el público). veredicto = uno contra el otro.")
enteros = ["series", "pares", "delta_oi", "compra", "venta", "indet", "complejo", "neto_medido", "pares_hueco"]
print(r.astype({c: "int64" for c in enteros}).rename(index=int, level=0).round(0).to_string())
print("\nVeredictos (zona-tipo):", r["veredicto"].value_counts().to_dict())
print("Nada se fusionó en un GEX: el signo medido y el supuesto quedan lado a lado.")
