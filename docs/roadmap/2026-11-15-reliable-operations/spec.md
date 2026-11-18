---
spec: reliable-operations
descripcion: Operación fiable de Kairos — copias verificadas, cifradas y externas con runbook de restauración, worker resistente a caídas de base, pool y plazos de conexión, despliegue con límites, healthchecks, bloqueo y retroceso, abstención calibrada, sonda de ida y vuelta y tests de fallos.
estado: aprobada      # borrador | aprobada | implementada | obsoleta
creado: 2026-11-15
actualizado: 2026-11-15
evaluacion: evaluation.md
design: n/a
plan: improvement-plan.md
generacion:
  inicio: 2026-11-15T14:42:54Z
  fin: 2026-11-15T14:55:57Z
  fuente: estimado        # producida dentro de la ventana medida de evaluation.md (sin marcador propio); su coste está incluido en el bloque generacion de evaluation.md
  tokens_reales: { entrada: 0, salida: 0, cache_creacion: 0, cache_lectura: 0 }
  eur: null
  horas_ia: 0.00
  duracion: 0m
  ratio_usado: 300000
---

# Operación fiable (Iniciativa 3 del plan director)

> **Evaluación:** [`evaluation.md`](evaluation.md)
> **Plan de implementación:** [`improvement-plan.md`](improvement-plan.md) · [`tasks.md`](tasks.md)
> **Origen:** [plan director](../2026-11-10-platform-audit/plan.md), «Iniciativa 3 — Operación fiable» (líneas 129-141); [auditoría](../2026-11-10-platform-audit/audit.md): O-01, O-02, O-03, O-05, O-06, S-06, B-02, B-03, B-05, B-06, B-07, B-15, M-01, M-06; §6.1 (severidades elevadas por el VPS).

> **Terminología:**
> - **Copia local**: volcado `pg_dump` en el volumen `memory-backups` del proyecto Compose.
> - **Copia externa**: la misma copia, cifrada, en un destino fuera del host (en esta iniciativa, un destino simulado: directorio montado o remoto `rclone` local). Nunca un servicio de nube real.
> - **Ensayo aislado**: `scripts/deploy-memory.py --project-name <x> --embed-stub [--roundtrip]`, con nombres de contenedores, redes y volúmenes distintos de `knowledge-graphs-*`.
> - **Trabajo venenoso**: trabajo cuyo proceso tumba al worker, de modo que su concesión expira y se vuelve a reclamar sin fin.
> - **Abstención**: la búsqueda declara «nada relevante» en lugar de devolver los mejores resultados aunque ninguno lo sea.
> - **Hecho** (con `fichero:línea`, verificado el 2026-11-15 sobre `b7ce9d6`) frente a **hipótesis** (marcada como tal).

## Contexto y objetivo

Tras la Iniciativa 2, Kairos tiene tres componentes y CI, pero no está listo para operar en un VPS sin supervisión. Hechos del reconocimiento:

1. **Copias sin garantías (O-01, S-06).** `admin backup` hace `pg_dump --format=custom` en claro, sin checksum, sin retención y dentro del volumen del mismo host (`server/memory_platform/admin.py:286-294`). Solo se ejecuta al desplegar (`scripts/deploy-memory.py:377-380`).
2. **Restauración nunca ejercitada en el despliegue (O-02).** `restore-check` existe y compara `store_fingerprints` en una base `memory_restore*` vacía (`admin.py:295-313`), pero el despliegue no lo llama (`deploy-memory.py`, ninguna aparición de `restore-check`).
3. **Plazo corto en copia y manifiesto (O-03).** `operator()` usa `timeout=120` por defecto (`deploy-memory.py:257-258`) para `content-manifest` (`:376`) y `backup` (`:380`); con una base grande, el despliegue aborta.
4. **El worker muere o pierde trabajos con la base caída (B-03).** `claim_job` está fuera del `try` de `run_once` (`worker.py:91`): una excepción de conexión sale de `run()` (`:178-184`) y termina el proceso. Un fallo de base en `complete_job` (`:145`) cae en `except Exception` (`:165-168`), que intenta `fail_job(..., 'provider_error')` y, si la base sigue caída, también lanza.
5. **Sin tope al reclamar (B-05).** `claim_job` reclama trabajos `running` con concesión expirada sin mirar `attempts` (`store_jobs.py:92`, `:105`).
6. **Índice de cola que no sirve y sin retención (B-06).** El índice es `(state, available_at)` (`schema.sql:19`) y la consulta ordena por `priority, available_at, created_at, id` con un `OR` sobre `running` caducado (`store_jobs.py:92`). Ninguna tabla tiene retención: `jobs`, `events`, `audit_events`, `login_attempts`, `web_sessions` (`schema.sql:7-19`).
7. **Sin pool y con permisos repetidos (B-02).** Cada `transaction()` abre una conexión nueva (`store.py:24-30`, único punto de `psycopg.connect`); hay 86 usos de `transaction()`/`connect`. Cada transacción repite `_active` (actor y clave, `store_auth.py:36-53`) y `_require` añade consultas por proyecto (`:60-77`). La búsqueda híbrida abre una transacción por capa (`retrieval.py:87-148`).
8. **Plazos que no cancelan (B-07).** Solo el *fallback* de trigramas y la búsqueda vectorial fijan `statement_timeout` (`store_documents.py:21-35`, `store_vectors.py:351-356`); `asyncio.timeout` sobre `to_thread` (`retrieval.py:113-115`, `:146-148`) no cancela la consulta en el servidor. No hay `connect_timeout`.
9. **Despliegue incompleto (O-05, O-06).** Solo `memory-mcp` tiene `mem_limit` (`docker-compose.yml:154`); `memory-worker` y `memory-web` no tienen healthcheck (`:170-194`); `ollama` y `memory-postgres` no heredan la rotación de logs de `x-process` (`:36-38`, `:41-85`). No hay bloqueo contra despliegues concurrentes ni retroceso de imágenes (todas `:latest`, `:69-198`). `OLLAMA_UPSTREAM` usa `host.docker.internal` sin `extra_hosts` (`:45`), que no resuelve en Linux.
10. **Sin abstención (M-01).** La búsqueda fusiona por RRF y devuelve los primeros `limit` siempre (`retrieval.py:172-190`). El RRF es **relativo al rango**, no mide relevancia absoluta; la capa semántica sí calcula una similitud coseno (`store_vectors.py:101`, `:408`) y la léxica marca `lexical_match` en cada `Hit`. El conjunto de evaluación tiene 72 preguntas, todas con respuesta (`tests/retrieval_eval/dataset-v1.jsonl`, 0 `expected: []`).
11. **Sin sonda (M-06).** Hay métricas de cola (`kairos_jobs_queue_depth`, `kairos_jobs_failed`, `observability.py:205-208`), pero nada comprueba la cadena escribir → indexar → buscar, y nada avisa de una cola atascada ni de capturas acumuladas en la cola en disco del cliente (`client/lib/outbox.mjs:177`).
12. **Huecos de tests (B-15).** Sin tests de worker con base caída; `body_too_large` (`app.py:36`) y `work_budget_exceeded` (`agent_store.py:186`) solo aparecen en los contratos base, no en tests; `test_chunk_schema.py:14` trocea `schema.sql` por marcador. `/health/ready` ya tiene un caso 503 (`test_observability.py:216`).

