"""
vista_medidas.py — Todo lo que dibuja app/panel_medidas.py, leyendo SOLO archivos ya calculados.

No importa config ni datos: no pide la API key, no recalcula y no puede gastar crédito. Lo que falta se
dice con SinDatos y el comando que lo genera (los scripts sí necesitan la clave, el panel no).

  rango implícito     data/validacion/rango_implicito.csv      scripts/validar_rango.py
  verificación        data/validacion/gamma_verificacion.csv   scripts/verificar_gamma.py
  gamma intradía      data/validacion/gamma_local.csv          scripts/validar_gamma_local.py
  perfil por precio   data/procesado/perfil_gamma_FECHA.parquet scripts/perfil_gamma.py --todas

Contrato de clases (clase(col); grita si una columna no está clasificada):
  MEDIDO    precios de mercado y movimientos del SPX
  MODELO    gamma Black-Scholes · OI sin signo, y sus errores contra la foto real
  SUPUESTO  lo que usa el signo de la hipótesis nula
"""
import glob
import os
import re

import numpy as np
import pandas as pd

from src import perfil_gamma as pg
from src import rango_implicito as ri

RUTA_RANGO = "data/validacion/rango_implicito.csv"
RUTA_VERIFICACION = "data/validacion/gamma_verificacion.csv"
RUTA_LOCAL = "data/validacion/gamma_local.csv"

MEDIDAS = ["straddle", "ancho", "impl_pct", "impl_prev_pct", "rango_hoy_pct", "rango_sig_pct", "mov_hoy_pct",
           "mov_sig_pct", "pago_sig_pct", "rango_prev_pct", "mov_pct", "mov_abs", "S", "S_sig", "spx", "horas", "forward",
           "dispersion", "K", "dist_FK", "call", "put"]
MODELO = ["gex_bruto", "gex_bruto_c", "gex_bruto_p", "gex_bruto_B", "gex_local_B", "err_recalculada", "err_vieja",
          "sesgo", "top5_que_siguen", "rho_recalculada", "rho_vieja", "cubierto_pct", "cobertura_pct", "foto",
          "recalculada", "gex_bruto_total"]   # foto / recalculada: las dos columnas de mapa() (gamma bruta por zona)
SUPUESTAS = ["gex_sup", "gex_sup_B", "gex_abs_B", "gex_sup_total"]
CLAVES = ["fecha", "sig", "venc", "t", "spot", "zona"]      # identifican la fila, no son mediciones
CLAVES_VERIFICACION = ["foto", "sig"]                       # en gamma_verificacion.csv 'foto' es la fecha de la foto
NOMBRE = {"impl_pct": "straddle de la víspera", "impl_prev_pct": "straddle de la víspera",
          "rango_hoy_pct": "rango de hoy (ingenuo)", "mov_hoy_pct": "|movimiento| de hoy (ingenuo)",
          "rango_prev_pct": "rango de los 30 min previos (ingenuo)", "gex_sup_B": "GEX neto con signo",
          "gex_abs_B": "|GEX neto|", "gex_bruto_B": "gamma bruta en el precio actual",
          "gex_local_B": "gamma bruta a ±50 pts del precio", "spx": "nivel del SPX (ingenuo)"}


class SinDatos(Exception):
    """Falta un archivo: el mensaje dice cuál y con qué comando se genera."""


def clase(col: str) -> str:
    if col in MEDIDAS:
        return "medido"
    if col in MODELO:
        return "modelo"
    if col in SUPUESTAS:
        return "supuesto"
    raise ValueError(f"columna sin clasificar: {col!r} (agregarla a MEDIDAS, MODELO o SUPUESTAS)")


def _leer(ruta: str, comando: str) -> pd.DataFrame:
    if not os.path.exists(ruta):
        raise SinDatos(f"Falta {ruta}. Se genera con: {comando}")
    t = pd.read_csv(ruta)
    if t.empty:
        raise SinDatos(f"{ruta} está vacío. Se genera con: {comando}")
    return t


# ---------------------------------------------------------------- rango implícito (MEDIDO)

def rango() -> pd.DataFrame:
    return _leer(RUTA_RANGO, "python scripts/validar_rango.py INICIO FIN").sort_values("fecha").reset_index(drop=True)


