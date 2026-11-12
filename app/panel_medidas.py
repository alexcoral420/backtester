"""
Uso:  streamlit run app/panel_medidas.py        (desde la raíz del proyecto)

Panel de las medidas sin signo del dealer (rama medidas-sin-signo): el rango implícito (straddle ATM) y la
gamma recalculada a otro precio. Cuatro vistas, lo mínimo para leerlas:
  1. Rango implícito    lo que el mercado cobraba la víspera contra lo que el SPX se movió      MEDIDO
  2. Gamma por precio   el mapa de gamma bruta de una foto llevado a otro precio                MODELO
                        (y, aparte, el neto con la hipótesis nula por precio)                   SUPUESTO
  3. Verificación       error de la gamma recalculada contra la foto real del día siguiente     MODELO
  4. Intradía           gamma en el precio actual contra el rango de los 30 min siguientes      MODELO vs MEDIDO

SOLO DIBUJA: todo sale de src/vista_medidas.py, que lee archivos ya calculados (data/validacion y
data/procesado/perfil_gamma_*.parquet). No importa config ni datos: no pide la API key ni puede gastar crédito.
La clase de cada columna la decide vista_medidas.clase; cómo se dibuja cada clase está en app/estilo.py.
Un eje nunca mezcla unidades ni clases distintas sin decirlo en el texto y en el patrón.
"""
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.estilo import (CALLS, GRILLA, MEDIDO_MIXTO, MODELO_MIXTO, NEGATIVO, ORDINAL_VIOLETA, POSITIVO, PUTS,   # noqa: E402
                        ROTULO, SUPERFICIE, TINTA_SUAVE, linea_clase, patron_clase)
from src import vista_medidas as vm                                                                     # noqa: E402

AZUL, NARANJA = CALLS, PUTS          # dos series MEDIDAS en un mismo gráfico (par validado)
VIOLETA_TENUE, VIOLETA = ORDINAL_VIOLETA[0], ORDINAL_VIOLETA[-1]     # [0] se funde con la superficie, [-1] resalta


def rotulo(col):
    """MEDIDO / MODELO / SUPUESTO según el contrato; grita si la columna no está clasificada."""
    return ROTULO[vm.clase(col)]


def corto(fecha):
    return pd.Timestamp(fecha).strftime("%d-%b")


