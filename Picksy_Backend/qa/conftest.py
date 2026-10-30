"""
conftest.py - El "cerebro" del bot de QA de Picksy.

Hace cuatro cosas:
  1. GUARDIA: se niega a correr contra una base de datos real (no perjudicar al proyecto).
  2. FIXTURES: cliente de la API, tiendas simuladas, limpieza de datos de prueba.
  3. REQUISITOS: cada prueba declara qué requisito cubre con @pytest.mark.req("RF-01").
     Se valida contra requisitos.yml (si el ID no existe, se detiene: es un error de QA).
  4. INFORMES: al terminar escribe en qa_salida/ el resumen por categorías, la matriz de
     trazabilidad y los datos de la ejecución (resultados.json) para el historial mensual.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

QA = Path(__file__).resolve().parent
BACKEND = QA.parent
load_dotenv(BACKEND / ".env")

SALIDA = Path(os.getenv("QA_SALIDA", BACKEND / "qa_salida"))
REQUISITOS = yaml.safe_load((QA / "requisitos.yml").read_text(encoding="utf-8"))
REQ_POR_ID = {r["id"]: r for r in REQUISITOS["requisitos"]}

_resultados = []          # un registro por caso ejecutado
_inicio = datetime.now(timezone.utc)


# --------------------------------------------------------------------------- configuración
def pytest_configure(config):
    config.addinivalue_line("markers", "req(*ids): requisito(s) del ERS que cubre la prueba")
    config.addinivalue_line("markers", "contrato: prueba de la alarma de cambios del contrato de la API")
    config.addinivalue_line("markers", "real: consulta tiendas REALES (solo con QA_TIENDAS_REALES=1)")


def pytest_collection_modifyitems(config, items):
    desconocidos = set()
    for item in items:
        for marca in item.iter_markers("req"):
            for rid in marca.args:
                if rid not in REQ_POR_ID:
                    desconocidos.add(f"{rid} (en {item.nodeid})")
        # Protección anti-bloqueo: lo que toca tiendas reales no corre por accidente.
        if item.get_closest_marker("real") and os.getenv("QA_TIENDAS_REALES") != "1":
            item.add_marker(pytest.mark.skip(
                reason="OMITIDA: consulta tiendas reales; solo corre con QA_TIENDAS_REALES=1"))
    if desconocidos:
        raise pytest.UsageError(
            "Marcador @pytest.mark.req con un ID que no está en requisitos.yml: "
            + ", ".join(sorted(desconocidos)))


# --------------------------------------------------------------------------- fixtures
def _bd_segura():
    nombre = (os.getenv("DB_NAME") or "").lower()
    return ("test" in nombre or os.getenv("CI") == "true"
            or os.getenv("QA_PERMITIR_BD_REAL") == "1")


@pytest.fixture(scope="session", autouse=True)
def guardia_y_limpieza():
    """Guardia: las pruebas crean y borran datos, así que NO corren contra tu base real.
    Permitido si el nombre de la base contiene 'test', si es el CI de GitHub (base desechable)
    o si pones QA_PERMITIR_BD_REAL=1 a propósito."""
    if not _bd_segura():
        pytest.exit(
            f"DETENIDO: DB_NAME='{os.getenv('DB_NAME')}' no parece una base de pruebas. "
            "Crea 'smartbudget_test' (python preparar_base.py con DB_NAME=smartbudget_test) "
            "o define QA_PERMITIR_BD_REAL=1 si sabes lo que haces.", returncode=3)
    from ayudas import consulta_db
    try:
        consulta_db("SELECT 1")
    except Exception as error:  # noqa: BLE001
        pytest.exit("ERROR DE INFRAESTRUCTURA: no hay conexión con la base de datos de pruebas "
                    f"({type(error).__name__}). Revisa que PostgreSQL esté encendido y el .env.", returncode=3)
    _limpiar()
    yield
    _limpiar()


def _limpiar():
    """Borra SOLO lo que crean las pruebas: usuarios qa_*, caché 'qa *' y productos de https://qa.test/"""
    from ayudas import consulta_db
    try:
        consulta_db("DELETE FROM historial_busquedas WHERE usuario_id IN "
                    "(SELECT id FROM usuarios WHERE correo LIKE %s)", ("qa\\_%@test.com",))
        consulta_db("DELETE FROM usuarios WHERE correo LIKE %s", ("qa\\_%@test.com",))
        consulta_db("DELETE FROM cache_busquedas WHERE termino LIKE %s", ("qa %",))
        consulta_db("DELETE FROM productos WHERE url LIKE %s", ("https://qa.test/%",))
    except Exception as error:  # noqa: BLE001
        print("Limpieza de datos de prueba no realizada:", error)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from main import app
    # raise_server_exceptions=False: un error 500 llega como respuesta 500 y se puede afirmar sobre él
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def tiendas(monkeypatch):
    """Tiendas simuladas: ninguna petición sale a Internet."""
    from mocks import TiendasSimuladas
    return TiendasSimuladas(monkeypatch)


