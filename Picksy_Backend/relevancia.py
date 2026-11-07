"""
Filtro de relevancia (DEF-01): las tiendas a veces devuelven cosas que no tienen nada que ver con lo buscado
(buscas "televisor samsung 55" y llega un cable HDMI o una funda). Aquí se descartan.

Regla: cada palabra importante de la búsqueda debe aparecer en el nombre del producto.
  - No importan mayúsculas ni tildes ("audifonos" encuentra "Audífonos").
  - Plural/singular cuentan igual ("zapatos" encuentra "zapato", "televisores" encuentra "televisor").
  - Las palabras de relleno ("de", "para", "con"...) se ignoran.
  - Los números sí cuentan ("iphone 15" no acepta "iPhone 14").
"""
import re

from cache import normalizar

RELLENO = {"de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "para", "con", "sin", "por", "en", "a", "al"}


def _raiz(palabra: str) -> str:
    """Quita la 's'/'es' final para que plural y singular coincidan (sin tocar números ni palabras cortas)."""
    if palabra.isdigit() or len(palabra) <= 3:
        return palabra
    if palabra.endswith("es") and len(palabra) > 4:
        return palabra[:-2]
    if palabra.endswith("s"):
        return palabra[:-1]
    return palabra


# Formas distintas de escribir lo mismo ("PlayStation 5", "PS5", "Play Station 5", "PS 5" son la misma consola).
ALIAS = [
    (re.compile(r"\bplay\s*station\b"), "ps"),
]


def _palabras(texto: str) -> list[str]:
    t = normalizar(texto)
    for patron, cambio in ALIAS:
        t = patron.sub(cambio, t)
    return re.findall(r"[a-z0-9]+", t)


def palabras_clave(busqueda: str) -> list[str]:
    todas = _palabras(busqueda)
    utiles = [p for p in todas if p not in RELLENO]
    return [_raiz(p) for p in (utiles or todas)]


def es_relevante(nombre: str, claves: list[str]) -> bool:
    if not claves:
        return True
    lista = _palabras(nombre)
    del_producto = {_raiz(p) for p in lista}
    texto = " ".join(del_producto)
    pegado = "".join(lista)   # "PS 5" y "PS5" -> "ps5"
    # CAMBIO (QA): pares de palabras vecinas unidas ("ps" + "5" -> "ps5"): así buscar "ps5" encuentra "PlayStation 5".
    unidas = {a + b for a, b in zip(lista, lista[1:])}
    for i, c in enumerate(claves):
        if c in del_producto:
            continue
        # La palabra seguida de un número pegado ("ps" en "ps5", "iphone" en "iphone15").
        if c.isalpha() and any(t.startswith(c) and t[len(c):].isdigit() for t in del_producto):
            continue
        # La búsqueda escrita pegada ("ps5", "iphone15") y el producto con espacio ("PlayStation 5", "iPhone 15").
        if re.fullmatch(r"[a-z]+\d+", c) and c in unidas:
            continue
        # Un número pegado a la palabra anterior de la búsqueda ("ps 5" -> "ps5", "iphone 15" -> "iphone15").
        if c.isdigit() and i > 0 and (claves[i - 1] + c) in pegado:
            continue
        # Palabras pegadas o con medida ("55pulgadas", "128gb"): se acepta si la clave está dentro de otra palabra
        # solo cuando la clave tiene 4 letras o más (evita que "tv" coincida con "ventilador").
        if len(c) >= 4 and c in texto:
            continue
        return False
    return True


def filtrar(productos: list, busqueda: str) -> tuple[list, int]:
    """Devuelve (productos relevantes, cuántos se descartaron)."""
    claves = palabras_clave(busqueda)
    buenos = [p for p in productos if es_relevante(p.nombre, claves)]
    return buenos, len(productos) - len(buenos)
