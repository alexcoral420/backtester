# backtester

Herramientas de investigación sobre opciones del SPX:

- **GEX (gamma exposure) y gamma walls** a partir de la cadena de opciones de cierre de un día.
- **Estudio 0DTE**: flujo intradía de las opciones SPXW que vencen el mismo día. Muestra quién agredió, cómo se acumula el flujo minuto a minuto y qué posición le queda al dealer.

Datos: [Databento](https://databento.com) (opciones OPRA, futuros ES de CME) y yfinance (cierre oficial del SPX).

## Instalación

Requiere Python 3.13 (es la versión con la que se desarrolla).

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

La API key de Databento se lee de la variable de entorno y nunca va en el código:

```powershell
$env:DATABENTO_API_KEY = "db-tu-clave"
```

Sin la variable, `config.py` lanza un error al importarse.

## Costo y caché

Databento cobra por cada descarga, así que todo el proyecto sigue la misma regla:

1. **Caché primero.** Cada descarga se guarda como parquet en `data/raw/`. Si el archivo ya existe, se lee del disco y no se paga de nuevo.
2. **Costo antes de bajar.** Si falta, se consulta `get_cost`, se muestra el costo estimado y se pide confirmación (`s/n`) antes de descargar.

Referencias: la cadena de un día cuesta unos $0,19. Para consultar el costo sin descargar nada:

```powershell
python scripts/costo_cadena.py 2026-09-24
python scripts/odte/ver_costos_0dte.py 2026-10-02 09:30 11:00
```

`data/raw/`, los `*.parquet` y los gráficos `data/*.png` no se versionan.

## Uso

Los scripts se corren desde la raíz del proyecto y reciben la fecha (y otros parámetros) como argumentos. Cada script explica su uso en el docstring del principio.

### GEX y walls

```powershell
python scripts/ver_gex.py 2026-09-24                          # GEX total y gamma walls del día
python scripts/comparar_versiones_gex.py 2026-09-24 2026-09-29 # método original vs versión C
python scripts/ver_walls.py 2026-09-24 261016                  # posición del dealer en los walls cercanos
python scripts/verificar_forward.py 2026-09-24                 # forward y dividendo implícitos por vencimiento
```

`src/gex.py` tiene dos métodos de cálculo (`construir_cadena(fecha, S, metodo=...)`):

| Método | Precio de cada opción | Opciones incluidas | Dividendos |
|---|---|---|---|
| `ultimo_trade` (default) | último trade del día | solo las que operaron | q = 0 |
| `mid_forward` (versión C) | punto medio bid/ask de cierre | todas con open interest | q medido por vencimiento con la paridad call-put |

La versión C existe porque el último trade estaba fuera del bid/ask de cierre en ~74% de las opciones y no existe para las que no operaron (~25% del OI).

Contribución de cada opción al GEX:

```
gex_contrib = gamma · OI · (+1 call / −1 put) · 100 · S² · 0.01
```

Los walls agrupan esa contribución en zonas de 25 puntos.

### Estudio 0DTE

```powershell
python scripts/odte/ver_definicion_0dte.py 2026-09-15            # qué opciones eran 0DTE ese día
python scripts/odte/ver_trades_0dte.py 2026-09-29 7600 7750      # baja los trades (tcbbo) de un rango de strikes
python scripts/odte/ver_flujo_0dte.py 2026-09-29 7600 7750       # trade sign minuto a minuto + gráfico
python scripts/odte/ver_apertura_0dte.py 2026-10-02 7695 7775 09:30 11:00 5
```

Como OPRA no trae el índice, el SPX minuto a minuto se estima como futuro ES menos la base (ES − SPX al cierre). Todas las horas usan la zona `America/New_York`.

Para clasificar cada trade hay dos reglas (`src/odte/clasificacion.py`):

- **Punto medio**: precio > medio → el público compra; precio < medio → el público vende.
- **Estricta**: solo cuentan los trades en el ask (compra) o en el bid (venta). Los trades impresos fuera del bid/ask se marcan como `complejo` (huella de órdenes de varias patas).

El dealer es el lado pasivo. Su tabla de signos (delta, gamma, cobertura, si frena o amplifica) está en `src/odte/dealer.py`.

## Estructura

```
config.py            API key (de la variable de entorno) y tasa libre de riesgo
src/
  datos.py           descargas de Databento con caché + costo; cierre del SPX (yfinance)
  simbolos.py        parseo único de símbolos OSI ('SPXW  261016C07800000')
  black_scholes.py   precio, IV, delta y gamma (con dividendo continuo q opcional)
  precio_justo.py    punto medio bid/ask de cierre por opción
  forward.py         forward implícito por vencimiento (paridad call-put)
  gex.py             cadena procesada, GEX total y gamma walls
  trade_sign.py      clasificación del flujo en strikes concretos
  odte/              paquete del estudio 0DTE (catálogo, precio, trades, clasificación, flujo, dealer)
scripts/             análisis y gráficos que usan src/ (scripts/odte/ para el estudio 0DTE)
tests/               tests con pytest
```

## Tests

```powershell
$env:DATABENTO_API_KEY = "cualquier-valor"   # algunos módulos importan config; los tests no usan la red
python -m pytest
python -m pytest tests/test_black_scholes.py  # un solo archivo
```
