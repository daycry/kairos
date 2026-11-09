# Kairos CLI

Instalador Node y puente MCP local para **Claude Code, Codex CLI y OpenCode**. El cliente inicia un proceso stdio pequeño; éste conecta con el único MCP autenticado de Kairos. La extracción, los índices y la memoria permanecen en el servidor.

Requiere **Node.js 20.12 o posterior**. El paquete no tiene dependencias npm, no requiere Python y no ejecuta scripts de instalación de terceros.

## Estado de distribución

Nombre previsto: `@daycry/kairos`, versión `0.2.0`, ejecutable `kairos`. **No está publicado en npm**. Un nombre similar en el registro no acredita que sea este proyecto. Esta entrega se prueba mediante su tarball local; publicar requiere una acción autorizada independiente.

Una vez descargado el tarball, puede ejecutarse sin consultar el registro:

```powershell
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos --version
```

La forma `npx @daycry/kairos install` sólo estará disponible cuando el paquete se publique y se compruebe esa distribución.

## Preparación

1. En Kairos, abrir **Configuración → Claves para agentes**.
2. Emitir una clave dedicada y limitarla a los proyectos necesarios. `read` permite consultar; `write` permite guardar memoria; `publish` y `validate` permiten publicar fuentes aprobadas. No conceder `admin` para estos flujos.
3. Guardar sólo el valor de la clave en un archivo privado **fuera del proyecto**, por ejemplo `C:\Private\kairos-agent.key`. No usar la contraseña de `admin` ni el archivo `bootstrap_password`.
4. Anotar la URL base y el ID del proyecto. La URL local es `http://127.0.0.1:5173`; en otro ordenador se necesita la URL HTTPS real del servidor.
5. Para capturar memoria, habilitar su política de proyecto en el servidor. La instalación básica no activa captura. Las opciones explícitas `--capture summary|full --context auto` añaden hooks o adaptadores nativos; el instalador no cambia una política remota `off`.

## Instalar

Con terminal interactivo, el comando pregunta por los parámetros que falten y muestra una vista previa antes de aplicar:

```powershell
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos install
```

Ejemplo no interactivo para los tres clientes, inicialmente sólo vista previa:

```powershell
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos install --client all --root C:/laragon/www/mi-proyecto --url http://127.0.0.1:5173 --project mi-proyecto --key-file C:/Private/kairos-agent.key --opencode-version 2 --dry-run
```

Después de revisar el resultado, sustituir `--dry-run` por **`--yes`** para aplicar. El `--yes` anterior a `--package` pertenece a npx; el que va después de `install` pertenece al instalador de Kairos.

Opciones:

| Opción | Uso |
| --- | --- |
| `--client claude\|codex\|opencode\|all` | Clientes que se configurarán. Claude significa Claude **Code**, no Claude Desktop. |
| `--root DIRECTORIO` | Proyecto consumidor existente; por defecto la carpeta actual. |
| `--url URL` | URL base; no añadir `/app/`, `/v1` ni `/mcp/`. Se exige HTTPS fuera de loopback. |
| `--project ID` | ID de proyecto existente y autorizado. |
| `--key-file ARCHIVO` | Archivo privado externo al proyecto. Su contenido no se inserta en la configuración. |
| `--opencode-version 1\|2` | Generación de configuración. Obligatoria para OpenCode nuevo; una configuración existente permite inferirla. |
| `--dry-run` | Vista previa sin mutaciones ni red; tiene prioridad sobre `--yes`. |
| `--yes` | Aplicar el plan sin otra pregunta. |
| `--replace` | Autorizar la sustitución de una entrada o runtime Kairos en conflicto, conservando copia previa. |

Sin terminal interactivo, omitir `--yes` conserva el modo de vista previa. El instalador no conecta con el servidor, no crea proyectos o claves y no inicia los clientes.

## Qué se escribe

| Cliente | Archivo | Entrada |
| --- | --- | --- |
| Claude Code | `.mcp.json` | `mcpServers.kairos`, transporte `stdio` |
| Codex | `.codex/config.toml` | Tabla `[mcp_servers.kairos]`, `command` y `args` |
| OpenCode 1 | `opencode.json` | `mcp.kairos`, tipo `local`, `enabled: true` |
| OpenCode 2 | `opencode.json` | `mcp.servers.kairos`, tipo `local`, `disabled: false` |

Cada entrada apunta al ejecutable Node utilizado para instalar y a una copia estable de este paquete en `.kairos/runtime/0.2.0/`. No depende de que npx conserve su caché ni de exportar variables de entorno antes de abrir el cliente. El proxy lee el archivo privado al realizar solicitudes y envía la clave al servidor mediante `Authorization: Bearer`.

