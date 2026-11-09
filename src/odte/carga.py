"""
carga.py — M4 (ODTE.md, "Diseño fijo de M4"): ¿un nivel con más carga aguanta más el toque?

Sin signo. La carga de una zona (múltiplo de 25) se conoce ANTES de la apertura de d:
  - MEDIDA:  oi_c, oi_p, oi_total, pct_puts de la foto procesada de d (OI al cierre de d-1, publicado 06:30 de d).
  - MODELO:  gex_bruto de la foto de d-1 SIN las series que vencen en d (gamma BS · OI, calls + puts sumados).
  - SUPUESTA: gex_sup (GEX neto de la misma foto de d-1, signo de la hipótesis nula) y es_wall_sup (top-N por
             |gex_sup| ese día). Es un predictor APARTE: nunca se combina con la carga en un solo número.

Carga RELATIVA: la carga de una zona vale por su percentil DENTRO DE SU CLASE DE REDONDEZ (100 / 50 / 25)
contra las zonas de referencia del día (las de la misma clase a <= `radio` pts del cierre de d-1). La duda 1
mostró que, sin estratificar, "más carga" y "más redonda" son la misma variable.
Una zona tocada fuera del radio (días de movimiento grande) se compara contra esa misma referencia y queda
marcada con fuera_radio=True.

Referencias (columna `referencia` del acumulador; cada una se analiza aparte, nunca se mezclan):
  "radio250" (la del diseño fijo): las zonas de la clase a <= RADIO pts del cierre de d-1. Primera corrida:
             el 77% de los toques cayó en la mitad alta, porque compara zonas cercanas (cargadas) contra lejanas.
  "tocadas"  (variante, 2026-11-09): solo las zonas de la misma clase TOCADAS ese día. Compara toques contra
             toques. Una clase con una sola zona tocada ese día no tiene contra qué compararse -> NaN (sin
             comparación), y esos toques quedan fuera del análisis de esta referencia.

El 0DTE no entra en ninguna carga (decisión del usuario, 2026-11-09; ver CLAUDE.md).
"""
import numpy as np
import pandas as pd

from src.walls import zonas_dia
from .toques import AGUANTO, CRUZO

BANDA = 25
RADIO = 250          # pts alrededor del cierre de d-1 que definen las zonas de referencia del día
TOP_WALLS = 5        # es_wall_sup = entre las TOP_WALLS zonas de referencia por |gex_sup|
MIN_DIAS = 10        # por debajo, una tasa no es evidencia (mismo criterio que analizar_odte)
CLASES = ("100", "50", "25")
REFERENCIAS = ("radio250", "tocadas")
REFERENCIA_FIJA = "radio250"

# CONTRATO de las columnas del acumulador (lo verifica tests/test_carga.py): cada columna en UNA lista.
CLAVES = ["fecha", "definicion", "referencia", "strike", "t_toque"]
PRECIO = ["lado", "dist_previa", "peor_exceso", "resultado", "S_previo", "dist_cierre_previo"]
MEDIDAS = ["oi_c", "oi_p", "oi_total", "pct_puts", "pct_carga_oi"]
MODELO = ["gex_bruto", "pct_carga_bruto"]
SUPUESTAS = ["gex_sup", "es_wall_sup"]
DESCRIPTIVAS = ["clase", "fuera_radio", "d1_vieja"]    # describen la fila; no son carga ni resultado


def clase(columna):
    """'medido', 'modelo', 'supuesto', 'precio', 'clave' o 'descriptiva'; ValueError si no está clasificada."""
    for nombre, lista in (("supuesto", SUPUESTAS), ("modelo", MODELO), ("medido", MEDIDAS),
                          ("precio", PRECIO), ("clave", CLAVES), ("descriptiva", DESCRIPTIVAS)):
        if columna in lista:
            return nombre
    raise ValueError(f"Columna sin clasificar en el contrato de M4: {columna!r}")


def clase_redondez(zona) -> str:
    """'100', '50' o '25'. Grita si la zona no es múltiplo de 25."""
    z = float(zona)
    if z % BANDA != 0:
        raise ValueError(f"zona {zona} no es múltiplo de {BANDA}")
    return "100" if z % 100 == 0 else "50" if z % 50 == 0 else "25"


