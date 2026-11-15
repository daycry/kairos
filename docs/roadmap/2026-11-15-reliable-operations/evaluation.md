---
generacion:
  inicio: 2026-11-15T14:42:54Z
  fin: 2026-11-15T14:55:57Z
  fuente: medido
  tokens_reales: { entrada: 74, salida: 61023, cache_creacion: 153195, cache_lectura: 3252734, respuestas: 36 }
  eur: null              # precioTokens no fiable; ejecuta la skill rates-verify
  horas_ia: 0.71
  duracion: 43m            # reloj: 13m
  ratio_usado: 300000      # default no calibrado
---

# 2026-11-15-reliable-operations

> Evaluación de coste y conveniencia de la Iniciativa 3 del plan director, «Operación fiable», para decidir si se planifica, en qué orden y si se corta en hitos.

| | |
|---|---|
| **Fecha** | 2026-11-15 |
| **Estado** | completado |
| **Prioridad global** | Alta |
| **Solicitante** | Daycry (plan director, Iniciativa 3; encargo del orquestador `/dev-cycle`) |
| **Spec** | [`spec.md`](spec.md) |
| **Plan** | [`improvement-plan.md`](improvement-plan.md) |
| **Características evaluadas** | 7 |

---

## Cuadro de mando

| Métrica | Total estimado | Confianza |
|--------|----------------|-----------|
| Esfuerzo humano equivalente | **412,8 h** (344 h base +20 %), de las que 156 h son revisión adversarial | Media |
| Tiempo IA (ejecución) | **55,0 h** nominales (45,9 h base +20 %) (+ 13,8 h supervisión); **≈ 19 h** si se repite la desviación de la Iniciativa 2 (−66 %) | Baja |
| Coste | **20.640 €** de desarrollo + tokens IA ⚠️ verificar | Media (desarrollo) / sin cifra (tokens) |
| Tokens IA facturables | **~13,8 M** (in 12,64 M / out 1,12 M) | Baja |
| Multiplicador productividad | **×6,0** | — |
| Características | **7** (+ integración y revisión adversarial como líneas propias) | — |

> Horas humanas (lo que vale el trabajo) y horas IA (lo que tarda el ciclo) van por separado y no se suman (LES-007). Las horas IA reales de la Iniciativa 2 salieron un **66 % por debajo** de lo estimado (10,9 h medidas frente a 32,1 h, cota inferior) y las de la Iniciativa 1 un 73 % (cota inferior). Con dos filas, ambas estimadas, es un indicio y no se aplica a la cifra nominal; se muestra al lado.

---

## Resumen ejecutivo

Se presupuestan los siete bloques del plan director: copias (C-01), worker (C-02), conexiones y plazos (C-03), despliegue (C-04), abstención (C-05), sonda (C-06) y tests (C-07). El total es de **412,8 h humanas equivalentes (20.640 € con margen)** más tokens IA, con **~55 h nominales de ejecución IA** (≈ 19 h si se repite la desviación medida). Siguiendo la retro de la Iniciativa 2, la revisión adversarial es una partida propia de **130 h base**: 0,5 veces la implementación y 1,0 vez en las dos superficies que tocan lo que ven los clientes (C-03, en todas las peticiones, y C-05, en la respuesta de búsqueda).

El reconocimiento confirma los catorce hallazgos con el código actual (`b7ce9d6`) y añade tres hechos que cambian el diseño. Primero, el **RRF no sirve de umbral de abstención**: es relativo al rango, así que la abstención debe apoyarse en la similitud coseno de la capa semántica y en `lexical_match`. Segundo, la puerta `retrieval-eval` usa **embeddings simulados**: un umbral calibrado con ellos no vale para `nomic-embed-text` (P-05). Tercero, `result_schemas.search` tiene **`additionalProperties: false`**: un campo nuevo es aditivo para nuestro diff, pero rompería a un cliente que valide con el esquema anterior. Por eso la abstención debe ser opcional y declararse a la Iniciativa 7 (P-04).

Es una iniciativa grande (L en el plan director, un 48 % más que la 2 en horas base). Se propone **cortarla en dos hitos sin quitar alcance**: **A «no perder datos ni parar»** (C-07, C-02, C-03, C-01: criterios de cierre 1 y 2; 237,6 h con margen) y **B «desplegar y detectar»** (C-04, C-06, C-05: criterio 3; 175,2 h con margen). Veredicto: **go**, con P-05 como única pregunta que puede requerir al usuario.

---

## Requerimientos recibidos

Mapa del encargo (spec §Alcance) a las características evaluadas.

