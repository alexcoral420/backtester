"""
forward.py — Forward implícito por vencimiento, medido del mercado con la paridad call-put.

Paridad (opciones europeas, como SPX):   C - P = e^(-rT)·(F - K)   =>   F = K + e^(rT)·(C - P)
De F sale el dividendo implícito:         q = r - ln(F / S) / T

Reglas (para no contaminar el forward con el mismo ruido que queremos arreglar):
  - Solo strikes donde call Y put tienen punto medio válido.
  - Solo los n strikes más cercanos al FORWARD (ATM-forward, donde las dos patas son líquidas).
    Dos pasadas: primero cerca de S (F aproximado), luego recentrado cerca de ese F.
    En plazos largos F está cientos de puntos sobre S: centrar en S usaría calls muy ITM.
  - Mediana entre esos strikes, y se reporta la DISPERSIÓN (máx - mín del F por strike):
    si es grande, el bid/ask de cierre no es una foto coherente y hay que saberlo.
  - Un forward por vencimiento. Los vencimientos sin suficientes strikes heredan el q del
    vencimiento medido más cercano en plazo, y quedan marcados origen = "heredado".
"""
import numpy as np
import pandas as pd

MIN_STRIKES = 3


def forward_por_vencimiento(tabla, S, r, n_strikes=5):
    """
    tabla: la de precio_justo.tabla_cierre (columnas venc, T, tipo, strike, mid).
    Devuelve un DataFrame indexado por venc con:
      T, n_strikes, forward, dispersion (pts), q, origen ("medido" / "heredado")
    """
    filas = []
    for venc, g in tabla[tabla["T"] > 0].groupby("venc"):
        T = g["T"].iloc[0]
        calls = g[g["tipo"] == "C"].set_index("strike")["mid"]
        puts = g[g["tipo"] == "P"].set_index("strike")["mid"]
        pares = pd.concat({"C": calls, "P": puts}, axis=1).dropna()
        f_strike = np.array([])
        centro = S
        for _ in range(2):                                   # pasada 1: cerca de S; pasada 2: cerca de F
            if not len(pares):
                break
            cerca = (pares.index.to_series() - centro).abs().nsmallest(n_strikes).index
            p = pares.loc[cerca]
            f_strike = p.index.values + np.exp(r * T) * (p["C"].values - p["P"].values)
            centro = float(np.median(f_strike))
        if len(f_strike) >= MIN_STRIKES:
            F = float(np.median(f_strike))
            filas.append(dict(venc=venc, T=T, n_strikes=len(f_strike), forward=F,
                              dispersion=float(f_strike.max() - f_strike.min()),
                              q=r - np.log(F / S) / T, origen="medido"))
        else:
            filas.append(dict(venc=venc, T=T, n_strikes=len(f_strike), forward=np.nan,
                              dispersion=np.nan, q=np.nan, origen="heredado"))

    fw = pd.DataFrame(filas).set_index("venc").sort_values("T")
    medidos = fw[fw["origen"] == "medido"]
    if medidos.empty:
        raise ValueError("Ningún vencimiento tiene strikes suficientes para medir el forward.")
    for venc in fw.index[fw["origen"] == "heredado"]:
        cercano = (medidos["T"] - fw.at[venc, "T"]).abs().idxmin()
        fw.at[venc, "q"] = medidos.at[cercano, "q"]
        fw.at[venc, "forward"] = S * np.exp((r - fw.at[venc, "q"]) * fw.at[venc, "T"])
    return fw


def q_por_opcion(tabla, fw):
    """Serie alineada con tabla: el q de cada opción según su vencimiento."""
    return tabla["venc"].map(fw["q"])