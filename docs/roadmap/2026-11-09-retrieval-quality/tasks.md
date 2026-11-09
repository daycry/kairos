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
| Fase 3 — pgvector + HNSW (C-03 · P1) | 0 | 6 | 0% | 0 / 32h | 0 / 4,29h | 0 / 1,08h | 0 / 1290k |
| Fase 4 — FTS por idioma + trigram (C-05 · P4) | 0 | 6 | 0% | 0 / 27h | 0 / 3,61h | 0 / 0,91h | 0 / 1090k |
| Fase 5 — Troceado para embeddings (C-06 · P2) | 0 | 7 | 0% | 0 / 28h | 0 / 4h | 0 / 1h | 0 / 1200k |
| Fase 6 — Híbrida con degradación y CLI (C-04 · P3) | 0 | 4 | 0% | 0 / 12h | 0 / 1,6h | 0 / 0,4h | 0 / 470k |
| Fase 7 — Observabilidad (C-07 · P12) — en paralelo desde T-06 | 0 | 4 | 0% | 0 / 18h | 0 / 2,6h | 0 / 0,64h | 0 / 770k |
| Fase 8 — Integración, revisión y activación | 0 | 5 | 0% | 0 / 26h | 0 / 4,31h | 0 / 1,06h | 0 / 1280k |
| **TOTAL** | **6** | **38** | **15.8%** | **0 / 173h** | **0,20 / 26,03h** | **0 / 6,5h** | **0 / 7780k** |

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

**Notas**: Procedencia: spec CA-04, CA-05. Clase: refactor (la misma suite verde antes y después; API pública de `Store` intacta). Patrones: `store.py` es una única clase (1.030 líneas, `store.py:855`, `:922`, `:954`, `:964`); tests que parchean `_require` sobre la instancia (`patch.object(self.store,'_require')`) en `test_store.py` y `test_embeddings.py`.
- **Resultado (T-04)**: `test_store_surface` (3 tests) + `store_surface.json` (63 miembros, firmas incluidas). Recibo previo `testing/store-refactor-before.json` (corrección intento 1, gap 1): la MISMA puerta congelada `frozen-source-gate.py` (sin modificar) ejecutada sobre el árbol de `60be598` (`git archive 60be598`, montado en solo lectura, `--network=none`, imagen `kairos-test:rq`): en su primer nivel, código de `60be598` + `test_store_surface.py` + `store_surface.json` (misma suite que el recibo posterior): `KAIROS_FROZEN_SOURCE` source_sha256 `7480cded…f4d9`, file_count 140; `MEMORY_TEST_RESULT` tests 194, failures 0, errors 0, skipped 0, passed true. La ejecución pura de `60be598` (sin el test de superficie, inexistente entonces) queda en el bloque `pre_refactor_suite_at_60be598`: source_sha256 `af443668…68fb`, file_count 138, tests 191, 0/0/0. Reorganizado en la revisión de la Fase 2, intento 2 (gap 5), para que antes y después comparen la misma suite (194 = 194). `python -c "from memory_platform.store import Store, as_dict, canonical, digest, new_id, lexical_query, clean"` -> import-ok.
- **Nota sobre CA-04**: el criterio dice «177/177»; la suite real ya era 191 tras T-03 y con el test de superficie son 194. Criterio sin reescribir; se marca porque su intención (misma suite verde, 0 fallos, 0 omitidos, antes y después) se cumple con 194/194. La decisión sobre la redacción es del usuario.

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

**Notas**: Procedencia: spec CA-04…CA-06, decisión «Refactor de Store» (mixins). Clase: refactor. Nombres de módulos a criterio del implementador. Riesgo: orden de resolución de métodos y helpers privados compartidos. Patrón de composición: ya hay clases separadas `agent_store.py`/`extended_store.py`/`portal_store.py`; ningún mixin existente en el repo, no se inventa otro patrón que la herencia múltiple simple.
- **Resultado (T-05)**: `store.py` 30 líneas (fachada, `class Store(AuthMixin, IngestMixin, DocumentsMixin, GraphMixin, JobsMixin, VectorsMixin)` + reexport de `as_dict, canonical, clean, digest, lexical_query, new_id`). `wc -l memory_platform/store*.py` (salida literal, todos ≤ 400):
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

**Notas**: Procedencia: spec CA-04. Clase: refactor. La puerta congelada y su `frozen_evidence.py` son del plan 2026-11-06; solo se amplía la lista de ficheros. Desde esta tarea se pueden iniciar las tareas de la fase 7 (T-30…).
- **Resultado (T-06)**: `frozen-source-gate.py` NO se modifica: no tiene lista de ficheros, copia el árbol completo `memory_platform` (con `excluded` por nombre), así que los `store_*.py` entran solos en el manifiesto. Ejecutada tal cual en la imagen `kairos-test:rq` (`--network=none`, candidato en solo lectura): `KAIROS_FROZEN_SOURCE` source_sha256 `e21645f0…900b`, file_count 157, manifiesto con `store.py` + 7 `store_*.py`; `MEMORY_TEST_RESULT` 194 tests, 0 fallos, 0 errores, 0 omitidos. Recibo `testing/store-refactor-after.json` (regenerado en la corrección, mismo hash `e21645f0…900b`). Comparación previo/posterior con la misma suite: 194 = 194, 0 fallos, 0 omitidos (primer nivel del recibo previo: `60be598` + `test_store_surface.py` + `store_surface.json`, source_sha256 `7480cded…f4d9`, file_count 140). La ejecución pura de `60be598` (191 tests, `af443668…68fb`, 138) queda en el bloque `pre_refactor_suite_at_60be598`. Los 19 ficheros de diferencia de file_count entre el previo (138) y el posterior (157) son 9 de T-04/T-05 y 10 ficheros no versionados de `packages/kairos-cli/.npm-cache` presentes solo en el árbol de trabajo; `memory_platform` difiere solo en esos 9 y `store.py`.

---

## Fase 3 — pgvector + HNSW (C-03 · P1)

**Estado**: borrador · **Estimado**: 32h base (38.4h con margen) · **Real**: — · **Coste est.**: 1.920 € · **Tokens est.**: 1200k in / 90k out

### T-07 — Imagen PostgreSQL derivada con pgvector en compose y target `test`

- **Descripción**: Añadir al Dockerfile una etapa `postgres-pgvector` derivada de `postgres:17-bookworm@sha256:839fbb5a…` que instale `postgresql-17-pgvector` con versión fijada (≥ 0.8.0, a verificar con `apt-cache madison` en el digest), y usarla en `memory-postgres` (compose con `build:`) y como base del target `test` (y derivados `live-probe`, `lifecycle-test`). Resultado: producción y suite comparten binarios, con digest y versión de pgvector fijados.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,54h · real —
- **Supervisión**: est. 0,13h (≈25 % IA) · real —
- **Previsión IA**: 150k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-06
- **Tipo**: devops
- **Archivos**: `memory_platform/Dockerfile`, `docker-compose.yml`, `docs/roadmap/2026-11-09-retrieval-quality/testing/pgvector-version.txt`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker compose --profile memory config` → `memory-postgres` muestra `build` con target `postgres-pgvector`; `grep -n "postgres:17-bookworm@sha256" memory_platform/Dockerfile docker-compose.yml` → una sola declaración del digest (en el Dockerfile)
  - `docker run --rm --entrypoint psql kairos-pg:rq --version` y `docker run --rm kairos-pg:rq sh -c "ls /usr/share/postgresql/17/extension/vector.control /usr/share/postgresql/17/extension/unaccent.control /usr/share/postgresql/17/extension/pg_trgm.control"` → los tres ficheros existen
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (la suite de 177 sigue verde sobre la imagen nueva)

**Criterios de aceptación**
- [ ] CA-13: `memory-postgres` y el target `test` usan la misma base con digest `sha256` y pgvector con versión fijada; `docker compose config` lo muestra
- [ ] La versión de pgvector instalada es ≥ 0.8.0 y consta en `testing/pgvector-version.txt`
- [ ] `unaccent` y `pg_trgm` están disponibles en el digest fijado (supuesto ⚠️ verificar de la spec)
- [ ] Volumen existente compatible: misma versión mayor 17, sin `pg_upgrade`

**Subtareas**
- [ ] Verificar la versión disponible de `postgresql-17-pgvector` en PGDG para el digest y fijarla
- [ ] Crear la etapa `postgres-pgvector` y apuntar `test` a ella
- [ ] Cambiar `memory-postgres` a `build:` con la misma etapa
- [ ] Comprobar que `deploy-memory.py` sigue construyendo/arrancando `memory-postgres` (fase `database`)

**Notas**: Procedencia: spec CA-13, decisión P-01, riesgos R-01/R-02. Clase: cambio de infraestructura. Patrones: `docker-compose.yml:42` (imagen actual), `memory_platform/Dockerfile:24` (target `test`), digests fijados con `@sha256`. Alternativa descartada en la spec: imagen `pgvector/pgvector`. Pendiente verificar: privilegios para `CREATE EXTENSION vector` (R-03) — se comprueba en T-08.

### T-08 — Migración aditiva: extensión `vector`, `embedding`, `dims` y relleno

- **Descripción**: Añadir la versión de esquema siguiente (aditiva): `CREATE EXTENSION vector`, columna `embedding vector` y `dims` generada en `memory.embeddings`, relleno desde `vector double precision[]` y el índice HNSW parcial para `nomic-embed-text:768` (configurable con `MEMORY_VECTOR_INDEXES`). La columna original queda intacta. Resultado: base migrada sin pérdida, con hash por fila idéntico.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,67h · real —
- **Supervisión**: est. 0,17h (≈25 % IA) · real —
- **Previsión IA**: 190k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-07
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/config.py`, `memory_platform/admin.py`, `memory_platform/tests/test_pgvector_migration.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_pgvector_migration`: test en rojo antes de la migración)
  - `grep -nEi "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → ninguna coincidencia en las versiones nuevas (CA-34)

**Criterios de aceptación**
- [ ] CA-07: tras `python -m memory_platform.admin migrate` sobre una base con embeddings de 2 y 768 dims existe la extensión `vector` ≥ 0.8.0, todas las filas tienen `embedding` no nulo con `dims = array_length(vector,1)`, la columna `vector` es idéntica (hash por fila antes/después) y `memory.schema_versions` registra la versión nueva
- [ ] CA-34: la migración no contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE` y `content_manifest().sha256` es igual antes y después
- [ ] La migración falla antes de cambiar datos si la extensión no está disponible (transacción + bloqueo consultivo actuales)

