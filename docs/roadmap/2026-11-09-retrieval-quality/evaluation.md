---
generacion:
  inicio: 2026-11-09T11:34:20Z
  fin: 2026-11-09T11:43:21Z
  fuente: medido
  tokens_reales: { entrada: 46, salida: 46548, cache_creacion: 94919, cache_lectura: 1394493, respuestas: 23 }
  eur: null              # precioTokens no fiable; ejecuta la skill rates-verify
  horas_ia: 0.47
  duracion: 28m            # reloj: 9m
  ratio_usado: 300000      # default no calibrado
---

# 2026-11-09-retrieval-quality

> Evaluación de coste y conveniencia de la iniciativa 1 de 3 de la mejora integral de Kairos, «Calidad de recuperación» (P13, P11, P1, P3, P4, P2, P12), para decidir si se planifica y en qué orden.

| | |
|---|---|
| **Fecha** | 2026-11-09 |
| **Estado** | completado |
| **Prioridad global** | Alta |
| **Solicitante** | Daycry (vía `/dev-cycle`, flujo completo) |
| **Spec** | [`spec.md`](spec.md) |
| **Plan** | [`improvement-plan.md`](improvement-plan.md) |
| **Características evaluadas** | 7 |

---

## Cuadro de mando

| Métrica | Total estimado | Confianza |
|--------|----------------|-----------|
| Esfuerzo humano equivalente | **199,2 h** (166 h base +20 %) | Media |
| Tiempo IA (ejecución) | **30,3 h** (25,3 h base +20 %) (+ 7,6 h supervisión) | Baja |
| Coste | **9.960 €** de desarrollo + tokens IA ⚠️ verificar | Media (desarrollo) / sin cifra (tokens) |
| Tokens IA facturables | **~7,6 M** (in 6,95 M / out 0,63 M) | Baja |
| Multiplicador productividad | **×5,3** | — |
| Características | **7** (+ líneas de integración y revisión) | — |

> Horas humanas (lo que vale el trabajo) y horas-IA (lo que tarda el ciclo) se presentan por separado y no se suman (doctrina LES-007). En el histórico del kit las horas-IA se desviaron entre −77 % y −96 %; aquí su confianza es Baja.

---

## Resumen ejecutivo

Se presupuestan siete cambios para que la recuperación de Kairos sea medible y mejor: conjunto de evaluación (C-01), refactor de `store.py` (C-02), pgvector/HNSW (C-03), híbrida por defecto (C-04), FTS por idioma con trigram (C-05), troceado para embeddings (C-06) y observabilidad (C-07). El total es de **199,2 h humanas equivalentes (9.960 € con margen)** más tokens IA (sin cifra en € porque no hay precio de tokens verificado), con **~30 h de ejecución IA**. Las dos partidas caras y arriesgadas son C-03 (cambio de imagen PostgreSQL + migración de vectores) y C-06 (troceado + reindexado). El reconocimiento del código ha encontrado que **P3 ya está activo en el servidor** (`semantic` vale `True` por defecto), lo que rebaja C-04 a un endurecimiento barato. Veredicto: **go condicionado** a cerrar las preguntas P-01 (imagen), P-03 (idioma), P-05 (métricas), P-06 (umbrales) y P-08 (oráculo rojo).

---

## Requerimientos recibidos

Mapa del encargo (spec §Alcance) a las características evaluadas.

| ID | Característica | Requisito origen (ref.) | ¿Claro? |
|----|---------------|-------------------------|---------|
| C-01 | Conjunto de evaluación + recall@k/MRR por capa | P13 · spec §Alcance, CA-01…CA-03 | Sí; faltan umbrales (P-06) |
| C-02 | División de `store.py` por dominio | P11 · spec CA-04…CA-06 | Sí |
| C-03 | pgvector + HNSW sustituyendo el coseno en Python | P1 · spec CA-07…CA-14 | Ambiguo: imagen (P-01) e indexado por modelo/dimensión (P-02) |
| C-04 | Híbrida léxica + semántica por defecto con degradación | P3 · spec CA-15…CA-18 | Ambiguo: la premisa «hoy opt-in» no coincide con el código (P-04) |
| C-05 | FTS por idioma (es/en, `unaccent`) + `pg_trgm` | P4 · spec CA-19…CA-23 | Ambiguo: estrategia de idioma y alcance del portal (P-03) |
| C-06 | Troceado de documentos/notas largas para embeddings | P2 · spec CA-24…CA-29 | Parcial: tamaño/solape y ventana de reindexado (P-07) |
| C-07 | Logs estructurados + métricas Prometheus | P12 · spec CA-30…CA-32 | Ambiguo: exposición y consumidor (P-05) |

