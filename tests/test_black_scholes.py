"""
Tests de Black-Scholes contra valores conocidos y contra sus propias identidades.
Si algo aquí falla, el GEX y la gamma dinámica están mal desde la base.
"""
import numpy as np
import pytest

from src.black_scholes import (calcular_iv, delta_opcion, gamma_opcion,
                               precio_bs, valor_intrinseco)

# Caso de libro: S = K = 100, un año, tasa 5%, volatilidad 20%
S, K, T, R, SIGMA = 100.0, 100.0, 1.0, 0.05, 0.20


# ---------------- precio ----------------

def test_valor_de_libro():
    assert precio_bs(S, K, T, R, SIGMA, "C") == pytest.approx(10.4506, abs=1e-4)
    assert precio_bs(S, K, T, R, SIGMA, "P") == pytest.approx(5.5735, abs=1e-4)


@pytest.mark.parametrize("strike", [80, 95, 100, 105, 120])
@pytest.mark.parametrize("t", [1 / 365, 7 / 365, 0.25, 1.0])
def test_paridad_call_put(strike, t):
    """C - P = S - K·e^(-rT): identidad que no depende del modelo de volatilidad."""
    c = precio_bs(S, strike, t, R, SIGMA, "C")
    p = precio_bs(S, strike, t, R, SIGMA, "P")
    assert c - p == pytest.approx(S - strike * np.exp(-R * t), abs=1e-8)


def test_vencida_vale_el_intrinseco():
    assert precio_bs(105, 100, 0, R, SIGMA, "C") == 5.0
    assert precio_bs(105, 100, 0, R, SIGMA, "P") == 0.0
    assert valor_intrinseco(95, 100, "P") == 5.0


# ---------------- volatilidad implícita ----------------

@pytest.mark.parametrize("strike", [90, 100, 110])
@pytest.mark.parametrize("tipo", ["C", "P"])
@pytest.mark.parametrize("vol", [0.10, 0.35, 0.80])
def test_iv_ida_y_vuelta(strike, tipo, vol):
    """Precio generado con una vol -> la IV calculada debe devolver esa misma vol."""
    precio = precio_bs(S, strike, 0.1, R, vol, tipo)
    assert calcular_iv(precio, S, strike, 0.1, R, tipo) == pytest.approx(vol, abs=1e-6)


def test_iv_vencida_es_nan():
    """Regresión del borde: con T = 0, brentq podía devolver un número inventado."""
    assert np.isnan(calcular_iv(5.0, 105, 100, 0, R, "C"))


def test_iv_precio_imposible_es_nan():
    """Una call 20 puntos dentro del dinero no puede valer 3: no hay vol que la explique."""
    assert np.isnan(calcular_iv(3.0, 120, 100, 0.1, R, "C"))


def test_iv_precio_invalido_es_nan():
    assert np.isnan(calcular_iv(np.nan, S, K, T, R, "C"))
    assert np.isnan(calcular_iv(0.0, S, K, T, R, "C"))


# ---------------- delta y gamma ----------------

def test_delta_call_menos_delta_put_es_uno():
    dc = delta_opcion(S, 105, 0.25, R, SIGMA, "C")
    dp = delta_opcion(S, 105, 0.25, R, SIGMA, "P")
    assert dc - dp == pytest.approx(1.0, abs=1e-12)
    assert 0 < dc < 1 and -1 < dp < 0


def test_gamma_es_la_derivada_del_delta():
    """Consistencia entre funciones: mover S un poco y medir cuánto cambia el delta."""
    h = 0.01
    dd = (delta_opcion(S + h, K, 0.25, R, SIGMA, "C") -
          delta_opcion(S - h, K, 0.25, R, SIGMA, "C")) / (2 * h)
    assert gamma_opcion(S, K, 0.25, R, SIGMA) == pytest.approx(dd, rel=1e-5)


def test_gamma_maxima_cerca_del_dinero_y_crece_al_vencer():
    """Las dos propiedades que hacen de las 0DTE 'bombas de gamma'."""
    atm = gamma_opcion(S, 100, 0.25, R, SIGMA)
    otm = gamma_opcion(S, 120, 0.25, R, SIGMA)
    assert atm > otm
    assert gamma_opcion(S, 100, 1 / 365, R, SIGMA) > atm


