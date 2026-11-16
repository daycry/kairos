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

## Fase 3 — Cola: índices parciales y retención de tablas (T-14 a T-20)

- **Fecha**: 2026-11-16
- **Lentes**: intento 1, A, B, C y D (C por el SQL con f-string de `admin.py` y `ci.yml`; D por `schema.sql` y `store_jobs.py`); intento 2, A y B.
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**: suite del servidor 925 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 925; `scope-check.py --base d23f4a7` exit 0; prueba de invariancia del contrato MCP antes y después de podar; mutantes en rojo en las Notas.
- **Decisión del orquestador (intento 1)**: la poda conserva el contrato de las herramientas MCP; no borra trabajos citados por un evento conservado ni de la versión vigente.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Podar trabajos `failed` cambiaba `event_status`, el reenvío de `ingest_event`, `document_status` y `backfill-chunks` | Corregido: exclusiones (a) eventos conservados, (b) versión vigente, (c) recibo; prueba de invariancia |
| 1 | Minor | Coordinación; promesa falsa del bloqueo de la migración; rastro de la poda; cursor; VACUUM/WAL | Corregidos (guarda `jobqueue`, fila `retention_prune`, cursor keyset, manual) |
| 1 | Minor | Un reclamo concurrente puede esperar un ciclo por el trabajo que perdió la comparación | Deuda aceptada, documentada |
| 2 | Minor | Textos de `configuration.md`, coordinación (`counts.jobs`), spec P-03, dry-run y `--table` | Corregidos en el cierre |
| 2 | Minor | Invariancia sin `publish_document`/`revoke_document`/portal; NOT EXISTS sobre `events` sin índice | Deuda aceptada |

## Fase 4 — Pool y plazos de conexión (T-21 a T-29)

- **Fecha**: 2026-11-16
- **Lentes**: intento 1, A, B, C y D (C por `ci.yml`; D por `worker.py`); intento 2, A y B.
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**: suite del servidor 1006 tests, 0 fallos, errores y omitidos; suite de kairos-mcp en verde; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1006; `scope-check.py --base 9416128` exit 0; contrato MCP sin cambios; mutantes en rojo en las Notas (`execution-history.md`).

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Una conexión establecida que se queda muda (half-open) se colgaba ~15 min y reabría la deuda de la Fase 2 | Corregido: keepalives y `tcp_user_timeout`, plazo del cliente en `Connection.wait`, `FaultProxy.freeze()` y 14 pruebas |
| 1 | Minor | Métrica con `_landed`; carrera busy/caída; búsqueda saturada `partial`; readiness; texto de sesión; S-08; casilla de T-24; mediciones; validación del lease; `graph_data` | Corregidos |
| 2 | Minor | Changelog desactualizados y frase de `PREPARE` | Corregidos en el cierre |
| 2 | Minor | Plazo total en `executemany`; carrera de `saturated()`; clasificación con varias direcciones; `StoreUnavailable` en una capa; mutantes sin anotar | Deuda → T-30 (Fase 5) |

## Fase 5 — Permisos por transacción (T-30 a T-34)

- **Fecha**: 2026-11-16
- **Lentes**: intento 1, A, B, C y D (C por `auth.py`, `auth_scope.py`, `store_auth.py` y `ci.yml`); intento 2, A, B y C.
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important. El intento 1 no tuvo ninguno; se corrigieron sus Minor (uno de seguridad) y se relanzó la revisión.
- **Evidencia**: suite del servidor 1054 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1054; `scope-check.py --base 04822a0` exit 0; contrato MCP sin cambios; consultas por búsqueda 63 → 49 con pool (14 son del propio pool); pruebas de carrera con dos conexiones (`test_auth_race.py`); mutantes en rojo en las Notas.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Minor (seguridad, CWE-367) | Comprobar-esperar-comprobar respondía desde la caché tras esperar un bloqueo | Corregido: la caché se vacía tras cada espera y se relee el permiso; 8 pruebas de carrera |
| 1 | Minor | Pruebas estáticas poco estrictas; prueba de savepoints vacua; rutas con bearer; texto «misma instantánea»; clasificación del pool; evidencia | Corregidos |
| 1 | Minor | `gather` no cancela las capas hermanas tras un 503 | Deuda aceptada |
| 2 | Minor | Ingesta sin re-exigir `write`; readiness sin conexión previa; `_faults_at_ok` sin lock; tabla de respuestas, coordinación y Changelog | Corregidos en el cierre (886388a) |
| 2 | Minor | Falsos negativos del recorrido estático; hilo suelto en `test_auth_race` al fallar | Deuda aceptada → Iniciativa 9 |

## Fase 6 — Copias locales: integridad, cifrado, retención y verificación (T-35 a T-43)

- **Fecha**: 2026-11-16
- **Lentes**: intento 1, A, B, C y D (C por `ci.yml`, `Dockerfile`, copias cifradas y `deploy-memory.py`; D por `backup.py`); intento 2, A, B, C y D; intento 3, A, B y D.
- **Veredicto**: cerrada en el intento 3 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**: suite del servidor 1154 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1154; `scope-check.py --base 99079d8` exit 0; contrato MCP sin cambios; ensayo aislado `kairos-ops-a` repetido tras los fixes (`verified` antes de `migrate`, aborto con manifiesto alterado, `knowledge-graphs-*` idéntico); mutantes en rojo en las Notas.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important (seguridad, CWE-312/459) | Un SIGTERM durante el cifrado dejaba el volcado completo en claro en el volumen de copias | Corregido: `pg_dump` → `age` por tubería, manejador en todo `create_backup`, `init: true`, barrido de parciales |
| 1 | Important | Las huellas cargaban cada tabla entera en RAM en cada copia y despliegue | Corregido en fix1 (tramos) y de nuevo en fix2 (una pasada, suma de sha256 por fila) |
| 1 | Important | `content_sha256` nunca se comparaba: una copia cifrada descifrada no se podía verificar | Corregido: `verify-backup --manifest`, `restore-check --from-manifest <m>` |
| 1 | Minor | Coordinación con la Iniciativa 7, nombre del efímero, `trust`, `fsync`, carreras de `prune`, códigos estables, `maintenance_work_mem`, rehash en `prune` | Corregidos (el rehash de `restore-check` quedó rebatido) |
| 2 | Important | Huellas por tramos de coste cuadrático | Corregido en fix2 (una lectura por tabla) |
| 2 | Important | El barrido podía borrar el parcial de una copia viva | Corregido: cerrojo `flock` durante toda la copia |
| 2 | Important | Sin ensayo real tras cambiar el arranque del efímero | Corregido: ensayo T-40 repetido |
| 2 | Minor | Changelog, recuento pegado, `ci.yml`, `stat()` en `prune`, fallo de `age` frente a EPIPE, nombre ≤ 63 | Corregidos en fix2 |
| 3 | Minor | Changelog de T-36 incompleto | Corregido en el cierre |
| 3 | Minor | Resto de la carrera de dos `--prune`; coste por fila de las huellas en Python | Deuda → T-46 y T-50 |
