"""
Uso:  python scripts/ver_spx_1min.py 2026-09-29
Muestra el SPX estimado (ES - base) en barras de 1 minuto del horario regular.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cero_dte import spx_1min

if len(sys.argv) < 2:
    raise SystemExit("Uso: python scripts/ver_spx_1min.py AAAA-MM-DD")

fecha = sys.argv[1]
df, base = spx_1min(fecha)

print(f"\nBarras en horario regular: {len(df)}")
print(f"Base ES - SPX:             {base:+.2f} puntos")
print(f"SPX apertura (09:30):      {df['spx'].iloc[0]:.2f}")
print(f"SPX cierre   (16:00):      {df['spx'].iloc[-1]:.2f}")
print(f"SPX máximo del día:        {df['spx'].max():.2f}  a las {df['spx'].idxmax():%H:%M}")
print(f"SPX mínimo del día:        {df['spx'].min():.2f}  a las {df['spx'].idxmin():%H:%M}")
print("\nPrimeras barras:")
print(df[["close", "spx", "volume"]].head())
print("\nÚltimas barras:")
print(df[["close", "spx", "volume"]].tail())