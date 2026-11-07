import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import config
import limitador
import totp
from database import engine

router = APIRouter(prefix="/auth", tags=["Autenticación"])

DURACION_SESION_HORAS = config.SESION_HORAS   # CAMBIO: antes 24 h fijas; ahora viene del .env (SESION_HORAS, por defecto 2)
DURACION_2FA_MINUTOS = 5          # tiempo para escribir el código de 6 dígitos tras la contraseña
DURACION_REGISTRO_MINUTOS = 15    # CAMBIO (2FA): tiempo para escanear el QR y confirmar el registro
esquema_bearer = HTTPBearer(auto_error=False)


# ---------- Modelos: definen qué datos debe enviar el usuario ----------
class RegistroEntrada(BaseModel):
    correo: EmailStr
    contrasena: str = Field(min_length=8, max_length=50)


class RegistroConfirmarEntrada(BaseModel):
    token_registro: str
    codigo: str = Field(min_length=6, max_length=10, description="Código de 6 dígitos de Google Authenticator")


class LoginEntrada(BaseModel):
    correo: EmailStr
    contrasena: str


# ---------- Funciones de contraseña ----------
def encriptar(contrasena: str) -> str:
    return bcrypt.hashpw(contrasena.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar(contrasena: str, hash_guardado: str) -> bool:
    return bcrypt.checkpw(contrasena.encode("utf-8"), hash_guardado.encode("utf-8"))


# ---------- Registro, paso 1 (RF-01) ----------
# CAMBIO (2FA): el usuario YA NO se guarda en la tabla "usuarios" aquí. Sus datos esperan en
# "registros_pendientes" hasta que confirme el código de Google Authenticator (paso 2).
@router.post("/registro", status_code=201)
def registro(datos: RegistroEntrada, request: Request):
    correo = datos.correo.lower()
    # CAMBIO (límite de intentos): máximo 10 registros por hora desde la misma conexión.
    limitador.exigir_libre(f"registro-ip:{limitador.ip_de(request)}", 10, 3600)
    limitador.anotar(f"registro-ip:{limitador.ip_de(request)}", 3600)
    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT id FROM usuarios WHERE correo = :correo"),
            {"correo": correo},
        ).first()
        if existe:
            raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")

        # Limpieza: registros vencidos y cualquier intento anterior con este mismo correo.
        conn.execute(text("DELETE FROM registros_pendientes WHERE expira_en < NOW() OR correo = :correo"),
                     {"correo": correo})

        secreto = totp.nuevo_secreto()
        token = secrets.token_urlsafe(32)
        expira = datetime.now(timezone.utc) + timedelta(minutes=DURACION_REGISTRO_MINUTOS)
        conn.execute(
            text("""
                INSERT INTO registros_pendientes (token, correo, contrasena_hash, totp_secreto, expira_en)
                VALUES (:t, :correo, :hash, :secreto, :expira)
            """),
            {"t": token, "correo": correo, "hash": encriptar(datos.contrasena),
             "secreto": totp.proteger(secreto), "expira": expira},   # CAMBIO (seguridad): se guarda cifrado
        )

    return {
        "token_registro": token,
        "expira_en": expira.isoformat(),
        **totp.datos_para_app(secreto, correo),   # secreto, uri y qr
        "mensaje": "Escanea el QR con Google Authenticator y confirma con el código de 6 dígitos para crear la cuenta.",
    }


# ---------- Registro, paso 2: confirmar el código y crear el usuario de verdad ----------
@router.post("/registro/confirmar", status_code=201)
def registro_confirmar(datos: RegistroConfirmarEntrada):
    error = None    # el error se lanza DESPUÉS de cerrar el bloque, para que el contador de intentos se guarde
    codigo_error = 400

    with engine.begin() as conn:
        pendiente = conn.execute(
            text("""
                SELECT correo, contrasena_hash, totp_secreto, intentos
                FROM registros_pendientes WHERE token = :t AND expira_en > NOW()
            """),
            {"t": datos.token_registro},
        ).first()

        if pendiente is None:
            error = "El registro venció o no existe. Vuelve a llenar el formulario de registro."
        else:
            paso = totp.verificar_codigo(totp.revelar(pendiente.totp_secreto), datos.codigo, 0)
            if paso is None:
                intentos = pendiente.intentos + 1
                if intentos >= totp.MAX_INTENTOS:
                    conn.execute(text("DELETE FROM registros_pendientes WHERE token = :t"), {"t": datos.token_registro})
                    error = "Demasiados intentos. Vuelve a llenar el formulario de registro."
                else:
                    conn.execute(text("UPDATE registros_pendientes SET intentos = :i WHERE token = :t"),
                                 {"i": intentos, "t": datos.token_registro})
                    error = f"Código incorrecto o vencido. Te quedan {totp.MAX_INTENTOS - intentos} intentos."
            else:
                # totp_ultimo_paso queda en 0 a propósito: así el usuario puede entrar enseguida con el mismo
                # código que acaba de usar para registrarse, sin esperar 30 segundos.
                try:
                    # Savepoint: si el correo se registró mientras tanto, el error no daña el resto.
                    with conn.begin_nested():
                        nuevo_id = conn.execute(
                            text("""
                                INSERT INTO usuarios (correo, contrasena_hash, totp_secreto, totp_activo, totp_ultimo_paso, rol)
                                VALUES (:correo, :hash, :secreto, TRUE, 0, 'usuario')
                                RETURNING id
                            """),
                            {"correo": pendiente.correo, "hash": pendiente.contrasena_hash,
                             "secreto": pendiente.totp_secreto},
                        ).scalar()
                        # CAMBIO (recuperación): 8 códigos de un solo uso por si el usuario pierde el teléfono.
                        codigos = totp.generar_codigos_recuperacion(conn, nuevo_id)
                except IntegrityError:
                    error = "Ya existe una cuenta con ese correo"
                    codigo_error = 409
                conn.execute(text("DELETE FROM registros_pendientes WHERE token = :t"), {"t": datos.token_registro})
                if error is None:
                    return {
                        "mensaje": "Cuenta creada correctamente. Ya puedes iniciar sesión con tu correo, contraseña y código.",
                        # Se muestran UNA sola vez: el usuario debe guardarlos en un lugar seguro.
                        "codigos_recuperacion": codigos,
                    }

    raise HTTPException(status_code=codigo_error, detail=error)