**Objetivo**: que Kairos no pierda datos ni se quede parado sin que nadie lo sepa: copias verificadas, cifradas, externas y restaurables con un runbook probado; un worker que sobrevive a la caída de la base; conexiones y plazos acotados; un despliegue con límites, healthchecks, bloqueo y retroceso; una búsqueda capaz de decir «nada relevante»; y una sonda que detecta un worker parado. Todo probado con fixtures aislados, sin tocar la instalación desplegada.

**Fuente**: encargo del orquestador `/dev-cycle` (2026-11-15) sobre la sección «Iniciativa 3» del plan director.

## Clasificación y primer oráculo

| Bloque | Clase | Primer oráculo (test que debe fallar antes del cambio) |
|---|---|---|
| C-01 Copias | Capacidad nueva (cifrado, retención, copia externa, verificación) + defecto (O-03, plazo) | `verify-backup` detecta un byte alterado en la copia; el despliegue llama a `backup` con el plazo propio |
| C-02 Worker | Defecto (B-03, B-05) + capacidad nueva (retención) + rendimiento (índice) | Con la base cortada durante `claim_job`, `Worker.run()` sigue vivo; con base cortada en `complete_job`, el trabajo no queda `failed` |
| C-03 Conexiones y plazos | Refactor (pool, permisos por transacción) + cambio de comportamiento (plazos por defecto) | Una consulta `pg_sleep` más larga que el plazo se cancela en el servidor; conexiones abiertas por búsqueda tras calentar = 0 |
| C-04 Despliegue | Cambio de comportamiento (Compose y script de despliegue) | `docker compose config` del proyecto aislado muestra límites, healthchecks y rotación en todos los servicios; un segundo despliegue concurrente falla con `deployment_locked` |
| C-05 Abstención | Capacidad nueva, **visible para clientes** | Pregunta negativa del conjunto ampliado con `abstain` activo → `items: []` y `abstained: true` |
| C-06 Sonda | Capacidad nueva | Con `memory-worker` parado en el ensayo, la sonda termina con código ≠ 0 y `stage=index` |
| C-07 Tests | Refactor de pruebas + cobertura | Los tests nuevos de límites fallan si se quita el control; la suite sin `schema.sql` troceado mantiene el recuento |

## Decisiones de diseño

Propuestas; las marcadas con P-NN dependen de una pregunta abierta y se adoptan como se indica salvo que el orquestador decida otra cosa.

