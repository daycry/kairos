---
generacion:
  inicio: 2026-11-09T11:52:27Z
  fin: 2026-11-09T11:57:52Z
  fuente: medido          # medido | estimado
  tokens_reales: { entrada: 12, salida: 46710, cache_creacion: 55206, cache_lectura: 493194, respuestas: 6 }
  eur: null              # precioTokens no fiable; ejecuta la skill rates-verify
  horas_ia: 0.34
  duracion: 20m            # reloj: 5m
  ratio_usado: 300000      # default no calibrado
  # ventana compartida con improvement-plan.md
verificacion: obligatoria   # cada T-XX lleva `- **Verificación**:`; lo exige ledger-lint (exit 1 si falta)
---

# Checklist de Tareas — Calidad de recuperación de Kairos (iniciativa 1 de 3)

| | |
|---|---|
| **Estado** | en-progreso |
| **Fecha** | 2026-11-09 |
| **Plan** | [`improvement-plan.md`](./improvement-plan.md) |
| **Diseño** | n/a |

> **⚠️ Ledger canónico de progreso.** Este fichero es la **fuente única de verdad** del avance del plan. **Cualquier** implementador —el agente `implementer`, el chat principal, o un orquestador SDD externo— **debe** marcar aquí cada tarea (checkbox + estado) al completarla y actualizar el resumen. Los ledgers propios de otras herramientas son **espejo**, no fuente.

---

## Resumen de progreso

| Fase | Completadas | Total | Progreso | H. humanas (real/est) | H. IA ejec. (real/est) | Supervisión (real/est) | Tokens (real/est) |
|------|------------|-------|----------|-----------------------|------------------------|------------------------|-------------------|
| Fase 1 — Medida (C-01 · P13) | 3 | 3 | 100% | 0 / 16h | 0,62 / 2,21h | 0 / 0,56h | 0 / 660k |
| Fase 2 — Refactor de `store.py` (C-02 · P11) | 3 | 3 | 100% | 0 / 14h | 0,20 / 3,41h | 0 / 0,85h | 0 / 1020k |
| Fase 3 — pgvector + HNSW (C-03 · P1) | 6 | 6 | 100% | 0 / 32h | 2,21 / 4,29h | 0 / 1,08h | 0 / 1290k |
| Fase 4 — FTS por idioma + trigram (C-05 · P4) | 6 | 6 | 100% | 0 / 27h | 2,18 / 3,61h | 0 / 0,91h | 0 / 1090k |
| Fase 5 — Troceado para embeddings (C-06 · P2) | 7 | 7 | 100.0% | 0 / 28h | 1,43 / 4h | 0 / 1h | 0 / 1200k |
| Fase 6 — Híbrida con degradación y CLI (C-04 · P3) | 4 | 4 | 100.0% | 0 / 12h | 0 / 1,6h | 0 / 0,4h | 0 / 470k |
| Fase 7 — Observabilidad (C-07 · P12) — en paralelo desde T-06 | 4 | 4 | 100.0% | 0 / 18h | 0,49 / 2,6h | 0 / 0,64h | 0 / 770k |
| Fase 8 — Integración, revisión y activación | 0 | 5 | 0% | 0 / 26h | 0 / 4,31h | 0 / 1,06h | 0 / 1280k |
| **TOTAL** | **33** | **38** | **86.8%** | **0 / 173h** | **7,13 / 26,03h** | **0 / 6,5h** | **0 / 7780k** |

> Las horas de este ledger son **base** (sin el margen del 20 %); con margen: humanas 207,6 h, IA 31,2 h. Las horas IA y los tokens son estimaciones (ratio 300.000 tok/h no calibrado).

> **Horas → Jira.** El worklog que imputa `jira-sync` al completar cada tarea es **Tiempo IA (ejec.) + Supervisión** (real; o estimación si no hay real), topado a la jornada configurada. Ver `skills/jira-sync/SKILL.md`.

---

## Fase 1 — Medida (C-01 · P13)

**Estado**: completado · **Estimado**: 16h base (19.2h con margen) · **Real**: — · **Coste est.**: 960 € · **Tokens est.**: 600k in / 60k out

### T-01 — Dataset sintético `dataset-v1` y umbrales

- **Descripción**: Crear `memory_platform/tests/retrieval_eval/dataset-v1.jsonl` con ≥ 60 preguntas sintéticas (≥ 20 es, ≥ 20 en, ≥ 10 con errores tipográficos o identificadores, ≥ 10 con la respuesta más allá del carácter 8.000 de un documento largo) y sus referencias esperadas, más `thresholds.json` con los umbrales acordados. Resultado: un dataset determinista, sin datos reales, listo para congelar.
- **Changelog**: Se añade un conjunto de evaluación sintético (72 preguntas en español, inglés, errores tipográficos y documentos largos) con umbrales de calidad para medir la recuperación.
- **Cerrada**: 2026-11-09
- **Estado**: completado
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0,83h · real 0,20 (medido)
- **Supervisión**: est. 0,21h (≈25 % IA) · real —
- **Previsión IA**: 225k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `memory_platform/tests/retrieval_eval/dataset-v1.jsonl`, `memory_platform/tests/retrieval_eval/thresholds.json`, `memory_platform/tests/retrieval_eval/README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m memory_platform.tests.retrieval_eval.check_dataset memory_platform/tests/retrieval_eval/dataset-v1.jsonl` → `OK` con recuento por subconjunto (es ≥ 20, en ≥ 20, typo/id ≥ 10, largo ≥ 10, total ≥ 60) y SHA-256 impreso
  - `python -c "import json;t=json.load(open('memory_platform/tests/retrieval_eval/thresholds.json'));print(t)"` → incluye `fused_recall_at_5: 0.80`, `fused_mrr: 0.60`, `subset_gain_points: 15`

**Criterios de aceptación**
- [x] CA-01: el dataset cumple los recuentos mínimos por subconjunto y cada pregunta tiene al menos una referencia esperada válida
- [x] Todos los datos son sintéticos; ningún texto procede de la base desplegada
- [x] `thresholds.json` recoge exactamente los umbrales de la decisión P-06 (recall@5 fused ≥ 0,80; MRR ≥ 0,60; +15 pts en idioma/errores/documento largo)

**Subtareas**
- [x] Redactar memorias y documentos sintéticos es/en (incluidos documentos > 8.000 caracteres con el dato tras el carácter 8.000)
- [x] Redactar preguntas con referencias esperadas y etiquetas de subconjunto
- [x] Escribir `check_dataset.py` (validación de recuentos y esquema, calcula SHA-256)

**Notas**: Procedencia: spec CA-01, decisión P-06. Clase de cambio: capacidad nueva (test nuevo en rojo, en la puerta `retrieval-eval`). Patrones: ningún equivalente de dataset en el repo (`grep` de `retrieval` en `memory_platform/tests` solo halla `test_retrieval.py`, que prueba mecánica, no calidad); estructura de módulo de test según `memory_platform/tests/test_embeddings.py`. Riesgo R-07: el dataset lo escribe quien implementa; se congela en T-03.

**Evidencia de verificación (2026-11-09)**
- `python -m memory_platform.tests.retrieval_eval.check_dataset memory_platform/tests/retrieval_eval/dataset-v1.jsonl` → `OK es=24 en=24 typo_id=12 long=12 total=72` · `sha256 1bba8d997c6dcc8e11f2ddceba2a78e8c38c0bd7cafd4aa458dd1547ad4be6f6`
- `thresholds.json` → `{'dataset': 'dataset-v1', 'fused_recall_at_5': 0.8, 'fused_mrr': 0.6, 'subset_gain_points': 15, 'gain_subsets': ['es', 'typo_id', 'long']}`
- Nota: 144 registros sintéticos; las preguntas es/typo_id no comparten ninguna palabra exacta con su objetivo (comprobado por script al generarlo) y las long llevan una palabra ausente del documento. Dataset ya congelado (hash en T-03).

### T-02 — Proveedor de embeddings simulado, cargador y métricas

- **Descripción**: Crear `fake_embeddings.py` (proveedor determinista sin red, misma interfaz que `Embeddings` de `providers.py`) y `run.py`: carga el dataset en PostgreSQL aislado, ejecuta `Retrieval.search` por capa (`episodic`, `documental`, `semantic`, `fused`) y calcula recall@1/5/10 y MRR por capa y subconjunto. Escribe un JSON con SHA-256 del dataset, la observación local de interfaces de red (`network_interfaces`) y `product_database_accessed: false`.
- **Changelog**: Nuevo arnés de evaluación de recuperación que mide recall y MRR por capa y subconjunto con embeddings simulados, sin red ni base de datos real.
- **Cerrada**: 2026-11-09
- **Estado**: completado
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0,83h · real 0,42 (medido: 0,16 + 0,17 + 0,09 de la correccion del intento 2)
- **Supervisión**: est. 0,21h (≈25 % IA) · real —
- **Previsión IA**: 225k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: test
- **Archivos**: `memory_platform/tests/retrieval_eval/fake_embeddings.py`, `memory_platform/tests/retrieval_eval/run.py`, `memory_platform/tests/retrieval_eval/test_metrics.py`, `memory_platform/tests/retrieval_eval/__init__.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → pasa con `test_metrics` incluido (recall@k/MRR sobre casos calculados a mano: valores exactos) y `failures: 0`
  - `python -m memory_platform.tests.retrieval_eval.run --report out.json` dos veces en el harness aislado → los dos JSON difieren solo en la marca de tiempo (CA-03)

**Criterios de aceptación**
- [x] CA-01: el informe contiene recall@1/5/10 y MRR para las cuatro capas y cada subconjunto, más el SHA-256 del dataset
- [x] CA-03: dos ejecuciones con el proveedor simulado producen informes idénticos salvo la marca de tiempo; el recibo registra la observación local de interfaces de red (no afirma «sin red») y `product_database_accessed: false` *(CA-03 enmendado por el usuario el 2026-11-09; original: «el recibo registra `network: none`»)*
- [x] El cargador solo se conecta al DSN del harness aislado y se niega a ejecutarse si `MEMORY_DSN` no apunta a una base temporal

**Subtareas**
- [x] Implementar el proveedor simulado (vector estable por hash de n-gramas, 2 y 768 dims según el modelo) — implementado con hash SHA-256 de palabras más trigramas de caracteres
- [x] Implementar cargador y ejecución por capa sobre `Retrieval`
- [x] Implementar métricas e informe JSON; test con casos calculados a mano
- [x] Salvaguarda de DSN: abortar si el host no es local/temporal

**Notas**: Procedencia: spec CA-01, CA-03, decisión «Embeddings en CI». Clase: capacidad nueva (test nuevo en rojo). Patrones: arranque de PostgreSQL aislado en `memory_platform/tests/run_postgres.py:15-40`; capas y fusión en `memory_platform/retrieval.py:97-146`; interfaz de proveedor en `memory_platform/providers.py` (`Embeddings.embed`).

**Evidencia de verificación (2026-11-09)**
- `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → exit 0; `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 186}` (177 previos + 9 de `test_metrics`; antes de la revision eran 183 = 177 + 6).
- CA-03: la puerta ejecuta la evaluación dos veces en el mismo harness (`deterministic: true`) (ver la comparación de hashes entre dos ejecuciones independientes en la corrección del intento 2); recibo: `network_interfaces`, `product_database_accessed: false`.
- Salvaguarda de DSN: `check_dsn` aborta salvo `MEMORY_DSN == MEMORY_TEST_DSN` en host local y base `memory_test` (probado en `test_metrics`).
- Nota de alcance: la verificación pedía `run --report out.json` dos veces; se cubre con el modo de la puerta (que ya lo hace dos veces y compara) más dos builds. El proveedor simulado es un bag-of-words hasheado: mide la tubería, no la calidad de un modelo real (T-36 lo hará contra Ollama).

**Correccion tras la revision (intento 1, 2026-11-09)**
- Guarda de DSN (gap 1): `check_dsn` resuelve el DSN con `psycopg.conninfo.conninfo_to_dict` y exige `host` loopback, `hostaddr` loopback si existe, puerto 55432, `dbname=memory_test`, solo claves host/hostaddr/port/dbname/user (rechaza `service`, `passfile`, `options`...). Test con `?host=`, `?hostaddr=`, `?dbname=`, `?service=`, `?port=`, `?passfile=`, host multiple y puerto distinto.
- Backends (gap 2): el informe lleva `query_backends` (estado y `partial` por consulta y capa, tambien clave estructural del determinismo); `_measure` convierte una excepcion de la capa semantica en `unavailable`; `evaluate_gate` falla con `backend_unavailable:<capa>`. Test `test_measure_records_a_layer_that_raises...`.
- N-gramas (gap 3): `fake_embeddings.py` hashea palabras mas trigramas de caracteres con SHA-256 (sin PYTHONHASHSEED). Linea base regenerada (dataset intacto, `sha256sum -c` OK): fused recall@5 0,50, MRR 0,340; subconjuntos fused recall@5 es 0,333, typo_id 0,583, long 0,50, en 0,625; capas recall@5 episodic 0,385, documental 0,20, semantic 0,903. Dos copias de `baseline.json` identicas (`cmp`).
- Minor 5/9: `load_dataset` reutiliza `check_dataset.validate`; test de `deterministic`/`STRUCTURAL_KEYS` (dos informes que difieren en una clave estructural -> `deterministic: false` y fallo `determinism`).
- Minor 7: el recibo ya no afirma `network: none` (en el intento 2 la sonda TCP se sustituyo por una observacion local de interfaces). `docker build --network=none` no es viable (falla en `apt-get` de capas previas), asi que se ejecuto la imagen `kairos-test:rq` con `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 ... python -m memory_platform.tests.run_postgres` -> `network: unreachable`. Documentado en `testing/README.md` y en el Dockerfile.
- Verificacion: `docker build --target test` (con `--no-cache-filter test`) -> exit 0, `"tests": 186, "failures": 0, "errors": 0, "skipped": 0, "passed": true`. Puerta con red desactivada -> exit 1; `deterministic: true`, sin `backend_unavailable`.
- Horas IA medidas del fix: 0,17 h (ventana compartida con T-03-fix1; se imputan a T-02).

**Correccion tras la revision (intento 2, 2026-11-09)**
- Gap 1: `check_dsn` rechaza la ejecucion si hay en el entorno `PGHOSTADDR`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGSERVICE`, `PGSERVICEFILE` o `PGSYSCONFDIR`; ya no supone `hostaddr`; `connect_dsn` fija `hostaddr=127.0.0.1` en el DSN con el que se conecta (`build_report`). Docstring con lo que garantiza y lo que no (no inspecciona `PGOPTIONS`/`PGPASSFILE`, que no eligen destino). Tests con cada variable (incluidas `PGHOSTADDR` y `PGSERVICE`) y con `os.environ` real parcheado.
- Gap 2: eliminada la segunda `load_dataset`; la que queda valida con `check_dataset.validate`. Test: `expected: []` e id inexistente -> `SystemExit` con "expected".
- Gap 3: `network_state()` (TCP a 1.1.1.1) sustituida por `network_observation()`: lista `/sys/class/net`, una sola vez en `run()`, fuera de `STRUCTURAL_KEYS`; el informe trae `network_interfaces` y `network_observation` (describe solo lo observado). Test con tres casos.
- Gap 6: test que exige que una errata (`authentiction`) quede mas cerca de `authentication` (coseno > 0,5) que una palabra distinta (`authorization`).
- Gap 7: textos de `network: none` actualizados arriba. Comparacion de dos ejecuciones independientes (build `retrieval-eval` y `docker run --network=none`), informe sin `generated_at` ni campos de red: sha256 `4cb8fbfd...f053b3e` en ambas (identicas).
- Verificacion: `docker build --target test` (con `--no-cache-filter test`) -> exit 0, `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 191}` (177 + 14 de `test_metrics`). Puerta con `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq ...` -> exit 1 solo por `fused_recall_at_5`, `fused_mrr`, `subset:es|typo_id|long`; `deterministic: true`, sin `backend_unavailable`, `network_interfaces: ["lo"]` (only the loopback interface exists). `sha256sum -c dataset-v1.sha256` -> OK; `cmp` de las dos `baseline.json` -> identicas (cifras sin cambio).
- Horas IA medidas del fix: 0,09 h (`T-02-fix2`).

---

### T-03 — Puerta `retrieval-eval`, línea base en rojo y congelación del dataset

- **Descripción**: Añadir el modo `MEMORY_RETRIEVAL_EVAL=1` a `run_postgres.py`, el target `retrieval-eval` al Dockerfile y el contrato de la puerta (compara con `thresholds.json`, sale 1 si falla). Ejecutarla sobre el código actual, registrar la línea base en `testing/` y congelar el hash de `dataset-v1` antes de tocar la recuperación. Resultado: puerta separada que falla (rojo) en idioma, errores tipográficos y documento largo, y suite de 177 intacta (191 en total con los 14 tests de `test_metrics`).
- **Changelog**: Nueva puerta de calidad de recuperación separada de la suite, con línea base registrada y conjunto de evaluación congelado por hash.
- **Cerrada**: 2026-11-09
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,55h · real 0,00 (medido)
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 150k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-02
- **Tipo**: test
- **Archivos**: `memory_platform/tests/run_postgres.py`, `memory_platform/Dockerfile`, `memory_platform/tests/retrieval_eval/run.py`, `docs/roadmap/2026-11-09-retrieval-quality/testing/baseline.json`, `docs/roadmap/2026-11-09-retrieval-quality/testing/dataset-v1.sha256`, `docs/roadmap/2026-11-09-retrieval-quality/testing/README.md`, `memory_platform/tests/retrieval_eval/baseline.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → falla (exit ≠ 0) y el informe lista como fallidos al menos los subconjuntos idioma, errores tipográficos y documento largo (CA-02)
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (los 177 tests previos + 14 de `test_metrics` = 191 siguen verdes: la puerta nueva no forma parte de la suite)
  - `sha256sum memory_platform/tests/retrieval_eval/dataset-v1.jsonl` → coincide con `testing/dataset-v1.sha256`

**Criterios de aceptación**
- [x] CA-02: sobre el código previo a C-03…C-06 la puerta falla y la línea base queda en `docs/roadmap/2026-11-09-retrieval-quality/testing/baseline.json`
- [x] La suite backend sigue en 177/177 con 0 omitidos (decisión P-08): 191 con los 14 de `test_metrics`, 0 fallos, 0 omitidos
- [x] El hash de `dataset-v1` queda congelado y registrado (mitigación R-07)

**Subtareas**
- [x] Modo nuevo en `run_postgres.py` y target `retrieval-eval` (derivado de `test`, como `live-probe`)
- [x] Ejecutar la puerta, guardar `baseline.json` y el hash
- [x] Documentar en `testing/README.md` cómo se ejecuta la puerta y cómo se regenera la línea base

**Notas**: Procedencia: spec CA-02, CA-35, decisión P-08. Clase: capacidad nueva (test nuevo en rojo). Patrones: modos alternativos de `run_postgres.py:27-34` (`MEMORY_LIVE_PROBE`, `MEMORY_CLIENT_PROBE`) y target `live-probe` en `memory_platform/Dockerfile:34-37`; puerta congelada en `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`. Los evidencias de pruebas se escriben solo en `testing/`.

**Evidencia de verificación (2026-11-09)**
- `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → exit 1 (rojo esperado). Fused global: recall@5 0,153 (umbral 0,80), MRR 0,156 (umbral 0,60). Subconjuntos fallidos (CA-02): `es` recall@5 0,00; `typo_id` 0,00; `long` 0,50 (todos < 0,80 y sin ganancia sobre línea base). Control `en` recall@10 1,0. Capas: episodic 0,385, documental 0,20 (n=20), semantic 0,417 (recall@5).
- `docker build --target test ... -t kairos-test:rq .` (con `--no-cache-filter test`) → `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 183}`: 177 previos intactos + 6 nuevos de `test_metrics`; la puerta no forma parte de la suite.
- `sha256sum -c testing/dataset-v1.sha256` → `OK` (hash `1bba8d99...ad4be6f6`).
- Hallazgos de la línea base: (1) en `fused` los documentos (siempre `validated`) tienen prioridad sobre las memorias, por eso `en` tiene recall@1 0,17 pero recall@10 1,0; (2) en `semantic` los candidatos de score 0 se ordenan por clave, lo que da a `long` un 0,42 de recall@5 por desempate y no por señal. Para C-03/C-06.
- Notas de alcance: añadidos a `Archivos` `testing/README.md` y una copia `memory_platform/tests/retrieval_eval/baseline.json` (la imagen Docker no contiene `docs/`; la puerta la usa para medir la ganancia por subconjunto). Horas IA medidas de T-03: 0,00 porque el trabajo se hizo dentro de la ventana de T-02.

**Correccion tras la revision (intento 1, 2026-11-09)**
- Gap 4 (P-06): `evaluate_gate` exige recall@5 fused >= 0,80, MRR >= 0,60 y ganancia >= 15 puntos en es/typo_id/long (ya no «o»); sin linea base falla con `baseline_missing`. README de `retrieval_eval` y tests actualizados (un recall@5 de 0,85 sin ganancia falla).
- Minor 6: si `baseline.dataset_sha256` no coincide con el del informe falla con `baseline_dataset_mismatch`. Minor 8: «177» -> «186 (177 + 9 de test_metrics)» en comentario del Dockerfile y criterios.
- Linea base regenerada con el proveedor de n-gramas (ver T-02). Puerta sobre el codigo previo: exit 1 con `fused_recall_at_5` (0,50 < 0,80), `fused_mrr` (0,340 < 0,60), `subset:es`, `subset:typo_id`, `subset:long` (ganancia 0,0 < 15), `deterministic: true`, `network: unreachable`.
- `sha256sum -c testing/dataset-v1.sha256` -> OK (`1bba8d99...ad4be6f6`); `baseline.json` identicas en `testing/` y en `retrieval_eval/`.
- Horas IA medidas: 0,17 h en ventana compartida con T-02-fix1 (imputadas a T-02; T-03 sigue en 0,00).

**Correccion tras la revision (intento 2, 2026-11-09)**
- Gap 4: `testing/README.md` y el comentario del target `retrieval-eval` documentan el comando que funciona (`docker build --target test` + `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 <imagen> python -m memory_platform.tests.run_postgres`) y advierten que `docker build --network=none` falla en `apt-get`. Comentario del Dockerfile: 191 = 177 + 14 de `test_metrics`.
- Gap 5: Verificacion 1 ejecutada tal cual tras las correcciones: `docker build --progress=plain --target retrieval-eval -f memory_platform/Dockerfile .` -> exit 1 (rojo esperado). Informe: `deterministic: true`, `dataset_sha256: 1bba8d99...ad4be6f6`, `product_database_accessed: false`, `network_interfaces: ["eth0","lo"]` (el build tiene red; solo se observa), fallos `fused_recall_at_5` (0,50), `fused_mrr` (0,340), `subset:es` (0,333), `subset:typo_id` (0,583), `subset:long` (0,50); sin `backend_unavailable`. Cifras identicas a la linea base.
- `sha256sum -c testing/dataset-v1.sha256` -> OK; `cmp` de las dos `baseline.json` -> identicas. Horas IA: 0,00 (imputadas a T-02-fix2).

---

## Fase 2 — Refactor de `store.py` (C-02 · P11)

**Estado**: completado · **Estimado**: 14h base (16.8h con margen) · **Real**: — · **Coste est.**: 840 € · **Tokens est.**: 900k in / 120k out

### T-04 — Instantánea de superficie de `Store` y recibo previo de la suite

- **Descripción**: Antes de mover nada: capturar `dir(Store)` (sin dunders) y `inspect.signature` de cada método en una instantánea versionada, crear el test de superficie (CA-05) y registrar un recibo de la suite completa en verde sobre el código sin tocar. Resultado: red de seguridad medible para el refactor.
- **Changelog**: Nueva red de seguridad que detecta cualquier cambio accidental en los nombres o firmas públicos del almacén de memoria.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,73h · real 0,13 (medido; 0,04 + 0,09 de la corrección intento 1)
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 25k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-03
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_store_surface.py`, `memory_platform/tests/store_surface.json`, `docs/roadmap/2026-11-09-retrieval-quality/testing/store-refactor-before.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (177 + el test nuevo, sobre el `store.py` sin modificar)
  - `python -c "from memory_platform.store import Store, as_dict, canonical, digest, new_id, lexical_query, clean"` → sin error

**Criterios de aceptación**
- [x] CA-05: `test_store_surface` compara nombres públicos y privados y firmas contra `store_surface.json` y pasa sobre el código actual
- [x] CA-04: recibo previo con 177/177, 0 fallos, 0 omitidos guardado en `testing/store-refactor-before.json`

**Subtareas**
- [x] Generar `store_surface.json` desde el código sin tocar
- [x] Escribir el test (incluido el import de helpers reexportados)
- [x] Ejecutar la suite y guardar el recibo

**Notas**: Procedencia: spec CA-04, CA-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `65f909b4968c`.

### T-05 — Dividir `Store` en mixins por dominio con `store.py` como fachada

- **Descripción**: Mover los ~65 métodos de `Store` a módulos de dominio (`store_auth.py`, `store_ingest.py`, `store_documents.py`, `store_jobs.py`, `store_vectors.py`, `store_graph.py`) y compartir helpers privados (`_require`, `_item`, `_jobs`) sin cambiar firmas. `store.py` compone `class Store(...mixins)` y reexporta `as_dict`, `canonical`, `digest`, `new_id`, `lexical_query`, `clean`. Resultado: ningún cambio de comportamiento y ningún módulo > 400 líneas.
- **Changelog**: El almacén de memoria se reorganiza internamente en módulos por dominio, sin cambiar su API ni su comportamiento.
- **Estado**: completado
- **Tiempo humano**: est. 9h · real —
- **Tiempo IA (ejec.)**: est. 2,19h · real 0,05 (medido)
- **Supervisión**: est. 0,55h (≈25 % IA) · real —
- **Previsión IA**: 580k in / 75k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-04
- **Tipo**: backend
- **Archivos**: `memory_platform/store.py`, `memory_platform/store_auth.py`, `memory_platform/store_ingest.py`, `memory_platform/store_documents.py`, `memory_platform/store_jobs.py`, `memory_platform/store_vectors.py`, `memory_platform/store_graph.py`, `memory_platform/store_common.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (misma suite que en T-04, incluido `test_store_surface`)
  - `wc -l memory_platform/store.py memory_platform/store_*.py` → `store.py` ≤ 120 y cada módulo nuevo ≤ 400