**Subtareas**
- [ ] Escribir primero el test de migración sobre fixture con versión actual y embeddings de 2 y 768 dims
- [ ] Añadir la migración (extensión, columnas, relleno, índice HNSW parcial)
- [ ] Leer `MEMORY_VECTOR_INDEXES` (`nomic-embed-text:768` por defecto)
- [ ] Comprobar el rol del DSN de migración para `CREATE EXTENSION` y documentar el resultado (R-03)

**Notas**: Procedencia: spec CA-07, CA-34, decisiones P-01/P-02. Clase: cambio de comportamiento (test nuevo en rojo). Patrones: versiones aditivas con `INSERT INTO memory.schema_versions … ON CONFLICT DO NOTHING` en `memory_platform/schema.sql:21`, `:26`; columna actual `memory.embeddings` en `schema.sql:34-45`; `lock_timeout` ya usado en `schema.sql`. Los índices dentro de la transacción de `migrate` son aceptables por el volumen (21 documentos).

### T-09 — Búsqueda vectorial con HNSW, escaneo iterativo, ruta exacta y doble escritura

- **Descripción**: Reescribir `search_vectors`, `_vector_candidates` y `has_vectors` en `store_vectors.py` para usar el operador `<=>` de pgvector: HNSW con `hnsw.iterative_scan = relaxed_order`, `hnsw.max_scan_tuples = 20000`, `hnsw.ef_search = 100` por transacción para el modelo/dimensión indexados y ruta exacta SQL (tope 10.000) para el resto. Conservar permisos, versión vigente, hash, `deadline`/`statement_timeout`, `candidate_limit` y `candidates_truncated`. `complete_job` escribe `vector` y `embedding` en la misma fila.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 8h · real —
- **Tiempo IA (ejec.)**: est. 1,07h · real —
- **Supervisión**: est. 0,27h (≈25 % IA) · real —
- **Previsión IA**: 300k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-08
- **Tipo**: backend
- **Archivos**: `memory_platform/store_vectors.py`, `memory_platform/store_jobs.py`, `memory_platform/retrieval.py`, `memory_platform/config.py`, `memory_platform/tests/test_embeddings.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluidos los tests de `test_embeddings.py` sin cambiar sus aserciones, CA-09)
  - `docker build --target test …` ejecuta el nuevo `test_vector_search_paths` → paridad: mismo conjunto de ids que la ruta anterior en 2 dims (ruta exacta) y mismo top-k en 768 dims frente al coseno exacto

**Criterios de aceptación**
- [ ] CA-09: las pruebas existentes de `test_embeddings.py` pasan sin cambiar sus aserciones (sin permiso → `Forbidden`; borrados/sustituidos/hijos desfasados excluidos; otro modelo, dimensión distinta o vector cero → `[]`; filtros `categories`/`tags`)
- [ ] CA-10: con `deadline` vencido se lanza `semantic_deadline_exceeded` (503); con plazo corto se aplica `statement_timeout` (espía sobre `set_config`)
- [ ] CA-11: cada acierto conserva `candidate_limit` y `candidates_truncated`; con 2 dims usa ruta exacta y con > 10.000 candidatos `candidates_truncated = true`
- [ ] CA-12: `complete_job` rellena `vector` y `embedding` en la misma fila
- [ ] Paridad de resultados con la ruta actual en el fixture de 2 dims

**Subtareas**
- [ ] Escribir tests en rojo de rutas (ANN/exacta), doble escritura y `candidates_truncated`
- [ ] Implementar consulta ANN con escaneo iterativo y parámetros por transacción
- [ ] Implementar ruta exacta SQL para dimensiones/modelos no indexados
- [ ] Eliminar la consulta extra de `has_vectors` si es posible sin cambiar su semántica
- [ ] Doble escritura en `complete_job`

**Notas**: Procedencia: spec CA-09…CA-12, decisiones P-02, «Filtrado con ANN», «candidates_truncated». Clase: cambio de comportamiento que funciona (test en rojo + paridad con la ruta actual). Patrones: `store.py:922` (`_vector_candidates`), `:954` (`has_vectors`), `:964` (`search_vectors`), `:855-886` (`complete_job`); estados `backends.semantic` en `retrieval.py:97-146`. Se conserva la recomprobación final de autorización de `search_vectors`.

### T-10 — Pruebas de plan HNSW y recall frente al coseno exacto

- **Descripción**: Tests con ≥ 2.000 embeddings de 768 dims del modelo indexado: `EXPLAIN` demuestra el uso del índice HNSW y el top-10 coincide ≥ 95 % con el coseno exacto de referencia; test de filtrado (permisos/proyecto/versión) con escaneo iterativo; ajuste de `ef_search`/`max_scan_tuples` con la puerta `retrieval-eval`.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 7h · real —
- **Tiempo IA (ejec.)**: est. 0,94h · real —
- **Supervisión**: est. 0,24h (≈25 % IA) · real —
- **Previsión IA**: 260k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-09
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_vector_index.py`, `docs/roadmap/2026-11-09-retrieval-quality/testing/hnsw-recall.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_vector_index`)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → informe con la capa `semantic` sobre HNSW; ninguna capa empeora más de 2 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [ ] CA-08: el plan de `search_vectors` usa el índice HNSW y recall@10 ≥ 95 % frente al coseno exacto sobre las mismas filas
- [ ] El filtrado por permisos/proyecto/versión con ANN no pierde resultados por debajo del umbral (escaneo iterativo)
- [ ] Los parámetros finales (`ef_search`, `max_scan_tuples`) quedan documentados con su evidencia

**Subtareas**
- [ ] Generar 2.000 vectores deterministas de 768 dims en el fixture
- [ ] Test de `EXPLAIN` (el plan menciona el índice HNSW parcial)
- [ ] Test de recall@10 frente a la ruta exacta
- [ ] Afinar parámetros con la puerta `retrieval-eval` y guardar `hnsw-recall.json`

**Notas**: Procedencia: spec CA-08, riesgo R-04. Clase: cambio de comportamiento (test nuevo en rojo con la ruta exacta como oráculo). La puerta usa el proveedor simulado (mide mecánica, no calidad del modelo; la calidad real se mide en T-36).

### T-11 — Ensayo de despliegue y restauración en instancia aislada

- **Descripción**: En una instancia aislada con datos sintéticos (nunca la desplegada, volúmenes y nombre de proyecto propios), ejecutar `scripts/deploy-memory.py` con la imagen nueva hasta completar sus 10 fases, comprobar la copia de seguridad previa, `content_manifest().sha256` antes/después y la restauración de esa copia con `admin restore` en una instancia con pgvector (`store_fingerprints` idénticos). Resultado: evidencia de CA-14 sin tocar la base real.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,67h · real —
- **Supervisión**: est. 0,17h (≈25 % IA) · real —
- **Previsión IA**: 190k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-10
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `scripts/tests`, `docs/roadmap/2026-11-09-retrieval-quality/testing/deploy-rehearsal.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/deploy-memory.py --apply --project-name kairos-rehearsal …` (opciones de aislamiento a fijar en la tarea) → `status: ok`, las 10 fases en `phases`, backup presente
  - `python -m memory_platform.admin content-manifest` antes y después de migrar en la instancia de ensayo → mismo `sha256`
  - `docker volume ls --filter name=knowledge-graphs_memory` → los volúmenes reales siguen sin cambios (el ensayo usa volúmenes `kairos-rehearsal_*`)

