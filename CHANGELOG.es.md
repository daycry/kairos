# Registro de cambios

Aquí se recogen los cambios relevantes de Kairos. El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Cada sección sale de un ledger cerrado de `docs/roadmap/`, que tiene el detalle y la evidencia completos. La versión en inglés es [CHANGELOG.md](CHANGELOG.md).

Kairos aún no tiene versiones etiquetadas. Todo lo que sigue está sin publicar. El CLI `@daycry/kairos` está en la 0.3.0 y no se ha publicado en npm.

## [Sin publicar]

### Changed — iniciativa `retrieval-quality` (2026-11-09)

La búsqueda ya se puede medir y encuentra más de lo que guardas. [Ledger](docs/roadmap/2026-11-09-retrieval-quality/tasks.md) · [revisión final](docs/roadmap/2026-11-09-retrieval-quality/review.md)

**Calidad de la búsqueda**

- **Evaluación de la recuperación.** Un conjunto sintético congelado de 72 preguntas (español, inglés, erratas y documentos largos) y la puerta `retrieval-eval` miden recall@k y MRR por capa y subconjunto, sin red. La búsqueda combinada pasa de recall@5 0,50 y MRR 0,34 a 1,00 y 0,97. Con el modelo real `nomic-embed-text` llega a 1,00 y 0,99.
- **pgvector y HNSW.** La búsqueda semántica corre en PostgreSQL con pgvector, no con coseno en Python. Un índice HNSW cubre el modelo indexado y el coseno exacto en SQL cubre el resto, con los mismos permisos y plazos. PostgreSQL usa ahora una imagen derivada con pgvector en versión fijada.
- **Búsqueda léxica por idioma.** Notas, documentos, hechos, corpus de agente y filtros del portal ignoran las tildes y reconocen formas de la palabra en español e inglés (`canción`/`canciones`, `failed`/`fails`). Si salen pocos resultados, `pg_trgm` añade coincidencias aproximadas para erratas e identificadores como `ERR-4471`, marcadas como tales.
- **Troceado de textos largos.** Documentos y notas se dividen en fragmentos de unos 1.500 caracteres con 200 de solape. La búsqueda encuentra ya lo que hay más allá del antiguo corte de 8.000 caracteres, y los resultados traen un `matched_chunk` opcional con el pasaje que coincide. `admin backfill-chunks` prepara el contenido existente y se ejecuta en el despliegue.
- **Búsqueda híbrida por defecto, con degradación.** Si solo falla la capa semántica, la búsqueda y el contexto devuelven igualmente los resultados léxicos y lo indican en el campo opcional `degraded` (`timeout`, `provider_error`, `store_error`, `no_vectors`, `embeddings_disabled`). El parámetro opcional `semantic_budget_ms` limita el tiempo de la capa semántica.
- **Fusión ajustable.** «Validado» es ahora una bonificación ajustable en el orden combinado (`MEMORY_FUSION_VALIDATED_BONUS`), no un orden absoluto. También se configuran `MEMORY_FUSION_K` y `MEMORY_FUSION_WEIGHTS`.

**Operación**

- **Logs estructurados.** La API y el trabajador escriben logs JSON de una línea con nivel, evento, duración e identificador de petición. Los secretos se redactan, todo fallo que antes era silencioso deja traza con su tipo de excepción y las librerías de terceros nunca registran por debajo de INFO.
- **Métricas Prometheus.** `GET /metrics` expone la latencia por capa de búsqueda, los errores de proveedor por código, la profundidad de la cola de trabajos, los trabajos fallidos por código y la saturación de los embeddings, siempre con etiquetas de valores cerrados. Solo responde en la red interna, con credencial de administrador o no responde (`MEMORY_METRICS`), y nginx y Caddy nunca lo publican.
- **Migraciones aditivas hasta el esquema v11.** Añaden la extensión `vector`, `unaccent`, `pg_trgm`, columnas por idioma, la tabla `memory.embedding_chunks` y un índice parcial de trabajos fallidos. Un test falla ahora si alguna migración borra o reescribe datos existentes.
- **Ensayo de despliegue.** `scripts/deploy-memory.py` admite un proyecto de ensayo aislado. Se ensayó la activación completa (migración, relleno de vectores y fragmentos, verificación) con contenido idéntico y la cola vacía al terminar. El despliegue real pasa a la Iniciativa 5 del [plan director](docs/roadmap/2026-11-10-platform-audit/plan.md).
- **Manuales.** Los manuales de arquitectura, configuración, operación, integración y uso describen todo lo anterior, y todas las variables nuevas están listadas y propagadas por Compose.

**Clientes y contrato**

- **Contrato MCP.** Solo cambios aditivos: los campos opcionales `matched_chunk`, `degraded` y `semantic_budget_ms`. Las 34 herramientas conservan su contrato.
- **CLI 0.3.0 (sin publicar).** El contexto automático usa también la búsqueda semántica, con un presupuesto de 1,1 s, y acepta el aviso `degraded` del servidor.

**Límites conocidos**

- Con el modelo real de embeddings, una de las 12 preguntas de documentos largos sale en segunda posición en vez de en la primera (`ca18:long`). Se acepta como deuda; la fusión se ajustará con el modelo real en la Iniciativa 5.

### Added — iniciativas anteriores (del 2026-11-04 al 2026-11-06)

Estos ledgers son anteriores al formato actual y `changelog-sync` no los lee, así que este resumen sigue sus listas de tareas.

- **Producto nativo (`native-product`, 2026-11-04).** Kairos pasa a ser un repositorio propio con API y trabajador nativos sobre PostgreSQL. Añade estado de trabajo privado por actor y proyecto, 23 herramientas MCP, la vista «Mi trabajo», un instalador Node sin dependencias, un despliegue con copia previa y verificación MCP, manuales propios y contratos exportados. Las herramientas MCP se aceptaron en clientes reales de Claude Code, Codex y OpenCode. [Ledger](docs/roadmap/2026-11-04-native-product/tasks.md)
- **Memoria automática por cliente (`automatic-memory`, 2026-11-05).** Los eventos nativos de cada cliente se capturan solos, con la privacidad aplicada antes de guardar nada. Completan el circuito una cola recuperable, un despachador local con IPC autenticado en loopback (los hooks nunca llaman al servidor remoto) y una inyección de contexto acotada y autorizada. El instalador fusiona los hooks sin borrar configuraciones ajenas. Aceptada en Claude, Codex y OpenCode. [Ledger](docs/roadmap/2026-11-05-automatic-memory/tasks.md)
- **Flujos funcionales (`functional-parity`, 2026-11-06).** Añade búsqueda de código local, esquema y expansión de símbolos con exclusiones y límites explícitos. También añade escritura de observaciones con nombre, recuperación de usos de herramientas y trabajo de equipo compartido, separado de las listas privadas. Hay respuestas generadas sobre el corpus con presupuesto de tokens y citas comprobadas, y vistas de observaciones, reglas, trabajo y actividad. Falta publicar el paquete en el registro. [Ledger](docs/roadmap/2026-11-06-functional-parity/tasks.md)
