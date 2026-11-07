"""
Funciones de Google Authenticator (TOTP) que usan varios archivos.
(CAMBIO (2FA): estas funciones estaban dentro de dos_factores.py; se pasaron aquí para que
 auth.py y dos_factores.py puedan usarlas sin importarse el uno al otro.)

Cómo funciona (resumen):
  1. El servidor genera una clave secreta y se la muestra al usuario como código QR.
  2. El usuario escanea el QR con la app. Desde ese momento, la app y el servidor
     calculan el MISMO número de 6 dígitos, que cambia cada 30 segundos.
  3. Al iniciar sesión, además de la contraseña, el usuario escribe ese número.
"""
import base64
import hashlib
import hmac
import io
import re
import secrets
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

import pyotp
import qrcode
import qrcode.image.svg

import config

NOMBRE_APP = "Picksy"       # aparece en Google Authenticator
PASO_SEGUNDOS = 30          # el código cambia cada 30 s (estándar TOTP)
VENTANA = 1                 # se acepta también el código anterior y el siguiente (relojes algo desfasados)
MENSAJE_USADO = "Ese código ya se usó. Espera a que la app muestre uno nuevo (cambia cada 30 segundos) e inténtalo de nuevo."
MAX_INTENTOS = 5            # intentos de código por cada registro / inicio de sesión pendiente


def nuevo_secreto() -> str:
    return pyotp.random_base32()


def uri_de(secreto: str, correo: str) -> str:
    return pyotp.TOTP(secreto, interval=PASO_SEGUNDOS).provisioning_uri(name=correo, issuer_name=NOMBRE_APP)


def limpiar(codigo: str) -> str:
    """'123 456' -> '123456' (la app muestra el código con un espacio)."""
    return re.sub(r"\s", "", codigo)