**Criterios de aceptación**
- [ ] CA-14: las 10 fases completan con la imagen nueva, existe la copia previa y `content_manifest().sha256` es igual antes y después de migrar
- [ ] CA-14: restaurar la copia con `admin restore` en una instancia con pgvector produce `store_fingerprints` idénticos al origen
- [ ] Evidencia en `testing/deploy-rehearsal.json` sin secretos; el ensayo no usó los volúmenes `knowledge-graphs_memory-postgres-data` ni `knowledge-graphs_memory-backups`
- [ ] R-03 resuelto: queda anotado qué rol ejecuta `CREATE EXTENSION vector`

**Subtareas**
- [ ] Preparar el aislamiento (nombre de proyecto, volúmenes, secretos sintéticos, puertos) sin tocar los reales
- [ ] Sembrar datos sintéticos con la versión de esquema anterior
- [ ] Ejecutar el despliegue de ensayo y registrar fases y manifiestos
- [ ] Restaurar la copia en una segunda instancia y comparar `store_fingerprints`
- [ ] Destruir la instancia de ensayo y sus volúmenes

**Notas**: Procedencia: spec CA-14, riesgos R-01/R-02/R-03. Clase: verificación operativa (sin cambio de producto salvo ajustes mínimos de `deploy-memory.py` que lo hagan ensayable). Patrones: fases en `scripts/deploy-memory.py:23`, `VOLUMES` en `:22`, `compare_content` en `:67`; `admin.py` (`content_manifest`, `store_fingerprints`, `backup`/`restore`); tests de despliegue en `memory_platform/tests/test_deploy.py`. Restricción: nunca la base desplegada; si el aislamiento no se puede garantizar, se detiene y se informa. Requiere el motor Docker; ya hubo un bloqueo de acceso al motor el 2026-11-09 (`testing/activation.json`).

### T-12 — Procedimiento de retroceso y documentación operativa de pgvector

- **Descripción**: Documentar en `docs/operations.md` el retroceso asimétrico de la imagen (mantener la imagen nueva con código anterior, o restaurar la copia previa en la imagen antigua), el orden de fases del despliegue y los parámetros HNSW; ensayar el retroceso en la instancia aislada de T-11. Resultado: procedimiento verificado y escrito.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real —
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-11
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`, `docs/architecture.md`, `docs/roadmap/2026-11-09-retrieval-quality/testing/rollback-rehearsal.json`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `docs/operations.md` contiene las secciones «Retroceso de pgvector» y «Imagen PostgreSQL», con comandos y la advertencia de la asimetría (R-01)
  - `python scripts/build-handbook.py --check` (si el script admite `--check`; si no, `python scripts/build-handbook.py`) → sin error y sin enlaces rotos

**Criterios de aceptación**
- [ ] CA-14: el procedimiento de retroceso queda documentado en `docs/operations.md` y se ensayó en instancia aislada (evidencia en `testing/rollback-rehearsal.json`)
- [ ] `docs/configuration.md` documenta `MEMORY_VECTOR_INDEXES` y los parámetros `hnsw.*`
- [ ] `docs/architecture.md` describe pgvector, HNSW y la ruta exacta

**Subtareas**
- [ ] Ensayar el retroceso (código anterior con imagen nueva; restauración en imagen antigua) en la instancia aislada
- [ ] Escribir las secciones de `operations.md`, `configuration.md` y `architecture.md`

**Notas**: Procedencia: spec CA-14, CA-36, riesgo R-01. Clase: documentación. Patrón: tono y estructura de `docs/operations.md` existente; manuales con capturas generados por `scripts/build-handbook.py` según el commit abb40be.

---

## Fase 4 — FTS por idioma + trigram (C-05 · P4)

**Estado**: borrador · **Estimado**: 27h base (32.4h con margen) · **Real**: — · **Coste est.**: 1.620 € · **Tokens est.**: 1000k in / 90k out

### T-13 — Migración FTS: `unaccent`, `pg_trgm`, columnas es/en e índices

- **Descripción**: Versión de esquema aditiva: extensiones `unaccent` y `pg_trgm`, envoltorio `IMMUTABLE` de `unaccent`, columnas FTS es y en (generadas en `documents`; calculadas en la inserción y rellenadas en `memory_items` y en las tablas de agente/corpus con `search_vector`), índices GIN y trigram. Las columnas `search_vector` `simple` se conservan.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,67h · real —
- **Supervisión**: est. 0,17h (≈25 % IA) · real —
- **Previsión IA**: 185k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-12
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/tests/test_fts_migration.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_fts_migration`: test en rojo antes de la migración)
  - `grep -nEi "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → ninguna coincidencia en las versiones nuevas (CA-34)

**Criterios de aceptación**
- [ ] CA-22: existen las columnas e índices nuevos, `search_vector` `simple` sigue presente y consultable, y tras migrar el recuento de filas con la columna FTS nueva nula es 0 en cada tabla afectada
- [ ] CA-34: sin `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE`; `content_manifest().sha256` igual antes y después
- [ ] El envoltorio de `unaccent` es `IMMUTABLE` y las columnas generadas se crean sin error (riesgo de la evaluación)

**Subtareas**
- [ ] Test en rojo sobre fixture con datos previos
- [ ] Escribir migración (extensiones, envoltorio, columnas, GIN, trigram)
- [ ] Relleno de filas existentes y comprobación de nulos
- [ ] Anotar el bloqueo por reescritura de tabla (R-06) y su `lock_timeout`

**Notas**: Procedencia: spec CA-22, CA-34, decisión P-03. Clase: cambio (test nuevo en rojo). Patrones: FTS actual en `memory_platform/schema.sql:13` y `:27-31`; versiones aditivas en `schema.sql:21`, `:26`. Dependencia técnica real solo de T-06/T-07; se secuencia tras T-12 por el orden recomendado y para no solapar ediciones de `schema.sql`.

### T-14 — Consultas léxicas de `Store` con configuración es/en

- **Descripción**: Adaptar los puntos de consulta de `store_documents.py`/`store_graph.py` (antes `store.py:342`, `:437`, `:533-535`, `:572-579`, `:734`) y las dos inserciones para calcular las columnas nuevas; consulta = OR de las configuraciones es, en y simple, con rango = máximo. Resultado: «configuracion cancion» encuentra «configuración de las canciones» y «deploying fails» encuentra «deployment failed».
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 8h · real —
- **Tiempo IA (ejec.)**: est. 1,07h · real —
- **Supervisión**: est. 0,27h (≈25 % IA) · real —
- **Previsión IA**: 295k in / 25k out tok · ⚠️ verificar €
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `memory_platform/store_documents.py`, `memory_platform/store_graph.py`, `memory_platform/store_ingest.py`, `memory_platform/store_common.py`, `memory_platform/tests/test_store.py`, `memory_platform/tests/test_native.py`, `memory_platform/tests/test_fts_language.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_fts_language` con CA-19 y CA-20 en rojo antes del cambio)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → los subconjuntos de idioma mejoran ≥ 15 puntos de recall@5 respecto de `baseline.json` en las capas léxicas

**Criterios de aceptación**
- [ ] CA-19: «configuracion cancion» devuelve el documento con «configuración de las canciones» en el top-5 de la capa `documental`
- [ ] CA-20: «deploying fails» devuelve la memoria «deployment failed» en el top-5 de la capa `episodic`
- [ ] CA-23 (hechos nativos): `search_native_facts` usa la configuración nueva; test con consulta sin tilde que antes no encontraba el elemento
- [ ] Las consultas existentes con la configuración `simple` siguen devolviendo lo mismo (suite verde)

**Subtareas**
- [ ] Escribir tests en rojo (CA-19, CA-20, hechos nativos)
- [ ] Calcular columnas en la inserción de `memory_items` y documentos
- [ ] Reescribir consultas con OR de las tres configuraciones
- [ ] Verificar sin regresión en `test_store.py` y `test_native.py`

**Notas**: Procedencia: spec CA-19, CA-20, CA-23, decisión P-03. Clase: cambio (test nuevo en rojo con consulta sin tilde/derivada). Patrones: `store.py:523-536` (`search_items`), `:560-585` (`search_documents`), `:720-737` (`search_native_facts`), `lexical_query` reexportada. Tras T-05 estas funciones viven en los mixins; las rutas de arriba se leen en el mixin correspondiente. Riesgo: el stemming puede bajar la precisión en identificadores (se conserva `simple` y se añade trigram en T-17).

### T-15 — Búsquedas de corpus de agente y respuestas de corpus en es/en

- **Descripción**: Aplicar la configuración nueva a `agent_store.py` (3 consultas) y `corpus_answers.py` (1) con sus escrituras de columna. Resultado: cada punto de llamada encuentra elementos con consultas sin tilde que antes fallaban.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0,8h · real —
- **Supervisión**: est. 0,2h (≈25 % IA) · real —
- **Previsión IA**: 220k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `memory_platform/agent_store.py`, `memory_platform/corpus_answers.py`, `memory_platform/tests/test_agent_tools.py`, `memory_platform/tests/test_corpus_answers.py`, `memory_platform/tests/test_fts_language.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye un test en rojo por punto de llamada)