| Decisión | Elección propuesta | Motivo |
|---|---|---|
| Orden de trabajo | **C-07 (arnés de fallos) → C-02 → C-03 → C-01 → C-04 → C-06 → C-05**, en dos hitos (ver evaluación) | El arnés de inyección de fallos es el oráculo de C-02 y C-03; los dos tocan el núcleo y conviene tenerlos antes de añadir servicios. C-05 es el único cambio visible para clientes y va al final, coordinado con la Iniciativa 7 |
| Cifrado (S-06) | **`age` con destinatario de clave pública** (`MEMORY_BACKUP_RECIPIENTS_FILE`); la clave privada nunca está en el host ni en el repo (P-01) | El servidor puede cifrar pero no descifrar: un VPS comprometido no expone las copias. Alternativa: `gpg` simétrico, que exige el secreto en el host |
| Integridad | **Manifiesto `<copia>.json`** junto a cada copia: sha256 del fichero tal como queda en disco (cifrado), bytes, versión de esquema, hora, cifrado sí/no, recuentos de `store_fingerprints` | `verify-backup` y la copia externa verifican sin descifrar; la restauración compara recuentos |
| Retención de copias | **`backup --prune --keep N`** sobre ficheros con el patrón propio y manifiesto válido; nunca borra la última copia verificada; `N ≥ 1` | O-01; evita borrar ficheros ajenos al volumen |
| Copia externa programada | **Servicio Compose `memory-backup`** (perfil `backup`, imagen `operator`) que ejecuta `admin backup-cycle` cada `MEMORY_BACKUP_INTERVAL`: copia, cifra, verifica, sube al destino, verifica en destino y aplica retención local y remota. Destinos `dir:<ruta montada>` y `rclone:<remoto>:<ruta>` (P-02) | Configurable y probado en local con un directorio y un remoto `rclone` de tipo `local`/`alias`; ningún servicio de nube real ni credencial en el repo |
| `--verify-backup` (O-02) | **Opcional en `deploy-memory.py`, activado por defecto en los ensayos**: restaura la copia previa en un contenedor PostgreSQL efímero del propio proyecto con base `memory_restore_<marca>`, compara `store_fingerprints` y aborta antes de `migrate` si difieren | Reutiliza `restore-check` y sus salvaguardas (`admin.py:295-313`); nunca escribe en la base del proyecto |
| Plazo de copia (O-03) | **`--backup-timeout`** (por defecto 3.600 s, como `MIGRATE_TIMEOUT_SECONDS`, `deploy-memory.py:27`) para `content-manifest`, `backup` y `verify-backup` | El plazo de 120 s no escala con la base |
| Errores del worker (B-03) | **Clase propia `StoreUnavailable`** para `psycopg.OperationalError`/`InterfaceError` y agotamiento del pool; `claim_job` dentro de un bucle con espera exponencial con *jitter* y tope (`MEMORY_WORKER_DB_BACKOFF_MAX`, 60 s); un fallo de base al completar no marca `failed` ni consume intento de proveedor: el trabajo vuelve a ser reclamable al expirar la concesión | Distingue «la base no responde» de «el proveedor falló» |
| Tope al reclamar (B-05) | **Un trabajo `running` con concesión expirada y `attempts ≥ max_attempts` pasa a `failed` con `attempts_exhausted`** en la misma transacción de reclamo, en lugar de reclamarse | Corta el bucle de trabajos venenosos sin perderlos: quedan visibles en `kairos_jobs_failed` y se pueden reintentar con `retry_job` |
| Índice de cola (B-06) | **Migración aditiva (versión de esquema 12)** con índice parcial `(priority, available_at, created_at, id) WHERE state IN ('pending','unknown')` y otro parcial para `running` por `lease_until`; si el `OR` impide usarlo, `claim_job` hace dos sondeos ordenados con la misma semántica | Sirve el `ORDER BY` real; no toca filas ni columnas |
| Retención de tablas (B-06) | **`admin prune-tables`** (por lotes, con `--dry-run`) y ejecución periódica opcional desde `memory-backup`; ventanas por tabla configurables (P-03); **nunca en una migración** | Las migraciones son aditivas (CLAUDE.md); borrar filas antiguas es operación, no esquema |
| Pool (B-02) | **`psycopg_pool.ConnectionPool`** dentro de `Store.transaction()`, tamaño `MEMORY_POOL_MIN`/`MEMORY_POOL_MAX`, espera `MEMORY_POOL_TIMEOUT`; los comandos de `admin` siguen con conexión directa | `store.py:28` es el único punto de conexión; `store_surface.json` no cambia |
| Plazos por defecto (B-07) | **`connect_timeout` y `statement_timeout` como opciones de conexión** (`MEMORY_CONNECT_TIMEOUT`, 5 s; `MEMORY_STATEMENT_TIMEOUT_MS`, 15.000 ms en la API y 30.000 en el worker, por debajo de `request_timeout`, `config.py:232`); `migrate`, `backfill-chunks` y `backup` sin límite propio | El servidor cancela la consulta aunque el hilo siga; los `set_config` locales existentes ya restauran su valor previo (`store_documents.py:27-35`) |
| Permisos por transacción (B-02) | **Caché de `_active` y de las concesiones por proyecto en el ámbito de la conexión, válida solo hasta el `COMMIT`** | Reduce consultas sin relajar la revocación: la siguiente transacción vuelve a leer |
| Límites de recursos (O-05) | **`mem_limit` y `cpus` en todos los servicios**, con variables `MEMORY_*_MEM_LIMIT` y valores por defecto documentados para 32 GB locales y un VPS pequeño | O-05 |
| Healthchecks (O-05) | **Worker: latido** (`/tmp/kairos-worker-heartbeat`, en el `tmpfs` existente) que el bucle escribe en cada vuelta (y la renovación de la concesión de un trabajo largo) con el plazo del siguiente latido y que el healthcheck compara con el reloj (enmienda de la revisión de la Fase 9, n.º 1); **web**: `GET /health/live` del proxy | El worker no tiene HTTP; el sistema de ficheros es de solo lectura salvo `/tmp` (`docker-compose.yml:32-33`) |
| Bloqueo de despliegue (O-06) | **Fichero de bloqueo exclusivo en el directorio privado del proyecto** con PID, host y hora; un bloqueo huérfano se informa y solo se rompe con `--break-lock` | Evita dos despliegues sobre el mismo proyecto |
| Retroceso de imágenes (O-06) | **Etiquetas locales `kairos-*:<versión>-<marca>`** antes de cada construcción, registro en `deployment-status.json` y `--rollback` que vuelve a las anteriores sin migrar (P-08) | Las migraciones son aditivas: el código anterior funciona sobre la base migrada (`docs/operations.md:186`, `:201`) |
| `extra_hosts` (O-06) | **`host.docker.internal:host-gateway`** en el servicio `ollama` | El VPS es Linux (audit §6.1) |
| Abstención (M-01) | **Señal absoluta, no RRF**: abstiene cuando la mejor similitud semántica queda por debajo de un umbral por modelo (`MEMORY_ABSTAIN_THRESHOLDS`, p. ej. `nomic-embed-text:0.xx`) y ningún resultado tiene `lexical_match`. Se pide con el parámetro opcional `abstain` y el operador puede activarla por defecto con `MEMORY_ABSTAIN_DEFAULT` (P-04). La respuesta añade `abstained: true` y deja `items: []` | El RRF depende del rango y no sirve de umbral; el contrato solo crece (parámetro y campo opcionales) |
| Calibración de la abstención | **Conjunto ampliado `dataset-v1-negatives`** (≥ 20 preguntas sin respuesta, ES/EN) y métricas nuevas en `retrieval-eval`: abstención correcta en negativas y abstención falsa en positivas, con umbrales en `thresholds.json`; umbral real de `nomic-embed-text` según P-05 | La puerta usa embeddings simulados (`fake_embeddings.py:1-8`): un umbral calibrado con ellos no vale para el modelo real |
| Sonda (M-06) | **`admin probe`** (o `scripts/kairos-probe.py`) contra `/v1` con una clave de alcance solo a un proyecto dedicado `kairos-probe`: escribe un recuerdo sintético con marca única, espera su recibo `embed`, lo busca con la capa semántica, lo retira y mide cada etapa. Servicio `memory-probe` opcional con intervalo; métricas `kairos_probe_success`, `kairos_probe_stage_seconds`, `kairos_probe_last_success_timestamp` | Cubre todos los eslabones; no ensucia proyectos de usuarios |
| Cola atascada (M-06) | **`kairos_jobs_oldest_pending_seconds`** en `/metrics` y aviso de la sonda por encima de `MEMORY_QUEUE_STUCK_SECONDS`; **`kairos doctor`** avisa si la cola en disco del cliente tiene capturas pendientes más antiguas que un umbral (P-07) | M-06 nombra la cola del CLI; la del servidor es el eslabón que detecta un worker parado |
| Canal de alerta | **Métrica, evento de log y código de salida ≠ 0**, más un fichero de reglas Prometheus de ejemplo; el envío a una persona es de la Iniciativa 5 (P-06) | No hay Alertmanager ni correo configurados; el VPS los añade |

## Configuración / parámetros

