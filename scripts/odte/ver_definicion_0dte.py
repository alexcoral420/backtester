"""
Uso:  python scripts/odte/ver_definicion_0dte.py 2026-09-15
Muestra qué opciones SPXW existían ese día y cuáles eran 0DTE.
"""
import os
import sys

# scripts/odte/ -> sube 3 niveles hasta la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import descargar_definicion, filtrar_0dte, resumen

if len(sys.argv) < 2:
    raise SystemExit("Uso: python scripts/odte/ver_definicion_0dte.py AAAA-MM-DD")

fecha = sys.argv[1]
df_todo = descargar_definicion(fecha)

# Mostramos las columnas una vez, para verificar nombres y escalas reales
print("Columnas disponibles:", list(df_todo.columns))

df_0dte = filtrar_0dte(df_todo, fecha)
resumen(df_todo, df_0dte)