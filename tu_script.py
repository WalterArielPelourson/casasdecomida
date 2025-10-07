import requests
import json
from datetime import datetime, timedelta
import math

# --- 1. Configuración ---
GOOGLE_MAPS_API_KEY = "YOUR_GOOGLE_MAPS_API_KEY"  # ¡REEMPLAZA CON TU PROPIA API KEY!
ENVIO_COSTO = 10000
MAX_PEDIDOS_POR_FRANJA_HORARIA = 5
RADIO_ENVIO_CUADRAS = 30 # Aproximadamente 2.4 km (1 cuadra ~ 80 metros)

# Coordenadas de la sucursal (ejemplo, reemplaza con las de tu casa de comida)
SUCURSAL_LAT = -34.6037  # Latitud de Buenos Aires, por ejemplo
SUCURSAL_LON = -58.3816  # Longitud de Buenos Aires, por ejemplo

# --- 2. Clases Base ---

class Plato:
    def __init__(self, id_plato, nombre, descripcion, precio):
        self.id_plato = id_plato
        self.nombre = nombre
        self.descripcion = descripcion
        self.precio = precio

    def __str__(self):
        return f"{self.id_plato}. {self.nombre} - ${self.precio:,.2f}\n   Descripción: {self.descripcion}"

class Pedido:
    def __init__(self, id_pedido, cliente_nombre, cliente_apellido, direccion_entrega, es_envio, horario_entrega):
        self.id_pedido = id_pedido
        self.cliente_nombre = cliente_nombre
        self.cliente_apellido = cliente_apellido
        self.direccion_entrega = direccion_entrega
        self.es_envio = es_envio
        self.horario_entrega = horario_entrega
        self.items = []  # Lista de tuplas: (Plato, cantidad)
        self.costo_total = 0

    def agregar_item(self, plato, cantidad):
        self.items.append({"plato": plato, "cantidad": cantidad})
        self._calcular_costo_total()

    def _calcular_costo_total(self):
        total = sum(item["plato"].precio * item["cantidad"] for item in self.items)
        if self.es_envio:
            total += ENVIO_COSTO
        self.costo_total = total

    def __str__(self):
        detalle = f"--- Pedido #{self.id_pedido} ---\n"
        detalle += f"Cliente: {self.cliente_nombre} {self.cliente_apellido}\n"
        detalle += f"Dirección de Entrega: {self.direccion_entrega}\n"
        detalle += f"Tipo: {'Envío' if self.es_envio else 'Retiro en Sucursal'}\n"
        detalle += f"Horario de Entrega/Retiro: {self.horario_entrega.strftime('%H:%M')}\n"
        detalle += "Detalle del Pedido:\n"
        for item in self.items:
            plato = item["plato"]
            cantidad = item["cantidad"]
            detalle += f"  - {cantidad} x {plato.nombre} (${plato.precio:,.2f} c/u) = ${plato.precio * cantidad:,.2f}\n"
        if self.es_envio:
            detalle += f"Costo de Envío: ${ENVIO_COSTO:,.2f}\n"
        detalle += f"Costo Total: ${self.costo_total:,.2f}\n"
        detalle += "------------------------\n"
        return detalle

# --- 3. Funciones de Google Maps ---

def obtener_info_restaurante_google_maps(nombre_restaurante, api_key):
    """
    Busca información de un restaurante en Google Maps (Place Search y Place Details).
    Retorna un diccionario con nombre, dirección, coordenadas y horarios.
    """
    if not api_key or api_key == "YOUR_GOOGLE_MAPS_API_KEY":
        print("Advertencia: API Key de Google Maps no configurada. No se obtendrá información real.")
        return {
            "nombre": nombre_restaurante,
            "direccion": "Dirección de ejemplo, si la API Key no está configurada.",
            "lat": SUCURSAL_LAT,
            "lon": SUCURSAL_LON,
            "horario_atencion": ["Lunes a Viernes: 09:00 - 23:00", "Sábado y Domingo: 10:00 - 00:00"],
            "url_mapa": "https://maps.google.com/?q=Casa+de+Comida+Ejemplo"
        }

    # 1. Place Search para encontrar el Place ID
    search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params_search = {
        "input": nombre_restaurante,
        "inputtype": "textquery",
        "fields": "place_id",
        "key": api_key
    }
    try:
        response_search = requests.get(search_url, params=params_search)
        response_search.raise_for_status()
        data_search = response_search.json()

        if data_search["status"] == "OK" and data_search["candidates"]:
            place_id = data_search["candidates"][0]["place_id"]
        else:
            print(f"No se encontró Place ID para '{nombre_restaurante}'. Status: {data_search.get('status')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la API de Google Places (Search): {e}")
        return None

    # 2. Place Details para obtener la información completa
    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    params_details = {
        "place_id": place_id,
        "fields": "name,formatted_address,geometry,opening_hours,url",
        "key": api_key
    }
    try:
        response_details = requests.get(details_url, params=params_details)
        response_details.raise_for_status()
        data_details = response_details.json()

        if data_details["status"] == "OK" and data_details["result"]:
            result = data_details["result"]
            horario = result.get("opening_hours", {}).get("weekday_text", ["Horario no disponible"])
            
            return {
                "nombre": result.get("name"),
                "direccion": result.get("formatted_address"),
                "lat": result["geometry"]["location"]["lat"],
                "lon": result["geometry"]["location"]["lng"],
                "horario_atencion": horario,
                "url_mapa": result.get("url")
            }
        else:
            print(f"No se encontraron detalles para el Place ID {place_id}. Status: {data_details.get('status')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la API de Google Places (Details): {e}")
        return None

