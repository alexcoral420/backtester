"""
Uso:  streamlit run app/panel_odte.py        (desde la raíz del proyecto)

Panel del módulo 0DTE (src/odte): el día con sus toques y la carga, el flujo por minuto, M4 (carga contra
toques), la muestra y por qué no hay signo (M1 y M2). SOLO DIBUJA: todos los datos salen de src/odte/vista.py,
que lee únicamente la caché (data/raw, data/procesado, data/validacion). Nunca descarga ni pide la API key.

Días sin datos: no rompen. vista.inventario() dice qué se puede dibujar cada día hábil; lo que falta se lista
(p. ej. el 2026-10-20, sin datos en Databento) y cada gráfico avisa con el motivo en vez de fallar.

Convención medido / modelo / supuesto: la CLASE de cada columna la decide carga.clase (contrato de M4), nunca a
mano; cómo se dibuja cada clase está en app/estilo.py.
  MEDIDO   precio, toques, OI, flujo clasificado:  sólido, líneas continuas
  MODELO   gamma bruta (sin signo):                 violeta, punteado, "MODELO" en el texto
  SUPUESTO GEX neto y wall (hipótesis nula):        rayado, "SUPUESTO" en el texto; nunca en el eje de la carga
Un eje nunca mezcla clases ni unidades: cada magnitud tiene su propio panel (no hay ejes dobles).
"""
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.estilo import (CALLS, COLOR_RESULTADO, COMPRA, GRILLA, NEGATIVO, NEUTRO, ORDINAL_AZUL, ORDINAL_VIOLETA,
                        POSITIVO, PUTS, ROTULO, SIMBOLO_RESULTADO, SUPERFICIE, TINTA, TINTA_SUAVE, VENTA,
                        linea_clase, patron_clase)
from src.odte import carga as cg
from src.odte import vista
from src.odte.toques import AGUANTO, CRUZO, VENTANA_CORTA, Definicion

DEF = Definicion()
RESULTADOS = [AGUANTO, CRUZO, VENTANA_CORTA]
NOMBRE_PREDICTOR = {"base": "frecuencia base", "mult100": "múltiplo de 100 aguanta", "distancia": "distancia previa",
                    "carga_oi": "carga por OI", "carga_bruto": "carga por gamma bruta", "wall_sup": "wall con signo"}
# Clase de cada predictor: la de la columna en la que se apoya (contrato de carga.py). Los ingenuos no usan carga.
CLASE_PREDICTOR = {"carga_oi": cg.clase("pct_carga_oi"), "carga_bruto": cg.clase("pct_carga_bruto"),
                   "wall_sup": cg.clase("es_wall_sup")}


def rotulo(col):
    """MEDIDO / MODELO / SUPUESTO según el contrato; grita si la columna no está clasificada."""
    return ROTULO[vista.clase(col)]


def hora(idx):
    """Plotly dibuja las horas con zona en UTC: se le pasa la hora de Nueva York sin zona."""
    return idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx


def corto(fecha):
    return pd.Timestamp(fecha).strftime("%d-%b")


def base_layout(fig, alto, **kw):
    fig.update_layout(height=alto, margin=dict(l=70, r=20, t=60, b=50), legend=dict(orientation="h", y=-0.14), **kw)
    fig.update_xaxes(gridcolor=GRILLA, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=GRILLA, zeroline=False, automargin=True)
    return fig


# ---------------------------------------------------------------- datos (solo caché; SinDatos -> texto, no error)

@st.cache_data(show_spinner="Leyendo la caché…")
def inventario():
    return vista.inventario()


def _intentar(funcion, *args):
    """(resultado, None) o (None, motivo). Un día sin datos devuelve su motivo en vez de romper la página."""
    try:
        return funcion(*args), None
    except vista.SinDatos as e:
        return None, str(e)


@st.cache_data(show_spinner=False)
def precio_y_toques(fecha):
    spx, motivo = _intentar(vista.spx_dia, fecha)
    if spx is None:
        return None, None, motivo
    return spx, vista.toques_dia(fecha, DEF), None


@st.cache_data(show_spinner=False)
def carga(fecha):
    return _intentar(vista.carga_del_dia, fecha)


@st.cache_data(show_spinner="Clasificando trades…")
def flujo(fecha, estricto):
    return _intentar(vista.flujo_dia, fecha, estricto)


@st.cache_data(show_spinner="Buscando días con flujo en caché…")
def dias_con_flujo(candidatos):
    """Días cuyo tcbbo en caché cubre alguna serie 0DTE, y por qué no los demás."""
    ok, sin = [], {}
    for f in candidatos:
        r, motivo = flujo(f, True)
        if r is None:
            sin[f] = motivo
        else:
            ok.append(f)
    return ok, sin


@st.cache_data(show_spinner=False)
def acumulador_carga():
    return vista.leer_carga()


@st.cache_data(show_spinner=False)
def acumulador_m2():
    return vista.leer_toques_m2()


# ---------------------------------------------------------------- página

st.set_page_config(page_title="0DTE SPX", layout="wide")
inv = inventario()
if inv.empty:
    st.error("No hay datos del módulo 0DTE en caché (data/raw, data/procesado). El panel solo lee: los datos se "
             "generan con scripts/walls_tiempo.py y los scripts de scripts/odte/, que avisan el costo antes de bajar.")
    st.stop()

