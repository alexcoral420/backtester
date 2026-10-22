"""
Uso:  streamlit run app/panel.py        (desde la raíz del proyecto)

Panel de walls (SPX+SPXW, plazo horas): mapa, perfil del día, ficha de un wall, descomposición del
cambio de GEX y rotación. SOLO DIBUJA: lee las cadenas ya procesadas de data/procesado/ (las genera
scripts/walls_tiempo.py) y todos los números salen de src/walls.py. Nunca descarga ni pide la API key.

Convención medido / supuesto (contrato de walls.py, nunca a mano):
  MEDIDO   (OI, ΔOI, % puts):   escalas de un solo tono, barras sólidas
  SUPUESTO (gex, pos, mer, ven): escala divergente azul/rojo con gris en 0, barras RAYADAS,
                                 título y hover con "SUPUESTO" (signo de la hipótesis nula)
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

from src.walls import es_supuesta, evolucion, zonas_por_tramo

CARPETA = "data/procesado"
PATRON = os.path.join(CARPETA, "cadena_SPX+SPXW_horas_*.parquet")

# Paleta validada (dataviz, references/palette.md). Calls/puts = slots categóricos 1 y 2.
CALLS, PUTS, TERCERO = "#2a78d6", "#eb6834", "#1baf7a"
SEQ_AZUL = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
SEQ_NARANJA = ["#fde4d6", "#f6b08f", "#eb6834", "#b84a1f", "#7a2e10"]
DIVERGENTE = [[0.0, "#b3261e"], [0.25, "#e66767"], [0.5, "#e1e0d9"], [0.75, "#5598e7"], [1.0, "#104281"]]
NEUTRO, TINTA_SUAVE = "#898781", "#52514e"

ETIQUETAS = {
    "oi_c": "OI calls", "oi_p": "OI puts", "oi_total": "OI total", "pct_puts": "% del OI en puts",
    "doi_c": "ΔOI calls", "doi_p": "ΔOI puts", "oi_venc": "OI vencido",
    "gex": "GEX", "pos": "posicionamiento", "mer": "mercado", "ven": "vencidas", "S": "SPX",
}
MEDIDAS_EXTRA = {"oi_total"}            # derivadas de columnas medidas, también medidas


def supuesta(col):
    return False if col in MEDIDAS_EXTRA else es_supuesta(col)


def titulo(col, texto=None):
    t = texto or ETIQUETAS.get(col, col)
    return f"SUPUESTO · {t} (signo de la hipótesis nula)" if supuesta(col) else f"MEDIDO · {t}"


def unidad(col):
    return " $B" if supuesta(col) else ""


def patron(col):
    """Barras rayadas para lo supuesto (segunda codificación además del título)."""
    return dict(shape="/", fgcolor="rgba(255,255,255,0.55)", solidity=0.25) if supuesta(col) else None


# ---------------------------------------------------------------- datos (cache: no se recalcula al mover un control)

@st.cache_data(show_spinner="Leyendo cadenas procesadas…")
def cargar():
    rutas = sorted(glob.glob(PATRON))
    cadenas = {}
    for r in rutas:
        f = pd.Timestamp(re.search(r"(\d{4}-\d{2}-\d{2})\.parquet$", r).group(1))
        cadenas[f] = pd.read_parquet(r)
    if len(cadenas) < 2:
        return None, None, None
    D, Z = evolucion(cadenas)
    for col in ["gex", "pos", "mer", "ven"]:
        D[col], Z[col] = D[col] / 1e9, Z[col] / 1e9
    Z["S"] = Z["fecha"].map(D["S"])
    Z["dist_pct"] = (Z["zona"] - Z["S"]) / Z["S"] * 100
    Z["oi_total"] = Z["oi_c"] + Z["oi_p"]
    fechas = list(D.index)
    # Flujo que explica el ΔOI de cada fecha: el día anterior de la serie; si hay días hábiles en el medio
    # (huecos de datos o feriados), se avisa. Aproximado: no conoce feriados (la app no usa internet).
    flujo = {}
    for a, b in zip(fechas[:-1], fechas[1:]):
        extra = int(np.busday_count(a.date(), b.date())) - 1
        flujo[b] = a.strftime("%m-%d") + (f" (+{extra} día hábil sin datos o feriado)" if extra > 0 else "")
    D["flujo_de"] = pd.Series(flujo)
    return cadenas, D, Z


@st.cache_data
def perfil(fecha):
    cadenas, _, _ = cargar()
    t = zonas_por_tramo(cadenas[fecha])
    t["gex"] = t["gex"] / 1e9
    return t


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
    st.caption("**MEDIDO**: OI, ΔOI, % puts (sin signo).  \n"
               "**SUPUESTO**: GEX y su descomposición, con el signo de la hipótesis nula "
               "(público vende calls, compra puts). Barras rayadas = supuesto.")
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
    metrica = st.radio("Color", ["oi_total", "pct_puts", "gex"], horizontal=True,
                       format_func=lambda c: f"{ETIQUETAS[c]} ({'supuesto' if supuesta(c) else 'medido'})")
    m = Zv.pivot(index="zona", columns="fecha", values=metrica)
    if metrica == "gex":
        lim = float(np.nanmax(np.abs(m.values)))
        escala = dict(colorscale=DIVERGENTE, zmid=0, zmin=-lim, zmax=lim)
    else:
        escala = dict(colorscale=SEQ_AZUL if metrica == "oi_total" else SEQ_NARANJA)
    extra = Zv.pivot(index="zona", columns="fecha", values="oi_c"), Zv.pivot(index="zona", columns="fecha", values="oi_p")
    datos = np.dstack([extra[0].values, extra[1].values, Zv.pivot(index="zona", columns="fecha", values="gex").values])
    fig = go.Figure(go.Heatmap(
        x=m.columns, y=m.index, z=m.values, customdata=datos, xgap=2, ygap=2,
        colorbar=dict(title=ETIQUETAS[metrica] + unidad(metrica)), **escala,
        hovertemplate=("%{x|%d-%b} · zona %{y:.0f}<br>" + ETIQUETAS[metrica] + ": %{z:,.1f}" + unidad(metrica)
                       + "<br>OI calls %{customdata[0]:,.0f} · OI puts %{customdata[1]:,.0f}"
                       + "<br>GEX %{customdata[2]:+.2f} $B (SUPUESTO)<extra></extra>")))
    fig.add_trace(go.Scatter(x=Dv.index, y=Dv["S"], mode="lines+markers", name="SPX cierre",
                             line=dict(color="#0b0b0b", width=2), marker=dict(size=8, color="#fcfcfb",
                             line=dict(color="#0b0b0b", width=2)),
                             hovertemplate="%{x|%d-%b} · SPX %{y:,.2f}<extra></extra>"))
    fig.update_layout(title=titulo(metrica, f"{ETIQUETAS[metrica]} por zona y día, con el SPX encima"),
                      height=650, xaxis=eje_fecha, yaxis_title="zona (25 pts)", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    st.caption("Lectura: el mapa (filas) cambia lento; el precio (línea) se mueve por encima. "
               "Una zona que cambia de color a lo largo de una fila es posicionamiento que cambió.")

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
    g = t.groupby("zona")[["oi_c", "oi_p", "gex"]].sum().reset_index()
    izq, der = st.columns(2)
    with izq:
        f1 = go.Figure()
        f1.add_trace(go.Bar(y=g["zona"], x=g["oi_c"], orientation="h", name="calls", marker_color=CALLS,
                            hovertemplate="zona %{y:.0f} · OI calls %{x:,.0f}<extra></extra>"))
        f1.add_trace(go.Bar(y=g["zona"], x=-g["oi_p"], orientation="h", name="puts", marker_color=PUTS,
                            customdata=g["oi_p"], hovertemplate="zona %{y:.0f} · OI puts %{customdata:,.0f}<extra></extra>"))
        f1.add_hline(y=S, line=dict(color="#0b0b0b", width=2, dash="dot"), annotation_text=f"SPX {S:,.0f}")
        f1.update_layout(title=titulo("oi_c", "OI por zona (calls a la derecha, puts a la izquierda)"),
                         barmode="relative", bargap=0.15, height=700, xaxis_title="contratos",
                         yaxis_title="zona", legend=dict(orientation="h"))
        st.plotly_chart(f1, width="stretch")
    with der:
        colores = np.where(g["gex"] >= 0, "#3987e5", "#e66767")
        f2 = go.Figure(go.Bar(y=g["zona"], x=g["gex"], orientation="h", marker=dict(color=colores, pattern=patron("gex")),
                              name="GEX", hovertemplate="zona %{y:.0f} · GEX %{x:+.2f} $B (SUPUESTO)<extra></extra>"))
        f2.add_hline(y=S, line=dict(color="#0b0b0b", width=2, dash="dot"), annotation_text=f"SPX {S:,.0f}")
        f2.update_layout(title=titulo("gex", "GEX por zona ($B)"), bargap=0.15, height=700,
                         xaxis_title="$B por 1% de movimiento", yaxis_title="zona", showlegend=False)
        st.plotly_chart(f2, width="stretch")
    with st.expander("Tabla"):
        st.dataframe(g.assign(pct_puts=g["oi_p"] / (g["oi_c"] + g["oi_p"]) * 100).round(2), width="stretch")

# ---------------------------------------------------------------- 3. ficha de un wall
with tab_wall:
    cerca = Zv.copy()
    cerca["rk"] = cerca.groupby("fecha")["gex"].transform(lambda s: s.abs().rank(ascending=False))
    candidatos = sorted(cerca.loc[cerca["rk"] <= 8, "zona"].unique().astype(int))
    zona = st.selectbox("Wall (top-8 de |GEX| algún día en la ventana)", candidatos,
                        index=candidatos.index(7750) if 7750 in candidatos else 0)
    w = Z[(Z["zona"] == zona) & (Z["fecha"] >= ini) & (Z["fecha"] <= fin)].set_index("fecha")

    fa = go.Figure()
    fa.add_trace(go.Scatter(x=w.index, y=w["oi_c"], name="OI calls", stackgroup="oi", line=dict(color=CALLS, width=2),
                            hovertemplate="%{x|%d-%b} · calls %{y:,.0f}<extra></extra>"))
    fa.add_trace(go.Scatter(x=w.index, y=w["oi_p"], name="OI puts", stackgroup="oi", line=dict(color=PUTS, width=2),
                            hovertemplate="%{x|%d-%b} · puts %{y:,.0f}<extra></extra>"))
    fa.update_layout(title=titulo("oi_c", f"Carga del wall {zona}: OI apilado"), height=320, xaxis=eje_fecha,
                     yaxis_title="contratos", legend=dict(orientation="h"), hovermode="x unified")
    st.plotly_chart(fa, width="stretch")

    fb = go.Figure()
    fb.add_trace(go.Bar(x=w.index, y=w["doi_c"], name="ΔOI calls (abiertas − cerradas)", marker_color=CALLS,
                        hovertemplate="%{x|%d-%b} · ΔOI calls %{y:+,.0f}<extra></extra>"))
    fb.add_trace(go.Bar(x=w.index, y=w["doi_p"], name="ΔOI puts", marker_color=PUTS,
                        hovertemplate="%{x|%d-%b} · ΔOI puts %{y:+,.0f}<extra></extra>"))
    fb.add_trace(go.Bar(x=w.index, y=-w["oi_venc"], name="vencido (sale del libro)", marker_color=NEUTRO,
                        customdata=w["oi_venc"], hovertemplate="%{x|%d-%b} · vencido %{customdata:,.0f}<extra></extra>"))
    fb.update_layout(title=titulo("doi_c", f"Rotación del wall {zona}: lo que se abrió vs lo que venció"),
                     barmode="group", bargap=0.2, bargroupgap=0.05, height=320, xaxis=eje_fecha,
                     yaxis_title="contratos", legend=dict(orientation="h"), hovermode="x unified")
    st.plotly_chart(fb, width="stretch")
    st.caption("El ΔOI de cada fecha es el flujo del día de mercado ANTERIOR (regla de tiempo).")

    fc = go.Figure(go.Scatter(x=w.index, y=w["gex"], mode="lines+markers", name="GEX",
                              line=dict(color=TINTA_SUAVE, width=2, dash="dash"), marker=dict(size=8),
                              hovertemplate="%{x|%d-%b} · GEX %{y:+.2f} $B (SUPUESTO)<extra></extra>"))
    fc.add_hline(y=0, line=dict(color="#c3c2b7", width=1))
    fc.update_layout(title=titulo("gex", f"GEX del wall {zona} ($B)"), height=280, xaxis=eje_fecha,
                     yaxis_title="$B", showlegend=False)
    st.plotly_chart(fc, width="stretch")
    with st.expander("Tabla"):
        st.dataframe(w[["S", "oi_c", "oi_p", "pct_puts", "doi_c", "doi_p", "oi_venc", "gex", "pos", "mer", "ven"]]
                     .round(2), width="stretch")

# ---------------------------------------------------------------- 4. descomposición
with tab_desc:
    dd = Dv.dropna(subset=["pos"])
    fd = go.Figure()
    for col, color in [("pos", CALLS), ("mer", PUTS), ("ven", TERCERO)]:
        fd.add_trace(go.Bar(x=dd.index, y=dd[col], name=ETIQUETAS[col], marker=dict(color=color, pattern=patron(col)),
                            hovertemplate="%{x|%d-%b} · " + ETIQUETAS[col] + " %{y:+.2f} $B (SUPUESTO)<extra></extra>"))
    fd.update_layout(title=titulo("pos", "Cambio diario del GEX total, por causa ($B)"), barmode="relative",
                     bargap=0.2, height=420, xaxis=eje_fecha, yaxis_title="$B", legend=dict(orientation="h"),
                     hovermode="x unified")
    st.plotly_chart(fd, width="stretch")
    dS = D["S"].diff().reindex(dd.index)             # contra el día anterior de la serie COMPLETA
    fs = go.Figure(go.Bar(x=dd.index, y=dS, marker_color=NEUTRO, hovertemplate="%{x|%d-%b} · ΔSPX %{y:+.1f} pts<extra></extra>"))
    fs.update_layout(title=titulo("S", "Movimiento del SPX ese día (puntos)"), height=240, xaxis=eje_fecha,
                     yaxis_title="pts", showlegend=False)
    st.plotly_chart(fs, width="stretch")
    mismo = int((dd["mer"] * dS > 0).sum())
    st.caption(f"'mercado' tuvo el mismo signo que el movimiento del SPX en {mismo} de {len(dd)} días: "
               "el GEX total sigue sobre todo al precio, no al posicionamiento.")
    with st.expander("Tabla"):
        st.dataframe(dd[["S", "gex", "pos", "mer", "ven", "flujo_de"]].round(2), width="stretch")

# ---------------------------------------------------------------- 5. rotación
with tab_rot:
    W = Zv[Zv["zona"].isin(candidatos) & (Zv["fecha"] > ini)]
    Wt = Zv[Zv["zona"].isin(candidatos)]
    r = W.groupby("zona")[["doi_c", "doi_p", "oi_venc", "pos", "mer", "ven"]].sum()
    r.insert(0, "oi_ini", Wt.groupby("zona")["oi_total"].first())
    r.insert(1, "oi_fin", Wt.groupby("zona")["oi_total"].last())
    r.insert(2, "pct_puts_ini", Wt.groupby("zona")["pct_puts"].first())
    r.insert(3, "pct_puts_fin", Wt.groupby("zona")["pct_puts"].last())
    r["renovado_%"] = (r["oi_venc"] / r["oi_ini"] * 100)
    st.subheader("Rotación por wall en la ventana")
    st.caption("MEDIDO: oi_ini/fin, pct_puts, doi (abierto neto, sin vencimientos), oi_venc, renovado_% "
               "(vencido / OI inicial).  SUPUESTO ($B): pos, mer, ven.")
    st.dataframe(r.rename(index=int).round(1), width="stretch")