**Criterios de aceptación**
- [x] CA-04: la suite completa pasa igual que antes (177 + test de superficie, 0 fallos, 0 omitidos)
- [x] CA-05: nombres y firmas idénticos a la instantánea; los imports `from memory_platform.store import …` siguen funcionando
- [x] CA-06: `store.py` ≤ 120 líneas y ningún módulo de dominio supera 400
- [x] Sin cambios de comportamiento: ningún test existente modificado

**Subtareas**
- [x] Crear `store_common.py` con helpers y estado compartido
- [x] Mover dominio a dominio ejecutando la suite tras cada movimiento
- [x] Recomponer `Store` en la fachada y reexportar helpers
- [x] Revisar importadores: `app.py`, `admin.py`, `agent_store.py`, `extended_store.py`, `portal_store.py`, `corpus_answers.py`, `agent_tools.py`, `worker.py`

**Notas**: Procedencia: spec CA-04…CA-06, decisión «Refactor de Store» (mixins). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ef3c30c6b54e`.
```
30 memory_platform/store.py
  217 memory_platform/store_auth.py
   36 memory_platform/store_common.py
  258 memory_platform/store_documents.py
  102 memory_platform/store_graph.py
  193 memory_platform/store_ingest.py
  112 memory_platform/store_jobs.py
  141 memory_platform/store_vectors.py
 1089 total
```. Cuerpos de método movidos sin cambios. Suite tras el refactor: `MEMORY_TEST_RESULT` tests 194, failures 0, errors 0, skipped 0, passed true (idéntico al recibo previo); `test_store_surface` OK; ningún test existente modificado. Importadores (`app, admin, agent_store, extended_store, portal_store, corpus_answers, worker`) usan `from .store import …`, que sigue válido (suite verde). Puerta `retrieval-eval` tras el refactor: mismas cifras que la línea base (fused recall@5 0,5; MRR 0,3398; mismos fallos), `deterministic: true`, exit 1 esperado.
- **Nota sobre CA-04**: ver nota de T-04 (194 en lugar de 177 por tests añadidos, no por cambios de comportamiento).

### T-06 — Recibo posterior del refactor y ajuste de la puerta congelada

- **Descripción**: Actualizar la lista de ficheros del manifiesto de `frozen-source-gate.py` para los módulos nuevos y registrar el recibo de la suite completa tras el refactor, comparable con el previo. Resultado: CA-04 demostrado con dos recibos.
- **Changelog**: Queda demostrado con dos recibos de la suite que el refactor del almacén no cambió ningún resultado.
- **Estado**: completado
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,49h · real 0,02 (medido)
- **Supervisión**: est. 0,12h (≈25 % IA) · real —
- **Previsión IA**: 130k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-05
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`, `docs/roadmap/2026-11-09-retrieval-quality/testing/store-refactor-after.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0`
  - `python -c "import json;a=json.load(open('docs/roadmap/2026-11-09-retrieval-quality/testing/store-refactor-before.json'));b=json.load(open('docs/roadmap/2026-11-09-retrieval-quality/testing/store-refactor-after.json'));print(a['tests']==b['tests'],b['failures'],b['skipped'])"` → `True 0 0` (ambos recibos son de la puerta congelada con su `source_sha256`; el previo, en su primer nivel, es el código de 60be598 con la misma suite de 194 tests; la ejecución pura de 60be598, 191 tests, queda en `pre_refactor_suite_at_60be598`)

**Criterios de aceptación**
- [x] CA-04: recibo previo y posterior con el mismo recuento de tests, 0 fallos y 0 omitidos
- [x] El manifiesto de la puerta congelada incluye los módulos `store_*.py` y su hash coincide con el árbol actual

**Subtareas**
- [x] Ajustar el manifiesto de `frozen-source-gate.py` — no necesario: la puerta copia el árbol entero (`frozen-source-gate.py:45-48`); se verificó que no hacía falta cambio
- [x] Ejecutar la puerta y guardar el recibo posterior

**Notas**: Procedencia: spec CA-04. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `8b476017d058`.

---

## Fase 3 — pgvector + HNSW (C-03 · P1)

**Estado**: completado · **Estimado**: 32h base (38.4h con margen) · **Real**: — · **Coste est.**: 1.920 € · **Tokens est.**: 1200k in / 90k out

### T-07 — Imagen PostgreSQL derivada con pgvector en compose y target `test`

- **Descripción**: Añadir al Dockerfile una etapa `postgres-pgvector` derivada de `postgres:17-bookworm@sha256:839fbb5a…` que instale `postgresql-17-pgvector` con versión fijada (≥ 0.8.0, a verificar con `apt-cache madison` en el digest), y usarla en `memory-postgres` (compose con `build:`) y como base del target `test` (y derivados `live-probe`, `lifecycle-test`). Resultado: producción y suite comparten binarios, con digest y versión de pgvector fijados.
- **Changelog**: PostgreSQL de memoria pasa a una imagen propia con pgvector (versión fijada), la misma que usan las pruebas; los datos existentes siguen siendo compatibles.
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,54h · real 0,06 (medido)
- **Supervisión**: est. 0,13h (≈25 % IA) · real —
- **Previsión IA**: 150k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-06
- **Tipo**: devops
- **Archivos**: `memory_platform/Dockerfile`, `docker-compose.yml`, `docs/roadmap/2026-11-09-retrieval-quality/testing/pgvector-version.txt`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker compose --profile memory config` → `memory-postgres` muestra `build` con target `postgres-pgvector`; `grep -n "postgres:17-bookworm@sha256" memory_platform/Dockerfile docker-compose.yml` → una sola declaración del digest (en el Dockerfile)
  - `docker run --rm --entrypoint psql kairos-pg:rq --version` y `docker run --rm kairos-pg:rq sh -c "ls /usr/share/postgresql/17/extension/vector.control /usr/share/postgresql/17/extension/unaccent.control /usr/share/postgresql/17/extension/pg_trgm.control"` → los tres ficheros existen
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (la suite de 177 sigue verde sobre la imagen nueva)

**Criterios de aceptación**
- [x] CA-13: `memory-postgres` y el target `test` usan la misma base con digest `sha256` y pgvector con versión fijada; `docker compose config` lo muestra
- [x] La versión de pgvector instalada es ≥ 0.8.0 y consta en `testing/pgvector-version.txt`
- [x] `unaccent` y `pg_trgm` están disponibles en el digest fijado (supuesto ⚠️ verificar de la spec)
- [x] Volumen existente compatible: misma versión mayor 17, sin `pg_upgrade`

**Subtareas**
- [x] Verificar la versión disponible de `postgresql-17-pgvector` en PGDG para el digest y fijarla
- [x] Crear la etapa `postgres-pgvector` y apuntar `test` a ella
- [x] Cambiar `memory-postgres` a `build:` con la misma etapa
- [x] Comprobar que `deploy-memory.py` sigue construyendo/arrancando `memory-postgres` (fase `database`)

**Notas**: Procedencia: spec CA-13, decisión P-01, riesgos R-01/R-02. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e629bc633e74`.


### T-08 — Migración aditiva: extensión `vector`, `embedding`, `dims` y relleno

- **Descripción**: Añadir la versión de esquema siguiente (aditiva): `CREATE EXTENSION vector`, columna `embedding vector` y `dims` generada en `memory.embeddings`, relleno desde `vector double precision[]` y el índice HNSW parcial para `nomic-embed-text:768` (configurable con `MEMORY_VECTOR_INDEXES`). La columna original queda intacta. Resultado: base migrada sin pérdida, con hash por fila idéntico.
- **Changelog**: La base de memoria incorpora pgvector con una migración aditiva que conserva los vectores existentes y rellena la columna nueva; configurable con MEMORY_VECTOR_INDEXES.
- **Estado**: completado
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,67h · real 0,21 (medido; 0,16 + 0,05 de la corrección intento 1)
- **Supervisión**: est. 0,17h (≈25 % IA) · real —
- **Previsión IA**: 190k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-07
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/config.py`, `memory_platform/admin.py`, `memory_platform/tests/test_pgvector_migration.py`, memory_platform/store_auth.py, memory_platform/store_vectors.py, docs/roadmap/2026-11-09-retrieval-quality/testing/migration-cost.json
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_pgvector_migration`: test en rojo antes de la migración)
  - `grep -nEi "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → ninguna coincidencia en las versiones nuevas (CA-34)

**Criterios de aceptación**
- [x] CA-07: tras `python -m memory_platform.admin migrate` sobre una base con embeddings de 2 y 768 dims existe la extensión `vector` ≥ 0.8.0, todas las filas tienen `embedding` no nulo con `dims = array_length(vector,1)`, la columna `vector` es idéntica (hash por fila antes/después) y `memory.schema_versions` registra la versión nueva
- [x] CA-34: la migración no contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE` y `content_manifest().sha256` es igual antes y después
- [x] La migración falla antes de cambiar datos si la extensión no está disponible (transacción + bloqueo consultivo actuales)

**Subtareas**
- [x] Escribir primero el test de migración sobre fixture con versión actual y embeddings de 2 y 768 dims
- [x] Añadir la migración (extensión, columnas, relleno, índice HNSW parcial)
- [x] Leer `MEMORY_VECTOR_INDEXES` (`nomic-embed-text:768` por defecto)
- [x] Comprobar el rol del DSN de migración para `CREATE EXTENSION` y documentar el resultado (R-03)

**Notas**: Procedencia: spec CA-07, CA-34, decisiones P-01/P-02. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `62628383c266`.

### T-09 — Búsqueda vectorial con HNSW, escaneo iterativo, ruta exacta y doble escritura

- **Descripción**: Reescribir `search_vectors`, `_vector_candidates` y `has_vectors` en `store_vectors.py` para usar el operador `<=>` de pgvector: HNSW con `hnsw.iterative_scan = relaxed_order`, `hnsw.max_scan_tuples = 20000`, `hnsw.ef_search = 100` por transacción para el modelo/dimensión indexados y ruta exacta SQL (tope 10.000) para el resto. Conservar permisos, versión vigente, hash, `deadline`/`statement_timeout`, `candidate_limit` y `candidates_truncated`. `complete_job` escribe `vector` y `embedding` en la misma fila.
- **Changelog**: La búsqueda semántica usa pgvector: índice HNSW para el modelo indexado y coseno exacto en SQL para el resto, con los mismos permisos, plazos y avisos de truncado.
- **Estado**: completado
- **Tiempo humano**: est. 8h · real —
- **Tiempo IA (ejec.)**: est. 1,07h · real 0,92 (medido; 0,44 + 0,40 + 0,08 de la corrección intento 2)
- **Supervisión**: est. 0,27h (≈25 % IA) · real —
- **Previsión IA**: 300k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-08
- **Tipo**: backend
- **Archivos**: `memory_platform/store_vectors.py`, `memory_platform/store_jobs.py`, `memory_platform/retrieval.py`, `memory_platform/config.py`, `memory_platform/tests/test_embeddings.py`, memory_platform/tests/test_vector_search_paths.py, memory_platform/tests/store_surface.json, memory_platform/tests/test_retrieval.py, `docker-compose.yml`, `docs/configuration.md`, `docs/operations.md` (los tres últimos añadidos por la corrección intento 3: variable `MEMORY_VECTOR_EXACT_FALLBACK_MS` en `x-memory-environment` y su documentación)
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluidos los tests de `test_embeddings.py` sin cambiar sus aserciones, CA-09)
  - `docker build --target test …` ejecuta el nuevo `test_vector_search_paths` → paridad: mismo conjunto de ids que la ruta anterior en 2 dims (ruta exacta) y mismo top-k en 768 dims frente al coseno exacto

**Criterios de aceptación**
- [x] CA-09: las pruebas existentes de `test_embeddings.py` pasan sin cambiar sus aserciones (sin permiso → `Forbidden`; borrados/sustituidos/hijos desfasados excluidos; otro modelo, dimensión distinta o vector cero → `[]`; filtros `categories`/`tags`)
- [x] CA-10: con `deadline` vencido se lanza `semantic_deadline_exceeded` (503); con plazo corto se aplica `statement_timeout` (espía sobre `set_config`)
- [x] CA-11: cada acierto conserva `candidate_limit` y `candidates_truncated`; con 2 dims usa ruta exacta y con > 10.000 candidatos `candidates_truncated = true`
- [x] CA-12: `complete_job` rellena `vector` y `embedding` en la misma fila
- [x] Paridad de resultados con la ruta actual en el fixture de 2 dims

**Subtareas**
- [x] Escribir tests en rojo de rutas (ANN/exacta), doble escritura y `candidates_truncated`
- [x] Implementar consulta ANN con escaneo iterativo y parámetros por transacción
- [x] Implementar ruta exacta SQL para dimensiones/modelos no indexados
- [x] Eliminar la consulta extra de `has_vectors` si es posible sin cambiar su semántica
- [x] Doble escritura en `complete_job`

**Notas**: Procedencia: spec CA-09…CA-12, decisiones P-02, «Filtrado con ANN», «candidates_truncated». Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `106b33409546`.
- **Verificación**: suite completa `MEMORY_TEST_RESULT` tests 207, failures 0, errors 0, skipped 0, passed true (199 + 8 de `test_vector_search_paths`); `test_embeddings` (5 tests) verde sin tocar. Paridad: ruta exacta, mismo orden e ids que el ranking Python anterior (incluidos empates); HNSW 768 dims: top-1 exacto y ≥ 9/10 del top-10 del coseno exacto (el recall@10 ≥ 95 % sobre 2.000 filas es T-10). CA-10: `semantic_deadline_exceeded` 503 con plazo vencido y un único `set_config('statement_timeout')` con plazo corto. CA-11: 2 dims → ruta exacta; 10.050 candidatos → `candidates_truncated=true`, `candidate_limit=10000`. CA-12: un INSERT con `(…,vector,embedding)`, fila con `dims=vector_dims(embedding)=array_length(vector)=768`.
- **Corrección intento 1 (T-09-fix1)**: gaps #2, #5, #6, #10, #12, #13. **#2**: `_vector_candidates(self, c, projects, model, categories, tags, limit, *, stream=False, identities=None)` restaurado (parámetro aceptado e ignorado, con comentario) y `memory_platform/tests/store_surface.json` devuelto a su contenido de `fc4c045` (`git show fc4c045:… > …`; `git diff fc4c045 --stat -- memory_platform/tests/store_surface.json` vacío); lo nuevo es de módulo (`vector_results`, `rank_ann`, `rank_exact`, `VectorResults`), no añade nombres a `Store`; `test_store_surface` 3/3 sin regenerar. **#5/#12**: `rank_ann` cuenta los vectores del modelo y dimensión SOLO en `project_id = ANY(proyectos autorizados)` (con `LIMIT 10.001`, usa el índice `memory_embedding_scope`): ≤ 10.000 → recalcula con `rank_exact`; > 10.000 y respuesta corta (incluida vacía) → `candidates_truncated = true`; el volumen de otros proyectos ya no influye. `search_vectors` devuelve `VectorResults` (subclase de `list`, compatible con los llamantes: `== []`, indexado) con `candidates_truncated` y `candidate_limit`, y `retrieval._scan_vectors/vectors()` los lee aunque no haya aciertos (`status = partial`). **#6**: `candidate_limit` se calcula ANTES de `hit()` (que descarta el campo). **#13**: `arm()` recalcula `statement_timeout` con lo que queda del plazo antes de cada sentencia (ranking, recuento, exacta, lectura de payload). **#10**: nota añadida al changelog de `improvement-plan.md` (fila nueva, sin reescribir lo aprobado). Tests (`test_vector_search_paths`, 12): `test_short_answer_is_judged_on_authorized_rows_only` (150 vectores de otro proyecto + 5 propios, tope parcheado a 100: recupera los 5 en orden exacto con 1 llamada a `rank_exact`), `test_empty_answer_over_a_large_authorized_population_is_truncated` (vacío + `candidates_truncated`), `test_short_answer_over_a_large_authorized_population_flags_every_hit`, `test_population_count_uses_only_the_authorized_projects` (SQL con `e.project_id=ANY(%s)` y parámetro `[pid]`), y `test_expired_deadline_and_short_deadline_timeout` ahora exige ≥ 3 `set_config('statement_timeout')` no crecientes; en `test_retrieval` (+2): `test_backend_reports_the_candidate_limit_of_the_route_that_ran` (20000) y `test_truncated_empty_semantic_answer_is_partial`. Rojo: no aplicable por construcción (los tests leen atributos de `VectorResults` que no existían; contra el código anterior fallan con `AttributeError`).
- **Corrección intento 2 (T-09-fix2)**: gaps #1, #2, #4. #1: Suite completa sobre el árbol actual (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq .`, exit 0), línea literal: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 235}`. #2 (prosa desactualizada, sin reescribir criterios): `memory_platform/tests/store_surface.json` figura en `Archivos` pero **NO se modifica** desde la corrección intento 1 (`git diff fc4c045 --stat -- memory_platform/tests/store_surface.json` vacío); las frases anteriores de esta tarea que dicen que la instantánea cambió quedan sustituidas por esta nota. #4: el recuento de población de `rank_ann` aplica `CURRENT_RESOURCE` (mismos filtros de versión vigente, hash, borrado, padre, categorías y etiquetas que la clasificación) manteniendo `project_id = ANY(autorizados)`, así que versiones antiguas y elementos retirados ya no empujan un corpus pequeño por encima del límite de la ruta exacta. Test nuevo `test_withdrawn_and_old_rows_do_not_count_towards_the_exact_route_limit` (150 filas, 120 borradas y 1 con versión nueva: solo 29 vigentes → ruta exacta, 29 aciertos, sin `candidates_truncated`; con el recuento anterior habría sido 150 > 100 y habría salido truncado). Honestidad sobre los tests de truncado: pgvector no permite forzar con datos reales que el escaneo pare antes de `limit` (con `ef_search`/`max_scan_tuples` parcheados a 1 seguía devolviendo aciertos), así que los dos tests de truncado reales del intento 1 se sustituyeron por `test_short_or_empty_scan_over_a_large_authorized_population_is_truncated` y `test_short_scan_over_a_population_within_the_exact_limit_is_recomputed` (conexión simulada para el recuento y el escaneo, que prueban la decisión de `rank_ann`) y `test_a_truncated_route_marks_the_results_object_and_every_hit` (base real, ruta forzada a truncada, que prueba que el aviso llega al objeto y a cada acierto); la propagación a `retrieval` sigue cubierta por `test_truncated_empty_semantic_answer_is_partial`. Medición de horas: los cuatro marcadores `-fix2` se abrieron a la vez y miden la misma ventana (0,08 h cada uno); se imputan una sola vez, aquí.
- **Corrección tras el cierre (T-09-fix3, a petición del usuario; deuda #3 del intento 3 de la Fase 3)**: el respaldo exacto de `rank_ann` hacía un recuento (`CURRENT_RESOURCE`, `LIMIT 10001`) y después `rank_exact` recorría lo mismo: dos recorridos con SubPlan correlacionado. **Diseño final**: (a) un único recorrido: se elimina el recuento; si el escaneo HNSW sale corto se ejecuta `rank_exact` y, si informa `truncated` (más de 10.000 candidatos vigentes), se devuelven las filas HNSW con `truncated=True` y `candidate_limit` 20.000; si no, el resultado exacto. (b) presupuesto acotado: el respaldo corre en un savepoint (`with c.transaction():`, el patrón de psycopg que ya usa `Store.transaction`) con `statement_timeout = min(resto del plazo, MEMORY_VECTOR_EXACT_FALLBACK_MS)`; nueva `config.exact_fallback_ms()` (defecto 1500, entero positivo 1..600000, validada también al arrancar en `Settings.from_env`), pasada por `x-memory-environment` de `docker-compose.yml` y documentada en `docs/configuration.md` y `docs/operations.md`. `arm(cap=None)` de `search_vectors` aplica el tope; sin plazo global restaura el `statement_timeout` de sesión al terminar. (c) si el tope cancela el respaldo (`QueryCanceled`) y el plazo global NO ha vencido, el savepoint se revierte y se devuelven las filas HNSW con `truncated=True` (el llamante ve `partial`; la transacción sigue sirviendo la lectura final); si ha vencido el plazo global, `arm()` relanza `semantic_deadline_exceeded` como antes. (d) sin fallbacks silenciosos: el degradado es `candidates_truncated=True`, distinguible. Sin cambios de firma de `Store` (`store_surface.json` intacto; `rank_ann`/`rank_exact` son funciones de módulo) ni migraciones; 34 herramientas MCP sin tocar. **Rojo previo**: `RED: 7 de 240 fallaron (4 failures + 3 errors: test_exhausted_fallback_budget_* x2, test_the_global_deadline_expiring_during_the_fallback_*, test_short_answer_over_more_current_candidates_*, test_short_or_empty_scan_*, test_short_scan_over_a_population_*, test_population_count_*) · 2026-11-09`, es decir `MEMORY_TEST_RESULT … "errors": 3, "failures": 4, "passed": false, … "tests": 240` contra el código sin cambiar. **Tests** (`test_vector_search_paths`): los tres de stub se reescriben sin debilitar ningún assert de comportamiento: `test_short_or_empty_scan_over_a_large_authorized_population_is_truncated` (antes: recuento simulado 101>100 daba `([], 20000, True)` y 5000 daba `(some, True)` sin llamar a `rank_exact`; ahora: `rank_exact` devuelve `truncated=True` y salen las mismas dos tuplas, vacía y con filas, con UNA llamada por búsqueda), `test_short_scan_over_a_population_within_the_exact_limit_is_recomputed` (antes: población 100 daba el resultado de `rank_exact`; ahora: `rank_exact` no truncado da su resultado exacto, 1 llamada) y `test_population_count_uses_only_the_authorized_projects` (antes: SQL del recuento con `e.project_id=ANY(%s)` y `[pid]`; ahora: no existe ninguna sentencia `count(*) AS n` y hay UN solo recorrido `WITH cand` con `e.project_id=ANY(%s)`, parámetro `[pid]` y `NOT d.deleted`). Las filas no vigentes siguen cubiertas por `test_withdrawn_and_old_rows_do_not_count_towards_the_exact_route_limit` y las de otros proyectos por `test_short_answer_is_judged_on_authorized_rows_only` (sin cambios). Nuevos: `test_a_full_scan_never_runs_the_exact_fallback`, `test_short_answer_over_more_current_candidates_than_the_exact_limit_is_flagged_with_the_index_rows` (datos reales: 8 candidatos, límite parcheado a 5, salen 8 filas HNSW truncadas), `test_exhausted_fallback_budget_returns_the_index_rows_as_partial_and_keeps_the_transaction_usable` (respaldo real que duerme 10 s con tope 300 ms: cancelado, 6 filas HNSW truncadas, `statement_timeout` 300 aplicado y la misma transacción sirve la lectura final), `test_exhausted_fallback_budget_without_a_deadline_still_degrades_to_partial`, `test_the_global_deadline_expiring_during_the_fallback_keeps_semantic_deadline_exceeded` (503) y `ExactFallbackSettingTests`. Límite conocido (preexistente, no cambiado): `rank_exact` calcula `truncated` desde la primera fila, así que con más de 10.000 candidatos y TODOS los primeros 10.000 de norma cero devolvería vacío sin truncado; no ocurre con vectores reales. **Suite completa** (`docker build --progress=plain --target test -f memory_platform/Dockerfile .`, exit 0), línea literal: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 241}` (235 + 6). Medición: usage-meter `T-09-fix3` y `T-10-fix3` abiertos a la vez (ventana de 13 min de reloj, sin transcripciones: 0,22 h IA `(estimado)`, imputadas una sola vez aquí).

### T-10 — Pruebas de plan HNSW y recall frente al coseno exacto

- **Descripción**: Tests con ≥ 2.000 embeddings de 768 dims del modelo indexado: `EXPLAIN` demuestra el uso del índice HNSW y el top-10 coincide ≥ 95 % con el coseno exacto de referencia; test de filtrado (permisos/proyecto/versión) con escaneo iterativo; ajuste de `ef_search`/`max_scan_tuples` con la puerta `retrieval-eval`.
- **Changelog**: Comprobado con 2.600 vectores de 768 dimensiones que la búsqueda por índice HNSW devuelve los mismos resultados que el coseno exacto, también con filtros de permisos y etiquetas.
- **Estado**: completado
- **Tiempo humano**: est. 7h · real —
- **Tiempo IA (ejec.)**: est. 0,94h · real 0,19 (medido; 0,14 + 0,05 de la corrección intento 1)
- **Supervisión**: est. 0,24h (≈25 % IA) · real —
- **Previsión IA**: 260k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-09
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_vector_index.py`, `docs/roadmap/2026-11-09-retrieval-quality/testing/hnsw-recall.json`, `docs/roadmap/2026-11-09-retrieval-quality/testing/phase3-eval.json` (añadido por la corrección tras el cierre: informe completo de `retrieval-eval`, deuda #1 del intento 3)
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_vector_index`)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → informe con la capa `semantic` sobre HNSW; ninguna capa empeora más de 2 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [x] CA-08: el plan de `search_vectors` usa el índice HNSW y recall@10 ≥ 95 % frente al coseno exacto sobre las mismas filas
- [x] El filtrado por permisos/proyecto/versión con ANN no pierde resultados por debajo del umbral (escaneo iterativo)
- [x] Los parámetros finales (`ef_search`, `max_scan_tuples`) quedan documentados con su evidencia

