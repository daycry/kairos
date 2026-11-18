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

## Fase 7 — Copia externa programada y runbook de restauración (T-44 a T-49)

- **Fecha**: 2026-11-16
- **Lentes**: intento 1, A, B y C (C por `ci.yml`, `docker-compose.yml`, `Dockerfile`, credenciales de `rclone` y clave del ensayo); intento 2, A, B, C y D (D por un `sleep` acotado del ensayo).
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**: suite del servidor 1195 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1195; `scope-check.py --base eaff0d1` exit 0; contrato MCP sin cambios; ensayo aislado `kairos-ops-b` repetido tras fix1 (`restored_and_content_verified` en un PostgreSQL efímero nuevo, `knowledge-graphs-*` idéntico, `kairos-ops` sin restos); mutantes en rojo en las Notas.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Critical (seguridad, CWE-311) | `upload` subía al destino externo copias en claro, como la `kairos-before-*` de cada despliegue | Corregido: solo salen copias con manifiesto `encrypted` y cabecera age; `backup-cycle` no arranca con destino y sin destinatarios (`backup_encryption_required`) |
| 1 | Important | La métrica de la copia externa seguía en 1 si el ciclo fallaba antes de la etapa externa | Corregido: cualquier fallo del ciclo escribe 0 y `backup_cycle_failed` |
| 1 | Minor | Coordinación, ensayo en el mismo clúster, permisos de `rclone.conf`, limpieza de la clave, retención remota, manifiesto remoto truncado, `cleanup()`, carrera de `--prune` | Corregidos en fix1 |
| 1 | Minor | Red `egress` con destino `dir:`; JSON de usage-meter en T-48 | Deuda → Fase 9; deuda aceptada |
| 2 | Minor | Métrica en la validación de arranque, evento en la retención local, resto de la carrera de `--prune`, ventana comprobar-subir (CWE-367), «sin red» en el runbook | Deuda → T-50 |

## Hito A — revisión del diff completo (T-51, criterio 3)

- **Fecha**: 2026-11-17
- **Lentes**: intento 1, una lente del hito sobre `main...HEAD` (80 ficheros: interacciones entre fases, código nuevo de la Fase 8, coherencia de CHANGELOG, docs, Coordinación, contrato MCP y migraciones) y una Lente C sobre el código de la Fase 8 (`12bef4d`, `de36248`); intento 2, lentes B+C sobre el fix1 (`3d54967..ca0d3ca`). Ninguna había revisado las fases.
- **Veredicto**: sin hallazgos Critical ni Important abiertos. Contrato MCP sin cambios; migraciones solo aditivas; `statement_timeout` no alcanza a `pg_dump`, huellas, `restore-check` ni `prune-tables`; huellas y volcado salen de una sola instantánea.
- **Evidencia**: suite MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 1203}; `scope-check.py --base main` exit 0; ensayo del hito A `kairos-ops-c` (`restored_and_content_verified`, `worker_survived_db_restart` con 256 pendientes, 0 reinicios, 0 `failed`, `knowledge-graphs-*` idéntico).

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important → Minor (arbitrado) | «Cifrada» se decide por la cabecera age y el manifiesto: quien escribe en `memory-backups` puede fabricar cabecera + volcado en claro con un manifiesto falsificado (CWE-345) | Deuda declarada: solo escriben en ese volumen servicios que ya tienen las credenciales de la base (sacarían los datos directamente); `operations.md` ya declara que el manifiesto detecta corrupción, no manipulación, y que la autenticidad depende del cifrado y de proteger el volumen; sin la clave privada no hay forma de detectarlo en el servidor |
| 1 | Minor | Manifiesto subido con campos libres (CWE-200); reescritura del mismo inodo tras comprobar (CWE-367) | Mismo atacante y misma declaración; la copia mala tras un desajuste se borra del destino desde el fix1 |
| 1 | Minor | Métrica en 1 ante `Settings.from_env()` o `MEMORY_RETENTION_*` inválidos y ante un fallo de la retención local; CHANGELOG con promesas que el código no cumple (métrica, `MEMORY_CONNECT_TIMEOUT`) | Corregidos en el fix1 |
| 1 | Minor | `backup-cycle --loop` sin `connect_timeout` ni keepalives (F4×F7) | Corregido: `guarded_dsn` en admin, `pg_dump`/`pg_restore` y `restore-check`, sin `statement_timeout` |
| 1 | Minor | `rclone rcat` anulaba `--retries` | Corregido: `copyto --copy-links /proc/self/fd/<n>` desde el descriptor verificado |
| 1 | Minor | El ensayo no exigía trabajos pendientes con la base parada; detalles de `configuration.md` y Coordinación | Corregidos |
| 2 | Minor | Mensaje «nothing was deleted» tras borrar la copia mala; `copyto` sin `--ignore-times` no reemplaza un manifiesto remoto dañado del mismo tamaño y fecha | Corregidos por el orquestador |

