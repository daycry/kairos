# Integración de custom-agents con Kairos

Última actualización: 2026-11-05.

## Una única conexión

El equipo consumidor debe integrar un servidor MCP llamado `kairos`. El instalador de [clientes](install.md) prepara el puente stdio Node y su conexión HTTP autenticada. El cliente no necesita conocer los componentes internos, acceder a carpetas remotas ni ejecutar indexaciones.

Configura dirección base, proyecto y fichero de clave. Crea claves separadas por proyecto o integración y limita sus permisos. La política de captura es una condición adicional: disponer de `write` no permite saltarse una captura desactivada.

El contrato real lo define [mcp.py](../memory_platform/mcp.py) con los tipos de [models.py](../memory_platform/models.py). `tools/list` debe ser la fuente del esquema que utilice el consumidor: evita mantener una copia divergente de sus argumentos.

## Herramientas disponibles

| Herramienta | Función | Validación del resultado |
|---|---|---|
| `projects` | Descubrir sólo proyectos autorizados, políticas y contadores | Comprobar que el proyecto esperado está permitido |
| `search` | Recuperar por proyecto, texto y capas | Revisar parcialidad, versión y procedencia |
| `details` | Ampliar referencias después de revalidar acceso | Conservar fuente y avisos de truncado/sustitución |
| `context` | Preparar contexto acotado con fuentes | No tratarlo como conocimiento exhaustivo |
| `timeline` | Recuperar cronología por ventana o referencia | Respetar límites y permisos |
| `remember` | Registrar un evento autorizado | Guardar el recibo y consultar su estado |
| `capture_policy` | Comprobar permisos y consentimiento vigentes | `capture_allowed=false` impide admitir o enviar nueva captura |
| `event_status` | Consultar recibo y trabajos del evento | `complete` y trabajos, no sólo aceptación |
| `publish_document` | Publicar una fuente aprobada | Comprobar identidad, hash y estado documental |
| `document_status` | Consultar versión, hash, retirada y trabajos | Comparar con el envío local esperado |
| `document_manifest` | Paginar inventario documental | Consumir todas las páginas necesarias |
| `revoke_document` | Registrar retirada con versión siguiente | Consultar estado y exclusión de recuperación vigente |

La distribución implementa 34 herramientas MCP de servidor. El esquema completo exportado está en [kairos-mcp.json](contracts/kairos-mcp.json); comprueba también `tools/list` en el servidor desplegado. Un contenedor anterior puede ofrecer todavía una lista más corta. Las tres herramientas locales opcionales de código pertenecen al proxy del cliente y no leen el sistema de archivos del servidor.

El ciclo automático opcional está descrito en [instalación](install.md). custom-agents puede utilizar ese runtime sin implementar otro cliente de ingestión. Antes de persistir un evento automático llama `capture_policy(project_id)` y respeta el techo de captura local y remoto. Después de una entrega incierta, `event_status(event_id, project_id)` requiere lectura y escritura actuales y puede confirmar `{found: false, event_id, project_id}`. Sólo esa ausencia confirmada permite repetir el evento exacto; un error MCP no es ausencia. La forma anterior `event_status(event_id)` conserva su contrato. Los documentos aprobados mantienen su outbox y conciliación documental separados.

El runtime añade `capture: {mode, hook_event, fingerprint}` al evento automático. `fingerprint` es SHA-256 del JSON canónico de `{project, runtime, session, event, payload}`: claves ordenadas recursivamente, UTF-8, sin espacios, conservando los campos realmente enviados del payload. El servidor verifica esa identidad antes de aplicar valores predeterminados y privacidad, y devuelve `capture_hash` en el recibo. No fabriques este campo para notas manuales: usa el runtime o el contrato y sus regresiones. El servidor exige su política actual para una captura nueva `full`; los reintentos idénticos ya aceptados conservan su recibo. Los tags heredados `capture:full` y `capture:summary` también respetan ese techo. No existe una comprobación semántica universal que descubra transcripciones disfrazadas de notas manuales.

