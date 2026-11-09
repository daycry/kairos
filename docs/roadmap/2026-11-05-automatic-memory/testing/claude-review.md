# Revisión independiente con Claude CLI

Fuentes: snapshot inmutable de 128 archivos. Herramientas disponibles: Read, Grep y Glob. Sin ejecución de pruebas ni acceso a servicios o credenciales.

# Revisión de Kairos: captura automática, instalador, MCP/Store y límites de la plataforma

Todo lo que sigue sale de leer el código. No he ejecutado nada; donde algo necesita ejecución para confirmarse, lo indico.

## Veredicto global

**No lo considero listo para dar por cerrado el bloque de captura automática y el instalador.** El núcleo del servidor está bien construido: idempotencia de `remember` y `publish_document`, revocación comprobada en cada llamada, tombstones y verificación de corpus ante retiradas. El IPC local y el puente MCP también son sólidos.

Sin embargo, encuentro varios defectos reales en la parte nueva:

- **OpenCode:** la automatización falla siempre, por cómo se fija la ruta de Node en la instalación.
- **Producción frente a pruebas:** con la configuración de producción, cada evento técnico capturado llama al proveedor de embeddings. Esto contradice la documentación y la evidencia aportada.
- **Outbox:** la cola local no se poda nunca. Acaba bloqueando la captura de forma permanente.
- **Ajustes ajenos:** cualquier hook ajeno añadido después del de Kairos desactiva toda la automatización en silencio.
- **Contexto automático:** la consulta que genera casi nunca encuentra nada con prompts normales.

No he encontrado nada de gravedad crítica (pérdida de datos o brecha de seguridad demostrable).

### Cobertura real

| Estado | Archivos |
|---|---|
| **Leído completo** | `docs/roadmap/2026-11-05-automatic-memory/tasks.md`, su `testing/verification.json`, `docs/roadmap/2026-11-04-native-product/tasks.md`, `docs/integration.md`. Cliente: `capture.mjs`, `outbox.mjs`, `dispatcher.mjs`, `lifecycle.mjs`, `hooks.mjs`, `install.mjs`, `config.mjs`, `lifecycle-config.mjs`, `opencode.mjs`, `files.mjs`, `privacy.mjs`, `mcp.mjs`, `cli.mjs`. Tests: `capture`, `dispatcher` y `lifecycle` (`.test.mjs`), y `lifecycle-live.mjs`. Servidor: `mcp.py`, `store.py`, `privacy.py`, `models.py`, `auth.py`, `worker.py`, `tests/lifecycle_probe.py` |
| **Leído en parte** | `retrieval.py` (líneas 70–203), `agent_store.py` (155–363), `docs/install.md` (84–133), `providers.py` y `app.py` (por búsquedas), `install.test.mjs` (por búsquedas), `docker-compose.yml` (por búsquedas) |
| **No revisado** | Portal web (`web/src/*`, sus tests y vite), `scripts/*` (deploy, diagnose, admin, client, build-handbook), `admin.py`, `activity.py`, `agent_tools.py`, `initialize.py`, `config.py`, `nginx.conf`, `ollama-proxy`, los Dockerfiles en detalle, `test_*.py` del servidor salvo `create_core`, `npx-smoke`/`prepare-smoke`, el resto de `docs/` y los contratos exportados |
| **No disponible** | `memory_platform/schema.sql`, que `store.py:55` carga pero no está en la copia. No puedo verificar restricciones, índices ni claves únicas. Probablemente es una omisión del snapshot, porque el despliegue funciona. |

**El criterio 6 (portal, despliegue y backups) prácticamente no lo he revisado.** No extrapolo nada a esas áreas.

---

## Defectos demostrables (Important)

### I-1. La automatización de OpenCode falla siempre: la ruta de Node fija rompe el plugin
- **Dónde:**
  - `install.mjs:29-33` incluye `node: process.execPath` en el binding.
  - `install.mjs:147` hace que `loadInstallation` recalcule el plan sin `replace`.
  - `opencode.mjs:14-15` llama a `loadInstallation` y luego a `ensureDispatcher` dentro del proceso de OpenCode.
  - `lifecycle.mjs:112` arranca el daemon con `process.execPath`.
