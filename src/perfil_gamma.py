"""
perfil_gamma.py — La gamma de la foto, RECALCULADA a otro precio y a otra hora.

Por qué: la foto procesada calcula la gamma de cada opción con el spot del CIERRE. La gamma se concentra
cerca del spot, así que después de un movimiento grande (11-05: 7688 → 7353) el mapa de gamma por zona
de la foto ya no vale. El OI no cambia con el precio; la gamma sí.

Qué se recalcula: gamma Black-Scholes de cada opción en un spot S2, con la volatilidad implícita de la
foto FIJA por opción ("sticky strike"), el mismo q medido y el plazo que quede (T − avance).
Todo es MODELO (gamma · OI, sin signo); el neto con la hipótesis nula va en una columna SUPUESTA aparte.

Verificable, en tres niveles (tests/test_perfil_gamma.py y scripts/verificar_gamma.py):
  1. IDENTIDAD: en el spot de la foto y sin avance, el recálculo reproduce la gamma guardada (insumos grita
     si no).
  2. FÓRMULA: gamma_vec coincide con black_scholes.gamma_opcion y con la segunda diferencia numérica del
     precio.
  3. REALIDAD: con la foto de d se predice la gamma de cada serie al cierre de d+1 y se compara con la foto
     real de d+1 (mismas series, OI de d, mismo S²). `error_prediccion` da ese error al lado del de usar la
     foto VIEJA sin recalcular: el recálculo solo se justifica si su error es menor.

Qué NO incluye: lo que vence el propio día (0DTE). Igual que carga.py: la serie intradía de d sale de la
foto de d−1 sin lo que vence en d (decisión del usuario del 2026-11-09; CLAUDE.md).
"""
import os

import numpy as np
import pandas as pd
from scipy.stats import norm

BANDA = 25
RADIO = 250              # pts alrededor del spot nuevo para comparar rankings de zonas
RADIO_LOCAL = 50         # pts alrededor del spot que cuentan como gamma "local"
TOL_IDENTIDAD = 1e-9     # diferencia relativa máxima entre la gamma guardada y la recalculada en el mismo spot
ANIO_SEG = 365 * 24 * 3600
PROCESADO = "data/procesado/cadena_SPX+SPXW_horas_{}.parquet"
RAICES, PLAZO = ("SPX", "SPXW"), "horas"
RUTA_PERFIL = "data/procesado/perfil_gamma_{}.parquet"      # rejilla zona × spot ya calculada (la lee el panel)
PASO_REJILLA, ALCANCE_REJILLA, ALCANCE_ZONAS = 25, 400, 600

MODELO = ["gamma_s2", "gex_bruto", "gex_bruto_c", "gex_bruto_p", "gex_bruto_local", "real", "recalculada", "vieja"]
SUPUESTAS = ["gex_sup"]


def clase(columna):
    if columna in MODELO:
        return "modelo"
    if columna in SUPUESTAS:
        return "supuesto"
    raise ValueError(f"columna sin clasificar: {columna!r} (agregarla a MODELO o SUPUESTAS)")


def gamma_vec(S, K, T, r, sigma, q=0.0):
    """Gamma Black-Scholes respecto al spot, vectorizada (misma fórmula que black_scholes.gamma_opcion).
    nan donde T <= 0 o la volatilidad no sirve."""
    S, K, T, sigma, q = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (S, K, T, sigma, q)))
    ok = (T > 0) & np.isfinite(sigma) & (sigma > 0)
    Tb, sb = np.where(ok, T, 1.0), np.where(ok, sigma, 1.0)
    raiz = sb * np.sqrt(Tb)
    d1 = (np.log(S / K) + (r - q + 0.5 * sb**2) * Tb) / raiz
    return np.where(ok, np.exp(-q * Tb) * norm.pdf(d1) / (S * raiz), np.nan)


