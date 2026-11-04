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
| `veredicto.py` | ¿Qué signo del dealer sostiene el flujo medido, y con cuánto respaldo? | M1; usa `MIN_ABS` de `signo_medido` |
| `cruce.py` | ¿Cuándo llegó el precio al strike? (primer cruce / máxima aproximación) | M1 |
| `calendario.py` | ¿A qué hora cerró el mercado ese día? (cierres tempranos, tabla por año) | M3 |
| `descargas.py` | ¿Qué falta en caché para un rango de días, y cuánto cuesta? | M3; `asegurar_odte` |
| `constantes.py` | Dataset, raíz, caché, zona NY | |

### `scripts/odte/` (13 scripts, ~1.000 líneas), todos de UN día

| Grupo | Scripts |
|---|---|
| Exploración | `ver_definicion_0dte`, `ver_spx_1min`, `ver_trades_0dte`, `ver_costos_0dte` |
| Flujo en el tiempo | `ver_flujo_0dte`, `ver_apertura_0dte`, `ver_giro_0dte`, `ver_zoom_0dte` |
| Sesgos de la clasificación | `ver_sesgo_0dte`, `ver_paquete_0dte` |
| Por strike | `ver_strikes_0dte`, `antes_despues_0dte`, `caracterizar_strike_0dte` |

### Tests

`test_catalogo`, `test_clasificacion`, `test_dealer`, `test_flujo`, `test_trades`, `test_precio_spx`,
`test_veredicto`, `test_cruce` (desde M1), `test_descargas` (desde M3, con un cliente de Databento falso). Cubren:
- el bug de `expiration` (medianoche UTC = día anterior en NY);
- las fronteras bid/ask de ambas reglas;
- el desborde de `size` uint32 con flujo negativo;
- la estabilidad de la ruta de caché (si se rompe, se vuelve a pagar);
- la única fuente del cierre del SPX.

**Sin tests:** `precio.spx_1min` (cálculo de la base). La lógica de corte "primer cruce / máxima
aproximación" tiene tests desde M1 (`src/odte/cruce.py`).

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
| R1 ✅ M1 | `clasificar_trades` tenía `estricto=False` (regla histórica) por defecto | `clasificacion.py` | Un script nuevo que olvide el flag usa la regla vieja sin avisar. Hoy `ver_flujo` y `ver_sesgo` lo omiten a propósito, para comparar. |
| R2 ✅ M3 | Horas fijas: vencimiento 16:00 y ES 09:30–15:59 | `catalogo.py`, `precio.py` | En días de cierre temprano (13:00: 2026-11-27, 2026-12-24) el vencimiento queda mal y la base sale de una barra sin actividad, sin que se note. |
| R3 ⚠️ | La caché del `tcbbo` depende de la lista exacta de símbolos | `trades.py` | Pedir el mismo día con un rango de strikes un poco distinto vuelve a pagar datos que se solapan. **Pasó el 2026-11-04:** `signo_walls` con más archivos procesados elige otras series y sus 26 días quedan sin caché. |
| R4 ✅ M1 | El signo medido por strike se calculaba dentro de los scripts, solo con `MIN_ABS` | `ver_strikes_0dte`, `antes_despues_0dte` | Ignora `MIN_REL` y el % indeterminado: un "dealer −" puede apoyarse en el 10% del volumen. Choca con el contrato medido/supuesto. |
| R5 ✅ M3 | Cada descarga pedía su propia confirmación, con mensajes por stdout | `catalogo.py`, `precio.py`, `trades.py` | Un rango de N días pediría ~3N confirmaciones (CLAUDE.md lo prohíbe) y ensucia el stdout de los scripts. |

---

## 4. Mejoras propuestas

Orden aplicado: **M1 → M3** (M1 se hizo primero por un malentendido; la recomendación era M3 → M1). No quedó
inconsistente: M1 no descarga nada y M3 no toca el veredicto; el único cruce es que `corte_strike` recibe la
sesión de `spx_1min`, que desde M3 termina en la última barra real del día (12:59 en un cierre temprano).
Siguiente: **M2**. Orden recomendado original: **M3 → M1 → M2**. Sin la descarga de rango no se puede armar la muestra, y sin un veredicto
honesto la muestra mediría el 10% del volumen como si fuera todo.