| Parámetro | Clave | Default hoy | Valor objetivo |
|---|---|---|---|
| Destinatarios de cifrado | `MEMORY_BACKUP_RECIPIENTS_FILE` (nuevo, fichero de claves públicas `age`) | — | sin valor; con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` (por defecto en el servicio `memory-backup`) es obligatorio |
| Copias locales conservadas | `MEMORY_BACKUP_KEEP` / `--keep` | ilimitadas | **7** |
| Intervalo de la copia externa | `MEMORY_BACKUP_INTERVAL` | — | **24 h** |
| Destino externo | `MEMORY_BACKUP_DESTINATION` (`dir:` o `rclone:`) | — | sin valor (servicio apagado) |
| Copias externas conservadas | `MEMORY_BACKUP_REMOTE_KEEP` | — | **30** |
| Plazo de copia en el despliegue | `--backup-timeout` | 120 s | **3.600 s** |
| Espera máxima del worker sin base | `MEMORY_WORKER_DB_BACKOFF_MAX` | — (el proceso muere) | **60 s** |
| Pool | `MEMORY_POOL_MIN` / `MEMORY_POOL_MAX` / `MEMORY_POOL_TIMEOUT` | sin pool | **1 / 10 / 5 s** (a medir en el plan) |
| Plazos de conexión | `MEMORY_CONNECT_TIMEOUT` / `MEMORY_STATEMENT_TIMEOUT_MS` | sin plazo | **5 s / 15.000 ms** (API), 30.000 ms (worker) |
| Retención | `MEMORY_RETENTION_*` por tabla | sin retención | según P-03 |
| Abstención | `MEMORY_ABSTAIN_THRESHOLDS` / `MEMORY_ABSTAIN_DEFAULT` | — | umbral por modelo según P-05; **`off`** por defecto (P-04) |
| Sonda | `MEMORY_PROBE_INTERVAL` / `MEMORY_PROBE_TIMEOUT` / `MEMORY_QUEUE_STUCK_SECONDS` | — | **300 s / 120 s / 900 s** |
| Límites de recursos | `MEMORY_<SERVICIO>_MEM_LIMIT`, `_CPUS` | solo `memory-mcp: 1g` | por servicio, documentados |

## Arquitectura y componentes

- **Servidor (`server/memory_platform/`)**: `admin.py` (subcomandos `backup` ampliado, `verify-backup`, `backup-cycle`, `prune-tables`, `probe`); `worker.py` (clasificación de errores, espera, latido); `store.py` (pool y opciones de conexión); `store_auth.py` (caché por transacción); `store_jobs.py` (tope al reclamar, sondeos de cola); `schema.sql` (versión 12, índices parciales); `retrieval.py` y `models.py` (abstención); `observability.py` (métricas de sonda y antigüedad de cola); `config.py` (parámetros nuevos).
- **Imagen `operator`**: añade `age` y `rclone` fijados por versión (hipótesis: disponibles en Debian bookworm).
- **Compose**: límites, healthchecks y rotación en todos los servicios; `extra_hosts`; servicios opcionales `memory-backup` y `memory-probe` (perfiles propios, sin puertos publicados, sin clave privada montada).
- **`scripts/deploy-memory.py`**: `--backup-timeout`, `--verify-backup`, bloqueo, etiquetado de imágenes y `--rollback`.
- **Cliente**: `kairos doctor` informa de la antigüedad de la cola en disco (`client/lib/outbox.mjs`).
- **Contratos**: `memory-platform.openapi.json` y `kairos-mcp.json` con el parámetro `abstain` y el campo `abstained`, solo aditivos.
- **Docs**: `docs/operations.md` (runbook de restauración, copia externa, retroceso, sonda), `docs/configuration.md`, `docs/architecture.md`, `CHANGELOG*.md` con la nota para la Iniciativa 7.

## Flujo (paso a paso)

1. **Copia programada**: `memory-backup` despierta → `pg_dump` → cifrado `age` → manifiesto con sha256 → `verify-backup` local → subida al destino → verificación del sha256 en destino → retención local y remota → métrica y log.
2. **Despliegue**: bloqueo → inspección → `content-manifest` y `backup` con plazo propio → `--verify-backup` (restauración en base efímera y comparación) → etiquetado de imágenes → construcción → migración → arranque con healthchecks → verificación → liberación del bloqueo. `--rollback` vuelve a las etiquetas registradas sin migrar.
3. **Worker**: reclamo (con tope) → proveedor → completar; si la base falla en cualquier punto, espera y reintenta sin terminar el proceso ni consumir intentos de proveedor.
4. **Búsqueda con abstención**: capas → fusión RRF → si `abstain`, compara la mejor similitud semántica con el umbral del modelo y mira `lexical_match` → `abstained: true, items: []` o la respuesta normal.
5. **Sonda**: escribir → esperar recibo → buscar → retirar → métricas; fallo en cualquier etapa → código ≠ 0, `probe_failed` con la etapa y `kairos_probe_success 0`.
6. **Restauración (runbook)**: descargar del destino → verificar sha256 → descifrar con la clave privada fuera del servidor → `restore-check` en base vacía `memory_restore*` → comparar → corte manual documentado.

## Alcance

- **Dentro (esta iniciativa):**
  - C-01 Copias (O-01, O-02, O-03, S-06).
  - C-02 Worker (B-03, B-05, B-06).
  - C-03 Conexiones y plazos (B-02, B-07).
  - C-04 Despliegue (O-05, O-06).
  - C-05 Abstención (M-01).
  - C-06 Sonda y cola atascada (M-06).
  - C-07 Tests (B-15).
- **Fuera:**
  - El despliegue real, la copia externa a un proveedor de nube real y el envío de alertas a personas (Iniciativa 5, con autorización expresa).
  - Paneles y Alertmanager (Iniciativa 5, observabilidad).
  - Límites por clave, rotación de claves y caducidad (Iniciativa 4).
  - Retirada del MCP interno (versión 0.5.0, decidida en la Iniciativa 2) y lock de dependencias con hashes (B-19, Iniciativa 9).
  - Puntuación con recencia y uso (Iniciativa 8): la abstención solo usa la similitud y la coincidencia léxica.
  - Borrar tablas, columnas o volúmenes; borrar filas dentro de una migración.

## Manejo de errores

| Caso | Comportamiento |
|---|---|
| Base caída al reclamar | El worker registra `store_unavailable` (sin DSN), espera con *backoff* y sigue vivo; el latido sigue avanzando para no reiniciarlo en bucle, salvo que la caída supere el umbral del healthcheck |
| Base caída al completar o fallar un trabajo | El trabajo no cambia de estado por la caída y no consume intento de proveedor: el worker conserva el resultado en memoria y repite la escritura (misma espera que el reclamo), renovando la concesión al volver la base, dentro de un presupuesto por escritura (`MEMORY_WORKER_WRITE_RETRY_SECONDS`, por defecto igual a la concesión, y 5 escrituras fallidas seguidas). Agotado el presupuesto, o perdida la concesión, abandona (`job_write_abandoned`) y el trabajo vuelve a ser reclamable al expirar la concesión. **Límites declarados:** (1) no se reviven concesiones vencidas: una caída más larga que lo que le queda a la concesión cuando empieza (entre dos tercios de `MEMORY_LEASE_SECONDS` y la concesión entera, porque el latido la renueva cada tercio), o que el presupuesto de escritura si es menor, puede costar el intento y, en el último, acabar `attempts_exhausted` con el resultado perdido; (2) la muerte del proceso con el resultado en memoria; (3) la caída al leer el vector guardado de un `embed`, antes de llamar al proveedor (en el último intento acaba `attempts_exhausted`) |
| Error transitorio que la base contesta al completar o fallar (`40001`, `40P01`, `57014`, `55P03`, clase `53`) | No es caída de base, pero se repite la escritura dentro del mismo presupuesto; agotado, `fail_job` con `store_error` y reintento (terminal solo si se agotan los intentos). En el latido no da el trabajo por perdido. Cualquier otro error contestado (p. ej. `54xxx`) va directo a `store_error` |
| Trabajo con `attempts ≥ max_attempts` y concesión expirada | `failed` con `attempts_exhausted`; visible en `kairos_jobs_failed`; `retry_job` lo reactiva |
| Pool agotado | Espera hasta `MEMORY_POOL_TIMEOUT`; después 503 `store_busy` con `request_id` |
| `statement_timeout` agotado | 503 `store_timeout` en la API (o capa `unavailable` con `reason: timeout` en la búsqueda, como hoy); la conexión vuelve al pool sana |
| Copia sin destinatario con cifrado obligatorio | Falla con un mensaje que nombra `MEMORY_BACKUP_RECIPIENTS_FILE`; no escribe copia en claro |
| sha256 no coincide | `verify-backup` falla con `backup_checksum_mismatch`; el despliegue aborta antes de migrar; la copia externa no sube ni borra nada |
| Destino externo no disponible | `backup_offsite_failed` con el tipo de destino (sin credenciales), métrica a 0, reintento en el siguiente ciclo; nunca borra copias locales por ello |
| Restauración verificada distinta | `restore-check` falla (comportamiento actual, `admin.py:312`); el despliegue aborta |
| Despliegue concurrente | `deployment_locked` con PID y hora del dueño; no toca nada; `--break-lock` explícito para un bloqueo huérfano |
| `--rollback` sin etiquetas anteriores | Falla con `no_previous_images`; no cambia servicios |
| `abstain` sin umbral para el modelo | La búsqueda responde normal y añade `abstention: "uncalibrated"` (aditivo); nunca abstiene a ciegas |
| Sonda: etapa agotada | Código ≠ 0, `probe_failed` con `stage` (`write`, `index`, `search`, `retire`), métrica a 0; intenta retirar lo escrito |

## Criterios de aceptación

Todos se comprueban con fixtures aislados (PostgreSQL efímero del target `test`, proxy TCP cortable, servidores HTTP simulados, destinos de copia en directorios temporales o un proyecto Compose aislado con nombre distinto de `knowledge-graphs`), nunca contra la base, los contenedores, los volúmenes ni las redes `knowledge-graphs-*`, ni contra el Ollama del host.

**C-01 · Copias (O-01, O-02, O-03, S-06)**

- [ ] CA-01 — `admin backup` escribe la copia y su manifiesto `<copia>.json` (sha256, bytes, versión de esquema, hora, `encrypted`, recuentos); `admin verify-backup` recalcula el sha256 y falla con `backup_checksum_mismatch` si se altera un byte (test).
- [ ] [GWT] CA-02 — Dado `MEMORY_BACKUP_RECIPIENTS_FILE` con una clave pública `age` de prueba generada en el test, Cuando se hace `backup`, Entonces el fichero no empieza por la cabecera `PGDMP` ni contiene el texto de una fila sembrada, y solo se restaura tras descifrar con la clave privada del test, que nunca está en el contenedor del servidor. Con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` y sin destinatarios, falla nombrando la variable y no deja fichero.
- [ ] CA-03 — `backup --prune --keep N` conserva las N copias más recientes con manifiesto válido, nunca borra la última verificada ni ficheros sin el patrón propio, rechaza `N < 1` e informa de lo borrado (test con ficheros señuelo).
- [ ] CA-04 — `deploy-memory.py` llama a `content-manifest`, `backup` y `verify-backup` con `--backup-timeout` (por defecto 3.600 s), comprobado en `test_deploy.py` (O-03).
- [ ] [GWT] CA-05 — Dado un ensayo aislado con `--verify-backup`, Cuando termina la fase `backup`, Entonces la copia se restaura en un contenedor PostgreSQL efímero con base `memory_restore_*`, se comparan `store_fingerprints`, el despliegue aborta antes de `migrate` si difieren, el contenedor efímero se elimina y el informe registra resultado y duración.
- [ ] [GWT] CA-06 — Dado `memory-backup` con un intervalo corto y un destino `dir:` (y, en otro caso, `rclone:` con un remoto local configurado en el test), Cuando vence el intervalo, Entonces sube copia cifrada y manifiesto, verifica el sha256 en destino y aplica `MEMORY_BACKUP_REMOTE_KEEP`; con el destino inaccesible registra `backup_offsite_failed`, pone su métrica a 0, reintenta en el ciclo siguiente y no borra copias locales.
- [ ] CA-07 — `docs/operations.md` tiene un runbook de restauración desde la copia externa con pasos ejecutables, y un ensayo automatizado lo sigue: descarga del destino simulado, verificación, descifrado, `restore-check` en un proyecto aislado vacío y comparación de manifiesto, con resultado `restored_and_content_verified` (criterio de cierre 1 del plan director).
- [ ] CA-08 — Ninguna clave privada ni credencial de destino está en el repositorio ni en una imagen; `docker compose config` del proyecto aislado no monta la clave privada en ningún servicio (test).

