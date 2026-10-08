from src.gex import construir_cadena
from src.datos import precio_spx

fecha = "2026-09-24"
S = precio_spx(fecha)
cadena = construir_cadena(fecha, S)

# Comparar OI de strikes redondos vs intermedios, cerca del precio
cerca = cadena[(cadena["strike"] >= 7790) & (cadena["strike"] <= 7810)]
print(cerca.groupby("strike")["open_interest"].sum().to_string())