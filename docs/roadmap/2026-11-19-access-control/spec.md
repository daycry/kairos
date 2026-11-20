---
spec: access-control
descripcion: Control de acceso y privacidad de Kairos — ciclo de vida de contraseñas, usuarios, sesiones y claves, login que no se bloquea entre clientes, límites por clave, redacción de secretos ampliada y compartida entre servidor y cliente, modelo de identidad con guía de alta y baja, y superficie de secretos acotada.
estado: aprobada          # borrador | aprobada | implementada | obsoleta
creado: 2026-11-19
actualizado: 2026-11-20
evaluacion: evaluation.md
design: design.md
plan: improvement-plan.md
generacion:
  inicio: 2026-11-19T16:25:09Z
  fin: 2026-11-19T16:41:35Z
  fuente: medido
  fuente_id: src-8ffaaac4e3b9a11805b5148dbea387f65be01b42fba05cbf3ca54c4b799a95c8
  ventana_id: win-d160bcbce17f45f78b88d4c127450e3d
  revision_medicion: 4
  medicion_persistida: true
  tokens_reales: { entrada: 50, salida: 60273, cache_creacion: 264999, cache_lectura: 3479592 }
  eur: null               # precioTokens no fiable: ejecutar rates-verify
  horas_ia: 1.08
  duracion: 1h 5m
  ratio_usado: 300000     # default no calibrado
---

# Control de acceso y privacidad (Iniciativa 4 del plan director)

> **Evaluación:** [evaluation.md](evaluation.md) — go con condiciones (2026-11-19)
> **Diseño:** [design.md](design.md) — aprobado (2026-11-20), opción O2 «Costuras de acceso»; cierra D-01 a D-07
> **Plan de implementación:** [improvement-plan.md](improvement-plan.md) · [tasks.md](tasks.md) · [test-plan.md](test-plan.md) — borrador (2026-11-20), 106 tareas en 18 fases y 3 hitos
> **Origen:** [plan director](../2026-11-10-platform-audit/plan.md), «Iniciativa 4 — Control de acceso y privacidad» (líneas 143-154), §4 «Restricciones permanentes» y decisión abierta 3; [auditoría](../2026-11-10-platform-audit/audit.md): S-01, S-02, S-03, S-07, S-08, S-10, S-11 y §6.1 (severidades elevadas por el VPS); [integración con custom-agents](../2026-11-10-platform-audit/custom-agents-integration.md), líneas 77-80 y 112.

> **Terminología:**
> - **Usuario**: fila de `memory.actors`; entra al portal con contraseña y obtiene una **sesión** (cookie).
> - **Clave**: credencial `mp_…` de `memory.api_keys`, enviada como `Authorization: Bearer`; pertenece al usuario que la crea y lleva su lista de proyectos y permisos.
> - **Permisos**: los cinco existentes, por proyecto: `read`, `write`, `publish`, `validate`, `admin`. Esta iniciativa no añade ninguno.
> - **Rutas**: `/v1` (API), `/mcp` del MCP interno de `memory-api` (obsoleto, montado mientras `MEMORY_MOUNT_MCP=1`), `/mcp` de `kairos-mcp` y el portal (sesión).
> - **Redacción**: sustituir un secreto por `[REDACTADO]` (servidor) o `[REDACTED]` (cliente) antes de guardar, enviar o escribir en un log.
> - **Administrador global** («administrador general» en la decisión 6): `actors.is_admin` con sesión. **Administrador de proyecto**: usuario con el permiso `admin` sobre un proyecto, sin ser administrador global.
> - **Hecho** (con `fichero:línea`, verificado el 2026-11-19 sobre `75c9638`; los añadidos en la revisión del 2026-11-20, sobre `a83fc99`) frente a **hipótesis** (marcada como tal).
> - **A confirmar en `design.md`**: default provisional que la spec fija para poder presupuestar y probar; `architect` lo confirma o lo sustituye en el diseño, sin cambiar el criterio observable. Lista completa en «Entrada para `design.md`».

## Contexto y objetivo

Kairos va a un VPS y lo usarán varias máquinas y, quizá, varias personas (auditoría §6.1). Hoy el acceso se puede conceder, pero casi no se puede retirar ni renovar, y el filtro de secretos tiene huecos. Estado de cada hallazgo en el código de hoy:

| Hallazgo | Estado hoy | Evidencia | ¿Entra? |
|---|---|---|---|
| **S-01** Redacción con huecos | **Abierto.** Las siete cadenas sintéticas de la auditoría (`SECRET_KEY=`, `DB_PASS=`, `sk_live_`, `glpat-`, `hf_`, `curl -u`, `mp_…`) salen sin redactar en servidor y cliente (comprobado hoy ejecutando ambos módulos). Los dos módulos ya divergen: `sk-` exige 32 caracteres en el servidor y 24 en el cliente. No hay casos compartidos | `server/memory_platform/privacy.py:17-27`, `client/lib/privacy.mjs:4,51-59` | Sí |
| **S-02** Login que se bloquea para todos | **Abierto** (purga resuelta). Cada intento se cuenta antes de verificar, acierte o no, y el bloqueo es `username` **o** IP. La IP es la del proxy: `request.client.host`, nginx no envía `X-Forwarded-For` y uvicorn arranca sin cabeceras de proxy. La purga de `login_attempts` ya existe (Iniciativa 3) | `auth.py:76-82`, `app.py:210`, `app.py:504`, `web/nginx.conf:60-65`; purga: `admin.py:252,266` | Sí, salvo la purga |
| **S-03** Ciclo de vida de credenciales | **Parcial.** El esquema ya tiene `actors.disabled` y `api_keys.expires_at`, y la autenticación los respeta; la revocación vale desde la petición siguiente (Iniciativa 3, CA-18). Pero nada los escribe: no hay cambio de contraseña, deshabilitar usuario, retirar permisos, revocar sesiones ajenas, caducidad al crear una clave ni rotación. Las únicas rutas son login, logout, crear y listar usuarios, crear, listar y revocar claves; `admin` solo tiene `bootstrap` | `schema.sql:3,6`, `auth.py:60,69`, `store_auth.py:12-29,171-235`, `models.py:83-92`, `app.py:206-221,246,262,369-379`, `admin.py:339-342` | Sí |
| **S-07** scrypt débil | **Abierto.** `n=16384` (2^14). El hash ya guarda sus parámetros (`v`, `n`, `r`, `p`), así que se puede reforzar al iniciar sesión. El hash ficticio para usuarios inexistentes fija el mismo `n` | `auth.py:22-23,85` | Sí |
| **S-08** Sin límites por clave | **Abierto** (mitigado en parte). Solo el login responde 429. El cuerpo está acotado y el pool agota con 503 `store_busy` (Iniciativa 3). Cada flujo de actividad dura 25 s como mucho y revalida la credencial en cada sondeo, pero no hay tope de flujos abiertos a la vez ni tasa por clave | `auth.py:81`, `app.py:79,470-484`, `activity.py:37,62-63` | Sí |
| **S-10** Secretos dentro del repo | **Parcial.** El despliegue exige `MEMORY_SECRETS_DIR` o `--secret-dir` y la documentación propone una ruta externa, pero nada comprueba que esté fuera del repositorio ni de una carpeta sincronizada; el Compose sigue cayendo en `./secrets`; `.private/` sigue dentro del repo (ignorado por git, sincronizado por OneDrive) | `scripts/deploy-memory.py:579-584,642,1124-1129`, `docker-compose.yml:337-339`, `docs/configuration.md:25`, `.gitignore:4,6` | Sí |
| **S-11** Permisos del fichero de clave | **Abierto.** El cliente comprueba que la clave esté fuera del proyecto, que sea un fichero y su tamaño; no mira permisos | `client/lib/files.mjs:64-78` | Sí |
| Red de inferencia privada | **Resuelto** (Iniciativas 2 y 3): red `inference` interna, proxy con lista de rutas permitidas y sin root | `docker-compose.yml:61-70,327`, `ollama-proxy/default.conf.template:39-58` | Solo una prueba de guarda |

Otros hechos que condicionan el diseño:

1. **El portal ya gestiona parte del acceso.** Tiene pestañas «Claves para agentes» y «Usuarios» para crear y listar, y revoca claves (`web/src/memory-portal.ts:612-666`). No tiene cambio de contraseña ni ninguna de las acciones nuevas.
2. **`kairos-mcp` no guarda credenciales.** Valida el Bearer contra `/v1/auth/me` en las peticiones que no son una `tools/call` y en las herramientas `local`; una `tools/call` conoce su credencial por la petición a `/v1` que hace (`mcp/kairos_mcp/auth.py:37-45,75`, `mcp/kairos_mcp/translate.py:191-200`). Hereda la revocación, y esas validaciones contarían de más en un límite por clave. (Corregido el 2026-11-20: antes decía «en cada petición».)
3. **Una clave de un usuario no administrador nunca supera los permisos de su dueño** (`store_auth.py:76-82`): retirar un permiso al usuario lo retira a sus claves.
4. **Los documentos y el estado de trabajo no se redactan: se rechazan** si contienen un secreto (`store_documents.py:80`, `agent_store.py:67`, `privacy.py:164-172`). Ampliar los patrones aumenta los rechazos que verá quien publique (custom-agents, Iniciativa 7).
5. **Un solo proceso de API** (`app.py:504`, sin `workers`): un límite en memoria del proceso es exacto hoy.