@pytest.fixture
def termino():
    from ayudas import termino_nuevo
    return termino_nuevo()


# --------------------------------------------------------------------------- recolección
PATRON_INFRA = re.compile(r"OperationalError|Connection refused|could not connect|ConnectionError", re.I)


def _categoria(estado, marcas, razon):
    if estado == "failed":
        if PATRON_INFRA.search(razon or ""):
            return "ERROR DE INFRAESTRUCTURA"   # fallo del entorno o del bot, NO del producto
        return "CAMBIÓ EL CONTRATO" if "contrato" in marcas else "FALLÓ UNA REGLA"
    if estado == "xfailed":
        return "DEFECTO CONOCIDO"
    if estado == "xpassed":
        return "POSIBLEMENTE CORREGIDO"
    if estado == "skipped":
        return "BLOQUEADO" if razon.upper().startswith("BLOQUEADO") else "OMITIDA"
    return "PASÓ"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultado = yield
    rep = resultado.get_result()
    if not (rep.when == "call" or (rep.when == "setup" and (rep.failed or rep.skipped))):
        return
    if hasattr(rep, "wasxfail"):
        estado = "xfailed" if rep.skipped else "xpassed"
        razon = rep.wasxfail or ""
    elif rep.skipped:
        estado = "skipped"
        razon = rep.longrepr[2] if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
        razon = re.sub(r"^Skipped: ", "", razon)
    elif rep.failed:
        estado = "failed"
        razon = str(rep.longreprtext)[-300:].replace("\n", " ")
    else:
        estado, razon = "passed", ""
    marcas = {m.name for m in item.iter_markers()}
    reqs = sorted({rid for m in item.iter_markers("req") for rid in m.args})
    defecto = re.search(r"DEF-\d+", razon or "")
    _resultados.append({
        "caso": item.nodeid.replace("qa/", ""),
        "requisitos": reqs,
        "estado": estado,
        "categoria": _categoria(estado, marcas, razon),
        "defecto": defecto.group(0) if defecto else None,
        "motivo": (razon or "")[:300],
        "duracion_s": round(rep.duration, 3),
    })


# --------------------------------------------------------------------------- informes
EJECUTADOS = {"passed", "failed", "xfailed", "xpassed"}


def _estado_requisito(rid):
    req = REQ_POR_ID[rid]
    casos = [r for r in _resultados if rid in r["requisitos"]]
    ejecutados = [c for c in casos if c["estado"] in EJECUTADOS]
    if not ejecutados:
        if req.get("implementado") is False:
            return "No implementado (v1)", casos
        bloqueados = [c for c in casos if c["categoria"] == "BLOQUEADO"]
        if bloqueados or req.get("bloqueado_por"):
            return "Bloqueado (" + ", ".join(req.get("bloqueado_por", [])) + ")", casos
        return ("Revisión manual pendiente" if req.get("metodo_manual") else "Sin prueba"), casos
    if any(c["estado"] == "failed" for c in ejecutados):
        return "Falló", casos
    if any(c["estado"] == "xfailed" for c in ejecutados):
        return "Defecto conocido", casos
    if any(c["estado"] == "xpassed" for c in ejecutados):
        return "Posiblemente corregido", casos
    if any(c["categoria"] == "BLOQUEADO" for c in casos) or req.get("bloqueado_por"):
        return "Parcial (bloqueado por " + ", ".join(req.get("bloqueado_por", ["?"])) + ")", casos
    return "Verificado (automático)", casos


def _commit():
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:  # noqa: BLE001
        return "desconocido"


