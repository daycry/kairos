---
generacion:
  inicio: 2026-11-12T09:41:28Z
  fin: 2026-11-12T09:53:04Z
  fuente: medido
  tokens_reales: { entrada: 76, salida: 53628, cache_creacion: 144554, cache_lectura: 3498012, respuestas: 38 }
  eur: null              # precioTokens no fiable; ejecuta la skill rates-verify
  horas_ia: 0.66
  duracion: 40m            # reloj: 12m
  ratio_usado: 300000      # default no calibrado
---

# 2026-11-12-three-components

> Evaluación de coste y conveniencia de la Iniciativa 2 del plan director, «Separación en tres componentes», para decidir si se planifica y en qué orden.

| | |
|---|---|
| **Fecha** | 2026-11-12 |
| **Estado** | completado |
| **Prioridad global** | Alta |
| **Solicitante** | Daycry (plan director, Iniciativa 2) |
| **Spec** | [`spec.md`](spec.md) |
| **Plan** | [`improvement-plan.md`](improvement-plan.md) |
| **Características evaluadas** | 7 |

---

## Cuadro de mando

| Métrica | Total estimado | Confianza |
|--------|----------------|-----------|
| Esfuerzo humano equivalente | **278,4 h** (232 h base +20 %), de las que 88,8 h son revisión adversarial | Media |
| Tiempo IA (ejecución) | **38,3 h** (31,9 h base +20 %) (+ 9,6 h supervisión) | Baja |
| Coste | **13.920 €** de desarrollo + tokens IA ⚠️ verificar | Media (desarrollo) / sin cifra (tokens) |
| Tokens IA facturables | **~9,6 M** (in 8,79 M / out 0,78 M) | Baja |
| Multiplicador productividad | **×5,8** | — |
| Características | **7** (+ integración y revisión adversarial como líneas propias) | — |

> Las horas humanas (lo que vale el trabajo) y las horas IA (lo que tarda el ciclo) se presentan por separado y no se suman (LES-007). En `retrieval-quality` las horas IA quedaron un 73 % por debajo de lo estimado, pero es una cota inferior sin medición completa (retro, 2026-11-12), así que su confianza sigue siendo Baja.

---

## Resumen ejecutivo

Se presupuestan siete bloques para separar Kairos en servidor, MCP y cliente: integración continua (C-01), paridad REST (C-02), `kairos-mcp` propio (C-03), servidor sin modelo de lenguaje (C-04), esquema de observación (C-05), estructura del repositorio (C-06) y compatibilidad (C-07). El total es de **278,4 h humanas equivalentes (13.920 € con margen)** más tokens IA (sin cifra en euros porque no hay precio verificado), con **~38 h de ejecución IA**. Por recomendación de la retro anterior, la revisión adversarial se presupuesta como partida propia: 0,5 veces la implementación, es decir, 74 h base.

El reconocimiento del código ha medido que **7 de las 34 herramientas no tienen endpoint `/v1`** y 2 lo tienen en parte. Además, han aparecido **dos conflictos con el CLI 0.3.0 publicado**: envía `generate: true` en los resúmenes (`capture.mjs:84`) y parsea el texto de cada herramienta como JSON (`dispatcher.mjs:15-20`). Por eso, apagar la extracción y aplicar el envoltorio S-05 exige decisiones de compatibilidad (P-02, P-03).

La partida más cara y arriesgada es C-03: reproducir 34 herramientas con esquemas idénticos sin importar código del servidor. Veredicto: **go condicionado** a P-01, P-02, P-03, P-04, P-07, P-09, P-10 y P-11.

---

## Requerimientos recibidos

Mapa del encargo (spec §Alcance) a las características evaluadas.

