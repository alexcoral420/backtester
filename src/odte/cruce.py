"""
cruce.py — ¿Cuándo llegó el precio al strike?

Para la pregunta "¿qué posición tenía el dealer CUANDO llegó el precio?" solo vale el flujo previo:
el flujo del día completo mezcla lo de antes y lo de después de que el precio tocara el strike.

Primer cruce = la primera barra de 1 min cuyo lado (arriba/abajo del strike) difiere del lado de la
primera barra del día. "Arriba" es estrictamente > strike. Cuentan como "antes" los trades con
timestamp < inicio de esa barra (conservador: el minuto del cruce queda fuera).

Strike NUNCA cruzado -> el corte es la MÁXIMA APROXIMACIÓN: el minuto del mínimo del día si el strike
está debajo del precio, o del máximo si está encima. Así no se cuela el flujo posterior al giro
(caso 7690 del 14-oct: +5 antes del mínimo de las 14:01, -1.594 en el día completo).
"""
import pandas as pd


def corte_strike(dia: pd.Series, strike: float) -> tuple[pd.Timestamp, str]:
    """dia: SPX por minuto (índice = inicio de cada barra, hora NY). Devuelve (corte, etiqueta):
    'HH:MM' si se cruzó, 'nunca (aprox HH:MM)' si no."""
    if dia.empty:
        raise ValueError("serie de precios vacía: no hay sesión para cortar")
    if not dia.index.is_monotonic_increasing:
        raise ValueError("la serie de precios debe estar ordenada en el tiempo")
    arriba = dia > strike
    cambio = arriba[arriba != arriba.iloc[0]]
    if len(cambio):
        return cambio.index[0], cambio.index[0].strftime("%H:%M")
    t0 = dia.idxmin() if arriba.iloc[0] else dia.idxmax()
    return t0, f"nunca (aprox {t0:%H:%M})"
