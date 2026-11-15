"""
Errores con un formato unificado (lo que pidió el profesor).

Todos los errores de la API responden JSON con la misma forma:
    {
      "detail": "Mensaje para el usuario",                      <- se mantiene: el frontend y QA ya lo leen
      "error":  {"codigo": "NO_AUTORIZADO", "mensaje": "...", "detalles": ...}
    }
Además, cualquier error inesperado del servidor (500) también sale como JSON y CON las cabeceras de CORS;
antes el navegador lo mostraba como "No se pudo conectar con el servidor".
"""
import logging
import math

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("picksy")

CODIGOS = {
    400: "SOLICITUD_INVALIDA", 401: "NO_AUTENTICADO", 403: "PROHIBIDO", 404: "NO_ENCONTRADO",
    405: "METODO_NO_PERMITIDO", 409: "CONFLICTO", 422: "DATOS_INVALIDOS", 429: "DEMASIADOS_INTENTOS",
    500: "ERROR_INTERNO", 503: "SERVICIO_NO_DISPONIBLE",
}


def _cuerpo(estado: int, mensaje, detalles=None, detail=None) -> dict:
    return {
        "detail": mensaje if detail is None else detail,
        "error": {"codigo": CODIGOS.get(estado, f"HTTP_{estado}"), "mensaje": mensaje if isinstance(mensaje, str) else "Datos inválidos", "detalles": detalles},
    }


def _sin_no_finitos(x):
    """CAMBIO (QA): si el cuerpo trae NaN o Infinity, FastAPI repite ese valor en el error de validación y
    json.dumps no puede escribirlo: la respuesta salía como 500. Aquí se convierten en texto."""
    if isinstance(x, float) and not math.isfinite(x):
        return str(x)
    if isinstance(x, dict):
        return {k: _sin_no_finitos(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sin_no_finitos(v) for v in x]
    return x


def instalar(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(_cuerpo(exc.status_code, str(exc.detail)), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validacion(request: Request, exc: RequestValidationError):
        errores = _sin_no_finitos(jsonable_encoder(exc.errors()))
        # "detail" conserva la lista estándar de FastAPI (compatibilidad); "error" trae el resumen.
        return JSONResponse(_cuerpo(422, "Revisa los datos enviados.", errores, detail=errores), status_code=422)

    @app.exception_handler(OperationalError)
    async def base_caida(request: Request, exc: OperationalError):
        log.error("Base de datos no disponible: %s", exc)
        return JSONResponse(_cuerpo(503, "La base de datos no está disponible. Inténtalo en un momento."), status_code=503)


async def error_inesperado(request: Request, call_next):
    """Middleware: convierte cualquier excepción no prevista en un 500 en JSON (y deja rastro en el log)."""
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("Error inesperado en %s %s", request.method, request.url.path)
        return JSONResponse(_cuerpo(500, "Ocurrió un error inesperado en el servidor."), status_code=500)
