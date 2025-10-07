from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, current_app
import sqlite3
from datetime import datetime, timedelta
import math
import requests
import json
import os
import sys

# Importar Flask-Login y Werkzeug para autenticación
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

# Importar configuración
from config import (
    GOOGLE_MAPS_API_KEY, MAX_PEDIDOS_POR_FRANJA_HORARIA,
    RADIO_ENVIO_CUADRAS, CUADRA_METROS, DB_NAME,
    SUCURSAL_LAT, SUCURSAL_LON, HORA_APERTURA, HORA_CIERRE, INTERVALO_FRANJAS_MINUTOS,
    DEFAULT_COMPANY_FOR_ORDERS
)

app = Flask(__name__)
app.secret_key = 'super_secreto_de_casa_comida_web_202024' # CAMBIA ESTO POR UNA CLAVE MÁS SEGURA EN PRODUCCIÓN

# Inicializar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Define la vista a la que redirigir si se requiere login
login_manager.login_message = "Por favor, inicie sesión para acceder a esta página."
login_manager.login_message_category = "warning"

# --- Constante para el costo de envío por defecto si no está en DB ---
DEFAULT_ENVIO_COSTO = 500.00
# --- Costo por envío al repartidor (valor por defecto, también configurable en DB) ---
DEFAULT_PAGO_REPARTIDOR_POR_ENVIO = 300.00

# --- Funciones de Base de Datos ---
def conectar_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Permite acceder a las columnas por nombre
    return conn

