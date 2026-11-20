---
design: "access-control"
titulo: "Control de acceso y privacidad (Iniciativa 4)"
estado: aprobado              # borrador | aprobado | obsoleto
creado: "2026-11-20"
actualizado: "2026-11-20"
spec: spec.md
evaluacion: "evaluation.md"
plan: improvement-plan.md
adr: "docs/knowledge/candidates/pending/2026-11-20-access-seams-server-capabilities.md"   # sha256 82c84969b6f7aa0f69e0aa780d2220973e11cbe43300506e3999469d7d9d7635
opcion_elegida: "O2"
generacion:
  inicio: 2026-11-20T08:37:10Z
  fin: 2026-11-20T08:59:18Z
  fuente: medido
  fuente_id: src-8ffaaac4e3b9a11805b5148dbea387f65be01b42fba05cbf3ca54c4b799a95c8
  ventana_id: win-bb4d799eb8a04707add9f9a8686adc0a
  revision_medicion: 3
  medicion_persistida: true
  tokens_reales: { entrada: 108, salida: 108782, cache_creacion: 287623, cache_lectura: 10451401, respuestas: 52 }
  eur: null               # precioTokens no fiable: ejecutar rates-verify
  horas_ia: 1.32
  duracion: 1h 19m         # reloj: 22m; las dos pasadas
  ratio_usado: 300000     # default no calibrado
---

# Diseño — Control de acceso y privacidad (Iniciativa 4)

> **Spec:** [`spec.md`](spec.md) (aprobada) · **Evaluación:** [`evaluation.md`](evaluation.md) (go con condiciones, 3 hitos) · **Plan:** [`improvement-plan.md`](improvement-plan.md) (borrador) · **ADR:** propuesta en [`2026-11-20-access-seams-server-capabilities.md`](../../knowledge/candidates/pending/2026-11-20-access-seams-server-capabilities.md), a la espera de `knowledge-curator`

| | |
|---|---|
| **Estado** | aprobado |
| **Opción elegida** | O2 — Costuras de acceso |
| **Validada por el usuario** | 2026-11-20, a través del orquestador `/dev-cycle`; literal: «2: un sitio para cada cosa (Recommended)» |

## 1. Contexto y restricciones

La spec pide tres cosas que condicionan el diseño. El acceso se retira con efecto en la petición siguiente y en todas las rutas (CA-01 a CA-11). Un cliente abusivo o con mala contraseña no deja sin servicio a los demás (CA-12 a CA-21). Toda la gestión está en el portal, con su equivalente por API (CA-39 a CA-43). CA-38 exige además que roles, grupos o inicio de sesión único entren solo con tablas o columnas nuevas.

La spec deja siete puntos provisionales (D-01 a D-07) y la evaluación señala cinco decisiones que cruzan componentes. Este documento las cierra todas. Las que no dependen de la opción global están decididas en «Decisiones comunes» (DC-1 a DC-10); el usuario solo elige lo que cambia entre O1, O2 y O3.

**Qué hay hoy** (verificado sobre `45fd4fb`):

| Tema | Hecho | Dónde |
|---|---|---|
| Resolvedor | `_active`, `_global_admin`, `_require` y `_delegate` deciden y guardan su respuesta lo que dura la transacción | `server/memory_platform/store_auth.py:58-84,160-169`, `auth_scope.py:44-50` |
| Lecturas que deciden fuera de él | `Auth._actor` compone permisos y proyectos; `/metrics` mira `actor['is_admin']`; `list_projects` filtra por permisos; `list_keys` decide con una consulta propia | `auth.py:43-54`, `app.py:201-203`, `store_auth.py:96-103`, `store_auth.py:209-212` |
| Guardas que ya existen | Un recorrido del paquete detecta todo escritor de las tablas de permisos que no vacía la caché, toda transacción sin resolvedor y todo lector de `project_grants` o `api_keys` fuera de una lista | `server/memory_platform/tests/test_auth_cache.py:359,442,461` |
| Portal | Decide con `scopes.includes('admin')`. `/v1/auth/me` publica `id`, `username`, `scopes` y `project_ids` | `web/src/memory-portal.ts:75,609`, `app.py:64-65` |
| Errores | `MemoryError` no lleva cabeceras. Los dos MCP pasan el mensaje del servidor, sin tocarlo, al error de herramienta | `errors.py:4-10`, `app.py:133-139`, `mcp.py:49-53`, `mcp/kairos_mcp/client.py:39-42` |
| `kairos-mcp` | Descarta las cabeceras de `/v1`. Llama a `/v1/auth/me` solo cuando el cuerpo no es una `tools/call`, y en las herramientas `local` | `mcp/kairos_mcp/client.py:80-92`, `mcp/kairos_mcp/auth.py:37-45,75`, `mcp/kairos_mcp/translate.py:191-200` |
| Cliente | Descarta el texto de un error de herramienta (`mcp_tool_rejected`). Suma el intento antes de llamar a `remember` | `client/lib/mcp.mjs:92`, `client/lib/dispatcher.mjs:134-135` |
| Login | `login` corre en el pool de hilos de la API y scrypt se ejecuta fuera de la transacción | `app.py:207-213`, `auth.py:74-93` |
| scrypt en otros contenedores | `memory-bootstrap` crea el primer usuario con un `mem_limit` de 256 MB | `docker-compose.yml:118-121`, `store_auth.py:48-49` |
| Sonda | `memory-probe` escribe y retira una nota cada 300 s con su propia clave | `docker-compose.yml:288-303` |

**Restricciones que fijan el espacio de soluciones**

- Migraciones solo aditivas. La versión 13 se define entera en el hito A (D-07) y CA-10 la limita a «columnas e índices».
- `docs/contracts/kairos-mcp.json` no cambia: mismas herramientas y mismos esquemas (CA-20, CA-26, CA-37).
- Ninguna prueba toca recursos `knowledge-graphs-*` (`CLAUDE.md`).
- `memory-api` es un proceso Python único (`app.py:504`). Todo trabajo nuevo por petición queda acotado, fuera del bucle de eventos y con plazo (retro de la Iniciativa 2, aprendizaje 1). Aplica a scrypt y a las expresiones regulares de la redacción.
- Hipótesis de la spec: una sola réplica de `memory-api` en el VPS. O1 y O2 dependen de ella; O3 no.
- No existen `docs/CONSTITUTION.md` ni ADR en `docs/knowledge/adr/`: ninguna decisión previa acota las opciones.
- El presupuesto es el de `evaluation.md` (582 h, tres hitos). Este diseño no re-estima.

**Invariantes, propiedad de los datos y estados:**

