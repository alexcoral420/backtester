"""
Ver el trade sign (flujo del dealer) de las opciones ATM de un día.
Uso:  python scripts/ver_tradesign.py 2026-09-24 261016
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from src.datos import precio_spx
from src.trade_sign import elegir_atm, clasificar_flujo, flujo_neto


def main():
    fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
    vencimiento = sys.argv[2] if len(sys.argv) > 2 else "261016"
    fecha_fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Trade sign para {fecha} (vencimiento {vencimiento})...")
    S = precio_spx(fecha)
    print(f"SPX: {S:.0f}")

    simbolos = elegir_atm(fecha, S, vencimiento, n_strikes=3)
    t = clasificar_flujo(fecha, fecha_fin, simbolos)

    calls = t[t["tipo"] == "C"]
    puts = t[t["tipo"] == "P"]
    print(f"\nTotal de trades: {len(t)}")
    print(f"Flujo neto CALLS: {flujo_neto(calls):+d}  ({'dealer short' if flujo_neto(calls)>0 else 'dealer long'})")
    print(f"Flujo neto PUTS:  {flujo_neto(puts):+d}  ({'dealer short' if flujo_neto(puts)>0 else 'dealer long'})")


if __name__ == "__main__":
    main()