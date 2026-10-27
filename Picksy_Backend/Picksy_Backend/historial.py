"""
Historial de búsquedas (B-06 · RF-15).

- Cada vez que un usuario CON sesión busca, se guarda el término, el presupuesto y un resumen.
- Si el usuario no ha iniciado sesión, /buscar sigue funcionando igual, pero no se guarda nada.
- Endpoints (todos requieren sesión):
    GET    /historial        últimas 50 búsquedas del usuario (la más reciente primero)
    DELETE /historial        borra todo el historial del usuario
    DELETE /historial/{id}   borra una búsqueda
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from auth import usuario_actual
from database import engine

router = APIRouter(prefix="/historial", tags=["Historial"])

LIMITE = 50

# auto_error=False: si no llega el token, no es error; simplemente no hay usuario.
_esquema_opcional = HTTPBearer(auto_error=False)


def usuario_opcional(
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(_esquema_opcional),
):
    """Devuelve el usuario si hay una sesión válida; si no, None (sin lanzar error)."""
    if credenciales is None:
        return None
    try:
        return usuario_actual(credenciales)
    except HTTPException:
        return None


def _resumen(respuesta: dict) -> dict:
    """Versión corta de la respuesta de /buscar, para no guardar cientos de productos."""
    mejor = respuesta.get("mejor_opcion")
    return {
        "viables": len(respuesta.get("viables", [])),
        "descartadas": len(respuesta.get("descartadas", [])),
        "mejor": (
            {"tienda": mejor["tienda"], "nombre": mejor["nombre"], "total": mejor["total"]}
            if mejor else None
        ),
    }


def guardar_busqueda(usuario: Optional[dict], respuesta: dict) -> None:
    """Guarda la búsqueda en el historial. Nunca debe romper la búsqueda: si falla, solo se avisa."""
    if not usuario:
        return
    try:
        termino = respuesta["producto"]
        presupuesto = respuesta["presupuesto"]
        with engine.begin() as conn:
            # Evita duplicados seguidos (doble clic, o reordenar y volver a buscar).
            repetida = conn.execute(
                text("""
                    SELECT 1 FROM historial_busquedas
                    WHERE usuario_id = :u AND lower(termino) = lower(:t) AND presupuesto = :p
                      AND creado_en > NOW() - INTERVAL '1 minute'
                    LIMIT 1
                """),
                {"u": usuario["id"], "t": termino, "p": presupuesto},
            ).first()
            if repetida:
                return
            conn.execute(
                text("""
                    INSERT INTO historial_busquedas (usuario_id, termino, presupuesto, resultado)
                    VALUES (:u, :t, :p, CAST(:r AS JSONB))
                """),
                {"u": usuario["id"], "t": termino, "p": presupuesto,
                 "r": json.dumps(_resumen(respuesta), ensure_ascii=False)},
            )
    except Exception as error:  # noqa: BLE001 - el historial es secundario
        print(f"[historial] No se pudo guardar la búsqueda: {error}")


@router.get("")
def listar_historial(usuario: dict = Depends(usuario_actual)):
    with engine.connect() as conn:
        filas = conn.execute(
            text("""
                SELECT id, termino, presupuesto, resultado, creado_en
                FROM historial_busquedas
                WHERE usuario_id = :u
                ORDER BY creado_en DESC, id DESC
                LIMIT :limite
            """),
            {"u": usuario["id"], "limite": LIMITE},
        ).all()
    return [
        {
            "id": f.id,
            "termino": f.termino,
            "presupuesto": float(f.presupuesto),
            "resultado": f.resultado,
            "creado_en": f.creado_en.isoformat(),
        }
        for f in filas
    ]


@router.delete("")
def borrar_todo(usuario: dict = Depends(usuario_actual)):
    with engine.begin() as conn:
        resultado = conn.execute(
            text("DELETE FROM historial_busquedas WHERE usuario_id = :u"),
            {"u": usuario["id"]},
        )
    return {"borradas": resultado.rowcount}


@router.delete("/{busqueda_id}")
def borrar_una(busqueda_id: int, usuario: dict = Depends(usuario_actual)):
    with engine.begin() as conn:
        resultado = conn.execute(
            text("DELETE FROM historial_busquedas WHERE id = :id AND usuario_id = :u"),
            {"id": busqueda_id, "u": usuario["id"]},  # el "AND usuario_id" impide borrar lo de otro usuario
        )
    if resultado.rowcount == 0:
        raise HTTPException(status_code=404, detail="Esa búsqueda no existe en tu historial")
    return {"borrada": busqueda_id}