def insumos(fecha: str, r: float) -> pd.DataFrame:
    """La foto procesada de `fecha` más lo que le falta para recalcular: q (forward medido por raíz) y T.
    SOLO CACHÉ: grita si falta la foto o la cadena cruda (nunca descarga). Grita también si la gamma
    recalculada en el spot de la foto no reproduce la guardada (identidad)."""
    from src.datos import ruta_cadena
    from src.forward import q_por_raiz
    from src.precio_justo import tabla_cierre

    ruta = PROCESADO.format(fecha)
    faltan = [p for p in [ruta] + [ruta_cadena(x, s, fecha) for x in RAICES for s in ("ohlcv-1d", "statistics")]
              if not os.path.exists(p)]
    if faltan:
        raise FileNotFoundError(f"{fecha}: falta en caché {', '.join(faltan)} (perfil_gamma no descarga)")
    c = pd.read_parquet(ruta)
    S = float(c["S"].iloc[0])
    t = tabla_cierre(fecha, RAICES, PLAZO)
    t = t[t["T"] > 0].copy()
    t["q"] = q_por_raiz(t, S, r)
    c = c.merge(t[["q", "T"]], left_on="symbol", right_index=True, how="left", validate="one_to_one")
    if c[["q", "T"]].isna().any().any():
        raise ValueError(f"{fecha}: hay series de la foto sin q o T en la cadena cruda")
    c["r"] = r
    verificar_identidad(c)
    return c


def verificar_identidad(c: pd.DataFrame, tol: float = TOL_IDENTIDAD) -> float:
    """Diferencia relativa máxima entre la gamma guardada y la recalculada en el spot de la foto. Grita si
    supera `tol` o si no coinciden las series sin gamma."""
    g = gamma_vec(c["S"], c["strike"], c["T"], c["r"], c["iv"], c["q"])
    if (np.isnan(g) != c["gamma"].isna().to_numpy()).any():
        raise ValueError("identidad: las series sin gamma de la foto y del recálculo no coinciden")
    con = c["gamma"].notna().to_numpy()
    dif = float(np.max(np.abs(g[con] / c["gamma"].to_numpy()[con] - 1))) if con.any() else 0.0
    if dif > tol:
        raise ValueError(f"identidad: la gamma recalculada difiere de la guardada en {dif:.2e} (tolerancia {tol:.0e})")
    return dif


def cobertura(c: pd.DataFrame) -> float:
    """% del OI de la foto con volatilidad utilizable (lo demás queda fuera del perfil)."""
    return float(100 * c.loc[c["iv"].notna(), "open_interest"].sum() / c["open_interest"].sum())


def gex_bruto_en(c: pd.DataFrame, S2: float, avance: float = 0.0) -> pd.Series:
    """Gamma en dólares SIN signo de cada opción en el spot S2 (gamma · OI · 100 · S2² · 0.01), `avance`
    años después de la foto. Lo que para entonces venció vale 0; lo que no tiene volatilidad, nan."""
    T = c["T"] - avance
    g = gamma_vec(S2, c["strike"], T, c["r"], c["iv"], c["q"])
    g = np.where((T <= 0).to_numpy(), 0.0, g)
    return pd.Series(g * c["open_interest"].to_numpy() * 100 * S2**2 * 0.01, index=c.index)


def perfil(c: pd.DataFrame, spots, avance: float = 0.0, banda: int = BANDA) -> pd.DataFrame:
    """Una fila por (spot, zona): gex_bruto_c, gex_bruto_p, gex_bruto (MODELO) y gex_sup (SUPUESTO: neto con
    el signo de la hipótesis nula). Zonas de `banda` puntos, como walls.zonas_dia."""
    from src.gex import signo_gamma_supuesto      # aquí y no arriba: gex importa config (la API key)

    zona = (c["strike"] / banda).round() * banda
    signo = signo_gamma_supuesto(c["tipo"])
    partes = []
    for S2 in spots:
        b = gex_bruto_en(c, float(S2), avance)
        d = pd.DataFrame(dict(zona=zona, gex_bruto_c=b.where(c["tipo"] == "C", 0.0),
                              gex_bruto_p=b.where(c["tipo"] == "P", 0.0), gex_bruto=b, gex_sup=b * signo))
        z = d.dropna(subset=["gex_bruto"]).groupby("zona").sum()
        z.insert(0, "spot", float(S2))
        partes.append(z.reset_index())
    return pd.concat(partes, ignore_index=True)


