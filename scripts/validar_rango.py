"""
Uso:  python scripts/validar_rango.py 2026-09-24 2026-11-06     (suma esos días al acumulador y analiza todo)
      python scripts/validar_rango.py                           (solo analiza el acumulador)

¿El movimiento que el MERCADO espera (straddle ATM del primer vencimiento SPXW, src/rango_implicito.py)
anticipa el rango del día siguiente mejor que el predictor ingenuo (el rango de hoy)?

  MEDIDO    straddle, ancho, impl_pct (straddle / S), rangos y movimientos del SPX
  SUPUESTO  gex_sup_B (GEX total de la foto procesada, signo de la hipótesis nula): solo va al lado,
            para ver los dos predictores sobre los mismos días. NaN si el día no tiene foto procesada.

$0, SOLO CACHÉ: un día sin la cadena SPXW en data/raw se salta y se lista; nunca descarga ni cotiza.
El SPX diario sale de yfinance (gratis, sin caché): un día cuya sesión siguiente no terminó se salta. Regla: foto del cierre de d contra el día del vencimiento del
straddle; si ese vencimiento no es el día de mercado siguiente, el día se lista y no entra.

Acumulador: data/validacion/rango_implicito.csv (propio; no se mezcla con los CSV de GEX ni de 0DTE).
"""
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO                                   # noqa: E402
from src import rango_implicito as ri                                  # noqa: E402
from src.datos import ruta_cadena                                      # noqa: E402
from src.precio_justo import tabla_cierre                              # noqa: E402

RUTA = "data/validacion/rango_implicito.csv"
PROCESADO = "data/procesado/cadena_SPX+SPXW_horas_{}.parquet"
pd.set_option("display.width", 250)

if len(sys.argv) not in (1, 3):
    raise SystemExit("Uso: python scripts/validar_rango.py [INICIO FIN]   (desde la raíz del proyecto)")