**Subtareas**
- [x] Generar 2.000 vectores deterministas de 768 dims en el fixture
- [x] Test de `EXPLAIN` (el plan menciona el índice HNSW parcial)
- [x] Test de recall@10 frente a la ruta exacta
- [x] Afinar parámetros con la puerta `retrieval-eval` y guardar `hnsw-recall.json`

**Notas**: Procedencia: spec CA-08, riesgo R-04. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0afe04a48b8a`.
- **Verificación**: suite completa `MEMORY_TEST_RESULT` tests 209, failures 0, errors 0, skipped 0, passed true (207 + 2). Puerta: `docker build --progress=plain --target retrieval-eval -f memory_platform/Dockerfile .` → exit 1 (rojo esperado por diseño hasta las fases 4-6: fused recall@5 0,5 < 0,8, MRR 0,339809 < 0,6, ganancias de subconjunto 0) y el informe `RETRIEVAL_EVAL_RESULT` es IDÉNTICO al de `baseline.json` en `layers` (semantic recall@5 0,902778 / MRR 0,869097; episodic 0,384615; documental 0,2; fused 0,5 / 0,339809): `layers == baseline.layers` True, `deterministic` true. Ninguna capa empeora (0 puntos). Matiz: dataset-v1 solo tiene 72 recursos embebibles, así que la puerta valida la mecánica; el recall del HNSW lo prueba `test_vector_index`. Observación (no corregida, fuera de alcance): la consulta final de payload (`_vector_candidates`) sigue materializando `to_jsonb` de todos los documentos del proyecto (comportamiento previo); medir si hay corpus grandes.
- **Corrección intento 1 (T-10-fix1)**: gaps #5 (parte de pruebas) y #9. **#9**: `testing/hnsw-recall.json` lleva ahora el barrido REAL (`parameter_sweep`, 8 mediciones, ejecutado de nuevo en un PostgreSQL de pruebas aislado con el código corregido): `ef_search` 10/40/100/200 × sin filtro y etiqueta rara → `recall_at_10 = 1.0` y `exact_fallbacks = 0` en las 8, `ms_per_query` solo indicativo; el texto del ledger y de `docs/configuration.md` ya coincidía. **#5**: `test_a_tiny_project_inside_the_large_index_gets_all_its_hits_exactly` en `test_vector_index` (3 tests ahora): 4 vectores de un proyecto pequeño dentro del índice de 2.600 filas → 1 llamada a `rank_exact`, los 4 en orden exacto, sin truncado.
- **Corrección intento 2 (T-10-fix2)**: gap #1. Suite completa sobre el árbol actual (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq .`, exit 0), línea literal: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 235}`. Puerta (la Verificación de esta tarea la pide): `docker build --progress=plain --target retrieval-eval -f memory_platform/Dockerfile .` → exit 1 (rojo esperado por diseño) con `layers` IDÉNTICO a `baseline.json`: `{"documental": {"mrr": 0.2, "recall@5": 0.2}, "episodic": {"mrr": 0.384615, "recall@5": 0.384615}, "fused": {"mrr": 0.339809, "recall@5": 0.5}, "semantic": {"mrr": 0.869097, "recall@5": 0.902778}}`, `deterministic` true, `gate.passed` false.
- **Evidencia literal (deuda #1, intento 3)** (T-10-fix3, tras el cierre, a petición del usuario): `docker build --progress=plain --target retrieval-eval -f memory_platform/Dockerfile .` sobre el árbol con la corrección de T-09 → exit 1 (rojo esperado por diseño). El informe `RETRIEVAL_EVAL_RESULT` completo, tal como lo imprime `run.py` (25 KB: incluye `network_interfaces`), está en `docs/roadmap/2026-11-09-retrieval-quality/testing/phase3-eval.json`, sha256 `c06e9b461853bf26bdfe8a2d1bba8c021088769bf52d8063fc0be516853e3f3b` (la línea JSON del informe más un salto de línea). Claves: `dataset`, `dataset_sha256`, `deterministic` (true), `embedding_provider`, `gate`, `generated_at`, `layers`, `limit`, `model`, `network_interfaces`, `network_observation`, `product_database_accessed`, `query_backends`. Bloque `gate` literal: `{"baseline_compared": true, "failures": [{"check": "fused_recall_at_5", "required": 0.8, "value": 0.5}, {"check": "fused_mrr", "required": 0.6, "value": 0.339809}, {"check": "subset:es", "gain_points": 0.0, "required_gain_points": 15, "value": 0.333333}, {"check": "subset:typo_id", "gain_points": 0.0, "required_gain_points": 15, "value": 0.583333}, {"check": "subset:long", "gain_points": 0.0, "required_gain_points": 15, "value": 0.5}], "passed": false, "thresholds": {"dataset": "dataset-v1", "fused_mrr": 0.6, "fused_recall_at_5": 0.8, "gain_subsets": ["es", "typo_id", "long"], "subset_gain_points": 15}}`. `layers` literal (`overall` y `subsets`): `{"documental": {"overall": {"mrr": 0.2, "n": 20, "recall@1": 0.2, "recall@10": 0.2, "recall@5": 0.2}, "subsets": {"en": {"mrr": 1.0, "n": 4, "recall@1": 1.0, "recall@10": 1.0, "recall@5": 1.0}, "es": {"mrr": 0.0, "n": 4, "recall@1": 0.0, "recall@10": 0.0, "recall@5": 0.0}, "long": {"mrr": 0.0, "n": 12, "recall@1": 0.0, "recall@10": 0.0, "recall@5": 0.0}}}, "episodic": {"overall": {"mrr": 0.384615, "n": 52, "recall@1": 0.384615, "recall@10": 0.384615, "recall@5": 0.384615}, "subsets": {"en": {"mrr": 1.0, "n": 20, "recall@1": 1.0, "recall@10": 1.0, "recall@5": 1.0}, "es": {"mrr": 0.0, "n": 20, "recall@1": 0.0, "recall@10": 0.0, "recall@5": 0.0}, "typo_id": {"mrr": 0.0, "n": 12, "recall@1": 0.0, "recall@10": 0.0, "recall@5": 0.0}}}, "fused": {"overall": {"mrr": 0.339809, "n": 72, "recall@1": 0.180556, "recall@10": 0.916667, "recall@5": 0.5}, "subsets": {"en": {"mrr": 0.356614, "n": 24, "recall@1": 0.166667, "recall@10": 1.0, "recall@5": 0.625}, "es": {"mrr": 0.341022, "n": 24, "recall@1": 0.208333, "recall@10": 1.0, "recall@5": 0.333333}, "long": {"mrr": 0.354167, "n": 12, "recall@1": 0.25, "recall@10": 0.5, "recall@5": 0.5}, "typo_id": {"mrr": 0.289418, "n": 12, "recall@1": 0.083333, "recall@10": 1.0, "recall@5": 0.583333}}}, "semantic": {"overall": {"mrr": 0.869097, "n": 72, "recall@1": 0.847222, "recall@10": 0.916667, "recall@5": 0.902778}, "subsets": {"en": {"mrr": 1.0, "n": 24, "recall@1": 1.0, "recall@10": 1.0, "recall@5": 1.0}, "es": {"mrr": 1.0, "n": 24, "recall@1": 1.0, "recall@10": 1.0, "recall@5": 1.0}, "long": {"mrr": 0.214583, "n": 12, "recall@1": 0.083333, "recall@10": 0.5, "recall@5": 0.416667}, "typo_id": {"mrr": 1.0, "n": 12, "recall@1": 1.0, "recall@10": 1.0, "recall@5": 1.0}}}}`. `layers == baseline.json['layers']` True: ninguna capa empeora (0 puntos).

### T-11 — Ensayo de despliegue y restauración en instancia aislada

- **Descripción**: En una instancia aislada con datos sintéticos (nunca la desplegada, volúmenes y nombre de proyecto propios), ejecutar `scripts/deploy-memory.py` con la imagen nueva hasta completar sus 10 fases, comprobar la copia de seguridad previa, `content_manifest().sha256` antes/después y la restauración de esa copia con `admin restore` en una instancia con pgvector (`store_fingerprints` idénticos). Resultado: evidencia de CA-14 sin tocar la base real.
- **Changelog**: El despliegue y la restauración con la nueva imagen de PostgreSQL se ensayaron de principio a fin en una instalación aislada, sin tocar la real; el script admite ahora un proyecto de ensayo.
- **Estado**: completado
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,67h · real 0,75 (medido; 0,53 + 0,22 de la corrección intento 1)
- **Supervisión**: est. 0,17h (≈25 % IA) · real —
- **Previsión IA**: 190k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-10
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `scripts/tests`, `docs/roadmap/2026-11-09-retrieval-quality/testing/deploy-rehearsal.json`, memory_platform/tests/test_deploy_isolation.py
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/deploy-memory.py --apply --project-name kairos-rehearsal …` (opciones de aislamiento a fijar en la tarea) → `status: ok`, las 10 fases en `phases`, backup presente
  - `python -m memory_platform.admin content-manifest` antes y después de migrar en la instancia de ensayo → mismo `sha256`
  - `docker volume ls --filter name=knowledge-graphs_memory` → los volúmenes reales siguen sin cambios (el ensayo usa volúmenes `kairos-rehearsal_*`)

**Criterios de aceptación**
- [x] CA-14: las 10 fases completan con la imagen nueva, existe la copia previa y `content_manifest().sha256` es igual antes y después de migrar
- [x] CA-14: restaurar la copia con `admin restore` en una instancia con pgvector produce `store_fingerprints` idénticos al origen
- [x] Evidencia en `testing/deploy-rehearsal.json` sin secretos; el ensayo no usó los volúmenes `knowledge-graphs_memory-postgres-data` ni `knowledge-graphs_memory-backups`
- [x] R-03 resuelto: queda anotado qué rol ejecuta `CREATE EXTENSION vector`

**Subtareas**
- [x] Preparar el aislamiento (nombre de proyecto, volúmenes, secretos sintéticos, puertos) sin tocar los reales
- [x] Sembrar datos sintéticos con la versión de esquema anterior
- [x] Ejecutar el despliegue de ensayo y registrar fases y manifiestos
- [x] Restaurar la copia en una segunda instancia y comparar `store_fingerprints`
- [x] Destruir la instancia de ensayo y sus volúmenes

**Notas**: Procedencia: spec CA-14, riesgos R-01/R-02/R-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `37f605675cd7`.
- **Verificación**: `docker volume ls --filter name=knowledge-graphs_memory --format '{{.Name}}'` antes y después del ensayo: idéntico (`knowledge-graphs_memory-backups`, `_memory-managed-data`, `_memory-postgres-data`); ningún comando direccionó contenedores/redes/volúmenes `knowledge-graphs-*` (todos con `-p kairos-rehearsal` y verificación previa de que `config` solo trae nombres `kairos-rehearsal_*`). Suite final `MEMORY_TEST_RESULT` tests 215, failures 0, errors 0, skipped 0, passed true. Un intento de leer la BD real (`psql` en el contenedor `knowledge-graphs-memory-postgres-1`) fue DENEGADO por el clasificador y no se ejecutó; no se usó ningún dato de la instalación real.
- **Destrucción**: la instancia se destruyó DESPUÉS del ensayo de retroceso de T-12 (que reutiliza esa instancia): `docker compose -p kairos-rehearsal … down -v --remove-orphans` tras verificar los nombres; `docker ps -a/volume ls/network ls --filter name=kairos-rehearsal` → vacío; imágenes `kairos-rehearsal-*` eliminadas; secretos sintéticos y `.private/kairos-rehearsal` borrados.
- **Nota**: la Verificación pide `--project-name kairos-rehearsal …` («opciones de aislamiento a fijar en la tarea»): fijadas arriba. `scripts/tests` no se tocó (los tests nuevos viven en `memory_platform/tests`, que ejecuta la suite).
- **Corrección intento 1 (T-11-fix1)**: gaps #1, #3(d), #7, #16. **#1/#16**: las imágenes del override son siempre `rehearsal-<proyecto>-<servicio>:latest` (nunca `kairos-*`: un proyecto llamado `kairos` ya no reutiliza `kairos-api:latest`); `check_isolation_names` aborta si algo generado coincide con un `image:` o un `knowledge-graphs_*` de `docker-compose.yml`; la carpeta privada es `.private/rehearsal-<proyecto>` y el script aborta si ya existe con ficheros que el ensayo no creó. **#7**: en modo aislado no se heredan `MEMORY_*`, `COMPOSE_*` ni `KAIROS*` del entorno (se pasa un entorno limpio + `MEMORY_ALLOWED_ORIGINS`), `MEMORY_SECRETS_DIR` solo sale del env-file del proyecto, y se pasa SIEMPRE `--env-file` del proyecto (si falta, el script aborta antes de cualquier llamada a Compose) para que Compose no cargue el `.env` raíz. **#3(d)**: la fase `migrate` usa `timeout=MIGRATE_TIMEOUT_SECONDS` (3600 s, no los 120 s) y el informe registra `migrate_timeout_seconds`. Tests nuevos en `test_deploy_isolation` (12 en total): `test_project_named_kairos_cannot_produce_installed_image_tags`, `test_a_colliding_generated_name_is_refused`, `test_existing_private_subdirectory_of_somebody_else_is_never_adopted`, `test_isolated_environment_drops_memory_compose_and_kairos_variables`, `test_isolated_run_needs_its_own_env_file_before_any_compose_call`, `test_migrate_phase_has_its_own_long_timeout_recorded_in_the_report`; `test_deploy` (7) intacto.
- **Ensayo repetido**: como cambiaron `schema.sql`, `store_vectors.py`, `deploy-memory.py` y otros ficheros que cubre el ensayo, se REPITIÓ entero sobre el árbol corregido (`kairos-rehearsal`, carpeta `.private/rehearsal-kairos-rehearsal`, imágenes `rehearsal-kairos-rehearsal-*`): 10 fases, `status: complete`, `migrate_timeout_seconds: 3600`, `content_manifest().sha256` igual (`a1d0de28…ede35`), restauración de la copia previa con `store_fingerprints` idénticos, `restore-check` del dump posterior `restored_and_content_verified`, y un `admin migrate` posterior con `relfilenode` idénticos. `deploy-rehearsal.json` y `rollback-rehearsal.json` se regeneraron con los `source_sha256` del árbol corregido, con `store_auth.py` incluido. Instancia destruida de nuevo (`docker ps/volume ls/network ls --filter name=kairos-rehearsal` vacío; imágenes `rehearsal-*` retiradas; `.private/rehearsal-kairos-rehearsal` y secretos borrados); `docker volume ls --filter name=knowledge-graphs_memory` idéntico al inicial.
- **Corrección intento 2 (T-11-fix2)**: gaps #1 y #2. #1: Suite completa sobre el árbol actual (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq .`, exit 0), línea literal: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 235}`. #2 (prosa desactualizada, sin reescribir criterios): desde la corrección intento 1 la carpeta del ensayo es `.private/rehearsal-<proyecto>/` (no `.private/<proyecto>/`) y las imágenes se llaman `rehearsal-<proyecto>-<servicio>:latest` (no `kairos-rehearsal-*`); donde los bloques anteriores de esta tarea dicen lo contrario rige esta nota. El ensayo se hizo con esos nombres definitivos (`.private/rehearsal-kairos-rehearsal`, `rehearsal-kairos-rehearsal-*`) y los `source_sha256` de la evidencia son los del árbol que ejercitó el ensayo. Después cambiaron solo `store_vectors.py` (el recuento de población usa `CURRENT_RESOURCE`) y `docker-compose.yml` (la variable `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` con su valor por defecto de 256MB, el que la migración ya usaba); sus hashes actuales constan en `post_rehearsal_changes` de `deploy-rehearsal.json` y `rollback-rehearsal.json`, el ensayo NO se repitió y lo cubre la suite de arriba (no cambia el camino de despliegue que ejercita).

### T-12 — Procedimiento de retroceso y documentación operativa de pgvector

- **Descripción**: Documentar en `docs/operations.md` el retroceso asimétrico de la imagen (mantener la imagen nueva con código anterior, o restaurar la copia previa en la imagen antigua), el orden de fases del despliegue y los parámetros HNSW; ensayar el retroceso en la instancia aislada de T-11. Resultado: procedimiento verificado y escrito.
- **Changelog**: Nuevo procedimiento de retroceso de pgvector, ensayado, y documentación de la imagen de PostgreSQL, de MEMORY_VECTOR_INDEXES y de los parámetros HNSW.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real 0,08 (medido)
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-11
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`, `docs/architecture.md`, `docs/roadmap/2026-11-09-retrieval-quality/testing/rollback-rehearsal.json`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `docs/operations.md` contiene las secciones «Retroceso de pgvector» y «Imagen PostgreSQL», con comandos y la advertencia de la asimetría (R-01)
  - `python scripts/build-handbook.py --check` (si el script admite `--check`; si no, `python scripts/build-handbook.py`) → sin error y sin enlaces rotos

**Criterios de aceptación**
- [x] CA-14: el procedimiento de retroceso queda documentado en `docs/operations.md` y se ensayó en instancia aislada (evidencia en `testing/rollback-rehearsal.json`)
- [x] `docs/configuration.md` documenta `MEMORY_VECTOR_INDEXES` y los parámetros `hnsw.*`
- [x] `docs/architecture.md` describe pgvector, HNSW y la ruta exacta

**Subtareas**
- [x] Ensayar el retroceso (código anterior con imagen nueva; restauración en imagen antigua) en la instancia aislada
- [x] Escribir las secciones de `operations.md`, `configuration.md` y `architecture.md`

**Notas**: Procedencia: spec CA-14, CA-36, riesgo R-01. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c472cd5ffe0b`.
- **Verificación**: lectura de `docs/operations.md`: contiene `## Imagen PostgreSQL` y `## Retroceso de pgvector` con comandos y la advertencia. `scripts/build-handbook.py` no admite `--check` ni corre en el host (falta `markdown_it`): se ejecutó la misma etapa que usa la imagen web, `docker build --progress=plain --no-cache-filter handbook --target handbook -f memory_platform/Dockerfile.web .` → exit 0 y `Kairos handbook generated: 24 verified files.` (los enlaces nuevos `configuration.md#búsqueda-vectorial-pgvector` y `operations.md#imagen-postgresql` siguen la numeración de anclas de los demás).

