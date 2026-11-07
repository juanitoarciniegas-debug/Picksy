"""
Pruebas automatizadas de QA - Picksy API (VERSIÓN 3: registro y login con Google Authenticator, /buscar con sesión)
Ubicación: Picksy_Backend/test_api.py
Ejecutar:  pytest test_api.py -v --html=reporte_qa.html --self-contained-html

CAMBIO v3: ya no se puede registrar ni entrar solo con correo y contraseña.
  registro  = POST /auth/registro + POST /auth/registro/confirmar (código de 6 dígitos)
  login     = POST /auth/login    + POST /auth/2fa/login         (código de 6 dígitos)
Los códigos se calculan con pyotp igual que la app del celular. Las pruebas rápidas y completas del bot están en qa/.
"""
import os
import time
import uuid

import pyotp
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from main import app

load_dotenv()
client = TestClient(app)

# ---------------- CONFIG ----------------
URL_REGISTRO = "/auth/registro"
URL_LOGIN = "/auth/login"
URL_BUSCAR = "/buscar"
URL_TIENDAS = "/tiendas"
URL_HISTORIAL = "/historial"

CAMPO_CORREO = "correo"
CAMPO_CLAVE = "contrasena"
CAMPO_TOKEN = "token"            # el login devuelve {"token", "tipo", "expira_en"}
PARAM_PRODUCTO = "producto"
PARAM_PRESUPUESTO = "presupuesto"
CLAVE_OK = "Prueba1234"
# ----------------------------------------


def correo_nuevo():
    return f"qa_{uuid.uuid4().hex[:8]}@test.com"


SECRETOS = {}   # correo -> secreto del Authenticator (solo vive en memoria durante las pruebas)


def _codigo(secreto):
    return pyotp.TOTP(secreto, interval=30).now()


def registrar_paso1(correo, clave=CLAVE_OK):
    return client.post(URL_REGISTRO, json={CAMPO_CORREO: correo, CAMPO_CLAVE: clave})


def registrar(correo, clave=CLAVE_OK):
    """Registro COMPLETO (paso 1 + confirmar con el código). Devuelve la respuesta del último paso hecho."""
    r1 = registrar_paso1(correo, clave)
    if r1.status_code != 201:
        return r1
    SECRETOS[correo] = r1.json()["secreto"]
    return client.post(URL_REGISTRO + "/confirmar", json={
        "token_registro": r1.json()["token_registro"], "codigo": _codigo(r1.json()["secreto"])})


def login(correo, clave=CLAVE_OK):
    """PASO 1 del login (contraseña). Con 2FA activo devuelve token_2fa, no la sesión."""
    return client.post(URL_LOGIN, json={CAMPO_CORREO: correo, CAMPO_CLAVE: clave})


def login_completo(correo, clave=CLAVE_OK):
    """Los DOS pasos. Devuelve la respuesta con el token de sesión."""
    paso1 = login(correo, clave)
    assert paso1.status_code == 200, paso1.text
    consulta_db("UPDATE usuarios SET totp_ultimo_paso = 0 WHERE correo = %s", (correo,))   # anti-repetición de QA
    return client.post("/auth/2fa/login", json={"token_2fa": paso1.json()["token_2fa"], "codigo": _codigo(SECRETOS[correo])})


def headers_de(correo):
    assert registrar(correo).status_code == 201
    token = login_completo(correo).json()[CAMPO_TOKEN]
    return {"Authorization": f"Bearer {token}"}


_sesion = {}


def sesion_por_defecto():
    """/buscar y /tiendas exigen sesión en la v3: una cuenta de QA compartida por estas pruebas."""
    if "h" not in _sesion:
        _sesion["h"] = headers_de(correo_nuevo())
    return _sesion["h"]


def buscar(producto, presupuesto, headers=None, **extra):
    params = {PARAM_PRODUCTO: producto, PARAM_PRESUPUESTO: presupuesto, **extra}
    return client.get(URL_BUSCAR, params=params, headers=sesion_por_defecto() if headers is None else headers)


def buscar_ok(producto, presupuesto, headers=None, **extra):
    """Busca y EXIGE 200: así ningún test pasa en vacío por un error de ruta."""
    r = buscar(producto, presupuesto, headers, **extra)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    return r.json()


