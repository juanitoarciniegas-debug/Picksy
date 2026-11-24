"""
Analista (rol 'analista'; el administrador también puede).

Solo ve números agregados para entender cómo se usa Picksy. NUNCA ve correos, contraseñas ni quién
buscó qué: ningún endpoint devuelve datos de una persona.

Endpoints:
    GET /analista/resumen                          usuarios por rol, membresías, pagos y búsquedas (hoy, 7 días, por día)
    GET /analista/busquedas-populares?dias=30&limite=10   lo que más se busca
    GET /analista/tiendas-ganadoras?dias=30&limite=10     tiendas que más veces dieron la mejor opción
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth import requiere_rol
from database import engine
from roles import ROLES

router = APIRouter(prefix="/analista", tags=["Analista"])

permiso = requiere_rol("analista")

_COLOMBIA = timezone(timedelta(hours=-5))
DIAS_GRAFICA = 14


@router.get("/resumen")
def resumen(usuario=Depends(permiso)):
    with engine.connect() as conn:
        por_rol = {r: 0 for r in ROLES}
        for f in conn.execute(text("SELECT rol, COUNT(*) AS n FROM usuarios GROUP BY rol")).all():
            por_rol[f.rol] = f.n
        nuevos_7 = conn.execute(text("SELECT COUNT(*) FROM usuarios WHERE creado_en > NOW() - INTERVAL '7 days'")).scalar()
        membresias = conn.execute(text("SELECT COUNT(*) FROM membresias WHERE vence_en > NOW()")).scalar()
        pagos = conn.execute(
            text("SELECT COUNT(*) AS n, COALESCE(SUM(valor), 0) AS total FROM pagos_membresia WHERE estado = 'pagado'")
        ).first()
        por_dia = {
            f.dia: f.n for f in conn.execute(
                text("""SELECT dia, SUM(busquedas) AS n FROM uso_diario
                        WHERE dia > (NOW() AT TIME ZONE 'America/Bogota')::date - :dias GROUP BY dia"""),
                {"dias": DIAS_GRAFICA},
            ).all()
        }
    hoy = datetime.now(_COLOMBIA).date()
    serie = []
    for atras in range(DIAS_GRAFICA - 1, -1, -1):
        dia = hoy - timedelta(days=atras)
        serie.append({"dia": dia.isoformat(), "busquedas": int(por_dia.get(dia, 0))})
    return {
        "usuarios_total": sum(por_rol.values()),
        "usuarios_por_rol": por_rol,
        "usuarios_nuevos_7_dias": nuevos_7,
        "membresias_activas": membresias,
        "pagos_confirmados": pagos.n,
        "ingresos_simulados": float(pagos.total),     # los pagos de Picksy son simulados (ERS: no hay cobro real)
        "busquedas_hoy": serie[-1]["busquedas"],
        "busquedas_7_dias": sum(x["busquedas"] for x in serie[-7:]),
        "busquedas_por_dia": serie,
    }


@router.get("/busquedas-populares")
def busquedas_populares(
    dias: int = Query(default=30, ge=1, le=365),
    limite: int = Query(default=10, ge=1, le=50),
    usuario=Depends(permiso),
):
    with engine.connect() as conn:
        filas = conn.execute(
            text("""
                SELECT lower(termino) AS termino, COUNT(*) AS veces
                FROM historial_busquedas
                WHERE creado_en > NOW() - (:dias * INTERVAL '1 day')
                GROUP BY lower(termino) ORDER BY veces DESC, termino LIMIT :limite
            """),
            {"dias": dias, "limite": limite},
        ).all()
    return {"dias": dias, "busquedas": [{"termino": f.termino, "veces": f.veces} for f in filas]}


@router.get("/tiendas-ganadoras")
def tiendas_ganadoras(
    dias: int = Query(default=30, ge=1, le=365),
    limite: int = Query(default=10, ge=1, le=50),
    usuario=Depends(permiso),
):
    with engine.connect() as conn:
        filas = conn.execute(
            text("""
                SELECT resultado->'mejor'->>'tienda' AS tienda, COUNT(*) AS veces
                FROM historial_busquedas
                WHERE creado_en > NOW() - (:dias * INTERVAL '1 day') AND resultado->'mejor'->>'tienda' IS NOT NULL
                GROUP BY 1 ORDER BY veces DESC, tienda LIMIT :limite
            """),
            {"dias": dias, "limite": limite},
        ).all()
    return {"dias": dias, "tiendas": [{"tienda": f.tienda, "veces": f.veces} for f in filas]}
