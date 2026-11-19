---
design: n/a
test-plan: n/a (sin UI)
generacion:
  inicio: 2026-11-15T14:59:36Z
  fin: 2026-11-15T15:13:35Z
  fuente: medido
  fuente_id: src-8ffaaac4e3b9a11805b5148dbea387f65be01b42fba05cbf3ca54c4b799a95c8
  ventana_id: win-0c98ac585a4c4a9c84a654dc295181da
  revision_medicion: 1
  medicion_persistida: true
  tokens_reales: { entrada: 42, salida: 83827, cache_creacion: 110341, cache_lectura: 2993293 }
  eur: null
  horas_ia: 0.65
  duracion: 39m
  ratio_usado: 300000
---

# 2026-11-15-reliable-operations

> Operación fiable de Kairos: copias verificadas, cifradas y externas con runbook de restauración, worker resistente a caídas de base, pool y plazos, despliegue con límites, bloqueo y retroceso, abstención calibrada y sonda de ida y vuelta (Iniciativa 3 del plan director).

| | |
|---|---|
| **Fecha** | 2026-11-15 |
| **Estado** | en-progreso |
| **Tipo** | Infra |
| **Prioridad** | Alta |
| **Solicitante** | Daycry (plan director, Iniciativa 3) |
| **Responsable** | Daycry |
| **Spec** | [`spec.md`](spec.md) |
| **Evaluación** | [`evaluation.md`](evaluation.md) |
| **Diseño** | n/a (sin paso de diseño; las decisiones están en la tabla «Decisiones de diseño» de la spec, P-01 a P-10 decididas el 2026-11-15) |

---

## Cuadro de mando

| Métrica | Estimado | Real | Confianza |
|--------|---------|------|-----------|
| Tiempo humano | **412,8 h** (344,0 h base +20 %), de ellas 156,0 h de revisión adversarial | 0 h | Media |
| Tiempo IA (ejecución) | **55,0 h** (45,9 h base +20 %) (+ 13,8 h supervisión) | 0 h | Baja |
| Coste total | **20.640 €** de desarrollo + tokens ⚠️ verificar | 0 € | Media (desarrollo) / sin cifra (tokens) |
| Tokens IA | **13,76 M** (in 12,66 M / out 1,10 M) | 0 | Baja |
| Multiplicador productividad | **×6,0** | — | — |
| Tareas | **98** en 16 fases | 0 hechas | — |

> Frente a la evaluación (412,8 h, 20.640 €, 13,76 M tokens): **sin diferencias**; el plan reparte sus cifras por característica en tareas y no re-estima. Hito A «no perder datos ni parar» 237,6 h · 11.880 €; hito B «desplegar y detectar» 175,2 h · 8.760 € (coinciden con la evaluación: 237,6 h y 175,2 h). La revisión adversarial es partida propia por fase (0,5 × la implementación; 1,0 × en C-03 y C-05). Las horas IA nominales (55,0 h) no se ajustan por las desviaciones de las Iniciativas 1 y 2 (−73 % y −66 %, cotas inferiores); con ese ajuste serían ≈ 19 h. Horas humanas e IA no se suman (LES-007).

---

## Estimación por fase

| Fase | Hito | Estimado (h, con margen) | De ellas, revisión (h) | Tokens (in / out) | Coste € |
|------|------|-------------|-----|-------------------|---------|
| Fase 1 — Arnés de fallos y tests de límites (C-07) | A | 32,4 | 10,8 | 994 k / 86 k | 1.620 |
| Fase 2 — Worker resistente a la caída de base (C-02, B-03) | A | 27,0 | 9,0 | 828 k / 72 k | 1.350 |
| Fase 3 — Cola: índices parciales y retención de tablas (C-02, B-06) | A | 27,0 | 9,0 | 828 k / 72 k | 1.350 |
| Fase 4 — Pool y plazos de conexión (C-03, B-02 y B-07) | A | 48,0 | 24,0 | 1472 k / 128 k | 2.400 |
| Fase 5 — Permisos por transacción (C-03, B-02) | A | 24,0 | 12,0 | 736 k / 64 k | 1.200 |
| Fase 6 — Copias locales: integridad, cifrado, retención y verificación (C-01) | A | 43,2 | 14,4 | 1325 k / 115 k | 2.160 |
| Fase 7 — Copia externa programada y runbook de restauración (C-01) | A | 28,8 | 9,6 | 883 k / 77 k | 1.440 |
| Fase 8 — Cierre del hito A: no perder datos ni parar | A | 7,2 | 0,0 | 221 k / 19 k | 360 |
| Fase 9 — Compose: límites, healthchecks, rotación y `extra_hosts` (C-04) | B | 19,8 | 6,6 | 607 k / 53 k | 990 |
| Fase 10 — Despliegue: bloqueo, etiquetado y retroceso (C-04) | B | 34,2 | 11,4 | 1049 k / 91 k | 1.710 |
| Fase 11 — Sonda de ida y vuelta (C-06) | B | 23,4 | 7,8 | 718 k / 62 k | 1.170 |
| Fase 12 — Cola atascada, servicio de sonda y `kairos doctor` (C-06) | B | 23,4 | 7,8 | 718 k / 62 k | 1.170 |
| Fase 13 — Abstención: señal absoluta, parámetro y contratos (C-05) | B | 33,6 | 16,8 | 1030 k / 90 k | 1.680 |
| Fase 14 — Calibración de la abstención y puerta `retrieval-eval` (C-05) | B | 33,6 | 16,8 | 1030 k / 90 k | 1.680 |
| Fase 15 — Cierre del hito B: desplegar y detectar | B | 2,4 | 0,0 | 74 k / 6 k | 120 |
| Fase 16 — Cierre de la iniciativa: ensayo, CHANGELOG y versión 0.4.1 | B | 4,8 | 0,0 | 147 k / 13 k | 240 |
| **Total** | | **412,8 h** | **156,0 h** | **12659 k / 1101 k** | **20.640 €** |

Reparto por característica de la evaluación (horas base de implementación): C-07 18 h (Fase 1) · C-02 30 h (Fases 2 y 3) · C-03 30 h (Fases 4 y 5) · C-01 40 h (Fases 6 y 7) · C-04 30 h (Fases 9 y 10) · C-06 26 h (Fases 11 y 12) · C-05 28 h (Fases 13 y 14) = 202 h; integración y cierre 12 h (Fases 8, 15 y 16); revisión adversarial 130 h: 0,5 × (C-07 18 + C-02 30 + C-01 40 + C-04 30 + C-06 26) + 1,0 × (C-03 30 + C-05 28). Total 344 h base. Cada fase tiene su suite completa y su revisión como tareas propias.

---

## Presupuesto económico

**Coste = (horas × tarifa) + coste de tokens de IA.** Todos los importes en **EUR**.

### Supuestos (ajustables)

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Tarifa de desarrollo | 50 €/h | Valor por defecto del kit (sin `.claude/rates.json`) |
| Modelo IA asumido | Claude Opus (familia vigente en el ciclo) | Igual que la evaluación |
| Precio input | ⚠️ verificar € / 1M tokens | Sin `precioTokens` fiable; ejecutar la skill `rates-verify` |
| Precio output | ⚠️ verificar € / 1M tokens | Ídem |
| Tipo de cambio | 1 USD = 0,92 € | Valor por defecto del kit |
| Margen de contingencia | 20 % | Sobre horas base humanas e IA, revisión incluida |
| Supervisión humana | 25 % de las horas IA | Valor por defecto; en las iniciativas anteriores quedó corto (la revisión por intentos lo desborda) |
| Ratio tokens→hora IA | 300.000 tok/h | Valor no calibrado (heredado de la evaluación; `CALIBRATION.md` sin ratio medido) |
| Tokens por hora humana base | ~40.000 facturables (92 % entrada / 8 % salida) | Derivado de la Iniciativa 2; los tokens no llevan margen |
| Revisión adversarial | 0,5 × implementación; 1,0 × en C-03 y C-05 | Partida propia por fase (retro de la Iniciativa 2) |