**Ambigüedades / información que falta:**

- **P3 ya está activo**: `models.py:146` y `:181` (`semantic: bool = True`), `mcp.py:150`/`:160` y el contrato (`"default": true`). Quien lo desactiva es el cliente CLI (`packages/kairos-cli/lib/dispatcher.mjs:84`, `semantic: false` en el contexto automático). Cambiar el CLI exige una versión npm nueva, hoy bloqueada por la cuenta del publicador. Se presupuesta solo la parte de servidor; el CLI es opcional (+4 h).
- **Oráculo rojo vs. suite verde**: el encargo pide un test de calidad en rojo (P13) y la misma suite verde antes y después de P11. Se presupone una puerta `retrieval-eval` separada (P-08).
- **Privilegios de extensión**: no consta qué rol usa el DSN de migración; `CREATE EXTENSION vector` puede requerir superusuario (⚠️ verificar).
- **Dimensiones**: el esquema admite 1..4096; HNSW de pgvector indexa como máximo 2.000 dims (`vector`) o 4.000 (`halfvec`). Por encima → solo ruta exacta.
- **Consumidor de métricas**: no hay Prometheus en `docker-compose.yml`; se presupuesta solo el endpoint.

---

## Datos necesarios para una evaluación completa

- [x] **Requerimientos** completos y sin ambigüedades — completos en alcance; las ambigüedades están listadas arriba y en la spec (P-01…P-08)
- [x] **Alcance** de cada característica acotado (qué entra y qué NO)
- [x] **Criterios de aceptación / éxito** por característica (CA-01…CA-36 en la spec)
- [ ] **Restricciones** — confirmadas (aditivo, 34 herramientas MCP, `deploy-memory.py`, nunca la BD desplegada); **falta** plazo y umbrales de calidad (P-06)
- [ ] **Dependencias externas** — imagen/paquete pgvector (P-01), Ollama para la evaluación real (P-06), publicación npm si se toca el CLI (P-04)
- [x] **Contexto técnico** del proyecto (stack, integraciones) disponible — reconocimiento del repositorio hecho
- [ ] **Tarifa/hora y supuestos de coste** — sin `.claude/rates.json`; se usan los valores por defecto y el precio de tokens queda ⚠️ verificar

---

## Supuestos económicos (ajustables)

**Coste = (horas × tarifa) + coste de tokens de IA.** Importes en **EUR**.

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Tarifa de desarrollo | 50 €/h | Valor por defecto del kit (no hay `.claude/rates.json`) |
| Modelo IA asumido | Claude Opus (familia vigente en el ciclo) | Base de la previsión de tokens |
| Precio input | ⚠️ verificar € / 1M tokens | Sin `precioTokens` fiable; ejecuta la skill `rates-verify` |
| Precio output | ⚠️ verificar € / 1M tokens | Ídem |
| Tipo de cambio | 1 USD = 0,92 € | Valor por defecto del kit |
| Margen de contingencia | 20 % | Sobre horas base humanas e IA |
| Supervisión humana | 25 % de las horas IA | Valor por defecto; probablemente corto para el despliegue de C-03 (ver riesgos) |
| Ratio tokens→hora IA | 300.000 tok/h facturables | Valor por defecto **no calibrado** (no existe `docs/roadmap/CALIBRATION.md`) |
| Tokens facturables | entrada no cacheada + creación de caché + salida | La lectura de caché no cuenta |

**Método de esfuerzo humano**: estimación por componentes sobre el código leído (puntos de llamada contados con `grep`, tamaño de los módulos, tests existentes que tocan cada área), como *mid-point* realista sin colchón; el margen se aplica después. **Calibración**: no hay histórico del proyecto (`docs/knowledge/` solo contiene `candidates/pending`); se aplican las lecciones de doctrina LES-001/LES-009 (la revisión es la partida grande → línea propia), LES-005 (código con TDD → ejecución más cara, revisión más barata) y LES-008 (coste de proceso aparte).

---

## Evaluación por característica

### C-01 — Conjunto de evaluación de recuperación (P13)

