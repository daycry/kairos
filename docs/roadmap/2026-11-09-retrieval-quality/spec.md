---
spec: retrieval-quality
descripcion: Calidad de recuperación de Kairos — evaluación medible, refactor de Store, pgvector/HNSW, búsqueda híbrida robusta, FTS por idioma, troceado para embeddings y observabilidad.
estado: aprobada          # borrador | aprobada | implementada | obsoleta
creado: 2026-11-09
actualizado: 2026-11-09
evaluacion: evaluation.md
design: n/a
plan: improvement-plan.md
generacion:
  inicio: 2026-11-09T11:34:20Z
  fin: 2026-11-09T11:43:21Z
  fuente: estimado        # producida dentro de la ventana medida de evaluation.md (sin marcador propio); su coste está incluido en el bloque generacion de evaluation.md
  tokens_reales: { entrada: 0, salida: 0, cache_creacion: 0, cache_lectura: 0 }
  eur: null
  horas_ia: 0.00
  duracion: 0m
  ratio_usado: 300000
---

# Calidad de recuperación (iniciativa 1 de 3 de la mejora integral de Kairos)

> **Evaluación:** [`evaluation.md`](evaluation.md)
> **Plan de implementación:** [`improvement-plan.md`](improvement-plan.md) · [`tasks.md`](tasks.md)

> **Terminología:**
> - **Capa**: origen de un resultado de `search`/`context`: `episodic` (memory_items, léxica), `documental` (documents, léxica), `temporal` (hechos nativos) y `semantic` (vectores; sus aciertos se etiquetan como `episodic`/`documental`). **Fusionado** = lista final tras la fusión RRF de `Retrieval.search`.
> - **Fragmento (chunk)**: tramo contiguo del texto de un elemento con su posición (`ordinal`, `char_start`, `char_end`) y su propio embedding.
> - **Ruta exacta**: búsqueda vectorial sin índice ANN (coseno exacto, hoy en Python; tras C-03, operador `<=>` de pgvector sin índice).
> - **Conjunto de evaluación**: preguntas sintéticas + memorias esperadas, versionado en el repositorio; nunca datos de la base desplegada.

## Contexto y objetivo

Kairos es la memoria central de los agentes. Hoy la recuperación tiene cuatro límites medibles en el código:

1. **Vectores sin índice**: `Store.search_vectors` (`memory_platform/store.py:964`) recorre hasta 10.000 candidatos autorizados vía `_vector_candidates` (`store.py:922`) y calcula el coseno exacto en Python; la columna es `vector double precision[]` (`memory_platform/schema.sql:41`, 1..4096 dimensiones, varios modelos). No escala más allá del tope y marca `candidates_truncated`.
2. **FTS sin idioma**: todo el texto se indexa con `to_tsvector('simple', …)` (`schema.sql:28-30`; `store.py:342`, `:437`, `:533`, `:572-579`, `:734`; `agent_store.py:213`, `:329-331`, `:366`; `corpus_answers.py:180-181`; `portal_store.py:42-79`). Sin stemming es/en, sin `unaccent` y sin tolerancia a errores tipográficos o identificadores.
3. **Un único embedding truncado**: `worker.py:50` embebe `title + content` cortado a `[:8000]` (y `providers.py` vuelve a cortar a 8000); el contenido más allá de ese punto de documentos de hasta 200.000 caracteres es invisible para la búsqueda semántica.
4. **Sin medida ni observabilidad**: no existe conjunto de evaluación de recuperación ni métricas/logs estructurados (`grep` de `logging`/`prometheus` en `memory_platform/*.py` vacío).

**Objetivo**: hacer la recuperación **medible** (C-01) y mejorarla de forma demostrable con esa medida (C-03…C-06), con el código de persistencia dividido por dominio (C-02) y con observabilidad operativa (C-07), sin romper las 34 herramientas MCP ni el despliegue existente.

**Fuente**: encargo del usuario en la conversación de `/dev-cycle` (2026-11-09), «adelante con todo» sobre una propuesta de 13 puntos, dividida en 3 iniciativas; esta cubre P13, P11, P1, P3, P4, P2 y P12.

## Decisiones de diseño

