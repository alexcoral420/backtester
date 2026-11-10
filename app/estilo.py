"""
estilo.py — Paleta y marcas compartidas por los paneles (app/panel.py y app/panel_odte.py).

Paleta validada (dataviz, references/palette.md; validate_palette.js pasa en cada modo con su superficie).
Modo oscuro = sus propios pasos, no un "invertir".

Convención medido / modelo / supuesto (la CLASE la decide el contrato de cada módulo: walls.clase o
carga.clase; aquí solo está cómo se dibuja cada clase):
  medido    sólido, línea continua, escalas de un solo tono
  modelo    punteado, línea de puntos, escala violeta, "MODELO" en el texto
  supuesto  rayado, línea discontinua, escala divergente, "SUPUESTO" en el texto
"""
import streamlit as st

OSCURO = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
if OSCURO:
    CALLS, PUTS = "#3987e5", "#d95926"
    COLOR_COMPONENTE = {"pos": "#199e70", "mer": "#c98500", "ven": "#d55181"}
    TINTA, TINTA_SUAVE, SUPERFICIE, MEDIO = "#f0efec", "#c3c2b7", "#1a1a19", "#383835"
    GRILLA = "#2c2c2a"
else:
    CALLS, PUTS = "#2a78d6", "#eb6834"
    COLOR_COMPONENTE = {"pos": "#1baf7a", "mer": "#eda100", "ven": "#e87ba4"}
    TINTA, TINTA_SUAVE, SUPERFICIE, MEDIO = "#0b0b0b", "#52514e", "#fcfcfb", "#e1e0d9"
    GRILLA = "#e1e0d9"
# Rampa secuencial azul completa (palette.md, pasos 100->700): 9 pasos en vez de 5 para distinguir cargas.
# Claro: el paso claro = poco y se funde con la superficie. Oscuro: invertida (lo poco se funde con lo oscuro).
_AZUL_9 = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#104281", "#0d366b"]
SEQ_AZUL = _AZUL_9[::-1] if OSCURO else _AZUL_9
SEQ_NARANJA = ["#fde4d6", "#f6b08f", "#eb6834", "#b84a1f", "#7a2e10"]
if OSCURO:
    SEQ_NARANJA = SEQ_NARANJA[::-1]
DIVERGENTE = [[0.0, "#b3261e"], [0.25, "#e66767"], [0.5, MEDIO], [0.75, "#5598e7"], [1.0, "#104281"]]
POSITIVO, NEGATIVO = "#3987e5", "#e66767"          # polos de DIVERGENTE, para barras supuestas por signo
NEUTRO = "#898781"
# Modelo: violeta (ColorBrewer "Purples", un solo tono), distinto de lo medido aunque no haya patrón en un heatmap.
SEQ_VIOLETA = ["#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#54278f", "#3f007d"]
if OSCURO:
    SEQ_VIOLETA = SEQ_VIOLETA[::-1]

# --- Panel 0DTE (validado 2026-11-09 con validate_palette.js en claro y oscuro) -------------------------------
# Resultado del toque: verde / magenta (slots 6 y 5) pasan todas las parejas en los dos modos (aqua/magenta
# fallaba en oscuro: CVD ΔE 1,6). Además cada resultado lleva su forma de marcador: nunca solo color.
if OSCURO:
    AGUANTO, CRUZO = "#008300", "#d55181"
    COMPRA, VENTA = "#199e70", "#c98500"                      # slots 3 y 4 (adyacentes: CVD ΔE 8,4)
    ORDINAL_AZUL = ["#184f95", "#3987e5", "#9ec5f4"]          # poco -> mucho (el paso tenue se funde con lo oscuro)
    ORDINAL_VIOLETA = ["#6a51a3", "#bcbddc"]
else:
    AGUANTO, CRUZO = "#008300", "#e87ba4"
    COMPRA, VENTA = "#1baf7a", "#eda100"
    ORDINAL_AZUL = ["#86b6ef", "#2a78d6", "#104281"]
    ORDINAL_VIOLETA = ["#9e9ac8", "#54278f"]
SIMBOLO_RESULTADO = {"aguantó": "circle", "cruzó": "x", "ventana corta": "diamond-open"}
COLOR_RESULTADO = {"aguantó": AGUANTO, "cruzó": CRUZO, "ventana corta": NEUTRO}

# fillmode="overlay": el color de la barra es el FONDO y el patrón va encima. Con el valor por defecto
# ("replace") una barra de un solo color con fgcolor blanco queda transparente (solo se ve si el color es una lista).
_PATRON = {"supuesto": dict(shape="/", fgcolor="rgba(255,255,255,0.55)", solidity=0.25, fillmode="overlay"),
           "modelo": dict(shape=".", fgcolor="rgba(255,255,255,0.6)", solidity=0.3, fillmode="overlay"),
           "medido": None}
_TRAZO = {"supuesto": "dash", "modelo": "dot", "medido": "solid"}
ROTULO = {"supuesto": "SUPUESTO", "modelo": "MODELO", "medido": "MEDIDO"}


def patron_clase(k):
    """Segunda codificación además del texto: rayado = supuesto, punteado = modelo, sólido = medido."""
    return _PATRON[k]


def linea_clase(k, color, ancho=2):
    return dict(color=color, width=ancho, dash=_TRAZO[k])
