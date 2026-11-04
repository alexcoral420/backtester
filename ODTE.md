# ODTE.md — Estado y bitácora del módulo 0DTE

Trazabilidad del paquete `src/odte/` y de los scripts `scripts/odte/`: qué hay, sobre qué fundamentos
trabaja, qué riesgos tiene y qué mejoras se van aplicando. Se actualiza en cada mejora (ver **Bitácora**).

- Revisión inicial: 2026-11-04, rama `spxw-raices`, commit `48d7433`.
- Último cambio de código del módulo a esa fecha: `1171d50` (2026-10-17).

---

## 1. Archivos

### `src/odte/` (345 líneas): un módulo por pregunta

| Módulo | Pregunta | Fuente / costo |
|---|---|---|
| `catalogo.py` | ¿Qué SPXW existían y cuáles eran 0DTE? | schema `definition` (~$0,03/día) |
| `precio.py` | ¿Dónde estaba el SPX cada minuto? | ES 1-min (`ES.v.0`) − base de cierre (~$0,005/día) |
| `trades.py` | ¿Qué se negoció? | `tcbbo`; caché por md5 de los símbolos + franja |
| `clasificacion.py` | ¿Quién agredió? | regla del punto medio (histórica) vs estricta (bid/ask exacto) + flag `complejo` |
| `flujo.py` | ¿Cómo se acumula? | neto del público por minuto, calls/puts separados, acumulados |
| `dealer.py` | Tabla de signos del dealer | también la usa `src/gex.py` |
| `constantes.py` | Dataset, raíz, caché, zona NY | |

### `scripts/odte/` (13 scripts, ~1.000 líneas), todos de UN día

| Grupo | Scripts |
|---|---|
| Exploración | `ver_definicion_0dte`, `ver_spx_1min`, `ver_trades_0dte`, `ver_costos_0dte` |
| Flujo en el tiempo | `ver_flujo_0dte`, `ver_apertura_0dte`, `ver_giro_0dte`, `ver_zoom_0dte` |
| Sesgos de la clasificación | `ver_sesgo_0dte`, `ver_paquete_0dte` |
| Por strike | `ver_strikes_0dte`, `antes_despues_0dte`, `caracterizar_strike_0dte` |

### Tests

`test_catalogo`, `test_clasificacion`, `test_dealer`, `test_flujo`, `test_trades`, `test_precio_spx`. Cubren:
- el bug de `expiration` (medianoche UTC = día anterior en NY);
- las fronteras bid/ask de ambas reglas;
- el desborde de `size` uint32 con flujo negativo;
- la estabilidad de la ruta de caché (si se rompe, se vuelve a pagar);
- la única fuente del cierre del SPX.

**Sin tests:** `precio.spx_1min` (cálculo de la base) y la lógica de corte "primer cruce / máxima
aproximación", que hoy vive solo en `scripts/odte/ver_strikes_0dte.py`.

---

## 2. Fundamentos

1. **Hora NY explícita en todo.** El vencimiento sale del símbolo (no de `expiration`) y se fija a las 16:00 NY.
2. **SPX intradía = ES − base.** OPRA no trae el índice. La base es ES (barra 15:59) − cierre oficial del SPX y se
   asume constante durante el día.
3. **Quién agredió, regla estricta (vigente).** Tres estados: compra (en el ask), venta (en el bid) e indeterminado
   (todo lo demás, incluido lo impreso fuera del spread = `complejo`). Lo indeterminado no se redistribuye.
   La regla del punto medio se conserva solo para comparar.
4. **El dealer es el lado pasivo.** Su signo es el contrario al del público; su gamma tiene el signo de su posición
   (largo = +, corto = −), sin depender del delta.
5. **Costo primero, caché siempre.** `get_cost` → confirmación `s/n` → descarga → parquet en `data/raw/`.
6. **Orden temporal.** Para la pregunta "¿qué tenía el dealer cuando llegó el precio?" solo cuenta el flujo
   anterior al primer cruce (o a la máxima aproximación si nunca cruzó). El minuto del cruce queda fuera.

---

## 3. Estado actual (2026-11-04)

**Caché 0DTE:**
- `tcbbo`: 2026-09-24 … 2026-10-19.
- `definition`: 11 días (09-29, 09-30, 10-02, 10-05, 10-06, 10-12, 10-13, 10-14, 10-15, 10-16, 10-19).
- ES 1-min: esos mismos días salvo 09-30 (10 días).
- Desde el 20-oct no hay nada de 0DTE.