**Objetivo**: que el acceso a Kairos se pueda dar, acotar, renovar y retirar con efecto inmediato en todas las rutas; que un cliente abusivo o con mala contraseña no deje sin servicio a los demás; y que los secretos conocidos no lleguen a la base, a los logs ni a un tercero. Todo probado con fixtures aislados, sin tocar la instalación desplegada.

**Fuente**: encargo del orquestador `/dev-cycle` (2026-11-19) sobre la sección «Iniciativa 4» del plan director.

## Clasificación y primer oráculo

| Bloque | Clase | Primer oráculo (test que debe fallar antes del cambio) |
|---|---|---|
| A-01 Credenciales (S-03, S-07) | Capacidad nueva + defecto | Tras cambiar la contraseña, otra sesión del mismo usuario recibe 401; una clave creada con caducidad vencida recibe 401 |
| A-02 Login (S-02) | Defecto | Diez fallos desde la IP `a` para el usuario U; el login correcto de U desde la IP `b`, a través del proxy, responde 200 |
| A-03 Límites (S-08) | Capacidad nueva, **visible para clientes** | La clave K1 supera su tasa y recibe 429 mientras K2 sigue recibiendo 200 |
| A-04 Redacción (S-01) | Defecto + capacidad nueva, **visible para clientes** | El fichero de casos compartido con las siete cadenas de S-01 falla en las dos suites |
| A-05 Identidad | Documentación ejecutable | El test que sigue la guía de alta y baja no existe |
| A-06 Superficie (S-10, S-11) | Defecto | El despliegue acepta un directorio de secretos dentro del repo; el cliente acepta una clave con modo `0644` |
| A-07 Revisión y cierre | Proceso | — |
| A-08 Portal (P-02) | Capacidad nueva en la interfaz | La prueba de navegador que deshabilita un usuario desde la pestaña «Usuarios» no encuentra el control |

## Decisiones de diseño

P-01, P-02, P-03 y P-07 están confirmadas por el usuario (2026-11-19, ver «Decisiones confirmadas»). Las demás P-NN son técnicas y se adoptan como se indica salvo que el orquestador decida otra cosa.

| Decisión | Elección propuesta | Motivo |
|---|---|---|
| Alcance de la gestión de usuarios | **El usuario y de 2 a 5 personas más, con varias máquinas e integraciones** (P-01, confirmada). Toda acción existe en `/v1`; las de recuperación, también en `admin`; y todas, en el portal (P-02, confirmada). Excepción declarada (2026-11-20): la anulación de límites por clave solo existe como comando `admin set-key-limits` | Decisión abierta 3 del plan director, resuelta el 2026-11-19 |
| Extensibilidad (P-01) | **El diseño no cierra la puerta a roles o grupos, operaciones en bloque ni inicio de sesión único.** Los permisos se resuelven en un único punto, el resolvedor (`_active`, `_global_admin` y `_require`, `store_auth.py:58-84`); ninguna ruta ni pantalla decide permisos por su cuenta, salvo una lista cerrada y justificada de lecturas que no deciden un acceso (CA-38); la construcción del actor (`auth.py:44-50`) y la comprobación de `/metrics` (`app.py:202`) pasan al resolvedor, cuya frontera exacta queda a confirmar en `design.md`; lo nuevo se añade con tablas o columnas nuevas. Una nota de diseño en `docs/architecture.md` explica cómo se añadiría cada ampliación | El usuario preguntó si después se podrá ampliar; la respuesta es sí y debe ser comprobable (CA-38) |
| Portal (P-02) | **Toda la gestión de acceso está en el portal**, en las pestañas actuales «Usuarios» y «Claves para agentes» y en una sección «Mi cuenta»: alta de usuario, deshabilitar y rehabilitar, permisos por proyecto, cambio de contraseña, cierre de sesiones, caducidad y rotación de claves. El alta de usuario conserva la delegación actual (decisión 6): también la ejecuta un administrador de proyecto, solo para sus proyectos (`_delegate`, `store_auth.py:160-175`). Las acciones de administración **nuevas** (deshabilitar y rehabilitar, permisos por proyecto, sesiones ajenas) y el listado de usuarios solo los ve y los ejecuta el administrador global que ya existe (`is_admin`, `store_auth.py:63-66`); el servidor las rechaza aunque se llamen a mano. Cada acción del portal usa una ruta de `/v1` documentada en el OpenAPI, sin rutas privadas del portal | Respuesta del usuario: «Todo en el portal». El CLI y la Iniciativa 7 necesitan el equivalente por API |
| Cambio de contraseña | **`POST /v1/auth/password`** (contraseña actual y nueva; solo con sesión y CSRF). Revoca todas las demás sesiones del usuario y conserva la actual. No revoca claves | S-03. Las claves son credenciales independientes con su propia revocación |
| Recuperación del administrador | **`admin set-password --username --password-file`**, que revoca todas las sesiones del usuario | Sin correo ni segundo factor, el operador con acceso al servidor es la vía de recuperación |
| Deshabilitar usuario | **`PATCH /v1/users/{id}`** con `disabled` (administrador global) y `admin disable-user`/`enable-user`. Revoca sus sesiones; sus claves dejan de valer mientras esté deshabilitado. Nunca a uno mismo ni al último administrador activo. No se borran usuarios | `actors.disabled` ya se respeta (`auth.py:60,69`); migraciones aditivas |
| Retirar permisos | **`PUT /v1/users/{id}/grants`** sustituye los permisos por proyecto del usuario | S-03; las claves del usuario quedan acotadas por el hecho 3 |
| Sesiones | El usuario lista y cierra sus sesiones; un administrador cierra todas las de un usuario | S-03 |
| Caducidad de claves | **Solo si se pide** (P-03, confirmada): campo opcional de caducidad al crear; sin él, la clave no caduca. Las claves existentes no adquieren caducidad. La lista de claves y `/v1/auth/me` muestran `expires_at` | `api_keys.expires_at` ya existe y se respeta (`schema.sql:6`, `auth.py:60`) |
| Rotación | **`POST /v1/keys/{id}/rotate`**: emite una clave nueva con el mismo nombre, proyectos y permisos; la antigua caduca tras un periodo de gracia (24 h por defecto; 0 = inmediata) | Permite cambiar la clave de una máquina sin corte |
| Último uso | **`api_keys.last_used_at`** (columna aditiva, escritura como mucho una vez por minuto y clave) | Sin saber qué clave se usa no se puede rotar ni dar de baja con criterio |
| Aviso en el cliente | **`kairos doctor`** lee `expires_at` de `/v1/auth/me`, lo guarda en su estado local (sin la clave) y avisa cuando una clave **con caducidad** vence en menos de 14 días; ante un 401 dice «clave caducada» si el `expires_at` guardado ya venció y «clave inválida» en otro caso. El 401 del servidor no cambia. Con una clave sin caducidad no avisa | Una clave que caduca en silencio detiene la captura automática |
| scrypt (S-07) | **Parámetros objetivo provisionales `n=2^17, r=8, p=1`**, definitivos tras medir tiempo y memoria dentro de los contenedores que derivan scrypt, cada uno con su `mem_limit`: `memory-api`, `memory-bootstrap` (256 MB) y `memory-admin`; rehash al iniciar sesión con éxito; logins simultáneos acotados; el hash ficticio usa el coste objetivo (P-04) | `n=2^17` son unos 128 MB por verificación y `memory-api` tiene 1 GB en el VPS (`docs/configuration.md:172`). Aprendizaje 3 de la retro de la Iniciativa 3: medir antes de fijar |
| Qué cuenta el login (S-02) | **Solo los fallos.** Un acierto no cuenta ni borra los fallos de su IP | Diez aciertos ya no bloquean; un atacante con cuenta propia no limpia su contador |
| Cubos del login | **Bloqueo solo por IP de cliente** (10 fallos en 15 min, 429 con `Retry-After`). Los fallos por usuario se miden y se registran (`login_user_failures`), pero no bloquean (P-05) | Un bloqueo por nombre de usuario deja que cualquiera bloquee a `admin` desde fuera, justo lo que el criterio de cierre prohíbe |
| IP real | **`MEMORY_TRUSTED_PROXIES`** (lista de redes). nginx envía `X-Forwarded-For`; la API toma la dirección no fiable más a la derecha y solo si el par inmediato es de confianza. Sin proxies de confianza, se ignora la cabecera | Evita tanto la IP compartida como la suplantación por cabecera. Deja listo el encadenado con el proxy HTTPS de la Iniciativa 5 |
| Límite de tasa (S-08) | **Cubo de fichas por credencial en memoria de `memory-api`**, con valores por defecto globales y anulación opcional por clave (columna aditiva); la anulación por clave la fija el operador con el comando `admin set-key-limits`; no tiene control en el portal ni ruta en `/v1`. 429 `rate_limited` con `Retry-After`. Valores provisionales, fijados tras medir el perfil real del cliente (P-06) | Hecho 5. Aprendizaje 3 de la retro |
| Cuota | **Cuota diaria de escrituras por clave**, configurable, 429 `quota_exceeded`. Valor por defecto según P-06. El contador vive **en la base**, con escritura agrupada, y sobrevive a un reinicio de `memory-api` (default provisional, a confirmar en `design.md`). El cubo de tasa sigue en memoria. La anulación por clave la fija el operador con el comando `admin set-key-limits`; no tiene control en el portal ni ruta en `/v1` | El plan director pide cuota y tasa. En memoria, un reinicio pondría la cuota del día a cero |
| Flujos abiertos | **Tope de flujos de actividad simultáneos por credencial y global**, 429 `too_many_streams` | S-08 «SSE sin tope» |
| Validación de `kairos-mcp` | La lectura `/v1/auth/me` que hace `kairos-mcp` (en las peticiones que no son una `tools/call` y en las herramientas `local`) no consume del límite de la clave | Hecho 2: sin esto esas peticiones MCP gastarían límite sin hacer trabajo; una `tools/call` cuenta una vez, por su petición a `/v1` |
| 429 en el cliente y a través de `kairos-mcp` | **El 429 no consume intentos de la cola del cliente**, y el plazo de `Retry-After` viaja en el mensaje del error de herramienta con un formato estable, sin tocar los esquemas de `kairos-mcp.json` (default provisional, a confirmar en `design.md`) | Hoy la captura pasa a `failed` al quinto intento (`client/lib/dispatcher.mjs:134-144`) y un error de `/v1` llega como texto en un resultado `isError` (`mcp/kairos_mcp/tools.py:84`): sin esto, «sin pérdida» (CA-20) no se cumple |
| Casos de redacción compartidos | **Un fichero de casos** (entrada, qué debe desaparecer, qué debe conservarse) que leen la suite del servidor y la del cliente | S-01: los dos módulos ya divergen |
| Patrones nuevos | Nombres `*_KEY`, `*_PASS` y afines; prefijos `sk_live_`/`sk_test_`/`rk_live_`, `glpat-`, `hf_`, `npm_`, la clave propia `mp_`; `curl -u`/`--user`; `Authorization: Basic` | S-01 y formatos habituales |
| Detector de entropía | **Conservador** (P-07, confirmada): redacta una cadena de alta entropía solo si va junto a un nombre o contexto de secreto; nunca hashes, UUID, SHA de commit ni rutas | Hecho 4: un detector agresivo haría rechazar documentos legítimos con un hash |
| Dónde se aplica | En el cliente, antes de disco, cola y red (camino actual, `client/lib/capture.mjs:74`); en el servidor, al recibir, en todas las rutas que guardan texto. Sin reanálisis de lo ya guardado | Plan director. El VPS empieza de cero (decisión del 2026-11-12) |
| Identidad | **Un usuario por persona; una clave por máquina y otra por integración; cada clave con los proyectos y permisos mínimos.** Guía de alta y baja ejecutada por un test | Plan director, bloque «Identidad»; `custom-agents-integration.md:78` |
| Directorio de secretos (S-10) | El despliegue **rechaza** un directorio de secretos dentro del repositorio o de una carpeta sincronizada conocida (OneDrive, Dropbox, iCloud, Google Drive), antes de tocar nada. `.private/` se queda donde está y un test comprueba que no contiene secretos (P-08) | S-10 |
| Fichero de clave (S-11) | **POSIX**: el cliente falla con `key_file_too_open` si grupo u otros tienen permisos. **Windows**: `kairos doctor` avisa, en el mejor esfuerzo, de ACL abiertas o de una clave en carpeta sincronizada (P-09) | Windows no tiene modos POSIX; el equipo actual es Windows y el VPS, Linux |
| Revisión de seguridad | La hace un revisor distinto del implementador, sobre el diff completo y la superficie de acceso; severidades A/M/B de la auditoría. Cada fix se revisa como código nuevo | Criterio de cierre; aprendizaje 1 de la retro |
| Esquema 13 (restricción de entrega) | **El hito A define de una vez todas las columnas e índices de la versión 13**, incluidas las que usan hitos posteriores (anulación de límites por clave, `last_used_at` y lo que el diseño añada para la cuota). Ningún hito posterior reabre la versión 13 ni crea una versión 14 | La iniciativa se entrega en tres hitos (`evaluation.md`, R-13); una versión de esquema reabierta entre PR rompe la actualización de quien ya aplicó la primera |
| Pruebas del portal | **Dos niveles** para CA-39 a CA-42: DOM de frontera en `web/tests/` (CI) y Chromium real con `server/memory_platform/Dockerfile.e2e` y `server/memory_platform/tests/e2e_portal.py` (Docker local, fuera de la CI). Cada nivel declara su equivalente local (ver «Pruebas») | `web/tests/` no es un navegador: define sus propias clases `Element`, `Input` y `Select`. Aprendizaje 4 de la retro de la Iniciativa 3 |
| Versión | **0.4.2** de servidor, MCP y cliente (cambios aditivos); la 0.5.0 sigue reservada para retirar el MCP interno (P-10) | Continuidad con la Iniciativa 3, P-10 |

