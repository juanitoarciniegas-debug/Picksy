import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as EsperaAgotada
from conectores.farmatodo import ConectorFarmatodo

import httpx

import config
from cache import guardar_cache, leer_cache, normalizar
from conectores.algolia import ConectorAlgolia
from conectores.buscalibre import ConectorBuscalibre
from conectores.nextdata import ConectorFalabella, ConectorHomecenter
from conectores.vtex import ConectorVtex

CONECTORES = [
    ConectorVtex("Éxito", "www.exito.com"),
    ConectorVtex("Olímpica", "www.olimpica.com"),
    ConectorHomecenter(),
    ConectorFalabella(),
    ConectorAlgolia("Alkosto", "https://www.alkosto.com"),
    ConectorAlgolia("Ktronix", "https://www.ktronix.com"),
    ConectorAlgolia("Alkomprar", "https://www.alkomprar.com"),
    ConectorBuscalibre(),
    ConectorFarmatodo(),
]

# CAMBIO (ERS: 10 tiendas): Mercado Libre se suma SOLO si hay credenciales de su API en el .env (ver config.py).
# Sin ellas la lista queda exactamente igual que antes (9 conectores).
if config.ML_CLIENT_ID and config.ML_CLIENT_SECRET:
    from conectores.mercadolibre import ConectorMercadoLibre

    CONECTORES.append(ConectorMercadoLibre(config.ML_CLIENT_ID, config.ML_CLIENT_SECRET))

NOMBRES = [c.nombre for c in CONECTORES]

LIMITE_SEGUNDOS = 8

log = logging.getLogger("picksy")

# CAMBIO (disponibilidad de tiendas): reintento ante fallos PASAJEROS de red.
CODIGOS_PASAJEROS = {429, 500, 502, 503, 504}   # la tienda dijo "intenta de nuevo" o falló por dentro
MARGEN_REINTENTO = 3.0                          # solo se reintenta si quedan al menos 3 s dentro del límite de la búsqueda
PAUSA_REINTENTO = 0.4                           # segundos de espera antes de volver a preguntar


def _es_pasajero(error: Exception) -> bool:
    """¿Vale la pena volver a intentar? Sí si fue un corte de red / tiempo agotado o un 429 / 5xx.
    No si la tienda nos bloqueó (403), cambió la página (parseo) o devolvió algo raro: repetir no lo arregla."""
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in CODIGOS_PASAJEROS
    return False


def _resumen(error: Exception) -> str:
    """Texto corto para el log, sin la dirección completa (lleva lo que la persona buscó)."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"http={error.response.status_code}"
    if isinstance(error, httpx.TransportError):
        return "red"
    return str(error)[:120]


def _consultar(conector, termino: str, hora_tope: float):
    """Pregunta a la tienda. Si falla por un problema pasajero reintenta (config.TIENDA_REINTENTOS veces)
    mientras queden al menos MARGEN_REINTENTO segundos antes de la hora tope de la búsqueda."""
    intentos = 0
    while True:
        try:
            return conector.buscar(termino)
        except Exception as error:
            intentos += 1
            if (intentos > config.TIENDA_REINTENTOS or not _es_pasajero(error)
                    or hora_tope - time.time() < MARGEN_REINTENTO):
                raise
            log.warning("TIENDA_REINTENTO tienda=%s intento=%s error=%s %s",
                        conector.nombre, intentos, type(error).__name__, _resumen(error))
            time.sleep(PAUSA_REINTENTO)


def buscar_en_todas(termino: str, tiendas=None, forzar: bool = False):
    if tiendas:
        pedidas = {t.lower() for t in tiendas}
        conectores = [c for c in CONECTORES if c.nombre.lower() in pedidas]
    else:
        conectores = CONECTORES

    clave = normalizar(termino)
    hora_tope = time.time() + LIMITE_SEGUNDOS

    def ejecutar(conector):
        # 1. ¿Hay datos guardados de menos de 24 horas?
        if not forzar:
            try:
                guardados = leer_cache(clave, conector.nombre)
                if guardados is not None:
                    return guardados, None
            except Exception:
                pass  # si la base de datos falla, se sigue sin caché

        # 2. Consultar la tienda (con un reintento si fue un fallo pasajero de red)
        try:
            productos = _consultar(conector, termino, hora_tope)
        except Exception as error:
            # CAMBIO (monitoreo): cada falla queda en el log del servidor con un formato fácil de buscar
            #   journalctl -u picksy | grep TIENDA_FALLO
            log.warning("TIENDA_FALLO tienda=%s error=%s %s", conector.nombre, type(error).__name__, _resumen(error))
            # 3. Si falla, usar datos viejos si existen (RF-06, RNF-05)
            try:
                viejos = leer_cache(clave, conector.nombre, solo_vigente=False)
            except Exception:
                viejos = None
            if viejos:
                return viejos, f"{conector.nombre} no respondió; se muestran datos guardados anteriormente"
            return [], f"{conector.nombre} no respondió ({type(error).__name__})"

        # 4. Guardar para la próxima vez.
        # CAMBIO (QA DEF-05): también se guarda cuando la tienda no devuelve nada (lista vacía);
        # cache.py le da una vigencia corta (30 min) a esos resultados vacíos.
        try:
            guardar_cache(clave, conector.nombre, productos)
        except Exception:
            pass
        return productos, None

    pool = ThreadPoolExecutor(max_workers=max(len(conectores), 1))
    futuros = [(c, pool.submit(ejecutar, c)) for c in conectores]

    productos = []
    avisos = []
    for conector, futuro in futuros:
        try:
            lista, aviso = futuro.result(timeout=max(0.0, hora_tope - time.time()))
        except EsperaAgotada:
            log.warning("TIENDA_LENTA tienda=%s (pasó el límite de %s s)", conector.nombre, LIMITE_SEGUNDOS)
            try:
                viejos = leer_cache(clave, conector.nombre, solo_vigente=False)
            except Exception:
                viejos = None
            if viejos:
                lista = viejos
                aviso = f"{conector.nombre} tardó demasiado; se muestran datos guardados anteriormente"
            else:
                lista = []
                aviso = f"{conector.nombre} tardó demasiado y se omitió; estará disponible en la próxima búsqueda"
        productos.extend(lista)
        if aviso:
            avisos.append(aviso)

    pool.shutdown(wait=False)  # no esperar a las tiendas que siguen trabajando
    return productos, avisos