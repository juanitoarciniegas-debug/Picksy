import time

from buscador import buscar_en_todas

TERMINO = "televisor"

for nombre, forzar in [("En frío (consulta las tiendas)", True), ("Con caché", False)]:
    t0 = time.time()
    productos, avisos = buscar_en_todas(TERMINO, forzar=forzar)
    print(f"{nombre}: {len(productos)} productos en {time.time() - t0:.1f}s")
    for aviso in avisos:
        print("   aviso:", aviso)