`.kairos/installation.json` contiene la URL, el ID de proyecto, la ruta del archivo privado y los hashes del runtime; no la clave. Las copias de configuración se conservan en `.kairos/backups/`. `.kairos/.gitignore` excluye esos archivos de Git. Las copias pueden contener otros ajustes sensibles que ya existieran: proteger la carpeta mediante los permisos del sistema y evitar sincronizarla o publicarla.

Se preservan otros servidores MCP y ajustes. La edición TOML sólo administra una tabla convencional de Kairos; conserva los bytes ajenos. JSONC y construcciones TOML que no se puedan editar con seguridad se rechazan antes de modificar destinos. No se eliminan carpetas ni archivos ajenos.

Los clientes pueden requerir aprobar el servidor o confiar en el proyecto. El instalador no desactiva esas comprobaciones ni modifica sus políticas de aprobación.

## Comprobar

```powershell
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos doctor --root C:/laragon/www/mi-proyecto
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos doctor --root C:/laragon/www/mi-proyecto --online
```

La primera comprobación es local. `--online` añade únicamente `initialize`, `notifications/initialized`, `tools/list` y una consulta `projects`. Exige el conjunto mínimo de once herramientas de Kairos; admite herramientas adicionales. Un servidor anterior puede aparecer como `degraded` con `missing_tools`. No se guarda ninguna nota ni se activa captura para obtener un resultado verde.

`ready` comprueba transporte, catálogo y autorización del proyecto. No prueba todas las escrituras, la extracción, el worker, la indexación ni la conexión nativa dentro de los tres programas. Después de configurar, abrir el cliente y revisar su inventario MCP; probar las escrituras únicamente en un proyecto autorizado para ello.

## Recuperar una instalación interrumpida

El instalador valida todos los destinos antes de escribir. Cada archivo se sustituye de forma atómica y el lote mantiene un diario. El lote completo no se presenta como una transacción multiarchivo: si falla una escritura pueden quedar cambios parciales, señalados por `partial_installation_recovery_required`.

```powershell
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos recover --root C:/laragon/www/mi-proyecto --dry-run
npx --offline --yes --package ./daycry-kairos-0.2.0.tgz kairos recover --root C:/laragon/www/mi-proyecto --yes
```

La recuperación valida hashes, copias y destinos antes de mutar. Si otro proceso o el usuario modificaron un destino, se rechaza la recuperación automática para conservar esa modificación. No borrar manualmente el diario ni las copias para forzar una nueva instalación.

Si un proceso terminó abruptamente y dejó `install.lock`, añadir `--unlock` únicamente a una recuperación explícita. Se comprueba que el PID registrado no esté activo. Los locks son cooperativos; los permisos del sistema siguen siendo necesarios frente a procesos que no los respeten. Un lock inválido o cuyo propietario no se pueda descartar no se elimina automáticamente.

## Puente MCP

El subcomando `mcp` es el proceso iniciado por los clientes:

```text
node .kairos/runtime/0.2.0/bin/kairos.mjs mcp --url URL_BASE --key-file ARCHIVO_PRIVADO
```

Su entrada y salida usan mensajes JSON-RPC 2.0 delimitados por líneas. `stdout` contiene exclusivamente el protocolo; los diagnósticos saneados van a `stderr`. No se inventan IDs para notificaciones ni se convierten errores HTTP en respuestas de éxito. Las llamadas conservan IDs y contenido; los resultados inciertos deben reconciliarse con las herramientas de Kairos antes de reintentarlos.

El destino HTTP se limita a `/mcp/` bajo la URL configurada. No sigue redirecciones. El puente aplica límites de entrada, respuesta, concurrencia y tiempo y admite respuestas JSON o SSE del servidor stateless actual. La automatización opcional utiliza un dispatcher propio separado del proxy stdio.

## Automatización opcional

Añade `--capture summary --context auto` a `install --dry-run`. Para actualizar una instalación, selecciona todos sus clientes y usa `--replace`. El servidor necesita el contrato que incluye `capture_policy` y la conciliación `event_status(event_id, project_id)`, además de permisos vigentes. La política más restrictiva entre cliente y servidor prevalece. `summary` guarda metadatos técnicos y resúmenes explícitos; no fabrica resúmenes leyendo transcripciones. `full` añade entradas/resultados admitidos y mensajes nativos disponibles, con consentimiento independiente del servidor.

Se fusionan handlers en `.claude/settings.json` y `.codex/hooks.json`, o un adaptador propio en `.opencode/plugins/`. Se conservan ajustes ajenos y la revisión de confianza del cliente. Los hooks inline de Codex requieren una fusión manual explícita. La orquestación cloud de Codex no ejecuta estos hooks locales. Los adaptadores V1/V2 comprueban el directorio de cada sesión antes de capturar o inyectar contexto.