- Invariante 1. Una credencial retirada recibe 401 en la petición siguiente: en `/v1`, en los dos `/mcp` y en un flujo abierto.
- Invariante 2. Todo cambio en `actors`, `project_grants`, `api_keys` o `web_sessions` vacía la caché de permisos de su transacción y deja un evento de auditoría.
- Invariante 3. Ningún tope de un cliente (login, tasa, cuota, flujos) cambia la respuesta que recibe otro.
- Propiedad. Solo `memory-api` escribe identidad, permisos y contadores de límites. `kairos-mcp` no guarda nada. El cliente es dueño de su cola y de su `credential.json`.
- Estados. Clave: `activa → en gracia → caducada` y `activa → revocada`; de `revocada` y `caducada` no se vuelve. Usuario: `activo ⇄ deshabilitado`. Sesión: `abierta → cerrada` o `abierta → caducada`, sin vuelta.

## 2. Opciones (2-3)

### Decisiones comunes a las tres opciones

Estas diez decisiones valen para O1, O2 y O3. Cada una dice por qué no depende de la opción.

**DC-1 · Qué es «decidir un acceso» y qué queda fuera (D-02, CA-38 a).** Una función decide un acceso cuando su resultado cambia si la petición sigue o qué filas ve quien llama. Esas lecturas viven solo en el resolvedor. La definición es la misma en las tres opciones; cambia cómo se organiza lo nuevo alrededor.

| Función del resolvedor | Estado | Qué responde |
|---|---|---|
| `_load_active`, `_active` (`store_auth.py:12-29,58-61`) | existe | ¿La credencial sigue viva? |
| `_global_admin` (`store_auth.py:63-66`) | existe | ¿Es administrador global con sesión? |
| `_require` (`store_auth.py:68-84`) | existe | ¿Tiene este permiso en este proyecto? |
| `_delegate` (`store_auth.py:160-169`) | existe | ¿Puede delegar estos permisos en estos proyectos? |
| `_describe` | nueva: sale de `Auth._actor` (`auth.py:43-54`) | Permisos y proyectos de la credencial recién probada |
| `_visible_projects` | nueva: sale de `list_projects` (`store_auth.py:96-103`) | ¿Qué proyectos ve? |
| `_admin_somewhere` | nueva: sale de `list_keys` (`store_auth.py:209-212`) | ¿Administra algún proyecto? |
| `authenticate_bearer`, `authenticate_session` (`auth.py:56-72`) | existen | Prueba de credencial: buscan el token y llaman a `_describe` |

`/metrics` en modo `admin` (`app.py:201-203`) llama a `_global_admin` dentro de una transacción. Deja de fiarse del `is_admin` que viaja en el diccionario del actor.

Lista cerrada de excepciones del test:

| Lectura | Por qué no decide |
|---|---|
| `corpus_answers.py:133-143` y `extended_store.py:54-66` | Son bloqueos `FOR SHARE`: descartan las filas y llaman al resolvedor después de `invalidate_auth` |
| `list_users` (`store_auth.py:187-194`) | Muestra permisos de otros usuarios a quien `_global_admin` ya admitió |
| `list_keys`, `revoke_key` y la rotación nueva (`store_auth.py:206-235`) | Leen claves como recurso (la clave listada, revocada o rotada), no la credencial de quien llama. Cada fila pasa por `_require` |
| `probe.py:678-681,722-733,780-793` | Comando de operador en conexión directa, sin actor de petición |

> **Nota 2026-11-20 (fase 1, fix2).** El test añade, frente a esta lista, las excepciones que el recorrido real exige. Ninguna decide un acceso. `auth.py:login`: solo la lectura de fila completa (`SELECT *` sobre `actors`), que entrega entera a `_actor` → `_describe`, el único que mira `is_admin`; leer `is_admin` por nombre en `login` falla. `admin.py:inspect_store` y `backup.py:table_digest`: componen un `SELECT` sobre cualquier tabla del esquema para contar o resumir filas, y solo se admiten mientras compongan solo `SELECT`. `admin.py:prune_tables`: quinto escritor de `web_sessions`, acotado a sesiones ya muertas (caducadas o revocadas antes del corte, predicado exacto fijado en el test): ningún acceso cambia, no hay permisos que vaciar en una transacción de operador, y cada ejecución deja un evento `retention_prune`, no uno por fila. También quedan en la lista cerrada de SQL con tabla compuesta (`DYNAMIC_SQL`) las funciones que eligen entre dos tablas constantes (`store_jobs.py`, `derive_single_fragment`) y `migrate_vector_indexes`.

> **Nota 2026-11-20 (fase 1, fix5).** No hay silencios por la forma del SQL: cualquier `is_admin` en un literal SQL fuera del resolvedor es lectura, también al escribirlo, y un escritor legítimo se declara por función en la lista cerrada del test, dentro de la cual todo `is_admin` pasa (coste asumido, como en `probe.py`). Entra `store_auth.py:bootstrap_user`: escribe `is_admin=true` del primer actor y devuelve la fila guardada; no decide ningún acceso, el candado `pg_advisory_xact_lock` y el `Conflict` si ya hay actores lo limitan al primer arranque. `probe.py:provision_locked`, que escribe `is_admin=false` del actor de servicio, ya estaba.

> **Nota 2026-11-20 (fase 1, fix8).** La guarda ya no interpreta SQL con expresiones regulares: analiza cada literal SQL con el parser de PostgreSQL 17 (`pglast` 7.24, libpg_query 17), una dependencia solo de la imagen de pruebas (`server/requirements-test.txt`, etapa `test` del Dockerfile; no está en `api`, `operator` ni `worker`). El árbol dice qué tablas se leen y escriben, si se toma una fila completa de `actors` (con alcance por consulta, CTE, subconsulta y sentencia) y qué bloqueos `FOR SHARE` hay; `is_admin` sigue siendo cualquier literal que escriba la palabra. Lo que no se parsea y nombra una tabla de la guarda, o lleva un hueco, es rojo (`unparseable SQL`) salvo en las funciones de la lista cerrada. No cambia qué decide un acceso ni la lista de excepciones, salvo seis funciones que arman SQL por fragmentos y solo quedan exentas de ese tipo.

> **Nota 2026-11-20 (fase 1, fix9; corrige la de fix8).** La guarda analiza todo literal SQL que nombre una tabla vigilada o lleve un hueco, empiece como empiece (fragmentos, `EXPLAIN`, `DO $$...$$`), y cuando no parsea informa también de las tablas que nombra y de los huecos de tabla; las seis exenciones de `unparseable SQL` de fix8 sobran y se retiran. Queda un límite declarado: lo que ni nombra una tabla vigilada ni lleva un hueco no se analiza.

El test amplía el recorrido que ya existe en `test_auth_cache.py:461`. Añade `actors.is_admin` (en SQL y en accesos `['is_admin']` o `.get('is_admin')`) y exige una justificación escrita por excepción. Es la primera tarea del hito A.