| ID | Característica | Requisito origen (ref.) | Clase | ¿Claro? |
|----|---------------|-------------------------|-------|---------|
| C-01 | Copias: sha256, cifrado, retención, plazo propio, `--verify-backup`, copia externa programada, runbook | O-01, O-02, O-03, S-06 · spec CA-01…CA-08 | Capacidad nueva + defecto (O-03) | Parcial: herramienta de cifrado (P-01) y mecanismo de programación y destinos (P-02) |
| C-02 | Worker: base frente a proveedor, espera, tope al reclamar, índice parcial, retención | B-03, B-05, B-06 · spec CA-09…CA-14 | Defecto + capacidad nueva + rendimiento | Parcial: ventanas de retención y tratamiento de `events` (P-03) |
| C-03 | Pool, `statement_timeout` y `connect_timeout`, actor y permisos por transacción | B-02, B-07 · spec CA-15…CA-19 | Refactor + cambio de comportamiento | Sí; los valores por defecto los fija el plan con medición |
| C-04 | Límites, healthchecks, rotación de logs, bloqueo, retroceso de imágenes, `extra_hosts` | O-05, O-06 · spec CA-20…CA-25 | Cambio de comportamiento | Parcial: forma del retroceso sin registro (P-08) |
| C-05 | Abstención con umbral calibrado y «nada relevante» | M-01 · spec CA-26…CA-29 | Capacidad nueva **visible para clientes** | Ambiguo: activación por defecto (P-04) y calibración con el modelo real (P-05) |
| C-06 | Sonda de ida y vuelta y alerta de cola atascada | M-06 · spec CA-30…CA-33 | Capacidad nueva | Ambiguo: qué es «alerta» (P-06) y qué cola (P-07) |
| C-07 | Tests: base caída, concesión expirada, trabajo venenoso, límites, tests frágiles | B-15 · spec CA-34…CA-36 | Refactor de pruebas + cobertura | Sí |

**Hechos del reconocimiento** (con `fichero:línea`; detalle en la spec, §Contexto):

- **Copias**: `pg_dump` en claro, `chmod 600`, sin checksum ni retención (`admin.py:286-294`); `restore-check` existe (`:295-313`) y el despliegue no lo usa; `content-manifest` y `backup` heredan `timeout=120` (`deploy-memory.py:257-258`, `:376`, `:380`).
- **Worker**: `claim_job` fuera del `try` (`worker.py:91`), así que una caída de base termina `run()`; los fallos de base al completar caen en `except Exception` como `provider_error` (`:165-168`); sin tope de intentos al reclamar trabajos `running` caducados (`store_jobs.py:92`, `:105`).
- **Cola**: el índice `(state, available_at)` (`schema.sql:19`) no sirve al `ORDER BY priority,available_at,created_at,id` con `OR` (`store_jobs.py:92`); la última versión de esquema es la 11 (`schema.sql:214-228`).
- **Retención**: ninguna tabla la tiene. `events` lo leen `event_status`, la actividad, el historial y `get_tool_uses` (`store_documents.py:252-329`, `extended_store.py:96`, `portal_store.py:64-73`); `projection_receipts.job_id` referencia `jobs(id)` (`schema.sql:20`).
- **Conexiones**: un único `psycopg.connect` (`store.py:28`) y 86 usos de `transaction()`; `_active` repite dos consultas por transacción y `_require` añade concesiones por proyecto (`store_auth.py:36-77`).
- **Plazos**: `statement_timeout` solo en el *fallback* de trigramas y en la búsqueda vectorial (`store_documents.py:21-35`, `store_vectors.py:351-356`); los `asyncio.timeout` sobre hilos no cancelan (`retrieval.py:113-115`, `:146-148`).
- **Compose**: `mem_limit` solo en `memory-mcp` (`docker-compose.yml:154`); sin healthcheck en worker ni web; `ollama` y `memory-postgres` sin rotación; imágenes `:latest`; `host.docker.internal` sin `extra_hosts` (`:45`).
- **Abstención**: fusión RRF por rango (`retrieval.py:172-190`); similitud coseno en la capa semántica (`store_vectors.py:101`, `:408`); 72 preguntas, todas con respuesta; proveedor simulado (`fake_embeddings.py:1-8`); `result_schemas.search` con `additionalProperties: false` en todos sus niveles (`docs/contracts/kairos-mcp.json`).
- **Observabilidad**: ya hay `kairos_jobs_queue_depth` y `kairos_jobs_failed` (`observability.py:205-208`), pero no la antigüedad del pendiente más viejo. El worker no expone HTTP.
- **Tests**: `body_too_large` (`app.py:36`) y `work_budget_exceeded` (`agent_store.py:186`) sin tests; `test_chunk_schema.py:14` trocea `schema.sql` por marcador; `/health/ready` ya tiene un caso 503 (`test_observability.py:216`).

**Hipótesis** (spec, §Supuestos): `age` y `rclone` se pueden fijar en la imagen `operator`; `psycopg_pool` es compatible con `psycopg 3.3.7`; un índice parcial sirve al reclamo (o dos sondeos); la similitud del proveedor simulado no se parece a la de `nomic-embed-text`.

---

## Datos necesarios para una evaluación completa

