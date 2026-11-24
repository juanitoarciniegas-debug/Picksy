"""
Comprueba, en español y paso a paso, si las credenciales de Mercado Libre sirven desde ESTE equipo (el servidor).
Córrelo UNA vez antes de dejar Mercado Libre activo en producción.

Uso:   python herramientas/probar_mercadolibre.py [--termino celular]
Lee ML_CLIENT_ID y ML_CLIENT_SECRET del .env (nunca los muestra). Código de salida: 0 = todo bien, 1 = algo falló, 2 = faltan credenciales.
"""
import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para poder importar los módulos del backend

import config  # noqa: E402
from conectores.mercadolibre import ConectorMercadoLibre  # noqa: E402

PISTAS = {
    400: "Mercado Libre rechazó la solicitud del token. Revisa que ML_CLIENT_ID y ML_CLIENT_SECRET estén completos y sin espacios, "
         "y que la aplicación permita el acceso con sus propias credenciales.",
    401: "Credenciales o token no válidos. Revisa ML_CLIENT_ID y ML_CLIENT_SECRET (¿copiaste el 'Secret Key' correcto de la aplicación?).",
    403: "Mercado Libre no deja a esta aplicación (o a esta IP) hacer la búsqueda. Posibles causas: la aplicación no tiene el permiso de "
         "lectura/búsqueda activado en el DevCenter, la cuenta no está verificada, o la IP del servidor está bloqueada.",
    404: "La dirección no existe: puede que Mercado Libre haya cambiado la API. Revisa su documentación.",
    429: "Demasiadas consultas seguidas. Espera unos minutos y vuelve a probar.",
}


def mensaje_de_la_api(respuesta: httpx.Response) -> str:
    try:
        datos = respuesta.json()
        partes = [str(datos[c]) for c in ("error", "message", "cause") if datos.get(c)]
        return " · ".join(partes)[:300] or respuesta.text[:300]
    except Exception:  # noqa: BLE001
        return respuesta.text[:300]


def explicar(error: Exception) -> None:
    if isinstance(error, httpx.HTTPStatusError):
        codigo = error.response.status_code
        print(f"   FALLÓ: Mercado Libre respondió HTTP {codigo}. Dijo: {mensaje_de_la_api(error.response)}")
        print("   " + PISTAS.get(codigo, "Es un error de Mercado Libre (5xx): prueba más tarde." if codigo >= 500 else "Respuesta inesperada."))
    elif isinstance(error, httpx.TransportError):
        print(f"   FALLÓ: no hay conexión con api.mercadolibre.com desde este equipo ({type(error).__name__}).")
    else:
        print(f"   FALLÓ: {type(error).__name__}: {error}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prueba las credenciales de Mercado Libre.")
    ap.add_argument("--termino", default="celular")
    a = ap.parse_args(argv)

    if not (config.ML_CLIENT_ID and config.ML_CLIENT_SECRET):
        print("Faltan ML_CLIENT_ID y/o ML_CLIENT_SECRET en el .env. Sin ellos Mercado Libre queda desactivado (es lo normal).")
        return 2

    conector = ConectorMercadoLibre(config.ML_CLIENT_ID, config.ML_CLIENT_SECRET)

    print("1) Pidiendo el token de acceso...")
    try:
        conector._obtener_token()
        print("   OK: Mercado Libre entregó el token.")
    except Exception as error:  # noqa: BLE001
        explicar(error)
        return 1

    print(f"2) Buscando '{a.termino}' en Mercado Libre Colombia...")
    try:
        productos = conector.buscar(a.termino, limite=5)
    except Exception as error:  # noqa: BLE001
        explicar(error)
        return 1
    if not productos:
        print("   La búsqueda respondió, pero sin productos válidos. Prueba con otro término (--termino).")
        return 1
    print(f"   OK: {len(productos)} productos. Ejemplos:")
    for p in productos[:3]:
        print(f"     - {p.nombre[:55]:<55} ${p.precio:>12,.0f}  {'envío gratis' if p.envio == 0 else ''}")
    print("\nTodo bien: Mercado Libre está listo. Reinicia la API (sudo systemctl restart picksy) para que aparezca como tienda 10.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
