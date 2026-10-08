"""
Posicionamiento del dealer en los gamma walls CERCANOS al precio.
Uso:  python scripts/ver_walls.py 2026-09-24 261016
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from src.datos import precio_spx, descargar_cadena
from src.gex import construir_cadena, gamma_walls
from src.trade_sign import simbolos_de_wall, clasificar_flujo, flujo_neto


def main():
    fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
    vencimiento = sys.argv[2] if len(sys.argv) > 2 else "261016"
    pct = float(sys.argv[3]) if len(sys.argv) > 3 else 0.035
    fecha_fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    S = precio_spx(fecha)
    print(f"SPX: {S:.0f}  |  vencimiento: {vencimiento}\n")

    # Descargar la cadena UNA VEZ
    cadena = construir_cadena(fecha, S)
    precios_crudos, _ = descargar_cadena(fecha)

    arriba, abajo = gamma_walls(cadena, S, n=5)
    walls = list(arriba["nivel"]) + list(abajo["nivel"])

    # FILTRO: solo walls cercanos (dentro del 2% del precio)
    rango = S * pct
    walls_cercanos = [w for w in walls if abs(w - S) <= rango]

    print("=== POSICIONAMIENTO DEL DEALER (walls cercanos) ===\n")
    for strike in sorted(walls_cercanos, reverse=True):
        simbolos = simbolos_de_wall(precios_crudos, strike, vencimiento)
        if not simbolos:
            print(f"Wall {strike:.0f}: sin opciones en este vencimiento\n")
            continue

        t = clasificar_flujo(fecha, fecha_fin, simbolos)
        f_call = flujo_neto(t[t["tipo"] == "C"])
        f_put = flujo_neto(t[t["tipo"] == "P"])
        neto = f_call + f_put

        pos = "resistencia" if strike > S else "soporte"
        print(f"Wall {strike:.0f} [{pos}]:")
        print(f"   CALL: {f_call:+d}  ({'short' if f_call>0 else 'long'})")
        print(f"   PUT:  {f_put:+d}  ({'short' if f_put>0 else 'long'})")
        print(f"   NETO: {neto:+d}  -> {'TRAMPOLÍN' if neto>0 else 'BARRERA'}\n")


if __name__ == "__main__":
    main()