Las ampliaciones futuras entran así (base de la nota de CA-38 c en `docs/architecture.md`):

| Ampliación | Tablas nuevas | Qué cambia en el código |
|---|---|---|
| Roles o grupos | `roles`, `role_permissions`, `actor_roles` (o `groups`, `group_members`, `group_grants`) | `_require`, `_describe` y `_delegate` unen los permisos directos con los heredados. `project_grants` conserva su significado |
| Inicio de sesión único | `actor_identities(provider, subject, actor_id)` | Una ruta de login nueva que abre la misma fila de `web_sessions`. scrypt queda para las cuentas locales |
| Operaciones en bloque | ninguna | Rutas nuevas que llaman en bucle a los mismos escritores |

**DC-2 · Un 429 con una sola forma (D-01, lado servidor).** Un módulo nuevo, `server/memory_platform/limits.py`, construye todo 429 de límites. No depende de la opción porque la forma de la respuesta no depende de dónde vive el contador.

- Estado 429, cabecera `Retry-After` en segundos enteros (mínimo 1) y cuerpo `{"error": {"code", "message", "retry_after"}, "request_id"}`.
- El mensaje es fijo y completo por código. Ejemplo: `Rate limit exceeded [code=rate_limited retry_after=17]`. Los otros dos empiezan por `Daily write quota exceeded` y `Too many activity streams`.
- `MemoryError` (`errors.py:4-10`) gana un `retry_after` opcional. `error()` (`app.py:133-135`) y `AuthenticatedMCP` (`mcp.py:187-211`) añaden la cabecera cuando existe.
- El plazo viaja en el mensaje porque `kairos-mcp` descarta las cabeceras (`mcp/kairos_mcp/client.py:80-92`) y los dos MCP ya pasan el mensaje sin tocarlo. `kairos-mcp` no necesita código de traducción. Un test suyo fija el texto: `Error executing tool remember: Rate limit exceeded [code=rate_limited retry_after=17]`.
- El contrato MCP no cambia: es un resultado `isError` con la forma actual (`mcp/kairos_mcp/tools.py:82-84`).
- El bloqueo de login por IP usa el mismo constructor, con `rate_limited`.

**DC-3 · La exención de `kairos-mcp` es de la ruta, no de quien llama.** `GET /v1/auth/me` pertenece a la clase `identity`: no gasta del cubo de la credencial ni de su cuota. No hay cabecera ni secreto que suplantar, porque la exención vale para cualquiera que llame a esa ruta.

- La clase `identity` tiene un cubo propio por credencial, para que no sea una vía sin tope. Si se agota, `kairos-mcp` no rechaza la petición: solo rechaza con un 401 (`mcp/kairos_mcp/app.py:51-57`).
- `limits.py` guarda una tabla cerrada `operation_id → clase`: `exempt` (`/health/*`, `/metrics`, login, logout), `identity`, `read`, `write` (cuenta para la cuota) y `stream`. No se clasifica por método HTTP: `/v1/search` y `/v1/context` son `POST` de lectura (`app.py:423-433`).
- Un test recorre las rutas de la aplicación y falla si alguna no tiene clase. Sigue el patrón de `RouteTableTests` (`test_auth_cache.py:529`).
- El límite se cobra después de autenticar y por identificador de credencial (`key_id` o `session_id`). Se llama desde `identity()` (`app.py:159-170`) y desde `AuthenticatedMCP` (`mcp.py:187-211`). Las herramientas de escritura del MCP interno cobran cuota en `stored()` (`mcp.py:59-65`).
- Una petición sin credencial válida recibe 401 antes y no crea estado en el limitador.

**DC-4 · Para el cliente, un 429 es una espera y no un intento (D-01, lado cliente).** Vale para las tres opciones porque el cliente no sabe dónde cuenta el servidor.

- `MCPTransport.call` (`client/lib/mcp.mjs:90-94`) lee el texto del error de herramienta y lo compara entero con los tres mensajes fijos. Si coincide, lanza un `KairosError` con el código y un plazo. También reconoce un 429 HTTP con `Retry-After`: lo devuelve el MCP interno y lo devolverá el proxy de la Iniciativa 5.
- Se compara la cadena entera, no se busca el patrón dentro. Así un mensaje de validación que cite texto capturado no puede fingir un límite.
- `Dispatcher.tick` (`client/lib/dispatcher.mjs:139-145`) trata ese error aparte. Devuelve `attempts` al valor anterior, porque el intento ya se sumó en la línea 135. No suma `failures`. Fija `next_attempt_at` con el plazo. Detiene todos los envíos hasta entonces, porque el límite es de la clave y no de la captura.
- El plazo se acota entre 1 s y 24 h más un margen.
- La fase sigue en `unknown`. El reintento pregunta `event_status` antes de repetir, como hoy (`dispatcher.mjs:127-133`). Esa regla no cambia.
- Una captura limitada nunca pasa a `failed`. `kairos doctor` ya avisa de una cola parada (`capture_queue_stale`, `client/lib/mcp.mjs:117-120`) y `status()` muestra el código.

**DC-5 · Tope de logins: un semáforo que una sola IP no puede llenar (R-02).** Un módulo nuevo, `server/memory_platform/passwords.py`, reúne todo scrypt: `hash_password`, `verify_password`, el hash ficticio y el semáforo. No depende de la opción en O1 y O2; O3 solo cambia dónde viven los huecos.

| Aspecto | Decisión |
|---|---|
| Dónde | Semáforo en memoria del proceso con `MEMORY_LOGIN_CONCURRENCY` huecos. Lo usan todas las derivaciones scrypt de la API: login, cambio de contraseña y alta de usuario |
| Orden | 1) IP bloqueada por fallos: 429, sin tocar scrypt. 2) Una IP ocupa como mucho un hueco, en uso o en espera. 3) Espera acotada: como mucho tantas peticiones en espera como huecos, y 2 s. 4) scrypt |
| Qué responde lleno | 503 `login_busy` con `Retry-After`. No cuenta como fallo de login ni toca el contador de la IP |
| Por qué no bloquea a otros | Una IP gasta un hueco y, tras diez fallos, ninguno. El ataque desde muchas IP a la vez queda como deuda declarada del proxy público (Iniciativa 5) |
| Memoria | Huecos × unos 128 MB con `n=2^17, r=8`. El número de huecos sale de la medición de CA-09 |
| Coste constante | Cada intento hace exactamente una derivación con el coste objetivo. Es la verificación (hash nuevo), el hash ficticio (usuario inexistente o deshabilitado) o, con un hash antiguo, la verificación barata más una derivación de coste objetivo |
| Rehash transparente | Con un hash antiguo y la contraseña correcta, esa derivación de coste objetivo es el hash nuevo. Se guarda en la transacción que abre la sesión, con `UPDATE … WHERE password_hash=<el leído>`. Si la escritura falla, el login sigue |
| Techo | `verify_password` rechaza parámetros guardados por encima del objetivo |

