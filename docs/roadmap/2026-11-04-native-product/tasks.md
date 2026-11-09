# Kairos: consolidación de producto nativo

Este ledger corresponde exclusivamente a la distribución de esta raíz. El coordinador lo actualiza con resultados observados. Código preparado, pruebas aisladas y activación del servidor son estados diferentes.

## Implementación

- [x] N-01 · Código de producto en un repositorio independiente. Sin montajes de fuentes del host, índices antiguos, paquetes de referencia ni adaptadores retirados. Los datos existentes permanecen fuera de Git.
- [x] N-02 · API y trabajador nativos con PostgreSQL, extracción y embeddings configurados. Imagen del trabajador derivada de la API, sin SDKs de otros motores.
- [x] N-03 · Migración aditiva y estado de trabajo privado por actor/proyecto, revisiones e idempotencia.
- [x] N-04 · Doce herramientas adicionales de trabajo, observaciones y corpus; 23 herramientas MCP en total. Las consultas de corpus declaran evidencia léxica.
- [x] N-05 · Vista «Mi trabajo» con tareas persistidas, filtros, progreso explícito, lectura sin permisos de mutación y reintentos estables.
- [x] N-06 · Corrección del reintento manual: los eventos en segundo plano no interrumpen una lectura activa ni ocultan su error. Rojo observado en Chromium: 16 de 17 recorridos; regresión añadida.
- [x] N-07 · Instalador Node sin dependencias, runtime estable y empaquetado local para npx; preserva configuraciones ajenas.
- [x] N-08 · Despliegue con previsualización, comprobación de volúmenes, copia previa, migración y verificación MCP de identidades/hashes.
- [x] N-09 · Manuales propios, contratos exportados y compilación reproducible de la documentación web.
- [x] N-10 · Distribución activada y verificada en el host. Configuración de redes corregida; informe privado complete, 2 proyectos, 21 documentos con identidades/hashes/versiones conservados y 23 herramientas MCP. Web, panel y contrato publicados responden. Sin borrado de datos ni cambio de captura.

## Functional acceptance

- [x] A-01 - Automatic capture and context injection through each real client lifecycle, with consent and a recoverable outbox. Accepted for technical summary capture in Claude 0.1.6, Codex 0.1.5 and OpenCode 0.1.5. OpenCode context was independently proven on 0.1.4. Scope and evidence: [automatic memory ledger](../2026-11-05-automatic-memory/tasks.md) and [native closure](../2026-11-05-automatic-memory/testing/native-acceptance-closure.md).
- [x] A-02 · Análisis de código en el cliente con límites y exclusiones explícitos. Isolated implementation accepted; see [functional workflows](../2026-11-06-functional-parity/tasks.md). Activation is recorded separately.
- [x] A-03 · Herramientas restantes de escritura de observaciones y recuperación de usos de herramientas. Isolated implementation accepted; see [functional workflows](../2026-11-06-functional-parity/tasks.md). Activation is recorded separately.
- [x] A-04 · Trabajo compartido de equipo, además de las listas privadas actuales. Isolated implementation accepted; see [functional workflows](../2026-11-06-functional-parity/tasks.md). Activation is recorded separately.
- [x] A-05 · Consulta generativa de corpus con continuidad, presupuesto y evidencia. Lexical retrieval remains available alongside explicit generation. Functional implementation accepted in isolated PostgreSQL/Chromium and bounded native provider tests; activation separate. See [functional workflows](../2026-11-06-functional-parity/tasks.md).
- [x] A-06 · Completar el diseño de las vistas de trabajo, observaciones, reglas y actividad con datos reales. Functional implementation accepted in isolated PostgreSQL/Chromium and bounded native provider tests; activation separate. See [functional workflows](../2026-11-06-functional-parity/tasks.md).
- [x] A-07 - MCP acceptance in real Claude Code, Codex and OpenCode clients. All three completed projects/context reads, with independent context/capture evidence. Accepted on 2026-11-06 within the documented scope; this is not acceptance of every tool or npm publication.
- [ ] A-08 · Publicación del paquete y verificación de instalación desde el registro. El tarball local está preparado; no se ha publicado.

No se declara equivalencia funcional completa mientras falten estos recorridos. No se sustituyen por botones sin implementación ni por una sonda de salud.

## Evidencia

Los resultados se registran en `testing/verification.json`. Los contenedores de pruebas usan PostgreSQL, FastAPI y Chromium locales con datos sintéticos; no acceden a las conversaciones, credenciales o proyectos reales. La inspección de fuentes y la instalación de paquetes de prueba se realizan fuera del repositorio del producto.

2026-11-06: A-01/A-07 siguen abiertos. Verificador ampliado a contexto y captura de Claude/Codex/OpenCode, con 51 regresiones aprobadas y procedimientos de recuperaci?n; faltan pruebas nativas de la ampliaci?n y resolver incidencias ya registradas. La preparaci?n no se considera paridad completa. V?ase [procedimiento de ensayo](../2026-11-05-automatic-memory/testing/native-automation-matrix.md).