- **Corrección intento 1 (T-12, gaps #8 y #15)**: #8: la evidencia de esta tarea estaba tras la cabecera de la Fase 4; movida a este bloque. #15: el coste de `SELECT e.*` del código anterior (arrastra `embedding` como texto, del orden de 2 veces más datos por fila) queda documentado en el retroceso de `docs/operations.md` como deuda aceptada. El ensayo de retroceso se repitió sobre el árbol corregido (ver T-11); `rollback-rehearsal.json` regenerado.

---

## Fase 4 — FTS por idioma + trigram (C-05 · P4)

**Estado**: completado · **Estimado**: 27h base (32.4h con margen) · **Real**: 2,18h IA (medido, ventanas únicas) · **Coste est.**: 1.620 € · **Tokens est.**: 1000k in / 90k out

### T-13 — Migración FTS: `unaccent`, `pg_trgm`, columnas es/en e índices

- **Descripción**: Versión de esquema aditiva: extensiones `unaccent` y `pg_trgm`, envoltorio `IMMUTABLE` de `unaccent`, columnas FTS es y en (generadas en `documents`; calculadas en la inserción y rellenadas en `memory_items` y en las tablas de agente/corpus con `search_vector`), índices GIN y trigram. Las columnas `search_vector` `simple` se conservan.
- **Changelog**: La base de memoria incorpora búsqueda por idioma (español e inglés, sin tildes) y trigramas mediante una migración aditiva que conserva todos los datos.
- **Estado**: completado
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,67h · real 2,18 (medido; 1,48 + 0,70 de la corrección intento 1, ventana única de T-13/T-14/T-16/T-17 fix1; ventana única que cubre toda la Fase 4, T-13…T-18 se trabajaron intercaladas)
- **Supervisión**: est. 0,17h (≈25 % IA) · real —
- **Previsión IA**: 185k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-12
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/tests/test_fts_migration.py`, `memory_platform/tests/test_pgvector_migration.py`, `docs/operations.md`, `docs/roadmap/2026-11-09-retrieval-quality/testing/fts-migration-cost.json`, `scripts/deploy-memory.py`, `memory_platform/tests/test_deploy_isolation.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_fts_migration`: test en rojo antes de la migración)
  - `grep -nEi "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → ninguna coincidencia en las versiones nuevas (CA-34)

**Criterios de aceptación**
- [x] CA-22: existen las columnas e índices nuevos, `search_vector` `simple` sigue presente y consultable, y tras migrar el recuento de filas con la columna FTS nueva nula es 0 en cada tabla afectada
- [x] CA-34: sin `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE`; `content_manifest().sha256` igual antes y después
- [x] El envoltorio de `unaccent` es `IMMUTABLE` y las columnas generadas se crean sin error (riesgo de la evaluación)

**Subtareas**
- [x] Test en rojo sobre fixture con datos previos
- [x] Escribir migración (extensiones, envoltorio, columnas, GIN, trigram)
- [x] Relleno de filas existentes y comprobación de nulos
- [x] Anotar el bloqueo por reescritura de tabla (R-06) y su `lock_timeout`

**Notas**: Procedencia: spec CA-22, CA-34, decisión P-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `814d4bdc4fe4`.

### T-14 — Consultas léxicas de `Store` con configuración es/en

- **Descripción**: Adaptar los puntos de consulta de `store_documents.py`/`store_graph.py` (antes `store.py:342`, `:437`, `:533-535`, `:572-579`, `:734`) y las dos inserciones para calcular las columnas nuevas; consulta = OR de las configuraciones es, en y simple, con rango = máximo. Resultado: «configuracion cancion» encuentra «configuración de las canciones» y «deploying fails» encuentra «deployment failed».
- **Changelog**: La búsqueda de notas, documentos y hechos encuentra resultados sin tildes y con otras formas de la palabra (canciones/canción, fails/failed) en español e inglés.
- **Estado**: completado
- **Tiempo humano**: est. 8h · real —
- **Tiempo IA (ejec.)**: est. 1,07h · real — (incluido en la ventana de T-13)
- **Supervisión**: est. 0,27h (≈25 % IA) · real —
- **Previsión IA**: 295k in / 25k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `memory_platform/store_documents.py`, `memory_platform/store_graph.py`, `memory_platform/store_ingest.py`, `memory_platform/store_common.py`, `memory_platform/tests/test_store.py`, `memory_platform/tests/test_native.py`, `memory_platform/tests/test_fts_language.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_fts_language` con CA-19 y CA-20 en rojo antes del cambio)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → los subconjuntos de idioma mejoran ≥ 15 puntos de recall@5 respecto de `baseline.json` en las capas léxicas

**Criterios de aceptación**
- [x] CA-19: «configuracion cancion» devuelve el documento con «configuración de las canciones» en el top-5 de la capa `documental`
- [x] CA-20: «deploying fails» devuelve la memoria «deployment failed» en el top-5 de la capa `episodic`
- [x] CA-23 (hechos nativos): `search_native_facts` usa la configuración nueva; test con consulta sin tilde que antes no encontraba el elemento
- [x] Las consultas existentes con la configuración `simple` siguen devolviendo lo mismo (suite verde)

**Subtareas**
- [x] Escribir tests en rojo (CA-19, CA-20, hechos nativos)
- [x] Calcular columnas en la inserción de `memory_items` y documentos
- [x] Reescribir consultas con OR de las tres configuraciones
- [x] Verificar sin regresión en `test_store.py` y `test_native.py`

**Notas**: Procedencia: spec CA-19, CA-20, CA-23, decisión P-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2ea8a303b05c`.

### T-15 — Búsquedas de corpus de agente y respuestas de corpus en es/en

- **Descripción**: Aplicar la configuración nueva a `agent_store.py` (3 consultas) y `corpus_answers.py` (1) con sus escrituras de columna. Resultado: cada punto de llamada encuentra elementos con consultas sin tilde que antes fallaban.
- **Changelog**: Las búsquedas de corpus de agente, observaciones y respuestas de corpus también ignoran tildes y reconocen formas derivadas en español e inglés.
- **Estado**: completado
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0,8h · real — (incluido en la ventana de T-13)
- **Supervisión**: est. 0,2h (≈25 % IA) · real —
- **Previsión IA**: 220k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `memory_platform/agent_store.py`, `memory_platform/corpus_answers.py`, `memory_platform/tests/test_agent_tools.py`, `memory_platform/tests/test_corpus_answers.py`, `memory_platform/tests/test_fts_language.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye un test en rojo por punto de llamada)

**Criterios de aceptación**
- [x] CA-23: un test por cada punto de llamada de `agent_store.py` (213, 329-331, 366) y `corpus_answers.py` (180-181) con una consulta sin tilde que antes no encontraba el elemento
- [x] Las búsquedas con la configuración `simple` anterior siguen devolviendo los mismos aciertos en los tests existentes

**Subtareas**
- [x] Un test en rojo por punto de llamada
- [x] Adaptar las cuatro consultas y las escrituras asociadas
- [x] Comprobar `test_agent_tools.py` y `test_corpus_answers.py` sin cambios en sus aserciones

**Notas**: Procedencia: spec CA-23, decisión P-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `38e8da7d1d3d`.

### T-16 — Filtros del portal con la configuración nueva (solo backend)

- **Descripción**: Adaptar los cinco filtros de texto de `portal_store.py` (líneas 42-79) a la configuración es/en/simple. No cambia ninguna interfaz de usuario: el cambio es solo de backend y de consulta, sin tocar `web/`.
- **Changelog**: Los filtros de texto del portal (sesiones, trabajos, historial, actividad y notas) ignoran tildes y reconocen formas derivadas, sin cambios en la interfaz.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real — (incluido en la ventana de T-13)
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `memory_platform/portal_store.py`, `memory_platform/tests/test_portal_collections.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye test en rojo con consulta sin tilde en un filtro del portal)

**Criterios de aceptación**
- [x] Cada uno de los cinco filtros de `portal_store.py` encuentra el elemento con consulta sin tilde/derivada (decisión P-03: el portal también pasa a la configuración nueva)
- [x] `test_portal_collections.py` pasa sin cambiar aserciones previas
- [x] Ningún fichero de la interfaz web modificado (`git diff --stat` solo en `memory_platform/`)

**Subtareas**
- [x] Test en rojo por filtro
- [x] Adaptar las consultas de `portal_store.py:42-79`

**Notas**: Procedencia: decisión P-03 (alcance del portal incluido; +3 h respecto de la evaluación base). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `19a482854272`.

### T-17 — Respaldo `pg_trgm` y fusión de rangos

- **Descripción**: Cuando el FTS devuelve menos de `limit`, completar con coincidencias por similitud `pg_trgm` sobre títulos e identificadores (`similarity_threshold` 0,3) y fusionar rangos sin duplicados. Resultado: «pg_advisroy_lock» encuentra una memoria con `pg_advisory_xact_lock`.
- **Changelog**: Si la búsqueda léxica devuelve pocos resultados, se completa con títulos parecidos (erratas e identificadores como ERR-4471), señalados como coincidencia aproximada.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real — (incluido en la ventana de T-13)
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-14
- **Tipo**: backend
- **Archivos**: `memory_platform/store_documents.py`, `memory_platform/store_graph.py`, `memory_platform/store_common.py`, `memory_platform/tests/test_fts_language.py`, `memory_platform/retrieval.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/models.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye CA-21 en rojo antes del cambio)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → el subconjunto de errores tipográficos/identificadores mejora ≥ 15 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [x] CA-21: buscar «pg_advisroy_lock» devuelve la memoria con `pg_advisory_xact_lock` en el top-5 por el respaldo trigram
- [x] El respaldo solo se ejecuta cuando el FTS devuelve menos de `limit`, sin duplicar aciertos
- [x] El umbral de similitud (0,3) se confirma o ajusta con la puerta `retrieval-eval` y queda registrado

**Subtareas**
- [x] Test en rojo (CA-21)
- [x] Implementar respaldo y fusión sin duplicados
- [x] Ajustar umbral con C-01 y anotar el valor final

**Notas**: Procedencia: spec CA-21, decisión P-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `130baddff2a5`.

### T-18 — Verificación integrada de FTS por idioma

- **Descripción**: Ejecutar la suite y la puerta de evaluación tras toda la fase 4 y registrar el avance frente a la línea base. Resultado: fase 4 cerrada con evidencia de que no hay regresión en ningún subconjunto.
- **Changelog**: Informe de calidad de la fase de búsqueda léxica: mejoran español y errores tipográficos en las capas léxicas sin empeorar ninguna capa.
- **Estado**: completado
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,27h · real — (incluido en la ventana de T-13)
- **Supervisión**: est. 0,07h (≈25 % IA) · real —
- **Previsión IA**: 75k in / 5k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-14, T-15, T-16, T-17
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-09-retrieval-quality/testing/phase4-eval.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0`
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → informe `phase4-eval.json`: ningún subconjunto empeora más de 2 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [x] CA-22/CA-23 comprobados en la suite completa (0 fallos, 0 omitidos)
- [x] La mejora del subconjunto idioma y errores es visible en el informe frente a la línea base

**Subtareas**
- [x] Ejecutar suite y puerta
- [x] Guardar el informe en `testing/`

**Notas**: Procedencia: spec CA-22, CA-23, CA-35 (parcial). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `4afb02026297`.

---

## Fase 5 — Troceado para embeddings (C-06 · P2)

**Estado**: completado · **Estimado**: 28h base (33.6h con margen) · **Real**: 1,43h IA (medido, ventana única) · **Coste est.**: 1.680 € · **Tokens est.**: 1100k in / 100k out

### T-19 — Troceador por párrafos/encabezados con solape

- **Descripción**: Crear `memory_platform/chunking.py`: función pura que divide `title + content` en fragmentos de ~1.500 caracteres con solape de 200 (`MEMORY_CHUNK_CHARS`, `MEMORY_CHUNK_OVERLAP`, máximo `MEMORY_CHUNK_MAX` = 200) respetando párrafos y encabezados, y devuelve `ordinal`, `char_start`, `char_end`. Resultado: cobertura total sin huecos, comprobada por test.
- **Changelog**: Los documentos y notas largos se dividen en fragmentos de unos 1.500 caracteres con solape de 200, respetando encabezados y párrafos, para poder indexar todo su texto.
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,57h · real 1,43 (medido, ventana única de la Fase 5: T-19…T-25 se trabajaron intercaladas)
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-18
- **Tipo**: backend
- **Archivos**: `memory_platform/chunking.py`, `memory_platform/config.py`, `memory_platform/tests/test_chunking.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunking` en rojo antes de crear el módulo)

**Criterios de aceptación**
- [x] CA-24 (parte pura): los intervalos `[char_start, char_end)` de un documento de 50.000 caracteres cubren todo el texto sin huecos y con el solape configurado, y los `ordinal` son consecutivos
- [x] Un documento de 200.000 caracteres produce ≤ 200 fragmentos
- [x] Texto corto (< tamaño de fragmento) produce un único fragmento

**Subtareas**
- [x] Tests en rojo (cobertura, solape, tope, texto corto)
- [x] Implementar el troceador
- [x] Añadir los tres parámetros a `config.py`

**Notas**: Procedencia: spec CA-24, decisión P-07 (1.500/200). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `842d11e48d73`.


RED: `test_chunking` falló con ModuleNotFoundError: No module named memory_platform.chunking (Ran 1 test, FAILED errors=1) · 2026-11-09.


RED: `test_a_run_of_blanks_never_becomes_a_fragment_and_the_coverage_stays_whole (mutante: sin el tramo en blanco)` falló con AssertionError: fragmento en blanco en 'T\nintro\n'+'\n'*4000+'fin' (1 failure) · 2026-11-09.

- **Corrección (intento 1)**: el «Resultado» anterior queda ampliado: ningún fragmento es nunca solo blancos (el tramo se une al anterior), ver la tabla del intento 1 fila 3.

### T-20 — Tabla `memory.embedding_chunks` e índice HNSW parcial

- **Descripción**: Migración aditiva de la tabla `memory.embedding_chunks` (`ordinal`, `char_start`, `char_end`, `vector`/`embedding`, modelo, hash e identidad del recurso) con HNSW parcial como en T-08, sin tocar la clave primaria de `memory.embeddings`.
- **Changelog**: La base de memoria incorpora una tabla de fragmentos con su propio índice vectorial mediante una migración aditiva que conserva todos los datos.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,43h · real — (incluido en la ventana de T-19)
- **Supervisión**: est. 0,11h (≈25 % IA) · real —
- **Previsión IA**: 120k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-19, T-08
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/tests/test_chunk_schema.py`, `memory_platform/store_vectors.py`, `memory_platform/tests/test_pgvector_migration.py`, `memory_platform/tests/test_fts_migration.py`, `docs/operations.md`, `docs/roadmap/2026-11-09-retrieval-quality/testing/chunk-cost.json`, `docs/roadmap/2026-11-09-retrieval-quality/testing/chunk-cost-measure.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunk_schema`)
  - `grep -nEi "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → ninguna coincidencia en las versiones nuevas (CA-34)

**Criterios de aceptación**
- [x] La tabla existe tras `admin migrate` con claves y borrado coherentes con `memory.embeddings`
- [x] CA-34: migración sin operaciones destructivas; `content_manifest().sha256` sin cambios
- [x] El índice HNSW parcial solo cubre el modelo y la dimensión configurados

**Subtareas**
- [x] Test de esquema en rojo
- [x] Escribir la migración
- [x] Comprobar migración idempotente

**Notas**: Procedencia: spec CA-24, CA-34, decisión «Troceado». Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `252956194e65`.


RED: `test_chunk_schema` falló con contra el schema.sql del commit base: Ran 6 tests, FAILED failures=4 errors=2 (sin version 10, sin tabla, sin indice) · 2026-11-09.

### T-21 — Worker y proveedor: embeddings por lotes dentro del plazo del job

- **Descripción**: Cambiar `worker.py:47-52` y `providers.py` para troceo + embebido por lotes (`/api/embed` con varias entradas) acotados al plazo del job (lease 120 s); un fallo en el fragmento k de n falla el job completo. Resultado: documentos de 200.000 caracteres caben en el plazo sin romper el semáforo de 1 petición.
- **Changelog**: El trabajador de embeddings procesa los textos largos por fragmentos y en lotes dentro del plazo del trabajo; si falla un fragmento, el trabajo completo falla o se reintenta.
- **Estado**: completado
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0,86h · real — (incluido en la ventana de T-19)
- **Supervisión**: est. 0,21h (≈25 % IA) · real —
- **Previsión IA**: 235k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-19
- **Tipo**: backend
- **Archivos**: `memory_platform/worker.py`, `memory_platform/providers.py`, `memory_platform/tests/test_worker.py`, `memory_platform/tests/test_providers.py`, `memory_platform/tests/test_jobs.py`, `memory_platform/config.py`, `memory_platform/tests/test_embed_many.py`, `memory_platform/tests/retrieval_eval/fake_embeddings.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye nuevos casos de lotes, plazo y fallo parcial en rojo antes del cambio)

**Criterios de aceptación**
- [x] CA-27 (parte worker): si el proveedor falla en el fragmento k de n, el job falla o reintenta según `max_attempts` y no se entrega ningún resultado parcial al almacén
- [x] El proveedor envía lotes acotados (tamaño y plazo por lote configurables) y respeta el semáforo existente
- [x] Los tests existentes de `test_worker.py`, `test_providers.py` y `test_jobs.py` pasan sin cambiar aserciones previas

**Subtareas**
- [x] Tests en rojo (lotes, plazo, fallo parcial)
- [x] Implementar `embed_many` en `providers.py`
- [x] Adaptar el worker al troceo y a los lotes

**Notas**: Procedencia: spec CA-27, riesgo R-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `55c1cf5760a4`.


RED: `test_worker+test_embed_many` falló con test_worker 17 tests FAILED failures=4 errors=3; test_embed_many 6 tests FAILED errors=6 (sin embed_many ni embed_receipt) · 2026-11-09.


RED: `test_the_job_deadline_grows_with_the_batches_up_to_the_global_ceiling + test_the_deadline_is_proportional_to_the_number_of_batches + test_a_single_fragment_cap_still_reports_the_truncation + test_long_text_..._delivered_whole (mutantes)` falló con AssertionError: plazo fijo de 120 s / aviso de truncado perdido con MEMORY_CHUNK_MAX=1 / vector del elemento = primer fragmento (failures=1, errors=1 por mutante) · 2026-11-09.

- **Corrección (intento 1)**: sustituye al «un solo plazo compartido» de arriba: plazo proporcional a los lotes (`MEMORY_EMBED_BATCH_TIMEOUT` × lotes, tope `MEMORY_EMBED_JOB_MAX_TIMEOUT`); el vector de elemento vuelve a ser el de `text[:8000]` (última entrada del último lote), no el del primer fragmento; `MEMORY_CHUNK_MAX=1` conserva el aviso de truncado (filas 5, 9 y 11).

### T-22 — `complete_job` transaccional con todos los fragmentos

- **Descripción**: Guardar en `complete_job` el vector del elemento (compatibilidad) y todos los fragmentos con su posición en una única transacción, con los recibos actuales. Resultado: nunca quedan fragmentos parciales de una versión.
- **Changelog**: Los fragmentos de un recurso se guardan junto con su vector en una sola transacción: nunca queda un conjunto parcial.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,43h · real — (incluido en la ventana de T-19)
- **Supervisión**: est. 0,11h (≈25 % IA) · real —
- **Previsión IA**: 120k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-20, T-21
- **Tipo**: backend
- **Archivos**: `memory_platform/store_jobs.py`, `memory_platform/store_vectors.py`, `memory_platform/tests/test_jobs.py`, `memory_platform/tests/test_chunk_jobs.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunk_jobs`: CA-27 en rojo antes del cambio)

**Criterios de aceptación**
- [x] CA-27: con fallo en el fragmento k de n no queda ningún fragmento de esa versión guardado y el job queda en reintento o fallido según `max_attempts`
- [x] La escritura de elemento y fragmentos es atómica (un único commit)
- [x] Los tests de `test_jobs.py` pasan sin cambios en sus aserciones

**Subtareas**
- [x] Test en rojo de atomicidad
- [x] Extender `complete_job` y los recibos
- [x] Prueba de reintento con `max_attempts`

**Notas**: Procedencia: spec CA-27, decisión «Fallo de proveedor a mitad del troceado». Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `3e8497137591`.


RED: `test_chunk_jobs` falló con Ran 10 tests, FAILED failures=7 errors=1 (complete_job no escribe fragmentos ni valida el recibo) · 2026-11-09.

### T-23 — Búsqueda agregada por elemento con `matched_chunk` y `excerpt`

- **Descripción**: Hacer que la capa semántica busque sobre fragmentos, agregue por elemento con la puntuación del mejor fragmento y devuelva el campo opcional `matched_chunk` (`ordinal`, `char_start`, `char_end`); `excerpt` usa el texto del fragmento ganador. Los aciertos sin fragmento omiten el campo y `ref` no cambia de formato. Resultado: un dato más allá de 8.000 caracteres se recupera.
- **Changelog**: La búsqueda semántica encuentra datos situados más allá de los primeros 8.000 caracteres de un documento y devuelve el campo opcional matched_chunk con el fragmento que coincide.
- **Estado**: completado
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,71h · real — (incluido en la ventana de T-19)
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-22, T-09
- **Tipo**: backend
- **Archivos**: `memory_platform/store_vectors.py`, `memory_platform/retrieval.py`, `memory_platform/models.py`, `memory_platform/tests/test_embeddings.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/tests/test_chunk_search.py`, `memory_platform/tests/retrieval_eval/run.py`, `memory_platform/tests/retrieval_eval/README.md`, `docs/operations.md`, `docs/roadmap/2026-11-09-retrieval-quality/testing/phase5-eval.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunk_search`: CA-24/25/26 en rojo antes del cambio)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → el subconjunto documento largo mejora ≥ 15 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [x] CA-24: documento de 50.000 caracteres con frase única hacia el carácter 40.000 → su búsqueda semántica lo devuelve en el top-3 con el `matched_chunk.ordinal` del fragmento que la contiene
- [x] CA-25: un elemento aparece una sola vez aunque coincidan varios fragmentos, con la puntuación del mejor
- [x] CA-26: tras publicar una versión nueva no se devuelven fragmentos de la anterior
- [x] Los aciertos sin fragmento omiten `matched_chunk`

**Subtareas**
- [x] Tests en rojo con documento largo (dato más allá de 8.000 caracteres)
- [x] Agregar por elemento en SQL
- [x] Añadir `matched_chunk` opcional a `Hit` y al ensamblado
- [x] Usar el texto del fragmento en `excerpt`