with st.sidebar:
    st.header("Panel 0DTE")
    st.caption("**MEDIDO**: precio, toques, OI y flujo clasificado. Sólido.  \n"
               "**MODELO**: gamma bruta (Black-Scholes · OI, calls y puts SUMADAS, sin signo). Violeta punteado.  \n"
               "**SUPUESTO**: GEX neto y wall, con el signo de la hipótesis nula (público vende calls, compra "
               "puts). Rayado.")
    st.caption(f"Definición del toque: `{DEF.etiqueta()}` — múltiplos de {DEF.paso}, a ≤ {DEF.tolerancia:g} pts, "
               f"desde las {DEF.desde}; cruza si pasa {DEF.margen:g} pts en {DEF.ventana_min} min.")
    st.caption(f"{len(inv)} días hábiles entre {corto(inv.index[0])} y {corto(inv.index[-1])}: "
               f"{int(inv['precio_ok'].sum())} con precio, {int(inv['carga_ok'].sum())} con carga, "
               f"{int((inv['catalogo'] & inv['tcbbo']).sum())} con catálogo y tcbbo.")
    vacios = [corto(f) for f in inv.index[inv["falta"].str.startswith("todo")]]
    if vacios:
        st.caption("Sin ningún dato (feriado o sin datos en Databento): " + ", ".join(vacios) + ". Se saltan.")
    st.caption("Solo lectura: el panel no descarga ni cotiza.")

st.title("0DTE: toques, carga y flujo")
tab_dia, tab_flujo, tab_m4, tab_muestra, tab_signo, tab_inv = st.tabs(
    ["El día", "Flujo por minuto", "M4: carga contra toques", "La muestra", "M1 y M2: por qué no hay signo",
     "Inventario de datos"])