**C-02 · Worker (B-03, B-05, B-06)**

- [ ] [GWT] CA-09 — Dado un trabajo en curso, Cuando la base se corta durante `complete_job`, Entonces el trabajo no pasa a `failed` ni recibe `provider_error`, y al volver la base se completa: el worker conserva el resultado y repite la escritura dentro de su presupuesto (`MEMORY_WORKER_WRITE_RETRY_SECONDS`), o, si la concesión vence antes, en una reclamación posterior. Alcance: no se reviven concesiones vencidas; una caída más larga que lo que le queda a la concesión cuando empieza (entre dos tercios de `MEMORY_LEASE_SECONDS` y la concesión entera, porque el latido la renueva cada tercio), o que el presupuesto de escritura (`MEMORY_WORKER_WRITE_RETRY_SECONDS`) si es menor, durante la escritura puede costar el intento y, en el último, acabar `attempts_exhausted` con el resultado perdido (se recomienda subir `MEMORY_LEASE_SECONDS` si se esperan caídas largas).
- [ ] [GWT] CA-10 — Dado el worker con la base cortada, Cuando `claim_job` falla repetidamente, Entonces `Worker.run()` no termina, las esperas crecen con *jitter* hasta `MEMORY_WORKER_DB_BACKOFF_MAX`, se registra `store_unavailable` sin DSN ni contraseña, y al restablecer la base procesa la cola.
- [ ] CA-11 — Los errores de proveedor reintentables conservan su política actual (`worker.py:148-160`); los errores de base no incrementan `attempts` más allá del reclamo ya contado (test que compara ambos caminos).
- [ ] CA-12 — Un trabajo `running` con concesión expirada y `attempts ≥ max_attempts` pasa a `failed` con `attempts_exhausted` en lugar de reclamarse; `retry_job` lo reactiva (test de trabajo venenoso).
- [ ] CA-13 — La migración de la versión de esquema 12 crea los índices parciales de cola; sobre una tabla sembrada con ≥ 10.000 trabajos terminales, el plan de `claim_job` (`EXPLAIN (FORMAT JSON)`) usa un índice nuevo y no un recorrido secuencial; `test_migrations_additive.py` pasa.
- [ ] CA-14 — `admin prune-tables --dry-run` informa y `admin prune-tables` borra por lotes según las ventanas de P-03; `content_manifest()` de los datos de memoria (elementos, documentos, embeddings y recibos vigentes) es igual antes y después; ningún trabajo con recibo en `projection_receipts` se borra; ninguna migración contiene `DELETE`.

