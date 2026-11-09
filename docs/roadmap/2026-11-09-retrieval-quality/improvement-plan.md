---
design: n/a
test-plan: n/a (sin UI)
generacion:
  inicio: 2026-11-09T11:52:27Z
  fin: 2026-11-09T11:57:52Z
  fuente: medido          # medido | estimado
  tokens_reales: { entrada: 12, salida: 46710, cache_creacion: 55206, cache_lectura: 493194, respuestas: 6 }
  eur: null              # precioTokens no fiable; ejecuta la skill rates-verify
  horas_ia: 0.34
  duracion: 20m            # reloj: 5m
  ratio_usado: 300000      # default no calibrado
---

# 2026-11-09-retrieval-quality

> Plan de implementación de la iniciativa 1 de 3 de la mejora integral de Kairos, «Calidad de recuperación»: medir la recuperación (P13), dividir `store.py` (P11), pgvector/HNSW (P1), FTS por idioma (P4), troceado para embeddings (P2), híbrida endurecida y CLI (P3) y observabilidad (P12).

| | |
|---|---|
| **Fecha** | 2026-11-09 |
| **Estado** | en-progreso |
| **Tipo** | Nueva Funcionalidad / Refactor / Infra |
| **Prioridad** | Alta |
| **Solicitante** | Daycry (vía `/dev-cycle`, flujo completo) |
| **Responsable** | Daycry |
| **Spec** | [`spec.md`](spec.md) |
| **Evaluación** | [`evaluation.md`](evaluation.md) |
| **Diseño** | n/a (sin paso de diseño; las decisiones de diseño están fijadas en la spec y en «Decisiones confirmadas») |

---

## Cuadro de mando

| Métrica | Estimado | Real | Confianza |
|--------|---------|------|-----------|
| Tiempo humano | **207,6 h** (173 h base +20 %) | 0 h | Media |
| Tiempo IA (ejecución) | **31,2 h** (26 h base +20 %) (+ 7,8 h supervisión) | 0 h | Baja |
| Coste total | **10.380 €** de desarrollo + tokens IA ⚠️ verificar | 0 € | Media (desarrollo) / sin cifra (tokens) |
| Tokens IA | **~7,78 M** (in 7,13 M / out 0,65 M) | 0 | Baja |
| Multiplicador productividad | **×5,3** | — | — |
| Tareas | **38** en 8 fases | 0 hechas | — |

> **Diferencias con la evaluación (`evaluation.md`: 199,2 h · 9.960 €):** el plan hereda sus horas por característica y añade lo que las decisiones del usuario (2026-11-09) pasaron de opcional a obligatorio: filtros del portal en C-05 (+3 h base, +180 € con margen; T-16) y CLI con `semantic: true` en C-04 (+4 h base, +240 € con margen; T-29). Resultado: 166 h → 173 h base, 9.960 € → 10.380 €. Tokens: +180 k respecto de la evaluación (portal +110 k, CLI +90 k).

---

## Estimación por fase

| Fase | Tareas | Base (h) | Con margen (h) | Tokens (in / out) | Coste € (con margen) |
|------|--------|----------|----------------|-------------------|----------------------|
| 1 — Medida (C-01 · P13) | T-01…T-03 | 16 | 19,2 | 600k / 60k | 960 |
| 2 — Refactor de `store.py` (C-02 · P11) | T-04…T-06 | 14 | 16,8 | 900k / 120k | 840 |
| 3 — pgvector + HNSW (C-03 · P1) | T-07…T-12 | 32 | 38,4 | 1.200k / 90k | 1.920 |
| 4 — FTS por idioma + trigram (C-05 · P4) | T-13…T-18 | 27 | 32,4 | 1.000k / 90k | 1.620 |
| 5 — Troceado (C-06 · P2) | T-19…T-25 | 28 | 33,6 | 1.100k / 100k | 1.680 |
| 6 — Híbrida y CLI (C-04 · P3) | T-26…T-29 | 12 | 14,4 | 430k / 40k | 720 |
| 7 — Observabilidad (C-07 · P12), en paralelo | T-30…T-33 | 18 | 21,6 | 700k / 70k | 1.080 |
| 8 — Integración, revisión y activación | T-34…T-38 | 26 | 31,2 | 1.200k / 80k | 1.560 |
| **Total** | **38** | **173** | **207,6** | **7.130k / 650k** | **10.380** |

