"""
Límite de intentos (rate limiting): protege contra quien intenta adivinar contraseñas o códigos.
Cuando se pasa del límite, la API responde 429 Too Many Requests con el encabezado Retry-After (segundos de espera).

Funciona en la memoria del servidor: sirve para una sola instancia de uvicorn (como en este proyecto).
Si algún día hubiera varios servidores, habría que guardar los contadores en la base de datos o en Redis.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_eventos: dict[str, deque] = defaultdict(deque)


def _purgar(clave: str, ventana: int) -> deque:
    cola = _eventos[clave]
    limite = time.monotonic() - ventana
    while cola and cola[0] < limite:
        cola.popleft()
    return cola


def anotar(clave: str, ventana: int = 900) -> None:
    """Registra un evento (un fallo, o una llamada) para esa clave."""
    _purgar(clave, ventana).append(time.monotonic())


def exigir_libre(clave: str, maximo: int, ventana: int) -> None:
    """Lanza 429 si esa clave ya tuvo 'maximo' eventos dentro de los últimos 'ventana' segundos."""
    cola = _purgar(clave, ventana)
    if len(cola) >= maximo:
        espera = max(1, int(ventana - (time.monotonic() - cola[0])))
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos. Espera {espera} segundos e inténtalo de nuevo.",
            headers={"Retry-After": str(espera)},
        )


def olvidar(clave: str) -> None:
    _eventos.pop(clave, None)


def reiniciar() -> None:
    """Borra todos los contadores (para las pruebas automáticas)."""
    _eventos.clear()


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "desconocida"
