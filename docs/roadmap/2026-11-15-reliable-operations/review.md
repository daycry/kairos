# Revisiones de reliable-operations

Cada fase cierra con su revisión adversarial. El detalle de cada intento está en `tasks.md`, en las secciones «Revisión de dos lentes».

## Fase 1 — Arnés de fallos y tests de límites (T-01 a T-06)

- **Fecha**: 2026-11-15
- **Lentes**: intento 1, A, B, C y D (C por `.github/workflows/ci.yml`; D por los tests de migración); intento 2, A y B.
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**: suite del servidor 806 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 806; `scope-check.py --base be001a4` exit 0; cada corrección con su mutante en rojo (Notas de T-02 y T-03).

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Los tests de bloqueo de las secciones FTS y de fragmentos miraban índices y no tablas, y `memory.embeddings` salió del conjunto vigilado | Corregido: cada sección se ejecuta sola sobre una base migrada y se leen los bloqueos de todas las tablas |
| 1 | Important | El test de registro de versiones no ejecutaba los INSERT de las versiones 8 a 11 | Corregido: test estático de `ON CONFLICT … DO NOTHING` y test dinámico que re-migra |
| 1 | Important | El test del cuerpo troceado entregaba un solo evento | Corregido: `BodyLimit` recibe eventos `http.request` reales |
| 1 | Minor | Aserción tautológica en el test de hilos del proxy; docstring de `expire_lease`; `test_job_leases` dependía de la cola compartida; Verificación sin pegar | Corregidos |
| 2 | Minor | Changelog de T-05 con 801; docstring de `asgi()` | Corregidos en el cierre |
| 2 | Minor | La guarda en Python de los índices HNSW queda sin cubrir; las etiquetas de sección van a mano | Deuda aceptada para T-14 (Fase 3) |

## Fase 2 — Worker resistente a la caída de base (T-07 a T-13)

- **Fecha**: 2026-11-15
- **Lentes**: intento 1, A, B, C y D (C por `.github/workflows/ci.yml`; D por `worker.py`); intentos 2 y 3, A y B.
- **Veredicto**: cerrada en el intento 3 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**: suite del servidor 884 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 884; `scope-check.py --base 920c1f0` exit 0; mutantes en rojo en las Notas (archivadas en `execution-history.md`).
- **Decisión del orquestador (intento 2)**: no se reviven concesiones vencidas; se declara el límite (una caída más larga que lo que queda de concesión puede costar el intento) en la spec, el manual y CA-09.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Una caída de base al completar gastaba el intento y podía perder el resultado | Corregido: reintento in situ de la escritura con renovación de la concesión |
| 1 | Minor | Clasificación demasiado amplia de errores como caída; validación de `MEMORY_MAX_ATTEMPTS`; `complete_job` `False`; reclamo por conjunto; documentación y coordinación | Corregidos |
| 1 | Minor | Base muda en `read` y sin `connect_timeout` | Diferidos a T-23 y T-25 |
| 2 | Important | El reintento in situ no tenía tope si la renovación funcionaba | Corregido: presupuesto `MEMORY_WORKER_WRITE_RETRY_SECONDS` y 5 escrituras |
| 2 | Important | Caída más larga que la concesión en el último intento | Límite declarado y fijado con una prueba |
| 2 | Minor | Transitorios que la base contesta; COMMIT con confirmación perdida; spec y coordinación | Corregidos |
| 3 | Minor | Precisión del umbral del límite; `job_outcome_unread` en la coordinación | Corregidos en el cierre |
| 3 | Minor | Observabilidad si el latido gana la carrera; prueba de `job_outcome_unread`; rango del defecto del presupuesto | Deuda aceptada para T-25 (Fase 4) |
