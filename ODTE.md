# ODTE.md — Estado y bitácora del módulo 0DTE

Trazabilidad del paquete `src/odte/` y de los scripts `scripts/odte/`: qué hay, sobre qué fundamentos
trabaja, qué riesgos tiene y qué mejoras se van aplicando. Se actualiza en cada mejora (ver **Bitácora**).

- Revisión inicial: 2026-11-04, rama `spxw-raices`, commit `48d7433`.
- Último cambio de código del módulo a esa fecha: `1171d50` (2026-10-17).

> **Por dónde seguir (actualizado 2026-11-09, rama `odte-mejoras`, 253 tests):**
> M1 y M2 cerradas (el signo no es identificable). En curso: **M4**, carga sin signo contra toques. Las tres
> dudas están resueltas y el **diseño está fijo** (sección M4, "Diseño fijo de M4"). ES en caché: los 30 días.
> **Lo siguiente:** el script de M4, sus tests y la corrida ($0).

---

## 1. Archivos

### `src/odte/` (345 líneas): un módulo por pregunta

| Módulo | Pregunta | Fuente / costo |
|---|---|---|
| `catalogo.py` | ¿Qué SPXW existían y cuáles eran 0DTE? | schema `definition` (~$0,03/día) |
| `precio.py` | ¿Dónde estaba el SPX cada minuto? | ES 1-min (`ES.v.0`) − base de cierre (~$0,005/día) |
| `trades.py` | ¿Qué se negoció? | `tcbbo`; caché POR SÍMBOLO (desde R3): `asegurar_tcbbo` / `leer_tcbbo` |
| `clasificacion.py` | ¿Quién agredió? | regla del punto medio (histórica) vs estricta (bid/ask exacto) + flag `complejo` |
| `flujo.py` | ¿Cómo se acumula? | neto del público por minuto, calls/puts separados, acumulados |
| `dealer.py` | Tabla de signos del dealer | también la usa `src/gex.py` |
| `veredicto.py` | ¿Qué signo del dealer sostiene el flujo medido, y con cuánto respaldo? | M1; usa `MIN_ABS` de `signo_medido` |
| `cruce.py` | ¿Cuándo llegó el precio al strike? (primer cruce / máxima aproximación) | M1 |
| `calendario.py` | ¿A qué hora cerró el mercado ese día? (cierres tempranos, tabla por año) | M3 |
| `descargas.py` | ¿Qué falta en caché para un rango de días, y cuánto cuesta? | M3; `asegurar_odte` |
| `toques.py` | Cuando el precio llegó a un strike, ¿aguantó o se cruzó? ¿Qué flujo medido había antes? | M2 |
| `constantes.py` | Dataset, raíz, caché, zona NY | |

### `scripts/odte/` (15 scripts): 13 de UN día y 2 de rango (M2)

| Grupo | Scripts |
|---|---|
| Exploración | `ver_definicion_0dte`, `ver_spx_1min`, `ver_trades_0dte`, `ver_costos_0dte` |
| Flujo en el tiempo | `ver_flujo_0dte`, `ver_apertura_0dte`, `ver_giro_0dte`, `ver_zoom_0dte` |
| Sesgos de la clasificación | `ver_sesgo_0dte`, `ver_paquete_0dte` |
| Por strike | `ver_strikes_0dte`, `antes_despues_0dte`, `caracterizar_strike_0dte` |
| Muestra (rango, M2) | `validar_0dte` (acumula en `data/validacion/odte_toques.csv`), `analizar_odte` ($0) |

### Tests

`test_catalogo`, `test_clasificacion`, `test_dealer`, `test_flujo`, `test_trades`, `test_precio_spx`,
`test_veredicto`, `test_cruce` (desde M1), `test_descargas` (desde M3, con un cliente de Databento falso), `test_toques` (desde M2). Cubren:
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
`ratio_flujo_oi` y `reverificar_walls` importan `clasificar_trades`, y varios también `parametros_tcbbo`
(pública desde M3; antes era la privada `_parametros_tcbbo`).

**Tipo de evidencia:** hasta M2 eran casos sueltos (29-sep, 2-oct, 14-oct). Desde M2 hay una muestra de varios
días (16 toques en 6 días, episodios = días, contra dos ingenuos), pero con 0 toques con signo medido: la
pregunta del signo quedó cerrada como "sin evidencia" (ver M2). La pregunta sin signo es M4.

**Resultado de Fase B que también aplica aquí:** con la regla estricta, entre 85% y 96% del volumen es
indeterminado y ~30% se imprime fuera del bid/ask (paquetes).

### Riesgos detectados

| # | Riesgo | Dónde | Efecto |
|---|---|---|---|
| R1 ✅ M1 | `clasificar_trades` tenía `estricto=False` (regla histórica) por defecto | `clasificacion.py` | Un script nuevo que olvide el flag usa la regla vieja sin avisar. Hoy `ver_flujo` y `ver_sesgo` lo omiten a propósito, para comparar. |
| R2 ✅ M3 | Horas fijas: vencimiento 16:00 y ES 09:30–15:59 | `catalogo.py`, `precio.py` | En días de cierre temprano (13:00: 2026-11-27, 2026-12-24) el vencimiento queda mal y la base sale de una barra sin actividad, sin que se note. |
| R3 ✅ | La caché del `tcbbo` dependía de la lista exacta de símbolos | `trades.py` | Pedir el mismo día con un rango de strikes un poco distinto vuelve a pagar datos que se solapan. **Pasó el 2026-11-04:** `signo_walls` con más archivos procesados elige otras series y sus 26 días quedan sin caché. |
| R4 ✅ M1 | El signo medido por strike se calculaba dentro de los scripts, solo con `MIN_ABS` | `ver_strikes_0dte`, `antes_despues_0dte` | Ignora `MIN_REL` y el % indeterminado: un "dealer −" puede apoyarse en el 10% del volumen. Choca con el contrato medido/supuesto. |
| R5 ✅ M3 | Cada descarga pedía su propia confirmación, con mensajes por stdout | `catalogo.py`, `precio.py`, `trades.py` | Un rango de N días pediría ~3N confirmaciones (CLAUDE.md lo prohíbe) y ensucia el stdout de los scripts. |