# ---------------------------------------------------------------- 1. el día
with tab_dia:
    dias = list(inv.index[inv["precio_ok"]])
    if not dias:
        st.info("Ningún día tiene a la vez el ES 1-min y el SPX 5m en caché: no hay precio por minuto que dibujar.")
    else:
        sin_precio = [corto(f) for f in inv.index[~inv["precio_ok"]]]
        dia = st.select_slider("Día", options=dias, value=dias[-1], format_func=corto) if len(dias) > 1 else dias[0]
        if sin_precio:
            st.caption("Días sin precio por minuto, fuera del selector: " + ", ".join(sin_precio) + ".")
        spx, tq, motivo = precio_y_toques(dia)
        if spx is None:
            st.info(f"No se puede dibujar el día. {motivo}")
        else:
            c, motivo_carga = carga(dia)
            lo = np.floor((spx.min() - 30) / 25) * 25
            hi = np.ceil((spx.max() + 30) / 25) * 25
            fig = make_subplots(rows=1, cols=4, shared_yaxes=True, horizontal_spacing=0.015,
                                column_widths=[0.55, 0.16, 0.145, 0.145],
                                subplot_titles=(f"{rotulo('spx')} · SPX por minuto y toques",
                                                f"{rotulo('oi_total')} · OI por zona",
                                                f"{rotulo('gex_bruto')} · gamma bruta",
                                                f"{rotulo('gex_sup')} · GEX neto"))
            for k in np.arange(lo, hi + 1, 25):                       # las zonas: líneas recesivas, las de 100 un poco más
                fig.add_hline(y=k, line=dict(color=GRILLA, width=1.5 if k % 100 == 0 else 0.6), row=1, col=1)
            fig.add_trace(go.Scatter(x=hora(spx.index), y=spx, mode="lines", name="SPX (ES − base móvil)",
                                     line=linea_clase(vista.clase("spx"), TINTA),
                                     hovertemplate="%{x|%H:%M} · SPX %{y:,.1f}<extra></extra>"), row=1, col=1)
            for res in RESULTADOS:
                g = tq[tq["resultado"] == res]
                for r in g.itertuples():                              # la ventana que decide y el margen de cruce
                    fig.add_shape(type="rect", x0=r.t_toque.tz_localize(None), x1=r.t_fin.tz_localize(None),
                                  y0=r.strike - DEF.margen, y1=r.strike + DEF.margen, line_width=0,
                                  fillcolor=COLOR_RESULTADO[res], opacity=0.14, row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=hora(pd.DatetimeIndex(g["t_toque"])) if len(g) else [], y=g["strike"], mode="markers",
                    name=res, marker=dict(symbol=SIMBOLO_RESULTADO[res], size=13, color=COLOR_RESULTADO[res],
                                          line=dict(color=SUPERFICIE if res != VENTANA_CORTA else NEUTRO, width=2)),
                    customdata=np.column_stack([g["lado"], g["dist_previa"], g["peor_exceso"]]) if len(g) else None,
                    hovertemplate=("zona %{y:.0f} · %{x|%H:%M} · <b>" + res + "</b><br>venía de %{customdata[0]}"
                                   "<br>distancia 30 min antes %{customdata[1]:.1f} pts"
                                   "<br>peor exceso %{customdata[2]:.1f} pts<extra></extra>")), row=1, col=1)
            if c is not None:
                z = c["zonas"]
                z = z[(z.index >= lo) & (z.index <= hi)]
                extra = np.column_stack([z["oi_total"], z["pct_carga_oi"], z["clase"], z["pct_puts"]])
                for col, color, nombre in (("oi_c", CALLS, "OI calls"), ("oi_p", PUTS, "OI puts")):
                    fig.add_trace(go.Bar(
                        y=z.index, x=z[col], orientation="h", name=nombre, width=18,
                        marker=dict(color=color, pattern=patron_clase(cg.clase(col)),
                                    line=dict(color=SUPERFICIE, width=2)), customdata=extra,
                        hovertemplate=("zona %{y:.0f} (clase %{customdata[2]}) · " + nombre + " %{x:,.0f}"
                                       "<br>OI total %{customdata[0]:,.0f} · %{customdata[3]:.0f}% puts"
                                       "<br>percentil en su clase %{customdata[1]:.0f}<extra></extra>")), row=1, col=2)
                fig.add_trace(go.Bar(
                    y=z.index, x=z["gex_bruto"] / 1e9, orientation="h", name="gamma bruta (MODELO)", width=18,
                    marker=dict(color=ORDINAL_VIOLETA[-1] if len(ORDINAL_VIOLETA) else NEUTRO,
                                pattern=patron_clase(cg.clase("gex_bruto"))),
                    customdata=z["pct_carga_bruto"], showlegend=False,
                    hovertemplate=("zona %{y:.0f} · gamma bruta %{x:,.2f} $B (MODELO, sin signo)"
                                   "<br>percentil en su clase %{customdata:.0f}<extra></extra>")), row=1, col=3)
                sup = z["gex_sup"] / 1e9
                fig.add_trace(go.Bar(
                    y=z.index, x=sup, orientation="h", name="GEX neto (SUPUESTO)", width=18, showlegend=False,
                    marker=dict(color=np.where(sup >= 0, POSITIVO, NEGATIVO),
                                pattern=patron_clase(cg.clase("gex_sup"))),
                    text=np.where(z["es_wall_sup"], "wall", ""), textposition="outside", cliponaxis=False,
                    hovertemplate="zona %{y:.0f} · GEX neto %{x:+.2f} $B (SUPUESTO)<extra></extra>"), row=1, col=4)
                fig.add_vline(x=0, line=dict(color=TINTA_SUAVE, width=1), row=1, col=4)
            fig.update_xaxes(title_text="hora (Nueva York)", tickformat="%H:%M", row=1, col=1)
            fig.update_xaxes(title_text="contratos", rangemode="tozero", row=1, col=2)
            fig.update_xaxes(title_text="$B (MODELO)", rangemode="tozero", row=1, col=3)
            fig.update_xaxes(title_text="$B (SUPUESTO)", row=1, col=4)
            fig.update_yaxes(title_text="SPX / zona (25 pts)", range=[lo, hi], row=1, col=1)
            base_layout(fig, 720, barmode="stack", title=f"{corto(dia)} · el precio contra las zonas, y la carga que "
                                                         "se conocía antes de abrir")
            st.plotly_chart(fig, width="stretch")
            cuenta = tq["resultado"].value_counts()
            st.caption(f"Toques: {len(tq)} — " + ", ".join(f"{cuenta.get(r, 0)} {r}" for r in RESULTADOS)
                       + f". La banda sombreada es la ventana de {DEF.ventana_min} min y el margen de ±{DEF.margen:g} pts: "
                       "si un cierre de 1 min la pasa hacia el otro lado, el toque cuenta como cruce.")
            if c is None:
                st.info(f"Sin carga para este día: {motivo_carga}. Se dibuja solo el precio.")
            else:
                st.caption(f"OI: foto del {corto(dia)} = OI al cierre del día anterior, publicado a las 06:30. "
                           f"Gamma bruta y GEX neto: foto del {corto(c['foto_previa'])}, sin lo que vence el {corto(dia)}. "
                           "La gamma bruta suma calls y puts (no las resta). El GEX neto y la marca “wall” usan el "
                           "signo SUPUESTO y van en su propio panel: no se combinan con la carga.")
                if c["d1_vieja"]:
                    st.warning(f"La foto anterior ({corto(c['foto_previa'])}) no es la del día hábil previo: falta un "
                               "día en el medio. El OI está bien; la gamma bruta y el GEX neto salen de una foto vieja.")
                with st.expander("Tabla: toques del día con la carga de su zona"):
                    t = cg.unir(tq.assign(t_toque=tq["t_toque"].dt.strftime("%H:%M")).drop(columns="t_fin"), c["zonas"])
                    nombres = {col: f"{col} [{rotulo(col)}]" for col in t.columns if cg.clase(col) in ("modelo", "supuesto")}
                    st.dataframe(t.rename(columns=nombres).round(1), width="stretch", hide_index=True)