**Notas**: Procedencia: spec CA-24…CA-26, decisión «Señal del fragmento». Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0899ea9f22ac`.


RED: `test_chunk_search` falló con Ran 10 tests, FAILED failures=3 errors=6 (sin rank_chunks_* ni matched_chunk) · 2026-11-09.


RED: `test_once_everything_is_chunked_the_item_route_never_runs_and_no_fallback_is_paid + test_the_two_routes_share_one_exact_fallback_allowance + test_an_element_found_by_both_routes_appears_once_with_its_best_score + test_matched_chunk_only_when_the_fragment_is_not_the_whole_text... (mutantes)` falló con AssertionError: item_route.call_count 1 != 0 / fallback de la segunda ruta ejecutado / elemento duplicado / matched_chunk siempre presente (1 failure por mutante) · 2026-11-09.

- **Corrección (intento 1)**: la ruta por elemento solo corre si queda un recurso vigente sin fragmentos (`embeddings.chunked`), las rutas comparten un único cupo de respaldo exacto y se deduplican por elemento; el tope exacto de fragmentos es 10 × `EXACT_CANDIDATE_LIMIT` (sustituye a «10.000 fragmentos»); `matched_chunk` solo si no es todo el texto (filas 1, 7, 8 y 12).

### T-24 — Relleno idempotente de fragmentos y su integración en `deploy-memory.py`

- **Descripción**: Añadir `admin backfill-chunks`, que encola jobs `embed` solo para recursos vigentes sin fragmentos (segunda ejecución encola 0), y llamarlo desde `scripts/deploy-memory.py` tras `migrate` (decisión P-07), con progreso visible. Además cubre el relleno de vectores `embedding` si T-08 dejó filas pendientes.
- **Changelog**: El comando admin backfill-chunks, que el despliegue ejecuta tras migrar, prepara los fragmentos del contenido existente de forma repetible y sin bloquear tablas.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,43h · real — (incluido en la ventana de T-19)
- **Supervisión**: est. 0,11h (≈25 % IA) · real —
- **Previsión IA**: 120k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-22
- **Tipo**: devops
- **Archivos**: `memory_platform/admin.py`, `scripts/deploy-memory.py`, `memory_platform/tests/test_admin.py`, `memory_platform/tests/test_deploy.py`, `memory_platform/tests/test_deploy_isolation.py`, `docs/operations.md`, `memory_platform/tests/retrieval_eval/stale_measure.py`, `memory_platform/tests/retrieval_eval/stale-cost.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye test de idempotencia y un caso de `test_deploy.py` que verifica la llamada en la fase correspondiente)

**Criterios de aceptación**
- [x] CA-28: el relleno encola jobs `embed` solo para recursos vigentes sin fragmentos; ejecutarlo dos veces encola 0 la segunda
- [x] `deploy-memory.py` ejecuta el relleno tras `migrate` y registra su resultado en el informe de despliegue (sin secretos)
- [x] El modo de simulación (`--apply` ausente) solo imprime el plan e incluye el relleno

**Subtareas**
- [x] Test en rojo de idempotencia
- [x] Implementar el subcomando de `admin`
- [x] Integrar en la fase `bootstrap`/`migrate` de `deploy-memory.py` y actualizar `PHASES`/informe si procede

**Notas**: Procedencia: spec CA-28, decisión P-07. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ed9c46e2af4f`.


RED: `test_admin+test_deploy` falló con test_admin ImportError cannot import name backfill_chunks (FAILED errors=1); test_deploy contra el script del commit base Ran 11 tests FAILED failures=1 errors=3 · 2026-11-09.


RED: `test_live_writes_are_claimed_before_older_backfill_jobs + test_services_are_left_running_during_migrate_by_default + test_a_resource_that_is_one_fragment_with_its_item_vector_needs_no_provider_call + test_a_failed_job_is_queued_again... (mutantes)` falló con AssertionError: el trabajo del relleno se reclama antes que la escritura en vivo / el worker anterior no se detiene antes del relleno / recurso corto encolado / failed reencolado (failures=1-2 por mutante) · 2026-11-09.

- **Corrección (intento 1)**: el relleno va con prioridad 1, no reencola `failed` (`--retry-failed`), completa sin proveedor los recursos de un fragmento (`derived`) y el despliegue detiene `memory-worker` antes de encolarlo (filas 2, 4, 6 y 10).

### T-25 — Contrato aditivo `matched_chunk` y pruebas de contrato

- **Descripción**: Reflejar `matched_chunk` como campo opcional en `docs/contracts/kairos-mcp.json` y OpenAPI mediante `scripts/export-contracts.py` y comprobar con un diff aditivo que las 34 herramientas MCP siguen intactas.
- **Changelog**: El contrato exportado documenta el campo opcional matched_chunk de los resultados de búsqueda; las 34 herramientas MCP no cambian.
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,57h · real — (incluido en la ventana de T-19)
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-09
- **Dependencias**: T-23
- **Tipo**: backend
- **Archivos**: `scripts/export-contracts.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/tests/test_mcp.py`, `memory_platform/tests/test_contract_additive.py`, `memory_platform/Dockerfile`, `memory_platform/tests/contracts_base/kairos-mcp.json`, `memory_platform/tests/contracts_base/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_contract_additive`)
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → solo adiciones (el test confirma 0 eliminadas/cambiadas) y `python -c "import json;print(len(json.load(open('docs/contracts/kairos-mcp.json'))['tools']))"` → `34` (clave del contrato a confirmar al implementar)

**Criterios de aceptación**
- [x] CA-29: `matched_chunk` aparece como opcional en el contrato exportado y los aciertos sin fragmento lo omiten
- [x] CA-33: sigue habiendo 34 herramientas y el diff solo contiene adiciones (0 herramientas, campos o valores por defecto eliminados o cambiados)

**Subtareas**
- [x] Test aditivo (compara contra el contrato del commit base)
- [x] Regenerar contratos
- [x] Ajustar `test_mcp.py` si procede sin cambiar aserciones previas

**Notas**: Procedencia: spec CA-29, CA-33, riesgo R-09. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c7d776279990`.

---


RED: `test_contract_additive` falló con Ran 7 tests, FAILED errors=1: KeyError result_schemas (el contrato exportado no incluye el resultado de busqueda) · 2026-11-09.

## Fase 6 — Híbrida con degradación y CLI (C-04 · P3)

**Estado**: completado · **Estimado**: 12h base (14.4h con margen) · **Real**: — · **Coste est.**: 719 € · **Tokens est.**: 430k in / 40k out

### T-26 — Degradación probada y campo opcional `degraded`

- **Descripción**: Fijar con tests la degradación (proveedor 503/plazo/sin vectores/`semantic=false`) por HTTP y MCP para `search` y `context`, y añadir el campo opcional `degraded` en `backends`/respuesta cuando solo falla la capa semántica (se mantiene `partial` con su semántica actual). Resultado: la respuesta léxica es siempre válida y el cliente distingue una degradación de un fallo.
- **Changelog**: La búsqueda y el contexto indican con el campo opcional «degraded» cuándo solo falló la capa semántica y siguen devolviendo los resultados léxicos.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real — (no medido: T-26…T-29 se trabajaron intercaladas en una sola ejecución, sin ventana de usage-meter)
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-25
- **Tipo**: backend
- **Archivos**: `memory_platform/retrieval.py`, `memory_platform/models.py`, `memory_platform/mcp.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_mcp.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/tests/test_contract_additive.py`, `docs/integration.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye CA-15, CA-16, CA-17 y el caso `degraded` en rojo antes del cambio)
  - Evidencia (árbol final, 2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 398}` (incluye `DegradationTests`, `DegradedSemanticHttpTests`, `DegradedSemanticToolTests` y `test_contract_additive`); `git diff docs/contracts | grep -c "^-[^-]"` → `0`.

**Criterios de aceptación**
- [x] CA-15: sin `semantic` y con vectores, `backends.semantic.status = 'ok'` y hay al menos un acierto solo semántico fusionado con los léxicos
- [x] CA-16: con el proveedor devolviendo 503 o excediendo el plazo, `search` y `context` (HTTP y MCP) responden con léxicos, `backends.semantic.status = 'unavailable'`, `degraded` presente y tiempo ≤ `embedding_query_timeout` + 1 s
- [x] CA-17: con `semantic=false`, `status = 'off'` y 0 llamadas al proveedor
- [x] CA-33: `degraded` es opcional y el contrato solo gana el campo

**Subtareas**
- [x] Tests en rojo de degradación y `degraded`
- [x] Implementar el campo sin alterar `partial`
- [x] Regenerar contrato con `scripts/export-contracts.py`

**Notas**: Procedencia: spec CA-15…CA-17, decisión P-04. Clase: cambio (test en rojo de degradación y campo `degraded`). Hallazgo de la evaluación: `semantic` ya es `True` por defecto (`models.py:146`, `:181`; `mcp.py:150`, `:160`), por eso la tarea es de endurecimiento. Patrón: estados `partial`/`unavailable`/`off` en `retrieval.py:113`, `:129`, `:146`. Resultado (2026-11-11): `degraded` = `{layer: "semantic", reason}` con `reason` ∈ timeout, provider_error (status `unavailable`, `partial` true), no_vectors y embeddings_disabled (status `off`); solo se informa cuando ninguna otra capa falla (si fallan otras, quedan visibles en `backends`/`partial`). `partial` conserva su semántica. `backends.semantic.reason` repite el motivo. `mcp.py` no cambió (las herramientas devuelven el dict de `Retrieval`); el contrato (`Degraded` y el campo opcional en `SearchResult`) se regeneró con `scripts/export-contracts.py` desde la imagen de test (python 3.11) conservando el texto de los docstrings del commit base: `git diff --stat docs/contracts` = 80 inserciones, 0 supresiones; 34 herramientas. Aviso de CA-15: el criterio ya se cumplía (`semantic` es `true` por defecto); el test lo fija. **Corrección tras revisión (intento 2, gaps 2 y 6, fix1)**: gap 6 verificado (`retrieval.py` clasificaba todo como `provider_error`): ahora el plazo (`TimeoutError` o `MemoryError('semantic_deadline_exceeded')`) es `timeout`, un fallo del proveedor de embeddings `provider_error` y cualquier otro (base de datos en `has_vectors` o en el escaneo) un motivo nuevo `store_error`, añadido de forma aditiva al enum de `Degraded` (`models.py`), a los contratos y a `docs/integration.md`; test por motivo (`test_each_failure_of_the_semantic_layer_has_its_own_reason`: 5 casos). Gap 2 (parte servidor): campo OPCIONAL `semantic_budget_ms` (entero 1..600000, `models.Search`/`models.Context`, REST y MCP `search`/`context`); la capa semántica usa min(`MEMORY_EMBED_QUERY_TIMEOUT`, presupuesto) —nunca lo amplía— y al agotarse devuelve los léxicos con `degraded {layer:"semantic", reason:"timeout"}` (el `asyncio.timeout` cancela también el embed en curso, así que la consulta abortada ya no ocupa al proveedor). Tests: `test_retrieval` (presupuesto respetado ≤ presupuesto + 0,5 s con 5 s configurados; un presupuesto superior al configurado no lo extiende; presupuesto cumplido sin `degraded`; rango 0/-5/600001 rechazado), `test_api` (422 para 0, -1, 600001 y texto; 200 con `degraded` timeout en `search` y `context`), `test_mcp` (las herramientas `search` y `context` aceptan el campo; fuera de rango es error). Contratos regenerados con el exportador de Python 3.11 y fusionados conservando el texto base (solo `semantic_budget_ms` en `search`/`context` y `store_error` en el enum: 34 herramientas, `test_contract_additive` en verde; ese test pasa de `assertEqual(before, after)` a `additive_violations` más «la única entrada nueva es `semantic_budget_ms`, opcional»). Desviación: `test_contract_additive.py` y `docs/integration.md` se tocan aquí aunque no estaban en `Archivos`; se añaden. Medición: usage-meter `retrieval-quality/T-26-fix1` … `T-29-fix1` (una ventana compartida por las cuatro, 8 min de reloj; 0,08 h IA (medido), imputadas una sola vez aquí). **Corrección tras revisión (ronda 2, fix2, gaps N1, N3, N4)**: N1 verificado (`additive_violations` aceptaba claves nuevas que restringen la entrada): `test_contract_additive.py` compara ahora cada herramienta con igualdad EXACTA frente a la base (`tool_differences`: clave añadida, quitada o cambiada es diferencia); solo `search` y `context` difieren legítimamente (ya comprobado: las otras 32 son idénticas a 68ca247), y en ellas se quita únicamente la propiedad `semantic_budget_ms` y se compara igual de exacto; además `semantic_budget_ms` no está en `required` y es la única propiedad nueva. Test nuevo `test_the_exact_check_rejects_a_restricting_key_anywhere_in_a_tool`: `maximum`, `additionalProperties:false`, `minLength` y `dependentRequired` hacen fallar la comprobación. `additive_violations` se conserva solo para `result_schemas` y OpenAPI, donde crecer es legítimo. N3 verificado (`retrieval.py:135`): `has_vectors` corre ahora dentro del mismo `asyncio.timeout(budget)` (el presupuesto se calcula antes) y el motivo es `timeout`; test `test_the_budget_covers_the_vector_existence_check_too` (has_vectors de 1 s, presupuesto 150 ms, respuesta en ≤ 0,65 s con `degraded` timeout y sin llamar al proveedor). N4 verificado (`models.py:147,197` aceptaba `true` y `"1100"`): `Field(strict=True)` en `models.Search`/`models.Context` y en la firma de las herramientas MCP `search`/`context` (`mcp.py`), porque FastMCP convertía en modo laxo antes de llegar al modelo; el esquema exportado NO cambia (comprobado: `semantic_budget_ms` idéntico al de `docs/contracts` en MCP y OpenAPI, 34 herramientas, contratos sin regenerar). Tests de rechazo de bool, cadena y decimal en `test_retrieval`, `test_api` (422) y `test_mcp`. Evidencia posterior a las correcciones (2026-11-11, fix2): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 412}` (`docker build --target test ... -t kairos-test:rq6`, exit 0); puerta `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq6 python -m memory_platform.tests.run_postgres` exit 0, `gate.passed: true`, `failures: []` (CA-18 y CA-35 comprobados por la puerta), `fused` recall@5 1,0, MRR 0,971528 (mejor capa individual `semantic` 0,964583, CA-18 cumplido), CA-35 sin regresiones. Medición: usage-meter no disponible en esta ejecución, tiempo `(estimado)`.


RED: `memory_platform/tests/test_retrieval.py::DegradationTests (7 casos), test_api::DegradedSemanticHttpTests, test_mcp::DegradedSemanticToolTests` falló con MEMORY_TEST_RESULT tests=387 failures=1 errors=6 passed=false: KeyError 'degraded' en 5 casos y falta el campo degraded en el contrato exportado · 2026-11-11.

### T-27 — Ajuste de la fusión RRF con la puerta de evaluación

- **Descripción**: Con los datos de la puerta `retrieval-eval` tras las fases 3-5, comprobar y, si lo justifica la medida, ajustar `k=60` y los pesos por capa en `retrieval.py`. Resultado: el MRR de `fused` ≥ el de la mejor capa individual, en conjunto y por subconjunto.
- **Changelog**: En la búsqueda combinada «validado» es una bonificación ajustable (MEMORY_FUSION_VALIDATED_BONUS) y no un orden absoluto; la calidad mejora en todos los subconjuntos.
- **Estado**: completado
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real — (no medido: T-26…T-29 se trabajaron intercaladas en una sola ejecución, sin ventana de usage-meter)
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-26, T-03
- **Tipo**: backend
- **Archivos**: `memory_platform/retrieval.py`, `memory_platform/tests/retrieval_eval/thresholds.json`, `memory_platform/config.py`, `memory_platform/tests/retrieval_eval/run.py`, `memory_platform/tests/retrieval_eval/test_metrics.py`, `memory_platform/tests/run_postgres.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/tests/retrieval_eval/fusion-tuning.json`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → pasa los umbrales (`fused` recall@5 ≥ 0,80, MRR ≥ 0,60) y el MRR de `fused` ≥ mejor capa individual
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0`
  - Evidencia (árbol final, 2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 398}`; puerta `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq6 python -m memory_platform.tests.run_postgres` → exit 0, `gate.passed: true`, `failures: []`, `fused` recall@5 1.0 · MRR 0.971528 (en 1.0/1.0, es 1.0/1.0, long 1.0/0.829, typo_id 1.0/1.0); semantic MRR 0.964583; antes de la bonificación (orden absoluto) el mismo comando salía con exit 1 y `regression:en` −4,17, `regression:typo_id` −16,67.

**Criterios de aceptación**
- [x] CA-18: en `retrieval-eval` el MRR de `fused` es ≥ el de la mejor capa individual, en conjunto y por subconjunto
- [x] Cualquier cambio de `k` o pesos queda justificado en `testing/fusion-tuning.json` con el antes y el después
- [x] Sin cambios de la fusión si la medida no los justifica (se registra igualmente)

**Subtareas**
- [x] Ejecutar la puerta y analizar capas
- [x] Probar variantes de fusión solo si hay evidencia
- [x] Registrar resultado en `testing/`

**Notas**: Procedencia: spec CA-18, decisión P-06. Clase: cambio (test en rojo en la puerta si la fusión empeora). Patrón: fusión RRF `k=60` en `retrieval.py:97-146`. Decisión del usuario (2026-11-10): «validado» deja de ser un orden absoluto en la búsqueda combinada (`memory_platform/retrieval.py`, clave `(validado, RRF)`) y pasa a ser una **bonificación ajustable** en la puntuación; T-27 ajusta esa bonificación (además de `k=60` y los pesos por capa) con el conjunto de evaluación hasta cumplir los umbrales (`fused` recall@5 ≥ 0,80, MRR ≥ 0,60, ganancias de subconjuntos) y CA-35 (ningún subconjunto empeora más de 2 puntos de recall@5 frente a `baseline.json`). Resultado: bonificación `0.0001` en `Settings` (`MEMORY_FUSION_VALIDATED_BONUS`, validada al arrancar, 0 a 1; también `MEMORY_FUSION_K` y `MEMORY_FUSION_WEIGHTS`), `k=60` y pesos 1 sin cambios; recall@5 1,0 y MRR 0,9715 (línea base 0,50 y 0,34; fase 5: 0,54 y 0,40), subconjuntos en recall@5 todos 1,0 (cambio frente a la línea base: en +37,5, es +66,7, long +50, typo_id +41,7 puntos; frente a `phase5-eval.json`: en +41,7, es +66,7, long 0, typo_id +58,3), MRR de `fused` ≥ mejor capa individual en conjunto (0,9715 ≥ 0,9646 de `semantic`) y por subconjunto (CA-18). Rejilla (15 bonificaciones × k=60; 4 bonificaciones × k 20/60/100 × 3 juegos de pesos) y motivo en `memory_platform/tests/retrieval_eval/fusion-tuning.json`: el intervalo que cumple todo es 0 < bonificación ≤ 0,0002 (0,0001 y 0,0002 miden igual; se toma el centro, no el borde); de 0,0003 a 0,0005 falla CA-18 (MRR 0,9519); la meseta 0,003-0,01 (recall@5 0,847, MRR 0,820) cumple umbrales y CA-35 pero no CA-18; desde 0,02 reproduce el orden absoluto anterior y la puerta falla (recall@5 0,5417). La puerta de `run.py` comprueba ahora CA-35 (`max_subset_regression_points: 2` en `thresholds.json`; sin esa clave, o sin un subconjunto de la línea base, falla como `threshold_missing`/`subset_missing`, nunca pasa en silencio); umbrales y dataset sin cambios. Desviaciones: (1) `fusion-tuning.json` no está en `testing/` porque un hook reserva `docs/roadmap/**/testing/` a qa y bloqueó la escritura; vive junto a la puerta y puede moverse sin cambios; (2) se declaran además `config.py`, `run.py`, `test_metrics.py`, `run_postgres.py` (modo `MEMORY_FUSION_GRID` para medir la rejilla), `test_retrieval.py` y `docs/configuration.md`; (3) el Compose por defecto no declara las variables nuevas (usa los valores predeterminados). **Corrección tras revisión (intento 2, gaps 3, 4 y 5, fix1)**: gap 3 verificado (`evaluate_gate` no comprobaba CA-18): ahora falla como `ca18:overall` y `ca18:<subconjunto>` si el MRR de `fused` es menor que el de la mejor capa individual (episodic, documental, semantic; solo cuentan las capas que traen ese subconjunto), y como `ca18_layers_missing` si el informe no trae capas individuales (nunca pasa en silencio); las capas ya estaban en el informe. Test `test_ca18_fused_mrr_must_not_fall_below_the_best_single_layer_overall_or_in_any_subset` (igualdad pasa, global, subconjunto con la mejor capa léxica, capas ausentes); los fixtures de los otros tests añaden una capa individual. Evaluación fuera de línea tras el cambio: `gate.passed: true`, sin `failures` (CA-18 y CA-35 incluidos), recall@5 1,0 y MRR 0,9715 (mejor capa individual `semantic` 0,9646). Gap 4 verificado: `config.py:152-153` y `Archivos` apuntaban a `testing/fusion-tuning.json`; ahora citan `memory_platform/tests/retrieval_eval/fusion-tuning.json` (fichero sin mover). Gap 5 verificado: `docs/configuration.md` precisa que `MEMORY_FUSION_VALIDATED_BONUS` equivale a un orden absoluto solo cuando supera la mayor puntuación RRF posible (suma de pesos de capas / k: 0,0667 con k 60 y cuatro capas de peso 1; en el conjunto de evaluación ya desde 0,02), y que con otros k o pesos cambia. Medición: usage-meter `retrieval-quality/T-26-fix1` … `T-29-fix1` (una ventana compartida por las cuatro, 8 min de reloj; 0,08 h IA (medido), imputadas una sola vez aquí). **Corrección tras revisión (ronda 2, fix2, gap N2)**: sin cambios de código en esta tarea. Evidencia posterior a las correcciones (2026-11-11, fix2): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 412}` (`docker build --target test ... -t kairos-test:rq6`, exit 0); puerta `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq6 python -m memory_platform.tests.run_postgres` exit 0, `gate.passed: true`, `failures: []` (CA-18 y CA-35 comprobados por la puerta), `fused` recall@5 1,0, MRR 0,971528 (mejor capa individual `semantic` 0,964583, CA-18 cumplido), CA-35 sin regresiones (CA-18 repetido tras añadirlo a la puerta).


RED: `retrieval-eval (run_postgres con MEMORY_RETRIEVAL_EVAL=1) con la fusion actual y la comprobacion CA-35` falló con gate passed=false: fused recall@5 0.5417 y MRR 0.4031 bajo umbral, subset:es y typo_id sin ganancia, regression:en -4.17 y regression:typo_id -16.67 puntos · 2026-11-11.

### T-28 — Documentar `backends`, `degraded` y la semántica de `candidates_truncated`

