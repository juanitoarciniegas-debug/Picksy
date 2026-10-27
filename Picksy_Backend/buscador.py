import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as EsperaAgotada
from conectores.farmatodo import ConectorFarmatodo

from cache import guardar_cache, leer_cache, normalizar
from conectores.algolia import ConectorAlgolia
from conectores.buscalibre import ConectorBuscalibre
from conectores.nextdata import ConectorFalabella, ConectorHomecenter
from conectores.vtex import ConectorVtex

CONECTORES = [
    ConectorVtex("Éxito", "www.exito.com"),
    ConectorVtex("Olímpica", "www.olimpica.com"),
    ConectorHomecenter(),
    ConectorFalabella(),
    ConectorAlgolia("Alkosto", "https://www.alkosto.com"),
    ConectorAlgolia("Ktronix", "https://www.ktronix.com"),
    ConectorAlgolia("Alkomprar", "https://www.alkomprar.com"),
    ConectorBuscalibre(),
    ConectorFarmatodo(),
]

NOMBRES = [c.nombre for c in CONECTORES]

LIMITE_SEGUNDOS = 8


def buscar_en_todas(termino: str, tiendas=None, forzar: bool = False):
    if tiendas:
        pedidas = {t.lower() for t in tiendas}
        conectores = [c for c in CONECTORES if c.nombre.lower() in pedidas]
    else:
        conectores = CONECTORES

    clave = normalizar(termino)

    def ejecutar(conector):
        # 1. ¿Hay datos guardados de menos de 24 horas?
        if not forzar:
            try:
                guardados = leer_cache(clave, conector.nombre)
                if guardados is not None:
                    return guardados, None
            except Exception:
                pass  # si la base de datos falla, se sigue sin caché

        # 2. Consultar la tienda
        try:
            productos = conector.buscar(termino)
        except Exception as error:
            # 3. Si falla, usar datos viejos si existen (RF-06, RNF-05)
            try:
                viejos = leer_cache(clave, conector.nombre, solo_vigente=False)
            except Exception:
                viejos = None
            if viejos:
                return viejos, f"{conector.nombre} no respondió; se muestran datos guardados anteriormente"
            return [], f"{conector.nombre} no respondió ({type(error).__name__})"

        # 4. Guardar para la próxima vez (solo si hubo resultados)
        if productos:
            try:
                guardar_cache(clave, conector.nombre, productos)
            except Exception:
                pass
        return productos, None

    pool = ThreadPoolExecutor(max_workers=max(len(conectores), 1))
    futuros = [(c, pool.submit(ejecutar, c)) for c in conectores]
    limite = time.time() + LIMITE_SEGUNDOS

    productos = []
    avisos = []
    for conector, futuro in futuros:
        try:
            lista, aviso = futuro.result(timeout=max(0.0, limite - time.time()))
        except EsperaAgotada:
            try:
                viejos = leer_cache(clave, conector.nombre, solo_vigente=False)
            except Exception:
                viejos = None
            if viejos:
                lista = viejos
                aviso = f"{conector.nombre} tardó demasiado; se muestran datos guardados anteriormente"
            else:
                lista = []
                aviso = f"{conector.nombre} tardó demasiado y se omitió; estará disponible en la próxima búsqueda"
        productos.extend(lista)
        if aviso:
            avisos.append(aviso)

    pool.shutdown(wait=False)  # no esperar a las tiendas que siguen trabajando
    return productos, avisos