def base_layout(fig, alto, **kw):
    fig.update_layout(height=alto, margin=dict(l=70, r=20, t=90, b=50), title_y=0.97,
                      legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"), **kw)
    fig.update_xaxes(gridcolor=GRILLA, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=GRILLA, zeroline=False, automargin=True)
    return fig


def _intentar(funcion, *args):
    """(resultado, None) o (None, motivo): lo que falta se explica en vez de romper la página."""
    try:
        return funcion(*args), None
    except vm.SinDatos as e:
        return None, str(e)


@st.cache_data(show_spinner=False)
def datos_rango():
    return _intentar(vm.rango)


@st.cache_data(show_spinner=False)
def datos_verificacion():
    return _intentar(vm.verificacion)


@st.cache_data(show_spinner=False)
def datos_local():
    return _intentar(vm.gamma_local)


@st.cache_data(show_spinner=False)
def datos_perfil(fecha):
    return _intentar(vm.perfil, fecha)


# ---------------------------------------------------------------- página

st.set_page_config(page_title="Medidas sin signo", layout="wide")
rg, falta_rg = datos_rango()
ver, falta_ver = datos_verificacion()
loc, falta_loc = datos_local()
fotos = vm.fotos_con_perfil()

with st.sidebar:
    st.header("Medidas sin signo")
    st.caption("**MEDIDO**: precios de mercado (straddle) y movimientos del SPX. Sólido.  \n"
               "**MODELO**: gamma Black-Scholes · OI, calls y puts SUMADAS, sin signo, y su error contra la foto "
               "real. Violeta punteado.  \n"
               "**SUPUESTO**: el neto con el signo de la hipótesis nula (público vende calls, compra puts). "
               "Rayado. Solo aparece aparte, nunca sumado a lo demás.")
    st.caption("Solo lectura: el panel no descarga, no cotiza y no recalcula. Los archivos los generan "
               "`validar_rango.py`, `verificar_gamma.py`, `validar_gamma_local.py` y `perfil_gamma.py --todas`.")

st.title("Medidas sin signo: rango implícito y gamma recalculada")

# --- lo esencial, en cuatro números
k1, k2, k3, k4 = st.columns(4)
res_rg = vm.resumen_rango(rg) if rg is not None else None
if rg is not None:
    u = rg.iloc[-1]
    k1.metric(f"Straddle al cierre del {corto(u['fecha'])} · MEDIDO", f"{u['impl_pct']:.2f}% del SPX",
              f"{u['straddle']:.0f} pts ± {u['ancho'] / 2:.1f}", delta_color="off")
    c = res_rg["comparacion"]
    k2.metric("Error del straddle contra el rango siguiente · MEDIDO",
              f"{c.at['impl_pct', 'error_medio']:.2f}% del SPX",
              f"ingenuo {c.at['rango_hoy_pct', 'error_medio']:.2f} · gana {res_rg['gana']} de "
              f"{res_rg['episodios']} episodios (orientativo)", delta_color="off")
if ver is not None:
    k3.metric("Error de la gamma recalculada · MODELO", f"{ver['err_recalculada'].median():.1f}% por zona",
              f"foto vieja {ver['err_vieja'].median():.1f}% · mejor en "
              f"{int((ver['err_recalculada'] < ver['err_vieja']).sum())} de {len(ver)} pares", delta_color="off")
res_loc = vm.resumen_local(loc) if loc is not None else None
if loc is not None:
    g = res_loc.loc["gex_bruto_B"]
    k4.metric("Gamma actual (MODELO) vs rango 30 min (MEDIDO)", f"{g['entre_dias']:+.2f} entre días",
              f"{g['dentro_del_dia']:+.2f} dentro del día ({int(g['dias'])} días, orientativo)", delta_color="off")

tab_rango, tab_gamma, tab_ver, tab_intra = st.tabs(
    ["Rango implícito", "Gamma por precio", "Verificación", "Intradía"])

# ---------------------------------------------------------------- 1. rango implícito (MEDIDO)
with tab_rango:
    if rg is None:
        st.info(falta_rg)
    else:
        dias = [corto(f) for f in rg["sig"]]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=dias, y=rg["mov_sig_pct"], name="|movimiento| cierre → cierre del día (MEDIDO)",
            marker=dict(color=AZUL, line=dict(color=SUPERFICIE, width=2)),
            customdata=np.column_stack([rg["rango_sig_pct"], rg["fecha"]]),
            hovertemplate=("%{x}<br>movimiento %{y:.2f}% · rango del día %{customdata[0]:.2f}%"
                           "<extra></extra>")))
        fig.add_trace(go.Scatter(
            x=dias, y=rg["impl_pct"], name="straddle ATM de la víspera (MEDIDO)", mode="lines+markers",
            line=linea_clase(vm.clase("impl_pct"), NARANJA), marker=dict(size=8, color=NARANJA,
                                                                         line=dict(color=SUPERFICIE, width=2)),
            customdata=np.column_stack([rg["straddle"], rg["ancho"], rg["fecha"]]),
            hovertemplate=("straddle al cierre del %{customdata[2]}: %{y:.2f}% del SPX"
                           "<br>%{customdata[0]:.1f} pts, bid/ask %{customdata[1]:.1f} pts<extra></extra>")))
        fig.update_xaxes(type="category", tickangle=-45, title_text="día (el straddle es el del cierre anterior)")
        fig.update_yaxes(title_text="% del SPX", rangemode="tozero")
        base_layout(fig, 430, title="Lo que el mercado cobraba la víspera contra lo que el SPX se movió · MEDIDO")
        st.plotly_chart(fig, width="stretch")

        cal = res_rg["calibracion"]
        st.caption(
            f"{res_rg['dias']} días. El movimiento fue en promedio {cal['razon_media']:.2f} veces el straddle "
            f"(mediana {cal['razon_mediana']:.2f}); {cal['pct_dentro']:.0f}% de los días quedó por debajo "
            f"(con precio justo y movimientos normales ≈ 57%). Barra por encima de la línea = el día se movió más de lo que el mercado "
            f"cobraba.")
        t = res_rg["comparacion"].copy()
        t.insert(0, "clase", [rotulo(i) for i in t.index])
        t.index = [vm.NOMBRE[i] for i in t.index]
        st.dataframe(t.rename(columns={"n": "días", "spearman": "Spearman con el rango siguiente",
                                       "error_medio": "error medio (% del SPX)"}).round(2), width="stretch")
        st.caption(f"El straddle le gana al rango de hoy en {res_rg['gana']} de {res_rg['episodios']} episodios de "
                   "volatilidad (el tamaño honesto de la muestra): orientativo, no evidencia. El GEX neto es "
                   "**SUPUESTO** y va solo de referencia; con signo no tiene escala, por eso no tiene error.")

