---
spec: three-components
descripcion: Separación de Kairos en tres componentes — integración continua, paridad REST /v1, kairos-mcp propio sin acceso a la base, servidor sin modelo de lenguaje, esquema versionado de observación, estructura server/mcp/client/web y compatibilidad.
estado: aprobada          # borrador | aprobada | implementada | obsoleta
creado: 2026-11-12
actualizado: 2026-11-12
evaluacion: evaluation.md
design: n/a
plan: improvement-plan.md
generacion:
  inicio: 2026-11-12T09:41:28Z
  fin: 2026-11-12T09:53:04Z
  fuente: estimado        # producida dentro de la ventana medida de evaluation.md (sin marcador propio); su coste está incluido en el bloque generacion de evaluation.md
  tokens_reales: { entrada: 0, salida: 0, cache_creacion: 0, cache_lectura: 0 }
  eur: null
  horas_ia: 0.00
  duracion: 0m
  ratio_usado: 300000
---

# Separación en tres componentes (Iniciativa 2 del plan director)

> **Evaluación:** [`evaluation.md`](evaluation.md)
> **Plan de implementación:** [`improvement-plan.md`](improvement-plan.md) · [`tasks.md`](tasks.md)
> **Origen:** [plan director](../2026-11-10-platform-audit/plan.md), §1, §2 e «Iniciativa 2»; [auditoría](../2026-11-10-platform-audit/audit.md) (B-04, O-04, S-04, S-05, S-09); [integración con custom-agents](../2026-11-10-platform-audit/custom-agents-integration.md), §5.

> **Terminología:**
> - **kairos-server**: API REST `/v1`, permisos, almacenamiento, búsqueda y worker de embeddings. Hoy es `memory_platform/`.
> - **kairos-mcp**: proceso y contenedor nuevos que publican las 34 herramientas MCP y traducen cada una a una llamada `/v1` con la credencial de quien llama.
> - **kairos-client**: el CLI con hooks, cola en disco y puente stdio. Hoy es `packages/kairos-cli/` (`@daycry/kairos` 0.3.0).
> - **MCP interno**: el MCP montado hoy dentro del proceso de la API (`memory_platform/app.py:400-401`, `mcp.py:214-225`), con acceso directo a `Store`.
> - **Herramienta de lectura**: herramienta con `readOnlyHint=True` en su anotación MCP.
> - **Hecho** (con `fichero:línea`) frente a **hipótesis** (marcada como tal): la distinción se mantiene en todo el documento.

## Contexto y objetivo

El plan director decide (D-1…D-6) que Kairos irá a un VPS con Docker, se usará desde varias máquinas, el servidor no ejecutará modelos de lenguaje (solo `nomic-embed-text`), la extracción la hará el cliente y Kairos será el único backend externo de memoria de `custom-agents`. Hoy el código no cumple esa arquitectura:

1. **Sin integración continua.** No existe `.github/` (comprobado con `ls -a .github`: no existe). La suite backend solo corre con `docker build --target test` (`memory_platform/Dockerfile:31`, `memory_platform/tests/run_postgres.py:18-57`). Hallazgos B-04 y O-04.
2. **MCP acoplado al almacén.** `create_app` monta el MCP en el proceso de la API (`app.py:400-401` → `mcp.py:214-225`, `app.mount('/mcp', …)`). Las herramientas llaman a `Store`, `AgentStore`, `ExtendedStore` y `CorpusAnswers` directamente (`mcp.py:57-63`, `agent_tools.py:44-46`, `extended_tools.py:20-22`, `corpus_answer_tools.py:13`) y reutilizan los modelos Pydantic del servidor (`mcp.py` usa `m.Event`, `m.Document`, `m.Search`…).
3. **Sin paridad REST.** De las 34 herramientas (`docs/contracts/kairos-mcp.json`, 34 entradas en `tools`), **7 no tienen endpoint `/v1` equivalente** y 3 lo tienen solo en parte (tabla de §Arquitectura).
4. **El servidor llama a un modelo de lenguaje.** El worker crea un proveedor `extract` con Ollama (`worker.py:82`, `:125-131`) que usa `/api/chat` (`providers.py:71-90`); `corpus_answer` también (`corpus_answers.py:101-105`). El modelo por defecto es `beam:cloud` (`config.py:219`, `:272`; `docker-compose.yml:9`; `docs/configuration.md:24`), señalado en S-04. El CLI pide extracción en los resúmenes (`packages/kairos-cli/lib/capture.mjs:84`, `generate: kind === 'summary' && …`), que el servidor convierte en trabajo `extract` (`store_ingest.py:183`).
5. **Proxy de Ollama abierto.** `ollama-proxy/default.conf.template:15-25` reenvía `location /` completo (pull, delete, create, chat), con la red `egress` (`docker-compose.yml:45-47`). Hallazgo S-09.
6. **Contenido no fiable sin marcar.** Solo `context` (`retrieval.py:243`), `observation_context` (`agent_tools.py:127`), `team_brief` (`extended_store.py:227`) y `query_corpus` (`agent_store.py:345`) añaden un aviso; `search`, `details`, `timeline`, `get_observations` y el resto devuelven texto sin marcar. Hallazgo S-05.
7. **Observaciones sin esquema.** `/v1/observations` acepta el `Event` genérico (`models.py:106-117`) con `payload` libre; no hay esquema versionado de observación ni de resumen de sesión.
8. **Estructura plana.** El servidor vive en `memory_platform/` (106 ficheros seguidos), el cliente en `packages/kairos-cli/` (53) y el portal ya está en `web/` (32), pero su imagen se construye desde `memory_platform/Dockerfile.web` con `memory_platform/nginx.conf`.

