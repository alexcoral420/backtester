"""
catalogo.py — ¿Qué opciones SPXW existían un día y cuáles eran 0DTE?
Fuente: schema `definition` de Databento.
"""
import os
from datetime import datetime, timedelta

import databento as db
import pandas as pd

from config import DATABENTO_KEY
from .constantes import CARPETA_CACHE, DATASET, RAIZ, ZONA_NY


def descargar_definicion(fecha: str) -> pd.DataFrame:
    """
    Baja el CATÁLOGO de opciones SPXW que existían en `fecha` (formato 'AAAA-MM-DD').
    Usa caché: si ya se descargó antes, lo lee del disco y no vuelve a pagar.
    """
    ruta = os.path.join(CARPETA_CACHE, f"definicion_SPXW_{fecha}.parquet")

    # 1) Si ya existe en disco -> usarlo (adquisición una vez, uso muchas)
    if os.path.exists(ruta):
        print(f"[caché] leyendo {ruta}")
        return pd.read_parquet(ruta)

    # 2) Rango: el día pedido completo (end es exclusivo, por eso +1 día)
    inicio = fecha
    fin = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    cliente = db.Historical(DATABENTO_KEY)
    parametros = dict(
        dataset=DATASET,
        symbols=RAIZ,
        stype_in="parent",     # "parent" = traer toda la familia sin listar cada símbolo
        schema="definition",
        start=inicio,
        end=fin,
    )

    # 3) Ver el costo ANTES de pagar
    costo = cliente.metadata.get_cost(**parametros)
    print(f"Costo estimado: ${costo:.4f}")
    if input("¿Descargar? (s/n): ").strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")

    # 4) Descargar con protección ante los timeouts 504 de Databento
    try:
        df = cliente.timeseries.get_range(**parametros).to_df()
    except Exception as e:
        raise RuntimeError(f"Falló la descarga del definition: {e}")

    os.makedirs(CARPETA_CACHE, exist_ok=True)
    df.to_parquet(ruta)
    print(f"[guardado] {ruta} ({len(df)} filas)")
    return df


def filtrar_0dte(df: pd.DataFrame, fecha: str) -> pd.DataFrame:
    """
    Se queda solo con las opciones cuyo vencimiento cae en `fecha` (hora de Nueva York).
    """
    df = df.copy()
    # La columna `expiration` de Databento es una CONVENCIÓN (medianoche UTC), no la hora real.
    # Fuente de verdad: la fecha dentro del símbolo. 'SPXW  261001P03400000' -> '261001'
    df["fecha_venc"] = pd.to_datetime(
        df["raw_symbol"].str.split().str[1].str[:6], format="%y%m%d"
    ).dt.date
    objetivo = pd.Timestamp(fecha).date()
    df = df[df["fecha_venc"] == objetivo].copy()

    # Hora REAL de liquidación de las SPXW: 16:00 Nueva York. La fijamos nosotros.
    df["venc_ny"] = pd.Timestamp(f"{fecha} 16:00", tz=ZONA_NY)
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