| Id | Mejora | Resuelve | Estado |
|---|---|---|---|
| M3 | Descargas 0DTE con el patrón de `datos.py` | R5, R2 (R3 no) | **hecha** (2026-11-04) |
| M1 | Veredicto del signo medido en `src`, con el % indeterminado al lado | R4, R1 | **hecha** (2026-11-04) |
| M2 | De días sueltos a una muestra validada | evidencia anecdótica | pendiente |

### M3: descargas alineadas con `datos.py` — HECHA

**Qué se hizo:**
- `datos.asegurar_descargas(pedidos, descripcion, solo_costo)`: el patrón "caché primero, costo total, UNA
  confirmación" en un solo lugar. Cliente diferido (`datos._cliente`) y mensajes por stderr.
- `trades.asegurar_tcbbo({fecha: símbolos}, desde, hasta, solo_costo)`: rango de tcbbo con una confirmación.
  `parametros_tcbbo` es pública. `b2_flujo`, `signo_walls` y `medir_niveles` dejaron de copiar el bloque de
  descarga (eran 3 copias idénticas) y usan esta función. Mismo formato de archivo (NY, mismas 7 columnas).
- `catalogo` y `precio`: `pedidos_definicion` / `pedidos_es` + `ruta_*` / `parametros_*`. `descargar_definicion` y
  `descargar_es_1min` usan el patrón (ya no `input()` ni `print` por stdout).
- `descargas.asegurar_odte({fecha: (kmin, kmax)}, desde, hasta, solo_costo)`: un rango 0DTE completo con **como
  mucho DOS** confirmaciones: 1) catálogo + ES, 2) tcbbo. Son dos porque el costo del tcbbo depende de qué
  símbolos existían, y eso solo lo dice el catálogo. Ventana sin opciones -> `RuntimeError`.
- `calendario.hora_cierre(fecha)` (R2): 16:00, o 13:00 el 2026-11-27 y el 2026-12-24. Un año sin tabla grita.
  Lo usan `filtrar_0dte` (vencimiento) y el ES (última barra = cierre − 1 min).
- Efecto lateral: `catalogo`, `trades` y `precio` ya no importan `config` al cargarse; sus tests corren sin
  `DATABENTO_API_KEY` (los que importan `gex` todavía la necesitan).

**Verificación ($0, desde caché):** stdout antes/después de 8 scripts (`b2_flujo`, `signo_walls`,
`medir_niveles`, `ver_strikes`, `antes_despues`, `caracterizar_strike`, `ver_zoom`, `ver_flujo`). Todos los
números idénticos; la única diferencia son las líneas `[caché] ...`, que pasaron de stdout a stderr.
`signo_walls` se comparó hasta el paso de costo (sin clave real no se puede cotizar).

**R3 se volvió urgente:** con `data/procesado` hasta el 11-03, `signo_walls` elige 653 series en vez de 512, así que
la huella md5 de cada día cambia y **los 26 días de flujo quedan sin caché**, incluidos los 17 ya pagados (~$6,26).
Correrlo sin `--solo-costo` volvería a cobrar todo. Verificado espiando `asegurar_tcbbo` (0 de 26 en caché).

**Cambios de comportamiento a saber:**
- `signo_walls --solo-costo` ya no lista el costo por día, solo el total.
- La tabla de cierres tempranos se escribió a mano: conviene confirmarla contra el calendario oficial de
  NYSE/Cboe, y agregar 2027 antes de usar fechas de ese año.
- R3 (caché atada a la lista exacta de símbolos) sigue abierto y ahora es el riesgo más caro (ver arriba).

**Propuesta original:**
- `asegurar_odte(fechas, ...)`: suma el costo de catálogo + ES + `tcbbo` de todos los días que falten y pide **una**
  confirmación.
- Mensajes de caché y costo a stderr; cliente de Databento creado de forma diferida.
- `_parametros_tcbbo` pasa a ser pública, porque la usa medio proyecto.
- Hora de cierre real de cada día en lugar de 16:00 fijo (R2).

### M1: veredicto honesto en `src` — HECHA