| Decisión | Elección | Motivo |
|---|---|---|
| Orden de trabajo | **C-01 → C-02 → C-03 → C-05 → C-06 → C-04; C-07 en paralelo desde C-02** | C-01 da la línea base; C-02 reduce el riesgo de tocar `store.py`; C-04 (fusión) se ajusta mejor cuando ya existen las señales finales (C-03/C-05/C-06). Difiere del orden del encargo solo en mover P3 al final (ver evaluación). |
| Oráculo de calidad | **Puerta separada `retrieval-eval`** fuera de la suite de 177 tests | El test de calidad nace en rojo (encargo P13) pero la suite debe seguir verde antes y después de C-02; ambos requisitos solo son compatibles si los umbrales de calidad viven en una puerta propia. Pendiente de confirmar (P-08). |
| Embeddings en CI | **Proveedor simulado determinista** + **ejecución real opcional** contra Ollama con datos sintéticos | La suite aislada no tiene red; la calidad semántica real solo se puede afirmar con el modelo real (P-06). |
| Refactor de `Store` | **Mixins por dominio** en módulos nuevos; `memory_platform/store.py` queda como fachada que compone `Store` y reexporta `as_dict`, `canonical`, `digest`, `new_id`, `lexical_query`, `clean` | Conserva `from memory_platform.store import Store, …` y `patch.object(store, '_require')` usados por la suite. |
| Imagen PostgreSQL | **Imagen derivada** `FROM postgres:17-bookworm@sha256:839fbb5a…` + paquete PGDG `postgresql-17-pgvector` con versión fijada (≥ 0.8.0), usada por `memory-postgres` y por el target `test` del Dockerfile | Misma versión mayor (17) y misma base → el volumen de datos es compatible sin `pg_upgrade`; suite y producción comparten binarios. Alternativa: `pgvector/pgvector:0.8.x-pg17-bookworm@sha256:…`. Pendiente de confirmar (P-01). |
| Almacenamiento vectorial | **Columna nueva `embedding vector`** (sin dimensión fija) + **`dims` generada**; la columna `vector double precision[]` se conserva y se sigue escribiendo (doble escritura) | Migración aditiva y retroceso posible a código anterior mientras la extensión exista. |
| Índice ANN | **HNSW parcial por (modelo, dimensión)** sobre la expresión `(embedding::vector(768)) vector_cosine_ops WHERE model='nomic-embed-text' AND dims=768`; dimensiones/modelos sin índice → **ruta exacta** en SQL | HNSW exige dimensión fija y admite como mucho 2.000 dims en `vector` (4.000 en `halfvec`); el esquema admite 1..4096. Qué modelos se indexan es configurable (P-02). |
| Filtrado con ANN | **Escaneo iterativo** de pgvector (`hnsw.iterative_scan = relaxed_order`, `hnsw.max_scan_tuples` acotado) con los mismos filtros de permisos/proyecto/versión vigente/hash y recomprobación final (la actual de `search_vectors`) | Evita perder resultados por post-filtrado; conserva la doble comprobación de autorización existente. |
| `candidates_truncated` | **Se conserva** en cada acierto y en `backends.semantic`; pasa a significar «la búsqueda alcanzó su tope de candidatos (ruta exacta: 10.000; ANN: `max_scan_tuples`) antes de completar `limit`» | Contrato estable; la semántica nueva se documenta. |
| FTS por idioma | **Doble vector es + en** con `unaccent` (envoltorio `IMMUTABLE`) además del `simple` actual; consulta = OR de ambas configuraciones, rango = máximo; **`pg_trgm`** sobre títulos/identificadores como respaldo cuando el FTS devuelve menos de `limit` | No exige detectar idioma por fila ni configuración por proyecto; robusto para contenido mixto. Alternativas en P-03. |
| Troceado | **Tabla nueva `memory.embedding_chunks`**; troceado por párrafos/encabezados, objetivo ~1.500 caracteres con solape ~200 (configurable); un resultado por elemento con la puntuación de su mejor fragmento | No altera la clave primaria de `memory.embeddings` (aditivo). Parámetros a confirmar (P-07). |
| Señal del fragmento | **Campo opcional `matched_chunk`** (`ordinal`, `char_start`, `char_end`) en el acierto; `excerpt` usa el texto del fragmento ganador | Adición opcional al contrato; `ref` no cambia de formato. |
| Búsqueda híbrida (P3) | **El servidor ya usa `semantic=True` por defecto** (`models.py:146`, `:181`; `mcp.py:150`, `:160`; contrato `kairos-mcp.json` `"default": true`). El trabajo es: probar y endurecer la degradación, ajustar la fusión con C-01 y decidir el `semantic: false` fijo del cliente CLI (`packages/kairos-cli/lib/dispatcher.mjs:84`) | El encargo describía `semantic` como opt-in; el código muestra lo contrario. Ver P-04. |
| Métricas | **`GET /metrics` en `memory-api` en formato de texto Prometheus**, protegido por credencial de administrador **o** solo en la red interna `memory-data`; métricas de cola/errores de proveedor derivadas de la base de datos al leerlas (el worker no expone HTTP) | Sin servicio Prometheus en `docker-compose.yml`; exposición a decidir (P-05). |

