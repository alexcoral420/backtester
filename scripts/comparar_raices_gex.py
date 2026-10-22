"""
Uso:  python scripts/comparar_raices_gex.py 2026-10-16 2026-10-19 ...

¿Qué cambia al sumar las SPXW (diarias/semanales PM) al GEX? Método mid_forward, tres configuraciones
para separar los dos efectos:
  A  SPX        plazo dias   = el default de siempre
  B  SPX        plazo horas  = solo el efecto de medir T con la hora de vencimiento
  C  SPX+SPXW   plazo horas  = el efecto de las SPXW
Por fecha: GEX total, IV nan por raíz, de dónde sale el GEX de C (raíz x plazo), y los 10 niveles
de A y C (niveles_gamma, por magnitud). Los signos son SUPUESTOS (hipótesis nula) en las tres.
Cadenas en caché: $0. Las que falten (SPXW casi siempre): UNA confirmación con el costo total
(~$0,46 por día de SPXW, consultado el 22-oct).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import asegurar_cadenas, precio_spx
from src.gex import construir_cadena, gex_por_plazo, gex_total, niveles_gamma

CONFIGS = {"A": (("SPX",), "dias"), "B": (("SPX",), "horas"), "C": (("SPX", "SPXW"), "horas")}

fechas = sys.argv[1:]
if not fechas:
    raise SystemExit("Uso: python scripts/comparar_raices_gex.py AAAA-MM-DD [AAAA-MM-DD ...]")
asegurar_cadenas(fechas, ("SPX", "SPXW"))                  # UNA sola confirmación de costo
pd.set_option("display.width", 200)

resumen = []
for fecha in fechas:
    S = precio_spx(fecha)
    print(f"\n=== {fecha} | SPX {S:.2f} ===")
    cadenas = {k: construir_cadena(fecha, S, raices=r, plazo=p) for k, (r, p) in CONFIGS.items()}
    fila = {"fecha": fecha}
    for k, c in cadenas.items():
        fila[k] = gex_total(c) / 1e9
        nan_iv = c.groupby("raiz")["iv"].apply(lambda s: f"{s.isna().mean() * 100:.0f}%").to_dict()
        print(f"  {k} {'+'.join(CONFIGS[k][0]):8s} {CONFIGS[k][1]:5s} GEX ${fila[k]:+7.2f}B | "
              f"opciones {len(c):6,d} | IV nan {nan_iv}")
    resumen.append(fila)

    print("\n  C: GEX por raíz y plazo ($B)")
    print((gex_por_plazo(cadenas["C"]) / 1e9).round(2).to_string().replace("\n", "\n    ").join(["    ", ""]))

    cols = ["nivel", "posicion", "gex_neto", "pct_abs", "signo_supuesto", "dominante"]
    for k in ("A", "C"):
        v = niveles_gamma(cadenas[k].dropna(subset=["gex_contrib"]), S, n=10)[cols]
        v["gex_neto"] = v["gex_neto"] / 1e9
        print(f"\n  {k}: 10 niveles por magnitud (gex_neto en $B)")
        print(v.round(2).to_string(index=False).replace("\n", "\n    ").join(["    ", ""]))

print("\n=== Resumen: GEX total ($B) por configuración ===")
r = pd.DataFrame(resumen).set_index("fecha")
r["C-A"] = r["C"] - r["A"]
r["signo cambia"] = (r["A"] > 0) != (r["C"] > 0)
print(r.round(2).to_string())
