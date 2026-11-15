"""Pruebas del propio bot: que el informe en Word se genere bien (no llevan marcador de requisito)."""
import json
import zipfile
from pathlib import Path

from docx import Document

import generar_word

REQUISITOS_YML = Path(__file__).resolve().parent / "requisitos.yml"


def _resultados(tmp_path, casos, **extra):
    d = {"fecha_hora_utc": "2026-11-10 01:19:22", "id_ejecucion": "1-1", "disparador": "push", "commit": "abcdef1234567",
         "rama": "version-4", "version_software": "v4", "tiendas_reales": "no", "duracion_s": 10.5, "enlace_al_run": "",
         "total": len(casos), "pasaron": 1, "fallaron": 0, "omitidas": 0, "xfail": 0, "xpass": 0, "req_cubiertos": 1,
         "req_totales": 25, "req_propuestos": [], "requisitos": {"RF-01": "Verificado (automático)"},
         "requisitos_sin_prueba": [], "casos": casos}
    d.update(extra)
    (tmp_path / "resultados.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _texto(ruta):
    doc = Document(ruta)
    partes = [p.text for p in doc.paragraphs]
    for tabla in doc.tables:
        partes += [c.text for fila in tabla.rows for c in fila.cells]
    return "\n".join(partes)


def test_el_informe_word_trae_todos_los_casos_y_se_abre(tmp_path):
    casos = [{"caso": f"test_x.py::test_caso_{i}", "categoria": "PASÓ", "requisitos": ["RF-01"], "estado": "passed",
              "duracion_s": 0.1, "motivo": "", "defecto": ""} for i in range(50)]
    _resultados(tmp_path, casos, total=50, pasaron=50)
    ruta = generar_word.generar(tmp_path, REQUISITOS_YML)
    assert ruta.exists() and ruta.suffix == ".docx" and ruta.name.startswith("Informe_QA_version-4_20261110-0119_abcdef1")
    assert zipfile.is_zipfile(ruta)
    texto = _texto(ruta)
    assert all(f"test_caso_{i}" in texto for i in range(50)), "Falta algún caso en el detalle"
    assert "Informe de pruebas automatizadas" in texto and "RF-01" in texto and "PASÓ" in texto


def test_el_informe_word_muestra_los_hallazgos_y_el_resultado_general(tmp_path):
    casos = [
        {"caso": "test_a.py::test_roto", "categoria": "FALLÓ UNA REGLA", "requisitos": ["RF-01"], "estado": "failed",
         "duracion_s": 1, "motivo": "esperaba 200 y llegó 500", "defecto": ""},
        {"caso": "test_b.py::test_conocido", "categoria": "DEFECTO CONOCIDO", "requisitos": [], "estado": "xfailed",
         "duracion_s": 1, "motivo": "DEF-02 falta una tienda", "defecto": "DEF-02"},
    ]
    _resultados(tmp_path, casos, fallaron=1, xfail=1, pasaron=0)
    texto = _texto(generar_word.generar(tmp_path, REQUISITOS_YML))
    assert "FALLÓ" in texto and "esperaba 200 y llegó 500" in texto and "DEF-02" in texto


def test_el_informe_word_incluye_test_api_si_existe_el_junit(tmp_path):
    _resultados(tmp_path, [])
    (tmp_path / "junit_api.xml").write_text(
        '<testsuites><testsuite><testcase classname="test_api" name="test_login" time="0.2"/>'
        '<testcase classname="test_api" name="test_roto" time="0.1"><failure message="assert 1 == 2"/></testcase>'
        "</testsuite></testsuites>", encoding="utf-8")
    texto = _texto(generar_word.generar(tmp_path, REQUISITOS_YML))
    assert "test_api::test_login" in texto and "assert 1 == 2" in texto


def test_el_informe_word_oculta_los_secretos_del_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_PASSWORD", "clave-super-secreta")
    caso = {"caso": "test_s.py::test_s", "categoria": "FALLÓ UNA REGLA", "requisitos": [], "estado": "failed",
            "duracion_s": 1, "motivo": "el error trae clave-super-secreta dentro", "defecto": ""}
    _resultados(tmp_path, [caso], fallaron=1)
    assert "clave-super-secreta" not in _texto(generar_word.generar(tmp_path, REQUISITOS_YML))


def test_el_informe_word_sale_aunque_falte_requisitos_yml(tmp_path):
    _resultados(tmp_path, [])
    assert generar_word.generar(tmp_path, tmp_path / "no_existe.yml").exists()