- **Requisito origen**: P13; spec CA-01…CA-03, CA-35.
- **Descripción**: dataset sintético versionado (≥ 60 preguntas es/en, errores tipográficos, identificadores, documentos largos), proveedor de embeddings simulado determinista, script que carga en PostgreSQL aislado y mide recall@1/5/10 y MRR por capa y fusionado, línea base registrada y puerta `retrieval-eval` en rojo.
- **Complejidad**: Media.
- **Esfuerzo**: 16 h base (19,2 h con margen) · confianza Media. Desglose: dataset y referencias esperadas 6 h, proveedor simulado + cargador 3 h, métricas e informe 3 h, puerta y línea base 2 h, tests del propio script 2 h.
- **Previsión IA**: 600 k in / 60 k out tok (2,2 h IA base) · ⚠️ verificar €.
- **Coste**: (19,2 h × 50 €/h) + tokens = **960 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/tests/retrieval_eval/` (nuevo), `memory_platform/tests/run_postgres.py` (modo nuevo), `docs/roadmap/2026-11-09-retrieval-quality/testing/`.
- **Dependencias y prerequisitos**: ninguna; es la base de todas las demás.
- **Riesgos**: un dataset escrito por quien implementa puede sesgarse a favor de la solución (mitigación: congelar `dataset-v1` y su hash antes de C-03); el proveedor simulado no mide la calidad del modelo real.
- **Incógnitas / preguntas abiertas**: P-06 (umbrales y ejecución real con Ollama), P-08 (puerta separada).

### C-02 — División de `store.py` por dominio (P11)

- **Requisito origen**: P11; spec CA-04…CA-06.
- **Descripción**: dividir la clase monolítica `Store` (1.030 líneas, ~75 KB, ~65 métodos) en mixins por dominio (auth/proyectos, ingesta, documentos, trabajos, vectores, grafo/timeline) con `store.py` como fachada que conserva la API y los helpers reexportados.
- **Complejidad**: Media.
- **Esfuerzo**: 14 h base (16,8 h con margen) · confianza Alta. Desglose: instantánea de superficie + test CA-05 2 h, movimiento por dominios 7 h, imports cruzados y helpers 2 h, ejecuciones de suite congelada 3 h.
- **Previsión IA**: 900 k in / 120 k out tok (3,4 h IA base) · ⚠️ verificar €.
- **Coste**: (16,8 h × 50 €/h) + tokens = **840 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/store.py` y módulos nuevos; importadores: `app.py`, `admin.py`, `agent_store.py`, `extended_store.py`, `portal_store.py`, `corpus_answers.py`, `agent_tools.py`, `worker.py` y 17 módulos de test que importan desde `store`; la puerta `frozen-source-gate.py` (cambia la lista de ficheros del manifiesto).
- **Dependencias y prerequisitos**: C-01 recomendado antes (no bloqueante).
- **Riesgos**: regresiones sutiles por orden de resolución de métodos o helpers privados compartidos (`_require`, `_item`, `_jobs`); tests que parchean `_require` sobre la instancia (`patch.object(self.store,'_require')`) siguen funcionando con mixins.
- **Incógnitas / preguntas abiertas**: ninguna bloqueante; nombres de módulos a criterio del plan.

### C-03 — pgvector + HNSW (P1)