**Criterios de aceptación**
- [ ] CA-23: un test por cada punto de llamada de `agent_store.py` (213, 329-331, 366) y `corpus_answers.py` (180-181) con una consulta sin tilde que antes no encontraba el elemento
- [ ] Las búsquedas con la configuración `simple` anterior siguen devolviendo los mismos aciertos en los tests existentes

**Subtareas**
- [ ] Un test en rojo por punto de llamada
- [ ] Adaptar las cuatro consultas y las escrituras asociadas
- [ ] Comprobar `test_agent_tools.py` y `test_corpus_answers.py` sin cambios en sus aserciones

**Notas**: Procedencia: spec CA-23, decisión P-03. Clase: cambio (test nuevo en rojo con consulta sin tilde). Patrones: `agent_store.py:213`, `:329-331`, `:366`; `corpus_answers.py:180-181`.

### T-16 — Filtros del portal con la configuración nueva (solo backend)

- **Descripción**: Adaptar los cinco filtros de texto de `portal_store.py` (líneas 42-79) a la configuración es/en/simple. No cambia ninguna interfaz de usuario: el cambio es solo de backend y de consulta, sin tocar `web/`.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real —
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `memory_platform/portal_store.py`, `memory_platform/tests/test_portal_collections.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye test en rojo con consulta sin tilde en un filtro del portal)

**Criterios de aceptación**
- [ ] Cada uno de los cinco filtros de `portal_store.py` encuentra el elemento con consulta sin tilde/derivada (decisión P-03: el portal también pasa a la configuración nueva)
- [ ] `test_portal_collections.py` pasa sin cambiar aserciones previas
- [ ] Ningún fichero de la interfaz web modificado (`git diff --stat` solo en `memory_platform/`)

**Subtareas**
- [ ] Test en rojo por filtro
- [ ] Adaptar las consultas de `portal_store.py:42-79`

**Notas**: Procedencia: decisión P-03 (alcance del portal incluido; +3 h respecto de la evaluación base). Clase: cambio (test nuevo en rojo). Sin UI: no requiere `test-plan.md`. Patrón: `portal_store.py:42-79`.

### T-17 — Respaldo `pg_trgm` y fusión de rangos

- **Descripción**: Cuando el FTS devuelve menos de `limit`, completar con coincidencias por similitud `pg_trgm` sobre títulos e identificadores (`similarity_threshold` 0,3) y fusionar rangos sin duplicados. Resultado: «pg_advisroy_lock» encuentra una memoria con `pg_advisory_xact_lock`.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real —
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-14
- **Tipo**: backend
- **Archivos**: `memory_platform/store_documents.py`, `memory_platform/store_graph.py`, `memory_platform/store_common.py`, `memory_platform/tests/test_fts_language.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye CA-21 en rojo antes del cambio)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → el subconjunto de errores tipográficos/identificadores mejora ≥ 15 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [ ] CA-21: buscar «pg_advisroy_lock» devuelve la memoria con `pg_advisory_xact_lock` en el top-5 por el respaldo trigram
- [ ] El respaldo solo se ejecuta cuando el FTS devuelve menos de `limit`, sin duplicar aciertos
- [ ] El umbral de similitud (0,3) se confirma o ajusta con la puerta `retrieval-eval` y queda registrado

**Subtareas**
- [ ] Test en rojo (CA-21)
- [ ] Implementar respaldo y fusión sin duplicados
- [ ] Ajustar umbral con C-01 y anotar el valor final

**Notas**: Procedencia: spec CA-21, decisión P-03. Clase: cambio (test nuevo en rojo con consulta con errores). Patrón: fusión RRF y estados de capa en `retrieval.py:97-146`.

### T-18 — Verificación integrada de FTS por idioma

- **Descripción**: Ejecutar la suite y la puerta de evaluación tras toda la fase 4 y registrar el avance frente a la línea base. Resultado: fase 4 cerrada con evidencia de que no hay regresión en ningún subconjunto.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,27h · real —
- **Supervisión**: est. 0,07h (≈25 % IA) · real —
- **Previsión IA**: 75k in / 5k out tok · ⚠️ verificar €
- **Dependencias**: T-14, T-15, T-16, T-17
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-09-retrieval-quality/testing/phase4-eval.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0`
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → informe `phase4-eval.json`: ningún subconjunto empeora más de 2 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [ ] CA-22/CA-23 comprobados en la suite completa (0 fallos, 0 omitidos)
- [ ] La mejora del subconjunto idioma y errores es visible en el informe frente a la línea base

**Subtareas**
- [ ] Ejecutar suite y puerta
- [ ] Guardar el informe en `testing/`

**Notas**: Procedencia: spec CA-22, CA-23, CA-35 (parcial). Clase: verificación de fase.

---

## Fase 5 — Troceado para embeddings (C-06 · P2)

**Estado**: borrador · **Estimado**: 28h base (33.6h con margen) · **Real**: — · **Coste est.**: 1.680 € · **Tokens est.**: 1100k in / 100k out

### T-19 — Troceador por párrafos/encabezados con solape

- **Descripción**: Crear `memory_platform/chunking.py`: función pura que divide `title + content` en fragmentos de ~1.500 caracteres con solape de 200 (`MEMORY_CHUNK_CHARS`, `MEMORY_CHUNK_OVERLAP`, máximo `MEMORY_CHUNK_MAX` = 200) respetando párrafos y encabezados, y devuelve `ordinal`, `char_start`, `char_end`. Resultado: cobertura total sin huecos, comprobada por test.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,57h · real —
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-18
- **Tipo**: backend
- **Archivos**: `memory_platform/chunking.py`, `memory_platform/config.py`, `memory_platform/tests/test_chunking.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunking` en rojo antes de crear el módulo)

**Criterios de aceptación**
- [ ] CA-24 (parte pura): los intervalos `[char_start, char_end)` de un documento de 50.000 caracteres cubren todo el texto sin huecos y con el solape configurado, y los `ordinal` son consecutivos
- [ ] Un documento de 200.000 caracteres produce ≤ 200 fragmentos
- [ ] Texto corto (< tamaño de fragmento) produce un único fragmento

**Subtareas**
- [ ] Tests en rojo (cobertura, solape, tope, texto corto)
- [ ] Implementar el troceador
- [ ] Añadir los tres parámetros a `config.py`

**Notas**: Procedencia: spec CA-24, decisión P-07 (1.500/200). Clase: cambio (test nuevo en rojo con documento largo). Patrón de configuración: `memory_platform/config.py` (`MEMORY_EMBED_*`). Parámetros ajustables con C-01.

### T-20 — Tabla `memory.embedding_chunks` e índice HNSW parcial

- **Descripción**: Migración aditiva de la tabla `memory.embedding_chunks` (`ordinal`, `char_start`, `char_end`, `vector`/`embedding`, modelo, hash e identidad del recurso) con HNSW parcial como en T-08, sin tocar la clave primaria de `memory.embeddings`.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,43h · real —
- **Supervisión**: est. 0,11h (≈25 % IA) · real —
- **Previsión IA**: 120k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-19, T-08
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/tests/test_chunk_schema.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunk_schema`)
  - `grep -nEi "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → ninguna coincidencia en las versiones nuevas (CA-34)

**Criterios de aceptación**
- [ ] La tabla existe tras `admin migrate` con claves y borrado coherentes con `memory.embeddings`
- [ ] CA-34: migración sin operaciones destructivas; `content_manifest().sha256` sin cambios
- [ ] El índice HNSW parcial solo cubre el modelo y la dimensión configurados

**Subtareas**
- [ ] Test de esquema en rojo
- [ ] Escribir la migración
- [ ] Comprobar migración idempotente

**Notas**: Procedencia: spec CA-24, CA-34, decisión «Troceado». Clase: cambio (test nuevo en rojo). Patrón: `memory.embeddings` en `memory_platform/schema.sql:34-45`.

### T-21 — Worker y proveedor: embeddings por lotes dentro del plazo del job

- **Descripción**: Cambiar `worker.py:47-52` y `providers.py` para troceo + embebido por lotes (`/api/embed` con varias entradas) acotados al plazo del job (lease 120 s); un fallo en el fragmento k de n falla el job completo. Resultado: documentos de 200.000 caracteres caben en el plazo sin romper el semáforo de 1 petición.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0,86h · real —
- **Supervisión**: est. 0,21h (≈25 % IA) · real —
- **Previsión IA**: 235k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-19
- **Tipo**: backend
- **Archivos**: `memory_platform/worker.py`, `memory_platform/providers.py`, `memory_platform/tests/test_worker.py`, `memory_platform/tests/test_providers.py`, `memory_platform/tests/test_jobs.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye nuevos casos de lotes, plazo y fallo parcial en rojo antes del cambio)

**Criterios de aceptación**
- [ ] CA-27 (parte worker): si el proveedor falla en el fragmento k de n, el job falla o reintenta según `max_attempts` y no se entrega ningún resultado parcial al almacén
- [ ] El proveedor envía lotes acotados (tamaño y plazo por lote configurables) y respeta el semáforo existente
- [ ] Los tests existentes de `test_worker.py`, `test_providers.py` y `test_jobs.py` pasan sin cambiar aserciones previas

