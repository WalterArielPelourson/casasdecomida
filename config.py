# config.py


GOOGLE_MAPS_API_KEY = "YOUR_GOOGLE_MAPS_API_KEY" # ¡REEMPLAZA CON TU API KEY REAL!
# ENVIO_COSTO = 10000.0 # Esta línea se ha eliminado/comentado, ahora se gestiona desde la DB
MAX_PEDIDOS_POR_FRANJA_HORARIA = 5
RADIO_ENVIO_CUADRAS = 30
CUADRA_METROS = 80

DB_NAME = 'restaurante.db' # ASEGÚRATE DE QUE ESTE NOMBRE ES CORRECTO Y CONSISTENTE

# Coordenadas de la sucursal (ejemplo: Buenos Aires). Se actualizarán si Google Maps las encuentra.
SUCURSAL_LAT = -34.6037
SUCURSAL_LON = -58.3816

# Horario de operación por defecto (si no se carga de Google Maps)
HORA_APERTURA = "10:00"
HORA_CIERRE = "23:00"
INTERVALO_FRANJAS_MINUTOS = 15

# Nueva configuración para la empresa por defecto a la que los clientes hacen pedidos
DEFAULT_COMPANY_FOR_ORDERS = 2 # ID de la empresa por defecto para pedidos de clientes