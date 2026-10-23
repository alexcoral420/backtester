"""
Uso:  streamlit run app/panel.py        (desde la raíz del proyecto)

Panel de walls (SPX+SPXW, plazo horas): mapa, perfil del día, ficha de un wall, descomposición del
cambio de GEX y rotación. SOLO DIBUJA: lee las cadenas ya procesadas de data/procesado/ (las genera
scripts/walls_tiempo.py) y todos los números salen de src/walls.py. Nunca descarga ni pide la API key.

Convención medido / modelo / supuesto: la decide SIEMPRE el contrato de walls.py (clase), nunca a mano.
  MEDIDO   (OI, ΔOI, % puts, SPX):  escalas de un solo tono, barras sólidas, líneas continuas
  MODELO   (gex_bruto, desbalance): gamma Black-Scholes · OI SIN signo; escala violeta, barras punteadas,
                                    "MODELO" en título, eje, hover y tablas
  SUPUESTO (gex, pos, mer, ven):    escala divergente azul/rojo con gris en 0 (pos/mer/ven: colores propios
                                    distintos de calls/puts), barras RAYADAS, líneas
                                    discontinuas, "SUPUESTO" en título, eje/barra de color, hover y tablas
Regla de tiempo: el ΔOI (y 'posicionamiento') de la fecha d es el flujo del día de mercado ANTERIOR.
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.walls import CLAVES, EN_DOLARES, clase, es_supuesta, evolucion, rotacion, zonas_por_tramo

CARPETA = "data/procesado"
PATRON = os.path.join(CARPETA, "cadena_SPX+SPXW_horas_*.parquet")

# Paleta validada (dataviz, references/palette.md; validate_palette.js pasa en cada modo con su superficie).
#   calls/puts = slots categóricos 1-2; componentes del ΔGEX (todos supuestos) = slots 3-4-5, distintos de
#   calls/puts para no confundirse con series medidas. Modo oscuro = sus propios pasos, no un "invertir".
_OSCURO = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
if _OSCURO:
    CALLS, PUTS = "#3987e5", "#d95926"
    COLOR_COMPONENTE = {"pos": "#199e70", "mer": "#c98500", "ven": "#d55181"}
    TINTA, TINTA_SUAVE, SUPERFICIE, MEDIO = "#f0efec", "#c3c2b7", "#1a1a19", "#383835"
else:
    CALLS, PUTS = "#2a78d6", "#eb6834"
    COLOR_COMPONENTE = {"pos": "#1baf7a", "mer": "#eda100", "ven": "#e87ba4"}
    TINTA, TINTA_SUAVE, SUPERFICIE, MEDIO = "#0b0b0b", "#52514e", "#fcfcfb", "#e1e0d9"
# Rampa secuencial azul completa (palette.md, pasos 100->700): 9 pasos en vez de 5 para distinguir cargas.
# Claro: el paso claro = poco y se funde con la superficie. Oscuro: invertida (lo poco se funde con lo oscuro).
_AZUL_9 = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#104281", "#0d366b"]
SEQ_AZUL = _AZUL_9[::-1] if _OSCURO else _AZUL_9
SEQ_NARANJA = ["#fde4d6", "#f6b08f", "#eb6834", "#b84a1f", "#7a2e10"]
if _OSCURO:
    SEQ_NARANJA = SEQ_NARANJA[::-1]
DIVERGENTE = [[0.0, "#b3261e"], [0.25, "#e66767"], [0.5, MEDIO], [0.75, "#5598e7"], [1.0, "#104281"]]
POSITIVO, NEGATIVO = "#3987e5", "#e66767"          # polos de DIVERGENTE, para barras supuestas por signo
NEUTRO = "#898781"

ETIQUETAS = {
    "oi_c": "OI calls", "oi_p": "OI puts", "oi_total": "OI total", "pct_puts": "% del OI en puts",
    "doi_c": "ΔOI calls", "doi_p": "ΔOI puts", "oi_venc": "OI vencido", "S": "SPX", "dS": "ΔSPX",
    "gex": "GEX", "pos": "posicionamiento", "mer": "mercado", "ven": "vencidas",
    "gex_bruto": "gamma bruta", "gex_bruto_c": "gamma bruta calls", "gex_bruto_p": "gamma bruta puts",
    "desbalance_pct": "desbalance calls/puts",
}
# Escala secuencial por CLASE (regla: el estilo lo decide el contrato). Medido: azul (magnitud) / naranja (0-100).
# Modelo: violeta (ColorBrewer "Purples", un solo tono), distinto de lo medido aunque no haya patrón en un heatmap.
SEQ_VIOLETA = ["#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#54278f", "#3f007d"]
if _OSCURO:
    SEQ_VIOLETA = SEQ_VIOLETA[::-1]
ACOTADAS = ("pct_puts", "desbalance_pct")          # 0-100: escala lineal fija; el resto son magnitudes con cola larga
ESCALAS = ("logarítmica", "por percentiles", "lineal")      # para magnitudes con cola larga (OI, gamma bruta)


# ---------------------------------------------------------------- estilo derivado del contrato

def supuesta(col):
    return es_supuesta(col)                         # grita si la columna no está clasificada


def titulo(col, texto=None):
    t = texto or ETIQUETAS.get(col, col)
    return {"supuesto": f"SUPUESTO · {t} (signo de la hipótesis nula)",
            "modelo": f"MODELO · {t} (gamma Black-Scholes, sin signo)", "medido": f"MEDIDO · {t}"}[clase(col)]


def unidad(col):
    """Unidad + clase para ejes, barras de color, hover y tablas: la clase viaja con el número."""
    k = clase(col)
    if k == "medido":
        return ""
    return ("$B" if col in EN_DOLARES else "%") + (" (SUPUESTO)" if k == "supuesto" else " (MODELO)")


def etiqueta_eje(col, unidad_medida=""):
    return ETIQUETAS.get(col, col) + (" " + unidad(col) if clase(col) != "medido" else unidad_medida)


def eje_comun(cols, unidad_medida=""):
    """Título de un eje que comparte varias columnas: exige que sean todas de la MISMA clase (regla: un eje
    nunca mezcla medido, modelo y supuesto)."""
    clases = {clase(c) for c in cols}
    if len(clases) != 1:
        raise ValueError(f"Un eje no puede mezclar clases (medido/modelo/supuesto): {cols}")
    return unidad(cols[0]) or unidad_medida


def a_miles_de_millones(df):
    """Toda columna en $ (supuesta o de modelo) se pasa a $B; las medidas no se tocan."""
    for c in df.columns:
        if c not in CLAVES and clase(c) != "medido" and c in EN_DOLARES:
            df[c] = df[c] / 1e9
    return df


def patron(col):
    """Segunda codificación además del texto: rayado = supuesto, punteado = modelo, sólido = medido."""
    return {"supuesto": dict(shape="/", fgcolor="rgba(255,255,255,0.55)", solidity=0.25),
            "modelo": dict(shape=".", fgcolor="rgba(255,255,255,0.6)", solidity=0.3),
            "medido": None}[clase(col)]


def escala_magnitud(m, modo):
    """Color para una magnitud >= 0 con cola larga (8000 tiene ~2M contratos, el resto 50-500k).
    Devuelve (z para el color, tickvals, ticktext) con los ticks en la unidad REAL; el hover usa el valor real.
      logarítmica:     cada paso de color = x veces más carga (distingue 50k de 200k sin que 8000 lo tape)
      por percentiles: cada color = la misma cantidad de celdas (máximo contraste de orden, pierde proporción)
      lineal:          proporcional (8000 satura y el resto queda claro)"""
    v = m.values.astype(float)
    pos = v[np.isfinite(v) & (v > 0)]
    if not pos.size or modo == "lineal":
        return v, None, None
    if modo == "logarítmica":
        z = np.log10(np.where(v > 0, v, np.nan))
        lo, hi = int(np.floor(np.log10(pos.min()))), int(np.ceil(np.log10(pos.max())))
        ticks = [b * 10.0 ** e for e in range(lo, hi + 1) for b in (1, 2, 5) if pos.min() <= b * 10.0 ** e <= pos.max()]
        return z, np.log10(ticks), [f"{t:,.3g}" for t in ticks]
    plano = pd.Series(v.ravel()).where(lambda x: x > 0)
    z = (plano.rank(pct=True) * 100).to_numpy().reshape(v.shape)
    q = [0, 25, 50, 75, 90, 100]
    return z, q, [f"p{p} · {np.nanpercentile(pos, p):,.3g}" for p in q]


def color_barras(col, valores, base):
    """Supuesto: color por signo (polos de la escala divergente). Medido: el color fijo de la serie."""
    return np.where(np.asarray(valores) >= 0, POSITIVO, NEGATIVO) if supuesta(col) else base


def linea(col, color):
    return dict(color=color, width=2, dash={"supuesto": "dash", "modelo": "dot", "medido": "solid"}[clase(col)])


def tabla(df):
    """Tabla con cada columna rotulada según el contrato. Una columna sin clasificar hace fallar la página."""
    nombres = {c: (c if c in CLAVES or clase(c) == "medido" else f"{c} [{unidad(c)}]") for c in df.columns}
    st.dataframe(df.rename(columns=nombres).round(2), width="stretch")


# ---------------------------------------------------------------- datos (cache: no se recalcula al mover un control)

@st.cache_data(show_spinner="Leyendo cadenas procesadas…")
def cargar():
    cadenas = {}
    for r in sorted(glob.glob(PATRON)):
        f = pd.Timestamp(re.search(r"(\d{4}-\d{2}-\d{2})\.parquet$", r).group(1))
        cadenas[f] = pd.read_parquet(r)
    if len(cadenas) < 2:
        return None, None, None
    D, Z = evolucion(cadenas)
    D, Z = a_miles_de_millones(D), a_miles_de_millones(Z)
    # Día de flujo que explica el ΔOI de cada fecha: el anterior de la serie. Si hay días hábiles en el medio
    # (hueco de datos o feriado) se avisa. Aproximado: no conoce feriados (el panel no usa internet).
    fechas, flujo = list(D.index), {}
    for a, b in zip(fechas[:-1], fechas[1:]):
        extra = int(np.busday_count(a.date(), b.date())) - 1
        flujo[b] = a.strftime("%d-%b") + (f" (+{extra} día hábil sin datos o feriado)" if extra > 0 else "")
    D["flujo_de"] = pd.Series(flujo)
    Z["flujo_de"] = Z["fecha"].map(D["flujo_de"])
    return cadenas, D, Z


@st.cache_data
def perfil(fecha):
    cadenas, _, _ = cargar()
    return a_miles_de_millones(zonas_por_tramo(cadenas[fecha]))


# ---------------------------------------------------------------- página

st.set_page_config(page_title="Walls SPX", layout="wide")
cadenas, D, Z = cargar()
if D is None:
    st.error(f"Hacen falta al menos 2 cadenas en {CARPETA}/. Generalas con:\n\n"
             "`python scripts/walls_tiempo.py INICIO FIN` (pide confirmación de costo si falta caché).")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    fechas = list(D.index)
    ini, fin = st.select_slider("Ventana", options=fechas, value=(fechas[0], fechas[-1]),
                                format_func=lambda x: x.strftime("%d-%b"))
    dist = st.slider("Zonas a ≤ % del spot", 1.0, 8.0, 4.0, 0.5)
    st.caption("**MEDIDO**: OI, ΔOI, % puts, SPX (sin signo).  \n"
               "**MODELO**: gamma bruta (calls y puts SUMADAS, sin signo) y desbalance calls/puts. "
               "Punteado = modelo.  \n"
               "**SUPUESTO**: GEX y su descomposición, con el signo de la hipótesis nula "
               "(público vende calls, compra puts). Rayado o discontinuo = supuesto.")
    st.caption("ΔOI de una fecha = flujo del día de mercado ANTERIOR.")
    st.caption(f"{len(fechas)} días en {CARPETA}/. Solo lectura: el panel no descarga.")

Dv = D.loc[ini:fin]
Zv = Z[(Z["fecha"] >= ini) & (Z["fecha"] <= fin)]
lo, hi = (Zv["S"] * (1 - dist / 100)).min(), (Zv["S"] * (1 + dist / 100)).max()
Zv = Zv[(Zv["zona"] >= lo) & (Zv["zona"] <= hi)]
eje_fecha = dict(tickformat="%d-%b")

st.title("Walls SPX + SPXW")
tab_mapa, tab_dia, tab_wall, tab_desc, tab_rot = st.tabs(
    ["Mapa", "Perfil del día", "Ficha de un wall", "De dónde vino el cambio", "Rotación"])

# ---------------------------------------------------------------- 1. mapa
with tab_mapa:
    c1, c2 = st.columns([3, 2])
    metrica = c1.radio("Color", ["oi_total", "pct_puts", "gex_bruto", "desbalance_pct", "gex"], horizontal=True,
                       format_func=lambda c: f"{ETIQUETAS[c]} ({clase(c)})")
    cola_larga = not supuesta(metrica) and metrica not in ACOTADAS
    modo = c2.radio("Escala de color", ESCALAS, horizontal=True, disabled=not cola_larga,
                    help="Solo para OI total y gamma bruta. Logarítmica: cada paso de color = x veces más carga. "
                         "Por percentiles: cada color = la misma cantidad de celdas (orden, no proporción).")
    m = Zv.pivot(index="zona", columns="fecha", values=metrica)
    barra = dict(title=etiqueta_eje(metrica))
    z = m.values
    if supuesta(metrica):
        lim = float(np.nanmax(np.abs(m.values)))
        escala = dict(colorscale=DIVERGENTE, zmid=0, zmin=-lim, zmax=lim)
    elif cola_larga:
        z, tv, tt = escala_magnitud(m, modo)
        escala = dict(colorscale=SEQ_VIOLETA if clase(metrica) == "modelo" else SEQ_AZUL)
        if tv is not None:
            barra.update(tickvals=list(tv), ticktext=tt, title=etiqueta_eje(metrica) + f" · escala {modo}")
    elif clase(metrica) == "modelo":
        # desbalance invertido: oscuro = 0 = calls y puts se cancelan (lo que hay que ver)
        escala = dict(colorscale=SEQ_VIOLETA[::-1], zmin=0, zmax=100)
        barra.update(tickvals=[0, 50, 100], ticktext=["0 · balanceado", "50", "100 · un solo tipo"])
    else:
        escala = dict(colorscale=SEQ_NARANJA, zmin=0, zmax=100)
    piv = lambda c: Zv.pivot(index="zona", columns="fecha", values=c).values
    fmt = {"oi_total": ",.0f", "pct_puts": ".0f", "gex_bruto": ",.2f", "desbalance_pct": ".0f", "gex": "+.2f"}[metrica]
    fig = go.Figure(go.Heatmap(
        x=m.columns, y=m.index, z=z, colorbar=barra, xgap=2, ygap=2, **escala,
        customdata=np.dstack([piv("oi_c"), piv("oi_p"), piv("gex"), piv("gex_bruto"), piv("desbalance_pct"),
                              m.values]),
        hovertemplate=("%{x|%d-%b} · zona %{y:.0f}<br>" + etiqueta_eje(metrica) + ": %{customdata[5]:" + fmt + "}"
                       + "<br>OI calls %{customdata[0]:,.0f} · OI puts %{customdata[1]:,.0f}"
                       + "<br>gamma bruta %{customdata[3]:,.2f} $B (MODELO) · desbalance %{customdata[4]:.0f}% (MODELO)"
                       + "<br>GEX %{customdata[2]:+.2f} $B (SUPUESTO)<extra></extra>")))
    fig.add_trace(go.Scatter(x=Dv.index, y=Dv["S"], mode="lines+markers", name="SPX cierre (medido)",
                             line=linea("S", TINTA), marker=dict(size=8, color=SUPERFICIE, line=dict(color=TINTA, width=2)),
                             hovertemplate="%{x|%d-%b} · SPX %{y:,.2f}<extra></extra>"))
    fig.update_layout(title=titulo(metrica, f"{ETIQUETAS[metrica]} por zona y día, con el SPX encima"),
                      height=650, xaxis=eje_fecha, yaxis_title="zona (25 pts)", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    if metrica == "gex_bruto":
        st.caption("MODELO, sin signo: gamma de las calls + gamma de las puts de la zona, en $B por 1% (no se restan). "
                   "Es el tamaño de la gamma abierta ahí. Cuánto de eso cubre un dealer, y en qué dirección, depende de "
                   "quién tiene cada lado: eso es SUPUESTO.")
    elif clase(metrica) == "modelo":
        st.caption("MODELO, sin signo: |gamma bruta calls − puts| / bruta. Oscuro (cerca de 0) = calls y puts casi se "
                   "cancelan: ahí el GEX neto (SUPUESTO) es la resta de dos números grandes y un cambio chico en el "
                   "signo lo cambia mucho. Claro (cerca de 100) = un solo tipo: el GEX neto no sale de una resta, pero "
                   "su signo SIGUE siendo supuesto (si ese tipo tuviera el signo contrario, se invierte entero).")
    elif supuesta(metrica):
        st.caption("Con GEX, un cambio de color en una fila puede venir de que el PRECIO se acercó o alejó "
                   "(componente 'mercado'), no solo de posiciones nuevas: ver la pestaña 'De dónde vino el cambio'. "
                   "El color (+/−) es SUPUESTO.")
    else:
        st.caption("Medido: un cambio de color en una fila es OI que entró o salió de esa zona (aperturas, "
                   "cierres o VENCIMIENTOS; la ficha del wall los separa). El OI de una fecha es el del cierre anterior.")

# ---------------------------------------------------------------- 2. perfil del día
with tab_dia:
    dia = st.select_slider("Día", options=list(Dv.index), value=Dv.index[-1], format_func=lambda x: x.strftime("%d-%b"))
    t = perfil(dia)
    c1, c2 = st.columns(2)
    raices = c1.multiselect("Raíz", ["SPX", "SPXW"], default=["SPX", "SPXW"])
    tramos = c2.multiselect("Días al vencimiento", ["1-3d", "4-7d", "8-35d", ">35d"],
                            default=["1-3d", "4-7d", "8-35d", ">35d"])
    S = float(D.loc[dia, "S"])
    t = t[t["raiz"].isin(raices) & t["tramo"].isin(tramos) & t["zona"].between(S * (1 - dist / 100), S * (1 + dist / 100))]
    g = t.groupby("zona")[["oi_c", "oi_p", "gex", "gex_bruto_c", "gex_bruto_p"]].sum().reset_index()
    g["pct_puts"] = (g["oi_p"] / (g["oi_c"] + g["oi_p"]) * 100).where(g["oi_c"] + g["oi_p"] > 0)
    g["gex_bruto"] = g["gex_bruto_c"] + g["gex_bruto_p"]
    g["desbalance_pct"] = ((g["gex_bruto_c"] - g["gex_bruto_p"]).abs() / g["gex_bruto"] * 100).where(g["gex_bruto"] > 0)
    izq, der = st.columns(2)
    with izq:
        f1 = go.Figure()
        f1.add_trace(go.Bar(y=g["zona"], x=g["oi_c"], orientation="h", name="calls",
                            marker=dict(color=color_barras("oi_c", g["oi_c"], CALLS), pattern=patron("oi_c")),
                            hovertemplate="zona %{y:.0f} · OI calls %{x:,.0f}<extra></extra>"))
        f1.add_trace(go.Bar(y=g["zona"], x=-g["oi_p"], orientation="h", name="puts",
                            marker=dict(color=color_barras("oi_p", g["oi_p"], PUTS), pattern=patron("oi_p")),
                            customdata=g["oi_p"], hovertemplate="zona %{y:.0f} · OI puts %{customdata:,.0f}<extra></extra>"))
        f1.add_hline(y=S, line=dict(color=TINTA, width=2, dash="dot"), annotation_text=f"SPX {S:,.0f}")
        f1.update_layout(title=titulo("oi_c", "OI por zona (calls a la derecha, puts a la izquierda)"),
                         barmode="relative", bargap=0.15, height=700, xaxis_title="contratos",
                         yaxis_title="zona", legend=dict(orientation="h"))
        st.plotly_chart(f1, width="stretch")
    with der:
        f2 = go.Figure(go.Bar(y=g["zona"], x=g["gex"], orientation="h", name="GEX",
                              marker=dict(color=color_barras("gex", g["gex"], NEUTRO), pattern=patron("gex")),
                              hovertemplate="zona %{y:.0f} · " + etiqueta_eje("gex") + " %{x:+.2f}<extra></extra>"))
        f2.add_hline(y=S, line=dict(color=TINTA, width=2, dash="dot"), annotation_text=f"SPX {S:,.0f}")
        f2.update_layout(title=titulo("gex", "GEX por zona ($B por 1% de movimiento)"), bargap=0.15, height=700,
                         xaxis_title=etiqueta_eje("gex"), yaxis_title="zona", showlegend=False)
        st.plotly_chart(f2, width="stretch")
    izq2, der2 = st.columns(2)
    with izq2:
        f3 = go.Figure()
        # Agrupadas y las dos >= 0: NO espejadas (calls +, puts − imitaría el signo de la hipótesis nula)
        for col, color, nombre in [("gex_bruto_c", CALLS, "calls"), ("gex_bruto_p", PUTS, "puts")]:
            f3.add_trace(go.Bar(y=g["zona"], x=g[col], orientation="h", name=nombre,
                                marker=dict(color=color, pattern=patron(col)),
                                hovertemplate="zona %{y:.0f} · " + etiqueta_eje(col) + " %{x:,.2f}<extra></extra>"))
        f3.add_hline(y=S, line=dict(color=TINTA, width=2, dash="dot"), annotation_text=f"SPX {S:,.0f}")
        f3.update_layout(title=titulo("gex_bruto", "Gamma bruta por zona, calls y puts lado a lado (sin restar)"),
                         barmode="group", bargap=0.15, bargroupgap=0.05, height=700,
                         xaxis=dict(title=eje_comun(["gex_bruto_c", "gex_bruto_p"]), rangemode="tozero"),
                         yaxis_title="zona", legend=dict(orientation="h"))
        st.plotly_chart(f3, width="stretch")
    with der2:
        f4 = go.Figure(go.Bar(y=g["zona"], x=g["desbalance_pct"], orientation="h", name="desbalance",
                              marker=dict(color=NEUTRO, pattern=patron("desbalance_pct")),
                              customdata=g["gex_bruto"],
                              hovertemplate="zona %{y:.0f} · desbalance %{x:.0f}% (MODELO)"
                                            "<br>gamma bruta %{customdata:,.2f} $B (MODELO)<extra></extra>"))
        f4.add_vrect(x0=0, x1=30, fillcolor=TINTA_SUAVE, opacity=0.12, line_width=0,
                     annotation_text="calls ≈ puts: el GEX neto (SUPUESTO) es una resta", annotation_position="top left")
        f4.add_hline(y=S, line=dict(color=TINTA, width=2, dash="dot"), annotation_text=f"SPX {S:,.0f}")
        f4.update_layout(title=titulo("desbalance_pct", "Desbalance calls/puts: ¿el GEX neto sale de una resta?"),
                         bargap=0.15, height=700, xaxis=dict(range=[0, 100], title=etiqueta_eje("desbalance_pct")),
                         yaxis_title="zona", showlegend=False)
        st.plotly_chart(f4, width="stretch")
    st.caption("Gamma bruta y desbalance son MODELO (Black-Scholes con la IV de cierre), sin signo. Desbalance bajo "
               "(banda sombreada, < 30%) = calls y puts casi se cancelan: ahí el GEX de arriba (SUPUESTO) es la resta "
               "de dos números grandes y un cambio chico en el signo lo cambia mucho. Fuera de la banda el GEX NO "
               "pasa a ser medido: solo deja de depender de una resta; su signo sigue siendo supuesto. "
               "El 30% es una guía visual, no un umbral medido.")
    with st.expander("Tabla"):
        tabla(g.set_index("zona"))

# ---------------------------------------------------------------- 3. ficha de un wall
with tab_wall:
    cerca = Zv.copy()
    cerca["rk"] = cerca.groupby("fecha")["gex"].transform(lambda s: s.abs().rank(ascending=False))
    candidatos = sorted(cerca.loc[cerca["rk"] <= 8, "zona"].unique().astype(int))
    zona = st.selectbox("Wall (los 8 de mayor |GEX| algún día de la ventana; el ranking usa el GEX SUPUESTO)",
                        candidatos, index=candidatos.index(7750) if 7750 in candidatos else 0)
    w = Z[(Z["zona"] == zona) & (Z["fecha"] >= ini) & (Z["fecha"] <= fin)].set_index("fecha")
    flujo_w = w["flujo_de"].fillna("fuera de la serie")

    fa = go.Figure()
    for col, color, nombre in [("oi_c", CALLS, "OI calls"), ("oi_p", PUTS, "OI puts")]:
        fa.add_trace(go.Scatter(x=w.index, y=w[col], name=nombre, stackgroup="oi", line=linea(col, color),
                                hovertemplate="%{x|%d-%b} · " + nombre + " %{y:,.0f}<extra></extra>"))
    fa.update_layout(title=titulo("oi_c", f"Carga del wall {zona}: OI apilado (cierre del día anterior)"), height=320,
                     xaxis=eje_fecha, yaxis_title="contratos", legend=dict(orientation="h"), hovermode="x unified")
    st.plotly_chart(fa, width="stretch")

    fb = go.Figure()
    for col, color, nombre, signo, cuando in [
            ("doi_c", CALLS, "ΔOI calls (abiertas − cerradas)", 1, "flujo del %{customdata[1]}"),
            ("doi_p", PUTS, "ΔOI puts (abiertas − cerradas)", 1, "flujo del %{customdata[1]}"),
            ("oi_venc", NEUTRO, "vencido (sale del libro)", -1, "venció desde el archivo anterior (no es flujo)")]:
        fb.add_trace(go.Bar(x=w.index, y=signo * w[col], name=nombre,
                            marker=dict(color=color_barras(col, w[col], color), pattern=patron(col)),
                            customdata=np.column_stack([w[col], flujo_w]),
                            hovertemplate="archivo %{x|%d-%b} · " + cuando + "<br>" + nombre
                                          + " %{customdata[0]:,.0f}<extra></extra>"))
    fb.update_layout(title=titulo("doi_c", f"Rotación del wall {zona}: lo que se abrió vs lo que venció"),
                     barmode="group", bargap=0.2, bargroupgap=0.05, height=320, xaxis=eje_fecha,
                     yaxis_title="contratos", legend=dict(orientation="h"), hovermode="x unified")
    st.plotly_chart(fb, width="stretch")
    st.caption("Cada barra está en la fecha del ARCHIVO; el flujo que la explica es el del día de mercado "
               "anterior (en el hover). Lo vencido no es una posición cerrada.")

    fc = go.Figure(go.Scatter(x=w.index, y=w["gex"], mode="lines+markers", name="GEX",
                              line=linea("gex", TINTA_SUAVE), marker=dict(size=8),
                              hovertemplate="%{x|%d-%b} · " + etiqueta_eje("gex") + " %{y:+.2f}<extra></extra>"))
    fc.add_hline(y=0, line=dict(color="#c3c2b7", width=1))
    fc.update_layout(title=titulo("gex", f"GEX del wall {zona} ($B)"), height=280, xaxis=eje_fecha,
                     yaxis_title=etiqueta_eje("gex"), showlegend=False)
    st.plotly_chart(fc, width="stretch")
    with st.expander("Tabla"):
        tabla(w[["flujo_de", "S", "oi_c", "oi_p", "pct_puts", "doi_c", "doi_p", "oi_venc", "gex_bruto", "desbalance_pct",
                 "gex", "pos", "mer", "ven"]])

# ---------------------------------------------------------------- 4. descomposición
with tab_desc:
    dd = Dv.dropna(subset=["pos"])
    fd = go.Figure()
    for col, color in COLOR_COMPONENTE.items():
        fd.add_trace(go.Bar(x=dd.index, y=dd[col], name=ETIQUETAS[col] + (" (supuesto)" if supuesta(col) else ""),
                            marker=dict(color=color, pattern=patron(col)),
                            hovertemplate="%{x|%d-%b} · " + etiqueta_eje(col) + " %{y:+.2f}<extra></extra>"))
    fd.update_layout(title=titulo("pos", "Cambio diario del GEX total, por causa ($B)"), barmode="relative",
                     bargap=0.2, height=420, xaxis=eje_fecha, yaxis_title=eje_comun(list(COLOR_COMPONENTE)),
                     legend=dict(orientation="h"), hovermode="x unified")
    st.plotly_chart(fd, width="stretch")
    st.caption("Fechas = archivo d. 'posicionamiento' = ΔOI del flujo del día ANTERIOR valuado hoy; "
               "'mercado' y 'vencidas' = cambios entre el cierre anterior y el de d.")
    fs = go.Figure(go.Bar(x=dd.index, y=dd["dS"], marker=dict(color=color_barras("dS", dd["dS"], NEUTRO)),
                          hovertemplate="%{x|%d-%b} · ΔSPX %{y:+.1f} pts<extra></extra>"))
    fs.update_layout(title=titulo("dS", "Movimiento del SPX contra el cierre anterior (puntos)"), height=240,
                     xaxis=eje_fecha, yaxis_title="pts", showlegend=False)
    st.plotly_chart(fs, width="stretch")
    domina = int((dd["mer"].abs() > dd["pos"].abs()).sum())
    st.caption(f"SUPUESTO: |mercado| > |posicionamiento| en {domina} de {len(dd)} días. Este conteo no cambia "
               "si el signo supuesto se invierte para TODAS las opciones, pero sí si el signo real difiere "
               "por strike o vencimiento (lo que la fase B no pudo medir en el 98% del OI).")
    with st.expander("Tabla"):
        tabla(dd[["flujo_de", "S", "dS", "gex", "pos", "mer", "ven"]])

# ---------------------------------------------------------------- 5. rotación
with tab_rot:
    r = rotacion(Zv, candidatos)
    st.subheader("Rotación por wall en la ventana")
    st.caption("Filas: los mismos walls de la ficha, elegidos por ranking de |GEX| SUPUESTO; las columnas medidas "
               "valen por sí solas, pero QUÉ zonas aparecen depende del supuesto.")
    st.caption(f"oi_ini / pct_puts_ini = archivo {ini:%d-%b} (OI al cierre del día de mercado anterior); "
               f"oi_fin / pct_puts_fin = archivo {fin:%d-%b}. Un wall sin datos ese día queda vacío. "
               f"Flujos contados (doi): del {ini:%d-%b} al día de mercado anterior a {fin:%d-%b} (el ΔOI del archivo "
               f"{ini:%d-%b} se excluye: es flujo de un día fuera de la ventana). "
               "renovado_pct = OI vencido / oi_ini. Columnas [SUPUESTO $B] usan el signo de la hipótesis nula.")
    tabla(r.rename(index=int))