- **Descripción**: Describir en `docs/architecture.md` e `docs/integration.md` los estados de `backends.semantic`, el campo `degraded`, `matched_chunk` y la nueva semántica de `candidates_truncated` (tope de candidatos en ruta exacta o `max_scan_tuples` en ANN).
- **Changelog**: Los manuales explican los estados de la búsqueda, degraded, matched_chunk y candidates_truncated; los documentos largos se reindexan con otro tamaño de vector y la búsqueda semántica es más rápida.
- **Estado**: completado
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,27h · real — (no medido: T-26…T-29 se trabajaron intercaladas en una sola ejecución, sin ventana de usage-meter)
- **Supervisión**: est. 0,07h (≈25 % IA) · real —
- **Previsión IA**: 70k in / 5k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-26
- **Tipo**: docs
- **Archivos**: `memory_platform/store_jobs.py`, `docs/architecture.md`, `docs/integration.md`, `docs/en/architecture.md`, `memory_platform/worker.py`, `memory_platform/store_vectors.py`, `memory_platform/tests/test_worker.py`, `memory_platform/tests/test_vector_search_paths.py`, `memory_platform/tests/measure_vector_candidates.py`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: ambos manuales describen `status` ∈ {ok, partial, unavailable, off}, `degraded`, `matched_chunk` y `candidates_truncated` con los valores del contrato
  - `python scripts/build-handbook.py` → sin errores
  - Evidencia (árbol final, 2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 398}`; `python scripts/build-handbook.py --output /tmp/handbook` (contenedor `python:3.12-slim` + `markdown-it-py`, montado en solo lectura) → `Kairos handbook generated: 24 verified files.` exit 0; `docs/integration.md` y `docs/architecture.md` describen `status` ∈ {ok, partial, unavailable, off}, `degraded`, `matched_chunk`, `candidates_truncated` y `semantic: true` del CLI 0.3.0.

**Criterios de aceptación**
- [x] Los manuales coinciden con el contrato regenerado (CA-36)
- [x] Se documenta que el CLI usa `semantic: true` desde la versión nueva

**Subtareas**
- [x] Redactar secciones
- [x] Regenerar el manual

**Notas**: Procedencia: spec CA-36, decisión «candidates_truncated». Clase: documentación. Se comprueba si existe `docs/en/` antes de editarlo; si no existe, se omite sin crearlo. Alcance ampliado por el plan director (2026-11-10), con TDD en rojo (4 casos): (a) deuda de la Fase 5: si el vector de elemento reutilizado (`stored_item_vector`) no tiene las dimensiones de los fragmentos, `embed_receipt` (`worker.py`) vuelve a embeber el texto completo (verificado como el resto) en vez de producir un recibo que el almacén rechaza para siempre; `store_jobs.py` no cambió (la comprobación necesita las dimensiones de los fragmentos recién embebidos, que solo se conocen en el worker); (b) B-09: `has_vectors` es un `SELECT EXISTS` sobre `memory.embeddings` con la misma noción de recurso vigente, y la lectura final de `_vector_candidates` filtra por los identificadores ganadores (`i.id=ANY`, `d.id=ANY`) antes de `to_jsonb`; firmas intactas (`store_surface.json` sin diff). Medida (`python -m memory_platform.tests.measure_vector_candidates` con `MEASURE_B09=1`, 10.000 documentos + 10.000 notas embebidos, 15 repeticiones, mediana): `has_vectors` 793,75 ms → 31,33 ms (25,3×); lectura final de 10 ganadores 974,14 ms → 6,64 ms (146,7×); mismas respuestas y mismas filas. Documentación: `docs/architecture.md`, `docs/integration.md` (sección «Estado de cada capa») y `docs/configuration.md` (fusión); `docs/en/` no existe y no se crea. Desviaciones: el script de medida vive en `memory_platform/tests/` y no en `testing/` (hook de qa); `docs/configuration.md` se declara en T-27. **Corrección tras revisión (intento 2, gap 7, fix1)**: verificado (`worker.py:49` re-embebía el texto completo en un `embed_many` aparte que el plazo no contaba). Ahora el texto completo viaja SIEMPRE en el MISMO `embed_many` que los fragmentos (`embed_plan` ya contaba esa entrada: `inputs = fragmentos + 1`, así que el plazo del trabajo `embedding_job_timeout(inputs)` la cubre) y se comprueba `len(vectors) == inputs`. El vector de elemento ya guardado (`stored_item_vector`) se conserva solo si tiene las dimensiones del vector recién calculado; si no, se entrega el nuevo. Coste asumido: se pierde el ahorro de no re-embeber el texto completo en el backfill de fragmentos (una entrada más por trabajo, dentro del mismo lote y plazo) a cambio de una sola llamada acotada. Tests (`test_worker`): una sola llamada con la entrada extra y vector del almacén con otras dimensiones sustituido; el mismo caso sin verificar falla `embedding_unverified`; el vector del mismo tamaño se conserva con una llamada; el plazo se calcula con exactamente las entradas de la llamada. Medición: usage-meter `retrieval-quality/T-26-fix1` … `T-29-fix1` (una ventana compartida por las cuatro, 8 min de reloj; 0,08 h IA (medido), imputadas una sola vez aquí). **Corrección tras revisión (ronda 2, fix2, gap N5; sustituye a la solución de fix1 para el vector guardado)**: verificado (`worker.py:43` re-embebía siempre el texto completo, ~1,9× de trabajo de Ollama en textos cortos). Ahora `embed_receipt` reutiliza el vector guardado cuando existe (solo se envían los fragmentos); sin vector guardado, el texto completo viaja al final del MISMO `embed_many`; si el vector guardado tiene otras dimensiones que los fragmentos, hace una llamada extra `provider.embed(texto)` (verificada como el resto: un `verified:false` falla `embedding_unverified`; dimensiones distintas, `embedding_invalid`). El plazo del trabajo (`worker_deadline`, nuevo, usado en `run_once`) planifica n+1 entradas (`embed_plan` sigue devolviendo fragmentos+1) MÁS la llamada de un solo texto (`embedding_job_timeout(settings, 1)`) más el margen, así que cubre siempre el caso peor. `stored_item_vector` (`store_jobs.py`, se añade a `Archivos`; solo cambia el docstring) ya describe que el vector se conserva salvo dimensiones distintas. Tests (`test_worker`): vector del mismo tamaño → solo fragmentos y vector reutilizado; sin vector → un lote con el texto al final; dimensiones distintas → una llamada extra tras los fragmentos; la llamada extra cabe en el plazo (0,4 s totales con 0,25 s para n+1 entradas); extra sin verificar falla; el plazo planifica n+1 más la llamada extra. Evidencia posterior a las correcciones (2026-11-11, fix2): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 412}` (`docker build --target test ... -t kairos-test:rq6`, exit 0); puerta `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq6 python -m memory_platform.tests.run_postgres` exit 0, `gate.passed: true`, `failures: []` (CA-18 y CA-35 comprobados por la puerta), `fused` recall@5 1,0, MRR 0,971528 (mejor capa individual `semantic` 0,964583, CA-18 cumplido), CA-35 sin regresiones. Medición: usage-meter no disponible en esta ejecución, tiempo `(estimado)`.


RED: `test_worker::ChunkedEmbeddingWorkerTests (2 casos) y test_vector_search_paths::VectorSearchPathTests (2 casos has_vectors/identidades)` falló con MEMORY_TEST_RESULT failures=4 passed=false: AssertionError, sin re-embeber con dimensiones distintas y has_vectors/fetch aun usan to_jsonb sin filtro de identidades · 2026-11-11.

### T-29 — CLI: `semantic: true` en el contexto automático y versión sin publicar

- **Descripción**: Cambiar `packages/kairos-cli/lib/dispatcher.mjs:84` a `semantic: true`, tolerar el campo `degraded` en la respuesta, actualizar tests y subir la versión del paquete (0.3.0) en `package.json` con su entrada de changelog. NO publicar en npm (cuenta del publicador bloqueada, F-06 abierta).
- **Changelog**: El contexto automático del CLI usa también la búsqueda semántica (con plazo propio y aviso «degraded» si no llega a tiempo); versión 0.3.0 preparada, sin publicar.
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,53h · real — (no medido: T-26…T-29 se trabajaron intercaladas en una sola ejecución, sin ventana de usage-meter)
- **Supervisión**: est. 0,13h (≈25 % IA) · real —
- **Previsión IA**: 145k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-26
- **Tipo**: frontend
- **Archivos**: `packages/kairos-cli/lib/dispatcher.mjs`, `packages/kairos-cli/package.json`, `packages/kairos-cli/tests/dispatcher.test.mjs`, `packages/kairos-cli/tests/lifecycle.test.mjs`, `packages/kairos-cli/README.md`, `docs/release-cli.md`, `packages/kairos-cli/lib/config.mjs`, `docs/install.md`, `docs/code-analysis.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `node --test packages/kairos-cli/tests/dispatcher.test.mjs` → todos pasan, incluido el caso `semantic: true` en el contexto automático y el manejo de `degraded`
  - `grep -n "semantic: true" packages/kairos-cli/lib/dispatcher.mjs && grep -n "\"version\"" packages/kairos-cli/package.json` → ocurrencia en la línea del contexto automático y versión nueva
  - `git status --short packages/kairos-cli` → solo cambios de código/versión; ningún `npm publish` ejecutado (lectura: historial de comandos del cierre)
  - Evidencia (árbol final, 2026-11-11): `node --test tests/dispatcher.test.mjs` → `tests 12 · pass 12 · fail 0` (incluye `semantic: true` y los dos casos de `degraded`); las siete suites de `npm test` (`install, mcp, capture, dispatcher, lifecycle, code-analysis, artifact`) → `tests 90 · pass 90 · fail 0 · skipped 0`; `grep -n "semantic: true" packages/kairos-cli/lib/dispatcher.mjs` → línea 87; `"version": "0.3.0"` (package.json línea 3); `git status --short packages/kairos-cli` solo ficheros de código/versión/README; ningún `npm publish` ejecutado.

**Criterios de aceptación**
- [x] Decisión P-04: el contexto automático del CLI usa `semantic: true` y no falla si la respuesta trae `degraded`
- [x] La versión del paquete sube a la siguiente menor (0.3.0) y no se publica en npm
- [x] Latencia: con el proveedor lento el contexto automático no excede `embedding_query_timeout` (10 s) más 1 s

**Subtareas**
- [x] Test en rojo del caso `semantic: true`
- [x] Cambiar el despachador
- [x] Subir versión y documentar en `docs/release-cli.md` el bloqueo de publicación
- [x] Ejecutar tests del paquete

**Notas**: Procedencia: decisión P-04, riesgo de latencia de la evaluación. Clase: cambio (test en rojo). Patrón: `packages/kairos-cli/lib/dispatcher.mjs:84` (`layers: ['episodic','documental'], semantic: false, limit: 5, max_chars: 5000`). La publicación queda para cuando se desbloquee la cuenta (ver `docs/roadmap/2026-11-06-functional-parity/tasks.md`, F-06). Implementado: `dispatcher.mjs` pide `semantic: true`; si la llamada excede el plazo del cliente (`mcp_timeout`, 1,8 s por llamada; hook 8 s) repite una vez solo léxica y lo declara en la evidencia como `degraded: {layer: "semantic", reason: "client_timeout"}`; si el servidor informa `degraded` solo viajan `layer` y `reason` conocidos (nunca texto libre); cualquier otro error (autorización, red) sigue fallando. Versión `0.3.0` en `package.json` y `VERSION` (`config.mjs`; `COMPATIBLE_VERSIONS` conserva `0.2.0`); README, `docs/release-cli.md`, `docs/install.md` y `docs/code-analysis.md` actualizados, con el bloqueo de publicación (F-06). NO se ejecutó `npm publish` ni se construyó/publicó tarball alguno en ningún registro. Latencia: el servidor acota la espera de embeddings a `embedding_query_timeout` (probado: ≤ plazo + 1 s) y el cliente nunca espera más de su plazo por llamada. Desviaciones: `config.mjs`, `docs/install.md` y `docs/code-analysis.md` no estaban en `Archivos` (versión y rutas del runtime); el cambio de la aserción previa `semantic === false` del test de contexto a `true` es la decisión P-04 misma. **Corrección tras revisión (intento 2, gaps 1 y 2, fix1)**: gap 1 verificado (`docs/install.md:17` y `packages/kairos-cli/README.md` mandaban instalar `artifacts/daycry-kairos-0.3.0.tgz` y afirmaban un `release:check` del tarball que no existe; `README.md` raíz apuntaba al tarball 0.2.0 ignorado por git, hallazgo O-07 del audit): la prosa dice ahora que la 0.3.0 no está publicada ni empaquetada, que `artifacts/` está en `.gitignore` y que, desde un clon, primero se genera el tarball con `npm pack --ignore-scripts --offline --pack-destination ./artifacts` (el mismo comando de `docs/release-cli.md`; `package.json` no tiene script de empaquetado propio) dentro de `packages/kairos-cli` y luego se instala ese fichero; los comandos de `packages/kairos-cli/README.md` usan `./artifacts/daycry-kairos-0.3.0.tgz`. No se construyó ni publicó ningún tarball. `README.md` se añade a `Archivos` (sección «Conectar un agente»). Gap 2 (parte CLI) verificado: el hook abortaba a 1,8 s y el reintento léxico no cabía en los 2,2 s del IPC, y la petición abortada seguía en el servidor. Ahora el CLI envía UNA petición con `semantic_budget_ms: 1100` (`SEMANTIC_BUDGET_MS`, margen de 700 ms bajo el plazo de 1,8 s) y se elimina el reintento léxico y `client_timeout`; un `mcp_timeout` del cliente falla como cualquier error de transporte; el `degraded` del servidor (ahora también `store_error`) se tolera y viaja. Tests (`dispatcher.test.mjs`): una sola petición, presupuesto enviado y entre 1000 y 1200 ms, `degraded` timeout tolerado, sin reintento ante `mcp_timeout`. Documentación actualizada en `docs/integration.md`, `docs/install.md`, `packages/kairos-cli/README.md` y `docs/release-cli.md` (que aún describía el reintento). Medición: usage-meter `retrieval-quality/T-26-fix1` … `T-29-fix1` (una ventana compartida por las cuatro, 8 min de reloj; 0,08 h IA (medido), imputadas una sola vez aquí). **Corrección tras revisión (ronda 2, fix2, gaps N2 y N6)**: N6 verificado: `docs/install.md`, `docs/integration.md` y `packages/kairos-cli/README.md` afirmaban que la consulta de embeddings no sigue en marcha; ahora dicen que el servidor solo deja de esperar al proveedor (cancela su petición HTTP) y que Ollama puede terminar el cálculo; `docs/integration.md` añade que el presupuesto cubre toda la capa semántica y que `true`/`"1100"` se rechazan. El comentario de `dispatcher.mjs:11` cita ahora el plazo del IPC (2200 ms, `lifecycle.mjs:123`) y el del hook (8 s, `hooks.mjs:22`). Evidencia posterior a las correcciones (2026-11-11, fix2): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 412}` (`docker build --target test ... -t kairos-test:rq6`, exit 0); puerta `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq6 python -m memory_platform.tests.run_postgres` exit 0, `gate.passed: true`, `failures: []` (CA-18 y CA-35 comprobados por la puerta), `fused` recall@5 1,0, MRR 0,971528 (mejor capa individual `semantic` 0,964583, CA-18 cumplido), CA-35 sin regresiones; `npm test` en `packages/kairos-cli`: exit 0, 90 pruebas, 90 pasan, 0 fallan (fix2).

---


RED: `packages/kairos-cli/tests/dispatcher.test.mjs (3 casos de contexto automatico)` falló con node --test: pass 9 fail 3; AssertionError actual false expected true en args.semantic y degraded undefined en el payload · 2026-11-11.

## Fase 7 — Observabilidad (C-07 · P12) — en paralelo desde T-06

**Estado**: completado · **Estimado**: 18h base (21.6h con margen) · **Real**: — · **Coste est.**: 1.080 € · **Tokens est.**: 700k in / 70k out

### T-30 — Logging JSON con redacción y `request_id`

- **Descripción**: Crear `memory_platform/observability.py` con un formateador JSON de una línea (`ts`, `level`, `event`, y en búsquedas `request_id`, `layer`, `duration_ms`) que reutiliza `privacy.py` para redactar secretos, e instalarlo en `memory-api` y `memory-worker`.
- **Changelog**: Los logs de la API y del worker son JSON de una línea con nivel, evento, duración e identificador de petición, con los secretos redactados, y todo fallo antes silencioso deja traza con el tipo de excepción.
- **Estado**: completado
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,72h · real 0,49h (medido: ventana única de usage-meter compartida por T-30…T-33, 20 min de reloj, imputada aquí una sola vez)
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-06
- **Tipo**: backend
- **Archivos**: `memory_platform/observability.py`, `memory_platform/app.py`, `memory_platform/worker.py`, `memory_platform/privacy.py`, `memory_platform/tests/test_observability.py`, `memory_platform/activity.py`, `memory_platform/mcp.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_observability` con CA-32 en rojo antes de crear el módulo)
  - Evidencia (2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0; 412 de la fase 6 + 55 nuevas: 21 en `test_observability`, 34 en `test_metrics`; reparto corregido tras la revisión, intento 2); incluye `test_observability` con CA-32, request_id propagado de la respuesta a las líneas de capa y fallos, y la regla estática sin `except Exception` mudo.
  - Cobertura B-01 (`grep -n "except Exception" memory_platform/*.py`, 12 manejadores): 11 registran con `log_event`/`log_failure` o relanzan (`activity.py` sondeo, `app.py` readiness y línea de acceso, `mcp.py` `safe`, `retrieval.py` liberación del hueco vectorial (relanza), capa y capa semántica, `worker.py` latido y fallo inesperado, `observability.py` cola de métricas); el handler global `@app.exception_handler(Exception)` registra `unhandled_exception`. 0 sin traza; 1 justificado: `admin.py` (final del módulo) es el CLI, que termina diciendo el tipo de excepción sin credenciales y no vuelve a un servicio.

**Criterios de aceptación**
- [x] CA-32: los logs de `memory-api` y `memory-worker` son JSON de una línea con `ts`, `level`, `event` y, en búsquedas, `request_id`, `layer`, `duration_ms`; los secretos sintéticos aparecen redactados
- [x] Un `request_id` se propaga de la petición a los logs de sus capas
- [x] No se registra la consulta ni el contenido, solo duraciones y códigos

**Subtareas**
- [x] Test en rojo (formato, redacción, request_id)
- [x] Implementar formateador y contexto de petición
- [x] Instalar en API y worker

**Notas**: Procedencia: spec CA-32, decisión P-05, riesgo R-08. Clase: capacidad nueva (test nuevo en rojo). Patrones: redacción en `memory_platform/privacy.py` y `scripts/deploy-memory.py:31` (`redact_output`); `grep` de `logging` en `memory_platform/*.py` vacío (sin patrón previo). **Implementación (2026-11-11)**: `memory_platform/observability.py` (formateador `JsonFormatter`, `configure_logging`, `log_event`, `log_failure`, `REQUEST_ID` como `ContextVar`); `app.main()` y `worker.serve()` lo instalan (`uvicorn.run(..., log_config=None, access_log=False)`: línea de acceso JSON propia `http_request` con `method`, `route` (plantilla, sin ids), `status`, `duration_ms`; las comprobaciones de salud solo a nivel info si fallan). Campos cerrados (`FIELDS`): cualquier otro nombre se descarta, así que una consulta o un contenido no pueden entrar por descuido; los textos pasan por `privacy.redact_log` (nueva, no lanza nunca). Un fallo registra `exc_type`, jamás el mensaje. El `X-Request-ID` ahora también viaja en las respuestas de error (`error()`), incluidas las 503 del handler global. Ajuste del plan director (B-01): `activity.py` y `mcp.py` se añaden a `Archivos` (los demás manejadores están en ficheros ya declarados). Decisión: las rutas de salud se registran a nivel debug salvo que fallen, para no inundar el log con el healthcheck de 15 s. **Revisión de dos lentes, intento 2 (2026-11-11, medido `retrieval-quality/T-30-fix1`: 0,02 h-IA)**: (gap 1) `configure_logging` deja el logger raíz con un único manejador JSON (quita los previos, también el Rich de FastMCP, que se guardan y se restauran en `remove_logging`), todos los loggers propagan a él y `httpx`/`httpcore` bajan a WARNING; `create_mcp` llama a `enforce_logging()` justo tras `FastMCP(...)`, que lo reinstala si FastMCP volvió a tocar la raíz (FastMCP no ofrece un parámetro para no instalarlo). En registros de terceros `event` es el nombre del logger, `msg` va redactado y truncado a 300 y de `exc_info` solo sale `exc_type`. Tests: `test_every_logger_of_the_process_ends_in_one_json_line_with_no_secret` (una línea JSON por logger, DSN con secreto sintético y traceback ausentes, httpx INFO suprimido) y `test_the_root_logger_keeps_only_the_json_handler_even_after_fastmcp_is_created`. (gap 6) la línea de acceso usa el valor cerrado `mcp` para el Mount `/mcp` (`MOUNT_ROUTES`, `mount_label`; otro Mount sería `mount`; se calcula antes de enrutar porque el Mount reescribe la ruta y la ruta interior sería `/`); test `test_mcp_requests_are_logged_with_the_closed_route_mcp`. (gap 8) `_clean` redacta primero y trunca después; test con un token sintético que cruza el corte de 200 y el de 300 (`test_a_token_that_crosses_the_field_limit_is_still_redacted`). (gap 9) reparto corregido: 21 tests en `test_observability` y 34 en `test_metrics` (467 en total). El manejador de `getMessage()` del formateador captura solo `TypeError/ValueError/KeyError/IndexError` para no violar la regla estática B-01. Evidencia: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0, 2026-11-11); puerta offline `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq7 python -m memory_platform.tests.run_postgres` exit 0 (`RETRIEVAL_EVAL_RESULT` con `gate.passed: true`, 2026-11-11).


RED: `memory_platform/tests/test_observability.py (formato JSON, redaccion, request_id, except sin traza)` falló con unittest: ImportError cannot import name 'observability' from 'memory_platform' (modulo inexistente) · 2026-11-11.

### T-31 — Registro de métricas Prometheus con `prometheus_client` fijado

- **Descripción**: Añadir `prometheus_client` fijado en `requirements.txt` y el registro de métricas: histograma `kairos_retrieval_layer_seconds{layer}`, contador `kairos_provider_errors_total{provider,code}` y gauge `kairos_jobs_queue_depth{state,destination}` calculado desde `memory.jobs` al servir `/metrics`, con etiquetas de valores cerrados.
- **Changelog**: El servicio expone métricas Prometheus con latencia por capa de búsqueda, errores de proveedor por código y profundidad de la cola de trabajos, con etiquetas de valores cerrados.
- **Estado**: completado
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,72h · real — (incluido en la ventana medida de T-30)
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 20k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-30
- **Tipo**: backend
- **Archivos**: `memory_platform/observability.py`, `memory_platform/requirements.txt`, `memory_platform/tests/test_metrics.py`, `memory_platform/privacy.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_metrics`: formato y etiquetas en rojo antes del cambio)
  - `grep -n "prometheus_client==" memory_platform/requirements.txt` → versión exacta fijada
  - Evidencia (2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0; 412 de la fase 6 + 55 nuevas: 21 en `test_observability`, 34 en `test_metrics`; reparto corregido tras la revisión, intento 2); incluye `test_metrics` (nombres y etiquetas, valores cerrados, cola desde `memory.jobs` con PostgreSQL real).
  - `grep -n "prometheus_client==" memory_platform/requirements.txt` → `8:prometheus_client==0.23.1` (versión exacta; el Dockerfile la instala en `api`, `worker` y `test` con `pip install -r requirements.txt`, y el build de `test` la importó).

**Criterios de aceptación**
- [x] Las tres métricas se registran con los nombres y etiquetas del spec CA-30
- [x] Las etiquetas solo toman valores cerrados (capas, proveedores, códigos, estados); ninguna lleva ids de proyecto, consultas o credenciales
- [x] La profundidad de cola refleja `memory.jobs` en el momento de la lectura

**Subtareas**
- [x] Tests en rojo del registro
- [x] Implementar métricas y consulta de cola
- [x] Fijar versión de `prometheus_client`