La fase 8 agrupa las líneas transversales de la evaluación: integración, documentación y activación (10 h base: T-34, T-35, T-36, T-38) y revisión de dos lentes (16 h base: T-37).

---

## Presupuesto económico

**Coste = (horas × tarifa) + coste de tokens de IA.** Todos los importes en **EUR**.

### Supuestos (ajustables)

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Tarifa de desarrollo | 50 €/h | Valor por defecto del kit (no hay `.claude/rates.json`), el mismo de la evaluación |
| Modelo IA asumido | Claude Opus (familia vigente en el ciclo) | Base de la previsión de tokens |
| Precio input | ⚠️ verificar € / 1M tokens | Sin `precioTokens` fiable; ejecuta la skill `rates-verify` |
| Precio output | ⚠️ verificar € / 1M tokens | Ídem |
| Tipo de cambio | 1 USD = 0,92 € | Valor por defecto del kit |
| Margen de contingencia | 20 % | Sobre horas base humanas e IA |
| Supervisión humana | 25 % de las horas IA | Valor por defecto; probablemente corto para T-11 y T-38 (despliegue) |
| Ratio tokens → hora IA | 300.000 tok/h | Valor por defecto **no calibrado** (no existe `docs/roadmap/CALIBRATION.md`) |

### Desglose

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 173 h × 50 €/h | 8.650 € |
| Margen de contingencia | +20 % sobre desarrollo base (34,6 h) | 1.730 € |
| Tokens IA (input) | 7,13 M tok × precio input | ⚠️ verificar |
| Tokens IA (output) | 0,65 M tok × precio output | ⚠️ verificar |
| **Total estimado (con margen)** | 10.380 € + (7,13 × P_in + 0,65 × P_out) €, con P en €/1M tokens | **10.380 € + tokens ⚠️ verificar** |

> Las horas por tarea de `tasks.md` son base (sin margen). El precio de tokens no es verificable hoy: no se inventa cifra en €.

---

## Previsión de tokens (por fase)

Base: Claude Opus · sin precio verificado, por lo que el coste en € de tokens queda ⚠️ verificar.

| Fase | Input (tok) | Output (tok) | Total (tok) | Coste € |
|------|------------|-------------|-------------|---------|
| 1 — Medida | 600k | 60k | 660k | ⚠️ verificar |
| 2 — Refactor `store.py` | 900k | 120k | 1.020k | ⚠️ verificar |
| 3 — pgvector + HNSW | 1.200k | 90k | 1.290k | ⚠️ verificar |
| 4 — FTS por idioma | 1.000k | 90k | 1.090k | ⚠️ verificar |
| 5 — Troceado | 1.100k | 100k | 1.200k | ⚠️ verificar |
| 6 — Híbrida y CLI | 430k | 40k | 470k | ⚠️ verificar |
| 7 — Observabilidad | 700k | 70k | 770k | ⚠️ verificar |
| 8 — Integración y revisión | 1.200k | 80k | 1.280k | ⚠️ verificar |
| **Total** | **7.130k** | **650k** | **7.780k** | **⚠️ verificar** |

**Método de estimación:** heredado de la evaluación por característica (ficheros a leer × tamaño medio + generación de código y tests); fase 4 suma +110 k (portal) y fase 6 suma +90 k (CLI). El reparto por tarea es proporcional a sus horas dentro de la fase y se redondea a 5k.

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 207,6 h (173 h base) |
| Horas IA (ejecución) | 31,2 h (26 h base = 7,78 M tok ÷ 300.000 tok/h) |
| Supervisión humana | 7,8 h (25 % de 31,2 h) |
| **Horas totales (IA + supervisión)** | **39,0 h** |
| Horas ahorradas | 168,6 h |
| **Ahorro** | **81,2 %** |
| **Multiplicador de productividad** | **×5,3** |
| FTE equivalentes *(opcional)* | 1,05 |