# ---------------------------------------------------------------- 2. flujo por minuto
with tab_flujo:
    candidatos = tuple(inv.index[inv["flujo_ok"]])
    con_flujo, sin_flujo = dias_con_flujo(candidatos)
    if not con_flujo:
        st.info("Ningún día tiene en caché el catálogo 0DTE y tcbbo de sus series: no hay flujo que dibujar. "
                "(M2 está cerrada: no se recomienda pagar tcbbo para ampliarlo.)")
    else:
        c1, c2 = st.columns([2, 3])
        dia_f = c1.selectbox("Día con flujo en caché", con_flujo, index=len(con_flujo) - 1, format_func=corto)
        regla = c2.radio("Regla de clasificación", ["estricta (vigente)", "punto medio (histórica)"], horizontal=True,
                         help="Estricta: compra solo si se imprimió en el ask, venta solo en el bid; lo demás es "
                              "indeterminado y no entra en las líneas. Punto medio: firma todo lo que no esté justo "
                              "en el medio; se conserva solo para comparar.")
        es_estricta = regla.startswith("estricta")
        nombre_regla = "estricta" if es_estricta else "punto medio"
        k_flujo = vista.clase_flujo(es_estricta)                      # "medido", o "inferido" con el punto medio
        rot_flujo = ROTULO.get(k_flujo, "INFERIDO (regla del punto medio)")
        r, motivo = flujo(dia_f, es_estricta)
        estricta, _ = flujo(dia_f, True)
        if r is None:
            st.info(f"No se puede dibujar el flujo. {motivo}")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Franja con datos", f"{r['desde']}–{r['hasta']}")
            m2.metric("Series 0DTE en caché", f"{r['series_cubiertas']} de {r['series_0dte']}")
            m3.metric("Strikes con trades", f"{r['strike_min']:,.0f}–{r['strike_max']:,.0f}")
            m4.metric("Indeterminado (regla estricta)", f"{estricta['pct_indet']:.0f}%")
            if not r["sesion_completa"]:
                st.warning(f"Este día solo tiene tcbbo de {r['desde']} a {r['hasta']}: el flujo es de esa franja, "
                           "no del día completo.")
            spx_f, _, motivo_p = precio_y_toques(dia_f)
            f = r["flujo"]
            fg = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.42, 0.58],
                               subplot_titles=(f"{rotulo('spx')} · SPX por minuto",
                                               f"{rot_flujo} · flujo neto acumulado del público (contratos)"))
            if spx_f is not None:
                fg.add_trace(go.Scatter(x=hora(spx_f.index), y=spx_f, mode="lines", name="SPX", showlegend=False,
                                        line=linea_clase(vista.clase("spx"), TINTA),
                                        hovertemplate="SPX %{y:,.1f}<extra></extra>"), row=1, col=1)
            for col, color, nombre in (("acum_C", CALLS, "calls"), ("acum_P", PUTS, "puts")):
                fg.add_trace(go.Scatter(x=hora(f.index), y=f[col], mode="lines", name=nombre,
                                        line=(linea_clase(vista.clase(col), color) if es_estricta
                                              else dict(color=color, width=2, dash="dashdot")),
                                        hovertemplate=(nombre + " %{y:+,.0f}" + ("" if es_estricta else " (INFERIDO)")
                                                       + "<extra></extra>")), row=2, col=1)
            fg.add_hline(y=0, line=dict(color=TINTA_SUAVE, width=1), row=2, col=1)
            fg.update_xaxes(tickformat="%H:%M", title_text="hora (Nueva York)", row=2, col=1)
            fg.update_yaxes(title_text="SPX", row=1, col=1)
            fg.update_yaxes(title_text="contratos netos comprados", row=2, col=1)
            base_layout(fg, 640, hovermode="x unified",
                        title=f"{corto(dia_f)} · flujo de las 0DTE en caché, regla {nombre_regla}"
                              + ("" if es_estricta else " (INFERIDO)"))
            st.plotly_chart(fg, width="stretch")
            if not es_estricta:
                st.warning("Con la regla del punto medio el flujo NO es medido: firma todo lo que no esté justo en "
                           "el medio, incluido el interior del spread (INFERIDO por cercanía). Va con línea de raya "
                           "y punto, y se conserva solo para comparar con la regla estricta.")
            if spx_f is None:
                st.caption(f"Sin precio por minuto para este día: {motivo_p}.")
            v = estricta["volumen"]
            fv = go.Figure()
            for clave, color, nombre in (("compra", COMPRA, "compra (en el ask)"), ("venta", VENTA, "venta (en el bid)"),
                                         ("indet", NEUTRO, "indeterminado")):
                fv.add_trace(go.Bar(y=["volumen"], x=[v[clave]], orientation="h", name=nombre,
                                    marker=dict(color=color, line=dict(color=SUPERFICIE, width=2)),
                                    text=[f"{nombre}<br>{v[clave]:,.0f}"], textposition="inside", insidetextanchor="middle",
                                    hovertemplate=nombre + " %{x:,.0f} contratos<extra></extra>"))
            base_layout(fv, 190, barmode="stack", showlegend=False,
                        title=f"{rotulo('indet')} · volumen del día según la regla estricta (contratos)")
            fv.update_yaxes(visible=False)
            fv.update_layout(margin=dict(l=20, b=20))
            st.plotly_chart(fv, width="stretch")
            st.caption("Las líneas son el neto del PÚBLICO (+ = compró agresivamente). Con la regla estricta, lo "
                       "indeterminado no entra en las líneas y nunca se reparte. Leer de aquí el signo del dealer "
                       "(“el dealer es la contraparte”) es un SUPUESTO, y M1/M2 mostraron que el neto firmado es "
                       "~4% de lo indeterminado: estas curvas describen el flujo que se pudo firmar, no la posición "
                       "del dealer. El tcbbo en caché cubre solo los strikes que se bajaron.")
        if sin_flujo:
            with st.expander(f"Días con catálogo y tcbbo pero sin flujo 0DTE dibujable ({len(sin_flujo)})"):
                for f_, mot in sin_flujo.items():
                    st.write(f"- {mot}")