Con `MEMORY_TRUSTED_PROXIES` vacío todos los clientes comparten la IP del proxy, como hoy. En ese caso la regla 2 deja un login a la vez. El despliegue en Compose la define.

Tres hipótesis se miden en CA-09 y no se dan por ciertas: `hashlib.scrypt` libera el GIL, cuánta memoria ocupa la API en reposo, y `memory-bootstrap` (256 MB) y `memory-admin` pueden derivar con el coste objetivo.

**DC-6 · Esquema 13: lista cerrada (D-07, CA-10).** Todo se crea en el hito A. Solo columnas e índices, como exige CA-10.

| Tabla | Columna o índice | Tipo | Quién lo usa | Hito que lo usa |
|---|---|---|---|---|
| `memory.api_keys` | `last_used_at` | `timestamptz` | CA-06, CA-41 | A |
| `memory.api_keys` | `replaced_by` | `text` (identificador de la clave sucesora) | CA-07: una clave ya rotada no se rota otra vez | A |
| `memory.api_keys` | `limits` | `jsonb`; `NULL` significa valores globales | CA-17, CA-18: anulación por clave | B |
| `memory.api_keys` | `write_quota_day` | `date` | CA-18 | B |
| `memory.api_keys` | `write_quota_used` | `integer NOT NULL DEFAULT 0` | CA-18 | B |
| `memory.web_sessions` | `created_at` | `timestamptz DEFAULT clock_timestamp()` | CA-05, CA-40: lista de sesiones | A |
| `memory.web_sessions` | `client_ip` | `text` | CA-05, CA-40 | A |
| `memory.login_attempts` | índice `login_attempt_ip_time (client_ip, happened_at)` | — | CA-13: recuento por IP en cada login | A |
| `memory.web_sessions` | índice `web_session_actor (actor_id) WHERE revoked_at IS NULL` | — | CA-01, CA-03, CA-05: cerrar todas las sesiones de un usuario | A |

- `limits` es `jsonb` porque la forma del cubo se fija en el hito B, tras medir (CA-16), y la versión 13 se cierra en el hito A.
- `actors`, `project_grants` y `audit_events` no cambian. `disabled`, `is_admin` y `expires_at` ya existen (`schema.sql:3,6`). Las acciones nuevas (`password.changed`, `user.disabled`, `user.enabled`, `grants.replaced`, `sessions.revoked`, `key.rotated`) son valores nuevos de `audit_events.action`.
- `login_attempts` conserva sus columnas. Desde esta versión solo se insertan fallos. Las filas anteriores a la actualización, que incluyen aciertos, cuentan como fallos durante 15 minutos como mucho.
- La lista de sesiones muestra creación, caducidad, IP y cuál es la actual. No guarda agente de usuario ni última actividad: ningún criterio los usa y la versión 13 no se reabre.
- O3 añade tres tablas (ver O3), que CA-10 no admite tal como está escrita.

**DC-7 · `kairos doctor` y la caducidad (D-04, CA-08).** Es del cliente y de `/v1/auth/me`; ninguna opción lo cambia.

- `/v1/auth/me` añade, para una clave, `key: {id, name, prefix, expires_at}`. Son campos nuevos y opcionales.
- `doctor --online` llama a `GET <url>/v1/auth/me` con la clave. Es una lectura nueva del cliente y cae en la clase `identity`. Si responde 200, guarda `credential.json` en el directorio de estado del enlace (`client/lib/lifecycle-config.mjs:7-23`) con `key_id`, `prefix`, `expires_at` y `checked_at`.
- Ese directorio ya es distinto por raíz, URL, proyecto y ruta del fichero de clave. Dentro, el dato solo vale si el `prefix` guardado coincide con los diez primeros caracteres de la clave actual. Es el mismo prefijo que el servidor ya guarda y lista (`store_auth.py:201`). Un fichero con otra clave no hereda la caducidad.
- Sin red, `doctor` avisa si `expires_at` vence en menos de 14 días. Ante un 401 dice «clave caducada» si el dato vale y ya venció, y «clave inválida» en cualquier otro caso.

**DC-8 · Portal: «Mi cuenta» y el alta delegada (D-05, D-06).** La presentación es la misma; entre opciones cambia de dónde saca el portal qué mostrar.

- «Mi cuenta» es una vista nueva, `account`, con entrada en la barra superior junto a «Salir» (`web/src/memory-portal.ts:182-183`). La ve cualquier sesión. No vive dentro de `settingsView`, que sigue reservada a quien administra (`memory-portal.ts:608-609`).
- Alta delegada. El administrador de proyecto ve la pestaña «Usuarios» solo con el panel «Crear usuario». El formulario ofrece los proyectos y permisos que puede delegar. Tras el alta ve una confirmación y la lista de las altas de esa visita, guardada en memoria y perdida al recargar. Un texto explica que la lista completa es del administrador general. `GET /v1/users` no cambia.
- Deshabilitar, cerrar sesiones, revocar y rotar sin gracia piden confirmación con el diálogo que ya existe (`memory-portal.ts:693-696`).

**DC-9 · Pruebas del portal en dos niveles (CA-39 a CA-43).** La spec ya fija los niveles; el diseño reparte qué prueba cada uno.

| Nivel | Qué prueba | Qué no prueba |
|---|---|---|
| DOM de frontera, `web/tests/` (CI) | Qué controles ve cada perfil: administrador global, administrador de proyecto y usuario sin administración. Que cada acción llama a su ruta `/v1` con su cuerpo. Errores junto al campo. Campos de contraseña vacíos tras enviar. Lista actualizada sin recargar. Paridad con el OpenAPI (CA-43) | Cookies, CSRF real, foco y teclado |
| Chromium real, `server/memory_platform/Dockerfile.e2e` + `tests/e2e_portal.py` (Docker local) | Un flujo por criterio (CA-39 a CA-42) contra API y base de fixture: sesión real, CSRF y el 401 de una segunda sesión tras cerrarla o deshabilitar a su dueño | La matriz completa de perfiles |

Chromium no entra en la CI en esta iniciativa. Depende de dos etiquetas locales (`Dockerfile.e2e:1-2`) y la CI ya dejó de ejecutarse por causas externas (retro de la Iniciativa 3, aprendizaje 4). Su resultado se anota en el ledger. La primera tarea del portal ejecuta el arnés tal cual y anota su estado: su última evidencia es del 2026-11-06 (R-06).

**DC-10 · Los comandos `admin` usan los mismos escritores que `/v1`.** `set-password`, `disable-user` y `enable-user` llaman a los métodos del store, como `bootstrap` llama hoy a `bootstrap_user`. No hay SQL propio en `admin.py`. Así la auditoría, el cierre de sesiones y el vaciado de caché tienen una sola implementación.