**Objetivo**: separar servidor, MCP y cliente en tres componentes que solo se hablan por contrato (`/v1` y MCP), con integración continua como red de seguridad, un servidor que arranca y pasa su suite sin ningún modelo de lenguaje, y sin romper el contrato MCP, las migraciones ni el puente stdio del CLI.

**Fuente**: encargo aprobado por el usuario (2026-11-12) sobre la sección «Iniciativa 2» del plan director.

## Decisiones de diseño

| Decisión | Elección | Motivo |
|---|---|---|
| Orden de trabajo | **C-01 → C-04 → C-02 → C-05 → C-03 → C-07 → C-06** | La CI va primero por mandato del plan. C-04 es pequeño, independiente y reduce superficie. C-02 crea los endpoints que C-03 necesita. C-06 (renombrados masivos) va al final y con el PR #2 fusionado, para no chocar con correcciones de revisión de `feat/retrieval-quality` (P-09). Ver evaluación. |
| Fuente de los esquemas de entrada de kairos-mcp | **Generar las herramientas desde `docs/contracts/kairos-mcp.json`** (servidor MCP de bajo nivel con los `inputSchema` del contrato), en lugar de copiar los modelos Pydantic | El componente no puede importar código del servidor (plan §2). Si el contrato es la fuente, la identidad de esquemas se cumple por construcción. Alternativa: copiar los modelos con un test de igualdad. Decidido 2026-11-12 (P-05). |
| Correspondencia herramienta ↔ endpoint | **Campo aditivo `x-kairos-endpoint` por herramienta** en el contrato MCP (`{method, path}` o `local` para `important_workflow`) | Lo exige el plan §2.2; una prueba compara cada entrada con el OpenAPI exportado. |
| Credencial en kairos-mcp | **Solo `Authorization: Bearer`, reenviado tal cual a `/v1`**; kairos-mcp no tiene credencial propia | Plan §2.1 (sin permisos ni estado). Las sesiones con cookie y CSRF (`mcp.py:186-211`) quedan solo en el MCP interno; el portal no llama a `/mcp` (solo lo menciona en `web/src/memory-portal.ts:647`). Decidido 2026-11-12 (P-08). |
| Envoltorio de dato no fiable (S-05) | **Campos aditivos en el objeto JSON de respuesta** (`untrusted: true` y `warning`) en todas las herramientas de lectura; **sin** delimitar ni alterar el texto | El CLI parsea el texto de la herramienta como JSON (`packages/kairos-cli/lib/dispatcher.mjs:15-20`): delimitarlo rompería el cliente 0.3.0. Se aplica en kairos-mcp y en el MCP interno. Decidido 2026-11-12 (P-02). |
| Extracción en el servidor | **`MEMORY_EXTRACT_ENABLED=0` por defecto**; con extracción apagada, un evento con `generate: true` se acepta sin crear trabajo `extract` y el recibo lo indica con un campo aditivo | Conserva el CLI 0.3.0, que envía `generate: true` en resúmenes (`capture.mjs:84`). Decidido 2026-11-12 (P-03). |
| `corpus_answer` | **`MEMORY_CORPUS_ANSWER=off` por defecto**; la herramienta sigue en la lista (34) y responde el error `corpus_answer_disabled` sin llamar a ningún proveedor | D-4; contrato solo aditivo. Decidido 2026-11-12 (P-04). |
| Modelo por defecto | **`MEMORY_LLM_MODEL` sin valor por defecto**; si `extract` o `corpus_answer` están activos sin modelo, el arranque falla con un error claro | Retira `beam:cloud` (S-04, D-2). |
| Proxy de Ollama | **Lista de permitidos `/api/embed` y `/api/version`**; el resto, 403. `/api/chat` solo si un operador lo habilita con una variable explícita | S-09. Decidido 2026-11-12 (P-10). |
| Esquema de observación | **JSON Schema 2020-12 versionado** en `docs/contracts/` (`observation.v1`, `session-summary.v1`), validado en `/v1/observations` cuando el evento declara `schema_version`; los eventos sin ella siguen como hoy | Aditivo para el CLI 0.3.0, que no envía `schema_version`. Decidido 2026-11-12 (P-11). |
| Paquete Python del servidor | **`server/memory_platform/`**: se mueve el directorio y se conserva el nombre del paquete | Evita reescribir 391 apariciones de `memory_platform` en 74 ficheros seguidos y conserva `store_surface.json`. Alternativa: `kairos_server`. Decidido 2026-11-12 (P-06). |
| Enrutado de `/mcp` | **`/mcp` del proxy web pasa a kairos-mcp**; el MCP interno sigue en `memory-api:8790/mcp` una versión, con cabeceras `Deprecation` y `Sunset` y un evento de log | El puente stdio del CLI usa `baseURL + '/mcp/'` (`packages/kairos-cli/lib/mcp.mjs:33`) y sigue funcionando sin cambios. Decidido 2026-11-12 (P-07). |
| Integración continua | **GitHub Actions en Linux**, sin publicar imágenes ni paquetes y sin secretos (solo `GITHUB_TOKEN`) | La matriz Windows/macOS del CLI es O-09 (Iniciativa 9). Decidido 2026-11-12 (P-01). |

