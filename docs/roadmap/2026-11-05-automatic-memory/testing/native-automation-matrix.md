# Contexto y captura automática: Claude, Codex y OpenCode

La aceptación nativa está completada para lectura, contexto y captura técnica: Claude 0.1.6, Codex 0.1.5 y OpenCode 0.1.5; la prueba independiente de contexto de OpenCode conserva su runtime 0.1.4. Consulta el [cierre y sus límites](native-acceptance-closure.md). Las instrucciones siguientes permiten reproducir el ensayo; si ya activaste la captura, conserva las claves existentes en vez de repetir la activación. La paridad funcional completa sigue teniendo tareas pendientes.

## Alcance de esta ampliación

El helper `scripts/accept-native-clients.py` admite ahora `--enable-capture`, `--disable-capture`, `--run-context` y `--retire-context` para los tres clientes. Actúa sólo sobre sus carpetas de ensayo y el proyecto `custom-agents`. No modifica los proyectos de trabajo, EUIPO, modelos del servidor, puertos o credenciales existentes. No cambia el código del plugin custom-agents ni necesita reconstruir contenedores o publicar otro paquete npm.

La implementación y sus pruebas sintéticas no sustituyen la aceptación en cada cliente instalado. Las pruebas reales anteriores siguen siendo: lectura/contexto/captura técnica en Claude, lectura en Codex y lectura en OpenCode con Big Pickle. La ampliación de contexto/captura para estos dos últimos sigue pendiente de ejecución por el operador.

Validación de esta ampliación: **51/51 pruebas de scripts**, con transporte sintético y validación contra el esquema real de eventos de la API. Incluyen claves/políticas compartidas, exclusión de operaciones simultáneas, runtime y procedencia por cliente, marcador sin herramientas, rechazo de otra ejecución, creación/retirada con respuesta perdida, conservación de cambios ajenos y limpieza de claves propias. [Artefacto con hashes y lectura real del estado](native-automation-extension.json). La sesión del implementador se detuvo por permisos en el preflight privado; no creó claves de captura para Codex/OpenCode ni cambió sus ensayos. No es necesario desplegar contenedores para aplicar estos scripts.

## 1. Activar los dos ensayos pendientes

Cierra las sesiones nativas de ensayo antes de actualizar sus instalaciones. Desde la raíz del stack:

```powershell
python kairos/scripts/accept-native-clients.py --enable-capture codex
python kairos/scripts/accept-native-clients.py --enable-capture opencode
```

Cada comando debe devolver `capture_enabled`. Crea una clave **propia del cliente**, con `read/write` sólo en `custom-agents`, y configura `capture=summary`, `context=auto`. La clave original de lectura se conserva. Los archivos privados permanecen fuera de OneDrive y del producto. El preflight de escritura ocurre antes de crear claves o cambiar políticas.

Una operación local exclusiva impide activar/desactivar simultáneamente los clientes del mismo ensayo. La política conserva `temporal_projection`. Se guarda la política previa del primer cliente activo como base compartida: desactivar uno no apaga la captura de los demás. La última desactivación restaura esa base si la política actual todavía coincide con lo esperado. Una activación nueva, después de desactivar todos, toma una base nueva y conserva cambios externos realizados entre ensayos.

Si aparece `Capture activation already exists`, no repitas la creación de claves: inspecciona la activación o utiliza la desactivación de ese cliente para reconciliarla. Si el instalador detecta un propietario activo del runtime, cierra el cliente y permite que su dispatcher finalice por inactividad; no borres sus locks ni mates procesos por PID sin verificar. La activación conserva su diario para recuperación.

## 2. Revisar la confianza nativa de Codex

```powershell
python kairos/scripts/accept-native-clients.py --open codex
```