> Horas con el margen del 20 % ya aplicado. Las horas IA derivan de un ratio no calibrado (supuesto) y no incluyen el reloj de las construcciones del contenedor de pruebas, del ensayo de despliegue ni de la revisión; el plazo real del ciclo depende más de esas esperas que de los tokens. Reserva tiempo humano propio para la ventana de T-38.

---

## Resumen ejecutivo

Se planifican siete cambios para que la recuperación de Kairos sea medible y mejor: primero la puerta `retrieval-eval` con su línea base en rojo (T-01…T-03), después el refactor de `store.py` sin cambiar su API, pgvector con HNSW sobre una imagen PostgreSQL derivada, FTS es/en con `unaccent` y `pg_trgm`, troceado de documentos largos, degradación híbrida con el campo `degraded` y CLI con `semantic: true`, y métricas Prometheus solo en la red interna. Se hace para que los agentes encuentren datos que hoy no ven (más allá de 8.000 caracteres, con tildes, derivadas o con erratas) y para que cualquier mejora se pueda demostrar con cifras. Las 34 herramientas MCP y la base desplegada no se tocan hasta T-38, y solo con autorización expresa.

### Objetivos

- recall@5 de `fused` ≥ 0,80 y MRR ≥ 0,60 en `retrieval-eval`, con +15 puntos de recall@5 en los subconjuntos idioma, errores tipográficos y documento largo frente a la línea base (CA-35).
- Suite backend sin regresión: 177/177 antes y después del refactor y 0 fallos y 0 omitidos al final (CA-04, CA-36).
- pgvector ≥ 0.8.0 con HNSW solo para `nomic-embed-text:768`, recall@10 ≥ 95 % frente al exacto, con ensayo de despliegue, restauración y retroceso en instancia aislada (CA-08, CA-14).
- Contrato MCP estrictamente aditivo (34 herramientas; `matched_chunk` y `degraded` opcionales) y migraciones sin operaciones destructivas (CA-33, CA-34).

---

## Datos necesarios para un informe completo

- [x] **Requisitos funcionales** confirmados por el solicitante (spec `aprobada` y «Decisiones confirmadas» 2026-11-09)
- [x] **Alcance** cerrado (qué entra y qué NO: spec §Alcance; iniciativas 2 y 3 fuera)
- [x] **Criterios de éxito / métricas** acordados (CA-01…CA-36; umbrales de P-06)
- [ ] **Accesos y credenciales** necesarios — falta confirmar el rol del DSN de migración para `CREATE EXTENSION vector` (se comprueba en T-08/T-11) y la disponibilidad del motor Docker
- [x] **Entornos** disponibles: fixtures aislados con `run_postgres.py` y Ollama local autorizado con datos sintéticos; la base desplegada no se toca
- [x] **Stakeholders** identificados: Daycry (solicitante, aprobador de la ventana de T-38)
- [ ] **Dependencias externas** — paquete PGDG `postgresql-17-pgvector` (versión exacta a verificar en T-07); publicación npm del CLI bloqueada (fuera de plan)
- [x] **Restricciones** conocidas: migraciones aditivas, 34 herramientas MCP, nunca la base desplegada, `deploy-memory.py` como vía de despliegue
- [ ] **Tarifa/hora y supuestos de coste** confirmados — se usan los valores por defecto; precio de tokens ⚠️ verificar

---

## Análisis de impacto