### Desglose

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 344,0 h × 50 €/h (202 h implementación + 12 h integración + 130 h revisión) | 17.200 € |
| Margen de contingencia | +20 % sobre desarrollo base (68,8 h) | 3.440 € |
| Tokens IA (input) | 12,66 M tok × precio | ⚠️ verificar |
| Tokens IA (output) | 1,10 M tok × precio | ⚠️ verificar |
| **Total estimado (con margen)** | | **20.640 € + tokens ⚠️ verificar** |

> Si la medición de `nomic-embed-text` (P-05, T-89) queda `uncalibrated` por fallo de descarga, sus 2,5 h base se conservan para la medición en la Iniciativa 5, no se descuentan.

---

## Previsión de tokens (por fase)

Base: Claude Opus; precios sin verificar.

| Fase | Input (tok) | Output (tok) | Total (tok) | Coste € |
|------|------------|-------------|-------------|---------|
| Fase 1 | 994 k | 86 k | 1080 k | ⚠️ verificar |
| Fase 2 | 828 k | 72 k | 900 k | ⚠️ verificar |
| Fase 3 | 828 k | 72 k | 900 k | ⚠️ verificar |
| Fase 4 | 1472 k | 128 k | 1600 k | ⚠️ verificar |
| Fase 5 | 736 k | 64 k | 800 k | ⚠️ verificar |
| Fase 6 | 1325 k | 115 k | 1440 k | ⚠️ verificar |
| Fase 7 | 883 k | 77 k | 960 k | ⚠️ verificar |
| Fase 8 | 221 k | 19 k | 240 k | ⚠️ verificar |
| Fase 9 | 607 k | 53 k | 660 k | ⚠️ verificar |
| Fase 10 | 1049 k | 91 k | 1140 k | ⚠️ verificar |
| Fase 11 | 718 k | 62 k | 780 k | ⚠️ verificar |
| Fase 12 | 718 k | 62 k | 780 k | ⚠️ verificar |
| Fase 13 | 1030 k | 90 k | 1120 k | ⚠️ verificar |
| Fase 14 | 1030 k | 90 k | 1120 k | ⚠️ verificar |
| Fase 15 | 74 k | 6 k | 80 k | ⚠️ verificar |
| Fase 16 | 147 k | 13 k | 160 k | ⚠️ verificar |
| **Total** | **12659 k** | **1101 k** | **13760 k** | **⚠️ verificar** |

**Método de estimación:** se hereda la previsión por característica de la evaluación (13,76 M tokens facturables = 344 h base × ~40.000) y se reparte entre las tareas por horas base; la revisión toma su parte proporcional. Tokens facturables: entrada no cacheada + creación de caché + salida. Las cifras por tarea son orientativas y se calibran con `usage-meter` (cada tarea y cada intento de revisión abre y cierra su medición).

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 412,8 h (344,0 h base +20 %) |
| Horas IA (ejecución) | 55,0 h (45,9 h base +20 %; supuesto: 13,76 M tok ÷ 300.000 tok/h) |
| Supervisión humana | 13,8 h (25 % de las horas IA) |
| **Horas totales (IA + supervisión)** | **68,8 h** |
| Horas ahorradas | 344,0 h |
| **Ahorro** | **83 %** |
| **Multiplicador de productividad** | **×6,0** |
| FTE equivalentes *(opcional)* | 2,1 |

> Horas con el margen del 20 % ya aplicado. Las horas IA son una estimación aproximada y no incluyen el reloj de la suite en contenedor (764 pruebas), de la CI ni de los ensayos aislados, que aquí pesan más que en la Iniciativa 2: seis ensayos aislados (CA-05, CA-06/07, CA-24, CA-31, CA-37 y el de `retrieval-eval` con Ollama efímero) de uno en uno.

---

## Resumen ejecutivo

Kairos ya tiene tres componentes y CI, pero no está listo para operar sin supervisión en un VPS. Este plan lo prepara en dos hitos sobre la misma rama: **A «no perder datos ni parar»** (arnés de fallos, worker resistente, cola con índices y retención, pool y plazos, copias verificadas, cifradas y externas con runbook de restauración) y **B «desplegar y detectar»** (límites, healthchecks, bloqueo y retroceso de despliegue, sonda de ida y vuelta y abstención calibrada).

Son 98 tareas en 16 fases pequeñas. Cada fase cierra con la suite completa del servidor en verde (subiendo `KAIROS_MIN_TESTS`/`MIN_FLOOR`) y con su revisión adversarial de dos lentes como tarea propia, presupuestada aparte. Cada hito cierra con su ensayo aislado y su PR (solo con OK del usuario) y la iniciativa con el ensayo de cierre CA-37, el CHANGELOG y la versión 0.4.1. No hay interfaz web nueva.

### Objetivos

- Copia cifrada con `age`, verificada por sha256, con retención, externa y restaurable con un runbook ensayado (`restored_and_content_verified`) (CA-01 a CA-08).
- Worker que sobrevive a la caída de la base sin perder ni envenenar trabajos, cola indexada y retención por lotes (CA-09 a CA-14).
- Conexiones y plazos acotados: pool, `connect_timeout`, `statement_timeout`, 503 `store_timeout`/`store_busy` y permisos por transacción (CA-15 a CA-19).
- Despliegue con límites, healthchecks, rotación de logs, `extra_hosts`, bloqueo, etiquetado y `--rollback` (CA-20 a CA-25).
- Búsqueda capaz de decir «nada relevante», opcional y apagada por defecto, con contrato solo aditivo (CA-26 a CA-29).
- Sonda de ida y vuelta que detecta un worker parado y aviso de cola atascada (CA-30 a CA-33).
- Arnés de fallos y tests de límites que fallan si se quita el control (CA-34 a CA-36); ensayo de cierre y puertas finales (CA-37, CA-38).

---

## Datos necesarios para un informe completo

- [x] **Requisitos funcionales** confirmados por el solicitante (spec `aprobada`; P-01 a P-10 decididas el 2026-11-15, delegadas por el usuario)
- [x] **Alcance** cerrado (spec §Alcance: dentro C-01 a C-07; fuera despliegue real, nube real y alertas a personas)
- [x] **Criterios de éxito / métricas** acordados (CA-01 a CA-38)
- [x] **Accesos y credenciales** necesarios (ninguno: fixtures aislados; clave `age` de prueba generada en el test)
- [x] **Entornos** disponibles (PostgreSQL efímero del target `test`; proyecto Compose aislado con nombre distinto de `knowledge-graphs`; Ollama efímero propio para P-05)
- [x] **Stakeholders** identificados (solicitante único; coordinación con la Iniciativa 7 por el cambio visible de la abstención)
- [ ] **Dependencias externas** mapeadas: `age` y `rclone` fijables en bookworm (hipótesis, T-36 y T-44); descarga de `nomic-embed-text` (P-05); OK del usuario para los dos PR
- [x] **Restricciones** conocidas (sin pruebas contra la base desplegada, migraciones y contrato aditivos, nada publicado)
- [ ] **Tarifa/hora y supuestos de coste** confirmados (valor por defecto 50 €/h; precio de tokens ⚠️ verificar)

---

## Análisis de impacto

- **`server/memory_platform/`** — `admin.py` (subcomandos `verify-backup`, `backup-cycle`, `prune-tables`, `probe`; `backup` ampliado), `worker.py` (clasificación de errores, espera, latido), `store.py` (pool y opciones de conexión), `store_auth.py` (caché por transacción), `store_jobs.py` (tope al reclamar, sondeos), `schema.sql` (versión 12), `retrieval.py`/`models.py`/`store_vectors.py` (abstención), `observability.py`, `config.py`, `errors.py`, `app.py`, `requirements.txt`, `Dockerfile` (`age` y `rclone` en `operator`/`test`).
- **`docker-compose.yml`** — límites, healthchecks, rotación, `extra_hosts`, servicios opcionales `memory-backup` y `memory-probe` (perfiles propios). La instalación desplegada recoge los cambios en su próximo `up`; ninguna tarea lo ejecuta.
- **`scripts/`** — `deploy-memory.py` (`--backup-timeout`, `--verify-backup`, bloqueo, etiquetado, `--rollback`), `rehearse-restore.py` y `rehearse-reliable-operations.py` (ensayos aislados), `export-contracts.py`.
- **`client/`** — `kairos doctor` informa de la antigüedad de la cola en disco (`lib/outbox.mjs`, `lib/mcp.mjs`).
- **`docs/contracts/`**, **`mcp/contract/`** — `abstain`, `abstained`, `abstention` solo aditivos.
- **`server/memory_platform/tests/`** — arnés `fault_proxy.py`, tests de límites, de esquema por catálogo, de worker, pool, copias, despliegue, sonda y abstención; conjunto `dataset-v1-negatives.jsonl` y métricas de abstención en `retrieval_eval/`.
- **`docs/`**, **`CHANGELOG*.md`**, versiones 0.4.1 — manuales, runbook de restauración, nota para la Iniciativa 7.
- **`.github/workflows/ci.yml`**, **`scripts/tests/test_ci_workflow.py`** — mínimo de la suite y puerta de abstención.

