# Contraste de la revisión independiente

Fecha: 2026-11-05. Revisor: Claude CLI 2.1.311, sólo Read/Grep/Glob. Duración: 457,6 segundos, 52 llamadas de lectura/búsqueda. Informe original: [claude-review.md](claude-review.md). Evidencia y resultados de reproducciones: [claude-review-verification.json](claude-review-verification.json).

La revisión no aprueba el cierre de captura automática e instalador. Claude clasificó 9 observaciones Important, 6 Minor y 3 hipótesis; no reportó Critical. No equivale a una auditoría completa ni demuestra ausencia de vulnerabilidades.

## Alcance y límites

El snapshot original contenía 128 archivos con hashes verificados contra el producto antes de archivar la revisión. Claude declaró haber leído sólo parte del producto: dejó fuera la UI, los scripts de despliegue y backup y buena parte de los tests del servidor. El filtro de preparación omitió `memory_platform/schema.sql`; se corrigió el filtro para futuras capturas, pero el revisor no examinó ese archivo. No se atribuye cobertura a esas áreas.

Las reproducciones posteriores usan carpetas temporales, credenciales sintéticas y dobles controlados. No conectan con los proyectos, PostgreSQL, proveedores o servicios reales. Demuestran mecanismos concretos; no sustituyen una ejecución dentro de OpenCode ni una medición de producción.

## Hallazgos importantes contrastados

| ID | Resultado | Evidencia y límites | Trabajo necesario |
|---|---|---|---|
| I-1 | Mecanismo reproducido | Cambiar `process.execPath` tras instalar hace que `loadInstallation` lance `installation_binding_conflict`. El plugin llama a esa función dentro de su propio runtime. Falta aceptación real de OpenCode; no se mantiene como demostrado el absoluto «siempre falla». | Separar el ejecutable Node registrado del runtime anfitrión y probar el adaptador sin inyectar `send`. |
| I-2 | Creación de trabajo reproducida | Con `embedding_enabled=True`, `_jobs` añade `embed` incluso con destinos de extracción vacíos. Compose activa esa opción. La sonda previa desactivaba embeddings y su contador de llamadas era un literal. No se llamó al proveedor en esta reproducción. | Decidir el tratamiento de eventos técnicos y medir con configuración equivalente a producción; corregir documentación y evidencia. |
| I-3 | Reproducido | Dos registros `complete` agotan una cola con `maxRecords=2`; checkpoint y reapertura no admiten un tercero. | Retención/compactación con una estrategia que conserve idempotencia y recuperación. No borrar entregas inciertas para liberar espacio. |
| I-4 | Reproducido | Un recibo con trabajo fallido sigue en `accepted` y se consulta en cada tick elegible. La latencia a miles de filas requiere benchmark. | Estado de fallo, espera por registro y operación explícita de recuperación. |
| I-5 | Reproducido | Tras instalar, añadir un hook ajeno después del grupo de Kairos provoca `configuration_drift`. | Validar presencia e integridad del grupo propio conservando el orden ajeno. |
| I-6 | Mecanismo SQL identificado; utilidad pendiente de medir | El cliente construye hasta 12 términos y el servidor utiliza `plainto_tsquery`; la consulta exige todos. No se ha medido el «casi nunca» del informe sobre un corpus representativo. | Evaluar recuperación con preguntas normales y ruido de eventos técnicos; no cambiar globalmente la búsqueda sin probar relevancia. |
| I-7 | Bloqueo del event loop reproducido | Un autenticador síncrono de 100 ms retrasa un temporizador independiente al menos 90 ms dentro del middleware. La latencia/capacidad de PostgreSQL real y la necesidad/tamaño de un pool se deben medir. | Sacar el trabajo bloqueante del bucle y verificar concurrencia sin alterar la autorización. |
| I-8 | Guardia de versión reproducida | Un manifiesto de versión anterior simulado falla antes de que `--replace` pueda migrarlo. No se supone que exista ya un paquete futuro. | Migración explícita entre versiones y regresión con dos distribuciones. |
| I-9 | Reproducido en cliente y servidor | Valores sintéticos asignados a `DB_PASSWORD`, `AWS_SECRET_ACCESS_KEY` y `GITHUB_TOKEN` sobreviven al saneamiento de texto. No se inspeccionaron credenciales reales ni se demuestra una exposición previa. | Cubrir asignaciones prefijadas y formatos habituales; probar antes de ampliar captura. |

Las ocho reproducciones importantes corresponden a I-1, I-2, I-3, I-4, I-5, I-7, I-8 e I-9. I-9 tiene una comprobación por cada lado. La clasificación del revisor no se convierte automáticamente en una medición del impacto real.

## Hipótesis y observaciones pendientes

S-1 requiere verificar los contratos de hooks contra las versiones reales de los clientes; el conocimiento de memoria del revisor sobre `args`, `commandWindows` o `async` no basta para declararlos inválidos. S-2 requiere carga representativa de búsqueda semántica. S-3 requiere una prueba concurrente de recuperación de lock obsoleto. Las seis observaciones Minor, incluido el techo de captura del servidor, se conservan para evaluación explícita; no se descartan por su etiqueta.

## Reproducción

Desde la raíz de Kairos:

```powershell
node docs/roadmap/2026-11-05-automatic-memory/testing/review-triage.mjs
python docs/roadmap/2026-11-05-automatic-memory/testing/review-triage.py
```

No son correcciones ni sustituyen la suite original. Se han reabierto las tareas afectadas. La activación del servidor y la conservación de documentos siguen verificadas; se retira la afirmación general de que los eventos técnicos no generan llamadas al proveedor. No se han cambiado código de ejecución, servicios, datos, credenciales, modelos ni políticas durante esta revisión.

Orden recomendado: I-9 y consentimiento; I-1/I-5/I-8; I-2 con evidencia equivalente a producción; I-3/I-4; I-6/I-7 y mediciones. Después, revisión independiente del parche y aceptación real de clientes.
