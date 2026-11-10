# Auditoría de Kairos y plan de mejora

- **Fecha**: 2026-11-10 · **Base**: rama `feat/retrieval-quality`, commit `dbe6aa6`
- **Método**: tres auditorías de solo lectura (backend, seguridad estática, operación/producto/roadmap). No se ejecutó nada contra la instalación desplegada. Los costes de rendimiento son por inspección de código, sin `EXPLAIN`.
- **Estado**: propuesta. No es un plan aprobado ni un ledger; cada ola se convierte en iniciativa con `/dev-cycle` cuando se decida.

## 1. Veredicto

El núcleo es sólido y conviene conservarlo: escrituras idempotentes con versionado y hash, cola con *fencing* y revalidación, degradación explícita (`partial`, `candidates_truncated`), autorización por proyecto en todas las rutas y herramientas, SQL parametrizado, contenedores endurecidos, 376 tests contra PostgreSQL real.

No hay hallazgos críticos. Los riesgos se concentran en cuatro frentes:

1. **Operación a ciegas**: el backend no escribe logs ni métricas; un fallo de código no se distingue de una caída de Ollama.
2. **Datos sin red**: las copias solo se hacen al desplegar, sin retención, cifrado, copia externa ni prueba de restauración.
3. **Robustez bajo fallo**: un error pasajero de la base marca trabajos como fallidos para siempre; sin pool de conexiones; sin plazos por defecto.
4. **Privacidad**: la redacción de secretos tiene huecos comprobados y el modelo por defecto (`beam:cloud`) puede sacar contenido de la máquina.

Además, la calidad de búsqueda combinada sigue por debajo del umbral (recall@5 0,54 frente a 0,80) hasta la tarea T-27, y nada de las fases 3-5 está desplegado: producción sigue en `functional-parity`.

## 2. Hallazgos

Severidad: **A** alta, **M** media, **B** baja. Esfuerzo: S (horas), M (1-3 días), L (más).

### 2.1 Backend

| ID | Sev. | Hallazgo | Evidencia | Esf. |
|---|---|---|---|---|
| B-01 | A | Sin logging en todo el paquete; los `except Exception` devuelven 503/`unavailable` sin traza | `app.py:81-83`, `retrieval.py:123,140`, `mcp.py:51`, `worker.py:72,118` | S |
| B-02 | A | Sin pool: una conexión nueva por transacción; una búsqueda abre 5+N y `_require` lanza 3 consultas por proyecto | `store.py:28`, `auth.py:58`, `store_auth.py:36-76` | M |
| B-03 | A | Un error transitorio de base en `complete_job` marca el trabajo `failed`; una caída de base en `claim_job` mata el worker | `worker.py:103,118-135`, `store_jobs.py:189` | S |
| B-04 | A | Sin CI, lint ni tipado; los tests solo corren con `docker build --target test` | raíz del repo, `tests/run_postgres.py:18` | M |
| B-05 | M | `claim_job` reclama sin tope de intentos un trabajo que tumba al worker | `store_jobs.py:91,104` | S |
| B-06 | M | El índice de la cola no sirve al `ORDER BY priority,…`; sin retención de `jobs`, `events`, `audit_events`, `login_attempts`, `web_sessions` | `schema.sql:19`, `store_jobs.py:91` | M |
| B-07 | M | Solo la búsqueda vectorial y el trigram fijan `statement_timeout`; `asyncio.timeout` sobre un hilo no cancela la consulta | `retrieval.py:111-115`, `store.py:28` | S |
| B-08 | M | `graph_data` filtra en Python tras `LIMIT`: pierde coincidencias y responde `partial: False` | `store_graph.py:79-106` | S |
| B-09 | M | `_vector_candidates` serializa con `to_jsonb` todo el proyecto antes de filtrar; `has_vectors` lo ejecuta en cada búsqueda | `store_vectors.py:287-311`, `retrieval.py:129` | S |
| B-10 | M | Consultas sin índice útil y N+1 (hechos, timeline, `get_tool_uses`, `list_users`, `event_status`) | `store_graph.py:27-47`, `portal_store.py:46-78`, `store_auth.py:180-182` | M |
| B-11 | M | Esquema repartido entre `schema.sql` y tres cadenas en Python; versión 5 registrada dos veces; `/health/ready` no exige versión | `store_auth.py:12-25`, `agent_store.py:47`, `extended_store.py:28`, `app.py:106` | M |
| B-12 | M | Configuración doble: `Settings` y lecturas de entorno en caliente; 18 `getattr` con valores por defecto duplicados | `store_vectors.py:63,247,354`, `config.py:192-210` | S |
| B-13 | M | El presupuesto de work-state es un tope duro sin purga: tras 10.000 entradas, 409 para siempre | `agent_store.py:184-186`, `extended_store.py:160-164` | S |
| B-14 | M | El embedding de consulta comparte `Semaphore(1)` con el worker; un `httpx.AsyncClient` por petición | `providers.py:28,93-104` | S |
| B-15 | M | Sin tests de: caída de base en el worker, `body_too_large`, `/v1/users`, `/health/ready`, `work_budget_exceeded`; tests frágiles que comparan texto SQL o trocean `schema.sql` por marcador | `tests/test_jobs.py`, `tests/test_chunk_schema.py:14-21` | M |
| B-16 | M | Contratos implícitos entre mixins y stores que llaman a privados; `work_write`/`team_write` duplicados | `agent_store.py:163-193`, `extended_store.py:139-176` | M |
| B-17 | B | Código muerto (`policy`, `stream`, `budget`, `needs_reconciliation`, `ProviderError.ambiguous`) | `store_documents.py:112`, `store_jobs.py:12,85`, `worker.py:109` | S |
| B-18 | B | Densidad: 519 líneas de más de 120 caracteres (máximo 1.200); SQL de una línea con 30 parámetros posicionales | `store_ingest.py:85,180`, `store_jobs.py:165` | M |
| B-19 | B | Solo se fijan dependencias directas, sin hashes; PyYAML va a producción y solo lo usan tests | `requirements.txt:1-7` | S |

