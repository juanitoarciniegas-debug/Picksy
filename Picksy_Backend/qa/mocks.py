"""
mocks.py - Tiendas SIMULADAS para las pruebas.

Por qué existe: las pruebas rápidas NUNCA deben consultar tiendas reales (podrían
bloquear nuestra IP). Aquí se reemplaza el método `buscar` de cada conector real por
uno que devuelve productos falsos, controlados por la prueba.

Se reemplaza solo `buscar` de cada conector: el resto del sistema (caché, base de datos,
cálculo de totales, historial) sigue siendo el REAL. Así se prueba el código de Picksy,
no a las tiendas.
"""
import re
import time
from datetime import datetime, timezone

import buscador
from conectores.base import Producto


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def producto(tienda, nombre, precio, envio=0.0, disponible=True, n=1):
    """Crea un producto falso. La URL siempre empieza por https://qa.test/ para poder
    limpiarlo de la base de datos al terminar sin tocar datos reales."""
    return Producto(
        tienda=tienda,
        nombre=nombre,
        precio=float(precio),
        envio=None if envio is None else float(envio),
        disponible=disponible,
        url=f"https://qa.test/{_slug(tienda)}/{_slug(nombre)}-{n}",
        imagen=None,
        consultado_en=datetime.now(timezone.utc),
    )


class TiendasSimuladas:
    """Controla lo que 'responden' las tiendas durante una prueba."""

    def __init__(self, monkeypatch):
        self.catalogo = {}   # nombre de tienda -> lista de productos
        self.fallos = {}     # nombre de tienda -> excepción que lanza
        self.lentos = {}     # nombre de tienda -> segundos que tarda en responder
        self.llamadas = []   # (tienda, termino): sirve para saber si la caché evitó la consulta
        for conector in buscador.CONECTORES:
            monkeypatch.setattr(conector, "buscar", self._crear(conector.nombre))

    def _crear(self, nombre):
        def buscar(termino, limite=20):
            self.llamadas.append((nombre, termino))
            if nombre in self.lentos:
                time.sleep(self.lentos[nombre])
            if nombre in self.fallos:
                raise self.fallos[nombre]
            return list(self.catalogo.get(nombre, []))
        return buscar

    # --- atajos para escribir pruebas legibles ---
    def poner(self, tienda, *productos):
        self.catalogo[tienda] = list(productos)
        return self

    def hacer_fallar(self, tienda, error=None):
        self.fallos[tienda] = error or TimeoutError("tienda simulada caída")
        return self

    def hacer_lenta(self, tienda, segundos):
        self.lentos[tienda] = segundos
        return self

    def llamadas_a(self, termino_normalizado=None):
        if termino_normalizado is None:
            return list(self.llamadas)
        return [l for l in self.llamadas if l[1].lower().strip() == termino_normalizado]

    @property
    def nombres(self):
        return [c.nombre for c in buscador.CONECTORES]