def _percentil(valores: pd.Series, referencia: pd.Series) -> pd.Series:
    """% de la referencia por debajo de cada valor (los empates cuentan la mitad). NaN sin referencia."""
    ref = referencia.dropna().to_numpy()
    if len(ref) == 0:
        return pd.Series(np.nan, index=valores.index)
    return valores.map(lambda x: 100.0 * ((ref < x).mean() + 0.5 * (ref == x).mean()) if pd.notna(x) else np.nan)


def carga_dia(foto_d: pd.DataFrame, foto_previa: pd.DataFrame, fecha, S_previo: float,
              radio: float = RADIO, top: int = TOP_WALLS) -> pd.DataFrame:
    """Una fila por zona con la carga conocida antes de la apertura de `fecha`.
    foto_d / foto_previa: cadenas procesadas (data/procesado) de d y de d-1."""
    f = pd.Timestamp(fecha).normalize()
    venc_d = pd.to_datetime(foto_previa["vencimiento"]).dt.normalize() == f
    previa = foto_previa[~venc_d]
    if (pd.to_datetime(foto_d["vencimiento"]).dt.normalize() <= f).any():
        raise ValueError(f"la foto de {f:%Y-%m-%d} trae series que vencen ese día o antes (¿foto equivocada?)")

    med = zonas_dia(foto_d, BANDA)[["oi_c", "oi_p", "pct_puts"]]
    mod = zonas_dia(previa, BANDA)[["gex_bruto", "gex"]].rename(columns={"gex": "gex_sup"})
    z = med.join(mod, how="outer")
    z[["oi_c", "oi_p"]] = z[["oi_c", "oi_p"]].fillna(0.0)
    z["oi_total"] = z["oi_c"] + z["oi_p"]
    z["gex_bruto"] = z["gex_bruto"].fillna(0.0)
    z["gex_sup"] = z["gex_sup"].fillna(0.0)
    z.index = z.index.astype(float)
    z["clase"] = [clase_redondez(i) for i in z.index]
    z["fuera_radio"] = (z.index.to_series() - S_previo).abs().to_numpy() > radio

    ref = z[~z["fuera_radio"]]
    for col, dest in (("oi_total", "pct_carga_oi"), ("gex_bruto", "pct_carga_bruto")):
        z[dest] = np.nan
        for c in CLASES:
            en = z["clase"] == c
            z.loc[en, dest] = _percentil(z.loc[en, col], ref.loc[ref["clase"] == c, col])
    walls = ref["gex_sup"].abs().nlargest(top).index
    z["es_wall_sup"] = z.index.isin(walls)
    z.index.name = "strike"
    return z


def unir(tq: pd.DataFrame, carga: pd.DataFrame) -> pd.DataFrame:
    """A cada toque le pega la carga de su zona. Grita si un strike tocado no tiene zona en la carga."""
    falta = sorted(set(tq["strike"].astype(float)) - set(carga.index))
    if falta:
        raise ValueError(f"strikes tocados sin zona en la carga: {falta}")
    cols = MEDIDAS + MODELO + SUPUESTAS + ["clase", "fuera_radio"]
    r = tq.assign(_zona=tq["strike"].astype(float)).merge(carga[cols], left_on="_zona", right_index=True,
                                                         how="left", validate="many_to_one")
    return r.drop(columns="_zona")


def relativa_entre_tocadas(t: pd.DataFrame) -> pd.DataFrame:
    """Variante "tocadas": recalcula pct_carga_oi y pct_carga_bruto contra las zonas de la MISMA clase tocadas
    el MISMO día (todos los toques del día, también los de ventana corta: su carga se conocía igual).
    Con menos de 2 zonas en (día, clase) -> NaN: sin comparación."""
    if t.duplicated(["fecha", "strike"]).any():
        raise ValueError("hay zonas tocadas dos veces el mismo día: toques.py cuenta solo el primer toque")
    t = t.copy()
    for col, dest in (("oi_total", "pct_carga_oi"), ("gex_bruto", "pct_carga_bruto")):
        t[dest] = np.nan
        for _, g in t.groupby(["fecha", "clase"]):
            if len(g) >= 2:
                t.loc[g.index, dest] = _percentil(g[col], g[col])
    return t


# ------------------------------------------------------------------------------------------------
# Análisis (lo usa scripts/odte/analizar_carga.py). Solo toques con resultado aguantó / cruzó.
# ------------------------------------------------------------------------------------------------
def contables(t: pd.DataFrame) -> pd.DataFrame:
    return t[t["resultado"].isin([AGUANTO, CRUZO])].copy()


