# Configuración de Kairos

La configuración del servidor, las políticas de proyecto y la configuración del cliente son capas distintas. Cambiar una no modifica automáticamente las otras.

Kairos son tres componentes: el servidor (`memory-api` y `memory-worker`), kairos-mcp (`memory-mcp`, con su propia configuración mínima, ver [kairos-mcp](#kairos-mcp)) y el cliente. El MCP interno del servidor está en desuso y se retira en la 0.5.0 (`MEMORY_MOUNT_MCP`, en la tabla de abajo).

## Archivos que se conservan

| Archivo | Uso | ¿Se publica en Git? |
|---|---|---|
| `docker-compose.yml` | Única definición de servicios, redes, volúmenes y secretos de la distribución | Sí |
| `.env.example` | Plantilla sin credenciales para una instalación | Sí |
| `.env` | Preferencias de esta instalación | No |
| `.private/memory-platform.env` | Referencia privada generada al directorio de secretos; la utiliza el despliegue | No |
| Directorio de secretos externo | Contraseñas de PostgreSQL, DSN y contraseña de bootstrap | No |

El script lee `.env` y después `.private/memory-platform.env`. Si el directorio de secretos ya está configurado, pasar otra ruta por `--secret-dir` provoca un rechazo; no se sustituyen credenciales. La limpieza de una carpeta de código no autoriza borrar volúmenes ni secretos externos.

## Opciones disponibles en `.env`

El Compose interpola estas opciones. Cambiarlas exige volver a desplegar los servicios correspondientes; no basta con recargar el navegador.

| Variable | Valor de ejemplo | Significado |
|---|---|---|
| `MEMORY_SECRETS_DIR` | `C:/docker-secrets/knowledge-memory` | Carpeta externa de secretos. En Linux configura una ruta del servidor |
| `MEMORY_LLM_MODEL` | Sin valor | Modelo de lenguaje para extracción y respuestas generadas; solo es obligatorio si se activa `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on` (sin él, el arranque falla nombrando la variable) |
| `MEMORY_EXTRACT_ENABLED` | `0` | Con `0`, el worker no crea el proveedor `extract` y un evento con `generate: true` se acepta sin trabajo `extract` (el recibo añade `extraction: "disabled"`) |
| `MEMORY_CORPUS_ANSWER` | `off` | Con `off`, `corpus_answer` sigue listada; una petición nueva responde `corpus_answer_disabled` sin llamar a ningún proveedor, repetir un `request_id` guardado con la misma petición y el mismo `MEMORY_LLM_MODEL` devuelve la respuesta guardada y con otra petición es un conflicto (si vacías o cambias el modelo al apagar, también: usa `corpus_answer_status`); `corpus_answer_status` lee las respuestas ya guardadas |
| `MEMORY_MOUNT_MCP` | `1` | `1` monta el MCP interno de `memory-api` (`/mcp/`), en desuso: cada respuesta lleva `Deprecation` y `Sunset` con la versión que lo retira (0.5.0) y se registra `mcp_legacy_used`; `0` no lo monta y `/mcp` responde 404. Otro valor detiene el arranque. `/mcp/` del puerto 5173 lo sirve kairos-mcp, sin depender de esta variable |
| `MEMORY_EMBEDDING_MODEL` | `nomic-embed-text` | Modelo de embeddings; sus vectores deben ser compatibles con los índices existentes |
| `OLLAMA_UPSTREAM` | `host.docker.internal:11434` | Destino `host:puerto` al que conecta el proxy interno de Ollama |
| `OLLAMA_ALLOW_CHAT` | `0` | Con `0`, el proxy interno de Ollama solo deja pasar `/api/embed` y `/api/version`; el resto recibe 403 desde el propio proxy. Con `1` deja pasar también `/api/chat`; solo hace falta si activas `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on` |
| `MEMORY_ALLOWED_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Orígenes exactos separados por comas, sin rutas ni barra final |
| `MEMORY_COOKIE_SECURE` | `0` local; `1` con HTTPS | Cookie de sesión segura. Un origen remoto exige HTTPS y valor `1` |

### Servidor sin modelo de lenguaje

Por defecto el servidor solo usa el modelo de embeddings (`nomic-embed-text`): no extrae ni genera texto. Tres variables lo gobiernan y las tres vienen apagadas o vacías:

- `MEMORY_EXTRACT_ENABLED=0`: el worker no crea el proveedor de extracción. Un evento con `generate: true` (el CLI lo envía en los resúmenes) se acepta igualmente con 202 y no crea trabajo `extract`; el recibo añade el campo `extraction: "disabled"` y conserva todos los demás. Los trabajos `extract` que ya estaban en cola no se borran: el worker no llama a ningún proveedor, los deja `failed` con `error_code` `extraction_disabled` y `POST /v1/jobs/{id}/retry` los devuelve a la cola si activas la extracción más adelante.
- `MEMORY_CORPUS_ANSWER=off`: `corpus_answer` sigue en la lista de herramientas (son 34) y una petición nueva responde el error `corpus_answer_disabled` sin llamar a ningún proveedor (repetir un `request_id` guardado con la misma petición y el mismo `MEMORY_LLM_MODEL` devuelve la respuesta guardada; con otra petición o con otro modelo, conflicto); `corpus_answer_status` sigue leyendo las respuestas ya guardadas. Los valores admitidos son `on` y `off`.
- `MEMORY_LLM_MODEL` no tiene valor por defecto. Activar `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on` sin un modelo hace fallar el arranque de `memory-api` y `memory-worker` con un mensaje que nombra la variable. Una instalación que usaba el modelo por defecto anterior debe fijar `MEMORY_LLM_MODEL` si quiere seguir generando. `MEMORY_EXTRACT_ENABLED` solo admite `0` y `1`; cualquier otro valor impide arrancar.

Si activas alguna de las dos funciones, pon también `OLLAMA_ALLOW_CHAT=1`: sin ello el proxy interno responde 403 a `/api/chat`.

La configuración actual se conserva durante una actualización. Cambiar el modelo de embeddings no convierte automáticamente los vectores ya guardados: planifica y verifica una migración de índice antes de hacerlo. El proxy Ollama no inicia sesión ni descarga modelos; su proveedor debe estar preparado.

## Opciones avanzadas de los procesos

Las siguientes variables las interpreta `server/memory_platform/config.py`. Para llegar a los contenedores deben estar declaradas en `x-memory-environment` del Compose. **El Compose ya propaga, con su valor por defecto, estas:** `MEMORY_EMBED_BATCH_TIMEOUT`, `MEMORY_EMBED_JOB_MAX_TIMEOUT`, `MEMORY_EMBED_BATCH`, `MEMORY_CHUNK_CHARS`, `MEMORY_CHUNK_OVERLAP`, `MEMORY_CHUNK_MAX`, `MEMORY_VECTOR_INDEXES`, `MEMORY_VECTOR_EXACT_FALLBACK_MS`, `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM`, `MEMORY_FUSION_K`, `MEMORY_FUSION_VALIDATED_BONUS`, `MEMORY_FUSION_WEIGHTS`, `MEMORY_ABSTAIN_THRESHOLDS`, `MEMORY_ABSTAIN_DEFAULT`, `MEMORY_METRICS` y `MEMORY_LOG_LEVEL`; basta con ponerlas en `.env` (Compose las interpola) y volver a desplegar `memory-api`, `memory-worker` y, para la migración, `memory-migrate`. Las demás (`MEMORY_SESSION_TTL`, `MEMORY_REQUEST_TIMEOUT`, `MEMORY_PROVIDER_TIMEOUT`, `MEMORY_LEASE_SECONDS`, `MEMORY_MAX_ATTEMPTS`, `MEMORY_WORKER_DB_BACKOFF_MAX`, `MEMORY_WORKER_WRITE_RETRY_SECONDS`, `MEMORY_MAX_BODY_BYTES`, `MEMORY_EMBED_QUERY_TIMEOUT`, `MEMORY_EMBED_WORKER_TIMEOUT`) solo llegan al contenedor si las añades a `x-memory-environment` o al entorno del proceso; añadirlas únicamente a `.env` no las introduce. **Tampoco las propaga el Compose las cinco del pool y los plazos de la base** (`MEMORY_POOL_MIN`, `MEMORY_POOL_MAX`, `MEMORY_POOL_TIMEOUT`, `MEMORY_CONNECT_TIMEOUT`, `MEMORY_STATEMENT_TIMEOUT_MS`) **ni las cuatro `MEMORY_TCP_*`**: sin añadirlas a `x-memory-environment` rigen sus valores por defecto. **Las cinco `MEMORY_RETENTION_*_DAYS` tampoco las propaga el Compose** y solo las lee `admin prune-tables`: se pasan en el comando, con `docker compose --profile memory-admin run --rm --no-deps -e MEMORY_RETENTION_AUDIT_EVENTS_DAYS=730 memory-admin prune-tables --dry-run` (ver [operaciones](operations.md#poda-de-tablas-prune-tables)). **Las seis `MEMORY_BACKUP_*` tampoco las propaga el Compose** y solo las leen `backup`, `verify-backup` y `backup-cycle`: se pasan en el comando (`docker compose --profile memory-admin run --rm --no-deps -e MEMORY_BACKUP_RECIPIENTS_FILE=/run/keys/recipients.txt -v <fichero-publico>:/run/keys/recipients.txt:ro memory-admin backup …`).

| Variable | Predeterminado del proceso | Uso |
|---|---|---|
| `MEMORY_DSN_FILE` | Requerido en el despliegue | Archivo montado que contiene el DSN; el Compose usa `/run/secrets/memory_dsn` |
| `MEMORY_PROJECT_MAP_FILE` | Sin archivo en ejecución directa | Mapa JSON del servidor; el Compose incluye `projects.example.json`. No sustituye los permisos de proyecto |
| `MEMORY_OLLAMA_URL` | `http://ollama:11434` | URL de proveedor; el Compose utiliza el proxy interno |
| `MEMORY_LLM_MODEL` | Sin valor | Modelo de lenguaje; obligatorio solo con `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on` |
| `MEMORY_EXTRACT_ENABLED` | `0` | Extracción en el servidor (`0` o `1`); el Compose la propaga con ese valor |
| `MEMORY_CORPUS_ANSWER` | `off` | Respuestas generadas de corpus (`on` u `off`); el Compose la propaga con ese valor |
| `MEMORY_MOUNT_MCP` | `1` | MCP interno en desuso (`1` o `0`), ver [integración](integration.md#migración-el-mcp-interno-queda-en-desuso-y-se-retira-en-la-050); el Compose la propaga con ese valor |
| `MEMORY_SESSION_TTL` | `43200` segundos | Duración de sesión del portal |
| `MEMORY_REQUEST_TIMEOUT` | `30` segundos | Límite general de solicitudes según el consumidor |
| `MEMORY_PROVIDER_TIMEOUT` | `180` segundos | Plazo del proveedor; las respuestas de corpus lo acotan como máximo a 180 segundos |
| `MEMORY_LEASE_SECONDS` | `240` segundos (1 a 86400) | Arrendamiento de trabajos del worker. Se valida **siempre** contra su rango (también con `MEMORY_WORKER_WRITE_RETRY_SECONDS` fijado: de él salen el latido y las esperas del worker); fuera de él impide arrancar API, worker y admin |
| `MEMORY_MAX_ATTEMPTS` | `3` | Intentos máximos de trabajos gestionados; no activa reintentos de respuestas generadas de corpus. Entero de 1 o más (otro valor impide arrancar API, worker y admin). También es el tope de reclamos de un trabajo cuya concesión expira: al alcanzarlo pasa a `failed` con `attempts_exhausted` (ver [operaciones](operations.md#el-worker-sin-base-de-datos-y-los-trabajos-agotados)) |
| `MEMORY_WORKER_WRITE_RETRY_SECONDS` | igual a `MEMORY_LEASE_SECONDS` (240 s; 1 a 86400) | Presupuesto de tiempo, por escritura, con el que el worker repite `complete_job`/`fail_job` tras un fallo de la base (desde el primer fallo); además se rinde tras 5 escrituras fallidas seguidas. Agotado, deja de renovar la concesión y el trabajo vuelve a la cola al vencer (`job_write_abandoned`, `retry_budget`). Una caída más larga que lo que le queda a la concesión (entre dos tercios de `MEMORY_LEASE_SECONDS` y la concesión entera) puede costar el intento: si esperas caídas largas, sube `MEMORY_LEASE_SECONDS`. Su valor por defecto es `MEMORY_LEASE_SECONDS`, que se valida siempre contra el rango 1 a 86400 (fijes o no este presupuesto): una concesión fuera de él impide arrancar API, worker y admin. La valida `Settings.from_env()` en todos los procesos. Ver [operaciones](operations.md#el-worker-sin-base-de-datos-y-los-trabajos-agotados) |
| `MEMORY_WORKER_DB_BACKOFF_MAX` | `60` segundos (1 a 3600) | Espera máxima del worker entre dos reclamos mientras la base de datos no responde: crece 1, 2, 4… s con *jitter* hasta este tope y vuelve a empezar tras un acceso correcto; el worker usa la misma espera para repetir la escritura del resultado de un trabajo. La valida `Settings.from_env()` en todos los procesos (un valor inválido impide arrancar la API y admin, no solo el worker), aunque solo el worker la usa. Ver [operaciones](operations.md#el-worker-sin-base-de-datos-y-los-trabajos-agotados) |
| `MEMORY_POOL_MIN` | `1` (1 a `MEMORY_POOL_MAX`) | Conexiones que mantiene abiertas el pool de conexiones de la API y el del worker (cada proceso, el suyo). Entero; un valor fuera de rango impide arrancar API, worker y admin. `admin` no usa pool. Ver [operaciones](operations.md#pool-de-conexiones-y-plazos-de-la-base) |
| `MEMORY_POOL_MAX` | `10` (1 a 100) | Máximo de conexiones de cada pool. Una transacción solo retiene una mientras dura; una búsqueda híbrida usa hasta 3 en paralelo. Lo que exceda el máximo espera `MEMORY_POOL_TIMEOUT`. Si lo subes, comprueba el `max_connections` de PostgreSQL (100 por defecto: API y worker suman hasta el doble de este valor) |
| `MEMORY_POOL_TIMEOUT` | `5` segundos (0,1 a 300) | Espera máxima de una transacción por una conexión del pool. Agotada sin ningún fallo de conexión ni de comprobación registrado desde la última conexión entregada (todas las conexiones en uso, o el pool aún creciendo bajo carga con la base sana), la API responde 503 `store_busy` con `request_id` (no se cuelga); si consta un fallo de conexión o de comprobación (la base no contesta), 503 `service_unavailable`; el worker trata ambos como una caída de la base (espera y reintenta sin gastar el intento del trabajo). **Debe diferir de `MEMORY_CONNECT_TIMEOUT` en al menos 1 s** (si no, el proceso no arranca: con el plazo de conexión por encima de la espera, el primer intento contra una base muda aún no ha fallado al vencer la espera y saldría `store_busy`) |
| `MEMORY_CONNECT_TIMEOUT` | `3` segundos (2 a 120, enteros) | Plazo para establecer una conexión de servicio (API y worker). Contra un servidor que acepta y no responde, el fallo llega en este plazo más un segundo, no en minutos. Con 1 libpq esperaría igualmente 2 s: por eso el mínimo es 2. Por defecto queda por debajo de `MEMORY_POOL_TIMEOUT` (regla de clasificación en [operaciones](operations.md#pool-de-conexiones-y-plazos-de-la-base)) |
| `MEMORY_TCP_KEEPALIVES_IDLE` | `30` segundos (1 a 7200) | Inactividad tras la que el kernel empieza a enviar sondas `keepalive` por las conexiones de servicio (API y worker). Enteros; un valor inválido impide arrancar |
| `MEMORY_TCP_KEEPALIVES_INTERVAL` | `10` segundos (1 a 600) | Intervalo entre sondas sin respuesta |
| `MEMORY_TCP_KEEPALIVES_COUNT` | `3` (1 a 20) | Sondas sin respuesta tras las que se da por muerta la conexión (con los valores por defecto, unos 60 s) |
| `MEMORY_TCP_USER_TIMEOUT_MS` | `30000` ms (1000 a 3600000) | `tcp_user_timeout`: cuánto puede estar un dato enviado sin confirmar antes de que el kernel corte la conexión. Junto a las anteriores cierra el caso de una conexión abierta cuyo par desapareció (ver «Conexión ya establecida que enmudece» en [operaciones](operations.md#pool-de-conexiones-y-plazos-de-la-base)); el plazo del lado del cliente de cada operación (`statement_timeout` más 5 s) lo cubre también en redes que sigan contestando a nivel TCP |
| `MEMORY_STATEMENT_TIMEOUT_MS` | Sin valor: `15000` en la API y `30000` en el worker (100 a 3600000, enteros) | `statement_timeout` de cada conexión de servicio (opción de la conexión: PostgreSQL cancela la consulta aunque el hilo de la aplicación ya no la espere). Con un valor, el mismo en la API y en el worker. **No lo heredan** `migrate`, `backfill-chunks`, `backup`, `content-manifest`, `inspect`, `prune-tables` ni `restore-check` (conexión directa de `admin`, sin plazo), y tampoco la búsqueda vectorial ni el respaldo de trigramas, que fijan el suyo (ver «Pool de conexiones y plazos» en [operaciones](operations.md#pool-de-conexiones-y-plazos-de-la-base)). Una consulta cancelada es 503 `store_timeout` en la API |
| `MEMORY_MAX_BODY_BYTES` | `262144` bytes | Tamaño máximo de cuerpo HTTP |
| `MEMORY_EMBED_ENABLED` | `1` | Indexación semántica; el Compose la activa explícitamente |
| `MEMORY_EMBED_QUERY_TIMEOUT` | `10` segundos | Plazo de embeddings de consulta |
| `MEMORY_EMBED_WORKER_TIMEOUT` | `120` segundos | Plazo de embeddings del worker |
| `MEMORY_EMBED_BATCH` | `8` | Fragmentos por petición a `/api/embed` (1 a 64). Ver [troceado](operations.md#troceado-de-documentos-y-notas-largas) |
| `MEMORY_EMBED_BATCH_TIMEOUT` | `60` segundos | Plazo por lote de fragmentos (1 a 600); el plazo del trabajo es proporcional al número de lotes de `MEMORY_EMBED_BATCH` entradas |
| `MEMORY_EMBED_JOB_MAX_TIMEOUT` | `900` segundos | Tope del plazo de las **peticiones de fragmentos** de un trabajo de embeddings (1 a 3.600; no menor que el plazo por lote). **No es el tope del trabajo:** el trabajador le suma, cuando el texto tiene varios fragmentos y ya hay un vector de elemento guardado, una llamada más de texto único (`MEMORY_EMBED_WORKER_TIMEOUT`, 120 s) y 10 s de margen. Con los valores por defecto y el máximo de fragmentos (`MEMORY_CHUNK_MAX`=200, es decir 201 entradas) el trabajo puede durar hasta **1.030 s** (`worker_deadline`: 900 + 120 + 10; 910 s si no hay vector guardado), y con `MEMORY_EMBED_JOB_MAX_TIMEOUT=3600`, 3.730 s. Ver [troceado](operations.md#troceado-de-documentos-y-notas-largas) |
| `MEMORY_CHUNK_CHARS` | `1500` | Tamaño, en caracteres, de un fragmento de embeddings (200 a 6.000: el proveedor corta una entrada a 8.000) |
| `MEMORY_CHUNK_OVERLAP` | `200` | Solape entre fragmentos consecutivos; debe ser menor que la mitad de `MEMORY_CHUNK_CHARS` |
| `MEMORY_CHUNK_MAX` | `200` | Máximo de fragmentos por recurso (1 a 500); un texto que lo supere lo declara en el recibo (`chunks_truncated`), no se corta en silencio |
| `MEMORY_METRICS` | `internal` | Exposición de `GET /metrics` (formato de texto Prometheus): `internal` (solo peticiones que no llegan por un proxy: las que llevan `X-Forwarded-*`, `Forwarded` o `X-Real-IP` reciben 404), `admin` (credencial de administrador) u `off` (sin ruta). Otro valor impide arrancar. nginx (5173) y el ejemplo de Caddy nunca lo publican. Ver [observabilidad](operations.md#observabilidad-logs-y-metricas) |
| `MEMORY_LOG_LEVEL` | `INFO` | Nivel de los logs JSON de `memory-api` y `memory-worker` (`DEBUG`, `INFO`, `WARNING`, `ERROR`; un valor desconocido equivale a `INFO`). **Solo gobierna el logger `kairos`**: los registros de librerías de terceros (`mcp`, `uvicorn`, `asyncio`, `psycopg`…) nunca salen por debajo de `INFO` aunque el nivel sea `DEBUG`, porque a ese nivel el SDK de MCP vuelca los argumentos de cada llamada a herramienta, es decir, las consultas (CWE-532). Los eventos `kairos` en `DEBUG` solo llevan campos de vocabulario cerrado. Ver [observabilidad](operations.md#observabilidad-logs-y-metricas) |
| `MEMORY_VECTOR_INDEXES` | `nomic-embed-text:768` | Pares `modelo:dimensiones`, separados por comas, que tienen índice HNSW parcial (1 a 2.000 dimensiones; el nombre del modelo puede contener `:`). Lo lee la migración; vacío = ningún índice y todo por la ruta exacta |
| `MEMORY_VECTOR_EXACT_FALLBACK_MS` | `1500` | Tope, en milisegundos, de la comprobación exacta que sigue a una respuesta HNSW corta (entero positivo, 1 a 600000; un valor inválido impide arrancar). Cada consulta lo aplica como `statement_timeout` propio, limitado además por lo que quede del plazo global; ver «Búsqueda vectorial» más abajo |
| `MEMORY_RETENTION_LOGIN_ATTEMPTS_DAYS` | `30` días (1 a 36500) | Antigüedad desde la que `admin prune-tables` borra los intentos de inicio de sesión (`login_attempts`). En blanco equivale al valor por defecto. Solo la lee `prune-tables`: un valor inválido lo detiene con un mensaje claro (código 2) y no impide arrancar la API ni el worker. Ver [operaciones](operations.md#poda-de-tablas-prune-tables) |
| `MEMORY_RETENTION_WEB_SESSIONS_DAYS` | `30` días (1 a 36500) | Antigüedad desde la que se borran las sesiones del portal **caducadas o revocadas** (`web_sessions`); una sesión viva nunca se borra |
| `MEMORY_RETENTION_AUDIT_EVENTS_DAYS` | `365` días (1 a 36500) | Antigüedad desde la que se borran las filas de auditoría (`audit_events`) |
| `MEMORY_RETENTION_JOBS_FAILED_DAYS` | `90` días (1 a 36500) | Antigüedad (desde su última programación) desde la que se borran los trabajos `failed` huérfanos: sin recibo en `projection_receipts`, no citados por el recibo de un evento conservado y que no son de la versión actual de su documento o nota (ninguno de esos se borra nunca; ver [operaciones](operations.md#poda-de-tablas-prune-tables)) |
| `MEMORY_RETENTION_EVENTS_DAYS` | Sin valor: `events` **no se poda** (1 a 36500 para activarlo) | Antigüedad desde la que se borran los eventos de captura (`events`). **Cambia respuestas visibles** (`event_status`, la actividad por proyecto, `get_tool_uses` y la idempotencia de `ingest_event`) y se declara a la Iniciativa 7; actívala solo si lo has decidido. Podar `events` vuelve podables, en la misma ejecución, los trabajos que solo citaban los eventos borrados (ver [operaciones](operations.md#poda-de-tablas-prune-tables)) |
| `MEMORY_BACKUP_RECIPIENTS_FILE` | Sin valor: la copia es en claro salvo que se exija cifrado | Ruta (dentro del contenedor) de un fichero de claves **públicas** `age`, una por línea (`#` comenta). Con él, `admin backup` cifra la copia con `age` y la publica como `<nombre>.age`; un fichero con una clave privada, sin ninguna clave o ilegible detiene la copia (el mensaje nombra la variable, no la ruta). Solo lo leen `backup` y `verify-backup`. La clave privada **no** va al servidor ni al repositorio (ver [operaciones](operations.md#inspección-y-copia-de-base)) |
| `MEMORY_BACKUP_REQUIRE_ENCRYPTION` | `0` | `1`, `true`, `yes` u `on` exigen cifrado: sin `MEMORY_BACKUP_RECIPIENTS_FILE`, `backup` falla (`backup_encryption_required`) y no escribe nada. `0`, `false`, `no`, `off` o vacío lo desactivan; cualquier otro valor es un error estable (`backup_config_invalid`). **No abre la copia externa:** `backup-cycle` exige destinatarios (`backup_encryption_required`) tenga esta variable el valor que tenga |
| `MEMORY_BACKUP_KEEP` | `7` (1 a 100000) | Copias que conserva `admin backup --prune` cuando no se da `--keep N`: las `N` más recientes completas y verificadas de su propio patrón de nombre; nunca borra otros ficheros ni la última copia verificada |
| `MEMORY_BACKUP_DESTINATION` | Sin valor: `backup-cycle` se niega a ejecutarse | Destino de la copia externa: `dir:<ruta absoluta>` (un directorio montado, p. ej. `dir:/offsite`) o `rclone:<remoto>:<ruta>` (un remoto de `rclone.conf`). Un valor mal formado falla con `backup_destination_invalid` sin repetir el valor; el destino de otro tipo (`s3://…`, cadenas de conexión `:backend:`) se rechaza. **Exclusivo de una instalación:** la retención remota borra por los manifiestos que encuentra (ver [operaciones](operations.md)); solo recibe copias cifradas |
| `MEMORY_BACKUP_INTERVAL` | `24h` | Tiempo entre dos ciclos de `admin backup-cycle --loop`: un entero con unidad opcional `s`, `m`, `h` o `d` (sin unidad, segundos), de 1 segundo a 30 días. Un valor inválido falla con `backup_config_invalid` antes de escribir nada |
| `MEMORY_BACKUP_REMOTE_KEEP` | `30` (1 a 100000) | Copias que `backup-cycle` conserva en el destino externo: las `N` más recientes por la fecha de su manifiesto; solo se borra tras verificar el sha256 de la copia recién subida, y nunca con un fallo del destino o una copia que no coincide (`backup_keep_invalid` si no es válido) |
| `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` | `256MB` | `maintenance_work_mem` de la transacción de migración (construcción de los índices HNSW); tamaño como `256MB` o `1GB`. Solo lo lee `admin migrate` (el Compose lo pasa con este valor por defecto desde `x-memory-environment`); la migración construye los índices en serie (`max_parallel_maintenance_workers = 0`) para no depender de `/dev/shm`, que en un contenedor tiene 64 MB por defecto |

### Copia externa programada (`memory-backup`)

Servicio opcional del perfil `backup`: `docker compose --profile backup up -d memory-backup` (una instalación ya desplegada lo recoge solo en su próximo `up`; nada cambia hasta entonces). Ejecuta `admin backup-cycle --loop`: copia cifrada, verificación, subida a `MEMORY_BACKUP_DESTINATION`, lectura del sha256 en el destino y retención local (`MEMORY_BACKUP_KEEP`) y remota (`MEMORY_BACKUP_REMOTE_KEEP`) cada `MEMORY_BACKUP_INTERVAL`. Sin puertos publicados; usa solo la red de la base (con un destino `dir:` no tiene salida a Internet). Un destino `rclone:` necesita la red de salida (`egress`): se añade con `docker-compose.backup-rclone.yml` (ver abajo).

| Variable de `.env` | Predeterminado | Uso |
|---|---|---|
| `MEMORY_BACKUP_DESTINATION`, `MEMORY_BACKUP_INTERVAL`, `MEMORY_BACKUP_REMOTE_KEEP`, `MEMORY_BACKUP_KEEP` | ver arriba (`24h`, `30`, `7`) | El Compose las pasa al servicio |
| `MEMORY_BACKUP_REQUIRE_ENCRYPTION` | `1` en este servicio | El servicio se niega a escribir una copia en claro |
| `MEMORY_BACKUP_CONFIG_DIR` | `./backup-config` | Directorio del anfitrión que se monta de solo lectura en `/config`: `recipients.txt` (claves **públicas** `age`) y, con un destino `rclone:`, `rclone.conf` (los remotos y sus credenciales son del operador; nunca van al repositorio) |
| `MEMORY_BACKUP_OFFSITE_DIR` | `./offsite` | Directorio del anfitrión que se monta en `/offsite` para un destino `dir:/offsite` |

**Destino `rclone:` y red de salida.** `memory-backup` solo está en la red interna de la base: con `MEMORY_BACKUP_DESTINATION=dir:/offsite` no necesita nada más y no puede abrir conexiones a Internet. Con un destino `rclone:<remoto>:<ruta>` hace falta la red `egress`, y el Compose la añade solo a ese servicio con un fichero aparte: `docker compose -f docker-compose.yml -f docker-compose.backup-rclone.yml --profile backup up -d memory-backup`. Sin ese fichero un destino `rclone:` falla con `backup_offsite_failed` (el servicio no llega al remoto). Una instalación ya desplegada lo recoge solo en su próximo `up`.

**`rclone.conf`: propietario y permisos.** Contiene las credenciales del remoto: que lo lea el usuario del contenedor (uid `10001`) y nadie más. En el anfitrión: `chown 10001:10001 backup-config backup-config/rclone.conf && chmod 0500 backup-config && chmod 0400 backup-config/rclone.conf` (o `0600` en el fichero; también vale un grupo dedicado con gid `10001`). **Nunca `chmod 644` ni `666`** para «que funcione»: abre las credenciales a cualquier usuario del anfitrión. El directorio se monta de solo lectura (`:ro`); por eso los backends **OAuth** (Google Drive, Dropbox, OneDrive…), que renuevan su token reescribiendo `rclone.conf`, no pueden hacerlo: el token caduca y el ciclo falla con `backup_offsite_failed`. Usa un backend con credenciales estáticas (S3 compatible, SFTP, B2, WebDAV…) o renueva el token tú (`rclone config reconnect` en el anfitrión) y copia el fichero; quitar `:ro` es una decisión consciente del operador, no el valor por defecto.

La clave privada `age` no se monta en ningún servicio ni está en la imagen: el servicio cifra para las claves públicas y no puede descifrar. Un destino inaccesible se registra como `backup_offsite_failed` (solo el tipo de destino, nunca rutas ni credenciales), pone a 0 la métrica `kairos_backup_offsite_success` (junto con `kairos_backup_offsite_last_run_timestamp_seconds` se escribe en `kairos-offsite.prom` dentro del volumen de copias para un colector de ficheros de texto; `memory-api` no las expone), no borra ninguna copia local y el ciclo siguiente vuelve a enviar lo que falte; cualquier otro fallo del ciclo (base caída, `pg_dump`, cifrado, verificación local) pone también la métrica a 0 y, en el bucle, registra `backup_cycle_failed`. Solo se envían copias cifradas (una en claro del directorio local se omite y se avisa con `backup_offsite_plain_skipped`) y el destino debe ser exclusivo de una instalación. Comandos y restauración: [operaciones](operations.md).

### Sonda de ida y vuelta (`admin probe`)

Las lee `server/memory_platform/probe.py` (no `config.py`): `memory-admin` no las propaga (el servicio `memory-probe`, perfil `probe`, sí propaga `MEMORY_PROBE_URL`, `MEMORY_PROBE_INTERVAL`, `MEMORY_PROBE_TIMEOUT` y `MEMORY_QUEUE_STUCK_SECONDS`); con otro valor, pásalas al comando con `-e` o con las opciones de la línea de órdenes. Etapas, códigos de salida y aprovisionamiento: `docs/operations.md`, «Sonda de ida y vuelta».

| Variable | Predeterminado | Uso |
|---|---|---|
| `MEMORY_PROBE_TIMEOUT` | `120` (segundos, de 1 a 3600) | Presupuesto de todo el recorrido de `admin probe` (escribir, esperar el recibo `embed`, buscar, retirar). Con el worker parado la sonda falla en `index` con `timeout` en ese plazo; la retirada tiene 20 s propios (una ejecución dura como mucho `MEMORY_PROBE_TIMEOUT` + 20 s, más la purga que sigue: como mucho 25 s en total, 10 s para conectar y 15 s para toda ella); tras Ctrl-C o SIGTERM la retirada tiene 8 s y no hay purga (en un contenedor, `stop_grace_period: 15s`). Un valor que no es un número o está fuera de rango termina con `probe_failed` en la etapa `setup` (`timeout_invalid`) |
| `MEMORY_PROBE_INTERVAL` | `300` (segundos enteros, de 10 a 86400) | Espera entre el fin de una ejecución de `admin probe --loop` y el comienzo de la siguiente (el periodo real es la duración de una ejecución más este intervalo), lo que corre el servicio `memory-probe` (perfil `probe`). Solo segundos, sin unidad: el healthcheck del servicio usa el mismo número. Un valor fuera de rango termina con `interval_invalid` antes de ejecutar nada |
| `MEMORY_QUEUE_STUCK_SECONDS` | `900` (segundos) | Cuánto puede esperar el trabajo más antiguo de la cola (`kairos_jobs_oldest_pending_seconds`) antes de que `admin probe` avise con `queue_stuck` (evento de log, `queue` en el informe y salida distinta de 0). Un valor que no es un número positivo se ignora (`probe_setting_ignored`) y rige 900 |
| `MEMORY_PROBE_URL` | `http://memory-api:8790` | Dónde responde `/v1` visto desde el contenedor de la sonda: `http(s)://host[:puerto]` sin ruta, credenciales ni consulta (`url_invalid`). Opción `--url` |
| `MEMORY_PROBE_KEY_FILE` | `/backups/probe/kairos-probe.key` | Fichero (permisos 600) con el token de la clave de la sonda, que escribe `probe-provision` y lee `probe`. Opción `--key-file`. La clave nunca va en una variable ni en un argumento |
| `MEMORY_PROBE_METRICS_FILE` | `/backups/probe/kairos-probe.prom` | Fichero de texto de Prometheus con `kairos_probe_success`, `kairos_probe_stage_seconds{stage}`, `kairos_probe_last_run_timestamp_seconds` y `kairos_probe_last_success_timestamp_seconds`. Opción `--metrics-file` (vacío: no se escribe); si no se puede escribir, el comando sale con 1 (`probe_metrics_failed`) |
| `MEMORY_PROBE_HEARTBEAT_FILE` | junto al fichero de métricas, con el sufijo `.heartbeat` (`/backups/probe/kairos-probe.heartbeat`) | Fichero que `probe --loop` toca al empezar y al acabar cada ciclo y que lee el healthcheck de `memory-probe`; solo lo escribe el bucle (un `admin probe` a mano escribe el `.prom`, no este). Opción `--heartbeat-file` |

Los presupuestos de respuestas generadas se definen en `AnswerLimits`, en `corpus_answers.py`: no son variables `.env` ni un límite económico por organización. Sus unidades, límites de conversación, estados inciertos y ausencia de reenvío automático están en [consultas de corpus](corpus-generated-answers.md).

## Límites de memoria y CPU de los servicios

Todos los servicios del Compose declaran `mem_limit` y `cpus`, y cada uno tiene sus dos variables de `.env`: `MEMORY_<SERVICIO>_MEM_LIMIT` (un tamaño como `512m` o `2g`) y `MEMORY_<SERVICIO>_CPUS` (un decimal, como `0.5`). Los valores de memoria por defecto son los de un equipo local de 32 GB; la columna de la derecha propone valores para un VPS pequeño (4 GB de memoria, 2 vCPU). Todos los `cpus` valen `0` por defecto (sin cuota de CPU): `docker compose config` no pinta ningún `cpus` y el stack arranca en cualquier máquina, también con una sola vCPU. Un valor de `cpus` por encima del número de CPU del equipo y Docker rechaza el contenedor (`NanoCPUs > NumCPU`): el servicio no arranca; pon cuotas solo si conoces las CPU del anfitrión, y no más que ellas; los de la columna del VPS suponen 2 vCPU. Una instalación ya desplegada recoge los límites solo en su próximo `up`; un contenedor que supera su `mem_limit` lo mata Docker y `restart: unless-stopped` lo reinicia.

| Variable | Predeterminado (32 GB locales) | VPS pequeño (4 GB, 2 vCPU) | Servicio y motivo |
|---|---|---|---|
| `MEMORY_OLLAMA_MEM_LIMIT` | `256m` | `128m` | `ollama`: el proxy de lista de permitidos (nginx), sin estado |
| `MEMORY_OLLAMA_CPUS` | `0` | `0.5` | Ídem |
| `MEMORY_POSTGRES_MEM_LIMIT` | `4g` | `1536m` | `memory-postgres`: ver «Relleno» abajo |
| `MEMORY_POSTGRES_CPUS` | `0` | `1.5` | Ídem |
| `MEMORY_MIGRATE_MEM_LIMIT` | `512m` | `384m` | `memory-migrate`: cliente de la migración; la memoria de los índices es del servidor de la base |
| `MEMORY_MIGRATE_CPUS` | `0` | `1` | Ídem |
| `MEMORY_BOOTSTRAP_MEM_LIMIT` | `256m` | `128m` | `memory-bootstrap`: alta inicial de proyectos y claves |
| `MEMORY_BOOTSTRAP_CPUS` | `0` | `0.5` | Ídem |
| `MEMORY_FILES_MEM_LIMIT` | `128m` | `64m` | `memory-files`: solo ajusta propietarios del volumen de copias |
| `MEMORY_FILES_CPUS` | `0` | `0.25` | Ídem |
| `MEMORY_API_MEM_LIMIT` | `2g` | `1g` | `memory-api`: la API HTTP y el MCP interno en desuso; ver «Memoria de `memory-api`» abajo |
| `MEMORY_API_CPUS` | `0` | `1` | Ídem |
| `MEMORY_MCP_MEM_LIMIT` | `1g` | `512m` | `memory-mcp`: una respuesta de hasta 64 MiB se mantiene unas cinco veces (ver [kairos-mcp](#kairos-mcp)); por debajo de 512m una llamada grande puede matarlo |
| `MEMORY_MCP_CPUS` | `0` | `1` | Ídem; reserializa en su bucle de eventos respuestas de hasta 64 MiB (1-2 s con un núcleo): con media cuota el bloqueo se duplicaría y retrasaría las demás llamadas |
| `MEMORY_WORKER_MEM_LIMIT` | `1g` | `512m` | `memory-worker`: ver «Relleno» abajo |
| `MEMORY_WORKER_CPUS` | `0` | `1` | Ídem |
| `MEMORY_WEB_MEM_LIMIT` | `256m` | `128m` | `memory-web`: nginx con el portal y el manual |
| `MEMORY_WEB_CPUS` | `0` | `0.5` | Ídem |
| `MEMORY_ADMIN_MEM_LIMIT` | `1g` | `512m` | `memory-admin`: copias, restauraciones y mantenimiento (`admin …`) |
| `MEMORY_ADMIN_CPUS` | `0` | `1` | Ídem |
| `MEMORY_BACKUP_MEM_LIMIT` | `1g` | `512m` | `memory-backup` (perfil `backup`): cifrado y subida de la copia |
| `MEMORY_BACKUP_CPUS` | `0` | `0.5` | Ídem |
| `MEMORY_PROBE_MEM_LIMIT` | `256m` | `256m` | `memory-probe` (perfil `probe`): la sonda de ida y vuelta |
| `MEMORY_PROBE_CPUS` | `0` | `0.5` | Ídem |

**Los límites son topes, no reservas.** `mem_limit` solo fija hasta dónde puede crecer un contenedor; Docker no aparta esa memoria. En la columna del VPS los servicios de larga duración suman unos 4,25 GB de topes (`ollama` 128 + `memory-postgres` 1536 + `memory-api` 1024 + `memory-mcp` 512 + `memory-worker` 512 + `memory-web` 128 + `memory-backup` 512 MB, este último solo con el perfil `backup`; unos 3,75 GB sin él), más de lo que tiene un VPS de 4 GB, y es a propósito: los picos no coinciden. En reposo el conjunto ocupa del orden de 1,3 GB (la base unos 600 MB, la API y el worker unos 100-150 MB cada uno, el resto decenas de MB); el relleno de vectores sube la base y el worker (hasta ~2 GB entre los dos) cuando la API y el MCP están en reposo; la respuesta máxima sube la API (hasta ~0,5 GB) y el MCP (hasta ~0,4 GB) con la base en reposo; y la copia diaria corre unos minutos. El peor caso realista, con el sistema y el demonio de Docker (~0,5 GB), ronda los 3,2 GB. Lo que sí hay que hacer en 4 GB: añadir 1-2 GB de *swap* (con él, un pico puntual degrada en vez de que el núcleo mate un proceso del anfitrión) y no lanzar el relleno de vectores junto a un uso intenso; si el equipo tiene menos de 4 GB, usa el perfil `backup` en otra máquina y no bajes `memory-postgres` de `1536m` ni `memory-worker` de `512m`: es el mínimo con el que el relleno termina.

**Relleno (`memory-postgres` y `memory-worker`).** Un límite que mate estos dos durante el relleno de vectores lo repetiría sin fin (el trabajo vuelve a la cola al caducar la concesión). PostgreSQL construye los índices HNSW con `maintenance_work_mem` (256 MB por defecto, `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM`) en serie, y a eso se suman sus búferes compartidos (128 MB), las sesiones del pool y la caché de páginas del propio contenedor: unos 1,5 GB de trabajo, por eso `4g` en un equipo local y `1536m` como mínimo recomendado en un VPS. El worker conserva los vectores de los 200 fragmentos como máximo de un recurso (768 flotantes cada uno) varias veces mientras arma el recibo, unas decenas de MB, más el texto del recurso; `1g` deja un margen holgado y `512m` sigue siendo suficiente. Si subes `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` o `MEMORY_CHUNK_MAX`, sube también estos dos límites.

**Memoria de `memory-api`.** La respuesta más grande son 200 observaciones de unos 300 KB, y el campo `context` repite su contenido: un JSON de unos 120 MB y un pico de unos 360 MB mientras se construye (medido con `tracemalloc`: 200 observaciones × 300 KB). **El pool de conexiones no acota esa cuenta:** la petición suelta su conexión antes de construir la respuesta y el render se hace en el bucle de eventos, así que cuántas respuestas grandes hay a la vez en memoria depende de cuántos clientes las piden y de la velocidad con que se envían, no de `MEMORY_POOL_MAX`; el render en sí es serial (un pico de 360 MB cada vez) y las ya construidas esperan en memoria a que el cliente las lea. Con el proceso en reposo en unos 100 MB, el límite tolera, con una de ellas en pleno render (100 + 360 + k × 120): `2g` unas 14 respuestas máximas a la vez (k = 13; del orden de 16 si ninguna está en el render: 100 + 16 × 120 = 2020) y `1g` unas 5 (k = 4; del orden de 7 sin render: 100 + 7 × 120 = 940). Son valores holgados para un uso normal (la respuesta máxima exige 200 observaciones de 300 KB cada una), y por eso se conservan: `2g` por defecto y `1g` en el VPS. Pasados esos números, el contenedor muere por falta de memoria, y bajar el pool no lo evita: lo que acota la presión es limitar las peticiones simultáneas por cliente en el proxy inverso y no pedir a la vez respuestas máximas.

Los healthchecks de los servicios, la rotación de logs (`json-file`, 3 × 10 MB) y el caso Linux de `host.docker.internal` están en [operación](operations.md).

## kairos-mcp

El servicio `memory-mcp` del Compose (imagen `kairos-mcp`, puerto `8791` en una red interna compartida solo con `memory-api`) no tiene secretos, DSN ni variables `MEMORY_*`. Su configuración completa son estas variables del entorno del contenedor, que el Compose interpola desde `.env`:

| Variable | Predeterminado | Uso |
|---|---|---|
| `KAIROS_API_URL` | `http://memory-api:8790` (fijo en el Compose) | URL base de la API a la que traduce cada herramienta. Obligatoria: sin ella el proceso no arranca |
| `KAIROS_API_TIMEOUT` | `30` segundos | Plazo de cada petición a `/v1` (mayor que 0 y como máximo 600); una llamada completa dura como máximo 4 veces este plazo |
| `KAIROS_ALLOWED_ORIGINS` | el valor de `MEMORY_ALLOWED_ORIGINS` | Orígenes exactos cuyos nombres de host acepta la cabecera `Host` (protección frente a DNS rebinding), además de `localhost`, `127.0.0.1`, `[::1]` y `memory-mcp` |
| `KAIROS_MAX_BODY_BYTES` | `262144` bytes | Tamaño máximo de cuerpo de una petición MCP; iguálalo a `MEMORY_MAX_BODY_BYTES` |
| `KAIROS_VALIDATION_THREADS` | `1` | Validaciones de argumentos grandes (más de 1000 valores) de herramientas MCP que corren a la vez, cada una en un hilo fuera del event loop (de 1 a 64); las entradas pequeñas se validan en línea y no esperan, y una grande que espera su turno más de 5 s (constante, no configurable) recibe `Memory service temporarily unavailable` |

El contenedor `memory-mcp` lleva `mem_limit: 1g` por defecto en el Compose (`MEMORY_MCP_MEM_LIMIT`, ver [límites de los servicios](#límites-de-memoria-y-cpu-de-los-servicios)): una respuesta de `/v1` de decenas de MB (hasta 64 MiB; el servidor produce unos 52 MB como máximo) se mantiene unas cinco veces en memoria mientras se une, se interpreta y se recorta, y el límite acota el daño de varias llamadas grandes simultáneas (el contenedor se reinicia solo, `restart: unless-stopped`). Ajusta `MEMORY_MCP_MEM_LIMIT` si subes los límites de cuerpo y de respuesta del servidor.

El resto de lo que ve un cliente (credencial, dato no fiable, errores y topes de salida) está en [Integración](integration.md#conectar-con-kairos-mcp).

## Búsqueda vectorial (pgvector)

La búsqueda semántica usa la extensión pgvector con el operador de distancia coseno. Hay dos rutas, elegidas por modelo y dimensión del vector de consulta:

- **Ruta HNSW:** para cada par de `MEMORY_VECTOR_INDEXES` la migración crea un índice HNSW parcial (`WHERE model = … AND dims = …`). Cada consulta fija por transacción `hnsw.iterative_scan = relaxed_order`, `hnsw.max_scan_tuples = 20000` y `hnsw.ef_search = 100`; el escaneo iterativo sigue leyendo el índice hasta completar el número de aciertos aunque los filtros de permisos, proyecto, versión vigente, categorías y etiquetas descarten filas. Estos valores son constantes de `server/memory_platform/config.py`, no variables de entorno; con 2.600 vectores de 768 dimensiones dieron un recall@10 de 1,0 frente al coseno exacto para `ef_search` de 10 a 200 (`testing/hnsw-recall.json` de la iniciativa).
- **Ruta exacta:** cualquier otro modelo o dimensión (o más de 2.000 dimensiones) calcula el coseno exacto en SQL sobre los primeros 10.000 candidatos vigentes en orden estable de identidad.

`candidate_limit` indica el tope de la ruta usada (10.000 la exacta, 20.000 la HNSW). `candidates_truncated` es `true` si en la ruta exacta había más de 10.000 candidatos, o si en la HNSW la respuesta es corta y los vectores autorizados que cuentan superan 10.000 (el escaneo pudo detenerse en `max_scan_tuples`). Si el índice devuelve menos aciertos de los pedidos, se recorre **una sola vez** la ruta exacta sobre los vectores de ese modelo y dimensión en los proyectos **autorizados** (nunca el volumen de otros proyectos) que además son vigentes y cumplen los filtros de categorías y etiquetas de la consulta: hasta 10.000 candidatos el resultado exacto sustituye al del índice, porque un índice aproximado puede dejar inalcanzables vectores muy duplicados; por encima de 10.000, o si ese recorrido agota su propio tope (`MEMORY_VECTOR_EXACT_FALLBACK_MS`, por defecto 1500 ms y nunca más de lo que quede del plazo global), se devuelven las filas del índice marcadas como truncadas, aunque no quede ningún acierto, y `backends.semantic` pasa a `partial`. Si lo que se agota es el plazo global, el error sigue siendo `semantic_deadline_exceeded`. El recorrido corre en un punto de guardado (savepoint): al cancelarse se revierte y la transacción sigue sirviendo la lectura final.

Cambiar `MEMORY_VECTOR_INDEXES` no borra índices antiguos: ejecuta `admin migrate` para crear los nuevos y elimina los que sobren manualmente. Construir un índice nuevo en una base ya migrada toma un bloqueo `SHARE` sobre `memory.embeddings` (bloquea las escrituras de embeddings durante la construcción); por encima de unas 6,5·10^4 filas a 768 dimensiones el grafo deja de caber en los 256 MB de `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` y la construcción se vuelve mucho más lenta, así que conviene subir ese valor (ver [operación](operations.md#imagen-postgresql)). El Compose propaga `MEMORY_VECTOR_INDEXES` desde `.env` a `memory-migrate`, `memory-api` y `memory-worker`. Los vectores se escriben a la vez en `vector` (`double precision[]`, que permite el retroceso) y en `embedding` (pgvector).

## Fusión de capas de la búsqueda

La búsqueda combina las capas por fusión de rangos recíprocos: cada acierto suma `peso / (k + posición)` por capa y, si está validado y vigente, una bonificación. Se validan al arrancar y un valor fuera de rango impide el arranque.

| Variable | Predeterminado | Efecto |
|---|---|---|
| `MEMORY_FUSION_VALIDATED_BONUS` | `0.0001` | Bonificación (0 a 1) que suma un acierto validado y no sustituido. 0 desactiva la preferencia por lo validado. Equivale a un orden absoluto (lo validado primero) solo cuando supera la mayor puntuación RRF posible, la suma de los pesos de las capas dividida por `MEMORY_FUSION_K`: con k 60 y las cuatro capas con peso 1 es 0,0667 (en el conjunto de evaluación ya ocurre desde 0,02); con otros k o pesos el umbral cambia (con k pequeño y pesos altos, incluso 1 puede no bastar) |
| `MEMORY_FUSION_K` | `60` | Constante `k` de la fusión (entero de 1 a 1.000) |
| `MEMORY_FUSION_WEIGHTS` | vacío (peso 1 en todas) | Pesos por capa, `capa=peso,...`, con capas `episodic`, `documental`, `temporal` y `semantic` y pesos mayores que 0 y hasta 10 |

El Compose las propaga desde `.env` con estos mismos valores por defecto (`MEMORY_FUSION_WEIGHTS` vacío = peso 1 en todas las capas).

### Abstención

El parámetro `abstain` de la búsqueda responde «nada relevante» (`items: []`, `abstained: true`) cuando la mejor similitud semántica queda por debajo del umbral del modelo de embeddings y ninguna capa léxica aportó nada. La señal y sus reglas están en [arquitectura](architecture.md#abstención-la-señal-diseño-de-t-81). Está apagada por defecto y no hay umbrales hasta que la calibración los fije.

| Variable | Predeterminado | Efecto |
|---|---|---|
| `MEMORY_ABSTAIN_DEFAULT` | `off` | `on` abstiene también cuando la petición no trae `abstain` (la petición con `abstain` manda); `off` deja la respuesta idéntica a la anterior. Un valor distinto de `on` y `off` impide arrancar |
| `MEMORY_ABSTAIN_THRESHOLDS` | vacío (sin umbrales) | Umbral por modelo, `modelo=umbral,...`, con el umbral entre -1 y 1 (coseno). Un nombre con `=`, `;`, espacios u otros caracteres de un separador mal escrito, un umbral fuera de rango o un modelo repetido impiden el arrancar (el mensaje nombra la variable, no sus valores) |

El nombre del modelo se compara sin el sufijo `:latest` en los dos lados: `nomic-embed-text=0.55` sirve para `MEMORY_EMBEDDING_MODEL=nomic-embed-text:latest` y al revés; otra etiqueta (`:v2`) es otro modelo, y `nomic-embed-text` junto a `nomic-embed-text:latest` es un modelo repetido. Con `abstain` activo y sin umbral para el modelo, la búsqueda responde normal y añade `abstention: "uncalibrated"` siempre que la capa semántica haya terminado bien (con o sin aciertos); si esa capa está apagada, `degraded` o `partial` no hay señal y la respuesta lleva solo `abstained: false`. Una capa léxica caída, parcial o con el plazo de trigramas vencido (`fuzzy_timeout`) tampoco permite abstener. Cambiarlas exige volver a desplegar `memory-api`. Los valores predeterminados salen de `server/memory_platform/tests/retrieval_eval/fusion-tuning.json` (rejilla explorada y motivo). Cualquier cambio debe pasar la puerta `retrieval-eval`, que exige recall@5 ≥ 0,80, MRR ≥ 0,60 y que ningún subconjunto pierda más de 2 puntos de recall@5 frente a la línea base.

## Proyectos, categorías y permisos

Se gestionan desde **Configuración** del portal, con permiso de administración. Cada proyecto tiene identidad y política propias. `off` desactiva nuevas capturas; `summary` admite resúmenes y `full` requiere consentimiento explícito para contenido completo. Cambiar una política no elimina automáticamente registros ni colas pendientes.

Los permisos son `read`, `write`, `publish`, `validate` y `admin`, limitados además por los proyectos autorizados de la clave. Utiliza claves por integración y los permisos mínimos necesarios. Una clave de agente no sirve como contraseña del portal. Los permisos se resuelven una vez por transacción y la revocación de una clave, un usuario o una concesión vale desde la transacción siguiente de cualquier petición, y una transacción que espera un bloqueo vuelve a leerla al recibirlo (ver [arquitectura](architecture.md#permisos-por-transacción)).

Las categorías proceden de los metadatos del contenido; las etiquetas son listas de valores independientes. Mantén nombres consistentes. Las reglas usan la etiqueta exacta `kairos:rule`, conservando su categoría. No son instrucciones ejecutables ni se validan automáticamente.

## Configuración de clientes

El instalador necesita URL base, proyecto, raíz local y ruta a una clave privada. No introduce la clave en los archivos públicos del proyecto. La conexión MCP, la captura y la inyección de contexto son opciones separadas; el análisis local de código está apagado por defecto y requiere `--code-analysis on`.

`kairos doctor` avisa de una cola de capturas en disco que lleva demasiado tiempo sin entregarse: el umbral es 900 s y la variable de entorno `KAIROS_QUEUE_STALE_SECONDS` del proceso que lo ejecuta lo cambia (`docs/operations.md`, «Sonda de ida y vuelta»).

Consulta [instalación](install.md) para los archivos de Claude Code, Codex y OpenCode, actualización con `--replace`, consentimiento, outbox y recuperación. [Integración](integration.md) define las herramientas, identidades, recibos e idempotencia que debe respetar custom-agents.

## Aplicar y verificar cambios

1. Guarda una copia privada de la configuración y revisa qué procesos consumen cada opción.
2. Ejecuta `python scripts/deploy-memory.py` para revisar el plan.
3. Aplica con `python scripts/deploy-memory.py --apply` cuando corresponda a esta instalación.
4. Comprueba el resultado final, catálogo MCP y contenido con identidades y hashes. El estado de salud sólo confirma disponibilidad básica.

No ejecutes `down -v` como paso de configuración. Las instrucciones completas de copias, restauración y diagnóstico están en [operación](operations.md).