def rejilla(c: pd.DataFrame) -> pd.DataFrame:
    """El perfil en una rejilla fija de spots (múltiplos de PASO_REJILLA a <= ALCANCE_REJILLA del cierre, más
    el cierre mismo), zonas a <= ALCANCE_ZONAS. Lleva S (el spot de la foto) y cobertura_pct en cada fila.
    Es lo que se guarda en RUTA_PERFIL para que el panel dibuje sin recalcular (ni necesitar config)."""
    S = float(c["S"].iloc[0])
    lo = int(np.ceil((S - ALCANCE_REJILLA) / PASO_REJILLA)) * PASO_REJILLA
    spots = sorted(set(range(lo, int(S + ALCANCE_REJILLA) + 1, PASO_REJILLA)) | {S})
    p = perfil(c, spots)
    p = p[(p["zona"] - S).abs() <= ALCANCE_ZONAS].reset_index(drop=True)
    p["S"], p["cobertura_pct"] = S, cobertura(c)
    return p


def envejecimiento(c: pd.DataFrame, S2: float, avance: float = 0.0, radio: float = RADIO, top: int = 5) -> dict:
    """¿Cuánto cambia el mapa de gamma bruta por zona si el precio pasa del spot de la foto a S2?
    Sobre las zonas a <= radio de S2: Spearman entre el ranking viejo y el recalculado, cuántas de las
    `top` zonas siguen siendo top, y el total bruto viejo y nuevo (en $)."""
    S = float(c["S"].iloc[0])
    viejo = perfil(c, [S]).set_index("zona")["gex_bruto"]
    nuevo = perfil(c, [S2], avance=avance).set_index("zona")["gex_bruto"]
    p = pd.concat({"viejo": viejo, "nuevo": nuevo}, axis=1).fillna(0.0)
    p = p[np.abs(p.index.to_numpy() - S2) <= radio]
    return dict(S=S, S2=float(S2), zonas=len(p), spearman=float(p["viejo"].corr(p["nuevo"], method="spearman")),
                top_comunes=len(set(p["viejo"].nlargest(top).index) & set(p["nuevo"].nlargest(top).index)),
                bruto_viejo=float(p["viejo"].sum()), bruto_nuevo=float(p["nuevo"].sum()))


def error_prediccion(c_d: pd.DataFrame, c_sig: pd.DataFrame, banda: int = BANDA, radio: float = RADIO) -> dict:
    """La prueba contra la realidad. Con la foto de d (c_d, de `insumos`) se predice la gamma de cada serie
    en el spot y el plazo del cierre siguiente, y se compara con la gamma REAL de esa foto (c_sig).
    Las tres columnas usan las mismas series, el OI de d y el S² del día siguiente: solo cambia la gamma.
      real        = gamma de la foto siguiente
      recalculada = gamma de d llevada al spot y plazo siguientes (vol fija)
      vieja       = gamma de d tal cual (lo que se mira si no se recalcula)
    Devuelve zonas (DataFrame por zona) y los errores |x − real| sumados sobre las zonas a <= radio del
    spot nuevo, como % del real, más el % del bruto real cubierto por series comunes."""
    S2 = float(c_sig["S"].iloc[0])
    sig = c_sig.set_index("symbol")
    m = c_d.merge(sig[["gamma", "T"]].rename(columns={"gamma": "gamma_real", "T": "T_sig"}),
                  left_on="symbol", right_index=True, how="inner")
    m["gamma_rec"] = gamma_vec(S2, m["strike"], m["T_sig"], m["r"], m["iv"], m["q"])
    m = m.dropna(subset=["gamma", "gamma_real", "gamma_rec"])
    k = m["open_interest"] * 100 * S2**2 * 0.01
    z = pd.DataFrame(dict(zona=(m["strike"] / banda).round() * banda, real=m["gamma_real"] * k,
                          recalculada=m["gamma_rec"] * k, vieja=m["gamma"] * k)).groupby("zona").sum()
    cerca = z[np.abs(z.index.to_numpy() - S2) <= radio]
    total_sig = float((c_sig["gamma"] * c_sig["open_interest"]).sum() * 100 * S2**2 * 0.01)
    real = float(cerca["real"].sum())
    return dict(zonas=z, S=float(c_d["S"].iloc[0]), S2=S2, series=len(m),
                pct_cubierto=100 * float((m["gamma_real"] * m["open_interest"]).sum() * 100 * S2**2 * 0.01) / total_sig
                if total_sig else np.nan,
                err_recalculada=100 * float((cerca["recalculada"] - cerca["real"]).abs().sum()) / real,
                err_vieja=100 * float((cerca["vieja"] - cerca["real"]).abs().sum()) / real,
                sesgo_recalculada=100 * float((cerca["recalculada"] - cerca["real"]).sum()) / real,
                spearman_recalculada=float(cerca["recalculada"].corr(cerca["real"], method="spearman")),
                spearman_vieja=float(cerca["vieja"].corr(cerca["real"], method="spearman")))


