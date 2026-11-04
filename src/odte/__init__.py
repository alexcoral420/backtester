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
"""