### O1 — Ampliar en el sitio

Aplica los valores provisionales de la spec con la menor estructura nueva. Es lo que presupuestó la evaluación.

- **Escritores.** Cambio de contraseña, deshabilitar, permisos, sesiones y rotación son métodos nuevos de `AuthMixin` en `store_auth.py`. Cada uno llama a `_audit` y a `invalidate_auth` a mano, como los cinco actuales.
- **Qué sabe el portal.** `/v1/auth/me` añade `is_admin` y los permisos propios por proyecto. El portal deduce qué mostrar: `is_admin` para la administración nueva, y `admin` en algún proyecto para el alta delegada y las claves.
- **Límites.** El cubo de tasa y los huecos de flujos viven en memoria, en `limits.py`. La cuota se guarda en `api_keys` con escritura agrupada (detalle abajo).
- **Portal.** Las tres secciones crecen dentro de `web/src/memory-portal.ts` (`accessSettings`, líneas 641-670).

Cuota en O1 y O2 (D-03):

- La API lleva el contador en memoria y parte de `write_quota_day` y `write_quota_used`, que lee con la fila de la clave al autenticar (`auth.py:49`).
- Escribe en la base, en una transacción corta propia, en cuatro casos: hay 20 escrituras sin guardar (lote provisional, a fijar con CA-16), la clave llega a su cuota, pasó un minuto desde la última escritura (así se actualiza `last_used_at`) o la API se apaga.
- Pérdida máxima tras una caída: un lote por clave. Tras una parada ordenada, nada. Una clave agotada ya está guardada y sigue en 429 al reiniciar.
- El día es UTC. El `Retry-After` de `quota_exceeded` son los segundos hasta las 00:00 UTC.
- El reloj de `limits.py` se inyecta en los tests (R-10).
- La escritura usa un `lock_timeout` corto y, si no entra, se reintenta en la ocasión siguiente. Los bloqueos `FOR SHARE` de `extended_store.py:59` y `corpus_answers.py:137` chocan con un `UPDATE` de la misma fila.

Flujos en O1 y O2: cada hueco es una concesión en memoria que caduca a los 25 s que dura un flujo como máximo (`activity.py:38`) más un margen. El hueco se libera en el `finally` del generador y al terminar la respuesta. Un hueco perdido se libera solo al caducar.

| Criterio | Valoración |
|---|---|
| Complejidad | Baja. Dos módulos nuevos (`limits.py`, `passwords.py`); el resto crece donde está |
| Riesgo | Medio. `memory-portal.ts` (702 líneas, con líneas de más de 500 caracteres) recibe tres secciones: diffs difíciles de revisar y más intentos de revisión (R-09). La regla «quién ve qué» queda repartida por el portal. La auditoría depende de que cada escritor recuerde llamarla |
| Coste relativo | S. Es la base de la evaluación (C-05: test y traslado de lectores; C-08: `is_admin` en `/v1/auth/me`) |
| Reversibilidad | Alta. No añade superficie pública más allá de dos campos en `/v1/auth/me` |
| Extensibilidad | Media. Roles o grupos cambian el resolvedor y también el portal, que interpreta `is_admin` y `scopes` |
| Depende de una sola réplica | Sí: tasa, flujos y huecos de login son del proceso. La cuota no |

### O2 — Costuras de acceso

Reparte el estado igual que O1 (misma cuota, mismos flujos). Añade tres puntos únicos para lo nuevo, sin mover el resolvedor de `store_auth.py`.

- **Una puerta para los cambios.** Un mixin nuevo, `server/memory_platform/store_access.py`, reúne todos los escritores nuevos. Todos terminan en una función, `_access_changed`, que audita y vacía la caché. `test_auth_cache.py` comprueba que solo `store_auth.py`, `store_access.py`, `auth.py` y `probe.py` escriben las tablas de permisos.
- **El servidor dice qué puede hacer cada credencial.** El resolvedor calcula `capabilities` y `/v1/auth/me` las publica. Son las acciones de instancia permitidas (`users.list`, `users.manage`, `projects.create`, `account.password`, `account.sessions`) y, por proyecto, los permisos que la credencial puede delegar. El portal muestra controles solo según `capabilities`. El servidor sigue rechazando la acción (CA-38 b). Un test recorre acción → ruta y comprueba que una capacidad ausente implica 403.
- **Portal en módulos.** `web/src/access-panel.ts` («Usuarios» y «Claves para agentes») y `web/src/account-panel.ts` («Mi cuenta») se cargan como `corpus-panel.ts` (`memory-portal.ts:228`) y tienen sus tests. `memory-portal.ts` solo los monta. El DOM de frontera pasa a un fichero compartido entre tests.

La caché de permisos (R-01) queda cubierta igual en O1 y en O2: el recorrido de `test_auth_cache.py:359` detecta solo cualquier escritor nuevo. O2 añade la garantía de la auditoría y concentra el código nuevo en ficheros pequeños.

| Criterio | Valoración |
|---|---|
| Complejidad | Media. Tres módulos más (`store_access.py`, `access-panel.ts`, `account-panel.ts`) y un vocabulario cerrado de capacidades |
| Riesgo | Medio-bajo. Las capacidades pueden desviarse de lo que el servidor comprueba; lo cubre el test acción → ruta. El DOM de frontera se toca para compartirlo |
| Coste relativo | M. Supera la base de la evaluación en C-05 (capacidades y su test) y en C-08 (módulos y arnés). No cambia C-01 a C-04 ni C-06 |
| Reversibilidad | Media-alta. Los módulos son internos. `capabilities` queda publicado en `/v1/auth/me` y hay que mantenerlo |
| Extensibilidad | Alta. Roles, grupos o inicio de sesión único cambian el resolvedor y `capabilities`. El portal y los escritores no cambian |
| Depende de una sola réplica | Sí, igual que O1 |

### O3 — Estado en PostgreSQL

Mantiene las costuras de O2 y lleva a la base todo el estado de los límites. Es la única opción que no depende de una sola réplica.

- **Tasa.** Tabla `memory.rate_windows(credential_id, window_start, used)`. Cada petición autenticada hace un `INSERT … ON CONFLICT DO UPDATE` y lee el total. Es una ventana fija, no un cubo de fichas.
- **Cuota.** Exacta y sin lote: se cuenta en esa misma escritura.
- **Flujos.** Tabla de concesiones con caducidad.
- **Logins.** Los huecos son bloqueos consultivos de PostgreSQL. Cada login retiene una conexión del pool mientras dura scrypt.
- **Lo que arrastra.** Una escritura más por petición, en un pool que la Iniciativa 3 dimensionó sin ella (503 `store_busy`). Tres tablas nuevas y su purga en `admin.py:252-267`. Contradice dos textos de la spec: CA-10 («solo añade columnas e índices») y la fila «Límite de tasa» (cubo en memoria). Habría que enmendarla.