if len(sys.argv) == 3:
    inicio, fin = sys.argv[1], sys.argv[2]
    hist = yf.Ticker("^GSPC").history(start=(pd.to_datetime(inicio) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                                      end=(pd.to_datetime(fin) + pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
    hist.index = hist.index.tz_localize(None).normalize()
    pos = {d: i for i, d in enumerate(hist.index)}
    ahora = pd.Timestamp.now(tz="America/New_York")

    def terminada(d):
        """La sesión de d ya cerró (con margen: 16:30 NY). yfinance entrega la barra del día en curso."""
        return d.date() < ahora.date() or (d.date() == ahora.date() and ahora.hour * 60 + ahora.minute >= 16 * 60 + 30)
    filas, saltados = [], []
    for dia in [d for d in hist.index if pd.to_datetime(inicio) <= d <= pd.to_datetime(fin)]:
        fecha, i = dia.strftime("%Y-%m-%d"), pos[dia]
        if not all(os.path.exists(ruta_cadena(ri.RAIZ, s, fecha)) for s in ("ohlcv-1d", "statistics")):
            saltados.append(f"{fecha}: sin cadena {ri.RAIZ} en caché")
            continue
        if i == 0 or i + 1 >= len(hist.index):
            saltados.append(f"{fecha}: sin día previo o siguiente en yfinance")
            continue
        S, sig, prev = float(hist.loc[dia, "Close"]), hist.index[i + 1], hist.index[i - 1]
        if not terminada(sig):
            saltados.append(f"{fecha}: la sesión siguiente ({sig:%Y-%m-%d}) no terminó; yfinance daría una barra "
                            f"a medias como objetivo")
            continue
        try:
            m = ri.straddle_atm(tabla_cierre(fecha, (ri.RAIZ,), "horas"), S, TASA_LIBRE_RIESGO)
        except ValueError as e:
            saltados.append(f"{fecha}: {e}")
            continue
        if m["venc"].normalize() != sig:
            saltados.append(f"{fecha}: el primer vencimiento ({m['venc']:%Y-%m-%d}) no es el día de mercado "
                            f"siguiente ({sig:%Y-%m-%d})")
            continue
        gex = float("nan")
        if os.path.exists(PROCESADO.format(fecha)):
            gex = pd.read_parquet(PROCESADO.format(fecha), columns=["gex_contrib"])["gex_contrib"].sum() / 1e9
        h = hist.loc[sig]
        filas.append(dict(
            fecha=fecha, sig=sig.strftime("%Y-%m-%d"), S=S, venc=m["venc"].strftime("%Y-%m-%d"),
            horas=m["T"] * 365 * 24, forward=m["forward"], dispersion=m["dispersion"], K=m["K"],
            dist_FK=m["dist_FK"], call=m["call"], put=m["put"], straddle=m["straddle"], ancho=m["ancho"],
            impl_pct=m["straddle"] / S * 100,
            rango_hoy_pct=(hist.loc[dia, "High"] - hist.loc[dia, "Low"]) / S * 100,
            mov_hoy_pct=abs(S - hist.loc[prev, "Close"]) / S * 100,
            rango_sig_pct=(h["High"] - h["Low"]) / S * 100, mov_sig_pct=abs(h["Close"] - S) / S * 100,
            pago_sig_pct=abs(h["Close"] - m["K"]) / S * 100,          # lo que el straddle paga: |cierre − K|
            gex_sup_B=gex))
    for s in saltados:
        print(f"[saltado] {s}", file=sys.stderr)
    if filas:
        nuevo = pd.DataFrame(filas).set_index("fecha")
        os.makedirs(os.path.dirname(RUTA), exist_ok=True)
        acum = pd.read_csv(RUTA, index_col="fecha") if os.path.exists(RUTA) else pd.DataFrame()
        acum = pd.concat([acum[~acum.index.isin(nuevo.index)], nuevo]).sort_index()
        acum.round(6).to_csv(RUTA, index_label="fecha")
        print(f"[acumulado] {len(nuevo)} días guardados en {RUTA} (total {len(acum)})", file=sys.stderr)

if not os.path.exists(RUTA):
    raise SystemExit(f"No existe {RUTA}: corre primero con un rango de fechas.")
t = pd.read_csv(RUTA).sort_values("fecha").reset_index(drop=True)

print(f"=== Rango implícito (straddle ATM {ri.RAIZ}) | {len(t)} días | {t['fecha'].min()} a {t['fecha'].max()} ===")
print("\n--- Por día: MEDIDO (pts y % del spot); gex_sup_B = SUPUESTO, solo de referencia ---")
print(t[["fecha", "sig", "S", "K", "straddle", "ancho", "dispersion", "impl_pct", "rango_hoy_pct",
         "rango_sig_pct", "mov_sig_pct", "pago_sig_pct", "gex_sup_B"]].round(2).to_string(index=False))

c = ri.calibracion(t)
print(f"\n--- Calibración (sin ajustar nada): |cierre siguiente − strike| / straddle, {c['n']} días ---")
print(f"  media {c['razon_media']:.2f} (precio justo ≈ 1) | mediana {c['razon_mediana']:.2f} | "
      f"días con movimiento menor al straddle: {c['pct_dentro']:.0f}% (normal ≈ 57%)")
print(f"  ancho del bid/ask: mediana {100 * (t['ancho'] / t['straddle']).median():.1f}% del straddle | "
      f"dispersión del forward: mediana {t['dispersion'].median():.2f} pts")

t["gex_abs_B"] = t["gex_sup_B"].abs()
for objetivo, ingenuo, nombre in (("rango_sig_pct", "rango_hoy_pct", "RANGO del día siguiente"),
                                  ("mov_sig_pct", "mov_hoy_pct", "|MOVIMIENTO cierre→cierre| del día siguiente")):
    print(f"\n--- Objetivo: {nombre}. error_medio en % del spot, escalado sin mirar el día (menor = mejor) ---")
    print(ri.comparar(t, objetivo, ["impl_pct", ingenuo, "gex_sup_B", "gex_abs_B"]).round(3).to_string())
    print("  ¿De qué depende? (pred = straddle, ing = ingenuo; cada corte se escala dentro de sí mismo)")
    print(ri.robustez(t, objetivo, "impl_pct", ingenuo).round(3).to_string())
    e = ri.duelo_por_episodio(t, objetivo, "impl_pct", ingenuo)
    gana = int((e["gana"] == "impl_pct").sum())
    print(f"  Episodios de volatilidad (tamaño honesto de la muestra): {len(e)}. "
          f"El straddle le gana al ingenuo en {gana} de {len(e)}.")
    print(e.round(3).to_string(index=False))
print("\n  gex_sup_B y gex_abs_B (su valor absoluto) usan el signo SUPUESTO (hipótesis nula): el Spearman"
      "\n  negativo de gex_sup_B sería 'más GEX, menos rango'.")
print("  Con pocos episodios esto es orientativo, no evidencia.")
