"""
Verificación en dos pasos (2FA) con Google Authenticator (TOTP).

CAMBIO (2FA obligatorio): el 2FA ya no es opcional.
  - Un usuario NUEVO configura el Authenticator al registrarse (POST /auth/registro y /auth/registro/confirmar, en auth.py).
  - Cada inicio de sesión pide: correo + contraseña (POST /auth/login) + código de 6 dígitos (POST /auth/2fa/login).
  - Las cuentas ANTIGUAS que nunca activaron el Authenticator lo configuran en su próximo login
    (POST /auth/2fa/pendiente/configurar y /auth/2fa/pendiente/activar) y entran en el mismo paso.
  - Ya no existe "desactivar": nadie puede entrar sin el código.

CAMBIO (recuperación): en lugar del código de 6 dígitos también se acepta un CÓDIGO DE RECUPERACIÓN (de un solo uso),
que el usuario recibe al crear su cuenta. Así, quien pierde el teléfono no queda fuera.

CAMBIO (correos): cada vez que se completa un inicio de sesión se envía el correo "¿Acabas de entrar a Picksy?"
con la fecha, el dispositivo y la IP, y un botón "No fui yo" que lleva a cambiar la contraseña.

Endpoints:
    POST /auth/2fa/login                      segundo paso del login: token_2fa + código (o código de recuperación) -> sesión
    POST /auth/2fa/pendiente/configurar       cuenta antigua: genera la clave y el QR
    POST /auth/2fa/pendiente/activar          cuenta antigua: confirma con un código, activa el 2FA y da la sesión
    POST /auth/2fa/codigos-recuperacion       (con sesión) contraseña + código -> 8 códigos nuevos (los anteriores dejan de servir)
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

import config
import correos          # CAMBIO (correos): aviso de inicio de sesión
import limitador
import totp
from auth import crear_sesion, usuario_actual, verificar
from database import engine

router = APIRouter(prefix="/auth/2fa", tags=["Doble factor (2FA)"])


# ---------- Modelos ----------
class TokenEntrada(BaseModel):
    token_2fa: str


class LoginDosPasosEntrada(TokenEntrada):
    codigo: str = Field(min_length=6, max_length=20, description="Código de 6 dígitos de la app, o un código de recuperación")


class RegenerarEntrada(BaseModel):
    contrasena: str
    codigo: str = Field(min_length=6, max_length=20)


# ---------- Auxiliares ----------
def _datos_usuario(conn, usuario_id: int):
    return conn.execute(
        text("SELECT correo, totp_secreto, totp_activo, totp_ultimo_paso, contrasena_hash FROM usuarios WHERE id = :id"),
        {"id": usuario_id},
    ).first()


def _pendiente(conn, token: str):
    return conn.execute(
        text("SELECT usuario_id, intentos FROM login_pendientes WHERE token = :t AND expira_en > NOW()"),
        {"t": token},
    ).first()


def _fallo_de_codigo(conn, token: str, pendiente, secreto=None, ultimo_paso=0, codigo="") -> str:
    """Cuenta el intento fallido y devuelve el mensaje para el usuario."""
    if secreto and totp.codigo_ya_usado(secreto, codigo, ultimo_paso):
        return totp.MENSAJE_USADO   # el código era correcto: no cuenta como intento fallido
    limitador.anotar(f"codigo:{pendiente.usuario_id}", config.LOGIN_VENTANA_SEG)
    intentos = pendiente.intentos + 1
    if intentos >= totp.MAX_INTENTOS:
        conn.execute(text("DELETE FROM login_pendientes WHERE token = :t"), {"t": token})
        return "Demasiados intentos. Vuelve a escribir tu correo y contraseña."
    conn.execute(text("UPDATE login_pendientes SET intentos = :i WHERE token = :t"), {"i": intentos, "t": token})
    return f"Código incorrecto. Te quedan {totp.MAX_INTENTOS - intentos} intentos."


def validar_codigo_o_recuperacion(conn, usuario_id: int, fila, codigo: str):
    """
    Comprueba un código del Authenticator o un código de recuperación.
    Devuelve ("totp", paso), ("recuperacion", None) o (None, None).
    """
    if totp.parece_recuperacion(codigo):
        return ("recuperacion", None) if totp.usar_codigo_recuperacion(conn, usuario_id, codigo) else (None, None)
    paso = totp.verificar_codigo(totp.revelar(fila.totp_secreto), codigo, fila.totp_ultimo_paso)
    return ("totp", paso) if paso is not None else (None, None)


def _avisar_inicio(tareas: BackgroundTasks, request: Request, correo: str, con_codigo_recuperacion: bool = False) -> None:
    """CAMBIO (correos): "acabas de entrar a Picksy, ¿fuiste tú?". Se envía después de responder (no demora el login)."""
    tareas.add_task(correos.inicio_de_sesion, correo, limitador.ip_de(request),
                    request.headers.get("user-agent"), con_codigo_recuperacion)


MENSAJE_VENCIDO = "El inicio de sesión venció. Vuelve a escribir tu correo y contraseña."


# ---------- 1. Segundo paso del login ----------
@router.post("/login")
def login_segundo_paso(datos: LoginDosPasosEntrada, request: Request, tareas: BackgroundTasks):
    error = None  # el error se lanza DESPUÉS de cerrar el bloque, para que el contador de intentos se guarde

    with engine.begin() as conn:
        pendiente = _pendiente(conn, datos.token_2fa)
        if pendiente is None:
            error = MENSAJE_VENCIDO
        else:
            # Límite por usuario: aunque pida tokens nuevos, no puede probar más de 10 códigos cada 15 minutos.
            limitador.exigir_libre(f"codigo:{pendiente.usuario_id}", config.LOGIN_MAX_FALLOS * 2, config.LOGIN_VENTANA_SEG)
            fila = _datos_usuario(conn, pendiente.usuario_id)
            tipo, paso = validar_codigo_o_recuperacion(conn, pendiente.usuario_id, fila, datos.codigo) if fila.totp_activo else (None, None)
            if tipo is None:
                secreto = totp.revelar(fila.totp_secreto) if fila.totp_activo else None
                error = _fallo_de_codigo(conn, datos.token_2fa, pendiente, secreto, fila.totp_ultimo_paso, datos.codigo)
            else:
                if tipo == "totp":
                    conn.execute(text("UPDATE usuarios SET totp_ultimo_paso = :p WHERE id = :id"),
                                 {"p": paso, "id": pendiente.usuario_id})
                conn.execute(text("DELETE FROM login_pendientes WHERE token = :t"), {"t": datos.token_2fa})
                sesion = crear_sesion(conn, pendiente.usuario_id)
                if tipo == "recuperacion":
                    sesion["uso_codigo_recuperacion"] = True
                    sesion["codigos_restantes"] = totp.codigos_restantes(conn, pendiente.usuario_id)
                _avisar_inicio(tareas, request, fila.correo, tipo == "recuperacion")
                return sesion

    raise HTTPException(status_code=401, detail=error)


# ---------- 2. Cuenta antigua: generar la clave y el QR ----------
@router.post("/pendiente/configurar")
def configurar_pendiente(datos: TokenEntrada):
    with engine.begin() as conn:
        pendiente = _pendiente(conn, datos.token_2fa)
        if pendiente is None:
            raise HTTPException(status_code=401, detail=MENSAJE_VENCIDO)
        fila = _datos_usuario(conn, pendiente.usuario_id)
        if fila.totp_activo:
            raise HTTPException(status_code=409, detail="Esta cuenta ya tiene Google Authenticator. Escribe el código de la app.")

        secreto = totp.nuevo_secreto()
        conn.execute(
            text("UPDATE usuarios SET totp_secreto = :s, totp_ultimo_paso = 0 WHERE id = :id"),
            {"s": totp.proteger(secreto), "id": pendiente.usuario_id},
        )

    return {
        **totp.datos_para_app(secreto, fila.correo),   # secreto, uri y qr
        "mensaje": "Escanea el QR con Google Authenticator y escribe el código de 6 dígitos para entrar.",
    }


# ---------- 3. Cuenta antigua: confirmar el código, activar el 2FA y entrar ----------
@router.post("/pendiente/activar")
def activar_pendiente(datos: LoginDosPasosEntrada, request: Request, tareas: BackgroundTasks):
    error = None

    with engine.begin() as conn:
        pendiente = _pendiente(conn, datos.token_2fa)
        if pendiente is None:
            error = MENSAJE_VENCIDO
        else:
            fila = _datos_usuario(conn, pendiente.usuario_id)
            if fila.totp_activo:
                error = "Esta cuenta ya tiene Google Authenticator. Vuelve a iniciar sesión."
            elif not fila.totp_secreto:
                error = "Primero genera el QR en /auth/2fa/pendiente/configurar"
            else:
                secreto = totp.revelar(fila.totp_secreto)
                paso = totp.verificar_codigo(secreto, datos.codigo, fila.totp_ultimo_paso)
                if paso is None:
                    error = _fallo_de_codigo(conn, datos.token_2fa, pendiente, secreto, fila.totp_ultimo_paso, datos.codigo)
                else:
                    conn.execute(
                        text("UPDATE usuarios SET totp_activo = TRUE, totp_ultimo_paso = :p WHERE id = :id"),
                        {"p": paso, "id": pendiente.usuario_id},
                    )
                    conn.execute(text("DELETE FROM login_pendientes WHERE token = :t"), {"t": datos.token_2fa})
                    sesion = crear_sesion(conn, pendiente.usuario_id)
                    sesion["codigos_recuperacion"] = totp.generar_codigos_recuperacion(conn, pendiente.usuario_id)
                    _avisar_inicio(tareas, request, fila.correo)
                    return sesion

    raise HTTPException(status_code=401, detail=error)


# ---------- 4. Códigos de recuperación nuevos (con sesión) ----------
@router.post("/codigos-recuperacion")
def regenerar_codigos(datos: RegenerarEntrada, usuario=Depends(usuario_actual)):
    limitador.exigir_libre(f"codigo:{usuario['id']}", config.LOGIN_MAX_FALLOS * 2, config.LOGIN_VENTANA_SEG)
    with engine.begin() as conn:
        fila = _datos_usuario(conn, usuario["id"])
        if not verificar(datos.contrasena, fila.contrasena_hash):
            limitador.anotar(f"codigo:{usuario['id']}", config.LOGIN_VENTANA_SEG)
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")
        # Para generar códigos nuevos se pide el código de la app (no uno de recuperación).
        paso = totp.verificar_codigo(totp.revelar(fila.totp_secreto), datos.codigo, fila.totp_ultimo_paso) if not totp.parece_recuperacion(datos.codigo) else None
        if paso is None:
            limitador.anotar(f"codigo:{usuario['id']}", config.LOGIN_VENTANA_SEG)
            raise HTTPException(status_code=400, detail="Código incorrecto o vencido")
        conn.execute(text("UPDATE usuarios SET totp_ultimo_paso = :p WHERE id = :id"), {"p": paso, "id": usuario["id"]})
        return {"codigos_recuperacion": totp.generar_codigos_recuperacion(conn, usuario["id"])}
