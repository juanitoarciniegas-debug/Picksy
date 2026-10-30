"""
registrar.py - Guarda de forma PERMANENTE el resultado de una ejecución del bot.

Escribe (dentro de la carpeta docs/qa de la rama qa-registros):
  historial_qa.csv                      una fila por ejecución (fuente del informe mensual)
  ejecuciones/AAAA-MM/<fecha>_<id>.md   el detalle caso por caso de esa ejecución
  evidencias/AAAA-MM/<fecha>_<id>_*.html  los reportes HTML de pytest
  matriz_trazabilidad_actual.md         la matriz de la última ejecución

Solo usa la biblioteca estándar. Es idempotente: si se repite con la misma ejecución, reemplaza su fila.
Como el repositorio es PÚBLICO, todo texto pasa por un filtro que oculta valores de secretos del entorno.
"""
import argparse
import csv
import glob
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

COLUMNAS = ["fecha_hora_utc", "id_ejecucion", "disparador", "commit", "rama", "version_software",
            "resultado", "total", "pasaron", "fallaron", "omitidas", "xfail", "xpass",
            "defectos_abiertos", "defectos", "tiendas_reales", "duracion_s",
            "req_cubiertos", "req_totales", "enlace_al_run"]
VARIABLES_SECRETAS = ("DB_PASSWORD", "MAIL_PASSWORD", "MAIL_USERNAME", "MAIL_TO", "GITHUB_TOKEN")


def ocultar(texto):
    """Reemplaza por *** cualquier valor de variable secreta presente en el texto."""
    for nombre in VARIABLES_SECRETAS:
        valor = os.getenv(nombre)
        if valor and len(valor) >= 4:
            texto = texto.replace(valor, "***")
    return texto


def resultado_global(d, otros_fallaron):
    if any(c.get("categoria") == "ERROR DE INFRAESTRUCTURA" for c in d.get("casos", [])):
        return "ERROR DE INFRAESTRUCTURA"
    if d.get("fallaron") or otros_fallaron:
        return "FALLÓ"
    return "PASÓ"


def datos_minimos():
    """Si el bot ni siquiera alcanzó a escribir resultados.json, se deja constancia igual."""
    ahora = datetime.now(timezone.utc)
    run = os.getenv("GITHUB_RUN_ID")
    return {
        "fecha_hora_utc": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "id_ejecucion": f"{run}-{os.getenv('GITHUB_RUN_ATTEMPT', '1')}" if run else "local-" + ahora.strftime("%Y%m%d%H%M%S"),
        "disparador": os.getenv("GITHUB_EVENT_NAME", "local"), "commit": os.getenv("GITHUB_SHA", ""),
        "rama": os.getenv("GITHUB_REF_NAME", "local"), "version_software": os.getenv("QA_VERSION_SW", "v1"),
        "tiendas_reales": "sí" if os.getenv("QA_TIENDAS_REALES") == "1" else "no",
        "casos": [{"categoria": "ERROR DE INFRAESTRUCTURA", "caso": "el bot no generó resultados.json",
                   "requisitos": [], "estado": "failed", "duracion_s": 0, "motivo": "Ver el log de la ejecución"}],
        "enlace_al_run": (f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{run}" if run else ""),
    }


def escribir_fila(historial, fila):
    filas = []
    if historial.exists():
        with historial.open(encoding="utf-8", newline="") as f:
            filas = [r for r in csv.DictReader(f) if r["id_ejecucion"] != fila["id_ejecucion"]]
    filas.append({c: fila.get(c, "") for c in COLUMNAS})
    filas.sort(key=lambda r: r["fecha_hora_utc"])
    with historial.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)


def detalle_md(d):
    L = [f"# Ejecución {d['id_ejecucion']}", "",
         f"- **Fecha (UTC):** {d['fecha_hora_utc']}  ·  **Hora Colombia:** {hora_colombia(d['fecha_hora_utc'])}",
         f"- **Disparador:** {d['disparador']}  ·  **Rama:** {d['rama']}  ·  **Commit:** `{str(d['commit'])[:7]}`",
         f"- **Versión del software:** {d['version_software']}  ·  **Tiendas reales:** {d['tiendas_reales']}",
         f"- **Resultado:** {d['resultado']}"]
    if d.get("enlace_al_run"):
        L.append(f"- **Run en GitHub:** {d['enlace_al_run']}")
    L += ["", "| Caso | Requisitos | Resultado | Categoría | Segundos |", "|---|---|---|---|---|"]
    for c in d.get("casos", []):
        L.append(f"| `{c['caso']}` | {', '.join(c['requisitos']) or '-'} | {c['estado']} | {c['categoria']} | {c['duracion_s']} |")
    fallos = [c for c in d.get("casos", []) if c["categoria"] not in ("PASÓ", "OMITIDA")]
    if fallos:
        L += ["", "## Detalle de lo que no pasó", ""]
        L += [f"- `{c['caso']}` ({c['categoria']}): {c['motivo'][:250]}" for c in fallos]
    return "\n".join(L) + "\n"


def hora_colombia(utc_texto):
    return (datetime.strptime(utc_texto, "%Y-%m-%d %H:%M:%S") - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True, help="carpeta qa_salida con resultados.json")
    ap.add_argument("--destino", required=True, help="carpeta docs/qa donde se guarda el registro")
    ap.add_argument("--reportes", default="", help="patrón de los reportes HTML a copiar")
    ap.add_argument("--otros-fallaron", default="false", help="true si otra suite (p. ej. test_api.py) falló")
    a = ap.parse_args()

    entrada, destino = Path(a.entrada), Path(a.destino)
    f_json = entrada / "resultados.json"
    d = json.loads(f_json.read_text(encoding="utf-8")) if f_json.exists() else datos_minimos()
    d["resultado"] = resultado_global(d, a.otros_fallaron.lower() == "true")
    d["defectos"] = ",".join(d.get("defectos", [])) if isinstance(d.get("defectos"), list) else d.get("defectos", "")

    mes = d["fecha_hora_utc"][:7]
    marca = d["fecha_hora_utc"].replace(" ", "_").replace(":", "").replace("-", "")
    destino.mkdir(parents=True, exist_ok=True)

    escribir_fila(destino / "historial_qa.csv", d)

    carpeta = destino / "ejecuciones" / mes
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{marca}_{d['id_ejecucion']}.md").write_text(ocultar(detalle_md(d)), encoding="utf-8")

    if (entrada / "matriz_trazabilidad.md").exists():
        shutil.copy(entrada / "matriz_trazabilidad.md", destino / "matriz_trazabilidad_actual.md")

    if a.reportes:
        ev = destino / "evidencias" / mes
        ev.mkdir(parents=True, exist_ok=True)
        for ruta in glob.glob(a.reportes):
            shutil.copy(ruta, ev / f"{marca}_{d['id_ejecucion']}_{Path(ruta).name}")

    print(f"Registrada la ejecución {d['id_ejecucion']}: {d['resultado']} -> {destino}")


if __name__ == "__main__":
    main()
