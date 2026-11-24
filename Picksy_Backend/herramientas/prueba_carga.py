"""
Mide cuántas peticiones por segundo (TPS) aguanta la API y cuánto tarda en responder.

Uso (en el SERVIDOR, contra la propia API, sin pasar por Nginx):
    python herramientas/prueba_carga.py                                    # /api/v1/salud, 50 conexiones, 20 s
    python herramientas/prueba_carga.py --concurrencia 100 --segundos 30
    python herramientas/prueba_carga.py --url http://127.0.0.1:8000/api/v1/salud --salida tps.json

Para comparar 1 instancia contra 2 instancias, mide cada puerto por separado y la suma (ver MANUAL_OPERACION.md).

SEGURIDAD: solo acepta direcciones locales (127.0.0.1 / localhost). Apuntar esto a https://picksy.lat sería un ataque de
denegación de servicio a tu propio sitio (y Nginx limita a 50 peticiones/s por IP, así que ni siquiera mediría la API).
Con --permitir-remoto te saltas esa protección bajo tu responsabilidad. Úsalo solo con rutas públicas y baratas como
/api/v1/salud: NUNCA con /buscar (golpearía a las tiendas reales).

Ojo con el resultado: si la prueba corre en la misma máquina que la API, comparten procesador; el número es una medida
práctica de ESA máquina, no un límite teórico.
"""
import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from urllib.parse import urlsplit

import httpx

LOCALES = {"127.0.0.1", "localhost", "::1"}


def percentil(ordenados: list, p: float) -> float:
    """Percentil p (0-100) de una lista YA ordenada, en milisegundos."""
    if not ordenados:
        return 0.0
    indice = min(len(ordenados) - 1, max(0, int(round(p / 100 * (len(ordenados) - 1)))))
    return ordenados[indice] * 1000


async def medir(url: str, concurrencia: int, segundos: float, tiempo_max: float = 10.0) -> dict:
    latencias: list = []
    estados: Counter = Counter()
    errores: Counter = Counter()
    limites = httpx.Limits(max_connections=concurrencia, max_keepalive_connections=concurrencia)

    async with httpx.AsyncClient(limits=limites, timeout=tiempo_max) as cliente:
        fin = time.perf_counter() + segundos

        async def trabajador():
            while time.perf_counter() < fin:
                inicio = time.perf_counter()
                try:
                    respuesta = await cliente.get(url)
                except httpx.HTTPError as error:
                    errores[type(error).__name__] += 1
                else:
                    estados[respuesta.status_code] += 1
                    latencias.append(time.perf_counter() - inicio)

        arranque = time.perf_counter()
        await asyncio.gather(*(trabajador() for _ in range(concurrencia)))
        duracion = time.perf_counter() - arranque

    exitosas = sum(c for estado, c in estados.items() if 200 <= estado < 300)
    total = sum(estados.values()) + sum(errores.values())
    ordenadas = sorted(latencias)
    return {
        "url": url, "concurrencia": concurrencia, "segundos": round(duracion, 2),
        "peticiones": total, "exitosas": exitosas,
        "tps": round(exitosas / duracion, 1) if duracion > 0 else 0.0,
        "estados": dict(estados), "errores_de_red": dict(errores),
        "latencia_ms": {
            "p50": round(percentil(ordenadas, 50), 1), "p95": round(percentil(ordenadas, 95), 1),
            "p99": round(percentil(ordenadas, 99), 1), "max": round(ordenadas[-1] * 1000, 1) if ordenadas else 0.0,
        },
    }


def mostrar(r: dict) -> None:
    fallidas = r["peticiones"] - r["exitosas"]
    print(f"\nPrueba de carga sobre {r['url']}")
    print(f"  {r['concurrencia']} conexiones simultáneas durante {r['segundos']} s")
    print(f"  Peticiones: {r['peticiones']}  ·  exitosas: {r['exitosas']}  ·  fallidas: {fallidas}")
    print(f"  TPS (exitosas por segundo): {r['tps']}")
    lat = r["latencia_ms"]
    print(f"  Tiempo de respuesta (ms): mediana {lat['p50']} · p95 {lat['p95']} · p99 {lat['p99']} · máximo {lat['max']}")
    if r["estados"] and set(r["estados"]) != {200}:
        print(f"  Códigos HTTP: {r['estados']}")
    if r["errores_de_red"]:
        print(f"  Errores de red: {r['errores_de_red']}")
    if fallidas:
        print("  OJO: hubo respuestas que no fueron 2xx. Un 429 es el límite de velocidad de Nginx; un 503, la base de datos.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mide los TPS de la API de Picksy (solo direcciones locales).")
    ap.add_argument("--url", default="http://127.0.0.1:8000/api/v1/salud")
    ap.add_argument("--concurrencia", type=int, default=50, help="conexiones simultáneas (por defecto 50)")
    ap.add_argument("--segundos", type=float, default=20, help="duración de la prueba (por defecto 20)")
    ap.add_argument("--salida", help="archivo .json donde guardar el resultado")
    ap.add_argument("--permitir-remoto", action="store_true", help="permite direcciones que no son locales (bajo tu responsabilidad)")
    a = ap.parse_args(argv)

    anfitrion = urlsplit(a.url).hostname
    if anfitrion not in LOCALES and not a.permitir_remoto:
        print(f"Me niego a medir '{anfitrion}': esta herramienta solo acepta direcciones locales (127.0.0.1).\n"
              "Probar el sitio público equivale a atacarlo. Si de verdad es tuyo y lo sabes, agrega --permitir-remoto.")
        return 2
    if a.concurrencia < 1 or a.segundos <= 0:
        print("La concurrencia y los segundos deben ser positivos.")
        return 2

    resultado = asyncio.run(medir(a.url, a.concurrencia, a.segundos))
    mostrar(resultado)
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        print(f"  Resultado guardado en {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