**Rol real del paquete:** es la capa de `tcbbo` de todo el proyecto. `b2_flujo`, `signo_walls`, `medir_niveles`,
`ratio_flujo_oi` y `reverificar_walls` importan `clasificar_trades`, y varios también `_parametros_tcbbo`
(una función privada).

**Tipo de evidencia:** casos sueltos (29-sep, 2-oct, 14-oct). No hay muestra de varios días, ni episodios, ni
comparación contra un predictor ingenuo como exige la validación del GEX.

**Resultado de Fase B que también aplica aquí:** con la regla estricta, entre 85% y 96% del volumen es
indeterminado y ~30% se imprime fuera del bid/ask (paquetes).

### Riesgos detectados

| # | Riesgo | Dónde | Efecto |
|---|---|---|---|
| R1 | `clasificar_trades` tiene `estricto=False` (regla histórica) por defecto | `clasificacion.py` | Un script nuevo que olvide el flag usa la regla vieja sin avisar. Hoy `ver_flujo` y `ver_sesgo` lo omiten a propósito, para comparar. |
| R2 | Horas fijas: vencimiento 16:00 y ES 09:30–15:59 | `catalogo.py`, `precio.py` | En días de cierre temprano (13:00: 2026-11-27, 2026-12-24) el vencimiento queda mal y la base sale de una barra sin actividad, sin que se note. |
| R3 | La caché del `tcbbo` depende de la lista exacta de símbolos | `trades.py` | Pedir el mismo día con un rango de strikes un poco distinto vuelve a pagar datos que se solapan. |
| R4 | El signo medido por strike se calcula dentro de los scripts, solo con `MIN_ABS` | `ver_strikes_0dte`, `antes_despues_0dte` | Ignora `MIN_REL` y el % indeterminado: un "dealer −" puede apoyarse en el 10% del volumen. Choca con el contrato medido/supuesto. |
| R5 | Cada descarga pide su propia confirmación, con mensajes por stdout | `catalogo.py`, `precio.py`, `trades.py` | Un rango de N días pediría ~3N confirmaciones (CLAUDE.md lo prohíbe) y ensucia el stdout de los scripts. |

---

## 4. Mejoras propuestas

Orden recomendado: **M3 → M1 → M2**. Sin la descarga de rango no se puede armar la muestra, y sin un veredicto
honesto la muestra mediría el 10% del volumen como si fuera todo.

| Id | Mejora | Resuelve | Estado |
|---|---|---|---|
| M3 | Descargas 0DTE con el patrón de `datos.py` | R5, R2, R3 (parcial) | pendiente |
| M1 | Veredicto del signo medido en `src`, con el % indeterminado al lado | R4, R1 | pendiente |
| M2 | De días sueltos a una muestra validada | evidencia anecdótica | pendiente |

### M3: descargas alineadas con `datos.py`
- `asegurar_odte(fechas, ...)`: suma el costo de catálogo + ES + `tcbbo` de todos los días que falten y pide **una**
  confirmación.
- Mensajes de caché y costo a stderr; cliente de Databento creado de forma diferida.
- `_parametros_tcbbo` pasa a ser pública, porque la usa medio proyecto.
- Hora de cierre real de cada día en lugar de 16:00 fijo (R2).

### M1: veredicto honesto en `src`
- Una función (en `src/odte` o reutilizando `src/signo_medido`) que devuelva el signo del dealer junto con la
  fracción de volumen que lo respalda, y que diga "sin evidencia" cuando el indeterminado domina.
- Llevar `corte_strike` (primer cruce / máxima aproximación) a `src`, con tests.
- Revisar R1: hacer explícita la regla en cada llamada o cambiar el valor por defecto de forma deliberada.

### M2: muestra validada
- Un script de rango (`validar_0dte`) que mida algo fijo por día, por ejemplo el flujo estricto antes de tocar el
  nivel frente a si el nivel aguantó o se cruzó.
- Acumulador CSV propio, separado de los de GEX.
- Análisis por **episodios** y comparación contra un predictor ingenuo (la frecuencia base con la que aguanta el
  strike más cercano).

---

## 5. Bitácora

| Fecha | Cambio | Commit | Resultado / números |
|---|---|---|---|
| 2026-11-04 | Revisión inicial y creación de este archivo | — | 345 líneas en `src/odte`, 13 scripts, 6 tests; riesgos R1–R5; mejoras M1–M3 pendientes |