- **Escenario:** instalar con `--client opencode --capture summary`. El adaptador se ejecuta dentro de OpenCode, que corre sobre Bun. Allí `process.execPath` es el binario de OpenCode, no el `node` registrado. Resultado: `installation_binding_conflict` y ninguna captura ni contexto. Si se superara ese punto, se lanzaría el binario de OpenCode como si fuera Node para arrancar el daemon.
- **Consecuencia:** la captura y el contexto de OpenCode V1 y V2 nunca funcionan. El único rastro es `kairos: …` en stderr.
- **Certeza:** alta en la lógica. Falta confirmar en OpenCode real que el runtime de plugins es Bun.
- **Tests:** `lifecycle.test.mjs:100,111` inyecta `send` y se salta este camino. Falta una regresión que use el `send` por defecto con un `execPath` distinto.
- **Propuesta:** no comparar `node` en `loadInstallation` desde el plugin y arrancar el daemon con `data.node` del manifiesto.

### I-2. En producción, cada evento técnico llama al proveedor de embeddings
- **Dónde:**
  - `store.py:258-259` añade `embed` a todo `upsert` si `embedding_enabled`.
  - `docker-compose.yml:12` fija `MEMORY_EMBED_ENABLED: '1'`.
  - `worker.py:46-50` lanza la llamada al proveedor.
- **Contradicciones:**
  - `tasks.md:28` dice que «Los eventos técnicos no llaman al proveedor».
  - `verification.json` declara `"provider_calls": 0`.
  - La sonda usa `Store(dsn)`, que no tiene embeddings (`test_store.py:21`).
  - `lifecycle_probe.py:58` imprime `provider_calls: 0` como literal; no lo mide.
- **Escenario:** con política `summary`, cada `PostToolUse` genera un `remember`, un trabajo `embed` y una llamada a Ollama.
- **Consecuencias:**
  - La cola del worker es FIFO global (`store.py:774`) y procesa un trabajo cada vez. Ráfagas de captura retrasan las extracciones y los embeddings de documentos de otros proyectos.
  - El cliente mantiene cada fila en `accepted` hasta que termina el embedding (ver I-4).
- **Certeza:** alta.
- **Propuesta:** excluir `category=agent-activity` (o los eventos técnicos) del embedding, o documentarlo y corregir la evidencia. Hacer que la sonda mida las llamadas reales con la configuración de producción.

### I-3. El outbox no poda nunca: la captura se bloquea para siempre al llegar al límite
- **Dónde:**
  - `outbox.mjs:76-79`: `budget()` cuenta todas las filas.
  - No existe ningún `rows.delete` salvo la copia temporal de `outbox.mjs:128`.
  - Las filas `complete` y `retired` se conservan para siempre.
- **Escenario:** cada uso de herramienta es un registro. Tras unos 10.000 eventos por binding, `admit` falla siempre con `capture_queue_full`. La documentación (`install.md:120`) dice que no se borren archivos y no ofrece comando de compactación.
- **Coste por escritura:**
  - `budget()` serializa todas las filas en cada `admit` y `update`.
  - Cada aceptación fuerza un `checkpoint()` del snapshot completo con fsync (`outbox.mjs:131`). Con miles de filas son varios MB por evento.
- **Certeza:** alta en la lógica. El tiempo hasta llegar al límite depende del volumen.
- **Tests:** sólo se prueba `maxRecords: 1` (`capture.test.mjs:85-88`). Falta una regresión que llene la cola con filas `complete`.
- **Propuesta:** compactar los recibos terminales (o moverlos a un archivo de historial rotado) y excluirlos del presupuesto.

### I-4. Las filas que no pueden avanzar se consultan para siempre y frenan a las nuevas
- **Dónde:** `dispatcher.mjs:86-107` y `129-131`, y `outbox.mjs:134`. La fase `failed` existe pero nunca se asigna.
- **Escenario:**
  - Las filas `accepted` con trabajos fallidos (ver I-2 con Ollama caído) se consultan con `event_status` y `get_job` en cada vuelta.
  - Las filas con `attempts>=5`, las rebajadas de `full` o las que tienen captura apagada siguen llamando a `capture_policy` (y a `event_status` si están en `unknown`) cada vez que les toca.
  - Con N filas atascadas y 4 por tick cada 3 s, una fila nueva espera unos N/4·3 s. Con N=1000, unos 12 minutos.
  - Las filas que agotan los reintentos conservan su cuerpo y cuentan contra `maxPending=200`, hasta llenar la cola.
- **Certeza:** alta.
- **Tests:** `dispatcher.test.mjs:85-91` comprueba precisamente que la fila sigue en `accepted`, pero no el coste a largo plazo.
- **Propuesta:** fase terminal `failed`, backoff por fila y un comando de operador para descartar o reintentar.

### I-5. Un hook ajeno añadido después del de Kairos desactiva toda la automatización en silencio
- **Dónde:**
  - `hooks.mjs:51-70` quita el grupo gestionado y lo vuelve a añadir al final.
  - `hooks.mjs:70` compara arrays sensibles al orden.
  - `install.mjs:149` lanza `configuration_drift`.
