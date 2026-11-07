"""
Recuperar la contraseña (el enlace "¿La olvidaste?" del login).

Flujo:
  1. POST /auth/recuperar            {correo}  -> siempre responde lo mismo (no revela si el correo existe).
                                                Si existe, se envía un correo con un enlace válido 30 minutos.
  2. POST /auth/recuperar/restablecer {token, contrasena_nueva, codigo}
                                              -> cambia la contraseña. Como el 2FA es obligatorio, también se pide un
                                                 código de Google Authenticator (o un código de recuperación):
                                                 así, quien solo tiene el correo no puede apoderarse de la cuenta.

Correo: si en el .env está SMTP_HOST, se envía por SMTP. Si no, el enlace se imprime en la terminal del backend
(sirve para probar y para la demostración sin configurar un servidor de correo).
"""
import hashlib
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

import config
import limitador
import totp
from auth import encriptar
from dos_factores import validar_codigo_o_recuperacion
from database import engine

log = logging.getLogger("picksy")
router = APIRouter(prefix="/auth/recuperar", tags=["Recuperar contraseña"])

MINUTOS_ENLACE = 30
MENSAJE_GENERICO = "Si ese correo está registrado, te enviamos un enlace para restablecer la contraseña."


class RecuperarEntrada(BaseModel):
    correo: EmailStr


class RestablecerEntrada(BaseModel):
    token: str
    contrasena_nueva: str = Field(min_length=8, max_length=50)
    codigo: str = Field(min_length=6, max_length=20, description="Código de Google Authenticator o código de recuperación")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def enviar_correo(destino: str, enlace: str) -> None:
    """Envía el correo (o imprime el enlace si no hay SMTP configurado). Nunca lanza error hacia el usuario."""
    if not config.SMTP_HOST:
        print(f"\n[recuperación] Enlace para {destino} (válido {MINUTOS_ENLACE} min):\n    {enlace}\n")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = "Restablece tu contraseña de Picksy"
        msg["From"] = config.SMTP_REMITENTE
        msg["To"] = destino
        msg.set_content(
            "Hola,\n\nRecibimos una solicitud para restablecer tu contraseña de Picksy.\n"
            f"Abre este enlace (vale {MINUTOS_ENLACE} minutos):\n\n{enlace}\n\n"
            "Necesitarás también un código de Google Authenticator.\n"
            "Si no fuiste tú, ignora este mensaje: tu contraseña no cambia.\n"
        )
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as servidor:
            servidor.starttls()
            if config.SMTP_USUARIO:
                servidor.login(config.SMTP_USUARIO, config.SMTP_CLAVE)
            servidor.send_message(msg)
    except Exception:  # noqa: BLE001 - un fallo del correo no debe romper la respuesta
        log.exception("No se pudo enviar el correo de recuperación")


@router.post("", status_code=202)
def solicitar(datos: RecuperarEntrada, request: Request, tareas: BackgroundTasks):
    correo = datos.correo.lower()
    ip = limitador.ip_de(request)
    limitador.exigir_libre(f"recuperar-ip:{ip}", 10, 3600)
    limitador.exigir_libre(f"recuperar:{correo}", 3, 3600)
    limitador.anotar(f"recuperar-ip:{ip}", 3600)
    limitador.anotar(f"recuperar:{correo}", 3600)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM recuperaciones_clave WHERE expira_en < NOW()"))
        usuario = conn.execute(text("SELECT id FROM usuarios WHERE correo = :c"), {"c": correo}).first()
        if usuario:
            token = secrets.token_urlsafe(32)
            conn.execute(text("DELETE FROM recuperaciones_clave WHERE usuario_id = :u"), {"u": usuario.id})
            conn.execute(
                text("INSERT INTO recuperaciones_clave (token_hash, usuario_id, expira_en) VALUES (:h, :u, :e)"),
                {"h": _hash(token), "u": usuario.id, "e": datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_ENLACE)},
            )
            tareas.add_task(enviar_correo, correo, f"{config.FRONTEND_URL}/restablecer.html?token={token}")
    return {"mensaje": MENSAJE_GENERICO}


@router.post("/restablecer")
def restablecer(datos: RestablecerEntrada, request: Request):
    limitador.exigir_libre(f"restablecer-ip:{limitador.ip_de(request)}", 10, 900)
    error = None

    with engine.begin() as conn:
        fila = conn.execute(
            text("""
                SELECT r.usuario_id, u.totp_secreto, u.totp_activo, u.totp_ultimo_paso
                FROM recuperaciones_clave r JOIN usuarios u ON u.id = r.usuario_id
                WHERE r.token_hash = :h AND r.expira_en > NOW()
            """),
            {"h": _hash(datos.token)},
        ).first()
        if fila is None:
            error = "El enlace venció o no es válido. Pide uno nuevo."
        else:
            limitador.exigir_libre(f"codigo:{fila.usuario_id}", config.LOGIN_MAX_FALLOS * 2, config.LOGIN_VENTANA_SEG)
            tipo, paso = (validar_codigo_o_recuperacion(conn, fila.usuario_id, fila, datos.codigo)
                          if fila.totp_activo else ("sin2fa", None))
            if tipo is None:
                limitador.anotar(f"restablecer-ip:{limitador.ip_de(request)}", 900)
                limitador.anotar(f"codigo:{fila.usuario_id}", config.LOGIN_VENTANA_SEG)
                error = "Código incorrecto o vencido."
            else:
                if tipo == "totp":
                    conn.execute(text("UPDATE usuarios SET totp_ultimo_paso = :p WHERE id = :id"),
                                 {"p": paso, "id": fila.usuario_id})
                conn.execute(text("UPDATE usuarios SET contrasena_hash = :h WHERE id = :id"),
                             {"h": encriptar(datos.contrasena_nueva), "id": fila.usuario_id})
                # El enlace sirve una sola vez y se cierran todas las sesiones abiertas de esa cuenta.
                conn.execute(text("DELETE FROM recuperaciones_clave WHERE usuario_id = :u"), {"u": fila.usuario_id})
                conn.execute(text("DELETE FROM sesiones WHERE usuario_id = :u"), {"u": fila.usuario_id})
                conn.execute(text("DELETE FROM login_pendientes WHERE usuario_id = :u"), {"u": fila.usuario_id})
                return {"mensaje": "Contraseña actualizada. Ya puedes iniciar sesión."}

    raise HTTPException(status_code=400, detail=error)
