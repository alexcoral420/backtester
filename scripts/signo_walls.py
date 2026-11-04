"""
Uso:  python scripts/signo_walls.py --solo-costo               (consulta el costo, NO descarga: $0)
      python scripts/signo_walls.py                            (descarga lo que falte con UNA confirmación)
      python scripts/signo_walls.py --paquetes                 (además: combos C+P del mismo strike, $0 con caché)
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

from src.gex import HIPOTESIS_NULA_PUBLICO
from src.odte.clasificacion import clasificar_trades
from src.odte.trades import asegurar_tcbbo, ruta_cache_tcbbo
from src.simbolos import parsear_simbolos
from src.paquetes import VENTANA, combos_cp, resumen_combos
from src.signo_walls import UMBRAL_COBERTURA, comparar, elegir_series, flujo_por_dia, pares_doi

DESDE, HASTA = "09:30", "16:15"
PATRON = "data/procesado/cadena_SPX+SPXW_horas_*.parquet"

ap = argparse.ArgumentParser()
ap.add_argument("--zonas", nargs="+", type=float, default=[7700, 7725, 7750, 7775, 8000])
ap.add_argument("--cobertura", type=float, default=UMBRAL_COBERTURA)
ap.add_argument("--solo-costo", action="store_true")
ap.add_argument("--paquetes", action="store_true")
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
total = asegurar_tcbbo(por_dia, DESDE, HASTA, solo_costo=args.solo_costo)
if args.solo_costo:
    raise SystemExit(f"TOTAL ${total:.4f}. Solo costo: no se descargó nada.")

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
if not args.paquetes:
    raise SystemExit

# ---------------- paquetes: combos C+P del mismo strike (src/paquetes.py) ----------------
tr = tr.sort_index()
combos = pd.concat([combos_cp(g) for _, g in tr.groupby("dia")], ignore_index=True)
combos = combos[combos["zona"].isin(args.zonas)]
vol = tr.assign(zona=tr["symbol"].map({s: z for s, (z, _) in elegidas.items()})).groupby("zona")["size"].sum()
res = resumen_combos(combos, vol)
res.to_csv("data/b2/paquetes_walls.csv")
print(f"\n=== Paquetes: combos C+P mismo strike y vencimiento, mismo tamaño, en {VENTANA} (lado de cada pata INFERIDO) ===")
print("sintetico: gamma neta 0 sea cual sea la dirección (el signo no importa; la nula también le da 0)")
print("straddle:  gamma ±2γ que la nula da como 0; straddle_neto + = el público COMPRÓ gamma (dealer corto)")
print("Contratos por combo (una pata); en_combos y volumen cuentan las dos patas. Es FLUJO, no OI.")
print(res.rename(index=int).round(1).to_string())
desplazados = []
for seg in (3, 17, 61):                                      # control placebo: desplazar las calls rompe los paquetes
    t = tr.copy()
    es_c = (parsear_simbolos(t["symbol"])["tipo"] == "C").to_numpy()
    t.index = t.index.where(~es_c, t.index + pd.Timedelta(seconds=seg))
    desplazados.append(sum(len(combos_cp(g.sort_index())) for _, g in t.groupby("dia")))
print(f"Placebo (calls desplazadas 3/17/61 s): {desplazados} combos vs {len(combos)} reales (todas las zonas: "
      f"{sum(len(combos_cp(g)) for _, g in tr.groupby('dia'))})")