- [x] **Requerimientos** completos y sin ambigüedades: alcance cerrado por el plan director; ambigüedades listadas (P-01…P-10)
- [x] **Alcance** de cada característica acotado (qué entra y qué NO)
- [x] **Criterios de aceptación / éxito** por característica (CA-01…CA-38 en la spec)
- [x] **Restricciones**: confirmadas (fixtures aislados, nada `knowledge-graphs-*` ni Ollama del host, migraciones y contratos aditivos, Docker de uno en uno, sin despliegue real ni nube real, sin credenciales en el repo)
- [ ] **Dependencias externas**: calibración con el modelo real (P-05); coordinación con la Iniciativa 7 para la abstención (P-04)
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
| Supervisión humana | 25 % de las horas IA | Valor por defecto |
| Ratio tokens→hora IA | 300.000 tok/h facturables | **Default no calibrado**: `CALIBRATION.md` tiene dos filas, ambas `(estimado)`, sin ratio medido |
| Tokens por hora humana base | ~40.000 facturables (92 % entrada / 8 % salida) | Derivado de la Iniciativa 2 (9,57 M para 232 h base) |
| Revisión adversarial | 0,5 × implementación; **1,0 ×** en C-03 y C-05 | Ajuste de la retro de la Iniciativa 2: «el doble para servicios expuestos a entradas de clientes» |
| Tokens facturables | entrada no cacheada + creación de caché + salida | La lectura de caché no cuenta |

**Método de esfuerzo humano**: estimación por componentes sobre el código medido (puntos de cambio localizados con `fichero:línea`, subcomandos y servicios a añadir, tests existentes por área). Es un *mid-point* realista sin colchón; el margen se aplica después.

**Calibración aplicada**:

- La retro de la Iniciativa 2 y `CALIBRATION.md` piden la revisión como partida propia (≥ 0,5 veces la implementación, el doble en superficies expuestas a clientes) y medir con `usage-meter` también los intentos de revisión. Se aplica en las dos cosas.
- Horas IA: las dos iniciativas anteriores salieron un 66 % y un 73 % por debajo (cotas inferiores). Con menos de tres filas, y ambas estimadas, se trata como indicio: la cifra nominal no se toca y se da al lado la ajustada (≈ 19 h con margen).
- Doctrina: LES-001 y LES-009 (la revisión es la partida grande), LES-005 (TDD: la ejecución es más cara y la revisión más barata), LES-007 (horas humanas e IA por separado) y LES-008 (coste de proceso aparte).
- Aprendizaje 1 de la retro («corregir la clase entera»): en C-02 y C-03 los oráculos cubren la clase (todas las rutas de error de base, todas las transacciones), no un caso.
- Aprendizaje 2 («las pruebas con tiempos fallan en CI»): los tests de *backoff*, plazos y latido usan relojes inyectados o `threading.Event`, no esperas reales.
- Aprendizaje 3 («un despliegue vivo que monta ficheros del árbol se rompe»): el servicio `ollama` desplegado monta `ollama-proxy/default.conf.template` desde el árbol de trabajo (`docker-compose.yml:48`). C-04 no debe tocar ese fichero sin comprobar antes qué contenedores lo usan (riesgo R-08).
- La memoria del proyecto (`docs/knowledge/`) no tiene lecciones de estimación; el diario no tiene ninguna entrada de esta iniciativa.

---

## Evaluación por característica

### C-01 — Copias (O-01, O-02, O-03, S-06)

- **Requisito origen**: O-01, O-02, O-03, S-06; spec CA-01…CA-08. Criterio de cierre 1.
- **Clase / primer oráculo**: capacidad nueva + defecto · `verify-backup` detecta un byte alterado; el despliegue pasa `--backup-timeout`.
- **Descripción**: manifiesto con sha256 y `verify-backup`; cifrado `age` con clave pública; `--prune --keep N` seguro; plazo propio en el despliegue; `--verify-backup` con restauración en un contenedor efímero; servicio `memory-backup` con destinos `dir:` y `rclone:`; runbook de restauración y ensayo automatizado desde el destino externo simulado.
- **Complejidad**: Media-Alta.
- **Esfuerzo**: 40 h base (48 h con margen) · confianza Media. Desglose: manifiesto y `verify-backup` 3 h, cifrado `age` y su imagen 5 h, retención local 3 h, plazo propio 1,5 h, `--verify-backup` con PostgreSQL efímero 6 h, `memory-backup` con destinos, verificación remota y retención remota 8 h, runbook y ensayo de restauración 5 h, tests 6 h, documentación 2,5 h.
- **Previsión IA**: 1,47 M in / 0,13 M out tok (5,3 h IA base) · ⚠️ verificar €.
- **Coste**: (48 h × 50 €/h) + tokens = **2.400 € + tokens**.
- **Impacto / áreas afectadas**: `server/memory_platform/admin.py`, `Dockerfile` (target `operator`), `docker-compose.yml` (servicio `memory-backup`), `scripts/deploy-memory.py`, `test_admin.py`, `test_deploy*.py`, `docs/operations.md`.
- **Dependencias y prerequisitos**: P-01 y P-02; C-03 recomendado antes (los subcomandos de copia deben quedar fuera del `statement_timeout`).
- **Riesgos**: R-03 (perder la clave privada equivale a perder las copias: el runbook debe exigir su custodia fuera del VPS); el contenedor efímero de `--verify-backup` duplica la base en disco y RAM durante la verificación (con 32 GB y datos sembrados no importa; en el VPS sí, Iniciativa 5); `rclone` añade superficie a la imagen `operator`.
- **Incógnitas / preguntas abiertas**: P-01, P-02; disponibilidad de `age` y `rclone` fijables en bookworm (hipótesis).

