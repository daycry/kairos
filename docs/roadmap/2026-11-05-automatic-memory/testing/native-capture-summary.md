# Captura de resumen en la prueba real de Claude

Esta página conserva la prueba inicial de Claude. La activación y el verificador se han ampliado después a Codex y OpenCode: [procedimiento vigente y límites](native-automation-matrix.md). La ampliación requiere todavía sus ejecuciones nativas; no se extrapola el éxito de Claude.

Autorización del usuario: 2026-11-06, después de comprobar lectura e inyección de contexto en Claude con custom-agents cargado. Alcance: proyecto `custom-agents`, carpeta de ensayo de Claude y modo `summary`. EUIPO y las otras carpetas no se activan.

La ejecución iniciada a las 08:37 UTC llamó correctamente a `projects` y `context`. El stream confirmó MCP Kairos conectado, custom-agents cargado y seis respuestas de hooks. Dos inyectaron contexto de Kairos con referencias válidas del proyecto: `SessionStart` y `UserPromptSubmit`. El recolector reconoce esos resultados; no confunde los doce paquetes started/response con doce ejecuciones. Evidencia: [native-client-acceptance.json](native-client-acceptance.json).

## Activación

Desde `knowledge-graphs`:

```powershell
python kairos/scripts/accept-native-clients.py --enable-capture claude
```

El helper comprueba la escritura privada antes de contactar con la API. Crea una clave separada con permisos `read/write` únicamente para custom-agents, actualiza sólo el ensayo de Claude y cambia únicamente `capture_mode` a `summary`, conservando `temporal_projection`. Lee de vuelta la política antes de declarar `capture_enabled`. La clave original de lectura sigue siendo la usada por las otras carpetas.

El primer intento desde la sesión del implementador se detuvo al escribir el estado privado, antes de tocar la política. El operador completó después la activación y se contrastó la clave real contra MCP. Véase [capture-activation.json](capture-activation.json). No hay que repetir la activación cuando ya existe.

Después de `capture_enabled`, revisa la configuración cambiada y ejecuta la prueba:

```powershell
python kairos/scripts/accept-native-clients.py --open claude
# Dentro de Claude: /mcp para revisar Kairos; /exit para salir.
python kairos/scripts/accept-native-clients.py --run claude
python kairos/scripts/accept-native-clients.py --collect
```

El prompt controlado continúa pidiendo sólo lectura. Los hooks autorizados de ciclo de vida pueden guardar metadatos técnicos de sesión y del evento; no guardan el prompt o respuesta completos en summary. Los resúmenes explícitos mantienen su tratamiento normal. Hay que verificar después la sesión, IDs, hashes, procedencia y recibos de los eventos persistidos. El recolector no declara captura aceptada por ver la política activada.

## Reversión y fallos

```powershell
python kairos/scripts/accept-native-clients.py --disable-capture claude
```

Desactiva el ensayo y revoca sólo la clave propia de captura, verificando nombre, ID y scopes. Restaura la política anterior sólo si la política vigente sigue siendo la esperada; un cambio ajeno se conserva y requiere reconciliación. No borra memorias, fuentes ni particiones de outbox/recibos. `--cleanup` hace también esta desactivación antes de revocar la clave original de lectura.

Una respuesta perdida del PUT queda como activación pendiente de reconciliar. Repetir `--enable-capture` no crea otra clave a ciegas: exige verificar o desactivar el intento existente. Un cambio de política detectado antes del PUT no se sobrescribe. El lector de claves respeta la envoltura REST real `items`, incluida su verificación antes de revocar.

## Validación

`python -m unittest discover -s kairos/scripts/tests -v`: **20/20 pruebas** con datos y transporte sintéticos. Cubren activación limitada al proyecto/cliente, preflight privado anterior a red, pérdida de respuesta y restauración, limpieza de claves propias, contexto nativo, Ctrl+C y escritura atómica. Las cuatro regresiones de lectura persistida comprueban hashes/recibos, rechazo de sesiones o fechas anteriores, paginación inválida/incompleta y que una ejecución nueva no hereda la aceptación de otra.

## Prueba real de captura aceptada — 2026-11-06

La ejecución de Claude iniciada a las **09:10:51 UTC**, sesión `16c586bf-6f58-4e33-9ead-aa2ea27b5103`, terminó con código 0. El recolector volvió a leer la API y contrastó cuatro registros de esa sesión:

| Hook | Registro persistido | Recibo |
| --- | --- | --- |
| SessionStart | Inicio de sesión | accepted |
| UserPromptSubmit | Entrada técnica de la petición | accepted |
| Stop | Resumen técnico del cierre | accepted |
| SessionEnd | Fin de sesión | accepted |

Los cuatro conservan proyecto `custom-agents`, agente `claude`, versión 1, etiquetas `runtime:claude` y `capture:summary`, procedencia `agent://claude/<sesión>/…` y SHA-256 del contenido. El hash canónico de cada evento inmutable coincide con su vista actual; el fingerprint de captura coincide con su recibo. No tienen trabajos de embeddings o extracción. La cola del ensayo tiene seis eventos completados en total, incluidos dos de una apertura anterior, sin pendientes ni errores. No son seis registros de esta última sesión.

`--collect` verifica ahora la persistencia en cada lectura de un ensayo Claude con summary y contexto aceptado. Consulta notas, historial y recibos; exige los cuatro eventos de la sesión nativa actual y exporta sólo IDs, hashes y metadatos. Pagina hasta 1.000 notas y 1.000 eventos; un límite alcanzado, cierre ausente, hash incorrecto o API no disponible deja `automatic_capture_accepted=false` y `capture_verification.status=needs_review`. No crea eventos ni reenvía capturas.

Evidencia: [native-client-acceptance.json](native-client-acceptance.json), campos `automatic_capture_accepted=true` y `capture_verification`; estado del dispatcher en [claude-capture-queue-status.json](claude-capture-queue-status.json).

El stream nativo marcó **Stop como cancelled, exit_code=1**. Su evento y recibo sí están persistidos y coinciden. Se conserva la incidencia en `native_hook_failures`: esta prueba demuestra entrega y recuperación, pero no que todos los hooks terminen correctamente desde la perspectiva del cliente. No se ha determinado aún la causa de esa cancelación.

Este ensayo usa resúmenes técnicos de ciclo de vida; no demuestra aprendizaje semántico generado de una tarea real ni captura completa de conversaciones. Lectura MCP, inyección de contexto y persistencia están verificadas para Claude con custom-agents cargado. Codex y OpenCode siguen pendientes; C-08 y la aceptación global continúan abiertos. La captura permanece activada sólo en el ensayo de Claude, y EUIPO continúa fuera de esta activación.