## Configuración / parámetros

| Parámetro | Clave / mecanismo | Default | Valor objetivo |
|---|---|---|---|
| Modelos/dimensiones con índice HNSW | `MEMORY_VECTOR_INDEXES` (nuevo) | — | **`nomic-embed-text:768`** |
| Tope de la ruta exacta | constante actual `10000` | 10000 | **10000** (sin cambio) |
| Escaneo iterativo HNSW | `hnsw.iterative_scan`, `hnsw.max_scan_tuples`, `hnsw.ef_search` (por transacción) | off / 20000 / 40 | **`relaxed_order` / 20000 / 100** ⚠️ ajustar con C-01 |
| Tamaño y solape de fragmento | `MEMORY_CHUNK_CHARS`, `MEMORY_CHUNK_OVERLAP` (nuevos) | — | **1500 / 200** ⚠️ ajustar con C-01 |
| Máximo de fragmentos por elemento | `MEMORY_CHUNK_MAX` (nuevo) | — | **200** (200.000 caracteres / ~1.300 efectivos ≈ 154) |
| Umbral de respaldo trigram | `pg_trgm.similarity_threshold` / `word_similarity` | 0.3 | **0.3** ⚠️ ajustar con C-01 |
| Fusión RRF | `k=60` en `retrieval.py` (constante) | 60 | **60**; pesos por capa solo si C-01 lo justifica |
| Exposición de métricas | `MEMORY_METRICS` (nuevo) | — | **`off` / `internal` / `admin`** (P-05) |
| Umbrales de calidad | `retrieval_eval/thresholds.json` (nuevo) | — | **a confirmar (P-06)** |

## Arquitectura y componentes

- **Nuevo** `memory_platform/tests/retrieval_eval/`: `dataset-v1.jsonl` (memorias sintéticas y preguntas con referencias esperadas), `fake_embeddings.py` (proveedor determinista), `run.py` (carga en PostgreSQL aislado, ejecuta `Retrieval.search` por capa y fusionado, calcula recall@1/5/10 y MRR por capa y subconjunto, escribe JSON con el hash del dataset), `thresholds.json`.
- **Refactor** `memory_platform/store.py` → módulos de dominio (p. ej. `store_auth.py` [actores, claves, permisos, proyectos, políticas], `store_ingest.py` [eventos, extracción, validación], `store_documents.py`, `store_jobs.py` [cola, arrendamientos, recibos], `store_vectors.py`, `store_graph.py` [timeline, grafo, historia, actividad, hechos nativos]); `store.py` compone `class Store(...mixins)` y reexporta los helpers. Nombres finales a criterio del plan.
- **Esquema** (`schema.sql` o migraciones de dominio, versiones nuevas en `memory.schema_versions`, todas aditivas): extensiones `vector`, `unaccent`, `pg_trgm`; columnas `embedding`/`dims` en `memory.embeddings`; tabla `memory.embedding_chunks`; columnas FTS es/en en `memory_items`, `documents` y tablas de agente/corpus que hoy usan `search_vector`; índices GIN/HNSW/trigram nuevos.
- **Reutiliza**: autorización `_require`, consulta de recursos vigentes de `_vector_candidates`, presupuesto de tiempo (`deadline` + `statement_timeout`), fusión RRF y estados de `backends` de `retrieval.py`, `scripts/deploy-memory.py` (10 fases, copia de seguridad antes de migrar) y `admin.py` (`content_manifest`, `store_fingerprints`).
- **Infraestructura**: imagen PostgreSQL con pgvector en `docker-compose.yml` (`memory-postgres`) y en el target `test` de `memory_platform/Dockerfile`.
- **Observabilidad**: módulo nuevo de métricas/logs (formateador JSON con redacción vía `privacy.py`), instrumentación en `Retrieval.search` (latencia por capa), `providers.py` (errores por código) y consulta de profundidad de cola sobre `memory.jobs`.

