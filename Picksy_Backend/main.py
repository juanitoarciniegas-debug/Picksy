from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
import errores
from admin import router as admin_router
from analista import router as analista_router        # CAMBIO (roles): estadísticas agregadas
from auth import router as auth_router
from busqueda import router as busqueda_router
from carritos import router as carritos_router          # CAMBIO (RF-13/14/17): carritos y mochila
from dos_factores import router as dos_factores_router
from historial import router as historial_router
from moderacion import router as moderacion_router    # CAMBIO (roles): activar/desactivar tiendas
from pagos import router as pagos_router                # CAMBIO (pagos): métodos de pago, planes y pagos
from precios import router as precios_router            # CAMBIO (RF-16): variación de precios
from recuperacion import router as recuperacion_router  # CAMBIO: recuperar contraseña
from soporte import router as soporte_router          # CAMBIO (roles): ayuda a usuarios

app = FastAPI(title="Picksy API", version="1.0.0")

# CAMBIO (errores unificados): todos los errores salen en JSON con la misma forma (ver errores.py).
errores.instalar(app)
# Se agrega ANTES que CORS para quedar "por dentro": así un error 500 también lleva las cabeceras de CORS
# y el navegador puede leer el mensaje.
app.middleware("http")(errores.error_inesperado)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGENES,                       # CAMBIO: se configura en el .env (CORS_ORIGENES)
    allow_methods=["GET", "POST", "DELETE", "PATCH"],         # DELETE: borrar historial/usuarios/carritos · PATCH: roles y prioridades
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Total-Count", "Retry-After"],          # para que el navegador pueda leerlas
)

ROUTERS = [
    auth_router, dos_factores_router, recuperacion_router, busqueda_router,
    historial_router, carritos_router, precios_router, pagos_router, admin_router,
    soporte_router, analista_router, moderacion_router,   # CAMBIO (roles nuevos)
]

# CAMBIO (versionado): la API oficial vive en /api/v1/...
v1 = APIRouter(prefix="/api/v1")
for r in ROUTERS:
    v1.include_router(r)
app.include_router(v1)

# Compatibilidad: las rutas sin versión (/buscar, /auth/login ...) siguen funcionando para no romper
# lo que ya existe (pruebas del QA, pantallas viejas). No aparecen en /docs. Cuando todo el equipo use /api/v1 se pueden quitar.
for r in ROUTERS:
    app.include_router(r, include_in_schema=False)


@app.get("/")
def inicio():
    return {"mensaje": "Picksy funcionando", "version": "v1", "documentacion": "/docs"}


@app.get("/api/v1/salud", tags=["Estado"])
def salud():
    """Para comprobar que el servidor y la base de datos responden (lo usa el despliegue en AWS)."""
    from database import engine

    # CAMBIO (alta disponibilidad): el engine tiene pool_pre_ping (ver database.py), que ya hace un SELECT 1 al sacar la
    # conexión del pool y abre otra si estaba muerta. Repetir el SELECT 1 aquí sumaba un viaje extra a la base en cada
    # petición (-7 % de TPS medido). Si la base no responde, esta línea lanza OperationalError y errores.py lo
    # convierte en un 503 con el formato unificado.
    with engine.connect():
        pass
    return {"estado": "ok"}
