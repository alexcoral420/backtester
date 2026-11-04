"""
Paquete odte — estudio del flujo intradía de las opciones SPXW que vencen el mismo día.

Cada módulo responde UNA pregunta:
  catalogo       ¿qué opciones existían y cuáles eran 0DTE?
  precio         ¿dónde estaba el SPX cada minuto? (ES - base)
  trades         ¿qué se negoció? (tcbbo, con costo y caché)
  clasificacion  ¿quién agredió en cada trade?
  flujo          ¿cómo se acumula el flujo en el tiempo?
  veredicto      ¿qué signo del dealer sostiene el flujo medido, y con cuánto respaldo?
  cruce          ¿cuándo llegó el precio al strike?
  dealer         la tabla de signos del dealer
  calendario     ¿a qué hora cerró el mercado ese día? (cierres tempranos)
  descargas      ¿qué falta en caché para un rango de días, y cuánto cuesta? (UNA confirmación por paso)
  toques         cuando el precio llegó a un strike, ¿aguantó o se cruzó? ¿qué flujo había antes? (M2)
"""