### 2.2 Seguridad

| ID | Sev. | Hallazgo | Evidencia | Esf. |
|---|---|---|---|---|
| S-01 | M | La redacción no cubre `SECRET_KEY=`, `DB_PASS=`, `sk_live_`, `glpat-`, `hf_`, `curl -u`, ni las claves propias `mp_…` (comprobado con cadenas sintéticas) | `privacy.py:19-25`, `packages/kairos-cli/lib/privacy.mjs:4` | M |
| S-02 | M | El límite de login cuenta también los aciertos y, tras nginx, todos comparten IP: diez peticiones bloquean el login de todos | `auth.py:76-81`, `nginx.conf:48-53` | S |
| S-03 | M | No hay cambio de contraseña, deshabilitar usuario, retirar permisos ni revocar sesiones; las claves no caducan | `store_auth.py:161-192`, `app.py` | M |
| S-04 | M | El modelo por defecto `beam:cloud` y la red `egress` del proxy pueden enviar contenido fuera de la máquina sin aviso (**por confirmar si `:cloud` ejecuta en remoto**) | `config.py:159,201`, `docker-compose.yml:9,35-37` | S |
| S-05 | M | Solo `context`, `observation_context` y `team_brief` marcan el contenido como dato no fiable; `search`, `details`, `timeline` y otras devuelven texto crudo | `retrieval.py:204-218`, `mcp.py:149-169` | M |
| S-06 | B | Copia `pg_dump` sin cifrar en el mismo host | `admin.py:286-294` | S |
| S-07 | B | scrypt con N=2^14, por debajo de la recomendación actual | `auth.py:21-22` | S |
| S-08 | B | Sin cuota ni límite de tasa por clave; SSE sin tope | `app.py:85-96,320-335` | M |
| S-09 | B | El proxy de Ollama corre como root y expone toda la API (pull, delete, create); redes `inference` y `webui` con nombre fijo | `ollama-proxy/default.conf.template:13-25`, `docker-compose.yml:28-62,161-163` | S |
| S-10 | B | `./secrets` y `.private/` por defecto dentro del repo, que está en OneDrive | `docker-compose.yml:170-172`, `scripts/deploy-memory.py:342` | S |
| S-11 | B | El CLI no comprueba permisos del fichero de clave | `packages/kairos-cli/lib/files.mjs:64-70` | S |

### 2.3 Operación, CLI, portal y documentación

