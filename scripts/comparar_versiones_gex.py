"""
Uso:  python scripts/comparar_versiones_gex.py 2026-09-24 2026-09-29 2026-10-02 ...

Corre gex.py con los dos métodos en cada fecha y compara:
  - GEX total y su signo ("ultimo_trade" = el original, "mid_forward" = versión C con forward)
  - walls arriba/abajo de cada método, y qué niveles aparecen o desaparecen al cambiar
Fechas en caché: $0. Fechas nuevas: la descarga pide confirmación de costo (~$0,19 por día).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import precio_spx
from src.gex import construir_cadena, gamma_walls, gex_total

fechas = sys.argv[1:] or ["2026-09-24"]
resumen = []

for fecha in fechas:
    S = precio_spx(fecha)
    print(f"\n=== {fecha} | SPX {S:.2f} ===")
    walls = {}
    for metodo in ["ultimo_trade", "mid_forward"]:
        c = construir_cadena(fecha, S, metodo=metodo)
        arriba, abajo = gamma_walls(c.dropna(subset=["gex_contrib"]), S, n=5)
        walls[metodo] = (set(arriba["nivel"]), set(abajo["nivel"]))
        g = gex_total(c)
        resumen.append((fecha, metodo, g))
        print(f"  {metodo:13s} GEX ${g / 1e9:+6.2f}B | opciones {len(c):5,d} | "
              f"arriba {[int(x) for x in arriba['nivel']]}  abajo {[int(x) for x in abajo['nivel']]}")
    for i, lado in enumerate(["arriba", "abajo"]):
        viejo, nuevo = walls["ultimo_trade"][i], walls["mid_forward"][i]
        if viejo != nuevo:
            print(f"  {lado:6s}: desaparecen {sorted(int(x) for x in viejo - nuevo)} | "
                  f"aparecen {sorted(int(x) for x in nuevo - viejo)}")
        else:
            print(f"  {lado:6s}: mismos niveles")

print("\n=== Resumen: signo del GEX por método ===")
for fecha in fechas:
    v = {m: g for f, m, g in resumen if f == fecha}
    cambia = "  <- CAMBIA DE SIGNO" if (v["ultimo_trade"] > 0) != (v["mid_forward"] > 0) else ""
    print(f"  {fecha}: viejo ${v['ultimo_trade'] / 1e9:+6.2f}B | nuevo ${v['mid_forward'] / 1e9:+6.2f}B{cambia}")