## Flujo (paso a paso)

1. **Ingesta** (sin cambios de contrato): evento/documento → filas canónicas → job `embed`.
2. **Worker** (C-06): trocea `title + content` → embebe cada fragmento (en lotes acotados al tiempo del job) → `complete_job` guarda en una sola transacción el vector del elemento (compatibilidad) y los fragmentos con su posición, en ambas columnas cuando aplique (C-03).
3. **Búsqueda** (`search`/`context`): autorización → capas léxicas (FTS es/en/simple + respaldo trigram, C-05) y capa semántica (HNSW o ruta exacta sobre fragmentos, mejor fragmento por elemento, C-03/C-06) en paralelo con sus plazos → fusión RRF (C-04) → aciertos con `matched_chunk` opcional.
4. **Degradación** (C-04): si el proveedor de embeddings falla, excede plazo o no hay vectores, la respuesta sigue siendo válida con resultados léxicos y `backends.semantic` lo indica.
5. **Medida** (C-01): la puerta `retrieval-eval` produce el informe y lo compara con la línea base y los umbrales.
6. **Observabilidad** (C-07): cada búsqueda emite latencia por capa; `/metrics` expone histogramas, contadores y profundidad de cola.

## Alcance

- **Dentro (esta iteración):**
  - C-01 (P13) Conjunto de evaluación versionado y script de recall@k/MRR por capa; test de calidad en rojo frente a la línea base.
  - C-02 (P11) División de `store.py` por dominio con la API pública de `Store` intacta.
  - C-03 (P1) pgvector + HNSW con migración aditiva y ruta exacta para dimensiones no indexadas; cambio de imagen PostgreSQL.
  - C-04 (P3) Búsqueda híbrida por defecto endurecida (degradación, fusión ajustada) sin cambiar el contrato de entrada.
  - C-05 (P4) FTS consciente del idioma (es/en + `unaccent`) y `pg_trgm`.
  - C-06 (P2) Troceado para embeddings con posición y señal del fragmento.
  - C-07 (P12) Logs estructurados y métricas Prometheus protegidas o internas.
- **Fuera (iniciativas 2 y 3):**
  - Puntuación por recencia/uso, `memory_feedback`, casi-duplicados, ciclo de vida, contexto de inicio de sesión, consolidación.
  - Despliegue de un servidor Prometheus/Grafana (solo se expone el endpoint).
  - Cambiar el formato de `ref`, borrar la columna `double precision[]` o la columna `search_vector` `simple`.
  - Publicación npm del cliente (bloqueada por la cuenta del publicador; ver `docs/roadmap/2026-11-06-functional-parity/tasks.md`).

## Manejo de errores

| Caso | Comportamiento |
|---|---|
| Proveedor de embeddings caído, 4xx/5xx o plazo excedido en la consulta | Resultados léxicos; `backends.semantic.status = 'unavailable'`; sin excepción hacia el cliente; latencia acotada por `embedding_query_timeout`. |
| No hay vectores del modelo activo en los proyectos pedidos | `backends.semantic.status = 'off'`; sin llamada al proveedor. |
| Plazo semántico agotado en base de datos | `semantic_deadline_exceeded` (503) dentro de la capa → capa `unavailable`, resto de capas intactas (comportamiento actual). |
| Dimensión/modelo sin índice HNSW o > 2.000 dims | Ruta exacta en SQL con tope de 10.000 candidatos y `candidates_truncated` si se alcanza. |
| Extensión `vector`/`unaccent`/`pg_trgm` no disponible al migrar | La migración falla antes de cambiar datos (transacción + bloqueo consultivo actuales); `deploy-memory.py` se detiene en la fase `migrate` con la copia de seguridad ya hecha. |
| Fallo de proveedor a mitad del troceado | El job falla/reintenta completo; no se guarda ningún fragmento parcial (escritura en una única transacción en `complete_job`). |
| Elemento editado/sustituido/borrado | Sus fragmentos y vectores antiguos no se devuelven (filtro por versión y `canonical_hash` vigentes, como hoy). |
| `/metrics` sin credencial o desde fuera de la red permitida | 401/403 o no accesible, según P-05. |

