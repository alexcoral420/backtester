"""
trades.py — ¿Qué se negoció? Trades con bid/ask (schema tcbbo).
Lo caro del proyecto: siempre costo primero, caché siempre, UNA confirmación por rango.

Es la capa de tcbbo de TODO el proyecto (0DTE y fase B: b2_flujo, signo_walls, medir_niveles).

Caché POR SÍMBOLO (R3 de ODTE.md). Antes cada pedido era un archivo identificado por el md5 de la
lista EXACTA de símbolos: pedir el mismo día con otra lista volvía a pagar todo. Ahora:
  - Un símbolo está CUBIERTO para (día, franja) si aparece en algún archivo de ese día cuya franja
    contiene la pedida. Solo se descargan los símbolos no cubiertos, en un archivo nuevo.
  - Cada archivo nuevo lleva al lado un .json con los símbolos PEDIDOS: así un símbolo sin trades
    también queda cubierto y no se vuelve a pedir.
  - Archivos viejos (sin .json): cubren los símbolos que aparecen en ellos, y TODOS los de su pedido
    original si se vuelve a pedir exactamente la misma lista (el md5 coincide). Un símbolo sin trades
    de un archivo viejo, pedido dentro de otra lista, se vuelve a pedir (cuesta ~$0: no tiene datos).
  - leer_tcbbo arma el resultado tomando cada símbolo de UN solo archivo (sin duplicados), recortado
    a la franja pedida y ordenado por tiempo.
"""
import hashlib
import json
import os
import re
from functools import lru_cache

import pandas as pd

from src import datos
from .constantes import CARPETA_CACHE, DATASET, ZONA_NY

COLUMNAS = ["symbol", "price", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]
_ARCHIVO = re.compile(r"^tcbbo0dte_(\d{4}-\d{2}-\d{2})_([0-9a-f]{8})(?:_(\d{4,6})-(\d{4,6}))?\.parquet$")


def parametros_tcbbo(fecha: str, simbolos: list[str], desde: str = "09:30", hasta: str = "16:00") -> dict:
    """Parámetros de la consulta tcbbo. Horas en NY, convertidas a UTC para la API."""
    return dict(
        dataset=DATASET,
        symbols=simbolos,
        stype_in="raw_symbol",
        schema="tcbbo",
        start=pd.Timestamp(f"{fecha} {desde}", tz=ZONA_NY).tz_convert("UTC"),
        end=pd.Timestamp(f"{fecha} {hasta}", tz=ZONA_NY).tz_convert("UTC"),
    )


def _huella(simbolos) -> str:
    return hashlib.md5("|".join(sorted(simbolos)).encode()).hexdigest()[:8]


