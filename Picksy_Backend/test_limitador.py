"""
Pruebas del límite de intentos (limitador.py) en sus dos modos: memoria y Redis.

Cómo correrlas (no necesitan base de datos ni Internet):
    pytest test_limitador.py -v

Por defecto el modo Redis se prueba con un Redis FALSO (FalsoRedis, abajo) que implementa solo las órdenes que usa el limitador,
así corren en cualquier computador. Si además tienes un Redis de verdad, las MISMAS pruebas se repiten contra él:
    REDIS_URL_PRUEBAS=redis://127.0.0.1:6379/15 pytest test_limitador.py -v
(esto último además prueba que 2 procesos distintos comparten el mismo límite).
"""
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

import config
import limitador

REDIS_REAL = os.getenv("REDIS_URL_PRUEBAS", "").strip()
RAIZ = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------------------------- Redis falso
class _Tuberia:
    """Lo mínimo de redis.Redis().pipeline(): junta órdenes y las ejecuta todas en execute()."""

    def __init__(self, redis):
        self.redis, self.pendientes = redis, []

    def __getattr__(self, orden):
        def agregar(*args, **kwargs):
            self.pendientes.append((orden, args, kwargs))
            return self
        return agregar

    def execute(self):
        if self.redis.roto:
            raise ConnectionError("Redis de prueba caído")
        return [getattr(self.redis, "_" + o)(*a, **k) for o, a, k in self.pendientes]


class FalsoRedis:
    """Imita las órdenes de Redis que usa limitador.py (conjuntos ordenados + expiración)."""

    def __init__(self):
        self.datos: dict[str, dict[str, float]] = {}
        self.ttl: dict[str, int] = {}
        self.roto = False

    def pipeline(self):
        return _Tuberia(self)

    # --- órdenes (con guion bajo: las llama la tubería) ---
    def _zremrangebyscore(self, k, minimo, maximo):
        conjunto = self.datos.get(k, {})
        for m in [m for m, s in conjunto.items() if s <= float(maximo)]:
            del conjunto[m]
        if not conjunto:
            self.datos.pop(k, None)
        return 0

    def _zadd(self, k, mapa):
        self.datos.setdefault(k, {}).update(mapa)
        return len(mapa)

    def _expire(self, k, segundos):
        self.ttl[k] = segundos
        return True

    def _zcard(self, k):
        return len(self.datos.get(k, {}))

    def _zrange(self, k, inicio, fin, withscores=False):
        ordenado = sorted(self.datos.get(k, {}).items(), key=lambda par: par[1])
        return ordenado[inicio:fin + 1]

    # --- órdenes directas ---
    def delete(self, *llaves):
        if self.roto:
            raise ConnectionError("Redis de prueba caído")
        for k in llaves:
            self.datos.pop(k, None)
        return len(llaves)

    def scan_iter(self, match="*", count=None):
        if self.roto:
            raise ConnectionError("Redis de prueba caído")
        prefijo = match.rstrip("*")
        return iter([k for k in list(self.datos) if k.startswith(prefijo)])


# ---------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(params=["memoria", "redis-falso", "redis-real"])
def modo(request, monkeypatch):
    """Cada prueba que use 'modo' se repite en memoria, con Redis falso y (si hay uno) con Redis real."""
    if request.param == "memoria":
        monkeypatch.setattr(config, "REDIS_URL", "")
        cliente = None
    else:
        if request.param == "redis-real":
            if not REDIS_REAL:
                pytest.skip("no hay Redis real: define REDIS_URL_PRUEBAS=redis://127.0.0.1:6379/15")
            import redis
            cliente = redis.Redis.from_url(REDIS_REAL, decode_responses=True)
        else:
            cliente = FalsoRedis()
        monkeypatch.setattr(config, "REDIS_URL", "redis://prueba")
        monkeypatch.setattr(limitador, "_cliente", cliente)
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)
    limitador.reiniciar()
    yield request.param, cliente
    limitador.reiniciar()


def _llenar(clave, cuantos, ventana=900):
    for _ in range(cuantos):
        limitador.anotar(clave, ventana)