## Criterios de aceptación

Todos se comprueban en PostgreSQL aislado (`memory_platform/tests/run_postgres.py` dentro del target `test`, o la puerta congelada `frozen-source-gate.py`), nunca contra la base desplegada.

**C-01 · Evaluación (P13)**

- [ ] [GWT] CA-01 — Dado `memory_platform/tests/retrieval_eval/dataset-v1.jsonl` con ≥ 60 preguntas (≥ 20 en español, ≥ 20 en inglés, ≥ 10 con errores tipográficos o identificadores, ≥ 10 cuya respuesta está más allá del carácter 8.000 de un documento) y sus referencias esperadas, Cuando se ejecuta el script de evaluación sobre PostgreSQL aislado, Entonces escribe un JSON con recall@1, recall@5, recall@10 y MRR para cada capa (`episodic`, `documental`, `semantic`, `fused`) y cada subconjunto, más el SHA-256 del dataset.
- [ ] [GWT] CA-02 — Dado el código previo a C-03…C-06, Cuando se ejecuta la puerta `retrieval-eval` con los umbrales de `thresholds.json`, Entonces falla (rojo) al menos en los subconjuntos de idioma, errores tipográficos y documento largo, y la línea base queda registrada en `docs/roadmap/2026-11-09-retrieval-quality/testing/`.
- [ ] CA-03 — Dos ejecuciones consecutivas con el proveedor simulado producen informes idénticos salvo la marca de tiempo; el recibo registra `product_database_accessed: false` y la observación local de interfaces de red, sin afirmar «sin red» si no lo observa: ejecutada con `docker run --network=none`, `network_interfaces == ["lo"]`. *(Enmendado por el usuario el 2026-11-09, revisión de la Fase 1, intento 3; texto original: «el recibo registra `network: none`».)*

**C-02 · Refactor de `Store` (P11)**

- [ ] CA-04 — La suite backend completa pasa con el mismo resultado antes y después del refactor (177/177 o el recuento vigente, 0 fallos, 0 omitidos), con recibo de la puerta congelada en ambos momentos.
- [ ] CA-05 — Un test de superficie compara contra una instantánea tomada antes del refactor: nombres públicos y privados de `Store` (`dir(Store)` sin dunders) y `inspect.signature` de cada método idénticos; `from memory_platform.store import Store, as_dict, canonical, digest, new_id, lexical_query, clean` sigue funcionando.
- [ ] CA-06 — `memory_platform/store.py` queda como fachada (≤ 120 líneas) y ningún módulo de dominio nuevo supera 400 líneas (`wc -l`).

**C-03 · pgvector + HNSW (P1)**

- [ ] [GWT] CA-07 — Dada una base aislada en la versión de esquema actual con embeddings `double precision[]` de 2 y 768 dimensiones, Cuando se ejecuta `python -m memory_platform.admin migrate`, Entonces existe la extensión `vector` (versión ≥ 0.8.0), todas las filas de `memory.embeddings` tienen `embedding` no nulo con `dims = array_length(vector,1)`, la columna `vector` original es idéntica byte a byte (hash por fila antes/después) y `memory.schema_versions` contiene la versión nueva.
- [ ] [GWT] CA-08 — Dados ≥ 2.000 embeddings de 768 dimensiones del modelo indexado, Cuando se ejecuta la consulta de `search_vectors` con `EXPLAIN`, Entonces el plan usa el índice HNSW, y el top-10 devuelto coincide en ≥ 95 % (recall@10) con el top-10 del coseno exacto de referencia sobre las mismas filas.
- [ ] CA-09 — Las pruebas existentes de `memory_platform/tests/test_embeddings.py` pasan sin cambios en sus aserciones: lector sin permiso → `Forbidden`; elementos borrados/sustituidos/hijos con padre desfasado excluidos; otro modelo → `[]`; vector consulta de dimensión distinta → `[]`; vector cero → `[]`; filtros `categories`/`tags` respetados.
- [ ] CA-10 — Con un `deadline` ya vencido, `search_vectors` lanza `semantic_deadline_exceeded` (503); con un plazo corto aplica `statement_timeout` en la transacción (test con espía sobre `set_config`).
- [ ] CA-11 — Cada acierto semántico conserva `candidate_limit` y `candidates_truncated`, y `backends.semantic` los incluye; con vectores de dimensión no indexada (2 dims) la búsqueda devuelve resultados por la ruta exacta y, con > 10.000 candidatos, `candidates_truncated = true`.
- [ ] CA-12 — Una nueva escritura de embedding (`complete_job`) rellena tanto `vector` como `embedding` en la misma fila.
- [ ] CA-13 — `memory-postgres` (`docker-compose.yml`) y el target `test` (`memory_platform/Dockerfile`) usan la misma imagen base con digest `sha256` fijado y pgvector con versión fijada; `docker compose config` lo muestra.
- [ ] CA-14 — Ensayo de despliegue sobre una instancia aislada con datos sintéticos (nunca la desplegada): `scripts/deploy-memory.py` completa sus 10 fases con la imagen nueva, la copia de seguridad previa existe, `content_manifest().sha256` es igual antes y después de migrar, y restaurar esa copia con `admin restore` en una instancia con pgvector produce `store_fingerprints` idénticos al origen. El procedimiento de retroceso queda documentado en `docs/operations.md`.