| Criterio | Valoración |
|---|---|
| Complejidad | Alta. Cuatro mecanismos nuevos sobre la base y su purga |
| Riesgo | Alto. Latencia y carga en cada petición; presión sobre el pool; enmienda de la spec; los tests de tasa pasan de reloj inyectado a tiempo de base (R-10) |
| Coste relativo | L. Desborda C-03 y toca el dimensionado del pool de la Iniciativa 3: pediría re-evaluar |
| Reversibilidad | Baja. Las tablas no se pueden borrar (migraciones aditivas) |
| Extensibilidad | Alta, como O2, y además admite varias réplicas de `memory-api` |
| Depende de una sola réplica | No |

### Qué cambia de verdad entre opciones

| Pregunta | O1 | O2 | O3 |
|---|---|---|---|
| ¿Quién decide qué enseña el portal? | El portal, con `is_admin` y permisos | El servidor, con `capabilities` | El servidor, con `capabilities` |
| ¿Dónde va el código nuevo? | En `store_auth.py` y `memory-portal.ts` | En módulos nuevos | En módulos nuevos |
| ¿Dónde viven tasa, flujos y huecos de login? | Memoria del proceso | Memoria del proceso | PostgreSQL |
| ¿Dónde vive la cuota diaria? | `api_keys`, por lotes | `api_keys`, por lotes | Tabla propia, exacta |
| ¿Cabe en la spec tal como está? | Sí | Sí | No: enmienda de CA-10 y de la fila de tasa |
| Coste frente a la evaluación | S | M | L |

Entre O1 y O2 cambia quién decide qué enseña el portal y cómo se reparte el código. Entre O2 y O3 cambia dónde vive el estado de los límites.

## 3. Criterios de decisión

1. **Retirar acceso sin huecos.** Es el criterio de cierre 2 del plan director y los invariantes 1 y 2. Pesa más que el coste: un fallo aquí es un hallazgo alto en la revisión de seguridad (CA-34).
2. **Diffs que se puedan revisar.** La revisión adversarial es el 40 % del presupuesto. Las retros de las Iniciativas 2 y 3 atribuyen sus desvíos a bucles de revisión y a fixes que abrían hallazgos nuevos. El código nuevo en ficheros pequeños acorta cada vuelta.
3. **Ampliable con cambios aditivos.** Lo pide CA-38 y lo preguntó el usuario («¿después se podrá ampliar?»).
4. **Coste frente a la evaluación.** Una opción que obliga a re-evaluar retrasa el plan.
5. **No pagar hoy por una hipótesis.** La spec prevé de 3 a 6 personas y una réplica. La Iniciativa 5 confirmará o no la réplica única.
6. **Reversibilidad.** Lo que entra en el esquema no sale; lo que se publica en `/v1` se mantiene.

## 4. Recomendación · opción elegida y por qué

**Recomendación del arquitecto:** O2 — Costuras de acceso.

- Criterio 2: el portal y los escritores nuevos quedan en ficheros pequeños. O1 los mete en `memory-portal.ts` (75 kB) y en `store_auth.py`, justo donde la evaluación ya ve un riesgo de revisión.
- Criterio 3: con `capabilities`, añadir roles o grupos cambia el resolvedor y nada más. En O1 habría que cambiar también el portal.
- Criterio 1: una sola función audita y vacía la caché en todo cambio de acceso, por `/v1` y por `admin`.
- Criterios 4 y 5: cuesta algo más que la base de la evaluación, pero no pide re-evaluar ni enmendar la spec. O3 paga una escritura por petición y tres tablas por una segunda réplica que hoy nadie ha decidido.
- Si la Iniciativa 5 decide varias réplicas, O2 deja el camino preparado: `limits.py` es el único punto que cambiaría, y la cuota ya vive en la base.

**O2 — Costuras de acceso.** El usuario la eligió el 2026-11-20 («2: un sitio para cada cosa (Recommended)»). El plan construye el control de acceso sobre tres puntos únicos: `store_access.py` para todo cambio de acceso, `capabilities` en `/v1/auth/me` para lo que enseña el portal, y `limits.py` para los límites, con el estado en memoria del proceso y la cuota en `api_keys`. La anclan los criterios 1, 2 y 3; cumple el 4 y el 5 porque no pide re-evaluar ni enmendar el esquema de la spec.

Descartadas:

- **O1 — Ampliar en el sitio.** Lleva el código nuevo a `memory-portal.ts` y `store_auth.py`, donde la revisión es más difícil (criterio 2). Deja en el portal la regla de quién ve qué, así que roles o grupos obligarían a cambiarlo (criterio 3).
- **O3 — Estado en PostgreSQL.** Añade una escritura por petición y tres tablas que no se pueden retirar (criterio 6). Contradice CA-10 y pide re-evaluar (criterio 4). Paga por una segunda réplica que nadie ha decidido (criterio 5).

Alternativas que no llegan a opción, con su motivo:

| Alternativa | Por qué no |
|---|---|
| Limitar la tasa en nginx (`limit_req`) | No admite anulación por clave ni `Retry-After` calculado. `web/nginx.conf` lo monta la instalación desplegada (R-07) |
| Limitar antes de autenticar, por hash del token | Cualquier token inventado crea estado: el limitador pasa a ser la vía de agotar memoria |
| Una credencial o cabecera interna para `kairos-mcp` | `kairos-mcp` no guarda credenciales (hecho 2 de la spec) y una cabecera se puede suplantar |
| scrypt en un pool de procesos | scrypt ya corre en el pool de hilos de la API y cada proceso extra consume memoria fija en un contenedor de 1 GB. Se reabre solo si CA-09 mide que `hashlib.scrypt` no libera el GIL |
| Tabla `key_usage` aparte para cuota y último uso | CA-10 limita la versión 13 a columnas e índices, y la spec ya sitúa `last_used_at` en `api_keys` |
| Mover el resolvedor a un paquete nuevo | Cambia el código más sensible y los nombres que `test_auth_cache.py` recorre, sin que ningún criterio lo pida |
| Comprobar permisos en la capa de rutas | Rompe la regla «comprobar, esperar, comprobar» que hoy se cumple dentro de la transacción (`auth_scope.py:4-12`) |

## 5. Impacto en módulos y ficheros

Tabla de la opción elegida, O2. El plan debe respetarla.

