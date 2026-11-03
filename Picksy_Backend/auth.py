import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from database import engine

router = APIRouter(prefix="/auth", tags=["Autenticación"])

DURACION_SESION_HORAS = 24
DURACION_2FA_MINUTOS = 5   # CAMBIO (2FA): tiempo para escribir el código de 6 dígitos tras la contraseña
esquema_bearer = HTTPBearer(auto_error=False)

# ---------- Modelos: definen qué datos debe enviar el usuario ----------
class RegistroEntrada(BaseModel):
    correo: EmailStr
    contrasena: str = Field(min_length=8, max_length=50)


class LoginEntrada(BaseModel):
    correo: EmailStr
    contrasena: str


# ---------- Funciones de contraseña ----------
def encriptar(contrasena: str) -> str:
    return bcrypt.hashpw(contrasena.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar(contrasena: str, hash_guardado: str) -> bool:
    return bcrypt.checkpw(contrasena.encode("utf-8"), hash_guardado.encode("utf-8"))


# ---------- Registro (RF-01) ----------
@router.post("/registro", status_code=201)
def registro(datos: RegistroEntrada):
    correo = datos.correo.lower()
    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT id FROM usuarios WHERE correo = :correo"),
            {"correo": correo},
        ).first()
        if existe:
            raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")

        conn.execute(
            text("INSERT INTO usuarios (correo, contrasena_hash) VALUES (:correo, :hash)"),
            {"correo": correo, "hash": encriptar(datos.contrasena)},
        )
    return {"mensaje": "Cuenta creada correctamente"}


# CAMBIO (2FA): crear la sesión se movió a una función, porque ahora la usan dos caminos:
# el login normal (aquí) y el segundo paso del 2FA (dos_factores.py).
def crear_sesion(conn, usuario_id: int) -> dict:
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(hours=DURACION_SESION_HORAS)
    conn.execute(
        text("INSERT INTO sesiones (token, usuario_id, expira_en) VALUES (:token, :uid, :expira)"),
        {"token": token, "uid": usuario_id, "expira": expira},
    )
    return {"token": token, "tipo": "Bearer", "expira_en": expira.isoformat()}


# ---------- Login (RF-02 y RF-03) ----------
@router.post("/login")
def login(datos: LoginEntrada):
    correo = datos.correo.lower()
    with engine.begin() as conn:
        usuario = conn.execute(
            text("SELECT id, contrasena_hash, totp_activo FROM usuarios WHERE correo = :correo"),
            {"correo": correo},
        ).first()

        # Mismo mensaje si falla el correo o la contraseña: no revela cuál falló
        if usuario is None or not verificar(datos.contrasena, usuario.contrasena_hash):
            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

        # CAMBIO (2FA): si el usuario activó la verificación en dos pasos, todavía NO se da la sesión.
        # Se entrega un token temporal, y la sesión real se da en POST /auth/2fa/login con el código de 6 dígitos.
        if usuario.totp_activo:
            token_2fa = secrets.token_urlsafe(32)
            expira = datetime.now(timezone.utc) + timedelta(minutes=DURACION_2FA_MINUTOS)
            conn.execute(
                text("INSERT INTO login_pendientes (token, usuario_id, expira_en) VALUES (:t, :uid, :expira)"),
                {"t": token_2fa, "uid": usuario.id, "expira": expira},
            )
            return {"requiere_2fa": True, "token_2fa": token_2fa, "expira_en": expira.isoformat()}

        return crear_sesion(conn, usuario.id)


# ---------- Verificar quién es el usuario (se reutiliza en otros endpoints) ----------
def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(esquema_bearer)):
    if credenciales is None:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")

    token = credenciales.credentials.strip()
    with engine.connect() as conn:
        fila = conn.execute(
            text("""
                SELECT u.id, u.correo
                FROM sesiones s
                JOIN usuarios u ON u.id = s.usuario_id
                WHERE s.token = :token AND s.expira_en > NOW()
            """),
            {"token": token},
        ).first()

    if fila is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return {"id": fila.id, "correo": fila.correo, "token": token}


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
    # CAMBIO (2FA): también se informa si el usuario tiene activada la verificación en dos pasos.
    with engine.connect() as conn:
        activo = conn.execute(
            text("SELECT totp_activo FROM usuarios WHERE id = :id"),
            {"id": usuario["id"]},
        ).scalar()
    return {"id": usuario["id"], "correo": usuario["correo"], "dos_factores": bool(activo)}