- **Requisito origen**: P1; spec CA-07…CA-14.
- **Descripción**: imagen PostgreSQL con pgvector (producción y target `test`), migración aditiva (`CREATE EXTENSION vector`, columna `embedding vector` + `dims` generada, relleno desde `double precision[]`, HNSW parcial por modelo/dimensión), reescritura de `search_vectors`/`_vector_candidates`/`has_vectors` con escaneo iterativo y ruta exacta para dimensiones no indexadas, doble escritura en `complete_job`, conservando permisos, versión vigente, hash, `deadline` y `candidates_truncated`; ensayo de despliegue y restauración y procedimiento de retroceso.
- **Complejidad**: Alta.
- **Esfuerzo**: 32 h base (38,4 h con margen) · confianza Media. Desglose: imagen + Dockerfile + compose + digest 4 h, migración y relleno 5 h, consulta ANN + iterativa + ruta exacta + recomprobación 8 h, tests (planes `EXPLAIN`, recall frente a exacto, tests existentes) 7 h, ensayo de despliegue/restauración aislado 5 h, retroceso y documentación operativa 3 h.
- **Previsión IA**: 1,2 M in / 90 k out tok (4,3 h IA base) · ⚠️ verificar €.
- **Coste**: (38,4 h × 50 €/h) + tokens = **1.920 € + tokens**.
- **Impacto / áreas afectadas**: `docker-compose.yml` (`memory-postgres`), `memory_platform/Dockerfile` (target `test` y derivados `live-probe`, `lifecycle-test`), `memory_platform/schema.sql` o módulo de migración, `store.py` (o el mixin de vectores tras C-02), `retrieval.py` (estado `backends.semantic`), `memory_platform/tests/test_embeddings.py`, `docs/operations.md`.
- **Dependencias y prerequisitos**: C-02 (reduce conflicto en `store.py`); decisión P-01 (imagen) y P-02 (indexado).
- **Riesgos**: ver «Riesgos transversales» R-01…R-04 (retroceso asimétrico de imagen, privilegios de extensión, pérdida de recall por filtrado, límite de dimensiones).
- **Incógnitas / preguntas abiertas**: P-01, P-02; rol del DSN de migración (⚠️ verificar); versión exacta de pgvector disponible en PGDG para bookworm/PG17 en el digest fijado (⚠️ verificar).

### C-04 — Híbrida por defecto con degradación (P3)

- **Requisito origen**: P3; spec CA-15…CA-18.
- **Descripción**: el servidor ya ejecuta la capa semántica por defecto. El trabajo restante es fijar con tests la degradación (proveedor caído, plazo, sin vectores), evitar la consulta extra de `has_vectors` en cada búsqueda si C-03 lo permite, y ajustar la fusión RRF con los datos de C-01. Opcional: retirar `semantic: false` del contexto automático del CLI.
- **Complejidad**: Baja.
- **Esfuerzo**: 8 h base (9,6 h con margen) · confianza Media. Desglose: tests de degradación HTTP/MCP 3 h, ajuste de fusión guiado por C-01 3 h, documentación de `backends` 2 h. **Opcional CLI**: +4 h base (+4,8 h con margen, +240 €), no incluido en el total.
- **Previsión IA**: 350 k in / 30 k out tok (1,3 h IA base) · ⚠️ verificar €.
- **Coste**: (9,6 h × 50 €/h) + tokens = **480 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/retrieval.py`, `memory_platform/tests/test_retrieval.py`, `test_api.py`, `test_mcp.py`; opcional `packages/kairos-cli/lib/dispatcher.mjs`.
- **Dependencias y prerequisitos**: C-01 (medida), mejor tras C-03, C-05 y C-06 (las señales que se fusionan).
- **Riesgos**: activar la semántica en el contexto automático del CLI añade hasta `embedding_query_timeout` (10 s) de latencia al inicio de cada turno si Ollama está lento; `partial: true` cuando solo falla la semántica puede alarmar a clientes.
- **Incógnitas / preguntas abiertas**: P-04.

### C-05 — FTS por idioma + `pg_trgm` (P4)

- **Requisito origen**: P4; spec CA-19…CA-23.
- **Descripción**: extensiones `unaccent` y `pg_trgm`, envoltorio `IMMUTABLE` de `unaccent` (requisito de las columnas generadas), columnas FTS es/en nuevas (generadas en `documents`; calculadas en la inserción y rellenadas en `memory_items`, que hoy no es generada), índices GIN y trigram, y adaptación de los puntos de consulta.
- **Complejidad**: Alta.
- **Esfuerzo**: 24 h base (28,8 h con margen) · confianza Media. Desglose: migración + envoltorio + relleno 5 h, `store` (ítems, documentos, hechos nativos, 2 inserciones) 6 h, `agent_store.py` (3 consultas) y `corpus_answers.py` (1) 4 h, respaldo trigram y fusión de rangos 3 h, tests por punto de llamada 6 h. Si P-03 incluye `portal_store.py` (5 filtros): +3 h.
- **Previsión IA**: 900 k in / 80 k out tok (3,3 h IA base) · ⚠️ verificar €.
- **Coste**: (28,8 h × 50 €/h) + tokens = **1.440 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/schema.sql`, `store.py:342`, `:437`, `:533-535`, `:572-579`, `:734`; `agent_store.py:213`, `:329-331`, `:366`; `corpus_answers.py:180-181`; opcional `portal_store.py:42-79`.
- **Dependencias y prerequisitos**: C-02 recomendado; P-03.
- **Riesgos**: `unaccent` no es `IMMUTABLE` y rompe columnas generadas si no se envuelve; `ALTER TABLE … ADD COLUMN … GENERATED STORED` reescribe la tabla (bloqueo; volumen pequeño hoy); el stemming puede bajar la precisión en identificadores (de ahí el trigram y conservar `simple`).
- **Incógnitas / preguntas abiertas**: P-03.

