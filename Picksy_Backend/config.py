"""
Configuración de Picksy: todo lo que cambia entre tu computador y el servidor (AWS) se lee del archivo .env.
Si una variable no está, se usa el valor por defecto de abajo, así que el proyecto funciona igual que antes.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


# Cuánto dura una sesión (el profesor pidió tokens de corta duración).
SESION_HORAS = _entero("SESION_HORAS", 2)

# Direcciones del frontend que pueden llamar a la API (CORS), separadas por coma.
CORS_ORIGENES = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGENES",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5501,http://localhost:5501",
    ).split(",")
    if o.strip()
]

# Dirección pública del frontend: se usa para armar el enlace del correo de "recuperar contraseña".
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5500").rstrip("/")

# Clave para cifrar el secreto del Google Authenticator en la base de datos (ver preparar_base.py).
TOTP_CLAVE = os.getenv("TOTP_CLAVE", "").strip()

# Correo saliente (recuperar contraseña). Si SMTP_HOST está vacío, el enlace se imprime en la terminal del backend.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = _entero("SMTP_PORT", 587)
SMTP_USUARIO = os.getenv("SMTP_USUARIO", "").strip()
SMTP_CLAVE = os.getenv("SMTP_CLAVE", "")
SMTP_REMITENTE = os.getenv("SMTP_REMITENTE", SMTP_USUARIO or "no-responder@picksy.local")

# Límites de intentos (protección contra adivinar contraseñas o códigos).
LOGIN_MAX_FALLOS = _entero("LOGIN_MAX_FALLOS", 5)          # fallos por correo ...
LOGIN_VENTANA_SEG = _entero("LOGIN_VENTANA_SEG", 900)      # ... dentro de estos segundos (15 min)