## Configuración / parámetros

Los valores numéricos marcados como provisionales se fijan en el plan tras medir (CA-09, CA-16).

| Parámetro | Clave / mecanismo | Default hoy | Valor objetivo |
|---|---|---|---|
| Proxies de confianza | `MEMORY_TRUSTED_PROXIES` (nuevo) | — (se usa la IP del par) | redes internas del Compose en el despliegue; vacío fuera de él |
| Fallos de login por IP | `MEMORY_LOGIN_MAX_FAILURES` / `MEMORY_LOGIN_WINDOW` | 10 intentos (aciertos incluidos) / 15 min, fijos | **10 fallos / 15 min** |
| Coste de scrypt | constantes en `auth.py` | `n=2^14, r=8, p=1` | **`n=2^17, r=8, p=1`** (provisional) |
| Logins simultáneos | `MEMORY_LOGIN_CONCURRENCY` (nuevo) | sin tope | provisional, según la memoria medida |
| Caducidad de una clave nueva | campo opcional de la petición de alta | sin caducidad | **sin caducidad salvo que se pida** (P-03); no hay variable de entorno |
| Gracia de rotación | parámetro de la petición | — | **24 h** |
| Aviso de caducidad en el cliente | umbral de `kairos doctor` | — | **14 días** |
| Tasa por credencial | `MEMORY_RATE_LIMIT_*` (nuevo) | sin límite | provisional (P-06) |
| Cuota diaria de escrituras | `MEMORY_WRITE_QUOTA_PER_DAY` (nuevo) | sin cuota | provisional (P-06) |
| Flujos simultáneos | `MEMORY_STREAMS_PER_CREDENTIAL` / `MEMORY_STREAMS_MAX` (nuevo) | sin tope | provisional (**4 / 50**) |
| Directorio de secretos | `MEMORY_SECRETS_DIR` / `--secret-dir` | `./secrets` en el Compose | obligatorio, fuera del repo y de carpetas sincronizadas |

## Arquitectura y componentes