**Subtareas**
- [ ] Tests en rojo (lotes, plazo, fallo parcial)
- [ ] Implementar `embed_many` en `providers.py`
- [ ] Adaptar el worker al troceo y a los lotes

**Notas**: Procedencia: spec CA-27, riesgo R-05. Clase: cambio (test en rojo). Patrones: `memory_platform/worker.py:47-52` (texto `[:8000]`), `providers.py` (`Embeddings.embed`, una entrada por petición, `truncate: True`).

### T-22 — `complete_job` transaccional con todos los fragmentos

- **Descripción**: Guardar en `complete_job` el vector del elemento (compatibilidad) y todos los fragmentos con su posición en una única transacción, con los recibos actuales. Resultado: nunca quedan fragmentos parciales de una versión.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,43h · real —
- **Supervisión**: est. 0,11h (≈25 % IA) · real —
- **Previsión IA**: 120k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-20, T-21
- **Tipo**: backend
- **Archivos**: `memory_platform/store_jobs.py`, `memory_platform/store_vectors.py`, `memory_platform/tests/test_jobs.py`, `memory_platform/tests/test_chunk_jobs.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunk_jobs`: CA-27 en rojo antes del cambio)

**Criterios de aceptación**
- [ ] CA-27: con fallo en el fragmento k de n no queda ningún fragmento de esa versión guardado y el job queda en reintento o fallido según `max_attempts`
- [ ] La escritura de elemento y fragmentos es atómica (un único commit)
- [ ] Los tests de `test_jobs.py` pasan sin cambios en sus aserciones

**Subtareas**
- [ ] Test en rojo de atomicidad
- [ ] Extender `complete_job` y los recibos
- [ ] Prueba de reintento con `max_attempts`

**Notas**: Procedencia: spec CA-27, decisión «Fallo de proveedor a mitad del troceado». Clase: cambio (test nuevo en rojo). Patrón: `store.py:855-886` (`complete_job`, embeddings).

### T-23 — Búsqueda agregada por elemento con `matched_chunk` y `excerpt`

- **Descripción**: Hacer que la capa semántica busque sobre fragmentos, agregue por elemento con la puntuación del mejor fragmento y devuelva el campo opcional `matched_chunk` (`ordinal`, `char_start`, `char_end`); `excerpt` usa el texto del fragmento ganador. Los aciertos sin fragmento omiten el campo y `ref` no cambia de formato. Resultado: un dato más allá de 8.000 caracteres se recupera.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,71h · real —
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-22, T-09
- **Tipo**: backend
- **Archivos**: `memory_platform/store_vectors.py`, `memory_platform/retrieval.py`, `memory_platform/models.py`, `memory_platform/tests/test_embeddings.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/tests/test_chunk_search.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_chunk_search`: CA-24/25/26 en rojo antes del cambio)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → el subconjunto documento largo mejora ≥ 15 puntos de recall@5 frente a `baseline.json`

**Criterios de aceptación**
- [ ] CA-24: documento de 50.000 caracteres con frase única hacia el carácter 40.000 → su búsqueda semántica lo devuelve en el top-3 con el `matched_chunk.ordinal` del fragmento que la contiene
- [ ] CA-25: un elemento aparece una sola vez aunque coincidan varios fragmentos, con la puntuación del mejor
- [ ] CA-26: tras publicar una versión nueva no se devuelven fragmentos de la anterior
- [ ] Los aciertos sin fragmento omiten `matched_chunk`

**Subtareas**
- [ ] Tests en rojo con documento largo (dato más allá de 8.000 caracteres)
- [ ] Agregar por elemento en SQL
- [ ] Añadir `matched_chunk` opcional a `Hit` y al ensamblado
- [ ] Usar el texto del fragmento en `excerpt`

**Notas**: Procedencia: spec CA-24…CA-26, decisión «Señal del fragmento». Clase: cambio (test nuevo en rojo con documento largo con dato más allá de 8.000 caracteres). Patrones: `retrieval.py:97-146` y `:191-208`; `models.py:143-152`, `:178-189` (`Hit`).

### T-24 — Relleno idempotente de fragmentos y su integración en `deploy-memory.py`

- **Descripción**: Añadir `admin backfill-chunks`, que encola jobs `embed` solo para recursos vigentes sin fragmentos (segunda ejecución encola 0), y llamarlo desde `scripts/deploy-memory.py` tras `migrate` (decisión P-07), con progreso visible. Además cubre el relleno de vectores `embedding` si T-08 dejó filas pendientes.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,43h · real —
- **Supervisión**: est. 0,11h (≈25 % IA) · real —
- **Previsión IA**: 120k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-22
- **Tipo**: devops
- **Archivos**: `memory_platform/admin.py`, `scripts/deploy-memory.py`, `memory_platform/tests/test_admin.py`, `memory_platform/tests/test_deploy.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye test de idempotencia y un caso de `test_deploy.py` que verifica la llamada en la fase correspondiente)

**Criterios de aceptación**
- [ ] CA-28: el relleno encola jobs `embed` solo para recursos vigentes sin fragmentos; ejecutarlo dos veces encola 0 la segunda
- [ ] `deploy-memory.py` ejecuta el relleno tras `migrate` y registra su resultado en el informe de despliegue (sin secretos)
- [ ] El modo de simulación (`--apply` ausente) solo imprime el plan e incluye el relleno

**Subtareas**
- [ ] Test en rojo de idempotencia
- [ ] Implementar el subcomando de `admin`
- [ ] Integrar en la fase `bootstrap`/`migrate` de `deploy-memory.py` y actualizar `PHASES`/informe si procede

**Notas**: Procedencia: spec CA-28, decisión P-07. Clase: cambio (test nuevo en rojo). Patrones: fases en `scripts/deploy-memory.py:23`, `Deployment.apply` (`:137`) y `operator()` (`:127`), `test_deploy.py`. Evita sobrecarga de Ollama: relleno en lotes del worker (R-05).

### T-25 — Contrato aditivo `matched_chunk` y pruebas de contrato

- **Descripción**: Reflejar `matched_chunk` como campo opcional en `docs/contracts/kairos-mcp.json` y OpenAPI mediante `scripts/export-contracts.py` y comprobar con un diff aditivo que las 34 herramientas MCP siguen intactas.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,57h · real —
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-23
- **Tipo**: backend
- **Archivos**: `scripts/export-contracts.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/tests/test_mcp.py`, `memory_platform/tests/test_contract_additive.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_contract_additive`)
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → solo adiciones (el test confirma 0 eliminadas/cambiadas) y `python -c "import json;print(len(json.load(open('docs/contracts/kairos-mcp.json'))['tools']))"` → `34` (clave del contrato a confirmar al implementar)

**Criterios de aceptación**
- [ ] CA-29: `matched_chunk` aparece como opcional en el contrato exportado y los aciertos sin fragmento lo omiten
- [ ] CA-33: sigue habiendo 34 herramientas y el diff solo contiene adiciones (0 herramientas, campos o valores por defecto eliminados o cambiados)

**Subtareas**
- [ ] Test aditivo (compara contra el contrato del commit base)
- [ ] Regenerar contratos
- [ ] Ajustar `test_mcp.py` si procede sin cambiar aserciones previas

**Notas**: Procedencia: spec CA-29, CA-33, riesgo R-09. Clase: cambio. Patrón: `scripts/export-contracts.py`, contrato existente `"default": true` de `semantic`.

---

## Fase 6 — Híbrida con degradación y CLI (C-04 · P3)

**Estado**: borrador · **Estimado**: 12h base (14.4h con margen) · **Real**: — · **Coste est.**: 719 € · **Tokens est.**: 430k in / 40k out

### T-26 — Degradación probada y campo opcional `degraded`

- **Descripción**: Fijar con tests la degradación (proveedor 503/plazo/sin vectores/`semantic=false`) por HTTP y MCP para `search` y `context`, y añadir el campo opcional `degraded` en `backends`/respuesta cuando solo falla la capa semántica (se mantiene `partial` con su semántica actual). Resultado: la respuesta léxica es siempre válida y el cliente distingue una degradación de un fallo.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real —
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-25
- **Tipo**: backend
- **Archivos**: `memory_platform/retrieval.py`, `memory_platform/models.py`, `memory_platform/mcp.py`, `memory_platform/tests/test_retrieval.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_mcp.py`, `docs/contracts/kairos-mcp.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye CA-15, CA-16, CA-17 y el caso `degraded` en rojo antes del cambio)

**Criterios de aceptación**
- [ ] CA-15: sin `semantic` y con vectores, `backends.semantic.status = 'ok'` y hay al menos un acierto solo semántico fusionado con los léxicos
- [ ] CA-16: con el proveedor devolviendo 503 o excediendo el plazo, `search` y `context` (HTTP y MCP) responden con léxicos, `backends.semantic.status = 'unavailable'`, `degraded` presente y tiempo ≤ `embedding_query_timeout` + 1 s
- [ ] CA-17: con `semantic=false`, `status = 'off'` y 0 llamadas al proveedor
- [ ] CA-33: `degraded` es opcional y el contrato solo gana el campo