## Configuración / parámetros

| Parámetro | Clave / mecanismo | Default hoy | Valor objetivo |
|---|---|---|---|
| Extracción en el servidor | `MEMORY_EXTRACT_ENABLED` (nuevo) | siempre activa (`worker.py:82`) | **`0`** |
| Respuestas generadas | `MEMORY_CORPUS_ANSWER` (nuevo) | siempre activas | **`off`** |
| Modelo de lenguaje | `MEMORY_LLM_MODEL` | `beam:cloud` (`config.py:219`, `docker-compose.yml:9`) | **sin valor**; obligatorio solo si se activa una de las dos anteriores |
| Rutas del proxy de Ollama | plantilla `ollama-proxy/default.conf.template` + `OLLAMA_ALLOW_CHAT` (nuevo) | `location /` completo | **`/api/embed`, `/api/version`**; `/api/chat` solo con `OLLAMA_ALLOW_CHAT=1` |
| URL de la API para kairos-mcp | `KAIROS_API_URL` (nuevo) | — | **`http://memory-api:8790`** en Compose |
| Plazo de kairos-mcp hacia `/v1` | `KAIROS_API_TIMEOUT` (nuevo) | — | **30 s** (igual que `request_timeout`, `config.py:221`) |
| MCP interno | `MEMORY_MOUNT_MCP` (nuevo) | montado siempre | **`1` con aviso de retirada** durante una versión; `0` lo desmonta |
| Versión de cada componente | fichero `VERSION` o `package.json` por componente | solo el CLI (`0.3.0`) | a fijar (P-07) |

## Arquitectura y componentes

**Paridad REST medida** (hecho: comparación de `mcp.py`, `agent_tools.py`, `extended_tools.py` y `corpus_answer_tools.py` con las rutas de `app.py:133-396`):

| Herramienta | Servicio que llama hoy | Endpoint `/v1` | Estado |
|---|---|---|---|
| `projects`, `remember`, `publish_document`, `document_status`, `document_manifest`, `revoke_document`, `search`, `details`, `context`, `timeline` | `Store` / `Retrieval` | `GET /v1/projects`, `POST /v1/events`, `POST·GET·DELETE /v1/projects/{id}/documents…`, `GET …/manifest`, `POST /v1/search·details·context·timeline` (`app.py:186-346`) | Existe |
| `work_state_write`, `work_state_read`, `list_corpora`, `rebuild_corpus`, `prime_corpus`, `reprime_corpus` | `AgentStore` | `…/work-state`, `…/corpora`, `…/prime` (con `fresh`), `…/rebuild` (`app.py:206-272`) | Existe |
| `observation_add`, `observation_record_event`, `get_tool_uses`, `team_work_write`, `team_work_read`, `team_brief` | `ExtendedStore` | `POST /v1/observations`, `POST /v1/observations/events`, `GET /v1/tool-uses`, `…/team-work`, `…/team-brief` (`app.py:222-251`) | Existe |
| `observation_generation_status` | `Store.get_job` | `GET /v1/jobs/{id}` (`app.py:305`) | Existe |
| `corpus_answer`, `corpus_answer_status` | `CorpusAnswers` | `…/corpora/{name}/answers…` (`app.py:274-283`) | Existe |
| `build_corpus` | `AgentStore.build_corpus` | `POST …/corpora` (`app.py:258`) | **Parcial**: `CorpusSelection` (`models.py:37-44`) no acepta `dateStart`/`dateEnd`, que la herramienta sí pasa (`agent_tools.py:72`) |
| `event_status` | `get_event_receipt` + `get_job` por trabajo, o `reconcile_capture` con `project_id` (`mcp.py:98-115`) | `GET /v1/events/{id}` y `GET /v1/jobs/{id}` | **Parcial**: falta la reconciliación por proyecto (`store_documents.py:258`) |
| `capture_policy` | `Store.capture_policy` (`store_auth.py:126-137`) | `GET …/policy` devuelve otra cosa (`get_policy`, `store_auth.py:121-124`) | **Falta** |
| `query_corpus` | `AgentStore.query_corpus` | — | **Falta** |
| `get_observations`, `observation_search`, `observation_context` | `AgentStore.observations` (`agent_store.py:355`) | `GET /v1/observations` existe pero sirve el listado del portal (`PortalStore.page`, `app.py:353-355`), con otra semántica | **Falta** (3) |
| `team_search` | `ExtendedStore.team_search` (`extended_store.py:202`) | — | **Falta** |
| `important_workflow` | texto fijo (`agent_tools.py:135-146`) | no necesita | **Local** en kairos-mcp |