- **Servidor (`server/memory_platform/`)**: `auth.py` (coste de scrypt, rehash, login por fallos, IP real); `store_auth.py` (contraseña, deshabilitar, permisos, sesiones, caducidad, rotación, último uso); `app.py` (rutas nuevas, límites, tope de flujos, cabeceras de proxy); `models.py`; `privacy.py` (patrones, entropía); `admin.py` (`set-password`, `disable-user`, `enable-user`, `set-key-limits`); `config.py`; `schema.sql` (**versión 13**, solo columnas e índices nuevos, definida entera en el hito A); `observability.py` (métricas de límites y de fallos de login).
- **`kairos-mcp` (`mcp/kairos_mcp/`)**: traduce el 429 a un error de herramienta con la forma actual, con el plazo de `Retry-After` en el mensaje (formato estable, a confirmar en `design.md`). Sin credenciales propias, como hoy.
- **Proxy web (`web/nginx.conf`)**: envía `X-Forwarded-For` a `memory-api`. **Portal (`web/src/memory-portal.ts`, `memory-api.ts`)**: sección «Mi cuenta» (contraseña y sesiones), pestaña «Usuarios» ampliada (deshabilitar, rehabilitar, permisos por proyecto, cerrar sesiones) y pestaña «Claves para agentes» ampliada (caducidad opcional, último uso, rotación). La vista de configuración se niega hoy entera a quien no tiene el permiso `admin` (`memory-portal.ts:609`): «Mi cuenta» necesita una entrada propia para cualquier usuario. Pruebas en dos niveles con fixtures aislados: DOM de frontera (`web/tests/`) y Chromium real (`server/memory_platform/Dockerfile.e2e`, `server/memory_platform/tests/e2e_portal.py`).
- **Cliente (`client/lib/`)**: `privacy.mjs` (mismos casos que el servidor), `files.mjs` (permisos del fichero de clave), `doctor` (lee y guarda `expires_at`, caducidad, permisos), cola en disco (`dispatcher.mjs`: respeta `Retry-After` y el 429 no consume intentos).
- **Despliegue**: `scripts/deploy-memory.py` (validación del directorio de secretos), `docker-compose.yml` (sin valor por defecto inseguro; variables nuevas).
- **Contratos**: `memory-platform.openapi.json` crece de forma aditiva (rutas y campos opcionales). `kairos-mcp.json`: mismas herramientas y esquemas.
- **Docs**: guía de identidad (alta y baja), `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md`, `CHANGELOG*.md` con nota para la Iniciativa 7.
- **Casos de redacción compartidos**: un fichero versionado en el repo, leído por las dos suites.

## Flujo (paso a paso)

1. **Alta de persona**: el administrador global, o un administrador de proyecto para sus proyectos, crea el usuario, desde el portal o por API, con sus proyectos y permisos → la persona entra y cambia su contraseña.
2. **Alta de máquina o integración**: el usuario crea una clave con nombre, proyectos, permisos mínimos y, si quiere, caducidad → la guarda en un fichero fuera del proyecto con permisos restringidos → `kairos doctor` lo confirma.
3. **Rotación**: `rotate` → clave nueva en la máquina → la antigua deja de valer al acabar la gracia.
4. **Baja de máquina**: revocar su clave → 401 en `/v1`, en ambos `/mcp` y en un flujo abierto. **Baja de persona**: deshabilitar el usuario → sus sesiones y claves dejan de valer.
5. **Login**: IP real desde el proxy de confianza → ¿IP bloqueada por fallos? → verificación con coste constante → fallo: se registra; acierto: sesión y, si el hash es antiguo, rehash.
6. **Petición con clave**: autenticación → límite de tasa y cuota de esa credencial → la petición sigue o recibe 429 con `Retry-After`.
7. **Captura**: el cliente redacta antes de disco y red → el servidor vuelve a redactar (o rechaza, en documentos y estado de trabajo) al recibir → los logs pasan por las mismas reglas.

## Alcance

- **Dentro (esta iniciativa):**
  - A-01 Credenciales: cambio de contraseña con revocación de sesiones, deshabilitar y rehabilitar usuario, retirar permisos, cerrar sesiones, caducidad, rotación y último uso de claves, scrypt reforzado con rehash (S-03, S-07).
  - A-02 Login: contar solo fallos, IP real desde proxy de confianza, cubos que no bloquean a terceros (S-02).
  - A-03 Límites: tasa y cuota por clave, tope de flujos abiertos (S-08).
  - A-04 Redacción: patrones ampliados, detector de entropía, casos compartidos entre servidor y cliente (S-01).
  - A-05 Identidad: modelo usuario/clave y guía de alta y baja probada.
  - A-06 Superficie: validación del directorio de secretos, permisos del fichero de clave, prueba de guarda de la red de inferencia (S-10, S-11).
  - A-07 Revisión de seguridad sin hallazgos altos.
  - A-08 Portal: toda la gestión de acceso en el portal, restringida al administrador donde corresponde y con equivalente por API (P-02).
  - Extensibilidad comprobable del modelo de permisos (P-01).
- **Fuera:**
  - HTTPS, proxy inverso público, despliegue real y corte al VPS (Iniciativa 5, con autorización expresa).
  - **Ampliación futura, no cerrada por este diseño (P-01):** equipo mayor u organización, roles o grupos, operaciones en bloque sobre usuarios y claves, e inicio de sesión único. Entrarían como cambios aditivos.
  - OAuth, segundo factor, recuperación de contraseña por correo y autorregistro.
  - Permisos nuevos; privacidad entre usuarios dentro de un mismo proyecto.
  - Borrar usuarios o claves (solo deshabilitar y revocar); cifrado en reposo de la base.
  - Reanalizar o reescribir lo ya guardado con los patrones nuevos.
  - S-04 (modelo remoto), S-05 (contenido no fiable) y S-06 (copias cifradas), resueltos en las Iniciativas 2 y 3; de S-09, los nombres fijos de red (Iniciativa 5).
  - El observador del cliente (Iniciativa 6) y la integración con custom-agents (Iniciativa 7): aquí solo se les deja la puerta abierta.
  - Retirar el MCP interno (0.5.0) y el bloqueo de dependencias con hashes (Iniciativa 9).
  - Publicar en registros externos (npm, registros de imágenes).

## Manejo de errores

| Caso | Comportamiento |
|---|---|
| Clave revocada, caducada o de un usuario deshabilitado | 401 en la petición siguiente, en todas las rutas; un flujo abierto se cierra en el sondeo siguiente |
| Contraseña actual incorrecta al cambiarla | Rechazo sin cambio; cuenta como fallo de login de esa IP |
| Contraseña nueva de menos de 12 caracteres | 422 `invalid_password` (regla actual, `auth.py:19-20`) |
| Deshabilitarse a uno mismo o al último administrador activo | 409; nada cambia |
| Login de un usuario deshabilitado o inexistente | Misma respuesta y mismo coste que una contraseña incorrecta |
| IP con 10 fallos en la ventana | 429 `rate_limited` con `Retry-After`; otras IP no se ven afectadas |
| `X-Forwarded-For` desde un par que no es de confianza | Se ignora; cuenta la IP del par |
| Tasa o cuota superada | 429 `rate_limited` o `quota_exceeded` con `Retry-After`; el cliente conserva la captura en su cola y reintenta tras el plazo, sin consumir intentos; `kairos-mcp` devuelve un error de herramienta con la forma actual y el plazo en el mensaje |
| Demasiados flujos | 429 `too_many_streams`; al cerrarse uno se libera el hueco |
| Acción de administración nueva (deshabilitar, rehabilitar, permisos, sesiones ajenas) o listado de usuarios con una sesión que no es de administrador global, o con una clave | 403 desde el servidor; el portal no muestra el control |
| Alta de usuario por un administrador de proyecto | Se admite para sus proyectos y con permisos que él tiene, como hoy (`_delegate`); fuera de ellos se rechaza como hoy |
| 401 en el cliente con una clave cuyo `expires_at` guardado ya venció | `kairos doctor` informa «clave caducada»; sin ese dato, «clave inválida». El servidor responde el mismo 401 a las dos |
| Rotar una clave revocada o caducada | 409; no emite clave |
| Rotar una clave ya rotada y aún en periodo de gracia | 409; no emite clave |
| Secreto nuevo en una captura | Se redacta y el recibo lo indica, como hoy |
| Secreto nuevo en un documento o estado de trabajo | Rechazo con el código actual (`sensitive_source_requires_review` u homólogo); ningún código nuevo en el contrato MCP |
| Directorio de secretos dentro del repo o de una carpeta sincronizada | El despliegue aborta con `secrets_dir_unsafe` antes de cualquier fase |
| Fichero de clave con permisos abiertos (POSIX) | `key_file_too_open`; no se envía nada; el mensaje no contiene la clave |

## Criterios de aceptación

Todos se comprueban con fixtures aislados (PostgreSQL efímero del target `test`, servidores HTTP y proxy simulados, navegador de pruebas, proyecto Compose con nombre distinto de `knowledge-graphs`), nunca contra la base, los contenedores, los volúmenes ni las redes `knowledge-graphs-*`.

**A-01 · Credenciales (S-03, S-07)**

