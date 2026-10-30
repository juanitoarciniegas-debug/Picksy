"""
informe_mensual.py - Arma el informe de QA de un mes a partir de historial_qa.csv.

Uso:  python informe_mensual.py --historial docs/qa/historial_qa.csv --mes 2026-10 --destino docs/qa/informes
Solo usa la biblioteca estándar. Las fechas se agrupan en HORA DE COLOMBIA (UTC-5).
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def a_colombia(utc_texto):
    return datetime.strptime(utc_texto, "%Y-%m-%d %H:%M:%S") - timedelta(hours=5)


def entero(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--historial", required=True)
    ap.add_argument("--mes", required=True, help="AAAA-MM")
    ap.add_argument("--destino", required=True)
    a = ap.parse_args()

    historial = Path(a.historial)
    filas = []
    if historial.exists():
        with historial.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                r["_local"] = a_colombia(r["fecha_hora_utc"])
                if r["_local"].strftime("%Y-%m") == a.mes:
                    filas.append(r)
    filas.sort(key=lambda r: r["_local"])

    L = [f"# Informe mensual de QA · Picksy · {a.mes}", "",
         "Elaborado por Ingeniería de QA. Generado automáticamente desde `historial_qa.csv`; "
         "las horas están en hora de Colombia (UTC-5).", ""]

    if not filas:
        L += ["No hay ejecuciones registradas en este mes.", ""]
    else:
        pasaron = sum(1 for r in filas if r["resultado"] == "PASÓ")
        cuenta = Counter(r["resultado"] for r in filas)
        por_disp = Counter(r["disparador"] for r in filas)
        L += ["## 1. Resumen ejecutivo", "",
              f"- Ejecuciones en el mes: **{len(filas)}** ({', '.join(f'{v} {k}' for k, v in por_disp.items())})",
              f"- Resultado: **{pasaron} PASÓ** ({100 * pasaron / len(filas):.0f} %) · "
              + " · ".join(f"{v} {k}" for k, v in cuenta.items() if k != "PASÓ"),
              f"- Última ejecución: **{filas[-1]['resultado']}** el {filas[-1]['_local'].strftime('%Y-%m-%d %H:%M')}"
              f" (commit `{filas[-1]['commit'][:7]}`)", ""]

        con_req = [r for r in filas if entero(r["req_totales"])]
        L += ["## 2. Cobertura de requisitos", ""]
        if con_req:
            u = con_req[-1]
            L.append(f"Al cierre del mes, **{u['req_cubiertos']} de {u['req_totales']}** requisitos tienen al menos una "
                     "prueba ejecutada. El estado de cada uno está en `matriz_trazabilidad_actual.md`.")
        else:
            L.append("Las ejecuciones de este mes no registraron cobertura por requisito (se midió antes de existir el bot de trazabilidad).")
        L.append("")

        L += ["## 3. Todas las ejecuciones del mes", "",
              "| Fecha (Colombia) | Disparador | Commit | Resultado | Pasaron | Fallaron | Defectos conocidos | Tiendas reales | Enlace |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in filas:
            enlace = f"[run]({r['enlace_al_run']})" if r["enlace_al_run"] else "-"
            L.append(f"| {r['_local'].strftime('%Y-%m-%d %H:%M')} | {r['disparador']} | `{r['commit'][:7] or '-'}` | {r['resultado']} | "
                     f"{r['pasaron'] or '-'} | {r['fallaron'] or '-'} | {r['xfail'] or '-'} | {r['tiendas_reales']} | {enlace} |")
        L.append("")

        semanas = defaultdict(list)
        for r in filas:
            lunes = (r["_local"] - timedelta(days=r["_local"].weekday())).strftime("%Y-%m-%d")
            semanas[lunes].append(r)
        L += ["## 4. Tendencia por semana", "", "| Semana (lunes) | Ejecuciones | PASÓ | Otros resultados |", "|---|---|---|---|"]
        for lunes, rs in sorted(semanas.items()):
            ok = sum(1 for r in rs if r["resultado"] == "PASÓ")
            L.append(f"| {lunes} | {len(rs)} | {ok} | {len(rs) - ok} |")
        L.append("")

        defectos = sorted({d for r in filas for d in (r["defectos"] or "").split(",") if d})
        L += ["## 5. Defectos", "",
              f"Defectos que las pruebas siguieron detectando en el mes: **{', '.join(defectos) or 'ninguno'}**. "
              "El detalle de cada uno (severidad, pasos, estado) está en `docs/qa/defectos/`.", ""]

        manual = historial.parent / "manual" / "registro_manual.csv"
        L += ["## 6. Pruebas manuales", ""]
        hechas = []
        if manual.exists():
            with manual.open(encoding="utf-8", newline="") as f:
                hechas = [r for r in csv.DictReader(f) if str(r.get("fecha", "")).startswith(a.mes)]
        if hechas:
            L += ["| Fecha | Caso | Resultado | Captura |", "|---|---|---|---|"]
            L += [f"| {r.get('fecha')} | {r.get('caso')} | {r.get('resultado')} | {r.get('captura', '-')} |" for r in hechas]
        else:
            L.append("No hay pruebas manuales registradas en este mes (`manual/registro_manual.csv`).")
        L.append("")

        infra = [r for r in filas if r["resultado"] == "ERROR DE INFRAESTRUCTURA"]
        L += ["## 7. Observaciones del mes", ""]
        if infra:
            L.append(f"- {len(infra)} ejecución(es) terminaron por error de infraestructura (no por defectos de Picksy).")
        L += ["- Riesgos vigentes y acciones del mes siguiente: **completar por QA** antes de entregar.", ""]

    destino = Path(a.destino)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{a.mes}_informe.md"
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("Informe escrito en", ruta)


if __name__ == "__main__":
    main()