- **Escenario:** el usuario u otra herramienta añade un grupo `PostToolUse` después del de Kairos en `.claude/settings.json`. A partir de ahí:
  - `runHook` falla en `loadInstallation`.
  - `Dispatcher.current()` también falla en cada tick, así que ni se envían los pendientes ni se consultan los aceptados.
- **Consecuencia:** captura y contexto se detienen sin aviso visible para el usuario. En la práctica, preservar ajustes ajenos acaba rompiendo Kairos.
- **Certeza:** alta.
- **Tests:** falta la regresión (instalar, añadir un hook ajeno al mismo evento y llamar a `loadInstallation`).
- **Propuesta:** comprobar sólo que el grupo propio está presente (comparando como multiconjunto), no el orden del array.

### I-6. El contexto automático casi nunca encuentra nada con prompts normales
- **Dónde:** `capture.mjs:85-89` genera hasta 12 términos. Las búsquedas de `store.py:493` y `536` usan `plainto_tsquery`, que exige que estén todos (AND). Además el dispatcher pide `semantic:false`.
- **Escenario:** un prompt de 10 palabras sólo coincide con memorias que contengan las 10. Con `q` vacío (`SessionStart` u OpenCode, que no envía el prompt, `opencode.mjs:34`) se devuelven los elementos más recientes, que serán notas técnicas tipo «bash: completed».
- **Certeza:** alta en la semántica SQL. El impacto en la utilidad depende de los datos.
- **Tests:** la sonda real usa un prompt de 2 palabras (`lifecycle-live.mjs:45`), así que no lo detecta.
- **Propuesta:** consulta OR (por ejemplo `websearch_to_tsquery` con `or`) y excluir `agent-activity` del contexto.

### I-7. La autenticación MCP bloquea el bucle de eventos
- **Dónde:** `mcp.py:188-192` llama a `authenticate_bearer`, `authenticate_session` y `require_csrf` de forma síncrona dentro del ASGI asíncrono. Cada `transaction()` abre una conexión psycopg nueva (`store.py:44-50`) y no hay pool.
- **Escenario:** varios dispatchers y clientes simultáneos. Cada petición MCP congela el bucle mientras conecta y consulta. Con latencia de base de datos, el timeout de 1,8 s del dispatcher genera estados `unknown` y reconciliaciones adicionales.
- **Certeza:** alta en que bloquea; la magnitud necesita una prueba de carga.
- **Propuesta:** `asyncio.to_thread` en el middleware y un pool de conexiones.

### I-8. Actualizar a otra versión del paquete es imposible, aunque la documentación indica cómo hacerlo
- **Dónde:** `install.mjs:28` y `146` rechazan cualquier manifiesto con otra `runtime.version`.
- **Contradicción:** `install.md:80` dice que una instalación existente se actualiza con `--replace`.
- **Escenario:** cuando exista la 0.1.1, `install --replace` sobre una instalación 0.1.0 fallará con `incompatible_installation_manifest`. Los hooks siguen apuntando a `runtime/0.1.0`.
- **Certeza:** alta en el código. Hoy no se puede reproducir porque sólo existe una versión.
- **Propuesta:** un camino de migración explícito y una regresión con dos versiones de manifiesto.

### I-9. En modo `full` no se redactan secretos de estilo `.env`
- **Dónde:** `privacy.mjs:25`, con `\b(?:password|…)`. No hay límite de palabra entre `_` y `P`, así que `DB_PASSWORD=x`, `AWS_SECRET_ACCESS_KEY=…` o `GITHUB_TOKEN=ghp_…` pasan sin redactar. El servidor tiene el mismo hueco (`privacy.py:21`). Tampoco hay patrones `ghp_`, `xox*` ni `AIza`.
- **Escenario:** con `full` activo en ambos lados, un `cat .env` capturado llega a PostgreSQL con los secretos.
- **Matiz:** `install.md:96` advierte que la limpieza no reconoce cualquier secreto. Aun así, este es el caso más habitual.
- **Certeza:** alta.
- **Propuesta:** cubrir nombres con prefijo y guion bajo y añadir tokens de proveedores conocidos.

## Sospechas que necesitan ejecución