# ---------------------------------------------------------------- 3. M4
with tab_m4:
    todo = acumulador_carga()
    if todo is None or todo.empty:
        st.info("No existe data/validacion/odte_carga.csv. Se genera a $0 con: "
                "`python scripts/odte/validar_carga.py INICIO FIN --sin 2026-10-20`.")
    else:
        st.warning(f"**M4 está cerrada: SIN EVIDENCIA.** Con {todo['fecha'].nunique()} días, la carga de una zona "
                   "no predice si el nivel aguanta el toque. Los gráficos muestran por qué; no son una señal.")
        c1, c2 = st.columns(2)
        definicion = c1.selectbox("Definición del toque", sorted(todo["definicion"].unique()))
        refs = [r for r in cg.REFERENCIAS if r in set(todo.loc[todo["definicion"] == definicion, "referencia"])]
        ref = c2.radio("Carga relativa medida contra", refs, horizontal=True,
                       format_func=lambda x: {"radio250": "zonas a ±250 pts del cierre previo (diseño fijo)",
                                              "tocadas": "solo las zonas tocadas ese día (variante)"}[x])
        t0 = cg.contables(todo[(todo["definicion"] == definicion) & (todo["referencia"] == ref)])
        sin_comp = t0["pct_carga_oi"].isna() | t0["pct_carga_bruto"].isna()
        t = t0[~sin_comp]
        if sin_comp.any():
            st.caption(f"{int(sin_comp.sum())} toques sin comparación (única zona de su clase tocada ese día) quedan "
                       f"fuera: se analizan {len(t)} toques en {t['fecha'].nunique()} días.")
        if t.empty:
            st.info("No quedan toques para analizar con esta referencia.")
        else:
            base = cg.tasa(t)
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Toques · días · zonas", f"{len(t)} · {t['fecha'].nunique()} · {t['strike'].nunique()}")
            a2.metric("Aguante base", f"{base:.0f}%")
            a3.metric(f"Alta − baja por toque (OI, {rotulo('pct_carga_oi')})", f"{cg.diferencia(t, 'pct_carga_oi'):+.1f} pts")
            a4.metric("Alta − baja, un voto por zona", f"{cg.voto_por_zona(t, 'pct_carga_oi')['diferencia']:+.1f} pts")

            izq, der = st.columns(2)
            for lugar, col, pasos in ((izq, "pct_carga_oi", ORDINAL_AZUL[0::2]), (der, "pct_carga_bruto", ORDINAL_VIOLETA)):
                k = cg.clase(col)
                celdas = cg.celdas(t, col).reset_index()
                fc = go.Figure()
                for mitad, color in zip(("baja", "alta"), pasos):
                    g = celdas[celdas["carga"] == mitad].set_index("clase").reindex(list(cg.CLASES))
                    con = g["dias"].fillna(0) >= cg.MIN_DIAS
                    fc.add_trace(go.Bar(
                        x=[f"múltiplos de {c_}" for c_ in g.index], y=g["pct_aguanto"], name=f"carga {mitad}",
                        marker=dict(color=color, pattern=patron_clase(k), opacity=np.where(con, 1.0, 0.35),
                                    line=dict(color=SUPERFICIE, width=2)),
                        text=[("" if pd.isna(n) else f"{p:.0f}%<br>{int(n)} toques<br>{int(d)} días"
                               + ("" if ok else "<br><b>sin evidencia</b>"))
                              for p, n, d, ok in zip(g["pct_aguanto"], g["toques"], g["dias"], con)],
                        textposition="outside", cliponaxis=False,
                        hovertemplate="%{x} · carga " + mitad + "<br>aguantó %{y:.0f}%<extra></extra>"))
                fc.add_hline(y=base, line=dict(color=TINTA_SUAVE, width=1.5, dash="dot"),
                             annotation_text=f"aguante base {base:.0f}%", annotation_position="top right")
                base_layout(fc, 470, barmode="group", bargap=0.25, bargroupgap=0.08,
                            title=f"{ROTULO[k]} · aguante por clase y mitad de carga "
                                  f"({'OI' if k == 'medido' else 'gamma bruta'})")
                fc.update_yaxes(title_text="% de toques que aguantaron", range=[0, 125], tickvals=[0, 25, 50, 75, 100])
                lugar.plotly_chart(fc, width="stretch")
                f1 = cg.dejar_una_fuera(t, col)
                da = f1[f1["cambia_signo"] == True]                     # noqa: E712
                lugar.caption(f"{ROTULO[k]} · alta − baja: {cg.diferencia(t, col):+.1f} pts por toque. Quitando una zona va de "
                              f"{f1['diferencia_sin'].min():+.1f} a {f1['diferencia_sin'].max():+.1f}"
                              + ("; ninguna zona sola da vuelta el signo." if da.empty else
                                 "; **depende de la zona " + ", ".join(str(int(z_)) for z_ in da["zona"]) + "**."))
            st.caption(f"Barras atenuadas = celdas con menos de {cg.MIN_DIAS} días: NO son evidencia, se muestran "
                       "para que se vea de qué tamaño es la muestra. “Alta” = en la mitad de arriba de su clase.")

            ac = cg.aciertos(t).sort_values()
            fp = go.Figure()
            for nombre_p, valor in ac.items():
                k = CLASE_PREDICTOR.get(nombre_p)
                color = {None: NEUTRO, "medido": ORDINAL_AZUL[1], "modelo": ORDINAL_VIOLETA[-1], "supuesto": NEUTRO}[k]
                etiqueta = NOMBRE_PREDICTOR[nombre_p] + (f" ({ROTULO[k]})" if k else " (ingenuo)")
                fp.add_trace(go.Bar(y=[etiqueta], x=[valor], orientation="h", showlegend=False, width=0.6,
                                    marker=dict(color=color, pattern=patron_clase(k) if k else None),
                                    text=[f"{valor:.0f}%"], textposition="outside", cliponaxis=False,
                                    hovertemplate=etiqueta + " · acierta %{x:.1f}%<extra></extra>"))
            fp.add_vline(x=float(ac["base"]), line=dict(color=TINTA, width=1.5, dash="dot"),
                         annotation_text="frecuencia base: hay que superarla", annotation_position="top")
            base_layout(fp, 380, title="Acierto de cada predictor sobre los MISMOS toques · la clase va en cada "
                                       "barra (MEDIDO, MODELO, SUPUESTO); no se suman")
            fp.update_xaxes(title_text="% de toques acertados", range=[0, 105])
            fp.update_layout(margin=dict(l=270))                       # rótulos largos en el eje de categorías
            st.plotly_chart(fp, width="stretch")
            st.caption("La carga tiene que ganarle a la frecuencia base (predecir siempre el resultado más común) para "
                       "decir algo. Gris liso = ingenuos; azul = MEDIDO; violeta punteado = MODELO; rayado = SUPUESTO "
                       "(el wall con signo, un predictor aparte que nunca se suma a la carga).")

            fd = go.Figure()
            for res in (AGUANTO, CRUZO):
                g = t[t["resultado"] == res]
                fd.add_trace(go.Scatter(
                    x=g["pct_carga_oi"], y=g["peor_exceso"], mode="markers", name=res,
                    marker=dict(symbol=SIMBOLO_RESULTADO[res], size=10, color=COLOR_RESULTADO[res],
                                line=dict(color=SUPERFICIE, width=1.5)),
                    customdata=np.column_stack([g["fecha"], g["strike"], g["clase"], g["oi_total"]]),
                    hovertemplate=("%{customdata[0]} · zona %{customdata[1]} (clase %{customdata[2]}) · <b>" + res
                                   + "</b><br>percentil de carga %{x:.0f} · OI %{customdata[3]:,.0f}"
                                     "<br>peor exceso %{y:.1f} pts<extra></extra>")))
            fd.add_hline(y=DEF.margen, line=dict(color=TINTA_SUAVE, width=1.5, dash="dot"),
                         annotation_text=f"margen de cruce ({DEF.margen:g} pts)", annotation_position="top left")
            base_layout(fd, 430, title=f"{rotulo('peor_exceso')} · cada toque: carga relativa de la zona contra cuánto se pasó el precio")
            fd.update_xaxes(title_text="percentil de carga por OI dentro de su clase", range=[-3, 103])
            fd.update_yaxes(title_text="peor exceso más allá del nivel (pts)")
            st.plotly_chart(fd, width="stretch")
            st.caption("Si la carga frenara al precio, los puntos de la derecha quedarían abajo y casi todos serían "
                       "“aguantó”.")
            with st.expander("Tabla: celdas y predictores"):
                st.dataframe(cg.celdas(t, "pct_carga_oi").round(1), width="stretch")
                st.dataframe(ac.rename(lambda n: NOMBRE_PREDICTOR[n] + (f" [{ROTULO[CLASE_PREDICTOR[n]]}]"
                                                                    if n in CLASE_PREDICTOR else " [ingenuo]"))
                             .round(1).rename("% de acierto").to_frame(), width="stretch")