def obtener_coordenadas_desde_direccion(direccion, api_key):
    """
    Convierte una dirección en latitud y longitud usando la API de Geocoding.
    Retorna una tupla (lat, lon) o None si falla.
    """
    if not api_key or api_key == "YOUR_GOOGLE_MAPS_API_KEY":
        print("Advertencia: API Key de Google Maps no configurada. Usando coordenadas de ejemplo.")
        # Simula un resultado para una dirección de ejemplo
        if "calle falsa 123" in direccion.lower():
            return -34.6000, -58.4000 # Un punto cercano a la sucursal de ejemplo
        else:
            return -34.6100, -58.3900 # Otro punto cercano
        

    geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": direccion,
        "key": api_key
    }
    try:
        response = requests.get(geocoding_url, params=params)
        response.raise_for_status()
        data = response.json()

        if data["status"] == "OK" and data["results"]:
            location = data["results"][0]["geometry"]["location"]
            return location["lat"], location["lng"]
        else:
            print(f"No se pudieron obtener coordenadas para la dirección: '{direccion}'. Status: {data.get('status')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la API de Google Geocoding: {e}")
        return None

def calcular_distancia_cuadras(lat1, lon1, lat2, lon2):
    """
    Calcula la distancia Haversine entre dos puntos en la Tierra y la convierte
    aproximadamente a "cuadras".
    1 grado de latitud ~ 111 km.
    1 cuadra ~ 80 metros.
    """
    R = 6371  # Radio de la Tierra en kilómetros

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) * math.sin(dlat / 2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distancia_km = R * c
    distancia_cuadras = distancia_km / 0.08  # 1 cuadra = 80 metros = 0.08 km
    return distancia_cuadras

# --- 4. Sistema Principal ---

class SistemaCasaComida:
    def __init__(self, nombre_casa_comida):
        self.nombre = nombre_casa_comida
        self.catalogo = {}  # {id_plato: Plato}
        self.pedidos = []
        self.proximo_id_pedido = 1
        self.info_restaurante = None
        self.franjas_horarias_ocupadas = {} # {datetime_hora: contador_pedidos}

        self._cargar_catalogo_ejemplo()
        self._cargar_info_restaurante()

    def _cargar_catalogo_ejemplo(self):
        # Aquí puedes cargar tu catálogo desde un archivo, base de datos, etc.
        self.catalogo = {
            "1": Plato("1", "Hamburguesa Clásica", "Carne, lechuga, tomate, queso, cebolla, pepinillos.", 3500.00),
            "2": Plato("2", "Pizza Muzzarella", "Salsa de tomate, muzzarella, orégano.", 4200.00),
            "3": Plato("3", "Milanesa Napolitana", "Ternera, salsa, jamón, queso, papas fritas.", 5800.00),
            "4": Plato("4", "Ensalada César", "Lechuga, crutones, queso parmesano, aderezo César.", 3000.00),
            "5": Plato("5", "Empanadas de Carne (unidad)", "Carne cortada a cuchillo, aceitunas, huevo.", 600.00),
            "6": Plato("6", "Gaseosa Coca-Cola", "Lata de 354ml.", 800.00),
            "7": Plato("7", "Agua Mineral", "Botella de 500ml.", 700.00),
            "8": Plato("8", "Flan Casero", "Flan con dulce de leche y crema.", 2500.00),
        }

    def _cargar_info_restaurante(self):
        print(f"Buscando información de '{self.nombre}' en Google Maps...")
        self.info_restaurante = obtener_info_restaurante_google_maps(self.nombre, GOOGLE_MAPS_API_KEY)
        if self.info_restaurante:
            print("Información del restaurante cargada.")
        else:
            print("No se pudo cargar la información del restaurante de Google Maps. Usando datos por defecto.")
            self.info_restaurante = {
                "nombre": self.nombre,
                "direccion": "Calle Falsa 123, Ciudad Ejemplo",
                "lat": SUCURSAL_LAT,
                "lon": SUCURSAL_LON,
                "horario_atencion": ["Lunes a Sábado: 10:00 - 22:00", "Domingo: Cerrado"],
                "url_mapa": "https://maps.google.com/?q=Casa+de+Comida+Ejemplo"
            }

    def mostrar_info_restaurante(self):
        print("\n--- Información de la Casa de Comida ---")
        print(f"Nombre: {self.info_restaurante['nombre']}")
        print(f"Dirección: {self.info_restaurante['direccion']}")
        print("Horario de Atención:")
        for horario in self.info_restaurante['horario_atencion']:
            print(f"  - {horario}")
        print(f"Ver en Google Maps: {self.info_restaurante['url_mapa']}")
        print("---------------------------------------")

    def mostrar_carta(self):
        print("\n--- Nuestra Carta ---")
        if not self.catalogo:
            print("El catálogo está vacío.")
            return

        for plato_id in sorted(self.catalogo.keys(), key=lambda x: int(x)):
            print(self.catalogo[plato_id])
        print("---------------------\n")

    def cargar_pedido(self):
        print("\n--- Realizar Nuevo Pedido ---")

        # Datos del cliente
        cliente_nombre = input("Nombre del cliente: ").strip()
        cliente_apellido = input("Apellido del cliente: ").strip()
        direccion_entrega = input("Dirección de entrega (calle, número, piso, depto, localidad): ").strip()

        # Determinar si es envío o retiro
        es_envio = False
        distancia_cuadras = None
        
        cliente_lat_lon = obtener_coordenadas_desde_direccion(direccion_entrega, GOOGLE_MAPS_API_KEY)
        
        if cliente_lat_lon:
            cliente_lat, cliente_lon = cliente_lat_lon
            sucursal_lat = self.info_restaurante.get("lat", SUCURSAL_LAT)
            sucursal_lon = self.info_restaurante.get("lon", SUCURSAL_LON)

            distancia_cuadras = calcular_distancia_cuadras(sucursal_lat, sucursal_lon, cliente_lat, cliente_lon)

            print(f"Distancia a la sucursal: {distancia_cuadras:.2f} cuadras.")
            if distancia_cuadras <= RADIO_ENVIO_CUADRAS:
                es_envio = True
                print(f"¡Excelente! Su dirección está dentro de nuestro rango de envío ({RADIO_ENVIO_CUADRAS} cuadras).")
            else:
                print(f"Lo sentimos, su dirección ({distancia_cuadras:.2f} cuadras) está fuera de nuestro rango de envío ({RADIO_ENVIO_CUADRAS} cuadras).")
                print("El retiro deberá ser por sucursal.")
        else:
            print("No se pudo validar la dirección del cliente. Por seguridad, el retiro será por sucursal.")

        # Cargar ítems del catálogo
        pedido_actual = Pedido(self.proximo_id_pedido, cliente_nombre, cliente_apellido, direccion_entrega, es_envio, None)
        
        while True:
            self.mostrar_carta()
            seleccion_id = input("Ingrese el número del plato a agregar (o 'f' para finalizar): ").lower().strip()
            if seleccion_id == 'f':
                break

            if seleccion_id in self.catalogo:
                plato_seleccionado = self.catalogo[seleccion_id]
                while True:
                    try:
                        cantidad = int(input(f"Cantidad de '{plato_seleccionado.nombre}': "))
                        if cantidad > 0:
                            pedido_actual.agregar_item(plato_seleccionado, cantidad)
                            print(f"{cantidad} x '{plato_seleccionado.nombre}' agregados al pedido.")
                            break
                        else:
                            print("La cantidad debe ser mayor que cero.")
                    except ValueError:
                        print("Por favor, ingrese un número válido para la cantidad.")
            else:
                print("ID de plato no válido. Por favor, intente de nuevo.")

        if not pedido_actual.items:
            print("El pedido está vacío. Cancelando pedido.")
            return

        # Seleccionar horario de entrega/retiro
        horario_seleccionado = self._seleccionar_horario()
        if not horario_seleccionado:
            print("No se pudo seleccionar un horario. Cancelando pedido.")
            return

        pedido_actual.horario_entrega = horario_seleccionado
        self.pedidos.append(pedido_actual)
        self.proximo_id_pedido += 1
        
        # Incrementar contador de franja horaria ocupada
        self.franjas_horarias_ocupadas[horario_seleccionado] = self.franjas_horarias_ocupadas.get(horario_seleccionado, 0) + 1

        print("\n¡Pedido cargado con éxito!")
        print(pedido_actual)

    def _generar_franjas_horarias(self, inicio_str="10:00", fin_str="23:00", intervalo_minutos=15):
        """Genera una lista de objetos datetime para las franjas horarias."""
        franjas = []
        hoy = datetime.now().date()
        
        # Obtener el inicio y fin del horario de atención para hoy (simplificado)
        # En un sistema real, aquí se pararía el `horario_atencion` de info_restaurante
        # y se determinaría el horario según el día de la semana.
        try:
            inicio_hora, inicio_min = map(int, inicio_str.split(':'))
            fin_hora, fin_min = map(int, fin_str.split(':'))
        except ValueError:
            print("Error: Formato de hora inválido para generar franjas.")
            return []

        hora_actual_dt = datetime.now()
        inicio_hoy = datetime.combine(hoy, datetime.min.time()).replace(hour=inicio_hora, minute=inicio_min)
        fin_hoy = datetime.combine(hoy, datetime.min.time()).replace(hour=fin_hora, minute=fin_min)

        # Si el inicio de la franja es antes de ahora, empezar 15 minutos después de ahora
        if inicio_hoy < hora_actual_dt:
            inicio_hoy = hora_actual_dt + timedelta(minutes=(intervalo_minutos - hora_actual_dt.minute % intervalo_minutos) % intervalo_minutos)
            inicio_hoy = inicio_hoy.replace(second=0, microsecond=0)

        current_time = inicio_hoy
        while current_time <= fin_hoy:
            franjas.append(current_time)
            current_time += timedelta(minutes=intervalo_minutos)
        return franjas

    def _seleccionar_horario(self):
        """Permite al cliente seleccionar una franja horaria para el pedido."""
        print("\n--- Seleccione Horario de Entrega/Retiro ---")
        franjas_disponibles = self._generar_franjas_horarias()
        
        if not franjas_disponibles:
            print("No hay franjas horarias disponibles en este momento.")
            return None

        while True:
            print("\nHorarios disponibles:")
            for i, franja in enumerate(franjas_disponibles):
                pedidos_en_franja = self.franjas_horarias_ocupadas.get(franja, 0)
                estado = ""
                if pedidos_en_franja >= MAX_PEDIDOS_POR_FRANJA_HORARIA:
                    estado = " (COMPLETO)"
                
                print(f"{i+1}. {franja.strftime('%H:%M')}{estado}")
            
            seleccion = input("Seleccione el número de horario deseado: ").strip()
            if not seleccion.isdigit():
                print("Entrada inválida. Por favor, ingrese un número.")
                continue

            indice = int(seleccion) - 1
            if 0 <= indice < len(franjas_disponibles):
                horario_elegido = franjas_disponibles[indice]
                pedidos_en_franja = self.franjas_horarias_ocupadas.get(horario_elegido, 0)

                if pedidos_en_franja < MAX_PEDIDOS_POR_FRANJA_HORARIA:
                    print(f"Horario seleccionado: {horario_elegido.strftime('%H:%M')}")
                    return horario_elegido
                else:
                    print(f"Lo sentimos, el horario de {horario_elegido.strftime('%H:%M')} está completo. Por favor, elija otra franja.")
            else:
                print("Número de horario inválido. Intente de nuevo.")

# --- 5. Interfaz de Usuario (Bucle Principal) ---

def main():
    sistema = SistemaCasaComida("La Esquina del Sabor") # Nombre de tu casa de comida

    while True:
        print("\n--- MENÚ PRINCIPAL ---")
        print("1. Ver información del restaurante")
        print("2. Ver nuestra carta")
        print("3. Realizar un nuevo pedido")
        print("4. Salir")

        opcion = input("Seleccione una opción: ").strip()

        if opcion == '1':
            sistema.mostrar_info_restaurante()
        elif opcion == '2':
            sistema.mostrar_carta()
        elif opcion == '3':
            sistema.cargar_pedido()
        elif opcion == '4':
            print("Gracias por usar nuestro sistema. ¡Hasta pronto!")
            break
        else:
            print("Opción no válida. Por favor, intente de nuevo.")

if __name__ == "__main__":
    main()