| ID | Sev. | Hallazgo | Evidencia | Esf. |
|---|---|---|---|---|
| O-01 | A | Copias solo al desplegar: sin retención, checksum, cifrado ni salida del volumen | `scripts/deploy-memory.py:303-304`, `admin.py:292-294` | M |
| O-02 | A | El despliegue nunca ejecuta `restore-check` | `admin.py:295-313` | M |
| O-03 | A | La copia y `content-manifest` usan el plazo de 120 s: con una base grande el despliegue aborta | `scripts/deploy-memory.py:210,300-334` | S |
| O-04 | A | Sin CI/CD, etiquetas, changelog ni imágenes versionadas; 10 commits sin subir; repo en OneDrive | sin `.github/`, `git tag` vacío | M |
| O-05 | M | Sin límites de recursos; worker y web sin healthcheck; postgres y ollama sin rotación de logs | `docker-compose.yml:28-62,123-146` | S |
| O-06 | M | Retroceso manual, sin bloqueo contra despliegues concurrentes; `host.docker.internal` no resuelve en Linux | `docs/operations.md:83,150-154`, `docker-compose.yml:32` | M |
| O-07 | A | El README instala desde un tarball que git ignora; npm sigue bloqueado | `README.md:159`, `.gitignore` | S |
| O-08 | M | El bloqueo del outbox se decide por PID vivo, sin comando de reparación | `packages/kairos-cli/lib/outbox.mjs:11-33` | M |
| O-09 | M | CLI: 83 tests sin cobertura y solo en Linux, con rutas específicas de Windows; los hooks fijan la ruta absoluta de Node | `packages/kairos-cli/lib/hooks.mjs:12-22`, `lib/install.mjs:34` | M |
| O-10 | M | Portal: `fetch` sin plazo; sin lint ni prueba de accesibilidad; `memory-portal.ts` de 702 líneas | `web/src/memory-api.ts:38-50` | M |
| O-11 | M | `MEMORY_CHUNK_*`, `MEMORY_EMBED_BATCH` y `MEMORY_VECTOR_INDEXES` no están en `configuration.md` ni los propaga Compose | `config.py:97`, `docker-compose.yml:3-16` | S |
| O-12 | M | README, `architecture.md`, `integration.md` y `manual.md` no reflejan las fases 3-5; `operations.md` mezcla runbook, historial y mediciones | `docs/operations.md:15-21,188-190` | M |
| O-13 | B | Sin CONTRIBUTING, LICENSE raíz ni CHANGELOG; ninguna iniciativa tiene retro; idioma mezclado y caracteres rotos en ledgers antiguos | `docs/roadmap/2026-11-05-automatic-memory/tasks.md:60-68` | S |

### 2.4 Utilidad como memoria de agentes

La auditoría anterior mide si lo construido está bien hecho. Estas mejoras cubren si lo que el agente recibe es cierto, vigente y oportuno. Ninguna está en los planes actuales salvo donde se indica.

| ID | Mejora | Qué resuelve | Relación con lo planificado | Esf. |
|---|---|---|---|---|
| M-01 | **Abstención**: umbral de relevancia calibrado con la puerta de evaluación y respuesta explícita «nada relevante» | Hoy se devuelven los mejores resultados aunque ninguno sea bueno | Nuevo; se apoya en T-27 | S |
| M-02 | **Vigencia anclada a evidencia**: cada recuerdo guarda a qué está anclado (fichero, commit, fecha); si el ancla cambia, se marca «posiblemente obsoleto» y baja en el orden | Recuerdos sobre código o decisiones que ya no son ciertos | Amplía el punto 7 (ciclo de vida) | M |
| M-03 | **Contradicciones**: detectar parejas «mismo tema, afirmación distinta» y resolverlas por sustitución o marca de conflicto | Dos recuerdos opuestos conviven y gana el que mejor puntúa | Reutiliza la maquinaria del punto 5 (casi-duplicados) | M |
| M-04 | **Filtro al escribir**: decidir al guardar si algo es duradero, reutilizable y no repetido | El ruido de la captura automática degrada la búsqueda | Complementa el punto 9 (consolidación), que limpia después | M |
| M-05 | **Evaluación con uso real**: registrar qué resultados usó, ignoró o corrigió el agente; conjunto de evaluación con consultas reales; medir la calidad de la extracción | La puerta actual son 72 consultas sintéticas con embeddings simulados | Se apoya en el punto 8 (`memory_feedback`) | M |
| M-06 | **Sonda de ida y vuelta**: escribir un recuerdo sintético, esperar al worker, buscarlo y retirarlo; alerta si la cola de envío del CLI acumula capturas | Pérdida silenciosa de memoria en cualquier eslabón | Nuevo; usa las métricas de la Fase 7 | S |
| M-07 | **Ámbito de usuario**: proyecto personal por usuario para preferencias que valen en todos los proyectos, incluido en el contexto de inicio | Todo cuelga de un proyecto (`project_id` obligatorio en todo el esquema) | Nuevo; sin cambio de esquema; se consume en el punto 10 | S |

Comprobado y **ya resuelto**: corregir y olvidar. `remember` admite correcciones, `observation_record_event` admite revisión, corrección y retirada, y `revoke_document` deja lápida; la búsqueda ignora lo borrado o sustituido, incluidos sus fragmentos.

## 3. Estado del roadmap