# ---------------------------------------------------------------- 4. la muestra
with tab_muestra:
    todo = acumulador_carga()
    if todo is None or todo.empty:
        st.info("No existe data/validacion/odte_carga.csv: no hay muestra de toques que dibujar.")
    else:
        definicion_m = sorted(todo["definicion"].unique())[0]
        tm = todo[(todo["definicion"] == definicion_m) & (todo["referencia"] == cg.REFERENCIA_FIJA)]
        mapa = vista.mapa_toques(tm)
        # Todos los días hábiles del inventario: un día sin datos queda como columna vacía y rotulada, no desaparece
        dias_m = [f for f in inv.index if inv.index[0] <= f <= inv.index[-1] and f >= tm["fecha"].min()]
        mapa = mapa.reindex(columns=dias_m)
        codigo = {AGUANTO: 0, CRUZO: 1, VENTANA_CORTA: 2}
        signo = {AGUANTO: "●", CRUZO: "✕", VENTANA_CORTA: "◇"}
        zc = mapa.replace(codigo).astype(float).values
        texto = mapa.replace(signo).fillna("").values
        oi = tm.pivot(index="strike", columns="fecha", values="oi_total").reindex(index=mapa.index, columns=dias_m).values
        pc = tm.pivot(index="strike", columns="fecha", values="pct_carga_oi").reindex(index=mapa.index, columns=dias_m).values
        etiquetas_x = [corto(f) for f in dias_m]
        escala = [[0, COLOR_RESULTADO[AGUANTO]], [0.33, COLOR_RESULTADO[AGUANTO]], [0.34, COLOR_RESULTADO[CRUZO]],
                  [0.66, COLOR_RESULTADO[CRUZO]], [0.67, NEUTRO], [1, NEUTRO]]
        fm = make_subplots(rows=1, cols=2, shared_yaxes=True, column_widths=[0.82, 0.18], horizontal_spacing=0.02,
                           subplot_titles=(f"{rotulo('resultado')} · resultado de cada toque, por día y zona",
                                           "toques por zona"))
        fm.add_trace(go.Heatmap(
            x=etiquetas_x, y=mapa.index, z=zc, zmin=0, zmax=2, colorscale=escala, showscale=False, xgap=2, ygap=2,
            text=texto, texttemplate="%{text}", textfont=dict(color="#ffffff", size=13),
            customdata=np.dstack([mapa.fillna("").values, oi, pc]), hoverongaps=False,
            hovertemplate=("%{x} · zona %{y:.0f} · <b>%{customdata[0]}</b><br>OI %{customdata[1]:,.0f} · percentil "
                           "en su clase %{customdata[2]:.0f}<extra></extra>")), row=1, col=1)
        for res in RESULTADOS:                                        # leyenda (el mapa no tiene barra de color)
            fm.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=f"{signo[res]} {res}",
                                    marker=dict(symbol="square", size=12, color=COLOR_RESULTADO[res])), row=1, col=1)
        por_zona = tm.groupby(["strike", "resultado"]).size().unstack(fill_value=0).reindex(index=mapa.index, fill_value=0)
        for res in RESULTADOS:
            if res in por_zona.columns:
                fm.add_trace(go.Bar(y=por_zona.index, x=por_zona[res], orientation="h", width=18, showlegend=False,
                                    marker=dict(color=COLOR_RESULTADO[res], line=dict(color=SUPERFICIE, width=2)),
                                    hovertemplate="zona %{y:.0f} · " + res + " %{x}<extra></extra>"), row=1, col=2)
        vacios_m = [corto(f) for f in dias_m if mapa[f].isna().all()]
        for f in dias_m:
            if inv.loc[f, "falta"].startswith("todo"):
                fm.add_annotation(x=corto(f), y=mapa.index.max(), text="sin<br>datos", showarrow=False, yshift=28,
                                  font=dict(size=10, color=TINTA_SUAVE), row=1, col=1)
        fm.update_xaxes(type="category", tickangle=-60, row=1, col=1)
        fm.update_xaxes(title_text="toques", row=1, col=2)
        fm.update_yaxes(title_text="zona (25 pts)", dtick=25, row=1, col=1)
        base_layout(fm, 720, barmode="stack",
                    title=f"La muestra de M4: {len(tm)} toques en {tm['fecha'].nunique()} días ({definicion_m})")
        st.plotly_chart(fm, width="stretch")
        st.caption("● aguantó · ✕ cruzó · ◇ ventana corta (el toque fue a menos de 30 min del cierre; no cuenta). "
                   "Cada zona cuenta su primer toque del día. Las mismas zonas se repiten día tras día: los toques no "
                   "son independientes, por eso el tamaño honesto de la muestra son los días."
                   + (f" Columnas vacías (sin toques o sin datos): {', '.join(vacios_m)}." if vacios_m else ""))
        with st.expander("Tabla: toques por zona"):
            st.dataframe(por_zona.sort_index(ascending=False), width="stretch")