- **`memory_platform/store.py`** (1.030 líneas) — se divide en mixins por dominio (T-05); queda como fachada ≤ 120 líneas.
- **`memory_platform/schema.sql`** — versiones aditivas nuevas: `vector`, `unaccent`, `pg_trgm`, columnas `embedding`/`dims`, columnas FTS es/en, tabla `memory.embedding_chunks` e índices HNSW/GIN/trigram (T-08, T-13, T-20).
- **`memory_platform/retrieval.py`**, **`models.py`**, **`mcp.py`** — estado de capas, `degraded`, `matched_chunk`, instrumentación de latencia (T-23, T-26, T-32).
- **`memory_platform/worker.py`**, **`providers.py`** — troceo, lotes de embeddings, errores por código (T-21, T-32).
- **`memory_platform/agent_store.py`**, **`corpus_answers.py`**, **`portal_store.py`** — consultas FTS con la configuración nueva (T-15, T-16).
- **`memory_platform/Dockerfile`**, **`docker-compose.yml`** — imagen PostgreSQL derivada con pgvector, target `retrieval-eval`, `memory-postgres` con `build:` (T-03, T-07, T-33).
- **`scripts/deploy-memory.py`**, **`memory_platform/admin.py`** — relleno de fragmentos y vectores en el despliegue (T-24, T-38).
- **`packages/kairos-cli/`** — `semantic: true` en `lib/dispatcher.mjs:84` y versión nueva, sin publicar (T-29).
- **`docs/`** — `architecture.md`, `configuration.md`, `operations.md`, `integration.md`, contratos regenerados (T-12, T-25, T-28, T-34, T-35).
- **Sin interfaz web**: los filtros del portal cambian solo en backend; no se modifica nada de `web/`.

---

## Cambios arquitectónicos

- **Puerta `retrieval-eval` separada** de la suite de 177 tests (P-08): el oráculo de calidad nace en rojo sin romper la suite que debe estar verde antes y después del refactor.
- **Mixins por dominio** con `store.py` como fachada: conserva `from memory_platform.store import Store, …` y `patch.object(store, '_require')`.
- **Imagen derivada única** (etapa `postgres-pgvector` del Dockerfile) para producción y suite: mismas versión mayor (17) y base, por lo que el volumen sirve sin `pg_upgrade`.
- **Almacenamiento vectorial aditivo**: columna `embedding vector` + `dims` generada, doble escritura y `vector double precision[]` intacta (retroceso posible mientras la extensión exista).
- **HNSW parcial solo para `nomic-embed-text:768`** (`MEMORY_VECTOR_INDEXES`) con escaneo iterativo; ruta exacta SQL (tope 10.000) para el resto.
- **FTS doble es + en** con `unaccent` (envoltorio `IMMUTABLE`) además del `simple`, consulta OR con rango máximo y respaldo `pg_trgm`; incluye `portal_store.py`.
- **Troceado** 1.500/200 en `memory.embedding_chunks` con un resultado por elemento (mejor fragmento) y `matched_chunk` opcional; relleno idempotente en el despliegue.
- **Degradación visible**: campo opcional `degraded` cuando solo falla la capa semántica; `partial` conserva su semántica.
- **`/metrics` solo en red interna** (`MEMORY_METRICS=internal`) con `prometheus_client` fijado; sin Prometheus/Grafana en el compose.

---

## Archivos a crear/modificar

| Archivo | Acción | Propósito |
|---------|--------|-----------|
| `memory_platform/tests/retrieval_eval/` (`dataset-v1.jsonl`, `fake_embeddings.py`, `run.py`, `thresholds.json`, `check_dataset.py`) | Crear | Dataset, proveedor simulado, métricas y puerta |
| `memory_platform/tests/run_postgres.py` | Modificar | Modo `MEMORY_RETRIEVAL_EVAL=1` |
| `memory_platform/store.py` + `store_auth.py`, `store_ingest.py`, `store_documents.py`, `store_jobs.py`, `store_vectors.py`, `store_graph.py`, `store_common.py` | Modificar / Crear | División por dominio (nombres finales a criterio del implementador) |
| `memory_platform/schema.sql` | Modificar | Versiones aditivas (vector, FTS, fragmentos) |
| `memory_platform/chunking.py` | Crear | Troceador |
| `memory_platform/observability.py` | Crear | Logs JSON, métricas |
| `memory_platform/retrieval.py`, `models.py`, `mcp.py`, `worker.py`, `providers.py`, `config.py`, `app.py`, `admin.py` | Modificar | Capas, campos opcionales, lotes, métricas, relleno |
| `memory_platform/agent_store.py`, `corpus_answers.py`, `portal_store.py` | Modificar | FTS con configuración nueva |
| `memory_platform/Dockerfile`, `docker-compose.yml`, `memory_platform/nginx.conf`, `memory_platform/Caddyfile.example`, `memory_platform/requirements.txt` | Modificar | Imagen con pgvector, target `retrieval-eval`, bloqueo de `/metrics`, `prometheus_client` |
| `scripts/deploy-memory.py`, `scripts/export-contracts.py` | Modificar | Relleno en despliegue; contrato regenerado |
| `packages/kairos-cli/lib/dispatcher.mjs`, `package.json`, tests y docs de release | Modificar | `semantic: true`, versión 0.3.0 sin publicar |
| `memory_platform/tests/test_*.py` nuevos (superficie, migraciones, FTS, troceo, métricas, contrato) | Crear | Pruebas en rojo por clase de cambio |
| `docs/architecture.md`, `configuration.md`, `operations.md`, `integration.md`, `docs/contracts/*` | Modificar | Documentación y contratos |
| `docs/roadmap/2026-11-09-retrieval-quality/testing/` | Crear | Evidencias: línea base, recibos, ensayos, informes finales |

