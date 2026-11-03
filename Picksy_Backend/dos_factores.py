"""
Verificación en dos pasos (2FA) con TOTP: funciona con Google Authenticator, Microsoft Authenticator, Authy, etc.

Cómo funciona (resumen):
  1. El servidor genera una clave secreta y se la muestra al usuario como código QR.
  2. El usuario escanea el QR con la app. Desde ese momento, la app y el servidor
     calculan el MISMO número de 6 dígitos, que cambia cada 30 segundos.
  3. Al iniciar sesión, además de la contraseña, el usuario escribe ese número.

Endpoints:
    POST /auth/2fa/configurar   (con sesión)  genera la clave y el QR
    POST /auth/2fa/activar      (con sesión)  confirma con un código y activa el 2FA
    POST /auth/2fa/desactivar   (con sesión)  pide contraseña + código
    POST /auth/2fa/login        (pública)     segundo paso del login: token_2fa + código -> sesión
"""
import base64
import hmac
import io
import re
import time
from typing import Optional

import pyotp
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from auth import crear_sesion, usuario_actual, verificar
from database import engine

router = APIRouter(prefix="/auth/2fa", tags=["Doble factor (2FA)"])

NOMBRE_APP = "Picksy"       # aparece en Google Authenticator
PASO_SEGUNDOS = 30          # el código cambia cada 30 s (estándar TOTP)
VENTANA = 1                 # se acepta también el código anterior y el siguiente (relojes algo desfasados)
MAX_INTENTOS = 5            # intentos de código por cada inicio de sesión pendiente


# ---------- Modelos ----------
class CodigoEntrada(BaseModel):
    codigo: str = Field(min_length=6, max_length=10, description="Código de 6 dígitos de la app")


class DesactivarEntrada(CodigoEntrada):
    contrasena: str


class LoginDosPasosEntrada(CodigoEntrada):
    token_2fa: str


# ---------- Funciones auxiliares ----------
def _limpiar(codigo: str) -> str:
    """'123 456' -> '123456' (la app muestra el código con un espacio)."""
    return re.sub(r"\s", "", codigo)


