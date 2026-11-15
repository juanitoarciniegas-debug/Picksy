"""
Panel de administrador (roles).

Roles:
  - 'usuario': usa Picksy (buscar, historial).
  - 'admin'  : además puede ver la lista de usuarios y eliminarlos.

Reglas de protección de los administradores:
  - Un administrador NO puede eliminarse a sí mismo: solo OTRO administrador puede eliminarlo.
  - Nunca puede quedar el sistema sin administradores (no se elimina ni se degrada al último).
  - Un usuario normal no puede usar ninguno de estos endpoints (403).

Endpoints (todos requieren sesión de administrador):
    GET    /admin/usuarios            lista de usuarios
    DELETE /admin/usuarios/{id}       elimina un usuario (y su historial y sesiones)
    PATCH  /admin/usuarios/{id}/rol   cambia el rol ('usuario' o 'admin')
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth import solo_admin
from database import engine

router = APIRouter(prefix="/admin", tags=["Administración"])


class RolEntrada(BaseModel):
    rol: Literal["usuario", "admin"]


def _bloquear_admins(conn) -> int:
    """Bloquea las filas de los administradores durante la operación (evita que dos admins se borren a la vez)
    y devuelve cuántos hay."""
    filas = conn.execute(text("SELECT id FROM usuarios WHERE rol = 'admin' FOR UPDATE")).all()
    return len(filas)


@router.get("/usuarios")
def listar_usuarios(admin=Depends(solo_admin)):
    with engine.connect() as conn:
        filas = conn.execute(
            text("SELECT id, correo, rol, totp_activo, creado_en FROM usuarios ORDER BY id")
        ).all()
    return [
        {"id": f.id, "correo": f.correo, "rol": f.rol, "dos_factores": f.totp_activo,
         "creado_en": f.creado_en.isoformat()}
        for f in filas
    ]


@router.delete("/usuarios/{usuario_id}")
def eliminar_usuario(usuario_id: int, admin=Depends(solo_admin)):
    if usuario_id == admin["id"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta de administrador. Debe hacerlo otro administrador.")

    with engine.begin() as conn:
        total_admins = _bloquear_admins(conn)
        objetivo = conn.execute(
            text("SELECT id, correo, rol FROM usuarios WHERE id = :id"), {"id": usuario_id}
        ).first()
        if objetivo is None:
            raise HTTPException(status_code=404, detail="Ese usuario no existe")
        if objetivo.rol == "admin" and total_admins <= 1:
            raise HTTPException(status_code=409, detail="No se puede eliminar al último administrador")

        # ON DELETE CASCADE borra también sus sesiones, historial y carritos.
        conn.execute(text("DELETE FROM usuarios WHERE id = :id"), {"id": usuario_id})
    return {"eliminado": objetivo.id, "correo": objetivo.correo}


@router.patch("/usuarios/{usuario_id}/rol")
def cambiar_rol(usuario_id: int, datos: RolEntrada, admin=Depends(solo_admin)):
    if usuario_id == admin["id"]:
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol")

    with engine.begin() as conn:
        total_admins = _bloquear_admins(conn)
        objetivo = conn.execute(
            text("SELECT id, correo, rol FROM usuarios WHERE id = :id"), {"id": usuario_id}
        ).first()
        if objetivo is None:
            raise HTTPException(status_code=404, detail="Ese usuario no existe")
        if objetivo.rol == "admin" and datos.rol != "admin" and total_admins <= 1:
            raise HTTPException(status_code=409, detail="No se puede quitar el rol al último administrador")

        conn.execute(text("UPDATE usuarios SET rol = :rol WHERE id = :id"), {"rol": datos.rol, "id": usuario_id})
    return {"id": objetivo.id, "correo": objetivo.correo, "rol": datos.rol}