---

## Cambios arquitectónicos

- **Orden C-07 → C-02 → C-03 → C-01 (hito A) y C-04 → C-06 → C-05 (hito B)** (P-09): el arnés es el oráculo de C-02 y C-03; C-02 antes que C-03 para que el worker ya clasifique `store_busy`/`store_timeout`; C-01 después de C-03 para que las copias queden fuera del `statement_timeout`; C-05, el único cambio visible para clientes, al final.
- **Cifrado `age` con clave pública** (P-01): el servidor cifra y no puede descifrar; la clave privada no está en el host ni en el repo (CA-08).
- **Manifiesto `<copia>.json`** con sha256 del fichero cifrado: `verify-backup` y la copia externa verifican sin descifrar.
- **`StoreUnavailable`** distingue «la base no responde» de «el proveedor falló»; un fallo de base no consume intento (CA-11).
- **Tope al reclamar** (`attempts_exhausted`) y **migración 12 aditiva** con índices parciales; la retención es `admin prune-tables`, nunca una migración; `events` sin retención por defecto (P-03).
- **Pool y plazos como opciones de conexión de servicio**; `admin` sin límite; caché de permisos limitada a la transacción (R-05).
- **Despliegue**: latido del worker en `/tmp`, bloqueo exclusivo con `--break-lock`, etiquetas locales `<versión>-<marca>` y `--rollback` sin migrar (P-08).
- **Abstención por señal absoluta** (similitud semántica + `lexical_match`), por modelo, opcional y apagada por defecto (P-04, P-05); sin umbral, `uncalibrated`.
- **Sonda** contra `/v1` con clave acotada a `kairos-probe`; canal de alerta = métrica, evento de log y código de salida (P-06); envío a personas en la Iniciativa 5.
- **Ensayos aislados** de uno en uno con `--project-name`; no se tocan ficheros que monta la instalación desplegada (R-08).

---

## Archivos a crear/modificar

| Archivo | Acción | Propósito |
|---------|--------|-----------|
| `server/memory_platform/{admin,worker,store,store_auth,store_jobs,retrieval,models,store_vectors,observability,config,errors,app}.py` | Modificar | Copias, worker, pool, plazos, permisos, abstención, sonda, métricas |
| `server/memory_platform/schema.sql` | Modificar | Versión 12: índices parciales de cola (aditiva) |
| `server/memory_platform/{requirements.txt,Dockerfile}` | Modificar | `psycopg_pool`; `age` y `rclone` en `operator` y `test` |
| `server/memory_platform/tests/{fault_proxy,measure_connections}.py` y tests nuevos | Crear | Arnés de fallos, medición y pruebas por área |
| `server/memory_platform/tests/{test_chunk_schema,test_fts_migration,test_pgvector_migration,test_migrations_additive,test_deploy,test_deploy_isolation,test_observability}.py` | Modificar | Pruebas por catálogo, despliegue y observabilidad |
| `server/memory_platform/tests/retrieval_eval/{dataset-v1-negatives.jsonl,measure_abstention.py}` | Crear | Negativas y medición real del umbral |
| `server/memory_platform/tests/retrieval_eval/{run.py,thresholds.json,check_dataset.py,test_metrics.py,README.md}` | Modificar | Métricas y umbrales de abstención |
| `docker-compose.yml` | Modificar | Límites, healthchecks, rotación, `extra_hosts`, `memory-backup`, `memory-probe` |
| `scripts/deploy-memory.py` | Modificar | `--backup-timeout`, `--verify-backup`, bloqueo, etiquetas, `--rollback` |
| `scripts/{rehearse-restore,rehearse-reliable-operations}.py` y sus tests en `scripts/tests/` | Crear | Ensayos aislados |
| `scripts/export-contracts.py`, `docs/contracts/*.json`, `mcp/contract/kairos-mcp.json`, `mcp/tests/tool_cases.py` | Modificar | Contratos aditivos de la abstención |
| `client/lib/{outbox,mcp}.mjs`, `client/tests/doctor-outbox.test.mjs`, `client/README.md`, `client/package.json` | Modificar/Crear | `kairos doctor` y versión |
| `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py` | Modificar | Mínimo de la suite y puerta de abstención |
| `docs/{operations,configuration,architecture,manual}.md`, `docs/examples/prometheus-rules.yml`, `CHANGELOG*.md`, `docs/roadmap/**` | Modificar/Crear | Manuales, runbook, reglas de ejemplo, notas de cambio y revisiones |
| `server/VERSION`, `mcp/VERSION` | Modificar | Versión 0.4.1 |

No se aplican `interop/**` ni las piezas de `docs/agents/CONTRACTS.md`: este repositorio no es el kit de agentes. No se toca `ollama-proxy/default.conf.template` ni ningún fichero que monte la instalación desplegada. Ninguna tarea escribe en `docs/roadmap/**/testing/`.

---

## Dependencias y prerequisitos

