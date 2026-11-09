# Conectar un cliente mediante MCP

Última actualización: 2026-11-05.

## Requisitos

Necesitas Node `>=20.12.0`, un proyecto consumidor existente, una dirección de Kairos accesible, un proyecto remoto autorizado y una clave con sus permisos. Un administrador crea el proyecto y la clave desde el panel. Si vas a capturar memoria, también debe activar una política compatible.

El paquete configura Claude Code, Codex u OpenCode. No configura aplicaciones de escritorio distintas aunque compartan marca con un cliente. No cambia sus decisiones de confianza o aprobación. No necesita Python ni acceso al disco del servidor.

La dirección del instalador es la base, por ejemplo `http://127.0.0.1:5173` en local o `https://memoria.example.org` en remoto. No añadas `/app/`, `/v1` ni `/mcp/`; el puente construye la ruta MCP. El acceso remoto exige HTTPS. El HTTP local sólo está permitido para loopback.

Guarda la clave sin prefijo `Bearer`, comillas ni JSON en un fichero privado externo al repositorio consumidor, por ejemplo `C:/Private/kairos-agent.key`. El fichero debe ser legible únicamente por el usuario del cliente y los administradores que correspondan. No pegues su valor en una línea de comandos.

## Distribución disponible

El paquete propio se llama `@daycry/kairos`, versión `0.2.0`. Su publicación en npm está pendiente. Por tanto, no se presenta `npx @daycry/kairos` como una instalación pública ya disponible. Usa el archivo local preparado en `packages/kairos-cli/artifacts/daycry-kairos-0.2.0.tgz`.

Desde la raíz de este repositorio, comprueba su versión:

```powershell
npx --offline --yes --package ./packages/kairos-cli/artifacts/daycry-kairos-0.2.0.tgz kairos --version
```

`--offline` evita consultar el registro. El archivo debe existir; esta opción no lo descarga ni sustituye la entrega del tarball. Las pruebas del paquete verifican su instalación local; la publicación y disponibilidad pública requieren otra entrega explícita.

## Previsualizar e instalar

Ejemplo para los tres clientes de un proyecto consumidor:

```powershell
npx --offline --yes --package ./packages/kairos-cli/artifacts/daycry-kairos-0.2.0.tgz kairos install --client all --root C:/laragon/www/mi-proyecto --url http://127.0.0.1:5173 --project mi-proyecto --key-file C:/Private/kairos-agent.key --opencode-version 2 --dry-run
```

Revisa el destino, el proyecto remoto y los archivos previstos. Para aplicar, sustituye el último `--dry-run` por `--yes`. El primer `--yes`, antes de `--package`, pertenece a npx; el último confirma al instalador Kairos. `--dry-run` prevalece y no modifica archivos ni llama al servidor.

Puedes instalar un único cliente cambiando `all` por `claude`, `codex` u `opencode`. `--root` es la carpeta del proyecto consumidor, no la del servidor. Para un OpenCode nuevo indica su formato con `--opencode-version 1` o `2`. En una configuración existente, el instalador puede inferir el formato cuando es inequívoco.

En una terminal interactiva, `kairos install` pregunta los datos que falten y muestra la vista previa. Sin terminal interactiva y sin confirmación permanece en previsualización. Un conflicto de entrada Kairos requiere una sustitución explícita con `--replace` y conserva copia previa; no fuerces conflictos sin revisar la configuración existente.

## Archivos que se generan

| Cliente | Archivo | Entrada |
|---|---|---|
| Claude Code | `.mcp.json` | `mcpServers.kairos` |
| Codex | `.codex/config.toml` | `[mcp_servers.kairos]` |
| OpenCode 1 | `opencode.json` | `mcp.kairos` |
| OpenCode 2 | `opencode.json` | `mcp.servers.kairos` |

La configuración ejecuta Node con una copia estable del puente en `.kairos/runtime/0.2.0/`. No depende de que la caché temporal de npx siga existiendo. `.kairos/installation.json` guarda la dirección, proyecto, ruta de clave y hashes del runtime; no guarda el secreto.

