"""
Funciones de Black-Scholes: precio teórico, volatilidad implícita, delta y gamma.
Son la base matemática del GEX y de la gamma dinámica.

T en AÑOS. Regla de borde: con T <= 0 la opción ya venció.
  - precio_bs  devuelve el valor intrínseco (lo que vale al vencer)
  - delta      devuelve el delta al vencer (1/0 para call, -1/0 para put)
  - calcular_iv y gamma devuelven nan (no existen al vencimiento)

Dividendos: q = rendimiento de dividendo continuo (0.013 = 1,3% anual). Por defecto 0,
y con q = 0 todo da EXACTAMENTE lo mismo que la versión sin dividendos.
Idea: el índice "pierde" los dividendos que paga, así que el precio a plazo (forward) es
  F = S · e^((r - q)·T)
y la opción se valúa sobre ese F. Sin q, el modelo cree que F está más alto de lo real:
  - las calls ITM le parecen más caras de lo que paga el mercado -> IV nan (el error que grita)
  - las puts le parecen más baratas -> sube la vol para igualar -> IV inflada (el que susurra)
"""
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def _d1(S, K, T, r, sigma, q=0.0):
    return (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))


def valor_intrinseco(S, K, tipo):
    """Lo que vale la opción si se ejerce ahora mismo."""
    return max(S - K, 0.0) if tipo == "C" else max(K - S, 0.0)


def precio_bs(S, K, T, r, sigma, tipo, q=0.0):
    """Precio teórico de una opción europea (Black-Scholes con dividendo continuo q)."""
    if T <= 0:
        return valor_intrinseco(S, K, tipo)
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = d1 - sigma * np.sqrt(T)
    S_desc = S * np.exp(-q * T)          # spot sin los dividendos que se pagarán antes del vencimiento
    K_desc = K * np.exp(-r * T)
    if tipo == "C":
        return S_desc * norm.cdf(d1) - K_desc * norm.cdf(d2)
    return K_desc * norm.cdf(-d2) - S_desc * norm.cdf(-d1)


def calcular_iv(precio_mercado, S, K, T, r, tipo, q=0.0):
    """Deriva la volatilidad implícita invirtiendo Black-Scholes.
    Devuelve nan si no hay solución: vencida, precio inválido o fuera del rango 1%-500%."""
    if T <= 0 or not np.isfinite(precio_mercado) or precio_mercado <= 0:
        return np.nan
    # Piso: valor de la opción con vol cero = intrínseco sobre el FORWARD, descontado
    S_desc, K_desc = S * np.exp(-q * T), K * np.exp(-r * T)
    piso = max(S_desc - K_desc, 0.0) if tipo == "C" else max(K_desc - S_desc, 0.0)
    if precio_mercado < piso:
        return np.nan
    try:
        return brentq(
            lambda sigma: precio_bs(S, K, T, r, sigma, tipo, q) - precio_mercado,
            0.01, 5.0
        )
    except (ValueError, RuntimeError):
        return np.nan


def delta_opcion(S, K, T, r, sigma, tipo, q=0.0):
    """Delta: cuánto cambia el precio de la opción por cada punto del SPOT.
    Call entre 0 y e^(-qT), put entre -e^(-qT) y 0."""
    if T <= 0:
        if tipo == "C":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    if not np.isfinite(sigma) or sigma <= 0:
        return np.nan
    d1 = _d1(S, K, T, r, sigma, q)
    e = np.exp(-q * T)
    return e * norm.cdf(d1) if tipo == "C" else e * (norm.cdf(d1) - 1.0)


def gamma_opcion(S, K, T, r, sigma, q=0.0):
    """Gamma: cuánto cambia el delta por cada punto del SPOT (la que usa el GEX).
    Es la MISMA para call y put del mismo strike (por eso no recibe 'tipo').
    Ojo: el factor e^(-qT) es lo que la hace gamma respecto al spot y no al forward."""
    if T <= 0 or not np.isfinite(sigma) or sigma <= 0:
        return np.nan
    d1 = _d1(S, K, T, r, sigma, q)
    return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))