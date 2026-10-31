# Informe mensual de QA · Picksy · 2026-10

Elaborado por Ingeniería de QA. Generado automáticamente desde `historial_qa.csv`; las horas están en hora de Colombia (UTC-5).

## 1. Resumen ejecutivo

- Ejecuciones en el mes: **12** (4 manual_local, 6 push, 2 schedule)
- Resultado: **6 PASÓ** (50 %) · 6 FALLÓ
- Última ejecución: **FALLÓ** el 2026-10-31 11:01 (commit `63cc9f0`)

## 2. Cobertura de requisitos

Al cierre del mes, **1 de 25** requisitos tienen al menos una prueba ejecutada. El estado de cada uno está en `matriz_trazabilidad_actual.md`.

## 3. Todas las ejecuciones del mes

| Fecha (Colombia) | Disparador | Commit | Resultado | Pasaron | Fallaron | Defectos conocidos | Tiendas reales | Enlace |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 18:13 | manual_local | `-` | FALLÓ | 28 | 1 | 0 | sí | - |
| 2026-10-27 18:14 | manual_local | `-` | FALLÓ | 28 | 1 | 0 | sí | - |
| 2026-10-27 18:33 | manual_local | `-` | FALLÓ | 28 | 1 | 0 | sí | - |
| 2026-10-27 18:48 | push | `5288d04` | FALLÓ | - | - | - | sí | - |
| 2026-10-27 20:38 | push | `2f67f77` | PASÓ | - | - | - | sí | - |
| 2026-10-27 22:27 | push | `622d3b8` | PASÓ | - | - | - | sí | - |
| 2026-10-27 22:49 | manual_local | `-` | PASÓ | 28 | 0 | 1 | sí | - |
| 2026-10-27 22:51 | push | `79e1b45` | PASÓ | - | - | 1 | sí | - |
| 2026-10-29 20:33 | push | `7835c34` | PASÓ | 123 | 0 | 4 | no | [run](https://github.com/juanitoarciniegas-debug/Picksy/actions/runs/40986437957) |
| 2026-10-29 20:53 | push | `63cc9f0` | PASÓ | 124 | 0 | 4 | no | [run](https://github.com/juanitoarciniegas-debug/Picksy/actions/runs/40988418623) |
| 2026-10-30 11:59 | schedule | `63cc9f0` | FALLÓ | 8 | 1 | 0 | sí | [run](https://github.com/juanitoarciniegas-debug/Picksy/actions/runs/41094725067) |
| 2026-10-31 11:01 | schedule | `63cc9f0` | FALLÓ | 8 | 1 | 0 | sí | [run](https://github.com/juanitoarciniegas-debug/Picksy/actions/runs/41217492466) |

## 4. Tendencia por semana

| Semana (lunes) | Ejecuciones | PASÓ | Otros resultados |
|---|---|---|---|
| 2026-10-26 | 12 | 6 | 6 |

## 5. Defectos

Defectos que las pruebas siguieron detectando en el mes: **DEF-01, DEF-02, DEF-03, DEF-04, DEF-05**. El detalle de cada uno (severidad, pasos, estado) está en `docs/qa/defectos/`.

## 6. Pruebas manuales

No hay pruebas manuales registradas en este mes (`manual/registro_manual.csv`).

## 7. Observaciones del mes

- Riesgos vigentes y acciones del mes siguiente: **completar por QA** antes de entregar.

