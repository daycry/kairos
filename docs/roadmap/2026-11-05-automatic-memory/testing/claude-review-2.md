# Revisión independiente con Claude CLI

Fuentes: snapshot inmutable de 138 archivos. Herramientas disponibles: Read, Grep y Glob. Sin ejecución de pruebas ni acceso a servicios o credenciales.

# Segunda revisión de Kairos, candidato 0.1.1 (solo lectura)

## Veredicto

Las correcciones I-1 a I-9 y M-1 a M-6 están en el código y, en general, resuelven lo que se reportó. No he encontrado nada Critical, pero sí un hallazgo nuevo Important (N-1) que sale de la propia actualización 0.1.0 → 0.1.1. Antes de cerrar C-05 y C-08 sigue haciendo falta:

- **S-1:** aceptar el formato de hooks dentro de los clientes reales.
- **N-1:** blindar la actualización contra un dispatcher 0.1.0 que siga vivo.

Todo sale de leer el código; no he ejecutado nada. Las 139 pruebas de servidor, las 59 de cliente y la sonda declaradas no las he observado, y no las tomo como prueba de que no haya defectos.

### Cobertura real

| Estado | Archivos |
|---|---|
| **Leído completo** | Cliente: `install.mjs`, `hooks.mjs`, `config.mjs`, `files.mjs`, `opencode.mjs`, `lifecycle.mjs`, `lifecycle-config.mjs`, `outbox.mjs`, `dispatcher.mjs`, `capture.mjs`, `privacy.mjs`, `cli.mjs`. Servidor: `mcp.py`, `retrieval.py`, `worker.py`, `privacy.py`, `schema.sql`, `models.py` (líneas 1–170). Documentos: `claude-review.md`, `review-triage.md`, `review-fixes.md`, `tasks.md` (automatic-memory), `install.md` (líneas 76–155) |
| **Leído en parte** | `store.py` (completo salvo nada relevante omitido), `app.py` (15–264), `lifecycle.test.mjs` (1–120), `mcp.mjs` (por búsquedas), `agent_tools.py`, `activity.py`, `agent_store.py`, `integration.md` y `web/src` (por búsquedas). Para los tests solo he visto los nombres |
| **No revisado** | `scripts/*` (despliegue, backups, diagnose, admin), `admin.py`, `initialize.py`, `config.py`, `providers.py`, Dockerfiles, compose, nginx, portal web en detalle, cuerpos de la mayoría de tests, contratos exportados, `docs/roadmap/2026-11-04-native-product/tasks.md` en este pase |
| **No disponible** | El runtime real 0.1.0. N-1 depende de que se comporte como describió el primer pase |

**El criterio 6 (portal, despliegue y backups) sigue prácticamente sin revisar.** No extrapolo conclusiones a esas áreas.

---

## Verificación de las observaciones anteriores