def alta(t: pd.DataFrame, col: str = "pct_carga_oi") -> pd.Series:
    """True si la carga relativa está en la mitad alta de su clase (>= mediana de la referencia)."""
    if t[col].isna().any():
        raise ValueError(f"{col} tiene NaN: hay toques sin referencia en su clase")
    return t[col] >= 50


def tasa(t: pd.DataFrame) -> float:
    return float("nan") if t.empty else 100.0 * (t["resultado"] == AGUANTO).mean()


def celdas(t: pd.DataFrame, col: str = "pct_carga_oi") -> pd.DataFrame:
    """Tasa de aguante por clase × mitad de carga, con toques, días (episodios) y zonas distintas."""
    t = t.assign(carga=np.where(alta(t, col), "alta", "baja"))
    g = t.groupby(["clase", "carga"])
    r = pd.DataFrame({"toques": g.size(), "dias": g["fecha"].nunique(), "zonas": g["strike"].nunique(),
                      "pct_aguanto": g["resultado"].apply(lambda r: 100.0 * (r == AGUANTO).mean())})
    r["evidencia"] = np.where(r["dias"] >= MIN_DIAS, "sí", "NO (< %d días)" % MIN_DIAS)
    return r


def diferencia(t: pd.DataFrame, col: str = "pct_carga_oi") -> float:
    """Estadístico principal: tasa de aguante (pts %) de la mitad alta menos la baja, con 'alta' definida
    dentro de cada clase. NaN si una de las dos mitades está vacía."""
    a = alta(t, col)
    if a.all() or (~a).all():
        return float("nan")
    return tasa(t[a]) - tasa(t[~a])


def voto_por_zona(t: pd.DataFrame, col: str = "pct_carga_oi") -> dict:
    """Cada zona vota una vez: tasa de aguante por zona y su carga relativa mediana; luego la diferencia
    alta − baja entre ZONAS (no entre toques). Neutraliza las zonas que se repiten por rotación."""
    z = t.groupby("strike").agg(pct=(col, "median"), aguanta=("resultado", lambda r: (r == AGUANTO).mean()))
    a = z["pct"] >= 50
    if a.all() or (~a).all():
        return dict(zonas=len(z), alta=int(a.sum()), baja=int((~a).sum()), diferencia=float("nan"))
    return dict(zonas=len(z), alta=int(a.sum()), baja=int((~a).sum()),
                diferencia=100.0 * (z.loc[a, "aguanta"].mean() - z.loc[~a, "aguanta"].mean()))


def dejar_una_fuera(t: pd.DataFrame, col: str = "pct_carga_oi") -> pd.DataFrame:
    """La diferencia recalculada quitando cada zona; cambia_signo marca si una sola zona da vuelta el resultado."""
    total = diferencia(t, col)
    filas = []
    for z, g in t.groupby("strike"):
        d = diferencia(t[t["strike"] != z], col)
        filas.append(dict(zona=z, toques=len(g), diferencia_sin=d,
                          cambia_signo=bool(np.sign(d) != np.sign(total)) if pd.notna(d) and pd.notna(total) else None))
    return pd.DataFrame(filas)


def predicciones(t: pd.DataFrame) -> pd.DataFrame:
    """Una columna por predictor ('aguantó'/'cruzó'), todas sobre los MISMOS toques.
    Ingenuos: base (siempre el resultado más común), mult100 (aguanta si la zona es múltiplo de 100),
    distancia (aguanta si llegó desde lejos: dist_previa > mediana).
    Carga (sin signo): carga_oi (MEDIDA), carga_bruto (MODELO): aguanta si está en la mitad alta de su clase.
    wall_sup (SUPUESTO): aguanta si la zona es un wall del signo supuesto."""
    a = lambda m: pd.Series(np.where(m, AGUANTO, CRUZO), index=t.index)
    mayoria = AGUANTO if (t["resultado"] == AGUANTO).mean() >= 0.5 else CRUZO
    return pd.DataFrame({
        "base": pd.Series(mayoria, index=t.index),
        "mult100": a(t["clase"] == "100"),
        "distancia": a(t["dist_previa"] > t["dist_previa"].median()),
        "carga_oi": a(alta(t, "pct_carga_oi")),
        "carga_bruto": a(alta(t, "pct_carga_bruto")),
        "wall_sup": a(t["es_wall_sup"].astype(bool)),
    })


def aciertos(t: pd.DataFrame) -> pd.Series:
    """% de acierto de cada predictor sobre los mismos toques."""
    p = predicciones(t)
    return p.eq(t["resultado"], axis=0).mean() * 100
