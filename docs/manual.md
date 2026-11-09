# Manual de uso de Kairos

Última actualización: 2026-11-06.

## Para qué sirve

Kairos conserva contexto útil entre tareas y agentes. Permite encontrar decisiones de un proyecto, aprender de errores concretos, publicar fuentes aprobadas y comprobar de dónde sale cada resultado. El servicio central evita depender de una carpeta compartida entre todos los clientes.

Aprender significa conservar una experiencia que pueda recuperarse más adelante. No significa que se hayan cambiado los pesos del modelo. Una nota puede ser incorrecta, estar pendiente de revisión o haber sido sustituida. Comprueba su versión, evidencia y validación antes de aplicarla.

El flujo habitual es consultar antes de actuar, trabajar sobre el proyecto, guardar un resumen pequeño de lo aprendido y comprobar su procesamiento. Las conversaciones completas y los repositorios enteros no son la unidad recomendada de captura.

## Primer acceso

Abre `http://127.0.0.1:5173/` para la web pública. El panel privado está en `/app/` y la documentación publicada en `/docs/`. En una instalación remota usa la dirección HTTPS que facilite su administrador; `127.0.0.1` siempre se refiere a tu propio equipo.

Introduce el usuario y contraseña que haya preparado el administrador. Este manual no incluye credenciales universales. Si no recuerdas la contraseña, solicita al operador el procedimiento de acceso de esa instalación; no compartas la contraseña de bootstrap en incidencias o conversaciones.

Después del acceso, Kairos carga los proyectos autorizados. No ver un proyecto puede significar que tu cuenta no tiene permiso o que todavía no se ha creado. Una clave de agente y una contraseña de usuario tienen usos diferentes: la clave sirve para integrar un cliente, no para rellenar el formulario de acceso.

## Orientarse en el panel

| Sección | Para qué usarla |
|---|---|
| Mi trabajo | Revisar listas y tareas persistidas por los agentes; completar una tarea autorizada |
| Memoria | Revisar notas y aprendizajes recibidos; crear y versionar memoria |
| Observaciones | Recuperar registros vigentes con su sesión, autor, versión y evidencia |
| Reglas del proyecto | Revisar guías explícitas, crear versiones y distinguir lo validado de lo pendiente |
| Actividad | Comprobar entregas registradas sin mostrar entradas ni salidas privadas de herramientas |
| Consultar corpus | Crear una selección de memorias y obtener respuestas generadas con citas |
| Buscar | Recuperar resultados por contenido y preparar contexto acotado |
| Mapa | Explorar documentos, memorias y relaciones visualmente |
| Sesiones | Localizar sesiones y consultar memoria vinculada |
| Historia | Revisar el recorrido cronológico de los eventos |
| Operaciones | Comprobar el procesamiento y los fallos pendientes |
| Configuración | Administrar proyectos, políticas, usuarios y claves si tienes permiso |

Algunas acciones no aparecen si tu cuenta carece de su permiso. No intentes solventarlo usando una clave de administrador en todos los agentes; pide el permiso mínimo necesario para tu tarea.

## Revisar Mi trabajo

Abre **Mi trabajo** desde el menú. Las tarjetas muestran las listas que tu identidad ha guardado en los proyectos seleccionados. No son una simulación de agentes conectados. La fecha corresponde a la última actualización persistida y la versión permite detectar cambios concurrentes.

Busca por nombre de proyecto, lista o tarea y utiliza el selector de estado. Ambos filtros actúan sobre las listas cargadas, sin llamar al modelo. **Actualizar trabajo** vuelve a consultar el servidor. Un fallo de un proyecto se muestra por separado; las listas recibidas de otros proyectos siguen disponibles.

Despliega **Ver tareas y detalles** para revisar los elementos. La barra representa tareas finalizadas respecto al total de esa lista. Una tarea `done` o `dropped` cuenta como finalizada; no implica aprobación del conocimiento ni calidad del resultado. **Necesita tu atención** procede del campo explícito `needs_input`, no de una deducción sobre tu actividad.

Con permiso de escritura y captura habilitada puedes pulsar **Completar**. Si se pierde la respuesta, **Reintentar confirmación** conserva exactamente la operación original y su identificador. No cierres la vista mientras una confirmación sea incierta: consulta el estado antes de crear otra modificación. Un cambio concurrente puede exigir actualizar la lista y revisar su nueva versión.

