"""
Autenticación: RF-01 (registro), RF-02 (login/logout), RF-03 (sesión) y RNF-02 (hash).
Los resultados esperados salen del ERS y de los criterios de aceptación; los códigos HTTP
exactos (201, 409, 422, 401) salen del contrato de la API.
"""
from datetime import datetime, timedelta, timezone

import pytest

from ayudas import (CLAVE_OK, consulta_db, correo_nuevo, iniciar_sesion, registrar,
                    usuario_con_sesion)

pytestmark = pytest.mark.req("RF-01")


# ----------------------------------------------------------------------------- RF-01
def test_cp01_1_registro_valido_crea_cuenta(client):
    correo = correo_nuevo()
    r = registrar(client, correo)
    assert r.status_code == 201
    assert consulta_db("SELECT 1 FROM usuarios WHERE correo=%s", (correo,))
    assert CLAVE_OK not in r.text, "La respuesta no debe devolver la contraseña"


def test_cp01_2_correo_repetido_se_rechaza_con_mensaje_claro(client):
    correo = correo_nuevo()
    registrar(client, correo)
    r = registrar(client, correo)
    assert r.status_code == 409
    assert "correo" in r.json()["detail"].lower()
    assert consulta_db("SELECT COUNT(*) FROM usuarios WHERE correo=%s", (correo,))[0][0] == 1


def test_cp01_2b_correo_repetido_con_otras_mayusculas(client):
    correo = correo_nuevo()
    registrar(client, correo)
    assert registrar(client, correo.upper().replace("@TEST.COM", "@test.com")).status_code == 409


@pytest.mark.parametrize("correo", ["abc", "abc@", "@test.com", "sin arroba.com", ""])
def test_cp01_3_correo_invalido(client, correo):
    assert registrar(client, correo).status_code == 422


@pytest.mark.parametrize("clave,esperado", [
    ("1234567", 422),        # 7 caracteres: límite inferior inválido
    ("12345678", 201),       # 8 caracteres: límite inferior válido
    ("x" * 50, 201),         # 50: límite superior válido
    ("x" * 51, 422),         # 51: la API rechaza (OBS: el ERS no define máximo)
])
def test_cp01_4_limites_de_la_contrasena(client, clave, esperado):
    assert registrar(client, correo_nuevo(), clave).status_code == esperado


# ----------------------------------------------------------------------------- RF-02
@pytest.mark.req("RF-02")
def test_cp02_1_login_correcto_devuelve_token_con_expiracion(client):
    correo = correo_nuevo()
    registrar(client, correo)
    r = iniciar_sesion(client, correo)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token"] and cuerpo["tipo"] == "Bearer"
    assert datetime.fromisoformat(cuerpo["expira_en"]) > datetime.now(timezone.utc)


@pytest.mark.req("RF-02")
def test_cp02_2_error_no_revela_que_dato_fallo(client):
    """Criterio de aceptación: contraseña mala y correo inexistente dan EXACTAMENTE el mismo error."""
    correo = correo_nuevo()
    registrar(client, correo)
    mala_clave = iniciar_sesion(client, correo, "ClaveIncorrecta99")
    sin_cuenta = iniciar_sesion(client, correo_nuevo())
    assert mala_clave.status_code == sin_cuenta.status_code == 401
    assert mala_clave.json() == sin_cuenta.json()
    assert "token" not in mala_clave.json()


@pytest.mark.req("RF-02")
def test_cp02_4_cerrar_sesion_invalida_el_token(client):
    _, cab = usuario_con_sesion(client)
    assert client.get("/auth/me", headers=cab).status_code == 200
    assert client.post("/auth/logout", headers=cab).status_code == 200
    # Criterio de aceptación: tras cerrar sesión no se accede a datos privados
    assert client.get("/auth/me", headers=cab).status_code == 401
    assert client.get("/historial", headers=cab).status_code == 401


@pytest.mark.req("RF-02")
@pytest.mark.parametrize("ruta,metodo", [
    ("/auth/me", "get"), ("/auth/logout", "post"), ("/historial", "get"), ("/historial", "delete"),
])
def test_cp02_5_rutas_privadas_sin_token_dan_401(client, ruta, metodo):
    assert getattr(client, metodo)(ruta).status_code == 401


@pytest.mark.req("RF-02")
def test_cp02_5b_token_inventado_da_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer token-que-no-existe"})
    assert r.status_code == 401


# ----------------------------------------------------------------------------- RF-03
@pytest.mark.req("RF-03")
def test_cp03_1_sesion_vigente_da_acceso(client):
    correo, cab = usuario_con_sesion(client)
    r = client.get("/auth/me", headers=cab)
    assert r.status_code == 200 and r.json()["correo"] == correo


@pytest.mark.req("RF-03")
def test_cp03_1b_la_sesion_dura_24_horas(client):
    """A-04/ERS: 'persiste durante el tiempo definido'. La API define 24 h."""
    correo = correo_nuevo()
    registrar(client, correo)
    expira = datetime.fromisoformat(iniciar_sesion(client, correo).json()["expira_en"])
    horas = (expira - datetime.now(timezone.utc)) / timedelta(hours=1)
    assert 23.9 < horas <= 24.0


@pytest.mark.req("RF-03")
def test_cp03_2_sesion_vencida_se_rechaza_de_forma_controlada(client):
    correo, cab = usuario_con_sesion(client)
    token = cab["Authorization"].split()[1]
    # Se fuerza el vencimiento en la base de PRUEBA (no hay que esperar 24 h)
    consulta_db("UPDATE sesiones SET expira_en = NOW() - INTERVAL '1 second' WHERE token = %s", (token,))
    r = client.get("/auth/me", headers=cab)
    assert r.status_code == 401
    assert "expirada" in r.json()["detail"].lower() or "inválida" in r.json()["detail"].lower()


# ----------------------------------------------------------------------------- RNF-02
@pytest.mark.req("RNF-02")
def test_rnf02_1_contrasena_guardada_como_hash_bcrypt(client):
    correo = correo_nuevo()
    registrar(client, correo)
    guardado = consulta_db("SELECT contrasena_hash FROM usuarios WHERE correo=%s", (correo,))[0][0]
    assert guardado != CLAVE_OK
    assert guardado.startswith("$2b$"), "Debe ser bcrypt"


@pytest.mark.req("RNF-02")
def test_rnf02_1b_dos_usuarios_con_la_misma_clave_tienen_hash_distinto(client):
    """Prueba que bcrypt usa 'sal' aleatoria: no se puede comparar hashes para adivinar claves."""
    a, b = correo_nuevo(), correo_nuevo()
    registrar(client, a)
    registrar(client, b)
    hashes = [consulta_db("SELECT contrasena_hash FROM usuarios WHERE correo=%s", (c,))[0][0] for c in (a, b)]
    assert hashes[0] != hashes[1]


@pytest.mark.req("RNF-02")
def test_rnf02_1c_las_respuestas_nunca_exponen_el_hash(client):
    correo = correo_nuevo()
    textos = [registrar(client, correo).text, iniciar_sesion(client, correo).text]
    token = iniciar_sesion(client, correo).json()["token"]
    textos.append(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).text)
    for t in textos:
        assert "$2b$" not in t and "hash" not in t.lower()
