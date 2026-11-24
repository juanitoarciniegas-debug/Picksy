"""
Límite de intentos (rate limiting): protege contra quien intenta adivinar contraseñas o códigos.
Cuando se pasa del límite, la API responde 429 Too Many Requests con el encabezado Retry-After (segundos de espera).

Tiene DOS modos y las rutas (auth, pagos, 2FA, recuperación) lo usan igual en los dos:

1. MEMORIA (por defecto, REDIS_URL vacío): los contadores viven en la memoria del proceso de Python.
   Sirve para UNA sola instancia de uvicorn (como el despliegue actual: --workers 1).

2. REDIS (REDIS_URL=redis://127.0.0.1:6379/0): los contadores viven en Redis, así que varias instancias de la API
   (por ejemplo 2 procesos detrás de Nginx, o 2 servidores) comparten el MISMO límite. Es lo que hace falta
   para la alta disponibilidad: sin esto, quien falla el login 5 veces en la instancia A tendría otros 5 intentos
   en la B.  CAMBIO (alta disponibilidad).

Si Redis se cae, el limitador NO tumba la API: cambia solo a la memoria del proceso (el límite deja de ser
compartido mientras dure la falla), deja un aviso en el log y vuelve a probar Redis cada 30 segundos.

Privacidad: en Redis la clave se guarda con SHA-256 (no quedan correos ni IPs legibles) y cada contador
se borra solo cuando vence su ventana.
"""
import hashlib
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException, Request

import config

log = logging.getLogger("picksy")

# ---------------------------------------------------------------------------------------------- modo memoria
_eventos: dict[str, deque] = defaultdict(deque)


def _purgar(clave: str, ventana: int) -> deque:
    cola = _eventos[clave]
    limite = time.monotonic() - ventana
    while cola and cola[0] < limite:
        cola.popleft()
    return cola


# ---------------------------------------------------------------------------------------------- modo Redis
_PREFIJO = "picksy:limite:"
_REINTENTAR_REDIS_SEG = 30          # si Redis falla, se usa la memoria y se vuelve a probar pasado este tiempo
_cliente = None                     # cliente de Redis (se crea la primera vez que hace falta)
_redis_caido_hasta = 0.0            # time.monotonic() hasta el que no se intenta Redis
_SIN_REDIS = object()               # "no se pudo usar Redis: usa la memoria"


def _redis():
    """Cliente de Redis, o None si no se usa Redis o está en pausa por una falla reciente."""
    global _cliente
    if not config.REDIS_URL or time.monotonic() < _redis_caido_hasta:
        return None
    if _cliente is None:
        import redis  # solo se importa si de verdad se usa Redis: sin REDIS_URL no hace falta instalarlo

        _cliente = redis.Redis.from_url(
            config.REDIS_URL,
            socket_connect_timeout=0.5,   # un límite de intentos nunca debe hacer lenta la API
            socket_timeout=0.5,
            decode_responses=True,
        )
    return _cliente


def _marcar_caido(error: Exception) -> None:
    global _redis_caido_hasta
    _redis_caido_hasta = time.monotonic() + _REINTENTAR_REDIS_SEG
    log.warning("LIMITADOR Redis no disponible (%s: %s). Se usa la memoria del proceso y se reintenta en %s s.",
                type(error).__name__, error, _REINTENTAR_REDIS_SEG)


def _con_redis(operacion):
    """Ejecuta operacion(cliente). Si Redis no está o falla, devuelve _SIN_REDIS y el llamador usa la memoria."""
    try:
        r = _redis()
        if r is None:
            return _SIN_REDIS
        return operacion(r)
    except Exception as error:  # noqa: BLE001  (ConnectionError, TimeoutError, paquete no instalado...)
        _marcar_caido(error)
        return _SIN_REDIS


def _clave_redis(clave: str) -> str:
    return _PREFIJO + hashlib.sha256(clave.encode("utf-8")).hexdigest()[:32]


def modo() -> str:
    """'redis' o 'memoria' (para diagnóstico)."""
    return "redis" if (config.REDIS_URL and time.monotonic() >= _redis_caido_hasta) else "memoria"


# ---------------------------------------------------------------------------------------------- API pública
def anotar(clave: str, ventana: int = 900) -> None:
    """Registra un evento (un fallo, o una llamada) para esa clave."""
    ahora = time.time()

    def en_redis(r):
        k = _clave_redis(clave)
        p = r.pipeline()                                   # MULTI/EXEC: las 3 órdenes se aplican juntas
        p.zremrangebyscore(k, "-inf", ahora - ventana)
        p.zadd(k, {f"{ahora:.6f}:{uuid.uuid4().hex[:8]}": ahora})   # miembro único aunque coincida el instante
        p.expire(k, int(ventana) + 1)                      # el contador se borra solo
        p.execute()
        return True

    if _con_redis(en_redis) is _SIN_REDIS:
        _purgar(clave, ventana).append(time.monotonic())


def exigir_libre(clave: str, maximo: int, ventana: int) -> None:
    """Lanza 429 si esa clave ya tuvo 'maximo' eventos dentro de los últimos 'ventana' segundos."""
    ahora = time.time()

    def en_redis(r):
        k = _clave_redis(clave)
        p = r.pipeline()
        p.zremrangebyscore(k, "-inf", ahora - ventana)
        p.zcard(k)
        p.zrange(k, 0, 0, withscores=True)
        _, cantidad, primero = p.execute()
        return cantidad, (ahora - primero[0][1]) if primero else 0.0   # (cuántos hay, antigüedad del más viejo)

    resultado = _con_redis(en_redis)
    if resultado is _SIN_REDIS:
        cola = _purgar(clave, ventana)
        resultado = (len(cola), (time.monotonic() - cola[0]) if cola else 0.0)

    cantidad, antiguedad = resultado
    if cantidad >= maximo:
        espera = max(1, int(ventana - antiguedad))
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos. Espera {espera} segundos e inténtalo de nuevo.",
            headers={"Retry-After": str(espera)},
        )


def olvidar(clave: str) -> None:
    _con_redis(lambda r: r.delete(_clave_redis(clave)))
    _eventos.pop(clave, None)


def reiniciar() -> None:
    """Borra todos los contadores (para las pruebas automáticas)."""
    global _redis_caido_hasta
    _redis_caido_hasta = 0.0

    def en_redis(r):
        llaves = list(r.scan_iter(match=_PREFIJO + "*", count=500))
        if llaves:
            r.delete(*llaves)
        return True

    _con_redis(en_redis)
    _eventos.clear()


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "desconocida"