### C-02 — Worker (B-03, B-05, B-06)

- **Requisito origen**: B-03, B-05, B-06; spec CA-09…CA-14. Criterio de cierre 2.
- **Clase / primer oráculo**: defecto + capacidad nueva + rendimiento · con la base cortada en `claim_job`, `run()` sigue vivo.
- **Descripción**: `StoreUnavailable` para errores de conexión y pool; reclamo en bucle con espera exponencial con *jitter*; los fallos de base al completar no cambian el estado; tope `attempts_exhausted` al reclamar; versión de esquema 12 con índices parciales de cola; `admin prune-tables` por lotes con `--dry-run`.
- **Complejidad**: Media.
- **Esfuerzo**: 30 h base (36 h con margen) · confianza Media. Desglose: clasificación de errores y bucle con espera 8 h, tope al reclamar 3 h, índices y posible división del reclamo en dos sondeos con `EXPLAIN` 4 h, retención con claves foráneas y lotes 8 h, tests unitarios 5,5 h, documentación 1,5 h.
- **Previsión IA**: 1,10 M in / 0,10 M out tok (4,0 h IA base) · ⚠️ verificar €.
- **Coste**: (36 h × 50 €/h) + tokens = **1.800 € + tokens**.
- **Impacto / áreas afectadas**: `worker.py`, `store_jobs.py`, `schema.sql`, `admin.py`, `config.py`, `errors.py`, `test_worker.py`, `test_jobs.py`, `test_migrations_additive.py`.
- **Dependencias y prerequisitos**: arnés de C-07 (oráculo); P-03.
- **Riesgos**: R-01 (ocultar un fallo real de base como «espera» indefinida: el latido debe dejar de avanzar si la caída supera el umbral); R-04 (retención que borra datos que ven los clientes); el reclamo y su semántica de reconciliación (`unknown`, `needs_reconciliation`, `store_jobs.py:104`) son delicados.
- **Incógnitas / preguntas abiertas**: P-03.

### C-03 — Conexiones y plazos (B-02, B-07)

- **Requisito origen**: B-02, B-07; spec CA-15…CA-19.
- **Clase / primer oráculo**: refactor + cambio de comportamiento · una consulta `pg_sleep` más larga que el plazo se cancela en el servidor.
- **Descripción**: `psycopg_pool` en `Store.transaction()` (versión fijada); `connect_timeout` y `statement_timeout` como opciones de conexión, distintos para API y worker y sin límite en `admin`; 503 `store_timeout` y `store_busy`; caché de `_active` y de concesiones por transacción; medición antes y después (consultas por búsqueda, conexiones, latencia).
- **Complejidad**: Media-Alta (toca todas las rutas de datos).
- **Esfuerzo**: 30 h base (36 h con margen) · confianza Media-Baja. Desglose: pool y configuración 7 h, plazos por defecto y exclusiones de `admin` 5 h, mapeo de errores a 503 2 h, caché por transacción 6 h, tests (servidor mudo, `pg_sleep`, pool agotado, contador de consultas, revocación) 7 h, medición 2 h, documentación 1 h.
- **Previsión IA**: 1,10 M in / 0,10 M out tok (4,0 h IA base) · ⚠️ verificar €.
- **Coste**: (36 h × 50 €/h) + tokens = **1.800 € + tokens**.
- **Impacto / áreas afectadas**: `store.py`, `store_auth.py`, `config.py`, `app.py` (manejador de errores), `requirements.txt`, `worker.py`, `admin.py`; la suite entera ejercita el cambio.
- **Dependencias y prerequisitos**: arnés de C-07.
- **Riesgos**: R-02 (un `statement_timeout` por defecto corta consultas largas legítimas: migraciones, relleno, `content-manifest`, `graph_data`); R-05 (la caché por transacción no debe sobrevivir al `COMMIT` ni compartirse entre peticiones del pool); `store_surface.json` congelado; el pool con `asyncio.to_thread` debe dimensionarse frente al número de hilos.
- **Incógnitas / preguntas abiertas**: ninguna bloqueante; los valores por defecto se miden en el plan.

### C-04 — Despliegue (O-05, O-06)

