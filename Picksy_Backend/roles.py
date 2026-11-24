"""
Roles de Picksy y límite diario de búsquedas.

Roles (columna usuarios.rol):
  - 'usuario'           cuenta normal: busca, mochila, historial, membresía. Tiene un límite de búsquedas por día
                        (BUSQUEDAS_DIARIAS_USUARIO) mientras no tenga una membresía vigente.
  - 'premium'           lo mismo que 'usuario' pero SIN límite de búsquedas. También es premium quien tiene una
                        membresía vigente, aunque su rol siga siendo 'usuario'.
  - 'soporte'           ayuda a los usuarios: ve sus datos básicos, desbloquea cuentas y cierra sesiones.
                        No puede borrar usuarios ni cambiar roles, ni tocar cuentas de administrador.
  - 'analista'          ve estadísticas agregadas (sin datos personales): búsquedas, tiendas, membresías.
  - 'moderador_tiendas' activa o desactiva tiendas (una tienda desactivada deja de salir en las búsquedas).
  - 'admin'             puede todo lo anterior, además de ver/borrar usuarios y cambiar roles (admin.py).

Nadie sin sesión entra: no existe un rol de invitado (orden del profesor). Los roles se asignan SOLO con
PATCH /admin/usuarios/{id}/rol (o crear_admin.py para el primer administrador). El registro nunca los acepta.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text

import config
from database import engine

ROLES = ("usuario", "premium", "soporte", "analista", "moderador_tiendas", "admin")

# Roles que buscan sin límite diario (el personal necesita probar sin toparse con el tope).
ROLES_SIN_LIMITE = ("premium", "soporte", "analista", "moderador_tiendas", "admin")

# Colombia no tiene horario de verano: UTC-5 fijo (así no se depende de la base de zonas horarias del sistema).
_COLOMBIA = timezone(timedelta(hours=-5))
_HOY = "(NOW() AT TIME ZONE 'America/Bogota')::date"


def _membresia_vigente(conn, usuario_id: int) -> bool:
    fila = conn.execute(
        text("SELECT 1 FROM membresias WHERE usuario_id = :u AND vence_en > NOW()"), {"u": usuario_id}
    ).first()
    return fila is not None


def _limite_diario(conn, usuario: dict) -> Optional[int]:
    """Cuántas búsquedas por día puede hacer esta cuenta. None = sin límite."""
    if config.BUSQUEDAS_DIARIAS_USUARIO <= 0 or usuario["rol"] in ROLES_SIN_LIMITE:
        return None
    if _membresia_vigente(conn, usuario["id"]):
        return None
    return config.BUSQUEDAS_DIARIAS_USUARIO


def _segundos_hasta_medianoche() -> int:
    ahora = datetime.now(_COLOMBIA)
    manana = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((manana - ahora).total_seconds()))


def consumir_busqueda(usuario: dict) -> None:
    """Cuenta una búsqueda del día. Si la cuenta ya llegó a su límite diario responde 429.

    Es una sola sentencia atómica: dos búsquedas simultáneas no pueden pasarse del tope."""
    with engine.begin() as conn:
        limite = _limite_diario(conn, usuario)
        fila = conn.execute(
            text(f"""
                INSERT INTO uso_diario (usuario_id, dia, busquedas)
                VALUES (:u, {_HOY}, 1)
                ON CONFLICT (usuario_id, dia) DO UPDATE SET busquedas = uso_diario.busquedas + 1
                WHERE CAST(:limite AS INTEGER) IS NULL OR uso_diario.busquedas < CAST(:limite AS INTEGER)
                RETURNING busquedas
            """),
            {"u": usuario["id"], "limite": limite},
        ).first()
    if fila is None:
        espera = _segundos_hasta_medianoche()
        raise HTTPException(
            status_code=429,
            detail=(f"Llegaste al límite de {limite} búsquedas de hoy. Con una membresía Premium no tienes límite. "
                    "El contador se reinicia a medianoche (hora de Colombia)."),
            headers={"Retry-After": str(espera)},
        )


def estado_cupo(conn, usuario: dict) -> dict:
    """Datos para que el frontend muestre la insignia Premium y cuántas búsquedas quedan (se agrega a /auth/me)."""
    limite = _limite_diario(conn, usuario)
    usadas = conn.execute(
        text(f"SELECT COALESCE(SUM(busquedas), 0) FROM uso_diario WHERE usuario_id = :u AND dia = {_HOY}"),
        {"u": usuario["id"]},
    ).scalar()
    return {
        "premium": usuario["rol"] == "premium" or _membresia_vigente(conn, usuario["id"]),
        "limite_diario": limite,                                        # None = sin límite
        "busquedas_hoy": int(usadas),
        "busquedas_restantes": None if limite is None else max(0, limite - int(usadas)),
    }