| ID | Estado en el código | Evidencia | Pendiente o residual |
|---|---|---|---|
| I-1 | **Corregido** | El Node físico se registra en `install.mjs:32-38`, el daemon arranca con `data.node` (`lifecycle.mjs:117`) y el plugin valida contra el manifiesto (`opencode.mjs:13-17`). Test: `lifecycle.test.mjs:50-67` | El test simula otro `execPath` dentro de Node, no en Bun. Falta aceptación en OpenCode real |
| I-2 | **Corregido** | `store.py:437-438` pasa `embed=not technical`, que cubre `capture`, el modo heredado y `agent-activity` | Efecto lateral menor: una nota manual con `category=agent-activity` tampoco tendrá embedding |
| I-3 | **Corregido** | Presupuestos incrementales (`outbox.mjs:47-55`). Compacta sólo los terminales sin cuerpo (`118-123`). Checkpoint cada 128 escrituras o 1 MiB (`112`). Concilia los evictados con `capture_hash` (`dispatcher.mjs:65-75`) | Cada captura nueva hace ahora dos llamadas remotas (`capture_policy` y `event_status`) dentro del presupuesto IPC de 2,2 s |
| I-4 | **Corregido en lo principal** | Rotación con cursor (`dispatcher.mjs:100-103`), espera por fila si la política está en off o rebajada (`111-113`), fase `failed` (`122`, `149`), `retry`/`retire` (`outbox.mjs:150-159`) | Ver N-2: los rechazos de escritura siguen usando backoff global |
| I-5 | **Corregido** | Se conserva la posición del grupo propio (`hooks.mjs:51-70`). Test: `lifecycle.test.mjs:41-48` | — |
| I-6 | **Corregido (mecanismo)** | El modo `any` usa `websearch_to_tsquery` con OR (`store.py:34-39`). Exclusión de categorías en SQL (`528`, `575`) y en la capa semántica (`retrieval.py:105`) | No hay medición de relevancia. Con la configuración `simple`, las palabras vacías («the», «que») coinciden con casi todo. Ya está declarado como no medido |
| I-7 | **Corregido** | `asyncio.to_thread` en el middleware (`mcp.py:190-194`) y en `stored()` (`54-60`). En REST, las dependencias síncronas de FastAPI ya van al threadpool | Sigue sin pool de conexiones, y la autenticación comparte el ejecutor por defecto con búsquedas lentas (ver S-2b) |
| I-8 | **Corregido con riesgo nuevo** | `install.mjs:29-31`, `config.mjs:10`, `allowed()` en `install.mjs:15-16`. Test: `lifecycle.test.mjs:69-96` | El test fabrica la versión «0.1.0» copiando ficheros de 0.1.1 y cambiando el texto; no usa el artefacto real. Ver N-1 |
| I-9 | **Corregido** | Coincidencia por sufijo `(?:^|_)` y camelCase (`privacy.mjs:4`, `privacy.py:25,29-31`), más tokens de proveedor (`privacy.mjs:55`, `privacy.py:22`) | Ver N-6: quedan huecos habituales (`PGPASSWORD`, `mongodb://`) |
| M-1 | **Corregido** | Fingerprint verificado (`store.py:353-357`), cuerpo de `summary` restringido (`363-369`), `full` exige `full` en servidor (`410-411`) | Una transcripción enviada como nota manual sigue sin detectarse; está declarado |
| M-2 / M-3 / M-6 | **Corregido (documentación)** | `install.md:102`, `install.md:142`, `integration.md:146` | — |
| M-4 | **Riesgo aceptado y documentado** | `opencode.mjs:50` sigue en `output.system`, con delimitación de datos no confiables (`dispatcher.mjs:93`) | Pendiente de aceptación del comportamiento real del agente |
| M-5 | **Corregido** | `worker.py:76-78` | — |
| S-1 | **Abierto** | `hooks.mjs:19-20`. El implementador cita la documentación oficial; yo no puedo comprobarla sin red | Sólo se cierra con C-08 en Claude Code y Codex reales |
| S-2 | **Memoria: corregido. CPU y latencia: abierto** | Cursor de servidor en lotes de 128 y top-100 con `bisect` (`store.py:940-990`) | Ver S-2b |
| S-3 | **Corregido** | La guarda `queue.recovery.lock` se toma en toda adquisición (`outbox.mjs:23-39`) | Si el proceso cae con la guarda tomada, el diagnóstico es el mismo `capture_state_busy` (`26`) que con un propietario vivo, así que el operador no puede distinguirlos |

---

## Hallazgos nuevos

### Critical
Ninguno.

### Important

**N-1. Un dispatcher 0.1.0 que sigue vivo intercepta los hooks 0.1.1 y nunca llega a cerrarse por inactividad.**
- **Dónde:**
  - `lifecycle.mjs:115` da por bueno el dispatcher si `/status` responde 200.
  - El endpoint no lleva la versión del runtime (`lifecycle.mjs:67`, `88-89`).
  - Cada petición IPC, aunque falle, renueva `lastActivity` (`lifecycle.mjs:47`, `79`).
- **Escenario:**
  1. Se ejecuta `install --replace` mientras hay sesiones abiertas y el daemon 0.1.0 vivo.
  2. Los hooks 0.1.1 leen el mismo `endpoint.json` (el binding y la carpeta no cambian), reciben 200 en `/status` y mandan `/capture` y `/context` al daemon antiguo.
  3. Este llama a su `loadInstallation`, que rechaza el manifiesto 0.1.1 con `not_installed` y devuelve 503.
  4. Cada intento renueva su actividad, así que no se cierra mientras los hooks sigan llegando al menos cada 15 minutos. Mientras tanto retiene `queue.lock`, y el daemon nuevo no puede arrancar.