**C-03 · Conexiones y plazos (B-02, B-07)**

- [ ] CA-15 — `Store.transaction()` toma conexiones de un pool (`psycopg_pool`, versión fijada en `requirements.txt`); tras calentar, una búsqueda híbrida no abre conexiones nuevas (conjunto de `pg_backend_pid()` estable); `store_surface.json` no cambia y `test_store_surface` pasa.
- [ ] [GWT] CA-16 — Dado `MEMORY_STATEMENT_TIMEOUT_MS` por defecto, Cuando una consulta de servicio dura más (`pg_sleep`), Entonces PostgreSQL la cancela, la API responde 503 `store_timeout` y la conexión vuelve al pool utilizable; `migrate`, `backfill-chunks` y `backup` no heredan el plazo.
- [ ] CA-17 — Con un DSN hacia un puerto que acepta y no responde, el fallo de conexión llega en ≤ `MEMORY_CONNECT_TIMEOUT` + 1 s (test con servidor TCP mudo).
- [ ] CA-18 — Una búsqueda sobre N proyectos ejecuta la lectura de actor y clave una sola vez por transacción (contador de consultas en el test); una clave revocada deja de valer en la petición siguiente.
- [ ] CA-19 — Con el pool agotado, una petición espera como máximo `MEMORY_POOL_TIMEOUT` y recibe 503 `store_busy`; no se cuelga.

**C-04 · Despliegue (O-05, O-06)**

- [ ] CA-20 — Todos los servicios de `docker-compose.yml` declaran `mem_limit` y `cpus` configurables por variable, con valores documentados en `docs/configuration.md` (test sobre `docker compose config`).
- [ ] CA-21 — `memory-worker` y `memory-web` tienen healthcheck; con el bucle del worker detenido (test unitario del latido y caso en el ensayo), el contenedor pasa a `unhealthy` en ≤ plazo del último latido + `interval × retries`. **Enmienda (revisión de la Fase 9, n.º 1; cambio de criterio aprobado por el orquestador):** el texto original decía «≤ `interval × retries`», que ningún umbral de antigüedad mayor que 0 cumple (hay que esperar a que el fichero caduque) y que con un `MEMORY_LEASE_SECONDS` largo tampoco seguía la cadencia del latido; el fichero guarda ahora el plazo del siguiente latido y el healthcheck lo compara con el reloj.
  - *Nota de enmienda (revisión de la Fase 10, fix3, con la delegación del usuario «Las preguntas toma la mejor decisión»; AMPLÍA la cota numérica del criterio, no es solo una aclaración; el criterio aprobado no se reescribe):* la cota del ensayo se deduce de cómo Docker programa las sondas, que espera `interval` **después** de que una termina: el instante de `unhealthy` (el final de la `retries`-ésima sonda fallida consecutiva) es como mucho plazo del último latido + duración de la última sonda correcta + `interval × retries` + suma de las duraciones de las `retries` sondas que fallan. El ensayo lee ese instante y esas duraciones de `State.Health.Log` en vez del reloj del sondeo; con sondas de ~1 s la diferencia con el texto es de unos 4 s, y con las `retries` sondas agotando su plazo (`timeout`, 5 s) llega a unos 20 s por encima de lo que dice el texto (`interval × retries` más la duración de las sondas que fallan).
- [ ] CA-22 — Todos los servicios, `ollama` y `memory-postgres` incluidos, rotan logs (`json-file` con `max-size` y `max-file`), comprobado en `docker compose config`.
- [ ] [GWT] CA-23 — Dado un despliegue en curso sobre un proyecto, Cuando se lanza otro sobre el mismo proyecto, Entonces el segundo termina con `deployment_locked` sin ejecutar ninguna fase; un bloqueo con PID muerto se informa y solo se rompe con `--break-lock`.
  - *Nota de enmienda (revisión de la Fase 10, fix2; cambio de mecanismo aprobado por el orquestador, el criterio aprobado arriba no se reescribe):* el bloqueo pasa a ser un bloqueo del sistema operativo sobre `deployment.lock` (`flock`/`msvcrt.locking`), que el sistema libera cuando el proceso muere: un dueño muerto de este equipo ya no deja un bloqueo que romper, el siguiente despliegue lo toma sin opciones, y `--break-lock` no es necesario para tomar ningún bloqueo, ni siquiera el de un fichero escrito por otro equipo (un directorio privado compartido): si el sistema deja tomarlo se toma sin la opción, que solo hace que se nombre como rotura. Fix3: «se informa» se cumple al tomarlo: si el fichero no estaba vacío (un despliegue que no terminó), el nuevo lo avisa por stderr y en el informe (`previous_run_interrupted`, con su PID, equipo y hora); `--break-lock` no borra ni renombra ningún fichero y no toma un bloqueo que el sistema mantiene. Fix4: el aviso de un fichero de otro equipo no afirma que su despliegue murió (en un disco compartido el bloqueo del sistema puede no propagarse y puede seguir en marcha), nada del fichero llega crudo a la terminal, y el fichero debe ser normal con un solo nombre (un enlace duro, simbólico o de reanálisis es `deployment_locked` sin tocarlo; en Windows se crea además sin seguir enlaces). El resto del criterio (el segundo termina con `deployment_locked`, sin ejecutar ninguna fase) no cambia.
- [ ] [GWT] CA-24 — Dado un ensayo aislado desplegado dos veces con imágenes etiquetadas, Cuando se ejecuta `--rollback`, Entonces los servicios vuelven a las etiquetas anteriores sin migrar, `content-manifest` es igual y una búsqueda funciona.
- [ ] CA-25 — El servicio `ollama` declara `extra_hosts: ["host.docker.internal:host-gateway"]` (test sobre `docker compose config`) y `docs/operations.md` explica el caso Linux.

**C-05 · Abstención (M-01) — visible para clientes**

