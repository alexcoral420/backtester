"""
Uso:  python scripts/walls_tiempo.py 2026-09-24 2026-10-21 --sin 2026-10-20
      opciones: --sin FECHA [FECHA ...]  días a saltar (p. ej. sin datos en Databento)
                --dist 4                  walls a <= este % del spot
                --top 8                   ... que fueron top-N de |GEX| algún día

Evolución de los walls con SPX+SPXW (plazo horas, mid_forward): cuán CARGADOS están y POR QUÉ
cambia su GEX (src/walls.py: posicionamiento + mercado + vencidas, suma exacta).
  1. Por día: GEX total y su cambio descompuesto
  2. Por wall: GEX, OI total (miles) y % de puts
  3. Por wall, toda la ventana: posicionamiento vs mercado vs vencidas
  4. Las mayores aperturas/cierres zona-día (sin vencimientos), con el día de flujo que las explica
Medido: OI, ΔOI, % puts. Supuesto (hipótesis nula): el signo de gex, pos, mer, ven.

Cadenas en caché: $0. Las que falten: UNA confirmación con el costo total (~$0,66 por día sin caché).
Cada cadena procesada se guarda en data/procesado/ (construirla tarda ~2 min por día).
"""
import argparse
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import asegurar_cadenas
from src.gex import construir_cadena
from src.walls import evolucion

RAICES, PLAZO = ("SPX", "SPXW"), "horas"
CARPETA = "data/procesado"
COLUMNAS = ["symbol", "raiz", "vencimiento", "dte", "tipo", "strike", "open_interest", "iv", "gamma", "gex_contrib"]

ap = argparse.ArgumentParser()
ap.add_argument("inicio")
ap.add_argument("fin")
ap.add_argument("--sin", nargs="*", default=[])
ap.add_argument("--dist", type=float, default=4.0)
ap.add_argument("--top", type=int, default=8)
args = ap.parse_args()

hist = yf.Ticker("^GSPC").history(start=args.inicio, end=(pd.to_datetime(args.fin) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
hist.index = hist.index.tz_localize(None).normalize()
mercado = list(hist.index)                                          # días de mercado reales (para ver huecos)
dias = [d for d in mercado if d.strftime("%Y-%m-%d") not in args.sin]
if len(dias) < 2:
    raise SystemExit("Hacen falta al menos 2 días de mercado en el rango.")
asegurar_cadenas([d.strftime("%Y-%m-%d") for d in dias], RAICES)    # UNA sola confirmación de costo

os.makedirs(CARPETA, exist_ok=True)
cadenas = {}
for d in dias:
    f = d.strftime("%Y-%m-%d")
    ruta = os.path.join(CARPETA, f"cadena_{'+'.join(RAICES)}_{PLAZO}_{f}.parquet")
    if not os.path.exists(ruta):
        S = float(hist.loc[d, "Close"])
        c = construir_cadena(f, S, raices=RAICES, plazo=PLAZO)[COLUMNAS].copy()
        c["S"] = S
        c.to_parquet(ruta)
        print(f"[procesado] {ruta}", file=sys.stderr)
    cadenas[d] = pd.read_parquet(ruta)

D, Z = evolucion(cadenas)
for col in ["gex", "pos", "mer", "ven"]:
    D[col], Z[col] = D[col] / 1e9, Z[col] / 1e9
Z["S"] = Z["fecha"].map(D["S"])
Z["dist_pct"] = (Z["zona"] - Z["S"]) / Z["S"] * 100

# Qué flujo explica el ΔOI de cada fecha: el día de mercado anterior. Si hubo días saltados, son varias sesiones.
flujo = {}
for i, d in enumerate(dias[1:], start=1):
    previo, sesiones = dias[i - 1], mercado.index(d) - mercado.index(dias[i - 1])
    flujo[d] = previo.strftime("%m-%d") + ("" if sesiones == 1 else f" (+{sesiones - 1} ses.)")

pd.set_option("display.width", 250)
md = lambda df: df.rename(index=lambda x: x.strftime("%m-%d"))

print(f"=== 1. GEX total por día ($B) y de dónde salió el cambio | SPX+SPXW, plazo {PLAZO} ===")
D["dS"] = D["S"].diff()
D["flujo_de"] = pd.Series(flujo)
print(md(D[["S", "dS", "gex", "pos", "mer", "ven", "flujo_de"]]).round(2).to_string())
mismo = (D["dS"] * D["mer"] > 0).sum()
print(f"  'mercado' con el mismo signo que el movimiento del SPX: {mismo} de {D['dS'].notna().sum()} días")

cerca = Z[Z["dist_pct"].abs() <= args.dist].copy()
cerca["rk"] = cerca.groupby("fecha")["gex"].transform(lambda s: s.abs().rank(ascending=False))
walls = sorted(cerca.loc[cerca["rk"] <= args.top, "zona"].unique())
W = Z[Z["zona"].isin(walls)]
print(f"\n=== 2. Walls a <= {args.dist:g}% del spot que fueron top-{args.top} de |GEX| algún día ===")
tabla = lambda col, k=1.0: md(W.assign(v=W[col] * k).pivot(index="fecha", columns="zona", values="v")
                             .rename(columns=int))
g = tabla("gex")
g.insert(0, "S", D["S"].round(0).values)
print("\n--- GEX por wall ($B, signo supuesto) ---")
print(g.round(1).to_string())
print("\n--- OI total (miles de contratos, medido): cuán CARGADO está ---")
print(md(W.assign(v=(W["oi_c"] + W["oi_p"]) / 1e3).pivot(index="fecha", columns="zona", values="v")
         .rename(columns=int)).round(0).to_string())
print("\n--- % del OI que es put (medido; el signo supuesto depende de este balance) ---")
print(tabla("pct_puts").round(0).to_string())

print("\n=== 3. Por wall, toda la ventana ($B): ¿posicionamiento, mercado o vencimientos? ===")
ini, fin = W.groupby("zona").first(), W.groupby("zona").last()
r = W.groupby("zona")[["pos", "mer", "ven"]].sum()
r.insert(0, "gex_ini", ini["gex"]); r.insert(1, "gex_fin", fin["gex"])
for col, k in [("oi_c", "C"), ("oi_p", "P")]:
    r[f"OI_{k}_ini"], r[f"OI_{k}_fin"] = ini[col] / 1e3, fin[col] / 1e3
r[["dOI_C", "dOI_P", "OI_venc"]] = W.groupby("zona")[["doi_c", "doi_p", "oi_venc"]].sum() / 1e3
print(r.rename(index=int).round(1).to_string())
print("  (OI en miles. dOI = aperturas netas sin contar vencimientos; OI_venc = lo que venció)")

print(f"\n=== 4. Las 12 mayores aperturas/cierres zona-día (|ΔOI| sin vencimientos, a <= {args.dist:g}% del spot) ===")
cz = cerca[cerca["doi_c"].notna()].copy()
cz["abs"] = cz["doi_c"].abs() + cz["doi_p"].abs()
top = cz.nlargest(12, "abs")
top["flujo_de"] = top["fecha"].map(flujo)
top["fecha"] = top["fecha"].dt.strftime("%m-%d")
top["zona"] = top["zona"].astype(int)
print(top[["fecha", "flujo_de", "zona", "S", "doi_c", "doi_p", "oi_venc", "pos", "mer", "gex"]]
      .round(2).to_string(index=False))
