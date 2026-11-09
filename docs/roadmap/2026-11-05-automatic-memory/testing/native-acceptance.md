# Prueba dentro de clientes nativos

Current status, 2026-11-06: native reads, automatic context and technical summary capture are accepted in all three clients. See [the acceptance closure and its limits](native-acceptance-closure.md). The preparation notes below describe the historical starting state; they are not the current result.

Preparación del 2026-11-05. El servidor está desplegado y verificado; este procedimiento prueba clientes reales, sin modificar los proyectos de trabajo ni activar captura en ellos. El preparador y recolector están en `scripts/accept-native-clients.py`.

## Alcance y estado actual

Se ha observado Claude Code 2.1.311, Codex CLI 0.166.0 y el paquete instalado OpenCode 2.0.12. Este último no ha podido iniciar desde la sesión del implementador: Windows deniega abrir su log de usuario. La copia local del repositorio custom-agents declara 3.1.0; la instalación activa de Claude declara **3.2.1**, en su caché de plugins. Son ubicaciones diferentes. Codex tiene custom-agents habilitado en su configuración. No se ha encontrado un adaptador específico de Kairos en los scripts/skills/documentación del plugin examinado; disponer de las tools MCP y migrar los workflows propios del plugin son comprobaciones diferentes.

El script prepara tres carpetas nuevas dentro de `.private/native-acceptance/<run>/`. Sólo contienen un documento sintético y los archivos del instalador; no leen el repositorio de EUIPO, conversaciones existentes ni candidatos. Una clave nueva de **sólo lectura** se restringe a `custom-agents`; no reemplaza claves de trabajo ni cambia políticas, modelos, puertos o credenciales existentes. Clave, estado del dispatcher y salida nativa se guardan en `C:/docker-secrets/knowledge-memory/native-acceptance/<run>/`, fuera de Git y OneDrive. La ruta debe tener los mismos permisos privados que los secretos existentes.

Esta sesión no puede escribir en esa carpeta privada. La preparación intentada se detuvo antes de login/creación de clave; no hay una aceptación nativa realizada ni se ha activado captura. Las once pruebas del preparador pasan con datos y transporte simulados; no son evidencia de conexión real de un cliente.

Actualización del 2026-11-06: el operador preparó el ensayo `fd288af212a04055850bf418b7c6c6f3`. Se verificaron las tres instalaciones 0.1.2, clave de sólo lectura, captura off/contexto auto y `doctor --online`: las tres devuelven ready, autorización correcta y 24 tools sin ausencias. El comando nativo de Claude lista Kairos como pendiente de aprobación; el de Codex aún no lo lista en su configuración efectiva. No se aprobó nada automáticamente. El intento de ejecución con Claude desde esta sesión se detuvo al crear el log privado, antes de iniciar el cliente. Siguiente paso: abrir la UI nativa desde PowerShell del operador, revisar/aprobar y ejecutar `--run`. Evidencia: [native-preparation.json](native-preparation.json), [native-config-probes.json](native-config-probes.json) y [native-client-acceptance.json](native-client-acceptance.json). Esta última aún registra los tres clientes como `not_run`.

## 1. Preparar

Desde `knowledge-graphs` en PowerShell del usuario:

```powershell
python kairos/scripts/accept-native-clients.py
python kairos/scripts/accept-native-clients.py --prepare
```

El primer comando sólo imprime el plan. El segundo crea la clave de ensayo, instala Kairos 0.1.2 en las tres carpetas nuevas y devuelve su identificador, sin imprimir el secreto. La captura local permanece `off` y el contexto queda `auto`. El script no instala paquetes globales, no publica npm ni cambia configuraciones de los proyectos de trabajo.

Una segunda preparación se rechaza si hay un ensayo vigente. Si se pierde la respuesta al crear una clave, el identificador/nombre del ensayo queda guardado; `--cleanup` consulta el servidor y reconcilia esa clave antes de revocarla, sin crear otras a ciegas.

## 2. Revisar la conexión y los hooks en cada cliente

```powershell
python kairos/scripts/accept-native-clients.py --open claude
python kairos/scripts/accept-native-clients.py --open codex
python kairos/scripts/accept-native-clients.py --open opencode
```

Cada comando abre únicamente la carpeta correspondiente. Revisa el MCP `kairos` y sus comandos Node/ruta de clave, y aprueba esa conexión en la UI nativa. En Codex abre `/hooks`, revisa las definiciones exactas de Kairos y confíalas sólo si coinciden con los archivos preparados; las definiciones modificadas requieren revisión nueva. No se usa `--dangerously-bypass-hook-trust`, no se edita el almacén de confianza y no se desactiva el sandbox. Sal del cliente para continuar.

En Claude usa `/mcp` para revisar/aprobar Kairos y `/exit` para salir normalmente. El proceso Python espera mientras la interfaz esté abierta. Si pulsas Ctrl+C, el lanzador devuelve `cancelled` con código 130 y no considera la prueba aceptada; ya no imprime un traceback. Si interrumpes una ejecución `--run`, se guarda su cancelación en lugar de conservar un resultado previo.

Claude carga explícitamente la instalación de custom-agents registrada por su cliente, si existe, junto al MCP de prueba. No se modifica la caché del plugin. Codex y OpenCode conservan sus preferencias y autenticación nativas. El script no selecciona otro modelo. Si falta autenticación o el cliente no permite confiar una conexión, resuélvelo en su propia interfaz; no compartas claves ni volcados de configuración.