El plan cita «estado de documentos» entre los que faltan: el endpoint ya existe (`app.py:309`), así que no se cuenta.

- **Nuevo `mcp/`** (paquete `kairos_mcp`): servidor MCP *streamable HTTP* en `/mcp/`; cliente `httpx` hacia `KAIROS_API_URL`; las 34 herramientas generadas desde el contrato; traducción de errores `{"error": {"code", "message"}}` al mismo `ValueError(message)` que hoy (`mcp.py:48-55`); presupuestos de salida `NORMAL_BYTES`/`DETAIL_BYTES` (`agent_tools.py:15-16`) aplicados en el propio MCP; `GET /health/live`; Dockerfile propio sin dependencias de base de datos (ni `psycopg` ni secretos).
- **Servidor**: endpoints nuevos de C-02; `x-kairos-endpoint` en el exportador (`scripts/export-contracts.py:25-26`); interruptores de C-04; validación de C-05; cabeceras de retirada del MCP interno (C-07).
- **Compose**: servicio `memory-mcp` (imagen `kairos-mcp`) en una red nueva compartida solo con `memory-api`, sin `memory-data`, `inference` ni secretos; `memory-web` enruta `/mcp` a `memory-mcp` (`memory_platform/nginx.conf:56-60` hoy apunta a `memory-api`). La red `egress` del proxy de Ollama solo se conserva si el upstream lo exige (hoy `host.docker.internal`).
- **Estructura final**: `server/` (hoy `memory_platform/`, con `Dockerfile`, `schema.sql`, tests), `mcp/`, `client/` (hoy `packages/kairos-cli/`), `web/` (recibe `Dockerfile.web` y `nginx.conf`). Hay que actualizar la puerta congelada, que fija `memory_platform` y `packages` (`docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py:26`, `:45`, `:77`), el target `lifecycle-test` (`memory_platform/Dockerfile:63-66`) y los `RUNTIME_FILES` del CLI (`packages/kairos-cli/lib/config.mjs:11`).
- **CI**: `.github/workflows/ci.yml` con los trabajos `server` (target `test`), `retrieval-eval` (proveedor simulado), `mcp`, `client` (`npm test`, `release:check`), `web` (`typecheck`, `test`, `build`, target `test` de `Dockerfile.web`) y `contracts` (diff aditivo).

## Flujo (paso a paso)

1. **Agente → kairos-mcp**: llamada MCP con `Authorization: Bearer <clave del usuario>`.
2. **kairos-mcp → `/v1`**: valida los argumentos contra el `inputSchema` del contrato, llama al endpoint declarado en `x-kairos-endpoint` reenviando la misma cabecera y aplica el presupuesto de salida.
3. **Servidor**: autentica, aplica permisos y responde como hoy. kairos-mcp no decide permisos.
4. **Respuesta**: en las herramientas de lectura, kairos-mcp añade `untrusted: true` y `warning` (P-02) sin tocar los campos existentes.
5. **Captura del cliente**: `POST /v1/observations` con `schema_version` (cuando el observador de la Iniciativa 6 exista) → validación contra el esquema → 202. Sin extracción en el servidor.
6. **Compatibilidad**: el MCP interno responde igual que hoy, con cabeceras `Deprecation`/`Sunset`; el puente stdio del CLI apunta a `/mcp/` del proxy, que ahora sirve kairos-mcp.

## Alcance

- **Dentro (esta iniciativa):**
  - C-01 Integración continua (B-04, O-04).
  - C-02 Paridad REST `/v1` y prueba de correspondencia herramienta ↔ endpoint.
  - C-03 `kairos-mcp`: paquete, contenedor y envoltorio de dato no fiable (S-05).
  - C-04 Servidor sin modelo de lenguaje: `extract` apagado, `corpus_answer` opcional, proxy de Ollama con lista de permitidos (S-09), sin `beam:cloud` (S-04).
  - C-05 Esquema versionado de observación y de resumen de sesión, validado al recibir; migración aditiva si hace falta.
  - C-06 Estructura `server/`, `mcp/`, `client/`, `web/`, cada uno con imagen, tests y versión.
  - C-07 Compatibilidad: MCP interno con aviso de retirada durante una versión y puente stdio del CLI operativo.