| ID | Característica | Requisito origen (ref.) | ¿Claro? |
|----|---------------|-------------------------|---------|
| C-01 | Integración continua | B-04, O-04 · spec CA-01…CA-03 | Sí; falta activar Actions y fijar el alcance de sistemas (P-01) |
| C-02 | Paridad REST `/v1` + prueba de correspondencia | Plan §2.2 · spec CA-04…CA-07 | Sí; el plan cita «estado de documentos» como pendiente, pero el endpoint ya existe (`app.py:309`) |
| C-03 | `kairos-mcp` paquete y contenedor + S-05 | D-5, S-05 · spec CA-08…CA-13 | Ambiguo: forma del envoltorio (P-02), fuente de esquemas (P-05) y credencial (P-08) |
| C-04 | Servidor sin modelo de lenguaje | D-2, D-4, S-04, S-09 · spec CA-14…CA-18 | Ambiguo: trato de `generate: true` (P-03), `corpus_answer` apagado (P-04), `/api/chat` opcional (P-10) |
| C-05 | Esquema versionado de observación y resumen | Plan §2.2 · spec CA-19…CA-22 | Parcial: el consumidor (observador) es la Iniciativa 6; obligatoriedad de `schema_version` (P-11) |
| C-06 | Estructura `server/`, `mcp/`, `client/`, `web/` | D-5 · spec CA-23…CA-26 | Parcial: nombre del paquete (P-06), versiones (P-07), momento respecto del PR #2 (P-09) |
| C-07 | Compatibilidad: MCP interno una versión + puente stdio | Plan §Iniciativa 2 · spec CA-27, CA-28 | Parcial: versión de retirada (P-07) |

**Hechos del reconocimiento** (con `fichero:línea`):

- **CI**: no existe `.github/`. La suite solo corre con `docker build --target test` (`memory_platform/Dockerfile:31`, `tests/run_postgres.py:18-57`). Hoy hay 462 funciones `def test_` en 41 ficheros del backend, 7 ficheros de test del CLI en `npm test` (`packages/kairos-cli/package.json`) y 5 del portal (`web/tests/`).
- **MCP montado**: `app.py:400-401` → `mcp.py:214-225` (`app.mount('/mcp', AuthenticatedMCP(...))`, con bearer o cookie más CSRF, `mcp.py:186-211`). Las 34 herramientas se reparten así: 12 en `mcp.py`, 13 en `agent_tools.py`, 7 en `extended_tools.py` y 2 en `corpus_answer_tools.py`. Las que llaman a servicios lo hacen con `asyncio.to_thread(getattr(store, …))`.
- **Paridad**: sin endpoint, `capture_policy`, `query_corpus`, `get_observations`, `observation_search`, `observation_context` y `team_search`, más la reconciliación de `event_status`. Parciales: `build_corpus` (sin fechas en `models.py:37-44`) y `event_status` (compuesta). Local: `important_workflow`. Tabla completa en la spec, §Arquitectura.
- **`extract`/`beam`**: el worker crea el proveedor `extract` siempre (`worker.py:82`, `:125-131`) y este llama a `/api/chat` (`providers.py:78`). `corpus_answer` también usa `/api/chat` (`corpus_answers.py:105`). El modelo por defecto `beam:cloud` aparece en `config.py:219` y `:272`, `docker-compose.yml:9` y `docs/configuration.md:24`. El CLI pide extracción en los resúmenes (`capture.mjs:84`) y `store_ingest.py:183` la convierte en trabajo.
- **Proxy de Ollama**: `ollama-proxy/default.conf.template:15-25` reenvía `location /` completo con `client_max_body_size 0` y plazos de 1 h. El servicio está en las redes `inference` y `egress` (`docker-compose.yml:45-47`).
- **Puente stdio**: `MCPTransport` llama a `baseURL + '/mcp/'` (`packages/kairos-cli/lib/mcp.mjs:33`) y exige 11 herramientas (`:7-8`). El proxy web enruta `/mcp` a `memory-api` (`memory_platform/nginx.conf:56-60`).
- **Renombrado**: `memory_platform` aparece 391 veces en 74 ficheros seguidos, sin contar `docs/roadmap`, y `packages/kairos-cli`, 27 veces en 11. La puerta congelada fija ambos nombres (`frozen-source-gate.py:26`, `:45`, `:77`). `store_surface.json` no contiene rutas.

**Hipótesis** (marcadas en la spec, §Supuestos): GitHub Actions ejecuta el target `test` en un tiempo aceptable; el SDK `mcp==1.27.1` permite publicar herramientas con un `inputSchema` arbitrario; el `payload` `jsonb` basta para el esquema de observación sin columnas nuevas.

---

## Datos necesarios para una evaluación completa