El selector **Mi trabajo privado / Trabajo del equipo** cambia el ámbito de las listas. Las privadas sólo son visibles para tu identidad. Las del equipo son visibles para lectores del proyecto y sus cambios requieren permiso de escritura y captura habilitada. Cada edición compartida conserva el autor, la versión y el hash; dos ediciones sobre la misma versión no se sobrescriben silenciosamente. Los agentes utilizan `work_state_write` para listas privadas y `team_work_write` para las compartidas. Los detalles de una tarea pueden incluir descripción, responsable, evidencia y categoría como campos de texto. Consulta [observaciones y equipo](extended-workflows.md).

El contador muestra listas visibles frente a listas cargadas y tareas guardadas en las listas visibles. No representa agentes conectados, horas trabajadas ni aprendizaje validado. Si seleccionas una categoría, una lista debe declarar esa categoría en sus campos o en alguna tarea para aparecer.

## Observaciones y reglas

**Observaciones** muestra la memoria vigente del proyecto. Al retirarla o sustituirla deja de aparecer como vigente. **Historia** conserva el recorrido de entregas y no debe confundirse con la última versión. Los títulos, etiquetas y fuentes se muestran como texto; una etiqueta que contiene comas sigue siendo una sola etiqueta.

**Reglas del proyecto** utiliza la etiqueta exacta `kairos:rule`. Pulsa **Nueva regla**, indica título, contenido, sesión y autor y añade la procedencia. La categoría permanece disponible para organizar reglas, por ejemplo `backend` o `despliegue`. Guardar una regla no la aprueba: el estado validado exige permiso de validación y referencias de evidencia. El servidor no ejecuta su contenido. Los agentes deben tratarla como información recuperada y contrastarla con las instrucciones autorizadas de su tarea. Para dejar de usarla, retírala; para corregirla, crea su siguiente versión.

**Actividad** enumera eventos realmente recibidos, su fecha y referencia. Un evento recibido no demuestra que la extracción o los embeddings hayan terminado; compruébalo en **Operaciones**. Con un proyecto seleccionado, la barra de actividad puede anunciar nuevas entregas y actualizar memoria, observaciones, reglas o actividad. Si se corta la conexión aparece una acción de reconexión; no se simula actividad.

## Consultar un corpus

1. Selecciona un único proyecto y abre **Consultar corpus**. Cada usuario conserva sus propias selecciones.
2. Escribe un nombre y, opcionalmente, palabras de búsqueda y etiquetas exactas, una por línea. La categoría de la barra lateral acota la selección. **Crear selección** incorpora hasta 500 memorias vigentes; no sube archivos ni añade documentos externos automáticamente.
3. Pulsa **Preparar corpus** para fijar IDs, versiones y hashes. Preparar no llama al modelo.
4. Escribe una pregunta y pulsa **Enviar al modelo**. Esta acción sí utiliza el modelo configurado y consume presupuesto de admisión. Las preguntas siguientes conservan un contexto acotado de esa conversación.
5. Revisa la respuesta, sus citas literales, referencias, generación y modelo. Se muestra **Sin validar**: comprobar que una cita existe no garantiza que la interpretación sea correcta.
6. Si la respuesta se pierde, conserva el identificador mostrado y pulsa **Comprobar consulta pendiente**. No envíes la misma pregunta con otro identificador: el servidor podría haberla procesado. Un estado `unknown` conserva su reserva y no se reenvía automáticamente.
7. **Nueva conversación** limpia la continuidad para esa selección; no restablece el presupuesto acumulado ni borra fuentes. Si una fuente cambia o se retira, pulsa **Actualizar selección de fuentes** y vuelve a preparar el corpus antes de preguntar. Si la selección pierde más de la mitad de sus memorias, el servidor exige revisión explícita; el agente puede utilizar `rebuild_corpus` con `force` después de esa revisión.

La vista no llama al modelo al abrirse. Si no hay evidencia suficiente, no se genera una respuesta inventada. Las reservas se expresan en unidades de admisión de tokens, no en euros ni en coste facturado. Los límites y estados exactos se describen en [respuestas sobre corpus](corpus-generated-answers.md).