- [ ] [GWT] CA-01 — Dado un usuario con dos sesiones abiertas, Cuando cambia su contraseña desde una de ellas con la actual correcta y una nueva válida, Entonces la contraseña antigua ya no inicia sesión, la nueva sí, la otra sesión recibe 401 en su petición siguiente y queda un evento de auditoría `password.changed`. Con la actual incorrecta no cambia nada y cuenta como fallo de login.
- [ ] CA-02 — `admin set-password --username --password-file` cambia la contraseña, revoca todas las sesiones del usuario y no imprime la contraseña ni su hash (test).
- [ ] [GWT] CA-03 — Dado un usuario con una sesión y dos claves, Cuando un administrador lo deshabilita, Entonces la sesión y las dos claves reciben 401 en su petición siguiente y su login responde igual que una contraseña incorrecta. Al rehabilitarlo, las claves no revocadas vuelven a valer y las sesiones no. Deshabilitarse a uno mismo o al último administrador activo responde 409.
- [ ] CA-04 — Un administrador sustituye los permisos por proyecto de un usuario; la petición siguiente de su sesión y de sus claves sobre un proyecto retirado responde como un proyecto sin acceso (404 o 403, según el contrato actual); queda auditado (test).
- [ ] CA-05 — Un usuario lista sus sesiones y las cierra todas menos la actual; un administrador cierra todas las de otro usuario; cada sesión cerrada recibe 401 en su petición siguiente (test).
- [ ] CA-06 — Una clave creada **sin** indicar caducidad no caduca (P-03); una creada con caducidad deja de valer al vencer (401); la lista de claves y `/v1/auth/me` muestran `expires_at`, y la lista, `last_used_at`; las claves anteriores a la migración conservan «sin caducidad» (test).
- [ ] [GWT] CA-07 — Dada una clave activa, Cuando se rota con una gracia de 24 h, Entonces se emite una clave nueva, mostrada una sola vez, con el mismo nombre, proyectos y permisos; la antigua vale hasta el fin de la gracia y después recibe 401; con gracia 0 deja de valer en la petición siguiente; rotar una clave revocada responde 409; rotar una clave ya rotada y aún en periodo de gracia responde 409 y no emite clave.
- [ ] CA-08 — `kairos doctor` lee `expires_at` de `/v1/auth/me` cuando la clave se valida con éxito y lo guarda en su estado local, sin la clave. Con ese dato: avisa cuando una clave con caducidad vence en menos de 14 días; no avisa con una clave sin caducidad; y ante un 401 informa «clave caducada» si el `expires_at` guardado ya venció, y «clave inválida» en cualquier otro caso (sin dato guardado, sin caducidad o con caducidad futura). El 401 del servidor no cambia: responde lo mismo a una clave caducada y a una inválida (`auth.py:60`). Ni los mensajes ni el estado local contienen la clave (tests del cliente con reloj controlado y servidor simulado).
- [ ] CA-09 — El plan mide tiempo y memoria de una verificación scrypt con los parámetros candidatos dentro de los contenedores que derivan scrypt, cada uno con su `mem_limit`: `memory-api`, `memory-bootstrap` (256 MB) y `memory-admin`, y lo deja en el ledger **antes** de fijarlos. Con los definitivos: los hashes nuevos los usan; un hash antiguo verifica y se sustituye en el primer login correcto; el hash ficticio cuesta lo mismo; N logins simultáneos (N = tope configurado + 5) no superan el límite de memoria del contenedor.
- [ ] CA-10 — La migración de la versión de esquema 13 solo añade columnas e índices; `test_migrations_additive.py` pasa; tras actualizar desde 0.4.1 con usuarios, sesiones y claves sembrados, todos siguen valiendo.
- [ ] [GWT] CA-11 — Dada una clave que responde 200 en `/v1`, en el `/mcp` interno, en el `/mcp` de `kairos-mcp` (a través del proxy web) y que mantiene abierto un flujo de actividad, Cuando se revoca, Entonces la petición siguiente a cada ruta recibe 401 y el flujo se cierra en un intervalo de sondeo más un margen. Lo mismo al caducar la clave y al deshabilitar a su dueño; y una sesión del portal cerrada o de un usuario deshabilitado recibe 401 (criterio de cierre 2 del plan director).

**A-02 · Login (S-02)**

- [ ] CA-12 — Treinta logins correctos seguidos desde la misma IP en la ventana no producen 429 (test).
- [ ] [GWT] CA-13 — Dado el cliente A, que falla diez veces la contraseña del usuario U a través del proxy web, Cuando el cliente B, desde otra IP, inicia sesión como U con la contraseña correcta, Entonces recibe 200; el undécimo intento de A recibe 429 con `Retry-After` (criterio de cierre 3 del plan director).
- [ ] CA-14 — A través del proxy web, la API registra la IP del cliente y no la del proxy; un `X-Forwarded-For` enviado por un par que no es de confianza se ignora (no sirve para esquivar el bloqueo ni para bloquear a otra IP); con dos proxies de confianza encadenados se toma la dirección no fiable más a la derecha; `MEMORY_TRUSTED_PROXIES` está documentada (tests con proxy simulado).
- [ ] CA-15 — Sin regresión: `/metrics` en modo `internal` sigue respondiendo 404 a través del proxy; `prune-tables` sigue purgando `login_attempts`; los fallos por usuario se publican como métrica o evento sin bloquear (P-05); ningún registro de login guarda la contraseña.

**A-03 · Límites (S-08) — visible para clientes**

- [ ] CA-16 — El plan mide el perfil real de peticiones del cliente (una sesión con hooks, una reindexación, la sonda y una publicación como la de custom-agents) y lo deja en el ledger **antes** de fijar los valores por defecto, que quedan con un margen declarado sobre el pico medido.
- [ ] [GWT] CA-17 — Dadas las claves K1 y K2, Cuando K1 supera su tasa, Entonces K1 recibe 429 `rate_limited` con `Retry-After` y K2 sigue recibiendo 200 en el mismo intervalo; `/health/*` y el login no dependen del límite de ninguna clave.
- [ ] CA-18 — Una clave que agota su cuota diaria de escrituras recibe 429 `quota_exceeded` en las escrituras y sigue pudiendo leer; la cuota se restablece al cambiar el periodo; una anulación por clave prevalece sobre el valor global; la anulación por clave la fija el operador con el comando `admin set-key-limits`; no tiene control en el portal ni ruta en `/v1`. El contador vive en la base, con escritura agrupada, y sobrevive a un reinicio de `memory-api`: tras reiniciar, una clave que había agotado su cuota sigue recibiendo 429 y las demás conservan lo consumido salvo, como mucho, el último lote sin escribir, de tamaño acotado y declarado (default provisional, a confirmar en `design.md`). Tests con reloj controlado y con reinicio del proceso.
- [ ] CA-19 — Abrir más flujos de actividad que el tope por credencial responde 429 `too_many_streams`; el tope global también se aplica; un flujo cerrado, también por desconexión del cliente, libera su hueco (test).
- [ ] CA-20 — Ante un 429, el cliente conserva la captura en su cola en disco y reintenta respetando `Retry-After`, sin pérdida: el 429 no consume intentos, así que una captura limitada más de cinco veces seguidas no pasa a `failed` con `capture_retry_limit` y se entrega cuando el límite se levanta. `kairos-mcp` devuelve un error de herramienta con la forma actual (`isError`), cuyo mensaje lleva el código y el plazo en un formato estable que el cliente interpreta, sin tocar los esquemas de `kairos-mcp.json`. Los dos puntos son default provisional, a confirmar en `design.md`. La validación `/v1/auth/me` de `kairos-mcp` no consume del límite; `test_contract_additive.py` pasa para ambos contratos.
- [ ] CA-21 — `/metrics` publica los rechazos por motivo, sin etiqueta por clave; el evento de log lleva el identificador de la clave, nunca el token (test).

**A-04 · Redacción (S-01) — visible para clientes**

- [ ] CA-22 — Existe un fichero de casos compartido con al menos 40 casos (las siete cadenas de S-01, los patrones actuales y al menos 15 casos que **no** deben redactarse: hash sha256, UUID, SHA de commit, rutas, identificadores), y lo ejecutan la suite del servidor y la del cliente; un caso nuevo sin implementar deja en rojo las dos.
- [ ] [GWT] CA-23 — Dada cada una de las siete cadenas de S-01 dentro de una captura, Cuando la procesa el cliente y cuando la recibe el servidor, Entonces el secreto no aparece en la salida de ninguno de los dos, ni en el fichero de la cola del cliente, ni en la base, ni en una línea de log.
- [ ] CA-24 — El detector de entropía es conservador (P-07): solo redacta una cadena de alta entropía junto a un nombre o contexto de secreto. El plan mide su tasa de redacción sobre un corpus sin secretos (la documentación del repo y el conjunto de evaluación de búsqueda) **antes** de fijar el umbral, y el umbral definitivo no redacta ninguno de los casos «no redactar» de CA-22.
- [ ] CA-25 — Una tabla ruta → comportamiento cubre todas las rutas de `/v1` que guardan texto (eventos, notas, documentos, estado de trabajo, trabajo de equipo, respuestas de corpus) y un test por ruta comprueba que un secreto nuevo se redacta o se rechaza según la tabla; una clave `mp_…` nunca queda guardada.
- [ ] CA-26 — Los rechazos nuevos usan los códigos de error actuales; `kairos-mcp.json` no cambia; el cambio de comportamiento se declara en `CHANGELOG*.md` con una nota para la Iniciativa 7.
- [ ] CA-27 — Las reglas nuevas no abren una denegación de servicio: una entrada adversaria del tamaño máximo admitido termina dentro de una cota medida en el plan, en servidor y cliente (test).

