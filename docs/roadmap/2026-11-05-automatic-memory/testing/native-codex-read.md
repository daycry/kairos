# Codex: lectura nativa confirmada, automatización pendiente

Ejecución real iniciada el 2026-11-06 a las 09:23:33 UTC, hilo `01a1b02b-a9fc-7681-ab2b-48ee63f9266b`. El cliente terminó con código 0 y sin timeout. El stream privado contiene llamadas MCP completadas satisfactoriamente a `projects` y `context`. El recolector reconoce sus resultados y marca `native_mcp_read_observed=true`. No se exportan los textos de las respuestas.

La instalación de ensayo de Codex conserva `capture=off` y `context=auto`, con clave de lectura. Sus hooks configurados son SessionStart y UserPromptSubmit. La ausencia de escrituras es coherente con capture off y no prueba un fallo del servidor.

El stream de esta ejecución contiene thread.started, turn.started, item.started, item.completed y turn.completed. No incluye respuestas de hooks ni inventario de plugins. Por tanto, `native_hook_events_observed=0` sólo cuenta lo observado en ese stream; no demuestra que ningún hook se ejecutara. La cola de captura está vacía, algo que tampoco decide si los hooks de contexto funcionaron, puesto que no necesitan escribir eventos de captura.

El recolector anterior producía `custom_agents_plugin_loaded=false` para Codex porque buscaba el inventario de inicialización de Claude. Se corrige a `null` cuando falta ese inventario, y se añaden `hook_execution_status` y `evidence_limitations`. No se infiere que el plugin esté desinstalado o desactivado. Una regresión distingue inventario ausente de inventario explícitamente vacío y mantiene sin aceptar contexto/captura sin evidencia positiva.

Validación del helper: **21/21 pruebas**. El informe regenerado conserva lectura aceptada de Codex, persistencia aceptada de Claude y aceptación global incompleta: [native-client-acceptance.json](native-client-acceptance.json).

La [documentación oficial de hooks de Codex](https://learn.chatgpt.com/docs/hooks) explica que los hooks locales requieren una capa de proyecto de confianza y revisión de su definición exacta mediante `/hooks`. No se ha probado que la confianza sea la causa de la falta de evidencia en este ensayo. No se modifica su almacén de confianza ni se utilizan flags que lo omitan.

Pendiente: obtener evidencia nativa específica de ejecución e inyección de contexto de Codex; después realizar una prueba de escritura autorizada para ese cliente. OpenCode todavía no se ha ejecutado. No repetir ni ampliar la activación de Claude para intentar resolver estas verificaciones.
