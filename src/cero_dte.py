"""
cero_dte.py — Todo lo relacionado con opciones 0DTE (vencen el mismo día).
Módulo nuevo: NO modifica gex.py, trade_sign.py ni datos.py.
"""
import hashlib
import os
from datetime import datetime, timedelta

import databento as db
import pandas as pd
import yfinance as yf

from config import DATABENTO_KEY

DATASET = "OPRA.PILLAR"
RAIZ = "SPXW.OPT"            # familia completa de SPXW (vencimientos PM, incluye las diarias)
CARPETA_CACHE = "data/raw"
ZONA_NY = "America/New_York"


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


# ============================================================
# PASO 2 — Precio del SPX minuto a minuto (vía futuro ES)
# ============================================================

def descargar_es_1min(fecha: str) -> pd.DataFrame:
    """
    Barras de 1 minuto del ES (contrato más operado) para `fecha`, solo horario regular NY.
    Caché en data/raw/es_1min_FECHA.parquet.
    """
    ruta = os.path.join(CARPETA_CACHE, f"es_1min_{fecha}.parquet")
    if os.path.exists(ruta):
        print(f"[caché] leyendo {ruta}")
        return pd.read_parquet(ruta)

    fin = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    cliente = db.Historical(DATABENTO_KEY)
    parametros = dict(
        dataset="GLBX.MDP3",       # CME Globex (futuros)
        symbols="ES.v.0",          # continuo: el contrato con más volumen ese día
        stype_in="continuous",
        schema="ohlcv-1m",
        start=fecha,
        end=fin,
    )

    costo = cliente.metadata.get_cost(**parametros)
    print(f"Costo estimado ES: ${costo:.4f}")
    if input("¿Descargar? (s/n): ").strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")

    try:
        df = cliente.timeseries.get_range(**parametros).to_df()
    except Exception as e:
        raise RuntimeError(f"Falló la descarga del ES: {e}")

    # El índice es ts_event (INICIO de cada barra) en UTC -> lo pasamos a Nueva York
    df.index = df.index.tz_convert(ZONA_NY)
    # Horario regular: barras que empiezan entre 09:30 y 15:59 (la de 15:59 cierra a las 16:00)
    df = df.between_time("09:30", "15:59")[["open", "high", "low", "close", "volume"]]

    os.makedirs(CARPETA_CACHE, exist_ok=True)
    df.to_parquet(ruta)
    print(f"[guardado] {ruta} ({len(df)} barras)")
    return df


def cierre_spx(fecha: str) -> float:
    """Cierre oficial diario del SPX (^GSPC) desde yfinance."""
    fin = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    hist = yf.Ticker("^GSPC").history(start=fecha, end=fin)
    if hist.empty:
        raise RuntimeError(f"yfinance no devolvió cierre del SPX para {fecha}")
    return float(hist["Close"].iloc[-1])


def spx_1min(fecha: str) -> tuple[pd.DataFrame, float]:
    """
    SPX estimado minuto a minuto = ES - base.
    base = cierre ES (barra 15:59) - cierre oficial SPX. Se asume constante en el día.
    Devuelve (df con columna 'spx', base).
    """
    es = descargar_es_1min(fecha)
    base = float(es["close"].iloc[-1]) - cierre_spx(fecha)
    df = es.copy()
    df["spx"] = df["close"] - base
    return df, base


# ============================================================
# PASO 3 — Trades (tcbbo) de las 0DTE cercanas al precio
# ============================================================

def seleccionar_0dte(fecha: str, strike_min: float, strike_max: float) -> pd.DataFrame:
    """Las 0DTE de `fecha` con strike dentro de [strike_min, strike_max]."""
    catalogo = descargar_definicion(fecha)
    odte = filtrar_0dte(catalogo, fecha)
    sel = odte[(odte["strike_price"] >= strike_min) & (odte["strike_price"] <= strike_max)]
    return sel[["raw_symbol", "instrument_class", "strike_price", "venc_ny"]].reset_index(drop=True)


def _parametros_tcbbo(fecha: str, simbolos: list[str], desde: str, hasta: str) -> dict:
    """Parámetros de la consulta tcbbo. Horas en NY, convertidas a UTC para la API."""
    return dict(
        dataset=DATASET,
        symbols=simbolos,
        stype_in="raw_symbol",
        schema="tcbbo",
        start=pd.Timestamp(f"{fecha} {desde}", tz=ZONA_NY).tz_convert("UTC"),
        end=pd.Timestamp(f"{fecha} {hasta}", tz=ZONA_NY).tz_convert("UTC"),
    )