---

## 4. Mejoras propuestas

Orden aplicado: **M1 → M3** (M1 se hizo primero por un malentendido; la recomendación era M3 → M1). No quedó
inconsistente: M1 no descarga nada y M3 no toca el veredicto; el único cruce es que `corte_strike` recibe la
sesión de `spx_1min`, que desde M3 termina en la última barra real del día (12:59 en un cierre temprano).
Después de M3 se resolvió **R3** (caché por símbolo), porque M2 necesita rangos. Después, **M2** (cerrada: sin evidencia, estructural). Siguiente: **M4**. Orden recomendado original: **M3 → M1 → M2**. Sin la descarga de rango no se puede armar la muestra, y sin un veredicto
honesto la muestra mediría el 10% del volumen como si fuera todo.

| Id | Mejora | Resuelve | Estado |
|---|---|---|---|
| M3 | Descargas 0DTE con el patrón de `datos.py` | R5, R2 (R3 no) | **hecha** (2026-11-04) |
| M1 | Veredicto del signo medido en `src`, con el % indeterminado al lado | R4, R1 | **cerrada** (2026-11-04): peor caso se mantiene |
| M2 | De días sueltos a una muestra validada | evidencia anecdótica | **cerrada** (2026-11-04): sin evidencia, estructural |
| M4 | ¿Un nivel con más carga (OI, sin signo) aguanta más? | la pregunta de M2 sin necesitar el signo | diseño fijo (2026-11-09): dudas 1–3 resueltas, ES de los 30 días en caché; falta el script |

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
- R3 (caché atada a la lista exacta de símbolos) quedaba abierto y era el riesgo más caro: resuelto después,
  ver **R3: caché por símbolo**.

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

**Criterio del signo: CERRADO, el peor caso se mantiene** (2026-11-04). Quedaba abierto si era demasiado
exigente y convenía pedir que el neto superara solo una FRACCIÓN del volumen sin firmar. No se relaja,
porque el neto firmado es una fracción mínima de lo indeterminado. Razón `|neto| / indeterminado` por strike,
día completo, en las mismas corridas de M1:
| Día (strikes) | mediana | máximo | > 100% | > 50% | > 25% | > 10% | > 5% |
|---|---|---|---|---|---|---|---|
| 10-12 (25) | 0,080 | 0,18 | 0 | 0 | 0 | 8 | 15 |
| 10-14 (25) | 0,039 | 0,56 | 0 | 1 | 1 | 1 | 6 |

Para obtener signos en una parte relevante de los strikes habría que bajar el umbral al 5–10% del
indeterminado. Eso no sería un criterio sino elegir la respuesta. La muestra de M2 da lo mismo antes
del toque (mediana 0,035, máximo 0,40). Conclusión: **con la regla de cotización, el agresor no es
identificable en el intradía 0DTE**; el veredicto "indet. domina" es la respuesta correcta, no un
exceso de exigencia. `veredicto.py` no cambia.

**Propuesta original:**
- Una función (en `src/odte` o reutilizando `src/signo_medido`) que devuelva el signo del dealer junto con la
  fracción de volumen que lo respalda, y que diga "sin evidencia" cuando el indeterminado domina.
- Llevar `corte_strike` (primer cruce / máxima aproximación) a `src`, con tests.
- Revisar R1: hacer explícita la regla en cada llamada o cambiar el valor por defecto de forma deliberada.

### R3: caché por símbolo — HECHA

**Qué se hizo** (`src/odte/trades.py`):
- Un símbolo está cubierto para (día, franja) si aparece en algún archivo de ese día cuya franja contiene la
  pedida. `asegurar_tcbbo` solo cotiza y descarga los no cubiertos, en un archivo nuevo.
- Cada archivo nuevo lleva un `.json` con los símbolos PEDIDOS: un símbolo sin trades queda cubierto.
- Archivos viejos (sin `.json`): cubren los símbolos que aparecen en ellos, y todos los de su pedido original
  si se pide exactamente la misma lista (md5). Un símbolo sin trades de un archivo viejo, dentro de otra lista,
  se vuelve a pedir (no tiene datos: cuesta ~$0).
- `leer_tcbbo(fecha, símbolos, desde, hasta)` lee SOLO de caché: cada símbolo de UN archivo (sin duplicados),
  recortado a la franja y ordenado por tiempo; si falta algo, grita. `plan_tcbbo` dice de dónde sale cada uno.
- `b2_flujo`, `signo_walls`, `medir_niveles` y `ver_zoom_0dte` leen con `leer_tcbbo` (ya no con la ruta exacta).
- Corregido de paso: `asegurar_descargas` crea la carpeta antes de `procesar` (el `.json` fallaba sin ella).

