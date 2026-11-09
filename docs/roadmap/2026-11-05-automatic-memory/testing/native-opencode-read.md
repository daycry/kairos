# OpenCode: lectura aceptada con Big Pickle

La ejecución real iniciada a las 10:19 UTC del 2026-11-06, sesión `ses_e4fa19200ffeOC9RN9zCEdmRas`, usó explícitamente `opencode/big-pickle`, terminó con código 0 y no produjo errores nativos ni stderr. Completó descubrimiento de herramientas y llamadas a `kairos.projects` y `kairos.context`. Evidencia sin contenido privado: [native-opencode-read.json](native-opencode-read.json).

El recolector anterior devolvía needs_review porque sólo reconocía nombres planos `kairos_*`. Los paquetes reales contienen `tool_use`, herramienta exterior `execute`, y recibos estructurados `metadata.metadata.toolCalls` con `kairos.projects`/`kairos.context` y status completed. Las salidas JSON contienen las envolturas de resultados esperadas. Este formato corresponde al [Code Mode predeterminado de OpenCode 2](https://opencode.ai/v2/docs/mcp-servers).

Se reproduce el falso negativo con una regresión: `test_opencode_codemode_reads_are_recognized_from_native_receipts` falla antes del cambio. La corrección sólo admite recibos nativos completados y no truncados, con una llamada inequívoca y salida JSON de la forma esperada. Rechaza menciones en texto, estados fallidos, herramientas de otros servidores, resultados con isError y lotes cuya salida no se pueda asociar a una llamada. No evalúa ni interpreta el código ejecutado. Se conserva el soporte anterior para nombres planos.

Tras el cambio pasan **32/32 pruebas de scripts**, y volver a recoger la misma ejecución produce read_observed con projects/context. No se repite el ensayo ni se llama otra vez al modelo para corregir el informe.

Esta prueba acepta lectura MCP. No prueba por sí sola inyección automática de contexto ni captura; OpenCode continúa con capture off y la aceptación global permanece abierta. La ejecución más reciente de Codex fue interrumpida con código 130 a las 10:05 UTC; su lectura satisfactoria anterior queda documentada en [native-codex-read.md](native-codex-read.md), sin atribuir ese éxito a la ejecución cancelada.

La propuesta de conocimiento sobre formatos nativos queda documentada aquí y pendiente de curación configurada; no se modifican memorias personales.
