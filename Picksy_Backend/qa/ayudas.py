"""ayudas.py - Funciones comunes de las pruebas de QA (API y base de datos).

VERSIÓN 3 DEL SOFTWARE: el login ya no entrega la sesión con la contraseña sola. El flujo real es
    registro (paso 1) -> confirmar con código de Google Authenticator (paso 2) -> login (paso 1) -> código (paso 2)
Aquí se automatiza ese flujo calculando los códigos con pyotp, igual que la app del celular.
"""
import os
import time
import uuid
from dataclasses import dataclass, field

import psycopg2
import pyotp

PREFIJO_CORREO = "qa_"
DOMINIO_CORREO = "@test.com"
CLAVE_OK = "Prueba1234"
PASO = 30            # segundos que dura cada código TOTP

SIN_SESION = object()   # señal para buscar(): "pide esto SIN iniciar sesión"


def correo_nuevo():
    """Usuario de prueba: qa_xxxxxxxx@test.com. Se borra al terminar la sesión de pruebas."""
    return f"{PREFIJO_CORREO}{uuid.uuid4().hex[:8]}{DOMINIO_CORREO}"


def termino_nuevo():
    """Término de búsqueda único ('qa 1a2b3c'): evita que la caché de una prueba afecte a otra."""
    return f"qa {uuid.uuid4().hex[:6]}"


def consulta_db(sql, params=None):
    con = psycopg2.connect(
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )
    try:
        with con, con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    finally:
        con.close()


# --------------------------------------------------------------------------- códigos TOTP
def codigo_totp(secreto, desplazamiento=0):
    """Código que mostraría la app en el paso actual (+N pasos de 30 s)."""
    return pyotp.TOTP(secreto, interval=PASO).at(time.time() + desplazamiento * PASO)


def codigo_incorrecto(secreto):
    """Un código de 6 dígitos que seguro NO es válido ahora (ni en la ventana ±1 que acepta la API)."""
    validos = {codigo_totp(secreto, d) for d in range(-3, 4)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in validos)


def liberar_paso(correo):
    """La API rechaza reutilizar un paso de 30 s (anti-repetición). Para encadenar varios
    inicios de sesión en una prueba se reinicia el contador en la base de PRUEBA."""
    consulta_db("UPDATE usuarios SET totp_ultimo_paso = 0 WHERE correo = %s", (correo,))


