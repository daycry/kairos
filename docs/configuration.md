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

Los presupuestos de respuestas generadas se definen en `AnswerLimits`, en `corpus_answers.py`: no son variables `.env` ni un límite económico por organización. Sus unidades, límites de conversación, estados inciertos y ausencia de reenvío automático están en [consultas de corpus](corpus-generated-answers.md).

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
