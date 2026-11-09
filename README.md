# Kairos

Kairos centraliza memoria de agentes, documentos aprobados y relaciones con procedencia. Un mismo servicio permite consultar contexto, guardar aprendizajes y revisar su procesamiento desde una aplicación web.

La instalación incluye una API autenticada, un trabajador de procesamiento, PostgreSQL, una web y un instalador MCP para Claude Code, Codex y OpenCode. La memoria pertenece a proyectos con permisos y políticas de captura independientes.

- [Documentación](docs/index.md).
- [Servidor desde cero](docs/server-install.md).
- [Configuración](docs/configuration.md).
- [Manual de uso](docs/manual.md).
- [Observaciones y trabajo compartido](docs/extended-workflows.md).
- [Respuestas sobre corpus](docs/corpus-generated-answers.md).
- [Análisis local de código](docs/code-analysis.md).
- [Instalación de clientes](docs/install.md).
- [Integración de custom-agents](docs/integration.md).
- [Operación y recuperación](docs/operations.md).
- [Arquitectura y alcance actual](docs/architecture.md).

Web local: `http://127.0.0.1:5173/`. Panel: `/app/`. Documentación publicada: `/docs/`. El instalador usa la dirección base y conecta por `/mcp/`.

El paquete `@daycry/kairos` está preparado para distribución local; su publicación en el registro npm queda pendiente. Conectar MCP permite usar sus herramientas, pero no activa por sí mismo la captura de todas las acciones del cliente. Consulta los límites en el manual antes de activar la captura.

Última actualización: 2026-11-06.