**C-04 · Híbrida por defecto (P3)**

- [ ] [GWT] CA-15 — Dada una petición `search` sin el campo `semantic` y vectores disponibles, Cuando se ejecuta, Entonces `backends.semantic.status = 'ok'` y aparece al menos un acierto solo semántico (sin coincidencia léxica) fusionado con los léxicos.
- [ ] [GWT] CA-16 — Dado un proveedor de embeddings que devuelve 503 o excede el plazo, Cuando se llama a `search` y a `context` (HTTP y MCP), Entonces la respuesta es correcta con resultados léxicos, `backends.semantic.status = 'unavailable'` y el tiempo total ≤ `embedding_query_timeout` + 1 s.
- [ ] [GWT] CA-17 — Dado `semantic=false`, Cuando se llama a `search`, Entonces `backends.semantic.status = 'off'` y el proveedor de embeddings recibe 0 llamadas.
- [ ] CA-18 — En `retrieval-eval`, el MRR del resultado `fused` es ≥ que el de la mejor capa individual, en conjunto y por subconjunto.

**C-05 · FTS por idioma y trigram (P4)**

- [ ] [GWT] CA-19 — Dado un documento en español con «configuración de las canciones», Cuando se busca «configuracion cancion» (sin tildes, singular), Entonces el documento aparece en el top-5 de la capa `documental`.
- [ ] [GWT] CA-20 — Dada una memoria en inglés con «deployment failed», Cuando se busca «deploying fails», Entonces aparece en el top-5 de la capa `episodic`.
- [ ] [GWT] CA-21 — Dada una memoria que contiene el identificador `pg_advisory_xact_lock`, Cuando se busca «pg_advisroy_lock», Entonces aparece en el top-5 mediante el respaldo trigram.
- [ ] CA-22 — Migración aditiva: existen las columnas/índices nuevos, las columnas `search_vector` `simple` siguen presentes y consultables, y tras migrar `count(*)` de filas con la columna FTS nueva nula es 0 en cada tabla afectada.
- [ ] CA-23 — Las búsquedas de corpus de agente (`agent_store.py`), respuestas de corpus (`corpus_answers.py`) y hechos nativos (`store.search_native_facts`) usan la configuración nueva: un test por punto de llamada con una consulta sin tilde que antes no encontraba el elemento. (Los filtros del portal en `portal_store.py` según P-03.)

**C-06 · Troceado (P2)**