Las copias están en `.kairos/backups/`. Pueden contener configuraciones previas sensibles: protégelas. El instalador conserva entradas de otros MCP y ajustes ajenos. Si encuentra JSONC o una estructura TOML que no puede actualizar de forma segura, rechaza el cambio antes de escribir; adapta la configuración explícitamente y vuelve a previsualizar.

## Comprobar la conexión

Después de instalar puedes ejecutar el runtime persistente desde el proyecto consumidor:

```powershell
node .kairos/runtime/0.2.0/bin/kairos.mjs doctor --root .
node .kairos/runtime/0.2.0/bin/kairos.mjs doctor --root . --online
```

La primera comprobación valida archivos, hashes y configuración local. La segunda inicializa MCP y consulta herramientas y proyectos. Es de lectura: no crea memorias, no publica documentos y no prueba al trabajador de generación. Un estado `ready` significa que esas comprobaciones terminaron; no certifica la aceptación completa de tu cliente.

Reabre el cliente si necesita recargar sus servidores. Revisa que aparece `kairos`, autoriza su conexión conforme a las reglas del cliente y pide listar proyectos. Después haz una búsqueda sobre un proyecto autorizado y abre un detalle. Para comprobar escritura, usa sólo un proyecto de prueba con captura permitida, registra un resumen autorizado, espera `event_status` y recupéralo. El recorrido está descrito en [integración](integration.md).

## Recuperar una instalación local

```powershell
node .kairos/runtime/0.2.0/bin/kairos.mjs recover --root . --dry-run
node .kairos/runtime/0.2.0/bin/kairos.mjs recover --root . --yes
```

La recuperación comprueba hashes y destinos. Si alguien editó el archivo después de la instalación, puede rechazar la restauración para no pisar ese trabajo. Resuelve ese conflicto revisando la copia, no borrando toda la configuración de clientes.

`recover --unlock` sirve exclusivamente para un bloqueo de instalación cuyo proceso ya no está activo. No elimina automáticamente bloqueos corruptos o de propietario desconocido. No tiene relación con bloqueos de la base de datos ni con el procesamiento central.

## Captura y contexto automáticos opcionales

La conexión MCP básica continúa sin captura. Para instalar también el ciclo de vida añade `--capture summary --context auto` a la vista previa. Para actualizar una instalación existente, selecciona todos sus clientes y añade `--replace`. El servidor debe permitir captura en ese proyecto y la clave debe tener `read` y `write`; el instalador no cambia esa política.

```powershell
npx --offline --yes --package ./packages/kairos-cli/artifacts/daycry-kairos-0.2.0.tgz kairos install --client all --root C:/laragon/www/mi-proyecto --url http://127.0.0.1:5173 --project mi-proyecto --key-file C:/Private/kairos-agent.key --opencode-version 2 --capture summary --context auto --dry-run
```

Sustituye el último `--dry-run` por `--yes` después de revisar. La política efectiva es la más restrictiva entre cliente y servidor.

| Opción | Qué conserva o consulta |
|---|---|
| `--capture off` | Ningún evento nuevo; valor predeterminado |
| `--capture summary` | Metadatos técnicos de herramientas y sesiones; resúmenes sólo cuando el emisor proporciona `summary` explícitamente |
| `--capture full` | También entradas/resultados de herramientas admitidas, prompts y respuesta final cuando el evento nativo los proporciona; exige `full` en servidor y cliente |
| `--context off` | No inyecta contexto automáticamente; valor predeterminado |
| `--context auto` | Recupera hasta cinco fuentes actuales del proyecto, sin llamada al modelo ni caché local de contexto |