def cab(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- cuentas
@dataclass
class Cuenta:
    correo: str
    clave: str = CLAVE_OK
    secreto: str = ""
    codigos_recuperacion: list = field(default_factory=list)
    token: str = ""

    @property
    def cab(self):
        return cab(self.token)


def registrar(client, correo, clave=CLAVE_OK):
    """PASO 1 del registro: devuelve la respuesta cruda (201 con token_registro, secreto y QR)."""
    return client.post("/auth/registro", json={"correo": correo, "contrasena": clave})


def confirmar_registro(client, token_registro, codigo):
    """PASO 2 del registro."""
    return client.post("/auth/registro/confirmar", json={"token_registro": token_registro, "codigo": codigo})


def crear_cuenta(client, correo=None, clave=CLAVE_OK):
    """Registro completo (los dos pasos). Devuelve la Cuenta SIN sesión."""
    correo = correo or correo_nuevo()
    r1 = registrar(client, correo, clave)
    assert r1.status_code == 201, r1.text
    secreto = r1.json()["secreto"]
    r2 = confirmar_registro(client, r1.json()["token_registro"], codigo_totp(secreto))
    assert r2.status_code == 201, r2.text
    return Cuenta(correo, clave, secreto, r2.json()["codigos_recuperacion"])


def login_paso1(client, correo, clave=CLAVE_OK):
    return client.post("/auth/login", json={"correo": correo, "contrasena": clave})


def login_paso2(client, token_2fa, codigo):
    return client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": codigo})


def iniciar_sesion(client, correo, clave=CLAVE_OK, secreto=None):
    """Login completo. Con `secreto` hace los DOS pasos y devuelve la respuesta del segundo.
    Sin `secreto` solo hace el primero (sirve para comprobar errores de contraseña)."""
    r = login_paso1(client, correo, clave)
    if secreto is None or r.status_code != 200:
        return r
    liberar_paso(correo)
    return login_paso2(client, r.json()["token_2fa"], codigo_totp(secreto))


def cuenta_con_sesion(client):
    """Cuenta nueva con la sesión ya abierta (registro + login en dos pasos)."""
    c = crear_cuenta(client)
    r = iniciar_sesion(client, c.correo, c.clave, c.secreto)
    assert r.status_code == 200, r.text
    c.token = r.json()["token"]
    return c


def usuario_con_sesion(client):
    """Atajo: (correo, cabeceras con el token)."""
    c = cuenta_con_sesion(client)
    return c.correo, c.cab


def admin_con_sesion(client):
    """Cuenta con rol 'admin'. El rol se asigna en la base de PRUEBA (igual que crear_admin.py)
    porque ninguna ruta de la API permite que un usuario se ascienda a sí mismo."""
    c = crear_cuenta(client)
    consulta_db("UPDATE usuarios SET rol = 'admin' WHERE correo = %s", (c.correo,))
    r = iniciar_sesion(client, c.correo, c.clave, c.secreto)
    assert r.status_code == 200, r.text
    c.token = r.json()["token"]
    return c


def id_de(correo):
    return consulta_db("SELECT id FROM usuarios WHERE correo = %s", (correo,))[0][0]


# --------------------------------------------------------------------------- búsqueda
_defecto = {}


def cabecera_por_defecto(client):
    """Una sesión de QA compartida por las pruebas de búsqueda (/buscar exige sesión en la v3).
    Se crea una sola vez; se borra con el resto de usuarios qa_* al terminar."""
    ya = _defecto.get("cab")
    if ya and client.get("/auth/me", headers=ya).status_code == 200:
        return ya
    _defecto["cab"] = cuenta_con_sesion(client).cab
    return _defecto["cab"]


def buscar(client, producto, presupuesto, headers=None, **extra):
    """GET /buscar. headers=None -> con la sesión de QA por defecto; headers=SIN_SESION -> sin sesión."""
    if headers is SIN_SESION:
        headers = {}
    elif headers is None:
        headers = cabecera_por_defecto(client)
    params = {"producto": producto, "presupuesto": presupuesto, **extra}
    return client.get("/buscar", params=params, headers=headers)


def buscar_ok(client, producto, presupuesto, headers=None, **extra):
    """Busca y EXIGE 200, para que ninguna prueba pase 'en vacío' por una ruta equivocada."""
    r = buscar(client, producto, presupuesto, headers, **extra)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    return r.json()


# --------------------------------------------------------------------------- carritos (v3)
def crear_carrito(client, headers, presupuesto=1_000_000, nombre=None):
    """POST /carritos y EXIGE 201. Devuelve el JSON del carrito."""
    cuerpo = {"presupuesto": presupuesto}
    if nombre is not None:
        cuerpo["nombre"] = nombre
    r = client.post("/carritos", json=cuerpo, headers=headers)
    assert r.status_code == 201, f"{r.status_code}: {r.text[:200]}"
    return r.json()


def agregar_item(client, headers, carrito_id, precio, prioridad=3, envio=None, nombre=None, tienda="Éxito", url=None):
    """POST /carritos/{id}/items. Devuelve la respuesta cruda (para poder probar errores).
    La URL es siempre https://qa.test/... para que la limpieza final la borre sin tocar datos reales."""
    cuerpo = {
        "tienda": tienda, "nombre": nombre or f"Producto QA {uuid.uuid4().hex[:6]}",
        "url": url or f"https://qa.test/carrito/{uuid.uuid4().hex}",
        "precio": precio, "prioridad": prioridad,
    }
    if envio is not None:
        cuerpo["envio"] = envio
    return client.post(f"/carritos/{carrito_id}/items", json=cuerpo, headers=headers)


def agregar_item_ok(client, headers, carrito_id, precio, prioridad=3, **extra):
    r = agregar_item(client, headers, carrito_id, precio, prioridad, **extra)
    assert r.status_code == 201, f"{r.status_code}: {r.text[:200]}"
    return r.json()