**Subtareas**
- [ ] Tests en rojo de degradación y `degraded`
- [ ] Implementar el campo sin alterar `partial`
- [ ] Regenerar contrato con `scripts/export-contracts.py`

**Notas**: Procedencia: spec CA-15…CA-17, decisión P-04. Clase: cambio (test en rojo de degradación y campo `degraded`). Hallazgo de la evaluación: `semantic` ya es `True` por defecto (`models.py:146`, `:181`; `mcp.py:150`, `:160`), por eso la tarea es de endurecimiento. Patrón: estados `partial`/`unavailable`/`off` en `retrieval.py:113`, `:129`, `:146`.

### T-27 — Ajuste de la fusión RRF con la puerta de evaluación

- **Descripción**: Con los datos de la puerta `retrieval-eval` tras las fases 3-5, comprobar y, si lo justifica la medida, ajustar `k=60` y los pesos por capa en `retrieval.py`. Resultado: el MRR de `fused` ≥ el de la mejor capa individual, en conjunto y por subconjunto.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0,4h · real —
- **Supervisión**: est. 0,1h (≈25 % IA) · real —
- **Previsión IA**: 110k in / 10k out tok · ⚠️ verificar €
- **Dependencias**: T-26, T-03
- **Tipo**: backend
- **Archivos**: `memory_platform/retrieval.py`, `memory_platform/tests/retrieval_eval/thresholds.json`, `docs/roadmap/2026-11-09-retrieval-quality/testing/fusion-tuning.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile .` → pasa los umbrales (`fused` recall@5 ≥ 0,80, MRR ≥ 0,60) y el MRR de `fused` ≥ mejor capa individual
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0`

**Criterios de aceptación**
- [ ] CA-18: en `retrieval-eval` el MRR de `fused` es ≥ el de la mejor capa individual, en conjunto y por subconjunto
- [ ] Cualquier cambio de `k` o pesos queda justificado en `testing/fusion-tuning.json` con el antes y el después
- [ ] Sin cambios de la fusión si la medida no los justifica (se registra igualmente)

**Subtareas**
- [ ] Ejecutar la puerta y analizar capas
- [ ] Probar variantes de fusión solo si hay evidencia
- [ ] Registrar resultado en `testing/`

**Notas**: Procedencia: spec CA-18, decisión P-06. Clase: cambio (test en rojo en la puerta si la fusión empeora). Patrón: fusión RRF `k=60` en `retrieval.py:97-146`.

### T-28 — Documentar `backends`, `degraded` y la semántica de `candidates_truncated`

- **Descripción**: Describir en `docs/architecture.md` e `docs/integration.md` los estados de `backends.semantic`, el campo `degraded`, `matched_chunk` y la nueva semántica de `candidates_truncated` (tope de candidatos en ruta exacta o `max_scan_tuples` en ANN).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0,27h · real —
- **Supervisión**: est. 0,07h (≈25 % IA) · real —
- **Previsión IA**: 70k in / 5k out tok · ⚠️ verificar €
- **Dependencias**: T-26
- **Tipo**: docs
- **Archivos**: `docs/architecture.md`, `docs/integration.md`, `docs/en/architecture.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: ambos manuales describen `status` ∈ {ok, partial, unavailable, off}, `degraded`, `matched_chunk` y `candidates_truncated` con los valores del contrato
  - `python scripts/build-handbook.py` → sin errores

**Criterios de aceptación**
- [ ] Los manuales coinciden con el contrato regenerado (CA-36)
- [ ] Se documenta que el CLI usa `semantic: true` desde la versión nueva

**Subtareas**
- [ ] Redactar secciones
- [ ] Regenerar el manual

**Notas**: Procedencia: spec CA-36, decisión «candidates_truncated». Clase: documentación. Se comprueba si existe `docs/en/` antes de editarlo; si no existe, se omite sin crearlo.

### T-29 — CLI: `semantic: true` en el contexto automático y versión sin publicar