## Proyectos y categorías

Cada proyecto es un espacio de memoria con identidad y permisos propios. Por ejemplo, `portal-clientes` y `facturacion` pueden tener agentes, fuentes y políticas diferentes. Una categoría organiza contenido dentro del proyecto: `despliegue`, `backend` o `decisiones`.

La barra lateral permite buscar proyectos por su nombre. Esa búsqueda reduce el catálogo visible; no busca dentro de los documentos. Abre el acordeón del proyecto para ver sus categorías indentadas. Usa **Todo el proyecto** para quitar la categoría conservando el proyecto. **Todos los proyectos autorizados** amplía el ámbito a tus proyectos accesibles.

Las categorías proceden de los metadatos del contenido; no se crean editando el HTML de la barra. Al enviar una memoria o publicar una fuente, informa `category`. Utiliza una convención consistente: `Backend` y `backend` pueden acabar como categorías diferentes. Las etiquetas son otra dimensión, con varios valores por elemento; conserva sus valores completos, incluidas comas y acentos.

| Control | Alcance real |
|---|---|
| Proyecto de la barra | Determina qué proyectos consulta la vista |
| Categoría de la barra | Filtra Buscar y Mapa |
| Texto de Buscar | Se envía al motor de recuperación con las capas y filtros seleccionados |
| Texto de Mapa | Se aplica al solicitar la instantánea del mapa |
| Filtrar esta lista | Busca entre los elementos ya cargados en Memoria, Historia u Operaciones |
| Filtrar por sesión o agente | Busca en las sesiones ya cargadas |

Cambiar la categoría no transforma una lista de operaciones en una lista por categoría. Para encontrar un elemento que no se ha cargado, usa **Cargar más**, cambia el proyecto o utiliza Buscar. Con más de veinte proyectos autorizados, selecciona uno para las consultas que alcanzan ese límite.

## Qué significan los contadores

Los números responden a preguntas distintas. No tienen por qué coincidir entre pantallas.

| Dónde aparece | Qué cuenta | Qué no significa |
|---|---|---|
| Tarjetas de Buscar | Totales de memorias, documentos gestionados, sesiones y operaciones de los proyectos seleccionados | Coincidencias del texto ni total después de la categoría |
| Encabezado de resultados | Resultados recibidos en esa consulta | Todo el contenido existente o todas las páginas |
| Lista: visibles / cargados | Coincidencias del filtro local y filas descargadas | Total global de la base de datos |
| Mapa: memorias, documentos, entidades, relaciones | Elementos de la instantánea actual y sus conexiones válidas | Inventario completo de todos los proyectos |

Por ejemplo, «8 visibles · 50 cargados · hay más páginas» quiere decir que el navegador descargó 50 filas, el filtro local muestra ocho y aún puede pedir más. «20 resultados recibidos» puede deberse al límite de la consulta. Que el mapa tenga más bolitas que documentos es normal: también representa memorias y entidades.

## Buscar información y preparar contexto

Selecciona el proyecto y escribe una pregunta concreta, por ejemplo: «¿Qué comprobaciones debemos hacer antes de desplegar el backend?». Elige las capas que necesitas: memoria episódica, documentos o relaciones temporales. Añade categoría y etiquetas si quieres restringir el resultado. Ejecuta la búsqueda.

Una tarjeta muestra título, proyecto, capa, estado de validación, versión, extracto y, cuando existe, fuente con hash. Abre el título para ampliar la ficha. No copies un extracto sin abrir su evidencia si la decisión tiene consecuencias.

La búsqueda combina la recuperación del servidor y, cuando se solicita y está disponible, la recuperación semántica. Un resultado vacío no demuestra ausencia de conocimiento: revisa el proyecto, las capas, los filtros y las operaciones pendientes. Busca también palabras que aparezcan en la fuente.

La acción de preparar contexto devuelve una selección acotada con procedencia y avisos. Su objetivo es facilitar el siguiente trabajo del agente. Sigue siendo una selección, no una garantía de que todo el conocimiento relevante esté incluido. Si aparece un aviso de resultados parciales, comprueba qué capa no respondió antes de tomarlo como una respuesta completa.

## Leer una ficha y evaluar su fiabilidad