# ---------------------------------------------------------------- 5. M1 y M2
with tab_signo:
    m2 = acumulador_m2()
    if m2 is None or m2.empty:
        st.info("No existe data/validacion/odte_toques.csv (la muestra de M2).")
    else:
        st.warning("**M1 y M2 están cerradas: el signo del dealer no es identificable.** Antes de cada toque, lo "
                   "que la regla estricta puede firmar es una fracción mínima de lo que no puede.")
        definicion_2 = st.selectbox("Definición", sorted(m2["definicion"].unique()), key="def_m2")
        t2 = m2[m2["definicion"] == definicion_2].sort_values(["fecha", "strike"]).reset_index(drop=True)
        t2["toque"] = [f"{corto(f)} · {int(k)}" for f, k in zip(t2["fecha"], t2["strike"])]
        razon = vista.razon_neto_indet(t2)
        partes = vista.partes_indet(t2)
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Toques · días", f"{len(t2)} · {t2['fecha'].nunique()}")
        b2.metric("Toques con signo medido", int(t2["dealer_medido"].isin(["+", "-"]).sum()))
        b3.metric("|neto| / indeterminado, mediana", f"{razon.median():.3f}")
        b4.metric("Indeterminado en el punto medio, mediana", f"{partes['indet_medio'].median():.0f}%")
        fs = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.03, column_widths=[0.4, 0.32, 0.28],
                           subplot_titles=(f"{rotulo('indet')} · volumen antes del toque (contratos)",
                                           f"{rotulo('indet_medio')} · dónde se imprimió lo indeterminado (%)",
                                           f"{rotulo('razon_neto_indet')} · |neto| / indeterminado"))
        for clave, color, nombre in (("compra", COMPRA, "compra (en el ask)"), ("venta", VENTA, "venta (en el bid)"),
                                     ("indet", NEUTRO, "indeterminado")):
            fs.add_trace(go.Bar(y=t2["toque"], x=t2[clave], orientation="h", name=nombre, legendgroup="vol",
                                marker=dict(color=color, line=dict(color=SUPERFICIE, width=2)),
                                hovertemplate="%{y} · " + nombre + " %{x:,.0f}<extra></extra>"), row=1, col=1)
        partes["indet_fuera"] = partes["indet_fuera"] + partes["indet_sin_cotizacion"].fillna(0)
        for clave, color, nombre in (("indet_medio", ORDINAL_AZUL[0], "en el punto medio exacto"),
                                     ("indet_interior", ORDINAL_AZUL[1], "interior del spread"),
                                     ("indet_fuera", ORDINAL_AZUL[2], "fuera del spread (paquetes)")):
            fs.add_trace(go.Bar(y=t2["toque"], x=partes[clave], orientation="h", name=nombre, legendgroup="ubic",
                                marker=dict(color=color, line=dict(color=SUPERFICIE, width=2)),
                                hovertemplate="%{y} · " + nombre + " %{x:.0f}%<extra></extra>"), row=1, col=2)
        fs.add_trace(go.Scatter(y=t2["toque"], x=razon, mode="markers", showlegend=False,
                                marker=dict(size=10, color=TINTA, line=dict(color=SUPERFICIE, width=1.5)),
                                customdata=np.column_stack([t2["neto"], t2["indet"], t2["dealer_medido"]]),
                                hovertemplate=("%{y} · razón %{x:.3f}<br>neto %{customdata[0]:+,.0f} · indeterminado "
                                               "%{customdata[1]:,.0f}<br>veredicto: %{customdata[2]}<extra></extra>")),
                     row=1, col=3)
        fs.add_vline(x=1, line=dict(color=TINTA, width=1.5, dash="dot"), row=1, col=3,
                     annotation_text="mínimo para un signo", annotation_position="top left")
        fs.update_xaxes(title_text="contratos", row=1, col=1)
        fs.update_xaxes(title_text="% de lo indeterminado", range=[0, 100], row=1, col=2)
        fs.update_xaxes(title_text="razón (sin unidad)", range=[0, max(1.15, 1.1 * float(razon.max()))], row=1, col=3)
        fs.update_yaxes(autorange="reversed", row=1, col=1)
        base_layout(fs, max(420, 34 * len(t2) + 160), barmode="stack",
                    title="Flujo de cada zona ANTES de su toque (regla estricta, calls + puts)")
        st.plotly_chart(fs, width="stretch")
        st.caption("Para dar un signo, el neto firmado tiene que superar a todo lo indeterminado (peor caso): la razón "
                   "tiene que pasar de 1 (máximo de esta muestra: " + f"{razon.max():.2f}" + "). Lo indeterminado impreso en el "
                   "punto medio exacto (mediana " + f"{partes['indet_medio'].median():.0f}%"
                   + ") no lo puede firmar ninguna regla de bid/ask. Los azules van de claro a oscuro "
                   "según qué tan lejos del punto medio se imprimió el trade.")
        with st.expander("Tabla"):
            st.dataframe(t2[["fecha", "strike", "t_toque", "resultado", "compra", "venta", "indet", "neto",
                             "pct_indet", "dealer_medido"]].assign(razon=razon.round(3)),
                         width="stretch", hide_index=True)

# ---------------------------------------------------------------- 6. inventario
with tab_inv:
    st.caption("Qué hay en caché para cada día hábil y qué se puede dibujar. Un día al que le falta algo no rompe "
               "el panel: queda fuera del selector correspondiente. Los días hábiles sin nada son feriados o días "
               "sin datos en Databento (aproximado: el panel no conoce el calendario de feriados).")
    marca = lambda s: s.map({True: "sí", False: "—"})
    ver = pd.DataFrame({"día": [corto(f) for f in inv.index], "precio por minuto": marca(inv["precio_ok"]).values,
                        "carga": marca(inv["carga_ok"]).values, "foto anterior": [corto(f) if f else "—" for f in inv["foto_previa"]],
                        "catálogo + tcbbo": marca(inv["flujo_ok"]).values, "falta": inv["falta"].replace("", "—").values})
    st.dataframe(ver, width="stretch", hide_index=True, height=38 * (len(ver) + 1))
