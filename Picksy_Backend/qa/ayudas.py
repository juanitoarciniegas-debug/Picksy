"""ayudas.py - Funciones comunes de las pruebas de QA (API y base de datos)."""
import os
import uuid

import psycopg2

PREFIJO_CORREO = "qa_"
DOMINIO_CORREO = "@test.com"
CLAVE_OK = "Prueba1234"


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


def registrar(client, correo, clave=CLAVE_OK):
    return client.post("/auth/registro", json={"correo": correo, "contrasena": clave})


def iniciar_sesion(client, correo, clave=CLAVE_OK):
    return client.post("/auth/login", json={"correo": correo, "contrasena": clave})


def usuario_con_sesion(client):
    """Crea un usuario, inicia sesión y devuelve (correo, cabeceras con el token)."""
    correo = correo_nuevo()
    assert registrar(client, correo).status_code == 201
    r = iniciar_sesion(client, correo)
    assert r.status_code == 200, r.text
    return correo, {"Authorization": f"Bearer {r.json()['token']}"}


def buscar(client, producto, presupuesto, headers=None, **extra):
    params = {"producto": producto, "presupuesto": presupuesto, **extra}
    return client.get("/buscar", params=params, headers=headers or {})


def buscar_ok(client, producto, presupuesto, headers=None, **extra):
    """Busca y EXIGE 200, para que ninguna prueba pase 'en vacío' por una ruta equivocada."""
    r = buscar(client, producto, presupuesto, headers, **extra)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    return r.json()