`summary` no transcribe conversaciones ni convierte una respuesta final en resumen por su cuenta. Un evento técnico no solicita extracción LLM ni embedding, incluso con embeddings activados en el servidor. Un resumen explícito, o una respuesta final admitida en `full`, solicita generación en el trabajador; los aprendizajes derivados pueden generar embeddings y siguen sin validación humana automática. Las notas manuales y documentos mantienen su indexación habitual. Los adaptadores de OpenCode no leen el historial para fabricar un resumen al recibir `session.idle`. Los campos de credenciales reconocidos, asignaciones prefijadas como `DB_PASSWORD`, JSON anidado/serializado y bloques `<private>` se sanean antes de persistir. Esto no garantiza reconocer cualquier secreto arbitrario. Revisa qué herramientas puede usar un proyecto antes de autorizar `full`.

Los hooks se fusionan en `.claude/settings.json` y `.codex/hooks.json`. OpenCode 1 carga `.opencode/plugins/kairos-memory.js`; OpenCode 2 carga `.opencode/plugins/kairos-memory/index.js`. Conserva la revisión de confianza nativa: en Codex revisa `/hooks`; Kairos no aprueba hooks ni modifica el almacén de confianza. Los hooks locales de Codex requieren orquestación local. Si existen hooks inline en `.codex/config.toml`, la instalación se detiene para una fusión explícita. No borres esa configuración para forzarla.

Para validar el ciclo completo en este checkout hay un ensayo separado de proyectos de trabajo: [contexto y captura en los tres clientes](roadmap/2026-11-05-automatic-memory/testing/native-automation-matrix.md). Prueba un marcador temporal mediante el contexto inicial sin permitir herramientas, y contrasta la captura con eventos y recibos persistidos. El helper crea claves limitadas, conserva diarios privados y retira sólo su marcador sintético. Un doctor ready, una respuesta del modelo o exit 0 no sustituyen esa aceptación.

La cola se guarda fuera del proyecto: por defecto en `%LOCALAPPDATA%/Kairos/memory/<binding>` en Windows y `~/.local/state/Kairos/memory/<binding>` en otros sistemas. Puedes elegir una base privada externa con `--state-dir`. No la sitúes en una carpeta compartida o sincronizada; protégela con permisos del sistema. La vista previa no crea la cola. Cada combinación de carpeta, servidor, proyecto y fichero de clave tiene una cola diferente; cambiar esa combinación no migra silenciosamente entregas antiguas.

Un proceso local Node recibe IPC autenticado exclusivamente en `127.0.0.1`, mantiene la cola y habla con MCP. El hook no llama directamente al servidor ni espera al modelo. Sí espera una respuesta IPC acotada, que puede incluir comprobaciones remotas de permisos y contexto; una red lenta puede consumir ese presupuesto. El dispatcher limita el tiempo de red y termina después de quince minutos sin actividad de hooks. Las entregas admitidas sobreviven en disco y se reanudan al siguiente evento o con `sync`:

```powershell
node .kairos/runtime/0.2.0/bin/kairos.mjs sync --root .
node .kairos/runtime/0.2.0/bin/kairos.mjs status --root .
```

`sync` arranca el dispatcher si falta y solicita procesamiento en segundo plano; su respuesta no significa que toda la cola haya terminado. `status` consulta un dispatcher activo y muestra contadores y los veinte recibos locales más recientes, sin cuerpos ni claves. Si el dispatcher ya terminó por inactividad, ejecuta `sync` antes.

| Estado | Interpretación |
|---|---|
| `pending` | Espera envío |
| `unknown` | Una entrega incierta necesita conciliación |
| `accepted` | Tiene recibo; puede esperar trabajos centrales |
| `complete` | Se verificaron todos los trabajos del recibo |
| `retired` | La versión fue sustituida |
| `failed` | Se alcanzó el límite de intentos o falló un trabajo central; queda fuera de la rotación automática |
| `processing_failed` | Contador de recibos aceptados con trabajos fallidos; consulta sus IDs con `event_status` |

