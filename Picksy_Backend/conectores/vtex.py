from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .base import Producto

CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-CO,es;q=0.9",
}


class ConectorVtex:
    def __init__(self, nombre: str, dominio: str):
        self.nombre = nombre
        self.dominio = dominio

    def _enlace(self, p: dict) -> str:
        """
        CAMBIO (enlace al producto): el campo "link" que devuelve VTEX a veces trae un dominio interno
        (por ejemplo ...vtexcommercestable.com.br) o viene vacío, y el botón «Ver en la tienda» no abría
        la publicación. Se toma solo la RUTA del enlace y se arma siempre con el dominio público de la tienda.
        """
        ruta = urlsplit((p.get("link") or "").strip()).path
        if not ruta or ruta == "/":
            texto = (p.get("linkText") or "").strip("/ ")
            ruta = f"/{texto}/p" if texto else ""
        return f"https://{self.dominio}{ruta}" if ruta else ""

    def buscar(self, termino: str, limite: int = 20) -> list:
        url = f"https://{self.dominio}/api/catalog_system/pub/products/search"
        parametros = {"ft": termino, "_from": 0, "_to": limite - 1}

        respuesta = httpx.get(
            url,
            params=parametros,
            headers=CABECERAS,
            timeout=20,
            follow_redirects=True,
        )
        respuesta.raise_for_status()  # si la tienda responde error, se lanza excepción
        datos = respuesta.json()

        ahora = datetime.now(timezone.utc)
        productos = []
        for p in datos:
            items = p.get("items") or []
            if not items:
                continue
            item = items[0]
            vendedores = item.get("sellers") or []
            if not vendedores:
                continue
            oferta = vendedores[0].get("commertialOffer", {})
            precio = oferta.get("Price")
            if precio is None or precio <= 0:
                continue  # sin precio válido no hay nada que comparar
            imagenes = item.get("images") or []

            productos.append(Producto(
                tienda=self.nombre,
                nombre=p.get("productName", "Sin nombre"),
                precio=float(precio),
                envio=None,  # pendiente: ver nota de abajo
                disponible=(oferta.get("AvailableQuantity") or 0) > 0,
                url=self._enlace(p),
                imagen=imagenes[0].get("imageUrl") if imagenes else None,
                consultado_en=ahora,
            ))
        return productos