# Crear la sesión es una función porque la usan varios caminos:
# el segundo paso del login y la activación del 2FA de cuentas antiguas (dos_factores.py).
def crear_sesion(conn, usuario_id: int) -> dict:
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(hours=DURACION_SESION_HORAS)
    conn.execute(
        text("INSERT INTO sesiones (token, usuario_id, expira_en) VALUES (:token, :uid, :expira)"),
        {"token": token, "uid": usuario_id, "expira": expira},
    )
    return {"token": token, "tipo": "Bearer", "expira_en": expira.isoformat()}


# ---------- Login (RF-02 y RF-03) ----------
# CAMBIO (2FA obligatorio): ya nunca se entrega la sesión solo con la contraseña.
#   - Usuario con Google Authenticator   -> {requiere_2fa: true, token_2fa}      -> POST /auth/2fa/login
#   - Cuenta antigua SIN Authenticator   -> {requiere_configuracion_2fa: true, token_2fa}
#                                           -> POST /auth/2fa/pendiente/configurar y /activar
@router.post("/login")
def login(datos: LoginEntrada, request: Request):
    correo = datos.correo.lower()
    # CAMBIO (límite de intentos): tras LOGIN_MAX_FALLOS contraseñas incorrectas (15 min), responde 429.
    clave_correo, clave_ip = f"login:{correo}", f"login-ip:{limitador.ip_de(request)}"
    limitador.exigir_libre(clave_correo, config.LOGIN_MAX_FALLOS, config.LOGIN_VENTANA_SEG)
    limitador.exigir_libre(clave_ip, config.LOGIN_MAX_FALLOS * 6, config.LOGIN_VENTANA_SEG)
    with engine.begin() as conn:
        usuario = conn.execute(
            text("SELECT id, contrasena_hash, totp_activo FROM usuarios WHERE correo = :correo"),
            {"correo": correo},
        ).first()

        # Mismo mensaje si falla el correo o la contraseña: no revela cuál falló
        if usuario is None or not verificar(datos.contrasena, usuario.contrasena_hash):
            limitador.anotar(clave_correo, config.LOGIN_VENTANA_SEG)
            limitador.anotar(clave_ip, config.LOGIN_VENTANA_SEG)
            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
        limitador.olvidar(clave_correo)

        conn.execute(text("DELETE FROM login_pendientes WHERE expira_en < NOW() OR usuario_id = :uid"),
                     {"uid": usuario.id})
        token_2fa = secrets.token_urlsafe(32)
        expira = datetime.now(timezone.utc) + timedelta(minutes=DURACION_2FA_MINUTOS)
        conn.execute(
            text("INSERT INTO login_pendientes (token, usuario_id, expira_en) VALUES (:t, :uid, :expira)"),
            {"t": token_2fa, "uid": usuario.id, "expira": expira},
        )

        if usuario.totp_activo:
            return {"requiere_2fa": True, "token_2fa": token_2fa, "expira_en": expira.isoformat()}
        return {"requiere_configuracion_2fa": True, "token_2fa": token_2fa, "expira_en": expira.isoformat()}


# ---------- Verificar quién es el usuario (se reutiliza en otros endpoints) ----------
def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(esquema_bearer)):
    if credenciales is None:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")

    token = credenciales.credentials.strip()
    with engine.connect() as conn:
        fila = conn.execute(
            text("""
                SELECT u.id, u.correo, u.rol
                FROM sesiones s
                JOIN usuarios u ON u.id = s.usuario_id
                WHERE s.token = :token AND s.expira_en > NOW()
            """),
            {"token": token},
        ).first()

    if fila is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return {"id": fila.id, "correo": fila.correo, "rol": fila.rol, "token": token}


# CAMBIO (roles): para los endpoints que solo puede usar un administrador (ver admin.py).
def solo_admin(usuario=Depends(usuario_actual)):
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo un administrador puede hacer esto")
    return usuario


# ---------- Logout (RF-02) ----------
@router.post("/logout")
def logout(usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM sesiones WHERE token = :token"),
            {"token": usuario["token"]},
        )
    return {"mensaje": "Sesión cerrada"}


# ---------- Datos del usuario con sesión activa ----------
@router.get("/me")
def me(usuario=Depends(usuario_actual)):
    # CAMBIO (roles): también se informa el rol, para que el frontend muestre u oculte el panel de administrador.
    return {"id": usuario["id"], "correo": usuario["correo"], "rol": usuario["rol"], "dos_factores": True}