**Verificación ($0):** stdout idéntico en 7 scripts (la única diferencia: `ver_zoom` ya no imprime `[caché]`).
Cero descargas y cero cotizaciones. 10 tests nuevos con archivos "viejos" y un cliente falso.

**Efecto en `signo_walls`** (data/procesado hasta 11-03, 26 días de flujo, 653 series):
| | día-serie | sin caché |
|---|---|---|
| Antes de R3 | 11.381 | 11.381 (100%) |
| Después de R3 | 11.381 | 5.672 (50%) |

De lo que falta: 2.647 son los 9 días nuevos (10-21..11-02), nunca descargados. Unos 3.000 son de los días
viejos: series que la nueva selección agrega más símbolos sin trades de los archivos viejos (no se pueden
distinguir; estos cuestan ~$0). El costo real se ve con `python scripts/signo_walls.py --solo-costo`.

### M2: muestra validada — CERRADA: sin evidencia, estructural (2026-11-04)

**Qué se hizo:**
- `src/odte/toques.py`: `Definicion` (los 5 parámetros, con `etiqueta()` estable), `niveles`, `primer_toque`,
  `toques` (precio: toque, lado, resultado) y `flujo_previo` (flujo MEDIDO antes del toque + veredicto de M1).
  18 tests en `tests/test_toques.py`.
- `scripts/odte/validar_0dte.py INICIO FIN [--solo-cache | --solo-costo] [--sin F1,F2] [--paso --tol --desde
  --ventana --margen]`: como mucho DOS confirmaciones para todo el rango: 1) catálogo + ES; 2) tcbbo **solo de
  los strikes tocados** (se conocen recién con el ES, por eso no usa `asegurar_odte`, que pide todos los
  strikes de una ventana). Acumula en `data/validacion/odte_toques.csv`, separado de los de GEX; cada corrida
  reemplaza sus filas (fecha, definición), así que varias definiciones conviven en el mismo CSV sin mezclarse.
- `scripts/odte/analizar_odte.py [definición]`: $0. Episodios = días; la prueba "dealer + → aguanta,
  dealer − → cruza" solo sobre toques con signo medido, contra los dos ingenuos en esos mismos toques;
  menos de 10 días con signo = "NO es evidencia".

#### Definiciones (vigente y alternativas a analizar con la muestra)

Todo se mide con **cierres de barras de 1 min** del SPX estimado (ES − base). Índice = inicio de la barra, hora NY.

| Concepto | Definición vigente (`p25_t2_d1000_v30_m5`) | Alternativas a probar | Por qué importa |
|---|---|---|---|
| **Nivel** | strikes múltiplos de **25** | 5 (todos los strikes); 50; solo los gamma walls del día anterior | 25 reduce niveles pegados (correlacionados) y abarata el tcbbo; 5 da más toques pero muy dependientes entre sí |
| **Toque** | primera barra desde las **10:00** cuyo cierre queda a **≤ 2 pts** del strike, o salta al otro lado, viniendo de **fuera** de la banda (barra anterior a > 2 pts) | tolerancia 1 / 3 pts; desde 09:45 / 10:30; usar máximo/mínimo de la barra en vez del cierre; todos los toques del día, no solo el primero | 10:00 evita el ruido de la apertura; "viniendo de fuera" evita contar como toque un precio que ya estaba encima del strike |
| **Lado** | el lado de la barra anterior al toque (`arriba` = venía de arriba, el strike actúa como soporte) | — | separa soporte de techo |
| **Resultado** | en las **30** barras desde la del toque (incluida), si algún cierre pasa el strike hacia el otro lado por **> 5 pts** → `cruzó`; si no → `aguantó`. Sesión que termina antes → `ventana corta` (fuera de la muestra) | ventana 15 / 60 min o hasta el cierre; margen 3 / 10 pts; margen proporcional al rango del día | define qué es "aguantar"; con margen chico, el ruido de 1 min cuenta como cruce |
| **Flujo medido** | trades del strike (calls + puts) desde las 09:30 hasta **antes** del inicio de la barra del toque, regla estricta | solo los últimos 30/60 min antes del toque; calls y puts por separado contra la nula | el flujo posterior no puede explicar el toque (orden temporal, fundamento 6) |
| **Signo** | `veredicto.signo_dealer`: \|neto\| ≥ 200 **y** \|neto\| > indeterminado (peor caso) | criterio menos exigente: \|neto\| > una fracción del indeterminado (descartado en el cierre de M1: el peor caso se mantiene) | hoy es el cuello de botella: ver resultado |
| **Hipótesis** | dealer + (largo de gamma) → aguanta; dealer − (corto) → se cruza | — | |
| **Ingenuos** | a) frecuencia base (siempre el resultado más común); b) recorrido: aguanta si `dist_previa` (\|SPX − K\| 30 min antes) > mediana | distancia a la apertura; rango de la primera hora | el signo tiene que ganarles en los MISMOS toques |
| **Episodio** | el día (los toques de un día comparten régimen y flujo) | rachas del mismo signo medido dentro del día | tamaño honesto de la muestra = días |

Una definición nueva se corre con las opciones del script; queda en el CSV con su propia `definicion` y se
analiza aparte (`analizar_odte.py <etiqueta>`). Cambiar paso o tolerancia cambia los strikes tocados, y
eso puede pedir tcbbo nuevo; las demás opciones reusan la caché.