Sin `agents/`, `commands/` ni `hooks/` en este proyecto: no aplica `interop/**`.

---

## Dependencias y prerequisitos

Orden: T-01 → T-02 → T-03 → T-04 → T-05 → T-06 → T-07 → … (cadena de fases 1-6) y fase 8 al final.

| Tarea | Depende de |
|-------|-----------|
| T-02, T-03 | T-01, T-02 |
| T-04, T-05, T-06 | T-03, T-04, T-05 |
| T-07 → T-12 | T-06, luego en cadena (T-08←T-07, T-09←T-08, T-10←T-09, T-11←T-10, T-12←T-11) |
| T-13 | T-12 (técnicamente solo T-06/T-07) |
| T-14, T-15, T-16 | T-13 |
| T-17 | T-14 |
| T-18 | T-14, T-15, T-16, T-17 |
| T-19 | T-18 (técnicamente independiente) |
| T-20 | T-19, T-08 |
| T-21 | T-19 |
| T-22 | T-20, T-21 |
| T-23 | T-22, T-09 |
| T-24 | T-22 |
| T-25 | T-23 |
| T-26 | T-25 |
| T-27 | T-26, T-03 |
| T-28, T-29 | T-26 |
| **T-30 → T-33 (fase 7, paralelo)** | T-30←T-06, T-31←T-30, T-32←T-31, T-33←T-31 y T-32 |
| T-34 | T-12, T-18, T-25, T-28, T-29, T-33 |
| T-35 | T-25, T-26, T-33 |
| T-36 | T-27, T-23 |
| T-37 | T-34, T-35, T-36 |
| T-38 | T-37 y autorización expresa del usuario |

- Bloqueo externo (fuera de plan): la publicación npm del CLI (F-06 del plan 2026-11-06). T-29 sube la versión y no publica.
- Requiere motor Docker accesible (T-03, T-07, T-11, T-38).

---

## Criterios de aceptación (global)

