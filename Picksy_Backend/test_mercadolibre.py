"""
Pruebas del conector de Mercado Libre con respuestas SIMULADAS de la API (no sale nada a Internet).
Recuerda: esto demuestra que el conector lee bien el formato que documenta Mercado Libre; que las credenciales y
los permisos reales funcionen desde el servidor se comprueba con  python herramientas/probar_mercadolibre.py

    pytest test_mercadolibre.py -v
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from conectores import mercadolibre
from conectores.mercadolibre import ConectorMercadoLibre

RAIZ = Path(__file__).resolve().parent


def _resp(codigo, cuerpo, metodo="GET"):
    pedido = httpx.Request(metodo, "https://api.mercadolibre.com/x")
    return httpx.Response(codigo, json=cuerpo, request=pedido)


def _item(**cambios):
    base = {
        "id": "MCO1", "title": "Audífonos Bluetooth Inalámbricos", "price": 89900, "currency_id": "COP",
        "available_quantity": 25, "permalink": "https://articulo.mercadolibre.com.co/MCO-1-audifonos",
        "thumbnail": "http://http2.mlstatic.com/D_1-I.jpg", "condition": "new",
        "shipping": {"free_shipping": True},
    }
    base.update(cambios)
    return base


class Api:
    """Reemplaza httpx.post y httpx.get y guarda lo que se pidió, para poder afirmar sobre ello."""

    def __init__(self, monkeypatch, busquedas=None, token="TOKEN-1"):
        self.tokens_pedidos = 0
        self.busquedas = list(busquedas if busquedas is not None else [_resp(200, {"results": [_item()]})])
        self.llamadas_get = []
        self.token = token
        monkeypatch.setattr(httpx, "post", self._post)
        monkeypatch.setattr(httpx, "get", self._get)

    def _post(self, url, data=None, headers=None, timeout=None, **_):
        assert url == "https://api.mercadolibre.com/oauth/token"
        assert data["grant_type"] == "client_credentials"
        assert data["client_id"] == "id-app" and data["client_secret"] == "secreto-app"
        self.tokens_pedidos += 1
        return _resp(200, {"access_token": f"{self.token}-{self.tokens_pedidos}", "expires_in": 21600}, "POST")

    def _get(self, url, params=None, headers=None, timeout=None, **_):
        self.llamadas_get.append({"url": url, "params": params, "headers": headers})
        return self.busquedas.pop(0)


@pytest.fixture
def conector():
    return ConectorMercadoLibre("id-app", "secreto-app")


def test_pide_token_busca_y_convierte_el_resultado(conector, monkeypatch):
    api = Api(monkeypatch)
    productos = conector.buscar("audifonos")
    assert len(productos) == 1
    p = productos[0]
    assert (p.tienda, p.nombre, p.precio) == ("Mercado Libre", "Audífonos Bluetooth Inalámbricos", 89900.0)
    assert p.envio == 0.0 and p.disponible is True              # envío gratis -> 0.0 (el frontend dice "Envío gratis")
    assert p.url == "https://articulo.mercadolibre.com.co/MCO-1-audifonos"
    assert p.imagen == "https://http2.mlstatic.com/D_1-I.jpg"   # siempre https
    assert p.consultado_en.tzinfo is not None

    llamada = api.llamadas_get[0]
    assert llamada["url"] == "https://api.mercadolibre.com/sites/MCO/search"
    assert llamada["params"]["q"] == "audifonos" and llamada["params"]["condition"] == "new"
    assert llamada["headers"]["Authorization"] == "Bearer TOKEN-1-1"


def test_sin_envio_gratis_el_envio_queda_sin_informar(conector, monkeypatch):
    Api(monkeypatch, [_resp(200, {"results": [_item(shipping={"free_shipping": False})]})])
    assert conector.buscar("x")[0].envio is None


def test_cantidad_cero_es_agotado(conector, monkeypatch):
    Api(monkeypatch, [_resp(200, {"results": [_item(available_quantity=0)]})])
    assert conector.buscar("x")[0].disponible is False


def test_descarta_resultados_sin_precio_con_precio_de_relleno_o_sin_enlace(conector, monkeypatch):
    malos = [_item(price=None), _item(price=1), _item(permalink=""), _item(title=" "), "no es un diccionario"]
    Api(monkeypatch, [_resp(200, {"results": malos + [_item(id="MCO9")]})])
    productos = conector.buscar("x")
    assert len(productos) == 1                                   # solo sobrevive el bueno; nada se cae


def test_respeta_el_limite_pedido(conector, monkeypatch):
    Api(monkeypatch, [_resp(200, {"results": [_item(id=f"MCO{i}") for i in range(30)]})])
    assert len(conector.buscar("x", limite=5)) == 5


def test_nunca_pide_mas_de_50_a_la_api(conector, monkeypatch):
    api = Api(monkeypatch)
    conector.buscar("x", limite=200)
    assert api.llamadas_get[0]["params"]["limit"] == 50


def test_respuesta_sin_resultados_da_lista_vacia(conector, monkeypatch):
    Api(monkeypatch, [_resp(200, {"results": []})])
    assert conector.buscar("zzzz") == []
    Api(monkeypatch, [_resp(200, {})])
    assert conector.buscar("zzzz") == []


def test_el_token_se_guarda_y_no_se_pide_en_cada_busqueda(conector, monkeypatch):
    api = Api(monkeypatch, [_resp(200, {"results": []}), _resp(200, {"results": []})])
    conector.buscar("a")
    conector.buscar("b")
    assert api.tokens_pedidos == 1


def test_el_token_se_renueva_cuando_vence(conector, monkeypatch):
    api = Api(monkeypatch, [_resp(200, {"results": []}), _resp(200, {"results": []})])
    conector.buscar("a")
    conector._vence = time.time() - 1                           # "pasaron 6 horas"
    conector.buscar("b")
    assert api.tokens_pedidos == 2
    assert api.llamadas_get[1]["headers"]["Authorization"] == "Bearer TOKEN-1-2"


def test_si_la_api_responde_401_pide_otro_token_y_reintenta_una_vez(conector, monkeypatch):
    api = Api(monkeypatch, [_resp(401, {"message": "invalid_token"}), _resp(200, {"results": [_item()]})])
    assert len(conector.buscar("x")) == 1
    assert api.tokens_pedidos == 2 and len(api.llamadas_get) == 2


def test_un_403_que_se_repite_lanza_error_y_no_entra_en_bucle(conector, monkeypatch):
    api = Api(monkeypatch, [_resp(403, {"message": "forbidden"}), _resp(403, {"message": "forbidden"})])
    with pytest.raises(httpx.HTTPStatusError) as e:
        conector.buscar("x")
    assert e.value.response.status_code == 403
    assert len(api.llamadas_get) == 2                            # exactamente 2 intentos, no más


def test_un_429_o_un_5xx_lanza_error_para_que_buscador_lo_reintente(conector, monkeypatch):
    Api(monkeypatch, [_resp(503, {})])
    with pytest.raises(httpx.HTTPStatusError) as e:
        conector.buscar("x")
    assert e.value.response.status_code == 503


def test_si_la_api_no_entrega_token_se_lanza_un_error_claro(conector, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, {"token_type": "Bearer"}, "POST"))
    with pytest.raises(ValueError, match="token"):
        conector.buscar("x")


def test_si_piden_el_token_y_falla_las_credenciales_no_aparecen_en_el_error(conector, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(401, {"message": "invalid client"}, "POST"))
    with pytest.raises(httpx.HTTPStatusError) as e:
        conector.buscar("x")
    assert "secreto-app" not in str(e.value) and "id-app" not in str(e.value)


def test_constantes_del_conector():
    assert mercadolibre.SITIO == "MCO" and ConectorMercadoLibre.nombre == "Mercado Libre"


# ---------------------------------------------------------------------------------------------- se activa solo con credenciales
def _nombres_con(env_extra):
    """Importa buscador en un proceso limpio con esas variables y devuelve la lista de tiendas."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ML_")}
    env.setdefault("DB_PORT", "5432")
    env.update(env_extra)
    salida = subprocess.run(
        [sys.executable, "-c", "import buscador; print('|'.join(buscador.NOMBRES))"],
        cwd=RAIZ, check=True, capture_output=True, text=True, env={**env, "PYTHONPATH": str(RAIZ)},
    )
    return salida.stdout.strip().split("|")


def test_sin_credenciales_mercado_libre_no_se_activa_y_quedan_9_tiendas():
    nombres = _nombres_con({})
    assert "Mercado Libre" not in nombres and len(nombres) == 9


def test_con_credenciales_mercado_libre_se_suma_como_tienda_10():
    nombres = _nombres_con({"ML_CLIENT_ID": "123", "ML_CLIENT_SECRET": "abc"})
    assert nombres[-1] == "Mercado Libre" and len(nombres) == 10


def test_con_una_sola_credencial_no_se_activa():
    assert "Mercado Libre" not in _nombres_con({"ML_CLIENT_ID": "123"})