**Primera corrida ($0, `--solo-cache`, 09-24..10-19):** 6 días medidos (09-29, 10-12, 10-14, 10-15, 10-16 y
10-19); 4 días saltados por falta de tcbbo de los strikes tocados (10-02, 10-05, 10-06, 10-13); 8 sin
catálogo/ES.
| | toques | días |
|---|---|---|
| Total | 16 (8 aguantó, 8 cruzó) | 6 |
| Con signo medido | **0** | 0 |
| `indet. domina` | 13 (mediana 44,5% indet.) | 5 |
| `sin evidencia` | 3 | 2 |

La prueba no se puede hacer: ningún toque pasa el veredicto. Es lo mismo que mostró M1, ahora en una
muestra. Referencia: la frecuencia base es 50% y el ingenuo de recorrido acierta 38% (peor que la moneda).

#### Cierre: por qué el resultado es estructural y no falta de muestra

Evidencia en `data/validacion/odte_toques.csv` (columnas `indet_*` y `neto_inferido_interior`, de
`toques.flujo_previo` + `clasificacion.ubicar_trades`); se reproduce con `analizar_odte.py`, sección
"Por qué no hay signo". 16 toques, flujo antes del toque:
| Medida | Valor |
|---|---|
| \|neto\| / indeterminado | mediana **0,035**, máximo 0,40 (el peor caso exige > 1) |
| Toques que pasarían con umbral 50% / 25% / 10% / 5% del indet. | 0 / 1 / 2 / 6 |
| Indet. en el punto medio exacto (ninguna regla de bid/ask lo firma) | mediana 44% (28–59%) |
| Indet. en el interior del spread | mediana 49% (40–60%) |
| Indet. fuera del spread (paquetes) | mediana 9% (1–19%) |
| Signo del neto estricto = signo del interior firmado por cercanía (INFERIDO) | **9 de 16** |
| Veredicto con el interior firmado por cercanía (INFERIDO) | 1 "+", 11 indet. domina, 4 sin evidencia |

Lectura:
- El neto firmado es ~4% de lo que no se puede firmar. Ningún umbral defendible lo convierte en signo
  (ver el cierre de M1).
- Casi la mitad de lo indeterminado está en el punto medio exacto: no lo firma ninguna regla de cotización.
- Firmar el interior por cercanía no rescata la medición: el signo cambia en 7 de 16 toques según la
  regla, así que **depende de la regla, no del mercado**. Y aun así solo 1 toque pasa el veredicto.
- Es el mismo hallazgo de Fase B (85–96% indeterminado en las walls, `signo_walls`), ahora en el
  intradía 0DTE. **Con OPRA tcbbo y reglas de cotización, el agresor (y con él el signo del dealer) no
  es identificable, ni en el plazo medio ni en el intradía.**

Además, aunque un signo pasara: el flujo intradía es un CAMBIO de inventario, no su nivel (la posición
que el dealer traía no se mide), y "el dealer es la contraparte" es un supuesto (fundamento 4).

**Qué sobrevive:** el lado del precio de `toques.py` (`Definicion`, `toques`: toque, lado, resultado), que
no depende del signo y es la base de **M4**; y los volúmenes medidos sin signo (compra + venta + indet).

**Qué se archiva:** la prueba "dealer + → aguanta / dealer − → cruza" y ampliar esta muestra con tcbbo.
**No se recomienda** pagar el paso 2 de `validar_0dte` para eso: solo confirmaría el "sin evidencia".
(`--solo-costo` no se probó con la clave real.)

**Siguiente (M4, propuesta):** cambiar la pregunta en vez del umbral: ¿un nivel con más carga (OI medido sin
signo; gamma bruta como MODELO) aguanta más? Antes de correrla hay que dejar escrito el diseño
fijo y resolver tres dudas: de dónde sale el OI 0DTE sin mirar al futuro, cuántos días alcanzan con la
caché, y el error de la base ES − SPX frente a la tolerancia de 2 pts.

**Propuesta original:**
- Un script de rango (`validar_0dte`) que mida algo fijo por día, por ejemplo el flujo estricto antes de tocar el
  nivel frente a si el nivel aguantó o se cruzó.
- Acumulador CSV propio, separado de los de GEX.
- Análisis por **episodios** y comparación contra un predictor ingenuo (la frecuencia base con la que aguanta el
  strike más cercano).

### M4: ¿un nivel con más carga aguanta más? — PROPUESTA (sin código)

**Pregunta:** sin signo. ¿Un nivel con más carga aguanta más el toque que uno con poca carga?

**Borrador del diseño** (aún no es el diseño fijo):
- **Carga** = OI de mediano plazo por zona de 25 puntos, de `walls.zonas_dia`: `oi_c` / `oi_p` / `oi_total`
  (MEDIDO) y `gex_bruto` (MODELO, sin signo). Zonas `round(strike/25)*25`, los mismos múltiplos que usa
  `toques.py`. **No** usar `gamma_walls`, porque depende del signo supuesto.
- **Reacción** = `toques.py` con la definición vigente (`p25_t2_d1000_v30_m5`), sobre el ES 1-min del día d.
- **Sin mirar al futuro:** de la foto procesada de d solo vale `open_interest` (= cierre de d−1, conocido en la
  mañana de d). S, IV y gamma de esa foto son del cierre de d, así que la gamma bruta sale de la foto de d−1,
  sin las series que vencen en d. Así ninguna de las dos cargas incluye la 0DTE (la foto de d ya la excluye
  por T>0, `gex.py:91`).