2026-11-06, 14:18 UTC native runs: MCP reads verified again in Codex/OpenCode on runtime 0.1.3; automatic context and current-session lifecycle capture remain unaccepted. Runtime 0.1.4 corrects the OpenCode context/event contracts and forwards a bounded user retrieval query; Codex timeout normalization is classified as advisory. Red/green regressions, 59 Python tests, 70 Windows client tests and offline npm installation pass. Local tarball verified; operator-side fixture refresh and native acceptance pending. C-08 and A-01/A-07 remain open. See [runtime 0.1.4](../2026-11-05-automatic-memory/testing/native-runtime-0.1.4.md).

2026-11-06, 16:12 UTC: OpenCode 0.1.4 native automatic context accepted without tools; probe retired and receipts verified. MCP reads verified from grouped Code Mode receipts after collector correction. SessionStart persisted, Stop missing. Installed OpenCode artifact investigation identified successful execution completion as session.execution.succeeded; runtime 0.1.5 switches to that event and preserves native event identity. RED/GREEN regression, 62 scripts tests, 72 Windows client tests and offline npm installation pass. Package remains local. Operator refresh/new capture readback pending; C-08 and A-01/A-07 remain open. See [runtime 0.1.5](../2026-11-05-automatic-memory/testing/native-runtime-0.1.5.md).

2026-11-06, 17:24 UTC: operator applied OpenCode runtime 0.1.5. Successful native projects/context reads and current-session SessionStart/Stop capture are accepted by live note/history/receipt readback, with matching canonical/source/capture hashes and no generation jobs. The separate no-tools context proof remains accepted with its original 0.1.4 runtime and timestamp. No historical closures were synthesized. Codex automation and the Claude cancelled-Stop diagnostic remain open; C-08 and A-01/A-07 are not closed. Evidence: [OpenCode capture](../2026-11-05-automatic-memory/testing/native-opencode-capture-0.1.5.json).

2026-11-06: remaining Codex inspection confirms hooks enabled, trusted parent workspace and only two saved fixture approvals; current per-definition native trust remains unobserved because app-server initialization/control-socket access is denied to this session. Operator asked to refresh to frozen 0.1.5 and review /hooks. Claude terminal handlers are async despite documented print-mode teardown cancellation; isolated 0.1.6 candidate makes terminal admission synchronous, with RED/GREEN and 74/74 Windows tests plus offline installation. Working installer remains 0.1.5 during Codex review; candidate adoption and native Claude retest pending. C-08 and A-01/A-07 stay open. See [remaining acceptance](../2026-11-05-automatic-memory/testing/codex-trust-and-claude-terminal-candidate.md).

2026-11-06: operator reports Codex hook review complete. Fixture is 0.1.5 with seven saved approvals; fresh native context/read-capture tests requested. Adopted Claude terminal correction 0.1.6 from the validated isolated candidate after full baseline checks and source/test byte comparison. Candidate suite 74/74, adopted-root checks 2/2, offline package install and all 18 artifact files verified. Installed Codex/OpenCode fixtures unchanged. Claude refresh/native run pending; C-08 and A-01/A-07 remain open. Procedure: [runtime 0.1.6](../2026-11-05-automatic-memory/testing/native-runtime-0.1.6.md).

2026-11-06, 19:32 UTC: Codex 0.1.5 native context and read tests accepted after operator refresh and native hook review. The unpredictable context marker was echoed without tools and retired with matching receipts. Both new sessions separately persisted SessionStart, UserPromptSubmit, Stop and SessionEnd with matching canonical/source/capture hashes, accepted receipts and no generation jobs. Native output has no fatal errors or timeout advisories. Codex acceptance is resolved for this successful technical-summary cycle. Claude 0.1.6 refresh/native terminal validation remains pending; C-08 and A-01/A-07 remain open. Evidence: [Codex capture](../2026-11-05-automatic-memory/testing/native-codex-capture-0.1.5.json).

2026-11-06, 19:35 UTC: Claude 0.1.6 native run accepted with projects/context, scoped native context hooks, all four lifecycle events, exact hashes/receipts and no terminal cancellation or native error. Codex and OpenCode proofs remain accepted. Collector global-status regression reproduced (all criteria true but hard-coded incomplete), corrected with explicit all-client/no-error criteria and a declared technical-summary scope; 63/63 script tests pass and live recollection now reports native_acceptance_complete. C-08, A-01 and A-07 are closed. A-02/A-03/A-04/A-05/A-06/A-08 remain open; full product parity is not declared. Evidence: [native closure](../2026-11-05-automatic-memory/testing/native-acceptance-closure.json).

2026-11-06 functional expansion: A-02/A-03/A-04/A-05/A-06 accepted within the recorded test scope. A-08 remains open: local 0.2.0 tarball and clean-cache npx checks pass, public npm publication is not completed. Deployment was attempted and stopped at engine permission denial before changes; the live installation has not been updated by this initiative.

2026-11-09: the live installation now runs the functional-parity release (deployment verified, see [activation](../2026-11-06-functional-parity/testing/activation.json)). A-08 remains open: publication of the reviewed 0.2.0 tarball is blocked by the npm publisher account status; the registry returns 404.