def verificar_codigo(secreto: str, codigo: str, ultimo_paso: int) -> Optional[int]:
    """
    Devuelve el 'paso' de tiempo en el que el código es válido, o None si no lo es.
    Rechaza pasos ya usados (ultimo_paso): así un código espiado no sirve una segunda vez.
    """
    codigo = limpiar(codigo)
    if not re.fullmatch(r"\d{6}", codigo):
        return None
    totp = pyotp.TOTP(secreto, interval=PASO_SEGUNDOS)
    ahora = time.time()
    for desplazamiento in range(-VENTANA, VENTANA + 1):
        momento = ahora + desplazamiento * PASO_SEGUNDOS
        paso = int(momento // PASO_SEGUNDOS)
        if paso > ultimo_paso and hmac.compare_digest(totp.at(momento), codigo):
            return paso
    return None


def codigo_ya_usado(secreto: str, codigo: str, ultimo_paso: int) -> bool:
    """True si el código es correcto pero ya se usó (la app lo sigue mostrando hasta que cambia, cada 30 s)."""
    codigo = limpiar(codigo)
    if not re.fullmatch(r"\d{6}", codigo):
        return False
    totp = pyotp.TOTP(secreto, interval=PASO_SEGUNDOS)
    ahora = time.time()
    for desplazamiento in range(-VENTANA, VENTANA + 1):
        momento = ahora + desplazamiento * PASO_SEGUNDOS
        paso = int(momento // PASO_SEGUNDOS)
        if paso <= ultimo_paso and hmac.compare_digest(totp.at(momento), codigo):
            return True
    return False


def qr_como_imagen(uri: str) -> str:
    """Genera el QR en formato SVG y lo devuelve listo para usar en <img src="...">."""
    imagen = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buffer = io.BytesIO()
    imagen.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def datos_para_app(secreto: str, correo: str) -> dict:
    """Lo que el frontend necesita para mostrar el QR."""
    uri = uri_de(secreto, correo)
    return {"secreto": secreto, "uri": uri, "qr": qr_como_imagen(uri)}


# ---------------------------------------------------------------------------
# Cifrado del secreto (seguridad): en la base de datos NO se guarda la clave del Authenticator en claro.
# Se cifra con la clave TOTP_CLAVE del .env (preparar_base.py la crea sola la primera vez).
# Si TOTP_CLAVE no existe, todo sigue funcionando pero el secreto queda sin cifrar.
# Los secretos viejos (sin cifrar) siguen funcionando: se reconocen porque no empiezan con "gAAAA".
# ---------------------------------------------------------------------------
_fernet = Fernet(config.TOTP_CLAVE.encode()) if config.TOTP_CLAVE else None


def proteger(secreto: str) -> str:
    """Lo que se guarda en la base de datos."""
    return _fernet.encrypt(secreto.encode()).decode() if _fernet else secreto


def revelar(guardado: Optional[str]) -> Optional[str]:
    """El secreto real, a partir de lo que hay en la base de datos."""
    if not guardado or not guardado.startswith("gAAAA"):
        return guardado
    if _fernet is None:
        raise RuntimeError("Hay secretos cifrados pero falta TOTP_CLAVE en el .env")
    try:
        return _fernet.decrypt(guardado.encode()).decode()
    except InvalidToken as error:
        raise RuntimeError("TOTP_CLAVE no corresponde a la que cifró los secretos") from error


# ---------------------------------------------------------------------------
# Códigos de recuperación: 8 códigos de un solo uso para entrar si se pierde el teléfono.
# En la base solo se guarda su hash (como una contraseña).
# ---------------------------------------------------------------------------
CANTIDAD_CODIGOS_RECUPERACION = 8
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin letras/números que se confunden (0/O, 1/I)


def nuevo_codigo_recuperacion() -> str:
    letras = "".join(secrets.choice(_ALFABETO) for _ in range(10))
    return f"{letras[:5]}-{letras[5:]}"


def normalizar_recuperacion(codigo: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", codigo.upper())


def hash_recuperacion(codigo: str) -> str:
    return hashlib.sha256(normalizar_recuperacion(codigo).encode()).hexdigest()


def parece_recuperacion(codigo: str) -> bool:
    """True si NO es un código de 6 dígitos y tiene la forma de un código de recuperación (10 caracteres)."""
    return not re.fullmatch(r"\d{6}", limpiar(codigo)) and len(normalizar_recuperacion(codigo)) == 10


def generar_codigos_recuperacion(conn, usuario_id: int) -> list[str]:
    """Borra los códigos anteriores del usuario, crea 8 nuevos y los devuelve (solo se pueden ver esta vez)."""
    from sqlalchemy import text   # import local: totp.py no depende de la base de datos en el resto de funciones

    conn.execute(text("DELETE FROM codigos_recuperacion WHERE usuario_id = :u"), {"u": usuario_id})
    codigos = [nuevo_codigo_recuperacion() for _ in range(CANTIDAD_CODIGOS_RECUPERACION)]
    for c in codigos:
        conn.execute(
            text("INSERT INTO codigos_recuperacion (usuario_id, codigo_hash) VALUES (:u, :h)"),
            {"u": usuario_id, "h": hash_recuperacion(c)},
        )
    return codigos


def usar_codigo_recuperacion(conn, usuario_id: int, codigo: str) -> bool:
    """Marca el código como usado. Devuelve False si no existe o ya se usó."""
    from sqlalchemy import text

    filas = conn.execute(
        text("""
            UPDATE codigos_recuperacion SET usado_en = NOW()
            WHERE usuario_id = :u AND codigo_hash = :h AND usado_en IS NULL
        """),
        {"u": usuario_id, "h": hash_recuperacion(codigo)},
    ).rowcount
    return filas == 1


def codigos_restantes(conn, usuario_id: int) -> int:
    from sqlalchemy import text

    return conn.execute(
        text("SELECT count(*) FROM codigos_recuperacion WHERE usuario_id = :u AND usado_en IS NULL"),
        {"u": usuario_id},
    ).scalar()