La outbox privada se sitúa fuera del proyecto, por defecto en `%LOCALAPPDATA%/Kairos/memory/` o `~/.local/state/Kairos/memory/`; `--state-dir` permite elegir otra base privada. No sincronizarla ni compartirla. Conserva UUID y fecha originales, confirma permisos antes de persistir y concilia entregas inciertas antes de repetir el evento exacto. El cuerpo local se elimina tras aceptación. Los datos nuevos sin autorización comprobable se omiten con diagnóstico. El contexto usa hasta cinco fuentes del proyecto, sin respaldo de caché ante errores.

`kairos sync --root PROYECTO` arranca el dispatcher y solicita envío en segundo plano. `kairos status --root PROYECTO` consulta un dispatcher activo: `pending` espera envío, `unknown` conciliación, `accepted` trabajos centrales, `complete` comprobación terminada, `retired` sustitución y `failed` intervención tras error o agotamiento de intentos. Muestra recibos recientes sin cuerpos. `queue-retry --event-id UUID --yes` vuelve a conciliar el mismo evento; `queue-retire --event-id UUID --yes` lo abandona localmente sin borrar memoria remota. Ninguna operación vuelve a publicar una fuente ya aceptada ni relanza por sí sola trabajos centrales fallidos.

Límites: 200 cuerpos, 10.000 registros y 8 MiB; cinco envíos por evento, espera por registro y hasta sesenta segundos ante fallos de transporte; inactividad del dispatcher de quince minutos. La outbox v2 separa cuerpos de su journal de metadatos y compacta sólo recibos terminales sin cuerpo. Las identidades compactadas se comprueban contra `capture_hash` remoto antes de reutilizarse. Una cola sin espacio recuperable rechaza nuevas admisiones sin descartar trabajo pendiente. Cambiar la conexión crea otra partición; no migra envíos inciertos.

Actualiza primero el servidor. Para pasar de 0.1.0, 0.1.1 o 0.1.2 a 0.2.0, cierra clientes, deja terminar el dispatcher anterior y usa `--replace` para todos los clientes gestionados. La instalación rechaza un propietario activo antes de cambiar archivos. Nunca compartas una partición entre versiones simultáneas. Se conserva el runtime anterior y se migra la cola sin cambiar UUID, fecha ni contenido. El ejecutable Node registrado se usa aunque OpenCode hospede el plugin en otro runtime. No borres locks activos; la recuperación de una guarda obsoleta requiere comprobar ausencia de propietarios y una copia privada. El procedimiento completo está en [instalación](../../docs/install.md).

IPC v2 autentica y cifra cada petición y respuesta con AES-256-GCM; el secreto del endpoint no se transmite al listener. Los endpoints de otra versión se rechazan sin contacto y `doctor` los diagnostica. Los cuerpos en disco siguen necesitando permisos privados. Un cuerpo ausente, inválido o sobredimensionado queda aislado como `failed`; contexto y demás entregas continúan. `queue-retire` funciona también sin dispatcher y con la captura apagada para `pending`, `unknown` y `failed`. Retirar localmente una entrega incierta no confirma que el servidor la haya borrado.

Los eventos técnicos automáticos no solicitan embeddings; los aprendizajes derivados, notas manuales y documentos sí pueden hacerlo. El contexto automático combina términos alternativos y excluye `agent-activity`, con cinco fuentes y 5.000 caracteres como máximo. Los hooks esperan IPC acotado, que puede incluir comprobaciones remotas; no esperan un modelo. Para desactivar, instala `--capture off --context off --replace` para todos los clientes gestionados. Esto conserva recibos y configuración ajena. La aceptación en cada cliente real es una comprobación adicional a las pruebas de protocolo y del proceso de hook.

## Desarrollo y entrega local

La versión 0.2.0 añade navegación local opcional mediante `--code-analysis on`; permanece apagada por defecto. Las herramientas `code_outline`, `code_smart_search` y `code_unfold` sólo leen archivos elegidos explícitamente y no los publican en el servidor. Esta entrega identifica su analizador como léxico; no acredita paridad AST. Límites, ejemplos y exclusiones: [análisis local](../../docs/code-analysis.md). Preparación verificable y publicación: [entrega CLI](../../docs/release-cli.md).

```powershell
npm test
npm pack --ignore-scripts --offline --pack-destination ./artifacts
```

En un entorno que bloquee el spawn del runner de Node, ejecutar `node tests/run.mjs` recorre las mismas regresiones en proceso. El paquete distribuido contiene sólo `bin/`, `lib/`, README, licencia y `package.json`; no incluye fixtures, claves, configuración local ni `node_modules`.

El código es propio de Kairos. Instalar el proxy básico no activa la automatización ni certifica todos los recorridos de cada versión de cliente.
