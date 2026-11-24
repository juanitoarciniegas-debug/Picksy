"""
Pruebas de las herramientas de operación (carpeta herramientas/ y despliegue/). No necesitan Internet ni la base de datos:
usan servidores locales de mentira.

    pytest test_herramientas.py -v
"""
import datetime
import http.server
import json
import shutil
import socket
import ssl
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "herramientas"))

import alerta_certificado  # noqa: E402
import probar_mercadolibre  # noqa: E402
import prueba_carga  # noqa: E402
import revisar_tiendas  # noqa: E402

import buscador  # noqa: E402
import config  # noqa: E402
from conectores.base import Producto  # noqa: E402


# ---------------------------------------------------------------------------------------------- servidores de mentira
class _Manejador(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"       # permite reutilizar la conexión, como hace Nginx con la API

    def do_GET(self):
        codigo = 429 if self.path.startswith("/limitado") else 503 if self.path.startswith("/caido") else 200
        cuerpo = b'{"estado":"ok"}'
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args):       # sin ruido en la consola de las pruebas
        pass


@pytest.fixture
def servidor_http():
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()
    servidor.server_close()


def _puerto_cerrado() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


# ---------------------------------------------------------------------------------------------- prueba_carga.py (TPS)
def test_percentil_sobre_lista_ordenada():
    datos = [i / 1000 for i in range(1, 101)]          # 1 ms ... 100 ms
    assert prueba_carga.percentil(datos, 50) == pytest.approx(50, abs=1.5)
    assert prueba_carga.percentil(datos, 99) == pytest.approx(99, abs=1.5)
    assert prueba_carga.percentil([], 95) == 0.0


def test_carga_mide_tps_y_latencias_contra_un_servidor_local(servidor_http):
    r = prueba_carga.asyncio.run(prueba_carga.medir(servidor_http + "/api/v1/salud", concurrencia=5, segundos=1))
    assert r["peticiones"] > 20 and r["exitosas"] == r["peticiones"]
    assert r["estados"] == {200: r["peticiones"]} and r["errores_de_red"] == {}
    assert r["tps"] > 10
    assert 0 < r["latencia_ms"]["p50"] <= r["latencia_ms"]["p95"] <= r["latencia_ms"]["max"]


def test_carga_no_cuenta_como_exitosas_las_respuestas_que_no_son_2xx(servidor_http):
    r = prueba_carga.asyncio.run(prueba_carga.medir(servidor_http + "/limitado", concurrencia=3, segundos=0.5))
    assert r["exitosas"] == 0 and r["tps"] == 0 and set(r["estados"]) == {429}


def test_carga_si_nadie_contesta_cuenta_errores_y_no_se_cae():
    url = f"http://127.0.0.1:{_puerto_cerrado()}/api/v1/salud"
    r = prueba_carga.asyncio.run(prueba_carga.medir(url, concurrencia=2, segundos=0.5))
    assert r["exitosas"] == 0 and sum(r["errores_de_red"].values()) > 0