## Fase 9 — Compose: límites, healthchecks, rotación y `extra_hosts` (T-54 a T-60)

- **Fecha**: 2026-11-17
- **Lentes**: intento 1, A, B, C y D (C por `docker-compose.yml`, el override de rclone, `Dockerfile` y `ci.yml`; D por `worker.py`); intento 2, A, B, C y D; intento 3, A, B y C; intento 4 (ciclo 2, con la delegación del usuario), A y C.
- **Veredicto**: cerrada en el intento 4 sin hallazgos Critical ni Important abiertos. T-56 sigue en curso hasta que T-64 ejercite el `unhealthy` real.
- **Evidencia**: suite del servidor 1241 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1241; `scope-check.py --base main` exit 0; contrato MCP, `ollama-proxy/default.conf.template` y `web/nginx.conf` sin cambios; simulación del bucle real del worker con 135 combinaciones de concesión, espera y latencia sin sondas fallidas (Lente B, intento 3).

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Umbral fijo de 180 s del healthcheck frente al latido por renovación (falso `unhealthy` con concesión larga; cota de CA-21 incumplible) | Corregido: el latido escribe su propio plazo; CA-21 y T-64 enmendados a «plazo del último latido + interval × retries» |
| 1 | Important | `cpus` por defecto por encima de las vCPU de un VPS pequeño (Docker no crea el contenedor) | Corregido: `cpus` 0 por defecto (sin cuota); cuotas explícitas en la columna VPS |
| 1 | Important (seguridad, CWE-306) | La guía de Linux pedía `OLLAMA_HOST=0.0.0.0` | Corregido en tres pasos (intentos 1-3): pasarela IPv4 de `docker0` + reglas `INPUT` solo para la subred de `egress`; sin comodín por IPv6 |
| 1 | Important | Tope de `memory-api` sin dimensionar para su respuesta máxima | Corregido: `2g` por defecto y `1g` en VPS, con la cuenta medida |
| 1 | Minor | Arranque como acceso correcto, escaneo de claves, CPU de `memory-mcp` en VPS, `README` fuera de alcance, `compose config` sin pegar | Corregidos |
| 2 | Important | Hueco de latido entre el reclamo y la primera renovación | Corregido en fix2, con prueba del bucle real (RED de comportamiento) |
| 2 | Important | La guía de Linux con la pasarela de `egress` no restringía el acceso y rompía el proxy | Corregido en fix2 |
| 2 | Minor | Reintento de la renovación, cuenta de memoria, suma de la columna VPS, Notas de T-56 | Corregidos |
| 3 | Important (seguridad, CWE-306) | La alternativa `0.0.0.0` abría `[::]:11434`, fuera de las reglas IPv4 | Corregido en fix3 (ciclo 2) |
| 3 | Minor | Trabajo con la concesión perdida sin latido; dos mutantes vivos del latido | Deuda → T-64 |
| 4 | Minor | Volver a aplicar la regla por IP de `ollama` tras recrearlo | Corregido en el cierre |

## Fase 10 — Despliegue: bloqueo, etiquetado y retroceso (T-61 a T-67)