def crear_tablas():
    """Crea las tablas de la base de datos si no existen y añade columnas si faltan."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS platos (
            id_plato INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            precio REAL NOT NULL,
            activo INTEGER DEFAULT 1,
            id_empresa INTEGER,
            rubro TEXT, 
            FOREIGN KEY(id_empresa) REFERENCES empresas(id_empresa)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repartidores (
            id_repartidor INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            telefono TEXT,
            activo INTEGER DEFAULT 1,
            id_empresa INTEGER,
            FOREIGN KEY(id_empresa) REFERENCES empresas(id_empresa)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nombre TEXT NOT NULL,
            cliente_apellido TEXT NOT NULL,
            direccion_entrega TEXT NOT NULL,
            es_envio INTEGER NOT NULL,
            horario_entrega TEXT NOT NULL,
            costo_envio REAL NOT NULL,
            costo_total REAL NOT NULL,
            forma_pago TEXT NOT NULL,
            estado_pago TEXT NOT NULL DEFAULT 'Pendiente',
            fecha_creacion TEXT NOT NULL,
            fecha_pago TEXT,
            lat_cliente REAL,
            lon_cliente REAL,
            id_repartidor INTEGER,
            id_empresa INTEGER,
            FOREIGN KEY(id_repartidor) REFERENCES repartidores(id_repartidor),
            FOREIGN KEY(id_empresa) REFERENCES empresas(id_empresa)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pedido INTEGER NOT NULL,
            id_plato INTEGER NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            FOREIGN KEY(id_pedido) REFERENCES pedidos(id_pedido),
            FOREIGN KEY(id_plato) REFERENCES platos(id_plato)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingresos_egresos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            monto REAL NOT NULL,
            descripcion TEXT,
            fecha_hora TEXT NOT NULL,
            id_pedido_origen INTEGER,
            id_repartidor_origen INTEGER,
            id_empresa INTEGER,
            FOREIGN KEY(id_pedido_origen) REFERENCES pedidos(id_pedido),
            FOREIGN KEY(id_repartidor_origen) REFERENCES repartidores(id_repartidor),
            FOREIGN KEY(id_empresa) REFERENCES empresas(id_empresa)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT,
            id_empresa INTEGER,
            FOREIGN KEY(id_empresa) REFERENCES empresas(id_empresa)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id_empresa INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            telefono TEXT,  
            direccion TEXT, 
            activo INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id_rol INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_rol TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            id_rol INTEGER NOT NULL,
            id_empresa INTEGER,
            activo INTEGER DEFAULT 1,
            primer_login_requerido INTEGER DEFAULT 1,
            FOREIGN KEY(id_rol) REFERENCES roles(id_rol),
            FOREIGN KEY(id_empresa) REFERENCES empresas(id_empresa)
        )
    """)

    # --- Comprobar y añadir columnas si faltan (para migraciones sin borrar DB) ---
    cursor.execute("PRAGMA table_info(pedidos)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'id_repartidor' not in columns:
        cursor.execute("ALTER TABLE pedidos ADD COLUMN id_repartidor INTEGER REFERENCES repartidores(id_repartidor)")
        print("Columna 'id_repartidor' añadida a la tabla 'pedidos'.")
    if 'id_empresa' not in columns:
        cursor.execute("ALTER TABLE pedidos ADD COLUMN id_empresa INTEGER REFERENCES empresas(id_empresa)")
        print("Columna 'id_empresa' añadida a la tabla 'pedidos'.")

    cursor.execute("PRAGMA table_info(ingresos_egresos)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'id_repartidor_origen' not in columns:
        cursor.execute("ALTER TABLE ingresos_egresos ADD COLUMN id_repartidor_origen INTEGER REFERENCES repartidores(id_repartidor)")
        print("Columna 'id_repartidor_origen' añadida a la tabla 'ingresos_egresos'.")
    if 'id_empresa' not in columns:
        cursor.execute("ALTER TABLE ingresos_egresos ADD COLUMN id_empresa INTEGER REFERENCES empresas(id_empresa)")
        print("Columna 'id_empresa' añadida a la tabla 'ingresos_egresos'.")

    cursor.execute("PRAGMA table_info(platos)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'id_empresa' not in columns:
        cursor.execute("ALTER TABLE platos ADD COLUMN id_empresa INTEGER REFERENCES empresas(id_empresa)")
        print("Columna 'id_empresa' añadida a la tabla 'platos'.")
    if 'rubro' not in columns:
        cursor.execute("ALTER TABLE platos ADD COLUMN rubro TEXT")
        print("Columna 'rubro' añadida a la tabla 'platos'.")

    cursor.execute("PRAGMA table_info(repartidores)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'id_empresa' not in columns:
        cursor.execute("ALTER TABLE repartidores ADD COLUMN id_empresa INTEGER REFERENCES empresas(id_empresa)")
        print("Columna 'id_empresa' añadida a la tabla 'repartidores'.")

    cursor.execute("PRAGMA table_info(configuracion)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'id_empresa' not in columns:
        cursor.execute("ALTER TABLE configuracion ADD COLUMN id_empresa INTEGER REFERENCES empresas(id_empresa)")
        print("Columna 'id_empresa' añadida a la tabla 'configuracion'.")
    
    cursor.execute("PRAGMA table_info(empresas)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'telefono' not in columns:
        cursor.execute("ALTER TABLE empresas ADD COLUMN telefono TEXT")
        print("Columna 'telefono' añadida a la tabla 'empresas'.")
    if 'direccion' not in columns:
        cursor.execute("ALTER TABLE empresas ADD COLUMN direccion TEXT")
        print("Columna 'direccion' añadida a la tabla 'empresas'.")

    cursor.execute("INSERT OR IGNORE INTO roles (id_rol, nombre_rol) VALUES (1, 'super_admin')")
    cursor.execute("INSERT OR IGNORE INTO roles (id_rol, nombre_rol) VALUES (2, 'admin_empresa')")
    cursor.execute("INSERT OR IGNORE INTO roles (id_rol, nombre_rol) VALUES (3, 'empleado')")

    conn.commit()
    conn.close()

def guardar_configuracion(clave, valor, id_empresa=None):
    """Guarda un par clave-valor en la tabla de configuración, opcionalmente por empresa."""
    conn = conectar_db()
    cursor = conn.cursor()
    if id_empresa:
        cursor.execute("REPLACE INTO configuracion (clave, valor, id_empresa) VALUES (?, ?, ?)", (clave, str(valor), id_empresa))
    else:
        cursor.execute("REPLACE INTO configuracion (clave, valor, id_empresa) VALUES (?, ?, NULL)", (clave, str(valor)))
    conn.commit()
    conn.close()

def cargar_configuracion(clave, valor_defecto=None, id_empresa=None):
    """Carga un valor de la tabla de configuración por su clave, opcionalmente por empresa."""
    conn = conectar_db()
    cursor = conn.cursor()
    if id_empresa:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = ? AND id_empresa = ?", (clave, id_empresa))
    else:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = ? AND id_empresa IS NULL", (clave,))

    resultado = cursor.fetchone()
    conn.close()
    if resultado:
        return resultado['valor']
    return valor_defecto

def get_costo_envio():
    """Obtiene el costo de envío desde la base de datos o usa un valor por defecto."""
    if current_user.is_authenticated and current_user.id_empresa:
        costo = cargar_configuracion('ENVIO_COSTO', str(DEFAULT_ENVIO_COSTO), current_user.id_empresa)
    else:
        costo = cargar_configuracion('ENVIO_COSTO', str(DEFAULT_ENVIO_COSTO), None)
    try:
        return float(costo)
    except ValueError:
        return DEFAULT_ENVIO_COSTO

def get_pago_repartidor_por_envio():
    """Obtiene el pago por envío al repartidor desde la base de datos o usa un valor por defecto."""
    if current_user.is_authenticated and current_user.id_empresa:
        pago = cargar_configuracion('PAGO_REPARTIDOR_POR_ENVIO', str(DEFAULT_PAGO_REPARTIDOR_POR_ENVIO), current_user.id_empresa)
    else:
        pago = cargar_configuracion('PAGO_REPARTIDOR_POR_ENVIO', str(DEFAULT_PAGO_REPARTIDOR_POR_ENVIO), None)
    try:
        return float(pago)
    except ValueError:
        return DEFAULT_PAGO_REPARTIDOR_POR_ENVIO

def _agregar_super_admin_inicial():
    """Agrega un usuario super_admin inicial si no existe ninguno,
       y una empresa por defecto con un admin_empresa si no existen."""
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE id_rol = (SELECT id_rol FROM roles WHERE nombre_rol = 'super_admin')")
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash("admin_password_inicial_segura", method='pbkdf2:sha256')
        cursor.execute("""
            INSERT INTO usuarios (email, password, nombre, apellido, id_rol, id_empresa, activo, primer_login_requerido)
            VALUES (?, ?, ?, ?, (SELECT id_rol FROM roles WHERE nombre_rol = 'super_admin'), NULL, 1, 0)
        """, ("admin@tudominio.com", hashed_password, "Super", "Admin",))
        conn.commit()
        print("Usuario 'super_admin' inicial creado: admin@tudominio.com con la contraseña 'admin_password_inicial_segura' (¡CÁMBIALA!)")

    default_company_id = DEFAULT_COMPANY_FOR_ORDERS
    cursor.execute("INSERT OR IGNORE INTO empresas (id_empresa, nombre, telefono, direccion, activo) VALUES (?, ?, NULL, NULL, 1)",
                   (default_company_id, "Empresa Principal por Defecto"))
    conn.commit()
    print(f"Empresa por defecto (ID: {default_company_id}, Nombre: Empresa Principal por Defecto) asegurada.")

    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE id_rol = (SELECT id_rol FROM roles WHERE nombre_rol = 'admin_empresa') AND id_empresa = ?", (default_company_id,))
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash("empresa_password_segura", method='pbkdf2:sha256')
        cursor.execute("""
            INSERT INTO usuarios (email, password, nombre, apellido, id_rol, id_empresa, activo, primer_login_requerido)
            VALUES (?, ?, ?, ?, (SELECT id_rol FROM roles WHERE nombre_rol = 'admin_empresa'), ?, 1, 1)
        """, ("admin_empresa@empresa.com", hashed_password, "Admin", "Empresa", default_company_id))
        conn.commit()
        print(f"Usuario 'admin_empresa' inicial creado para Empresa Principal (ID: {default_company_id}): admin_empresa@empresa.com con la contraseña 'empresa_password_segura' (¡CÁMBIALA!)")

    conn.close()

def _agregar_platos_ejemplo_a_db():
    """Agrega platos de ejemplo a la DB si no existen, asignándolos a la empresa por defecto."""
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM platos")
    if cursor.fetchone()[0] == 0:
        default_company_id = DEFAULT_COMPANY_FOR_ORDERS

        platos_ejemplo = [
            ("Hamburguesa Clásica", "Carne 180gr, lechuga, tomate, queso cheddar, cebolla caramelizada, pepinillos.", 3500.00, "Comidas"),
            ("Pizza Muzzarella Grande", "Salsa de tomate casera, abundante muzzarella, aceitunas verdes, orégano.", 4200.00, "Pizzas"),
            ("Milanesa Napolitana (con fritas)", "Tierna milanesa de ternera, salsa, jamón, queso gratinado, acompañada de papas fritas.", 5800.00, "Comidas"),
            ("Ensalada César con Pollo", "Lechuga romana, crutones, queso parmesano, aderezo César y tiras de pollo grillado.", 3000.00, "Ensaladas"),
            ("Empanadas de Carne (unidad)", "Carne picada a cuchillo, huevo, aceitunas. Jugosas y sabrosas.", 600.00, "Entradas"),
            ("Gaseosa Coca-Cola", "Lata de 354ml, bien fría.", 800.00, "Bebidas"),
            ("Agua Mineral sin Gas", "Botella de 500ml.", 700.00, "Bebidas"),
            ("Flan Casero con Dulce de Leche y Crema", "Receta de la abuela, irresistible.", 2500.00, "Postres"),
            ("Cerveza Artesanal IPA", "Pinta de cerveza artesanal de lupulado intenso.", 1500.00, "Bebidas"),
        ]
        for nombre, desc, precio, rubro in platos_ejemplo:
            cursor.execute("INSERT INTO platos (nombre, descripcion, precio, activo, id_empresa, rubro) VALUES (?, ?, ?, 1, ?, ?)",
                           (nombre, desc, precio, default_company_id, rubro))
        conn.commit()
        print(f"Platos de ejemplo agregados a la base de datos para la empresa ID {default_company_id}.")
    conn.close()

def _agregar_repartidor_ejemplo_a_db():
    """Agrega un repartidor de ejemplo a la DB si no existen repartidores, asignándolos a la empresa por defecto."""
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM repartidores")
    if cursor.fetchone()[0] == 0:
        default_company_id = DEFAULT_COMPANY_FOR_ORDERS

        cursor.execute("INSERT INTO repartidores (nombre, apellido, telefono, activo, id_empresa) VALUES (?, ?, ?, 1, ?)",
                       ("Juan", "Perez", "1123456789", default_company_id))
        cursor.execute("INSERT INTO repartidores (nombre, apellido, telefono, activo, id_empresa) VALUES (?, ?, ?, 1, ?)",
                       ("Maria", "Gomez", "1198765432", default_company_id))
        conn.commit()
        print(f"Repartidores de ejemplo agregados a la base de datos para la empresa ID {default_company_id}.")
    conn.close()


# --- Clases de Modelo ---
class Plato:
    def __init__(self, id_plato, nombre, descripcion, precio, activo=1, id_empresa=None, rubro=None):
        self.id_plato = id_plato
        self.nombre = nombre
        self.descripcion = descripcion
        self.precio = precio
        self.activo = activo
        self.id_empresa = id_empresa
        self.rubro = rubro 

class Repartidor:
    def __init__(self, id_repartidor, nombre, apellido, telefono, activo=1, id_empresa=None):
        self.id_repartidor = id_repartidor
        self.nombre = nombre
        self.apellido = apellido
        self.telefono = telefono
        self.activo = activo
        self.id_empresa = id_empresa

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

class Pedido:
    def __init__(self, id_pedido, cliente_nombre, cliente_apellido, direccion_entrega, es_envio,
                 horario_entrega, costo_envio, costo_total, forma_pago, estado_pago, fecha_creacion,
                 lat_cliente, lon_cliente, fecha_pago=None, id_repartidor=None, id_empresa=None):
        self.id_pedido = id_pedido
        self.cliente_nombre = cliente_nombre
        self.cliente_apellido = cliente_apellido
        self.direccion_entrega = direccion_entrega
        self.es_envio = bool(es_envio)
        self.horario_entrega = datetime.strptime(horario_entrega, '%Y-%m-%d %H:%M:%S') if isinstance(horario_entrega, str) else horario_entrega
        self.costo_envio = costo_envio
        self.costo_total = costo_total
        self.forma_pago = forma_pago
        self.estado_pago = estado_pago
        self.fecha_creacion = datetime.strptime(fecha_creacion, '%Y-%m-%d %H:%M:%S') if isinstance(fecha_creacion, str) else fecha_creacion
        self.fecha_pago = datetime.strptime(fecha_pago, '%Y-%m-%d %H:%M:%S') if fecha_pago else None
        self.lat_cliente = lat_cliente
        self.lon_cliente = lon_cliente
        self.id_repartidor = id_repartidor
        self.id_empresa = id_empresa
        self.repartidor = None
        self.items = []

    def agregar_item(self, plato, cantidad, precio_unitario):
        self.items.append({"plato": plato, "cantidad": cantidad, "precio_unitario": precio_unitario})

    def generar_ticket(self):
        ticket_html = f"""
        <div class="ticket">
            <h4 class="text-center">TICKET DE PEDIDO #{self.id_pedido}</h4>
            <hr>
            <p><strong>Cliente:</strong> {self.cliente_nombre} {self.cliente_apellido}</p>
            <p><strong>Dirección:</strong> {self.direccion_entrega}</p>
            <p><strong>Tipo:</strong> {'Envío' if self.es_envio else 'Retiro en Sucursal'}</p>
            <p><strong>Horario:</strong> {self.horario_entrega.strftime('%H:%M')} ({self.horario_entrega.strftime('%d/%m')})</p>
        """
        if self.es_envio and self.repartidor:
            ticket_html += f"<p><strong>Repartidor:</strong> {self.repartidor.nombre_completo}</p>"

        ticket_html += """<hr>
            <h6>Detalle del Pedido:</h6>
            <ul class="list-unstyled">
        """
        for item in self.items:
            plato_nombre = item["plato"].nombre if isinstance(item["plato"], Plato) else item["plato"]
            cantidad = item["cantidad"]
            precio_unitario = item["precio_unitario"]
            ticket_html += f"<li>{cantidad} x {plato_nombre} @ ${precio_unitario:,.2f} = ${cantidad * precio_unitario:,.2f}</li>"

        ticket_html += "</ul>"
        if self.es_envio:
            ticket_html += f"<p><strong>Costo de Envío:</strong> ${self.costo_envio:,.2f}</p>"

        ticket_html += f"""
            <hr>
            <p><strong>TOTAL: ${self.costo_total:,.2f}</strong></p>
            <hr>
            <p><strong>Forma de Pago:</strong> {self.forma_pago}</p>
            <p><strong>Estado del Pago:</strong> {self.estado_pago}</p>
        """
        if self.fecha_pago:
            ticket_html += f"<p><strong>Fecha de Pago:</strong> {self.fecha_pago.strftime('%d/%m/%Y %H:%M')}</p>"

        ticket_html += f"""
            <hr>
            <p class="text-center">¡Gracias por su compra!</p>
        </div>
        """
        return ticket_html

class Empresa:
    def __init__(self, id_empresa, nombre, telefono=None, direccion=None, activo=1):
        self.id_empresa = id_empresa
        self.nombre = nombre
        self.telefono = telefono
        self.direccion = direccion
        self.activo = activo

class Rol:
    def __init__(self, id_rol, nombre_rol):
        self.id_rol = id_rol
        self.nombre_rol = nombre_rol

class Usuario(UserMixin):
    def __init__(self, id_usuario, email, password, nombre, apellido, id_rol, id_empresa, activo=1, primer_login_requerido=1, nombre_rol=None):
        self.id = id_usuario
        self.email = email
        self.password = password
        self.nombre = nombre
        self.apellido = apellido
        self.id_rol = id_rol
        self.id_empresa = id_empresa
        self.activo = activo
        self.primer_login_requerido = primer_login_requerido
        self.nombre_rol = nombre_rol

    def get_id(self):
        return str(self.id)

    def is_active(self):
        return bool(self.activo)

    def get_full_name(self):
        return f"{self.nombre} {self.apellido}"

    def has_role(self, role_name):
        return self.nombre_rol == role_name

@login_manager.user_loader
def load_user(user_id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id_usuario, u.email, u.password, u.nombre, u.apellido,
               u.id_rol, u.id_empresa, u.activo, u.primer_login_requerido,
               r.nombre_rol
        FROM usuarios u
        JOIN roles r ON u.id_rol = r.id_rol
        WHERE u.id_usuario = ?
    """, (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        return Usuario(
            user_data['id_usuario'],
            user_data['email'],
            user_data['password'],
            user_data['nombre'],
            user_data['apellido'],
            user_data['id_rol'],
            user_data['id_empresa'],
            user_data['activo'],
            user_data['primer_login_requerido'],
            user_data['nombre_rol']
        )
    return None

# --- Funciones de Google Maps y Geocodificación ---

_info_restaurante = None

def obtener_info_restaurante_google_maps_cached(nombre_restaurante):
    global _info_restaurante, SUCURSAL_LAT, SUCURSAL_LON
    if _info_restaurante:
        return _info_restaurante

    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY == "YOUR_GOOGLE_MAPS_API_KEY":
        print("Advertencia: API Key de Google Maps no configurada. Usando datos de ejemplo para el restaurante.")
        _info_restaurante = {
            "nombre": nombre_restaurante,
            "direccion": "Dirección de ejemplo, 1234, Ciudad Ficticia",
            "lat": SUCURSAL_LAT,
            "lon": SUCURSAL_LON,
            "horario_atencion": ["Lunes a Viernes: 09:00 - 23:00", "Sábado y Domingo: 10:00 - 00:00"],
            "url_mapa": "https://maps.google.com/?q=Casa+de+Comida+Ejemplo"
        }
        return _info_restaurante

    search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params_search = { "input": nombre_restaurante, "inputtype": "textquery", "fields": "place_id", "key": GOOGLE_MAPS_API_KEY, "language": "es" }
    try:
        response_search = requests.get(search_url, params=params_search, timeout=5)
        response_search.raise_for_status()
        data_search = response_search.json()
        if data_search["status"] == "OK" and data_search["candidates"]:
            place_id = data_search["candidates"][0]["place_id"]
        else:
            print(f"Error al buscar Place ID para '{nombre_restaurante}'. Status: {data_search.get('status')}. Error: {data_search.get('error_message')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error de red con Google Places (Search): {e}")
        return None
    except json.JSONDecodeError:
        print("Error al procesar respuesta JSON de Google Places (Search).")
        return None

    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    params_details = { "place_id": place_id, "fields": "name,formatted_address,geometry,opening_hours,url", "key": GOOGLE_MAPS_API_KEY, "language": "es" }
    try:
        response_details = requests.get(details_url, params=params_details, timeout=5)
        response_details.raise_for_status()
        data_details = response_details.json()
        if data_details["status"] == "OK" and data_details["result"]:
            result = data_details["result"]
            _info_restaurante = {
                "nombre": result.get("name", nombre_restaurante),
                "direccion": result.get("formatted_address", "Dirección no disponible"),
                "lat": result["geometry"]["location"]["lat"],
                "lon": result["geometry"]["location"]["lng"],
                "horario_atencion": result.get("opening_hours", {}).get("weekday_text", ["Horario no disponible"]),
                "url_mapa": result.get("url", f"https://maps.google.com/?q={nombre_restaurante.replace(' ', '+')}")
            }
            SUCURSAL_LAT = _info_restaurante['lat']
            SUCURSAL_LON = _info_restaurante['lon']
            return _info_restaurante
        else:
            print(f"Error al obtener detalles del restaurante: {data_details.get('status')}. Error: {data_details.get('error_message')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error de red con Google Places (Details): {e}")
        return None
    except json.JSONDecodeError:
        print("Error al procesar respuesta JSON de Google Places (Details).")
        return None

def obtener_coordenadas_desde_direccion(direccion):
    """
    Convierte una dirección en latitud y longitud usando la API de Geocoding.
    Si la API Key no es válida o hay un error, retorna coordenadas de ejemplo.
    """
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY == "YOUR_GOOGLE_MAPS_API_KEY":
        print("Advertencia: API Key de Google Maps no configurada. Usando coordenadas de ejemplo para la dirección.")
        if "calle falsa 123" in direccion.lower(): return -34.6000, -58.4000
        elif "avenida siempreviva 742" in direccion.lower(): return -34.6050, -58.3850
        else: return -34.6100, -58.3900


    geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = { "address": direccion, "key": GOOGLE_MAPS_API_KEY, "language": "es" }
    try:
        response = requests.get(geocoding_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "OK" and data["results"]:
            location = data["results"][0]["geometry"]["location"]
            return location["lat"], location["lng"]
        else:
            print(f"No se pudieron obtener coordenadas para la dirección: {data.get('status')}. Error: {data.get('error_message')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error de red con Google Geocoding: {e}")
        return None
    except json.JSONDecodeError:
        print("Error al procesar respuesta JSON de Google Geocoding.")
        return None

def calcular_distancia_cuadras(lat1, lon1, lat2, lon2):
    """
    Calcula la distancia Haversine (línea recta) entre dos puntos geográficos
    y la convierte aproximadamente a "cuadras".
    """
    R = 6371.0

    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distancia_km = R * c
    distancia_metros = distancia_km * 1000
    distancia_cuadras = distancia_metros / CUADRA_METROS
    return distancia_cuadras

# --- Lógica de Negocio y Utilidades para la App Web ---

def get_company_filter_conditions_and_params(table_alias=''):
    """
    Genera una lista de condiciones y los parámetros para filtrar por empresa para el usuario actual.
    Si el usuario es super_admin, no añade condiciones de empresa.
    Retorna (list_of_conditions, list_of_params).
    """
    conditions = []
    params = []

    if current_user.is_authenticated and not current_user.has_role('super_admin'):
        if current_user.id_empresa:
            if table_alias:
                conditions.append(f"{table_alias}.id_empresa = ?")
            else:
                conditions.append("id_empresa = ?")
            params.append(current_user.id_empresa)
        else:
            conditions.append("1 = 0") # Asegura que no se muestre nada si el admin_empresa no tiene id_empresa
    return conditions, params

def get_company_id_for_frontend_context():
    """
    Determina la ID de la empresa para operaciones de frontend (hacer pedido, carrito, etc.).
    Si un usuario de empresa está logueado, usa su ID de empresa.
    De lo contrario (público o super_admin), usa la DEFAULT_COMPANY_FOR_ORDERS.
    """
    if current_user.is_authenticated and not current_user.has_role('super_admin') and current_user.id_empresa:
        return current_user.id_empresa
    return DEFAULT_COMPANY_FOR_ORDERS

def _generar_franjas_horarias_disponibles(company_id_for_franjas):
    """
    Genera una lista de franjas horarias futuras disponibles (no completas).
    Cada franja es un string 'HH:MM'. Filtra por la empresa proporcionada.
    """
    franjas = []
    hoy = datetime.now().date()

    try:
        inicio_hora, inicio_min = map(int, HORA_APERTURA.split(':'))
        fin_hora, fin_min = map(int, HORA_CIERRE.split(':'))
    except ValueError:
        print("Error en formato de HORA_APERTURA o HORA_CIERRE en config.py")
        return []

    inicio_turno_hoy = datetime.combine(hoy, datetime.min.time()).replace(hour=inicio_hora, minute=inicio_min)
    fin_turno_hoy = datetime.combine(hoy, datetime.min.time()).replace(hour=fin_hora, minute=fin_min)

    hora_actual_dt = datetime.now()

    current_time = hora_actual_dt + timedelta(minutes=(INTERVALO_FRANJAS_MINUTOS - hora_actual_dt.minute % INTERVALO_FRANJAS_MINUTOS) % INTERVALO_FRANJAS_MINUTOS)
    current_time = current_time.replace(second=0, microsecond=0)

    if current_time < inicio_turno_hoy:
         current_time = inicio_turno_hoy

    franjas_ocupadas = _cargar_franjas_ocupadas_desde_db_interna(company_id_for_franjas)

    franjas_para_mostrar = []
    while current_time <= fin_turno_hoy:
        if current_time > hora_actual_dt:
            pedidos_en_franja = franjas_ocupadas.get(current_time, 0)
            if pedidos_en_franja < MAX_PEDIDOS_POR_FRANJA_HORARIA:
                franjas_para_mostrar.append(current_time.strftime('%H:%M'))
        current_time += timedelta(minutes=INTERVALO_FRANJAS_MINUTOS)

    return franjas_para_mostrar

def _cargar_franjas_ocupadas_desde_db_interna(company_id):
    """
    Carga el conteo de pedidos por franja horaria para pedidos 'Pendiente'
    desde la base de datos, considerando solo franjas futuras para el día actual y
    filtrando por la empresa proporcionada.
    Retorna un diccionario {datetime_obj: count}
    """
    franjas_ocupadas = {}
    conn = conectar_db()
    cursor = conn.cursor()

    hoy_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    query_conditions = ["estado_pago = 'Pendiente'", "horario_entrega >= ?"]
    query_params = [hoy_str]

    company_conditions, company_params = get_company_filter_conditions_and_params(table_alias='p')
    query_conditions.extend(company_conditions)
    query_params.extend(company_params)


    final_query = f"""
        SELECT horario_entrega, COUNT(*) AS num_pedidos
        FROM pedidos p
        WHERE {' AND '.join(query_conditions)}
        GROUP BY horario_entrega
    """
    cursor.execute(final_query, query_params)

    resultados = cursor.fetchall()
    for row in resultados:
        dt_obj = datetime.strptime(row['horario_entrega'], '%Y-%m-%d %H:%M:%S')
        franjas_ocupadas[dt_obj] = row['num_pedidos']
    conn.close()
    return franjas_ocupadas

def _obtener_pedido_completo_por_id(id_pedido):
    """
    Recupera un objeto Pedido completo (con sus ítems y datos de repartidor si aplica)
    de la base de datos, aplicando filtro de empresa para usuarios no super_admin.
    """
    conn = conectar_db()
    cursor = conn.cursor()

    base_query = """
        SELECT p.*, r.nombre AS repartidor_nombre, r.apellido AS repartidor_apellido, r.telefono AS repartidor_telefono
        FROM pedidos p
        LEFT JOIN repartidores r ON p.id_repartidor = r.id_repartidor
    """
    where_conditions = ["p.id_pedido = ?"]
    query_params = [id_pedido]

    company_conditions, company_params = get_company_filter_conditions_and_params(table_alias='p')
    where_conditions.extend(company_conditions)
    query_params.extend(company_params)
    
    final_query = base_query + " WHERE " + " AND ".join(where_conditions)

    cursor.execute(final_query, query_params)
    pedido_data = cursor.fetchone()

    if not pedido_data:
        conn.close()
        return None

    pedido = Pedido(
        pedido_data['id_pedido'], pedido_data['cliente_nombre'], pedido_data['cliente_apellido'],
        pedido_data['direccion_entrega'], pedido_data['es_envio'], pedido_data['horario_entrega'],
        pedido_data['costo_envio'], pedido_data['costo_total'], pedido_data['forma_pago'],
        pedido_data['estado_pago'], pedido_data['fecha_creacion'],
        pedido_data['lat_cliente'], pedido_data['lon_cliente'],
        pedido_data['fecha_pago'], pedido_data['id_repartidor'], pedido_data['id_empresa']
    )

    if pedido_data['id_repartidor']:
        pedido.repartidor = Repartidor(
            pedido_data['id_repartidor'],
            pedido_data['repartidor_nombre'],
            pedido_data['repartidor_apellido'],
            pedido_data['repartidor_telefono']
        )

    cursor.execute("""
        SELECT ip.cantidad, ip.precio_unitario, p.id_plato, p.nombre, p.descripcion, p.rubro
        FROM items_pedido ip
        JOIN platos p ON ip.id_plato = p.id_plato
        WHERE ip.id_pedido = ?
    """, (id_pedido,))

    items_data = cursor.fetchall()
    for item_row in items_data:
        plato = Plato(item_row['id_plato'], item_row['nombre'], item_row['descripcion'], item_row['precio_unitario'], id_empresa=pedido.id_empresa, rubro=item_row['rubro'])
        pedido.agregar_item(plato, item_row['cantidad'], item_row['precio_unitario'])

    conn.close()
    return pedido

def init_app():
    """
    Función de inicialización que se ejecuta al inicio de la aplicación.
    Crea tablas si no existen, añade platos de ejemplo y carga la información del restaurante.
    """
    print("Inicializando la aplicación...")
    crear_tablas()
    _agregar_super_admin_inicial()
    _agregar_platos_ejemplo_a_db()
    _agregar_repartidor_ejemplo_a_db()
    obtener_info_restaurante_google_maps_cached("La Esquina del Sabor")

    if cargar_configuracion('ENVIO_COSTO', id_empresa=None) is None:
        guardar_configuracion('ENVIO_COSTO', DEFAULT_ENVIO_COSTO, id_empresa=None)
        print(f"Costo de envío inicial '{DEFAULT_ENVIO_COSTO}' guardado como configuración global.")

    if cargar_configuracion('PAGO_REPARTIDOR_POR_ENVIO', id_empresa=None) is None:
        guardar_configuracion('PAGO_REPARTIDOR_POR_ENVIO', DEFAULT_PAGO_REPARTIDOR_POR_ENVIO, id_empresa=None)
        print(f"Costo de pago a repartidor inicial '{DEFAULT_PAGO_REPARTIDOR_POR_ENVIO}' guardado como configuración global.")

    print("Aplicación inicializada.")

# --- Rutas de la Aplicación (Views) ---

@app.route('/')
def index():
    """Página principal, muestra información del restaurante."""
    info = obtener_info_restaurante_google_maps_cached("La Esquina del Sabor")
    return render_template('index.html', info=info)

# --- Rutas de Autenticación ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()

        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id_usuario, u.email, u.password, u.nombre, u.apellido,
                   u.id_rol, u.id_empresa, u.activo, u.primer_login_requerido,
                   r.nombre_rol
            FROM usuarios u
            JOIN roles r ON u.id_rol = r.id_rol
            WHERE u.email = ?
        """, (email,))
        user_data = cursor.fetchone()
        conn.close()

        if user_data:
            user = Usuario(
                user_data['id_usuario'],
                user_data['email'],
                user_data['password'],
                user_data['nombre'],
                user_data['apellido'],
                user_data['id_rol'],
                user_data['id_empresa'],
                user_data['activo'],
                user_data['primer_login_requerido'],
                user_data['nombre_rol']
            )
            if check_password_hash(user.password, password) and user.is_active():
                login_user(user)
                flash(f"Bienvenido, {user.nombre}!", "success")

                if user.primer_login_requerido:
                    return redirect(url_for('cambiar_clave_inicial'))

                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                flash("Credenciales inválidas o usuario inactivo.", "danger")
        else:
            flash("Credenciales inválidas o usuario no encontrado.", "danger")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for('index'))

@app.route('/cambiar_clave_inicial', methods=['GET', 'POST'])
@login_required
def cambiar_clave_inicial():
    if not current_user.primer_login_requerido:
        flash("Tu contraseña ya ha sido cambiada o no se requiere cambio inicial.", "info")
        return redirect(url_for('index'))

    if request.method == 'POST':
        nueva_clave = request.form['nueva_clave']
        confirmar_clave = request.form['confirmar_clave']

        if not nueva_clave or len(nueva_clave) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "danger")
        elif nueva_clave != confirmar_clave:
            flash("Las contraseñas no coinciden.", "danger")
        else:
            conn = conectar_db()
            cursor = conn.cursor()
            try:
                hashed_password = generate_password_hash(nueva_clave, method='pbkdf2:sha256')
                cursor.execute("""
                    UPDATE usuarios SET password = ?, primer_login_requerido = 0
                    WHERE id_usuario = ?
                """, (hashed_password, current_user.id))
                conn.commit()
                current_user.password = hashed_password
                current_user.primer_login_requerido = 0

                flash("Tu contraseña ha sido actualizada con éxito. Ya puedes acceder a la aplicación.", "success")
                return redirect(url_for('index'))
            except sqlite3.Error as e:
                conn.rollback()
                flash(f"Error al actualizar la contraseña: {e}", "danger")
            finally:
                conn.close()

    return render_template('cambiar_clave_inicial.html')

@app.route('/hacer_pedido', methods=['GET', 'POST'])
def hacer_pedido():
    """
    Ruta para que el cliente realice un nuevo pedido.
    GET: Muestra el formulario con la carta y el carrito (unificado).
    POST: Procesa el formulario, guarda el pedido en la DB y redirige a la confirmación.
    """
    company_id_for_frontend = get_company_id_for_frontend_context()

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id_plato, nombre, descripcion, precio, rubro FROM platos WHERE activo = 1 AND id_empresa = ? ORDER BY id_plato ASC",
                   (company_id_for_frontend,))
    platos_db = cursor.fetchall()
    conn.close()

    if request.method == 'POST':
        cliente_nombre = request.form['nombre'].strip()
        cliente_apellido = request.form['apellido'].strip()
        direccion_entrega = request.form['direccion'].strip()
        forma_pago = request.form['forma_pago']
        horario_str = request.form['horario_entrega']
        es_envio_solicitado = 'es_envio_solicitado' in request.form

        pedido_id_empresa = company_id_for_frontend

        form_data_on_error = request.form.to_dict()
        form_data_on_error['es_envio_solicitado'] = es_envio_solicitado

        if not all([cliente_nombre, cliente_apellido, forma_pago, horario_str]):
            flash("Todos los campos obligatorios (nombre, apellido, forma de pago, horario de entrega) deben ser completados.", "danger")
            return render_template('hacer_pedido.html',
                                   platos=platos_db,
                                   franjas_horarias=_generar_franjas_horarias_disponibles(company_id_for_frontend),
                                   carrito_detalle=_get_carrito_detalle(platos_db),
                                   total_carrito=_get_total_carrito(),
                                   costo_envio=get_costo_envio(),
                                   request_form=form_data_on_error,
                                   carrito=session.get('carrito', {}))

        if es_envio_solicitado and not direccion_entrega:
            flash("Si desea envío a domicilio, la dirección de entrega es obligatoria.", "danger")
            return render_template('hacer_pedido.html',
                                   platos=platos_db,
                                   franjas_horarias=_generar_franjas_horarias_disponibles(company_id_for_frontend),
                                   carrito_detalle=_get_carrito_detalle(platos_db),
                                   total_carrito=_get_total_carrito(),
                                   costo_envio=get_costo_envio(),
                                   request_form=form_data_on_error,
                                   carrito=session.get('carrito', {}))

        try:
            horario_entrega_dt = datetime.strptime(horario_str, '%H:%M')
            hoy = datetime.now().date()
            horario_entrega_completo = datetime.combine(hoy, horario_entrega_dt.time())

            franjas_ocupadas = _cargar_franjas_ocupadas_desde_db_interna(company_id_for_frontend)
            if franjas_ocupadas.get(horario_entrega_completo, 0) >= MAX_PEDIDOS_POR_FRANJA_HORARIA:
                flash(f"Lo sentimos, el horario {horario_str} se ha completado. Por favor, elija otra franja.", "danger")
                return render_template('hacer_pedido.html',
                                       platos=platos_db,
                                       franjas_horarias=_generar_franjas_horarias_disponibles(company_id_for_frontend),
                                       carrito_detalle=_get_carrito_detalle(platos_db),
                                       total_carrito=_get_total_carrito(),
                                       costo_envio=get_costo_envio(),
                                       request_form=form_data_on_error,
                                       carrito=session.get('carrito', {}))

        except ValueError:
            flash("Horario de entrega inválido.", "danger")
            return render_template('hacer_pedido.html',
                                   platos=platos_db,
                                   franjas_horarias=_generar_franjas_horarias_disponibles(company_id_for_frontend),
                                   carrito_detalle=_get_carrito_detalle(platos_db),
                                   total_carrito=_get_total_carrito(),
                                   costo_envio=get_costo_envio(),
                                   request_form=form_data_on_error,
                                   carrito=session.get('carrito', {}))

        es_envio = False
        costo_envio_aplicado = 0.0
        lat_cliente, lon_cliente = None, None

        current_envio_costo = get_costo_envio()

        if es_envio_solicitado:
            cliente_lat_lon = obtener_coordenadas_desde_direccion(direccion_entrega)
            if cliente_lat_lon:
                lat_cliente, lon_cliente = cliente_lat_lon
                distancia_cuadras = calcular_distancia_cuadras(SUCURSAL_LAT, SUCURSAL_LON, lat_cliente, lon_cliente)
                if distancia_cuadras <= RADIO_ENVIO_CUADRAS:
                    es_envio = True
                    costo_envio_aplicado = current_envio_costo
                    flash(f"Su dirección está dentro del rango de envío ({distancia_cuadras:.2f} cuadras). Costo de envío aplicado.", "info")
                else:
                    flash(f"Su dirección ({distancia_cuadras:.2f} cuadras) está fuera del rango de envío. El pedido será para retiro en sucursal y no se aplicará costo de envío.", "warning")
            else:
                flash("No se pudo validar su dirección para el envío. El pedido será para retiro en sucursal y no se aplicará costo de envío.", "warning")
        else:
            flash("El pedido será para retiro en sucursal.", "info")

        if 'carrito' not in session or not session['carrito']:
            flash("El carrito está vacío. Agregue productos antes de hacer el pedido.", "danger")
            return render_template('hacer_pedido.html',
                                   platos=platos_db,
                                   franjas_horarias=_generar_franjas_horarias_disponibles(company_id_for_frontend),
                                   carrito_detalle=_get_carrito_detalle(platos_db),
                                   total_carrito=_get_total_carrito(),
                                   costo_envio=get_costo_envio(),
                                   request_form=form_data_on_error,
                                   carrito=session.get('carrito', {}))

        items_pedido_para_db = []
        costo_total_pedido = costo_envio_aplicado
        for item_id, item_data in session['carrito'].items():
            plato = next((p for p in platos_db if str(p['id_plato']) == item_id), None)
            if plato:
                cantidad = item_data['cantidad']
                precio_unitario = plato['precio']
                items_pedido_para_db.append({"plato_id": plato['id_plato'], "cantidad": cantidad, "precio_unitario": precio_unitario})
                costo_total_pedido += (cantidad * precio_unitario)
            else:
                flash(f"Producto con ID {item_id} no encontrado en el catálogo. Por favor, revise su carrito.", "danger")
                session.pop('carrito', None)
                return redirect(url_for('hacer_pedido'))

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            fecha_creacion_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            horario_entrega_iso = horario_entrega_completo.strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute("""
                INSERT INTO pedidos (
                    cliente_nombre, cliente_apellido, direccion_entrega, es_envio,
                    horario_entrega, costo_envio, costo_total, forma_pago, estado_pago,
                    fecha_creacion, lat_cliente, lon_cliente, id_repartidor, id_empresa
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cliente_nombre, cliente_apellido, direccion_entrega, int(es_envio),
                horario_entrega_iso, costo_envio_aplicado,
                costo_total_pedido, forma_pago, "Pendiente",
                fecha_creacion_str, lat_cliente, lon_cliente,
                None, pedido_id_empresa
            ))
            id_nuevo_pedido = cursor.lastrowid

            for item in items_pedido_para_db:
                cursor.execute("""
                    INSERT INTO items_pedido (id_pedido, id_plato, cantidad, precio_unitario)
                    VALUES (?, ?, ?, ?)
                """, (id_nuevo_pedido, item["plato_id"], item["cantidad"], item["precio_unitario"]))

            conn.commit()
            flash(f"Pedido #{id_nuevo_pedido} realizado con éxito!", "success")
            session.pop('carrito', None)
            return redirect(url_for('pedido_confirmacion', id_pedido=id_nuevo_pedido))

        except sqlite3.Error as e:
            conn.rollback()
            flash(f"Error al guardar el pedido: {e}", "danger")
            return render_template('hacer_pedido.html',
                                   platos=platos_db,
                                   franjas_horarias=_generar_franjas_horarias_disponibles(company_id_for_frontend),
                                   carrito_detalle=_get_carrito_detalle(platos_db),
                                   total_carrito=_get_total_carrito(),
                                   costo_envio=get_costo_envio(),
                                   request_form=form_data_on_error,
                                   carrito=session.get('carrito', {}))
        finally:
            conn.close()

    franjas_horarias = _generar_franjas_horarias_disponibles(company_id_for_frontend)

    return render_template('hacer_pedido.html',
                           platos=platos_db,
                           franjas_horarias=franjas_horarias,
                           carrito_detalle=_get_carrito_detalle(platos_db),
                           total_carrito=_get_total_carrito(),
                           costo_envio=get_costo_envio(),
                           request_form={},
                           carrito=session.get('carrito', {}))


# --- FUNCIONES AUXILIARES PARA EL CARRO (PARA RECARGAS CON ERRORES) ---
def _get_carrito_detalle(platos_db):
    """
    Genera el detalle del carrito para la plantilla, útil para recargas con errores.
    """
    carrito_detalle = []
    if 'carrito' in session and session['carrito']:
        for item_id, item_data in session['carrito'].items():
            plato = next((p for p in platos_db if str(p['id_plato']) == item_id), None)
            if plato:
                subtotal = plato['precio'] * item_data['cantidad']
                carrito_detalle.append({
                    'id_plato': plato['id_plato'],
                    'nombre': plato['nombre'],
                    'precio_unitario': plato['precio'],
                    'cantidad': item_data['cantidad'],
                    'subtotal': subtotal,
                    'rubro': plato['rubro'] 
                })
    return carrito_detalle

def _get_total_carrito():
    """
    Calcula el total de los productos en el carrito, útil para recargas con errores.
    """
    total = 0.0
    if 'carrito' in session:
        for item_data in session['carrito'].values():
            total += item_data.get('precio', 0.0) * item_data.get('cantidad', 0)
    return total
# ---------------------------------------------------------------------------

@app.route('/pedido_confirmacion/<int:id_pedido>')
def pedido_confirmacion(id_pedido):
    """Muestra la confirmación del pedido y el ticket para imprimir."""
    pedido = _obtener_pedido_completo_por_id(id_pedido)
    if not pedido:
        flash("Pedido no encontrado.", "danger")
        return redirect(url_for('index'))

    ticket_html = pedido.generar_ticket()
    return render_template('pedido_confirmacion.html', pedido=pedido, ticket_html=ticket_html, admin_view=True)

# --- Rutas de API para el Carrito (AJAX) ---

@app.route('/api/add_to_cart/<int:plato_id>', methods=['POST'])
def add_to_cart(plato_id):
    """Añade un plato al carrito de la sesión, respetando la empresa del contexto del frontend."""
    cantidad = int(request.form.get('cantidad', 1))
    if cantidad <= 0:
        return jsonify({"success": False, "message": "La cantidad debe ser un número positivo"}), 400

    company_id_for_frontend = get_company_id_for_frontend_context()

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id_plato, nombre, precio, rubro FROM platos WHERE id_plato = ? AND activo = 1 AND id_empresa = ?",
                   (plato_id, company_id_for_frontend))
    plato = cursor.fetchone()
    conn.close()

    if plato:
        if 'carrito' not in session:
            session['carrito'] = {}

        plato_id_str = str(plato['id_plato'])
        if plato_id_str in session['carrito']:
            session['carrito'][plato_id_str]['cantidad'] += cantidad
        else:
            session['carrito'][plato_id_str] = {
                'nombre': plato['nombre'],
                'precio': plato['precio'],
                'cantidad': cantidad,
                'rubro': plato['rubro'] 
            }
        session.modified = True

        total_items = sum(item['cantidad'] for item in session['carrito'].values())
        return jsonify({"success": True, "message": f"{plato['nombre']} agregado al carrito.", "total_items": total_items})
    return jsonify({"success": False, "message": "Plato no encontrado o inactivo"}), 404

@app.route('/api/remove_from_cart/<int:plato_id>', methods=['POST'])
def remove_from_cart(plato_id):
    """Elimina un plato específico del carrito de la sesión."""
    if 'carrito' in session:
        plato_id_str = str(plato_id)
        if plato_id_str in session['carrito']:
            del session['carrito'][plato_id_str]
            session.modified = True
            total_items = sum(item['cantidad'] for item in session['carrito'].values())
            return jsonify({"success": True, "message": "Ítem eliminado del carrito.", "total_items": total_items})
    return jsonify({"success": False, "message": "Ítem no encontrado en el carrito"}), 404

@app.route('/api/update_cart_quantity/<int:plato_id>', methods=['POST'])
def update_cart_quantity(plato_id):
    """
    Actualiza la cantidad de un plato en el carrito de la sesión.
    Si la cantidad es 0, elimina el plato. Si el plato no existe y la cantidad > 0, lo añade.
    """
    cantidad = request.form.get('cantidad')
    
    if cantidad is None:
        current_app.logger.warning(f"Request for plato_id {plato_id} missing 'cantidad' in form data.")
        return jsonify({"success": False, "message": "Falta el campo 'cantidad'."}), 400
        
    try:
        cantidad = int(cantidad)
    except ValueError:
        current_app.logger.warning(f"Request for plato_id {plato_id} received invalid 'cantidad': {cantidad}")
        return jsonify({"success": False, "message": "El valor de 'cantidad' debe ser un número entero."}), 400

    plato_id_str = str(plato_id)

    if 'carrito' not in session:
        session['carrito'] = {}
        current_app.logger.debug("Carrito inicializado en la sesión.")

    if cantidad <= 0:
        if plato_id_str in session['carrito']:
            del session['carrito'][plato_id_str]
            session.modified = True
            current_app.logger.info(f"Plato {plato_id_str} eliminado del carrito. Cantidad <= 0.")
            return jsonify({"success": True, "message": "Ítem eliminado del carrito."})
        else:
            current_app.logger.info(f"Intento de eliminar plato {plato_id_str} (cantidad 0) que no está en el carrito.")
            return jsonify({"success": True, "message": "Ítem no encontrado en el carrito (no se pudo eliminar), pero la cantidad es 0."})

    if plato_id_str in session['carrito']:
        session['carrito'][plato_id_str]['cantidad'] = cantidad
        session.modified = True
        current_app.logger.info(f"Cantidad del plato {plato_id_str} actualizada a {cantidad}.")
        return jsonify({"success": True, "message": "Cantidad actualizada."})
    else:
        current_app.logger.info(f"Intentando añadir plato {plato_id_str} al carrito con cantidad {cantidad}.")
        
        try:
            company_id_for_frontend = get_company_id_for_frontend_context()
        except NameError:
            current_app.logger.error("Function 'get_company_id_for_frontend_context' is not defined.")
            return jsonify({"success": False, "message": "Error interno: Función de empresa no definida."}), 500
        except Exception as e:
            current_app.logger.error(f"Error getting company_id_for_frontend_context: {e}")
            return jsonify({"success": False, "message": "Error interno al obtener contexto de empresa."}), 500

        conn = None
        try:
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id_plato, nombre, precio, rubro FROM platos WHERE id_plato = ? AND activo = 1 AND id_empresa = ?",
                           (plato_id, company_id_for_frontend))
            plato_data = cursor.fetchone()
            
            if plato_data:
                session['carrito'][plato_id_str] = {
                    'nombre': plato_data['nombre'],
                    'precio': plato_data['precio'],
                    'cantidad': cantidad,
                    'rubro': plato_data['rubro']
                }
                session.modified = True
                current_app.logger.info(f"Plato {plato_data['nombre']} (ID: {plato_id_str}) añadido al carrito.")
                return jsonify({"success": True, "message": f"{plato_data['nombre']} añadido al carrito."})
            else:
                current_app.logger.warning(f"Plato {plato_id_str} no encontrado, inactivo o no pertenece a la empresa {company_id_for_frontend}.")
                return jsonify({"success": False, "message": "Plato no encontrado o inactivo."}), 404
        except Exception as e:
            current_app.logger.error(f"Error al conectar o consultar la base de datos para plato {plato_id_str}: {e}")
            return jsonify({"success": False, "message": "Error interno al procesar la solicitud."}), 500
        finally:
            if conn:
                conn.close()

@app.route('/api/get_cart_status', methods=['GET'])
def get_cart_status():
    """Retorna el número total de ítems y el precio total actual del carrito."""
    total_items = sum(item['cantidad'] for item in session.get('carrito', {}).values())
    total_precio = 0
    if 'carrito' in session:
        for item_data in session['carrito'].values():
            total_precio += item_data.get('precio', 0.0) * item_data.get('cantidad', 0)

    return jsonify({"success": True, "total_items": total_items, "total_precio": total_precio})

@app.route('/api/clear_cart', methods=['POST'])
def clear_cart():
    """Limpia completamente el carrito de la sesión."""
    session.pop('carrito', None)
    session.modified = True
    return jsonify({"success": True, "message": "Carrito vaciado.", "total_items": 0})


# --- Rutas de Administración/Gestión ---

@app.route('/gestion/pedidos')
@login_required
def gestion_pedidos():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa') or current_user.has_role('empleado')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()

    base_query = """
        SELECT p.id_pedido, p.cliente_nombre, p.cliente_apellido, p.direccion_entrega, p.horario_entrega,
               p.forma_pago, p.costo_total, p.estado_pago, p.es_envio,
               r.nombre AS repartidor_nombre, r.apellido AS repartidor_apellido,
               e.nombre AS nombre_empresa
        FROM pedidos p
        LEFT JOIN repartidores r ON p.id_repartidor = r.id_repartidor
        LEFT JOIN empresas e ON p.id_empresa = e.id_empresa
    """
    where_conditions, query_params = get_company_filter_conditions_and_params(table_alias='p')
    
    final_query_parts = [base_query]
    if where_conditions:
        final_query_parts.append("WHERE " + " AND ".join(where_conditions))
    
    final_query_parts.append("ORDER BY p.horario_entrega DESC")
    
    final_query = " ".join(final_query_parts)

    cursor.execute(final_query, query_params)
    pedidos = cursor.fetchall()
    conn.close()

    pedidos_procesados = []
    for p in pedidos:
        p_dict = dict(p)
        p_dict['horario_entrega_dt'] = datetime.strptime(p_dict['horario_entrega'], '%Y-%m-%d %H:%M:%S')
        pedidos_procesados.append(p_dict)

    conn = conectar_db()
    cursor = conn.cursor()
    base_repartidores_query = "SELECT id_repartidor, nombre, apellido, activo FROM repartidores"
    where_rep_conditions, query_rep_params = get_company_filter_conditions_and_params() # No table_alias for repartidores directly
    
    final_rep_query_parts = [base_repartidores_query]
    if where_rep_conditions:
        final_rep_query_parts.append("WHERE " + " AND ".join(where_rep_conditions))
    
    final_rep_query_parts.append("ORDER BY nombre, apellido")
    final_rep_query = " ".join(final_rep_query_parts)

    cursor.execute(final_rep_query, query_rep_params)
    repartidores = cursor.fetchall()
    conn.close()

    print(f"Repartidores cargados para gestión: {repartidores}")

    return render_template('gestion_pedidos.html',
                           pedidos=pedidos_procesados,
                           repartidores=repartidores)

@app.route('/gestion/pedido/<int:id_pedido>/detalle')
@login_required
def detalle_pedido(id_pedido):
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa') or current_user.has_role('empleado')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    pedido = _obtener_pedido_completo_por_id(id_pedido)
    if not pedido:
        flash("Pedido no encontrado.", "danger")
        return redirect(url_for('gestion_pedidos'))

    ticket_html = pedido.generar_ticket()
    return render_template('pedido_confirmacion.html', pedido=pedido, ticket_html=ticket_html, admin_view=True)

@app.route('/gestion/pedido/<int:id_pedido>/asignar_repartidor', methods=['POST'])
@login_required
def asignar_repartidor(id_pedido):
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_pedidos'))

    id_repartidor = request.form.get('id_repartidor')
    if not id_repartidor:
        flash("Debe seleccionar un repartidor.", "danger")
        return redirect(url_for('gestion_pedidos'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        update_query_base = "UPDATE pedidos SET id_repartidor = ?"
        update_where_conditions = ["id_pedido = ?"]
        update_params = [id_repartidor, id_pedido]

        company_conditions, company_params = get_company_filter_conditions_and_params()
        update_where_conditions.extend(company_conditions)
        update_params.extend(company_params)

        final_update_query = update_query_base + " WHERE " + " AND ".join(update_where_conditions)

        cursor.execute(final_update_query, update_params)

        if cursor.rowcount == 0 and not current_user.has_role('super_admin'):
             flash("Pedido no encontrado o no tienes permiso para asignarle un repartidor.", "danger")
             conn.rollback()
             return redirect(url_for('gestion_pedidos'))

        conn.commit()
        flash(f"Repartidor asignado al pedido #{id_pedido} con éxito.", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"Error al asignar repartidor: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('gestion_pedidos'))


@app.route('/gestion/pedido/<int:id_pedido>/marcar_pagado', methods=['POST'])
@login_required
def marcar_pedido_pagado(id_pedido):
    """
    Marca un pedido como 'Pagado' en la base de datos y registra un ingreso en la caja.
    Si es un envío, registra el egreso al repartidor.
    """
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa') or current_user.has_role('empleado')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('index'))

    pedido = _obtener_pedido_completo_por_id(id_pedido)
    if not pedido:
        flash(f"Pedido con ID {id_pedido} no encontrado o no tienes permiso para verlo.", "danger")
        return redirect(url_for('gestion_pedidos'))

    if pedido.estado_pago == 'Pagado':
        flash(f"El pedido #{id_pedido} ya está marcado como pagado.", "warning")
        return redirect(url_for('gestion_pedidos'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        fecha_pago_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        update_query_base = "UPDATE pedidos SET estado_pago = 'Pagado', fecha_pago = ?"
        update_where_conditions = ["id_pedido = ?"]
        update_params_pedido = [fecha_pago_str, id_pedido]
        
        company_conditions, company_params = get_company_filter_conditions_and_params()
        update_where_conditions.extend(company_conditions)
        update_params_pedido.extend(company_params)

        final_update_query = update_query_base + " WHERE " + " AND ".join(update_where_conditions)
        cursor.execute(final_update_query, update_params_pedido)


        if cursor.rowcount == 0 and not current_user.has_role('super_admin'):
            flash("Pedido no encontrado o no tienes permiso para marcarlo como pagado.", "danger")
            conn.rollback()
            return redirect(url_for('gestion_pedidos'))

        cursor.execute("""
            INSERT INTO ingresos_egresos (tipo, monto, descripcion, fecha_hora, id_pedido_origen, id_repartidor_origen, id_empresa)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
        """, ('Ingreso', pedido.costo_total, f"Pago de Pedido #{id_pedido} ({pedido.forma_pago})", fecha_pago_str, pedido.id_pedido, pedido.id_empresa))

        if pedido.es_envio and pedido.id_repartidor:
            pago_repartidor = get_pago_repartidor_por_envio()
            cursor.execute("""
                INSERT INTO ingresos_egresos (tipo, monto, descripcion, fecha_hora, id_pedido_origen, id_repartidor_origen, id_empresa)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('Pago a Repartidor', pago_repartidor, f"Pago por envío Pedido #{id_pedido}", fecha_pago_str, pedido.id_pedido, pedido.id_repartidor, pedido.id_empresa))
            flash(f"Se registró un pago de ${pago_repartidor:,.2f} al repartidor por este envío.", "info")

        conn.commit()
        flash(f"Pedido #{id_pedido} marcado como pagado y registrado como ingreso.", "success")

    except sqlite3.Error as e:
        conn.rollback()
        flash(f"Error al marcar el pedido como pagado: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('gestion_pedidos'))

@app.route('/gestion/catalogo')
@login_required
def gestion_catalogo():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa') or current_user.has_role('empleado')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()

    base_query = "SELECT id_plato, nombre, descripcion, precio, activo, id_empresa, rubro FROM platos"
    where_conditions, query_params = get_company_filter_conditions_and_params()
    
    final_query_parts = [base_query]
    if where_conditions:
        final_query_parts.append("WHERE " + " AND ".join(where_conditions))
    
    final_query_parts.append("ORDER BY id_plato ASC")
    final_query = " ".join(final_query_parts)

    cursor.execute(final_query, query_params)
    platos = cursor.fetchall()
    conn.close()
    return render_template('gestion_catalogo.html', platos=platos)

@app.route('/gestion/catalogo/agregar', methods=['GET', 'POST'])
@login_required
def agregar_plato():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_catalogo'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        rubro = request.form['rubro'].strip()
        try:
            precio = float(request.form['precio'].replace(',', '.'))
            if precio <= 0:
                flash("El precio debe ser un número positivo.", "danger")
                return render_template('agregar_plato.html', request_form=request.form.to_dict())
        except ValueError:
            flash("Precio inválido. Ingrese un número.", "danger")
            return render_template('agregar_plato.html', request_form=request.form.to_dict())

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            plato_id_empresa = current_user.id_empresa
            if current_user.has_role('super_admin'):
                plato_id_empresa = request.form.get('id_empresa_asignar')
                if not plato_id_empresa:
                    plato_id_empresa = DEFAULT_COMPANY_FOR_ORDERS
                else:
                    plato_id_empresa = int(plato_id_empresa)
                flash(f"Como Super Admin, el plato se ha asignado a la Empresa ID {plato_id_empresa}.", "info")
            elif not plato_id_empresa:
                 flash("Tu usuario no tiene una empresa asignada para agregar platos.", "danger")
                 return redirect(url_for('gestion_catalogo'))

            cursor.execute("INSERT INTO platos (nombre, descripcion, precio, activo, id_empresa, rubro) VALUES (?, ?, ?, 1, ?, ?)",
                           (nombre, descripcion, precio, plato_id_empresa, rubro))
            conn.commit()
            flash(f"Plato '{nombre}' agregado con éxito.", "success")
        except sqlite3.Error as e:
            flash(f"Error al agregar plato: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('gestion_catalogo'))

    empresas_disponibles = []
    if current_user.has_role('super_admin'):
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
        empresas_disponibles = cursor.fetchall()
        conn.close()

    return render_template('agregar_plato.html', empresas_disponibles=empresas_disponibles, request_form={})

@app.route('/gestion/catalogo/editar/<int:id_plato>', methods=['GET', 'POST'])
@login_required
def editar_plato(id_plato):
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_catalogo'))

    conn = conectar_db()
    cursor = conn.cursor()
    base_query = "SELECT id_plato, nombre, descripcion, precio, activo, id_empresa, rubro FROM platos"
    where_conditions = ["id_plato = ?"]
    query_params = [id_plato]

    company_conditions, company_params = get_company_filter_conditions_and_params()
    where_conditions.extend(company_conditions)
    query_params.extend(company_params)

    final_query = base_query + " WHERE " + " AND ".join(where_conditions)

    cursor.execute(final_query, query_params)
    plato = cursor.fetchone()
    conn.close()

    if not plato:
        flash("Plato no encontrado o no tienes permiso para editarlo.", "danger")
        return redirect(url_for('gestion_catalogo'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        rubro = request.form['rubro'].strip()
        activo = 1 if 'activo' in request.form else 0
        try:
            precio = float(request.form['precio'].replace(',', '.'))
            if precio <= 0:
                flash("El precio debe ser un número positivo.", "danger")
                return render_template('editar_plato.html', id_plato=id_plato, plato=plato, request_form=request.form.to_dict())
        except ValueError:
            flash("Precio inválido. Ingrese un número.", "danger")
            return render_template('editar_plato.html', id_plato=id_plato, plato=plato, request_form=request.form.to_dict())

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            update_query_base = """
                UPDATE platos SET
                    nombre = ?,
                    descripcion = ?,
                    precio = ?,
                    activo = ?,
                    rubro = ?
            """
            update_where_conditions = ["id_plato = ?"]
            update_params = [nombre, descripcion, precio, activo, rubro, id_plato]

            company_conditions, company_params = get_company_filter_conditions_and_params()
            update_where_conditions.extend(company_conditions)
            update_params.extend(company_params)

            final_update_query = update_query_base + " WHERE " + " AND ".join(update_where_conditions)

            cursor.execute(final_update_query, update_params)
            if cursor.rowcount == 0 and not current_user.has_role('super_admin'):
                 flash("Plato no encontrado o no tienes permiso para editarlo.", "danger")
                 conn.rollback()
                 return redirect(url_for('gestion_catalogo'))

            conn.commit()
            flash(f"Plato '{nombre}' actualizado con éxito.", "success")
        except sqlite3.Error as e:
            flash(f"Error al editar plato: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('gestion_catalogo'))

    return render_template('editar_plato.html', plato=plato, request_form=plato)

@app.route('/gestion/catalogo/eliminar/<int:id_plato>', methods=['POST'])
@login_required
def eliminar_plato(id_plato):
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_catalogo'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        update_query_base = "UPDATE platos SET activo = 0"
        update_where_conditions = ["id_plato = ?"]
        update_params = [id_plato]

        company_conditions, company_params = get_company_filter_conditions_and_params()
        update_where_conditions.extend(company_conditions)
        update_params.extend(company_params)

        final_update_query = update_query_base + " WHERE " + " AND ".join(update_where_conditions)

        cursor.execute(final_update_query, update_params)
        if cursor.rowcount == 0 and not current_user.has_role('super_admin'):
             flash("Plato no encontrado o no tienes permiso para inactivarlo.", "danger")
             conn.rollback()
             return redirect(url_for('gestion_catalogo'))

        conn.commit()
        flash(f"Plato con ID {id_plato} marcado como inactivo.", "success")
    except sqlite3.Error as e:
        flash(f"Error al inactivar plato: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('gestion_catalogo'))

@app.route('/gestion/caja', methods=['GET', 'POST'])
@login_required
def arqueo_caja():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        if 'registrar_egreso' in request.form:
            try:
                monto = float(request.form['monto'].replace(',', '.'))
                if monto <= 0:
                    flash("El monto debe ser un número positivo.", "danger")
                    return redirect(url_for('arqueo_caja'))
                descripcion = request.form['descripcion'].strip()
                if not descripcion:
                    flash("La descripción del egreso no puede estar vacía.", "danger")
                    return redirect(url_for('arqueo_caja'))

                conn = conectar_db()
                cursor = conn.cursor()
                try:
                    fecha_hora_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    egreso_id_empresa = current_user.id_empresa
                    if current_user.has_role('super_admin'):
                        egreso_id_empresa = request.form.get('id_empresa_asignar_egreso')
                        if not egreso_id_empresa:
                            egreso_id_empresa = DEFAULT_COMPANY_FOR_ORDERS
                        else:
                            egreso_id_empresa = int(egreso_id_empresa)
                        flash(f"Como Super Admin, el egreso se ha asignado a la Empresa ID {egreso_id_empresa}.", "info")
                    elif not egreso_id_empresa:
                        flash("Tu usuario no tiene una empresa asignada para registrar egresos.", "danger")
                        return redirect(url_for('arqueo_caja'))

                    cursor.execute("""
                        INSERT INTO ingresos_egresos (tipo, monto, descripcion, fecha_hora, id_pedido_origen, id_repartidor_origen, id_empresa)
                        VALUES ('Egreso', ?, ?, ?, NULL, NULL, ?)
                    """, (monto, descripcion, fecha_hora_str, egreso_id_empresa))
                    conn.commit()
                    flash(f"Egreso de ${monto:,.2f} registrado con éxito.", "success")
                except sqlite3.Error as e:
                    flash(f"Error al registrar egreso: {e}", "danger")
                finally:
                    conn.close()
            except ValueError:
                flash("Monto inválido. Ingrese un número.", "danger")
            return redirect(url_for('arqueo_caja'))

        elif 'realizar_arqueo' in request.form:
            fecha_inicio_str = request.form['fecha_inicio'].strip()
            fecha_fin_str = request.form['fecha_fin'].strip()

            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)

                if fecha_inicio > fecha_fin:
                    flash("La fecha de inicio no puede ser posterior a la fecha de fin.", "danger")
                    return redirect(url_for('arqueo_caja'))

                conn = conectar_db()
                cursor = conn.cursor()

                fecha_inicio_iso = fecha_inicio.strftime('%Y-%m-%d %H:%M:%S')
                fecha_fin_iso = fecha_fin.strftime('%Y-%m-%d %H:%M:%S')

                base_query = """
                    SELECT ie.tipo, ie.monto, ie.descripcion, ie.fecha_hora, ie.id_pedido_origen,
                           r.nombre AS repartidor_nombre, r.apellido AS repartidor_apellido,
                           e.nombre AS nombre_empresa
                    FROM ingresos_egresos ie
                    LEFT JOIN repartidores r ON ie.id_repartidor_origen = r.id_repartidor
                    LEFT JOIN empresas e ON ie.id_empresa = e.id_empresa
                """
                where_conditions = ["ie.fecha_hora BETWEEN ? AND ?"]
                query_params = [fecha_inicio_iso, fecha_fin_iso]

                company_conditions, company_params = get_company_filter_conditions_and_params(table_alias='ie')
                where_conditions.extend(company_conditions)
                query_params.extend(company_params)

                final_query = base_query + " WHERE " + " AND ".join(where_conditions) + " ORDER BY ie.fecha_hora ASC"
                
                cursor.execute(final_query, query_params)
                movimientos = cursor.fetchall()
                conn.close()

                total_ingresos = sum(m['monto'] for m in movimientos if m['tipo'] == 'Ingreso')
                total_egresos = sum(m['monto'] for m in movimientos if m['tipo'] != 'Ingreso')
                balance = total_ingresos - total_egresos

                movimientos_procesados = []
                for m in movimientos:
                    m_dict = dict(m)
                    fecha_dt = datetime.strptime(m_dict['fecha_hora'], '%Y-%m-%d %H:%M:%S')
                    m_dict['fecha_hora_formateada'] = fecha_dt.strftime('%d/%m/%Y %H:%M')

                    if m_dict['repartidor_nombre'] and m_dict['repartidor_apellido']:
                        m_dict['repartidor_nombre_completo'] = f"{m_dict['repartidor_nombre']} {m_dict['repartidor_apellido']}"
                    else:
                        m_dict['repartidor_nombre_completo'] = None

                    movimientos_procesados.append(m_dict)

                session['arqueo_resultados'] = {
                    'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y'),
                    'fecha_fin': fecha_fin.strftime('%d/%m/%Y'),
                    'movimientos': movimientos_procesados,
                    'total_ingresos': total_ingresos,
                    'total_egresos': total_egresos,
                    'balance': balance
                }
                return redirect(url_for('arqueo_caja'))

            except ValueError:
                flash("Formato de fecha inválido. Use AAAA-MM-DD.", "danger")
                return redirect(url_for('arqueo_caja'))

    arqueo_resultados = session.pop('arqueo_resultados', None)

    empresas_para_egreso = []
    if current_user.has_role('super_admin'):
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
        empresas_para_egreso = cursor.fetchall()
        conn.close()

    return render_template('arqueo_caja.html',
                           arqueo_resultados=arqueo_resultados,
                           now=datetime.now(),
                           empresas_para_egreso=empresas_para_egreso)


@app.route('/gestion/configuracion', methods=['GET', 'POST'])
@login_required
def gestion_configuracion():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        config_id_empresa = None
        if current_user.has_role('admin_empresa') and current_user.id_empresa:
            config_id_empresa = current_user.id_empresa
        elif current_user.has_role('super_admin'):
            config_id_empresa_form = request.form.get('config_for_company')
            if config_id_empresa_form and config_id_empresa_form != 'global':
                config_id_empresa = int(config_id_empresa_form)

        if 'update_envio_costo' in request.form:
            try:
                nuevo_costo_envio = float(request.form['costo_envio'].replace(',', '.'))
                if nuevo_costo_envio < 0:
                    flash("El costo de envío no puede ser negativo.", "danger")
                else:
                    guardar_configuracion('ENVIO_COSTO', nuevo_costo_envio, config_id_empresa)
                    flash(f"Costo de envío actualizado a ${nuevo_costo_envio:,.2f} {'para tu empresa' if config_id_empresa else 'globalmente'}.", "success")
            except ValueError:
                flash("Valor de costo de envío inválido. Ingrese un número.", "danger")

        elif 'update_pago_repartidor' in request.form:
            try:
                nuevo_pago_repartidor = float(request.form['pago_repartidor_por_envio'].replace(',', '.'))
                if nuevo_pago_repartidor < 0:
                    flash("El pago al repartidor no puede ser negativo.", "danger")
                else:
                    guardar_configuracion('PAGO_REPARTIDOR_POR_ENVIO', nuevo_pago_repartidor, config_id_empresa)
                    flash(f"Pago por envío a repartidor actualizado a ${nuevo_pago_repartidor:,.2f} {'para tu empresa' if config_id_empresa else 'globalmente'}.", "success")
            except ValueError:
                flash("Valor de pago a repartidor inválido. Ingrese un número.", "danger")

        return redirect(url_for('gestion_configuracion'))

    costo_envio_actual = get_costo_envio()
    pago_repartidor_actual = get_pago_repartidor_por_envio()

    empresas_para_config = []
    if current_user.has_role('super_admin'):
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
        empresas_para_config = cursor.fetchall()
        conn.close()

    return render_template('gestion_configuracion.html',
                           costo_envio_actual=costo_envio_actual,
                           pago_repartidor_actual=pago_repartidor_actual,
                           empresas_para_config=empresas_para_config,
                           current_user_company_id=current_user.id_empresa if current_user.is_authenticated else None)

# --- RUTAS DE GESTIÓN DE REPARTIDORES ---
@app.route('/gestion/repartidores')
@login_required
def gestion_repartidores():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()

    base_query = "SELECT id_repartidor, nombre, apellido, telefono, activo, id_empresa FROM repartidores"
    where_conditions, query_params = get_company_filter_conditions_and_params()
    
    final_query_parts = [base_query]
    if where_conditions:
        final_query_parts.append("WHERE " + " AND ".join(where_conditions))
    
    final_query_parts.append("ORDER BY apellido, nombre")
    
    final_query = " ".join(final_query_parts)

    cursor.execute(final_query, query_params)
    repartidores = cursor.fetchall()
    conn.close()
    return render_template('gestion_repartidores.html', repartidores=repartidores)

@app.route('/gestion/repartidores/agregar', methods=['GET', 'POST'])
@login_required
def agregar_repartidor():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_repartidores'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        apellido = request.form['apellido'].strip()
        telefono = request.form['telefono'].strip()

        if not nombre or not apellido:
            flash("Nombre y apellido del repartidor son obligatorios.", "danger")
            return redirect(url_for('agregar_repartidor'))

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            repartidor_id_empresa = current_user.id_empresa
            if current_user.has_role('super_admin'):
                repartidor_id_empresa = request.form.get('id_empresa_asignar')
                if not repartidor_id_empresa:
                    repartidor_id_empresa = DEFAULT_COMPANY_FOR_ORDERS
                else:
                    repartidor_id_empresa = int(repartidor_id_empresa)
                flash(f"Como Super Admin, el repartidor se ha asignado a la Empresa ID {repartidor_id_empresa}.", "info")
            elif not repartidor_id_empresa:
                flash("Tu usuario no tiene una empresa asignada para agregar repartidores.", "danger")
                return redirect(url_for('gestion_repartidores'))

            cursor.execute("INSERT INTO repartidores (nombre, apellido, telefono, activo, id_empresa) VALUES (?, ?, ?, 1, ?)",
                           (nombre, apellido, telefono, repartidor_id_empresa))
            conn.commit()
            flash(f"Repartidor '{nombre} {apellido}' agregado con éxito.", "success")
        except sqlite3.Error as e:
            flash(f"Error al agregar repartidor: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('gestion_repartidores'))

    empresas_disponibles = []
    if current_user.has_role('super_admin'):
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
        empresas_disponibles = cursor.fetchall()
        conn.close()

    return render_template('agregar_repartidor.html', empresas_disponibles=empresas_disponibles)

@app.route('/gestion/repartidores/editar/<int:id_repartidor>', methods=['GET', 'POST'])
@login_required
def editar_repartidor(id_repartidor):
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_repartidores'))

    conn = conectar_db()
    cursor = conn.cursor()
    base_query = "SELECT id_repartidor, nombre, apellido, telefono, activo, id_empresa FROM repartidores"
    where_conditions = ["id_repartidor = ?"]
    query_params = [id_repartidor]

    company_conditions, company_params = get_company_filter_conditions_and_params()
    where_conditions.extend(company_conditions)
    query_params.extend(company_params)

    final_query = base_query + " WHERE " + " AND ".join(where_conditions)

    cursor.execute(final_query, query_params)
    repartidor = cursor.fetchone()
    conn.close()

    if not repartidor:
        flash("Repartidor no encontrado o no tienes permiso para editarlo.", "danger")
        return redirect(url_for('gestion_repartidores'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        apellido = request.form['apellido'].strip()
        telefono = request.form['telefono'].strip()
        activo = 1 if 'activo' in request.form else 0

        if not nombre or not apellido:
            flash("Nombre y apellido del repartidor son obligatorios.", "danger")
            return redirect(url_for('editar_repartidor', id_repartidor=id_repartidor))

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            update_query_base = """
                UPDATE repartidores SET
                    nombre = ?,
                    apellido = ?,
                    telefono = ?,
                    activo = ?
            """
            update_where_conditions = ["id_repartidor = ?"]
            update_params = [nombre, apellido, telefono, activo, id_repartidor]

            company_conditions, company_params = get_company_filter_conditions_and_params()
            update_where_conditions.extend(company_conditions)
            update_params.extend(company_params)

            final_update_query = update_query_base + " WHERE " + " AND ".join(update_where_conditions)

            cursor.execute(final_update_query, update_params)
            if cursor.rowcount == 0 and not current_user.has_role('super_admin'):
                 flash("Repartidor no encontrado o no tienes permiso para editarlo.", "danger")
                 conn.rollback()
                 return redirect(url_for('gestion_repartidores'))

            conn.commit()
            flash(f"Repartidor '{nombre} {apellido}' actualizado con éxito.", "success")
        except sqlite3.Error as e:
            flash(f"Error al editar repartidor: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('gestion_repartidores'))

    return render_template('editar_repartidor.html', repartidor=repartidor)

@app.route('/gestion/repartidores/eliminar/<int:id_repartidor>', methods=['POST'])
@login_required
def eliminar_repartidor(id_repartidor):
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_repartidores'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        update_query_base = "UPDATE repartidores SET activo = 0"
        update_where_conditions = ["id_repartidor = ?"]
        update_params = [id_repartidor]
        
        company_conditions, company_params = get_company_filter_conditions_and_params()
        update_where_conditions.extend(company_conditions)
        update_params.extend(company_params)

        final_update_query = update_query_base + " WHERE " + " AND ".join(update_where_conditions)

        cursor.execute(final_update_query, update_params)
        if cursor.rowcount == 0 and not current_user.has_role('super_admin'):
            flash("Repartidor no encontrado o no tienes permiso para inactivarlo.", "danger")
            conn.rollback()
            return redirect(url_for('gestion_repartidores'))

        conn.commit()
        flash(f"Repartidor con ID {id_repartidor} marcado como inactivo.", "success")
    except sqlite3.Error as e:
        flash(f"Error al inactivar repartidor: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('gestion_repartidores'))

@app.route('/gestion/reporte_repartidores', methods=['GET', 'POST'])
@login_required
def reporte_repartidores():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()
    base_repartidores_query = "SELECT id_repartidor, nombre, apellido FROM repartidores WHERE activo = 1"
    where_rep_conditions, query_rep_params = get_company_filter_conditions_and_params()
    
    final_rep_query_parts = [base_repartidores_query]
    if where_rep_conditions:
        final_rep_query_parts.append(" AND " + " AND ".join(where_rep_conditions)) # Note the ' AND ' here for filtering within an existing WHERE
    
    final_rep_query_parts.append("ORDER BY apellido, nombre")
    final_rep_query = " ".join(final_rep_query_parts)

    cursor.execute(final_rep_query, query_rep_params)
    repartidores_activos = cursor.fetchall()
    conn.close()

    reporte_generado = None
    if request.method == 'POST':
        id_repartidor_seleccionado = request.form.get('id_repartidor')
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')

        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)

            if fecha_inicio > fecha_fin:
                flash("La fecha de inicio no puede ser posterior a la fecha de fin.", "danger")
                return redirect(url_for('reporte_repartidores'))

            conn = conectar_db()
            cursor = conn.cursor()

            base_query = """
                SELECT ie.fecha_hora, ie.monto, ie.id_pedido_origen,
                       r.nombre AS repartidor_nombre, r.apellido AS repartidor_apellido,
                       e.nombre AS nombre_empresa
                FROM ingresos_egresos ie
                JOIN repartidores r ON ie.id_repartidor_origen = r.id_repartidor
                LEFT JOIN empresas e ON ie.id_empresa = e.id_empresa
            """
            where_conditions = ["ie.tipo = 'Pago a Repartidor'", "ie.fecha_hora BETWEEN ? AND ?"]
            query_params = [fecha_inicio.strftime('%Y-%m-%d %H:%M:%S'), fecha_fin.strftime('%Y-%m-%d %H:%M:%S')]

            if id_repartidor_seleccionado and id_repartidor_seleccionado != 'todos':
                where_conditions.append("ie.id_repartidor_origen = ?")
                query_params.append(id_repartidor_seleccionado)

            company_conditions, company_params = get_company_filter_conditions_and_params(table_alias='ie')
            where_conditions.extend(company_conditions)
            query_params.extend(company_params)

            final_query = base_query + " WHERE " + " AND ".join(where_conditions) + " ORDER BY ie.fecha_hora ASC"
            
            cursor.execute(final_query, query_params)
            pagos = cursor.fetchall()
            conn.close()

            total_pagado = sum(p['monto'] for p in pagos)

            repartidor_nombre_reporte = "Todos los Repartidores"
            if id_repartidor_seleccionado and id_repartidor_seleccionado != 'todos':
                for rep in repartidores_activos:
                    if str(rep['id_repartidor']) == id_repartidor_seleccionado:
                        repartidor_nombre_reporte = f"{rep['nombre']} {rep['apellido']}"
                        break

            pagos_procesados = []
            for p in pagos:
                p_dict = dict(p)
                p_dict['fecha_hora_formateada'] = datetime.strptime(p_dict['fecha_hora'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M')
                pagos_procesados.append(p_dict)


            reporte_generado = {
                'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y'),
                'fecha_fin': fecha_fin.strftime('%d/%m/%Y'),
                'repartidor_nombre': repartidor_nombre_reporte,
                'pagos': pagos_procesados,
                'total_pagado': total_pagado
            }

        except ValueError:
            flash("Formato de fecha inválido. Use AAAA-MM-DD.", "danger")
            return redirect(url_for('reporte_repartidores'))

    return render_template('reporte_repartidores.html',
                           repartidores=repartidores_activos,
                           reporte_generado=reporte_generado,
                           now=datetime.now())


# --- NUEVAS RUTAS DE GESTIÓN DE EMPRESAS Y USUARIOS (SUPER ADMIN) ---

@app.route('/gestion/empresas')
@login_required
def gestion_empresas():
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id_empresa, nombre, telefono, direccion, activo FROM empresas ORDER BY nombre")
    empresas = cursor.fetchall()
    conn.close()
    return render_template('gestion_empresas.html', empresas=empresas)

@app.route('/gestion/empresas/agregar', methods=['GET', 'POST'])
@login_required
def agregar_empresa():
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_empresas'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        telefono = request.form['telefono'].strip()
        direccion = request.form['direccion'].strip()

        if not nombre:
            flash("El nombre de la empresa es obligatorio.", "danger")
            return render_template('agregar_empresa.html', request_form=request.form.to_dict())

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO empresas (nombre, telefono, direccion, activo) VALUES (?, ?, ?, 1)",
                           (nombre, telefono, direccion))
            conn.commit()
            flash(f"Empresa '{nombre}' agregada con éxito.", "success")
        except sqlite3.IntegrityError:
            flash(f"Ya existe una empresa con el nombre '{nombre}'.", "danger")
            return render_template('agregar_empresa.html', request_form=request.form.to_dict())
        except sqlite3.Error as e:
            flash(f"Error al agregar empresa: {e}", "danger")
            return render_template('agregar_empresa.html', request_form=request.form.to_dict())
        finally:
            conn.close()
        return redirect(url_for('gestion_empresas'))
    return render_template('agregar_empresa.html', request_form={})

@app.route('/gestion/empresas/editar/<int:id_empresa>', methods=['GET', 'POST'])
@login_required
def edita_empresa(id_empresa):
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_empresas'))

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id_empresa, nombre, telefono, direccion, activo FROM empresas WHERE id_empresa = ?", (id_empresa,))
    empresa = cursor.fetchone()
    conn.close()

    if not empresa:
        flash("Empresa no encontrada.", "danger")
        return redirect(url_for('gestion_empresas'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        telefono = request.form['telefono'].strip()
        direccion = request.form['direccion'].strip()
        activo = 1 if 'activo' in request.form else 0

        if not nombre:
            flash("El nombre de la empresa es obligatorio.", "danger")
            return render_template('editar_empresa.html', empresa=empresa, request_form=request.form.to_dict())

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE empresas SET nombre = ?, telefono = ?, direccion = ?, activo = ? WHERE id_empresa = ?",
                           (nombre, telefono, direccion, activo, id_empresa))
            conn.commit()
            flash(f"Empresa '{nombre}' actualizada con éxito.", "success")
        except sqlite3.IntegrityError:
            flash(f"Ya existe una empresa con el nombre '{nombre}'.", "danger")
            return render_template('editar_empresa.html', empresa=empresa, request_form=request.form.to_dict())
        except sqlite3.Error as e:
            flash(f"Error al editar empresa: {e}", "danger")
            return render_template('editar_empresa.html', empresa=empresa, request_form=request.form.to_dict())
        finally:
            conn.close()
        return redirect(url_for('gestion_empresas'))

    return render_template('editar_empresa.html', empresa=empresa, request_form=empresa)

@app.route('/gestion/empresas/eliminar/<int:id_empresa>', methods=['POST'])
@login_required
def eliminar_empresa(id_empresa):
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_empresas'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE empresas SET activo = 0 WHERE id_empresa = ?", (id_empresa,))
        cursor.execute("UPDATE usuarios SET activo = 0 WHERE id_empresa = ?", (id_empresa,))

        conn.commit()
        flash(f"Empresa con ID {id_empresa} marcada como inactiva y sus usuarios asociados inactivados.", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"Error al inactivar empresa: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('gestion_empresas'))


@app.route('/gestion/usuarios')
@login_required
def gestion_usuarios():
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id_usuario, u.email, u.nombre, u.apellido, u.activo, u.primer_login_requerido,
               r.nombre_rol, e.nombre AS nombre_empresa
        FROM usuarios u
        JOIN roles r ON u.id_rol = r.id_rol
        LEFT JOIN empresas e ON u.id_empresa = e.id_empresa
        ORDER BY u.apellido, u.nombre
    """)
    usuarios = cursor.fetchall()
    conn.close()
    return render_template('gestion_usuarios.html', usuarios=usuarios)


@app.route('/gestion/usuarios/agregar', methods=['GET', 'POST'])
@login_required
def agregar_usuario():
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_usuarios'))

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id_rol, nombre_rol FROM roles ORDER BY nombre_rol")
    roles = cursor.fetchall()
    cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
    empresas = cursor.fetchall()
    conn.close()

    if request.method == 'POST':
        email = request.form['email'].strip()
        nombre = request.form['nombre'].strip()
        apellido = request.form['apellido'].strip()
        id_rol = request.form['id_rol']
        id_empresa = request.form.get('id_empresa')
        password_inicial = request.form['password_inicial']
        primer_login_requerido = 1 if 'primer_login_requerido' in request.form else 0

        if not all([email, nombre, apellido, id_rol, password_inicial]):
            flash("Todos los campos obligatorios deben ser completados.", "danger")
            return render_template('agregar_usuario.html', roles=roles, empresas=empresas, request_form=request.form)

        if id_empresa == '':
            id_empresa = None
        else:
            id_empresa = int(id_empresa)

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            hashed_password = generate_password_hash(password_inicial, method='pbkdf2:sha256')
            cursor.execute("""
                INSERT INTO usuarios (email, password, nombre, apellido, id_rol, id_empresa, activo, primer_login_requerido)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """, (email, hashed_password, nombre, apellido, id_rol, id_empresa, primer_login_requerido))
            conn.commit()
            flash(f"Usuario '{email}' agregado con éxito. Contraseña inicial: {password_inicial}", "success")
        except sqlite3.IntegrityError:
            flash(f"Ya existe un usuario con el email '{email}'.", "danger")
            return render_template('agregar_usuario.html', roles=roles, empresas=empresas, request_form=request.form)
        except sqlite3.Error as e:
            flash(f"Error al agregar usuario: {e}", "danger")
            return render_template('agregar_usuario.html', roles=roles, empresas=empresas, request_form=request.form)
        finally:
            conn.close()
        return redirect(url_for('gestion_usuarios'))

    return render_template('agregar_usuario.html', roles=roles, empresas=empresas, request_form={})

@app.route('/gestion/usuarios/editar/<int:id_usuario>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id_usuario):
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para acceder a esta página.", "danger")
        return redirect(url_for('gestion_usuarios'))

    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id_usuario, u.email, u.nombre, u.apellido, u.activo, u.primer_login_requerido,
               u.id_rol, u.id_empresa
        FROM usuarios u
        WHERE u.id_usuario = ?
    """, (id_usuario,))
    usuario = cursor.fetchone()

    if not usuario:
        flash("Usuario no encontrado.", "danger")
        conn.close()
        return redirect(url_for('gestion_usuarios'))

    cursor.execute("SELECT id_rol, nombre_rol FROM roles ORDER BY nombre_rol")
    roles = cursor.fetchall()
    cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
    empresas = cursor.fetchall()
    conn.close()

    if request.method == 'POST':
        email = request.form['email'].strip()
        nombre = request.form['nombre'].strip()
        apellido = request.form['apellido'].strip()
        id_rol = request.form['id_rol']
        id_empresa = request.form.get('id_empresa')
        activo = 1 if 'activo' in request.form else 0
        primer_login_requerido = 1 if 'primer_login_requerido' in request.form else 0
        nueva_password = request.form.get('nueva_password', '').strip()

        if not all([email, nombre, apellido, id_rol]):
            flash("Todos los campos obligatorios deben ser completados.", "danger")
            return render_template('editar_usuario.html', usuario=usuario, roles=roles, empresas=empresas, request_form=request.form)

        if id_empresa == '':
            id_empresa = None
        else:
            id_empresa = int(id_empresa)

        conn = conectar_db()
        cursor = conn.cursor()
        try:
            update_query = """
                UPDATE usuarios SET email = ?, nombre = ?, apellido = ?, id_rol = ?,
                id_empresa = ?, activo = ?, primer_login_requerido = ?
            """
            update_params = [email, nombre, apellido, id_rol, id_empresa, activo, primer_login_requerido]

            if nueva_password:
                hashed_password = generate_password_hash(nueva_password, method='pbkdf2:sha256')
                update_query += ", password = ?"
                update_params.append(hashed_password)
                flash("Contraseña actualizada.", "info")

            update_query += " WHERE id_usuario = ?"
            update_params.append(id_usuario)

            cursor.execute(update_query, tuple(update_params))
            conn.commit()
            flash(f"Usuario '{email}' actualizado con éxito.", "success")
        except sqlite3.IntegrityError:
            flash(f"Ya existe un usuario con el email '{email}'.", "danger")
            return render_template('editar_usuario.html', usuario=usuario, roles=roles, empresas=empresas, request_form=request.form)
        except sqlite3.Error as e:
            flash(f"Error al actualizar usuario: {e}", "danger")
            return render_template('editar_usuario.html', usuario=usuario, roles=roles, empresas=empresas, request_form=request.form)
        finally:
            conn.close()
        return redirect(url_for('gestion_usuarios'))

    return render_template('editar_usuario.html', usuario=usuario, roles=roles, empresas=empresas, request_form=usuario)

@app.route('/gestion/usuarios/eliminar/<int:id_usuario>', methods=['POST'])
@login_required
def eliminar_usuario(id_usuario):
    if not current_user.has_role('super_admin'):
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for('gestion_usuarios'))

    if id_usuario == current_user.id:
        flash("No puedes eliminar tu propio usuario mientras estás conectado.", "danger")
        return redirect(url_for('gestion_usuarios'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE usuarios SET activo = 0 WHERE id_usuario = ?", (id_usuario,))
        conn.commit()
        flash(f"Usuario con ID {id_usuario} marcado como inactivo.", "success")
    except sqlite3.Error as e:
        flash(f"Error al inactivar usuario: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('gestion_usuarios'))


# --- FUNCIONES PARA REPORTES DE VENTAS ---

def _get_company_id_for_report(selected_company_id_str):
    """Determina el ID de la empresa para filtrar los reportes."""
    if current_user.has_role('super_admin'):
        if selected_company_id_str and selected_company_id_str != 'all':
            return int(selected_company_id_str)
        return None # Para super_admin, None significa todas las empresas
    return current_user.id_empresa # Para admin_empresa, siempre su propia empresa

def _fetch_report_data(start_date_str, end_date_str, company_id):
    """
    Función central para ejecutar todas las consultas de reportes.
    Retorna un diccionario con todos los datos.
    """
    report_data = {
        'top_selling_by_rubro': [],
        'top_selling_overall': [],
        'most_used_payment_methods': [],
        'total_quantity_per_product_overall': [] 
    }

    if not start_date_str or not end_date_str:
        return report_data

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        current_app.logger.error(f"Error de formato de fecha en reporte: {start_date_str} - {end_date_str}")
        return report_data

    conn = conectar_db()
    cursor = conn.cursor()

    params_base_dates = [start_date.strftime('%Y-%m-%d %H:%M:%S'), end_date.strftime('%Y-%m-%d %H:%M:%S')]
    
    # Obtener condiciones de filtro de empresa una sola vez para 'pedidos' (p)
    company_conditions_p, company_params_p = get_company_filter_conditions_and_params(table_alias='p')

    # Combinar condiciones base de fecha con las de empresa
    base_where_conditions = ["p.fecha_creacion BETWEEN ? AND ?"] + company_conditions_p
    base_query_params = params_base_dates + company_params_p


    # 1. Productos más vendidos por rubro (SUMADO por rubro)
    query_by_rubro = f"""
        SELECT pl.rubro, SUM(ip.cantidad) AS total_cantidad_vendida
        FROM items_pedido ip
        JOIN platos pl ON ip.id_plato = pl.id_plato
        JOIN pedidos p ON ip.id_pedido = p.id_pedido
        WHERE {' AND '.join(base_where_conditions)}
        GROUP BY pl.rubro
        ORDER BY total_cantidad_vendida DESC
    """
    cursor.execute(query_by_rubro, base_query_params)
    report_data['top_selling_by_rubro'] = cursor.fetchall()

    # 2. Productos más vendidos en total (general) / Cantidad total vendida de cada producto
    query_overall_products = f"""
        SELECT pl.nombre, pl.rubro, SUM(ip.cantidad) AS total_cantidad_vendida
        FROM items_pedido ip
        JOIN platos pl ON ip.id_plato = pl.id_plato
        JOIN pedidos p ON ip.id_pedido = p.id_pedido
        WHERE {' AND '.join(base_where_conditions)}
        GROUP BY pl.id_plato, pl.nombre, pl.rubro
        ORDER BY total_cantidad_vendida DESC
    """
    cursor.execute(query_overall_products, base_query_params)
    report_data['top_selling_overall'] = cursor.fetchall()
    report_data['total_quantity_per_product_overall'] = report_data['top_selling_overall'] # Reutiliza los datos

    # 3. Medios de pago más usados
    query_payment_methods = f"""
        SELECT forma_pago, COUNT(*) AS total_usos, SUM(costo_total) AS total_monto
        FROM pedidos p
        WHERE {' AND '.join(base_where_conditions)}
        GROUP BY forma_pago
        ORDER BY total_usos DESC
    """
    cursor.execute(query_payment_methods, base_query_params)
    report_data['most_used_payment_methods'] = cursor.fetchall()

    conn.close()
    return report_data

@app.route('/gestion/reportes/ventas', methods=['GET', 'POST'])
@login_required
def reportes_ventas():
    if not (current_user.has_role('super_admin') or current_user.has_role('admin_empresa')):
        flash("No tienes permiso para acceder a esta página de reportes.", "danger")
        return redirect(url_for('index'))

    start_date = request.form.get('fecha_inicio', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.form.get('fecha_fin', datetime.now().strftime('%Y-%m-%d'))
    
    empresas_disponibles = []
    selected_company_id = None
    selected_company_id_str = request.form.get('id_empresa_reporte')

    if current_user.has_role('super_admin'):
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id_empresa, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
        empresas_disponibles = cursor.fetchall()
        conn.close()
        
        if selected_company_id_str and selected_company_id_str != 'all':
            try:
                selected_company_id = int(selected_company_id_str)
            except ValueError:
                flash("ID de empresa seleccionada inválida.", "danger")
                selected_company_id = None 
        elif selected_company_id_str == 'all':
            selected_company_id = None 
        else:
            selected_company_id = None 
    else: 
        selected_company_id = current_user.id_empresa
        selected_company_id_str = str(current_user.id_empresa)


    reportes_generados = None
    if request.method == 'POST':
        if not start_date or not end_date:
            flash("Debe seleccionar ambas fechas (inicio y fin) para generar el reporte.", "danger")
        else:
            try:
                datetime.strptime(start_date, '%Y-%m-%d')
                datetime.strptime(end_date, '%Y-%m-%d')

                reportes_generados = _fetch_report_data(start_date, end_date, selected_company_id)
                if not any(reportes_generados.values()):
                    flash("No se encontraron datos para el período y empresa seleccionados.", "info")
            except ValueError:
                flash("Formato de fecha inválido. Use AAAA-MM-DD.", "danger")
            except Exception as e:
                flash(f"Error al generar reportes: {e}", "danger")
                current_app.logger.error(f"Error generando reportes de ventas: {e}")

    return render_template('reportes_ventas.html',
                           start_date=start_date,
                           end_date=end_date,
                           reportes=reportes_generados,
                           empresas_disponibles=empresas_disponibles,
                           selected_company_id=selected_company_id_str)


if __name__ == '__main__':
    # --- SUGERENCIA: Descomenta las siguientes líneas si quieres forzar la recreación de la DB
    # --- Esto es útil para desarrollo cuando se hacen cambios en las tablas.
    # --- ADVERTENCIA: ¡Esto borrará todos tus datos actuales de la base de datos!
    # if os.path.exists(DB_NAME):
    #     os.remove(DB_NAME)
    #     print(f"Base de datos '{DB_NAME}' eliminada para recreación.")

    init_app()
    app.run(debug=True)