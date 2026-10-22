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

For multi-day ranges, `datos.asegurar_cadenas(fechas, raices)` sums the cost of every missing (date, root, schema) and asks for **one** confirmation for the total. After that, `descargar_cadena` reads from the cache without prompting. Range scripts (`validar_gex`, `b2_flujo`) use this single-confirmation pattern. Do not reintroduce one prompt per day.

Do not bypass this, and do not run a script on uncached dates without the user knowing it will prompt for and spend credit. Cached dates cost $0. In `src/datos.py`, cache/cost messages go to **stderr** so that script stdout stays clean for before/after diffs. The `antes.txt`/`despues*.txt`/`gex_*.txt` files at the root are such captures, written by PowerShell redirection and therefore UTF-16.

## Architecture

**Core pipeline (`src/`)**, daily chain → GEX:
- `datos.py`: the only layer that talks to the outside world. `descargar_cadena(fecha, raices)` fetches the `ohlcv-1d` + `statistics` schemas per root (`SPX` monthly AM, `SPXW` daily/weekly PM) and returns `(precios, oi)` deduplicated to one row per symbol. `precio_spx(fecha)` is the **single** source of the SPX close (`odte.precio.cierre_spx` is an alias). The Databento client is created lazily.
- `simbolos.py`: the **single** OSI symbol parser (`'SPXW  261016C07800000'`). It was consolidated from 6 copies, so always use it rather than re-parsing. It raises on an unexpected format.
- `black_scholes.py`: price/IV/delta/gamma with an optional continuous dividend `q`. With `q=0` the results are exactly the pre-dividend behaviour. Edge rule: `T<=0` → intrinsic value / expiry delta, and IV and gamma are `nan`.
- `precio_justo.py`: `tabla_cierre(fecha)` gives the closing bid/ask mid per option from the already-downloaded `statistics` (stat_type 8 = bid, 7 = ask, 9 = OI). It exists because the last trade was stale for ~74% of options.
- `forward.py`: the implied forward per expiry from put-call parity on ATM-forward strikes (median, with reported dispersion). This gives the implied `q`. Expiries with too few strikes inherit `q` from the nearest measured one (`origen="heredado"`).
- `gex.py`: `construir_cadena(fecha, S, metodo)` with two methods:
  - `"mid_forward"` (**default since Oct 2026**, "versión C"): closing mid, all options with OI, `q` measured per expiry.
  - `"ultimo_trade"` (the original, kept for comparison): last trade price, only traded options, `q=0`.

  The default changed for **valuation** reasons: the unused OI is ~25% of the book, missing IVs created phantom walls (the 7000 wall on 24-sep), and the last trade was stale. It did **not** change for predictive reasons, since next-day range prediction came out even between the two methods. The docstring records this, so keep it accurate. Changes to the default method must be deliberate. The project compares methods side by side instead of silently replacing one.

  Two more parameters, both off by default (default output is bit-identical to before they existed):
  - `raices=("SPX",)` (default, monthly AM only) or `("SPX", "SPXW")`, which adds the daily/weekly PM short-dated gamma. The forward is measured **per root** (`forward.q_por_raiz`). `forward_por_vencimiento` raises if given more than one root, because SPX AM and SPXW PM share the third-Friday expiry and strikes.
  - `plazo="dias"` (default, calendar days/365) or `"horas"`, which is NY close of `fecha` → 9:30 (SPX) / 16:00 (SPXW) of expiry, DST-aware. `simbolos.plazo_anios` is the **single** place T is computed. Use `"horas"` with SPXW.

  The chain carries `raiz` and `dte` columns. `gex_por_plazo(cadena)` breaks the total down by root × DTE bucket (`1-3d`, `4-7d`, `8-35d`, `>35d`). This SPXW work lives on branch `spxw-raices`. Tag `antes-spxw` marks main before it.

  `gex_contrib = gamma · OI · signo · 100 · S² · 0.01`. Here `signo` comes from `signo_gamma_supuesto`, which derives it from `HIPOTESIS_NULA_PUBLICO` (the public sells calls and buys puts) through the `odte.dealer` sign table. It is an **assumed** sign, not a measured one, so don't hard-code `+1/−1`. Two views of the profile:
  - `gamma_walls` buckets the strikes into `banda`-point zones and returns the top `+` zones above and the top `−` zones below the spot. That split bakes in the convention that "above = resistance, below = support".
  - `niveles_gamma` ranks zones by `|gex_neto|` with no such convention. It reports position, calls/puts, `pct_abs` and `signo_supuesto` as columns. With an optional `medido` series (net public contracts per strike under the strict rule) it adds `signo_medido`, where `"sin evidencia"` means below `MIN_ABS_NIVEL`=200 and `"no medido"` means the zone had no flow.