### C-06 — Troceado para embeddings (P2)

- **Requisito origen**: P2; spec CA-24…CA-29.
- **Descripción**: troceador por párrafos/encabezados con solape; tabla `memory.embedding_chunks` con posición y vector pgvector (+ HNSW parcial como C-03); worker que embebe por lotes dentro del plazo del job; `complete_job` transaccional con todos los fragmentos; búsqueda que agrega por elemento (mejor fragmento) y devuelve `matched_chunk`; relleno idempotente del contenido existente; contrato aditivo.
- **Complejidad**: Alta.
- **Esfuerzo**: 28 h base (33,6 h con margen) · confianza Media-Baja. Desglose: troceador + tests de cobertura 4 h, esquema + índice 3 h, worker/proveedor por lotes y plazos 6 h, `complete_job` y recibos 3 h, búsqueda agregada + `matched_chunk` + `excerpt` 5 h, relleno idempotente 3 h, contrato + tests 4 h.
- **Previsión IA**: 1,1 M in / 100 k out tok (4,0 h IA base) · ⚠️ verificar €.
- **Coste**: (33,6 h × 50 €/h) + tokens = **1.680 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/worker.py:47-52`, `providers.py` (`Embeddings.embed`: una entrada por petición), `store.py` (`complete_job`, vectores), `retrieval.py`, `models.py` (`Hit`), `docs/contracts/kairos-mcp.json`, `scripts/export-contracts.py`, `test_worker.py`, `test_embeddings.py`, `test_jobs.py`.
- **Dependencias y prerequisitos**: C-03 (tipo `vector` e índice); C-01 para ajustar tamaño/solape.
- **Riesgos**: un documento de 200.000 caracteres son ~150 fragmentos; con el semáforo de 1 petición y 120 s de plazo por job no cabe sin lotes (R-05); reindexar todo el contenido existente carga Ollama durante el despliegue; el almacenamiento crece ~N veces.
- **Incógnitas / preguntas abiertas**: P-07.

### C-07 — Logs estructurados y métricas (P12)

- **Requisito origen**: P12; spec CA-30…CA-32.
- **Descripción**: logging JSON con redacción (reutilizando `privacy.py`) e `request_id`; métricas de latencia por capa en `Retrieval.search`, errores de proveedor por código, profundidad de cola leída de `memory.jobs` al servir `/metrics`; endpoint protegido o interno.
- **Complejidad**: Media.
- **Esfuerzo**: 18 h base (21,6 h con margen) · confianza Media. Desglose: logging JSON + redacción 4 h, registro de métricas + formato 4 h, instrumentación de capas/proveedores/worker 4 h, endpoint + protección 2 h, tests (no fuga de datos, formato, acceso) 4 h.
- **Previsión IA**: 700 k in / 70 k out tok (2,6 h IA base) · ⚠️ verificar €.
- **Coste**: (21,6 h × 50 €/h) + tokens = **1.080 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/app.py`, `retrieval.py`, `providers.py`, `worker.py`, `config.py`, `requirements.txt` (si `prometheus_client`), `nginx.conf`/`Caddyfile.example` (si la exposición es interna), `docker-compose.yml`.
- **Dependencias y prerequisitos**: ninguna dura; en paralelo desde C-02 (instrumenta los módulos ya divididos).
- **Riesgos**: fuga de ids de proyecto o consultas en etiquetas (privacidad y cardinalidad); varios procesos uvicorn exigirían modo multiproceso de métricas.
- **Incógnitas / preguntas abiertas**: P-05.

### Líneas transversales (no son características, pero se presupuestan aparte)