# ---------------------------------------------------------------- 2. gamma por precio (MODELO; neto SUPUESTO aparte)
with tab_gamma:
    if not fotos:
        st.info("No hay perfiles guardados. Se generan con: python scripts/perfil_gamma.py --todas")
    else:
        a, b = st.columns([1, 3])
        fecha = a.selectbox("Foto (cierre de)", fotos[::-1], format_func=corto)
        p, falta = datos_perfil(fecha)
        if p is None:
            st.info(falta)
        else:
            S = float(p["S"].iloc[0])
            rejilla = sorted(x for x in p["spot"].unique() if x != S)
            spot = b.select_slider("Precio hipotético del SPX", options=rejilla,
                                   value=min(rejilla, key=lambda x: abs(x - (S - 150))),
                                   format_func=lambda x: f"{x:,.0f}")
            mov = 100 * (spot / S - 1)
            m = vm.mapa(p, spot)
            fig = go.Figure()
            for col, color, nombre in (("foto", VIOLETA_TENUE, f"en el cierre de la foto ({S:,.0f})"),
                                       ("recalculada", VIOLETA, f"recalculada en {spot:,.0f}")):
                fig.add_trace(go.Bar(
                    x=m.index, y=m[col], name=f"gamma bruta {nombre} (MODELO)", width=9,
                    marker=dict(color=color, pattern=patron_clase(vm.clase(col)),
                                line=dict(color=SUPERFICIE, width=1)),
                    hovertemplate="zona %{x:.0f} · %{y:.2f} $B (MODELO, sin signo)<extra>" + nombre + "</extra>"))
            fig.add_vline(x=spot, line=dict(color=TINTA_SUAVE, width=1, dash="dot"),
                          annotation_text=f"precio hipotético {spot:,.0f}", annotation_position="top right")
            if abs(S - spot) <= 250:
                fig.add_vline(x=S, line=dict(color=TINTA_SUAVE, width=1), annotation_text="cierre de la foto",
                              annotation_position="top left")
            fig.update_xaxes(title_text="zona (25 pts)", dtick=50)
            fig.update_yaxes(title_text="$B por 1% de movimiento (MODELO)", rangemode="tozero")
            base_layout(fig, 430, barmode="group", bargap=0.15,
                        title=f"Foto del {corto(fecha)}: gamma bruta por zona si el SPX va a {spot:,.0f} "
                              f"({mov:+.1f}%) · MODELO, sin signo")
            st.plotly_chart(fig, width="stretch")
            top_f, top_r = set(m["foto"].nlargest(5).index), set(m["recalculada"].nlargest(5).index)
            texto = (f"Cobertura: {p['cobertura_pct'].iloc[0]:.1f}% del OI tiene volatilidad. De las 5 zonas con "
                     f"más gamma en este tramo según la foto, {len(top_f & top_r)} siguen entre las 5 al recalcular.")
            if ver is not None:
                e = vm.banda_error(ver, mov)
                texto += (f" **Banda de error**: en movimientos de {e['tramo']} ({e['n']} pares verificados) la "
                          f"recalculada se equivocó {e['err_recalculada']:.1f}% por zona (peor {e['peor']:.1f}%), "
                          f"contra {e['err_vieja']:.1f}% de usar la foto sin recalcular.")
            st.caption(texto + " No incluye lo que vence el mismo día (0DTE).")

            tot = vm.totales_por_spot(p)
            fs = go.Figure(go.Bar(
                x=tot.index, y=tot["gex_sup"], width=18,
                marker=dict(color=np.where(tot["gex_sup"] >= 0, POSITIVO, NEGATIVO),
                            pattern=patron_clase(vm.clase("gex_sup"))),
                customdata=tot["gex_bruto"],
                hovertemplate=("SPX %{x:,.0f} · neto %{y:+.1f} $B (SUPUESTO)"
                               "<br>bruto %{customdata:.0f} $B (MODELO)<extra></extra>")))
            fs.add_hline(y=0, line=dict(color=TINTA_SUAVE, width=1))
            fs.add_vline(x=S, line=dict(color=TINTA_SUAVE, width=1), annotation_text="cierre de la foto",
                         annotation_position="top left", annotation_bgcolor=SUPERFICIE)
            fs.update_xaxes(title_text="precio hipotético del SPX")
            fs.update_yaxes(title_text="$B (SUPUESTO)")
            base_layout(fs, 300, showlegend=False,
                        title="Neto con la hipótesis nula según el precio · SUPUESTO (no es un nivel medido)")
            st.plotly_chart(fs, width="stretch")
            st.caption("El neto es la resta de dos números grandes con un signo **SUPUESTO**: el precio donde "
                       "cruza cero solo vale si el supuesto vale. Un caso, no una prueba: en la foto del 4-nov era "
                       "positivo y el día siguiente el SPX cayó 335 pts.")