- **Requisito origen**: O-05, O-06; spec CA-20…CA-25.
- **Clase / primer oráculo**: cambio de comportamiento · `docker compose config` muestra límites, healthchecks y rotación en todos los servicios; un segundo despliegue falla con `deployment_locked`.
- **Descripción**: `mem_limit` y `cpus` por variable en todos los servicios; latido del worker en `/tmp` y healthcheck; healthcheck de `memory-web`; rotación de logs en `ollama` y `memory-postgres`; bloqueo con `--break-lock`; etiquetado de imágenes, registro y `--rollback`; `extra_hosts`.
- **Complejidad**: Media.
- **Esfuerzo**: 30 h base (36 h con margen) · confianza Media. Desglose: límites 2 h, latido y healthchecks 4 h, rotación 0,5 h, bloqueo 3 h, etiquetado y `--rollback` 8 h, `extra_hosts` 1 h, tests sobre `compose config` y dobles de `subprocess` 5 h, ensayo aislado de retroceso 4 h, documentación 2,5 h.
- **Previsión IA**: 1,10 M in / 0,10 M out tok (4,0 h IA base) · ⚠️ verificar €.
- **Coste**: (36 h × 50 €/h) + tokens = **1.800 € + tokens**.
- **Impacto / áreas afectadas**: `docker-compose.yml`, `scripts/deploy-memory.py`, `worker.py` (latido), `web/` (ruta de salud del proxy), `test_deploy.py`, `test_deploy_isolation.py`, `docs/operations.md`, `docs/configuration.md`.
- **Dependencias y prerequisitos**: C-02 (el latido vive en el bucle del worker); P-08.
- **Riesgos**: R-06 (límites de memoria demasiado bajos que matan a PostgreSQL o al worker durante el relleno); R-08 (el `docker-compose.yml` y la plantilla del proxy los usa también la instalación desplegada: un cambio en el árbol afecta a su próximo `up`, aunque esta iniciativa no despliegue); el retroceso es de imágenes, no de datos, y se apoya en que las migraciones sean aditivas.
- **Incógnitas / preguntas abiertas**: P-08.

### C-05 — Abstención (M-01), visible para clientes

- **Requisito origen**: M-01 (se apoya en T-27 de la Iniciativa 1); spec CA-26…CA-29.
- **Clase / primer oráculo**: capacidad nueva visible para clientes · pregunta negativa con `abstain` → `items: []` y `abstained: true`.
- **Descripción**: señal absoluta (mejor similitud semántica y `lexical_match`), umbral por modelo; parámetro `abstain` y `MEMORY_ABSTAIN_DEFAULT`; campos `abstained` y `abstention` opcionales en ambos contratos; ≥ 20 preguntas negativas; métricas de abstención y umbrales en `retrieval-eval`; prueba de rojo; nota para la Iniciativa 7.
- **Complejidad**: Media-Alta (la decisión es estadística y el contrato es público).
- **Esfuerzo**: 28 h base (33,6 h con margen) · confianza Media-Baja. Desglose: diseño de la señal 4 h, implementación en `retrieval.py` y modelos 5 h, conjunto de negativas 4 h, métricas, umbrales y prueba de rojo en la puerta 4 h, contratos y kairos-mcp regenerado 2 h, tests 5 h, medición con el modelo real si se aprueba P-05 2,5 h, documentación y nota de cambio 1,5 h.
- **Previsión IA**: 1,03 M in / 0,09 M out tok (3,7 h IA base) · ⚠️ verificar €.
- **Coste**: (33,6 h × 50 €/h) + tokens = **1.680 € + tokens**.
- **Impacto / áreas afectadas**: `retrieval.py`, `models.py`, `config.py`, `store_vectors.py` (exponer la similitud a la fusión), `tests/retrieval_eval/`, `docs/contracts/*.json`, `scripts/export-contracts.py`, `mcp/` (esquemas generados del contrato), `CHANGELOG*.md`.
- **Dependencias y prerequisitos**: P-04 y P-05; coordinación con la Iniciativa 7 (en paralelo).
- **Riesgos**: R-07 (umbral calibrado con embeddings simulados que no vale con el modelo real); R-09 (`additionalProperties: false` en el esquema de resultado: un cliente estricto rechaza el campo nuevo); la abstención se apoya en la capa semántica, y cuando está `degraded` (sin vectores, plazo) no hay señal: debe responder sin abstener.
- **Incógnitas / preguntas abiertas**: P-04, P-05.

### C-06 — Sonda y cola atascada (M-06)

- **Requisito origen**: M-06; spec CA-30…CA-33. Criterio de cierre 3.
- **Clase / primer oráculo**: capacidad nueva · con `memory-worker` parado, la sonda termina ≠ 0 con `stage=index`.
- **Descripción**: `admin probe` (o script) contra `/v1` con clave de alcance limitado a `kairos-probe`; etapas escribir, esperar recibo, buscar y retirar; métricas y log; servicio `memory-probe` con intervalo; `kairos_jobs_oldest_pending_seconds`; aviso de cola en disco en `kairos doctor`; reglas Prometheus de ejemplo.
- **Complejidad**: Media.
- **Esfuerzo**: 26 h base (31,2 h con margen) · confianza Media. Desglose: núcleo de la sonda 6 h, aprovisionamiento de proyecto y clave 3 h, métricas y antigüedad de cola 3 h, servicio e intervalo 3 h, aviso en `kairos doctor` 3 h, tests (servidor, cliente y ensayo con worker parado) 6 h, documentación 2 h.
- **Previsión IA**: 0,96 M in / 0,08 M out tok (3,5 h IA base) · ⚠️ verificar €.
- **Coste**: (31,2 h × 50 €/h) + tokens = **1.560 € + tokens**.
- **Impacto / áreas afectadas**: `admin.py` o `scripts/`, `observability.py`, `docker-compose.yml`, `client/lib/outbox.mjs`, `client/lib/mcp.mjs` (`doctor`), tests del cliente, `docs/operations.md`.
- **Dependencias y prerequisitos**: C-04 (servicio y ensayo); P-06 y P-07.
- **Riesgos**: la sonda en producción escribe y retira cada intervalo y deja lápidas en `kairos-probe` (crecimiento acotado pero continuo; la retención de C-02 no borra recuerdos); su clave es una credencial más que custodiar (Iniciativa 4).
- **Incógnitas / preguntas abiertas**: P-06, P-07.