| Línea | Base | Con margen | Coste | Tokens (in/out) | Motivo |
|---|---|---|---|---|---|
| Integración, documentación y activación | 10 h | 12 h | 600 € | 400 k / 40 k | Manuales (`architecture`, `configuration`, `operations`), contrato regenerado, despliegue real con `deploy-memory.py` y verificación |
| Revisión de dos lentes y correcciones | 16 h | 19,2 h | 960 € | 800 k / 40 k | LES-001/LES-009: la revisión es la partida grande en código de producto; LES-005 la abarata algo por TDD |
| Proceso (spec + evaluación + plan) | — | — | tokens | medido en `generacion:` | LES-008: coste de proceso aparte; esta evaluación lo mide en su frontmatter |

---

## Comparativa

Ordenada por el orden de trabajo recomendado.

| # | Característica | Complejidad | Horas (con margen) | Coste € (desarrollo) | Tokens | Prioridad | Confianza |
|---|---------------|-------------|-------|---------|--------|-----------|-----------|
| C-01 | Conjunto de evaluación (P13) | Media | 19,2 h | 960 € | 660 k | Crítica | Media |
| C-02 | Refactor `store.py` (P11) | Media | 16,8 h | 840 € | 1.020 k | Alta | Alta |
| C-03 | pgvector + HNSW (P1) | Alta | 38,4 h | 1.920 € | 1.290 k | Alta | Media |
| C-05 | FTS por idioma + trigram (P4) | Alta | 28,8 h | 1.440 € | 980 k | Alta | Media |
| C-06 | Troceado (P2) | Alta | 33,6 h | 1.680 € | 1.200 k | Alta | Media-Baja |
| C-04 | Híbrida por defecto (P3) | Baja | 9,6 h | 480 € | 380 k | Media | Media |
| C-07 | Observabilidad (P12) | Media | 21,6 h | 1.080 € | 770 k | Media | Media |
| — | Integración, docs y activación | — | 12 h | 600 € | 440 k | — | Media |
| — | Revisión de dos lentes | — | 19,2 h | 960 € | 840 k | — | Media |
| | **Total** | | **199,2 h** | **9.960 €** | **7.580 k** | | |

---

## Presupuesto total

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 166 h × 50 €/h | 8.300 € |
| Margen de contingencia | +20 % sobre desarrollo base (33,2 h) | 1.660 € |
| Tokens IA (input) | 6,95 M tok × precio input | ⚠️ verificar |
| Tokens IA (output) | 0,63 M tok × precio output | ⚠️ verificar |
| **Total estimado (con margen)** | 9.960 € + (6,95 × P_in + 0,63 × P_out) €, con P en €/1M tokens | **9.960 € + tokens ⚠️ verificar** |

> Opcionales fuera del total: retirar `semantic: false` del CLI (+240 €, sujeto a poder publicar en npm) e incluir los filtros del portal en C-05 (+180 €).

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 199,2 h (166 h base) |
| Horas IA (ejecución) | 30,3 h (25,3 h base = 7,58 M tokens facturables ÷ 300.000 tok/h) |
| Supervisión humana | 7,6 h (25 % de 30,3 h) |
| **Horas totales (IA + supervisión)** | **37,9 h** |
| Horas ahorradas | 161,3 h |
| **Ahorro** | **81 %** |
| **Multiplicador de productividad** | **×5,3** |
| FTE equivalentes *(opcional)* | 1,0 |

> Horas con el margen del 20 % ya aplicado. Las horas IA derivan de un ratio no calibrado y no incluyen el tiempo de reloj de las ejecuciones de la suite en contenedor ni del ensayo de despliegue; el plazo real del ciclo depende más de esas esperas y de la revisión que de los tokens. La supervisión del 25 % es probablemente baja para C-03 (cambio de imagen en producción): se recomienda que el usuario reserve tiempo propio para la ventana de despliegue.

---

## Recomendación

- **Veredicto**: **go condicionado** — planificar ya C-01 y C-02 (sin decisiones pendientes) y condicionar C-03…C-07 a las respuestas P-01, P-02, P-03, P-05, P-06 y P-08 de la spec.
- **Quick wins** (bajo coste, alto valor): C-01 (habilita la medida de todo lo demás), C-04 (casi todo ya existe; solo tests y ajuste).
- **Costosas / a valorar**: C-03 (cambio de imagen + migración; el mayor riesgo operativo) y C-06 (reindexado completo y carga en Ollama).
- **Orden sugerido**: C-01 → C-02 → C-03 → C-05 → C-06 → C-04, con C-07 en paralelo desde C-02 — C-01 fija la línea base antes de tocar nada; C-02 reduce conflictos en `store.py` para C-03/C-05/C-06; C-06 necesita el tipo `vector` de C-03; C-04 se ajusta al final porque fusiona las señales que producen C-03/C-05/C-06. Respecto del encargo, solo cambia la posición de P3 (de 4.º a 6.º).
- **Fuera de alcance recomendado**: cambio del CLI (bloqueado por npm) salvo decisión expresa en P-04; servidor Prometheus/Grafana; borrar las columnas antiguas (`double precision[]`, `search_vector` `simple`) — eso sería una iniciativa posterior, no aditiva.

