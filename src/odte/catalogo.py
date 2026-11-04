"""
catalogo.py — ¿Qué opciones SPXW existían un día y cuáles eran 0DTE?
Fuente: schema `definition` de Databento.
"""
import os

import pandas as pd

from src import datos
from src.simbolos import parsear_simbolos
from .calendario import hora_cierre
from .constantes import CARPETA_CACHE, DATASET, RAIZ, ZONA_NY


def ruta_definicion(fecha: str) -> str:
    return os.path.join(CARPETA_CACHE, f"definicion_SPXW_{fecha}.parquet")


def parametros_definicion(fecha: str) -> dict:
    """El día completo (end es exclusivo, por eso +1 día). "parent" = toda la familia SPXW."""
    fin = (pd.Timestamp(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return dict(dataset=DATASET, symbols=RAIZ, stype_in="parent", schema="definition",
                start=fecha, end=fin)


def pedidos_definicion(fechas) -> list:
    """Pedidos para datos.asegurar_descargas (el definition se guarda tal cual llega)."""
    return [(ruta_definicion(f), parametros_definicion(f), lambda df: df) for f in fechas]


def descargar_definicion(fecha: str) -> pd.DataFrame:
    """
    El CATÁLOGO de opciones SPXW que existían en `fecha` ('AAAA-MM-DD').
    Caché primero; si falta, costo + confirmación (datos.asegurar_descargas).
    """
    datos.asegurar_descargas(pedidos_definicion([fecha]), f"definition SPXW {fecha}")
    return pd.read_parquet(ruta_definicion(fecha))


def filtrar_0dte(df: pd.DataFrame, fecha: str) -> pd.DataFrame:
    """
    Se queda solo con las opciones cuyo vencimiento cae en `fecha` (hora de Nueva York).
    """
    df = df.copy()
    # La columna `expiration` de Databento es una CONVENCIÓN (medianoche UTC), no la hora real.
    # Fuente de verdad: la fecha dentro del símbolo. 'SPXW  261001P03400000' -> '261001'
    df["fecha_venc"] = parsear_simbolos(df["raw_symbol"])["venc"].dt.date
    objetivo = pd.Timestamp(fecha).date()
    df = df[df["fecha_venc"] == objetivo].copy()

    # Hora REAL de liquidación de las SPXW: el cierre de ese día en Nueva York (16:00, o 13:00 en
    # los cierres tempranos). La fijamos nosotros desde calendario.py.
    df["venc_ny"] = pd.Timestamp(f"{fecha} {hora_cierre(fecha)}", tz=ZONA_NY)
    return df


def seleccionar_0dte(fecha: str, strike_min: float, strike_max: float) -> pd.DataFrame:
    """Las 0DTE de `fecha` con strike dentro de [strike_min, strike_max]."""
    catalogo = descargar_definicion(fecha)
    odte = filtrar_0dte(catalogo, fecha)
    sel = odte[(odte["strike_price"] >= strike_min) & (odte["strike_price"] <= strike_max)]
    return sel[["raw_symbol", "instrument_class", "strike_price", "venc_ny"]].reset_index(drop=True)


def resumen(df_todo: pd.DataFrame, df_0dte: pd.DataFrame) -> None:
    """Imprime el catálogo de forma legible."""
    print("\n=== CATÁLOGO SPXW ===")
    print(f"Filas totales:              {len(df_todo)}")
    print(f"Símbolos únicos:            {df_todo['raw_symbol'].nunique()}")
    print(f"Vencimientos distintos:     {df_todo['expiration'].nunique()}")

    print("\n=== 0DTE (vencen hoy) ===")
    if df_0dte.empty:
        print("¡No hay 0DTE para esta fecha! (¿fin de semana, feriado o fecha sin datos?)")
        return
    unicas = df_0dte.drop_duplicates("raw_symbol")
    print(f"Opciones 0DTE únicas:       {len(unicas)}")
    print(f"  Calls: {(unicas['instrument_class'] == 'C').sum()}")
    print(f"  Puts:  {(unicas['instrument_class'] == 'P').sum()}")
    print(f"Strike mínimo:              {unicas['strike_price'].min()}")
    print(f"Strike máximo:              {unicas['strike_price'].max()}")
    print(f"Hora de vencimiento (NY):   {unicas['venc_ny'].iloc[0]}")