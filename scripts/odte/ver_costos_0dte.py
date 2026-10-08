"""
Uso:  python scripts/odte/ver_costos_0dte.py 2026-10-02 [desde] [hasta]
      python scripts/odte/ver_costos_0dte.py 2026-10-02 09:30 11:00

Antes de bajar el tcbbo (lo caro), muestra el rango del SPX en esa franja
y el COSTO de varias ventanas de strikes. No descarga trades.
(Sí baja el catálogo ~$0.03 y el ES ~$0.005, cada uno con confirmación.)
"""
import os
import sys

# scripts/odte/ -> sube 3 niveles hasta la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.precio import spx_1min
from src.odte.trades import costo_tcbbo_0dte

if len(sys.argv) < 2:
    raise SystemExit("Uso: python scripts/odte/ver_costos_0dte.py AAAA-MM-DD [desde HH:MM] [hasta HH:MM]")

fecha = sys.argv[1]
desde = sys.argv[2] if len(sys.argv) > 2 else "09:30"
hasta = sys.argv[3] if len(sys.argv) > 3 else "16:00"

# 1) Precio del SPX en la franja (para centrar la ventana de strikes)
spx, base = spx_1min(fecha)
franja = spx.between_time(desde, hasta)["spx"]
lo, hi = franja.min(), franja.max()
centro = round(((lo + hi) / 2) / 5) * 5            # redondeado al strike de 5 más cercano
print(f"\nSPX {desde}-{hasta}:  mín {lo:.2f}  máx {hi:.2f}  (rango {hi - lo:.1f} pts)")
print(f"Centro de la ventana: {centro}")

# 2) Costo de varias ventanas, sin descargar nada
print(f"\n{'Ventana':>16s} {'Strikes':>8s} {'Opciones':>9s} {'Costo':>9s}  ¿Cubre el rango?")
for ancho in (15, 25, 40, 60):
    kmin, kmax = centro - ancho, centro + ancho
    sel = seleccionar_0dte(fecha, kmin, kmax)
    costo = costo_tcbbo_0dte(fecha, sel["raw_symbol"].tolist(), desde, hasta)
    cubre = "sí" if (kmin <= lo and kmax >= hi) else "NO"
    print(f"{kmin:>7.0f}-{kmax:<7.0f} {len(sel)//2:>8d} {len(sel):>9d} {costo:>8.2f}$  {cubre}")

print("\nElige la ventana y descarga con:")
print(f"  python scripts/odte/ver_flujo_0dte.py {fecha} KMIN KMAX   (día completo)")
print("  (si eliges franja horaria, avísame y adapto los scripts de flujo a esa franja)")