def test_carga_se_niega_a_medir_un_sitio_publico(capsys, monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("no debe hacer ninguna petición")
    monkeypatch.setattr(prueba_carga, "medir", no_debe_llamarse)
    assert prueba_carga.main(["--url", "https://picksy.lat/api/v1/salud"]) == 2
    assert "Me niego a medir" in capsys.readouterr().out


def test_carga_guarda_el_resultado_en_json(servidor_http, tmp_path, capsys):
    salida = tmp_path / "tps.json"
    codigo = prueba_carga.main(["--url", servidor_http + "/api/v1/salud", "--concurrencia", "2",
                                "--segundos", "0.5", "--salida", str(salida)])
    assert codigo == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["tps"] > 0 and datos["concurrencia"] == 2
    assert "TPS (exitosas por segundo)" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------- revisar_tiendas.py
class _TiendaFalsa:
    def __init__(self, nombre, resultado):
        self.nombre, self.resultado = nombre, resultado

    def buscar(self, termino, limite=20):
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


def _producto():
    return Producto(tienda="X", nombre="Algo", precio=1000.0, envio=None, disponible=True,
                    url="https://x.test", imagen=None, consultado_en=datetime.datetime.now(datetime.timezone.utc))


def _403():
    pedido = httpx.Request("GET", "https://www.exito.com/api?ft=televisor")
    return httpx.HTTPStatusError("x", request=pedido, response=httpx.Response(403, request=pedido))


def test_revisar_distingue_ok_vacia_y_error():
    assert revisar_tiendas.revisar(_TiendaFalsa("A", [_producto()]), "t")["ok"] is True
    vacia = revisar_tiendas.revisar(_TiendaFalsa("B", []), "t")
    assert vacia["ok"] is False and "sin productos" in vacia["detalle"]
    caida = revisar_tiendas.revisar(_TiendaFalsa("Éxito", _403()), "t")
    assert caida["ok"] is False and caida["detalle"] == "HTTPStatusError http=403"


def test_revisar_main_sale_con_1_si_alguna_tienda_falla(monkeypatch, capsys):
    monkeypatch.setattr(buscador, "CONECTORES", [_TiendaFalsa("Buena", [_producto()]), _TiendaFalsa("Éxito", _403())])
    assert revisar_tiendas.main(["--pausa", "0"]) == 1
    salida = capsys.readouterr().out
    assert "Buena" in salida and "OK" in salida and "FALLÓ" in salida and "bloquea la IP" in salida
    assert "1 de 2 tiendas respondieron bien" in salida


def test_revisar_main_sale_con_0_si_todas_responden(monkeypatch):
    monkeypatch.setattr(buscador, "CONECTORES", [_TiendaFalsa("A", [_producto()]), _TiendaFalsa("B", [_producto()])])
    assert revisar_tiendas.main(["--pausa", "0"]) == 0


def test_revisar_una_tienda_que_no_existe(monkeypatch, capsys):
    monkeypatch.setattr(buscador, "CONECTORES", [_TiendaFalsa("A", [_producto()])])
    monkeypatch.setattr(buscador, "NOMBRES", ["A"])
    assert revisar_tiendas.main(["--tienda", "Zzz"]) == 2
    assert "No existe la tienda" in capsys.readouterr().out


def test_revisar_tiene_termino_para_todas_las_tiendas_con_conector():
    """Si agregan un conector nuevo, esta herramienta debe saber qué buscar en él."""
    for nombre in buscador.NOMBRES:
        assert nombre in revisar_tiendas.TERMINOS, f"agrega '{nombre}' a TERMINOS en herramientas/revisar_tiendas.py"


# ---------------------------------------------------------------------------------------------- alerta_certificado.py
def _crear_certificado(carpeta: Path, dias_para_vencer: float):
    """Certificado autofirmado para 'localhost'. Con dias_para_vencer negativo ya está vencido."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    clave = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    certificado = (
        x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(days=30))
        .not_valid_after(ahora + datetime.timedelta(days=dias_para_vencer))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                     key_encipherment=False, data_encipherment=False, key_agreement=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
        .sign(clave, hashes.SHA256())
    )
    cert_pem, llave_pem = carpeta / "cert.pem", carpeta / "llave.pem"
    cert_pem.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    llave_pem.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    return cert_pem, llave_pem


class _ServidorTLS:
    def __init__(self, cert, llave):
        self.contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.contexto.load_cert_chain(cert, llave)
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(5)
        self.puerto = self.socket.getsockname()[1]
        threading.Thread(target=self._servir, daemon=True).start()

    def _servir(self):
        while True:
            try:
                conexion, _ = self.socket.accept()
            except OSError:
                return
            try:
                with self.contexto.wrap_socket(conexion, server_side=True):
                    pass
            except (ssl.SSLError, OSError):
                pass

    def cerrar(self):
        self.socket.close()


@pytest.fixture
def sitio_https(tmp_path):
    """Devuelve una función: sitio_https(dias) -> (puerto, ruta_del_certificado) de un servidor HTTPS local."""
    abiertos = []

    def crear(dias):
        carpeta = tmp_path / f"cert_{len(abiertos)}"
        carpeta.mkdir()
        cert, llave = _crear_certificado(carpeta, dias)
        servidor = _ServidorTLS(cert, llave)
        abiertos.append(servidor)
        return servidor.puerto, str(cert)

    yield crear
    for s in abiertos:
        s.cerrar()


def test_dias_restantes_lee_el_vencimiento_real(sitio_https):
    puerto, cert = sitio_https(40)
    assert alerta_certificado.dias_restantes("localhost", puerto, cafile=cert) == pytest.approx(40, abs=0.1)


def test_certificado_con_muchos_dias_no_avisa(sitio_https, monkeypatch, capsys):
    enviados = []
    monkeypatch.setenv("ALERTA_CORREO", "equipo@picksy.lat")
    monkeypatch.setattr("correos.enviar", lambda *a, **k: enviados.append(a))
    puerto, cert = sitio_https(60)
    assert alerta_certificado.main(["--dominio", "localhost", "--puerto", str(puerto), "--cafile", cert]) == 0
    assert enviados == [] and "vence en" in capsys.readouterr().out


def test_certificado_por_vencer_envia_el_correo_con_los_pasos(sitio_https, monkeypatch):
    enviados = []
    monkeypatch.setenv("ALERTA_CORREO", "equipo@picksy.lat")
    monkeypatch.setattr("correos.enviar", lambda *a, **k: enviados.append(a))
    puerto, cert = sitio_https(5)
    assert alerta_certificado.main(["--dominio", "localhost", "--puerto", str(puerto), "--cafile", cert]) == 1
    assert len(enviados) == 1
    destino, asunto, texto = enviados[0]
    assert destino == "equipo@picksy.lat" and "certificado HTTPS de localhost" in asunto
    assert "vence en 5 días" in texto and "certbot renew" in texto


def test_certificado_ya_vencido_tambien_avisa(sitio_https, monkeypatch):
    enviados = []
    monkeypatch.setenv("ALERTA_CORREO", "equipo@picksy.lat")
    monkeypatch.setattr("correos.enviar", lambda *a, **k: enviados.append(a))
    puerto, cert = sitio_https(-2)
    assert alerta_certificado.main(["--dominio", "localhost", "--puerto", str(puerto), "--cafile", cert]) == 1
    assert "YA VENCIÓ" in enviados[0][2]


def test_si_no_se_puede_conectar_se_avisa_como_problema(monkeypatch):
    enviados = []
    monkeypatch.setenv("ALERTA_CORREO", "equipo@picksy.lat")
    monkeypatch.setattr("correos.enviar", lambda *a, **k: enviados.append(a))
    assert alerta_certificado.main(["--dominio", "localhost", "--puerto", str(_puerto_cerrado())]) == 1
    assert "No se pudo comprobar" in enviados[0][2]


def test_sin_alerta_correo_no_envia_pero_avisa_en_pantalla(sitio_https, monkeypatch, capsys):
    monkeypatch.delenv("ALERTA_CORREO", raising=False)
    puerto, cert = sitio_https(3)
    assert alerta_certificado.main(["--dominio", "localhost", "--puerto", str(puerto), "--cafile", cert]) == 1
    assert "define ALERTA_CORREO" in capsys.readouterr().out


def test_solo_ver_no_envia_correo(sitio_https, monkeypatch):
    enviados = []
    monkeypatch.setenv("ALERTA_CORREO", "equipo@picksy.lat")
    monkeypatch.setattr("correos.enviar", lambda *a, **k: enviados.append(a))
    puerto, cert = sitio_https(3)
    alerta_certificado.main(["--dominio", "localhost", "--puerto", str(puerto), "--cafile", cert, "--solo-ver"])
    assert enviados == []


def test_con_frontend_url_local_pide_indicar_el_dominio(monkeypatch, capsys):
    monkeypatch.setattr(config, "FRONTEND_URL", "http://127.0.0.1:5500")
    assert alerta_certificado.main([]) == 2
    assert "--dominio" in capsys.readouterr().out


def test_el_dominio_por_defecto_sale_de_frontend_url(monkeypatch):
    monkeypatch.setattr(config, "FRONTEND_URL", "https://picksy.lat")
    assert alerta_certificado.dominio_por_defecto() == "picksy.lat"


# ---------------------------------------------------------------------------------------------- probar_mercadolibre.py
def _resp(codigo, cuerpo, metodo="GET"):
    return httpx.Response(codigo, json=cuerpo, request=httpx.Request(metodo, "https://api.mercadolibre.com/x"))


def test_probar_ml_sin_credenciales_explica_que_es_lo_normal(monkeypatch, capsys):
    monkeypatch.setattr(config, "ML_CLIENT_ID", "")
    monkeypatch.setattr(config, "ML_CLIENT_SECRET", "")
    assert probar_mercadolibre.main([]) == 2
    assert "desactivado" in capsys.readouterr().out


def test_probar_ml_camino_feliz(monkeypatch, capsys):
    monkeypatch.setattr(config, "ML_CLIENT_ID", "id-app")
    monkeypatch.setattr(config, "ML_CLIENT_SECRET", "SECRETO-MUY-SECRETO")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, {"access_token": "T", "expires_in": 21600}, "POST"))
    item = {"title": "Celular Samsung", "price": 799000, "permalink": "https://articulo.mercadolibre.com.co/x",
            "available_quantity": 5, "shipping": {"free_shipping": True}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp(200, {"results": [item]}))
    assert probar_mercadolibre.main([]) == 0
    salida = capsys.readouterr().out
    assert "Mercado Libre entregó el token" in salida and "Celular Samsung" in salida and "Todo bien" in salida
    assert "SECRETO-MUY-SECRETO" not in salida


@pytest.mark.parametrize("codigo,pista", [(401, "Credenciales o token"), (403, "permiso"), (429, "Demasiadas"), (503, "5xx")])
def test_probar_ml_explica_cada_error_del_token(monkeypatch, capsys, codigo, pista):
    monkeypatch.setattr(config, "ML_CLIENT_ID", "id-app")
    monkeypatch.setattr(config, "ML_CLIENT_SECRET", "SECRETO-MUY-SECRETO")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(codigo, {"error": "invalid_client", "message": "no autorizado"}, "POST"))
    assert probar_mercadolibre.main([]) == 1
    salida = capsys.readouterr().out
    assert f"HTTP {codigo}" in salida and pista in salida and "no autorizado" in salida
    assert "SECRETO-MUY-SECRETO" not in salida


def test_probar_ml_sin_conexion(monkeypatch, capsys):
    monkeypatch.setattr(config, "ML_CLIENT_ID", "id-app")
    monkeypatch.setattr(config, "ML_CLIENT_SECRET", "s")

    def sin_red(*a, **k):
        raise httpx.ConnectError("sin red")
    monkeypatch.setattr(httpx, "post", sin_red)
    assert probar_mercadolibre.main([]) == 1
    assert "no hay conexión con api.mercadolibre.com" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------- despliegue/*.sh
necesita_bash = pytest.mark.skipif(
    sys.platform.startswith("win") or not shutil.which("bash") or not shutil.which("curl"),
    reason="necesita bash y curl (Linux o Git Bash)")


@pytest.fixture
def entorno_reinicio(tmp_path):
    """Un 'systemctl' falso que solo anota lo que le piden, y 2 servidores de salud de mentira."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    registro = tmp_path / "systemctl.log"
    (bin_ / "systemctl").write_text(f'#!/bin/sh\necho "$@" >> "{registro}"\n')
    (bin_ / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
    for f in bin_.iterdir():
        f.chmod(0o755)

    servidores = []

    def servidor_salud(codigo):
        class H(_Manejador):
            def do_GET(self):
                cuerpo = b"{}"
                self.send_response(codigo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
        s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        servidores.append(s)
        return s.server_address[1]

    def correr(codigo_a, codigo_b, espera_max=3):
        pa, pb = servidor_salud(codigo_a), servidor_salud(codigo_b)
        entorno = {"PATH": f"{bin_}:/usr/bin:/bin", "SERVICIOS": "inst_a inst_b", "PUERTOS": f"{pa} {pb}",
                   "ESPERA_MAX": str(espera_max)}
        r = subprocess.run(["bash", str(RAIZ / "despliegue" / "reiniciar_sin_cortes.sh")], capture_output=True,
                           text=True, env=entorno, timeout=60)
        llamadas = registro.read_text().splitlines() if registro.exists() else []
        return r, llamadas

    yield correr
    for s in servidores:
        s.shutdown()
        s.server_close()


@necesita_bash
def test_reinicio_sin_cortes_reinicia_una_por_una_y_en_orden(entorno_reinicio):
    r, llamadas = entorno_reinicio(200, 200)
    assert r.returncode == 0, r.stdout + r.stderr
    assert llamadas == ["restart inst_a", "restart inst_b"]
    assert "Listo" in r.stdout


@necesita_bash
def test_si_la_primera_no_vuelve_no_toca_la_segunda(entorno_reinicio):
    r, llamadas = entorno_reinicio(503, 200, espera_max=2)
    assert r.returncode == 1
    assert llamadas == ["restart inst_a"], "la segunda instancia debe seguir atendiendo, sin tocarla"
    assert "NO respondió" in r.stdout and "journalctl -u inst_a" in r.stdout


@necesita_bash
def test_si_la_segunda_falla_el_script_termina_con_error(entorno_reinicio):
    r, llamadas = entorno_reinicio(200, 503, espera_max=2)
    assert r.returncode == 1 and llamadas == ["restart inst_a", "restart inst_b"]


@necesita_bash
def test_respaldo_sin_env_termina_con_un_mensaje_claro(tmp_path):
    r = subprocess.run(["bash", str(RAIZ / "despliegue" / "respaldo.sh")], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PICKSY_DIR": str(tmp_path), "RESPALDO_DIR": str(tmp_path / "r")})
    assert r.returncode == 1 and "No encuentro" in r.stdout
