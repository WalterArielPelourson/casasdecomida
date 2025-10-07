# casa_comida_web/models.py

from datetime import datetime

class Plato:
    def __init__(self, id_plato, nombre, descripcion, precio):
        self.id_plato = str(id_plato) # Asegurar que sea string para las claves de dict
        self.nombre = nombre
        self.descripcion = descripcion
        self.precio = precio

    def to_dict(self):
        return {
            "id_plato": self.id_plato,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "precio": self.precio
        }

class Pedido:
    def __init__(self, id_pedido, cliente_nombre, cliente_apellido, direccion_entrega, es_envio, horario_entrega_str):
        self.id_pedido = id_pedido
        self.cliente_nombre = cliente_nombre
        self.cliente_apellido = cliente_apellido
        self.direccion_entrega = direccion_entrega
        self.es_envio = es_envio
        # Almacenar como string y convertir a datetime al usar si es necesario
        self.horario_entrega_str = horario_entrega_str 
        self.items = []  # Lista de tuplas: (Plato, cantidad)
        self.costo_total = 0 # Se calcula al agregar items y finalizar

    def agregar_item(self, plato, cantidad):
        self.items.append({"plato": plato.to_dict(), "cantidad": cantidad}) # Almacenar como dict del plato
        
    def _calcular_costo_total(self, envio_costo):
        total = sum(item["plato"]["precio"] * item["cantidad"] for item in self.items)
        if self.es_envio:
            total += envio_costo
        self.costo_total = total

    def to_dict(self):
        return {
            "id_pedido": self.id_pedido,
            "cliente_nombre": self.cliente_nombre,
            "cliente_apellido": self.cliente_apellido,
            "direccion_entrega": self.direccion_entrega,
            "es_envio": self.es_envio,
            "horario_entrega_str": self.horario_entrega_str,
            "items": self.items,
            "costo_total": self.costo_total
        }