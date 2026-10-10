"""
Uso:  python scripts/costo_cadena.py 2026-09-24

SOLO consulta el costo de la cadena de un día (no descarga nada, no gasta crédito).
Es lo mismo que baja descargar_cadena: ohlcv-1d (precios) + statistics (open interest),
para la familia SPX (mensuales AM) y para SPXW (diarias/semanales PM).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import databento as db
from config import DATABENTO_KEY

if len(sys.argv) < 2:
    raise SystemExit("Uso: python scripts/costo_cadena.py AAAA-MM-DD")

fecha = sys.argv[1]
fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
cliente = db.Historical(DATABENTO_KEY)

print(f"Costo de la cadena del {fecha} (consulta, sin descargar):\n")
total = 0.0
for raiz in ["SPX", "SPXW"]:
    for schema in ["ohlcv-1d", "statistics"]:
        costo = cliente.metadata.get_cost(
            dataset="OPRA.PILLAR", symbols=[f"{raiz}.OPT"], stype_in="parent",
            schema=schema, start=fecha, end=fin)
        total += costo
        print(f"  {raiz:5s} {schema:11s} ${costo:.4f}")
print(f"\n  Total SPX + SPXW: ${total:.4f}")
print("  (ver_gex.py actual baja solo SPX: suma las dos filas de SPX)")