- **Fuera:**
  - Observador en el cliente y su uso del esquema (Iniciativa 6); cambios funcionales del CLI salvo rutas y empaquetado.
  - HTTPS público, TLS y despliegue en el VPS (Iniciativa 5); despliegue en la instalación local.
  - Abstención M-01 (Iniciativa 3), rotación de claves y límites por clave (Iniciativa 4), proxy de Ollama sin root (S-09, segunda mitad; se propone en P-10 por si se quiere incluir).
  - Matriz Windows/macOS/Linux del CLI, lint y tipado completos (O-09, B-19; Iniciativa 9).
  - Publicación en npm o en registros de imágenes; retirada efectiva del MCP interno (sería la versión siguiente).
  - Borrar columnas, tablas o el trabajo `extract` del código: se desactiva, no se elimina.

## Manejo de errores

| Caso | Comportamiento |
|---|---|
| kairos-mcp sin cabecera `Authorization` o con un esquema distinto de `Bearer` | 401 con el mismo cuerpo de error que hoy (`mcp.py:194-207`), sin llamar a `/v1`. |
| `/v1` responde 4xx con `{"error": {code, message}}` | La herramienta falla con `message`, igual que el MCP interno (`mcp.py:51-52`). |
| `/v1` no responde, plazo agotado o 5xx | `Memory service temporarily unavailable` (igual que `mcp.py:53-55`) y evento de log sin contenido ni credenciales. |
| Evento con `generate: true` y extracción apagada | 202; sin trabajo `extract`; el recibo indica `extraction: "disabled"` (aditivo, P-03). |
| `corpus_answer` apagado | Error `corpus_answer_disabled` sin llamar a ningún proveedor; `corpus_answer_status` sigue leyendo respuestas ya guardadas (P-04). |
| Extracción o `corpus_answer` activos sin `MEMORY_LLM_MODEL` | El arranque falla con un mensaje que nombra la variable. |
| Petición al proxy de Ollama fuera de la lista | 403 desde el proxy; no llega al upstream. |
| Observación con `schema_version` desconocida o que no valida | 422 `invalid_observation` con la ruta JSON del primer error y sin eco del contenido. |
| MCP interno usado durante el periodo de compatibilidad | Respuesta normal con cabeceras `Deprecation` y `Sunset`, y evento de log `mcp_legacy_used` sin datos del usuario. |

## Criterios de aceptación

Todos se comprueban con fixtures aislados (PostgreSQL efímero del target `test`, servidores HTTP simulados o un proyecto Compose aislado con nombre distinto de `knowledge-graphs`), nunca contra la base, los contenedores, los volúmenes ni las redes `knowledge-graphs-*`.

**C-01 · Integración continua (B-04, O-04)**

- [ ] [GWT] CA-01 — Dado `.github/workflows/ci.yml`, Cuando se abre o actualiza un PR, Entonces se ejecutan los trabajos `server` (suite backend completa en el target `test`), `retrieval-eval` (proveedor simulado, umbrales recall@5 ≥ 0,80 y MRR ≥ 0,60), `client` (`npm test` y `release:check`), `web` (`typecheck`, `test`, `build`) y `contracts` (diff aditivo), y todos terminan en verde en el PR de esta rama (enlace a la ejecución en el ledger).
- [ ] CA-02 — El workflow no referencia más secreto que `GITHUB_TOKEN`, no hace `docker push` ni `npm publish` y no contacta con servicios desplegados (comprobación con `grep` en la puerta: `secrets\.`, `push`, `publish`).
- [ ] CA-03 — Un test que falla a propósito, en una rama desechable que no se fusiona, deja el trabajo correspondiente en rojo (enlace a la ejecución).

**C-02 · Paridad REST**

- [ ] [GWT] CA-04 — Dado el contrato exportado, Cuando se recorre `tools`, Entonces cada una de las 34 herramientas tiene `x-kairos-endpoint` con `method` y `path` presentes en `memory-platform.openapi.json`, o `local` (solo `important_workflow`).
- [ ] CA-05 — Existen endpoints `/v1` para `capture_policy`, la reconciliación de `event_status` por proyecto, `query_corpus`, `get_observations`, `observation_search`, `observation_context` y `team_search`, y `POST …/corpora` acepta `date_start` y `date_end`. Cada uno tiene un test de acceso permitido, de lector sin permiso (403) y de proyecto ajeno.
- [ ] [GWT] CA-06 — Dado un escenario sembrado en PostgreSQL aislado, Cuando se llama a cada herramienta por el MCP interno y a su endpoint por `/v1` con la misma credencial y argumentos, Entonces el contenido devuelto es igual (salvo el presupuesto de bytes y los campos aditivos de S-05). La prueba recorre las 34 herramientas.
- [ ] CA-07 — El diff de `memory-platform.openapi.json` contra `contracts_base` es solo aditivo (rutas, operaciones y campos opcionales nuevos; ninguno eliminado o cambiado).

**C-03 · kairos-mcp**