def exigir_resultados(data):
    """Si las tiendas no devolvieron nada, el test se marca SKIPPED (no 'pasó')."""
    if not data["viables"]:
        pytest.skip(f"Sin resultados de las tiendas. Avisos: {data.get('avisos')}")


def consulta_db(sql, params=None):
    import psycopg2
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


@pytest.fixture(scope="session", autouse=True)
def limpiar_usuarios_de_prueba():
    """Borra al final los usuarios qa_*@test.com creados por las pruebas (sus sesiones, historial y carritos se van en cascada)."""
    yield
    for sql in ("DELETE FROM registros_pendientes WHERE correo LIKE 'qa\\_%@test.com'",
                "DELETE FROM usuarios WHERE correo LIKE 'qa\\_%@test.com'"):
        try:
            consulta_db(sql)
        except Exception as e:
            print("Limpieza no realizada:", e)


@pytest.fixture(autouse=True)
def limitador_en_cero():
    """v3: la API limita registros y logins (429). Todas las pruebas llegan desde la misma conexión: se reinicia el contador."""
    import limitador
    limitador.reiniciar()


# ---------------- REGISTRO / LOGIN ----------------
def test_cp01_registro_valido():
    correo = correo_nuevo()
    assert registrar(correo).status_code == 201
    assert consulta_db("SELECT 1 FROM usuarios WHERE correo=%s", (correo,))


def test_cp01b_sin_confirmar_el_codigo_la_cuenta_no_existe():
    correo = correo_nuevo()
    assert registrar_paso1(correo).status_code == 201
    assert not consulta_db("SELECT 1 FROM usuarios WHERE correo=%s", (correo,))


def test_cp02_contrasena_corta():
    assert registrar_paso1(correo_nuevo(), "1234").status_code in (400, 422)


@pytest.mark.parametrize("correo", ["abc", "abc@", "@test.com", ""])
def test_cp03_correo_invalido(correo):
    assert registrar_paso1(correo).status_code in (400, 422)


def test_cp04_correo_duplicado():
    correo = correo_nuevo()
    registrar(correo)
    assert registrar_paso1(correo).status_code in (400, 409, 422)
    filas = consulta_db("SELECT COUNT(*) FROM usuarios WHERE correo=%s", (correo,))
    assert filas[0][0] == 1


def test_cp05_login_valido_en_dos_pasos():
    correo = correo_nuevo()
    registrar(correo)
    paso1 = login(correo)
    assert paso1.status_code == 200
    assert paso1.json()["requiere_2fa"] is True and CAMPO_TOKEN not in paso1.json(), "La contraseña sola no da sesión"
    r = login_completo(correo)
    assert r.status_code == 200
    assert CAMPO_TOKEN in r.json()


def test_cp06_login_clave_erronea():
    correo = correo_nuevo()
    registrar(correo)
    r = login(correo, "ClaveIncorrecta99")
    assert r.status_code in (400, 401)
    assert CAMPO_TOKEN not in r.json()


def test_cp07_clave_cifrada_en_bd():
    correo = correo_nuevo()
    registrar(correo)
    hash_guardado = consulta_db(
        "SELECT contrasena_hash FROM usuarios WHERE correo=%s", (correo,))[0][0]
    assert hash_guardado != CLAVE_OK
    assert hash_guardado.startswith("$2b$")


# ---------------- BÚSQUEDA ----------------
def test_tiendas_disponibles():
    """RF-05: el sistema expone las tiendas registradas (v3: con sesión)."""
    r = client.get(URL_TIENDAS, headers=sesion_por_defecto())
    assert r.status_code == 200
    tiendas = r.json()
    assert len(tiendas) > 0
    assert all("nombre" in t for t in tiendas)
    print(f"Tiendas registradas: {len(tiendas)} (el ERS dice 10)")


def test_buscar_y_tiendas_sin_sesion_dan_401():
    """v3: la búsqueda ya no es pública."""
    assert client.get(URL_BUSCAR, params={PARAM_PRODUCTO: "celular", PARAM_PRESUPUESTO: 1000000}).status_code == 401
    assert client.get(URL_TIENDAS).status_code == 401


@pytest.mark.slow
def test_cp08_viables_respetan_presupuesto():
    """HU-02: todo lo que se muestra como opción viable cuesta <= presupuesto."""
    presupuesto = 3000000
    data = buscar_ok("celular", presupuesto)
    exigir_resultados(data)
    for op in data["viables"]:
        assert op["total"] <= presupuesto
        assert op["precio"] <= presupuesto
    totales = [op["total"] for op in data["viables"]]
    assert totales == sorted(totales), "Las opciones deben ir de menor a mayor total"
    assert data["mejor_opcion"]["total"] == totales[0]


