"""
Uso:  python scripts/odte/antes_despues_0dte.py 2026-10-14 7675 7795 14:01
      python scripts/odte/antes_despues_0dte.py 2026-10-14 7675 7795 14:01 7680 7700   (solo esos strikes)

Flujo ESTRICTO 0DTE por strike cortado a una HORA (todo desde caché, $0).
KMIN KMAX = los MISMOS de la descarga original (la caché se identifica por la lista de símbolos).
Por strike: calls/puts netos ANTES y DESDE la hora, neto total y signo del dealer medido en cada tramo
(público vende -> dealer + | compra -> dealer - | |neto| < MIN_ABS -> sin evidencia).
Además: el neto ACUMULADO hasta cada media hora de los strikes pedidos.
Solo números.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.clasificacion import clasificar_trades
from src.odte.trades import descargar_tcbbo_0dte
from src.signo_medido import MIN_ABS

if len(sys.argv) < 5:
    raise SystemExit("Uso: python scripts/odte/antes_despues_0dte.py FECHA KMIN KMAX HH:MM [K1 K2]")
fecha, kmin, kmax, hora = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
k1, k2 = (float(sys.argv[5]), float(sys.argv[6])) if len(sys.argv) > 6 else (kmin, kmax)

sel = seleccionar_0dte(fecha, kmin, kmax)
tr = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())
tr = tr.reset_index().merge(sel[["raw_symbol", "instrument_class", "strike_price"]],
                            left_on="symbol", right_on="raw_symbol", how="left")
tr = tr[tr["strike_price"].between(k1, k2)].copy()
tr = clasificar_trades(tr, estricto=True)
ts = "ts_recv" if "ts_recv" in tr.columns else tr.columns[0]
corte = pd.Timestamp(f"{fecha} {hora}", tz=tr[ts].dt.tz)
tr["tramo"] = (tr[ts] < corte).map({True: "antes", False: "desde"})
tr["neto"] = tr["signo"].astype("int64") * tr["size"].astype("int64")
tr["indet"] = (tr["signo"] == 0) * tr["size"].astype("int64")


def dealer(x):
    return "sin evidencia" if abs(x) < MIN_ABS else ("-" if x > 0 else "+")


p = tr.pivot_table(index="strike_price", columns=["tramo", "instrument_class"], values="neto",
                   aggfunc="sum", fill_value=0)
r = pd.DataFrame(index=p.index.astype(int))
for tramo in ["antes", "desde"]:
    c = p.get((tramo, "C"), pd.Series(0, index=p.index)).values
    pp = p.get((tramo, "P"), pd.Series(0, index=p.index)).values
    r[f"{tramo}_calls"], r[f"{tramo}_puts"], r[f"{tramo}_total"] = c, pp, c + pp
    r[f"dealer_{tramo}"] = [dealer(x) for x in c + pp]
r["dia_total"] = r["antes_total"] + r["desde_total"]
r["dealer_dia"] = [dealer(x) for x in r["dia_total"]]
v = tr.groupby(["strike_price", "tramo"])[["size", "indet"]].sum()
for tramo in ["antes", "desde"]:
    x = v.xs(tramo, level="tramo") if tramo in v.index.get_level_values(1) else None
    r[f"%indet_{tramo}"] = ((x["indet"] / x["size"] * 100).round(0).reindex(p.index).values
                            if x is not None else None)

pd.set_option("display.width", 220)
print(f"\n=== {fecha} | strikes {int(k1)}-{int(k2)} | corte {hora} NY | flujo ESTRICTO del público ===")
print("(neto + = el público compró | dealer: + largo de gamma, - corto)\n")
print(r.to_string())

tr["media_hora"] = tr[ts].dt.floor("30min").dt.strftime("%H:%M")
a = tr.pivot_table(index="media_hora", columns="strike_price", values="neto", aggfunc="sum", fill_value=0)
a.columns = a.columns.astype(int)
print("\n--- Neto (calls + puts) ACUMULADO al cierre de cada media hora ---")
print(a.cumsum().to_string())