La ficha amplía el contenido, el problema, la corrección y la evidencia disponibles. Muestra la versión y avisa si fue sustituida. La fuente puede ser una URL o un identificador; las rutas e identificadores sin URL se muestran como texto y no se ejecutan.

| Estado | Cómo interpretarlo |
|---|---|
| Sin validar (`unverified`) | Registro pendiente de comprobación |
| Observado (`observed`) | Experiencia observada; no equivale a regla aprobada |
| Validado (`validated`) | Existe una validación registrada con su responsabilidad y evidencia |
| Sustituido (`superseded`) | Consulta la corrección o versión vigente |
| Desconocido (`unknown`) | La información disponible no permite afirmar el estado |

Si el detalle está truncado, no interpretes el final visible como el final del documento. Si la fuente ya no está disponible, vuelve a buscar: pudo cambiar de versión o retirarse. La puntuación o el orden de búsqueda no sustituyen la validación.

## Guardar una memoria útil

Necesitas permiso de escritura y una política que admita ese tipo de captura. En **Nueva memoria** completa:

1. Proyecto, tipo y título descriptivo.
2. Contenido con el contexto en el que sirve el aprendizaje.
3. Sesión de origen y agente o autor.
4. Problema observado y corrección cuando correspondan.
5. Evidencia: una referencia por línea.
6. Categoría, etiquetas y referencia de origen si las conoces.
7. Estado de validación acorde con lo que realmente se ha comprobado.

Ejemplo de aprendizaje: título «Comprobar el resultado de una entrega antes de reintentar»; problema «La conexión expiró después de enviar»; corrección «Consultar el recibo por su identidad estable antes de repetir»; evidencia «Incidencia interna y prueba de conciliación». Es más reutilizable que copiar toda una conversación.

Introduce una etiqueta por línea. `nota:uno,dos` es una etiqueta, no dos. Puedes usar comillas, acentos y emoji como texto. No incluyas contraseñas, claves ni datos personales innecesarios. Los fragmentos `<private>…</private>` y la detección del servidor ayudan a ocultar contenido, pero no reconocen todos los datos sensibles: revisa el texto antes de enviarlo.

Guardar devuelve un recibo. La aceptación significa que se registró la solicitud; no que todas las representaciones derivadas estén listas. Comprueba **Operaciones**. El formulario conserva la identidad del envío para permitir reintentar la misma solicitud si la respuesta se pierde. No cierres y crees otra memoria idéntica sólo porque tarde.

Si solicitas generación de aprendizajes a partir de un contenido autorizado, comprueba además el trabajo de extracción. La generación produce candidatos sin validar; un modelo no debe aprobar su propio resultado como conocimiento definitivo.

## Corregir y retirar memoria

Usa **Crear siguiente versión** para corregir un elemento existente. Se conserva su identidad y aumenta la versión. Indica qué cambió y aporta evidencia nueva cuando proceda. Para una corrección relacionada con otro aprendizaje, informa el identificador que sustituye.

**Retirar memoria** registra una nueva versión de retirada. No borra el historial como si el elemento nunca hubiera existido. Antes de confirmar, comprueba proyecto, título e identidad. Después revisa las operaciones asociadas y vuelve a consultar para confirmar que no aparece como memoria vigente.

Evita publicar una copia con un UUID nuevo para arreglar la anterior: genera duplicados y dificulta saber qué versión está vigente. Si el agente perdió su estado local, consulta recibos y manifiestos antes de reenviar.

## Publicar documentos aprobados

La publicación documental está separada de las notas de sesión. Necesita permisos de publicación y validación. El documento debe tener título, contenido, referencia de origen y evidencia de su aprobación. Añade categoría y etiquetas para facilitar su recuperación.

El formulario calcula SHA-256 sobre el contenido que envía. La identidad documental y su versión permiten reintentos seguros. No publiques candidatos pendientes como si fueran aprobados. Conservar una referencia al original permite explicar por qué una fuente está en la plataforma y dónde revisarla.

Tras enviar, comprueba sus trabajos en **Operaciones** y búscalo por una frase característica. Abre la ficha para revisar título, categoría, etiquetas, fuente y versión. En una integración automatizada, comprueba además `document_status` y el manifiesto; el procedimiento detallado está en [integración](integration.md).