Dentro de Codex, abre `/hooks` y revisa las nuevas definiciones de Kairos que apuntan al runtime del ensayo. Aprueba su definición exacta y sal normalmente. La [documentación oficial de Codex](https://learn.chatgpt.com/docs/hooks) explica esta revisión por hash; el helper no edita la confianza ni emplea flags para omitirla. Cambiar hooks puede requerir otra aprobación aunque el MCP ya funcionara.

En OpenCode se conserva el adaptador local Kairos. El doble registro global de custom-agents ya se resolvió; no hay que reinstalarlo. Si deseas revisar visualmente los plugins, usa `--open opencode` y sal normalmente antes de las ejecuciones siguientes.

## 3. Ejecutar contexto automático y lectura

```powershell
python kairos/scripts/accept-native-clients.py --run-context codex
python kairos/scripts/accept-native-clients.py --run codex

python kairos/scripts/accept-native-clients.py --run-context opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --run opencode --model opencode/big-pickle

python kairos/scripts/accept-native-clients.py --collect
```

Cada ejecución nativa tiene un límite de 180 segundos. Espera a que termine; Ctrl+C se registra como cancelación, no como aceptación. `--model` sólo selecciona el modelo para ese comando de OpenCode; no cambia sus valores predeterminados. Big Pickle ya superó la lectura en este entorno; la disponibilidad del proveedor puede variar.

`--run-context` y `--run` conservan archivos privados separados. Así, una prueba de contexto sin herramientas no pisa la evidencia de lectura MCP. Puede repetirse `--collect` si falta por llegar un evento de cierre; recoger resultados no vuelve a llamar al modelo ni reenvía capturas.

## Cómo se prueba el contexto automático

El helper genera un marcador impredecible y lo guarda temporalmente en una nota sintética de `custom-agents`. Es una fuente de ensayo explícitamente identificada por título, categoría, etiquetas y URI `kairos-test://context/…`. La identidad administradora valida exclusivamente ese dato sintético con evidencia de su origen, para que participe en la misma prioridad de recuperación que las fuentes validadas. No se promueve ningún candidato real ni se modifica documentación aprobada.

El prompt de la prueba contiene una etiqueta pública de búsqueda y pide devolver el marcador recibido en el contexto inicial. **No contiene el sufijo del marcador.** El cliente debe responder sin llamar a herramientas, comandos, archivos o MCP. El recolector exige la coincidencia con el marcador privado de ese intento, la sesión nativa correcta y recibos de creación/retirada coincidentes. Si observa una herramienta, una respuesta inventada, otro intento o exit 0 sin marcador, deja la inyección sin aceptar. Sólo exporta el hash del marcador y metadatos; no exporta contenido del contexto ni conversaciones.

La nota sintética usa un evento de captura estructurada con `generate=false`. El servidor la trata como evento técnico: sus recibos deben tener `jobs=[]`; no se solicitan embeddings ni extracción de aprendizaje para ella. La prueba valida inyección y entrega de metadatos; no demuestra aprendizaje semántico generado de una tarea real.

Al terminar, incluso ante un error del cliente, el helper intenta retirar **únicamente su nota**, comprobando antes ID, versión, agente y payload original. La retirada es una nueva versión auditada, no un borrado de historial. Las notas y documentos ajenos se conservan.

## Cómo se prueba la captura

El recolector no necesita que el cliente imprima sus hooks. Obtiene el identificador de la sesión desde la salida nativa y contrasta notas vigentes, eventos inmutables y recibos del servidor. Exige la procedencia, runtime, versión, hashes de contenido y canónicos, fingerprint de captura y ausencia de trabajos inesperados.

| Cliente | Runtime esperado | Eventos mínimos en este ensayo |
| --- | --- | --- |
| Claude | `claude` | SessionStart, UserPromptSubmit, Stop, SessionEnd |
| Codex | `codex` | SessionStart, UserPromptSubmit, Stop, SessionEnd |
| OpenCode 2 | `opencode-v2` | SessionStart, Stop |

El adaptador actual de OpenCode 2 observa creación e inactividad de sesión; no se inventa un SessionEnd que no haya entregado. Se permiten otros eventos de ciclo de vida conocidos con contenido técnico válido. Las llamadas MCP no se capturan como contenido de herramientas. El servidor mantiene los resúmenes técnicos separados de los aprendizajes explícitos.

Contexto y captura se evalúan por separado: puede aceptarse persistencia aunque el modelo no devuelva el marcador. Cada prueba permanece asociada a su sesión y fecha; una ejecución previa a la activación no se utiliza para aceptar captura de la activación nueva.

## 4. Interpretar el informe

El informe está en `testing/native-client-acceptance.json`. Comprueba en cada cliente:

- `native_mcp_read_observed`: las llamadas projects/context realmente terminaron correctamente.
- `automatic_context_injection_accepted` y `context_verification`: prueba nativa sin herramientas o evidencia explícita de hooks aceptada.
- `automatic_capture_accepted` y `capture_verification`: persistencia y recuperación contrastadas desde el servidor.
- `native_hook_failures` y `native_errors`: incidencias que no se ocultan por obtener exit 0.
- `capture_modes_by_client`: activación individual; el campo antiguo capture_mode describe sólo Claude y se conserva por compatibilidad.

La aceptación global continúa abierta mientras existan criterios o incidencias pendientes; el helper no cierra el ledger por su cuenta. La cancelación de Stop de Claude sigue documentada aunque su evento se persistiera.

## 5. Recuperar y desactivar

Si se interrumpe la retirada de un marcador:

```powershell
python kairos/scripts/accept-native-clients.py --retire-context codex
# O --retire-context opencode, según el ensayo afectado.
python kairos/scripts/accept-native-clients.py --collect
```

Antes de cada escritura remota se conserva un diario privado con UUID y fecha. Si se pierde la respuesta de creación, la recuperación consulta el recibo; si aún no existe, reconcilia **el mismo evento exacto**, de manera idempotente, antes de retirarlo. Esto evita un marcador huérfano que pudiera confirmarse tarde. Si se pierde la respuesta de retirada, consulta su UUID y no vuelve a ejecutar el cliente. No genera nuevas identidades para ocultar un resultado incierto.

Un error de permisos o API no disponible deja recuperación pendiente. Si la nota fue modificada por otro actor, no se retira ni se sobrescribe: requiere reconciliación explícita. No se declara contexto aceptado si la retirada no está verificada. La paginación del recolector está acotada a 1.000 notas/eventos por consulta; alcanzar el límite deja el criterio pendiente.

Para apagar un ensayo conservando las memorias técnicas ya entregadas:

```powershell
python kairos/scripts/accept-native-clients.py --disable-capture codex
python kairos/scripts/accept-native-clients.py --disable-capture opencode
```

Estas desactivaciones no apagan Claude mientras su ensayo siga activo. Si hay un marcador pendiente, utiliza también `--retire-context` para retirarlo. `--cleanup` reconcilia los marcadores propios, desactiva los tres ensayos y revoca sólo sus claves; conserva memorias, fuentes, volúmenes, logs privados y credenciales ajenas. No lo ejecutes si quieres mantener activa la captura de ensayo de Claude.
