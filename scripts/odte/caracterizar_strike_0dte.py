"""
Uso:  python scripts/odte/caracterizar_strike_0dte.py 2026-10-14 7675 7795 7790 C

Caracteriza el flujo ESTRICTO de UN strike 0DTE (todo desde caché, $0).
KMIN KMAX deben ser LOS MISMOS de la descarga original: la caché se identifica por la lista de símbolos.
Solo números, sin interpretación:
  - % indeterminado y % complejo del strike
  - por tamaño de trade (1-10, 11-49, 50-99, 100+): trades, volumen, compra, venta, indet, neto
  - concentración en el tiempo: % del neto en el top 1 / 5 / 10 minutos, y los 10 minutos de mayor |neto|
    con el SPX de ese minuto (barra cerrada anterior, sin mirar al futuro)
  - neto por media hora
  - los 10 trades más grandes
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.clasificacion import clasificar_trades
from src.odte.precio import spx_1min
from src.odte.trades import descargar_tcbbo_0dte

if len(sys.argv) < 5:
    raise SystemExit("Uso: python scripts/odte/caracterizar_strike_0dte.py FECHA KMIN KMAX STRIKE [C|P]")
fecha, kmin, kmax, k = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
tipo = sys.argv[5].upper() if len(sys.argv) > 5 else "C"

sel = seleccionar_0dte(fecha, kmin, kmax)
tr = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())
tr = tr.reset_index().merge(sel[["raw_symbol", "instrument_class", "strike_price"]],
                            left_on="symbol", right_on="raw_symbol", how="left")
tr = tr[(tr["strike_price"] == k) & (tr["instrument_class"] == tipo)].copy()
if tr.empty:
    raise SystemExit(f"Sin trades para {int(k)}{tipo} en {fecha}")
tr = clasificar_trades(tr, estricto=True)
tr["size"] = tr["size"].astype("int64")
ts = "ts_recv" if "ts_recv" in tr.columns else tr.columns[0]
tr = tr.sort_values(ts)
tr["minuto"] = tr[ts].dt.floor("min")
tr["neto"] = tr["signo"].astype("int64") * tr["size"]

spx, _ = spx_1min(fecha)
dia = spx.between_time("09:30", "16:00")["spx"]
px = dia.rename("spx_min").reset_index().rename(columns={dia.index.name or "index": "m"})
px["m"] = px["m"] + pd.Timedelta(minutes=1)
tr = pd.merge_asof(tr, px.sort_values("m"), left_on=ts, right_on="m", direction="backward")

vol = tr["size"].sum()
neto = tr["neto"].sum()
print(f"\n=== {fecha} | {int(k)}{tipo} 0DTE | flujo ESTRICTO ===")
print(f"Trades {len(tr):,} | volumen {vol:,} | compra {tr.loc[tr.signo == 1, 'size'].sum():,} | "
      f"venta {tr.loc[tr.signo == -1, 'size'].sum():,} | neto {neto:+,}")
print(f"% indeterminado {tr.loc[tr.signo == 0, 'size'].sum() / vol:.1%} | "
      f"% complejo (fuera del bid/ask) {tr.loc[tr['complejo'], 'size'].sum() / vol:.1%}")
print(f"Primer trade {tr[ts].iloc[0]:%H:%M:%S} | último {tr[ts].iloc[-1]:%H:%M:%S}")

# ---------------- por tamaño ----------------
tr["tamaño"] = pd.cut(tr["size"], [0, 10, 49, 99, np.inf], labels=["1-10", "11-49", "50-99", "100+"])
t = tr.groupby("tamaño", observed=False).agg(
    trades=("size", "size"), volumen=("size", "sum"),
    compra=("size", lambda s: s[tr.loc[s.index, "signo"] == 1].sum()),
    venta=("size", lambda s: s[tr.loc[s.index, "signo"] == -1].sum()),
    indet=("size", lambda s: s[tr.loc[s.index, "signo"] == 0].sum()), neto=("neto", "sum"))
t["% del volumen"] = (t["volumen"] / vol * 100).round(1)
t["% del neto"] = (t["neto"] / neto * 100).round(1) if neto else np.nan
print("\n--- Por tamaño de trade ---")
print(t.to_string())

# ---------------- concentración en el tiempo ----------------
m = tr.groupby("minuto").agg(trades=("size", "size"), volumen=("size", "sum"), neto=("neto", "sum"),
                             spx=("spx_min", "last"))
orden = m["neto"].abs().sort_values(ascending=False)
print(f"\n--- Concentración: {len(m)} minutos con trades ---")
for n in [1, 5, 10]:
    print(f"  top {n:2d} minutos por |neto|: {m.loc[orden.index[:n], 'neto'].sum():+,} "
          f"= {m.loc[orden.index[:n], 'neto'].sum() / neto:.0%} del neto del día")
top = m.loc[orden.index[:10]].copy()
top.index = top.index.strftime("%H:%M")
top["spx"] = top["spx"].round(1)
top["dist_strike"] = (top["spx"] - k).round(1)
print("\n--- Los 10 minutos de mayor |neto| ---")
print(top.to_string())

mh = tr.set_index(ts).resample("30min")["neto"].sum()
mh.index = mh.index.strftime("%H:%M")
print("\n--- Neto por media hora ---")
print(mh.to_string())

g = tr.nlargest(10, "size")[[ts, "size", "price", "bid_px_00", "ask_px_00", "signo", "complejo", "spx_min"]]
g[ts] = g[ts].dt.strftime("%H:%M:%S")
print("\n--- Los 10 trades más grandes (signo: 1 ask, -1 bid, 0 indet) ---")
print(g.to_string(index=False))