- [ ] La puerta `retrieval-eval` falla en la línea base (CA-02) y pasa al cierre con recall@5 `fused` ≥ 0,80, MRR ≥ 0,60 y +15 puntos en idioma/errores/documento largo; ningún subconjunto empeora más de 2 puntos (CA-35).
- [ ] Suite backend 177/177 antes y después del refactor; al final 0 fallos y 0 omitidos (CA-04, CA-36).
- [ ] `store.py` ≤ 120 líneas, módulos ≤ 400 y superficie de `Store` idéntica a la instantánea (CA-05, CA-06).
- [ ] pgvector ≥ 0.8.0, HNSW con recall@10 ≥ 95 % y ruta exacta para el resto; `docker compose config` muestra imagen con digest y versión fijados (CA-07…CA-13).
- [ ] Ensayo de despliegue/restauración y procedimiento de retroceso en instancia aislada (CA-14).
- [ ] FTS es/en y trigram cumplen CA-19…CA-23, incluido el portal (P-03).
- [ ] Troceado, `matched_chunk` y relleno idempotente cumplen CA-24…CA-29.
- [ ] Degradación probada por HTTP y MCP con `degraded` opcional (CA-15…CA-17) y MRR `fused` ≥ mejor capa (CA-18).
- [ ] `/metrics` solo interno y sin fuga de datos; logs JSON redactados (CA-30…CA-32).
- [ ] Contrato aditivo con 34 herramientas y migraciones sin DROP/TRUNCATE/DELETE/ALTER TYPE (CA-33, CA-34).
- [ ] CLI con `semantic: true` en versión nueva, sin publicar en npm.
- [ ] La base desplegada no se ha tocado salvo T-38 con autorización expresa.

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| R-01 Retroceso asimétrico de la imagen PostgreSQL | Media | Alto | Doble escritura en `double precision[]`, misma versión mayor 17, ensayo y retroceso documentado (T-07, T-11, T-12) |
| R-02 Orden de fases del despliegue (copia de seguridad tras arrancar la imagen nueva) | Media | Medio | Mismo formato de datos PG 17; manifiesto antes/después en T-11 y T-38 |
| R-03 Privilegios de `CREATE EXTENSION vector` | Media | Alto | Comprobar el rol en T-08 y en el ensayo T-11; alternativa de paso de operador previo a `migrate` |
| R-04 Recall del ANN con filtros y límites de dimensión | Media | Medio | Escaneo iterativo, ruta exacta, CA-08 contra el exacto (T-09, T-10) |
| R-05 Carga de reindexado y plazos del worker | Alta | Medio | Lotes con plazo, `MEMORY_CHUNK_MAX`, relleno idempotente en despliegue (T-21, T-24) |
| R-06 Migraciones con reescritura de tabla | Baja | Medio | Volumen pequeño, `lock_timeout`, CA-34 (T-08, T-13, T-20) |
| R-07 Medida sesgada o irreal | Media | Medio | Dataset congelado con hash antes de C-03 (T-03); ejecución real con Ollama (T-36) |
| R-08 Fuga de datos en observabilidad | Baja | Alto | Etiquetas cerradas, redacción con `privacy.py`, tests CA-31/CA-32 (T-30, T-33) |
| R-09 Contrato MCP: clientes estrictos ante campos nuevos | Baja | Medio | Solo campos opcionales y diff aditivo (T-25, T-26, T-35) |
| R-10 Tocar la base desplegada por error | Baja | Alto | Fixtures aislados, salvaguarda de DSN en el cargador, T-38 solo con autorización expresa |
| R-11 Latencia del CLI con `semantic: true` si Ollama está lento | Media | Medio | Tiempo máximo `embedding_query_timeout` + 1 s probado en T-26 y T-29; `degraded` visible |

---

## Métricas de éxito

- Recall@5 `fused` y MRR en el informe de `retrieval-eval` frente a `testing/baseline.json` (cifras de CA-35).
- Recall@10 del HNSW frente al coseno exacto ≥ 95 % (`testing/hnsw-recall.json`).
- Latencia por capa disponible en `/metrics` y cola de jobs a 0 tras el relleno del despliegue.
- Cero herramientas, campos o valores por defecto eliminados del contrato; 34 herramientas MCP presentes.

---

## Changelog del plan

| Fecha | Cambio | Autor |
|-------|--------|-------|
| 2026-11-09 | Creación del plan (38 tareas en 8 fases) heredando horas de la evaluación; añade portal (+3 h) y CLI (+4 h) por las decisiones P-03 y P-04 | planner |

---

## Siguiente paso

Con el **OK del plan** del usuario (puerta de control), el agente **`implementer`** lo ejecuta fase a fase sobre la rama `feat/retrieval-quality`, marcando `tasks.md` como **ledger canónico** (checkbox + estado por tarea). Al terminar, handoff a `qa` y cierre con `documenter`; con `test-plan: n/a (sin UI)` en el frontmatter, `qa` corre sus puertas deterministas y sale limpio sin pedir test-plan (ADR-017).