# ---------------------------------------------------------------- 3. verificación (MODELO contra la foto real)
with tab_ver:
    if ver is None:
        st.info(falta_ver)
    else:
        fig = go.Figure()
        for col, color, simbolo, nombre in (("err_vieja", VIOLETA_TENUE, "circle-open", "foto vieja sin recalcular"),
                                            ("err_recalculada", VIOLETA, "circle", "gamma recalculada")):
            fig.add_trace(go.Scatter(
                x=ver["mov_abs"], y=ver[col], mode="markers", name=f"{nombre} (MODELO)",
                marker=dict(size=10, color=color, symbol=simbolo, line=dict(color=color, width=2)),
                customdata=np.column_stack([ver["foto"], ver["sig"], ver["mov_pct"]]),
                hovertemplate=("%{customdata[0]} → %{customdata[1]} (SPX %{customdata[2]:+.2f}%)"
                               "<br>" + nombre + ": error %{y:.1f}% del real (MODELO)<extra></extra>")))
        fig.update_xaxes(title_text="|movimiento del SPX| entre las dos fotos, %", rangemode="tozero")
        fig.update_yaxes(title_text="error por zona, % de la gamma real (MODELO)", rangemode="tozero")
        base_layout(fig, 430, title="¿Cuánto se equivoca? Gamma de d llevada al cierre de d+1 contra la foto real "
                                    "de d+1 · MODELO")
        st.plotly_chart(fig, width="stretch")
        filas = []
        for nombre, mov in (("menos de 0,5%", 0.1), ("0,5% a 1%", 0.7), ("1% o más", 2.0)):
            e = vm.banda_error(ver, mov)
            filas.append({"movimiento": nombre, "pares": e["n"],
                          f"recalculada, mediana % [{rotulo('err_recalculada')}]": e["err_recalculada"],
                          f"recalculada, peor % [{rotulo('err_recalculada')}]": e["peor"],
                          f"foto vieja, mediana % [{rotulo('err_vieja')}]": e["err_vieja"]})
        st.dataframe(pd.DataFrame(filas).round(1), width="stretch", hide_index=True)
        st.caption(f"Todo **MODELO** (gamma Black-Scholes · OI, sin signo) contra la gamma de la foto real. "
                   f"{len(ver)} pares de fotos de días seguidos, mismas series y OI de d: solo cambia la gamma. Cada "
                   "foto reproduce su propia gamma guardada al recalcular en su precio (si no, el script se "
                   "detiene). El error no se corrige: corregirlo sería suponer cómo se mueve la volatilidad.")