@pytest.mark.slow
def test_cp09_tiempo_de_respuesta():
    """RNF-01: una búsqueda (sin caché) responde en ~10 s o menos."""
    inicio = time.perf_counter()
    buscar_ok("celular", 3000000, actualizar="true")
    duracion = time.perf_counter() - inicio
    print(f"Duración: {duracion:.1f} s")
    assert duracion <= 10


@pytest.mark.slow
def test_cp10_sin_resultados_no_falla():
    """Presupuesto bajo: responde 200, lista viable vacía y sin mejor opción."""
    data = buscar_ok("celular", 1000)
    assert data["viables"] == []
    assert data["mejor_opcion"] is None
    assert data["ahorro"] is None


@pytest.mark.slow
def test_cp11_cada_opcion_trae_precio_y_tienda():
    """RF-06."""
    data = buscar_ok("celular", 3000000)
    exigir_resultados(data)
    for op in data["viables"]:
        assert op["tienda"]
        assert op["precio"] is not None
        assert op["url"]


@pytest.mark.slow
def test_producto_inexistente_devuelve_lista_vacia():
    """DEF-01 (corregido en la v3 con el filtro de relevancia): un producto que no existe no trae sugerencias sin relación."""
    data = buscar_ok("asdfghjk", 1000000)
    assert data["viables"] == []


@pytest.mark.parametrize("producto,presupuesto", [
    ("celular", 0),            # presupuesto debe ser > 0
    ("celular", -5),
    ("celular", "abc"),
    ("", 1000000),             # producto mínimo 2 caracteres
    ("a", 1000000),
    ("x" * 101, 1000000),      # producto máximo 100 caracteres
])
def test_validacion_de_entradas_invalidas(producto, presupuesto):
    assert buscar(producto, presupuesto).status_code == 422


def test_tienda_desconocida_da_400():
    r = buscar("celular", 1000000, tiendas="TiendaQueNoExiste")
    assert r.status_code == 400


@pytest.mark.slow
def test_inyeccion_sql_no_rompe():
    antes = consulta_db("SELECT COUNT(*) FROM usuarios")[0][0]
    r = buscar("'; DROP TABLE usuarios;--", 1000000)
    assert r.status_code in (200, 422)          # nunca 500
    despues = consulta_db("SELECT COUNT(*) FROM usuarios")[0][0]
    assert despues >= antes


# ---------------- HISTORIAL ----------------
@pytest.mark.slow
def test_cp12_historial_con_sesion():
    """RF-07 / RF-08 / HU-03."""
    h = headers_de(correo_nuevo())
    buscar_ok("celular", 3000000, h)
    r = client.get(URL_HISTORIAL, headers=h)
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert int(r.headers["X-Total-Count"]) >= 1


def test_cp13_visitante_sin_sesion_no_puede_buscar_ni_guarda_historial():
    antes = consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0]
    r = client.get(URL_BUSCAR, params={PARAM_PRODUCTO: "celular", PARAM_PRESUPUESTO: 3000000})   # sin token
    assert r.status_code == 401
    despues = consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0]
    assert despues == antes


@pytest.mark.slow
def test_cp14_historial_aislado_entre_usuarios():
    h1 = headers_de(correo_nuevo())
    h2 = headers_de(correo_nuevo())
    buscar_ok("celular", 3000000, h1)
    assert len(client.get(URL_HISTORIAL, headers=h1).json()) >= 1   # el 1 sí tiene
    assert len(client.get(URL_HISTORIAL, headers=h2).json()) == 0   # el 2 no ve nada


# ---------------- SEGURIDAD ----------------
def test_historial_sin_token_da_401():
    assert client.get(URL_HISTORIAL).status_code in (401, 403)


def test_respuestas_no_exponen_el_hash():
    correo = correo_nuevo()
    textos = [registrar_paso1(correo).text]
    otro = correo_nuevo()
    textos.append(registrar(otro).text)
    textos.append(login(otro).text)
    textos.append(login_completo(otro).text)
    for t in textos:
        assert "$2b$" not in t
        assert "hash" not in t.lower()