- [ ] [GWT] CA-24 — Dado un documento de 50.000 caracteres con una frase única hacia el carácter 40.000, Cuando el worker procesa su job `embed`, Entonces existen fragmentos con `ordinal` consecutivos cuyos intervalos `[char_start, char_end)` cubren todo el texto sin huecos y con el solape configurado, y la búsqueda semántica de esa frase devuelve el documento en el top-3 con `matched_chunk.ordinal` del fragmento que la contiene.
- [ ] CA-25 — Un elemento aparece una sola vez en los resultados aunque coincidan varios de sus fragmentos; su puntuación es la del mejor fragmento.
- [ ] CA-26 — Tras publicar una versión nueva de un documento, los fragmentos de la versión anterior no se devuelven.
- [ ] CA-27 — Si el proveedor falla en el fragmento k de n, no queda ningún fragmento de esa versión guardado y el job queda en reintento o fallido según `max_attempts`.
- [ ] CA-28 — El relleno de fragmentos para el contenido existente encola jobs `embed` solo para recursos vigentes sin fragmentos; ejecutarlo dos veces encola 0 la segunda vez.
- [ ] CA-29 — `matched_chunk` aparece como campo opcional en el contrato exportado (`scripts/export-contracts.py`) y los aciertos sin fragmento lo omiten.

**C-07 · Observabilidad (P12)**

- [ ] [GWT] CA-30 — Dada la exposición elegida en P-05, Cuando se pide `GET /metrics` sin credencial válida (modo `admin`) o desde fuera de `memory-data` (modo `internal`), Entonces se rechaza (401/403 o sin ruta); con acceso válido responde 200 `text/plain; version=0.0.4` con `kairos_retrieval_layer_seconds` (histograma, etiqueta `layer`), `kairos_jobs_queue_depth` (etiquetas `state`, `destination`) y `kairos_provider_errors_total` (etiquetas `provider`, `code`).
- [ ] CA-31 — Ninguna métrica lleva como etiqueta ids de proyecto, consultas, contenido ni credenciales: un test hace búsquedas con una consulta y un token sintéticos y comprueba que no aparecen en `/metrics` ni en los logs.
- [ ] CA-32 — Los logs de `memory-api` y `memory-worker` son JSON de una línea con `ts`, `level`, `event` y, en búsquedas, `request_id`, `layer`, `duration_ms`; los secretos sintéticos aparecen redactados.

**Transversales**