---

## Riesgos transversales

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **R-01 Retroceso asimétrico de la imagen PostgreSQL**: tras `CREATE EXTENSION vector` y crear columnas/índices `vector`, volver a `postgres:17-bookworm` sin pgvector deja objetos que no cargan (la librería falta) | Media | Alto | Misma versión mayor (17) y misma base → volumen compatible; doble escritura en `double precision[]`; retroceso documentado = mantener la imagen nueva con código anterior, o restaurar la copia previa a la migración en la imagen antigua; ensayo aislado (CA-14). |
| **R-02 Orden de fases del despliegue**: `deploy-memory.py` arranca `memory-postgres` (fase `database`) antes de la copia (`backup`); con la imagen nueva la copia se hace ya sobre el binario nuevo | Media | Medio | Mismo formato de datos (PG 17); verificar en el plan si conviene una copia previa con la imagen antigua; `content_manifest` antes/después ya lo compara el script. |
| **R-03 Privilegios de `CREATE EXTENSION`**: `vector` puede no ser extensión de confianza y el rol del DSN de migración no consta | Media | Alto | ⚠️ verificar el rol; alternativa: crear la extensión en el `initdb`/arranque como superusuario o un paso de operador previo a `migrate`. |
| **R-04 Recall del ANN con filtros y dimensiones**: el post-filtrado por permisos/versión vigente reduce resultados; HNSW no indexa > 2.000 dims (`vector`); el orden ANN difiere del exacto y puede romper tests que esperan orden exacto | Media | Medio | Escaneo iterativo (pgvector ≥ 0.8.0), ruta exacta para dimensiones no indexadas (los tests usan 2 dims), CA-08 mide recall frente a exacto. |
| **R-05 Carga de reindexado y plazos del worker**: ~150 fragmentos por documento grande, semáforo de 1 petición, 120 s por job | Alta | Medio | Lotes en `/api/embed`, plazo por lote, `MEMORY_CHUNK_MAX`, relleno idempotente en ventana separada (P-07); con 21 documentos desplegados el volumen actual es manejable. |
| **R-06 Migraciones con reescritura de tabla** (columnas generadas STORED, índices dentro de la transacción de `migrate`) | Baja | Medio | Volumen pequeño; `lock_timeout` ya usado en `schema.sql`; CA-34 impide cambios destructivos. |
| **R-07 Medida sesgada o irreal**: dataset escrito por el implementador; embeddings simulados | Media | Medio | Congelar `dataset-v1` y su hash antes de C-03; ejecución real con Ollama y datos sintéticos (P-06). |
| **R-08 Fuga de datos en observabilidad**: ids de proyecto, consultas o tokens en etiquetas/logs | Baja | Alto | CA-31/CA-32; reutilizar `privacy.py`; etiquetas con valores cerrados. |
| **R-09 Contrato MCP**: añadir `matched_chunk` u otros campos rompe clientes estrictos | Baja | Medio | Solo campos opcionales; CA-33 (diff aditivo, 34 herramientas). |

---

## Siguiente paso

Para **ejecutar** lo aprobado, genera el plan detallado con el agente **`planner`** (crea `improvement-plan.md` + `tasks.md` en `docs/roadmap/2026-11-09-retrieval-quality/`). Se recomienda aprobar para planificar **todas** las características en el orden C-01 → C-02 → C-03 → C-05 → C-06 → C-04 (C-07 en paralelo desde C-02), con C-01 y C-02 desbloqueadas ya y C-03…C-07 sujetas a las respuestas P-01…P-08 de la spec. El `planner` heredará las horas y costes por característica de esta evaluación y actualizará la fila **Plan** de esta evaluación y el campo `plan:` de la spec.

---

## Changelog

- 2026-11-09 — Creación (evaluator, fase 1 de `/dev-cycle`). Estado `en-revision`. Spec creada en `borrador` y enlazada en ambos sentidos.