# ---------------------------------------------------------------------------------------------- comportamiento (igual en los 3 modos)
def test_por_debajo_del_maximo_no_bloquea(modo):
    _llenar("login:a@picksy.lat", 4)
    limitador.exigir_libre("login:a@picksy.lat", 5, 900)  # 4 intentos de 5 permitidos: no lanza nada


def test_al_llegar_al_maximo_responde_429_con_retry_after(modo):
    _llenar("login:a@picksy.lat", 5)
    with pytest.raises(HTTPException) as e:
        limitador.exigir_libre("login:a@picksy.lat", 5, 900)
    assert e.value.status_code == 429
    assert "Demasiados intentos" in e.value.detail
    espera = int(e.value.headers["Retry-After"])
    assert 1 <= espera <= 900
    assert f"Espera {espera} segundos" in e.value.detail


def test_cada_clave_cuenta_aparte(modo):
    _llenar("login:a@picksy.lat", 5)
    limitador.exigir_libre("login:b@picksy.lat", 5, 900)       # otro correo: sigue libre
    limitador.exigir_libre("login-ip:10.0.0.1", 5, 900)        # otra clave: sigue libre


def test_olvidar_borra_solo_esa_clave(modo):
    _llenar("login:a@picksy.lat", 5)
    _llenar("login:b@picksy.lat", 5)
    limitador.olvidar("login:a@picksy.lat")
    limitador.exigir_libre("login:a@picksy.lat", 5, 900)       # ya está libre (login correcto borra los fallos)
    with pytest.raises(HTTPException):
        limitador.exigir_libre("login:b@picksy.lat", 5, 900)   # la otra sigue bloqueada


def test_reiniciar_borra_todo(modo):
    _llenar("login:a@picksy.lat", 5)
    _llenar("registro-ip:1.2.3.4", 10, 3600)
    limitador.reiniciar()
    limitador.exigir_libre("login:a@picksy.lat", 5, 900)
    limitador.exigir_libre("registro-ip:1.2.3.4", 10, 3600)


def test_los_intentos_viejos_dejan_de_contar(modo):
    _llenar("codigo:7", 2, ventana=1)
    with pytest.raises(HTTPException):
        limitador.exigir_libre("codigo:7", 2, 1)
    time.sleep(1.2)                                            # la ventana de 1 s ya pasó
    limitador.exigir_libre("codigo:7", 2, 1)


# ---------------------------------------------------------------------------------------------- solo Redis
@pytest.fixture(params=["redis-falso", "redis-real"])
def solo_redis(request, monkeypatch):
    if request.param == "redis-real":
        if not REDIS_REAL:
            pytest.skip("no hay Redis real: define REDIS_URL_PRUEBAS=redis://127.0.0.1:6379/15")
        import redis
        cliente = redis.Redis.from_url(REDIS_REAL, decode_responses=True)
    else:
        cliente = FalsoRedis()
    monkeypatch.setattr(config, "REDIS_URL", "redis://prueba")
    monkeypatch.setattr(limitador, "_cliente", cliente)
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)
    limitador.reiniciar()
    yield cliente
    limitador.reiniciar()


def _llaves(cliente):
    if isinstance(cliente, FalsoRedis):
        return list(cliente.datos)
    return list(cliente.scan_iter(match="picksy:limite:*"))


def test_con_redis_los_contadores_no_viven_en_la_memoria_del_proceso(solo_redis):
    _llenar("login:a@picksy.lat", 3)
    assert not limitador._eventos, "con Redis el proceso no debe guardar contadores propios"
    assert len(_llaves(solo_redis)) == 1


def test_en_redis_no_queda_el_correo_ni_la_ip_legibles(solo_redis):
    _llenar("login:ana.perez@correo.com", 1)
    _llenar("login-ip:190.24.10.7", 1)
    for llave in _llaves(solo_redis):
        assert "ana" not in llave and "correo" not in llave and "190.24" not in llave
        assert llave.startswith("picksy:limite:")


def test_el_contador_se_borra_solo_al_vencer_la_ventana(solo_redis):
    limitador.anotar("recuperar:a@picksy.lat", 3600)
    llave = _llaves(solo_redis)[0]
    ttl = solo_redis.ttl[llave] if isinstance(solo_redis, FalsoRedis) else solo_redis.ttl(llave)
    assert 3500 <= ttl <= 3601