## 3. Ejecutar y recoger

```powershell
python kairos/scripts/accept-native-clients.py --run claude
python kairos/scripts/accept-native-clients.py --run codex
python kairos/scripts/accept-native-clients.py --run opencode
python kairos/scripts/accept-native-clients.py --collect
```

La petición controlada solicita únicamente `projects` y `context`, con semántica desactivada y contexto acotado, y una referencia documental real. No pide guardar memoria. Cada ejecución tiene un timeout de 180 segundos y guarda su salida sólo en la carpeta privada del ensayo. Los clientes se lanzan mediante sus ejecutables reales, evitando que un shim `.cmd` reinterprete los argumentos. Puede consumir el uso normal del modelo configurado en cada cliente; no se cambia a un modelo alternativo.

El recolector exporta sólo metadatos de aceptación, sin prompts, cuerpos, credenciales ni transcripciones: `native-client-acceptance.json` en esta carpeta. Un nombre de tool escrito en texto libre o un proceso con exit code cero no prueban una llamada exitosa. Se exigen eventos de ejecución reconocidos y resultados correctos; formatos desconocidos quedan `needs_review`. El recolector distingue explícitamente:

- **MCP de lectura observado:** `projects` y `context` ejecutados satisfactoriamente por el cliente real.
- **Hooks observados:** hay eventos de ciclo de vida; aún hay que comprobar origen y resultado de cada handler.
- **Contexto automático aceptado:** requiere evidencias de inyección real, que no se infieren de una llamada manual a `context`.
- **Captura aceptada:** la preparación inicial es de lectura y conserva las políticas `off`. Tras la activación explícita de summary en Claude, el recolector contrasta la sesión actual con notas, eventos inmutables y recibos mediante la API. Sólo esa verificación permite `automatic_capture_accepted=true`; no se deduce del código de salida o de la política.

El ensayo no permite cerrar C-08 completo por obtener tres respuestas de lectura. La prueba positiva de captura requiere un entorno/proyecto de aceptación con consentimiento y permisos de escritura explícitos, identidades estables y recuperación verificada; no se activa silenciosamente en los dos proyectos existentes.

## 4. Revocar el acceso de ensayo

Actualización del 2026-11-06: lectura, inyección automática y captura persistida de cuatro eventos técnicos aceptadas para la sesión de ensayo de Claude de las 09:10 UTC. Stop figura cancelado desde la perspectiva del cliente, aunque su entrega está verificada; la incidencia sigue abierta. Activación, evidencia, límites y reversión: [native-capture-summary.md](native-capture-summary.md). El helper actual pasa 20 pruebas; los recuentos inferiores describen fases anteriores. Codex y OpenCode siguen pendientes y mantienen capture off.

```powershell
python kairos/scripts/accept-native-clients.py --cleanup
```

Comprueba ID, nombre único, proyecto y scopes de la clave antes de revocarla. No puede revocar una clave cuyo nombre/scopes no coincidan con el ensayo. Retira su archivo local; conserva los logs privados y configuraciones para diagnóstico. No borra conocimiento, volúmenes ni credenciales de trabajo. Un dispatcher de prueba sin actividad finaliza por su timeout normal; no se matan procesos mediante PID sin verificar.

## Verificación del preparador

```powershell
python -m unittest discover -s kairos/scripts/tests -v
```

Once pruebas: scopes y conservación de configuración ajena; rechazo de escritura privada antes de red; pérdida de respuesta de creación; protección frente a revocación de otra clave; exclusión de OneDrive; argumentos sin cambio de modelo ni bypass; distinción entre llamadas reales, texto y errores; recuperación ante bloqueo breve de reemplazo en Windows; y conservación del destino cuando el reemplazo no es posible. El estado se escribe mediante temporal único y reemplazo atómico con reintentos acotados sólo para ese bloqueo. Nunca se borra el destino para resolverlo. Los temporales de esas pruebas contienen únicamente datos sintéticos y usan un directorio propio dentro del workspace.

Fuentes contrastadas: [hooks y confianza de Codex](https://learn.chatgpt.com/docs/hooks), [CLI de Codex](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [CLI de Claude Code](https://code.claude.com/docs/en/cli-reference) y [CLI de OpenCode](https://opencode.ai/docs/cli/). Las versiones y flags locales observados mandan sobre suposiciones acerca de otros clientes o releases.

Actualización de OpenCode: el doble registro global de custom-agents está [resuelto y verificado](opencode-plugin-repair.json). La primera ejecución posterior falló antes de llamar al MCP por `provider.auth`, HTTP 403, con `opencode/crouton-alpha-free`. Se puede repetir sólo ese ensayo con `--run opencode --model PROVEEDOR/MODELO`, usando un modelo disponible elegido explícitamente por el operador. No modifica el modelo predeterminado. Diagnóstico, límites y regresiones: [native-opencode-provider.md](native-opencode-provider.md). Los scripts actuales pasan 30 pruebas; OpenCode sigue sin aceptar.

Ampliación posterior: la lectura con Big Pickle está [aceptada](native-opencode-read.md). El helper admite ahora activación, retirada y prueba de contexto automático para los tres clientes, con claves separadas y recuperación de marcadores sintéticos. Procedimiento vigente: [contexto y captura automática por cliente](native-automation-matrix.md). Los resultados históricos anteriores no se convierten automáticamente en aceptación de la ampliación.
