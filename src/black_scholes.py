"""
Funciones de Black-Scholes: precio teórico, volatilidad implícita, delta y gamma.
Son la base matemática del GEX y de la gamma dinámica.

T en AÑOS. Regla de borde: con T <= 0 la opción ya venció.
  - precio_bs  devuelve el valor intrínseco (lo que vale al vencer)
  - delta      devuelve el delta al vencer (1/0 para call, -1/0 para put)
  - calcular_iv y gamma devuelven nan (no existen al vencimiento)
"""
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def _d1(S, K, T, r, sigma):
    return (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))


def valor_intrinseco(S, K, tipo):
    """Lo que vale la opción si se ejerce ahora mismo."""
    return max(S - K, 0.0) if tipo == "C" else max(K - S, 0.0)


def precio_bs(S, K, T, r, sigma, tipo):
    """Precio teórico de una opción (Black-Scholes). tipo = 'C' o 'P'."""
    if T <= 0:
        return valor_intrinseco(S, K, tipo)
    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    if tipo == "C":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def calcular_iv(precio_mercado, S, K, T, r, tipo):
    """Deriva la volatilidad implícita invirtiendo Black-Scholes.
    Devuelve nan si no hay solución: vencida, precio inválido o fuera del rango 1%-500%."""
    if T <= 0 or not np.isfinite(precio_mercado) or precio_mercado <= 0:
        return np.nan
    # Un precio por debajo del intrínseco descontado no corresponde a ninguna volatilidad
    if tipo == "C":
        piso = max(S - K * np.exp(-r * T), 0.0)
    else:
        piso = max(K * np.exp(-r * T) - S, 0.0)
    if precio_mercado < piso:
        return np.nan
    try:
        return brentq(
            lambda sigma: precio_bs(S, K, T, r, sigma, tipo) - precio_mercado,
            0.01, 5.0
        )
    except (ValueError, RuntimeError):
        return np.nan


def delta_opcion(S, K, T, r, sigma, tipo):
    """Delta: cuánto cambia el precio de la opción por cada punto del subyacente.
    Call entre 0 y 1, put entre -1 y 0."""
    if T <= 0:
        if tipo == "C":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    if not np.isfinite(sigma) or sigma <= 0:
        return np.nan
    d1 = _d1(S, K, T, r, sigma)
    return norm.cdf(d1) if tipo == "C" else norm.cdf(d1) - 1.0


def gamma_opcion(S, K, T, r, sigma):
    """Gamma: cuánto cambia el delta por cada punto del subyacente.
    Es la MISMA para call y put del mismo strike (por eso no recibe 'tipo')."""
    if T <= 0 or not np.isfinite(sigma) or sigma <= 0:
        return np.nan
    d1 = _d1(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))