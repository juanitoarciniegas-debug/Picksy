import re
import time
from datetime import datetime, timezone

import httpx

from .base import Producto
from .vtex import CABECERAS

SITIO = "https://www.farmatodo.com.co"
SERVIDOR = "https://api-search.farmatodo.com"
INDICE = "products-colombia"
VIGENCIA_CONFIG = 6 * 3600   # releer la configuración cada 6 horas
PRECIO_MINIMO = 100          # descarta precios de relleno como $0 o $1

PATRON = re.compile(
    r"x-algolia-application-id=([A-Za-z0-9]+)(?:&|&amp;)x-algolia-api-key=([A-Za-z0-9]+)"
)


class ConectorFarmatodo:
    nombre = "Farmatodo"
    especialidad = "farmacia"

    def __init__(self):
        self._config = None
        self._config_en = 0.0

    def _obtener_config(self, forzar: bool = False) -> dict:
        vigente = self._config and (time.time() - self._config_en) < VIGENCIA_CONFIG
        if vigente and not forzar:
            return self._config

        r = httpx.get(SITIO, headers=CABECERAS, timeout=25, follow_redirects=True)
        r.raise_for_status()
        m = PATRON.search(r.text)
        if not m:
            raise ValueError("No se pudo leer la configuración de búsqueda de Farmatodo")
        self._config = {"app_id": m.group(1), "clave": m.group(2)}
        self._config_en = time.time()
        return self._config

    def _consultar(self, termino: str, cantidad: int) -> list:
        for intento in (1, 2):
            c = self._obtener_config(forzar=(intento == 2))
            r = httpx.post(
                f"{SERVIDOR}/1/indexes/{INDICE}/query",
                headers={
                    "X-Algolia-Application-Id": c["app_id"],
                    "X-Algolia-API-Key": c["clave"],
                    "Origin": SITIO,
                    "Referer": SITIO + "/",
                },
                json={"query": termino, "hitsPerPage": cantidad, "filters": "outofstore:false"},
                timeout=20,
            )
            if r.status_code in (401, 403) and intento == 1:
                continue  # la clave pudo cambiar: se vuelve a leer y se reintenta
            r.raise_for_status()
            return r.json().get("hits", [])
        return []

    def buscar(self, termino: str, limite: int = 20) -> list:
        ahora = datetime.now(timezone.utc)
        productos = []
        # se piden algunos de más porque parte se descarta (muestras, precios de relleno)
        for h in self._consultar(termino, limite + 10):
            try:
                if h.get("rms_class") == "SAMPLING":
                    continue  # muestras gratis, no son productos a la venta
                precio = self._precio(h)
                if precio is None:
                    continue
                nombre = (h.get("mediaDescription") or "").strip()
                fragmento = h.get("url") or ""
                if not nombre or not fragmento:
                    continue
                imagenes = h.get("listUrlImages") or []
                imagen = h.get("mediaImageUrl") or (imagenes[0] if imagenes else None)

                productos.append(Producto(
                    tienda=self.nombre,
                    nombre=nombre,
                    precio=precio,
                    envio=None,
                    disponible=not h.get("outofstore", False),
                    url=f"{SITIO}/producto/{fragmento}",  # formato por confirmar
                    imagen=imagen,
                    consultado_en=ahora,
                ))
            except Exception:
                continue  # un producto raro no tumba toda la tienda
            if len(productos) >= limite:
                break
        return productos

    @staticmethod
    def _precio(h: dict):
        normal = h.get("fullPrice") or 0
        oferta = h.get("offerPrice") or 0
        precio = oferta if 0 < oferta < normal else normal
        return float(precio) if precio >= PRECIO_MINIMO else None