| Iniciativa | Estado | Pendiente |
|---|---|---|
| `native-product` (11-04) | 17 tareas hechas | Publicación npm (A-08), retro |
| `automatic-memory` (11-05) | 8 tareas hechas | Un candidato de conocimiento sin curar, retro |
| `functional-parity` (11-06) | Desplegada y verificada el 11-09 | Publicación npm (F-06) |
| `retrieval-quality` (11-09) | 25 de 38 tareas; fases 1-5 comiteadas; **pausada** | Fases 6-8 (T-26..T-38) |
| Puntos 6, 8, 5, 7, 10, 9 | Sin spec ni carpeta | Todo |

Deudas aceptadas en `retrieval-quality`, que este plan recoge: marcar filas antiguas con el índice real (medir en T-36), reescritura de filas idénticas, vector reutilizado con otras dimensiones, cancelación manual informada como tiempo agotado, desbordamiento de `float4` en la migración, combinaciones que faltan en el conjunto de evaluación.

## 4. Plan de mejora

Olas 0 a 6, con una 2-bis y una 3-bis. Cada una es desplegable por separado. **El orden vigente es el de la sección 6.4**, que tiene en cuenta el despliegue en VPS. El orden busca que nada nuevo llegue a producción sin copias probadas ni visibilidad.

### Ola 0 — Protección inmediata (horas, sin tocar código de producto)

| Acción | Cubre |
|---|---|
| Subir la rama `feat/retrieval-quality` al remoto | O-04 |
| Confirmar si `beam:cloud` ejecuta en remoto y decidir el modelo por defecto | S-04 |
| Copia manual de la base desplegada fuera del volumen y prueba de restauración en una base efímera | O-01, O-02 |
| Comprobar que el directorio de secretos real está fuera del repo y de OneDrive | S-10 |
| Corregir el README: instalación del CLI con `npm pack` o desde git | O-07 |

### Ola 1 — Cerrar `retrieval-quality` (fases 6-8), con cuatro ajustes

Se retoma tal cual está planificada, añadiendo:

- **Fase 6 (T-26..T-29)**: T-27 con «validado» como bonificación y la comprobación CA-35 en la puerta (ya decidido). Añadir a T-28 la comprobación de dimensiones del vector reutilizado (deuda de Fase 5) y B-09 (`has_vectors` como `EXISTS`, selección por identidades).
- **Fase 7 (T-30..T-33)**: ampliar T-30 para que el logging cubra todos los `except Exception` (B-01) y T-32 para medir saturación del semáforo de embeddings (B-14).
- **Fase 8**: T-34 absorbe O-11 y O-12. T-36 mide con Ollama real el plazo de documentos largos y el marcado de filas antiguas con índice HNSW.
- **Antes de T-38 (despliegue real)**: completar la Ola 2. Desplegar el esquema v8-v10 sin copias probadas ni plazo de copia ajustado (O-03) es el mayor riesgo del plan actual.

### Ola 2 — Iniciativa nueva «operación fiable» (previa al despliegue)

| Bloque | Contenido | Cubre |
|---|---|---|
| Copias | `backup --prune --keep N` con sha256, cifrado con clave externa, plazo propio, `--verify-backup` en el despliegue, runbook de restauración | O-01, O-02, O-03, S-06 |
| Worker | Distinguir errores de base de errores de proveedor, reintento con espera, tope de intentos en `claim_job`, índice parcial de cola | B-03, B-05, B-06 |
| Conexiones y plazos | `psycopg_pool`, `statement_timeout` y `connect_timeout` por defecto, actor y permisos resueltos una vez por transacción | B-02, B-07, S-08 (parte) |
| Despliegue | Límites de recursos, healthchecks, rotación de logs, bloqueo de despliegue, `--rollback-images`, `extra_hosts` | O-05, O-06 |
| CI | Workflow con suite backend, tests de CLI (matriz Windows/macOS/Linux) y web, `retrieval-eval`; ruff y mypy gradual; lock con hashes | B-04, B-19, O-04, O-09 |
| Tests | Integración worker+PostgreSQL con base caída, lease expirado y trabajo venenoso; límites sin cobertura | B-15 |
| Abstención | Umbral de relevancia y respuesta «nada relevante», calibrado con la puerta | M-01 |
| Sonda | Prueba periódica de ida y vuelta y alerta de cola de envío atascada | M-06 |

### Ola 3 — Iniciativa nueva «privacidad y control de acceso»