- **Orden entre fases:** 1 → 2 → … → 16. Hito A = Fases 1 a 8; hito B = Fases 9 a 16. La Fase 2 necesita el arnés de la Fase 1; la Fase 4 necesita la clasificación de la Fase 2; la Fase 7 necesita `age` de la Fase 6; el latido de la Fase 9 usa `last_store_ok` de la Fase 2; la sonda (Fase 11) necesita el servicio de la Fase 9; la Fase 13 precede a la 14.
- **Externa:** OK expreso del usuario para abrir cada PR (T-53 y T-95); sin merges a `main` ni publicación.
- **Externa:** descarga de `nomic-embed-text` (≈ 270 MB) en un Ollama efímero propio (P-05, T-89); si falla, `uncalibrated`.
- **Hipótesis a confirmar pronto:** `age` y `rclone` fijables en Debian bookworm (T-36, T-44); `psycopg_pool` compatible con `psycopg 3.3.7` y `asyncio.to_thread` (T-22); un índice parcial sirve a `claim_job` o se divide en dos sondeos (T-15).
- **Coordinación:** los cambios visibles para clientes (`abstain`/`abstained`, retención) se declaran a la Iniciativa 7 en los CHANGELOG. También los códigos nuevos de `error_code` que ya ve un cliente en `GET /v1/jobs/{id}`, en la métrica `kairos_jobs_failed{code}` y en `POST /v1/jobs/{id}/retry`: `attempts_exhausted` (T-10; un trabajo que agota `MEMORY_MAX_ATTEMPTS` por concesiones perdidas deja de reclamarse y pasa a `failed`) y `store_error` (T-09; un error de la base que no es una caída, p. ej. consulta cancelada o `lock_timeout`, distinguible de `provider_error`; los transitorios `40001`, `40P01`, `57014`, `55P03` y clase `53` se repiten antes dentro del presupuesto de escritura y, agotado, el trabajo se reprograma con `store_error`). También declarar a la Iniciativa 7: el evento de log `job_write_abandoned` (T-09; `reason` = `<acceso>:<motivo>`, con `retry_budget` cuando se agota el presupuesto de reintento), el evento `store_retry`, el evento `job_outcome_unread` (T-09; no se pudo leer el estado del trabajo tras un fallo ambiguo y se da por perdido), la variable nueva `MEMORY_WORKER_WRITE_RETRY_SECONDS` (T-09, por defecto igual a `MEMORY_LEASE_SECONDS`) y que un `MEMORY_MAX_ATTEMPTS` inválido (≤ 0 o no entero), que antes se aceptaba, ahora impide arrancar API, worker y admin (T-10). Cambios visibles de la Fase 3 (T-14 a T-18), uno a uno: (1) comando nuevo `admin prune-tables` (`--dry-run`, `--batch`, `--table`), que nada ejecuta solo; (2) las cinco variables nuevas `MEMORY_RETENTION_LOGIN_ATTEMPTS_DAYS` (30), `_WEB_SESSIONS_DAYS` (30), `_AUDIT_EVENTS_DAYS` (365), `_JOBS_FAILED_DAYS` (90) y `_EVENTS_DAYS` (sin ventana), que solo lee `admin`; (3) tras podar, `GET /v1/jobs/{id}` y `POST /v1/jobs/{id}/retry` de un trabajo huérfano podado (`failed`, de más de 90 días, de una versión anterior o de un recurso inexistente y no citado por un evento conservado) responden 404; un trabajo citado por el recibo de un evento conservado, de la versión actual de un documento o nota, o con recibo de proyección NO se poda, así que `event_status`, el reenvío de `remember`, `document_status` y `backfill-chunks` no cambian; (4) `kairos_jobs_failed`, el recuento de fallidos de la actividad y de `stats`, la lista de trabajos y `counts.jobs` de la herramienta MCP `projects` y de `GET /v1/projects` bajan por los huérfanos podados; (5) si un operador activa `MEMORY_RETENTION_EVENTS_DAYS`, un evento podado deja de aparecer en `event_status`, en la actividad y en `get_tool_uses`, su reenvío idempotente se trata como nuevo y los trabajos que solo citaba pasan a ser podables en la misma ejecución; la ventana debe superar cualquier ventana de reenvío o conciliación de los integradores; (6) cada ejecución real deja una fila `retention_prune` en `audit_events` (días de la ventana y filas borradas por tabla); (7) el esquema pasa a la versión 12 (dos índices parciales en `memory.jobs`, aditivos) y el índice de la versión 1 lleva una guarda: sin cambio de contrato. Cambios visibles de la Fase 4 (T-22 a T-27), uno a uno: (1) dos códigos de error 503 nuevos en la API, con mensaje fijo y `request_id`: `store_busy` («The store is busy; retry shortly»: el pool no dio conexión en `MEMORY_POOL_TIMEOUT`) y `store_timeout` («The store took too long to answer; retry shortly»: PostgreSQL canceló la sentencia en su `statement_timeout`); `kairos-mcp` los muestra tal cual como mensaje del error de la herramienta (antes «Memory service temporarily unavailable»; el contrato `docs/contracts/kairos-mcp.json` no cambia: mismas herramientas y esquemas) y el MCP interno montado en `/mcp` da los mismos textos; una caída de la base sigue siendo 503 `service_unavailable`; (2) cinco variables nuevas, validadas al arrancar (un valor fuera de rango impide arrancar API, worker y `admin`): `MEMORY_POOL_MIN` (1), `MEMORY_POOL_MAX` (10), `MEMORY_POOL_TIMEOUT` (5 s), `MEMORY_CONNECT_TIMEOUT` (5 s) y `MEMORY_STATEMENT_TIMEOUT_MS` (15.000 ms en la API, 30.000 en el worker); (3) dependencia nueva `psycopg-pool 3.3.3` en las imágenes de API, worker y operador; (4) una consulta de servicio que dure más de su plazo se cancela (antes no había plazo) y la API responde 503 `store_timeout`; `admin` (`migrate`, `backfill-chunks`, `backup`, `prune-tables`…) no hereda ningún plazo; (5) eventos de log nuevos `store_busy` y `store_timeout` (nivel `warning`, solo `exc_type` y `request_id`) y `pool_reset_failed`; (6) `MEMORY_WORKER_WRITE_RETRY_SECONDS`: su defecto (`MEMORY_LEASE_SECONDS`) se valida contra 1..86400, y un `MEMORY_LEASE_SECONDS` fuera de ese rango impide arrancar API, worker y `admin` (comparten `Settings.from_env`). Cambios visibles añadidos por la corrección 1 de la Fase 4, uno a uno: (7) `MEMORY_CONNECT_TIMEOUT` pasa de 5 s a 3 s por defecto y `MEMORY_POOL_TIMEOUT` y `MEMORY_CONNECT_TIMEOUT` deben diferir al menos 1 s (con otro par el proceso no arranca: una instalación que fijara los dos cerca, p. ej. ambos a 5, deja de arrancar); (8) cuatro variables nuevas, `MEMORY_TCP_KEEPALIVES_IDLE` (30 s), `MEMORY_TCP_KEEPALIVES_INTERVAL` (10 s), `MEMORY_TCP_KEEPALIVES_COUNT` (3) y `MEMORY_TCP_USER_TIMEOUT_MS` (30.000), validadas al arrancar y no propagadas por el Compose; (9) una conexión del pool que deja de responder sin cerrarse se corta del lado del cliente (`statement_timeout` más 5 s; comprobación y `RESET`, 1 s) y sale como 503 `service_unavailable`; (10) con el pool saturado una búsqueda responde 503 `store_busy` en lugar de 200 con `partial`; (11) `/health/ready` responde 200 con el pool saturado (evento de log `readiness_pool_saturated`) y 503 `not_ready` solo si la base no contesta (la Fase 5 acota los dos casos: cambio (1) de la Fase 5); (12) `MEMORY_LEASE_SECONDS` se valida siempre, también con `MEMORY_WORKER_WRITE_RETRY_SECONDS` fijado. Cambios visibles de la Fase 5 (T-30 a T-33), uno a uno: (1) frente a la Fase 4 (donde un pool con huecos libres que no daba conexión respondía 503 `service_unavailable` y solo uno con todas las conexiones en uso respondía `store_busy`), el 503 `service_unavailable` (la base no contesta) solo sale si el pool tiene registrado un fallo de conexión nueva, o una comprobación al entregar que agotó su plazo (una conexión ociosa que simplemente estaba cortada no cuenta: su reemplazo conecta o falla), desde la última conexión entregada; un pool que no da conexión en `MEMORY_POOL_TIMEOUT` sin ese rastro (todas las conexiones en uso, creciendo bajo carga con la base sana, o una conexión en entrega al que espera) responde 503 `store_busy` aunque queden huecos libres, y con el plazo de conexión por encima de la espera del pool una base muda antes de la primera conexión sale `store_busy` en lectura, escritura y búsqueda (la regla de diferencia mínima de 1 s entre ambos plazos no cambia); `/health/ready` sigue la regla con una excepción: 200 (con `readiness_pool_saturated` si hay conexiones en uso) solo si el pool ya entregó alguna conexión; un pool que nunca entregó ninguna (base muda al arrancar) da 503 `not_ready`, de modo que el contenedor no pasa a healthy; (2) con la base caída o muda dentro de una capa de búsqueda (episódica, documental o semántica) la petición responde 503 `service_unavailable` en lugar de 200 con las capas `unavailable` y `partial`; (3) garantía nueva y documentada (`docs/architecture.md`): los permisos se resuelven una vez por transacción y la revocación de una clave, un usuario, una sesión o una concesión se ve desde la transacción siguiente de cualquier petición, como antes; dentro de una transacción ya abierta la respuesta es la de la primera lectura en ella (READ COMMITTED) y tras esperar un bloqueo se relee, así que una revocación confirmada durante la espera se ve (ingesta, publicación, borrado de documentos y reintento de trabajos responden 401/403; la ingesta vuelve a exigir `write` tras esperar los bloqueos de `item:`); (4) sin variables nuevas, sin cambio de esquema, sin cambio en los códigos de error existentes ni en el contrato MCP; (5) interno: una búsqueda híbrida de 3 proyectos baja de 63 a 49 consultas con el pool (de 49 a 35 sin las 14 del pool). Fase 6 (copias, solo operador; sin cambio en la API, en los códigos de `error_code` ni en el contrato MCP): (1) `admin backup` escribe junto a cada copia su manifiesto `<copia>.json` (sha256, bytes, versión de esquema, hora UTC, `encrypted` y huellas por tabla) y, con destinatarios, publica `<nombre>.age` en lugar del volcado en claro; con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` y sin destinatarios falla con `backup_encryption_required` y no escribe nada; (2) subcomandos y opciones nuevos: `admin verify-backup`, `admin backup --prune --keep N` y `admin restore-check --from-manifest`, con códigos propios `backup_*`; (3) `scripts/deploy-memory.py` gana `--backup-timeout` (3600 s por defecto para `content-manifest`, `backup` y `verify-backup`) y `--verify-backup` (restauración de prueba en un PostgreSQL efímero antes de `migrate`; activo por defecto en los ensayos, opcional en la instalación; con copia cifrada solo verifica integridad); (4) variables nuevas `MEMORY_BACKUP_RECIPIENTS_FILE`, `MEMORY_BACKUP_REQUIRE_ENCRYPTION` y `MEMORY_BACKUP_KEEP`. Correcciones de la revisión (fix1), también solo para el operador: (5) `admin verify-backup --manifest <copia>.age.json` compara un volcado ya descifrado con `content_sha256` del manifiesto del cifrado (su salida gana la clave `verified`: `copy` o `content`) y `admin restore-check --from-manifest` acepta un valor opcional, ese mismo manifiesto explícito (sin valor, igual que antes); (6) con destinatarios el volcado en claro ya no toca el disco (`pg_dump` → proceso → `age`), un `SIGTERM` en cualquier punto limpia lo parcial, `backup` y `prune` barren los `.kairos-partial-*` huérfanos de más de una hora (campo `swept_partials` en su informe y aviso por stderr) y el servicio `memory-admin` pasa a `init: true`; (7) código nuevo `backup_config_invalid` (un `MEMORY_BACKUP_REQUIRE_ENCRYPTION` inválido deja de dar traza); (8) `backup --prune` verifica el sha256 solo de las N más recientes y borra las anteriores sin recalcularlo, y un borrado concurrente ya hecho no es un fallo; (9) el PostgreSQL efímero de `--verify-backup` pasa a llamarse `kairos-verify-<proyecto>-<marca>` (con la etiqueta `com.kairos.project`), con contraseña aleatoria por ejecución, sin capacidades y con `maintenance_work_mem=256MB`; las huellas por tabla se calculan en memoria acotada. Correcciones (fix2), también solo para el operador: (10) el manifiesto pasa a **formato 2**: las huellas por tabla son el número de filas y la suma módulo 2^256 de los sha256 por fila, calculadas en una sola pasada por tabla (los manifiestos de formato 1, que solo existen en esta rama, se rechazan con el código nuevo `backup_manifest_format_unsupported`; hay que hacer una copia nueva); (11) el barrido de `.kairos-partial-*` nunca borra el parcial de una copia en curso, aunque lleve horas sin escribir (cerrojo `flock` del proceso vivo); (12) si `age` falla, `backup` informa `backup_encryption_failed` aunque `pg_dump` también falle; un `--prune` que falla tras una copia válida imprime siempre el informe de la copia; (13) los nombres del PostgreSQL efímero de `--verify-backup` acortan el proyecto a 24 caracteres (con un hash corto) para no pasar de los 63 de un nombre de host; la etiqueta conserva el proyecto completo. Fase 7: (14) comando nuevo `admin backup-cycle [--output-dir] [--loop] [--prune-tables]` (copia cifrada, verificación, subida a `dir:<ruta>` o `rclone:<remoto>:<ruta>`, lectura de vuelta del sha256 en el destino y retención local y remota; el destino solo recibe copias cifradas, una copia en claro del directorio local se omite y se informa en `offsite.skipped_plain`, y el comando se niega a arrancar sin destinatarios aunque `MEMORY_BACKUP_REQUIRE_ENCRYPTION` valga 0; el destino es exclusivo de una instalación); variables nuevas `MEMORY_BACKUP_DESTINATION` (sin valor: se niega a ejecutarse), `MEMORY_BACKUP_INTERVAL` (24h) y `MEMORY_BACKUP_REMOTE_KEEP` (30), y de Compose `MEMORY_BACKUP_CONFIG_DIR` y `MEMORY_BACKUP_OFFSITE_DIR`; servicio nuevo opcional `memory-backup` (perfil `backup`, imagen `operator`, sin puertos, sin clave privada, redes `memory-data` y `egress`) que una instalación ya desplegada solo recoge en su próximo `up`; códigos nuevos `backup_destination_invalid` y `backup_offsite_failed` (`backup_config_invalid` es de la Fase 6; lo nuevo es su uso con `MEMORY_BACKUP_INTERVAL`; `backup_encryption_required` también existía y ahora lo devuelve `backup-cycle` sin destinatarios; más `backup_keep_invalid` para `MEMORY_BACKUP_REMOTE_KEEP`), eventos de log `backup_offsite_failed`, `backup_cycle_failed` (en `--loop`, solo `exc_type` y `code`) y `backup_offsite_plain_skipped`, y series `kairos_backup_offsite_success` y `kairos_backup_offsite_last_run_timestamp_seconds` en el fichero `kairos-offsite.prom` del volumen de copias; `rclone` 1.60.1 va fijado por versión en las imágenes `operator` y de pruebas; `backup --prune` ya no falla si otra poda borra una copia mientras la verifica. (15) comando nuevo `python scripts/rehearse-restore.py --project-name kairos-ops-<x> --embed-stub` (ensayo aislado del runbook de restauración de `docs/operations.md`: despliega el proyecto, hace un ciclo con el servicio `memory-backup`, descifra con una clave generada al vuelo y restaura en un PostgreSQL efímero nuevo hasta `restored_and_content_verified`; lo elimina todo, la clave incluida, también ante SIGTERM, al terminar y solo acepta nombres `kairos-ops-*`). Fase 8 (cierre del hito A; solo para el operador, sin cambio en la API, en los códigos de `error_code` ni en el contrato MCP): (16) una validación de arranque de `backup-cycle` que falla (sin destinatarios, fichero ilegible, destino o cualquier variable inválida, también `MEMORY_MAX_ATTEMPTS` y las ventanas `MEMORY_RETENTION_*` con `--prune-tables`) deja también `kairos_backup_offsite_success 0` en `kairos-offsite.prom` (crea el directorio de salida si falta); un fallo de la retención local tras una copia ya enviada registra además el evento `backup_cycle_failed` (`exc_type` y `code`) y deja la métrica en 0; la copia y su manifiesto se comprueban (cabecera `age`, sha256) y se suben desde el mismo descriptor abierto sin seguir enlaces, de modo que una copia cambiada después de verificarla sale en `offsite.skipped` con `backup_not_found`, `backup_manifest_invalid`, `backup_encryption_required` o `backup_checksum_mismatch` y nunca llega al destino; el destino `rclone:` recibe cada fichero con `rclone copyto` desde el descriptor ya comprobado (`/proc/self/fd/<n>`, con los reintentos de rclone) y una copia que no coincide en el destino se borra de él antes del error; comando nuevo `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-<x> --embed-stub --stage a` (ensayo aislado del cierre del hito A: restauración, medida de las huellas y parada y arranque de `memory-postgres` con trabajos en cola); (17) las conexiones directas de `admin` y las de `pg_dump`/`pg_restore` llevan `connect_timeout` (10 s), `keepalives` (30 s, 10 s, 3) y `tcp_user_timeout` (60 s), sin `statement_timeout`, para que `backup-cycle --loop` no se cuelgue con una conexión half-open; lo que el operador ponga en la DSN prevalece; (18) Compose (Fase 9, solo en el próximo `up` de la instalación desplegada): `mem_limit` y `cpus` en todos los servicios con las variables nuevas `MEMORY_<SERVICIO>_MEM_LIMIT`/`_CPUS` (`docs/configuration.md`; todos los `cpus` valen `0`, sin cuota, por defecto, y un `cpus` por encima de las CPU del equipo lo rechaza Docker; `memory-api` lleva `2g` por defecto), rotación `json-file` también en `ollama`, `memory-postgres` y `memory-files`, `extra_hosts: host.docker.internal:host-gateway` en `ollama`, healthchecks nuevos de `memory-web` (`/health/live`) y `memory-worker` (`/tmp/kairos-worker-heartbeat` guarda el plazo, en segundos de época, del siguiente latido y el healthcheck lo compara con el reloj; `unhealthy` en ≤ el plazo del último latido + `interval × retries` con el bucle parado o la base inalcanzable, con cualquier `MEMORY_LEASE_SECONDS`) y `memory-backup` solo en la red de la base: un destino `rclone:` necesita `-f docker-compose.yml -f docker-compose.backup-rclone.yml` (fichero nuevo). (19) Despliegue (Fase 10, solo para quien opera `scripts/deploy-memory.py` y el worker; sin cambio en la API, en los códigos de `error_code` de los trabajos ni en el contrato MCP): opciones nuevas `--break-lock` y `--rollback`; códigos nuevos `deployment_locked` (otro despliegue del mismo proyecto tiene el bloqueo `deployment.lock` del directorio privado, o el sistema operativo no deja tomarlo (un fichero de bloqueo escrito por otro equipo en un disco compartido se toma solo si el sistema lo deja, con o sin `--break-lock`, que ya no retira ni rompe nada: solo nombra la toma de un bloqueo libre de otro equipo); el bloqueo es del sistema operativo y se libera solo cuando muere el proceso: un dueño muerto de este equipo no necesita ninguna opción; código de salida 3, sin ejecutar ninguna fase) y `no_previous_images` (`--rollback` sin etiquetas anteriores registradas, o con una que ya no está en Docker; código de salida 4, sin tocar ningún servicio; también si las etiquetas registradas no son las que genera el script) y `already_at_previous` (los contenedores de los cuatro servicios Y el `:latest` de cada imagen, `operator` incluida, ya son las imágenes de destino; código de salida 5, sin tocar nada ni informar de un retroceso; si solo falta una de las dos cosas, `--rollback` la restaura: re-etiqueta `:latest` sin recrear los contenedores que ya están bien, o recrea solo los que difieren, y termina `rolled_back` con `rollback.retagged` y `rollback.recreated`); cada despliegue etiqueta antes de construir las imágenes del último despliegue que terminó bien (`images.good`, por id) como `kairos-<imagen>:<versión>-<marca>` (en un ensayo aislado, `rehearsal-<proyecto>-<imagen>:<versión>-<marca>`), conserva las dos últimas y la de destino del retroceso, y las registra en la clave nueva `images` de `deployment-status.json` (y, tras un retroceso, `rollback`; con `--break-lock`, `lock_broken`); `--rollback` vuelve a esas imágenes sin migrar ni tocar datos (imágenes, no datos; `status: rolled_back`); `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-<x> --embed-stub --stage rollback` ensaya el retroceso en un proyecto aislado (dos despliegues etiquetados, una versión defectuosa, `--rollback` sin migrar y con el mismo `content-manifest`, y `memory-worker` `unhealthy` con su bucle parado dentro de la cota de CA-21, comparada de forma estricta) y `--stage all` ahora lo incluye y termina en `rehearsal_ok`; el bloqueo no sigue enlaces simbólicos, no borra ni renombra ningún fichero (tampoco `--break-lock`) y avisa, por stderr y con `previous_run_interrupted`, si el fichero no estaba vacío al tomarlo; el registro de etiquetas es duradero (`status: in_progress` con `images.previous` y `images.good` antes de construir; `images.good` solo cambia al terminar `complete` o `rolled_back`; los ids leídos del informe solo valen como `sha256:` y 64 dígitos hexadecimales; la poda solo toca `<versión>-<marca>` exactas); Ctrl-C, SIGTERM y SIGHUP liberan el bloqueo, guardan `status: interrupted` y salen con 130 o 128 + señal (tras un `kill -9` queda el `in_progress`, que nunca se toma como bueno); una instalación sin `images.good` registra al empezar, tras la comprobación del motor y antes de la fase `configuration`, las imágenes que ejecutan sus contenedores como buenas (y sin registro ni estado fiable no inventa nada y `--rollback` dice por qué no puede volver); las órdenes de `compose run` llevan nombre propio y se paran al interrumpir (`unreaped_containers` si docker no contesta); una señal durante el manejo de un fallo no deja un traceback; nada del fichero de bloqueo llega crudo a la terminal y un fichero de bloqueo con más de un nombre o que no es normal es `deployment_locked`; en el worker, evento de log nuevo `job_cancelled` (`reason: lease_lost`): al perder la concesión de un trabajo en curso se cancela la llamada al proveedor (antes seguía hasta su plazo sin latir y el contenedor pasaba a `unhealthy`) y la fila del trabajo no se toca. (20) Sonda de ida y vuelta (Fase 11, solo para quien opera `memory-admin`; sin cambio en la API, en los códigos de error `error_code`, en las herramientas MCP ni en los contratos): subcomandos nuevos de `admin`, `probe-provision` (crea el proyecto `kairos-probe` y una clave `read`/`write` con alcance solo sobre él, idempotente; el token va a `MEMORY_PROBE_KEY_FILE`, nunca a la salida) y `probe` (escribe una nota sintética por `/v1`, espera su recibo `embed`, la busca con la capa semántica y la retira; sale con 0, o con 1 e `probe_failed` con `stage` y `code` cerrados, e intenta retirar lo escrito); variables nuevas `MEMORY_PROBE_TIMEOUT` (120 s), `MEMORY_PROBE_URL`, `MEMORY_PROBE_KEY_FILE` y `MEMORY_PROBE_METRICS_FILE` (`docs/configuration.md`); series nuevas `kairos_probe_success`, `kairos_probe_stage_seconds{stage}`, `kairos_probe_last_run_timestamp_seconds` y `kairos_probe_last_success_timestamp_seconds` (el nombre de la spec era `..._last_success_timestamp`: enmienda con `_seconds`, la convención del resto; una ejecución fallida conserva el valor del fichero anterior) en un fichero de texto (no en `/metrics`); campo de log nuevo `stage` y eventos `probe_failed`, `probe_retire_failed`, `probe_sweep_failed`, `probe_purge_failed`, `probe_metrics_failed` y `probe_aborted`. Una escritura de la clave de la sonda en otro proyecto da 404, no 403 (el servidor no revela proyectos fuera del alcance de una clave: nota de enmienda de T-68). Corrección de la revisión de la fase 11 (fix1; sin cambio de contrato HTTP ni MCP, no se añade ningún campo a la API): (a) la sonda da por bueno `search` solo si la nota **de esa ejecución** vuelve por la vía semántica (consulta sin palabras de la nota, `item_id` propio y una búsqueda de control con la capa semántica apagada que no la devuelva), barre al empezar las notas activas que dejó una ejecución anterior y toma un bloqueo de fichero (`<MEMORY_PROBE_KEY_FILE>.lock`) para no cruzarse con otra; (b) `probe-provision` crea una cuenta de servicio `kairos-probe` (sin contraseña utilizable, sin `is_admin`, con `read`, `write` y `admin` solo sobre `kairos-probe`, el mínimo para crear y revocar su clave) que es la dueña de la clave, de modo que la auditoría de la sonda no se atribuye a una persona; `--as <usuario>` nombra al administrador que crea el proyecto (única escritura que exige uno); comprueba la clave por el mismo camino que la API (`Auth`), rechaza con error explícito un proyecto o un usuario `kairos-probe` ajenos (`project_foreign`, `actor_foreign`, `actor_disabled`, `operator_unknown`) y se serializa con un bloqueo asesor; (c) `admin probe` borra las FILAS de las notas retiradas de `kairos-probe` (la de la ejecución y las de más de 10 minutos; nota, versiones, eventos, trabajos, recibos, vectores y fragmentos) con la base de `memory-admin`: sin migración, sin tocar tablas, columnas ni volúmenes, solo ese proyecto; (d) Ctrl-C, SIGTERM y cualquier excepción terminan con la retirada y `kairos_probe_success 0` (códigos nuevos `interrupted`, `internal_error` y `busy`), la retirada tiene 20 s propios (una ejecución dura como mucho `MEMORY_PROBE_TIMEOUT` + 20 s, y con la purga y la conexión que la siguen, como mucho 25 s más) y un fichero de métricas que no se puede escribir se registra y hace salir con 1 (`probe_metrics_failed`). Corrección de la revisión de la fase 11 (fix2; sin cambio de contrato HTTP ni MCP): la purga solo borra si `kairos-probe` es el proyecto de la sonda (la misma comprobación que el aprovisionamiento, `project_foreign`), no tras una clave rechazada ni tras una señal, y con un presupuesto total de 15 s (`purge_timeout`; cota total de una ejecución: `MEMORY_PROBE_TIMEOUT` + 20 s + 25 s de purga y conexión); la rotación revoca solo las claves de la cuenta de servicio y la del fichero; el alta de la cuenta, sus concesiones y la clave emitida se auditan a nombre del administrador (`user.created`, `grant.created`, `probe.key_issued`) y `--as` se valida siempre; tras Ctrl-C o SIGTERM, también con la escritura en vuelo, la retirada (8 s, caben en el `stop_grace_period: 15s` del contenedor) busca la nota por su `item_id` y por la marca única y una segunda señal no pierde el informe; el último éxito se lee y el fichero de métricas se escribe dentro del bloqueo de ejecución; el bloqueo pasa junto al fichero de métricas si la clave está en un montaje de solo lectura, o se omite con el aviso `probe_lock_unavailable`. (21) Cola atascada, servicio de sonda y `kairos doctor` (Fase 12; todo aditivo, sin cambio en la API, en los códigos de error, en las herramientas MCP ni en los contratos): `/metrics` publica la serie nueva `kairos_jobs_oldest_pending_seconds` (segundos que espera el trabajo más antiguo de `memory.jobs` ya vencido: pending o unknown desde `available_at`, running con la concesión caducada; 0 con la cola vacía); `admin probe` avisa con el evento de log `queue_stuck`, la clave `queue` del informe y salida distinta de 0 (`queue_stuck: oldest_pending_seconds=… threshold_seconds=…`) cuando esa antigüedad supera `MEMORY_QUEUE_STUCK_SECONDS` (900 s; un valor que no es un número positivo se ignora con `probe_setting_ignored`), y `admin probe --loop` repite la sonda con `MEMORY_PROBE_INTERVAL` (300 s, enteros de 10 a 86400) de espera tras cada ejecución, de modo que el periodo real es la duración de la ejecución más el intervalo; servicio Compose opcional `memory-probe` (perfil `probe`, sin puertos, `stop_grace_period: 15s`, variables `MEMORY_PROBE_MEM_LIMIT` y `MEMORY_PROBE_CPUS`) que la instalación desplegada recoge solo en su próximo `up`, y reglas Prometheus de ejemplo en `docs/examples/prometheus-rules.yml`; en el cliente, `kairos doctor` añade `capture_queue` (`pending`, `oldest_pending_seconds`, `threshold_seconds`, `stale`) cuando hay capturas pendientes en la cola en disco, y por encima del umbral (900 s o `KAIROS_QUEUE_STALE_SECONDS`) `warnings: ["capture_queue_stale"]` y estado `degraded` (salida 1); sin capturas pendientes la salida no cambia, no toma el bloqueo de la cola ni envía nada al servidor. Corrección de cierre (fix1): `kairos doctor` lee `queue.json` y `queue.jsonl` de un mismo momento (repite la lectura hasta 8 veces si un checkpoint del dispatcher las separa; una cola que cambia en todos los intentos se muestra como `unreadable`); `memory-probe` monta solo el subdirectorio `probe` del volumen `memory-backups` (`volume.subpath`, Engine 26 y Compose 2.26 o posteriores), así que la clave, el `.prom` y el latido del bucle pasan de `/backups/kairos-probe.*` a `/backups/probe/kairos-probe.*` (migración: `probe-provision` una vez más y, si un colector de ficheros de texto leía el volumen, apuntarlo también a `probe/`); su healthcheck lee ese latido, que solo escribe el bucle, con un margen que incluye `MEMORY_PROBE_TIMEOUT`; una parada (SIGTERM) termina siempre con `probe_interrupted` y, tras un recorrido correcto, conserva el resultado ya escrito; y `scripts/deploy-memory.py` recrea `memory-probe` tras un despliegue si estaba en marcha. (22) Abstención opcional en la búsqueda (Fase 13; solo aditivo, sin cambio en el comportamiento por defecto): `POST /v1/search` y la herramienta MCP `search` aceptan `abstain` (booleano, opcional) y la respuesta gana, solo con la abstención activa, `abstained` (true/false) y, si el modelo de embeddings no tiene umbral, `abstention: "uncalibrated"`; con `abstain` activo, la mejor similitud coseno de la capa semántica por debajo del umbral del modelo (`MEMORY_ABSTAIN_THRESHOLDS`, `modelo=umbral,...`, vacío por defecto) y ninguna capa léxica con resultados, estando todas las capas léxicas pedidas completas, dan `items: []` y `abstained: true`; una capa semántica `degraded`, `partial` o apagada, o una capa léxica `unavailable`, `partial` o con el plazo de trigramas vencido (`fuzzy_timeout`), nunca abstiene (fix1 de la revisión: `abstained: false`). `abstention: "uncalibrated"` sale siempre que la abstención está activa, la capa semántica terminó `ok` (también sin aciertos) y el modelo no tiene umbral; el modelo se compara sin `:latest` en los dos lados y un nombre con `=`, `;` o espacios en `MEMORY_ABSTAIN_THRESHOLDS` impide arrancar. Las dos variables ya pasan por `docker-compose.yml` (`x-memory-environment`) y están en `docs/configuration.md`. `MEMORY_ABSTAIN_DEFAULT` (`on` u `off`, `off` por defecto) decide qué hace una petición sin `abstain`; `context` solo sigue ese valor. Sin `abstain` y con `off` la respuesta es idéntica a la anterior. `memory-platform.openapi.json`, `kairos-mcp.json` (incluido `result_schemas.search`, con `additionalProperties: false`) y `mcp/contract/` ganan los campos opcionales; ambos CHANGELOG llevan la nota para la Iniciativa 7 (un cliente estricto con el esquema anterior rechazaría `abstained`, de ahí que siga apagada por defecto, P-04). El diseño de la señal está en `docs/architecture.md` y el umbral real se calibra en la Fase 14. (23) Calibración de la abstención (Fase 14; sin cambio de contrato ni de comportamiento por defecto): medido con `nomic-embed-text` en un Ollama efímero y aislado, ningún umbral cumple a la vez ≥ 70 % de abstención correcta y ≤ 5 % de falsa (0,60 da 50,0 % y 2,8 %), así que sigue `uncalibrated`: no se entrega ningún umbral por defecto (`MEMORY_ABSTAIN_THRESHOLDS` vacío, `MEMORY_ABSTAIN_DEFAULT=off`) y una petición con `abstain` sigue respondiendo `abstention: "uncalibrated"`; la puerta `retrieval-eval` mide ahora la abstención con metas propias del proveedor simulado (≥ 50 % y ≤ 5 %, R-07). Ambos CHANGELOG ampliaron la nota para la Iniciativa 7: activar la abstención cambia lo que ve `custom-agents` (una búsqueda puede devolver `items: []`) y debe decidirse junto con ese cliente. (24) Nombres que añadió el hito B y el cierre de su revisión, sin cambio de contrato: los eventos de log `probe_heartbeat_failed`, `probe_queue_failed`, `queue_age_unavailable` y `heartbeat_file_failed` (documentados en `docs/operations.md`), la variable `MEMORY_PROBE_HEARTBEAT_FILE` (solo `probe --loop`), las claves `probe_recreated` y `backup_recreated` del informe de `deploy-memory.py` (que con `apply` y con `--rollback` recrea ahora `memory-probe` y `memory-backup` si estaban en marcha), las claves `probe_recreate_skipped` y `backup_recreate_skipped` (el contenedor se creó con ficheros de Compose que no son `docker-compose.yml` ni `docker-compose.backup-rclone.yml`, o su etiqueta no se puede leer: no se recrea, el despliegue no falla y la salida de error trae la orden manual) y que la sonda envía `abstain: false` en todas sus búsquedas para que `MEMORY_ABSTAIN_DEFAULT=on` no la haga fallar.

---

## Criterios de aceptación (global)

- [ ] Restauración desde la copia externa ensayada y verificada (`restored_and_content_verified`) con el runbook de `docs/operations.md` (CA-01 a CA-08, criterio de cierre 1)
- [ ] El worker sobrevive a parar y arrancar `memory-postgres` con trabajos en cola, sin reinicios propios ni trabajos `failed` por la caída (CA-09 a CA-14, CA-37, criterio de cierre 2)
- [ ] Pool, plazos y permisos por transacción comprobados con el arnés de fallos y por medición (CA-15 a CA-19, CA-34 a CA-36)
- [ ] Despliegue con límites, healthchecks, rotación, `extra_hosts`, bloqueo y `--rollback` ensayado (CA-20 a CA-25)
- [ ] Abstención opcional con contrato solo aditivo y puerta `retrieval-eval` con las métricas de abstención y la prueba de rojo (CA-26 a CA-29)
- [ ] La sonda detecta `memory-worker` parado con `stage=index` y código ≠ 0 (CA-30 a CA-33, criterio de cierre 3)
- [ ] Migraciones solo aditivas, contratos aditivos frente a `contracts_base`, nada `knowledge-graphs-*` ni puerto 11434, suite con 0 fallos y 0 omitidos y `retrieval-eval` en verde (CA-38)

### Mapa criterio → tareas

| CA | Tareas |
|----|--------|
| CA-01 | T-35, T-41 |
| CA-02 | T-36, T-41 |
| CA-03 | T-37, T-41 |
| CA-04 | T-38, T-41 |
| CA-05 | T-39, T-40, T-41 |
| CA-06 | T-44, T-45, T-46 |
| CA-07 | T-47, T-50, T-96 |
| CA-08 | T-36, T-46 |
| CA-09 | T-09 |
| CA-10 | T-07, T-08, T-11 |
| CA-11 | T-07, T-09 |
| CA-12 | T-10, T-11 |
| CA-13 | T-14, T-15 |
| CA-14 | T-16, T-17, T-18 |
| CA-15 | T-21, T-22, T-26, T-27 |
| CA-16 | T-23, T-24, T-25, T-27 |
| CA-17 | T-23, T-25, T-27 |
| CA-18 | T-21, T-27, T-30, T-31, T-32 |
| CA-19 | T-24, T-25, T-27 |
| CA-20 | T-54, T-58 |
| CA-21 | T-56, T-57, T-58, T-64 |
| CA-22 | T-55, T-58 |
| CA-23 | T-61, T-65 |
| CA-24 | T-62, T-63, T-64, T-65 |
| CA-25 | T-55, T-58 |
| CA-26 | T-87 |
| CA-27 | T-81, T-82, T-84, T-88, T-89 |
| CA-28 | T-88, T-90 |
| CA-29 | T-81, T-82, T-83, T-84, T-91 |
| CA-30 | T-69, T-70, T-71, T-75 |
| CA-31 | T-69, T-70, T-71, T-77, T-96 |
| CA-32 | T-74, T-76, T-78 |
| CA-33 | T-68, T-70 |
| CA-34 | T-01, T-04, T-25 |
| CA-35 | T-02 |
| CA-36 | T-03 |
| CA-37 | T-50, T-96 |
| CA-38 | T-05, T-12, T-19, T-28, T-33, T-42, T-48, T-51, T-52, T-59, T-66, T-72, T-79, T-85, T-92, T-94, T-97, T-98 |

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| R-01 Esperas que esconden una caída (worker «sano» sin base) | Media | Alto | `last_store_ok` y latido que no avanza con la caída larga (T-08, T-56); la sonda lo detecta de extremo a extremo |
| R-02 `statement_timeout` corta trabajo legítimo (migraciones, relleno, copias, `graph_data`) | Media | Alto | Plazo solo en conexiones de servicio; `admin` sin límite; pruebas con el plazo activo en la API (T-23) |
| R-03 Clave privada perdida o expuesta | Baja | Alto | Cifrado de clave pública; runbook con custodia fuera del VPS; CA-08 comprueba que no se monta (T-36, T-46) |
| R-04 Retención que cambia lo que ven los clientes (`events`) | Media | Medio | `events` sin retención por defecto; `--dry-run`; nunca en migraciones; invariantes probadas (T-17) |
| R-05 Caché de permisos que relaja la revocación | Baja | Alto | Caché limitada a la transacción; pruebas de revocación con mutante; revisión a 1,0 × (T-30, T-31) |
| R-06 Límites de recursos que matan servicios en el relleno o la verificación | Media | Medio | Valores medidos en el ensayo aislado; variables por servicio; documentados (T-54) |
| R-07 Umbral de abstención no transferible (embeddings simulados) | Alta | Medio | Umbral por modelo; sin umbral, `uncalibrated`; medición real con Ollama efímero (T-89). **Enmienda 2026-11-18 (decisión del usuario del 2026-11-18, literal «12 de 24 en la CI»: metas de abstención **por proveedor**; con el proveedor simulado de la CI, ≥ 0,50 de abstención correcta (12 de las 24 negativas) y ≤ 0,05 de falsa, como guarda de regresión (sus embeddings no reflejan la calidad real, R-07; con ellos el 70 % exige un 6,9 % de falsa, medido); con modelos reales siguen ≥ 0,70 y ≤ 0,05; la medición real de T-89 dejó a `nomic-embed-text` sin calibrar)** |
| R-08 Ficheros del árbol que monta la instalación desplegada (`ollama-proxy/default.conf.template`, `docker-compose.yml`) | Media | Alto | No tocar la plantilla; los cambios de Compose se recogen en el próximo `up` (Iniciativa 5); ensayos con `--project-name`; CA-38 comprueba que nada apunta a `knowledge-graphs-*` |
| R-09 Cliente estricto frente a `abstained` (`additionalProperties: false`) | Media | Medio | Campo solo si se pide o el operador lo activa; CHANGELOG y nota a la Iniciativa 7 (T-83) |
| R-10 Bucles de revisión y ensayos lentos | Alta | Medio | Revisión como partida propia por fase; corregir la clase entera; ensayos agrupados; `usage-meter` por tarea e intento |
| R-11 Tests con tiempos (backoff, plazos, latido, sonda) | Alta | Medio | Relojes inyectados y `threading.Event`; sin `sleep` para esperar un estado |
| N-01 Fases F4, F5 y F13/F14 revisadas a 1,0 × pueden aún necesitar más intentos que los presupuestados | Media | Medio | Supervisión por encima del 25 % reservada; mediciones por intento para calibrar |
| N-02 Disponibilidad de `age`/`rclone` en bookworm | Media | Medio | Binario oficial con sha256 verificado como alternativa, anotado en T-36 |

---

## Métricas de éxito

- Cada una de las 98 tareas cerrada con su `Verificación` ejecutada y su medición de `usage-meter` (también cada intento de revisión).
- Revisiones adversariales por fase con 0 hallazgos Critical/Important abiertos al cierre.
- Suite backend: `tests` ≥ 764 y creciente, 0 fallos, 0 errores, 0 omitidos; `KAIROS_MIN_TESTS` = recuento final.
- Tres criterios de cierre del plan director demostrados en el ensayo aislado (restauración, supervivencia del worker, detección por la sonda).
- Horas IA reales frente a las 55,0 h estimadas, para calibrar `CALIBRATION.md` (tercera fila).

---

## Changelog del plan

| Fecha | Cambio | Autor |
|-------|--------|-------|
| 2026-11-15 | Creación del plan a partir de `spec.md` (aprobada) y `evaluation.md` (go): 98 tareas en 16 fases, dos hitos; hereda las cifras de la evaluación sin diferencias | planner |

---

## Siguiente paso

Con el **OK del plan** del usuario (puerta de control), el agente **`implementer`** lo ejecuta fase a fase sobre `feat/reliable-operations`, marcando `tasks.md` como **ledger canónico** (checkbox + estado por tarea). Al terminar, handoff a `qa` y cierre con `documenter`; con `test-plan: n/a (sin UI)` en el frontmatter, `qa` corre sus puertas deterministas y sale limpio sin pedir test-plan (ADR-017).
