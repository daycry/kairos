# Configuración de Kairos

La configuración del servidor, las políticas de proyecto y la configuración del cliente son capas distintas. Cambiar una no modifica automáticamente las otras.

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
| `MEMORY_LLM_MODEL` | `beam:cloud` | Modelo usado para generación y extracción; debe estar disponible en el proveedor |
| `MEMORY_EMBEDDING_MODEL` | `nomic-embed-text` | Modelo de embeddings; sus vectores deben ser compatibles con los índices existentes |
| `OLLAMA_UPSTREAM` | `host.docker.internal:11434` | Destino `host:puerto` al que conecta el proxy interno de Ollama |
| `MEMORY_ALLOWED_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Orígenes exactos separados por comas, sin rutas ni barra final |
| `MEMORY_COOKIE_SECURE` | `0` local; `1` con HTTPS | Cookie de sesión segura. Un origen remoto exige HTTPS y valor `1` |

La configuración actual se conserva durante una actualización. Cambiar el modelo de embeddings no convierte automáticamente los vectores ya guardados: planifica y verifica una migración de índice antes de hacerlo. El proxy Ollama no inicia sesión ni descarga modelos; su proveedor debe estar preparado.

## Opciones avanzadas de los procesos

Las siguientes variables las interpreta `memory_platform/config.py`. Para usarlas mediante Docker deben declararse explícitamente en `x-memory-environment` del Compose o en el entorno del proceso. Añadirlas únicamente a `.env` no las introduce automáticamente en el contenedor.

| Variable | Predeterminado del proceso | Uso |
|---|---|---|
| `MEMORY_DSN_FILE` | Requerido en el despliegue | Archivo montado que contiene el DSN; el Compose usa `/run/secrets/memory_dsn` |
| `MEMORY_PROJECT_MAP_FILE` | Sin archivo en ejecución directa | Mapa JSON del servidor; el Compose incluye `projects.example.json`. No sustituye los permisos de proyecto |
| `MEMORY_OLLAMA_URL` | `http://ollama:11434` | URL de proveedor; el Compose utiliza el proxy interno |
| `MEMORY_SESSION_TTL` | `43200` segundos | Duración de sesión del portal |
| `MEMORY_REQUEST_TIMEOUT` | `30` segundos | Límite general de solicitudes según el consumidor |
| `MEMORY_PROVIDER_TIMEOUT` | `180` segundos | Plazo del proveedor; las respuestas de corpus lo acotan como máximo a 180 segundos |
| `MEMORY_LEASE_SECONDS` | `240` segundos | Arrendamiento de trabajos del worker |
| `MEMORY_MAX_ATTEMPTS` | `3` | Intentos máximos de trabajos gestionados; no activa reintentos de respuestas generadas de corpus |
| `MEMORY_MAX_BODY_BYTES` | `262144` bytes | Tamaño máximo de cuerpo HTTP |
| `MEMORY_EMBED_ENABLED` | `1` | Indexación semántica; el Compose la activa explícitamente |
| `MEMORY_EMBED_QUERY_TIMEOUT` | `10` segundos | Plazo de embeddings de consulta |
| `MEMORY_EMBED_WORKER_TIMEOUT` | `120` segundos | Plazo de embeddings del worker |
| `MEMORY_EMBED_BATCH_TIMEOUT` | `60` segundos | Plazo por lote de fragmentos (1 a 600); el plazo del trabajo es proporcional al número de lotes de `MEMORY_EMBED_BATCH` entradas |
| `MEMORY_EMBED_JOB_MAX_TIMEOUT` | `900` segundos | Tope global del plazo de un trabajo de embeddings con varios fragmentos (1 a 3.600; no menor que el plazo por lote). Ver [troceado](operations.md#troceado-de-documentos-y-notas-largas) |
| `MEMORY_VECTOR_INDEXES` | `nomic-embed-text:768` | Pares `modelo:dimensiones`, separados por comas, que tienen índice HNSW parcial (1 a 2.000 dimensiones; el nombre del modelo puede contener `:`). Lo lee la migración; vacío = ningún índice y todo por la ruta exacta |
| `MEMORY_VECTOR_EXACT_FALLBACK_MS` | `1500` | Tope, en milisegundos, de la comprobación exacta que sigue a una respuesta HNSW corta (entero positivo, 1 a 600000; un valor inválido impide arrancar). Cada consulta lo aplica como `statement_timeout` propio, limitado además por lo que quede del plazo global; ver «Búsqueda vectorial» más abajo |
| `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` | `256MB` | `maintenance_work_mem` de la transacción de migración (construcción de los índices HNSW); tamaño como `256MB` o `1GB`. Solo lo lee `admin migrate` (el Compose lo pasa con este valor por defecto desde `x-memory-environment`); la migración construye los índices en serie (`max_parallel_maintenance_workers = 0`) para no depender de `/dev/shm`, que en un contenedor tiene 64 MB por defecto |

Los presupuestos de respuestas generadas se definen en `AnswerLimits`, en `corpus_answers.py`: no son variables `.env` ni un límite económico por organización. Sus unidades, límites de conversación, estados inciertos y ausencia de reenvío automático están en [consultas de corpus](corpus-generated-answers.md).

## Búsqueda vectorial (pgvector)

La búsqueda semántica usa la extensión pgvector con el operador de distancia coseno. Hay dos rutas, elegidas por modelo y dimensión del vector de consulta:

- **Ruta HNSW:** para cada par de `MEMORY_VECTOR_INDEXES` la migración crea un índice HNSW parcial (`WHERE model = … AND dims = …`). Cada consulta fija por transacción `hnsw.iterative_scan = relaxed_order`, `hnsw.max_scan_tuples = 20000` y `hnsw.ef_search = 100`; el escaneo iterativo sigue leyendo el índice hasta completar el número de aciertos aunque los filtros de permisos, proyecto, versión vigente, categorías y etiquetas descarten filas. Estos valores son constantes de `memory_platform/config.py`, no variables de entorno; con 2.600 vectores de 768 dimensiones dieron un recall@10 de 1,0 frente al coseno exacto para `ef_search` de 10 a 200 (`testing/hnsw-recall.json` de la iniciativa).
- **Ruta exacta:** cualquier otro modelo o dimensión (o más de 2.000 dimensiones) calcula el coseno exacto en SQL sobre los primeros 10.000 candidatos vigentes en orden estable de identidad.

`candidate_limit` indica el tope de la ruta usada (10.000 la exacta, 20.000 la HNSW). `candidates_truncated` es `true` si en la ruta exacta había más de 10.000 candidatos, o si en la HNSW la respuesta es corta y los vectores autorizados que cuentan superan 10.000 (el escaneo pudo detenerse en `max_scan_tuples`). Si el índice devuelve menos aciertos de los pedidos, se recorre **una sola vez** la ruta exacta sobre los vectores de ese modelo y dimensión en los proyectos **autorizados** (nunca el volumen de otros proyectos) que además son vigentes y cumplen los filtros de categorías y etiquetas de la consulta: hasta 10.000 candidatos el resultado exacto sustituye al del índice, porque un índice aproximado puede dejar inalcanzables vectores muy duplicados; por encima de 10.000, o si ese recorrido agota su propio tope (`MEMORY_VECTOR_EXACT_FALLBACK_MS`, por defecto 1500 ms y nunca más de lo que quede del plazo global), se devuelven las filas del índice marcadas como truncadas, aunque no quede ningún acierto, y `backends.semantic` pasa a `partial`. Si lo que se agota es el plazo global, el error sigue siendo `semantic_deadline_exceeded`. El recorrido corre en un punto de guardado (savepoint): al cancelarse se revierte y la transacción sigue sirviendo la lectura final.

Cambiar `MEMORY_VECTOR_INDEXES` no borra índices antiguos: ejecuta `admin migrate` para crear los nuevos y elimina los que sobren manualmente. Construir un índice nuevo en una base ya migrada toma un bloqueo `SHARE` sobre `memory.embeddings` (bloquea las escrituras de embeddings durante la construcción); por encima de unas 6,5·10^4 filas a 768 dimensiones el grafo deja de caber en los 256 MB de `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` y la construcción se vuelve mucho más lenta, así que conviene subir ese valor (ver [operación](operations.md#imagen-postgresql)). `MEMORY_VECTOR_INDEXES` debe declararse en `x-memory-environment` del Compose, como el resto de variables avanzadas, para llegar a los contenedores. Los vectores se escriben a la vez en `vector` (`double precision[]`, que permite el retroceso) y en `embedding` (pgvector).

## Fusión de capas de la búsqueda

La búsqueda combina las capas por fusión de rangos recíprocos: cada acierto suma `peso / (k + posición)` por capa y, si está validado y vigente, una bonificación. Se validan al arrancar y un valor fuera de rango impide el arranque.

| Variable | Predeterminado | Efecto |
|---|---|---|
| `MEMORY_FUSION_VALIDATED_BONUS` | `0.0001` | Bonificación (0 a 1) que suma un acierto validado y no sustituido. 0 desactiva la preferencia por lo validado. Equivale a un orden absoluto (lo validado primero) solo cuando supera la mayor puntuación RRF posible, la suma de los pesos de las capas dividida por `MEMORY_FUSION_K`: con k 60 y las cuatro capas con peso 1 es 0,0667 (en el conjunto de evaluación ya ocurre desde 0,02); con otros k o pesos el umbral cambia (con k pequeño y pesos altos, incluso 1 puede no bastar) |
| `MEMORY_FUSION_K` | `60` | Constante `k` de la fusión (entero de 1 a 1.000) |
| `MEMORY_FUSION_WEIGHTS` | vacío (peso 1 en todas) | Pesos por capa, `capa=peso,...`, con capas `episodic`, `documental`, `temporal` y `semantic` y pesos mayores que 0 y hasta 10 |

Para llegar a los contenedores deben declararse en `x-memory-environment` del Compose, como el resto de variables avanzadas (el Compose por defecto no las declara y usa los valores predeterminados). Los valores predeterminados salen de `memory_platform/tests/retrieval_eval/fusion-tuning.json` (rejilla explorada y motivo). Cualquier cambio debe pasar la puerta `retrieval-eval`, que exige recall@5 ≥ 0,80, MRR ≥ 0,60 y que ningún subconjunto pierda más de 2 puntos de recall@5 frente a la línea base.

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