- Por qué se excluye la 0DTE: no porque su gamma sea ~0 (cerca del precio crece como 1/√T), sino porque su OI
  de la mañana es chico (~1,5–3,5k por strike, frente a 50k–600k por zona) y la carga 0DTE se arma intradía.
  **Decisión del usuario (2026-11-09): el 0DTE NO se agrega a la cadena procesada.** Se midió con la caída
  del 11-05. Al cierre del 11-04, las series que vencían el 11-05 eran el 0,7% del OI y el 2% de la gamma
  bruta (MODELO). El OI 0DTE publicado a las 06:30 del 11-05 fue de 371k contratos en 518 series: 5–17k por
  zona de 25, frente a cargas de 65k–545k. Aporta muy poco; no volver a proponerlo sin evidencia nueva.
- **Riesgos que el diseño tiene que fijar:** un ingenuo "múltiplo de 100" (los números redondos podrían
  aguantar sin importar la carga); usar la carga RELATIVA dentro del día; zonas repetidas entre días por
  rotación (no son independientes); `pct_puts` solo como descriptivo.

**Dudas pendientes** (resolver en este orden: 1 → 3 → 2; explicar antes de ejecutar):

| # | Duda | Cómo se resuelve | Costo | Estado |
|---|---|---|---|---|
| 1 | ¿El OI usado ya se conocía antes del toque? ¿La carga varía entre las zonas tocadas? | Leer en el `statistics` crudo la fecha y hora del registro de OI (stat_type 9): ¿se publica antes de las 9:30 de d? Y comparar la carga de las zonas tocadas: si todas tienen una carga parecida, la pregunta no puede discriminar | $0 (caché) | **resuelta** (2026-11-06): el OI se conoce antes; la carga varía pero ≈ redondez (ver abajo) |
| 3 | ¿La base ES − SPX tiene un error menor que la tolerancia del toque (2 pts)? | Comparar el high y el low diario del SPX estimado (ES − base) con los de yfinance | $0 | **resuelta** (2026-11-06): con la base de cierre NO (40% de los minutos > 2 pts); con la base móvil sí (0,3%). Ver abajo |
| 2 | ¿Cuántos días alcanzan? | Inventario: días con foto de d, foto de d−1, SPX 5m y ES 1-min | $0,0988 (ES de 20 días, `get_cost`); la descarga la corre el usuario | **resuelta** (2026-11-09): 30 días posibles (ver abajo) |

#### Duda 1, resultado (2026-11-06, $0)

**1a, tiempo del OI.** En los 58 `statistics` crudos del 09-24 al 11-04 (SPX y SPXW), todos los registros de
OI (stat_type 9) llegan a las **06:30:00–06:30:04 ET del día d**: el 100% antes de las 9:30. Hay un solo
registro por símbolo y ninguno se revisa durante el día. `ts_ref` viene vacío, así que el registro no dice a qué
fecha se refiere; que sea el cierre de d−1 sigue apoyado en la regla de `inventario` (con tests). Conclusión:
la carga se conoce tres horas antes de la apertura y antes de cualquier toque (cuentan desde las 10:00). El
diseño no cambia.

**1b, ¿varía la carga entre las zonas tocadas?** Cruce de los 16 toques de M2 con la foto de cada día: OI
(MEDIDO) de la foto de d y gamma bruta (MODELO) de la foto de d−1, sin las series que vencen en d. El percentil
se calcula entre las zonas de 25 a ±250 pts del cierre de d−1.

| Clase de redondez | Toques | OI total de la zona | Percentil del OI | Resultado |
|---|---|---|---|---|
| múltiplo de 100 (7700, 7800) | 5 | 409k–505k | 90–100 | 1 aguantó / 4 cruzaron (7700 cruzó las 4) |
| múltiplo de 50 (7650, 7750) | 5 | 230k–300k | 75–80 | 4 aguantaron / 1 cruzó |
| múltiplo de 25 (7675, 7725) | 6 | 117k–156k | 35–45 | 3 / 3 |

- La carga varía 4,3x entre los toques, pero **casi toda la variación es redondez**: dentro de cada clase
  varía ~1,3x. Con esta muestra, "más carga" y "nivel más redondo" son la misma variable. Se confirma el
  riesgo del ingenuo "múltiplo de 100".
- Solo hay 6 zonas distintas (7700 y 7725 aparecen 4 veces cada una), y ningún toque cerca de 8000 (~2,2M).
- Solo como descripción, sin valor de resultado (6 episodios, carga confundida con redondez): la mediana de
  carga de los toques que cruzaron (345k) es mayor que la de los que aguantaron (253k).

**Consecuencia para el diseño: hay que estratificar por redondez (100 / 50 / 25).** La pregunta pasa a ser
"dentro de la misma clase, ¿la zona con más carga aguanta más?", y "¿la carga suma algo por encima del ingenuo
múltiplo de 100?". Para eso la muestra necesita niveles de la misma clase con cargas distintas (7700 vs 7800 vs
8000), lo que solo llega con más días en los que el precio recorra otras zonas: la duda 2 pesa más que antes.
Los walls con signo pueden entrar como un predictor más, rotulado SUPUESTO, pero tampoco escapan de esto:
también se concentran en los múltiplos de 100.

#### Duda 3, resultado y arreglo (2026-11-06, $0)

