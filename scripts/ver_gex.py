
"""
Ver el GEX y los gamma walls de un día.
Uso:  python scripts/ver_gex.py 2026-09-24
"""
import sys
import os
# Agregar la raíz del proyecto a las rutas de búsqueda
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.datos import precio_spx
from src.gex import construir_cadena, gex_total, gamma_walls


def main():
    # La fecha se pasa como argumento, o usa una por defecto
    fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"

    print(f"Calculando GEX para {fecha}...")
    S = precio_spx(fecha)
    print(f"SPX ese día: {S:.0f}")

    cadena = construir_cadena(fecha, S)
    gex = gex_total(cadena)

    print(f"\nGEX total: ${gex/1e9:+.2f}B", end="  ")
    print("(POSITIVO: rango/estabilizador)" if gex > 0 else "(NEGATIVO: amplificador/explosivo)")

    arriba, abajo = gamma_walls(cadena, S)
    print("\n=== RESISTENCIAS (gamma walls arriba) ===")
    print(arriba.to_string(index=False))
    print("\n=== SOPORTES/PRECIPICIOS (abajo) ===")
    print(abajo.to_string(index=False))


if __name__ == "__main__":
    main()