**A-05 · Identidad**

- [ ] CA-28 — Hay una guía con el modelo (un usuario por persona, una clave por máquina y otra por integración, permisos mínimos por proyecto) y pasos ejecutables, por el portal y por API o comando, para: alta de persona, alta de máquina, alta de integración, rotación, baja de máquina, baja de persona, portátil perdido y recuperación del administrador.
- [ ] [GWT] CA-29 — Dado un servidor de pruebas recién inicializado, Cuando un test sigue la guía (usuario, clave de máquina sobre un proyecto, clave de integración con `read`, `publish` y `validate`), Entonces cada clave hace lo suyo, ninguna alcanza otro proyecto (404) ni ejerce un permiso que no tiene (403), y tras las bajas todas reciben 401.
- [ ] CA-30 — La clave de integración de CA-29 supera la comprobación `health` que usará custom-agents (`projects` y `capture_policy`, `custom-agents-integration.md:50`); las claves emitidas antes de esta iniciativa siguen valiendo sin cambios en el cliente.
- [ ] CA-38 — Extensibilidad (P-01): (a) un test recorre el paquete del servidor y comprueba que solo el resolvedor de permisos (`_active`, `_global_admin`, `_require` y las funciones que las alimentan) lee `project_grants`, los permisos de una clave y `actors.is_admin`, salvo una lista cerrada de excepciones escrita en el propio test, cada una con su justificación: bloqueos `FOR SHARE` (`corpus_answers.py:140`, `extended_store.py:62`), listados (`store_auth.py:101,192`) y la sonda (`probe.py`). Una lectura nueva fuera del resolvedor y de la lista deja el test en rojo. La construcción del actor (`auth.py:44-50`) y la comprobación de `/metrics` en modo `admin` (`app.py:202`) pasan al resolvedor. La frontera exacta del resolvedor y la lista definitiva de excepciones: a confirmar en `design.md`; (b) el portal no decide permisos: oculta controles, y el servidor rechaza la acción; (c) `docs/architecture.md` tiene una nota que explica cómo se añadirían roles o grupos, operaciones en bloque e inicio de sesión único solo con tablas o columnas nuevas, sin cambiar el significado de las actuales, y la revisión de seguridad (CA-34) la valida.

**A-06 · Superficie (S-10, S-11)**

- [ ] CA-31 — `deploy-memory.py` aborta con `secrets_dir_unsafe`, antes de cualquier fase, si el directorio de secretos está dentro del repositorio o de una carpeta sincronizada conocida; el Compose no cae en `./secrets` sin avisar; un test comprueba que nada de lo que el despliegue escribe en `.private/` contiene un secreto.
- [ ] CA-32 — En POSIX, un fichero de clave legible por grupo u otros hace fallar al cliente con `key_file_too_open` sin enviar nada; en Windows, `kairos doctor` avisa según P-09; ningún mensaje contiene la clave (tests del cliente).
- [ ] CA-33 — Un test sobre `docker compose config` comprueba que la red `inference` es interna, que solo la usan el proxy de Ollama, `memory-api` y `memory-worker`, que solo el proxy tiene salida y que todo puerto publicado está en `127.0.0.1`.

**A-07 · Revisión y cierre**

- [ ] CA-34 — Una revisión de seguridad, hecha por un revisor distinto del implementador sobre el diff completo de la iniciativa y la superficie de acceso (autenticación, sesiones, claves, límites, redacción, secretos), termina con **cero hallazgos de severidad alta abiertos**; cada hallazgo medio tiene decisión registrada; queda en `review.md` (criterio de cierre 1 del plan director).
- [ ] CA-35 — Cada fix de revisión se revisa como código nuevo: su diff pasa por las mismas lentes que la fase y queda anotado en el ledger.
- [ ] CA-36 — Cada hallazgo en alcance (S-01, S-02, S-03, S-07, S-08, S-10, S-11) tiene al menos un test que falla si se retira su control.
- [ ] CA-37 — Al cerrar: migraciones solo aditivas; diff aditivo de `memory-platform.openapi.json` y `kairos-mcp.json` frente a su base, con las mismas herramientas MCP; ninguna prueba contra recursos `knowledge-graphs-*`; nada publicado en registros externos; suites de servidor, MCP, cliente y portal con 0 fallos y 0 omitidos; `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md` y `CHANGELOG*.md` actualizados.

**A-08 · Portal (P-02)**

Los casos de CA-39 a CA-42 se prueban en **dos niveles**, siempre con fixtures aislados y nunca contra el despliegue:

| Nivel | Qué es | Dónde corre | Equivalente local declarado |
|---|---|---|---|
| DOM de frontera | `web/tests/` con API de fixture y un DOM propio (no es un navegador) | CI | La misma suite en Docker local con `web/Dockerfile.test`; si la CI no se ejecuta, esa ejecución local cierra el criterio y se anota en el ledger |
| Chromium real | `server/memory_platform/Dockerfile.e2e` + `server/memory_platform/tests/e2e_portal.py`, con API y base de fixture | Solo Docker local, fuera de la CI: depende de las etiquetas locales `kairos-web:native-test` y `kairos-test:native` | Es ya la ejecución local; su resultado se anota en el ledger. La CI solo comprueba que su fixture siembra (`test_e2e_fixture.py`) |

Un caso de CA-39 a CA-42 se da por verificado cuando pasa en los dos niveles.

- [ ] [GWT] CA-39 — Dado un administrador global en la pestaña «Usuarios», Cuando da de alta un usuario, cambia sus permisos por proyecto, lo deshabilita, lo rehabilita y cierra sus sesiones, Entonces cada acción se refleja en la lista sin recargar, pide confirmación antes de deshabilitar o cerrar sesiones, y el efecto en el servidor es el de CA-03, CA-04 y CA-05.
- [ ] [GWT] CA-40 — Dado un usuario cualquiera en «Mi cuenta», Cuando cambia su contraseña y cierra sus otras sesiones, Entonces el resultado es el de CA-01 y CA-05, los errores (contraseña actual incorrecta, nueva demasiado corta) se muestran junto al campo y los campos de contraseña quedan vacíos tras enviar.
- [ ] [GWT] CA-41 — Dado un usuario con permiso para emitir claves en «Claves para agentes», Cuando crea una clave sin caducidad, otra con caducidad, y rota una, Entonces la lista muestra «sin caducidad» o la fecha, y el último uso; la clave nueva se muestra una sola vez; y el efecto es el de CA-06 y CA-07.
- [ ] CA-42 — Se mantiene la delegación del alta (decisión 6): un administrador de proyecto ve el control de alta y da de alta personas solo para sus proyectos y con permisos que él tiene, sin cambio de comportamiento en `POST /v1/users` (`store_auth.py:160-175`; `test_api_limits.py:147-149` sigue pasando sin tocarlo). Las acciones de administración nuevas (deshabilitar y rehabilitar, sustituir permisos, listar o cerrar sesiones ajenas) y el listado de usuarios son exclusivos del administrador global con sesión: quien no lo es no ve esos controles y, si llama a sus rutas a mano con su sesión o con una clave, recibe 403. Un usuario sin el permiso `admin` en ningún proyecto no ve ningún control de administración. Toda acción que cambia estado con sesión exige origen permitido y token CSRF (tests de servidor y de portal en los dos niveles).
- [ ] CA-43 — Paridad: una tabla en la guía de identidad lista cada acción del portal con su operación de `/v1` y, donde exista, su comando `admin`; un test comprueba que el portal solo llama a operaciones presentes en `memory-platform.openapi.json` y que ninguna acción de la tabla carece de operación.

## Pruebas