**Diagnóstico.** La base original es constante en el día: cierre del ES (barra 15:59) menos el cierre oficial
del SPX. Contra el SPX de 5 min de yfinance, en los 10 días con ES, el error es un **sesgo casi constante por
día** (−4,8 pts el 10-05, −4,3 el 10-14) y no ruido. Tiene dos causas:
1. El cierre oficial incluye el salto de la subasta (hasta −2,55 pts frente al último precio intradía, 10-14).
2. La base se mueve en el día (el 10-05 pasó de 50,9 a 57,0 entre las 9:35 y las 15:55).

**Arreglo** (`precio.py`):
- `cachear_spx_intradia` cachea el SPX de yfinance en `data/raw/spx_yf_{5m,1m}_FECHA.parquet`. Es gratis.
  `leer_spx_yf` lee solo de caché y grita si falta el archivo o si la sesión está incompleta.
- `base_movil` mide ES − SPX en el cierre de cada barra de 5 min y lo interpola a 1 min.
- `spx_1min(fecha, metodo_base="movil")` usa la base nueva. **El valor por defecto sigue siendo `"cierre"`**: M2
  y los scripts no cambian (stdout idéntico verificado en `ver_spx_1min`). M4 usa `"movil"`.

Ya está cacheado: 5m del 09-24 al 11-05 (31 días) y 1m del 10-08 al 11-05 (21 días), todos completos (78 y
390 barras). **Riesgo:** yfinance guarda solo 60 días de 5m y 30 de 1m. Los días nuevos hay que cachearlos
antes de que salgan de esa ventana; el 09-23 y anteriores ya no se pueden recuperar.

**Medición** (SPX estimado − SPX real, en pts):

| Prueba | Base | Sesgo | Mediana \|err\| | p95 | Máx | > 1 pt | > 2 pts |
|---|---|---|---|---|---|---|---|
| Contra el SPX de 1 min (6 días; verdad independiente: la base móvil usa solo los puntos de 5 min) | cierre | −1,26 | 1,51 | 4,54 | 5,54 | 59,9% | **40,0%** |
| | mediana del día (5m) | +0,06 | 0,30 | 1,07 | 4,83 | 6,5% | 0,6% |
| | **móvil (5m)** | +0,05 | **0,20** | **0,91** | 4,10 | 3,9% | **0,3%** |
| Validación cruzada en 5 min (10 días; base con la mitad de los puntos, error en la otra mitad) | cierre | −1,85 | 1,94 | 4,99 | 5,76 | 71,5% | 49,2% |
| | mediana del día | 0,00 | 0,32 | 1,06 | 4,58 | 5,4% | 0,5% |
| | **móvil** | −0,02 | **0,28** | 1,04 | 4,27 | 6,2% | 0,5% |

- El cierre de 5m y el de 1m de yfinance coinciden exactamente en el mismo instante (máx 0,0000 en 6 días).
- La base móvil quita el sesgo diario y deja el error en ~0,2 pts de mediana: unas 10 veces por debajo de la
  tolerancia de 2 pts. Frente a la mediana del día gana poco, pero sigue la deriva (10-05).
- **Efecto en los toques** (definición vigente, los 10 días con ES): de 24 toques, 5 quedan iguales, 12
  cambian de hora, **4 cambian de resultado** (todos de "aguantó" a "cruzó": 10-05 7750, 10-14 7725 y 7750,
  10-19 7725) y **3 desaparecen** (09-29 7650, 10-02 7700, 10-05 7725). La muestra de M2 estaba medida con
  la base sesgada. No cambia el cierre de M2 (que se apoya en el signo), pero M4 tiene que medirse con la base
  móvil.

#### Duda 2, resultado (2026-11-09, $0)

Fotos procesadas: 31 días (09-24..11-06, sin 10-20). Se descartan el 09-24, que no tiene foto de d−1, y
ningún otro: el 11-06 tenía el SPX de yfinance pendiente y se cacheó gratis (78 y 390 barras, completos).
- **30 días** tienen foto de d, foto de d−1 y SPX 5m (09-25..11-06, sin 10-20).
- 10 ya tienen ES. Faltan 20, que cuestan **$0,0988** según `get_cost` (cotizado con `solo_costo=True`, sin
  descargar): 09-25, 09-28, 09-30, 10-01, 10-07, 10-08, 10-09, 10-21..10-23, 10-26..10-30 y 11-02..11-06.
- Siguen siendo menos de los 40 deseados. Cada día nuevo cuesta foto (~$0,66) + ES (~$0,005). Para atrás
  no se puede ampliar: yfinance ya no tiene el 5m.
- **Caso especial 10-21:** su foto de d−1 es la del 10-19 (el 10-20 falta en Databento). El OI (foto del
  10-21) está bien; la gamma bruta (MODELO) sale de una foto dos sesiones vieja. Hay que marcarlo o excluirlo.
- La ventana incluye la caída del 11-05 (−335 pts) y el rango 7.350–7.820: aparecen niveles de la misma clase
  con cargas distintas (7400 vs 7500 vs 7600 vs 7700), que es lo que pedía la duda 1.

#### Diseño fijo de M4 (2026-11-09, antes de correr nada)

Con las tres dudas resueltas y las dos decisiones pendientes tomadas por el usuario (según la recomendación),
este es el diseño. Cambiarlo después de ver resultados es elegir la respuesta: cualquier variante va con su
propia etiqueta, al lado de esta y sin reemplazarla.

