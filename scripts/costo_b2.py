"""
Uso:  python scripts/costo_b2.py 2026-09-24 2026-10-08

SOLO CONSULTA el costo (get_cost) de los trades con bid/ask (tcbbo) para B2. NO descarga nada.
Tres niveles, cada uno con su costo por separado, para decidir con números reales:

  NIVEL 1 (prioridad absoluta): puts de los soportes más cercanos, venc. oct-16 / nov-20 / dic-18.
  NIVEL 2 (test de verticales):  pares de strikes vecinos de diciembre abiertos los mismos días.
  NIVEL 3 (secundaria completa): puts de arriba, las series que cubren el 80% del |ΔOI| de cada zona.

Días de flujo: por la regla de tiempo, el ΔOI de los archivos (d) se explica con el flujo de d-1,
así que se consultan los días de mercado ANTERIORES a cada archivo con OI del rango.
Ventana por día: sesión regular 9:30-16:15 hora de Nueva York (sin la sesión nocturna).
"""
import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import CARPETA_CACHE, _cliente, ruta_cadena
from src.inventario import delta_oi, fecha_flujo, oi_por_fecha

NY = "America/New_York"
NIVEL1 = {"strikes": [7650, 7600, 7500, 7400], "vencs": ["2026-10-16", "2026-11-20", "2026-12-18"]}
NIVEL2 = [(7795, 7805), (7845, 7855)]                      # pares vecinos, diciembre
NIVEL3_ZONAS = [7900, 7850, 7800]
VENC_N2 = "2026-12-18"

if len(sys.argv) < 3:
    raise SystemExit("Uso: python scripts/costo_b2.py INICIO FIN   (desde la raíz del proyecto)")
inicio, fin = pd.to_datetime(sys.argv[1]), pd.to_datetime(sys.argv[2])
fechas = sorted(os.path.basename(p)[-18:-8] for p in glob.glob(os.path.join(CARPETA_CACHE, "cadena_SPX_statistics_*.parquet")))
fechas = [f for f in fechas if inicio <= pd.to_datetime(f) <= fin and os.path.exists(ruta_cadena("SPX", "ohlcv-1d", f))]
dias_flujo = sorted({fecha_flujo(f, fechas) for f in fechas[1:]})
print(f"Días de flujo a consultar ({len(dias_flujo)}): {', '.join(d.strftime('%m-%d') for d in dias_flujo)}")

t = delta_oi(oi_por_fecha(fechas))
ult = t[t["fecha"] == t["fecha"].max()]
puts = ult[ult["tipo"] == "P"]


def simbolos(strikes, vencs):
    s = puts[puts["strike"].isin(strikes) & puts["venc"].isin(pd.to_datetime(vencs))]
    return sorted(s["symbol"].unique())


n1 = simbolos(NIVEL1["strikes"], NIVEL1["vencs"])
n2 = simbolos([k for par in NIVEL2 for k in par], [VENC_N2])

cambios = t[t["delta_oi"].notna() & (t["delta_oi"] != 0) & (t["tipo"] == "P")].copy()
cambios["zona"] = (cambios["strike"] / 25).round() * 25
n3 = []
for zona in NIVEL3_ZONAS:
    s = (cambios[cambios["zona"] == zona].groupby("symbol")["delta_oi"].apply(lambda x: x.abs().sum())
         .sort_values(ascending=False))
    acum = s.cumsum() / s.sum()
    n3 += list(s[acum.shift(fill_value=0) < 0.80].index)
n3 = sorted(set(n3) - set(n2))                              # lo del nivel 2 no se cuenta dos veces

cliente = _cliente()


def costo(simb):
    total = 0.0
    for d in dias_flujo:
        ini = pd.Timestamp(f"{d:%Y-%m-%d} 09:30", tz=NY).isoformat()
        fin_d = pd.Timestamp(f"{d:%Y-%m-%d} 16:15", tz=NY).isoformat()
        total += cliente.metadata.get_cost(dataset="OPRA.PILLAR", symbols=simb, stype_in="raw_symbol",
                                           schema="tcbbo", start=ini, end=fin_d)
    return total


print("\n=== Costo estimado (get_cost, sin descargar) ===")
for nombre, simb in [("NIVEL 1  soportes cercanos", n1), ("NIVEL 2  test de verticales", n2),
                     ("NIVEL 3  secundaria completa", n3)]:
    if not simb:
        print(f"  {nombre}: sin series")
        continue
    c = costo(simb)
    print(f"  {nombre}: {len(simb):2d} series x {len(dias_flujo)} días -> ${c:.2f}")
    for s in simb:
        print(f"      {s}")
print("\nNada se descargó. La compra se hace en otro paso, nivel por nivel, con su confirmación.")