- [x] **Requerimientos** completos y sin ambigüedades: alcance cerrado por el plan director; ambigüedades listadas (P-01…P-11)
- [x] **Alcance** de cada característica acotado (qué entra y qué NO)
- [x] **Criterios de aceptación / éxito** por característica (CA-01…CA-32 en la spec)
- [x] **Restricciones**: confirmadas (fixtures aislados, migraciones y contrato aditivos, `store_surface.json` congelado, sin publicar)
- [ ] **Dependencias externas**: activación de GitHub Actions (P-01); fusión del PR #2 antes de C-06 (P-09)
- [x] **Contexto técnico** del proyecto disponible: reconocimiento hecho
- [ ] **Tarifa/hora y supuestos de coste**: sin `.claude/rates.json`; valores por defecto y precio de tokens ⚠️ verificar

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
| Margen de contingencia | 20 % | Sobre horas base humanas e IA, revisión incluida |
| Supervisión humana | 25 % de las horas IA | Valor por defecto; probablemente corto (ver riesgos R-06) |
| Ratio tokens→hora IA | 300.000 tok/h facturables | **Valor por defecto no calibrado**: `CALIBRATION.md` tiene una sola fila marcada `(estimado)`, sin muestras medidas |
| Revisión adversarial | 0,5 × implementación (2 o 3 intentos por fase) | Ajuste de `CALIBRATION.md` y de la retro de `retrieval-quality` |
| Tokens facturables | entrada no cacheada + creación de caché + salida | La lectura de caché no cuenta |

**Método de esfuerzo humano**: estimación por componentes sobre el código medido (rutas contadas en `app.py`, herramientas contadas por fichero, apariciones contadas con `grep` para los renombrados, tests existentes por área). Es un *mid-point* realista sin colchón; el margen se aplica después.

**Calibración aplicada**:

- La retro y `CALIBRATION.md` (2026-11-12) piden la revisión como partida propia de unas 0,5 veces la implementación, y medir cada `T-XX` con `usage-meter`.
- De la doctrina se aplican LES-001 y LES-009 (la revisión es la partida grande), LES-005 (con TDD, la ejecución es más cara y la revisión más barata), LES-007 (horas humanas e IA por separado) y LES-008 (el coste de proceso, aparte).
- Con una sola fila, y además estimada, el histórico es un indicio, no una ley.
- No hay memoria del proyecto con lecciones de estimación (`docs/knowledge/` solo tiene `candidates/` y un diario de `retrieval-quality`).

---

## Evaluación por característica

### C-01 — Integración continua (B-04, O-04)

- **Requisito origen**: B-04, O-04; spec CA-01…CA-03.
- **Descripción**: `.github/workflows/ci.yml` con los trabajos `server` (target `test`), `retrieval-eval` (proveedor simulado), `client` (`npm test`, `release:check`), `web` (`typecheck`, `test`, `build`, target `test` de `Dockerfile.web`) y `contracts` (diff aditivo); caché de capas Docker; sin secretos ni publicación; prueba de rojo en una rama desechable.
- **Complejidad**: Baja-Media.
- **Esfuerzo**: 10 h base (12 h con margen) · confianza Media. Desglose: workflow y trabajos 3 h, caché y tiempos 2 h, recibos y artefactos 1 h, puesta en verde en el PR (variaciones de entorno entre Docker Desktop y Linux) 2 h, prueba de rojo y comprobación sin secretos 1 h, documentación 1 h.
- **Previsión IA**: 340 k in / 30 k out tok (1,2 h IA base) · ⚠️ verificar €.
- **Coste**: (12 h × 50 €/h) + tokens = **600 € + tokens**.
- **Impacto / áreas afectadas**: `.github/workflows/` (nuevo), `memory_platform/Dockerfile` (targets `test`, `retrieval-eval`), `memory_platform/Dockerfile.web` (target `test`), `packages/kairos-cli/Dockerfile.test`, `docs/operations.md`.
- **Dependencias y prerequisitos**: P-01 (activar Actions). Es la red de las demás características.
- **Riesgos**: el target `retrieval-eval` instala paquetes con `apt-get` (`Dockerfile:57`) y depende de la red y de los espejos; la duración de la suite en CI no está medida (hipótesis); un test que hoy pasa por el entorno de Windows puede fallar en Linux.
- **Incógnitas / preguntas abiertas**: P-01.

### C-02 — Paridad REST `/v1`