- [ ] CA-08 — `mcp/` no importa ningún módulo del servidor (test que analiza los `import` de `mcp/`: 0 apariciones de `memory_platform`) y su imagen no instala `psycopg`.
- [ ] [GWT] CA-09 — Dado el contenedor `kairos-mcp` arrancado solo con `KAIROS_API_URL`, sin variables `MEMORY_DSN*`, sin secretos montados y sin la red `memory-data`, Cuando se pide `GET /health/live`, Entonces responde 200; y `docker compose config` del proyecto aislado muestra el servicio sin `secrets` ni `memory-data`.
- [ ] CA-10 — `tools/list` de kairos-mcp devuelve las 34 herramientas en el mismo orden y con los mismos `name`, `description`, `inputSchema` y `annotations` que `docs/contracts/kairos-mcp.json`, comprobado con la misma regla de `test_contract_additive.py`.
- [ ] [GWT] CA-11 — Dados los tests de comportamiento del MCP interno (`test_mcp.py`, `test_mcp_write.py`, `test_agent_tools.py`, `test_extended_tools.py`, `test_corpus_gateway.py`, `test_extended_gateway.py`, `test_work_gateway.py`), Cuando se ejecutan contra la cadena kairos-mcp → servidor sobre PostgreSQL aislado, Entonces pasan con los mismos resultados (salvo los campos aditivos de S-05).
- [ ] CA-12 — Con una clave sin permiso de lectura, la herramienta falla con el mismo mensaje que el MCP interno; sin credencial, 401; kairos-mcp no guarda ni registra la credencial (test que busca el token sintético en sus logs: 0 apariciones).
- [ ] CA-13 — Todas las herramientas de lectura devuelven el envoltorio acordado en P-02 tanto en kairos-mcp como en el MCP interno; los campos existentes no cambian, y los tests del CLI 0.3.0 (`dispatcher.test.mjs`, `mcp.test.mjs`) pasan sin cambios.

**C-04 · Servidor sin modelo de lenguaje (D-2, D-4, S-04, S-09)**

- [ ] [GWT] CA-14 — Dada la configuración por defecto, Cuando se ingiere un evento `summary` con `generate: true`, Entonces la respuesta es 202, no se crea ningún trabajo `extract`, el recibo lo indica según P-03 y el worker no instancia el proveedor `extract`.
- [ ] CA-15 — Con la configuración por defecto, `corpus_answer` devuelve `corpus_answer_disabled` y el proveedor simulado recibe 0 llamadas; con `MEMORY_CORPUS_ANSWER=on` y un modelo configurado, los 21 tests actuales de `test_corpus_answers.py` pasan.
- [ ] CA-16 — `grep -n "beam"` en `memory_platform/config.py`, `docker-compose.yml` y `docs/configuration.md` no devuelve nada; activar `extract` o `corpus_answer` sin `MEMORY_LLM_MODEL` hace fallar `Settings.from_env()` con un mensaje que nombra la variable.
- [ ] [GWT] CA-17 — Dado el proxy de Ollama con un upstream simulado, Cuando se piden `/api/embed` y `/api/version`, Entonces llegan al upstream; y `/api/pull`, `/api/delete`, `/api/create`, `/api/chat` y `/api/generate` responden 403 sin llegar a él. Con `OLLAMA_ALLOW_CHAT=1`, `/api/chat` llega.
- [ ] CA-18 — La suite backend completa pasa con `MEMORY_LLM_MODEL` sin definir y un espía que falla ante cualquier llamada a `/api/chat`; el arranque de `memory-api` y `memory-worker` en el proyecto aislado tampoco llama a `/api/chat`.

**C-05 · Esquema de observación**

- [ ] CA-19 — Existen `docs/contracts/observation.v1.schema.json` y `docs/contracts/session-summary.v1.schema.json` (JSON Schema 2020-12) con `schema_version`. La observación declara tipo, título, hechos con cita literal, narrativa, conceptos, ficheros leídos y modificados. El resumen declara petición, investigado, aprendido, hecho y siguiente.
- [ ] [GWT] CA-20 — Dada una observación con `schema_version: "observation.v1"`, Cuando se envía a `POST /v1/observations`, Entonces es 202 si valida y 422 `invalid_observation` (con la ruta del error y sin eco del contenido) si falta un campo, sobra uno o excede un límite. Un evento sin `schema_version` se trata según P-11.
- [ ] CA-21 — Un conjunto de ejemplos válidos e inválidos versionado junto al esquema se valida igual en el test del servidor y con un validador independiente del servidor.
- [ ] CA-22 — Si hacen falta columnas o índices (por ejemplo, para filtrar por conceptos o ficheros), la migración es aditiva: `test_migrations_additive.py` pasa y `content_manifest().sha256` es igual antes y después de migrar.

**C-06 · Estructura del repositorio**

