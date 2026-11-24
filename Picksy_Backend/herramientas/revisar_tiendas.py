"""
Revisa, UNA por UNA, si cada tienda responde desde ESTE computador o servidor.
Sirve para saber qué tiendas bloquean la IP de AWS (por ejemplo, Éxito responde 403 desde el servidor) y como
chequeo rápido antes de una demostración.

Uso:   python herramientas/revisar_tiendas.py                 # una consulta a cada tienda, separadas 3 s
       python herramientas/revisar_tiendas.py --tienda Falabella --termino zapatos
No usa la base de datos ni el caché: pregunta directo a las tiendas. Código de salida: 0 si todas respondieron con
productos, 1 si alguna falló o no devolvió nada.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para poder importar los módulos del backend

# Un término que esa tienda sí vende (los mismos del humo diario de QA, más Mercado Libre).
TERMINOS = {
    "Éxito": "televisor", "Olímpica": "arroz", "Homecenter": "taladro", "Falabella": "zapatos",
    "Alkosto": "televisor", "Ktronix": "portatil", "Alkomprar": "licuadora", "Buscalibre": "libro",
    "Farmatodo": "acetaminofen", "Mercado Libre": "celular",
}


def revisar(conector, termino: str) -> dict:
    """Consulta una tienda y devuelve {tienda, ok, productos, segundos, detalle}."""
    import buscador

    inicio = time.perf_counter()
    try:
        productos = conector.buscar(termino, limite=5)
        detalle = "" if productos else "respondió, pero sin productos"
        ok, cantidad = bool(productos), len(productos)
    except Exception as error:  # noqa: BLE001
        ok, cantidad = False, 0
        detalle = f"{type(error).__name__} {buscador._resumen(error)}".strip()
    return {"tienda": conector.nombre, "termino": termino, "ok": ok, "productos": cantidad,
            "segundos": round(time.perf_counter() - inicio, 1), "detalle": detalle}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Revisa si cada tienda responde desde este equipo.")
    ap.add_argument("--tienda", help="revisar solo esta tienda (por ejemplo Falabella)")
    ap.add_argument("--termino", help="término de búsqueda (por defecto uno propio de cada tienda)")
    ap.add_argument("--pausa", type=float, default=3.0, help="segundos entre tienda y tienda (por defecto 3)")
    a = ap.parse_args(argv)

    import buscador

    conectores = [c for c in buscador.CONECTORES if not a.tienda or c.nombre.lower() == a.tienda.lower()]
    if not conectores:
        print(f"No existe la tienda '{a.tienda}'. Disponibles: {', '.join(buscador.NOMBRES)}")
        return 2

    print(f"{'Tienda':<15}{'Estado':<9}{'Productos':<11}{'Segundos':<10}Detalle")
    resultados = []
    for i, conector in enumerate(conectores):
        if i:
            time.sleep(a.pausa)              # no golpear a las tiendas: una consulta cada pocos segundos
        r = revisar(conector, a.termino or TERMINOS.get(conector.nombre, "televisor"))
        resultados.append(r)
        print(f"{r['tienda']:<15}{'OK' if r['ok'] else 'FALLÓ':<9}{r['productos']:<11}{r['segundos']:<10}{r['detalle']}")

    fallaron = [r["tienda"] for r in resultados if not r["ok"]]
    print(f"\n{len(resultados) - len(fallaron)} de {len(resultados)} tiendas respondieron bien.")
    if fallaron:
        print("No respondieron: " + ", ".join(fallaron))
        print("Un 'http=403' suele significar que la tienda bloquea la IP del servidor; no se arregla desde el código.")
    return 1 if fallaron else 0


if __name__ == "__main__":
    sys.exit(main())