def costo_tcbbo_0dte(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> float:
    """Solo CONSULTA el costo (no descarga nada, no gasta crédito)."""
    cliente = db.Historical(DATABENTO_KEY)
    return cliente.metadata.get_cost(**_parametros_tcbbo(fecha, simbolos, desde, hasta))


def ruta_cache_tcbbo(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> str:
    """Ruta del parquet en caché para esta combinación de día, símbolos y franja."""
    huella = hashlib.md5("|".join(sorted(simbolos)).encode()).hexdigest()[:8]
    sufijo = "" if (desde, hasta) == ("09:30", "16:00") else \
        f"_{desde.replace(':', '')}-{hasta.replace(':', '')}"
    return os.path.join(CARPETA_CACHE, f"tcbbo0dte_{fecha}_{huella}{sufijo}.parquet")


def descargar_tcbbo_0dte(fecha: str, simbolos: list[str],
                         desde: str = "09:30", hasta: str = "16:00") -> pd.DataFrame:
    """
    Trades con bid/ask (tcbbo) de los `simbolos` en `fecha`, entre `desde` y `hasta` (hora NY).
    Caché: data/raw/tcbbo0dte_FECHA_HASH[_HHMM-HHMM].parquet
    (sin sufijo = día completo, compatible con lo ya descargado).
    """
    ruta = ruta_cache_tcbbo(fecha, simbolos, desde, hasta)
    if os.path.exists(ruta):
        print(f"[caché] leyendo {ruta}")
        return pd.read_parquet(ruta)

    cliente = db.Historical(DATABENTO_KEY)
    parametros = _parametros_tcbbo(fecha, simbolos, desde, hasta)

    costo = cliente.metadata.get_cost(**parametros)
    print(f"Costo estimado tcbbo ({len(simbolos)} opciones): ${costo:.4f}")
    if input("¿Descargar? (s/n): ").strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")

    try:
        df = cliente.timeseries.get_range(**parametros).to_df()
    except Exception as e:
        raise RuntimeError(f"Falló la descarga del tcbbo: {e}")

    # Índice = ts_recv (UTC) -> Nueva York
    df.index = df.index.tz_convert(ZONA_NY)
    df = df[["symbol", "price", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]]

    os.makedirs(CARPETA_CACHE, exist_ok=True)
    df.to_parquet(ruta)
    print(f"[guardado] {ruta} ({len(df)} trades)")
    return df


# ============================================================
# PASO 4 — Trade sign minuto a minuto
# ============================================================

def clasificar_trades(trades: pd.DataFrame, estricto: bool = False) -> pd.DataFrame:
    """
    estricto=False (regla del punto medio):
      precio > medio -> +1 (el público COMPRA, dealer queda short esa opción)
      precio < medio -> -1 (el público VENDE, dealer queda long)
      precio = medio ->  0 (indeterminado, no suma)
    estricto=True (solo agresores limpios):
      precio == ask -> +1 | precio == bid -> -1 | todo lo demás -> 0
      - interior del spread: patas de spreads y mejoras de precio
      - FUERA del bid/ask: huella de órdenes complejas (paquetes de varias patas)
      Columna 'complejo' = True si el trade se imprimió fuera del bid/ask.
    'flujo' = signo x size, en int64 (size viene uint32 y no admite negativos).
    """
    df = trades.copy()
    precio = df["price"].round(4)
    bid, ask = df["bid_px_00"].round(4), df["ask_px_00"].round(4)
    df["complejo"] = (precio < bid) | (precio > ask)
    df["signo"] = 0
    if estricto:
        df.loc[precio == ask, "signo"] = 1
        df.loc[precio == bid, "signo"] = -1
    else:
        medio = ((df["bid_px_00"] + df["ask_px_00"]) / 2).round(4)
        df.loc[precio > medio, "signo"] = 1
        df.loc[precio < medio, "signo"] = -1
    df["flujo"] = df["signo"].astype("int64") * df["size"].astype("int64")
    return df


def flujo_por_minuto(clasificados: pd.DataFrame) -> pd.DataFrame:
    """
    Flujo neto del PÚBLICO por minuto, calls y puts separados, más sus acumulados.
    (El dealer tiene el signo contrario.)
    """
    minuto = clasificados.index.floor("1min")
    tabla = (clasificados.groupby([minuto, "instrument_class"])["flujo"]
             .sum()
             .unstack(fill_value=0)
             .rename(columns={"C": "flujo_C", "P": "flujo_P"}))
    tabla.index.name = "minuto"
    tabla["acum_C"] = tabla["flujo_C"].cumsum()
    tabla["acum_P"] = tabla["flujo_P"].cumsum()
    return tabla