- **Descripción**: Cambiar `packages/kairos-cli/lib/dispatcher.mjs:84` a `semantic: true`, tolerar el campo `degraded` en la respuesta, actualizar tests y subir la versión del paquete (0.3.0) en `package.json` con su entrada de changelog. NO publicar en npm (cuenta del publicador bloqueada, F-06 abierta).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,53h · real —
- **Supervisión**: est. 0,13h (≈25 % IA) · real —
- **Previsión IA**: 145k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-26
- **Tipo**: frontend
- **Archivos**: `packages/kairos-cli/lib/dispatcher.mjs`, `packages/kairos-cli/package.json`, `packages/kairos-cli/tests/dispatcher.test.mjs`, `packages/kairos-cli/tests/lifecycle.test.mjs`, `packages/kairos-cli/README.md`, `docs/release-cli.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `node --test packages/kairos-cli/tests/dispatcher.test.mjs` → todos pasan, incluido el caso `semantic: true` en el contexto automático y el manejo de `degraded`
  - `grep -n "semantic: true" packages/kairos-cli/lib/dispatcher.mjs && grep -n "\"version\"" packages/kairos-cli/package.json` → ocurrencia en la línea del contexto automático y versión nueva
  - `git status --short packages/kairos-cli` → solo cambios de código/versión; ningún `npm publish` ejecutado (lectura: historial de comandos del cierre)

**Criterios de aceptación**
- [ ] Decisión P-04: el contexto automático del CLI usa `semantic: true` y no falla si la respuesta trae `degraded`
- [ ] La versión del paquete sube a la siguiente menor (0.3.0) y no se publica en npm
- [ ] Latencia: con el proveedor lento el contexto automático no excede `embedding_query_timeout` (10 s) más 1 s

**Subtareas**
- [ ] Test en rojo del caso `semantic: true`
- [ ] Cambiar el despachador
- [ ] Subir versión y documentar en `docs/release-cli.md` el bloqueo de publicación
- [ ] Ejecutar tests del paquete

**Notas**: Procedencia: decisión P-04, riesgo de latencia de la evaluación. Clase: cambio (test en rojo). Patrón: `packages/kairos-cli/lib/dispatcher.mjs:84` (`layers: ['episodic','documental'], semantic: false, limit: 5, max_chars: 5000`). La publicación queda para cuando se desbloquee la cuenta (ver `docs/roadmap/2026-11-06-functional-parity/tasks.md`, F-06).

---

## Fase 7 — Observabilidad (C-07 · P12) — en paralelo desde T-06

**Estado**: borrador · **Estimado**: 18h base (21.6h con margen) · **Real**: — · **Coste est.**: 1.080 € · **Tokens est.**: 700k in / 70k out

### T-30 — Logging JSON con redacción y `request_id`

- **Descripción**: Crear `memory_platform/observability.py` con un formateador JSON de una línea (`ts`, `level`, `event`, y en búsquedas `request_id`, `layer`, `duration_ms`) que reutiliza `privacy.py` para redactar secretos, e instalarlo en `memory-api` y `memory-worker`.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,72h · real —
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-06
- **Tipo**: backend
- **Archivos**: `memory_platform/observability.py`, `memory_platform/app.py`, `memory_platform/worker.py`, `memory_platform/privacy.py`, `memory_platform/tests/test_observability.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_observability` con CA-32 en rojo antes de crear el módulo)

**Criterios de aceptación**
- [ ] CA-32: los logs de `memory-api` y `memory-worker` son JSON de una línea con `ts`, `level`, `event` y, en búsquedas, `request_id`, `layer`, `duration_ms`; los secretos sintéticos aparecen redactados
- [ ] Un `request_id` se propaga de la petición a los logs de sus capas
- [ ] No se registra la consulta ni el contenido, solo duraciones y códigos

**Subtareas**
- [ ] Test en rojo (formato, redacción, request_id)
- [ ] Implementar formateador y contexto de petición
- [ ] Instalar en API y worker

**Notas**: Procedencia: spec CA-32, decisión P-05, riesgo R-08. Clase: capacidad nueva (test nuevo en rojo). Patrones: redacción en `memory_platform/privacy.py` y `scripts/deploy-memory.py:31` (`redact_output`); `grep` de `logging` en `memory_platform/*.py` vacío (sin patrón previo).

### T-31 — Registro de métricas Prometheus con `prometheus_client` fijado

- **Descripción**: Añadir `prometheus_client` fijado en `requirements.txt` y el registro de métricas: histograma `kairos_retrieval_layer_seconds{layer}`, contador `kairos_provider_errors_total{provider,code}` y gauge `kairos_jobs_queue_depth{state,destination}` calculado desde `memory.jobs` al servir `/metrics`, con etiquetas de valores cerrados.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0,72h · real —
- **Supervisión**: est. 0,18h (≈25 % IA) · real —
- **Previsión IA**: 195k in / 20k out tok · ⚠️ verificar €
- **Dependencias**: T-30
- **Tipo**: backend
- **Archivos**: `memory_platform/observability.py`, `memory_platform/requirements.txt`, `memory_platform/tests/test_metrics.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye `test_metrics`: formato y etiquetas en rojo antes del cambio)
  - `grep -n "prometheus_client==" memory_platform/requirements.txt` → versión exacta fijada

**Criterios de aceptación**
- [ ] Las tres métricas se registran con los nombres y etiquetas del spec CA-30
- [ ] Las etiquetas solo toman valores cerrados (capas, proveedores, códigos, estados); ninguna lleva ids de proyecto, consultas o credenciales
- [ ] La profundidad de cola refleja `memory.jobs` en el momento de la lectura

**Subtareas**
- [ ] Tests en rojo del registro
- [ ] Implementar métricas y consulta de cola
- [ ] Fijar versión de `prometheus_client`

**Notas**: Procedencia: spec CA-30, CA-31, decisión P-05, riesgo R-08. Clase: capacidad nueva (test nuevo en rojo). Varios procesos uvicorn exigirían modo multiproceso: hoy es uno solo (se comprueba en `memory_platform/app.py`).

### T-32 — Instrumentación de capas, proveedores y worker

- **Descripción**: Instrumentar `Retrieval.search` (latencia por capa), `providers.py` (errores por código) y el worker (duración y errores de jobs). Resultado: cada búsqueda emite latencia por capa a logs y métricas.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,58h · real —
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: backend
- **Archivos**: `memory_platform/retrieval.py`, `memory_platform/providers.py`, `memory_platform/worker.py`, `memory_platform/tests/test_metrics.py`, `memory_platform/tests/test_retrieval.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye casos de instrumentación en rojo antes del cambio)

**Criterios de aceptación**
- [ ] CA-30 (contenido): tras una búsqueda, `kairos_retrieval_layer_seconds` tiene muestras para las capas ejecutadas
- [ ] Un fallo del proveedor incrementa `kairos_provider_errors_total` con su `code`
- [ ] La instrumentación no cambia respuestas ni orden de resultados (suite verde)

**Subtareas**
- [ ] Tests en rojo
- [ ] Envolver las capas en `Retrieval.search`
- [ ] Contar errores en `providers.py`
- [ ] Instrumentar el worker

**Notas**: Procedencia: spec CA-30, CA-32. Clase: capacidad nueva (test nuevo en rojo). Patrón: capas en `memory_platform/retrieval.py:97-146`.

### T-33 — Endpoint `/metrics` solo en red interna y ajuste de despliegue

- **Descripción**: Servir `GET /metrics` (`text/plain; version=0.0.4`) en `memory-api` con `MEMORY_METRICS=internal` (valores `off`/`internal`/`admin`), sin publicarlo por nginx en 5173 y sin exponer puerto nuevo en `docker-compose.yml`; rechazar peticiones que lleguen por el proxy público. Resultado: métricas accesibles solo desde `memory-data`.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0,58h · real —
- **Supervisión**: est. 0,14h (≈25 % IA) · real —
- **Previsión IA**: 155k in / 15k out tok · ⚠️ verificar €
- **Dependencias**: T-31, T-32
- **Tipo**: devops
- **Archivos**: `memory_platform/app.py`, `memory_platform/config.py`, `memory_platform/nginx.conf`, `memory_platform/Caddyfile.example`, `docker-compose.yml`, `memory_platform/tests/test_metrics.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .` → la salida contiene `MEMORY_TEST_RESULT` con `"passed": true`, `failures: 0`, `errors: 0`, `skipped: 0` (incluye CA-30/CA-31 en rojo antes del cambio, con `TestClient`)
  - `grep -n "metrics" memory_platform/nginx.conf memory_platform/Caddyfile.example` → el proxy bloquea `/metrics` (`return 404` o equivalente)
  - `docker compose --profile memory config | grep -c "8790:"` → sin puerto nuevo publicado para la API

**Criterios de aceptación**
- [ ] CA-30: desde fuera de la red interna (cabecera de proxy público) se rechaza; con acceso interno responde 200 `text/plain; version=0.0.4` con las tres métricas
- [ ] CA-31: con una consulta y un token sintéticos en búsquedas, ninguno aparece en `/metrics` ni en los logs
- [ ] `MEMORY_METRICS=off` desactiva la ruta (404)
- [ ] `/metrics` no se publica en nginx 5173

**Subtareas**
- [ ] Tests en rojo (acceso y fuga de datos)
- [ ] Implementar la ruta y los tres modos
- [ ] Bloquear `/metrics` en `nginx.conf` y `Caddyfile.example`
- [ ] Documentar `MEMORY_METRICS` en `docs/configuration.md`

**Notas**: Procedencia: spec CA-30, CA-31, decisión P-05 (solo red interna, `MEMORY_METRICS=internal`). Clase: capacidad nueva (test nuevo en rojo). Patrones: ajustes de entorno en `memory_platform/config.py`, redes `memory-data` y publicación de `memory-web` en `docker-compose.yml`, `memory_platform/nginx.conf`.

---

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

## Revisión de dos lentes — intento 1: Fase 1 (T-01…T-03) (T-01, T-02, T-03)

Lentes: A+B+C (C por ruta `memory_platform/Dockerfile`). Base `1d43523` + cambios sin commitear. `scope-check.py --base 1d43523` → exit 0 (15/15 en alcance).

**Veredicto por criterio (Lente A):** T-01 ✓ (CA-01, datos sintéticos, umbrales, verificación reproducida) · T-02 ✓ con salvedades (CA-01, CA-03; desviación de la Verificación 2 aceptada) · T-03 ✓ (CA-02, hash congelado, puerta fuera de la suite).

**Resultado: 4 gaps Important (corrección obligatoria) y 6 Minor.** T-02 y T-03 vuelven a `en-progreso`.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | La guarda de DSN se salta con parámetros de consulta de libpq (`?host=`, `?hostaddr=`, `?dbname=`, `?service=`, puerto sin comprobar); por CLI, `_setup` migraría e insertaría un actor admin con contraseña fija en esa base (CWE-20 → CWE-798). Lentes B y C | T-02 | corregido: `check_dsn` resuelve con `conninfo_to_dict`, exige host/hostaddr loopback, puerto 55432, `memory_test` y solo claves permitidas (`run.py` `check_dsn`); tests con `?host=`, `?hostaddr=`, `?dbname=`, `?service=`, puerto distinto | `run.py:80-82`; reproducido por B con `conninfo_to_dict` → `{'host':'db.example.com','dbname':'kairos'}` y `guard passed` |
| 2 | Important | La evaluación descarta `backends`/`partial`: una capa caída se mide como recall 0 sin rastro y la puerta solo falla por umbral (o pasaría si las demás capas alcanzan el umbral). Lente B | T-02, T-03 | corregido: `query_backends` por consulta/capa en el informe y clave estructural; `backend_unavailable:<capa>` en `evaluate_gate`; test con capa que lanza excepcion | `run.py:149-154,177-179`; sonda de B con `search_items` lanzando excepción → episodic 0, fused idéntico a la línea base, sin aviso |
| 3 | Important | El proveedor simulado hashea palabras completas, pero la subtarea de T-02 pide «vector estable por hash de n-gramas»; la capa semántica simulada no puede ayudar a `typo_id`. Lente B (fuera de lente, requisito) | T-02 | corregido: `fake_embeddings.py` hashea palabras y trigramas de caracteres (SHA-256); linea base regenerada, dataset intacto | `fake_embeddings.py:30-37` frente a la subtarea de T-02 |
| 4 | Important | La puerta acepta un subconjunto con recall@5 ≥ 0,80 **o** ganancia ≥ 15; P-06 (spec, decisiones confirmadas) exige +15 puntos de recall@5 en es/typo_id/long. Lente A | T-03 | corregido: ganancia obligatoria junto a los umbrales absolutos; README y tests | `run.py:72`; spec «Decisiones confirmadas» punto 6 |
| 5 | Minor | `run.py` carga el dataset sin validarlo (`expected: []` → `ZeroDivisionError`; id mal escrito → fallo silencioso). Lente B | T-02 | corregido: `load_dataset` valida con `check_dataset.validate` | `run.py:85-87,158,160`; `recall_at_k(['a'],[],5)` → `ZeroDivisionError` |
| 6 | Minor | La ganancia se calcula contra una línea base sin comprobar que su `dataset_sha256` coincida con el del informe. Lente B | T-03 | corregido: `baseline_dataset_mismatch` si los hashes difieren | `run.py:186-192` |
| 7 | Minor | El recibo declara `network: none` como constante; el `docker build` tiene red por defecto. Lente A | T-02 | corregido: `network` se observa (`reachable`/`unreachable`); verificado con `docker run --network=none`; `docker build --network=none` no viable (falla `apt-get` de capas previas); documentado | `run.py:177`; `Dockerfile:47-50` |
| 8 | Minor | Textos del ledger y comentario del Dockerfile siguen diciendo «177»; la suite tiene 183 (177 + 6 de `test_metrics`). Lentes A y B | T-03 | corregido: 186 (177 + 9 de `test_metrics`) en Dockerfile y ledger | `Dockerfile:48`; criterio de T-03 |
| 9 | Minor | No hay test de `STRUCTURAL_KEYS`/`deterministic`; los «dos builds idénticos» no tienen salida pegada. Lente A | T-02 | corregido: `test_determinism_flag_compares_the_structural_keys` | `run.py:191,198-199`; `tasks.md` evidencia de T-02 |
| 10 | Minor | Faltan las combinaciones `episodic×long` y `documental×typo_id` (inherente al diseño de dataset-v1, congelado). Lente A | T-01 | deuda aceptada (no se toca) | `run.py:158-159`; `dataset-v1.jsonl` q-049…q-060 |


## Revisión de dos lentes — intento 2: Fase 1 (T-01…T-03) (T-01, T-02, T-03)

Lentes: A+B+C (C por ruta `memory_platform/Dockerfile`). Traspaso de la tabla del intento 1; solo se re-evaluó lo corregido.

**Corregidos y verificados:** gaps 1 (parámetros de consulta), 2, 3, 4, 6 y 8 del intento 1. Gap 10: deuda aceptada.

**Resultado: 2 gaps Important y 5 Minor.** T-02 y T-03 vuelven a `en-progreso`. Siguiente: intento 3 de 3.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | La guarda de DSN supone `hostaddr=127.0.0.1` si el DSN no lo trae, pero libpq aplica `PGHOSTADDR` del entorno y redirige la conexión con la guarda superada (mismo impacto que el gap 1 del intento 1). Lentes B (Important) y C (Minor); arbitraje: Important, porque reabre el gap 1 | T-02 | corregido: la guarda rechaza `PGHOSTADDR`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGSERVICE`, `PGSERVICEFILE`, `PGSYSCONFDIR` en el entorno y la conexion fija `hostaddr=127.0.0.1` (`connect_dsn`); docstring exacto; tests por variable | `run.py:118`; sonda B/C en `kairos-test:rq`: `PGHOSTADDR=10.9.9.9` → conecta a `10.9.9.9:55432` |
| 2 | Important | La validación del dataset al cargar (gap 5 del intento 1) no se ejecuta: `load_dataset` está definida dos veces y la segunda, sin validar, anula la primera; el ledger y el README afirman lo contrario. Lentes A, B y C | T-02 | corregido: eliminada la `load_dataset` duplicada; valida con `check_dataset.validate`; tests con `expected: []` e id inexistente -> `SystemExit` | `run.py:122-134`; dataset con `expected: []` aceptado sin `SystemExit` |
| 3 | Minor | `network_state()` abre TCP a un tercero (1.1.1.1:53) en cada build con red, dos veces por ejecución; además da falsos `unreachable` tras un cortafuegos y puede romper el determinismo. Arbitraje: se sustituye por una observación local sin contacto externo. Lentes B y C | T-02 | corregido: `network_observation()` lista `/sys/class/net` (sin conexion), una vez por ejecucion, fuera de `STRUCTURAL_KEYS`; el recibo dice lo observado | `run.py:34-40,242` |
| 4 | Minor | La documentación ordena `docker build --network=none`, que no es viable (falla `apt-get`). Lente A | T-02, T-03 | corregido: README y Dockerfile documentan `docker build --target test` + `docker run --network=none ...` y la advertencia sobre `docker build --network=none` | `testing/README.md:9-13`; `Dockerfile:49`; `tasks.md:129` |
| 5 | Minor | La evidencia posterior a la corrección de T-03 no sale de su Verificación 1 (`docker build --target retrieval-eval`). Lente A | T-03 | corregido: Verificacion 1 (`docker build --target retrieval-eval`) ejecutada tras las correcciones; salida en el ledger de T-03 | `tasks.md:167` frente a `:176` |
| 6 | Minor | Ningún test distingue el proveedor de n-gramas de uno de palabras completas. Lente A | T-02 | corregido: test de errata frente a palabra distinta (coseno) | `test_metrics.py:92-97` |
| 7 | Minor | El ledger conserva `network: none` y la afirmación de «dos builds idénticos» sin salida pegada. Lente A | T-02 | corregido: textos `network: none` actualizados; dos ejecuciones independientes comparadas por hash (identicas) | `tasks.md:89,107,120` |


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


## Revisión de dos lentes — intento 1: Fase 2 (T-04…T-06) (T-04, T-05, T-06)

Lentes: A+B+C+D (C por ruta `store_auth.py` y contenido `sql-fstring`; D por contenido `n-plus-one` en `store_auth.py`). Base `60be598`. `scope-check.py --base 60be598` → exit 0.

**Lentes B, C y D: sin defectos.** 63 miembros de `Store` y 6 helpers idénticos por AST y bytecode; sin nombres sin definir (pyflakes), sin sombreado por MRO, sin imports circulares; SQL parametrizado igual que antes; ninguna consulta ni conexión nueva. Los N+1 de `list_users`/`list_keys` y la f-string SQL de `store_documents.py:96` son preexistentes e idénticos al original: no son gaps de este diff.

**Resultado: 1 gap Important y 3 Minor.** T-04 y T-06 vuelven a `en-progreso`.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | CA-04 de la spec pide «recibo de la puerta congelada en ambos momentos»; el recibo previo sale de `docker build --target test`, sin `source_sha256` ni bloque de la puerta congelada, así que nada lo liga al árbol anterior al refactor. Lente A | T-04, T-06 | corregido: recibo previo regenerado con la puerta congelada sin modificar sobre `git archive 60be598` (source_sha256 `af443668…68fb`, 138 ficheros, 191 tests verdes) y posterior sobre el árbol actual (`e21645f0…900b`, 157 ficheros, 194 verdes); además la misma suite de 194 sobre `60be598` + test de superficie (`7480cded…f4d9`, 194 verdes) para el «mismo recuento» literal; `testing/store-refactor-before.json` | `testing/store-refactor-before.json:1-14`; `spec.md:137` |
| 2 | Minor | Subtarea «Ajustar el manifiesto de `frozen-source-gate.py`» marcada `[x]` sin hacerse (la puerta copia el árbol entero y no necesitaba cambio). Lente A | T-06 | corregido: `ledger-lint` rechaza `completado` con subtareas sin marcar, así que se deja `[x]` con la nota «no necesario: la puerta copia el árbol entero (`frozen-source-gate.py:45-48`)»; texto sin reescribir | `tasks.md:288,292` |
| 3 | Minor | El `wc -l` pegado no es literal (`store_common 37`; el fichero tiene 36). Lente A | T-05 | corregido: `wc -l memory_platform/store*.py` pegado con su salida literal (store_common 36) en T-05 | `tasks.md:262` |
| 4 | Minor | Los criterios de T-04/T-05 dicen «177/177» y se marcan con 194. Lente A | T-04, T-05 | descartado (rebatido): la spec CA-04 dice «177/177 o el recuento vigente» (`spec.md:137`); el criterio no se reescribe y la nota del implementador lo explica | `spec.md:137`; `tasks.md:220,250` |


## Revisión de dos lentes — intento 2: Fase 2 (T-04…T-06) (T-04, T-05, T-06)

Lentes: A (solo evidencias y ledger cambiaron; el código de `memory_platform/` es el mismo que B, C y D aprobaron en el intento 1). Traspaso de la tabla del intento 1.

**Gaps 1-3 del intento 1: corregidos y verificados** (tres hashes de la puerta congelada reproducidos: `af443668…68fb` 138, `e21645f0…900b` 157, `7480cded…f4d9` 140; `scope-check` sin criterios alterados).

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 5 | Important | La Verificación planificada de T-06 se reescribió (de `a['tests']==b['tests']` → `True 0 0` a `b['tests']-a['tests']` → `3 0 0`) para encajar con un recibo previo de 191 tests, contradiciendo el criterio «mismo recuento». Lente A | T-06 | corregido por el orquestador: Verificación original restaurada; el recibo previo pasa a tener en su primer nivel el código de 60be598 con la misma suite (194, `source_sha256` `7480cded…f4d9`) y conserva la ejecución pura de 60be598 (191) en `pre_refactor_suite_at_60be598`. El comando original da `True 0 0` | `tasks.md` Verificación de T-06; `testing/store-refactor-before.json` |


## Revisión de dos lentes — intento 3: Fase 2 (T-04…T-06) (T-04, T-05, T-06)

Lentes: A (solo evidencias y ledger cambiaron). Traspaso de las tablas de los intentos 1 y 2.

**Gap 5 del intento 2: corregido y verificado** (Verificación de T-06 idéntica a la base salvo la nota; ejecutada → `True 0 0`; hashes `7480cded…f4d9` 140, `af443668…68fb` 138 y `e21645f0…900b` 157 reproducidos; `scope-check --base 60be598` sin criterios alterados).

**Resultado: sin gaps pendientes.** Fase 2 cerrada en revisión.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 6 | Minor | La prosa de evidencia de T-04 y T-06 seguía describiendo el recibo previo con 191 tests en el primer nivel y citaba un bloque `same_suite_on_pre_refactor_tree` que ya no existe. Lente A | T-04, T-06 | corregido por el orquestador: los Resultados de T-04 y T-06 describen el primer nivel (194, `7480cded…f4d9`) y el bloque `pre_refactor_suite_at_60be598` (191, `af443668…68fb`) | `tasks.md`, Resultados de T-04 y T-06 |

