"""
generar_word.py - Arma el INFORME DE PRUEBAS EN WORD de una ejecución del bot de QA.

Lee lo que el bot ya deja en qa_salida/ (resultados.json) y escribe, en esa misma carpeta:
    Informe_QA_<rama>_<AAAAMMDD-HHMM>_<commit>.docx

Qué trae el documento:
  1. Datos de la ejecución (fecha en hora de Colombia, rama, commit, versión, resultado general).
  2. Resumen con los conteos.
  3. Hallazgos: lo que falló, los defectos conocidos, los bloqueos por el ERS y los cambios del contrato.
  4. Estado de cada requisito (con los propuestos marcados).
  5. El detalle de TODOS los casos del bot, uno por fila.
  6. (opcional) Las pruebas de test_api.py, si existe qa_salida/junit_api.xml.

Uso:  python qa/generar_word.py --entrada qa_salida --requisitos qa/requisitos.yml [--otros-fallaron true]
Como el repositorio es PÚBLICO, todo texto pasa por el mismo filtro que registrar.py (oculta secretos).
Un fallo aquí NUNCA debe poner en rojo al proyecto: el flujo lo ejecuta con continue-on-error.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registrar import ocultar, resultado_global  # noqa: E402

VERDE, ROJO, AMBAR, GRIS, AZUL = "E2F0D9", "F8D7DA", "FFF2CC", "EDEDED", "DDEBF7"
VERDE_OSC = RGBColor(0x26, 0x3D, 0x2B)

ESTADOS = {  # estado de pytest -> (texto, color de fondo)
    "passed": ("Pasó", VERDE), "failed": ("Falló", ROJO), "skipped": ("Omitida", GRIS),
    "xfailed": ("Defecto conocido", AMBAR), "xpassed": ("Posiblemente corregido", AMBAR),
}
BLOQUES = [  # categoría del bot -> título del apartado de hallazgos
    ("ERROR DE INFRAESTRUCTURA", "Errores de infraestructura (base de datos o entorno; no son defectos de Picksy)"),
    ("FALLÓ UNA REGLA", "Fallos de una regla (posible defecto: QA confirma)"),
    ("CAMBIÓ EL CONTRATO", "Cambios en el contrato de la API (QA decide si son intencionales)"),
    ("POSIBLEMENTE CORREGIDO", "Defectos posiblemente corregidos (QA verifica y cierra)"),
    ("DEFECTO CONOCIDO", "Defectos conocidos que siguen abiertos"),
    ("BLOQUEADO", "Casos bloqueados por una ambigüedad del ERS"),
]


def t(valor, largo=None):
    """Texto seguro para el documento: sin secretos y con largo máximo."""
    texto = ocultar(str(valor if valor is not None else ""))
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", texto)      # caracteres que Word no admite
    return texto if largo is None or len(texto) <= largo else texto[: largo - 1] + "…"


def hora_colombia(utc_texto):
    try:
        return (datetime.strptime(utc_texto, "%Y-%m-%d %H:%M:%S") - timedelta(hours=5)).strftime("%d/%m/%Y %I:%M %p")
    except (TypeError, ValueError):
        return utc_texto or "-"


# ----------------------------------------------------------------------------- utilidades de Word
def sombrear(celda, color):
    tcPr = celda._tc.get_or_add_tcPr()
    for viejo in tcPr.findall(qn("w:shd")):
        tcPr.remove(viejo)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def escribir(celda, texto, negrita=False, tam=8, color=None, centrado=False):
    p = celda.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    if centrado:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(texto)
    r.font.size, r.bold = Pt(tam), negrita
    if color:
        r.font.color.rgb = color


def repetir_encabezado(fila):
    trPr = fila._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def no_partir_fila(fila):
    trPr = fila._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def tabla(doc, encabezados, anchos_cm, filas, colores=None, tam=8):
    """filas: lista de listas de texto. colores: {indice_de_columna: funcion(fila)->color o None}."""
    tb = doc.add_table(rows=1, cols=len(encabezados))
    tb.style = "Table Grid"
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    tb.autofit = False
    for i, (h, ancho) in enumerate(zip(encabezados, anchos_cm)):
        c = tb.rows[0].cells[i]
        c.width = Cm(ancho)
        sombrear(c, "263D2B")
        escribir(c, h, negrita=True, tam=tam, color=RGBColor(0xFF, 0xFF, 0xFF))
    repetir_encabezado(tb.rows[0])
    for col, ancho in zip(tb.columns, anchos_cm):      # el ancho también va en la rejilla de la tabla (si no, Word y
        col.width = Cm(ancho)                          # LibreOffice reparten las columnas por igual)
    for datos in filas:
        fila = tb.add_row()
        no_partir_fila(fila)
        for i, (valor, ancho) in enumerate(zip(datos, anchos_cm)):
            fila.cells[i].width = Cm(ancho)
            escribir(fila.cells[i], valor, tam=tam)
            if colores and i in colores:
                color = colores[i](datos)
                if color:
                    sombrear(fila.cells[i], color)
    return tb


def pie_con_numero(seccion, texto_izq):
    p = seccion.footer.paragraphs[0]
    p.text = ""
    r = p.add_run(texto_izq + "   ·   Página ")
    r.font.size = Pt(8)
    for tipo, contenido in (("begin", None), (None, "PAGE"), ("end", None)):
        run = p.add_run()
        run.font.size = Pt(8)
        if tipo:
            f = OxmlElement("w:fldChar")
            f.set(qn("w:fldCharType"), tipo)
            run._r.append(f)
        else:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = contenido
            run._r.append(it)


def titulo(doc, texto, nivel=1):
    h = doc.add_heading(texto, level=nivel)
    for r in h.runs:
        r.font.color.rgb = VERDE_OSC
        r.font.name = "Calibri"
    return h


def parrafo(doc, texto, negrita=False, tam=10):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.bold, r.font.size = negrita, Pt(tam)
    p.paragraph_format.space_after = Pt(4)
    return p


# ----------------------------------------------------------------------------- datos
def leer_requisitos(ruta):
    try:
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
        return {r["id"]: r for r in datos.get("requisitos", [])}
    except Exception:  # noqa: BLE001 - sin el YAML el informe sale igual, solo sin títulos
        return {}


def leer_junit(ruta):
    """Casos de test_api.py (u otra suite) desde un XML de pytest --junitxml."""
    if not ruta.exists():
        return []
    casos = []
    for tc in ET.parse(ruta).getroot().iter("testcase"):
        estado, motivo = "passed", ""
        for hijo in tc:
            if hijo.tag in ("failure", "error"):
                estado, motivo = "failed", (hijo.get("message") or "")
            elif hijo.tag == "skipped":
                estado = "xfailed" if "xfail" in (hijo.get("type") or "") else "skipped"
                motivo = hijo.get("message") or ""
        casos.append({"caso": f"{(tc.get('classname') or '').split('.')[-1]}::{tc.get('name')}", "estado": estado,
                      "duracion_s": round(float(tc.get("time") or 0), 3), "motivo": motivo})
    return casos


# ----------------------------------------------------------------------------- documento
def generar(entrada, requisitos, otros_fallaron=False, salida=None):
    entrada = Path(entrada)
    d = json.loads((entrada / "resultados.json").read_text(encoding="utf-8"))
    reqs = leer_requisitos(requisitos)
    casos = d.get("casos", [])
    api = leer_junit(entrada / "junit_api.xml")
    general = resultado_global(d, otros_fallaron or any(c["estado"] == "failed" for c in api))
    commit = str(d.get("commit", ""))[:7]

    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name, estilo.font.size = "Calibri", Pt(10)
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(27.94), Cm(21.59)            # carta horizontal
    for lado in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, lado, Cm(1.6))
    pie_con_numero(sec, f"Picksy · Informe de pruebas · {t(d.get('rama'))} · {commit}")

    # ---- portada
    p = doc.add_paragraph()
    r = p.add_run("Informe de pruebas automatizadas")
    r.font.size, r.bold, r.font.color.rgb = Pt(26), True, VERDE_OSC
    parrafo(doc, f"Picksy · versión {t(d.get('version_software'))} · rama {t(d.get('rama'))}", tam=13)
    parrafo(doc, f"Generado por el bot de QA el {hora_colombia(d.get('fecha_hora_utc'))}", tam=10)

    titulo(doc, "1. Datos de la ejecución")
    filas = [
        ["Resultado general", general],
        ["Fecha y hora", f"{hora_colombia(d.get('fecha_hora_utc'))}  ({t(d.get('fecha_hora_utc'))} UTC)"],
        ["Rama / commit", f"{t(d.get('rama'))} / {t(d.get('commit'))}"],
        ["Disparador", t(d.get("disparador"))],
        ["Versión del software", t(d.get("version_software"))],
        ["Tiendas reales", t(d.get("tiendas_reales"))],
        ["Duración del bot", f"{t(d.get('duracion_s'))} s"],
        ["Identificador de la ejecución", t(d.get("id_ejecucion"))],
        ["Enlace a la ejecución", t(d.get("enlace_al_run")) or "(ejecución local)"],
    ]
    color_general = {"PASÓ": VERDE, "FALLÓ": ROJO}.get(general, AMBAR)
    tb = tabla(doc, ["Dato", "Valor"], [6, 19.5], filas, tam=9)
    sombrear(tb.rows[1].cells[1], color_general)

    # ---- resumen
    titulo(doc, "2. Resumen")
    resumen = [
        ["Casos del bot", str(d.get("total", len(casos)))],
        ["Pasaron", str(d.get("pasaron", 0))],
        ["Fallaron", str(d.get("fallaron", 0))],
        ["Defectos conocidos (siguen abiertos)", str(d.get("xfail", 0))],
        ["Posiblemente corregidos (QA verifica y cierra)", str(d.get("xpass", 0))],
        ["Omitidas", str(d.get("omitidas", 0))],
        ["Requisitos con prueba ejecutada",
         f"{d.get('req_cubiertos', '-')} de {d.get('req_totales', '-')}"
         + (f"  (+{len(d['req_propuestos'])} propuestos, sin aprobar en el ERS)" if d.get("req_propuestos") else "")],
    ]
    if api:
        resumen.append(["Pruebas de test_api.py", f"{sum(c['estado'] == 'passed' for c in api)} pasaron de {len(api)}"
                        f" · {sum(c['estado'] == 'failed' for c in api)} fallaron"])
    tabla(doc, ["Concepto", "Cantidad"], [12, 13.5], resumen, tam=9)

    # ---- hallazgos
    titulo(doc, "3. Hallazgos")
    hubo = False
    for categoria, nombre in BLOQUES:
        lista = [c for c in casos if c.get("categoria") == categoria]
        if not lista:
            continue
        hubo = True
        titulo(doc, nombre, 2)
        tabla(doc, ["Caso", "Defecto", "Motivo"], [9, 2.5, 14],
              [[t(c["caso"]), t(c.get("defecto") or "-"), t(c.get("motivo"), 700)] for c in lista])
    fallos_api = [c for c in api if c["estado"] == "failed"]
    if fallos_api:
        hubo = True
        titulo(doc, "Fallos en test_api.py", 2)
        tabla(doc, ["Caso", "Motivo"], [9, 16.5], [[t(c["caso"]), t(c["motivo"], 700)] for c in fallos_api])
    if d.get("requisitos_sin_prueba"):
        hubo = True
        titulo(doc, "Requisitos sin prueba automática (revisión manual pendiente)", 2)
        parrafo(doc, ", ".join(t(x) for x in d["requisitos_sin_prueba"]))
    if not hubo:
        parrafo(doc, "Sin hallazgos: todas las pruebas ejecutadas pasaron.")

    # ---- requisitos
    titulo(doc, "4. Estado por requisito")
    por_req = {}
    for c in casos:
        for rid in c.get("requisitos", []):
            por_req[rid] = por_req.get(rid, 0) + 1
    filas = []
    for rid, etiqueta in d.get("requisitos", {}).items():
        r = reqs.get(rid, {})
        marca = "  [PROPUESTO]" if r.get("propuesto") else ""
        filas.append([rid, t(r.get("titulo", "-"), 160) + marca, t(r.get("prioridad", "-")), t(etiqueta, 200),
                      str(por_req.get(rid, 0))])

    def color_req(f):
        e = f[3]
        return (ROJO if "Defecto conocido" in e or "Falló" in e else AMBAR if ("Parcial" in e or "Posiblemente" in e
                or "Bloqueado" in e or "pendiente" in e) else VERDE if e.startswith("Verificado") else GRIS)
    tabla(doc, ["Requisito", "Título", "Prioridad", "Estado", "Casos"], [2, 11, 2, 9, 1.5], filas, {3: color_req})

    # ---- detalle de todos los casos
    titulo(doc, "5. Detalle de todos los casos del bot")
    parrafo(doc, f"{len(casos)} casos, en el orden en que se ejecutaron.", tam=9)
    filas = [[str(i), t(c["caso"]), ", ".join(c.get("requisitos", [])) or "-", ESTADOS.get(c["estado"], (c["estado"], None))[0],
              t(c.get("categoria")), str(c.get("duracion_s", ""))] for i, c in enumerate(casos, 1)]
    inverso = {v[0]: v[1] for v in ESTADOS.values()}
    tabla(doc, ["N.º", "Caso", "Requisitos", "Resultado", "Categoría", "Seg."], [1.2, 11.5, 3.3, 3.4, 4.6, 1.5], filas,
          {3: lambda f: inverso.get(f[3])}, tam=7.5)

    # ---- test_api.py
    if api:
        titulo(doc, "6. Pruebas de test_api.py")
        filas = [[str(i), t(c["caso"]), ESTADOS[c["estado"]][0], str(c["duracion_s"]), t(c["motivo"], 200)]
                 for i, c in enumerate(api, 1)]
        tabla(doc, ["N.º", "Caso", "Resultado", "Seg.", "Motivo"], [1.2, 10, 3.4, 1.5, 9.4], filas,
              {2: lambda f: inverso.get(f[2])}, tam=7.5)

    nombre = re.sub(r"[^A-Za-z0-9._-]+", "-", t(d.get("rama") or "local")).strip("-") or "local"
    marca = re.sub(r"[^0-9]", "", t(d.get("fecha_hora_utc")))
    marca = f"{marca[:8]}-{marca[8:12]}" if len(marca) >= 12 else "sin-fecha"
    destino = Path(salida) if salida else entrada / f"Informe_QA_{nombre}_{marca}_{commit or 'local'}.docx"
    doc.core_properties.title = "Informe de pruebas automatizadas de Picksy"
    doc.core_properties.author = "Bot de QA de Picksy"
    doc.save(destino)
    return destino


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True, help="carpeta qa_salida con resultados.json")
    ap.add_argument("--requisitos", default="qa/requisitos.yml")
    ap.add_argument("--otros-fallaron", default="false")
    ap.add_argument("--salida", default="", help="ruta del .docx (por defecto, dentro de la carpeta de entrada)")
    a = ap.parse_args()
    if not (Path(a.entrada) / "resultados.json").exists():
        print("No hay resultados.json: el bot no alcanzó a escribir resultados, no se genera el Word.")
        return
    ruta = generar(a.entrada, a.requisitos, a.otros_fallaron.lower() == "true", a.salida or None)
    print(f"Informe en Word generado: {ruta}")


if __name__ == "__main__":
    main()