def ruta_cache_tcbbo(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> str:
    """Nombre del archivo de UN pedido (día, lista de símbolos, franja). Con la caché por símbolo ya
    no hace falta conocerlo para leer: usar leer_tcbbo."""
    sufijo = "" if (desde, hasta) == ("09:30", "16:00") else \
        f"_{desde.replace(':', '')}-{hasta.replace(':', '')}"
    return os.path.join(CARPETA_CACHE, f"tcbbo0dte_{fecha}_{_huella(simbolos)}{sufijo}.parquet")


def _hora(txt: str) -> str:
    """'0930' -> '09:30' | '095055' -> '09:50:55' (sufijos de los nombres de archivo)."""
    return ":".join(txt[i:i + 2] for i in range(0, len(txt), 2))


def _instante(fecha: str, hora: str) -> pd.Timestamp:
    return pd.Timestamp(f"{fecha} {hora}", tz=ZONA_NY)


@lru_cache(maxsize=None)
def _cobertura(ruta: str, mtime: float) -> tuple[frozenset, bool]:
    """(símbolos que cubre el archivo, True si viene del .json de pedidos). mtime invalida la memoria."""
    lado = ruta[:-len(".parquet")] + ".json"
    if os.path.exists(lado):
        with open(lado, encoding="utf-8") as f:
            return frozenset(json.load(f)["simbolos"]), True
    return frozenset(pd.read_parquet(ruta, columns=["symbol"])["symbol"].astype(str).unique()), False


def archivos_tcbbo(fecha: str) -> list[dict]:
    """Archivos tcbbo en caché de `fecha`: ruta, huella, franja [inicio, fin) y símbolos cubiertos."""
    if not os.path.isdir(CARPETA_CACHE):
        return []
    salida = []
    for nombre in sorted(os.listdir(CARPETA_CACHE)):
        m = _ARCHIVO.match(nombre)
        if not m or m.group(1) != fecha:
            continue
        ruta = os.path.join(CARPETA_CACHE, nombre)
        desde, hasta = (_hora(m.group(3)), _hora(m.group(4))) if m.group(3) else ("09:30", "16:00")
        simbolos, con_json = _cobertura(ruta, os.path.getmtime(ruta))
        salida.append(dict(ruta=ruta, huella=m.group(2), inicio=_instante(fecha, desde),
                           fin=_instante(fecha, hasta), simbolos=simbolos, con_json=con_json))
    return salida


def plan_tcbbo(fecha: str, simbolos, desde: str = "09:30", hasta: str = "16:00") -> tuple[dict, list]:
    """De qué archivo sale cada símbolo pedido, y cuáles faltan.
    Devuelve ({ruta: [símbolos]}, [faltan]). Un símbolo sale de UN solo archivo (sin duplicados)."""
    pedidos = set(simbolos)
    inicio, fin = _instante(fecha, desde), _instante(fecha, hasta)
    candidatos = [a for a in archivos_tcbbo(fecha) if a["inicio"] <= inicio and a["fin"] >= fin]
    # Archivo viejo cuya lista original es EXACTAMENTE la pedida: cubre también sus símbolos sin trades
    for a in candidatos:
        if not a["con_json"] and a["huella"] == _huella(pedidos):
            return {a["ruta"]: sorted(pedidos)}, []
    asignacion, restantes = {}, set(pedidos)
    while restantes:
        # El que más cubre; a igualdad, la franja exacta (lectura idéntica a la del archivo original)
        mejor = max(candidatos, default=None,
                    key=lambda a: (len(a["simbolos"] & restantes), a["inicio"] == inicio and a["fin"] == fin))
        if mejor is None or not (mejor["simbolos"] & restantes):
            break
        tomados = mejor["simbolos"] & restantes
        asignacion[mejor["ruta"]] = sorted(tomados)
        restantes -= tomados
    # Lo que queda puede ser EXACTAMENTE la lista de un archivo viejo (símbolos sin trades): cubierto
    for a in candidatos:
        if restantes and not a["con_json"] and a["huella"] == _huella(restantes):
            asignacion[a["ruta"]] = sorted(set(asignacion.get(a["ruta"], [])) | restantes)
            restantes = set()
    return asignacion, sorted(restantes)


def a_nueva_york(df: pd.DataFrame) -> pd.DataFrame:
    """Lo que se guarda: índice ts_recv (UTC) -> Nueva York, y solo las columnas que se usan."""
    df = df.copy()
    df.index = df.index.tz_convert(ZONA_NY)
    return df[COLUMNAS]


def _guardar_con_pedido(ruta: str, simbolos: list[str]):
    """procesar() que, además, deja el .json con los símbolos pedidos al lado del parquet."""
    def procesar(df):
        with open(ruta[:-len(".parquet")] + ".json", "w", encoding="utf-8") as f:
            json.dump({"simbolos": sorted(simbolos)}, f)
        return a_nueva_york(df)
    return procesar


def asegurar_tcbbo(pedidos: dict, desde: str = "09:30", hasta: str = "16:00",
                   solo_costo: bool = False) -> float:
    """
    Deja en caché el tcbbo de VARIOS días con UNA confirmación del costo total.
    pedidos: {fecha: [símbolos]}. Solo se cotizan y descargan los símbolos que NO estén ya cubiertos.
    Devuelve el costo estimado de lo pendiente ($0 si todo está cubierto).
    solo_costo=True: consulta el costo sin preguntar ni descargar.
    """
    lista, faltan_total = [], 0
    for f, s in pedidos.items():
        _, faltan = plan_tcbbo(f, s, desde, hasta)
        if faltan:
            ruta = ruta_cache_tcbbo(f, faltan, desde, hasta)
            lista.append((ruta, parametros_tcbbo(f, faltan, desde, hasta), _guardar_con_pedido(ruta, faltan)))
            faltan_total += len(faltan)
    series = len({x for s in pedidos.values() for x in s})
    descripcion = (f"tcbbo {len(pedidos)} días, {series} series, {desde}-{hasta} "
                   f"({faltan_total} día-símbolo sin caché)")
    return datos.asegurar_descargas(lista, descripcion, solo_costo=solo_costo)


def leer_tcbbo(fecha: str, simbolos, desde: str = "09:30", hasta: str = "16:00") -> pd.DataFrame:
    """Trades de `simbolos` en `fecha` y [desde, hasta), SOLO desde la caché (nunca descarga).
    Si falta algún símbolo, grita: antes hay que correr asegurar_tcbbo."""
    asignacion, faltan = plan_tcbbo(fecha, simbolos, desde, hasta)
    if faltan:
        raise RuntimeError(f"tcbbo {fecha} {desde}-{hasta}: {len(faltan)} símbolos sin caché "
                           f"(p. ej. {faltan[0]!r}). Correr antes asegurar_tcbbo.")
    inicio, fin = _instante(fecha, desde), _instante(fecha, hasta)
    partes = []
    for ruta, suyos in asignacion.items():
        df = pd.read_parquet(ruta)
        df = df[df["symbol"].astype(str).isin(suyos)]
        partes.append(df[(df.index >= inicio) & (df.index < fin)])
    if not partes:
        return pd.DataFrame(columns=COLUMNAS, index=pd.DatetimeIndex([], tz=ZONA_NY, name="ts_recv"))
    if len(partes) == 1:
        return partes[0]
    return pd.concat(partes).sort_index(kind="stable")


def costo_tcbbo_0dte(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> float:
    """Solo CONSULTA el costo (no descarga nada, no gasta crédito). No mira la caché."""
    return datos._cliente().metadata.get_cost(**parametros_tcbbo(fecha, simbolos, desde, hasta))


def descargar_tcbbo_0dte(fecha: str, simbolos: list[str],
                         desde: str = "09:30", hasta: str = "16:00") -> pd.DataFrame:
    """
    Trades con bid/ask (tcbbo) de los `simbolos` en `fecha`, entre `desde` y `hasta` (hora NY).
    Caché por símbolo: solo se descarga lo que no esté ya en algún archivo del día.
    """
    asegurar_tcbbo({fecha: simbolos}, desde, hasta)
    return leer_tcbbo(fecha, simbolos, desde, hasta)