`context` y `search` admiten `match_mode: "all" | "any"` (predeterminado `all`) y `exclude_categories`. La captura automática utiliza `any` y excluye `agent-activity` para recuperar aprendizajes útiles frente al ruido técnico. Los eventos automáticos técnicos no crean trabajos de embedding; notas manuales, documentos y aprendizajes derivados conservan su tratamiento habitual. `semantic` es `true` por defecto. El contexto automático del CLI la usa desde la versión 0.3.0, con un plazo propio del cliente (1,8 s por petición; el hook, 8 s). El CLI envía una sola petición con `semantic_budget_ms: 1100`: si la capa semántica no termina en ese presupuesto, el servidor devuelve los aciertos léxicos con `degraded` (`reason: timeout`), que el CLI declara en la evidencia que entrega al agente. No hay reintento del CLI. El servidor solo deja de esperar al proveedor de embeddings (cancela su propia petición HTTP); Ollama puede terminar el cálculo que ya empezó.

`search` y `context` admiten además `semantic_budget_ms` (entero opcional, de 1 a 600000 ms; fuera de rango, o un valor que no es un entero —`true`, `"1100"`, `1.5` y también `500.0`— es un error de validación, 422 en REST). **La validación es estricta sobre el tipo JSON:** un número con parte decimal explícita se rechaza aunque valga lo mismo que un entero (`500.0`), a pesar de que el esquema publicado lo describe como `integer`; envía siempre `500`, sin punto decimal ni notación científica (`5e2`). La capa semántica usa el menor entre `MEMORY_EMBED_QUERY_TIMEOUT` y ese presupuesto: nunca lo amplía. El presupuesto cubre toda la capa semántica, también la comprobación de que hay vectores. Al agotarse, la respuesta conserva los resultados léxicos y trae `degraded: {layer: "semantic", reason: "timeout"}`, igual que con el plazo configurado. Es un campo aditivo del contrato; sin él, el comportamiento no cambia.

La búsqueda semántica puntúa como máximo 10.000 candidatos actuales autorizados, en orden estable de identidad; no garantiza encontrar el vecino global más cercano fuera de ese conjunto. Lee vectores por lotes de 128 y carga el contenido sólo de los mejores resultados (máximo 100). Si hay más candidatos, devuelve `candidates_truncated: true`, backend `partial` y respuesta parcial. No presentes ese resultado como una búsqueda completa del corpus.

### Estado de cada capa: `backends`, `partial` y `degraded`

`search` y `context` devuelven `backends` con una entrada por cada capa pedida (`episodic`, `documental`, `temporal`) y otra, `semantic`, para la capa de embeddings. Cada entrada trae `status` y `count`:

| `status` | Significado | Lista de esa capa |
|---|---|---|
| `ok` | La capa respondió completa | Sus aciertos |
| `partial` | Respuesta válida pero incompleta: una rama de la capa cayó, o la búsqueda semántica alcanzó un tope (`candidates_truncated: true`) | Los aciertos obtenidos |
| `unavailable` | La capa falló (plazo, proveedor o error) | Vacía |
| `off` | No se ejecutó: `semantic: false`, consulta vacía, ninguna capa léxica pedida, proyecto sin vectores o embeddings desactivados | Vacía |

`partial` (booleano de la respuesta) es `true` si algún backend no está en `ok` ni en `off`; mantiene ese significado.

`degraded` es un campo **opcional** de la respuesta (en el contrato, el objeto `Degraded`: `layer` y `reason`). Solo aparece cuando la capa semántica es la única que se queda corta: la respuesta léxica es completa y válida, pero no es la híbrida. `reason` vale `timeout` (se agotó `MEMORY_EMBED_QUERY_TIMEOUT` o el `semantic_budget_ms` de la petición), `provider_error` (falló el proveedor de embeddings) o `store_error` (falló la base de datos al buscar vectores; motivo añadido de forma aditiva): con los tres, `backends.semantic.status` es `unavailable` y `partial` es `true`, `no_vectors` (nada embebido para esos proyectos) o `embeddings_disabled` (el servidor funciona sin embeddings); en los dos últimos `status` es `off`. `backends.semantic.reason` repite el motivo. Pedir `semantic: false` no es una degradación: `status: off` y ninguna llamada al proveedor. Para distinguir una degradación de un fallo: con `degraded` hay aciertos léxicos válidos; un fallo llega como error HTTP o MCP, o como otra capa en `unavailable` (entonces `degraded` no se informa, porque no falla solo la semántica).