| Concepto | Definición fija |
|---|---|
| **Muestra** | Días con foto de d, foto de d−1, SPX 5m y ES 1-min: hasta 30 (09-25..11-06, sin 10-20). El **10-21** lleva `d1_vieja=True` (su foto de d−1 es la del 10-19) y se reporta con y sin él |
| **Zona** | `round(strike/25)*25`, los mismos múltiplos que usa `toques.py` |
| **Clase de redondez** | `100` / `50` / `25` (múltiplo de 100; de 50 pero no de 100; el resto) |
| **Carga MEDIDA** | `oi_total` (y `oi_c`, `oi_p`) de la zona en la foto de d (`walls.zonas_dia`): OI al cierre de d−1, publicado a las 06:30 de d |
| **Carga MODELO** | `gex_bruto` de la zona en la foto de d−1, **sin** las series que vencen en d. Sin signo |
| **Carga relativa** | percentil de la carga de la zona **dentro de su clase**, entre las zonas a ±250 pts del cierre de d−1, ese día. La pregunta se hace con esta, no con la carga absoluta |
| **Toque y resultado** | `toques.py`, definición vigente `p25_t2_d1000_v30_m5`, sobre `spx_1min(fecha, metodo_base="movil")`. `ventana corta` queda fuera de la muestra |
| **Pregunta principal** | dentro de cada clase, ¿los toques en zonas de carga relativa alta (≥ mediana de la clase) aguantan más que los de carga baja? Se reporta la tasa de `aguantó` por clase × mitad de carga, con n de toques, días y zonas en cada celda |
| **Ingenuos** (la carga tiene que ganarles en los MISMOS toques) | a) frecuencia base; b) "múltiplo de 100 aguanta"; c) distancia previa (\|SPX − K\| 30 min antes del toque > mediana) |
| **Episodio** | el día. Tamaño honesto = días con al menos un toque en la celda. Con menos de 10 días en una celda: "NO es evidencia" |
| **Control por zona** (decisión 1) | las mismas zonas se repiten entre días por rotación. Además del análisis por día: a) cada zona vota una vez (tasa de aguante por zona, después promedio); b) dejar una zona fuera: se quita cada zona y se recalcula. Si el resultado cambia de signo al quitar una zona, se reporta como "depende de la zona X". Siempre se informa el nº de zonas distintas |
| **Wall SUPUESTO** (decisión 2) | columna `gex_sup` = GEX neto de la zona en la foto de d−1 (hipótesis nula; misma exclusión de lo que vence en d) y `es_wall_sup` = la zona está entre las top-5 por \|gex\| ese día. Es un predictor **más**, evaluado aparte contra los mismos ingenuos y rotulado SUPUESTO en el CSV y en la salida. **Nunca** se combina con la carga en un solo número |
| **`pct_puts`** | solo descriptivo |
| **Acumulador** | `data/validacion/odte_carga.csv`, separado de `odte_toques.csv` y de los CSV de GEX. Una fila por toque, con columna `definicion`. Cada columna clasificada como medido / modelo / supuesto (como `walls.clase`), con un test que lo exija |
| **Costo** | $0: solo fotos procesadas, ES, SPX de yfinance y `toques.py`. **Sin tcbbo** |

#### Próxima sesión: por dónde seguir (anotado 2026-11-06)

**Estado de los datos al 2026-11-06:**

| Dato | Qué hay en caché | Para qué lo usa M4 |
|---|---|---|
| Fotos procesadas (`data/procesado/`) | 31 días, 09-24..11-06, sin 10-20 (Databento no tiene datos ese día). Actualizado 2026-11-09 | carga: OI de la foto de d, gamma bruta de la foto de d−1 |
| `statistics` crudo | hasta 11-06 (SPX y SPXW) | procesar fotos nuevas a $0 si también está el `ohlcv-1d` |
| ES 1 min | 30 días, 09-25..11-06 (sin 10-20); bajado el 2026-11-09 | el toque y su resultado |
| SPX yfinance | 5m del 09-24 al 11-06; 1m del 10-08 al 11-06 | base móvil (necesita el 5m del día) |
| tcbbo | — | **M4 no lo necesita** (es sin signo): no hay que pagar tcbbo |

**Pasos, en orden** (explicar cada uno antes de ejecutarlo; las descargas las corre el usuario):
1. **Duda 2, inventario y costo ($0).** Listar los días que tienen a la vez la foto de d, la foto de d−1, el
   SPX 5m y el ES. Sacar el costo exacto del ES que falta con
   `datos.asegurar_descargas(precio.pedidos_es(fechas), "ES 1-min", solo_costo=True)`. La estimación era
   ~18 días por ~$0,10. Sin ES, el día no entra.
2. **Decidir si se amplía la ventana.** Con ~27 días seguimos por debajo de los 40 deseados, y la duda 1 pide
   días en los que el precio recorra **niveles distintos de la misma clase** (7700 vs 7800 vs 8000).
   - Para adelante: el 11-04 ya tiene `statistics` y `ohlcv-1d` (SPX y SPXW) en caché, así que su foto sale a
     $0 con `walls_tiempo`. Desde el 11-05, cada día nuevo cuesta foto (~$0,66) + ES. Cachear su SPX de
     yfinance antes de 60 días.
   - Para atrás (antes del 09-24): **no se puede**, porque yfinance ya no tiene el 5m y sin él no hay base móvil.