def verificar_codigo(secreto: str, codigo: str, ultimo_paso: int):
    """
    Devuelve (paso, ya_usado):
      - (paso, False)  -> código válido; 'paso' es el intervalo de 30 s en el que se generó
      - (None, True)   -> el código es correcto pero YA se usó (la app sigue mostrando el mismo hasta que pasen 30 s)
      - (None, False)  -> código incorrecto
    Rechaza pasos ya usados (ultimo_paso): así un código espiado no sirve una segunda vez.
    """
    codigo = _limpiar(codigo)
    if not re.fullmatch(r"\d{6}", codigo):
        return None, False
    totp = pyotp.TOTP(secreto, interval=PASO_SEGUNDOS)
    ahora = time.time()
    ya_usado = False
    for desplazamiento in range(-VENTANA, VENTANA + 1):
        momento = ahora + desplazamiento * PASO_SEGUNDOS
        paso = int(momento // PASO_SEGUNDOS)
        if hmac.compare_digest(totp.at(momento), codigo):
            if paso > ultimo_paso:
                return paso, False
            ya_usado = True
    return None, ya_usado


MENSAJE_USADO = "Ese código ya se usó. Espera a que cambie en la app (cada 30 segundos) e inténtalo con el nuevo."


def _qr_como_imagen(uri: str) -> str:
    """Genera el QR en formato SVG y lo devuelve listo para usar en <img src="...">."""
    imagen = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buffer = io.BytesIO()
    imagen.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _datos_2fa(conn, usuario_id: int):
    return conn.execute(
        text("SELECT totp_secreto, totp_activo, totp_ultimo_paso, contrasena_hash FROM usuarios WHERE id = :id"),
        {"id": usuario_id},
    ).first()


# ---------- 1. Configurar: generar clave y QR ----------
@router.post("/configurar")
def configurar(usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        datos = _datos_2fa(conn, usuario["id"])
        if datos.totp_activo:
            raise HTTPException(status_code=409, detail="El 2FA ya está activado. Desactívalo primero para configurarlo de nuevo.")

        secreto = pyotp.random_base32()
        conn.execute(
            text("UPDATE usuarios SET totp_secreto = :s, totp_ultimo_paso = 0 WHERE id = :id"),
            {"s": secreto, "id": usuario["id"]},
        )

    uri = pyotp.TOTP(secreto, interval=PASO_SEGUNDOS).provisioning_uri(name=usuario["correo"], issuer_name=NOMBRE_APP)
    return {
        "secreto": secreto,          # por si el usuario prefiere escribirlo a mano en la app
        "uri": uri,
        "qr": _qr_como_imagen(uri),  # <img src="...">
        "mensaje": "Escanea el QR con Google Authenticator y confirma con el código de 6 dígitos en /auth/2fa/activar.",
    }


# ---------- 2. Activar: confirmar que la app quedó bien configurada ----------
@router.post("/activar")
def activar(datos: CodigoEntrada, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        fila = _datos_2fa(conn, usuario["id"])
        if fila.totp_activo:
            raise HTTPException(status_code=409, detail="El 2FA ya está activado")
        if not fila.totp_secreto:
            raise HTTPException(status_code=400, detail="Primero genera el QR en /auth/2fa/configurar")

        paso, ya_usado = verificar_codigo(fila.totp_secreto, datos.codigo, fila.totp_ultimo_paso)
        if paso is None:
            raise HTTPException(status_code=400, detail=MENSAJE_USADO if ya_usado else "Código incorrecto o vencido. Revisa la hora del teléfono e inténtalo de nuevo.")

        conn.execute(
            text("UPDATE usuarios SET totp_activo = TRUE, totp_ultimo_paso = :p WHERE id = :id"),
            {"p": paso, "id": usuario["id"]},
        )
    return {"mensaje": "Verificación en dos pasos activada"}


# ---------- 3. Desactivar ----------
@router.post("/desactivar")
def desactivar(datos: DesactivarEntrada, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        fila = _datos_2fa(conn, usuario["id"])
        if not fila.totp_activo:
            raise HTTPException(status_code=400, detail="El 2FA no está activado")
        # Se pide contraseña Y código: si alguien deja la sesión abierta, no puede quitar la protección.
        if not verificar(datos.contrasena, fila.contrasena_hash):
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")
        paso, ya_usado = verificar_codigo(fila.totp_secreto, datos.codigo, fila.totp_ultimo_paso)
        if paso is None:
            raise HTTPException(status_code=400, detail=MENSAJE_USADO if ya_usado else "Código incorrecto o vencido")

        conn.execute(
            text("UPDATE usuarios SET totp_activo = FALSE, totp_secreto = NULL, totp_ultimo_paso = 0 WHERE id = :id"),
            {"id": usuario["id"]},
        )
    return {"mensaje": "Verificación en dos pasos desactivada"}


# ---------- 4. Segundo paso del login ----------
@router.post("/login")
def login_segundo_paso(datos: LoginDosPasosEntrada):
    error = None  # el error se lanza DESPUÉS de cerrar el bloque, para que el contador de intentos se guarde

    with engine.begin() as conn:
        pendiente = conn.execute(
            text("SELECT usuario_id, intentos FROM login_pendientes WHERE token = :t AND expira_en > NOW()"),
            {"t": datos.token_2fa},
        ).first()

        if pendiente is None:
            error = "El inicio de sesión venció. Vuelve a escribir tu correo y contraseña."
        else:
            fila = _datos_2fa(conn, pendiente.usuario_id)
            paso, ya_usado = verificar_codigo(fila.totp_secreto, datos.codigo, fila.totp_ultimo_paso) if fila.totp_activo else (None, False)

            if paso is None:
                intentos = pendiente.intentos + 1
                if intentos >= MAX_INTENTOS:
                    conn.execute(text("DELETE FROM login_pendientes WHERE token = :t"), {"t": datos.token_2fa})
                    error = "Demasiados intentos. Vuelve a escribir tu correo y contraseña."
                else:
                    conn.execute(text("UPDATE login_pendientes SET intentos = :i WHERE token = :t"),
                                 {"i": intentos, "t": datos.token_2fa})
                    motivo = MENSAJE_USADO if ya_usado else "Código incorrecto."
                    error = f"{motivo} Te quedan {MAX_INTENTOS - intentos} intentos."
            else:
                conn.execute(text("UPDATE usuarios SET totp_ultimo_paso = :p WHERE id = :id"),
                             {"p": paso, "id": pendiente.usuario_id})
                conn.execute(text("DELETE FROM login_pendientes WHERE token = :t"), {"t": datos.token_2fa})
                return crear_sesion(conn, pendiente.usuario_id)

    raise HTTPException(status_code=401, detail=error)