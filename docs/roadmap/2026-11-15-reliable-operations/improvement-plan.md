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
- **Coordinación:** los cambios visibles para clientes (`abstain`/`abstained`, retención) se declaran a la Iniciativa 7 en los CHANGELOG. También los códigos nuevos de `error_code` que ya ve un cliente en `GET /v1/jobs/{id}`, en la métrica `kairos_jobs_failed{code}` y en `POST /v1/jobs/{id}/retry`: `attempts_exhausted` (T-10; un trabajo que agota `MEMORY_MAX_ATTEMPTS` por concesiones perdidas deja de reclamarse y pasa a `failed`) y `store_error` (T-09; un error de la base que no es una caída, p. ej. consulta cancelada o `lock_timeout`, distinguible de `provider_error`; los transitorios `40001`, `40P01`, `57014`, `55P03` y clase `53` se repiten antes dentro del presupuesto de escritura y, agotado, el trabajo se reprograma con `store_error`). También declarar a la Iniciativa 7: el evento de log `job_write_abandoned` (T-09; `reason` = `<acceso>:<motivo>`, con `retry_budget` cuando se agota el presupuesto de reintento), el evento `store_retry`, el evento `job_outcome_unread` (T-09; no se pudo leer el estado del trabajo tras un fallo ambiguo y se da por perdido), la variable nueva `MEMORY_WORKER_WRITE_RETRY_SECONDS` (T-09, por defecto igual a `MEMORY_LEASE_SECONDS`) y que un `MEMORY_MAX_ATTEMPTS` inválido (≤ 0 o no entero), que antes se aceptaba, ahora impide arrancar API, worker y admin (T-10).

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
| R-07 Umbral de abstención no transferible (embeddings simulados) | Alta | Medio | Umbral por modelo; sin umbral, `uncalibrated`; medición real con Ollama efímero (T-89) |
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