La acción **Retirar este documento** crea la siguiente versión de retirada. La retirada debe verificarse igual que la publicación. El mismo ID retirado no debe reutilizarse para resucitar la fuente; una nueva publicación requiere una decisión de identidad explícita.

## Sesiones, historia y actualizaciones

Una sesión agrupa actividad por su identificador y los agentes que la emitieron. No supone que se haya guardado una transcripción. Los clientes deben enviar los eventos que estén autorizados por la política.

**Ver memoria de esta sesión** consulta una página limitada de memorias y selecciona las que pertenecen a esa sesión. Si aparece «Sin notas en esta página», no es una demostración de que no existan en otra página. Para una investigación exhaustiva usa las consultas y ventanas temporales de la API/MCP.

Las listas ofrecen actualización y paginación. Un fallo al cargar más no elimina los elementos ya recibidos: reintenta esa carga. La actividad en vivo informa de conexión, reconexión o detención. Cuando vuelva la conexión, utiliza Actualizar si necesitas comprobar el estado definitivo de una operación.

## Explorar el mapa

El mapa representa memorias, documentos y entidades, con relaciones conservadas por el servidor. Selecciona proyectos y categorías; usa el campo de búsqueda y **Aplicar al mapa** para solicitar otra instantánea. **Actualizar mapa** repite la carga y **Centrar mapa** ajusta el encuadre.

Las categorías de cada proyecto reciben colores calculados para distinguir grupos. El color es una ayuda de orientación, no indica calidad, riesgo ni validación. Consulta el nombre del proyecto y categoría en la etiqueta o ficha: no dependas sólo del color. Con muchas categorías una paleta puede tener colores cercanos.

Al pasar por una bolita se muestra su nombre y tipo. Al pulsar una memoria o documento con referencia se abre la ficha de fuente. Algunas entidades no tienen ficha propia: en ese caso abre la evidencia de una relación. La ausencia de una relación puede deberse al filtro, al límite de la instantánea, a procesamiento pendiente o a que no existe una extracción con evidencia para ella.

El botón **Usar vista de lista** permite explorar los mismos datos sin manipular el mapa 3D. Es útil con teclado, pantallas pequeñas o equipos sin aceleración gráfica suficiente. El mapa pausa su animación cuando la página queda oculta y libera el renderizador al salir de la vista.

No confundas proximidad visual con relación demostrada. Las posiciones responden a la disposición del grafo. Comprueba la arista, su etiqueta y la fuente antes de deducir una dependencia entre elementos.

## Operaciones: recibido no significa terminado

Las tarjetas muestran destino, tipo, versión, intentos e identificador. Su estado permite distinguir trabajo pendiente de un fallo real.

| Estado habitual | Qué hacer |
|---|---|
| `pending` | Esperar al trabajador y actualizar; revisar la cola si no progresa |
| `running` | Dejar terminar y comprobar de nuevo |
| `succeeded` | Confirmar también el contenido recuperado para una aceptación completa |
| `failed` | Leer el código de error y corregir su causa antes de reintentar |
| `unknown` | Conciliar: el destino podría haber recibido la solicitud |

Los usuarios con escritura pueden solicitar reintentos de estados permitidos. **Conciliar resultado** comprueba un resultado incierto antes de volver a enviarlo. No uses repetidamente el botón como forma de acelerar una cola. Si el error persiste, conserva la identidad de operación y comunica el problema al operador.

## Configurar captura y acceso

En **Configuración → Proyectos y políticas**, un administrador crea el identificador y nombre del proyecto. El identificador acepta minúsculas, números, guiones y guiones bajos; debe ser estable. La captura empieza desactivada.

| Política | Uso |
|---|---|
| Desactivada (`off`) | No admitir nueva captura episódica |
| Resúmenes y aprendizajes (`summary`) | Captura acotada conforme a la política del servidor |
| Contenido completo (`full`) | Requiere consentimiento explícito adicional del cliente |

Activar la política permite recibir eventos; no instala capturadores en los clientes. La opción de conservar hechos y relaciones se aplica a nuevos eventos y no demuestra que se hayan reconstruido todos los anteriores. Cambiar la política no aprueba notas ni borra el contenido previo.

