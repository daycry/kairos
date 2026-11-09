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

`context` y `search` admiten `match_mode: "all" | "any"` (predeterminado `all`) y `exclude_categories`. La captura automática utiliza `any` y excluye `agent-activity` para recuperar aprendizajes útiles frente al ruido técnico. Los eventos automáticos técnicos no crean trabajos de embedding; notas manuales, documentos y aprendizajes derivados conservan su tratamiento habitual. `semantic` continúa siendo una opción explícita: el contexto automático la desactiva.

La búsqueda semántica puntúa como máximo 10.000 candidatos actuales autorizados, en orden estable de identidad; no garantiza encontrar el vecino global más cercano fuera de ese conjunto. Lee vectores por lotes de 128 y carga el contenido sólo de los mejores resultados (máximo 100). Si hay más candidatos, devuelve `candidates_truncated: true`, backend `partial` y respuesta parcial. No presentes ese resultado como una búsqueda completa del corpus.

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