La cola admite 200 cuerpos pendientes, 10.000 registros y 8 MiB. Cuando necesita espacio, compacta únicamente recibos terminales sin cuerpo. Nunca expulsa entregas inciertas, fallidas con contenido o pendientes. Sin espacio recuperable, rechaza la admisión con diagnóstico. Los envíos se limitan a cinco intentos por evento; la espera por registro permite que avance el resto de la cola. Se concilia primero con `event_status(event_id, project_id)` y sólo se repite el evento original tras ausencia confirmada. Un fallo de permisos o red nunca cuenta como ausencia. Tras compactar un recibo, otra invocación del mismo evento exige verificar su `capture_hash` remoto antes de reutilizarlo. Un recibo antiguo sin ese hash requiere revisión; no provoca un reenvío ciego.

La outbox v2 separa cuerpos privados en `sources/` del journal de metadatos. Confirma el recibo en disco antes de retirar el cuerpo; recupera ese orden tras una caída. Los checkpoints periódicos evitan reescribir toda la cola en cada aceptación. Una cola v1 se migra conservando el evento, fecha e identidad originales. No edites esos archivos manualmente.

Si la política baja de `full` a `summary`, los cuerpos completos pendientes no se envían y esperan otra comprobación. Una indisponibilidad anterior a comprobar permisos impide admitir contenido nuevo. No existe captura offline con permisos supuestos ni inyección desde una copia de contexto tras una revocación. Si el cliente no entrega un identificador estable de evento, se asigna uno por invocación; las retransmisiones de una admisión conservan ese identificador, pero dos invocaciones nativas indistinguibles no se deduplican por contenido.

Para resolver `failed`, consulta primero `event_status` y el error del trabajo. Estas operaciones locales exigen el UUID original y confirmación explícita:

```powershell
node .kairos/runtime/0.2.0/bin/kairos.mjs queue-retry --root . --event-id UUID --yes
node .kairos/runtime/0.2.0/bin/kairos.mjs queue-retire --root . --event-id UUID --yes
```

`queue-retry` vuelve a conciliar: un evento ya aceptado sólo consulta su recibo, sin republicar el cuerpo ni relanzar automáticamente un trabajo central fallido. `queue-retire` admite `pending`, `unknown` y `failed`; abandona la entrega local y retira su cuerpo. Funciona también con la automatización apagada y sin dispatcher: adquiere el bloqueo exclusivo de la cola. No borra memoria del servidor y una entrega `unknown` puede haberse aceptado allí. Conserva su identificador para investigar. No cambia el consentimiento ni lo reactiva.

Al retirar consentimiento, los cuerpos admitidos anteriormente se conservan hasta conciliarlos o retirarlos explícitamente. Si vuelves a permitir `full`, los pendientes compatibles podrán enviarse; revisa sus IDs y usa `queue-retire` antes de reactivar si ya no deseas entregarlos. Una actualización de privacidad no reescribe los eventos pendientes: deben conservar su identidad y contenido para conciliación.

Si falta un cuerpo o falla su hash/JSON, sólo esa fila pasa a `failed` con `capture_source_corrupt`. El contexto y otras entregas pueden continuar. No se reconstruye ni reenvía contenido inventado; `queue-retry` exige reparar el origen, o puedes retirar esa fila. Un journal o metadatos globales corruptos siguen deteniendo la cola para proteger identidades y autorización.

El contexto automático busca términos alternativos (`match_mode=any`), excluye `agent-activity` y limita el resultado a cinco fuentes y 5.000 caracteres. La búsqueda normal conserva `match_mode=all`. Las fuentes son texto no confiable, con procedencia; el cliente no debe convertirlas en instrucciones. Esta delimitación no garantiza inmunidad a instrucciones maliciosas dentro de un documento.

## Actualizar una instalación anterior

Actualiza primero el servidor y verifica el contrato con `doctor --online`. Después cierra las sesiones de agentes afectadas y deja terminar el dispatcher anterior (quince minutos sin actividad). Comprueba que ya no existe un proceso propietario activo antes de migrar una cola. No ejecutes versiones de dispatcher distintas sobre la misma partición.