En **Claves para agentes**, crea una clave por integración con sus proyectos y permisos mínimos. Se muestra una sola vez. Guárdala en un fichero privado fuera del repositorio consumidor y configura el instalador con su ruta. Revocar una clave corta su acceso sin borrar la memoria que envió.

En **Usuarios**, crea accesos humanos con proyectos y permisos. La contraseña inicial debe cumplir la validación del formulario. Administración no es necesaria para consultar ni para que un agente publique en proyectos concretos.

| Permiso | Capacidad |
|---|---|
| `read` | Consultar los proyectos concedidos y sus fuentes |
| `write` | Capturar memoria admitida y gestionar sus operaciones autorizadas |
| `publish` | Publicar o retirar fuentes documentales |
| `validate` | Registrar validación; necesario para publicar fuentes validadas |
| `admin` | Administrar proyectos, políticas y accesos |

## Rutina recomendada para agentes y personas

Antes de empezar, selecciona el proyecto, busca decisiones previas y abre su evidencia. Prepara contexto sólo con lo que resulte útil para la tarea. Durante el trabajo, conserva referencias a las pruebas o incidencias relevantes. Al cerrar, guarda un resumen breve del resultado, un aprendizaje aplicable o una corrección concreta.

No envíes cada mensaje como una nota. Deduplica experiencias repetidas y versiona las correcciones. Revisa periódicamente elementos sin validar, errores de procesamiento y fuentes sustituidas. Publica en la capa documental únicamente el conocimiento que haya pasado la aprobación del proyecto.

## Preguntas y problemas frecuentes

| Síntoma | Comprobación |
|---|---|
| No aparece un proyecto | Cuenta y permisos, catálogo cargado, filtro de proyectos; pedir acceso al administrador |
| No aparece una categoría | Metadatos de los elementos del proyecto y actualización del catálogo |
| La búsqueda no encuentra un documento recibido | Trabajos, proyecto, capas, texto, categoría, retirada o versión vigente |
| Un contador no coincide con el mapa | Son totales diferentes; leer la sección de contadores |
| Una bolita no abre contenido | Comprobar si es una entidad sin referencia; usar evidencia o vista de lista |
| La captura está rechazada | Política del proyecto, tipo de evento y permiso de escritura |
| Publicación rechazada | Validación, evidencia, hash, versión y permisos `publish`/`validate` |
| Hay un timeout después del envío | Consultar recibo por ID antes de repetir |
| El mapa tarda o no renderiza | Reintentar carga, reducir ámbito, usar lista y revisar la operación/API |
| La sesión ha caducado | Volver a entrar; no pegar cookies o tokens en una incidencia |
| Una clave ya no funciona | Revocación, ruta del fichero, permisos y dirección configurada |

Para soporte comunica fecha, proyecto, acción, código de error e identificadores del elemento, recibo o trabajo. No incluyas el contenido completo si es sensible, claves, cookies ni contraseñas. Los procedimientos técnicos están en [operación](operations.md).

## Límites que debes conocer

El paquete instalador todavía no está publicado en npm. MCP aporta herramientas de memoria; la conexión básica no activa captura. Puedes añadir hooks y contexto mediante las opciones explícitas de [instalación](install.md). `summary` conserva metadatos técnicos y resúmenes explícitos, sin leer conversaciones para fabricarlos. La política `full` necesita consentimiento independiente en cliente y servidor. Las pruebas del proceso de hook y del protocolo no certifican la aceptación dentro de cada cliente real. La documentación describe el funcionamiento disponible, no garantiza igualdad completa con otros productos.

El contexto y los listados están acotados. Un mapa es una instantánea, no una exportación completa. La generación puede fallar o producir errores y conserva incertidumbre. Una comprobación de salud no prueba generación, persistencia ni recuperación. Para aceptar una instalación realiza el recorrido completo con datos de prueba autorizados.

## Fuentes de este manual

La interfaz descrita procede de [memory-portal.ts](../web/src/memory-portal.ts), sus peticiones de [memory-api.ts](../web/src/memory-api.ts), el mapa de [memory-map.ts](../web/src/memory-map.ts), los estados y límites de [models.py](../memory_platform/models.py) y las herramientas de [mcp.py](../memory_platform/mcp.py).