- `trade_sign.py`: classifies trades on specific strikes (e.g. walls) by the price-vs-mid rule.

**Fase B, assumed vs measured dealer sign (`src/`)**:
- `inventario.py` (B1): OI per date and option, `delta_oi` against the previous date in the series (the `nueva` flag marks an option seen for the first time), and `por_zona`. It is sign-neutral and only reads the cache. **Time rule (confirmed, with tests):** the OI in day *d*'s file is the OI at the close of *d−1*, so the ΔOI of *d* is explained by the flow of the **previous** market day (`fecha_flujo`, which raises if there is no previous day).
- `signo_medido.py` (B3): `veredicto(neto_medido, delta_oi, accion_supuesta)` returns `confirma` / `CONTRADICE` / `demasiado chico` / `no atribuible` / `sin ΔOI`. It only gives an opinion when both minimums hold: `MIN_ABS`=200 contracts and `MIN_REL`=20% of the ΔOI. `pct_delta_indet` and `pct_oi_supuesto` measure how much of a wall's sign is assumption.
- Phase B result: 98–99.9% of the walls' sign is **assumed**. The assumed sign and the measured flow are always shown side by side and are **never merged** into one GEX number. The strict classification has three states (buy at ask / sell at bid / indeterminate), and the indeterminate part is never redistributed.

**0DTE package (`src/odte/`)**: one module per question (see `src/odte/__init__.py`): `catalogo` (the `definition` schema, 0DTE filter), `precio` (SPX per minute = ES 1-min minus the close basis, since OPRA has no index), `trades` (`tcbbo`, cache keyed by an md5 of the symbols plus the time window), `clasificacion` (midpoint rule vs a strict at-bid/at-ask rule, with a `complejo` flag for prints outside the spread), `flujo` (per-minute public flow; the dealer is the opposite sign), `dealer` (the dealer sign table). Constants are in `constantes.py`.

**Timezones:** every timestamp carries `America/New_York` explicitly. Databento `expiration` is midnight UTC, which falls on the *previous* day in NY. This was the project's first bug and has a regression test in `tests/test_catalogo.py`.

**Scripts (`scripts/`, `scripts/odte/`)** are one-off analyses/visualisations. Each does `sys.path.insert(0, <repo root>)` and then imports from `src`. Their module docstring documents the usage (`Uso: python scripts/... <fecha> [q]`). Charts are saved to `data/*.png` (gitignored). Some results are tracked in git as CSVs:
- `data/validacion/gex_dias.csv` is an **accumulator**. Each `validar_gex` run merges its days into it. `analizar_validacion.py` analyses all accumulated windows at $0.
- `data/b2/flujo_series.csv` is the output of `b2_flujo`.
- `validar_gex ... --spxw` (SPX+SPXW, `plazo="horas"`) writes to a **separate** accumulator, `data/validacion/gex_dias_spxw.csv`, analysed with `analizar_validacion.py <ruta>`. Never mix the two CSVs. `comparar_raices_gex.py` compares configs A (SPX/dias), B (SPX/horas) and C (SPX+SPXW/horas) per date. SPXW costs ~$0.46–0.49 per uncached day (SPX ~$0.20).

**Validation rules (`validar_gex` / `analizar_validacion`, not negotiable):**
- Always compare the day-before-close GEX with what happens next, never with the same day.
- Report GEX changes in $B, not %, because a % change flips sign when GEX is negative.
- Days are not independent, so report **episodes** (same-sign runs). The honest sample size is the number of episodes.
- Every result must beat the **naive predictor**, which is today's range (`rango_hoy`).

## Conventions seen in the code

- Prefer a loud failure ("error que grita") over silently wrong numbers ("error que susurra"): raise `ValueError`/`RuntimeError` with a clear message, and return `nan` rather than a fake value.
- Label every number by what it rests on. "Assumed" (from the null hypothesis) and "measured" (from classified flow) are separate columns, and no conclusion merges them. Below the evidence minimums, the answer is "sin evidencia" or "demasiado chico", never a guess.
- Commit messages are short Spanish summaries of what changed plus the numerical finding (e.g. GEX deltas and test counts).
