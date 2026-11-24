"""
Conector de Mercado Libre Colombia (sitio MCO) usando su API oficial.

ESTADO: OPCIONAL. Solo se activa si en el .env están ML_CLIENT_ID y ML_CLIENT_SECRET (ver config.py y buscador.py).
Sin ellos Picksy funciona exactamente igual que antes (9 tiendas con conector).

IMPORTANTE: este conector se escribió leyendo la documentación pública de la API y se probó con respuestas simuladas
(test_mercadolibre.py), pero NO se pudo probar contra la API real. Antes de la entrega corre una vez, en el servidor:
    python herramientas/probar_mercadolibre.py
Esa herramienta dice en español si las credenciales sirven y qué devuelve la búsqueda.

Cómo funciona
  1. Pide un token a la API con el flujo "client_credentials" (la propia aplicación, sin usuario de por medio).
     Dura unas 6 horas: se guarda en memoria y se renueva solo.
  2. Busca con GET /sites/MCO/search?q=...&condition=new y convierte cada resultado en un Producto.
Si la API responde error (401/403 por credenciales o permisos, 429, 5xx) se lanza la excepción: buscador.py la
convierte en el aviso "Mercado Libre no respondió", reintenta si fue un fallo pasajero y usa los datos guardados.
"""
import threading
import time
from datetime import datetime, timezone

import httpx

from .base import Producto

API = "https://api.mercadolibre.com"
SITIO = "MCO"            # Colombia
TIEMPO = 15              # segundos máximos por petición
MARGEN_TOKEN = 300       # el token se renueva 5 minutos antes de que venza
PRECIO_MINIMO = 100      # descarta precios de relleno como $0 o $1
MAXIMO_API = 50          # la API no entrega más de 50 resultados por consulta


class ConectorMercadoLibre:
    nombre = "Mercado Libre"
    especialidad = "general"

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = None
        self._vence = 0.0
        self._cerrojo = threading.Lock()   # las tiendas se consultan en hilos: un solo hilo pide el token

    def _obtener_token(self, forzar: bool = False) -> str:
        with self._cerrojo:
            if self._token and not forzar and time.time() < self._vence:
                return self._token
            r = httpx.post(
                f"{API}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                timeout=TIEMPO,
            )
            r.raise_for_status()
            datos = r.json()
            token = datos.get("access_token")
            if not token:
                raise ValueError("Mercado Libre no entregó un token de acceso")
            self._token = token
            self._vence = time.time() + max(60, int(datos.get("expires_in") or 21600) - MARGEN_TOKEN)
            return token

    def _consultar(self, termino: str, cantidad: int) -> list:
        for intento in (1, 2):
            token = self._obtener_token(forzar=(intento == 2))
            r = httpx.get(
                f"{API}/sites/{SITIO}/search",
                params={"q": termino, "limit": min(cantidad, MAXIMO_API), "condition": "new"},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=TIEMPO,
            )
            if r.status_code in (401, 403) and intento == 1:
                continue  # el token pudo vencer o revocarse: se pide otro y se reintenta una sola vez
            r.raise_for_status()
            return r.json().get("results") or []
        return []

    def buscar(self, termino: str, limite: int = 20) -> list:
        ahora = datetime.now(timezone.utc)
        productos = []
        # se piden algunos de más porque parte se descarta (sin precio, sin enlace)
        for h in self._consultar(termino, limite + 10):
            try:
                precio = h.get("price")
                if precio is None or float(precio) < PRECIO_MINIMO:
                    continue
                nombre = (h.get("title") or "").strip()
                enlace = (h.get("permalink") or "").strip()
                if not nombre or not enlace:
                    continue
                cantidad = h.get("available_quantity")
                gratis = bool((h.get("shipping") or {}).get("free_shipping"))
                imagen = (h.get("thumbnail") or "").replace("http://", "https://") or None

                productos.append(Producto(
                    tienda=self.nombre,
                    nombre=nombre,
                    precio=float(precio),
                    envio=0.0 if gratis else None,      # None = la API no informa el costo del envío
                    disponible=True if cantidad is None else cantidad > 0,
                    url=enlace,
                    imagen=imagen,
                    consultado_en=ahora,
                ))
            except Exception:
                continue  # un resultado raro no tumba toda la tienda
            if len(productos) >= limite:
                break
        return productos