- [ ] CA-33 — Las 34 herramientas MCP siguen presentes y el contrato regenerado `docs/contracts/kairos-mcp.json` solo tiene adiciones (script de diff: 0 herramientas, campos o valores por defecto eliminados o cambiados).
- [ ] CA-34 — Ninguna migración nueva contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE` (comprobación por `grep` en la puerta) y `content_manifest().sha256` es igual antes y después de migrar.
- [ ] CA-35 — Al cerrar la iniciativa, la puerta `retrieval-eval` pasa con los umbrales acordados (P-06) y ningún subconjunto empeora más de 2 puntos de recall@5 respecto de la línea base de CA-02.
- [ ] CA-36 — La suite backend completa pasa con 0 fallos y 0 omitidos al final, y los manuales afectados (`docs/architecture.md`, `docs/configuration.md`, `docs/operations.md`) describen pgvector, FTS por idioma, troceado y métricas.

## Pruebas

- Unitarias/integración en PostgreSQL aislado (`run_postgres.py`) dentro del target `test` con pgvector: migraciones (CA-07, CA-22, CA-34), búsqueda vectorial y planes (CA-08…CA-12), FTS (CA-19…CA-23), troceado y worker con proveedor simulado (CA-24…CA-29), retrieval/degradación (CA-15…CA-17), métricas/logs con `TestClient` (CA-30…CA-32), superficie de `Store` (CA-05) y diff de contrato (CA-33).
- Puerta `retrieval-eval` con proveedor simulado (CA-01…CA-03, CA-18, CA-35) y, si se aprueba P-06, una ejecución real contra Ollama `nomic-embed-text` con el dataset sintético en base aislada.
- Ensayo de despliegue y restauración en instancia aislada (CA-14).
- Los criterios [GWT] se traducen 1:1 a casos del test-plan con el mismo ID CA-XX.

## Referencias

- `memory_platform/store.py:922` (`_vector_candidates`), `:954` (`has_vectors`), `:964` (`search_vectors`), `:855-886` (`complete_job`, embeddings), `:523-536` (`search_items`), `:560-585` (`search_documents`), `:720-737` (`search_native_facts`).
- `memory_platform/schema.sql:13` (`memory_items.search_vector`), `:27-31` (FTS de documentos), `:34-45` (`memory.embeddings`).
- `memory_platform/retrieval.py:97-146` (`search`, capa semántica, fusión RRF), `:191-208` (`context`).
- `memory_platform/worker.py:47-52` (texto `[:8000]`), `memory_platform/providers.py` (`Embeddings.embed`, `[:8000]`, `truncate: True`).
- `memory_platform/models.py:143-152`, `:178-189` (`semantic: bool = True`); `memory_platform/mcp.py:150`, `:160`; `docs/contracts/kairos-mcp.json` (`"default": true`).
- `packages/kairos-cli/lib/dispatcher.mjs:84` (`semantic: false` en el contexto automático).
- `docker-compose.yml:42` (`postgres:17-bookworm@sha256:839fbb5a…`), `memory_platform/Dockerfile:24` (target `test`).
- `scripts/deploy-memory.py:23` (fases), `memory_platform/admin.py` (`store_fingerprints`, `content_manifest`, `backup`/`restore`).
- `docs/roadmap/2026-11-06-functional-parity/tasks.md` y `testing/frozen-source-gate.py` (suite 177/177 y puerta congelada).

## Decisiones confirmadas (revisión del usuario · 2026-11-09)

Puerta go aprobada por el usuario el 2026-11-09. Decisiones:

1. **P-01 Imagen PostgreSQL**: imagen derivada de `postgres:17-bookworm@sha256:839fbb5a…` + `postgresql-17-pgvector` fijado (≥ 0.8.0).
2. **P-02 Indexado**: HNSW solo para `nomic-embed-text` de 768 dimensiones; ruta exacta en SQL para el resto de modelos/dimensiones.
3. **P-03 Idioma del FTS**: doble vector es + en con `unaccent` en cada fila, más `pg_trgm`; los filtros del portal (`portal_store.py`) también pasan a la configuración nueva.
4. **P-04 Híbrida**: el CLI pasa a `semantic: true` en su próxima versión (publicación npm sujeta al desbloqueo de la cuenta); se añade el campo opcional `degraded` cuando solo falla la capa semántica (se mantiene `partial` con su semántica actual).
5. **P-05 Métricas**: `/metrics` solo en la red interna (no publicado por nginx en 5173); se añade la dependencia `prometheus_client` fijada. `MEMORY_METRICS=internal`.
6. **P-06 Calidad**: umbrales recall@5 `fused` ≥ 0,80 y MRR ≥ 0,60, y +15 puntos de recall@5 en los subconjuntos de idioma/errores/documento largo. Se autoriza una ejecución real contra el Ollama local (`nomic-embed-text`) con datos sintéticos en base aislada; nunca contra la base desplegada.
7. **P-07 Troceado**: 1.500 caracteres con solape de 200; el relleno de fragmentos del contenido existente se lanza en el despliegue.
8. **P-08 Oráculo rojo**: el test de calidad en rojo vive en la puerta separada `retrieval-eval`; la suite de 177 pruebas debe seguir verde antes y después del refactor.
9. **Enmienda CA-03 (2026-11-09)**: el recibo de la evaluación no afirma `network: none` como constante; registra la observación local de interfaces (`/sys/class/net`) y la Verificación usa `docker run --network=none`, donde debe ser `["lo"]`. Motivo: la revisión adversarial detectó que la constante no se comprobaba y que la sonda alternativa contactaba con un tercero.

## Supuestos

- La versión mayor de PostgreSQL no cambia (17), por lo que el volumen `knowledge-graphs_memory-postgres-data` se reutiliza sin `pg_upgrade`. Lo verifica CA-14.
- El rol del DSN de migración puede ejecutar `CREATE EXTENSION` para `vector` (⚠️ verificar: `unaccent` y `pg_trgm` son extensiones de confianza desde PostgreSQL 13; `vector` puede requerir superusuario). Lo verifica CA-07 en el ensayo de CA-14 con el mismo tipo de rol.
- El volumen de datos desplegado es pequeño (2 proyectos, 21 documentos según la activación del 2026-11-09), por lo que los rellenos y la creación de índices dentro de la transacción de migración caben en la ventana de despliegue.
- Las extensiones `unaccent` y `pg_trgm` forman parte de `contrib`, incluido en la imagen oficial `postgres` (⚠️ verificar en el digest fijado).
- La calidad semántica medida con el proveedor simulado demuestra la mecánica (troceado, índice, fusión), no la calidad del modelo; esa solo se afirma con la ejecución real de P-06.