**Qué se hizo:**
- `src/odte/veredicto.py`: `signo_dealer(compra, venta, indet)`, `vs_nula(..., accion_supuesta)`,
  `pct_indet(...)` y `volumenes(clasificados, por)`. Un signo solo si pasa dos pruebas:
  1) `|neto| >= MIN_ABS` (200), si no "sin evidencia";
  2) `|neto| > indeterminado` (peor caso: aunque todo lo indeterminado hubiera ido en contra, el signo
     no cambia), si no "indet. domina". Sin trades: "sin flujo".
  Sin `MIN_REL`: en el intradía 0DTE no hay ΔOI contra el cual medir; la prueba 2 cumple ese papel.
- El signo del dealer sale de `dealer.posicion_dealer` y la hipótesis nula de `gex.HIPOTESIS_NULA_PUBLICO`
  (antes los scripts los escribían a mano).
- `src/odte/cruce.py`: `corte_strike(dia, strike)`, movido desde `ver_strikes_0dte`, sin cambio de lógica.
- `clasificar_trades(trades, *, estricto)`: la regla es obligatoria y por nombre (R1). `ver_flujo` y
  `ver_sesgo` ahora pasan `estricto=False` de forma explícita.
- `ver_strikes_0dte` y `antes_despues_0dte` usan el veredicto y muestran `%indet` al lado de cada signo.

**Verificación ($0, desde caché):** antes/después de `ver_strikes_0dte` (10-12 y 10-14) y
`antes_despues_0dte` (10-14, corte 14:01). Los netos, cortes y comportamientos son idénticos; solo cambian
las columnas de veredicto.

**Resultado:** con la prueba del peor caso **ningún strike conserva un signo** en las tres corridas.
| Corrida | Antes (solo MIN_ABS) | Después |
|---|---|---|
| `ver_strikes` 10-12, día completo | + 20, − 3, sin evid. 2 | indet. domina 23, sin evid. 2 |
| `ver_strikes` 10-14, día completo | + 15, − 8, sin evid. 2 | indet. domina 23, sin evid. 2 |
| `ver_strikes` 10-14, calls / puts vs nula | confirma 15 / 7, CONTRADICE 5 / 14 | 0 confirma, 0 CONTRADICE |
| `antes_despues` 10-14 (75 celdas) | 44 +, 24 −, sin evid. 7 | 0 + / −; 68 indet. domina, 7 sin evid. |

El % indeterminado por strike va de 26% a 70%. El caso más fuerte, 7790 C del 14-oct (neto −13.561, 35%
indeterminado), tampoco pasa: lo indeterminado del strike (al menos 13,6k contratos) alcanza para anularlo. Los signos
"+"/"−" y los "confirma/CONTRADICE" que se leyeron antes en estos días descansaban en el volumen
firmado, que era menos que el no firmado.

**Pendiente de decidir:** si el peor caso es el criterio que queremos o es demasiado exigente (por
ejemplo, exigir que el neto supere una fracción del volumen sin firmar en vez de todo). Cualquier
cambio va en `veredicto.py`, con sus tests.

**Propuesta original:**
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
| 2026-11-04 | Revisión inicial y creación de este archivo. Antes: `spxw-raices` fusionada a `main` (fast-forward a `48d7433`); el trabajo 0DTE sigue en la rama `odte-mejoras` | `2ca92b5` | 345 líneas en `src/odte`, 13 scripts, 6 tests; riesgos R1–R5; mejoras M1–M3 pendientes |
| 2026-11-04 | M1: `veredicto.py` y `cruce.py` en `src/odte`; `estricto` obligatorio; `ver_strikes` y `antes_despues` con `%indet` | (este commit) | 193 tests (27 nuevos); netos idénticos; con el peor caso, 0 strikes con signo en 10-12 y 10-14 (antes 23 y 23) |
| 2026-11-04 | M3: `asegurar_descargas` (datos), `asegurar_tcbbo`, `asegurar_odte`, `calendario`; 3 scripts sin descarga copiada; mensajes a stderr | (este commit) | 206 tests (13 nuevos); stdout idéntico en 8 scripts salvo `[caché]`; rango 0DTE = como mucho 2 confirmaciones (antes ~3 por día) |