**Notas**: Procedencia: spec CA-30, CA-31, decisión P-05, riesgo R-08. Clase: capacidad nueva (test nuevo en rojo). Varios procesos uvicorn exigirían modo multiproceso: hoy es uno solo (se comprueba en `memory_platform/app.py`). **Implementación (2026-11-11)**: registro propio `CollectorRegistry` en `observability.py` (no el global: `/metrics` solo muestra métricas `kairos_*`). `kairos_retrieval_layer_seconds{layer}` (histograma), `kairos_provider_errors_total{provider,code}`, `kairos_jobs_queue_depth{state,destination}` (se recalcula con `refresh_queue_depth(store)` al servir `/metrics`: un `GROUP BY state, destination` sobre `memory.jobs`, con todos los pares cerrados a 0 para no dejar valores viejos; sin método nuevo en `Store`, así que `store_surface.json` no cambia; un fallo de base se registra y no tumba `/metrics`). Etiquetas cerradas por `closed()`: capas `episodic/documental/temporal/semantic`, proveedores `extract/embed`, códigos de error conocidos, estados y destinos de `memory.jobs`; todo lo demás es `other`. Un único proceso uvicorn (`app.main`, sin `workers`): no hace falta modo multiproceso; un test lo fija. Límite documentado en `docs/operations.md`: las métricas que ocurren en el proceso del worker (contadores de proveedor, `kairos_worker_*`) no salen por `/metrics` porque el worker no sirve HTTP; de él se leen logs y la cola. Archivos extra: `memory_platform/privacy.py` (`redact_log`, compartido con T-30). **Revisión de dos lentes, intento 2 (2026-11-11)**: (gap 2b) nueva serie `kairos_jobs_failed{destination,code}` derivada de `memory.jobs` (`state='failed'` agrupado por destino y `error_code`) al servir `/metrics`; `code` cerrado sobre `JOB_CODES` (los códigos de proveedor/worker más `destination_retired` y `superseded`), `other` para el resto y NULL; todos los pares a 0 para no dejar valores viejos. Diferencia documentada en `docs/operations.md`: `kairos_provider_errors_total` es un contador en memoria del proceso de la API (consultas) y no ve el worker; `kairos_jobs_failed` cuenta trabajos fallados, no intentos, y sí lo recoge. Tests: `test_failed_jobs_are_derived_from_the_table_by_closed_code` y la comprobación contra PostgreSQL real en `test_the_queue_depth_follows_real_jobs`. (gap 4) la lectura de la cola va con `SET LOCAL statement_timeout = 2000`, cuenta solo estados no terminales (`pending`, `running`, `failed`, `unknown`; `succeeded` deja de ser una serie de `kairos_jobs_queue_depth`) para usar el índice `memory_job_queue(state, available_at)`, y se cachea 10 s (`QUEUE_CACHE_SECONDS`, también el fallo); sin migraciones. Tests `test_the_scrape_query_is_bounded_and_skips_the_terminal_bulk` y `test_a_loop_of_scrapes_reads_the_database_once_per_window`. (gap 5) gauge `kairos_jobs_queue_scrape_success` (1/0); si falla la base valen los últimos buenos y el gauge a 0; test `test_a_failing_read_is_visible_in_the_scrape_success_gauge` y la ruta `/metrics`. Evidencia: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0, 2026-11-11); puerta offline `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq7 python -m memory_platform.tests.run_postgres` exit 0 (`RETRIEVAL_EVAL_RESULT` con `gate.passed: true`, 2026-11-11).


RED: `memory_platform/tests/test_metrics.py RegistryTests (nombres, etiquetas cerradas, profundidad de cola)` falló con unittest: ImportError cannot import name 'observability' from 'memory_platform' (registro inexistente) · 2026-11-11.

### T-32 — Instrumentación de capas, proveedores y worker