def resumen_rango(t: pd.DataFrame) -> dict:
    """Lo que hay que saber del straddle contra el día siguiente: comparación con el ingenuo y con el GEX
    (SUPUESTO, solo de referencia), episodios y calibración."""
    t = t.copy()
    t["gex_abs_B"] = t["gex_sup_B"].abs()
    comp = ri.comparar(t, "rango_sig_pct", ["impl_pct", "rango_hoy_pct", "gex_sup_B", "gex_abs_B"])
    duelo = ri.duelo_por_episodio(t, "rango_sig_pct", "impl_pct", "rango_hoy_pct")
    return dict(comparacion=comp, episodios=len(duelo), gana=int((duelo["gana"] == "impl_pct").sum()),
                calibracion=ri.calibracion(t), dias=len(t),
                robustez=ri.robustez(t, "rango_sig_pct", "impl_pct", "rango_hoy_pct"))


# ---------------------------------------------------------------- gamma por precio (MODELO)

def fotos_con_perfil() -> list[str]:
    patron = pg.RUTA_PERFIL.format("*")
    return sorted(m.group(1) for r in glob.glob(patron) if (m := re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(r))))


def perfil(fecha: str) -> pd.DataFrame:
    ruta = pg.RUTA_PERFIL.format(fecha)
    if not os.path.exists(ruta):
        raise SinDatos(f"Falta {ruta}. Se genera con: python scripts/perfil_gamma.py --todas")
    p = pd.read_parquet(ruta)
    if not {"gex_bruto_total", "gex_sup_total"} <= set(p.columns):
        raise SinDatos(f"{ruta} es de una versión vieja (sin los totales por spot). "
                       "Se regenera con: python scripts/perfil_gamma.py --todas --rehacer")
    return p


def mapa(p: pd.DataFrame, spot: float, radio: float = 250) -> pd.DataFrame:
    """Gamma bruta por zona (MODELO, $B) en el spot de la foto y en `spot`, zonas a <= radio de `spot`."""
    S = float(p["S"].iloc[0])
    if spot not in set(p["spot"]):
        raise ValueError(f"el spot {spot} no está en la rejilla guardada")
    m = pd.DataFrame(dict(foto=p[p["spot"] == S].set_index("zona")["gex_bruto"],
                          recalculada=p[p["spot"] == spot].set_index("zona")["gex_bruto"])).fillna(0.0) / 1e9
    return m[np.abs(m.index.to_numpy() - spot) <= radio]


def totales_por_spot(p: pd.DataFrame) -> pd.DataFrame:
    """Por spot hipotético: gex_bruto_total (MODELO) y gex_sup_total (SUPUESTO), en $B, sobre TODAS las zonas
    (perfil_gamma.rejilla los suma antes de recortar a ALCANCE_ZONAS). Sumar las zonas guardadas recortaría
    en forma asimétrica en los extremos: faltarían sobre todo puts abajo y calls arriba."""
    return p.groupby("spot")[["gex_bruto_total", "gex_sup_total"]].first() / 1e9


# ---------------------------------------------------------------- verificación (MODELO contra la foto real)

def verificacion() -> pd.DataFrame:
    t = _leer(RUTA_VERIFICACION, "python scripts/verificar_gamma.py")
    t["mov_abs"] = t["mov_pct"].abs()
    return t.sort_values("foto").reset_index(drop=True)


MIN_PARES_BANDA = 3          # pares verificados del MISMO sentido y de ese tamaño o mayor para que haya banda
SIN_VERIFICAR = "sin verificar"


def limite_verificado(v: pd.DataFrame, sentido: int) -> float:
    """Mayor |movimiento| (%) en ese sentido (+1 sube, −1 baja) que tiene al menos MIN_PARES_BANDA pares
    verificados del mismo sentido y de ese tamaño o mayor. 0 si no hay tantos pares en ese sentido.
    Un solo par grande no alcanza: no dice si su error es típico (el 11-04→11-05, −4,4%, se equivocó 15,6%)."""
    x = v.loc[np.sign(v["mov_pct"]) == sentido, "mov_abs"].sort_values(ascending=False)
    return float(x.iloc[MIN_PARES_BANDA - 1]) if len(x) >= MIN_PARES_BANDA else 0.0