- [ ] CA-26 — Existe un conjunto de ≥ 20 preguntas sin respuesta (ES y EN, incluidas preguntas cercanas al tema de un recuerdo existente), versionado aparte de `dataset-v1.jsonl`, que no cambia; `check_dataset.py` lo valida.
- [ ] [GWT] CA-27 — Dado el umbral del proveedor simulado en `thresholds.json`, Cuando la puerta ejecuta las preguntas negativas con `abstain: true`, Entonces responde `items: []` y `abstained: true` en al menos el porcentaje acordado (P-05), y sobre las positivas la abstención falsa no supera el tope acordado mientras recall@5 ≥ 0,80 y MRR ≥ 0,60 siguen cumpliéndose. **Enmienda 2026-11-18 (decisión del usuario del 2026-11-18, literal «12 de 24 en la CI»: metas de abstención **por proveedor**; con el proveedor simulado de la CI, ≥ 0,50 de abstención correcta (12 de las 24 negativas) y ≤ 0,05 de falsa, como guarda de regresión (sus embeddings no reflejan la calidad real, R-07; con ellos el 70 % exige un 6,9 % de falsa, medido); con modelos reales siguen ≥ 0,70 y ≤ 0,05; `thresholds.json`, `abstention.simulated`).** Redacción original conservada arriba.
- [ ] CA-28 — El trabajo `retrieval-eval` de la CI exige las métricas de abstención; un umbral absurdo (por ejemplo 0,99) lo deja en rojo en una ejecución de prueba.
- [ ] CA-29 — El parámetro `abstain` y los campos `abstained`/`abstention` son opcionales en `memory-platform.openapi.json` y en `kairos-mcp.json` (también en `result_schemas.search`); `test_contract_additive.py` pasa; sin `abstain` y con `MEMORY_ABSTAIN_DEFAULT=off` la respuesta es idéntica a la actual (test de no regresión); el cambio se declara en `CHANGELOG*.md` con una nota para la Iniciativa 7.

**C-06 · Sonda y cola atascada (M-06)**

- [ ] [GWT] CA-30 — Dado un ensayo aislado sano, Cuando se ejecuta la sonda, Entonces escribe un recuerdo sintético en el proyecto `kairos-probe`, espera su recibo `embed`, lo encuentra por búsqueda semántica, lo retira, termina con código 0 y publica la duración de cada etapa.
- [ ] [GWT] CA-31 — Dado el ensayo aislado con `memory-worker` parado, Cuando se ejecuta la sonda, Entonces falla en ≤ `MEMORY_PROBE_TIMEOUT` con `probe_failed` y `stage=index`, código ≠ 0 y `kairos_probe_success 0`, e intenta retirar lo escrito (criterio de cierre 3 del plan director).
- [ ] CA-32 — `/metrics` publica `kairos_jobs_oldest_pending_seconds`; la sonda avisa cuando supera `MEMORY_QUEUE_STUCK_SECONDS`; `kairos doctor` avisa cuando la cola en disco del cliente tiene capturas pendientes más antiguas que su umbral (tests de servidor y de cliente).
- [ ] CA-33 — La clave de la sonda solo tiene alcance sobre `kairos-probe`; tras una ejecución no quedan recuerdos activos de la sonda (solo retirados); ningún test de la sonda apunta a recursos `knowledge-graphs-*`.
  - (Enmienda de la revisión de la fase 11, intento 1, n.º 9 y 10, sin reescribir el criterio: «no quedan recuerdos activos» vale tras una ejecución que llega a retirar; si la base se corta a mitad, la nota queda activa y la siguiente ejecución la retira en su barrido inicial (y `admin probe` purga físicamente las filas retiradas de `kairos-probe`). La métrica `kairos_probe_last_success_timestamp` del alcance (tabla de la sonda) se publica como `kairos_probe_last_success_timestamp_seconds`, con el sufijo `_seconds` de `kairos_probe_last_run_timestamp_seconds` y `kairos_backup_offsite_last_run_timestamp_seconds`.)

**C-07 · Tests (B-15)**

- [ ] CA-34 — Existe un arnés de inyección de fallos (proxy TCP cortable entre el proceso y el PostgreSQL efímero) usado por los tests de base caída en el worker (CA-09, CA-10), concesión expirada y trabajo venenoso (CA-12).
- [ ] CA-35 — Hay tests de `body_too_large` (413), `/v1/users` (permitido, sin permiso, ajeno), `/health/ready` (listo y no listo) y `work_budget_exceeded` (409); cada uno falla si se retira el control correspondiente.
- [ ] CA-36 — Los tests que comparan texto SQL o trocean `schema.sql` por marcador (`test_chunk_schema.py:14-21` y los equivalentes que localice el plan) comprueban catálogo o comportamiento; el recuento de la suite no baja.

**Transversales**

- [ ] [GWT] CA-37 — Dado un ensayo de cierre en un proyecto Compose aislado, Cuando se para y arranca su `memory-postgres` con trabajos en cola, Entonces `memory-worker` no se reinicia por error propio (contador de reinicios igual), la cola se vacía tras volver la base y ningún trabajo queda `failed` por esa caída (criterio de cierre 2 del plan director). El mismo ensayo ejecuta CA-07 y CA-31 y deja la evidencia en el ledger.
- [ ] CA-38 — Al cerrar: migraciones solo aditivas; diff aditivo de ambos contratos frente a `contracts_base`; ninguna referencia a recursos `knowledge-graphs-*` ni al puerto 11434 del host salvo para rechazarlos; suite del servidor con 0 fallos y 0 omitidos; `retrieval-eval` en verde; `docs/operations.md`, `docs/configuration.md`, `docs/architecture.md` y `CHANGELOG*.md` actualizados.

## Pruebas

- Suite del servidor en PostgreSQL aislado (`docker build -f server/memory_platform/Dockerfile --target test`, hoy 764 tests, línea `MEMORY_TEST_RESULT`) para C-01 (subcomandos), C-02, C-03, C-05 y C-07.
- Arnés nuevo de inyección de fallos (proxy TCP en proceso) para CA-09, CA-10, CA-12, CA-16, CA-17 y CA-19.
- `scripts/tests/` y `test_deploy*.py` para el despliegue (CA-04, CA-20…CA-25) sobre `docker compose config` y dobles de `subprocess`.
- Ensayos aislados con `deploy-memory.py --project-name <x> --embed-stub --roundtrip` para CA-05, CA-06, CA-07, CA-21, CA-24, CA-30, CA-31 y CA-37, de uno en uno y en primer plano.
- Puerta `retrieval-eval` ampliada (CA-26…CA-28) y tests del cliente (`npm test`) para CA-32.
- Los criterios [GWT] se traducen 1:1 a casos del plan de pruebas con el mismo ID.

## Preguntas abiertas

**Decisión (2026-11-15, orquestador; el usuario delegó las decisiones abiertas: «Las preguntas toma la mejor decisión»):** puerta **go**. Se adoptan P-01 a P-10 tal como se recomiendan. P-05: se acepta medir el umbral de `nomic-embed-text` con un Ollama efímero y aislado (contenedor y volumen propios, desechados al terminar, nunca el Ollama del host); si la descarga falla, el umbral queda `uncalibrated` y se mide en la Iniciativa 5. **Enmienda 2026-11-18 a P-05 (decisión del usuario del 2026-11-18, literal «12 de 24 en la CI»: metas de abstención **por proveedor**; con el proveedor simulado de la CI, ≥ 0,50 de abstención correcta (12 de las 24 negativas) y ≤ 0,05 de falsa, como guarda de regresión (sus embeddings no reflejan la calidad real, R-07; con ellos el 70 % exige un 6,9 % de falsa, medido); con modelos reales siguen ≥ 0,70 y ≤ 0,05).** Los cambios visibles para clientes (`abstain`/`abstained`, retención) se declaran a la Iniciativa 7.

