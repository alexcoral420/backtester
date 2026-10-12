# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Research tooling for SPX options: computing dealer **GEX (gamma exposure)** and **gamma walls** from the daily option chain, plus a study of the intraday **0DTE** (SPXW same-day expiry) order flow. Data comes from Databento (OPRA options, CME ES futures) and yfinance (the SPX close). Code, comments, identifiers and commit messages are all in **Spanish**. Keep writing in Spanish.

## Commands

Windows, venv in `venv/`. Run everything from the repo root, because cache paths like `data/raw` are relative.

```powershell
venv\Scripts\activate
pip install -r requirements.txt          # requirements.txt is UTF-16 encoded

$env:DATABENTO_API_KEY = "db-..."        # required, see below
python -m pytest                         # all tests (pytest.ini sets pythonpath=. and testpaths=tests)
python -m pytest tests/test_forward.py::nombre_del_test   # single test
python scripts/ver_gex.py                # scripts take dates as positional args, e.g.
python scripts/comparar_versiones_gex.py 2026-09-24 2026-09-29
```

- `config.py` raises `ValueError` at import time if `DATABENTO_API_KEY` is unset. Several test modules import it transitively (gex, odte.catalogo/trades/precio), so **tests need the variable set**. Any dummy value works. The tests make no network calls (yfinance is monkeypatched).
- There is no linter/formatter config and no build step.

## Data and cost rules (important)

Databento downloads cost real money. Every download path follows the same pattern:
1. A **cache-first** parquet in `data/raw/` (gitignored). If the file exists, no API call is made.
2. Otherwise **`metadata.get_cost` first**, then an interactive `s/n` confirmation on stdin, and only then the download.

Do not bypass this, and do not run a script on uncached dates without the user knowing it will prompt for and spend credit. Cached dates cost $0. In `src/datos.py`, cache/cost messages go to **stderr** so that script stdout stays clean for before/after diffs. The `antes.txt`/`despues*.txt`/`gex_*.txt` files at the root are such captures, written by PowerShell redirection and therefore UTF-16.

## Architecture

**Core pipeline (`src/`)**, daily chain → GEX:
- `datos.py`: the only layer that talks to the outside world. `descargar_cadena(fecha, raices)` fetches the `ohlcv-1d` + `statistics` schemas per root (`SPX` monthly AM, `SPXW` daily/weekly PM) and returns `(precios, oi)` deduplicated to one row per symbol. `precio_spx(fecha)` is the **single** source of the SPX close (`odte.precio.cierre_spx` is an alias). The Databento client is created lazily.
- `simbolos.py`: the **single** OSI symbol parser (`'SPXW  261016C07800000'`). It was consolidated from 6 copies, so always use it rather than re-parsing. It raises on an unexpected format.
- `black_scholes.py`: price/IV/delta/gamma with an optional continuous dividend `q`. With `q=0` the results are exactly the pre-dividend behaviour. Edge rule: `T<=0` → intrinsic value / expiry delta, and IV and gamma are `nan`.
- `precio_justo.py`: `tabla_cierre(fecha)` gives the closing bid/ask mid per option from the already-downloaded `statistics` (stat_type 8 = bid, 7 = ask, 9 = OI). It exists because the last trade was stale for ~74% of options.
- `forward.py`: the implied forward per expiry from put-call parity on ATM-forward strikes (median, with reported dispersion). This gives the implied `q`. Expiries with too few strikes inherit `q` from the nearest measured one (`origen="heredado"`).
- `gex.py`: `construir_cadena(fecha, S, metodo)` with two methods:
  - `"ultimo_trade"` (**default, original**): last trade price, only traded options, `q=0`.
  - `"mid_forward"` ("versión C"): closing mid, all options with OI, `q` measured per expiry.

  `gex_contrib = gamma · OI · (+1 call / −1 put) · 100 · S² · 0.01`. `gamma_walls` buckets the strikes into `banda`-point zones. Changes to the default method must be deliberate. The project compares methods side by side instead of silently replacing one.
- `trade_sign.py`: classifies trades on specific strikes (e.g. walls) by the price-vs-mid rule.

**0DTE package (`src/odte/`)**: one module per question (see `src/odte/__init__.py`): `catalogo` (the `definition` schema, 0DTE filter), `precio` (SPX per minute = ES 1-min minus the close basis, since OPRA has no index), `trades` (`tcbbo`, cache keyed by an md5 of the symbols plus the time window), `clasificacion` (midpoint rule vs a strict at-bid/at-ask rule, with a `complejo` flag for prints outside the spread), `flujo` (per-minute public flow; the dealer is the opposite sign), `dealer` (the dealer sign table). Constants are in `constantes.py`.

**Timezones:** every timestamp carries `America/New_York` explicitly. Databento `expiration` is midnight UTC, which falls on the *previous* day in NY. This was the project's first bug and has a regression test in `tests/test_catalogo.py`.

**Scripts (`scripts/`, `scripts/odte/`)** are one-off analyses/visualisations. Each does `sys.path.insert(0, <repo root>)` and then imports from `src`. Their module docstring documents the usage (`Uso: python scripts/... <fecha> [q]`). Charts are saved to `data/*.png` (gitignored).

## Conventions seen in the code

- Prefer a loud failure ("error que grita") over silently wrong numbers ("error que susurra"): raise `ValueError`/`RuntimeError` with a clear message, and return `nan` rather than a fake value.
- Commit messages are short Spanish summaries of what changed plus the numerical finding (e.g. GEX deltas and test counts).
