"""
Uso:  python scripts/ver_sesgo_0dte.py 2026-09-29 7600 7750
Control de sesgo del trade sign (todo desde caché, sin costo):
  1) Compras vs ventas por TAMAÑO de trade (retail chico vs bloques grandes)
  2) DÓNDE se imprimió cada trade respecto al bid/ask (detecta spreads / órdenes complejas)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cero_dte import seleccionar_0dte, descargar_tcbbo_0dte, clasificar_trades

if len(sys.argv) < 4:
    raise SystemExit("Uso: python scripts/ver_sesgo_0dte.py AAAA-MM-DD STRIKE_MIN STRIKE_MAX")

fecha = sys.argv[1]
kmin, kmax = float(sys.argv[2]), float(sys.argv[3])

sel = seleccionar_0dte(fecha, kmin, kmax)
trades = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")

clas = clasificar_trades(trades)
clas["size"] = clas["size"].astype("int64")

# ------------------------------------------------------------
# 1) Por tamaño de trade
# ------------------------------------------------------------
cortes = [0, 10, 49, 99, float("inf")]
etiquetas = ["1-10 (retail)", "11-49", "50-99", "100+ (bloques)"]
clas["tamano"] = pd.cut(clas["size"], bins=cortes, labels=etiquetas)


def resumen_grupo(g: pd.DataFrame) -> pd.Series:
    n = len(g)
    return pd.Series({
        "trades": n,
        "%compra": (g["signo"] == 1).mean() * 100,
        "%venta": (g["signo"] == -1).mean() * 100,
        "%medio": (g["signo"] == 0).mean() * 100,
        "contratos": g["size"].sum(),
        "flujo_neto": g["flujo"].sum(),
    })


pd.set_option("display.width", 140)
pd.set_option("display.float_format", "{:,.1f}".format)

for tipo, nombre in [("C", "CALLS"), ("P", "PUTS")]:
    sub = clas[clas["instrument_class"] == tipo]
    tabla = sub.groupby("tamano", observed=True).apply(resumen_grupo)
    tabla[["trades", "contratos", "flujo_neto"]] = tabla[["trades", "contratos", "flujo_neto"]].astype("int64")
    print(f"\n=== {nombre}: compras vs ventas por tamaño de trade ===")
    print(tabla)

# ------------------------------------------------------------
# 2) Dónde se imprimió el trade respecto al bid/ask
# ------------------------------------------------------------
p = clas["price"].round(4)
bid = clas["bid_px_00"].round(4)
ask = clas["ask_px_00"].round(4)
medio = ((clas["bid_px_00"] + clas["ask_px_00"]) / 2).round(4)

ubicacion = pd.Series("??", index=clas.index)
ubicacion[p < bid] = "1 bajo el bid"
ubicacion[p == bid] = "2 en el bid"
ubicacion[(p > bid) & (p < medio)] = "3 entre bid y medio"
ubicacion[p == medio] = "4 en el medio"
ubicacion[(p > medio) & (p < ask)] = "5 entre medio y ask"
ubicacion[p == ask] = "6 en el ask"
ubicacion[p > ask] = "7 sobre el ask"
clas["ubicacion"] = ubicacion

tabla_ub = clas.groupby("ubicacion").agg(trades=("size", "size"), contratos=("size", "sum"))
tabla_ub["%trades"] = tabla_ub["trades"] / tabla_ub["trades"].sum() * 100
tabla_ub["%contratos"] = tabla_ub["contratos"] / tabla_ub["contratos"].sum() * 100
print("\n=== Dónde se imprimió cada trade (calls y puts juntos) ===")
print(tabla_ub)

fuera = ((p < bid) | (p > ask)).mean() * 100
print(f"\nTrades FUERA del bid/ask: {fuera:.1f}%  "
      "(alto = muchas órdenes complejas/spreads, que la regla del medio clasifica mal)")