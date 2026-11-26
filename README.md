# backtester

Herramientas de investigación sobre opciones del SPX:

- **GEX (gamma exposure) y gamma walls** a partir de la cadena de opciones de cierre de cada día (SPX mensuales y SPXW diarias/semanales).
- **Evolución de los walls**: cuánto OI carga cada zona y por qué cambia su GEX de un día a otro.
- **Fase B, signo del dealer supuesto contra medido**: cuánto del signo de cada wall es supuesto y cuánto se puede medir con el flujo.
- **Medidas sin signo**: el rango que el mercado espera (straddle ATM) y la gamma recalculada en otro precio y otra hora.
- **Estudio 0DTE**: el flujo intradía de las SPXW que vencen el mismo día.

Datos: [Databento](https://databento.com) (opciones OPRA y futuros ES de CME) y yfinance (el SPX diario e intradía).

El código, los comentarios y los commits están en español. `CLAUDE.md` tiene la guía completa de la arquitectura y las decisiones. `ODTE.md` tiene el estado y la bitácora del módulo 0DTE.

## Qué se sabe hasta ahora (2026-11-25)

Cada número del proyecto lleva su clase (ver [Clases de números](#clases-de-números)). Ninguna conclusión mezcla lo supuesto con lo medido.

| Pregunta | Resultado | Estado |
|---|---|---|
| ¿Se puede medir el signo del dealer en los walls? (Fase B, `signo_walls`) | Entre el 98% y el 99,9% del signo de los walls es **supuesto**. Con la regla estricta, las 10 celdas zona × tipo dan "demasiado chico": entre el 85% y el 96% del volumen queda indeterminado | cerrada |
| ¿Se puede medir el signo intradía en 0DTE? (M1, M2) | No: con OPRA tcbbo y reglas de cotización el agresor no es identificable | cerradas, sin evidencia |
| ¿Una zona con más OI aguanta más el toque? (M4) | `radio250`: la carga acierta 45%, contra 66% de la frecuencia base. `tocadas`: solo 20 toques | cerrada, sin evidencia |
| ¿El GEX de la víspera anticipa el rango del día siguiente? (`validar_gex`) | Los dos métodos salen parejos. El GEX con signo ordena los días más o menos como el straddle, pero no tiene escala | orientativo |
| ¿El straddle ATM anticipa el rango siguiente mejor que el rango de hoy? (`validar_rango`, 31 días) | Error medio 0,424 contra 0,544, pero error mediano 0,281 contra 0,272. Gana 16 de 31 días: la ventaja está en los días grandes | orientativo, no evidencia |
| ¿Se puede recalcular la gamma en otro precio? (`verificar_gamma`, 29 pares) | Error mediano por zona 3,5%, contra 14,0% de usar la foto vieja. Con movimientos de 1% o más: 6,4% contra 26,4% | verificado hasta −1,92% / +1,31% |
| ¿La gamma bruta en el precio actual anticipa el rango de los 30 min siguientes? (`validar_gamma_local`) | Una vez descontado el nivel del SPX, a la gamma le queda +0,07 | sin evidencia |

## Instalación

Requiere Python 3.13, la versión con la que se desarrolla.

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt      # requirements.txt está en UTF-16
```

La API key de Databento se lee de la variable de entorno y nunca va en el código:

```powershell
$env:DATABENTO_API_KEY = "db-tu-clave"
$env:PYTHONIOENCODING = "utf-8"       # la salida de los scripts usa Δ, ±, etc.
```

Sin la variable, `config.py` lanza un error al importarse. Los paneles no la necesitan.

## Costo y caché

Databento cobra cada descarga. Todo el proyecto sigue la misma regla:

1. **Caché primero.** Cada descarga se guarda como parquet en `data/raw/` (no se versiona). Si el archivo ya existe, no se vuelve a pagar.
2. **Costo antes de bajar.** Si falta algo, se suma el costo de todo lo pendiente con `metadata.get_cost` y se pide **una** confirmación `s/n` por el total.

Todo pasa por `datos.asegurar_descargas(pedidos, descripcion, solo_costo)`. Los envoltorios son:

| Función | Qué baja | Costo aproximado |
|---|---|---|
| `datos.asegurar_cadenas(fechas, raices)` | cadena de cierre (`ohlcv-1d` + `statistics`) | SPX ~$0,20 por día; SPX+SPXW ~$0,66 por día |
| `odte.precio.pedidos_es(fechas)` | ES 1-min (`GLBX.MDP3`, `ES.v.0`) | centavos por día |
| `odte.catalogo.pedidos_definicion(fechas)` | catálogo SPXW (`definition`) | ~$0,03 por día |
| `odte.trades.asegurar_tcbbo({fecha: símbolos})` | trades con bid/ask, con caché por símbolo | lo caro: depende de las series |
| `odte.descargas.asegurar_odte({fecha: (kmin, kmax)})` | catálogo + ES, y después tcbbo (como mucho dos confirmaciones) | |

Para cotizar sin descargar:

```powershell
python scripts/costo_cadena.py 2026-09-24
python scripts/odte/ver_costos_0dte.py 2026-10-02 09:30 11:00
python scripts/signo_walls.py --solo-costo
```

Los mensajes de caché y costo van a stderr: la salida normal de los scripts queda limpia para comparar antes y después.

No bajes un día antes de su cierre. Databento publica la cadena después de las 16:23 NY y a veces bastante más tarde: el 11-20 todavía no estaba a las 16:40.

### Actualizar la caché

Con días nuevos, en este orden (cambia las fechas):

```powershell
# 1) SPX de yfinance (gratis; yfinance guarda solo ~30 días de 1m y ~60 de 5m) + ES 1-min (una confirmación)
python -c "import pandas as pd; from src import datos; from src.odte.precio import pedidos_es, cachear_spx_intradia; f=[d.strftime('%Y-%m-%d') for d in pd.bdate_range('2026-11-09','2026-11-24')]; print(cachear_spx_intradia(f).to_string()); datos.asegurar_descargas(pedidos_es(f), 'ES 1-min')"

# 2) Cadenas SPX+SPXW y su procesado en data/procesado (una confirmación, ~$0,66 por día)
python scripts/walls_tiempo.py 2026-11-19 2026-11-24          # --sin FECHA para días sin datos (2026-10-20)

# 3) Todo lo demás sale de la caché ($0)
python scripts/perfil_gamma.py --todas
python scripts/verificar_gamma.py
python scripts/validar_rango.py 2026-11-19 2026-11-24
python scripts/validar_gamma_local.py 2026-11-09 2026-11-24   # necesita el paso 1 y rango_implicito.csv
```

El paso 1 es un comando suelto porque no hay script para bajar el ES de un rango fuera de `validar_0dte`.

## Paneles

Los tres solo leen archivos ya calculados: no piden la API key y no pueden gastar crédito.

```powershell
streamlit run app/panel.py           # walls: mapa, perfil del día, ficha de un wall, de dónde vino el cambio, rotación
streamlit run app/panel_medidas.py   # sin signo: rango implícito, gamma por precio, verificación, intradía
streamlit run app/panel_odte.py      # 0DTE: el día, flujo por minuto, M4, toques, inventario de caché
```

`app/estilo.py` tiene la paleta y las marcas de cada clase, compartidas por los tres paneles.

## Clases de números

| Clase | Qué es | Ejemplos | Cómo se muestra |
|---|---|---|---|
| **MEDIDO** | dato observado | OI, ΔOI, precios, straddle, rangos del SPX, flujo con regla estricta | escala de un solo tono, marcas sólidas |
| **MODELO** | gamma Black-Scholes · OI **sin signo** | gamma bruta, `desbalance_pct`, gamma recalculada | violeta, punteado, rótulo "MODELO" |
| **SUPUESTO** | usa el signo de la hipótesis nula | GEX neto, walls, `pos`/`mer`/`ven` | escala divergente, rayado, rótulo "SUPUESTO" |

La hipótesis nula (`gex.HIPOTESIS_NULA_PUBLICO`) dice que el público vende calls y compra puts, así que el dealer queda largo de calls y corto de puts. Es un supuesto por defecto, no una medición. El signo sale de la tabla de `src/odte/dealer.py`, nunca de un `+1/−1` escrito a mano.

Cada módulo que entrega columnas declara su contrato (`clase(col)`), y la función grita si una columna no está clasificada. Los tests exigen que toda columna de salida tenga clase.

## Uso

Los scripts se corren desde la raíz, porque las rutas de caché son relativas. Reciben las fechas como argumentos, y el docstring del principio de cada uno explica su uso.

### GEX y walls

```powershell
python scripts/ver_gex.py 2026-09-24                            # GEX total y gamma walls del día
python scripts/ver_niveles.py 2026-10-13 12 --b2                # zonas por |GEX| sin la convención arriba/abajo
python scripts/comparar_versiones_gex.py 2026-09-24 2026-09-29  # los dos métodos lado a lado
python scripts/comparar_raices_gex.py 2026-10-16 2026-10-19     # SPX/días vs SPX/horas vs SPX+SPXW/horas
python scripts/verificar_forward.py 2026-09-24                  # forward y q implícitos por vencimiento
python scripts/walls_tiempo.py 2026-09-24 2026-10-21 --sin 2026-10-20   # evolución y descomposición del ΔGEX
```

`gex.construir_cadena(fecha, S, metodo, raices, plazo)`:

| Método | Precio de cada opción | Opciones incluidas | Dividendos |
|---|---|---|---|
| `mid_forward` (**default** desde oct-2026) | punto medio bid/ask de cierre | todas con OI | `q` medido por vencimiento y raíz (paridad call-put) |
| `ultimo_trade` (el original, para comparar) | último trade del día | solo las que operaron | q = 0 |

El default cambió por **valuación**, no por predicción:
- el último trade estaba viejo en el ~74% de las opciones;
- el OI que no operó es ~25% del libro;
- sin forward, las IV faltantes inventaban walls (el 7000 del 24-sep).

La predicción del rango siguiente salió pareja entre los dos métodos.

Más opciones de `construir_cadena`:
- **`raices`:** `("SPX",)` (default) o `("SPX", "SPXW")`.
- **`plazo`:** `"dias"` (default) o `"horas"` (hora real de vencimiento: 9:30 SPX, 16:00 SPXW; usar con SPXW).
- **Lo que vence ese mismo día (0DTE) queda fuera.** Es una decisión del 2026-11-09: aporta ~2% de la gamma bruta.

```
gex_contrib = gamma · OI · signo_supuesto · 100 · S² · 0.01
```

- **`gamma_walls`** agrupa en zonas de 25 pts, con la convención "arriba = resistencia, abajo = soporte".
- **`niveles_gamma`** ordena por |GEX| sin esa convención. Opcionalmente, pone el signo medido al lado.
- **`walls.evolucion`** parte el ΔGEX entre dos fotos, en forma exacta, en tres términos:
  - **posicionamiento:** ΔOI · k;
  - **mercado:** OI de ayer · Δk;
  - **vencidas:** lo que salió del libro.

### Fase B: signo supuesto contra medido

```powershell
python scripts/inventario_oi.py 2026-09-24 2026-10-08   # B1: OI y ΔOI por zona, sin signo ($0)
python scripts/b2_flujo.py 2026-09-24 2026-10-08        # B2: dirección del ΔOI con la regla estricta (tcbbo)
python scripts/b3_reporte.py                            # B3: cuánto del signo es supuesto ($0)
python scripts/signo_walls.py --paquetes                # SPX+SPXW, calls y puts, combos C+P ($0 con caché)
```

**Regla de tiempo** (confirmada, con tests): el OI del archivo de *d* es el del cierre de *d−1*. Por eso el ΔOI de *d* se explica con el flujo del día de mercado anterior.

### Medidas sin signo

```powershell
python scripts/validar_rango.py 2026-09-24 2026-11-06      # straddle ATM contra el rango siguiente
python scripts/perfil_gamma.py 2026-11-04 7353.7 7500      # gamma de la foto recalculada en otros precios
python scripts/perfil_gamma.py --todas                     # guarda la rejilla zona × spot que lee el panel
python scripts/verificar_gamma.py                          # recalculada contra la foto real del día siguiente
python scripts/validar_gamma_local.py 2026-09-25 2026-11-06   # gamma en el precio actual contra los 30 min siguientes
```

Las cuatro son $0 y solo leen la caché. La gamma recalculada mantiene fija la IV de cada opción (sticky strike). El error del recálculo es la banda con la que hay que leer cualquier perfil.

### Estudio 0DTE

```powershell
python scripts/odte/ver_definicion_0dte.py 2026-09-15            # qué SPXW eran 0DTE ese día
python scripts/odte/ver_flujo_0dte.py 2026-09-29 7600 7750       # flujo minuto a minuto + gráfico (caché)
python scripts/odte/ver_strikes_0dte.py 2026-10-12 7750 7870     # flujo estricto por strike (caché)
python scripts/odte/validar_0dte.py 2026-09-29 2026-10-19 --solo-cache   # muestra de toques (M2)
python scripts/odte/validar_carga.py 2026-09-25 2026-11-06 --sin 2026-10-20   # M4
```

- **SPX por minuto.** OPRA no trae el índice, así que el SPX minuto a minuto es el ES menos la base. Hay dos formas de medir la base:
  - **de cierre:** constante en todo el día;
  - **móvil:** medida cada 5 min contra yfinance.
- **Clasificación de trades.** Hay dos reglas:
  - **punto medio:** la histórica;
  - **estricta:** solo firma lo que se imprimió exactamente en el ask o en el bid. Lo demás queda indeterminado y nunca se redistribuye.
- **Horas.** Todas las horas llevan la zona `America/New_York`, y los cierres tempranos salen de `odte/calendario.py`.

## Reglas de validación (no negociables)

- Siempre la foto del cierre de la víspera contra lo que pasó **después**, nunca contra el mismo día. Esto incluye escalas y umbrales: tampoco pueden usar el día que se predice.
- Todo resultado se compara con el **predictor ingenuo** (el rango de hoy) sobre las mismas filas. En el intradía, también con el nivel del SPX.
- Los días no son independientes: el tamaño honesto de la muestra son los **episodios** (o los días, en el intradía), y una celda con menos de 10 días no es evidencia.
- Los cambios de GEX se reportan en $B, no en %: con GEX negativo, el % invierte el signo.
- Cada pregunta tiene su propio acumulador, y los acumuladores nunca se mezclan.
- Las preguntas cerradas (M1, M2, M4 y Fase B) no se reabren pagando datos solo para agrandar la muestra.

Hay dos subagentes de solo lectura en `.claude/agents/`:
- **`revisor-supuesto-medido`** revisa cómo se **muestra** un número.
- **`revisor-validacion`** revisa cómo se **obtuvo**.

## Estructura

```
config.py               API key (variable de entorno) y tasa libre de riesgo
src/
  datos.py              única capa que habla con Databento; caché + costo; cierre del SPX (yfinance)
  simbolos.py           parser OSI único; plazo_anios (único lugar donde se calcula T)
  black_scholes.py      precio, IV, delta y gamma con dividendo continuo q
  precio_justo.py       bid/ask de cierre por opción (statistics 7/8/9)
  forward.py            forward y q implícitos por vencimiento y por raíz
  gex.py                cadena procesada, GEX, gex_por_plazo, gamma_walls, niveles_gamma
  walls.py              evolución de los walls y descomposición exacta del ΔGEX; contrato de clases
  inventario.py         B1: OI y ΔOI por fecha (regla de tiempo d−1)
  signo_medido.py       B3: veredicto supuesto contra medido (MIN_ABS 200, MIN_REL 20%)
  signo_walls.py        B2/B3 sobre SPX+SPXW con data/procesado
  paquetes.py           combos C+P reconstruidos por milisegundo
  trade_sign.py         clasificación por punto medio (histórica; ver Fallas)
  rango_implicito.py    straddle ATM del primer vencimiento SPXW y su comparación con el ingenuo
  perfil_gamma.py       gamma recalculada en otro spot y otra hora; series intradía
  vista_medidas.py      datos del panel de medidas (solo archivos ya calculados)
  odte/                 0DTE: catalogo, precio, trades, clasificacion, flujo, dealer, veredicto,
                        cruce, calendario, descargas, toques, carga (M4), vista (panel), constantes
app/                    panel.py, panel_medidas.py, panel_odte.py, estilo.py (Streamlit + Plotly)
scripts/                análisis de un día o de un rango (scripts/odte/ para el 0DTE)
tests/                  pytest (336 tests, sin red)
data/raw/               caché de descargas (no se versiona)
data/procesado/         cadenas procesadas y rejillas de perfil_gamma (no se versiona)
data/validacion/        acumuladores versionados: gex_dias, rango_implicito, gamma_verificacion,
                        gamma_local, odte_toques, odte_carga
data/b2/                resultados de la fase B: flujo_series, signo_walls, paquetes_walls
```

## Tests

```powershell
$env:DATABENTO_API_KEY = "cualquier-valor"   # algunos módulos importan config; los tests no usan la red
python -m pytest                             # 336 tests
python -m pytest tests/test_forward.py       # un archivo
```

`pytest.ini` pone la raíz en el path. yfinance está reemplazado en los tests (monkeypatch).

## Fallas encontradas (revisión del 2026-11-25)

Revisión de todo el repo: código, scripts, documentación y los datos en caché. Los 336 tests pasan. Cada falla se comprobó leyendo el código y, cuando se podía, con datos de la caché ($0). **Ninguna está corregida todavía.** Están ordenadas por gravedad.

### 1. Los cierres tempranos no entran en el plazo T (alta, inminente)

`simbolos.plazo_anios(modo="horas")` fija la foto a las 16:00 (`HORA_FOTO`) y el vencimiento SPXW a las 16:00 (`HORA_VENCIMIENTO`). `odte.calendario.hora_cierre` existe y sabe que el 2026-11-27 y el 2026-12-24 cierran a las 13:00, pero solo la usa el módulo 0DTE. `scripts/validar_gamma_local.py` también arma `cierre_prev` con `HORA_FOTO` fijo.

- **Foto del 11-25:** la SPXW que vence el 11-27 queda con T = 48 h en vez de 45 h (+6,7%). Su gamma ATM sale ~3% baja.
- **Foto del 11-27:** el plazo se mide desde las 16:00, cuando la sesión terminó a las 13:00. T queda ~3 h corto en todas las series, y el bloque intradía del 11-30 parte de una hora de foto equivocada.
- **Por qué importa:** nada avisa. Es un "error que susurra", justo lo que el proyecto evita.

**Corrección sugerida:** que `plazo_anios` use `hora_cierre` para la foto y para el vencimiento PM.

### 2. Dos scripts bajan tcbbo sin costo ni confirmación (alta)

`scripts/ver_walls.py` y `scripts/ver_tradesign.py` llaman a `trade_sign.clasificar_flujo`, que baja con `datos.descargar_trades` directamente:
- no pasa por `get_cost` ni pide confirmación `s/n`;
- usa la caché vieja por md5 de la lista exacta (`trades_*.parquet`), no la caché por símbolo de `odte.trades`;
- clasifica con la regla del punto medio, no la estricta.

Rompe la regla de costo del proyecto: alcanza con correr uno de esos scripts con otra fecha para gastar crédito sin aviso.

**Corrección sugerida:** pasarlos por `asegurar_tcbbo` y `leer_tcbbo`, o marcarlos como históricos y que griten si falta la caché.

### 3. El `q` implícito absorbe el desfase entre las 16:00 y las 16:15 (media)

`forward.forward_por_vencimiento` mide F con el bid/ask de cierre de las opciones (16:15) y calcula `q = r − ln(F/S)/T` con S = el cierre del SPX (16:00). En vencimientos de 1 a 3 días, el cambio de esos 15 minutos se convierte en un "dividendo" enorme.

Medido en los 42 días de `rango_implicito.csv`, con el primer vencimiento SPXW:
- |q| tiene mediana 15,8% anual;
- va de −71,6% (11-04) a +178% (10-29);
- F − S fue −36,6 pts el 10-29 y +37,7 pts el 11-20.

Consecuencias:
- **(a) La foto queda corrida.** La gamma de esas series queda centrada en el forward de las 16:15, mientras la foto guarda S = 16:00. El perfil por zona se corre F − S.
- **(b) Todo spot hipotético hereda el desfase.** `perfil_gamma` mantiene `q` fijo, así que cada spot de la rejilla, y la serie intradía de `validar_gamma_local`, arrastra ese desfase en los vencimientos cortos. El 11-20 eso es ~38 pts.
- **(c) Contamina los errores de verificación.** El error de `verificar_gamma` incluye la diferencia de desfase entre las dos fotos.

CLAUDE.md documenta la asincronía solo para el straddle. **Corrección sugerida:** guardar F − S por foto y reportarlo, o valuar sobre F con un spot coherente con él.

### 4. Nada impide procesar un día que todavía no cerró (media)

- **`datos.precio_spx`, `walls_tiempo` y `validar_gex`** toman la última fila de `yfinance.history`. Durante la sesión, esa fila es un precio intradía.
- **`walls_tiempo` congela el error.** Guarda la cadena procesada con ese S en `data/procesado/` y no la rehace.
- **`validar_gex` lo guarda en el acumulador.** Guardaría el rango parcial del día siguiente en `gex_dias.csv`.
- **`asegurar_cadenas` tampoco revisa** si la fecha ya cerró.

`validar_rango` sí tiene la guarda (salta el día cuya sesión siguiente no terminó). Hoy esto depende de la disciplina de quien corre el script.

### 5. Las descargas se guardan sin validar el contenido (baja, latente)

`asegurar_descargas`, `asegurar_cadenas` y `descargar_cadena` guardan lo que llegue. Si Databento devolviera un archivo vacío o parcial, quedaría en caché para siempre, porque la caché siempre gana.

Revisé los 43 `statistics` SPXW en caché y están completos: 18–22 mil series con OI, bid/ask ≈ 1,0 × OI y último evento entre las 17:30 y las 17:46. **Hoy no hay daño.**

**Corrección sugerida:** un control mínimo antes de guardar (filas > 0; en `statistics`, los tres `stat_type`).

### 6. A `validar_gex.py` le falta `--sin` (baja)

A diferencia de `walls_tiempo`, no permite saltar días sin datos en Databento (el 2026-10-20). Además, `cambio_*` se calcula con `diff()` dentro de cada corrida, y cruza los huecos sin marcarlos.

### 7. Documentación desactualizada (baja)

- **Este README** decía que `ultimo_trade` era el default. Ya está corregido.
- **`scripts/odte/caracterizar_strike_0dte.py`** dice que KMIN y KMAX deben ser "los mismos de la descarga original" porque la caché se identifica por la lista de símbolos. Eso dejó de ser cierto con la caché por símbolo (R3).
- **`ODTE.md`** dice "15 scripts" (hay 17) y "293 tests" (hay 336).
- **`CLAUDE.md`** menciona el acumulador `data/validacion/gex_dias_spxw.csv`, pero el archivo no existe: `validar_gex --spxw` nunca se corrió o el CSV no se guardó.

### 8. Archivos sueltos en la raíz (baja)

- **`probarkey.py`:** el nombre no dice lo que hace. No prueba la clave: arma la cadena del 09-24 e imprime el OI de 7790–7810. Usa yfinance y, sin caché, pediría una descarga.
- **`antes.txt`, `despues.txt`, `despues_q0.txt`, `gex_antes.txt`, `gex_despues.txt` y `nan_q0.txt`:** capturas en UTF-16 versionadas en git.

### Observaciones (no son fallas de código)

- **Hay trabajo sin commitear:** 9 archivos modificados, entre ellos `src/perfil_gamma.py` (la rejilla de ±1050 pts), el panel de medidas y dos acumuladores.
- **La caché intradía está atrasada:** ES 1-min y SPX de yfinance llegan solo hasta el 11-06, así que `gamma_local.csv` también.
- **Las cadenas y `data/procesado`** llegan al 11-24, sin el 10-20.
- **Descarté tres sospechas con datos:**
  - Ninguna serie sale de una foto a la siguiente sin haber vencido. Los archivos traen también OI = 0, así que `walls.descomponer` no confunde cierres con vencimientos.
  - Ningún trade de los 8,26 millones del tcbbo 0DTE en caché tiene bid = ask, así que la regla estricta no tiene casos ambiguos.
  - Las 43 cadenas SPXW en caché están completas.
