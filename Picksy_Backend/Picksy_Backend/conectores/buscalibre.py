import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .base import Producto
from .vtex import CABECERAS

SITIO = "https://www.buscalibre.com.co"


def _a_pesos(texto: str):
    """'$ 33.000' -> 33000.0"""
    digitos = re.sub(r"[^\d]", "", texto or "")
    return float(digitos) if digitos else None


class ConectorBuscalibre:
    nombre = "Buscalibre"
    especialidad = "libros"

    def buscar(self, termino: str, limite: int = 20) -> list:
        r = httpx.get(
            f"{SITIO}/libros/search",
            params={"q": termino},
            headers=CABECERAS,
            timeout=25,
            follow_redirects=True,
        )
        r.raise_for_status()
        sopa = BeautifulSoup(r.text, "html.parser")

        ahora = datetime.now(timezone.utc)
        productos = []
        for tarjeta in sopa.select("div.box-producto"):
            try:
                enlace = tarjeta.find("a", href=True)
                precio_tag = tarjeta.select_one("div.box-precios strong")
                if enlace is None or precio_tag is None:
                    continue
                precio = _a_pesos(precio_tag.get_text())
                if not precio or precio <= 0:
                    continue

                titulo = tarjeta.select_one("h3.nombre")
                nombre = (titulo.get_text(strip=True) if titulo else enlace.get("title", "")).strip()
                if not nombre:
                    continue

                url = enlace["href"]
                if url.startswith("/"):
                    url = SITIO + url

                img = tarjeta.find("img")
                imagen = (img.get("data-src") or img.get("src")) if img else None

                productos.append(Producto(
                    tienda=self.nombre,
                    nombre=nombre,
                    precio=precio,
                    envio=None,
                    disponible=True,  # no hay marca de agotado en la lista
                    url=url,
                    imagen=imagen,
                    consultado_en=ahora,
                ))
            except Exception:
                continue  # una tarjeta rara no tumba toda la tienda
            if len(productos) >= limite:
                break
        return productos