La versión 0.2.0 admite actualizar desde las versiones 0.1.0 a 0.1.6 con `install --replace`, seleccionando todos los clientes gestionados. La previsualización y la aplicación comprueban que el dispatcher anterior esté detenido; un propietario activo produce `dispatcher_upgrade_requires_stop` antes de cambiar la configuración. Mantén los clientes cerrados durante toda la operación. Previsualiza y aplica con la misma URL, proyecto, fichero de clave y carpeta privada. Conserva el runtime anterior para recuperación. Las versiones desconocidas se rechazan. El ejecutable Node físico elegido al instalar queda registrado; OpenCode puede usar su propio runtime sin cambiar ese Node. Si cambia la ubicación de Node, repite la instalación explícita.

El IPC v2 vincula el endpoint a la versión del runtime. `doctor` informa `version_mismatch` y los hooks rechazan `dispatcher_version_mismatch` sin contactar ni mantener activo al daemon antiguo. Espera su cierre con los clientes detenidos; no retires su lock ni lances versiones simultáneas.

Las peticiones y respuestas locales usan sobres autenticados AES-256-GCM, con claves separadas por dirección, IV aleatorio y vínculo a versión, proyecto/conexión, ruta e identidad fresca de petición. El secreto privado del endpoint nunca se envía al puerto. Un proceso ajeno que reutilice un puerto obsoleto no recibe el prompt en claro ni puede aportar contexto válido. Esto protege el canal; los cuerpos pendientes en disco requieren los permisos privados indicados anteriormente. No protege frente a otro proceso que ya pueda leer el secreto del mismo usuario. No hay compatibilidad automática con IPC en texto plano.

Un lock activo se respeta. La recuperación de un lock obsoleto se serializa con `queue.recovery.lock`. Si el propietario cae mientras mantiene esa guarda, se detiene la recuperación automática. Antes de cualquier intervención, cierra clientes y dispatchers, comprueba sus PID y realiza una copia privada de la partición; retira únicamente la guarda cuya ausencia de propietario hayas comprobado. No borres `queue.json`, `queue.jsonl` ni `sources/`, ni retires un lock mientras haya un proceso activo. Ante duda, conserva el estado y pide diagnóstico.

Para desactivar, previsualiza otra instalación con `--capture off --context off --replace` y todos los clientes gestionados. Se retiran los handlers propios y el adaptador propio queda inactivo; se conservan ajustes ajenos y recibos. Las pruebas de contrato y un proceso real de hook con PostgreSQL no sustituyen la aceptación dentro de cada versión de cliente.

Referencias de integración: [hooks de Codex](https://learn.chatgpt.com/docs/hooks), [hooks de Claude Code](https://code.claude.com/docs/en/hooks), [plugins de OpenCode 1](https://opencode.ai/docs/plugins/) y [plugins de OpenCode 2](https://dev.opencode.ai/v2/docs/build/plugins/server/).

## Límites del instalador

La navegación local de código es una opción independiente de la captura: `--code-analysis on` añade herramientas locales al proxy y fija su raíz. El valor predeterminado es `off`. Cambiarlo requiere `--replace` y todos los clientes gestionados. No se explora ni publica todo el repositorio. La entrega actual informa expresamente de sus límites léxicos: [análisis local](code-analysis.md). Para revisar el artefacto y distinguir instalación local de disponibilidad pública, consulta [entrega CLI](release-cli.md).

No crea usuarios, claves ni proyectos; no arranca Docker ni los clientes y no lee transcripciones. La instalación básica prepara MCP; los hooks requieren las opciones anteriores. La integración que decide cuándo llamar `remember` debe respetar autorización, privacidad e identidades estables. El paquete no se ha publicado todavía en npm.

Fuente: [guía del paquete](../packages/kairos-cli/README.md), [manifiesto](../packages/kairos-cli/package.json) y [entrada ejecutable](../packages/kairos-cli/bin/kairos.mjs).
