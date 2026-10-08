"""
Uso:  python scripts/odte/ver_trades_0dte.py 2026-09-29 7600 7750
Baja e inspecciona los trades (tcbbo) de las 0DTE con strike en ese rango.
"""
import os
import sys

# scripts/odte/ -> sube 3 niveles hasta la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.trades import descargar_tcbbo_0dte

if len(sys.argv) < 4:
    raise SystemExit("Uso: python scripts/odte/ver_trades_0dte.py AAAA-MM-DD STRIKE_MIN STRIKE_MAX")

fecha = sys.argv[1]
kmin, kmax = float(sys.argv[2]), float(sys.argv[3])

sel = seleccionar_0dte(fecha, kmin, kmax)
print(f"\nOpciones seleccionadas: {len(sel)} "
      f"({(sel['instrument_class'] == 'C').sum()} calls, {(sel['instrument_class'] == 'P').sum()} puts)")

trades = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())

# Unimos con el catálogo para tener tipo (C/P) y strike en cada trade
trades = trades.reset_index().merge(
    sel[["raw_symbol", "instrument_class", "strike_price"]],
    left_on="symbol", right_on="raw_symbol", how="left",
).set_index("ts_recv")

print(f"\nTrades totales:     {len(trades):,}")
print(f"Contratos totales:  {trades['size'].astype('int64').sum():,}")
print(f"Primer trade:       {trades.index.min():%H:%M:%S}")
print(f"Último trade:       {trades.index.max():%H:%M:%S}")

print("\nContratos por tipo:")
print(trades.groupby("instrument_class")["size"].sum())

print("\nTop 10 strikes por contratos (tipo, strike):")
top = trades.groupby(["instrument_class", "strike_price"])["size"].sum().sort_values(ascending=False)
print(top.head(10))

print("\nContratos por hora:")
print(trades["size"].astype("int64").groupby(trades.index.hour).sum())

# Chequeo de calidad: trades exactamente en el punto medio (no clasificables)
medio = (trades["bid_px_00"] + trades["ask_px_00"]) / 2
en_medio = (trades["price"] == medio).mean()
print(f"\n% de trades exactamente en el punto medio: {en_medio:.1%}")