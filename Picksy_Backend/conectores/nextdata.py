import json
import re
from datetime import datetime, timezone

import httpx

from .base import Producto
from .vtex import CABECERAS

PATRON = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def descargar_datos(url: str, parametros: dict) -> dict:
    respuesta = httpx.get(
        url, params=parametros, headers=CABECERAS, timeout=25, follow_redirects=True
    )
    respuesta.raise_for_status()
    m = PATRON.search(respuesta.text)
    if not m:
        raise ValueError("La página no trae el bloque __NEXT_DATA__")
    return json.loads(m.group(1))


def entrar(datos, *ruta):
    """Baja por el diccionario siguiendo la ruta; avisa si algo cambió en la tienda."""
    for clave in ruta:
        if not isinstance(datos, dict) or clave not in datos:
            raise ValueError(f"La tienda cambió su estructura: falta '{clave}'")
        datos = datos[clave]
    return datos


def _numero(texto) -> float:
    return float(str(texto).replace(".", "").replace(",", "").strip())


# ---------------------------- HOMECENTER ----------------------------
class ConectorHomecenter:
    nombre = "Homecenter"

    def buscar(self, termino: str, limite: int = 20) -> list:
        datos = descargar_datos(
            "https://www.homecenter.com.co/homecenter-co/search", {"Ntt": termino}
        )
        lista = entrar(datos, "props", "pageProps", "searchProps", "searchData", "results")

        ahora = datetime.now(timezone.utc)
        productos = []
        for p in lista:
            try:
                precio = self._precio(p.get("prices"))
                if precio is None:
                    continue
                gratis = any(
                    "gratis" in str(e.get("description", "")).lower()
                    for e in (p.get("events") or [])
                )
                imagenes = p.get("mediaUrls") or []
                productos.append(Producto(
                    tienda=self.nombre,
                    nombre=p.get("displayName", "Sin nombre"),
                    precio=precio,
                    envio=0.0 if gratis else None,
                    disponible=True,  # el listado no informa agotados
                    url=f"https://www.homecenter.com.co/homecenter-co/product/{p.get('productId')}",
                    imagen=imagenes[0] if imagenes else None,
                    consultado_en=ahora,
                ))
            except Exception:
                continue  # un producto raro no tumba toda la tienda
            if len(productos) >= limite:
                break
        return productos

    @staticmethod
    def _precio(precios):
        elegido = None
        for pr in precios or []:
            valor = pr.get("priceWithoutFormatting")
            if valor is None:
                continue
            if pr.get("type") == "INTERNET":
                return float(valor)
            if elegido is None:
                elegido = float(valor)
        return elegido


# ----------------------------- FALABELLA ----------------------------
class ConectorFalabella:
    nombre = "Falabella"

    def buscar(self, termino: str, limite: int = 20) -> list:
        datos = descargar_datos(
            "https://www.falabella.com.co/falabella-co/search", {"Ntt": termino}
        )
        lista = entrar(datos, "props", "pageProps", "results")

        ahora = datetime.now(timezone.utc)
        productos = []
        for p in lista:
            try:
                precio = self._precio(p.get("prices"))
                if precio is None:
                    continue
                imagenes = p.get("mediaUrls") or []
                productos.append(Producto(
                    tienda=self.nombre,
                    nombre=p.get("displayName", "Sin nombre"),
                    precio=precio,
                    envio=None,
                    disponible=True,  # pendiente: revisar el campo 'availability'
                    url=p.get("url", ""),
                    imagen=imagenes[0] if imagenes else None,
                    consultado_en=ahora,
                ))
            except Exception:
                continue
            if len(productos) >= limite:
                break
        return productos

    @staticmethod
    def _precio(precios):
        normales = []
        tarjeta = None
        for pr in precios or []:
            if pr.get("crossed"):
                continue  # precio tachado (el original)
            lista = pr.get("price") or []
            if not lista:
                continue
            valor = _numero(lista[0])
            if pr.get("type") == "cmrPrice":
                tarjeta = valor
            else:
                normales.append(valor)
        if normales:
            return min(normales)
        return tarjeta