"""
Funciones de Black-Scholes: precio teórico, volatilidad implícita y gamma.
Estas son la base matemática del GEX.
"""
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


def precio_bs(S, K, T, r, sigma, tipo):
    """Precio teórico de una opción (Black-Scholes). tipo = 'C' o 'P'."""
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if tipo == "C":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def calcular_iv(precio_mercado, S, K, T, r, tipo):
    """Deriva la volatilidad implícita invirtiendo Black-Scholes."""
    try:
        return brentq(
            lambda sigma: precio_bs(S, K, T, r, sigma, tipo) - precio_mercado,
            0.01, 5.0
        )
    except (ValueError, RuntimeError):
        return np.nan


def gamma_opcion(S, K, T, r, sigma):
    """Calcula la gamma de una opción (Black-Scholes)."""
    if np.isnan(sigma) or T <= 0:
        return np.nan
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))