### C-07 — Tests (B-15)

- **Requisito origen**: B-15; spec CA-34…CA-36.
- **Clase / primer oráculo**: refactor de pruebas + cobertura · los tests nuevos de límites fallan si se retira el control.
- **Descripción**: proxy TCP cortable en proceso delante del PostgreSQL efímero (base de los oráculos de C-02 y C-03); tests de `body_too_large`, `/v1/users`, `/health/ready` y `work_budget_exceeded`; sustitución de los tests que comparan texto SQL o trocean `schema.sql`.
- **Complejidad**: Baja-Media.
- **Esfuerzo**: 18 h base (21,6 h con margen) · confianza Media-Alta. Desglose: arnés de fallos 5 h, casos de concesión expirada y venenoso 2 h (los de base caída cuentan en C-02), tests de límites 5 h, tests frágiles 6 h.
- **Previsión IA**: 0,66 M in / 0,06 M out tok (2,4 h IA base) · ⚠️ verificar €.
- **Coste**: (21,6 h × 50 €/h) + tokens = **1.080 € + tokens**.
- **Impacto / áreas afectadas**: `server/memory_platform/tests/` (arnés nuevo, `test_api.py`, `test_chunk_schema.py` y equivalentes), `run_postgres.py` si el proxy necesita un puerto propio.
- **Dependencias y prerequisitos**: ninguna; va primero.
- **Riesgos**: el arnés de cortes es en sí una fuente de tests frágiles en CI (aprendizaje 2 de la retro): debe ser determinista (cortar y restaurar por orden explícito, sin esperas).
- **Incógnitas / preguntas abiertas**: ninguna.

### Líneas transversales (no son características, pero se presupuestan aparte)

| Línea | Base | Con margen | Coste | Tokens (in/out) | Motivo |
|---|---|---|---|---|---|
| Integración, ensayo de cierre y documentación | 12 h | 14,4 h | 720 € | 0,44 M / 0,04 M | Ensayo aislado con los tres criterios de cierre (CA-37), manuales y changelog (CA-38), contratos regenerados |
| Revisión adversarial | 130 h | 156 h | 7.800 € | 4,78 M / 0,42 M | 1,0 × C-03 y C-05 (58 h) + 0,5 × el resto de la implementación (72 h), según la retro de la Iniciativa 2 |
| Proceso (spec + evaluación + plan) | — | — | tokens | medido en `generacion:` | LES-008: coste de proceso aparte |

---

## Comparativa

Ordenada por el orden de trabajo recomendado.

| # | Característica | Hito | Complejidad | Horas (con margen) | Coste € (desarrollo) | Tokens | Prioridad | Confianza |
|---|---------------|------|-------------|-------|---------|--------|-----------|-----------|
| C-07 | Tests y arnés de fallos | A | Baja-Media | 21,6 h | 1.080 € | 0,72 M | Alta | Media-Alta |
| C-02 | Worker | A | Media | 36 h | 1.800 € | 1,20 M | Crítica | Media |
| C-03 | Conexiones y plazos | A | Media-Alta | 36 h | 1.800 € | 1,20 M | Alta | Media-Baja |
| C-01 | Copias | A | Media-Alta | 48 h | 2.400 € | 1,60 M | Crítica | Media |
| C-04 | Despliegue | B | Media | 36 h | 1.800 € | 1,20 M | Alta | Media |
| C-06 | Sonda y cola atascada | B | Media | 31,2 h | 1.560 € | 1,04 M | Alta | Media |
| C-05 | Abstención | B | Media-Alta | 33,6 h | 1.680 € | 1,12 M | Media | Media-Baja |
| — | Integración, ensayo y docs | A+B | — | 14,4 h | 720 € | 0,48 M | — | Media |
| — | Revisión adversarial | A+B | — | 156 h | 7.800 € | 5,20 M | — | Media |
| | **Total** | | | **412,8 h** | **20.640 €** | **13,76 M** | | |

**Corte propuesto en hitos** (P-09; no quita alcance). La revisión se asigna al hito de cada característica.