def test_vencida_delta_escalon_y_gamma_nan():
    assert delta_opcion(105, 100, 0, R, SIGMA, "C") == 1.0
    assert delta_opcion(95, 100, 0, R, SIGMA, "C") == 0.0
    assert delta_opcion(95, 100, 0, R, SIGMA, "P") == -1.0
    assert np.isnan(gamma_opcion(S, K, 0, R, SIGMA))
    assert np.isnan(gamma_opcion(S, K, T, R, np.nan))


# ---------------- dividendos (q) ----------------
Q = 0.013


@pytest.mark.parametrize("strike", [80, 100, 120])
@pytest.mark.parametrize("t", [7 / 365, 0.25, 1.0])
def test_paridad_con_dividendos(strike, t):
    """C - P = S·e^(-qT) - K·e^(-rT)."""
    c = precio_bs(S, strike, t, R, SIGMA, "C", q=Q)
    p = precio_bs(S, strike, t, R, SIGMA, "P", q=Q)
    assert c - p == pytest.approx(S * np.exp(-Q * t) - strike * np.exp(-R * t), abs=1e-8)


def test_q_cero_no_cambia_nada():
    """Con q = 0 todo da idéntico a la versión sin dividendos (refactor seguro)."""
    for tipo in ["C", "P"]:
        assert precio_bs(S, 95, 0.3, R, SIGMA, tipo, q=0.0) == precio_bs(S, 95, 0.3, R, SIGMA, tipo)
    assert gamma_opcion(S, 95, 0.3, R, SIGMA, q=0.0) == gamma_opcion(S, 95, 0.3, R, SIGMA)


def test_valor_de_libro_con_dividendos():
    """S=K=100, T=1, r=5%, q=3%, vol=20%: d1 = 0.2, d2 = 0
    -> 100·e^-0.03·N(0.2) - 100·e^-0.05·N(0) = 56.214 - 47.561 = 8.6525 (cuenta a mano)."""
    assert precio_bs(100, 100, 1, 0.05, 0.20, "C", q=0.03) == pytest.approx(8.6525, abs=1e-3)


def test_call_7000_deja_de_ser_nan():
    """Caso real 24-sep-2026: SPX ~7700, call 7000 venc 16-oct, mid 717.10.
    Sin dividendos el mid queda bajo el piso (nan); con q ~1.3% tiene IV."""
    S_, K_, T_, r_ = 7722.0, 7000.0, 22 / 365, 0.04
    piso_sin_q = S_ - K_ * np.exp(-r_ * T_)
    mid = piso_sin_q - 6.0                      # el mercado paga menos que el piso sin dividendos
    assert np.isnan(calcular_iv(mid, S_, K_, T_, r_, "C"))
    assert np.isfinite(calcular_iv(mid, S_, K_, T_, r_, "C", q=Q))


@pytest.mark.parametrize("tipo", ["C", "P"])
def test_iv_ida_y_vuelta_con_dividendos(tipo):
    precio = precio_bs(S, 105, 0.5, R, 0.25, tipo, q=Q)
    assert calcular_iv(precio, S, 105, 0.5, R, tipo, q=Q) == pytest.approx(0.25, abs=1e-6)


def test_put_iv_inflada_sin_dividendos():
    """El error que susurra: una put valuada CON q, invertida SIN q, da IV más alta."""
    precio = precio_bs(S, 110, 1.0, R, 0.20, "P", q=Q)
    assert calcular_iv(precio, S, 110, 1.0, R, "P") > 0.20


def test_gamma_con_q_es_derivada_del_delta_respecto_al_spot():
    """El factor e^(-qT): si falta, el GEX sale mal en silencio."""
    h = 0.01
    dd = (delta_opcion(S + h, K, 1.0, R, SIGMA, "C", q=Q) -
          delta_opcion(S - h, K, 1.0, R, SIGMA, "C", q=Q)) / (2 * h)
    assert gamma_opcion(S, K, 1.0, R, SIGMA, q=Q) == pytest.approx(dd, rel=1e-5)