- **S-1. Formato de hooks de Claude.** `hooks.mjs:19` usa `command: execPath` más `args[]`, sin pasar por la shell. Que yo sepa, el hook de comando de Claude Code se documenta como una cadena `command` que ejecuta la shell; no me consta que acepte `args`. Si no lo acepta, se ejecuta `node` sin argumentos con el JSON por stdin: falla en cada hook (en Windows, además, por los espacios de `Program Files`). Lo mismo aplica a `commandWindows`, `additionalContextLimit` y `async` en Codex. Los tests sólo validan la estructura (`lifecycle.test.mjs:34-35, 62-68`). Hay que comprobarlo en C-08 con los clientes reales.
- **S-2. Búsqueda semántica con muchos candidatos.** `store.py:879-933` carga hasta 10.001 candidatos con vector y payload completos en Python (unos cientos de MB por consulta con 768 dimensiones). Cuando se supera el límite, recorta por orden de `item_id`, no por relevancia. Con I-2, los proyectos con captura activa llegan pronto a ese límite. Necesita una prueba de carga.
- **S-3. Bloqueo de la cola.** En `outbox.mjs:23-35` hay una ventana TOCTOU con un lock obsoleto: dos daemons podrían acabar ambos como propietarios. La probabilidad es baja.

## Minor

- **M-1.** El servidor no aplica el techo `summary`/`full`: `store.py:379` sólo comprueba `off`. Depende de que el cliente sea honrado y hay una ventana entre `capture_policy` y `remember` (`dispatcher.mjs:95-109`). Además, `install.md:92` dice que `full` exige permiso en servidor y cliente.
- **M-2.** Los hooks síncronos (`UserPromptSubmit`) esperan a la red de forma indirecta: contexto y captura por IPC (hasta 2,2 s cada uno) y, dentro, `capture_policy` remota. Esta se consulta antes de descartar herramientas excluidas o proyectos ajenos (`dispatcher.mjs:61-62`). La frase «el hook no espera» de `install.md:102` es imprecisa.
- **M-3.** Actualizar Node (por ejemplo, rutas versionadas de nvm) rompe los hooks, y `doctor` falla si se ejecuta con otro `node`, porque el binding guarda `execPath` (`install.mjs:29`). No está documentado.
- **M-4.** OpenCode V1 inyecta memoria no confiable en `output.system` (`opencode.mjs:50`). Lleva etiqueta de dato no confiable, pero ocupa el rol de sistema.
- **M-5.** El worker convierte los `MemoryError` de `complete_job` en un genérico `provider_error` (`worker.py:75-77`) y se pierde el diagnóstico.
- **M-6.** `integration.md:140` dice que no existe un hook instalado automáticamente, mientras el instalador ofrece hooks opcionales. La frase es ambigua.

## Funcionalidades planificadas pendientes (no son defectos)

Siguen pendientes, según los propios documentos:

- Aceptación dentro de los clientes reales (C-08, A-07).
- Publicación en npm (A-08).
- Análisis de código en el cliente (A-02).
- Herramientas restantes de observaciones (A-03).
- Trabajo de equipo compartido (A-04).
- Consulta generativa de corpus; hoy es sólo léxica y así se declara (A-05).
- Vistas completas del portal (A-06).

## Áreas sin defectos encontrados (dentro de lo leído)

- **IPC local:** sólo loopback; comprueba Host, Origin y nonce, y limita tamaños.
- **Puente stdio/HTTP:** límites, correspondencia exacta de IDs y redirecciones rechazadas.
- **Transacción del instalador:** backups, journal de recuperación y verificación de bytes antes de escribir.
- **Idempotencia de `remember` y `publish_document`:** lock por evento y conflicto si cambia el hash.
- **Revocación y expiración:** se comprueban en cada llamada (`store.py:68-85`).
- **Ausencia confirmada:** sólo con permisos de escritura vigentes.
- **Corpus:** invalida lecturas ante retiradas o cambios (`agent_store.py:285-296`).
- **Manifiesto documental:** paginado.

## Acciones prioritarias

1. **Arreglar el binding de OpenCode (I-1)** y añadir un test sin `send` inyectado. Validar el formato de hooks de Claude y Codex en clientes reales (S-1) antes de declarar C-05 y C-06 cerradas para los tres clientes.
2. **Decidir si los eventos técnicos deben tener embedding (I-2).** Después, alinear `tasks.md`, `install.md` y `verification.json`, y hacer que la sonda mida las llamadas al proveedor con la configuración de producción.
3. **Dar un ciclo de vida al outbox (I-3, I-4):** compactar recibos terminales, fase `failed` con backoff, sacar las filas atascadas de la rotación y un comando de operador.
4. **Tolerar cambios ajenos en los hooks (I-5) y corregir la consulta de contexto (I-6)**, con regresiones específicas para ambos casos.
5. **Rendimiento del servidor:** sacar la autenticación MCP del bucle de eventos y usar un pool (I-7). Hacer una prueba de carga de búsqueda semántica y captura concurrente (S-2).