| Módulo / fichero (ruta real) | Cambio | Nuevo / modificado |
|---|---|---|
| `server/memory_platform/store_auth.py` | `_describe`, `_visible_projects` y `_admin_somewhere` entran en el resolvedor; caducidad opcional al crear clave; listados con `expires_at` y `last_used_at`. Los escritores nuevos no van aquí | modificado |
| `server/memory_platform/store_access.py` | Mixin con los escritores nuevos y `_access_changed`; cálculo de `capabilities` | nuevo |
| `server/memory_platform/store.py` | `Store` hereda el mixin nuevo | modificado |
| `server/memory_platform/auth.py` | `_actor` delega en `_describe`; login cuenta solo fallos por IP; scrypt sale a `passwords.py`; la sesión guarda `client_ip` | modificado |
| `server/memory_platform/passwords.py` | scrypt con coste objetivo, hash ficticio, semáforo acotado, rehash | nuevo |
| `server/memory_platform/limits.py` | Clases de ruta, cubo de tasa, cuota, huecos de flujos, constructor del 429. Estado en memoria del proceso; cuota en `api_keys` | nuevo |
| `server/memory_platform/app.py` | Rutas nuevas de `/v1`; `identity()` cobra el límite; `error()` añade `Retry-After`; `/metrics` usa `_global_admin`; `public_actor` publica los campos nuevos; IP real con `MEMORY_TRUSTED_PROXIES` | modificado |
| `server/memory_platform/mcp.py` | `AuthenticatedMCP` cobra el límite y responde el 429 con cabecera; `stored()` cobra cuota en las escrituras | modificado |
| `server/memory_platform/activity.py` | El flujo libera su hueco al terminar | modificado |
| `server/memory_platform/errors.py` | `MemoryError` admite `retry_after` | modificado |
| `server/memory_platform/models.py` | Modelos de las rutas nuevas; `expires_at` opcional en `KeyInput` | modificado |
| `server/memory_platform/admin.py` | `set-password`, `disable-user`, `enable-user` sobre los escritores del store; `set-key-limits` escribe `api_keys.limits` | modificado |
| `server/memory_platform/config.py` | Variables nuevas de login, proxies, tasa, cuota y flujos | modificado |
| `server/memory_platform/observability.py` | Contadores de rechazos por motivo y de fallos de login | modificado |
| `server/memory_platform/schema.sql` | Versión 13: las columnas e índices de DC-6, sin tablas nuevas | modificado |
| `server/memory_platform/tests/test_auth_cache.py` | El recorrido incluye `is_admin` y la lista de excepciones con justificación; lista de módulos autorizados a escribir las tablas de permisos | modificado |
| `server/memory_platform/tests/test_migrations_additive.py` | Caso de la versión 13 y actualización desde 0.4.1 | modificado |
| `server/memory_platform/tests/test_contract_additive.py` | Base de contratos para los campos y rutas nuevos | modificado |
| `server/memory_platform/tests/e2e_portal.py` | Cuatro flujos de Chromium (CA-39 a CA-42) | modificado |
| `server/memory_platform/tests/e2e_fixture.py` | Siembra de usuarios, permisos y claves para esos flujos | modificado |
| `mcp/kairos_mcp/client.py` | Sin cambio de comportamiento; un test fija que el mensaje del 429 pasa intacto | modificado |
| `mcp/tests/test_limits.py` | Caso del 429 con el texto estable y contrato sin cambios | modificado |
| `client/lib/mcp.mjs` | `MCPTransport.call` reconoce los tres mensajes y el 429 HTTP; `doctor` lee `/v1/auth/me` y guarda `credential.json` | modificado |
| `client/lib/errors.mjs` | `KairosError` admite un plazo de reintento | modificado |
| `client/lib/dispatcher.mjs` | El 429 no consume intentos y detiene los envíos hasta el plazo | modificado |
| `client/lib/files.mjs` | Permisos del fichero de clave (CA-32) | modificado |
| `client/tests/dispatcher.test.mjs` | Cola con una clave limitada más de cinco veces y con cuota agotada | modificado |
| `client/tests/mcp.test.mjs` | Mensajes estables, caducidad guardada y avisos de `doctor` | modificado |
| `web/src/memory-api.ts` | Métodos de las rutas nuevas | modificado |
| `web/src/memory-types.ts` | Tipos de `Actor` con los campos nuevos y `capabilities` | modificado |
| `web/src/memory-portal.ts` | Vista `account` y entrada en la barra superior; monta los dos módulos nuevos y deja de decidir con `scopes` | modificado |
| `web/src/access-panel.ts` | «Usuarios» y «Claves para agentes», pintados según `capabilities` | nuevo |
| `web/src/account-panel.ts` | «Mi cuenta»: contraseña y sesiones | nuevo |
| `web/src/memory-portal.css` | Estilos de las secciones nuevas | modificado |
| `web/tests/memory-portal.test.mjs` | Perfiles y controles visibles; el DOM de frontera sale a un fichero compartido con los tests de los módulos | modificado |
| `web/nginx.conf` | Envía `X-Forwarded-For` a `memory-api` en sus tres bloques | modificado |
| `docker-compose.yml` | Variables nuevas; sin `./secrets` por defecto; `mem_limit` de `memory-bootstrap` si CA-09 lo pide | modificado |
| `docs/contracts/memory-platform.openapi.json` | Rutas y campos nuevos, aditivos | modificado |
| `docs/architecture.md` | Nota de extensibilidad (CA-38 c) a partir de DC-1 | modificado |
| `docs/configuration.md` | Variables nuevas y su valor por defecto | modificado |
| `docs/operations.md` | Recuperación del administrador y lectura de los 429 | modificado |