- **Consecuencia:** captura y contexto quedan caídos de forma indefinida. Sólo se ve como `kairos: …` en stderr, y `status` muestra datos del daemon antiguo.
- **Mitigación actual:** `install.md:140` pide cerrar sesiones y esperar 15 minutos, pero el sistema no detecta que se haya omitido ese paso.
- **Certeza:** media-alta. El código 0.1.0 no está en la copia; me baso en la descripción del primer pase. Para confirmarlo hay que ejecutar un hook 0.1.1 contra un daemon 0.1.0 real.
- **Tests:** el test de actualización (`lifecycle.test.mjs:69`) no arranca ningún daemon. Falta esa regresión.
- **Propuesta:** incluir `runtime.version` en `endpoint.json` y en `/status`. `ensureDispatcher` debería rechazar una versión distinta con un diagnóstico explícito, y `doctor` debería informar de ello.

### Minor (defectos o imprecisiones demostrables)

**N-2. Los rechazos deterministas de `remember` no esperan por fila.**
- **Dónde:** `dispatcher.mjs:124-131`.
- **Escenario:** el servidor devuelve `mcp_tool_rejected` (todas las excepciones del servidor se mapean así en `mcp.py:46-52`). La excepción corta el lote, aplica backoff global y la fila queda en `unknown` sin `next_attempt_at`. Si todas las filas fallan igual (por ejemplo, cliente 0.1.1 contra un servidor 0.1.0 que rechaza el campo `capture`), `failures` nunca se reinicia. Se procesa una fila cada 60 s; vaciar 200 filas × 5 intentos lleva horas, y mientras tanto la cola llega a `capture_queue_full`.
- **Contradicción:** `install.md:121` afirma que «la espera por registro permite que avance el resto de la cola».
- **Propuesta:** fijar `next_attempt_at` en la fila ante cualquier excepción de la fila, y no sólo con la política en off.
- **Tests:** `dispatcher.test.mjs:102` cubre filas atascadas, pero no un rechazo repetido.

**N-3. No hay forma soportada de descartar cuerpos pendientes tras retirar el consentimiento.**
- **Dónde:** `outbox.mjs:155-158` (`retire` sólo admite `failed`), `lifecycle.mjs:114` (`ensureDispatcher` falla si capture y context están en off) y `cli.mjs:81`.
- **Escenario:** con `full` activo, el servidor baja a `summary` o a `off`, o el usuario desinstala con `--capture off --context off`. Los cuerpos `pending`, que pueden contener prompts y resultados de herramientas, se quedan en `sources/` indefinidamente. `queue-retire` no sirve: exige la fase `failed` y un dispatcher activo. La documentación prohíbe borrarlos a mano. Si la política vuelve a `full`, se envían contenidos admitidos mucho antes.
- **Propuesta:** un `queue-purge`/`queue-retire` que funcione sin dispatcher y sobre `pending`/`unknown`, documentado en la sección de desactivación.

**N-4. Un único cuerpo corrupto o ausente apaga también el contexto.**
- **Dónde:** `restore()` valida todos los cuerpos (`outbox.mjs:87-88`, `95-97`) y cualquier fallo aborta el constructor del dispatcher.
- **Escenario:** basta un archivo de `sources/` borrado (antivirus o sincronización) o dañado. `readBytes` devuelve `null`, el parseo falla y salta `capture_source_corrupt`. El dispatcher no arranca nunca, `runHook` falla en `ensureDispatcher` y no hay contexto aunque esté en `auto`. `queue-retire` tampoco funciona, porque necesita el dispatcher.
- **Consecuencia:** contradice el criterio de que los fallos de contexto sean independientes de la captura.
- **Certeza:** alta en la lógica.
- **Propuesta:** poner en cuarentena la fila afectada (fase `failed` con `capture_source_corrupt`) en lugar de abortar, o permitir el contexto sin cola.

**N-5. Faltan índices para las consultas que crecen con la captura** (confirmación por `EXPLAIN`).
- **Dónde:** `schema.sql:11` no tiene índice en `events(project_id, created_at, id)`. Lo usan `list_activity` (`store.py:681`), que el SSE del portal sondea cada 2 s por pestaña (`activity.py:59-62`), y `history` (`store.py:657`).
- **Otros casos:**
  - `projection_receipts` no tiene índice para el `EXISTS` correlacionado de `search_documents` (`store.py:566-570`).
  - El contexto con `q=''` (`SessionStart` y OpenCode) ordena todos los ítems vivos del proyecto (`store.py:528`).
- **Impacto:** hoy es nulo porque los dos proyectos tienen la captura en off. Con la captura activa, cada uso de herramienta añade un evento.
- **Propuesta:** crear los índices y medir con `EXPLAIN ANALYZE` sobre unos 100.000 eventos.