| Hito | Contenido | Criterios de cierre del plan director | Implementación (con margen) | Revisión (con margen) | Integración (con margen) | Total |
|---|---|---|---|---|---|---|
| A · no perder datos ni parar | C-07, C-02, C-03, C-01 | 1 (restauración desde la copia externa) y 2 (el worker sobrevive a la caída de base) | 141,6 h | 88,8 h | 7,2 h | **237,6 h · 11.880 €** |
| B · desplegar y detectar | C-04, C-06, C-05 | 3 (la sonda detecta un worker parado) | 100,8 h | 67,2 h | 7,2 h | **175,2 h · 8.760 €** |

>> Revisión base por hito: A = 0,5 × (18 + 30 + 40) + 1,0 × 30 (C-03) = 74 h → 88,8 h con margen; B = 0,5 × (30 + 26) + 1,0 × 28 (C-05) = 56 h → 67,2 h. La integración (14,4 h) se reparte a partes iguales. Suma de los dos hitos: 412,8 h · 20.640 €.
---

## Presupuesto total

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 344 h × 50 €/h (202 h implementación + 12 h integración + 130 h revisión) | 17.200 € |
| Margen de contingencia | +20 % sobre desarrollo base (68,8 h) | 3.440 € |
| Tokens IA (input) | 12,64 M tok × precio input | ⚠️ verificar |
| Tokens IA (output) | 1,12 M tok × precio output | ⚠️ verificar |
| **Total estimado (con margen)** | 20.640 € + (12,64 × P_in + 1,12 × P_out) €, con P en €/1M tokens | **20.640 € + tokens ⚠️ verificar** |

> Opcional fuera del total: medir el umbral de `nomic-embed-text` con un Ollama efímero y aislado (P-05) ya está dentro de C-05 (2,5 h). Si el orquestador lo difiere a la Iniciativa 5, C-05 baja unas 3 h con margen (−150 €).

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 412,8 h (344 h base) |
| Horas IA (ejecución) | 55,0 h (45,9 h base = 13,76 M tokens facturables ÷ 300.000 tok/h) |
| Supervisión humana | 13,8 h (25 % de 55,0 h) |
| **Horas totales (IA + supervisión)** | **68,8 h** |
| Horas ahorradas | 344,0 h |
| **Ahorro** | **83 %** |
| **Multiplicador de productividad** | **×6,0** |
| FTE equivalentes *(opcional)* | 2,2 |

> Horas con el margen del 20 % ya aplicado. Si se repite la desviación de la Iniciativa 2 (−66 %), las horas IA serían ≈ 18,7 h y la supervisión ≈ 4,7 h; no se aplica a la cifra nominal porque las dos filas de `CALIBRATION.md` son cotas inferiores sin ratio medido. Las horas IA no incluyen el reloj de la suite en contenedor (764 tests), de los ensayos aislados ni de la CI, que en esta iniciativa pesan más que en la 2: hay al menos seis ensayos aislados (CA-05, CA-06, CA-07, CA-24, CA-31, CA-37) y se ejecutan de uno en uno. Para que esta iniciativa calibre, cada `T-XX` **y cada intento de revisión** deben abrir y cerrar `usage-meter`.

---

## Recomendación

- **Veredicto**: **go**, en dos hitos. P-01…P-04 y P-06…P-10 son técnicas y el orquestador puede cerrarlas con las recomendaciones de la spec. P-05 solo necesita al usuario si se acepta descargar `nomic-embed-text` en un Ollama efímero propio; si no, la abstención sale sin umbral para el modelo real y se calibra en la Iniciativa 5, sin bloquear el resto.
- **Quick wins** (bajo coste, alto valor):
  - C-07: el arnés de cortes de base es el oráculo de todo el hito A y cierra B-15;
  - dentro de C-04: rotación de logs, `extra_hosts` y límites (unas 3,5 h base) cierran tres puntos de O-05 y O-06 que el VPS necesita sí o sí;
  - dentro de C-01: el plazo propio (O-03, 1,5 h base) quita un aborto seguro con una base grande.
- **Costosas / a valorar**:
  - C-01 es la partida mayor, pero es la condición de la Iniciativa 5 (copia externa cifrada y restauración probada);
  - C-03 tiene poca superficie de código y mucho riesgo transversal: revisión a 1,0 ×;
  - C-05 es la única capacidad visible para clientes y su calibración real depende de P-05. **Alternativa explícita** (no recomendada): moverla a la Iniciativa 8, junto a la puntuación con recencia y uso (punto 6). Ahorraría 33,6 h + 33,6 h de revisión con margen (≈ 3.360 €), pero saca M-01 del plan director de la 3 y habría que decírselo al usuario. Se recomienda mantenerla, opcional y apagada por defecto (P-04).