| Bloque | Contenido | Cubre |
|---|---|---|
| Redacción | Patrones ampliados, detector de entropía, test compartido backend/CLI | S-01 |
| LLM remoto | Modelo local por defecto u opt-in explícito, documentado | S-04 |
| Credenciales | Cambio de contraseña con revocación de sesiones, deshabilitar usuario, retirar permisos, caducidad y rotación de claves, scrypt reforzado con rehash | S-03, S-07 |
| Login | Contar solo fallos, IP real desde proxy de confianza, purga | S-02 |
| Contenido no fiable | Envoltorio delimitado y `warning` en todas las herramientas de lectura (cambio aditivo del contrato) | S-05 |
| Superficie | Lista blanca de rutas en el proxy de Ollama, proxy sin root, validación del directorio de secretos, permisos del fichero de clave | S-09, S-10, S-11 |

### Ola 3-bis — Iniciativa nueva «recuerdos fiables»

Va antes de la Ola 4 porque cambia el diseño de los puntos 5, 7 y 9.

| Bloque | Contenido | Cubre |
|---|---|---|
| Vigencia | Ancla de evidencia por recuerdo (esquema aditivo), marca «posiblemente obsoleto», penalización en el orden | M-02 |
| Contradicciones | Detección al escribir sobre la búsqueda vectorial existente; resolución por `superseded` o marca de conflicto | M-03 |
| Filtro al escribir | Criterio de admisión en la captura automática, medido con un conjunto etiquetado | M-04 |
| Ámbito de usuario | Proyecto personal por usuario y su lectura en el contexto | M-07 |

### Ola 4 — Funcionalidades pendientes (iniciativas 2 y 3 del objetivo original)

Orden por dependencias: cada punto alimenta al siguiente.

| Orden | Punto | Depende de | Nota |
|---|---|---|---|
| 1 | 8 · `memory_feedback` (herramienta 35) | Contrato aditivo | Fuente de señal para 6 y 7; actualizar la verificación del despliegue y el puente del CLI |
| 2 | 6 · Puntuación con recencia, validación y uso | T-27 en verde, señal de 8 | Esquema v11 aditivo; se ajusta con la misma puerta de evaluación |
| 3 | 5 · Casi-duplicados y fusión | HNSW y `pg_trgm` ya construidos | Fusionar con `superseded`, nunca borrando |
| 4 | 7 · Ciclo de vida por categoría | Estado `validated` de 6 | Solapa con 5: una fusión es una transición |
| 5 | 10 · Contexto de inicio con presupuesto de tokens | Orden de 6, T-29 | Requiere canal de distribución del CLI |
| 6 | 9 · Consolidación periódica | 5, 7, métricas de la Fase 7 | Necesita planificador; resumen siempre sin validar |

Antes de empezar: ampliar el conjunto de evaluación con las combinaciones que faltan, para que 6 y 5 se midan con la misma puerta. Con el punto 8 en marcha, construir el conjunto de evaluación con uso real (M-05).

### Ola 5 — Distribución y mantenibilidad (en paralelo, sin urgencia)

- Canal alternativo a npm: GitHub Release con el tarball o GitHub Packages (O-07, A-08, F-06).
- CLI: reparación del bloqueo del outbox y detección de ruta de Node obsoleta en `doctor` (O-08, O-09).
- Portal: plazo en `fetch`, lint, prueba de accesibilidad, dividir `memory-portal.ts` (O-10).
- Backend: migraciones numeradas con una fuente única y readiness que exija versión (B-11), `Settings` única (B-12), protocolo explícito entre stores (B-16), purga de work-state (B-13), correcciones de `graph_data` y N+1 (B-08, B-10), código muerto y formato (B-17, B-18).
- Documentación: separar `operations.md` en runbooks, notas de migración y changelog; CONTRIBUTING y LICENSE; retros de las iniciativas cerradas (O-12, O-13).

## 5. Integración con el plugin `custom-agents`

**Veredicto: viable, con esfuerzo medio.** El plugin (versión 3.2.3) ya tiene el hueco hecho: un puerto de conocimiento (`purpose: "knowledge"` con `knowledge.check/publish/read/rebuild`) y un contrato de adaptador en `skills/knowledge-services/backends/`. Añadir Kairos es un adaptador nuevo, sin tocar el núcleo. Hoy el plugin no menciona Kairos ni declara ningún servidor MCP.

**Alcance decidido por el usuario (2026-11-10):** Kairos sustituye a Kwipu y a Graphiti y pasa a ser el único sistema de memoria externo del plugin. La memoria local (`docs/knowledge/` en git) sigue siendo la de serie y la fuente de verdad.

### 5.1 Encaje

