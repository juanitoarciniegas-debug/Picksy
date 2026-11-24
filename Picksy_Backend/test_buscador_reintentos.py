"""
Pruebas del reintento por tienda y del registro de fallas en el log (buscador.py). No necesitan base de datos ni Internet: las tiendas y el caché son falsos.

    pytest test_buscador_reintentos.py -v
"""
import logging
from datetime import datetime, timezone

import httpx
import pytest

import buscador
import config
from conectores.base import Producto

BUSQUEDA = "audifonos-secretos-123"   # si aparece en el log, hay una fuga: se comprueba abajo


def _producto(tienda):
    return Producto(tienda=tienda, nombre="Audífonos de prueba", precio=50000.0, envio=None, disponible=True,
                    url="https://tienda.test/p/1", imagen=None, consultado_en=datetime.now(timezone.utc))


def _http(codigo):
    pedido = httpx.Request("GET", f"https://tienda.test/api?ft={BUSQUEDA}")
    return httpx.HTTPStatusError("falló", request=pedido, response=httpx.Response(codigo, request=pedido))


class TiendaFalsa:
    """Lanza las excepciones de 'fallos' en las primeras llamadas y después responde bien."""

    def __init__(self, nombre="TiendaFalsa", fallos=()):
        self.nombre = nombre
        self.fallos = list(fallos)
        self.llamadas = 0

    def buscar(self, termino):
        self.llamadas += 1
        if self.fallos:
            raise self.fallos.pop(0)
        return [_producto(self.nombre)]


@pytest.fixture
def entorno(monkeypatch):
    """Sin base de datos: el caché no guarda nada. Sin esperas reales entre reintentos."""
    monkeypatch.setattr(buscador, "leer_cache", lambda *a, **k: None)
    monkeypatch.setattr(buscador, "guardar_cache", lambda *a, **k: None)
    monkeypatch.setattr(buscador, "PAUSA_REINTENTO", 0)
    monkeypatch.setattr(config, "TIENDA_REINTENTOS", 1)
    monkeypatch.setattr(buscador, "LIMITE_SEGUNDOS", 8)

    def poner(tienda):
        monkeypatch.setattr(buscador, "CONECTORES", [tienda])
        return tienda
    return poner


# ---------------------------------------------------------------------------------------------- reintento
def test_un_corte_de_red_pasajero_se_reintenta_y_funciona(entorno):
    t = entorno(TiendaFalsa(fallos=[httpx.ConnectError("sin conexión")]))
    productos, avisos = buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 2
    assert len(productos) == 1 and avisos == []


@pytest.mark.parametrize("codigo", [429, 500, 502, 503, 504])
def test_los_errores_pasajeros_de_la_tienda_se_reintentan(entorno, codigo):
    t = entorno(TiendaFalsa(fallos=[_http(codigo)]))
    productos, avisos = buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 2 and len(productos) == 1 and avisos == []


def test_un_tiempo_agotado_de_red_tambien_cuenta_como_pasajero(entorno):
    t = entorno(TiendaFalsa(fallos=[httpx.ReadTimeout("lento")]))
    productos, _ = buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 2 and len(productos) == 1


@pytest.mark.parametrize("error", [_http(403), _http(404), ValueError("la página cambió"), KeyError("precio")])
def test_lo_que_repetir_no_arregla_no_se_reintenta(entorno, error):
    t = entorno(TiendaFalsa(fallos=[error]))
    productos, avisos = buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 1
    assert productos == [] and "TiendaFalsa no respondió" in avisos[0]


def test_se_reintenta_una_sola_vez(entorno):
    t = entorno(TiendaFalsa(fallos=[httpx.ConnectError("1"), httpx.ConnectError("2"), httpx.ConnectError("3")]))
    productos, avisos = buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 2                                   # 1 intento + 1 reintento
    assert productos == [] and "ConnectError" in avisos[0]


def test_con_reintentos_en_cero_se_comporta_como_antes(entorno, monkeypatch):
    monkeypatch.setattr(config, "TIENDA_REINTENTOS", 0)
    t = entorno(TiendaFalsa(fallos=[httpx.ConnectError("sin conexión")]))
    buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 1


def test_no_se_reintenta_si_ya_casi_no_queda_tiempo(entorno, monkeypatch):
    monkeypatch.setattr(buscador, "LIMITE_SEGUNDOS", 2)       # menos que MARGEN_REINTENTO (3 s)
    t = entorno(TiendaFalsa(fallos=[httpx.ConnectError("sin conexión")]))
    buscador.buscar_en_todas(BUSQUEDA)
    assert t.llamadas == 1


def test_el_reintento_no_afecta_a_las_otras_tiendas(monkeypatch, entorno):
    buena = TiendaFalsa("Buena")
    mala = TiendaFalsa("Mala", fallos=[_http(403)])
    monkeypatch.setattr(buscador, "CONECTORES", [buena, mala])
    productos, avisos = buscador.buscar_en_todas(BUSQUEDA)
    assert [p.tienda for p in productos] == ["Buena"]
    assert len(avisos) == 1 and "Mala" in avisos[0]
    assert buena.llamadas == 1


def test_si_falla_se_usan_los_datos_guardados_antes(entorno, monkeypatch):
    viejos = [_producto("TiendaFalsa")]
    monkeypatch.setattr(buscador, "leer_cache",
                        lambda clave, tienda, solo_vigente=True: None if solo_vigente else viejos)
    entorno(TiendaFalsa(fallos=[_http(403)]))
    productos, avisos = buscador.buscar_en_todas(BUSQUEDA)
    assert productos == viejos and "datos guardados anteriormente" in avisos[0]


# ---------------------------------------------------------------------------------------------- log de fallas
def test_cada_falla_queda_en_el_log_sin_la_busqueda_de_la_persona(entorno, caplog):
    entorno(TiendaFalsa("Éxito", fallos=[_http(403)]))
    with caplog.at_level(logging.WARNING, logger="picksy"):
        buscador.buscar_en_todas(BUSQUEDA)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "TIENDA_FALLO tienda=Éxito error=HTTPStatusError http=403" in texto
    assert BUSQUEDA not in texto, "el log no debe guardar lo que la persona buscó"


def test_el_reintento_tambien_queda_en_el_log(entorno, caplog):
    entorno(TiendaFalsa("Olímpica", fallos=[httpx.ConnectError("sin conexión")]))
    with caplog.at_level(logging.WARNING, logger="picksy"):
        buscador.buscar_en_todas(BUSQUEDA)
    assert any("TIENDA_REINTENTO tienda=Olímpica intento=1 error=ConnectError" in r.getMessage()
               for r in caplog.records)
    assert not any("TIENDA_FALLO" in r.getMessage() for r in caplog.records)   # al final sí respondió