- **Orden sugerido**: C-07 → C-02 → C-03 → C-01 (hito A, PR propio) → C-04 → C-06 → C-05 (hito B).
  - El arnés va primero: es el primer oráculo de C-02 y C-03.
  - C-02 antes que C-03: el bucle con espera del worker debe existir antes de introducir el pool y los errores `store_busy`/`store_timeout`, que el worker ha de clasificar como «base no disponible».
  - C-01 después de C-03: los subcomandos de copia deben quedar fuera del `statement_timeout`.
  - C-04 abre el hito B porque el latido y los servicios nuevos (`memory-backup`, `memory-probe`) viven en Compose.
  - C-05 va al final, coordinado con la Iniciativa 7, por ser el único cambio visible para clientes.
  - Respecto del encargo, cambian de posición los tests (de 7.º a 1.º) y la abstención (de 5.º a último).
- **Fuera de alcance recomendado**: despliegue real, nube real y envío de alertas a personas (Iniciativa 5); retirada del MCP interno (0.5.0); lock de dependencias con hashes (B-19, Iniciativa 9). La dependencia nueva `psycopg_pool` se fija por versión, como el resto.

---

## Riesgos transversales

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **R-01 Esperas que esconden una caída**: un worker que espera para siempre parece sano | Media | Alto | El latido deja de avanzar si la base lleva caída más que un umbral; métrica de errores de base; la sonda (C-06) lo detecta de extremo a extremo |
| **R-02 `statement_timeout` corta trabajo legítimo**: migraciones, relleno, `content-manifest`, copias, `graph_data` | Media | Alto | Plazo solo en las conexiones de servicio; `admin` sin límite; tests que ejecutan `migrate` y `backfill-chunks` con el plazo activo en la API |
| **R-03 Clave privada perdida o expuesta**: sin ella no hay restauración; con ella en el VPS, el cifrado no protege | Baja | Alto | Cifrado de clave pública; el runbook exige la custodia fuera del VPS y un ensayo de descifrado; CA-08 comprueba que no se monta |
| **R-04 Retención que cambia lo que ven los clientes**: `events` sostiene `event_status`, la actividad y `get_tool_uses` | Media | Medio | `events` sin retención por defecto (P-03); `--dry-run`; nunca en migraciones; declararlo a la Iniciativa 7 si se activa |
| **R-05 Caché de permisos que relaja la revocación** | Baja | Alto | Caché limitada a la transacción; test de revocación en la petición siguiente; revisión a 1,0 × en C-03 |
| **R-06 Límites de recursos que matan servicios** durante el relleno o la verificación de copias | Media | Medio | Valores por defecto medidos en el ensayo aislado; variables por servicio; documentados para 32 GB y para un VPS pequeño |
| **R-07 Umbral de abstención no transferible**: calibrado con embeddings simulados | Alta | Medio | Umbral por modelo; sin umbral, no se abstiene (`uncalibrated`); medición real según P-05 |
| **R-08 Ficheros del árbol montados por la instalación desplegada**: `ollama-proxy/default.conf.template` y `docker-compose.yml` (aprendizaje 3 de la retro) | Media | Alto | No cambiar la plantilla montada; los cambios de Compose los recoge la instalación solo en su próximo `up`, que es de la Iniciativa 5; los ensayos usan un *override* con nombres propios; CA-38 comprueba que nada apunta a `knowledge-graphs-*` |
| **R-09 Cliente estricto frente al campo nuevo**: `result_schemas.search` con `additionalProperties: false` | Media | Medio | El campo solo aparece si se pide (`abstain`) o si el operador lo activa (P-04); changelog y nota a la Iniciativa 7 |
| **R-10 Bucles de revisión y ensayos lentos**: la retro midió hasta 6 intentos en una fase; aquí hay seis ensayos aislados de uno en uno | Alta | Medio | Revisión como partida propia (156 h con margen); arreglar la clase entera en la primera corrección; ensayos agrupados en CA-37; `usage-meter` por tarea e intento |
| **R-11 Tests con tiempos**: *backoff*, plazos, latido y sonda dependen del reloj | Alta | Medio | Relojes inyectados y `threading.Event`; nada de `sleep` para esperar un estado (aprendizaje 2 de la retro) |

---

## Siguiente paso

Para **ejecutar** lo aprobado, genera el plan detallado con el agente **`planner`**, que crea `improvement-plan.md` y `tasks.md` en `docs/roadmap/2026-11-15-reliable-operations/`. Se recomienda aprobar **las siete características**, en dos hitos: A (C-07 → C-02 → C-03 → C-01) y B (C-04 → C-06 → C-05). El `planner` hereda horas y costes por característica, presupuesta la revisión por fase (0,5 × la implementación, 1,0 × en C-03 y C-05), exige `usage-meter` por `T-XX` y por intento de revisión y actualiza la fila **Plan** de esta evaluación y el campo `plan:` de la spec.

---

## Changelog

- 2026-11-15 — Creación (evaluator). Estado `en-revision`. Spec creada en `borrador` y enlazada en ambos sentidos.
- 2026-11-15 — Puerta **go** (orquestador, decisiones delegadas por el usuario): evaluación `completado`, spec `aprobada`; P-01 a P-10 adoptadas como se recomiendan.
- 2026-11-15 — Plan creado (planner): 98 tareas en 16 fases, mismas cifras (412,8 h · 20.640 €); fila **Plan** enlazada.