| Uso | En el plugin | En Kairos | Encaje |
|---|---|---|---|
| Publicar conocimiento aprobado | `backends/kairos.py` con `plan`, `apply`, `verify`, `rebuild`, `revoke`; `routing.kairos` en `taxonomy.json` | `publish_document` (SHA-256 exacto + evidencia), `document_manifest`, `document_status`, `revoke_document` | Muy bueno: la decisión del Curator ya va ligada al SHA, y el manifiesto permite reconciliar sin reenvíos a ciegas |
| Leer contexto | `consultar()` y `puede_leer()` del adaptador, vía `knowledge-find.py --intent` | `search`, `context`, `details`, `timeline` | Bueno; requiere M-01 y S-05 |
| Episodios de sesión | `journal.py replay` (fuera de los hooks) | `remember` como nota sin validar | Posible; el plugin prohíbe publicar el journal como doctrina, así que entra como episodio |
| Estado de tareas | Eventos `task.*` y `review.*` del puerto de integraciones | `team_work_write`, `team_brief` | Posible; hoy no existe adaptador de work-state |
| Salud y alta | `capabilities.py`, `/setup`, `/doctor` | `/health/ready`, `projects`, `capture_policy` | Directo |

### 5.2 Condiciones

1. **Kairos es proyección, no fuente.** El plugin fija que el Markdown en git es la única fuente (ADR-018) y que solo el Curator aprueba. Kairos recibe lo aprobado como documentos validados y es reconstruible con `rebuild`. Los agentes no escriben doctrina directamente.
2. **Transporte.** Los adaptadores del plugin hablan HTTP propio con solo la biblioteca estándar, no usan el MCP del runtime (así funcionan también en Codex y OpenCode). El cliente MCP existente está dentro de `graphiti.py`: hay que extraerlo como cliente genérico.
3. **Autenticación.** El cliente actual no gestiona credenciales. Hay que añadir clave bearer leída de una variable de entorno o almacén seguro, nunca del repositorio.
4. **Sin red en los hooks.** Lectura y escritura pasan por el router y la cola recuperable (`outbox.py`), no por `SessionStart` ni `SessionEnd`.
5. **Doble captura.** El CLI de Kairos ya captura sesiones con sus propios hooks. Hay que decidir quién captura en los proyectos que usen ambos, para no duplicar episodios.

### 5.3 Qué necesita Kairos para ser un backend fiable del plugin

| Requisito | Estado | Dónde se cubre |
|---|---|---|
| Contrato estable y solo aditivo | Hecho (prueba de contrato aditivo) | — |
| Idempotencia por hash y versión, lápidas | Hecho | — |
| Proyecto por repositorio y clave con permisos `publish` y `validate` | Existe; falta guía de alta | Ola 1, T-34 |
| Fases 3-5 desplegadas (búsqueda semántica y troceado) | Pendiente | Ola 1, T-38 |
| Copias probadas y worker tolerante a fallos | Pendiente | Ola 2 |
| Abstención y contenido marcado como no fiable en todas las lecturas | Pendiente | M-01, S-05 |
| Caducidad y rotación de claves | Pendiente | S-03 |
| Acceso desde otras máquinas (hoy solo `127.0.0.1`; HTTPS obligatorio fuera de loopback) | Depende del uso | Decisión 5 |

### 5.4 Sustitución de Kwipu y Graphiti

Ser el único backend externo simplifica el plugin y sube la exigencia sobre Kairos.

| Aspecto | Consecuencia |
|---|---|
| Migración de datos | No hace falta: los backends son proyecciones reconstruibles del Markdown. Basta `rebuild` contra Kairos |
| Código del plugin | Se retiran `backends/markdown_export.py` y `backends/graphiti*.py`, sus funciones en `capabilities.py` y sus pasos de `/setup`. El cliente MCP se extrae de `graphiti.py` antes de borrarlo. El contrato de adaptador se conserva |
| Decisiones registradas | ADR nuevo que sustituye a ADR-020 (Graphiti) y ADR-021 (Kwipu); ADR-018 (Markdown como fuente) se mantiene |
| Compatibilidad | Es un cambio rompedor para quien use Kwipu o Graphiti: versión mayor del plugin o un periodo con aviso de retirada |
| Paridad funcional | Antes de retirar, comprobar qué intenciones de lectura sirve hoy Graphiti (grafo de entidades y relaciones, consulta temporal, `group_id`) y cubrirlas con `search`, `context`, `timeline` y el grafo de Kairos. **Pendiente de verificar**: no se ha comparado función por función |
| Fiabilidad | Sin backend alternativo, una caída de Kairos deja al plugin solo con la memoria local. La degradación a búsqueda local ya existe en el plugin; las olas 1 y 2 pasan a ser requisito previo al cambio, no recomendación |
| Acceso | Si el plugin se usa en varias máquinas o por varias personas, Kairos necesita HTTPS, gestión de usuarios y rotación de claves (S-02, S-03) antes de activarse |