def test_modo_reporta_redis_cuando_se_usa(solo_redis):
    assert limitador.modo() == "redis"


# ---------------------------------------------------------------------------------------------- Redis se cae (no debe caer la API)
def test_si_redis_falla_se_sigue_con_la_memoria_y_se_avisa(monkeypatch, caplog):
    falso = FalsoRedis()
    monkeypatch.setattr(config, "REDIS_URL", "redis://prueba")
    monkeypatch.setattr(limitador, "_cliente", falso)
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)
    limitador.reiniciar()

    falso.roto = True
    with caplog.at_level(logging.WARNING, logger="picksy"):
        _llenar("login:a@picksy.lat", 5)                       # no lanza ConnectionError: usa la memoria
        with pytest.raises(HTTPException) as e:
            limitador.exigir_libre("login:a@picksy.lat", 5, 900)
    assert e.value.status_code == 429                          # el límite SIGUE funcionando (en este proceso)
    assert limitador.modo() == "memoria"
    assert any("Redis no disponible" in r.message for r in caplog.records)
    # Un solo aviso por caída, no uno por petición:
    assert sum("Redis no disponible" in r.message for r in caplog.records) == 1
    limitador.reiniciar()


def test_cuando_redis_vuelve_se_usa_otra_vez(monkeypatch):
    falso = FalsoRedis()
    monkeypatch.setattr(config, "REDIS_URL", "redis://prueba")
    monkeypatch.setattr(limitador, "_cliente", falso)
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)
    limitador.reiniciar()

    falso.roto = True
    limitador.anotar("login:z@picksy.lat", 900)                # falla -> memoria, pausa de 30 s
    assert limitador.modo() == "memoria"

    falso.roto = False
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)  # "pasaron 30 segundos"
    limitador.anotar("login:z@picksy.lat", 900)
    assert limitador.modo() == "redis"
    assert len(falso.datos) == 1
    limitador.reiniciar()


def test_si_el_paquete_redis_no_esta_instalado_no_se_cae(monkeypatch):
    """REDIS_URL puesto pero 'pip install redis' olvidado: la API sigue con la memoria."""
    monkeypatch.setattr(config, "REDIS_URL", "redis://prueba")
    monkeypatch.setattr(limitador, "_cliente", None)
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)
    monkeypatch.setitem(sys.modules, "redis", None)            # hace que "import redis" falle
    limitador.reiniciar()
    _llenar("login:q@picksy.lat", 5)
    with pytest.raises(HTTPException):
        limitador.exigir_libre("login:q@picksy.lat", 5, 900)
    limitador.reiniciar()


# ---------------------------------------------------------------------------------------------- 2 procesos (solo con Redis real)
@pytest.mark.skipif(not REDIS_REAL, reason="necesita un Redis real: REDIS_URL_PRUEBAS=redis://127.0.0.1:6379/15")
def test_dos_procesos_distintos_comparten_el_mismo_limite(monkeypatch):
    """La razón de ser de Redis: lo que anota el proceso A lo ve el proceso B (alta disponibilidad con 2 instancias)."""
    import redis
    monkeypatch.setattr(config, "REDIS_URL", REDIS_REAL)
    monkeypatch.setattr(limitador, "_cliente", redis.Redis.from_url(REDIS_REAL, decode_responses=True))
    monkeypatch.setattr(limitador, "_redis_caido_hasta", 0.0)
    limitador.reiniciar()

    otro_proceso = ("import limitador\n"
                    "for _ in range(5): limitador.anotar('login:compartido@picksy.lat', 900)\n"
                    "print(limitador.modo())")
    salida = subprocess.run(
        [sys.executable, "-c", otro_proceso], cwd=RAIZ, check=True, capture_output=True, text=True,
        env={**os.environ, "REDIS_URL": REDIS_REAL, "PYTHONPATH": str(RAIZ)},
    )
    assert salida.stdout.strip() == "redis"

    # Este proceso NO anotó nada, pero ve los 5 fallos del otro:
    with pytest.raises(HTTPException) as e:
        limitador.exigir_libre("login:compartido@picksy.lat", 5, 900)
    assert e.value.status_code == 429
    limitador.reiniciar()