**N-6. Quedan huecos de secretos muy habituales en un producto basado en PostgreSQL.**
- **Dónde:** `privacy.mjs:4` y `privacy.py:25`.
- **Casos:**
  - `PGPASSWORD=…` y `MYSQL_PWD=…` no tienen `_` antes del sufijo, o usan `pwd`.
  - `mongodb://u:p@`, `amqp://` y `https://user:pass@host` quedan fuera del patrón DSN (`privacy.mjs:58`).
- **Matiz:** la documentación ya advierte que no hay detección universal, así que esto no es una regresión.
- **Propuesta:** añadir esos nombres y credenciales en URL genéricas (`scheme://user:pass@`).

**N-7. El cliente IPC no autentica al daemon** (sólo relevante en equipos multiusuario).
- **Dónde:** `lifecycle.mjs:92-110` y `137`.
- **Escenario:** tras una caída que deja `endpoint.json`, otro proceso local escucha en ese puerto, responde 200 a `/status` y recibe la entrada cruda del hook (prompt y salida de herramientas en `full`). Además, su `context` se inyecta como `additionalContext` sin validar.
- **Certeza:** alta en la lógica; probabilidad baja.
- **Propuesta:** que el daemon demuestre conocer el nonce, por ejemplo con un HMAC en la respuesta.

### Sospechas que necesitan ejecución

- **S-2b. Coste de CPU de la búsqueda semántica.**
  - **Dónde:** `store.py:975-990`.
  - **Coste:** el coseno se calcula en Python puro y psycopg decodifica `double precision[]`. Con 10.000 candidatos de 768 dimensiones son unos 8 millones de floats convertidos y unos 30 millones de operaciones con el GIL tomado: varios segundos por consulta.
  - **Agravantes:** `asyncio.timeout` (`retrieval.py:100`) no cancela el hilo, y ese ejecutor lo comparte ahora la autenticación MCP (I-7). Bajo carga, la autenticación podría encolarse detrás de búsquedas abandonadas.
  - **Además:** `has_vectors` (`store.py:955`) ejecuta antes de cada búsqueda la misma CTE con `ORDER BY … LIMIT 1`.
  - **Para confirmarlo:** medir p95 con N clientes concurrentes y `EXPLAIN` de `has_vectors`.
- **S-1:** sin cambios. Se cierra sólo con la aceptación nativa.

### Funcionalidades planificadas pendientes (no son defectos)
- Aceptación dentro de Claude Code, Codex y OpenCode (C-08).
- Despliegue del parche de servidor.
- Publicación en npm.
- A-02 a A-08.

### Lagunas de tests
- I-8 y la migración v1 se prueban con datos fabricados a partir de 0.1.1. Falta una prueba con el tarball 0.1.0 real y su cola.
- Faltan regresiones para N-1 (dispatcher de otra versión), N-2 (rechazo repetido), N-3 (purga con la automatización apagada) y N-4 (`source` ausente con contexto activo).

### Áreas sin defectos nuevos (dentro de lo leído)
- Fusión de JSON y TOML y preservación de ajustes ajenos.
- Journal de instalación y recuperación.
- Bloqueos de instalación.
- Fingerprint entre cliente y servidor: la canonicalización de JS y Python coincide para el payload que se envía.
- Idempotencia de `ingest_event` y `publish_document`.
- Revocación comprobada en cada llamada.
- Validación de receipts en el dispatcher.
- Portal: no usa `innerHTML` y gestiona el 401 (sólo lo he comprobado con búsquedas).

## Acciones prioritarias

1. **Corregir N-1** con la versión en el endpoint, rechazo en `ensureDispatcher` y comprobación en `doctor`. Añadir una regresión con el artefacto 0.1.0 real antes de desplegar el parche en clientes con sesiones activas.
2. **Ejecutar C-08 en los tres clientes reales** para cerrar S-1, I-1 (Bun) y M-4 antes de marcar C-05 y C-06 como aceptadas.
3. **Dar al outbox salidas seguras:** espera por fila ante rechazos (N-2), purga o retirada sin dispatcher y sobre filas `pending` (N-3) y cuarentena de cuerpos corruptos sin tumbar el contexto (N-4).
4. **Antes de activar la captura en algún proyecto,** añadir los índices de N-5 y hacer una prueba de carga de la búsqueda semántica concurrente con la autenticación (S-2b).
5. **Revisar el criterio 6,** que sigue sin cubrir: scripts de despliegue y backup, Dockerfiles y compose, y el portal en detalle.