# ---------------------------------------------------------------- 4. intradía (MODELO contra MEDIDO)
with tab_intra:
    if loc is None:
        st.info(falta_loc)
    else:
        r = res_loc.iloc[::-1]
        nombres = [f"{vm.NOMBRE[i]} · {ROTULO[c]}" for i, c in zip(r.index, r["clase"])]
        color_clase = {"modelo": MODELO_MIXTO, "medido": MEDIDO_MIXTO}     # una clase supuesta aquí debe gritar
        colores = [color_clase[c] for c in r["clase"]]
        formas = [(patron_clase(c) or {}).get("shape", "") for c in r["clase"]]
        trama = {k: v for k, v in patron_clase("modelo").items() if k != "shape"}
        fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.06,
                            subplot_titles=("Entre días, misma franja horaria", "Dentro del mismo día"))
        for i, (col, grupos) in enumerate((("entre_dias", "franjas"), ("dentro_del_dia", "dias")), start=1):
            fig.add_trace(go.Bar(
                y=nombres, x=r[col], orientation="h", width=0.55, showlegend=False,
                marker=dict(color=colores, pattern=dict(shape=formas, **trama)),
                text=[f"{v:+.2f}" if pd.notna(v) else "sin dato" for v in r[col]], textposition="outside",
                cliponaxis=False, customdata=r[grupos],
                hovertemplate="%{y}<br>Spearman mediano %{x:+.2f} (%{customdata} grupos)<extra></extra>"),
                row=1, col=i)
            fig.add_vline(x=0, line=dict(color=TINTA_SUAVE, width=1), row=1, col=i)
            fig.update_xaxes(title_text="Spearman con el rango de los 30 min siguientes", range=[-0.75, 0.75],
                             row=1, col=i)
        base_layout(fig, 360, title="¿Qué anticipa el rango de los próximos 30 minutos? · naranja = MEDIDO, "
                                    "violeta punteado = MODELO")
        st.plotly_chart(fig, width="stretch")
        g = res_loc.loc["gex_bruto_B"]
        st.caption(
            f"{len(loc)} bloques de 30 min en {loc['fecha'].nunique()} días; el tamaño honesto de la muestra son "
            f"los días. **Entre días** (misma franja): más gamma bruta en el precio actual va con menos rango "
            f"({g['entre_dias']:+.2f}, mismo signo en {int(g['franjas_mismo_signo'])} de {int(g['franjas'])} "
            f"franjas), de tamaño parecido al ingenuo y al straddle y de signo opuesto. **Dentro del día** no hay evidencia de relación "
            f"({g['dentro_del_dia']:+.2f}; {int(g['dias_negativos'])} de {int(g['dias'])} días negativos): con esta muestra no sirve "
            "para elegir el momento. La gamma escala con 1/volatilidad, así que parte de esto es la volatilidad "
            "implícita leída de otra forma. Orientativo, no evidencia. El straddle es uno por día: no tiene corte "
            "dentro del día.")
