# Registro de QA de Picksy

Esta carpeta vive en la rama **qa-registros** (no en main). La escribe el bot; no se edita a mano, salvo `manual/` y `defectos/`.

| Ruta | Contenido |
|---|---|
| `historial_qa.csv` | Una fila por ejecución (fuente del informe mensual) |
| `ejecuciones/AAAA-MM/` | Detalle caso por caso de cada ejecución |
| `evidencias/AAAA-MM/` | Reportes HTML y capturas |
| `matriz_trazabilidad_actual.md` | Estado de cada requisito en la última ejecución |
| `manual/registro_manual.csv` | Pruebas manuales (fecha, caso, resultado, captura) |
| `defectos/` | Un archivo por defecto |
| `hallazgos/` | Hallazgos puntuales de revisión |
| `informes/` | Informe mensual |

Reglas: sin datos personales reales ni contraseñas (el repositorio es público). Horas del historial en UTC; los informes las muestran en hora de Colombia.
