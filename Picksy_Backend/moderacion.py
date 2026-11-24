"""
Moderación de tiendas (rol 'moderador_tiendas'; el administrador también puede).

El moderador decide qué tiendas participan en las búsquedas. Una tienda desactivada:
  - ya no se consulta en /buscar (ni aparece en sus resultados, aunque estuviera en la caché),
  - ya no aparece en /tiendas (el selector del frontend).
No se borra nada: se vuelve a activar con el mismo endpoint.

Endpoints:
    GET   /moderacion/tiendas              las tiendas de Picksy y si están activas
    PATCH /moderacion/tiendas/{id}         {"activa": true|false}
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth import requiere_rol
from buscador import NOMBRES
from database import engine

router = APIRouter(prefix="/moderacion", tags=["Moderación de tiendas"])
registro = logging.getLogger("picksy.moderacion")

permiso = requiere_rol("moderador_tiendas")


class EstadoTienda(BaseModel):
    activa: bool


def tiendas_inactivas() -> set:
    """Nombres (en minúsculas) de las tiendas que el moderador desactivó. Vacío = todas activas."""
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT nombre FROM tiendas WHERE NOT activa")).all()
    return {f.nombre.lower() for f in filas}


def _es_de_picksy(nombre: str) -> bool:
    """Solo se moderan las tiendas que Picksy realmente consulta (tienen conector)."""
    return nombre.lower() in {n.lower() for n in NOMBRES}


@router.get("/tiendas")
def listar_tiendas(usuario=Depends(permiso)):
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT id, nombre, sitio_web, activa FROM tiendas ORDER BY nombre")).all()
    return [
        {"id": f.id, "nombre": f.nombre, "sitio_web": f.sitio_web, "activa": f.activa}
        for f in filas if _es_de_picksy(f.nombre)
    ]


@router.patch("/tiendas/{tienda_id}")
def cambiar_estado(tienda_id: int, datos: EstadoTienda, usuario=Depends(permiso)):
    with engine.begin() as conn:
        tienda = conn.execute(
            text("SELECT id, nombre, activa FROM tiendas WHERE id = :id"), {"id": tienda_id}
        ).first()
        if tienda is None or not _es_de_picksy(tienda.nombre):
            raise HTTPException(status_code=404, detail="Esa tienda no existe")
        conn.execute(text("UPDATE tiendas SET activa = :a WHERE id = :id"), {"a": datos.activa, "id": tienda_id})
    registro.info("%s dejó la tienda %s %s", usuario["correo"], tienda.nombre, "activa" if datos.activa else "desactivada")
    return {"id": tienda.id, "nombre": tienda.nombre, "activa": datos.activa}