- [ ] CA-23 — Existen `server/`, `mcp/`, `client/` y `web/`; ya no existen `memory_platform/` ni `packages/kairos-cli/` en la raíz, y `git log --follow` conserva la historia de un fichero movido de cada uno.
- [ ] CA-24 — Cada componente tiene su Dockerfile (o imagen), su orden de tests, que la CI ejecuta, y su versión declarada (P-07).
- [ ] CA-25 — `memory_platform/tests/store_surface.json` (en su nueva ruta) no cambia y `test_store_surface` pasa; el recuento de la suite es igual antes y después de cada paso de movimiento, con recibo de la puerta congelada actualizada.
- [ ] CA-26 — `npm pack` del cliente produce la misma lista de ficheros que antes del movimiento y `release:check` pasa.

**C-07 · Compatibilidad**

- [ ] [GWT] CA-27 — Dado `MEMORY_MOUNT_MCP=1` (valor por defecto durante la versión de transición), Cuando se usa el MCP interno, Entonces los tests actuales del MCP interno pasan y cada respuesta lleva las cabeceras `Deprecation` y `Sunset` con la versión de retirada documentada; con `MEMORY_MOUNT_MCP=0`, `/mcp` en `memory-api` responde 404.
- [ ] CA-28 — El puente stdio del CLI (`kairos doctor` y el puente) funciona contra kairos-mcp en el proyecto aislado: el target `lifecycle-test` pasa y `REQUIRED_TOOLS` (`packages/kairos-cli/lib/mcp.mjs:7-8`) está presente.

**Transversales**

