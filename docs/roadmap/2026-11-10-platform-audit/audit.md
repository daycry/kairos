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

Seis olas. Cada una es desplegable por separado. El orden busca que nada nuevo llegue a producción sin copias probadas ni visibilidad.

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

### Ola 3 — Iniciativa nueva «privacidad y control de acceso»

| Bloque | Contenido | Cubre |
|---|---|---|
| Redacción | Patrones ampliados, detector de entropía, test compartido backend/CLI | S-01 |
| LLM remoto | Modelo local por defecto u opt-in explícito, documentado | S-04 |
| Credenciales | Cambio de contraseña con revocación de sesiones, deshabilitar usuario, retirar permisos, caducidad y rotación de claves, scrypt reforzado con rehash | S-03, S-07 |
| Login | Contar solo fallos, IP real desde proxy de confianza, purga | S-02 |
| Contenido no fiable | Envoltorio delimitado y `warning` en todas las herramientas de lectura (cambio aditivo del contrato) | S-05 |
| Superficie | Lista blanca de rutas en el proxy de Ollama, proxy sin root, validación del directorio de secretos, permisos del fichero de clave | S-09, S-10, S-11 |

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

Antes de empezar: ampliar el conjunto de evaluación con las combinaciones que faltan, para que 6 y 5 se midan con la misma puerta.

### Ola 5 — Distribución y mantenibilidad (en paralelo, sin urgencia)

- Canal alternativo a npm: GitHub Release con el tarball o GitHub Packages (O-07, A-08, F-06).
- CLI: reparación del bloqueo del outbox y detección de ruta de Node obsoleta en `doctor` (O-08, O-09).
- Portal: plazo en `fetch`, lint, prueba de accesibilidad, dividir `memory-portal.ts` (O-10).
- Backend: migraciones numeradas con una fuente única y readiness que exija versión (B-11), `Settings` única (B-12), protocolo explícito entre stores (B-16), purga de work-state (B-13), correcciones de `graph_data` y N+1 (B-08, B-10), código muerto y formato (B-17, B-18).
- Documentación: separar `operations.md` en runbooks, notas de migración y changelog; CONTRIBUTING y LICENSE; retros de las iniciativas cerradas (O-12, O-13).

## 5. Decisiones que necesita el plan

1. **Orden de Ola 1 y Ola 2**: se recomienda intercalar la Ola 2 antes de T-38. La alternativa es desplegar antes con una copia manual verificada (Ola 0) y asumir el resto.
2. **Modelo por defecto**: mantener `beam:cloud` con aviso explícito o pasar a un modelo local.
3. **Canal de distribución del CLI** mientras npm siga bloqueado.
4. **Alcance de la Ola 3**: completa, o solo S-01 y S-04 antes de las funcionalidades nuevas.

## 6. No comprobado

Estado real de contenedores, volúmenes y copias; contenido de `.env` y `.private/`; CVE de las versiones fijadas; si `beam:cloud` ejecuta en remoto; comportamiento de los hooks en macOS y Windows reales; planes de ejecución (`EXPLAIN`) de las consultas señaladas.
