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

Las siguientes variables las interpreta `server/memory_platform/config.py`. Para llegar a los contenedores deben estar declaradas en `x-memory-environment` del Compose. **El Compose ya propaga, con su valor por defecto, estas:** `MEMORY_EMBED_BATCH_TIMEOUT`, `MEMORY_EMBED_JOB_MAX_TIMEOUT`, `MEMORY_EMBED_BATCH`, `MEMORY_CHUNK_CHARS`, `MEMORY_CHUNK_OVERLAP`, `MEMORY_CHUNK_MAX`, `MEMORY_VECTOR_INDEXES`, `MEMORY_VECTOR_EXACT_FALLBACK_MS`, `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM`, `MEMORY_FUSION_K`, `MEMORY_FUSION_VALIDATED_BONUS`, `MEMORY_FUSION_WEIGHTS`, `MEMORY_METRICS` y `MEMORY_LOG_LEVEL`; basta con ponerlas en `.env` (Compose las interpola) y volver a desplegar `memory-api`, `memory-worker` y, para la migración, `memory-migrate`. Las demás (`MEMORY_SESSION_TTL`, `MEMORY_REQUEST_TIMEOUT`, `MEMORY_PROVIDER_TIMEOUT`, `MEMORY_LEASE_SECONDS`, `MEMORY_MAX_ATTEMPTS`, `MEMORY_WORKER_DB_BACKOFF_MAX`, `MEMORY_WORKER_WRITE_RETRY_SECONDS`, `MEMORY_MAX_BODY_BYTES`, `MEMORY_EMBED_QUERY_TIMEOUT`, `MEMORY_EMBED_WORKER_TIMEOUT`) solo llegan al contenedor si las añades a `x-memory-environment` o al entorno del proceso; añadirlas únicamente a `.env` no las introduce. **Las cinco `MEMORY_RETENTION_*_DAYS` tampoco las propaga el Compose** y solo las lee `admin prune-tables`: se pasan en el comando, con `docker compose --profile memory-admin run --rm --no-deps -e MEMORY_RETENTION_AUDIT_EVENTS_DAYS=730 memory-admin prune-tables --dry-run` (ver [operaciones](operations.md#poda-de-tablas-prune-tables)).

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
| `MEMORY_LEASE_SECONDS` | `240` segundos | Arrendamiento de trabajos del worker |
| `MEMORY_MAX_ATTEMPTS` | `3` | Intentos máximos de trabajos gestionados; no activa reintentos de respuestas generadas de corpus. Entero de 1 o más (otro valor impide arrancar API, worker y admin). También es el tope de reclamos de un trabajo cuya concesión expira: al alcanzarlo pasa a `failed` con `attempts_exhausted` (ver [operaciones](operations.md#el-worker-sin-base-de-datos-y-los-trabajos-agotados)) |
| `MEMORY_WORKER_WRITE_RETRY_SECONDS` | igual a `MEMORY_LEASE_SECONDS` (240 s; 1 a 86400) | Presupuesto de tiempo, por escritura, con el que el worker repite `complete_job`/`fail_job` tras un fallo de la base (desde el primer fallo); además se rinde tras 5 escrituras fallidas seguidas. Agotado, deja de renovar la concesión y el trabajo vuelve a la cola al vencer (`job_write_abandoned`, `retry_budget`). Una caída más larga que lo que le queda a la concesión (entre dos tercios de `MEMORY_LEASE_SECONDS` y la concesión entera) puede costar el intento: si esperas caídas largas, sube `MEMORY_LEASE_SECONDS`. La valida `Settings.from_env()` en todos los procesos. Ver [operaciones](operations.md#el-worker-sin-base-de-datos-y-los-trabajos-agotados) |
| `MEMORY_WORKER_DB_BACKOFF_MAX` | `60` segundos (1 a 3600) | Espera máxima del worker entre dos reclamos mientras la base de datos no responde: crece 1, 2, 4… s con *jitter* hasta este tope y vuelve a empezar tras un acceso correcto; el worker usa la misma espera para repetir la escritura del resultado de un trabajo. La valida `Settings.from_env()` en todos los procesos (un valor inválido impide arrancar la API y admin, no solo el worker), aunque solo el worker la usa. Ver [operaciones](operations.md#el-worker-sin-base-de-datos-y-los-trabajos-agotados) |
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
| `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` | `256MB` | `maintenance_work_mem` de la transacción de migración (construcción de los índices HNSW); tamaño como `256MB` o `1GB`. Solo lo lee `admin migrate` (el Compose lo pasa con este valor por defecto desde `x-memory-environment`); la migración construye los índices en serie (`max_parallel_maintenance_workers = 0`) para no depender de `/dev/shm`, que en un contenedor tiene 64 MB por defecto |

Los presupuestos de respuestas generadas se definen en `AnswerLimits`, en `corpus_answers.py`: no son variables `.env` ni un límite económico por organización. Sus unidades, límites de conversación, estados inciertos y ausencia de reenvío automático están en [consultas de corpus](corpus-generated-answers.md).

## kairos-mcp

El servicio `memory-mcp` del Compose (imagen `kairos-mcp`, puerto `8791` en una red interna compartida solo con `memory-api`) no tiene secretos, DSN ni variables `MEMORY_*`. Su configuración completa son estas variables del entorno del contenedor, que el Compose interpola desde `.env`:

| Variable | Predeterminado | Uso |
|---|---|---|
| `KAIROS_API_URL` | `http://memory-api:8790` (fijo en el Compose) | URL base de la API a la que traduce cada herramienta. Obligatoria: sin ella el proceso no arranca |
| `KAIROS_API_TIMEOUT` | `30` segundos | Plazo de cada petición a `/v1` (mayor que 0 y como máximo 600); una llamada completa dura como máximo 4 veces este plazo |
| `KAIROS_ALLOWED_ORIGINS` | el valor de `MEMORY_ALLOWED_ORIGINS` | Orígenes exactos cuyos nombres de host acepta la cabecera `Host` (protección frente a DNS rebinding), además de `localhost`, `127.0.0.1`, `[::1]` y `memory-mcp` |
| `KAIROS_MAX_BODY_BYTES` | `262144` bytes | Tamaño máximo de cuerpo de una petición MCP; iguálalo a `MEMORY_MAX_BODY_BYTES` |
| `KAIROS_VALIDATION_THREADS` | `1` | Validaciones de argumentos grandes (más de 1000 valores) de herramientas MCP que corren a la vez, cada una en un hilo fuera del event loop (de 1 a 64); las entradas pequeñas se validan en línea y no esperan, y una grande que espera su turno más de 5 s (constante, no configurable) recibe `Memory service temporarily unavailable` |

El contenedor `memory-mcp` lleva `mem_limit: 1g` en el Compose: una respuesta de `/v1` de decenas de MB (hasta 64 MiB; el servidor produce unos 52 MB como máximo) se mantiene unas cinco veces en memoria mientras se une, se interpreta y se recorta, y el límite acota el daño de varias llamadas grandes simultáneas (el contenedor se reinicia solo, `restart: unless-stopped`). Ajusta `mem_limit` si subes los límites de cuerpo y de respuesta del servidor.

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

El Compose las propaga desde `.env` con estos mismos valores por defecto (`MEMORY_FUSION_WEIGHTS` vacío = peso 1 en todas las capas). Los valores predeterminados salen de `server/memory_platform/tests/retrieval_eval/fusion-tuning.json` (rejilla explorada y motivo). Cualquier cambio debe pasar la puerta `retrieval-eval`, que exige recall@5 ≥ 0,80, MRR ≥ 0,60 y que ningún subconjunto pierda más de 2 puntos de recall@5 frente a la línea base.

## Proyectos, categorías y permisos

Se gestionan desde **Configuración** del portal, con permiso de administración. Cada proyecto tiene identidad y política propias. `off` desactiva nuevas capturas; `summary` admite resúmenes y `full` requiere consentimiento explícito para contenido completo. Cambiar una política no elimina automáticamente registros ni colas pendientes.

Los permisos son `read`, `write`, `publish`, `validate` y `admin`, limitados además por los proyectos autorizados de la clave. Utiliza claves por integración y los permisos mínimos necesarios. Una clave de agente no sirve como contraseña del portal.

Las categorías proceden de los metadatos del contenido; las etiquetas son listas de valores independientes. Mantén nombres consistentes. Las reglas usan la etiqueta exacta `kairos:rule`, conservando su categoría. No son instrucciones ejecutables ni se validan automáticamente.

## Configuración de clientes

El instalador necesita URL base, proyecto, raíz local y ruta a una clave privada. No introduce la clave en los archivos públicos del proyecto. La conexión MCP, la captura y la inyección de contexto son opciones separadas; el análisis local de código está apagado por defecto y requiere `--code-analysis on`.

Consulta [instalación](install.md) para los archivos de Claude Code, Codex y OpenCode, actualización con `--replace`, consentimiento, outbox y recuperación. [Integración](integration.md) define las herramientas, identidades, recibos e idempotencia que debe respetar custom-agents.

## Aplicar y verificar cambios

1. Guarda una copia privada de la configuración y revisa qué procesos consumen cada opción.
2. Ejecuta `python scripts/deploy-memory.py` para revisar el plan.
3. Aplica con `python scripts/deploy-memory.py --apply` cuando corresponda a esta instalación.
4. Comprueba el resultado final, catálogo MCP y contenido con identidades y hashes. El estado de salud sólo confirma disponibilidad básica.

No ejecutes `down -v` como paso de configuración. Las instrucciones completas de copias, restauración y diagnóstico están en [operación](operations.md).
