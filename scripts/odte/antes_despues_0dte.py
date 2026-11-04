"""
Uso:  python scripts/odte/antes_despues_0dte.py 2026-10-14 7675 7795 14:01
      python scripts/odte/antes_despues_0dte.py 2026-10-14 7675 7795 14:01 7680 7700   (solo esos strikes)

Flujo ESTRICTO 0DTE por strike cortado a una HORA (todo desde caché, $0).
KMIN KMAX = los MISMOS de la descarga original (la caché se identifica por la lista de símbolos).
Por strike: calls/puts netos ANTES y DESDE la hora, neto total y signo del dealer medido en cada tramo
(público vende -> dealer + | compra -> dealer -), con el veredicto de src/odte/veredicto.py:
|neto| < MIN_ABS -> "sin evidencia"; lo indeterminado alcanza para invertirlo -> "indet. domina".
Cada signo lleva su % indeterminado al lado.
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
from src.odte.veredicto import pct_indet, signo_dealer, volumenes

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


def veredictos(v):
    """Signo del dealer y % indeterminado de cada fila de un cuadro compra/venta/indet."""
    pct = [pct_indet(*x) for x in v.itertuples(index=False)]
    return ([signo_dealer(*x) for x in v.itertuples(index=False)],
            [None if q != q else round(q) for q in pct])


p = tr.pivot_table(index="strike_price", columns=["tramo", "instrument_class"], values="neto",
                   aggfunc="sum", fill_value=0)
vol = volumenes(tr, ["strike_price", "tramo"])
r = pd.DataFrame(index=p.index.astype(int))
for tramo in ["antes", "desde"]:
    c = p.get((tramo, "C"), pd.Series(0, index=p.index)).values
    pp = p.get((tramo, "P"), pd.Series(0, index=p.index)).values
    r[f"{tramo}_calls"], r[f"{tramo}_puts"], r[f"{tramo}_total"] = c, pp, c + pp
    vt = (vol.xs(tramo, level="tramo") if tramo in vol.index.get_level_values("tramo")
          else vol.iloc[0:0]).reindex(p.index, fill_value=0)
    r[f"dealer_{tramo}"], r[f"%indet_{tramo}"] = veredictos(vt)
r["dia_total"] = r["antes_total"] + r["desde_total"]
r["dealer_dia"], r["%indet_dia"] = veredictos(vol.groupby(level="strike_price").sum().reindex(p.index, fill_value=0))
r = r[["antes_calls", "antes_puts", "antes_total", "dealer_antes", "%indet_antes",
       "desde_calls", "desde_puts", "desde_total", "dealer_desde", "%indet_desde",
       "dia_total", "dealer_dia", "%indet_dia"]]

pd.set_option("display.width", 220)
print(f"\n=== {fecha} | strikes {int(k1)}-{int(k2)} | corte {hora} NY | flujo ESTRICTO del público ===")
print("(neto + = el público compró | dealer: + largo de gamma, - corto)\n")
print(r.to_string())

tr["media_hora"] = tr[ts].dt.floor("30min").dt.strftime("%H:%M")
a = tr.pivot_table(index="media_hora", columns="strike_price", values="neto", aggfunc="sum", fill_value=0)
a.columns = a.columns.astype(int)
print("\n--- Neto (calls + puts) ACUMULADO al cierre de cada media hora ---")
print(a.cumsum().to_string())