- **Descripción**: Instrumentar `Retrieval.search` (latencia por capa), `providers.py` (errores por código) y el worker (duración y errores de jobs). Resultado: cada búsqueda emite latencia por capa a logs y métricas.
- **Changelog**: Cada búsqueda registra la latencia de sus capas en logs y métricas, los fallos del proveedor de embeddings y extracción se cuentan por código y la espera por el semáforo de embeddings queda medida.
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,58h · real — (incluido en la ventana medida de T-30)
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-31
- **Tipo**: backend
- **Archivos**: `memory_platform/retrieval.py`, `memory_platform/providers.py`, `memory_platform/worker.py`, `memory_platform/tests/test_metrics.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/observability.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye casos de instrumentación en rojo antes del cambio)
  - Evidencia (2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0; 412 de la fase 6 + 55 nuevas: 21 en `test_observability`, 34 en `test_metrics`; reparto corregido tras la revisión, intento 2); incluye `InstrumentationTests` (capas, fallo de capa medido, respuestas sin cambio, errores por código, saturación) y `WorkerDeadlineTests` (deuda R1).
  - Puerta de calidad offline (`docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq7 python -m memory_platform.tests.run_postgres`) → exit 0, `gate.passed: true`, `failures: []`, `fused` MRR 0,971528 (idéntico al de la fase 6): la instrumentación no cambia resultados.

**Criterios de aceptación**
- [x] CA-30 (contenido): tras una búsqueda, `kairos_retrieval_layer_seconds` tiene muestras para las capas ejecutadas
- [x] Un fallo del proveedor incrementa `kairos_provider_errors_total` con su `code`
- [x] La instrumentación no cambia respuestas ni orden de resultados (suite verde)

**Subtareas**
- [x] Tests en rojo
- [x] Envolver las capas en `Retrieval.search`
- [x] Contar errores en `providers.py`
- [x] Instrumentar el worker

**Notas**: Procedencia: spec CA-30, CA-32. Clase: capacidad nueva (test nuevo en rojo). Patrón: capas en `memory_platform/retrieval.py:97-146`. **Implementación (2026-11-11)**: `Retrieval.search` mide cada capa (`record_layer`: histograma + línea `retrieval_layer` con `request_id`, `layer`, `duration_ms`, `status`; la semántica solo si llegó a ejecutarse: `semantic: false`/embeddings desactivados no miden); un fallo mide igual y registra `layer_failed` (con `reason` en la semántica). `providers.py`: `counted()` envuelve `Ollama.extract`, `Embeddings.embed` y `embed_many` y cuenta `ProviderError.code` (un plazo vencido es `provider_timeout`); el error se relanza sin cambios. **Hallazgo B-14 (saturación del semáforo)**: `embedding_slot` mide la espera por el hueco único con `kairos_embedding_wait_seconds{caller}` (histograma; también cuando el llamante se cancela esperando) y `kairos_embedding_slots_in_use{caller}` (gauge), `caller` ∈ `query`/`worker`; el semáforo es de cada proceso (la API y el worker no lo comparten), así que `/metrics` ve el de las consultas. Worker: `kairos_worker_jobs_total{destination,outcome}` y `kairos_worker_job_seconds{destination}` más los eventos `job_completed`/`job_failed`/`heartbeat_failed`/`lease_lost`. **Deuda de la fase 6 (Minor R1)**: `worker_deadline(settings, inputs, stored_vector=True)` solo suma la llamada extra de re-embebido (120 s) cuando hay vector guardado; `Worker.run_once` empieza con `stored_vector=False` y, en cuanto `stored_item_vector` devuelve un vector, amplía el plazo en curso con `limit.reschedule(limit.when()+embedding_job_timeout(settings, 1))`, de modo que el caso de dimensiones distintas conserva su plazo completo y un proveedor colgado sin vector guardado retiene al worker 910 s como máximo en vez de 1030 s (con los valores por defecto). Tests: sin vector guardado el trabajo vence con `provider_timeout` en cuanto agota los lotes; con vector de otras dimensiones la llamada extra cabe. Los tests de plazo viven en `test_metrics.py`. Archivos extra: `observability.py` y `docs/operations.md`. **Revisión de dos lentes, intento 2 (2026-11-11)**: (gap 2a) cuando el plazo de la capa semántica (`asyncio.timeout(budget)` exterior) vence durante la fase de embed, `counted` solo ve la cancelación; ahora `retrieval.py` cuenta `provider_timeout` en ese caso, sin doble cómputo si el timeout propio del proveedor ya lo contó (`counted` marca la excepción con `kairos_counted`). Tests `test_a_query_whose_budget_runs_out_during_the_embedding_counts_provider_timeout` y `test_the_providers_own_timeout_is_counted_once`. (gap 7) `test_with_a_stored_vector_of_other_dimensions_the_extra_call_still_fits` ahora usa llamada por lotes 0,35 s + llamada extra 0,35 s = 0,7 s, por encima del plazo base (0,5 s) y dentro del ampliado (1,0 s): comprobado que FALLA (`fail_job` con `provider_timeout`) al quitar temporalmente el `reschedule` del worker, y pasa al restaurarlo. Evidencia: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0, 2026-11-11); puerta offline `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq7 python -m memory_platform.tests.run_postgres` exit 0 (`RETRIEVAL_EVAL_RESULT` con `gate.passed: true`, 2026-11-11).


RED: `memory_platform/tests/test_metrics.py InstrumentationTests y WorkerDeadlineTests (capas, errores de proveedor, saturacion, plazo del worker)` falló con unittest: ImportError cannot import name 'observability' from 'memory_platform'; worker_deadline() got an unexpected keyword argument 'stored_vector' · 2026-11-11.

### T-33 — Endpoint `/metrics` solo en red interna y ajuste de despliegue

- **Descripción**: Servir `GET /metrics` (`text/plain; version=0.0.4`) en `memory-api` con `MEMORY_METRICS=internal` (valores `off`/`internal`/`admin`), sin publicarlo por nginx en 5173 y sin exponer puerto nuevo en `docker-compose.yml`; rechazar peticiones que lleguen por el proxy público. Resultado: métricas accesibles solo desde `memory-data`.
- **Changelog**: `GET /metrics` solo responde en la red interna (o con credencial de administrador, o queda desactivado con `MEMORY_METRICS`) y nunca se publica por nginx ni por el proxy HTTPS.
- **Estado**: completado
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,58h · real — (incluido en la ventana medida de T-30)
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Cerrada**: 2026-11-11
- **Dependencias**: T-31, T-32
- **Tipo**: devops
- **Archivos**: `memory_platform/app.py`, `memory_platform/config.py`, `memory_platform/nginx.conf`, `memory_platform/Caddyfile.example`, `docker-compose.yml`, `memory_platform/tests/test_metrics.py`, `docs/configuration.md`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye CA-30/CA-31 en rojo antes del cambio, con `TestClient`)
  - `grep -n "metrics" memory_platform/nginx.conf memory_platform/Caddyfile.example` → el proxy bloquea `/metrics` (`return 404` o equivalente)
  - `docker compose --profile memory config | grep -c "8790:"` → sin puerto nuevo publicado para la API
  - Evidencia (2026-11-11): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0; 412 de la fase 6 + 55 nuevas: 21 en `test_observability`, 34 en `test_metrics`; reparto corregido tras la revisión, intento 2); incluye `MetricsRouteTests` (CA-30 interno/proxy/off/admin, CA-31 consulta y token sintéticos ausentes de `/metrics` y de los logs) y `DeploymentTests`.
  - `grep -n "metrics" memory_platform/nginx.conf memory_platform/Caddyfile.example` → `nginx.conf:41` (comentario) y `:42: location ~* ^(/memory-api)?/+metrics { return 404; }`; `Caddyfile.example:5-7`: `@metrics path /metrics /metrics/* /memory-api/metrics /memory-api/metrics/*` + `respond @metrics 404` antes de `reverse_proxy`.
  - `docker compose --profile memory config | grep -c "8790:"` → `0` (igual que en el commit base: sin puerto nuevo; `memory-api` conserva `127.0.0.1:8790:8790`, que la configuración renderiza como `published: "8790"`); `MEMORY_METRICS: internal` aparece en el entorno compartido.

**Criterios de aceptación**
- [x] CA-30: desde fuera de la red interna (cabecera de proxy público) se rechaza; con acceso interno responde 200 `text/plain; version=0.0.4` con las tres métricas
- [x] CA-31: con una consulta y un token sintéticos en búsquedas, ninguno aparece en `/metrics` ni en los logs
- [x] `MEMORY_METRICS=off` desactiva la ruta (404)
- [x] `/metrics` no se publica en nginx 5173

**Subtareas**
- [x] Tests en rojo (acceso y fuga de datos)
- [x] Implementar la ruta y los tres modos
- [x] Bloquear `/metrics` en `nginx.conf` y `Caddyfile.example`
- [x] Documentar `MEMORY_METRICS` en `docs/configuration.md`

**Notas**: Procedencia: spec CA-30, CA-31, decisión P-05 (solo red interna, `MEMORY_METRICS=internal`). Clase: capacidad nueva (test nuevo en rojo). Patrones: ajustes de entorno en `memory_platform/config.py`, redes `memory-data` y publicación de `memory-web` en `docker-compose.yml`, `memory_platform/nginx.conf`. **Implementación (2026-11-11)**: `Settings.metrics_mode` (`off`/`internal`/`admin`, defecto `internal`; `MEMORY_METRICS` inválido impide arrancar, igual que `Settings(metrics_mode=...)`). `internal`: la ruta responde 200 `text/plain; version=0.0.4; charset=utf-8` salvo que la petición lleve cabeceras de proxy (`X-Forwarded-For/Host/Proto/Port`, `X-Real-IP`, `Forwarded`), en cuyo caso 404; `admin`: exige credencial (401 sin ella) de administrador (`is_admin`, 403 si no) y admite proxy; `off`: no se registra la ruta (404). `include_in_schema=False`: no aparece en OpenAPI ni en `docs/contracts` (el diff de contrato queda intacto; `test_contract_additive` en verde, 34 herramientas MCP). nginx bloquea `/metrics` y `/memory-api/metrics` con regex (gana a los prefijos), el ejemplo de Caddy para el VPS con HTTPS lo bloquea en el nombre público y el puerto 8790 sigue enlazado solo a `127.0.0.1`; el raspado se hace desde un contenedor de `memory-data` o desde el propio servidor sin cabeceras de proxy. Un proxy mal configurado que reenvíe `/metrics` con `X-Forwarded-*` sigue recibiendo 404 de la API (doble barrera). Documentado en `docs/configuration.md` (`MEMORY_METRICS`, `MEMORY_LOG_LEVEL`) y `docs/operations.md` (sección «Observabilidad: logs y métricas»). Un solo proceso uvicorn comprobado (`app.main` sin `workers`, Dockerfile sin `--workers`). **Revisión de dos lentes, intento 2 (2026-11-11)**: (gap 3) **Desviación consciente de CA-30**: el modo `internal` decide por ausencia de cabeceras de proxy y no por origen (en Docker la IP de origen no distingue redes de forma fiable). `docs/operations.md` dice ahora exactamente quién la lee (cualquier cliente que llegue directo a `memory-api:8790` sin cabeceras de proxy: contenedores de sus redes y el host por `127.0.0.1:8790`) y recomienda `MEMORY_METRICS=admin` u `off` en un VPS compartido. Evidencia: `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 467}` (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:rq7 .`, exit 0, 2026-11-11); puerta offline `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq7 python -m memory_platform.tests.run_postgres` exit 0 (`RETRIEVAL_EVAL_RESULT` con `gate.passed: true`, 2026-11-11).

---


RED: `memory_platform/tests/test_metrics.py MetricsRouteTests y DeploymentTests (acceso interno, proxy, off/admin, fuga CA-31)` falló con unittest: ImportError cannot import name 'observability' from 'memory_platform'; /metrics sin ruta (404) y Settings sin metrics_mode · 2026-11-11.

## Fase 8 — Integración, revisión y activación

**Estado**: borrador · **Estimado**: 26h base (31.2h con margen) · **Real**: — · **Coste est.**: 1.560 € · **Tokens est.**: 1200k in / 80k out

### T-34 — Manuales: pgvector, FTS por idioma, troceado y métricas

- **Descripción**: Completar `docs/architecture.md`, `docs/configuration.md` y `docs/operations.md` con FTS es/en y trigram, troceado (`MEMORY_CHUNK_*`), métricas y logs (`MEMORY_METRICS`), la puerta `retrieval-eval` y el relleno del despliegue. Regenerar el manual con capturas si el script lo hace.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,5h · real —
- **Supervisión**: est. 0,12h (≈25 % IA) · real —
- **Previsión IA**: 140k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-12, T-18, T-25, T-28, T-29, T-33
- **Tipo**: docs
- **Archivos**: `docs/architecture.md`, `docs/configuration.md`, `docs/operations.md`, `docs/manual.md`, `docs/README.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/build-handbook.py` → sin errores y sin enlaces rotos
  - `grep -nE "pgvector|unaccent|pg_trgm|embedding_chunks|MEMORY_METRICS|MEMORY_CHUNK_CHARS|retrieval-eval" docs/architecture.md docs/configuration.md docs/operations.md` → al menos una coincidencia por término en el manual correspondiente

**Criterios de aceptación**
- [ ] CA-36: los manuales afectados describen pgvector, FTS por idioma, troceado y métricas
- [ ] Todas las variables nuevas (`MEMORY_VECTOR_INDEXES`, `MEMORY_CHUNK_*`, `MEMORY_METRICS`) constan en `docs/configuration.md`

**Subtareas**
- [ ] Redactar y revisar cada manual
- [ ] Regenerar el manual con el script

**Notas**: Procedencia: spec CA-36. Clase: documentación. Patrón: estructura de manuales existente y script `scripts/build-handbook.py`.

### T-35 — Contrato regenerado y puertas transversales (CA-33, CA-34)

- **Descripción**: Regenerar `docs/contracts` y automatizar en una puerta el diff aditivo del contrato (34 herramientas) y el `grep` de migraciones sin operaciones destructivas. Resultado: dos comprobaciones repetibles al cierre.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,33h · real —
- **Supervisión**: est. 0,08h (≈25 % IA) · real —
- **Previsión IA**: 90k in / 5k out tok · ⚠️ verificar €
- **Dependencias**: T-25, T-26, T-33
- **Tipo**: test
- **Archivos**: `scripts/export-contracts.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/tests/test_contract_additive.py`, `memory_platform/tests/test_migrations_additive.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_contract_additive` y `test_migrations_additive`)
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → sin cambios adicionales respecto de lo ya commiteado en T-25/T-26

**Criterios de aceptación**
- [ ] CA-33: 34 herramientas y diff solo aditivo
- [ ] CA-34: ninguna migración nueva contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE` (test de `grep`)

**Subtareas**
- [ ] Escribir test de migraciones aditivas
- [ ] Regenerar y confirmar contratos

**Notas**: Procedencia: spec CA-33, CA-34. Clase: verificación transversal. Patrón: `scripts/export-contracts.py`.

### T-36 — Ejecución real con Ollama local y puerta final de calidad

- **Descripción**: Ejecutar `retrieval-eval` con el Ollama local (`nomic-embed-text`) y el dataset sintético en una base aislada (autorizado en P-06; nunca contra la base desplegada) y registrar el resultado final frente a umbrales y línea base. Resultado: calidad del modelo real medida, no solo la mecánica.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,33h · real —
- **Supervisión**: est. 0,08h (≈25 % IA) · real —
- **Previsión IA**: 90k in / 5k out tok · ⚠️ verificar €
- **Dependencias**: T-27, T-23
- **Tipo**: test
- **Archivos**: `memory_platform/tests/retrieval_eval/run.py`, `docs/roadmap/2026-11-09-retrieval-quality/testing/final-eval-fake.json`, `docs/roadmap/2026-11-09-retrieval-quality/testing/final-eval-ollama.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → pasa con el proveedor simulado (`final-eval-fake.json`)
  - `MEMORY_EMBEDDING_PROVIDER=ollama python -m memory_platform.tests.retrieval_eval.run --report testing/final-eval-ollama.json` en el harness aislado contra Ollama local → informe con recall@5 `fused` ≥ 0,80 y MRR ≥ 0,60 (el nombre exacto del selector de proveedor se fija en T-02)

**Criterios de aceptación**
- [ ] CA-35: la puerta pasa con los umbrales (P-06) y ningún subconjunto empeora más de 2 puntos de recall@5 frente a `baseline.json`; +15 pts de recall@5 en idioma, errores y documento largo
- [ ] El informe real registra `product_database_accessed: false` y solo datos sintéticos
- [ ] Si el Ollama local no está disponible se informa del bloqueo con el hash del dataset; no se sustituye por el proveedor simulado

**Subtareas**
- [ ] Verificar disponibilidad de Ollama local
- [ ] Ejecutar la puerta real en base aislada
- [ ] Guardar informes y resumen

**Notas**: Procedencia: spec CA-35, decisión P-06. Clase: verificación. Patrón: sondas con proveedor real en `memory_platform/tests/live_probe.py` y target `live-probe` (`memory_platform/Dockerfile:34-37`).

### T-37 — Revisión de dos lentes y correcciones

- **Descripción**: Revisión por dos lentes (A: correctitud y contrato; B: seguridad, privacidad, rendimiento y operación) de todo lo integrado, con correcciones hasta cerrar los hallazgos Critical/Important. Resultado: informe de revisión y suite verde final.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 16h · real —
- **Tiempo IA (ejec.)**: est. 2,65h · real —
- **Supervisión**: est. 0,66h (≈25 % IA) · real —
- **Previsión IA**: 740k in / 50k out tok · ⚠️ verificar €
- **Dependencias**: T-34, T-35, T-36
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-09-retrieval-quality/review.md`, `memory_platform/**`, `docs/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0`
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → pasa con el proveedor simulado
  - `python $SHAREDKIT/scope-check.py docs/roadmap/2026-11-09-retrieval-quality` → exit 0

**Criterios de aceptación**
- [ ] CA-36: la suite backend completa pasa con 0 fallos y 0 omitidos
- [ ] Sin hallazgos Critical/Important abiertos en `review.md`
- [ ] Ninguna fuga de datos en métricas/logs (revisión de R-08) y ninguna ruta del producto desplegado tocada

**Subtareas**
- [ ] Lente A
- [ ] Lente B
- [ ] Aplicar correcciones y repetir la suite

**Notas**: Procedencia: líneas transversales de la evaluación (revisión: partida grande, LES-001/LES-009). Clase: revisión. Reserva las 16 h de revisión de la evaluación.

### T-38 — Despliegue real con relleno y verificación (requiere autorización expresa)

- **Descripción**: Con la autorización expresa del usuario en ese momento (la base desplegada solo se toca por esta tarea), ejecutar `scripts/deploy-memory.py --apply` con la imagen nueva, el relleno de vectores y fragmentos y la verificación de la fase `verify`. Resultado: producción con pgvector, FTS por idioma y fragmentos, con el manifiesto de contenido comparado antes y después.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,5h · real —
- **Supervisión**: est. 0,12h (≈25 % IA) · real —
- **Previsión IA**: 140k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-37
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `docs/roadmap/2026-11-09-retrieval-quality/testing/activation.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/deploy-memory.py` (sin `--apply`) → el plan lista las 10 fases y el relleno; `--apply` solo tras la autorización del usuario
  - `python scripts/deploy-memory.py --apply` → `status: ok`, `content_manifest().sha256` igual antes y después, `backups` con la copia previa
  - `python scripts/diagnose-deployment.py` → sin hallazgos críticos y 34 herramientas MCP disponibles

**Criterios de aceptación**
- [ ] Autorización expresa registrada en el ledger antes de ejecutar
- [ ] Las 10 fases completan, existe la copia previa y el manifiesto de contenido es igual antes y después de migrar
- [ ] El relleno de vectores y fragmentos termina sin errores de proveedor y `kairos_jobs_queue_depth` vuelve a 0
- [ ] Si Docker no está accesible se detiene en `engine` y se informa; no se hace ningún cambio parcial

**Subtareas**
- [ ] Pedir autorización al usuario con el resultado de T-11/T-12
- [ ] Ejecutar el despliegue y el relleno
- [ ] Verificar y guardar evidencia sin secretos

**Notas**: Procedencia: spec CA-14, decisión P-07. Clase: operación. Restricción: nunca tocar la base desplegada sin esta autorización; el ensayo (T-11) es obligatorio antes. Patrón: `testing/activation.json` del plan 2026-11-06. Reserva tiempo humano propio para la ventana (supervisión probablemente superior al 25 %).

---

## Revisión de dos lentes — intento 3: Fase 1 (T-01…T-03) (T-01, T-02, T-03)

Lentes: A+B+C. Traspaso de las tablas de los intentos 1 y 2; solo se re-evaluó lo corregido.

**Gaps 1-7 del intento 2: corregidos y verificados.** Lente B: sin defectos (sondas en contenedor efímero con PostgreSQL temporal; 14 tests de `test_metrics` OK). Lente C: sin hallazgos (redirección por `PGHOSTADDR` rechazada de punta a punta; audit hook de red → `PY_NETWORK_EVENTS []`).

**Resultado: sin gaps pendientes.** Fase 1 cerrada en revisión.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Important | El criterio aprobado CA-03 de T-02 se reescribió (de «el recibo registra `network: none`» a la observación local de interfaces) sin aprobación; `scope-check.py` marca «criterios aprobados alterados». Lente A | T-02 | descartado (rebatido): el usuario aprobó el 2026-11-09 enmendar CA-03 en la spec y en el ledger; queda registrado como decisión 9 de `spec.md` y como nota en el criterio | Decisión del usuario en la conversación (puerta del intento 3); `spec.md` CA-03 y «Decisiones confirmadas», punto 9 |
| N2 | Minor | Subtarea aprobada «vector estable por hash de n-gramas» reescrita. Lente A | T-02 | corregido: texto original restaurado, con la implementación anotada detrás | `tasks.md`, subtareas de T-02 |
| N3 | Minor | Recuento obsoleto «186 / 9» en T-03 tras el intento 2 (la suite tiene 191 = 177 + 14). Lente A | T-03 | corregido: 191 / 14 en descripción, Verificación y criterio de T-03 | `Dockerfile:48`; evidencia de T-02 |

Nota de alcance: `scope-check.py --base 1d43523` sigue informando «criterio aprobado alterado» en CA-03 de T-02 porque compara con el ledger de la base; la alteración está autorizada por el usuario (N1).


## Revisión de dos lentes — intento 3: Fase 2 (T-04…T-06) (T-04, T-05, T-06)

Lentes: A (solo evidencias y ledger cambiaron). Traspaso de las tablas de los intentos 1 y 2.

**Gap 5 del intento 2: corregido y verificado** (Verificación de T-06 idéntica a la base salvo la nota; ejecutada → `True 0 0`; hashes `7480cded…f4d9` 140, `af443668…68fb` 138 y `e21645f0…900b` 157 reproducidos; `scope-check --base 60be598` sin criterios alterados).

**Resultado: sin gaps pendientes.** Fase 2 cerrada en revisión.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 6 | Minor | La prosa de evidencia de T-04 y T-06 seguía describiendo el recibo previo con 191 tests en el primer nivel y citaba un bloque `same_suite_on_pre_refactor_tree` que ya no existe. Lente A | T-04, T-06 | corregido por el orquestador: los Resultados de T-04 y T-06 describen el primer nivel (194, `7480cded…f4d9`) y el bloque `pre_refactor_suite_at_60be598` (191, `af443668…68fb`) | `tasks.md`, Resultados de T-04 y T-06 |


## Revisión de dos lentes — intento 3: Fase 3 (T-07…T-12) (T-07, T-08, T-09, T-10, T-11, T-12)

Lentes: A+B+C+D (un revisor), con traspaso de las tablas de los intentos 1 y 2. Base `fc4c045`. `scope-check.py --base fc4c045` → exit 0; `ledger-lint` exit 0.

**Gaps #1…#6 del intento 2:** todos ✓. Suite `MEMORY_TEST_RESULT … "tests": 235 … "passed": true` pegada en T-08 (`:382`), T-09 (`:424`), T-10 (`:460`) y T-11 (`:505`); criterios y `Verificación` de T-07…T-12 idénticos a `fc4c045` (comparación por script). **Tests de truncado sustituidos:** cobertura de comportamiento conservada; cada rama de decisión de `rank_ann` sigue cubierta y 4 de 5 mutaciones en memoria se detectan (sobrevive solo `LIMIT 10001`→`LIMIT size`, que afecta a la ruta elegida, no a la corrección). Lente C: sin hallazgos.

**Resultado: 0 Critical, 0 Important, 3 Minor. Revisión cerrada.**

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | La salida de `retrieval-eval` pegada en T-10 es una proyección de `layers` (sin `overall`/`subsets` ni `gate.failures`), no la salida literal. Basta para el criterio (ninguna capa empeora). Lente A | T-10 | corregido (tras el cierre, a petición del usuario): informe `RETRIEVAL_EVAL_RESULT` completo (con `layers` `overall`/`subsets` y `gate`/`failures`) guardado en `testing/phase3-eval.json` (sha256 `c06e9b46…3f3b`, exit 1 esperado, `layers` = `baseline.json`) y bloque `gate` pegado en T-10 («Evidencia literal (deuda #1, intento 3)») | `tasks.md:460`; `retrieval_eval/run.py:281` |
| 2 | Minor | La doc del truncado no reflejaba que el recuento solo incluye vectores vigentes que cumplen los filtros. Lente A/B | T-09 | corregido por el orquestador: `docs/configuration.md` describe el recuento como vigentes + filtros de categorías y etiquetas | `docs/configuration.md:62` |
| 3 | Minor | El recuento con `CURRENT_RESOURCE` usa SubPlan correlacionado por fila; con 10^6 vectores autorizados y un filtro muy raro pueden ser dos recorridos completos (segundos), y el backend semántico cae a `unavailable` por `statement_timeout`. Con el volumen real (~21 documentos) es despreciable. Lente D | T-09 | corregido (tras el cierre, a petición del usuario): un único recorrido (sin recuento; `rank_exact` informa `truncated`), en savepoint con `statement_timeout = min(resto del plazo, MEMORY_VECTOR_EXACT_FALLBACK_MS)` (1500 ms); tope agotado: filas HNSW con `truncated=True` (`partial`) y transacción usable; plazo global vencido: `semantic_deadline_exceeded`. Rojo 7/240, luego verde `MEMORY_TEST_RESULT … "tests": 241 … "passed": true`; detalle en T-09 (T-09-fix3) | `store_vectors.py:78-81` |

## Revisión de dos lentes — intento 2: Fase 4 (T-13…T-18) (T-13, T-14, T-15, T-16, T-17, T-18)

Lentes: A+B+C+D (un revisor), con traspaso de la tabla del intento 1. Base `7f15402`. `scope-check.py --base 7f15402` → exit 0; `ledger-lint` exit 0.

**Gaps #2…#11 del intento 1:** todos ✓. Suite literal del árbol final (279) en T-13/T-18; criterios 35/35 con texto literal de `7f15402`; `store_surface.json`, `docs/contracts` y `web/` sin diff; `Hit.lexical_match` opcional y aditivo (los contratos exportados no cambian: `scripts/export-contracts.py` regenerado sin diff). Respaldo trigram acotado a ≤1 s por capa (antes ~25 s con 10^6 filas).

**Resultado: 0 Critical, 0 Important, 4 Minor. Revisión cerrada.**

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Minor | Con `--stop-services-before-migrate`, si `migrate` falla, API y worker quedan parados y stderr no lo dice. Lente B | T-13 | corregido por el orquestador: `failure_hints()` en `scripts/deploy-memory.py` añade la línea «memory-api and memory-worker were stopped before migrate and are still stopped…» en fallos de `migrate`/`bootstrap`; test `test_a_failure_after_stopping_the_services_says_they_are_still_stopped` (`Ran 22 tests … OK` en `test_deploy_isolation` + `test_deploy`) | `scripts/deploy-memory.py`; `tests/test_deploy_isolation.py` |
| N2 | Minor | `except QueryCanceled` también captura un `pg_cancel_backend` de un admin y lo informa como `fuzzy_timeout`. Lente B | T-17 | deuda aceptada: degradado señalizado, no silencioso; mismo criterio que el respaldo exacto de la Fase 3 | `store_documents.py:33` |
| N3 | Minor | `CROSS JOIN LATERAL (SELECT key AS tkey)` puede aplanarse y recalcular `trigram_key` por uso. Lente D | T-17 | corregido por el orquestador: `OFFSET 0` en la subconsulta LATERAL de `trigram_items` y `trigram_documents` | `store_documents.py:47,60` |
| N4 | Minor | Ampliaciones de `Archivos` sin nota explícita (T-13: `deploy-memory.py`, `test_deploy_isolation.py`, `operations.md`, `fts-migration-cost.json`; T-17: `models.py`). Lente A | T-13, T-17 | corregido por el orquestador: esta fila es la nota; motivos en las correcciones #2, #5, #6 y #10 del intento 1 | `tasks.md:561,703,721` |

Suite tras N1/N3 (`docker build --progress=plain --target test -f memory_platform/Dockerfile -t kairos-test:p4b .`, exit 0):
`MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 280}`

## Revisión de dos lentes — intento 3: Fase 5 (T-19…T-25) (T-19, T-20, T-21, T-22, T-23, T-24, T-25)

Lentes: A+B+C+D. Las correcciones 1-11 del intento 2 se verifican ✓ (A, B, C, D). Veredicto: **sin gaps Critical/Important pendientes → fase cerrada**.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | Sin suite verde pegada sobre el árbol posterior al intento 2 | T-23/T-24 | corregido (orquestador): `docker build --no-cache-filter test --target test` → `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 376}`; retrieval-eval offline (`--network=none`) exit 1 por diseño, bloque `gate` idéntico a `phase5-eval.json` (`fused` 0,541667 / 0,403114) | Lente A |
| 2 | Minor | Marcar `chunked` impide HOT: cada fila obsoleta marcada inserta en el HNSW real; `stale-cost.json` midió sin HNSW; con decenas de miles de filas la fase `backfill` podría superar 1800 s | T-24 | deuda aceptada: reanudable e idempotente; corpus desplegado ≈21 documentos; medir con HNSW en T-36 | `admin.py:157-176` (D #1) |
| 3 | Minor | `ON CONFLICT DO UPDATE` reescribe la fila aunque los valores sean idénticos (tuplas muertas, entradas HNSW) | T-21/T-24 | deuda aceptada: lo limpia autovacuum; descripción del intento 2 #3 corregida | `store_jobs.py:165` (D #2) |
| 4 | Minor | Vector de elemento reutilizado con dims distintas a los fragmentos (mismo nombre de modelo, otras dims) → fallo permanente | T-21/T-24 | deuda aceptada: exige cambiar las dims bajo el mismo nombre; revisar en Fase 6 | `worker.py:88-90`; `store_jobs.py:61` (B G1) |
| 5 | Minor | Descripción de EOL del intento 2 #7 inexacta | T-20…T-24 | corregido: texto del intento 2 #7 | Lente B (fuera de lente) |

## Historial archivado

- 2026-11-10 · «Revisión de dos lentes — intento 1: Fase 1 (T-01…T-03) (T-01, T-02, T-03)» → [execution-history.md](execution-history.md) · SHA-256 `85bbafe9b8ac642a0abc0be550f75138be987911dc2d6a000c08fedf1142f383`
- 2026-11-10 · «Revisión de dos lentes — intento 2: Fase 1 (T-01…T-03) (T-01, T-02, T-03)» → [execution-history.md](execution-history.md) · SHA-256 `09ee58b3d039fb0834feeaded2f84bf3e778d485fe0d1cb0602f824b8fb9528a`
- 2026-11-10 · «Revisión de dos lentes — intento 1: Fase 2 (T-04…T-06) (T-04, T-05, T-06)» → [execution-history.md](execution-history.md) · SHA-256 `2e16acfe17980592894761a175f2178e4e65f7debfc48d1c626a88d7d23d1853`
- 2026-11-10 · «Revisión de dos lentes — intento 2: Fase 2 (T-04…T-06) (T-04, T-05, T-06)» → [execution-history.md](execution-history.md) · SHA-256 `fc0b8ff98641cecc7497a6394760aa1776393763c515bca22de89daa825a0358`
- 2026-11-10 · «Revisión de dos lentes — intento 1: Fase 3 (T-07…T-12) (T-07, T-08, T-09, T-10, T-11, T-12)» → [execution-history.md](execution-history.md) · SHA-256 `6e9760e45feb65c7352752a5f76e2e0338f9022807b701ed4e454dccb09e6f31`
- 2026-11-10 · «Revisión de dos lentes — intento 2: Fase 3 (T-07…T-12) (T-07, T-08, T-09, T-10, T-11, T-12)» → [execution-history.md](execution-history.md) · SHA-256 `718c89b6a1d570f4af96b5a6761e3e1629f37679bd28eb9c979fa09ffbd160a8`
- 2026-11-10 · «Revisión de dos lentes — intento 1: Fase 4 (T-13…T-18) (T-13, T-14, T-15, T-16, T-17, T-18)» → [execution-history.md](execution-history.md) · SHA-256 `04565b00abc6a24d1b2513a26bbd56bc5cde166e1366d4fc8c862c6905fc3a74`
- 2026-11-10 · «Revisión de dos lentes — intento 1: Fase 5 (T-19…T-25) (T-19, T-20, T-21, T-22, T-23, T-24, T-25)» → [execution-history.md](execution-history.md) · SHA-256 `321726471cd7c7840f901bd04e76c97b65fa30650edfbad97682166d0e132f8c`
- 2026-11-10 · «Revisión de dos lentes — intento 2: Fase 5 (T-19…T-25) (T-19, T-20, T-21, T-22, T-23, T-24, T-25)» → [execution-history.md](execution-history.md) · SHA-256 `8f53e668ea189469619321c4dff97dae3925b9a1aa8734fe77133c691ef18f6a`

## Revisión de dos lentes — intento 1: Fase 6 (T-26…T-29) — degradación, bonificación ajustable, B-09 y CLI 0.3.0 (T-26, T-27, T-28, T-29)

Lentes: A+B+D (C no aplica: `review-lens-select.py` sin motivos; D por ruta `worker`). `scope-check.py --base 68ca247` exit 0 (32 en alcance). Lente A: todos los criterios de T-26…T-29 ✓; `openapi-lint.py --diff` sin cambios rompedores; 34 herramientas.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | `docs/install.md:17` y `packages/kairos-cli/README.md:14,32,38` mandan instalar `artifacts/daycry-kairos-0.3.0.tgz` y afirman un `release:check` del tarball que no existe (`release-cli.md:3` dice lo contrario) | T-29 | corregido (intento 2) | Lente A |
| 2 | Important | El hook de contexto aborta a 1,8 s y reintenta solo léxico dentro de un plazo IPC de 2,2 s (`lifecycle.mjs:123`): el reintento casi nunca cabe y el hook se queda sin contexto, peor que con `semantic:false`; la petición abortada sigue en el servidor hasta 10 s y su embed ocupa Ollama durante el backfill | T-26/T-29 | corregido (intento 2) | Lentes B (#1) y D (G1), fusionados |
| 3 | Minor | La puerta no comprueba CA-18 (MRR de `fused` ≥ mejor capa); una bonificación de 0,005 pasa en verde | T-27 | corregido (intento 2) | Lente A (#2) |
| 4 | Minor | `config.py:152-153` y `Archivos` de T-27 apuntan a `testing/fusion-tuning.json`, que vive en `memory_platform/tests/retrieval_eval/` | T-27 | corregido (intento 2) | Lente A (#3) |
| 5 | Minor | `docs/configuration.md`: «1 equivale a un orden absoluto» solo con k y pesos por defecto | T-27 | corregido (intento 2) | Lentes A (#4) y B |
| 6 | Minor | `retrieval.py:131-144` clasifica errores de base de datos y `semantic_deadline_exceeded` como `provider_error` | T-26 | corregido (intento 2) | Lente B (#2) |
| 7 | Minor | `worker.py:49` re-embebe el texto completo en una llamada aparte que el plazo de `worker.py:91` no cuenta (timeout posible; 2× peticiones al proveedor) | T-28 | corregido (intento 2) | Lentes B (#3) y D (G2), fusionados |

## Revisión de dos lentes — intento 2: Fase 6 (T-26…T-29) — correcciones del intento 1 (T-26, T-27, T-28, T-29)

Lentes: A+B+D en un solo revisor de contexto fresco (C sin motivos). `scope-check.py --base 68ca247` exit 0 (35 en alcance). Gaps 1-7 del intento 1: ✓ cerrados. `openapi-lint.py --diff` sin cambios rompedores; 34/34 herramientas; solo `search` y `context` ganan `semantic_budget_ms` opcional.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Important | `test_contract_additive.py:115-122`: `additive_violations` acepta claves nuevas que restringen la entrada (`maximum`, `additionalProperties:false`, `minLength`, `dependentRequired`); la prueba de `search` ya no caza lo que cazaba la igualdad | T-26 | corregido (intento 3) | Lente A, mutaciones ejecutadas |
| N2 | Important | Ledger sin evidencia posterior a las correcciones: T-26…T-28 siguen con 398 tests y la puerta `retrieval-eval` no consta repetida tras añadir CA-18 | T-26…T-28 | corregido (intento 3) | Lente A |
| N3 | Minor | `has_vectors` (`retrieval.py:135`) queda fuera del presupuesto `semantic_budget_ms` | T-26 | corregido (intento 3) | Lente B |
| N4 | Minor | `semantic_budget_ms` acepta `true` (→ 1 ms) y `"1100"` por validación laxa | T-26 | corregido (intento 3) | Lente B |
| N5 | Minor | `worker.py:43` re-embebe siempre el texto completo, también cuando el vector guardado coincide: ~1,9× trabajo de Ollama en corpus cortos; docstring de `stored_item_vector` falso | T-28 | corregido (intento 3) | Lente D |
| N6 | Minor | `docs/install.md:148` y `docs/integration.md:36` afirman que el proveedor deja de calcular al agotarse el presupuesto; solo se cancela la espera HTTP | T-26 | corregido (intento 3) | Lente A (no verificable sin Ollama) |

## Revisión de dos lentes — intento 3: Fase 6 (T-26…T-29) — correcciones del intento 2 (T-26, T-27, T-28, T-29)

Lentes: A+B+D en un solo revisor de contexto fresco (C sin motivos). N1-N6 del intento 2: ✓ cerrados (test de contrato endurecido detecta mutaciones; 34/34 herramientas; `openapi-lint.py --diff` sin cambios; `node --test` 90/90; 93/96 unittest locales, 3 por falta de psycopg en el host). Sin gaps Critical ni Important: la fase queda cerrada. Los Minor pasan como deuda a la Fase 7 (T-30/T-34).

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| R1 | Minor | `worker_deadline` (`worker.py:31,105`) suma siempre la posible llamada extra (120 s), también sin vector guardado: un proveedor colgado retiene al trabajador hasta 1030 s en vez de 910 s | T-28 | deuda aceptada → Fase 7 | Lente D |
| R2 | Minor | `docs/operations.md:186,189` y `docs/configuration.md:51` siguen diciendo que el job no pasa de 900 s + 10 s | T-28 | deuda aceptada → T-34 | Lente A |
| R3 | Minor | `strict=True` rechaza `500.0` aunque el esquema publicado es `integer`; la documentación solo menciona `1.5` | T-26 | deuda aceptada → T-34 (documentar) | Lente B |

## Revisión de dos lentes — intento 1: Fase 7 (T-30…T-33) — observabilidad (T-30, T-31, T-32, T-33)

Lentes: A, B, C+D (C por ruta `docker-compose.yml` y `nginx.conf`; D por ruta `worker.py`). `scope-check.py --base a3b4a55` exit 0 (20 en alcance). Contratos sin cambios; 34 herramientas. Lente A: resto de criterios ✓.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | CA-32 solo se cumple en `kairos` y `uvicorn.error`: FastMCP instala un handler de texto en root (`mcp.py:31`) y httpx, mcp, asyncio y psycopg salen en texto de varias líneas, con tracebacks y mensajes sin redactar (reproducido: DSN con secreto en claro) | T-30 | corregido (intento 2) | Lentes A (#1) y B (#2) |
| 2 | Important | Errores de proveedor invisibles en `/metrics`: los timeouts de embed en consulta nunca cuentan (el `asyncio.timeout(budget)` exterior vence antes, `retrieval.py:146,152`), y los errores del worker (extract y embed de documentos) son un contador de otro proceso; el spec (`spec.md:62`) pide derivarlos de la base al leer | T-31/T-32 | corregido (intento 2) | Lentes A (#2) y B (#1) |
| 3 | Minor | El modo `internal` decide por ausencia de cabeceras de proxy, no por origen; no hay decisión registrada frente a CA-30 y `operations.md:224` promete «desde `memory-data`» | T-33 | corregido (intento 2) | Lentes A (#4) y C (#1) |
| 4 | Minor | `/metrics` abre una conexión y hace `GROUP BY` sobre todo `memory.jobs` (sin purga ni índice con `destination`) en cada lectura, sin `statement_timeout` | T-31 | corregido (intento 2) | Lentes C (#2) y D (#3) |
| 5 | Minor | Si falla la base, `/metrics` sirve la última profundidad de cola sin estado que lo distinga | T-31 | corregido (intento 2) | Lente B (#4) |
| 6 | Minor | Las peticiones MCP se registran con `route='unmatched'`, como un 404 | T-30 | corregido (intento 2) | Lente B (#3) |
| 7 | Minor | El test de la ampliación del plazo (`test_metrics.py:223-235`) pasa sin el `reschedule` | T-32 | corregido (intento 2) | Lentes A (#3) y B (#5) |
| 8 | Minor | `_clean` corta a 200 caracteres antes de redactar: un token partido puede escapar a la redacción | T-30 | corregido (intento 2) | Lente B (fuera de lente, verificado en código) |
| 9 | Minor | El ledger reparte 18/27 tests entre `test_observability` y `test_metrics`; el código tiene 17/28 | T-30…T-33 | corregido (intento 2) | Lente A (#5) |

## Revisión de dos lentes — intento 2: Fase 7 (T-30…T-33) — correcciones del intento 1 (T-30, T-31, T-32, T-33)

Lentes: A+B+C+D en un solo revisor de contexto fresco. Gaps 1-9 del intento 1: ✓ cerrados (root con un único handler JSON; secretos en `%s`, dict y `password=` redactados; `provider_timeout` contado sin doble conteo; `kairos_jobs_failed` con cardinalidad acotada; contratos sin cambios, 34 herramientas; `pytest` 54 passed, `test_contract_additive` 8/8). Sin gaps Critical ni Important: la fase queda cerrada. Los Minor pasan como deuda a la Fase 8.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Minor | Con `MEMORY_LOG_LEVEL=DEBUG` los loggers de terceros (mcp) vuelcan argumentos de herramientas, consultas incluidas; `operations.md` no lo advierte (CWE-532) | T-30 | deuda aceptada → Fase 8 | Lente C, sonda |
| N2 | Minor | Las consultas del scrape leen todas las filas `failed` históricas (terminal, sin purga, `superseded` frecuente) sin índice con `destination`/`error_code`; si pasan de 2 s se pierde también la profundidad de cola; el texto dice «solo no terminales» | T-31 | deuda aceptada → Fase 8 | Lente D, estimación sin medir |
