# Documentación de Kairos

Última actualización: 2026-11-09.

## Empieza por tu objetivo

| Quieres… | Documento |
|---|---|
| Entender la herramienta y utilizar el panel | [Manual completo](manual.md) |
| Instalar el servidor desde una carpeta nueva | [Servidor desde cero](server-install.md) |
| Entender los archivos y todas las opciones de configuración | [Referencia de configuración](configuration.md) |
| Conectar Claude Code, Codex u OpenCode | [Instalación de clientes](install.md) |
| Integrar custom-agents con una única conexión MCP | [Contrato de integración](integration.md) |
| Gestionar observaciones y trabajo compartido | [Observaciones y equipo](extended-workflows.md) |
| Generar respuestas citadas sobre memorias | [Consultas de corpus](corpus-generated-answers.md) |
| Explorar código local de forma explícita | [Análisis local](code-analysis.md) |
| Verificar el paquete y su publicación | [Entrega CLI](release-cli.md) |
| Desplegar, comprobar trabajos o recuperar una copia | [Operación](operations.md) |
| Conocer componentes, permisos y límites implementados | [Arquitectura](architecture.md) |
| Localizar fuentes para mantenimiento o agentes | [Índice de conocimiento](RAG-INDEX.md) |

El manual es dueño de las instrucciones del panel. La guía del servidor cubre el primer despliegue y la referencia de configuración describe sus parámetros. Instalación de clientes explica la conexión de agentes. Integración define identidad, entrega y conciliación. Operación reúne mantenimiento y recuperación. Arquitectura explica cómo encajan los componentes.

## Estado de esta documentación

Describe la implementación propia disponible: 34 herramientas MCP de servidor, almacenamiento central, procesamiento asíncrono y portal nativo. Las herramientas locales de código son una opción independiente del instalador. Comprueba la lista real del servidor desplegado: una compilación preparada no activa sus herramientas en un contenedor anterior. Un recibo de aceptación, una prueba unitaria o un estado de salud no acreditan por separado una integración completa con un cliente real.

Estado a 2026-11-09: la instalación local ejecuta esta distribución y superó la verificación de despliegue ([activación](roadmap/2026-11-06-functional-parity/testing/activation.json)). El paquete `@daycry/kairos` 0.2.0 está preparado y verificado, pero su publicación en npm sigue pendiente; la instalación de clientes usa el tarball local. La aceptación en cada cliente real debe verificarse en su entorno. No se promete captura automática universal ni equivalencia funcional completa con otros productos.

Las capturas de pantalla de los manuales están en `assets/screenshots/` y proceden de pruebas de interfaz con datos sintéticos.

No hay una sección separada de decisiones aprobadas, porque este repositorio no aporta un inventario de conocimiento aprobado para indexar. El avance de la distribución se mantiene en el [ledger de producto](roadmap/2026-11-04-native-product/tasks.md), separado del manual.

## Retirados

No se ha retirado ningún documento de esta estructura.