- Suite del servidor en PostgreSQL aislado (target `test` del `Dockerfile`) para A-01, A-02, A-03 y A-04, con reloj controlado para caducidad, gracia, ventanas y cuotas.
- Proxy HTTP simulado delante de la API para la IP real y los cubos de login (CA-13, CA-14), y la configuración real de `web/nginx.conf` en un proyecto Compose aislado para CA-11 y CA-13.
- Suite de `kairos-mcp` con servidor `/v1` simulado (CA-11, CA-20) y suite del cliente (`npm test`) para CA-08, CA-20, CA-23 y CA-32; CA-08 y CA-20 con reloj controlado.
- Portal (A-08) en dos niveles, nunca contra el portal desplegado: DOM de frontera (`web/tests/`, `web/Dockerfile.test`) con API de fixture, en la CI, para CA-39 a CA-43; y Chromium real (`server/memory_platform/Dockerfile.e2e`, `server/memory_platform/tests/e2e_portal.py`) en Docker local, fuera de la CI, para CA-39 a CA-42. Equivalente local de cada nivel declarado en A-08; el resultado del nivel local se anota en el ledger.
- Reinicio de `memory-api` sobre el PostgreSQL aislado para la persistencia de la cuota (CA-18).
- Test estático del resolvedor de permisos con su lista de excepciones (CA-38 a); es el primer test del orden sugerido por la evaluación.
- Fichero de casos de redacción ejecutado por las dos suites (CA-22 a CA-24).
- `scripts/tests/` y `test_deploy*.py` sobre `docker compose config` y dobles de `subprocess` para CA-31 y CA-33.
- Mediciones previas registradas en el ledger: scrypt (CA-09), perfil de peticiones (CA-16), entropía (CA-24), coste de las reglas (CA-27).
- Los criterios [GWT] se traducen 1:1 a casos del plan de pruebas con el mismo ID.

## Preguntas abiertas

Ninguna necesita ya al usuario. **Decisión (2026-11-19, usuario, a través del orquestador `/dev-cycle`):** P-01, P-02, P-03 y P-07 respondidas; el literal figura en cada fila. P-04, P-05, P-06, P-08, P-09 y P-10 son técnicas y se adoptan como se recomiendan.

| ID | Pregunta | Decisión | Origen |
|---|---|---|---|
| P-01 | ¿Cuántas personas y máquinas usarán Kairos? (decisión abierta 3 del plan director) | **El usuario y de 2 a 5 personas más**, con varias máquinas e integraciones. El diseño queda ampliable (roles o grupos, operaciones en bloque, inicio de sesión único) con cambios aditivos; esas ampliaciones quedan fuera de esta iniciativa (CA-38) | Usuario, 2026-11-19, literal: «de momento yo y 2-5 más, ¿despues se podrá ampliar?». El orquestador respondió que sí |
| P-02 | ¿Cuánta gestión de acceso va al portal? | **Toda**: alta, deshabilitar, permisos por proyecto, cambio de contraseña, cierre de sesiones, caducidad y rotación de claves. Administración restringida al administrador existente; cada acción con equivalente por API o comando (CA-39 a CA-43). Distinta de la recomendación inicial («lo mínimo») | Usuario, 2026-11-19, literal: «Todo en el portal» |
| P-03 | ¿Las claves nuevas caducan por defecto? | **No**: solo si se indica al crearlas. `kairos doctor` avisa de las que sí tienen caducidad (CA-06, CA-08). Distinta de la recomendación inicial (90 días) | Usuario, 2026-11-19, literal: «Solo si se pide» |
| P-04 | ¿Qué parámetros de scrypt? | `n=2^17, r=8, p=1` si la medición cabe dentro de los contenedores que derivan scrypt, cada uno con su `mem_limit`: `memory-api`, `memory-bootstrap` (256 MB) y `memory-admin`; si no, el equivalente de menor memoria (`n=2^16, p=2`) | Técnica; se fija tras medir (CA-09) |
| P-05 | ¿Bloqueo también por nombre de usuario? | No: solo por IP; los fallos por usuario se miden y se alertan | Técnica |
| P-06 | ¿Límites activos por defecto y con qué valores? | Activos, holgados, fijados tras medir (CA-16); `0` los desactiva; anulación por clave | Técnica; **se declara** a la Iniciativa 7 |
| P-07 | ¿Cómo de estricto es el detector de entropía? | **Conservador**: solo junto a un nombre o contexto de secreto (CA-24) | Usuario, 2026-11-19, literal: «Conservador» |
| P-08 | ¿Se mueve `.private/` fuera del repo? | No: se comprueba que no contiene secretos | Técnica |
| P-09 | ¿Qué se hace con los permisos del fichero de clave en Windows? | Aviso de `kairos doctor` en el mejor esfuerzo; fallo estricto solo en POSIX | Técnica |
| P-10 | ¿Qué versión sale? | 0.4.2 | Técnica |

### Entrada para `design.md`

Puntos que la spec fija como default provisional y que `architect` confirma o sustituye. Ninguno cambia el alcance ni el criterio observable.

| ID | Punto | Default provisional | Criterio |
|---|---|---|---|
| D-01 | Cómo trata el cliente un 429 y cómo llega `Retry-After` a través de `kairos-mcp` | El 429 no consume intentos de la cola; el plazo viaja en el mensaje del error de herramienta con formato estable; sin tocar los esquemas del contrato MCP | CA-20 |
| D-02 | Frontera exacta del resolvedor de permisos y lista definitiva de excepciones del test | Resolvedor: `_active`, `_global_admin`, `_require` y lo que las alimenta, más `auth.py:44-50` y `app.py:202`. Excepciones: bloqueos `FOR SHARE`, listados, sonda | CA-38 (a) |
| D-03 | Dónde y cómo se guarda la cuota diaria | Contador en la base, con escritura agrupada; sobrevive a un reinicio; pérdida máxima de un lote acotado. Quedan por decidir la estructura (dentro de la versión 13), el tamaño del lote y el límite del periodo diario | CA-18 |
| D-04 | Dónde guarda `kairos doctor` el `expires_at` y cuándo lo lee | Estado local del cliente, sin la clave. Hoy `client/lib/` no llama a `/v1/auth/me`: la lectura es nueva. Falta decidir cómo se asocia el dato a la clave (por ejemplo su identificador) para que un cambio de fichero de clave no herede la caducidad de otra | CA-08 |
| D-05 | Cómo presenta el portal el alta delegada | Sin default. Hoy `GET /v1/users` exige administrador global (`test_api_limits.py:140-141`): un administrador de proyecto puede dar de alta pero no listar. El diseño decide qué ve tras el alta, sin ampliar el listado | CA-39, CA-42 |
| D-06 | Entrada de «Mi cuenta» para cualquier usuario | Sin default. La vista de configuración se niega hoy a quien no tiene `admin` (`memory-portal.ts:609`) | CA-40 |
| D-07 | Columnas e índices de la versión 13 | Todas en el hito A (restricción de entrega); el diseño da la lista cerrada | CA-10 |

## Decisiones confirmadas (revisión del usuario · 2026-11-19)

1. Kairos lo usarán el usuario y de 2 a 5 personas más; el diseño debe poder ampliarse después. **Confirmado** («de momento yo y 2-5 más, ¿despues se podrá ampliar?»).
2. Toda la gestión de acceso está en el portal. **Confirmado** («Todo en el portal»).
3. Las claves no caducan salvo que se pida al crearlas. **Confirmado** («Solo si se pide»).
4. El detector de entropía es conservador. **Confirmado** («Conservador»).

5. Puerta go/no-go de la evaluación: **go** («go, pero seguimos mañana»). La spec pasa a `aprobada`.
6. CA-42: se **mantiene la delegación** («Mantener la delegación»): un administrador de proyecto sigue pudiendo dar de alta personas para su proyecto; el resto de la administración es solo del administrador general.
7. Paso de diseño con `architect` antes del plan: **sí** («Sí, con diseño»).

8. Opción de diseño (2026-11-20): **O2 — Costuras de acceso** («2: un sitio para cada cosa (Recommended)»). [design.md](design.md) queda `aprobado` y cierra D-01 a D-07.
9. Cuatro aclaraciones de la spec propuestas por el diseño (sección 7 de `design.md`), aprobadas el 2026-11-20 («Sí, así (Recommended)»). Ninguna cambia el alcance ni el número de criterios (43):
   1. Rotar una clave ya rotada y aún en periodo de gracia responde 409 y no emite clave (CA-07, «Manejo de errores»).
   2. La anulación de límites por clave la fija el operador con `admin set-key-limits`; no tiene control en el portal ni ruta en `/v1`. Es una excepción declarada a «toda acción existe en `/v1`» y a «todo en el portal» (CA-18, filas «Límite de tasa» y «Cuota», `admin.py`).
   3. scrypt se mide en los tres contenedores que lo derivan, cada uno con su `mem_limit`: `memory-api`, `memory-bootstrap` (256 MB) y `memory-admin` (CA-09, fila «scrypt (S-07)», P-04).
   4. Hecho 2 corregido: `kairos-mcp` solo valida contra `/v1/auth/me` en las peticiones que no son una `tools/call` y en las herramientas `local`. Ningún criterio cambia.

**Revisión del 2026-11-20 (aclaraciones dentro del alcance aprobado; la spec sigue `aprobada`, con los mismos 43 criterios).** Aplicados los 8 puntos de «Ambigüedades y problemas de la spec» de `evaluation.md`:

