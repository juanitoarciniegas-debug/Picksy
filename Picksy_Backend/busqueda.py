from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from buscador import CONECTORES, NOMBRES, buscar_en_todas
from historial import guardar_busqueda, usuario_opcional

router = APIRouter(tags=["Búsqueda"])


def _opcion(producto, total: float) -> dict:
    return {
        "tienda": producto.tienda,
        "nombre": producto.nombre,
        "precio": producto.precio,
        "envio": producto.envio,
        "envio_confirmado": producto.envio is not None,
        "total": total,
        "url": producto.url,
        "imagen": producto.imagen,
        "actualizado_en": producto.consultado_en.isoformat(),
    }


@router.get("/buscar")
def buscar(
    producto: str = Query(min_length=2, max_length=100, description="Qué quiere comprar"),
    presupuesto: float = Query(gt=0, description="Presupuesto máximo en COP"),
    tiendas: Optional[str] = Query(default=None, description="Tiendas separadas por coma"),
    actualizar: bool = Query(default=False, description="Ignorar la caché y consultar las tiendas ahora"),
    usuario=Depends(usuario_opcional),  # historial: None si no hay sesión
):
    lista = None
    if tiendas:
        lista = [t.strip() for t in tiendas.split(",") if t.strip()]
        validas = {n.lower() for n in NOMBRES}
        desconocidas = [t for t in lista if t.lower() not in validas]
        if desconocidas:
            raise HTTPException(
                status_code=400,
                detail=f"Tiendas no reconocidas: {desconocidas}. Disponibles: {NOMBRES}",
            )

    productos, avisos = buscar_en_todas(producto.strip(), lista, forzar=actualizar)

    disponibles = [p for p in productos if p.disponible]
    agotados = len(productos) - len(disponibles)

    # RF-08: total = precio + envío (si el envío no se conoce, cuenta como 0 y se marca)
    con_total = [(p, p.precio + (p.envio or 0.0)) for p in disponibles]

    # RF-09 y RF-10
    viables = sorted((x for x in con_total if x[1] <= presupuesto), key=lambda x: x[1])
    descartadas = sorted((x for x in con_total if x[1] > presupuesto), key=lambda x: x[1])

    # RF-11 (regla de ahorro provisional, ver nota)
    mejor = viables[0] if viables else None
    ahorro = (viables[-1][1] - viables[0][1]) if viables else None

    respuesta = {
        "producto": producto.strip(),
        "presupuesto": presupuesto,
        "mejor_opcion": _opcion(*mejor) if mejor else None,
        "ahorro": ahorro,
        "viables": [_opcion(p, t) for p, t in viables],
        "descartadas": [_opcion(p, t) for p, t in descartadas],
        "agotados": agotados,
        "avisos": avisos,
    }

    # Historial (B-06): solo guarda si el usuario tiene sesión iniciada.
    guardar_busqueda(usuario, respuesta)

    return respuesta


@router.get("/tiendas")
def listar_tiendas():
    """Tiendas disponibles, para que el frontend arme el selector."""
    return [
        {"nombre": c.nombre, "especialidad": getattr(c, "especialidad", "general")}
        for c in CONECTORES
    ]