| ID | Pregunta | Recomendación | ¿Necesita al usuario? |
|---|---|---|---|
| P-01 | ¿Con qué se cifran las copias? | `age` con clave pública en el servidor y privada fuera; descifrado solo en el runbook | No: decisión técnica delegada en el orquestador |
| P-02 | ¿Cómo se programa la copia externa y a qué destinos? | Servicio Compose `memory-backup` con bucle e intervalo, destinos `dir:` y `rclone:`; en esta iniciativa solo se prueban con un directorio y un remoto `rclone` local. El proveedor real se elige en la Iniciativa 5 | No (delegada) |
| P-03 | Ventanas de retención por tabla | `login_attempts` 30 días; `web_sessions` caducadas o revocadas, 30 días; `audit_events` 365 días; `jobs` terminales `failed` sin recibo, 90 días (nunca `succeeded` con recibo; precisado en la revisión de la Fase 3: tampoco un `failed` citado por el recibo de un evento conservado ni uno de la versión actual de su documento o nota, para conservar el contrato de las herramientas MCP); **`events` sin retención por defecto** (lo leen `event_status`, la actividad y `get_tool_uses`, `store_documents.py:252-329`): borrarlo cambia respuestas que ven los clientes | No (delegada); si se activa la de `events`, declararlo a la Iniciativa 7 |
| P-04 | ¿Abstención activa por defecto? | No: parámetro opcional `abstain` y `MEMORY_ABSTAIN_DEFAULT=off`. Activarla por defecto cambia las respuestas que verá `custom-agents` mientras la Iniciativa 7 está en curso; se activa cuando la 7 la consuma | No (delegada), pero **se declara** a la Iniciativa 7 |
| P-05 | ¿Cómo se calibra el umbral para `nomic-embed-text` si la puerta usa embeddings simulados y el Ollama del host está vedado? | Umbral por modelo. En esta iniciativa: el del proveedor simulado en la puerta, y el de `nomic-embed-text` medido con un Ollama **efímero y aislado** (contenedor propio, otro puerto, el modelo descargado en un volumen desechable) si el orquestador lo acepta; si no, sin umbral para `nomic` (respuesta `abstention: "uncalibrated"`) y medición en la Iniciativa 5. Metas propuestas: ≥ 70 % de abstención correcta en negativas y ≤ 5 % de abstención falsa en positivas. **Enmienda 2026-11-18 (decisión del usuario del 2026-11-18, literal «12 de 24 en la CI»: metas de abstención **por proveedor**; con el proveedor simulado de la CI, ≥ 0,50 de abstención correcta (12 de las 24 negativas) y ≤ 0,05 de falsa, como guarda de regresión (sus embeddings no reflejan la calidad real, R-07; con ellos el 70 % exige un 6,9 % de falsa, medido); con modelos reales siguen ≥ 0,70 y ≤ 0,05).** | Sí, si exige descargar un modelo (≈ 270 MB) en un contenedor nuevo |
| P-06 | ¿Qué es «alerta» en esta iniciativa? | Métrica, evento de log y código de salida, más reglas Prometheus de ejemplo; el envío a personas va en la Iniciativa 5 | No (delegada) |
| P-07 | ¿«Cola atascada» es la del servidor o la del cliente? | Las dos: antigüedad del pendiente más viejo en `/metrics` (detecta el worker parado) y aviso en `kairos doctor` para la cola en disco (M-06), sin telemetría del cliente al servidor | No (delegada) |
| P-08 | ¿Cómo se retrocede la imagen sin registro de imágenes? | Etiquetas locales `<versión>-<marca>`, se conservan las dos anteriores, `--rollback` sin migrar | No (delegada) |
| P-09 | ¿La iniciativa cabe en un ciclo o se corta? | Dos hitos en la misma rama, con revisión por fase: **A «no perder datos ni parar»** (C-07, C-02, C-03, C-01: criterios de cierre 1 y 2) y **B «desplegar y detectar»** (C-04, C-06, C-05: criterio 3). Un PR por hito, para que la Iniciativa 5 pueda empezar con A fusionado. No se quita alcance | No (delegada) |
| P-10 | ¿Qué versión sale? | 0.4.1 de servidor, MCP y cliente (cambios aditivos); la 0.5.0 sigue reservada para retirar el MCP interno (Iniciativa 2, P-07) | No (delegada) |

## Referencias

- `server/memory_platform/admin.py:23-47` (`store_fingerprints`, `pg_environment`), `:240-321` (subcomandos, `backup`, `restore-check`).
- `server/memory_platform/worker.py:78-184` (`Worker`, `run_once`, `run`); `store_jobs.py:89-192` (`claim_job`, `renew_lease`, `_current_job`, `complete_job`, `fail_job`).
- `server/memory_platform/store.py:24-30`; `store_auth.py:36-77`; `retrieval.py:87-190`; `store_documents.py:21-35`, `:252-329`; `store_vectors.py:100-102`, `:351-356`, `:408`; `config.py:232-235`, `:292-295`.
- `server/memory_platform/schema.sql:7-19`, `:214-228` (versión 11); `observability.py:189-213`.
- `scripts/deploy-memory.py:27-37`, `:236-258`, `:296-410`; `docker-compose.yml:31-221`; `docs/operations.md:128-201`.
- `server/memory_platform/tests/retrieval_eval/` (`dataset-v1.jsonl`, `thresholds.json`, `fake_embeddings.py`); `test_chunk_schema.py:14`; `test_observability.py:216`.
- `client/lib/outbox.mjs:177`; `docs/contracts/kairos-mcp.json` (`result_schemas.search` con `additionalProperties: false`).

## Supuestos

- **Hipótesis**: `age` y `rclone` están en Debian bookworm y se pueden fijar por versión en la imagen `operator`; si no, se usa el binario oficial con sha256 verificado.
- **Hipótesis**: `psycopg_pool` es compatible con `psycopg 3.3.7` (`requirements.txt:5`) y con el uso desde `asyncio.to_thread`.
- **Hipótesis**: un índice parcial sirve al `claim_job` actual; si el `OR` lo impide, la consulta se divide en dos sondeos con la misma semántica.
- **Hipótesis**: la similitud coseno del proveedor simulado no se parece a la de `nomic-embed-text`; por eso el umbral es por modelo (P-05).
- **Hecho**: `result_schemas.search` tiene `additionalProperties: false` en todos sus niveles; un cliente que valide con el esquema anterior rechazaría `abstained`. Por eso solo aparece si se pide `abstain` o el operador lo activa (P-04), y se declara a la Iniciativa 7.
- Los datos actuales no se migran a producción (decisión del 2026-11-12): las copias y restauraciones se ensayan con datos sembrados.
- Docker en primer plano y de uno en uno (32 GB de RAM); ningún ensayo convive con otro.