def banda_error(v: pd.DataFrame, mov_pct: float, exigir_cobertura: bool = True) -> dict:
    """Error típico de la gamma recalculada para un movimiento de ese tamaño (los tres tramos de
    verificar_gamma). n = pares en el tramo; con menos de 5 la mediana no dice mucho.
    Con exigir_cobertura (lo que usa el precio hipotético): si el movimiento pasa del limite_verificado de su
    sentido no hay banda (tramo SIN_VERIFICAR, n = 0, nan). Prestarle la mediana del tramo "1% o más", hecha
    con movimientos más chicos o del otro sentido, sería un número que susurra.
    Con cobertura, la banda sale solo de los pares del tramo en el MISMO sentido (sentido = "a la baja" /
    "al alza"); sin cobertura, del tramo entero en los dos sentidos (sentido = "ambos sentidos").
    exigir_cobertura=False: solo el resumen del tramo (la tabla de la pestaña verificación)."""
    m = abs(mov_pct)
    signo = -1 if mov_pct < 0 else 1
    limite = limite_verificado(v, signo)
    if exigir_cobertura and m > limite:
        return dict(tramo=SIN_VERIFICAR, n=0, err_recalculada=np.nan, err_vieja=np.nan, peor=np.nan, limite=limite,
                    sentido="a la baja" if signo < 0 else "al alza")
    if exigir_cobertura:
        v, sentido = v[np.sign(v["mov_pct"]) == signo], ("a la baja" if signo < 0 else "al alza")
    else:
        sentido = "ambos sentidos"
    tramo, x = (("menos de 0,5%", v[v["mov_abs"] < 0.5]) if m < 0.5 else
                ("0,5% a 1%", v[(v["mov_abs"] >= 0.5) & (v["mov_abs"] < 1)]) if m < 1 else
                ("1% o más", v[v["mov_abs"] >= 1]))
    return dict(tramo=tramo, n=len(x), err_recalculada=float(x["err_recalculada"].median()) if len(x) else np.nan,
                err_vieja=float(x["err_vieja"].median()) if len(x) else np.nan,
                peor=float(x["err_recalculada"].max()) if len(x) else np.nan, limite=limite, sentido=sentido)


# ---------------------------------------------------------------- gamma intradía (MODELO contra MEDIDO)

def gamma_local() -> pd.DataFrame:
    return _leer(RUTA_LOCAL, "python scripts/validar_gamma_local.py INICIO FIN")


def resumen_local(t: pd.DataFrame) -> pd.DataFrame:
    """Por predictor: Spearman mediano contra el rango de los 30 min siguientes, entre días (misma franja)
    y dentro del día, con cuántos grupos tuvo cada corte."""
    filas = []
    for col in ("gex_bruto_B", "gex_local_B", "spx", "rango_prev_pct", "impl_prev_pct"):
        f = pg.relacion_por_grupo(t, "t", col, "rango_sig_pct")
        d = pg.relacion_por_grupo(t, "fecha", col, "rango_sig_pct")
        filas.append(dict(predictor=col, clase=clase(col), entre_dias=f.median(), franjas=len(f),
                          franjas_mismo_signo=int((np.sign(f) == np.sign(f.median())).sum()),
                          dentro_del_dia=d.median() if len(d) else np.nan, dias=len(d),
                          dias_negativos=int((d < 0).sum())))
    return pd.DataFrame(filas).set_index("predictor")


def control_precio(t: pd.DataFrame) -> dict:
    """¿La gamma bruta dice algo que el NIVEL del SPX no diga ya? Entre días, misma franja (medianas por franja):
    gamma_con_spx  Spearman de la gamma bruta con el nivel del SPX
    spx / gamma    Spearman de cada uno con el rango de los 30 min siguientes
    parcial        lo que queda de la gamma al descontar el nivel del SPX (y de la gamma local)
    sin_un_dia     (mín, máx) de la mediana de la gamma al quitar un día cada vez"""
    def med(serie):
        return float(serie.median())
    obj = "rango_sig_pct"
    return dict(gamma_con_spx=med(pg.relacion_por_grupo(t, "t", "gex_bruto_B", "spx")),
                spx=med(pg.relacion_por_grupo(t, "t", "spx", obj)),
                gamma=med(pg.relacion_por_grupo(t, "t", "gex_bruto_B", obj)),
                parcial=med(pg.relacion_parcial_por_grupo(t, "t", "gex_bruto_B", obj, "spx")),
                parcial_local=med(pg.relacion_parcial_por_grupo(t, "t", "gex_local_B", obj, "spx")),
                sin_un_dia=pg.sin_un_dia(t, "t", "gex_bruto_B", obj), dias=int(t["fecha"].nunique()))