def serie_intradia(c_prev: pd.DataFrame, spx: pd.Series, fecha: str, cierre_prev: pd.Timestamp,
                   radio_local: float = RADIO_LOCAL) -> pd.DataFrame:
    """Gamma bruta (MODELO) en cada instante de `spx` (Series con índice NY del día `fecha`): la foto del
    día previo llevada al spot y a la hora de cada instante, SIN lo que vence en `fecha`.
    cierre_prev: instante (con zona) de la foto previa. Columnas: spx, gex_bruto (todas las series),
    gex_bruto_local (strikes a <= radio_local del spot)."""
    if spx.index.tz is None or cierre_prev.tzinfo is None:
        raise ValueError("serie_intradia necesita hora NY explícita en spx y en cierre_prev")
    if (spx.index <= cierre_prev).any():
        raise ValueError("serie_intradia: hay instantes anteriores a la foto previa")
    f = pd.Timestamp(fecha).normalize()
    c = c_prev[(pd.to_datetime(c_prev["vencimiento"]).dt.normalize() != f) & c_prev["iv"].notna()]
    K, T0, iv, q = (c[x].to_numpy(dtype=float) for x in ("strike", "T", "iv", "q"))
    oi, r = c["open_interest"].to_numpy(dtype=float), float(c["r"].iloc[0])
    filas = []
    for t, S2 in spx.items():
        T = T0 - (t - cierre_prev).total_seconds() / ANIO_SEG
        g = gamma_vec(S2, K, T, r, iv, q)
        d = np.where(T > 0, g, 0.0) * oi * 100 * S2**2 * 0.01
        filas.append(dict(t=t, spx=float(S2), gex_bruto=float(d.sum()),
                          gex_bruto_local=float(d[np.abs(K - S2) <= radio_local].sum())))
    return pd.DataFrame(filas).set_index("t")


def bloques(spx: pd.Series, minutos: int = 30, desde: str = "10:00") -> pd.DataFrame:
    """Bloques de `minutos` sin solaparse desde `desde`: t (inicio), spx (último cierre ANTES del bloque),
    rango_prev_pct y rango_sig_pct = (máx − mín) de los cierres de 1 min en los `minutos` previos / del
    bloque, en % del spx. Solo bloques con las dos ventanas completas."""
    if spx.index.tz is None:
        raise ValueError("bloques necesita hora NY explícita")
    paso = pd.Timedelta(minutes=minutos)
    t = pd.Timestamp(f"{spx.index[0]:%Y-%m-%d} {desde}", tz=spx.index.tz)
    filas = []
    while t + paso <= spx.index[-1] + pd.Timedelta(minutes=1):
        antes, despues = spx[(spx.index >= t - paso) & (spx.index < t)], spx[(spx.index >= t) & (spx.index < t + paso)]
        if len(antes) == minutos and len(despues) == minutos:
            S = float(antes.iloc[-1])
            filas.append(dict(t=t, spx=S, rango_prev_pct=100 * (antes.max() - antes.min()) / S,
                              rango_sig_pct=100 * (despues.max() - despues.min()) / S))
        t += paso
    return pd.DataFrame(filas, columns=["t", "spx", "rango_prev_pct", "rango_sig_pct"])


def relacion_por_grupo(t: pd.DataFrame, grupo: str, pred: str, obj: str, minimo: int = 5) -> pd.Series:
    """Spearman de `pred` contra `obj` dentro de cada valor de `grupo` (un día, o una franja horaria).
    Grupos con menos de `minimo` filas o sin variación quedan fuera."""
    sal = {}
    for g, x in t.groupby(grupo):
        x = x[[pred, obj]].dropna()
        if len(x) >= minimo and x[pred].nunique() > 1 and x[obj].nunique() > 1:
            sal[g] = x[pred].corr(x[obj], method="spearman")
    return pd.Series(sal, dtype=float)