- [ ] CA-29 — El contrato `docs/contracts/kairos-mcp.json` regenerado solo tiene adiciones respecto de `contracts_base` del commit de inicio de la iniciativa (`23ced03`): 34 herramientas, mismo orden, ningún campo, valor por defecto ni `required` eliminado o cambiado.
- [ ] CA-30 — Ninguna migración nueva contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE`, y ningún test ni script referencia contenedores, volúmenes o redes `knowledge-graphs-*` salvo para rechazarlos.
- [ ] [GWT] CA-31 — Dado un proyecto Compose aislado con `memory-postgres`, `memory-api`, `memory-worker`, `memory-mcp`, `memory-web` y un proveedor de embeddings simulado, Cuando un cliente MCP escribe una observación, espera su indexado y la busca, Entonces la encuentra por kairos-mcp sin que el servidor haya llamado a ningún modelo de lenguaje.
- [ ] CA-32 — Al cerrar, la suite backend pasa con 0 fallos y 0 omitidos, `retrieval-eval` pasa con los umbrales vigentes y los manuales afectados (`docs/architecture.md`, `docs/configuration.md`, `docs/operations.md`, `docs/install.md`, `docs/integration.md`, `README.md`) describen los tres componentes y la retirada del MCP interno.

## Pruebas

- Suite backend en PostgreSQL aislado (`run_postgres.py` en el target `test`) para C-02, C-04, C-05 y C-07; 462 funciones `def test_` en 41 ficheros `test_*.py` hoy (hecho, `grep -c`).
- Suite de kairos-mcp con dos modos: transporte ASGI en proceso contra la app del servidor sobre PostgreSQL aislado (CA-11) y servidor `/v1` simulado (errores, plazos, credencial, CA-12).
- Prueba de correspondencia herramienta ↔ endpoint y diff aditivo de ambos contratos (CA-04, CA-06, CA-07, CA-29).
- Proxy de Ollama con upstream simulado en un proyecto Compose aislado (CA-17).
- Ensayo completo de los cinco servicios en un proyecto Compose aislado con embeddings simulados (CA-31).
- CI en GitHub Actions (CA-01…CA-03).
- Los criterios [GWT] se traducen 1:1 a casos del plan de pruebas con el mismo ID.

## Preguntas abiertas

| ID | Pregunta | Recomendación | ¿Necesita al usuario? |
|---|---|---|---|
| P-01 | ¿Se activan GitHub Actions en el repositorio (minutos de cómputo, coste si es privado) y basta con Linux en esta iniciativa? | Sí, solo Linux; la matriz de sistemas queda en la Iniciativa 9 (O-09). Sin publicar imágenes ni paquetes | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-02 | Forma del envoltorio S-05: ¿campos aditivos `untrusted` y `warning` en el JSON, o delimitar el texto? | Campos aditivos: delimitar el texto rompe el CLI 0.3.0 (`dispatcher.mjs:15-20`) y a los clientes que comparan contenido | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-03 | Con la extracción apagada, ¿qué se hace con los eventos `generate: true` que envía el CLI 0.3.0 (`capture.mjs:84`)? | Aceptarlos sin trabajo `extract` y marcarlo en el recibo; rechazarlos (422) rompe la captura de resúmenes del CLI publicado | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-04 | ¿`corpus_answer` apagado debe seguir listado y fallar con `corpus_answer_disabled`, o desaparecer de la lista? | Seguir listado: quitarlo rompe el contrato de 34 herramientas | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-05 | ¿kairos-mcp genera sus herramientas desde el contrato JSON o copia los modelos Pydantic? | Desde el contrato (identidad por construcción, sin importar código del servidor) | **Decidida 2026-11-12** (técnica, aceptada con el resto): se adopta la recomendación |
| P-06 | ¿Se conserva el nombre de paquete `memory_platform` dentro de `server/` o se renombra a `kairos_server`? | Conservarlo en esta iniciativa; renombrarlo, si se quiere, en la 9 | **Decidida 2026-11-12** (técnica, aceptada con el resto): se adopta la recomendación |
| P-07 | Versión inicial de cada componente y versión en la que se retira el MCP interno | `server` y `mcp` 0.4.0, `client` 0.4.0 (sin publicar), retirada del MCP interno en 0.5.0 | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-08 | ¿kairos-mcp acepta solo `Bearer`, sin sesiones de portal con cookie y CSRF? | Solo `Bearer`; las sesiones siguen en el MCP interno mientras exista | **Decidida 2026-11-12** (técnica, aceptada con el resto): se adopta la recomendación |
| P-09 | ¿Se fusiona el PR #2 (`feat/retrieval-quality`) antes del bloque C-06? | Sí: los renombrados masivos sobre una rama base que aún recibe correcciones generan conflictos | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-10 | ¿Se permite `/api/chat` en el proxy cuando un operador active la extracción o `corpus_answer`? ¿Se incluye ya el proxy sin root (resto de S-09)? | Variable explícita `OLLAMA_ALLOW_CHAT=1`, apagada por defecto; proxy sin root dentro (≈ 1 h) | **Decidida 2026-11-12** (usuario): se adopta la recomendación |
| P-11 | ¿Se exige `schema_version` a toda observación nueva, o solo se valida cuando viene? | Validar solo cuando viene; exigirla rompe el CLI 0.3.0, que no la envía. El diseño definitivo lo cierra la Iniciativa 6 con `schema_version` v2 si hace falta | **Decidida 2026-11-12** (usuario): se adopta la recomendación |

## Referencias

- `memory_platform/app.py:133-396` (rutas `/v1`), `:400-401` (montaje MCP); `memory_platform/mcp.py:20-63` (`create_mcp`, `safe`, `stored`), `:68-172` (12 herramientas), `:185-225` (`AuthenticatedMCP`, `mount_mcp`).
- `memory_platform/agent_tools.py:15-16`, `:48-146` (13 herramientas); `extended_tools.py:24-76` (7); `corpus_answer_tools.py:15-37` (2).
- `memory_platform/store_auth.py:121-137`, `store_documents.py:258`, `agent_store.py:345`, `:355`, `extended_store.py:202`, `:227`; `models.py:37-44`, `:106-117`.
- `memory_platform/worker.py:82`, `:107-131`; `providers.py:71-90`, `:125`, `:160`; `corpus_answers.py:101-105`; `store_ingest.py:183`; `config.py:219`, `:272`.
- `ollama-proxy/default.conf.template:15-25`; `docker-compose.yml:9`, `:38-54` (proxy), `:114-131` (`memory-api`), `:169-173` (redes); `memory_platform/nginx.conf:43-62`.
- `memory_platform/Dockerfile:2-66`, `memory_platform/Dockerfile.web:1-28`; `memory_platform/tests/run_postgres.py:18-57`, `test_contract_additive.py:1-40`, `store_surface.json`, `contracts_base/`.
- `packages/kairos-cli/lib/mcp.mjs:7-8`, `:33`; `dispatcher.mjs:15-20`, `:35`; `capture.mjs:84`; `config.mjs:11`; `package.json`.
- `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py:26`, `:45`, `:77`.
- `scripts/export-contracts.py:11-30`; `docs/contracts/kairos-mcp.json` (34 herramientas; `result_schemas` solo de `search`).

## Supuestos

- **Hipótesis**: GitHub Actions dispone de Docker en `ubuntu-latest`, y la suite del target `test` cabe en el tiempo máximo de un trabajo. La ejecución local de la Fase 8 tardaba minutos; no está medido en CI.
- **Hipótesis**: el SDK `mcp==1.27.1` (`memory_platform/requirements.txt:6`) permite registrar herramientas con `inputSchema` arbitrario mediante el servidor de bajo nivel, lo que exige P-05. Si no reproduce exactamente las descripciones o anotaciones, el plan pasa a la alternativa de copiar los modelos con un test de igualdad.
- **Hipótesis**: el `payload` `jsonb` de `memory_items` (`schema.sql:13`) basta para guardar los campos del esquema de observación sin columnas nuevas; solo harían falta índices si `build_corpus` filtra por conceptos o ficheros con volumen real.
- Los datos actuales no se migran a producción (decisión del 2026-11-12), así que no hay ventana de corte ni relleno de producción en esta iniciativa.
- Nada se publica en npm ni en registros de imágenes; la versión del cliente cambia en `package.json` sin publicar.