Orden de retirada: adaptador `kairos` en modo `shadow` junto a los actuales, comparación de resultados, cambio de lectura a Kairos, y retirada de Kwipu y Graphiti en la versión siguiente.

### 5.5 Encaje en el plan: Ola 6

- **En el repositorio del plugin**: adaptador `kairos`, cliente MCP genérico con bearer, capacidad en `/setup` y `/doctor`, tests y evals según sus convenciones. Puede empezar en paralelo en modo `shadow` contra el contrato actual, como hizo Graphiti. El repositorio tiene trabajo sin comitear en la rama `fix/plugin-audit-remediation`: la integración parte de ahí cuando se cierre.
- **En Kairos**: los requisitos de la tabla anterior. Activar lectura real (`read`) solo tras las olas 1 y 2 y con M-01 y S-05 hechos.
- **Orden**: publicación primero (bajo riesgo, reconstruible), lectura después, episodios y estado de tareas al final.

## 6. Despliegue en un VPS con acceso desde varias máquinas

**Decidido por el usuario (2026-11-10):** Kairos correrá en un VPS con Docker y se usará desde otras máquinas. Hoy está pensado para una sola máquina: los puertos solo escuchan en `127.0.0.1` (`docker-compose.yml:113,143`) y Ollama corre en el host. `docs/server-install.md` tiene una sección de servidor remoto y hay un `Caddyfile.example`, pero el cambio de exposición reordena el plan.

### 6.1 Hallazgos que suben de severidad

| ID | Antes | Ahora | Motivo |
|---|---|---|---|
| S-02 Bloqueo global del login | Media | **Alta** | Con el servicio en internet, diez peticiones anónimas dejan a todos sin iniciar sesión |
| S-03 Ciclo de vida de credenciales | Media | **Alta** | Varias máquinas y personas: hace falta cambiar contraseñas, revocar sesiones, caducar y rotar claves |
| S-08 Sin límite de tasa por clave | Baja | **Media** | Una clave filtrada o un agente en bucle agota la base o Ollama de todos |
| S-04 Modelo `beam:cloud` | Media | **Resuelto como diseño** | Los modelos de lenguaje serán de nube (sección 6.3); se sustituye por consentimiento por proyecto y capa de proveedores |
| S-01 Huecos en la redacción de secretos | Media | **Alta** | El contenido capturado se envía a proveedores externos |
| S-06 / O-01 Copias sin cifrar en el mismo host | Baja / Alta | **Alta** | Un VPS se pierde o se compromete entero: la copia debe salir cifrada a otro sitio |
| S-09 Proxy de Ollama expone toda la API | Baja | **Media** | Más superficie si cualquier contenedor del VPS alcanza la red de inferencia |
| O-06 `host.docker.internal` en Linux | Media | **Alta** | El VPS es Linux: sin `extra_hosts` el proxy no alcanza a Ollama |
| B-02 / B-07 Sin pool ni plazos | Alta / Media | **Alta** | Varios clientes concurrentes por red |
| B-01 / O-07 Sin logs ni métricas | Alta | **Alta, bloqueante** | No se puede operar un servicio expuesto sin registro de accesos y errores |

### 6.2 Trabajo nuevo que aparece

| Bloque | Contenido |
|---|---|
| Exposición | TLS con renovación automática (Caddy), solo 443 abierto, cortafuegos, cabeceras, IP real del cliente propagada desde el proxy de confianza |
| Inferencia | Ollama como servicio de Compose o del host con `extra_hosts`; dimensionar CPU y memoria para `nomic-embed-text`; decisión sobre el modelo de extracción |
| Identidad | Un usuario por persona y una clave por máquina, con alcance por proyecto; guía de alta y de baja; clave propia para el plugin con `publish` y `validate` |
| Clientes | CLI y adaptador del plugin apuntando a la URL HTTPS; comportamiento sin conexión (la cola de envío ya existe) y latencia de red en el contexto de inicio |
| Migración | Trasladar la instalación local al VPS: copia verificada, restauración, comparación de manifiestos, corte |
| Servidor | Endurecimiento del host (SSH por clave, actualizaciones automáticas), límites de recursos, rotación de logs, alertas, copia externa cifrada programada |
| Prueba | Ensayo completo en un VPS de pruebas o proyecto Compose aislado antes del corte; prueba de restauración desde la copia externa |

### 6.3 Proveedores de modelos