Los aciertos que solo se encontraron por similitud de títulos (respaldo `pg_trgm`, ver [operación](operations.md#busqueda-lexica-por-idioma-y-trigramas)) llevan el campo opcional `lexical_match: "trigram"` y van detrás de los léxicos; la búsqueda léxica trata las consultas en español e inglés sin distinguir tildes (`unaccent`). Cada acierto semántico de un fragmento que no es todo el texto lleva `matched_chunk` (`ordinal`, `char_start`, `char_end`, puntos de código Unicode del texto `título + salto de línea + contenido`); sin fragmento propio, el campo se omite. `backends.semantic.candidate_limit` indica el tope de la ruta que respondió y `candidates_truncated` es `true` cuando se alcanzó: en la ruta exacta, más de 10.000 elementos candidatos (o el tope de fragmentos); en la ruta HNSW, el escaneo pudo detenerse en `max_scan_tuples` (20.000) con la respuesta corta. Ver [configuración](configuration.md#busqueda-vectorial-pgvector).

**Orden de los aciertos.** La búsqueda combina las capas por fusión de rangos recíprocos: cada acierto suma `peso / (k + posición)` por capa en la que aparece (`k = 60`, peso 1 en todas las capas) y los aciertos validados y vigentes suman además una bonificación de `0,0001`. Lo validado gana a igualdad razonable de posición, pero ya no es un orden absoluto: un acierto no validado mucho mejor posicionado puede superarlo. Los valores se ajustan con la puerta de evaluación (ver [configuración](configuration.md#fusion-de-capas-de-la-busqueda)).

| Herramienta | Uso y límites |
|---|---|
| `work_state_write` | Añadir cambios a una lista privada del actor y proyecto; requiere lectura, escritura y captura habilitada |
| `work_state_read` | Recuperar las listas, revisiones y tareas; las cerradas se excluyen salvo `includeClosed` |
| `get_observations` | Ampliar IDs de observaciones vigentes preservando título, etiquetas y procedencia |
| `observation_search` | Buscar observaciones por texto, dentro de un proyecto explícito |
| `observation_context` | Obtener evidencia textual acotada; no es una respuesta generada |
| `observation_generation_status` | Consultar un trabajo autorizado por su ID |
| `important_workflow` | Explicar la recuperación progresiva y la captura autorizada |
| `build_corpus` | Guardar una selección privada de hasta 500 observaciones vigentes |
| `prime_corpus` | Fijar su generación para consultas de evidencia |
| `query_corpus` | Recuperar fragmentos léxicos con referencias; requiere lectura y escritura porque persiste historial de consultas |
| `rebuild_corpus` | Actualizar la selección; rechaza perder más de la mitad sin `force` explícito |
| `reprime_corpus` | Fijar la generación vigente y comenzar un historial de consultas nuevo |
| `list_corpora` | Enumerar las selecciones privadas con versión, hash y sesión fijada |
| `observation_add` | Crear una observación con el contrato Event, UUIDs estables y versión 1 |
| `observation_record_event` | Añadir una revisión, corrección, evento de sesión o retirada con el mismo contrato |
| `get_tool_uses` | Recuperar resúmenes técnicos actuales con filtros y cursor; nunca salidas ni argumentos privados |
| `team_work_write` / `team_work_read` | Editar/leer listas explícitamente compartidas con el proyecto; versión esperada y recibo estable |
| `team_search` / `team_brief` | Buscar y resumir trabajo compartido con atribución |
| `corpus_answer` / `corpus_answer_status` | Solicitar una respuesta generada con citas o conciliar el resultado usando su mismo request_id |

Las herramientas adicionales responden mediante bloques de texto MCP. La mayoría contiene JSON; `important_workflow` devuelve instrucciones de uso. No confundas ese texto con un objeto `structuredContent`. Los bloques normales tienen un máximo de 32 KiB UTF-8 y `get_observations`, 256 KiB; una respuesta recortada lleva un marcador explícito y puede dejar de ser JSON completo. Acota la selección antes de automatizar su lectura.

### Diagnóstico: `X-Request-ID`, logs y métricas

Cada respuesta HTTP lleva `X-Request-ID`. Ese identificador aparece en los logs JSON del servidor, en la línea de acceso y en la de cada capa de la búsqueda, y permite al operador localizar una petición sin que el log contenga la consulta, el contenido ni los identificadores de proyecto. Cítalo en una incidencia. `GET /metrics` (formato Prometheus) no forma parte del contrato MCP ni del cliente: es solo de la red interna del servidor (ver [observabilidad](operations.md#observabilidad-logs-y-metricas)) y las herramientas MCP y sus esquemas no cambian por ello.

## Conectar con kairos-mcp

kairos-mcp (`memory-mcp`, versión 0.4.0) publica las mismas 34 herramientas por *streamable HTTP* en `/mcp/` del puerto `8791` de su red interna, con los mismos nombres, esquemas y anotaciones que el MCP interno (`docs/contracts/kairos-mcp.json`). La credencial es solo `Authorization: Bearer <clave>`; las sesiones con cookie del portal no se aceptan. Lo que ve un cliente respecto al MCP interno:

- **Dato no fiable.** Las herramientas con `readOnlyHint` (todas las de lectura salvo `important_workflow`) y `query_corpus` (anotada como escritura, pero su resultado es contenido recuperado) añaden `untrusted: true` y `warning` al principio del objeto JSON de la respuesta; ningún otro campo cambia y el texto sigue siendo JSON. El MCP interno hace lo mismo.
- **Errores.** Un fallo es un resultado con `isError` y el texto `Error executing tool <nombre>: <mensaje>`, con el mensaje del servidor. Caída, plazo (`KAIROS_API_TIMEOUT`, 30 s) o 5xx: `Memory service temporarily unavailable`. Sin cabecera `Authorization` o con otro esquema, y con una clave que `/v1` rechaza con 401: HTTP 401 con `{"error": {"code": "unauthorized", "message": "Authentication required"}, "request_id": ""}`. Cuerpo MCP mayor que `KAIROS_MAX_BODY_BYTES` (262144): 413 `body_too_large`. `initialize`, `tools/list` y `important_workflow` comprueban la credencial con `GET /v1/auth/me` (401 si la API la rechaza); si la API no responde no se rechaza la petición. Una respuesta de `/v1` con éxito pero cuerpo que no es un objeto JSON es un fallo de la llamada.
- **Tope de bytes.** 32 768 bytes (`NORMAL_BYTES`) en las herramientas de agente y 262 144 (`DETAIL_BYTES`) en `get_observations`, las observaciones y el equipo, y los corpus; un texto cortado termina con el marcador `[Output shortened at the UTF-8 byte budget; narrow the selection to retrieve more.]`. Las 12 herramientas básicas se limitan también a `DETAIL_BYTES` (el MCP interno no las limita).
- **`rebuild_corpus`.** Sin `expected_version` lee la versión actual y la envía; si otro `rebuild` la cambia entre la lectura y el envío, relee y reenvía como máximo 3 veces más, y después devuelve `Corpus version changed` (la herramienta montada en el MCP interno no tendría ese conflicto). Con `expected_version: 0` envía una versión que ningún corpus tiene: el servidor responde 403 o 404 en el orden del MCP interno y, para un corpus suyo, `Corpus version changed`, sin reconstruir. Una clave de solo lectura recibe el 403 de la herramienta con cualquier nombre.
- **Argumentos.** Un UUID en cualquier forma que acepta `uuid.UUID` (mayúsculas, sin guiones, con llaves) es el mismo UUID, y uno inválido da el texto del MCP interno; un entero como `20.0` es `20`; `.` y `..` en un argumento de ruta son valores, no rutas. `GET /v1/events/{id}` y `GET /v1/projects/{p}/documents/{id}` aceptan también un UUID en cualquier forma.
- **Diferencias con el MCP interno.** kairos-mcp añade `structuredContent` en las 12 herramientas básicas (el MCP interno solo envía el texto) y su 401 no lleva la cabecera `X-Request-ID` (el cuerpo es el mismo, con `request_id` vacío). Una llamada de herramienta que no llega a `/v1` (herramienta desconocida, argumentos que no cumplen el esquema o un UUID inválido) responde con el error de la herramienta a cualquier `Bearer` con esquema correcto, donde el MCP interno daría 401; no filtra datos. El texto `Input validation error: …` nombra el mejor de los 16 primeros errores del esquema (y cada rama de un `anyOf` aporta como máximo 16), así que con más de 16 fallos puede ser otro que el del SDK; con menos, es idéntico. El coste de validar es lineal en el tamaño de la entrada (hasta unos 2 s de CPU de Python para un cuerpo de 256 KiB, el mismo que cuesta una entrada válida de ese tamaño). Una entrada de hasta 1000 valores (cada elemento de un array y cada miembro de un objeto cuenta uno; una cadena larga es uno), que es casi toda llamada real, se valida en línea (unos 5 ms con elementos vacíos y hasta unos 15 ms con contenido real, como 140 `facts` o 990 cadenas de 256 B) y no hace cola detrás de las grandes: por HTTP, con 2, 6 y 40 validaciones grandes en curso, una llamada pequeña tarda 64-125 ms de mediana (6-15 ms sin carga; antes de 1 a 73 s), y con 40 cuerpos grandes llegando a la vez la primera puede tardar 1,6-4 s mientras el servidor lee esos cuerpos. Una entrada mayor se valida en un hilo de trabajo, fuera del event loop (el bucle se retrasa 12-55 ms en la imagen Linux de pruebas), de una en una por defecto (`KAIROS_VALIDATION_THREADS`, 1: el GIL comparte el CPU entre hilos de Python y con 2 no se midió ninguna mejora), y espera su turno como mucho 5 s: pasado ese plazo la llamada recibe `Memory service temporarily unavailable` sin llegar a `/v1`. Queda un límite: el CPU de un solo proceso es un techo de rendimiento (una validación grande ocupa 1-2 s de CPU) que un cliente con muchas peticiones grandes puede agotar, y las llamadas grandes legítimas pueden recibir ese error mientras tanto; acotar el ritmo por cliente es cosa del proxy o del rate limiting del operador. Una respuesta de `/v1` de hasta 64 MiB (el servidor produce unos 52 MB como máximo) se corta con el marcador del tope de su herramienta; más es `Memory service temporarily unavailable`.

Configuración del servicio en [Configuración](configuration.md#kairos-mcp); pruebas en [mcp/README.md](../mcp/README.md).

### Migración: el MCP interno queda en desuso y se retira en la 0.5.0

Desde la 0.4.0 la entrada MCP de la web (`/mcp/` del puerto `5173`, la que usa `kairos mcp`) la sirve kairos-mcp, no el servidor. Un cliente que usa esa dirección no cambia nada (el puente stdio del CLI sigue funcionando) pero ve las diferencias de la lista de arriba: solo `Authorization: Bearer` (sin sesión del portal), `structuredContent` en las 12 herramientas básicas, 401 sin `X-Request-ID` y el trato de las llamadas que no llegan a `/v1`.

- **El MCP interno sigue en `memory-api:8790/mcp/`** (el puerto `127.0.0.1:8790` publicado por el Compose) durante toda la 0.4.x. Cada respuesta suya, también un 401 o un error, lleva `Deprecation: true` y `Sunset: 0.5.0` (la versión que lo retira; no hay fecha fijada), y cada una deja en el log JSON del servidor un evento `mcp_legacy_used` con `method`, `status` y `request_id`, sin credencial, argumentos ni contenido. Busca ese evento en el log para saber qué clientes siguen usándolo.
- **`MEMORY_MOUNT_MCP`** (por defecto `1`). Con `0` el servidor no monta el MCP interno y cualquier ruta bajo `/mcp` de `memory-api` responde 404; un valor distinto de `0` y `1` detiene el arranque. Pruébalo antes de la 0.5.0 para comprobar que nadie lo usa; en la 0.5.0 desaparece el interruptor y el montaje.
- **Sin modelo de lenguaje.** `MEMORY_LLM_MODEL` ya no tiene valor por defecto (antes `beam:cloud`) y solo es obligatorio si activas `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on`. Quien dependía del valor anterior debe fijarlo.
- **Cambio en la captura de resúmenes (R-03).** Con `MEMORY_EXTRACT_ENABLED=0` (valor por defecto) un evento con `generate: true`, que el CLI envía en los resúmenes, se acepta con 202, queda guardado e indexado tal cual y no crea trabajo `extract`: el servidor ya no deriva aprendizajes del resumen, y el recibo añade `extraction: "disabled"`. Para recuperar la extracción en el servidor activa `MEMORY_EXTRACT_ENABLED=1` con un `MEMORY_LLM_MODEL`; los trabajos que ya estaban en cola quedan `extraction_disabled` y se reencolan con `POST /v1/jobs/{id}/retry`.
- **Cómo desplegarlo.** Reconstruye y recrea `memory-web` (nueva ruta y red `mcp`) junto con `memory-mcp`; `memory-web` no arranca sin `memory-mcp` sano. Pasos y comprobaciones en [operaciones](operations.md#retirada-del-mcp-interno).

## Compartir el estado de trabajo con el panel

Cada lista pertenece al actor autenticado y a un proyecto. Dos claves del mismo actor comparten sus listas dentro de los permisos concedidos. Actores diferentes no ven esas listas aunque puedan consultar el mismo proyecto. No se infiere el proyecto a partir del directorio del servidor.

```json
{
  "project": "mi-proyecto",
  "list": "Preparar entrega",
  "fields": {"task": "Verificar persistencia", "status": "doing"},
  "request_id": "entrega-42-verificar-persistencia",
  "expected_version": 0
}
```

Envía este objeto a `work_state_write`. `expected_version: 0` exige una lista nueva; para modificar una existente utiliza la versión recuperada. Conserva el `request_id` y el objeto completo ante un timeout. Repetirlo devuelve su recibo original; reutilizarlo con otro contenido produce conflicto. `fields.task` selecciona una tarea, `null` elimina un campo y los estados son `todo`, `doing`, `done` y `dropped`. Sin `task`, los campos describen la lista. `description`, `summary` y `needs_input` se representan en las tarjetas de **Mi trabajo**.

La web usa `GET` y `POST /v1/projects/{project_id}/work-state` sobre el mismo dominio persistente. Marcar una tarea como completada no valida conocimiento ni demuestra que una comprobación técnica haya pasado. La lista conserva revisiones e historial; un reinicio no la borra.

## Corpus de evidencia

Los corpus seleccionan observaciones ya autorizadas. No leen carpetas del servidor, no descargan URLs y no incluyen automáticamente documentos publicados. Los filtros `types`, `concepts` y `files` admiten listas; usa `concepts: ["nota:uno,dos"]` para conservar exactamente etiquetas con comas. El formato de texto separado por comas es sólo una comodidad para filtros simples, nunca una reconstrucción de etiquetas almacenadas.

El flujo de recuperación es `build_corpus` → `prime_corpus` → `query_corpus`. Cada corpus conserva IDs, versiones y hashes. Una modificación, retirada o sustitución de una fuente invalida su lectura hasta reconstruir y volver a fijar la generación. Se revalidan permisos y revocaciones incluso si hay un resultado en caché. `query_corpus` conserva el modo `lexical_evidence`: devuelve fragmentos y referencias sin llamar al modelo. Su historial está limitado a cien consultas y 2 MiB por corpus.

Para una respuesta generada utiliza `corpus_answer` pasando la sesión y versión devueltas por la preparación, una pregunta y un `request_id` estable. La operación reserva presupuesto de admisión, llama una sola vez al modelo configurado y comprueba citas y vigencia antes de persistir. Una respuesta incierta se consulta mediante `corpus_answer_status`; no se vuelve a generar automáticamente. `reprime_corpus` inicia otra conversación sin borrar las fuentes ni reiniciar el presupuesto acumulado. Consulta [respuestas sobre corpus](corpus-generated-answers.md) y [observaciones/equipo](extended-workflows.md) para límites y ejemplos completos. Las reglas son notas con etiqueta exacta `kairos:rule`; su validación requiere evidencia y permiso, no sólo su recepción.

## Dos flujos de escritura separados

La **memoria episódica** conserva experiencias, resúmenes, aprendizajes o correcciones. La **publicación documental** transporta conocimiento que ya está aprobado en el proyecto consumidor. Una nota generada no se convierte automáticamente en documento aprobado.

Mantén dos outbox o tipos de registros diferenciados. Cada registro debe conservar operación, proyecto, identidad, versión, hash, estado de entrega y recibo remoto. No guardes claves ni transcripciones completas en esos recibos. Un reinicio del plugin no debe perder la identidad de un envío incierto.

## Capturar memoria con identidad estable

Antes de una tarea llama `projects`, `search` y `details` o `context`. Después de una tarea, envía únicamente lo útil y autorizado. `remember` recibe un evento con `event_id`, `item_id`, `version`, `project_id`, `session_id`, `agent_id`, `event_type`, `occurred_at`, `payload` y opcionalmente `generate`.

Ejemplo conceptual del argumento `event`:

```json
{
  "event_id": "be691ff7-e210-4505-83d7-8cb0ac513648",
  "item_id": "f94c28a5-cf55-451d-b946-5966bd315d92",
  "version": 1,
  "project_id": "mi-proyecto",
  "session_id": "sesion-2026-11-04-01",
  "agent_id": "agente-backend",
  "event_type": "learning",
  "occurred_at": "2026-11-04T09:00:00Z",
  "generate": false,
  "payload": {
    "title": "Comprobar la entrega antes de reintentar",
    "content": "Tras un timeout, consultar primero el recibo estable.",
    "category": "integraciones",
    "tags": ["area:api", "nota:uno,dos", "revisión: \"válida\""],
    "validation_status": "observed",
    "evidence": ["incidencia:42"]
  }
}
```

Los UUID del ejemplo son ilustrativos. Genera los tuyos una sola vez y persístelos antes del primer envío. El mismo evento incierto se repite sin modificar su contenido, IDs ni fecha. Una corrección real utiliza la siguiente versión del elemento y un nuevo evento; `supersedes` puede señalar el elemento corregido.

Consulta `event_status(event_id)` después de una aceptación o timeout. `complete` significa que todos los trabajos asociados terminaron correctamente y el recibo no está sustituido. Guarda el resultado. Si faltan trabajos por terminar, deja el registro pendiente. Si el estado es incierto, concilia; no inventes un UUID nuevo.

`generate: true` solicita procesamiento de generación cuando el flujo está permitido. No equivale a validación: los aprendizajes generados permanecen sin validar. Tipos admitidos: `note`, `summary`, `learning`, `correction`, `session_start`, `session_end` y `delete`. La política del servidor puede restringirlos.

## Observaciones estructuradas con esquema versionado

Cuando quieras que el servidor compruebe la forma de una observación o de un resumen de sesión, añade el documento a `payload.structured` del mismo evento de `remember` o de `observation_add`. Dos esquemas JSON (JSON Schema 2020-12) lo definen:

| Esquema | Fichero | Campos (todos obligatorios) |
|---|---|---|
| `observation.v1` | `docs/contracts/observation.v1.schema.json` | `schema_version`, `type`, `title`, `facts`, `narrative`, `concepts`, `files_read`, `files_modified` |
| `session-summary.v1` | `docs/contracts/session-summary.v1.schema.json` | `schema_version`, `request`, `investigated`, `learned`, `completed`, `next_steps` |

`schema_version` es la constante del esquema (`"observation.v1"` o `"session-summary.v1"`) y elige con qué esquema se valida el documento. Ningún esquema admite campos sobrantes (`additionalProperties: false`). Límites de `observation.v1`: `type` es uno de `decision`, `bugfix`, `feature`, `refactor`, `change` o `discovery`; `title` de 1 a 200 caracteres; `narrative` de 1 a 20 000; `facts` hasta 20 elementos, cada uno con `statement` (1 a 500) y `evidence_quote` (1 a 2 000, la cita literal que respalda el hecho); `concepts` hasta 20 etiquetas únicas de 1 a 100 caracteres; `files_read` y `files_modified` hasta 50 rutas únicas de 1 a 500 caracteres. En `session-summary.v1`, los cinco campos de texto tienen de 1 a 4 000 caracteres. El límite de 256 KiB por evento sigue aplicándose, y el servidor no redacta `structured`: si contiene un bloque `<private>`, una clave privada o un dato con aspecto de secreto, rechaza el evento entero con 422 y no guarda nada: `sensitive_source_requires_review`, o `invalid_private_block` / `invalid_private_key_block` si el bloque está sin cerrar. Retira el dato sensible del documento antes de enviarlo. En el resto del evento se aplican las reglas de siempre: `title`, `content`, `problem`, `correction`, `evidence` y `tags` se redactan, y un elemento de `facts` con un dato sensible se descarta. Un documento de más de 1 000 valores (objetos, listas y escalares) se rechaza con `maxNodes`; uno válido en todos sus límites tiene menos de 200.

```json
{
  "schema_version": "observation.v1",
  "type": "bugfix",
  "title": "Corregir el bucle de reintentos del worker",
  "facts": [{"statement": "El bucle no esperaba entre intentos", "evidence_quote": "reintentaba cada 10 ms sin pausa"}],
  "narrative": "Al leer el worker vi que reintentaba cada 10 ms sin pausa. Añadí una espera exponencial.",
  "concepts": ["reintentos", "espera exponencial"],
  "files_read": ["worker/sync.py"],
  "files_modified": ["worker/sync.py"]
}
```

**Solo se valida lo que declara `structured`.** Un evento sin `payload.structured` no se valida y se acepta como siempre; el CLI 0.3.0 no lo envía y no cambia. Si `structured` llega y no cumple su esquema (falta un campo, sobra uno, un texto o una lista excede su límite, el tipo es erróneo o `schema_version` falta o es desconocida), el servidor responde **422** con el código `invalid_observation` y un mensaje con la ruta JSON del primer error, por ejemplo `Structured observation does not match its schema: maxLength at /payload/structured/title`. El mensaje nunca reproduce valores del contenido. Corrige el documento y reenvía el evento con la misma identidad: un 422 no deja nada guardado.

Valida un documento en local antes de enviarlo. Los ejemplos válidos e inválidos de cada esquema están en `docs/contracts/examples/<esquema>/valid/` y `.../invalid/`:

```bash
python -c "import json,sys,jsonschema;s=json.load(open('docs/contracts/observation.v1.schema.json',encoding='utf-8'));jsonschema.Draft202012Validator(s).validate(json.load(open(sys.argv[1],encoding='utf-8')))" mi-observacion.json
python -m unittest discover -s scripts/tests -p test_contract_examples.py
```

La primera orden termina con error y la ruta del fallo si el documento no es válido; la segunda comprueba todos los ejemplos con `jsonschema`, un validador que no comparte código con el servidor.

## Publicar conocimiento aprobado

El consumidor conserva la aprobación local y su evidencia. No debe enviar candidatos pendientes ni todo el repositorio. Para cada fuente, asigna un UUID documental canónico y una versión remota secuencial, manteniendo la correspondencia con su ID local.

`publish_document(project_id, document)` requiere `publish` y `validate`. `document` contiene `document_id`, `version`, `title`, `content`, `category`, `tags`, `source` y `validation`. El título es texto legible; las etiquetas siguen siendo una lista de cadenas y no se aplanan separándolas por comas.

`source.uri` debe permitir identificar el original. `source.sha256` debe ser el SHA-256 hexadecimal minúsculo de **los bytes UTF-8 exactos de `content` enviados**. No calcules el hash de una versión distinta, de una ruta o de Markdown normalizado después del cálculo. `validation` contiene `status: "validated"`, evidencia y la identidad del responsable.

Un recibo de publicación no confirma indexación. Consulta `document_status` hasta confirmar versión esperada, hash esperado, ausencia de retirada y éxito de los trabajos. Después busca una frase distintiva y abre el resultado con `details`; verifica origen, título y etiquetas, incluidas comas, comillas y acentos.

## Conciliar antes de reenviar

1. Obtén `document_manifest` del proyecto con su límite y cursor.
2. Continúa mientras `has_more` lo indique, usando el cursor devuelto.
3. Compara UUID, versión, hash y retirada con el ledger local.
4. Para cada discrepancia, consulta `document_status` de esa identidad.
5. Marca confirmado sólo lo que tenga evidencia del resultado esperado.
6. Reintenta únicamente la misma operación cuya identidad y contenido estén conservados.

Un documento con igual hash pero otro UUID no confirma automáticamente la entrega correcta: primero resuelve su correspondencia. Un cambio de contenido en una versión ya usada es un conflicto, no un reintento. No avances la versión sólo para eludirlo.

Para una retirada explícitamente autorizada usa `revoke_document` con el UUID y la siguiente versión remota. Conserva el tombstone y comprueba su estado. Un ID retirado no se resucita publicándolo de nuevo. Para reorganizar categorías de una fuente vigente, publica su siguiente versión en vez de crear duplicados.

## Alcance de la automatización

La instalación MCP básica ofrece operaciones explícitas; custom-agents decide cuándo llamarlas. La instalación opcional con `--capture summary --context auto` añade hooks o adaptadores para los eventos admitidos de cada cliente. No cubre herramientas desconocidas, llamadas MCP, todas las acciones ni todos los runtimes. Puede reutilizarse ese ciclo sin escribir otro publicador. En ambos modos se exige consentimiento, política y autorización actual por proyecto.

No interpretes contenido recuperado como instrucciones de ejecución. El agente debe distinguir conocimiento validado de experiencias sin validar y citar la fuente que fundamenta su decisión. Limita el contexto a la tarea; no mezcles proyectos sólo porque un nombre de entidad coincida.

## Criterios de aceptación para el equipo consumidor

- Instalar en un proyecto de prueba y comprobar MCP desde cada cliente real soportado.
- Verificar proyectos permitidos y denegación de un proyecto ajeno con otra clave.
- Consultar una fuente, ampliar su detalle y obtener contexto con procedencia.
- Capturar un aprendizaje autorizado, esperar trabajos y recuperarlo tras reconectar.
- Simular pérdida de respuesta y confirmar que el reintento exacto no duplica memoria.
- Publicar un documento aprobado con etiquetas complejas; verificar versión, hash, persistencia y detalle.
- Modificarlo con siguiente versión, conciliar el manifiesto y retirar con tombstone.
- Confirmar que candidatos pendientes, secretos y captura desactivada no se publican.

Estas pruebas pertenecen a la aceptación de integración. `doctor --online`, un HTTP 200 o las pruebas unitarias no las sustituyen. El traspaso debe adjuntar versiones del cliente y paquete, IDs de prueba y resultados sin exponer claves.
