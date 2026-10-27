from datetime import datetime, timezone

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
                url=p.get("link", ""),
                imagen=imagenes[0].get("imageUrl") if imagenes else None,
                consultado_en=ahora,
            ))
        return productos