def pytest_sessionfinish(session, exitstatus):
    if not _resultados:
        return
    SALIDA.mkdir(parents=True, exist_ok=True)
    cuenta = lambda e: sum(1 for r in _resultados if r["estado"] == e)  # noqa: E731
    estados = {rid: _estado_requisito(rid) for rid in REQ_POR_ID}
    cubiertos = [rid for rid, (_, casos) in estados.items()
                 if any(c["estado"] in EJECUTADOS for c in casos)]
    sin_prueba = [rid for rid, (e, _) in estados.items() if e in ("Sin prueba", "Revisión manual pendiente")]
    defectos = sorted({r["defecto"] for r in _resultados if r["estado"] == "xfailed" and r["defecto"]})
    ahora = datetime.now(timezone.utc)

    datos = {
        "fecha_hora_utc": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "id_ejecucion": (os.getenv("GITHUB_RUN_ID") + "-" + os.getenv("GITHUB_RUN_ATTEMPT", "1"))
                         if os.getenv("GITHUB_RUN_ID") else "local-" + ahora.strftime("%Y%m%d%H%M%S"),
        "disparador": os.getenv("GITHUB_EVENT_NAME", "local"),
        "commit": _commit(),
        "rama": os.getenv("GITHUB_REF_NAME", "local"),
        "version_software": os.getenv("QA_VERSION_SW", "v1"),
        "tiendas_reales": "sí" if os.getenv("QA_TIENDAS_REALES") == "1" else "no",
        "duracion_s": round((ahora - _inicio).total_seconds(), 1),
        "enlace_al_run": (f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}"
                          f"/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
                          if os.getenv("GITHUB_RUN_ID") else ""),
        "total": len(_resultados),
        "pasaron": cuenta("passed"),
        "fallaron": cuenta("failed"),
        "omitidas": cuenta("skipped"),
        "xfail": cuenta("xfailed"),
        "xpass": cuenta("xpassed"),
        "defectos_abiertos": len(defectos),
        "defectos": defectos,
        "req_cubiertos": len(cubiertos),
        "req_totales": len(REQ_POR_ID),
        "requisitos": {rid: e for rid, (e, _) in estados.items()},
        "requisitos_sin_prueba": sin_prueba,
        "casos": _resultados,
    }
    (SALIDA / "resultados.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    (SALIDA / "resumen.md").write_text(_resumen_md(datos, estados), encoding="utf-8")
    (SALIDA / "matriz_trazabilidad.md").write_text(_matriz_md(datos, estados), encoding="utf-8")


def _resumen_md(d, estados):
    L = ["## Resultado QA Picksy", ""]
    L.append(f"**{d['pasaron']} pasaron · {d['fallaron']} fallaron · {d['xfail']} defectos conocidos · "
             f"{d['omitidas']} omitidas · {d['xpass']} posiblemente corregidos** (de {d['total']} casos)")
    L.append("")
    L.append(f"Requisitos con prueba ejecutada: **{d['req_cubiertos']} de {d['req_totales']}** · "
             f"Tiendas reales: {d['tiendas_reales']} · Commit `{d['commit'][:7]}`")
    L.append("")
    bloques = [
        ("ERROR DE INFRAESTRUCTURA", "🔧 Error de infraestructura (base de datos o entorno; NO es defecto de Picksy)"),
        ("FALLÓ UNA REGLA", "❌ Falló una regla (posible defecto: QA confirma)"),
        ("CAMBIÓ EL CONTRATO", "🔔 Cambió el contrato de la API (QA decide si es intencional)"),
        ("POSIBLEMENTE CORREGIDO", "🟡 Defecto posiblemente corregido (QA verifica y cierra)"),
        ("DEFECTO CONOCIDO", "🐞 Defectos conocidos que siguen abiertos"),
        ("BLOQUEADO", "⛔ Casos bloqueados por una ambigüedad del ERS"),
    ]
    for cat, titulo in bloques:
        casos = [c for c in d["casos"] if c["categoria"] == cat]
        if casos:
            L += [f"### {titulo}", ""]
            for c in casos:
                extra = f" ({c['defecto']})" if c["defecto"] else ""
                L.append(f"- `{c['caso']}`{extra} - {c['motivo'][:160]}")
            L.append("")
    if d["requisitos_sin_prueba"]:
        L += ["### 📋 Requisitos sin prueba", "",
              ", ".join(d["requisitos_sin_prueba"]), ""]
    L += ["### Estado por requisito", "", "| Requisito | Estado | Casos |", "|---|---|---|"]
    for rid, (estado, casos) in estados.items():
        L.append(f"| {rid} | {estado} | {len(casos)} |")
    return "\n".join(L) + "\n"


def _matriz_md(d, estados):
    L = ["# Matriz de trazabilidad (generada por el bot)", "",
         f"Ejecución `{d['id_ejecucion']}` · {d['fecha_hora_utc']} UTC · commit `{d['commit'][:7]}` · versión {d['version_software']}", "",
         "| Requisito | Prioridad | Título | Estado | Casos que lo cubren |", "|---|---|---|---|---|"]
    for rid, (estado, casos) in estados.items():
        r = REQ_POR_ID[rid]
        nombres = "<br>".join(f"{c['caso'].split('::')[-1]} ({c['estado']})" for c in casos) or "-"
        L.append(f"| {rid} | {r.get('prioridad', '-')} | {r['titulo']} | {estado} | {nombres} |")
    return "\n".join(L) + "\n"


def pytest_terminal_summary(terminalreporter):
    ruta = SALIDA / "resumen.md"
    if ruta.exists():
        terminalreporter.section("BOT DE QA - resumen por categorías")
        texto = ruta.read_text(encoding="utf-8")
        try:
            terminalreporter.write(texto)
        except UnicodeEncodeError:   # consolas de Windows con codificación antigua
            terminalreporter.write(texto.encode("ascii", "replace").decode())