**Decidido por el usuario (2026-11-10):** Ollama está instalado en el VPS, y los modelos de lenguaje serán de nube: los modelos cloud de Ollama, los de OpenAI (Codex) y los de Claude. Enviar contenido a un proveedor externo deja de ser un riesgo por confirmar (S-04) y pasa a ser el diseño; lo que hay que construir es el control sobre ese envío.

Hoy solo existe un proveedor: la clase `Ollama` de `memory_platform/providers.py:52`, que llama a `/api/chat` y `/api/embed` del proxy, con un único modelo (`MEMORY_LLM_MODEL`, por defecto `beam:cloud`). Los modelos cloud de Ollama ya funcionan por ese camino. OpenAI y Claude necesitan adaptadores nuevos.

| Bloque | Contenido |
|---|---|
| Embeddings locales | Mantener `nomic-embed-text` en el Ollama del VPS. Cambiar de modelo de embeddings obliga a recalcular todos los vectores, y así el texto completo de la memoria no sale del servidor para indexarse |
| Capa de proveedores | Interfaz única para extracción y respuestas de corpus, con adaptadores Ollama, OpenAI y Claude (SDK oficial de cada uno); modelo y proveedor configurables por uso |
| Cadena de respaldo | Orden de proveedores con cambio automático ante error, límite de tasa o plazo; cortacircuitos; el resultado indica qué proveedor respondió |
| Consentimiento por proyecto | La política del proyecto declara qué proveedores externos puede usar; sin consentimiento, extracción desactivada. Documentado en el alta |
| Redacción antes de enviar | S-01 sube a **alta**: el filtro de secretos es la última barrera antes de un tercero |
| Coste y límites | Presupuesto diario por proyecto, métricas de tokens y coste por proveedor, lotes asíncronos para el reprocesado masivo |
| Procedencia | Cada extracción guarda proveedor, modelo y versión del prompt, para poder rehacerla y comparar calidad entre modelos (M-05) |
| Secretos y salida | Claves de API como secretos de Docker; salida de red limitada a los hosts de los proveedores configurados |

**Por decidir:** autenticación de OpenAI y Claude. Un servicio en un servidor debe usar claves de API de cada proveedor; las suscripciones de Codex o Claude Code están ligadas a un usuario y a su cliente, no a un servicio.

Este bloque entra en la Ola 3, antes de exponer el servicio.

### 6.4 Orden revisado

1. Ola 0 (protección inmediata).
2. Ola 1 (cerrar `retrieval-quality`), **sin** el despliegue T-38 en la instalación local si el destino va a ser el VPS: T-38 se convierte en el despliegue al VPS.
3. Ola 2 (operación fiable) y Ola 3 (privacidad y control de acceso) **completas**: ambas pasan a ser requisito previo a exponer el servicio.
4. **Ola 2-bis nueva: despliegue en VPS** (tabla 6.2), que termina con la migración y el corte.
5. Ola 6 (plugin) en modo `shadow` contra el VPS; después lectura real y retirada de Kwipu y Graphiti.
6. Ola 3-bis (recuerdos fiables), Ola 4 (funcionalidades) y Ola 5 (mantenibilidad).

## 7. Decisiones que necesita el plan

1. ~~Orden de Ola 1 y Ola 2~~: **resuelto por la sección 6.4**; las olas 2 y 3 van antes de exponer el servicio. Queda decidir si T-38 se ejecuta también en la instalación local o solo en el VPS.
2. ~~Modelo por defecto~~: **resuelto**, modelos de nube con embeddings locales (sección 6.3). Queda decidir la autenticación de OpenAI y Claude (claves de API) y el orden de la cadena de respaldo.
3. **Canal de distribución del CLI** mientras npm siga bloqueado.
4. ~~Alcance de la Ola 3~~: **resuelto**, completa, por la exposición a internet.
5. ~~Uso del plugin~~: **resuelto**, desde varias máquinas con Kairos en un VPS (sección 6). Quedan por decidir el modelo de extracción en el VPS, cuántas personas lo usarán y si la instalación local se migra o se empieza de cero.
6. **Captura de sesiones** en proyectos con plugin y CLI de Kairos: quién captura.
7. **Retirada de Kwipu y Graphiti**: versión mayor inmediata o periodo con aviso.

## 8. No comprobado

Estado real de contenedores, volúmenes y copias; contenido de `.env` y `.private/`; CVE de las versiones fijadas; si `beam:cloud` ejecuta en remoto; comportamiento de los hooks en macOS y Windows reales; planes de ejecución (`EXPLAIN`) de las consultas señaladas; en el plugin, si `capabilities.py` admite una capacidad nueva sin tocar ese fichero y el contenido de `phase4-knowledge-gate.md`.