3. **Escribir aquí el diseño fijo de M4**, antes de correr nada. Puntos ya decididos:
   - carga MEDIDA (`oi_total`, foto de d) y MODELO (`gex_bruto`, foto de d−1 sin las series que vencen en d);
   - estratificar por clase de redondez (100 / 50 / 25) y usar la carga relativa dentro de la clase y del día;
   - toques con `spx_1min(..., metodo_base="movil")` y la definición vigente `p25_t2_d1000_v30_m5`;
   - episodio = día;
   - ingenuos: frecuencia base, "múltiplo de 100" y distancia previa.

   Decidido el 2026-11-09 (ver "Diseño fijo de M4"): las zonas repetidas se controlan con un voto por zona y
   dejando una zona fuera; el wall con signo entra como predictor aparte, rotulado SUPUESTO.
4. Recién entonces: el script de M4 (acumulador propio, separado de `odte_toques.csv`), los tests y la corrida.

---

## 5. Bitácora

| Fecha | Cambio | Commit | Resultado / números |
|---|---|---|---|
| 2026-11-04 | Revisión inicial y creación de este archivo. Antes: `spxw-raices` fusionada a `main` (fast-forward a `48d7433`); el trabajo 0DTE sigue en la rama `odte-mejoras` | `2ca92b5` | 345 líneas en `src/odte`, 13 scripts, 6 tests; riesgos R1–R5; mejoras M1–M3 pendientes |
| 2026-11-04 | M1: `veredicto.py` y `cruce.py` en `src/odte`; `estricto` obligatorio; `ver_strikes` y `antes_despues` con `%indet` | `021973f` | 193 tests (27 nuevos); netos idénticos; con el peor caso, 0 strikes con signo en 10-12 y 10-14 (antes 23 y 23) |
| 2026-11-04 | M3: `asegurar_descargas` (datos), `asegurar_tcbbo`, `asegurar_odte`, `calendario`; 3 scripts sin descarga copiada; mensajes a stderr | `55092e5` | 206 tests (13 nuevos); stdout idéntico en 8 scripts salvo `[caché]`; rango 0DTE = como mucho 2 confirmaciones (antes ~3 por día) |
| 2026-11-04 | R3: caché tcbbo por símbolo (`plan_tcbbo`, `leer_tcbbo`, `.json` de pedidos); 4 scripts leen con `leer_tcbbo` | `f599886` | 216 tests (10 nuevos); stdout idéntico en 7 scripts; `signo_walls` pasa de 100% a 50% día-serie sin caché |
| 2026-11-04 | M2: `toques.py` (definición del toque y del resultado, flujo previo), `validar_0dte` (rango, 2 confirmaciones, tcbbo solo de strikes tocados), `analizar_odte`; definiciones y alternativas en la sección M2 | `0a31d46` | 18 tests nuevos; 1ª corrida $0: 16 toques en 6 días, 8 aguantó / 8 cruzó, **0 con signo medido** (13 indet. domina, 3 sin evidencia) |
| 2026-11-04 | Cierre de M1: el criterio del peor caso se mantiene (pendiente resuelto con la razón \|neto\|/indet) | `50518ac` | 10-12: mediana 0,080, máx 0,18; 10-14: mediana 0,039, máx 0,56; 0 de 50 strikes > 100%, 1 > 50% |
| 2026-11-04 | Cierre de M2: `ubicar_trades` (dónde se imprimió cada trade), descomposición del indet. y neto INFERIDO del interior en `flujo_previo`; sección "Por qué no hay signo" en `analizar_odte`; CSV regenerado ($0) | `8b1da5d` | 245 tests (11 nuevos); \|neto\|/indet mediana 0,035; indet. 44% en el medio exacto, 49% interior, 9% fuera; el signo cambia con la regla en 7 de 16; con interior inferido 1 de 16 con signo |
| 2026-11-06 | Coherencia de ODTE.md: §3 (tipo de evidencia tras M2, `parametros_tcbbo` pública), fila "Signo" de M2 (la alternativa quedó descartada en el cierre de M1), hashes en la bitácora; sección M4 con el borrador del diseño y las 3 dudas pendientes (1 → 3 → 2) | `a63d13d` | sin código; M4 sigue en propuesta |
| 2026-11-06 | M4, dudas 1 y 3: el OI se publica 06:30 ET de d; la carga de las zonas tocadas ≈ redondez (estratificar 100/50/25); `precio.py`: caché del SPX intradía de yfinance y `spx_1min(metodo_base="movil")` (por defecto sigue `"cierre"`) | `a9027b0` | 253 tests (8 nuevos); error vs SPX 1 min: > 2 pts del 40,0% al 0,3%, mediana \|err\| de 1,51 a 0,20; de 24 toques, 4 cambian de resultado y 3 desaparecen |
| 2026-11-09 | M4: duda 2 (inventario: 30 días posibles, ES de 20 días $0,0988 por `get_cost`), diseño fijo (carga relativa dentro de la clase de redondez, ingenuos, control por zona, wall SUPUESTO como predictor aparte, acumulador `odte_carga.csv`); decisión de no agregar el 0DTE a la cadena procesada (también en CLAUDE.md). Rama `m4-diseno` | `9a94545` | sin código |
| 2026-11-09 | ES de los 30 días en caché (la descarga terminó después del commit anterior) | (este commit) | muestra de M4 completa: 30 días, $0 de aquí en adelante |