## 6. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| R-01: un escritor nuevo deja viva una revocación dentro de su transacción | Media | Alto | El recorrido de `test_auth_cache.py:359` detecta cualquier escritor sin vaciado. La tabla de rutas (`:529`) comprueba el 401 en cada ruta nueva. `_access_changed` vacía la caché por construcción |
| R-02: scrypt agota la memoria de `memory-api` | Media | Alto | Semáforo de DC-5 y huecos fijados con CA-09. Test con N = huecos + 5 |
| scrypt con el coste objetivo no cabe en `memory-bootstrap` (256 MB) | Media | Alto | CA-09 mide también `memory-bootstrap` y `memory-admin`. Si no cabe, sube su `mem_limit` en `docker-compose.yml` antes de cambiar el coste |
| Durante la migración de hashes, el tiempo de respuesta delata qué cuentas existen | Media | Medio | Una derivación de coste objetivo por intento, siempre (DC-5). Queda la diferencia de la verificación antigua, unas decenas de milisegundos, hasta el primer login de cada usuario |
| Las esperas del semáforo ocupan hilos del pool de la API | Baja | Medio | En espera, como mucho tantas peticiones como huecos y 2 s; el resto recibe 503 al instante |
| Un ataque de login desde muchas IP llena los huecos | Baja | Medio | Deuda declarada: corresponde al proxy público de la Iniciativa 5. Se anota en `docs/operations.md` |
| La escritura de uso choca con los bloqueos `FOR SHARE` de la fila de la clave | Media | Bajo | Transacción propia con `lock_timeout` corto y reintento en la ocasión siguiente. El contador sigue en memoria mientras tanto |
| La sonda o una reindexación agotan la cuota por defecto | Media | Medio | CA-16 mide sonda, hooks, reindexación y publicación antes de fijar valores. `limits` por clave para la sonda |
| Texto capturado imita el mensaje de límite y deja una captura esperando | Baja | Medio | El cliente compara la cadena entera con tres mensajes fijos y acota el plazo a 24 h. `capture_queue_stale` avisa de la cola parada |
| El prefijo de la clave en `credential.json` expone 7 caracteres del secreto | Baja | Bajo | Es el prefijo que el servidor ya guarda y lista. El fichero vive fuera del proyecto, en el directorio de estado. El test de CA-08 comprueba que la clave entera no aparece |
| Tasa, flujos y huecos de login se multiplican si hay varias réplicas | Baja | Medio | Hipótesis de la spec. Si la Iniciativa 5 decide varias réplicas, `limits.py` pasa su estado a la base; la cuota ya está allí |
| `capabilities` se desvía de lo que el servidor comprueba | Media | Bajo | Test acción → ruta: capacidad ausente implica 403. El servidor decide siempre |
| O2 supera la base de la evaluación en C-05 y C-08 | Alta | Bajo | Trabajo que la evaluación no contó. En C-05: cálculo y publicación de `capabilities`, su test acción → ruta y la lista de módulos autorizados a escribir. En C-08: dos módulos de portal y el DOM de frontera compartido. `architect` no pone horas: `/dev-cycle` decide si `evaluator` ajusta esas dos partidas o si `planner` las absorbe. C-01 a C-04, C-06 y C-07 no cambian por O2 |
| Las aclaraciones del usuario añaden trabajo fuera de O2 | Alta | Bajo | `admin set-key-limits` (C-03) y la medición de scrypt en dos contenedores más (mediciones previas, CA-09). El planner las incluye como tareas propias |
| R-06: el arnés de Chromium lleva sin ejecutarse desde el 2026-11-06 | Alta | Medio | Primera tarea del portal: ejecutarlo tal cual y anotar su estado |
| R-07: `web/nginx.conf` y `docker-compose.yml` los usa la instalación desplegada | Media | Alto | `MEMORY_TRUSTED_PROXIES` vacío se comporta como hoy. Ensayos con nombre de proyecto propio |
| R-09: cada fix de revisión abre un hallazgo nuevo | Alta | Medio | Cada fix que añade comportamiento pasa por las lentes completas (lección pendiente `2026-11-19-review-fixes-like-new-code.md`). El primer fix de un hallazgo de CPU pide trabajo acotado, fuera del bucle, vía rápida y plazo |
| R-10: tests con tiempo que fallan en CI | Alta | Medio | Reloj inyectado en `limits.py` y `passwords.py`. Caducidad y gracia fechando filas hacia atrás. Sin `sleep` |

## 7. Preguntas abiertas

Para el usuario: ninguna. Eligió O2 el 2026-11-20.

**Aclaraciones de la spec aprobadas por el usuario y pendientes de aplicar.** El usuario las aprobó el 2026-11-20 a través del orquestador (literal: «Sí, así (Recommended)»). `architect` solo escribe el enlace `design:` de `spec.md`; el texto de los criterios es de `analyst`. Ninguna cambia el número de criterios: siguen siendo 43.

| # | Dónde en `spec.md` | Texto propuesto |
|---|---|---|
| 1 | CA-07 y la fila «Rotar una clave revocada o caducada» de «Manejo de errores» | Añadir: «rotar una clave ya rotada y aún en periodo de gracia responde 409 y no emite clave» |
| 2 | CA-18, las filas «Límite de tasa» y «Cuota», y `admin.py` en «Arquitectura y componentes» | Añadir: «la anulación por clave la fija el operador con el comando `admin set-key-limits`; no tiene control en el portal ni ruta en `/v1`». Es una excepción declarada a «toda acción existe en `/v1`» |
| 3 | CA-09, la fila «scrypt (S-07)» y P-04 | Sustituir «dentro del contenedor de la API con su `mem_limit`» por «dentro de los contenedores que derivan scrypt, cada uno con su `mem_limit`: `memory-api`, `memory-bootstrap` (256 MB) y `memory-admin`» |
| 4 | Hecho 2 de «Otros hechos» y la fila «Validación de `kairos-mcp`» | «`kairos-mcp` no guarda credenciales. Valida el Bearer contra `/v1/auth/me` en las peticiones que no son una `tools/call` y en las herramientas `local`; una `tools/call` conoce su credencial por la petición a `/v1` que hace (`mcp/kairos_mcp/auth.py:37-45,75`, `mcp/kairos_mcp/translate.py:191-200`)». Ningún criterio cambia |
| — | «Decisiones confirmadas» | Entrada nueva con la fecha 2026-11-20, los cuatro puntos y el literal «Sí, así (Recommended)» |

Para el planner y el implementador:

- Valores numéricos tras medir: huecos de login (CA-09), tasa, ráfaga, cuota, lote de escritura y cubo de la clase `identity` (CA-16).
- Forma exacta de `limits` (`jsonb`) y su validación; la escribe `admin set-key-limits`.
- El actor con el que actúan los comandos `admin` no debe chocar con la regla «nunca a uno mismo» al deshabilitar a un administrador.
- Ruta del fichero de casos de redacción compartidos. Propuesta: `docs/contracts/redaction-cases.json`, que la imagen de test del servidor ya puede copiar junto a `docs/contracts/examples`.
- Qué plazo anuncia `too_many_streams`: el diseño propone el tiempo hasta que caduque la concesión más antigua de la credencial.
- La lista cerrada de nombres de `capabilities` y su columna en la tabla de paridad de CA-43.
- El plan registra en el ledger la ruta y el SHA-256 de la propuesta de ADR (bloque `curation-refs-v1`): `docs/knowledge/candidates/pending/2026-11-20-access-seams-server-capabilities.md`, `82c84969b6f7aa0f69e0aa780d2220973e11cbe43300506e3999469d7d9d7635`.

---

## Changelog

| Fecha | Cambio |
|---|---|
| 2026-11-20 | Diseño creado (`borrador`); tres opciones y diez decisiones comunes presentadas al usuario |
| 2026-11-20 | El usuario elige O2 («2: un sitio para cada cosa (Recommended)»). Estado `aprobado`. Tabla de impacto y riesgos podados a O2. ADR propuesto en `docs/knowledge/candidates/pending/`. Cuatro aclaraciones de la spec aprobadas por el usuario, anotadas en la sección 7 para `analyst` |
