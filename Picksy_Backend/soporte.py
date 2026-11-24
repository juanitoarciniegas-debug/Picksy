"""
Soporte (rol 'soporte'; el administrador también puede).

Ayuda a los usuarios sin poder dañarlos: ve datos básicos, desbloquea cuentas y cierra sesiones.
NO puede borrar usuarios, cambiar roles ni tocar cuentas de administrador (eso es del administrador).
Nunca ve contraseñas, secretos del Authenticator ni códigos de recuperación.

Endpoints:
    GET  /soporte/usuarios?q=texto&pagina=1&limite=20   busca usuarios por correo (total en X-Total-Count)
    GET  /soporte/usuarios/{id}                         ficha de un usuario (membresía, búsquedas de hoy, sesiones)
    POST /soporte/usuarios/{id}/desbloquear             quita el bloqueo por intentos fallidos de login o de código
    POST /soporte/usuarios/{id}/cerrar-sesiones         cierra todas las sesiones abiertas de esa cuenta
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text

import limitador
from auth import requiere_rol
from database import engine

router = APIRouter(prefix="/soporte", tags=["Soporte"])

permiso = requiere_rol("soporte")


def _usuario(conn, usuario_id: int):
    fila = conn.execute(
        text("SELECT id, correo, rol, totp_activo, creado_en FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Ese usuario no existe")
    return fila


def _proteger_admin(actor: dict, objetivo) -> None:
    if objetivo.rol == "admin" and actor["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Soporte no puede gestionar cuentas de administrador")


@router.get("/usuarios")
def buscar_usuarios(
    response: Response,
    q: Optional[str] = Query(default=None, max_length=100, description="Parte del correo"),
    pagina: int = Query(default=1, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    usuario=Depends(permiso),
):
    filtro = "WHERE POSITION(lower(:q) IN lower(u.correo)) > 0" if q else ""
    params = {"q": q, "limite": limite, "desde": (pagina - 1) * limite}
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM usuarios u {filtro}"), params).scalar()
        filas = conn.execute(
            text(f"""
                SELECT u.id, u.correo, u.rol, u.totp_activo, u.creado_en,
                       EXISTS (SELECT 1 FROM membresias m WHERE m.usuario_id = u.id AND m.vence_en > NOW()) AS membresia
                FROM usuarios u {filtro}
                ORDER BY u.id LIMIT :limite OFFSET :desde
            """),
            params,
        ).all()
    response.headers["X-Total-Count"] = str(total)
    return [
        {"id": f.id, "correo": f.correo, "rol": f.rol, "dos_factores": f.totp_activo,
         "membresia_activa": f.membresia, "creado_en": f.creado_en.isoformat()}
        for f in filas
    ]


@router.get("/usuarios/{usuario_id}")
def ficha_usuario(usuario_id: int, usuario=Depends(permiso)):
    with engine.connect() as conn:
        u = _usuario(conn, usuario_id)
        membresia = conn.execute(
            text("SELECT plan, vence_en FROM membresias WHERE usuario_id = :id"), {"id": usuario_id}
        ).first()
        hoy = conn.execute(
            text("""SELECT COALESCE(SUM(busquedas), 0) FROM uso_diario
                    WHERE usuario_id = :id AND dia = (NOW() AT TIME ZONE 'America/Bogota')::date"""),
            {"id": usuario_id},
        ).scalar()
        sesiones = conn.execute(
            text("SELECT COUNT(*) FROM sesiones WHERE usuario_id = :id AND expira_en > NOW()"), {"id": usuario_id}
        ).scalar()
        vigente = conn.execute(
            text("SELECT 1 FROM membresias WHERE usuario_id = :id AND vence_en > NOW()"), {"id": usuario_id}
        ).first() is not None
    return {
        "id": u.id, "correo": u.correo, "rol": u.rol, "dos_factores": u.totp_activo,
        "creado_en": u.creado_en.isoformat(),
        "membresia": {"activa": vigente, "plan": membresia.plan if membresia else None,
                      "vence_en": membresia.vence_en.isoformat() if membresia else None},
        "busquedas_hoy": int(hoy),
        "sesiones_abiertas": sesiones,
    }


@router.post("/usuarios/{usuario_id}/desbloquear")
def desbloquear(usuario_id: int, usuario=Depends(permiso)):
    with engine.connect() as conn:
        u = _usuario(conn, usuario_id)
    _proteger_admin(usuario, u)
    # Son las mismas claves que usa el límite de intentos de auth.py y dos_factores.py.
    limitador.olvidar(f"login:{u.correo.lower()}")
    limitador.olvidar(f"codigo:{u.id}")
    return {"id": u.id, "correo": u.correo, "desbloqueado": True}


@router.post("/usuarios/{usuario_id}/cerrar-sesiones")
def cerrar_sesiones(usuario_id: int, usuario=Depends(permiso)):
    with engine.begin() as conn:
        u = _usuario(conn, usuario_id)
        _proteger_admin(usuario, u)
        cerradas = conn.execute(text("DELETE FROM sesiones WHERE usuario_id = :id"), {"id": usuario_id}).rowcount
        conn.execute(text("DELETE FROM login_pendientes WHERE usuario_id = :id"), {"id": usuario_id})
    return {"id": u.id, "correo": u.correo, "sesiones_cerradas": cerradas}