- **Fecha**: 2026-11-17
- **Lentes**: intento 1, A, B, C y D (C añadida por el orquestador: bloqueo con PID y etiquetas leídas de un JSON que acaban en `docker`; D por `worker.py`); intentos 2 a 5, B y A+C en un solo revisor. Ciclo 2 desde el intento 4, con la delegación del usuario.
- **Veredicto**: cerrada en el intento 5 sin hallazgos Critical ni Important abiertos; los Minor del cierre, corregidos en fix5.
- **Evidencia**: suite del servidor 1360 tests, 0 fallos, errores y omitidos (tras convertir en portable la única prueba solo de Windows); `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1360; scripts del anfitrión 181 OK; `scope-check.py --base main` exit 0; contrato MCP, `ollama-proxy/default.conf.template` y `web/nginx.conf` sin cambios; ensayo aislado `kairos-ops-d` etapa `rollback` con salida 0, `unhealthy` 78,2 s tras el plazo del último latido y listados de `knowledge-graphs-*` idénticos; exploraciones aleatorias de la Lente B con el doble de Docker (600 secuencias de 8 pasos con registro y 600 sin él, con fallos, `kill` y Ctrl-C en cada fase) sin problemas al cierre.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Se etiquetaba `:latest` y no la imagen en servicio: tras un fallo y un reintento, `--rollback` iba a una versión nunca servida | Corregido en fix1 y, por clase, en fix2 |
| 1 | Minor | Etiquetas de `images.previous` sin validar, carrera de `--break-lock`, reutilización de PID, margen de 10 s del ensayo, ítem (19), catálogo de eventos, versión de la etiqueta | Corregidos en fix1 (destino desconocido del worker: rebatido) |
| 2 | Important | `already_at_previous` comparaba con `:latest`; un fallo en `start`/`verify` y su reintento etiquetaban la versión fallida como anterior | Corregidos en fix2: «anterior» = último despliegue bueno (`images.good`) |
| 2 | Minor | Ventana del bloqueo por renombrado, Windows, JSON no objeto, gramática de tags, veredicto del ensayo, `.broken` huérfano | Corregidos en fix2: bloqueo del sistema operativo; cota del ensayo con `State.Health.Log` |
| 3 | Important | `:latest` desfasado tras `already_at_previous`; despliegue interrumpido sin registro de etiquetas | Corregidos en fix3 (ciclo 2): retroceso completo = contenedores y `:latest`; `in_progress` duradero |
| 3 | Minor | Ventanas del bloqueo, `O_NOFOLLOW`, ids `sha256:`, `TAG_MARK`, aviso de despliegue interrumpido, CA-21 como enmienda | Corregidos en fix3 |
| 4 | Important | Instalación sin `images.good`: una interrupción temprana perdía la referencia a la versión buena | Corregido en fix4 (registro desde los contenedores antes de `configuration`) |
| 4 | Minor | Señales en los manejadores, `migrate` huérfano, mensajes de otro equipo, notas de `--break-lock`, escapes de terminal, enlace duro | Corregidos en fix4 |
| 5 | Minor | `good` parcial sin contenedores, dos ventanas de señales, manual e ítem (19) en `engine`, `status` sin escapar | Corregidos en fix5 |

## Fase 11 — Sonda de ida y vuelta (T-68 a T-73)

- **Fecha**: 2026-11-18
- **Lentes**: intentos 1 y 2, A, B y C+D en un solo revisor (C por la clave de la sonda y `test_auth_cache.py`; D por el `sleep` de la sonda y la purga).
- **Veredicto**: cerrada en el intento 2 sin hallazgos Critical ni Important; los 7 Minor del intento 2, corregidos en fix2.
- **Evidencia**: suite del servidor 1460 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1460; `scope-check.py --base main` exit 0 sin criterios alterados; contrato MCP, `schema.sql`, `ollama-proxy/default.conf.template` y `web/nginx.conf` sin cambios; purga comprobada en PostgreSQL aislado (filas de la sonda a 0, cada sentencia por índice que empieza por `project_id`).

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Falso verde: cualquier nota activa de `kairos-probe` satisfacía la búsqueda semántica y nada barría los restos | Corregido en fix1: éxito solo con la nota de esta ejecución por la vía semántica, búsqueda de control y barrido inicial |
| 1 | Important | `valid_key` reutilizaba la clave con el dueño deshabilitado (comprobación duplicada a mano) | Corregido en fix1: misma vía que la API |
| 1 | Important | Notas retiradas con vector sin podar (~8 GB/año) | Corregido en fix1: purga de filas solo de `kairos-probe` |
| 1 | Minor | Interrupción sin limpieza, `.prom` silencioso, aprovisionamientos concurrentes, proyecto ajeno adoptado, auditoría al primer administrador, nombre de la métrica, criterio sin enmienda, retirada fuera del presupuesto, usage-meter | Corregidos en fix1 (usage-meter, por el orquestador) |
| 2 | Minor | Purga sin comprobar el dueño, rotación de la clave de un humano, auditoría del aprovisionamiento y `--as`, purga sin tope, interrupción con la escritura en vuelo, `last_success` que retrocede, `.lock` en solo lectura | Corregidos en fix2 |

## Fase 12 — Cola atascada, servicio de sonda y `kairos doctor` (T-74 a T-80)

- **Fecha**: 2026-11-18
- **Lentes**: intento 1, A, B y C+D en un solo revisor (C por `docker-compose.yml`, `Dockerfile` y `ci.yml`; D por la consulta de la cola).
- **Veredicto**: cerrada en el intento 1 sin hallazgos Critical ni Important; los 7 Minor, corregidos en fix1.
- **Evidencia**: suite del servidor 1494 tests, 0 fallos, errores y omitidos; `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1494; `scripts/tests` 186 OK; cliente 100/100; `scope-check.py --base main` exit 0; contrato MCP, `schema.sql`, migraciones, `ollama-proxy/default.conf.template` y `web/nginx.conf` sin cambios; `LIVE_QUEUE_SQL` con `Index Scan using memory_job_queue` (0,37 ms con 500 000 filas) y valores comprobados en PostgreSQL; ensayo aislado `kairos-ops-e` (sonda sana, worker parado detectado en `index` con `queue_stuck`, recuperación) con listados de `knowledge-graphs-*` idénticos.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Minor | SIGTERM tras una ida y vuelta correcta o durante la espera del bucle; healthcheck sin el plazo de la sonda y tapado por una ejecución manual; `doctor` frente al checkpoint de la cola; `memory-probe` con todo el volumen de copias en escritura; consulta de la cola sin prueba en PostgreSQL; `memory-probe` no recreado tras un despliegue; periodo del bucle en el manual | Corregidos en fix1 (`memory_dsn` se mantiene: el repo tiene un solo rol de base, motivo en el manual) |