- **Requisito origen**: plan §2.2; spec CA-04…CA-07.
- **Descripción**: 7 endpoints nuevos (`capture-policy`, reconciliación de eventos, `query_corpus`, búsqueda, contexto y lectura de observaciones con la semántica de `AgentStore.observations`, búsqueda de equipo), fechas en `CorpusSelection`, `x-kairos-endpoint` por herramienta en el exportador y prueba de correspondencia sobre las 34 herramientas con un escenario sembrado.
- **Complejidad**: Media.
- **Esfuerzo**: 20 h base (24 h con margen) · confianza Media-Alta. Desglose: endpoints y modelos 8 h, `x-kairos-endpoint` y exportador 3 h, prueba de correspondencia 3 h, tests de permisos y ajenos por endpoint 6 h.
- **Previsión IA**: 800 k in / 70 k out tok (2,9 h IA base) · ⚠️ verificar €.
- **Coste**: (24 h × 50 €/h) + tokens = **1.200 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/app.py`, `models.py`, `scripts/export-contracts.py`, `docs/contracts/*.json`, `tests/test_api.py`, `test_contract_additive.py` y un test nuevo de correspondencia.
- **Dependencias y prerequisitos**: C-01 recomendado antes.
- **Riesgos**: `GET /v1/observations` ya existe con la semántica del portal (`app.py:353-355`); los nuevos deben ir en rutas distintas para no cambiarla. El diff aditivo compara `required` exacto (`test_contract_additive.py:33-40`), así que un campo obligatorio nuevo lo rompe.
- **Incógnitas / preguntas abiertas**: ninguna bloqueante; los nombres de ruta los fija el plan.

### C-03 — `kairos-mcp` (paquete, contenedor y S-05)

- **Requisito origen**: D-5, S-05, integración §5; spec CA-08…CA-13.
- **Descripción**: paquete `mcp/` (`kairos_mcp`) con servidor MCP *streamable HTTP*. Incluye cliente `httpx` hacia `/v1`, con reenvío de la credencial del llamante; las 34 herramientas generadas desde el contrato con esquemas idénticos; la misma traducción de errores y los mismos presupuestos de bytes; `health`; Dockerfile sin `psycopg` ni secretos; servicio Compose en una red propia; envoltorio S-05 en todas las lecturas (también en el MCP interno); y ejecución de los 7 ficheros de tests de comportamiento MCP contra la cadena kairos-mcp → servidor.
- **Complejidad**: Alta.
- **Esfuerzo**: 38 h base (45,6 h con margen) · confianza Media-Baja. Desglose:
  - andamiaje, versión, Dockerfile y Compose: 5 h;
  - cliente HTTP, credencial, errores y plazos: 5 h;
  - 34 herramientas con esquemas idénticos: 10 h;
  - S-05 en unas 21 herramientas de lectura y en el MCP interno: 5 h;
  - arnés de tests en cadena (ASGI en proceso + PostgreSQL aislado) y adaptación de los 7 ficheros: 8 h;
  - prueba de arranque sin base: 3 h;
  - documentación: 2 h.
- **Previsión IA**: 1.600 k in / 150 k out tok (5,8 h IA base) · ⚠️ verificar €.
- **Coste**: (45,6 h × 50 €/h) + tokens = **2.280 € + tokens**.
- **Impacto / áreas afectadas**: `mcp/` (nuevo), `docker-compose.yml` (servicio y red), `memory_platform/nginx.conf` (`/mcp`), `memory_platform/mcp.py`, `agent_tools.py`, `extended_tools.py` (S-05 en el MCP interno), tests de MCP.
- **Dependencias y prerequisitos**: C-02 (endpoints); P-02, P-05 y P-08.
- **Riesgos**: R-01 (identidad exacta de esquemas, descripciones y anotaciones), R-02 (S-05 frente al CLI 0.3.0), R-05 (latencia de un salto HTTP más; `event_status` hace N+1 llamadas por trabajo).
- **Incógnitas / preguntas abiertas**: P-02, P-05, P-08; si `mcp==1.27.1` admite publicar `inputSchema` sin modelo Pydantic (hipótesis).

### C-04 — Servidor sin modelo de lenguaje

- **Requisito origen**: D-2, D-4, S-04, S-09; spec CA-14…CA-18.
- **Descripción**: `MEMORY_EXTRACT_ENABLED=0` por defecto (sin trabajo `extract` ni proveedor en el worker; recibo aditivo para `generate: true`), `MEMORY_CORPUS_ANSWER=off` por defecto con error `corpus_answer_disabled`, `MEMORY_LLM_MODEL` sin valor por defecto con validación al arrancar, lista de permitidos en el proxy de Ollama con `/api/chat` opcional, y prueba de la suite completa con un espía que falla ante `/api/chat`.
- **Complejidad**: Media.
- **Esfuerzo**: 20 h base (24 h con margen) · confianza Media. Desglose:
  - interruptor de `extract` en la ingesta y el worker: 4 h;
  - `corpus_answer` opcional: 3 h;
  - configuración y validación de `MEMORY_LLM_MODEL`: 2 h;
  - proxy con lista de permitidos y su prueba con upstream simulado: 3 h;
  - prueba sin modelo: 3 h;
  - ajuste de los tests que asumen `extract` (`test_worker.py`, `test_native.py`, `test_review_regressions.py`, `test_store.py`): 3 h;
  - documentación: 2 h.
- **Previsión IA**: 700 k in / 60 k out tok (2,5 h IA base) · ⚠️ verificar €.
- **Coste**: (24 h × 50 €/h) + tokens = **1.200 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/config.py`, `worker.py`, `store_ingest.py`, `corpus_answers.py`, `corpus_answer_tools.py`, `app.py`, `ollama-proxy/default.conf.template`, `docker-compose.yml`, `docs/configuration.md`, `docs/corpus-generated-answers.md`.
- **Dependencias y prerequisitos**: ninguna dura; P-03, P-04 y P-10.
- **Riesgos**: R-03 (el CLI 0.3.0 deja de producir recuerdos derivados de los resúmenes hasta la Iniciativa 6); la ruta `/api/chat` usada por `extract` y `corpus_answer` queda sin probar contra el proxy real si se apaga por defecto.
- **Incógnitas / preguntas abiertas**: P-03, P-04, P-10.

### C-05 — Esquema versionado de observación y resumen de sesión

- **Requisito origen**: plan §2.2 y §Iniciativa 2; spec CA-19…CA-22.
- **Descripción**: `observation.v1` y `session-summary.v1` en JSON Schema 2020-12 dentro de `docs/contracts/`, ejemplos válidos e inválidos versionados, validación en `POST /v1/observations` cuando el evento declara `schema_version`, error `invalid_observation` sin eco del contenido y migración aditiva solo si se justifican índices.
- **Complejidad**: Media.
- **Esfuerzo**: 21 h base (25,2 h con margen) · confianza Media-Baja. Desglose: diseño del esquema a partir del modelo de claude-mem y del plan §Iniciativa 6 4 h, modelos y exportación 3 h, validación en la ingesta 4 h, migración opcional 3 h, tests y ejemplos 5 h, documentación 2 h.
- **Previsión IA**: 700 k in / 60 k out tok (2,5 h IA base) · ⚠️ verificar €.
- **Coste**: (25,2 h × 50 €/h) + tokens = **1.260 € + tokens**.
- **Impacto / áreas afectadas**: `docs/contracts/` (esquemas nuevos), `memory_platform/models.py`, `extended_store.py` (`observation_add`, `observation_record_event`), `requirements.txt` si se usa un validador JSON Schema (dependencia fijada nueva), `schema.sql` si hay índices.
- **Dependencias y prerequisitos**: C-02 recomendado; P-11. Su consumidor real es la Iniciativa 6.
- **Riesgos**: R-04 (diseñar el esquema antes que el observador puede obligar a una v2 temprana); una dependencia nueva de validación amplía la superficie (B-19).
- **Incógnitas / preguntas abiertas**: P-11.

### C-06 — Estructura del repositorio

- **Requisito origen**: D-5; spec CA-23…CA-26.
- **Descripción**: `git mv memory_platform server/memory_platform` (conservando el nombre del paquete, P-06), `git mv packages/kairos-cli client`, traslado de `Dockerfile.web` y `nginx.conf` a `web/`, una versión por componente, actualización de Dockerfiles, Compose, puerta congelada, scripts, CI, `RUNTIME_FILES` del CLI y documentación; suite completa en cada paso con `store_surface.json` congelado.
- **Complejidad**: Media.
- **Esfuerzo**: 26 h base (31,2 h con margen) · confianza Media. Desglose: servidor (Dockerfiles, Compose, scripts, puerta congelada, 74 ficheros con 391 apariciones) 8 h, cliente (11 ficheros, `release:check`, `npm pack`) 4 h, imagen web 2 h, versiones y changelogs por componente 3 h, rutas de CI 2 h, documentación 4 h, ejecuciones de la suite por paso 3 h.
- **Previsión IA**: 1.000 k in / 80 k out tok (3,6 h IA base) · ⚠️ verificar €.
- **Coste**: (31,2 h × 50 €/h) + tokens = **1.560 € + tokens**.
- **Impacto / áreas afectadas**: todo el árbol; en especial `memory_platform/Dockerfile` (contextos `COPY`, target `lifecycle-test` con `packages/kairos-cli`), `docker-compose.yml`, `scripts/*.py`, `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`, `packages/kairos-cli/lib/config.mjs:11`, `README.md` y `docs/*.md`.
- **Dependencias y prerequisitos**: C-01 (CI como red); P-09 (PR #2 fusionado antes); P-06 y P-07.
- **Riesgos**: R-07 (conflictos con el PR #2 abierto); recibos y rutas de iniciativas cerradas en `docs/roadmap/` que apuntan a `memory_platform/` quedan como históricos (no se reescriben).
- **Incógnitas / preguntas abiertas**: P-06, P-07, P-09.

### C-07 — Compatibilidad

- **Requisito origen**: plan §Iniciativa 2; spec CA-27, CA-28.
- **Descripción**: `MEMORY_MOUNT_MCP` (por defecto `1` durante la versión de transición) con cabeceras `Deprecation` y `Sunset` y evento de log; `/mcp` del proxy web hacia kairos-mcp; prueba del puente stdio y de `kairos doctor` contra kairos-mcp en el target `lifecycle-test`; nota de migración.
- **Complejidad**: Baja-Media.
- **Esfuerzo**: 13 h base (15,6 h con margen) · confianza Media. Desglose: interruptor y cabeceras 3 h, enrutado nginx y Compose 3 h, prueba del puente contra kairos-mcp 5 h, nota de migración 2 h.
- **Previsión IA**: 450 k in / 40 k out tok (1,6 h IA base) · ⚠️ verificar €.
- **Coste**: (15,6 h × 50 €/h) + tokens = **780 € + tokens**.
- **Impacto / áreas afectadas**: `memory_platform/mcp.py`, `app.py`, `config.py`, `memory_platform/nginx.conf`, `docker-compose.yml`, `memory_platform/Dockerfile` (`lifecycle-test`), `docs/integration.md`.
- **Dependencias y prerequisitos**: C-03.
- **Riesgos**: las cabeceras de retirada no las ve el agente (solo las ve el cliente HTTP); para que alguien las note hace falta el log y la nota de migración.
- **Incógnitas / preguntas abiertas**: P-07.

### Líneas transversales (no son características, pero se presupuestan aparte)

| Línea | Base | Con margen | Coste | Tokens (in/out) | Motivo |
|---|---|---|---|---|---|
| Integración, ensayo aislado y documentación | 10 h | 12 h | 600 € | 400 k / 40 k | Ensayo de cinco servicios en Compose aislado (CA-31), manuales (CA-32), contratos regenerados |
| Revisión adversarial (2 o 3 intentos por fase) | 74 h | 88,8 h | 4.440 € | 2.800 k / 250 k | 0,5 × 148 h de implementación, según `CALIBRATION.md` y la retro (LES-001, LES-009) |
| Proceso (spec + evaluación + plan) | — | — | tokens | medido en `generacion:` | LES-008: coste de proceso aparte |

---

## Comparativa

Ordenada por el orden de trabajo recomendado.

| # | Característica | Complejidad | Horas (con margen) | Coste € (desarrollo) | Tokens | Prioridad | Confianza |
|---|---------------|-------------|-------|---------|--------|-----------|-----------|
| C-01 | Integración continua | Baja-Media | 12 h | 600 € | 370 k | Crítica | Media |
| C-04 | Servidor sin modelo de lenguaje | Media | 24 h | 1.200 € | 760 k | Alta | Media |
| C-02 | Paridad REST `/v1` | Media | 24 h | 1.200 € | 870 k | Alta | Media-Alta |
| C-05 | Esquema de observación | Media | 25,2 h | 1.260 € | 760 k | Media | Media-Baja |
| C-03 | `kairos-mcp` + S-05 | Alta | 45,6 h | 2.280 € | 1.750 k | Alta | Media-Baja |
| C-07 | Compatibilidad | Baja-Media | 15,6 h | 780 € | 490 k | Alta | Media |
| C-06 | Estructura del repositorio | Media | 31,2 h | 1.560 € | 1.080 k | Media | Media |
| — | Integración, ensayo y docs | — | 12 h | 600 € | 440 k | — | Media |
| — | Revisión adversarial | — | 88,8 h | 4.440 € | 3.050 k | — | Media |
| | **Total** | | **278,4 h** | **13.920 €** | **9.570 k** | | |

---

## Presupuesto total

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 232 h × 50 €/h (148 h implementación + 10 h integración + 74 h revisión) | 11.600 € |
| Margen de contingencia | +20 % sobre desarrollo base (46,4 h) | 2.320 € |
| Tokens IA (input) | 8,79 M tok × precio input | ⚠️ verificar |
| Tokens IA (output) | 0,78 M tok × precio output | ⚠️ verificar |
| **Total estimado (con margen)** | 13.920 € + (8,79 × P_in + 0,78 × P_out) €, con P en €/1M tokens | **13.920 € + tokens ⚠️ verificar** |

> Opcional fuera del total: proxy de Ollama sin root (resto de S-09), unas 1 h base (+60 € con margen), si se aprueba en P-10.

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 278,4 h (232 h base) |
| Horas IA (ejecución) | 38,3 h (31,9 h base = 9,57 M tokens facturables ÷ 300.000 tok/h) |
| Supervisión humana | 9,6 h (25 % de 38,3 h) |
| **Horas totales (IA + supervisión)** | **47,9 h** |
| Horas ahorradas | 230,5 h |
| **Ahorro** | **83 %** |
| **Multiplicador de productividad** | **×5,8** |
| FTE equivalentes *(opcional)* | 1,4 |

> Horas con el margen del 20 % ya aplicado. Las horas IA salen de un ratio no calibrado y no incluyen el tiempo de reloj de la suite en contenedor ni de la CI. En `retrieval-quality`, ese tiempo y los bucles de revisión dominaron el plazo real. Para que esta iniciativa sirva de calibración, cada `T-XX` y cada intento de revisión deben abrir y cerrar `usage-meter`.

---

## Recomendación

- **Veredicto**: **go condicionado**. C-01 y C-02 pueden planificarse ya, porque no dependen de ninguna pregunta salvo P-01. C-03, C-04, C-05, C-06 y C-07 quedan condicionadas a P-02, P-03, P-04, P-07, P-09, P-10 y P-11, que necesitan al usuario. P-05, P-06 y P-08 las puede cerrar el plan.
- **Quick wins** (bajo coste, alto valor):
  - C-01, la red de toda la separación y la cobertura de B-04 y O-04;
  - C-04, que cierra S-04 y S-09 y cumple D-2 con unas 24 h.
- **Costosas / a valorar**:
  - C-03 es el núcleo de la iniciativa y la partida con más incertidumbre;
  - C-05 es útil, pero su consumidor llega en la Iniciativa 6. Si se quiere recortar, puede ir al principio de la 6 sin bloquear el cierre de la 2. En ese caso habría que retirarla del criterio de cierre del plan, que hoy no la nombra de forma expresa.
- **Orden sugerido**: C-01 → C-04 → C-02 → C-05 → C-03 → C-07 → C-06.
  - La CI va primero, por mandato del plan.
  - C-04 es pequeña, independiente y reduce superficie antes de duplicar herramientas.
  - C-02 crea los endpoints que C-03 consume.
  - C-05 toca la ingesta antes de que kairos-mcp la envuelva.
  - C-07 depende de C-03.
  - C-06, los renombrados masivos, va al final, en un paso aislado y con el PR #2 ya fusionado (P-09). Así no se rebasan cambios de lógica sobre rutas movidas.
  - Respecto del encargo, solo cambian de posición la estructura (de 6.º a último) y el servidor sin modelo (de 4.º a 2.º).
- **Fuera de alcance recomendado**: retirar de verdad el MCP interno (versión siguiente), la matriz de sistemas del CLI (O-09), HTTPS y despliegue (Iniciativa 5) y renombrar el paquete Python (P-06).

---

## Riesgos transversales

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **R-01 Identidad del contrato en kairos-mcp**: las descripciones salen de *docstrings* y el diff compara texto, anotaciones y `required` (`test_contract_additive.py:28-40`); una diferencia mínima rompe CA-10 | Media | Alto | Generar desde `kairos-mcp.json` (P-05) y probar ambos MCP con la misma regla; si el SDK no lo permite, copiar modelos con un test de igualdad de esquemas |
| **R-02 S-05 rompe al cliente instalado**: el CLI 0.3.0 (sin publicar en npm, instalado desde tarball local) hace `JSON.parse` del texto de la herramienta (`dispatcher.mjs:15-20`) y `custom-agents` comparará contenido | Media | Alto | Envoltorio solo con campos aditivos (P-02); tests del CLI sin cambios en CA-13 |
| **R-03 Apagar `extract` cambia la captura del CLI**: hoy los resúmenes con `generate: true` (`capture.mjs:84`) producen recuerdos derivados; con `extract` apagado dejan de producirse hasta la Iniciativa 6 | Alta | Medio | Aceptar el evento y marcarlo en el recibo (P-03); documentarlo en la nota de migración; los datos actuales no se migran, así que no hay pérdida en producción |
| **R-04 Esquema de observación prematuro**: se diseña antes que el observador (Iniciativa 6) | Media | Medio | Validar solo cuando el evento declara `schema_version` (P-11); versionarlo para permitir una v2 sin romper |
| **R-05 Latencia y fallos del salto extra**: kairos-mcp añade un salto HTTP; `event_status` hace una llamada por trabajo | Media | Bajo | Cliente HTTP con conexión persistente y plazo; endpoint compuesto de estado si el ensayo lo justifica |
| **R-06 Bucles de revisión**: la retro midió 2 o 3 intentos por fase, con hallazgos reales en todas | Alta | Medio | Revisión como partida propia (88,8 h); fases pequeñas; `usage-meter` por tarea e intento; reservar supervisión por encima del 25 % |
| **R-07 Conflictos de renombrado con el PR #2**: `feat/three-components` sale de `feat/retrieval-quality`, con el PR #2 abierto | Media | Medio | C-06 al final y después de fusionar el PR #2 (P-09); `git mv` en commits sin cambios de contenido |
| **R-08 CI en otro sistema**: la suite se ha ejecutado en Docker Desktop sobre Windows; en `ubuntu-latest` pueden aflorar diferencias y tiempos no medidos | Media | Medio | C-01 primero, con 2 h reservadas para la puesta en verde; caché de capas |
| **R-09 Tocar recursos desplegados**: el ensayo de cinco servicios usa Compose y podría reutilizar nombres `knowledge-graphs-*` (las redes y volúmenes tienen `name:` fijo en `docker-compose.yml:169-177`) | Baja | Alto | Proyecto Compose aislado con fichero de *override* que renombra redes y volúmenes; CA-30 lo comprueba; nunca `deploy-memory.py` contra la instalación local |

---

## Siguiente paso

Para **ejecutar** lo aprobado, genera el plan detallado con el agente **`planner`**, que crea `plan.md` y `tasks.md` en `docs/roadmap/2026-11-12-three-components/`. Se recomienda aprobar **todas** las características en el orden C-01 → C-04 → C-02 → C-05 → C-03 → C-07 → C-06. C-01 y C-02 se pueden planificar ya, con P-01 respondida. El resto queda sujeto a P-02, P-03, P-04, P-07, P-09, P-10 y P-11. El `planner` hereda horas y costes por característica, presupuesta la revisión por fase (0,5 × implementación), exige `usage-meter` por `T-XX` y actualiza la fila **Plan** de esta evaluación y el campo `plan:` de la spec.

---

## Changelog

- 2026-11-12 — Creación (evaluator). Estado `en-revision`. Spec creada en `borrador` y enlazada en ambos sentidos.

## Puerta go/no-go

**Go** del usuario el 2026-11-12. Acepta las ocho recomendaciones de las preguntas abiertas (P-01, P-02, P-03, P-04, P-07, P-09, P-10, P-11); las técnicas (P-05, P-06, P-08) se adoptan como se recomiendan. La spec pasa a `aprobada`.
