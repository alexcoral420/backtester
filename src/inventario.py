"""
inventario.py — Fase B1: el OI acumulado por strike y su cambio día a día. NEUTRAL respecto al signo.

Mide CUÁNTO cambió el inventario, no QUIÉN lo movió (eso es B2, con la clasificación estricta).
Solo lee cadenas ya en caché: costo $0.

Conceptos:
  - OI (open interest) = contratos abiertos de una opción. Es el inventario total, sin dirección.
  - ΔOI = OI de hoy - OI del día anterior DE LA SERIE = posiciones abiertas (+) o cerradas (-).
  - Una opción que aparece por primera vez en la serie se marca 'nueva' (su ΔOI no es comparable).

REGLA DE TIEMPO (CONFIRMADA el 15-oct con 24-sep..8-oct, 24.087 cambios de OI):
el OI del archivo del día d es el de la MAÑANA de d = posiciones al cierre de d-1.
  |ΔOI(d)| vs volumen de d-1: Spearman +0,82 | vs volumen de d: +0,36
  8.173 opciones cambiaron de OI sin un solo contrato negociado el día d.
=> El ΔOI del archivo del día d se explica con el flujo del día de mercado ANTERIOR (fecha_flujo).
Consecuencia: la cadena del día d trae precios de d con OI de d-1, que es justo lo disponible al
cierre de d (el OI de d sale a la mañana siguiente): los backtests no usaron información futura.
"""
import pandas as pd

from src.datos import descargar_cadena
from src.simbolos import parsear_simbolos


def oi_por_fecha(fechas, raices=("SPX",)):
    """Tabla larga: una fila por (fecha, opción) con su OI. Columnas:
    fecha, symbol, raiz, venc, tipo, strike, oi."""
    partes = []
    for f in fechas:
        _, oi = descargar_cadena(f, raices)
        d = oi.rename(columns={"open_interest": "oi"}).copy()
        d["fecha"] = pd.to_datetime(f)
        partes.append(d)
    t = pd.concat(partes, ignore_index=True)
    info = parsear_simbolos(t["symbol"])
    return t.join(info[["raiz", "venc", "tipo", "strike"]])


def delta_oi(tabla):
    """Agrega delta_oi (cambio contra la fecha ANTERIOR de la serie para la misma opción) y 'nueva'.
    La primera fecha de la serie no tiene delta (nan)."""
    t = tabla.sort_values(["symbol", "fecha"]).copy()
    fechas = sorted(t["fecha"].unique())
    anterior = dict(zip(fechas[1:], fechas[:-1]))
    previo = t[["symbol", "fecha", "oi"]].rename(columns={"oi": "oi_prev", "fecha": "fecha_prev"})
    t["fecha_prev"] = t["fecha"].map(anterior)
    t = t.merge(previo, on=["symbol", "fecha_prev"], how="left")
    t["nueva"] = t["fecha_prev"].notna() & t["oi_prev"].isna()
    t["delta_oi"] = t["oi"] - t["oi_prev"]
    return t.drop(columns="fecha_prev")


def por_zona(tabla, banda=25):
    """Suma por fecha, zona de strike (misma banda que gamma_walls) y tipo: oi y delta_oi."""
    t = tabla.copy()
    t["zona"] = (t["strike"] / banda).round() * banda
    return t.groupby(["fecha", "zona", "tipo"], as_index=False)[["oi", "delta_oi"]].sum(min_count=1)


def fecha_flujo(fecha_oi, dias_mercado):
    """Día de mercado cuyo flujo explica el ΔOI del archivo del día fecha_oi = el día de mercado
    ANTERIOR (regla de tiempo confirmada). dias_mercado: los días hábiles reales (feriados fuera).
    Si fecha_oi es el primer día de la lista, no hay día anterior conocido -> ValueError (grita)."""
    dias = sorted(pd.to_datetime(list(dias_mercado)))
    f = pd.to_datetime(fecha_oi)
    previos = [d for d in dias if d < f]
    if not previos:
        raise ValueError(f"No hay día de mercado anterior a {f:%Y-%m-%d} en la lista: no se puede emparejar.")
    return previos[-1]