| # | Punto | Resolución | Dónde |
|---|---|---|---|
| 1 | CA-42 frente a la delegación | Se mantiene la delegación del alta (decisión 6); solo las acciones nuevas son del administrador global | CA-42, CA-39, fila «Portal (P-02)», flujo 1, manejo de errores |
| 2 | Pruebas de navegador | Dos niveles: DOM de frontera (CI) y Chromium real (Docker local), con equivalente local declarado | A-08, «Pruebas», supuestos |
| 3 | CA-20, «sin pérdida» | El 429 no consume intentos; plazo en el mensaje del error de herramienta. A confirmar en `design.md` | CA-20, D-01 |
| 4 | CA-08, caducada frente a inválida | `doctor` usa el `expires_at` guardado; el 401 no cambia | CA-08, D-04 |
| 5 | CA-38 (a) | Lista cerrada y justificada de excepciones; `auth.py:44-50` y `app.py:202` pasan al resolvedor. Frontera a confirmar en `design.md` | CA-38, D-02 |
| 6 | CA-18, dónde vive la cuota | En la base, con escritura agrupada; sobrevive a un reinicio. A confirmar en `design.md` | CA-18, D-03 |
| 7 | Esquema 13 en varios PR | El hito A define todas las columnas de la versión 13 | Restricción de entrega, D-07 |
| 8 | Frontmatter | `design: design.md` (lo crea `architect`) | Frontmatter y cabecera |

Otras correcciones evidentes hechas en esta revisión: la cabecera decía «Evaluación: pendiente» con la evaluación ya hecha; la ruta del arnés de navegador es `server/memory_platform/tests/e2e_portal.py`, no `tests/e2e_portal.py`; la hipótesis sobre la cola del cliente citaba `outbox.mjs` y los reintentos están en `dispatcher.mjs`.

## Referencias

- `server/memory_platform/auth.py:18-34` (hash y verificación), `:56-72` (autenticación), `:74-93` (login), `:95-98` (logout).
- `server/memory_platform/store_auth.py:12-29` (`_load_active`), `:63-84` (`_global_admin`, `_require`), `:160-235` (delegación, usuarios y claves).
- `server/memory_platform/app.py:23` (cabeceras de proxy), `:79` (duración del flujo), `:206-221`, `:246`, `:262`, `:369-379`, `:470-484`, `:504`.
- `server/memory_platform/schema.sql:3-9` (actores, permisos, claves, sesiones, intentos), `:257` (versión 12); `models.py:27-29,83-92`; `admin.py:252,266,339-342`.
- `server/memory_platform/privacy.py:17-27`, `:133-173`, `:176-181`; `store_ingest.py:131-141`; `store_documents.py:80`; `agent_store.py:67`.
- `client/lib/privacy.mjs:4,51-59`; `client/lib/capture.mjs:74`; `client/lib/files.mjs:64-78`; `client/lib/mcp.mjs:47`; `client/lib/dispatcher.mjs:134-144` (reintentos y `capture_retry_limit`).
- `mcp/kairos_mcp/app.py:51-57`; `mcp/kairos_mcp/auth.py:37-45,48-98`; `mcp/kairos_mcp/translate.py:191-200`; `mcp/kairos_mcp/tools.py:84` (error de `/v1` como resultado `isError`).
- `web/nginx.conf:50-75`; `web/src/memory-portal.ts:142-146,609,612-666`; `web/tests/memory-portal.test.mjs`, `web/Dockerfile.test` (DOM de frontera); `server/memory_platform/Dockerfile.e2e`, `server/memory_platform/tests/e2e_portal.py`, `test_e2e_fixture.py` (Chromium real).
- `server/memory_platform/tests/test_api_limits.py:140-149` (delegación del alta y listado solo para el administrador global); `corpus_answers.py:140`, `extended_store.py:62`, `probe.py:678-793` (lecturas de permisos fuera del resolvedor).
- `docker-compose.yml:48-70,159-160,325-339`; `scripts/deploy-memory.py:54,579-584,642,1124-1129`; `docs/configuration.md:25,34,61,87,172`.
- `docs/roadmap/2026-11-15-reliable-operations/retro.md:52-55` (aprendizajes 1, 3 y 4); `spec.md` de esa iniciativa, CA-18 (revocación en la petición siguiente).
- `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`.
- `evaluation.md` de esta iniciativa, «Ambigüedades y problemas de la spec» (líneas 97-106) y R-13.

## Supuestos

- **Hecho técnico:** las siete cadenas de S-01 no se redactan hoy en ningún lado — comprobado ejecutando `privacy.py` y `client/lib/privacy.mjs` con cadenas sintéticas el 2026-11-19.
- **Hecho técnico:** `actors.disabled` y `api_keys.expires_at` existen y la autenticación los respeta — `schema.sql:3,6`, `auth.py:60,69`, `store_auth.py:15,20`.
- **Hecho técnico:** el portal ya crea y lista usuarios y claves y revoca claves — `web/src/memory-portal.ts:612-666`.
- **Hecho técnico:** la API es un solo proceso — `app.py:504`.
- **Hecho técnico:** el administrador global es `actors.is_admin` con sesión, no con clave — `store_auth.py:63-66`. Es el único rol de administración de instancia que existe; esta iniciativa no crea otro.
- **Hecho técnico (corrige una hipótesis del 2026-11-19):** `web/tests/` y `web/Dockerfile.test` admiten una API de fixture, pero no son un navegador: `web/tests/memory-portal.test.mjs` define sus propias clases de DOM. El navegador real es Chromium en `server/memory_platform/Dockerfile.e2e` con `server/memory_platform/tests/e2e_portal.py`; depende de las etiquetas locales `kairos-web:native-test` y `kairos-test:native` (`Dockerfile.e2e:1-2`) y no corre en la CI. Por eso A-08 se prueba en dos niveles.
- **Hecho técnico:** un administrador de proyecto da de alta usuarios para su proyecto y no puede listarlos — `store_auth.py:160-175,189`, `test_api_limits.py:140-141,147-149`.
- **Hecho técnico:** el servidor responde el mismo 401 a una clave caducada y a una inválida — `auth.py:60`. `client/lib/` no llama hoy a `/v1/auth/me`.
- **Hipótesis:** `hashlib.scrypt` con `n=2^17` necesita subir `maxmem` y cabe en `memory-api` con logins simultáneos acotados; lo confirma la medición de CA-09.
- **Hecho técnico (corrige una hipótesis del 2026-11-19):** la cola del cliente reintenta con espera exponencial hasta 60 s, pero pasa la captura a `failed` con `capture_retry_limit` al quinto intento y no conoce el 429 ni `Retry-After` — `client/lib/dispatcher.mjs:134-144`. No basta enseñarle `Retry-After`: el 429 no debe consumir intentos (CA-20).
- **Default provisional (a confirmar en `design.md`):** D-01 a D-04 de «Entrada para `design.md`» — tratamiento del 429 y de `Retry-After` (CA-20), frontera del resolvedor (CA-38 a), cuota diaria en la base (CA-18) y estado local de `doctor` (CA-08).
- **Restricción de entrega:** el hito A define de una vez todas las columnas e índices de la versión 13 del esquema; los hitos B y C no la reabren ni crean una versión 14. `test_migrations_additive.py` pasa en el cierre de cada hito.
- **Hipótesis:** `.private/` no contiene secretos (solo la referencia al directorio de secretos, el estado y el bloqueo, `deploy-memory.py:54`); lo confirma el test de CA-31.
- **Hipótesis:** el `/mcp` interno autentica con las mismas funciones que `/v1` y hereda la revocación; lo confirma el test de CA-11.
- **Hipótesis:** el VPS ejecutará una sola réplica de `memory-api`; si la Iniciativa 5 decide varias, los límites en memoria (tasa y flujos) pasan a la base; la cuota diaria ya vive en ella. La confirmaría el diseño de la Iniciativa 5.
- **Restricción de negocio (confirmada por el usuario el 2026-11-19, P-01):** Kairos lo usan el usuario y de 2 a 5 personas más, desde varias máquinas; debe poder ampliarse después con cambios aditivos.
- **Restricción de negocio (supuesto hasta confirmar):** no hace falta correo, segundo factor ni inicio de sesión único en esta iniciativa — la confirmaría el usuario.
- **Restricción de negocio (supuesto hasta confirmar):** la integración con custom-agents necesita una clave por máquina y por integración con `read`, `publish` y `validate` sobre un proyecto — `custom-agents-integration.md:78`; la confirmaría la Iniciativa 7.
- **Restricciones del proyecto (CLAUDE.md y plan director §4):** nunca pruebas destructivas contra la base desplegada, solo fixtures aislados de PostgreSQL, HTTP y navegador; migraciones aditivas; se conserva el contrato de las herramientas MCP (`docs/contracts/kairos-mcp.json`); no se publica nada en registros externos sin el usuario; el despliegue real y el corte al VPS son de la Iniciativa 5 y requieren autorización expresa.
- Docker en primer plano y de uno en uno (32 GB de RAM), como en la Iniciativa 3.
