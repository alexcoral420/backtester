"""
calendario.py — ¿A qué hora cerró el mercado ese día?

Las SPXW PM liquidan al cierre: 16:00 NY un día normal, 13:00 NY en los cierres tempranos
(día después de Acción de Gracias, Nochebuena...). Con 16:00 fijo, esos días el vencimiento quedaba
mal y la base del ES salía de una barra sin actividad, sin que nada lo avisara (R2 de ODTE.md).

La tabla se escribe a mano por año (fuente: calendario de NYSE/Cboe). Un año sin tabla GRITA:
mejor detenerse a cargarla que suponer 16:00 en un día que cerró a las 13:00.
"""
import pandas as pd

CIERRE_NORMAL = "16:00"
CIERRES_TEMPRANOS = {
    2026: {"2026-11-27": "13:00", "2026-12-24": "13:00"},
}


def hora_cierre(fecha: str) -> str:
    """'HH:MM' (hora NY) del cierre del mercado en `fecha` ('AAAA-MM-DD')."""
    dia = pd.Timestamp(fecha)
    if dia.year not in CIERRES_TEMPRANOS:
        raise ValueError(f"No hay tabla de cierres tempranos para {dia.year}: agregarla en "
                         f"src/odte/calendario.py antes de usar {fecha}")
    return CIERRES_TEMPRANOS[dia.year].get(dia.strftime("%Y-%m-%d"), CIERRE_NORMAL)


def ultima_barra(fecha: str) -> str:
    """'HH:MM' de inicio de la última barra de 1 min de la sesión (la que termina al cierre)."""
    t = pd.Timestamp(f"{fecha} {hora_cierre(fecha)}") - pd.Timedelta(minutes=1)
    return t.strftime("%H:%M")
