import re
import time
from datetime import datetime, timezone

import httpx

from .base import Producto
from .vtex import CABECERAS

VIGENCIA_CONFIG = 6 * 3600  # releer la configuración de la tienda cada 6 horas


def _valor(html: str, nombre: str):
    patron = nombre + r"""\s*['"]?\s*:\s*['"]([^'"]{3,})['"]"""
    m = re.search(patron, html)
    return m.group(1) if m else None


class ConectorAlgolia:
    """Sirve para Alkosto, Ktronix y Alkomprar (misma plataforma, distinto índice)."""

    def __init__(self, nombre: str, sitio: str):
        self.nombre = nombre
        self.sitio = sitio
        self._config = None
        self._config_en = 0.0

    def _obtener_config(self, forzar: bool = False) -> dict:
        vigente = self._config and (time.time() - self._config_en) < VIGENCIA_CONFIG
        if vigente and not forzar:
            return self._config

        r = httpx.get(
            f"{self.sitio}/search",
            params={"text": "audifonos"},  # la configuración viene en cualquier búsqueda
            headers=CABECERAS,
            timeout=25,
            follow_redirects=True,
        )
        r.raise_for_status()
        html = r.text
        config = {
            "app_id": _valor(html, "applicationId") or _valor(html, "appId"),
            "clave": _valor(html, "apiKey"),
            "indice": _valor(html, "indexName"),
        }
        if not all(config.values()):
            raise ValueError("No se pudo leer la configuración de búsqueda de la tienda")
        self._config = config
        self._config_en = time.time()
        return config

    def _consultar(self, termino: str, limite: int) -> list:
        for intento in (1, 2):
            c = self._obtener_config(forzar=(intento == 2))
            r = httpx.post(
                f"https://{c['app_id']}-dsn.algolia.net/1/indexes/{c['indice']}/query",
                headers={
                    "X-Algolia-Application-Id": c["app_id"],
                    "X-Algolia-API-Key": c["clave"],
                    "Referer": self.sitio + "/",
                    "Origin": self.sitio,
                },
                json={"query": termino, "hitsPerPage": limite},
                timeout=20,
            )
            if r.status_code in (401, 403) and intento == 1:
                continue  # la clave pudo vencer: se vuelve a leer y se reintenta
            r.raise_for_status()
            return r.json().get("hits", [])
        return []

    def buscar(self, termino: str, limite: int = 20) -> list:
        ahora = datetime.now(timezone.utc)
        productos = []
        for h in self._consultar(termino, limite):
            try:
                precio = self._precio(h)
                if precio is None:
                    continue
                url = h.get("url_es_string") or ""
                if url.startswith("/"):
                    url = self.sitio + url
                productos.append(Producto(
                    tienda=self.nombre,
                    nombre=h.get("name_text_es", "Sin nombre"),
                    precio=precio,
                    envio=None,
                    disponible=bool(h.get("instockflag_boolean")),
                    url=url,
                    imagen=h.get("img-310wx310h_string"),
                    consultado_en=ahora,
                ))
            except Exception:
                continue  # un producto raro no tumba toda la tienda
        return productos

    @staticmethod
    def _precio(h: dict):
        for campo in ("discountprice_double", "pricevalue_cop_double"):
            valor = h.get(campo)
            if isinstance(valor, (int, float)) and valor > 0:
                return float(valor)
        return None