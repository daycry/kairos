---
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
  # ventana compartida con improvement-plan.md
verificacion: obligatoria   # cada T-XX lleva `- **Verificación**:`; lo exige ledger-lint (exit 1 si falta)
test-plan: n/a (sin UI)
---

# Checklist de Tareas — Operación fiable (Iniciativa 3 de Kairos)

| | |
|---|---|
| **Estado** | en-progreso |
| **Fecha** | 2026-11-15 |
| **Plan** | [`improvement-plan.md`](./improvement-plan.md) |
| **Diseño** | n/a |

> **⚠️ Ledger canónico de progreso.** Este fichero es la **fuente única de verdad** del avance del plan. **Cualquier** implementador —el agente `implementer`, el chat principal, o un orquestador SDD externo— **debe** marcar aquí cada tarea (checkbox + estado) al completarla y actualizar el resumen. Los ledgers propios de otras herramientas son **espejo**, no fuente.

> **Cifras.** Por tarea, las horas humanas, IA y supervisión son **base** (sin margen); las filas de fase y el resumen llevan el **+20 %** ya aplicado. Cada tarea y **cada intento de revisión** abre y cierra `usage-meter` y anota su JSON en `Notas`. La comprobación de tests es siempre `docker build -f server/memory_platform/Dockerfile --target test .` (imprime `MEMORY_TEST_RESULT`; línea base 764). Cada fase termina con su suite completa en verde y subiendo `KAIROS_MIN_TESTS`/`MIN_FLOOR`, y con su revisión adversarial como tarea propia. El implementer no escribe en `docs/roadmap/**/testing/` (reservado a `qa`): las evidencias van al ledger o junto a los tests.

> **Restricciones duras (valen para todas las tareas).** Nada contra la base desplegada ni contenedores, volúmenes o redes `knowledge-graphs-*`; nada contra el Ollama del host (puerto 11434); migraciones solo aditivas (ninguna con `DELETE`); el contrato MCP solo crece y se declara a la Iniciativa 7; `store_surface.json` congelado; Docker en primer plano y de uno en uno; ensayos con `scripts/deploy-memory.py --project-name <x>` (nombres propios, nunca `knowledge-graphs`); ninguna credencial ni clave privada en el repositorio ni en una imagen; no se modifican ficheros que monta la instalación desplegada (`ollama-proxy/default.conf.template`, etc.) salvo que la tarea lo declare, y los cambios de `docker-compose.yml` solo los recoge la instalación en su próximo `up` (Iniciativa 5): ninguna tarea recrea servicios reales. EOL conservado (`.gitattributes` es `* -text`).

> **Dependencia externa (no es tarea):** los dos PR (T-53 hito A, T-95 hito B) solo se abren con el OK expreso del usuario; no se hacen merges ni se publica nada.

---

## Resumen de progreso

| Fase | Completadas | Total | Progreso | H. humanas (real/est) | H. IA ejec. (real/est) | Supervisión (real/est) | Tokens (real/est) |
|------|------------|-------|----------|-----------------------|------------------------|------------------------|-------------------|
| Fase 1 — Arnés de fallos y tests de límites (C-07) | 6 | 6 | 100% | 0 / 32.4h | 0.83 / 4.3h | 0 / 1.1h | 0 / 1080 k |
| Fase 2 — Worker resistente a la caída de base (C-02, B-03) | 7 | 7 | 100% | 0 / 27.0h | 2.10 / 3.6h | 0 / 0.9h | 0 / 900 k |
| Fase 3 — Cola: índices parciales y retención de tablas (C-02, B-06) | 7 | 7 | 100% | 0 / 27.0h | 0.99 / 3.6h | 0 / 0.9h | 0 / 900 k |
| Fase 4 — Pool y plazos de conexión (C-03, B-02 y B-07) | 9 | 9 | 100% | 0 / 48.0h | 0 / 6.4h | 0 / 1.6h | 0 / 1600 k |
| Fase 5 — Permisos por transacción (C-03, B-02) | 5 | 5 | 100% | 0 / 24.0h | 0 / 3.2h | 0 / 0.8h | 0 / 800 k |
| Fase 6 — Copias locales: integridad, cifrado, retención y verificación (C-01) | 9 | 9 | 100% | 0 / 43.2h | 0 / 5.8h | 0 / 1.4h | 0 / 1440 k |
| Fase 7 — Copia externa programada y runbook de restauración (C-01) | 6 | 6 | 100% | 0 / 28.8h | 0 / 3.8h | 0 / 1.0h | 0 / 960 k |
| Fase 8 — Cierre del hito A: no perder datos ni parar | 4 | 4 | 100% | 0 / 7.2h | 1.06 / 1.0h | 0 / 0.2h | 0 / 240 k |
| Fase 9 — Compose: límites, healthchecks, rotación y `extra_hosts` (C-04) | 7 | 7 | 100% | 0 / 19.8h | 0.27 / 2.6h | 0 / 0.7h | 0 / 660 k |
| Fase 10 — Despliegue: bloqueo, etiquetado y retroceso (C-04) | 5 | 7 | 71.4% | 0 / 34.2h | 1.18 / 4.6h | 0 / 1.1h | 0 / 1140 k |
| Fase 11 — Sonda de ida y vuelta (C-06) | 0 | 6 | 0% | 0 / 23.4h | 0 / 3.1h | 0 / 0.8h | 0 / 780 k |
| Fase 12 — Cola atascada, servicio de sonda y `kairos doctor` (C-06) | 0 | 7 | 0% | 0 / 23.4h | 0 / 3.1h | 0 / 0.8h | 0 / 780 k |
| Fase 13 — Abstención: señal absoluta, parámetro y contratos (C-05) | 0 | 6 | 0% | 0 / 33.6h | 0 / 4.5h | 0 / 1.1h | 0 / 1120 k |
| Fase 14 — Calibración de la abstención y puerta `retrieval-eval` (C-05) | 0 | 7 | 0% | 0 / 33.6h | 0 / 4.5h | 0 / 1.1h | 0 / 1120 k |
| Fase 15 — Cierre del hito B: desplegar y detectar | 0 | 2 | 0% | 0 / 2.4h | 0 / 0.3h | 0 / 0.1h | 0 / 80 k |
| Fase 16 — Cierre de la iniciativa: ensayo, CHANGELOG y versión 0.4.1 | 0 | 3 | 0% | 0 / 4.8h | 0 / 0.6h | 0 / 0.2h | 0 / 160 k |
| **TOTAL** | **65** | **98** | **66.3%** | **0 / 412.8h** | **6.43 / 55.0h** | **0 / 13.8h** | **0 / 13760 k** |

> **Imputación externa opcional.** El adaptador elegido recibe las mediciones disponibles y aplica su contrato de jornada, supervisión e idempotencia. No inventes tiempo real ni recalcules horas fuera de su dueño; sin integración los datos permanecen locales.

---

## Fase 1 — Arnés de fallos y tests de límites (C-07)

**Estado**: completado · **Hito**: A · **Estimado**: 32.4h (27.0h base, de ellas 9.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.620 € · **Tokens est.**: 1080 k

### T-01 — Arnés `FaultProxy`: proxy TCP cortable delante del PostgreSQL efímero

- **Descripción**: Crear un proxy TCP en proceso que se interpone entre el código y el PostgreSQL efímero y permite cortar, restaurar y dejar «mudo» el destino por orden explícito (sin esperas). Es el oráculo de C-02 y C-03. Fuente: CA-34; B-15.
- **Changelog**: Interno: arnés de pruebas que corta, restaura o silencia la conexión con la base para probar caídas; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 4.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.60h (estimado) · real 0.06h (medido)
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 166 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/fault_proxy.py`, `server/memory_platform/tests/test_fault_proxy.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_fault_proxy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `FaultProxy` ofrece `cut()`, `restore()` y `mute()` deterministas (sin `sleep` para esperar un estado) y se cierra limpio en `tearDown`
- [x] Una consulta por el proxy tras `cut()` falla con `psycopg.OperationalError` y tras `restore()` vuelve a funcionar
- [x] Una conexión por el proxy en modo `mute()` acepta y no responde (base de CA-17)
- [x] No abre puertos fuera de `127.0.0.1` ni toca recursos `knowledge-graphs-*`

**Subtareas**
- [x] Escribir primero `test_fault_proxy.py` (rojo: no existe el módulo)
- [x] Implementar `FaultProxy` con hilos y `threading.Event`
- [x] Probar corte, restauración, modo mudo y cierre
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/run_postgres.py:30-31` (PostgreSQL efímero en `127.0.0.1:55432`, `MEMORY_TEST_DSN`) y `tests/llm_spy.py` / `tests/chain_services.py` (servidores en proceso con `.start()`/`.stop()`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `b58b78130691`.

### T-02 — Tests de `body_too_large`, `/v1/users`, `/health/ready` y `work_budget_exceeded`

- **Descripción**: Añadir pruebas que fallan si se retira el control: 413 `body_too_large`, `/v1/users` (permitido, sin permiso, ajeno), `/health/ready` (listo y no listo) y 409 `work_budget_exceeded`. Fuente: CA-35; B-15.
- **Changelog**: Interno: pruebas que fallan si se quita el límite de cuerpo, el permiso de usuarios, la comprobación de disponibilidad o el presupuesto de trabajo; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 0.27h (medido)
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_api_limits.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_api_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Cada uno de los cuatro controles tiene al menos una prueba positiva y una negativa en `test_api_limits.py`
- [x] Mutante comprobado por prueba: quitar el control (límite de cuerpo, comprobación de permiso de `/v1/users`, sondeo de `/health/ready`, presupuesto de trabajo) deja la prueba en rojo; la evidencia va en `Notas`
- [x] `/v1/users` cubre «permitido», «sin permiso» y «usuario ajeno»

**Subtareas**
- [x] Escribir las pruebas primero
- [x] Aplicar cada mutante en memoria y anotar el rojo
- [x] Dejar el código de producción intacto
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `app.py:36` (`body_too_large`), `agent_store.py:186` (`work_budget_exceeded`), `tests/test_observability.py:216` (caso 503 de `/health/ready` ya existente: se reutiliza el estilo, no se duplica). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2fefc0633626`.

### T-03 — Tests de esquema por catálogo y comportamiento, no por texto SQL

- **Descripción**: Sustituir los tests que trocean `schema.sql` por marcador o comparan texto SQL por comprobaciones sobre el catálogo (`information_schema`, `pg_indexes`) o el comportamiento, sin bajar el recuento. Fuente: CA-36; B-15.
- **Changelog**: Interno: las pruebas de migración parten de un esquema histórico fijo y comprueban el catálogo en vez de trocear el texto de schema.sql, así añadir índices no las rompe.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 6h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.80h (estimado) · real 0.49h (medido)
- **Supervisión**: est. 0.20h (≈25 % IA) · real —
- **Previsión IA**: 221 k in / 19 k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_chunk_schema.py`, `server/memory_platform/tests/test_fts_migration.py`, `server/memory_platform/tests/test_pgvector_migration.py`, `server/memory_platform/tests/test_migrations_additive.py`, `server/memory_platform/tests/schema_history.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_chunk_schema|test_fts_migration|test_pgvector_migration|test_migrations_additive|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Ningún test de la lista depende de un marcador de texto de `schema.sql` para construir la «versión anterior»; usa catálogo o aplica las versiones por la API de migración
- [x] El recuento de la suite no baja respecto de 764 (línea base de la iniciativa) y los casos sustituidos conservan su intención
- [x] `test_migrations_additive.py` sigue fallando si una migración contiene `DROP`/`DELETE` (mutante comprobado)
- [x] Los equivalentes que localice el recorrido (`grep -n "schema.sql" tests/*.py`) están en la lista de `Archivos` o se declaran fuera de alcance con motivo

**Subtareas**
- [x] Inventariar con `grep` los tests que leen `schema.sql` (hoy cuatro; `test_chunk_schema.py:13` los trocea por marcador)
- [x] Reescribir cada uno contra catálogo/comportamiento
- [x] Comprobar el recuento antes y después
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/test_chunk_schema.py:13-21` (`SCHEMA`, «schema.sql exactly as the previous release left the database»), `tests/test_fts_migration.py:11`, `tests/test_pgvector_migration.py:12`, `tests/test_migrations_additive.py:12-19` (`MIGRATION_SOURCES`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `cba1f3f0139e`.

### T-04 — Pruebas de concesión expirada y ayudante para caducarla

- **Descripción**: Dejar caracterizado el comportamiento actual de reclamo con concesión expirada (sin cambiarlo) y un ayudante `expire_lease` en el arnés, que usarán C-02 (trabajo venenoso, CA-12) y los tests de base caída. Fuente: CA-34 (concesión expirada y trabajo venenoso); B-15.
- **Changelog**: Interno: pruebas de caracterización del reclamo con concesión expirada y un ayudante para caducarla sin esperas; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real 0.07h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_job_leases.py`, `server/memory_platform/tests/fault_proxy.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_job_leases|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Hay pruebas de que un trabajo `running` con concesión expirada se reclama de nuevo y se cuenta un intento (comportamiento actual, `store_jobs.py:92`, `:105`)
- [x] `expire_lease(store, job_id)` caduca la concesión sin esperas reales
- [x] Las pruebas no cambian código de producción

**Subtareas**
- [x] Escribir las pruebas de caracterización
- [x] Añadir `expire_lease` al arnés
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/test_jobs.py` (reclamo y reintento) y `store_jobs.py:89-192`. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `4487d9fca4a6`.

### T-05 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: el mínimo de pruebas que exige la integración continua sube a 806; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real 0.07h (medido)
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 18 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-03, T-02, T-04
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `085447c72270`.

### T-06 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Superficie: el arnés no debe poder tocar bases fuera del PostgreSQL efímero. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 1; endurece los tests nuevos, sin cambios para quien usa Kairos.
- **Estado**: completado
- **Tiempo humano**: est. 9h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.20h (estimado) · real — (los revisores no tienen medición propia; constan en la telemetría de los subagentes)
- **Supervisión**: est. 0.30h (≈25 % IA) · real —
- **Previsión IA**: 331 k in / 29 k out tok · ⚠️ verificar €
- **Dependencias**: T-05
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Cerrada en el intento 2 de 3 (secciones «Revisión de dos lentes — intento 1/2» al final del ledger y `review.md`). Lentes: intento 1, A+B+C+D; intento 2, A+B. `scope-check.py --base be001a4` exit 0; suite 806 en verde (Notas de T-05). Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 2 — Worker resistente a la caída de base (C-02, B-03)

**Estado**: completado · **Hito**: A · **Estimado**: 27.0h (22.5h base, de ellas 7.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.350 € · **Tokens est.**: 900 k

### T-07 — Clase `StoreUnavailable` y clasificación de errores de base

- **Descripción**: Introducir `StoreUnavailable` para `psycopg.OperationalError`/`InterfaceError` (y, más adelante, agotamiento del pool) y un clasificador que distinga «la base no responde» de «el proveedor falló». Fuente: CA-10, CA-11; B-03.
- **Changelog**: Una base de datos que no responde se distingue ya de un fallo del proveedor: el error de base se señala aparte, sin dirección ni contraseña.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.20h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/errors.py`, `server/memory_platform/store.py`, `server/memory_platform/tests/test_store_unavailable.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_unavailable|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `StoreUnavailable` y un `is_store_unavailable(exc)` cubren `OperationalError`, `InterfaceError` y cortes de conexión a mitad de consulta con el `FaultProxy`
- [x] Un error de proveedor (`provider_error`) nunca se clasifica como base no disponible, y al revés (prueba de ambos caminos)
- [x] El mensaje registrado nunca incluye el DSN ni la contraseña

**Subtareas**
- [x] Escribir primero las pruebas con `FaultProxy` (rojo)
- [x] Implementar clase y clasificador
- [x] Probar la redacción del DSN
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `errors.py` (jerarquía de errores del servidor) y `store.py:24-30` (único punto de `psycopg.connect`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `5d4f52fd580e`.

### T-08 — Reclamo resiliente: espera exponencial con jitter y `MEMORY_WORKER_DB_BACKOFF_MAX`

- **Descripción**: Meter `claim_job` dentro del control de errores de `run_once`/`run` con espera exponencial con jitter y tope (`MEMORY_WORKER_DB_BACKOFF_MAX`, 60 s); registrar `store_unavailable` sin DSN y seguir vivo. El `Worker` expone el instante del último acceso correcto a la base (lo usa el latido en la Fase 9). Fuente: CA-10; B-03.
- **Changelog**: El worker ya no muere cuando la base de datos se cae: espera con pausas crecientes (hasta MEMORY_WORKER_DB_BACKOFF_MAX, 60 s por defecto), lo registra como store_unavailable y retoma la cola al volver.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real 0.36h (medido)
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-07
- **Tipo**: backend
- **Archivos**: `server/memory_platform/worker.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_worker_db_down.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_worker_db_down|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Con la base cortada, `Worker.run()` no termina tras N reclamos fallidos (prueba con `FaultProxy`, reloj y espera inyectados)
- [x] Las esperas crecen con jitter y se detienen en `MEMORY_WORKER_DB_BACKOFF_MAX`; al `restore()` el worker procesa la cola
- [x] Se registra `store_unavailable` sin DSN ni contraseña
- [x] `Worker.last_store_ok` avanza solo con accesos correctos (R-01: una caída larga no parece sana)

**Subtareas**
- [x] Escribir primero la prueba con la base cortada (rojo: `run()` termina)
- [x] Mover `claim_job` dentro del control de errores (`worker.py:91`)
- [x] Implementar espera, jitter y tope con reloj inyectado
- [x] Añadir `MEMORY_WORKER_DB_BACKOFF_MAX` a `config.py`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `worker.py:78-184` (`run_once`, `run`; `claim_job` fuera del `try` en `:91`, `run()` en `:178-184`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `5375106d7d1f`.

### T-09 — Un fallo de base al completar o fallar un trabajo no cambia su estado

- **Descripción**: Si la base cae durante `complete_job` o `fail_job`, el trabajo no pasa a `failed`, no recibe `provider_error` ni consume intento; vuelve a ser reclamable al expirar la concesión. Fuente: CA-09, CA-11; B-03.
- **Changelog**: Si la base falla al guardar el resultado de un trabajo, el worker lo conserva y repite la escritura (hasta MEMORY_WORKER_WRITE_RETRY_SECONDS); una caída más larga que la concesion puede costar el intento.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.82h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-08
- **Tipo**: backend
- **Archivos**: `server/memory_platform/worker.py`, `server/memory_platform/tests/test_worker_db_down.py`, `server/memory_platform/errors.py`, `server/memory_platform/observability.py`, `server/memory_platform/config.py`, `server/memory_platform/store_jobs.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_worker_db_down|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Con la base cortada durante `complete_job`, el trabajo no queda `failed` ni con `provider_error`, y tras `restore()` se completa en una reclamación posterior (prueba con `FaultProxy` y `expire_lease`)
- [x] Los errores de proveedor reintentables conservan su política actual (`worker.py:148-160`) y los de base no incrementan `attempts` más allá del reclamo ya contado (prueba que compara ambos caminos)
- [x] Si `fail_job` también falla por base caída, el worker sigue vivo

**Subtareas**
- [x] Escribir primero la prueba de ambos caminos (rojo)
- [x] Separar `except StoreUnavailable` del `except Exception` de `worker.py:165-168`
- [x] Verificar con la base cortada en `complete_job` y en `fail_job`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `worker.py:145` (`complete_job`), `:148-160` (política de reintento del proveedor), `:165-168` (`except Exception` → `fail_job(..., 'provider_error')`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `59449263d58d`.

### T-10 — Tope al reclamar: `attempts_exhausted` en el trabajo venenoso

- **Descripción**: Un trabajo `running` con concesión expirada y `attempts ≥ max_attempts` pasa a `failed` con `attempts_exhausted` en la misma transacción de reclamo, en lugar de reclamarse; `retry_job` lo reactiva. Fuente: CA-12; B-05.
- **Changelog**: Un trabajo cuyo worker muere sin parar deja de reclamarse al agotar MEMORY_MAX_ATTEMPTS: pasa a fallido con attempts_exhausted y se reactiva con el reintento; un valor inválido impide arrancar.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.35h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-09
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_jobs.py`, `server/memory_platform/tests/test_job_leases.py`, `server/memory_platform/worker.py`, `server/memory_platform/observability.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_native_runtime.py`, `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_job_leases|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Un trabajo venenoso (concesión expirada, `attempts ≥ max_attempts`) queda `failed` con `attempts_exhausted` y deja de reclamarse (prueba escrita en rojo antes del cambio)
- [x] `retry_job` (`store_jobs.py:68-78`) lo devuelve a `pending` y vuelve a procesarse
- [x] Es visible en `kairos_jobs_failed`
- [x] La semántica de reconciliación (`unknown`, `needs_reconciliation`, `store_jobs.py:104`) no cambia (pruebas existentes en verde)

**Subtareas**
- [x] Escribir primero la prueba de trabajo venenoso (rojo)
- [x] Aplicar el tope en `claim_job` (`store_jobs.py:92`, `:105`)
- [x] Comprobar `retry_job` y la métrica
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store_jobs.py:89-192` (`claim_job`, `renew_lease`, `_current_job`, `complete_job`, `fail_job`); `observability.py:205-208` (`kairos_jobs_failed`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `92342b06d044`.

### T-11 — Documentar el comportamiento del worker sin base

- **Descripción**: Documentar `MEMORY_WORKER_DB_BACKOFF_MAX`, el comportamiento sin base y `attempts_exhausted` en los manuales. Fuente: CA-10, CA-12 (documentación).
- **Changelog**: Los manuales explican qué hace el worker cuando la base de datos no responde (espera creciente, store_unavailable, MEMORY_WORKER_DB_BACKOFF_MAX) y cómo se reactiva un trabajo agotado.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.12h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-10
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`, `docs/roadmap/2026-11-15-reliable-operations/spec.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista `MEMORY_WORKER_DB_BACKOFF_MAX` con su default y `docs/operations.md` explica `store_unavailable` y `attempts_exhausted` con `retry_job`

**Criterios de aceptación**
- [x] Ambos manuales describen el comportamiento real (nombres y valores iguales a `config.py`)

**Subtareas**
- [x] Actualizar `docs/configuration.md`
- [x] Actualizar `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Estilo: `docs/operations.md` ya tiene una sección de cola y trabajos (`kairos_jobs_failed`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6b5c28734894`.

### T-12 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: el mínimo de pruebas que exige la integración continua sube a 884; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.25h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-11
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `f1e02ee9477b`.

### T-13 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: el reclamo y su reconciliación son delicados; R-01 (esperas que esconden una caída). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 2; endurece el worker frente a caídas de la base, sin otro cambio para quien usa Kairos que los ya descritos en T-07 a T-12.
- **Estado**: completado
- **Tiempo humano**: est. 7.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.00h (estimado) · real —
- **Supervisión**: est. 0.25h (≈25 % IA) · real —
- **Previsión IA**: 276 k in / 24 k out tok · ⚠️ verificar €
- **Dependencias**: T-12
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-13).

## Fase 3 — Cola: índices parciales y retención de tablas (C-02, B-06)

**Estado**: completado · **Hito**: A · **Estimado**: 27.0h (22.5h base, de ellas 7.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.350 € · **Tokens est.**: 900 k

### T-14 — Migración aditiva de esquema 12: índices parciales de cola

- **Descripción**: Añadir la versión de esquema 12 con un índice parcial `(priority, available_at, created_at, id) WHERE state IN ('pending','unknown')` y otro parcial para `running` por `lease_until`, solo con `CREATE INDEX IF NOT EXISTS`. Fuente: CA-13; B-06.
- **Changelog**: Interno: la cola de trabajos gana dos índices parciales (esquema 12) que la migración añade sin tocar filas ni columnas; el cambio no se nota hasta que la cola crece.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real 0.32h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: db
- **Archivos**: `server/memory_platform/schema.sql`, `server/memory_platform/tests/test_migrations_additive.py`, `server/memory_platform/tests/test_queue_indexes.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_queue_indexes|test_migrations_additive|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Una base migrada hasta la versión 11 llega a la 12 con los dos índices y sin tocar filas ni columnas
- [x] `test_migrations_additive.py` pasa y no hay `DROP`, `DELETE` ni `ALTER ... DROP` en la migración
- [x] Una base nueva y una migrada tienen el mismo catálogo de índices (prueba por catálogo)

**Subtareas**
- [x] Escribir primero la prueba de catálogo (rojo)
- [x] Añadir la versión 12 al final de `schema.sql`
- [x] Comprobar migración desde la 11
- [x] `usage-meter start/close` de la tarea

**Notas**: Deuda Minor heredada de la revisión de la Fase 1 (intento 2, n.º 3 y 4): cubrir la guarda en Python de los índices HNSW (`store_vectors.py:23-24`) frente a un `migrate()` repetido, y que las etiquetas de sección de la prueba genérica salgan de `schema.sql` en vez de ir a mano. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `75d9cf808631`.

### T-15 — `EXPLAIN` de `claim_job` sobre 10.000 trabajos y, si hace falta, dos sondeos

- **Descripción**: Comprobar con `EXPLAIN (FORMAT JSON)` que `claim_job` usa un índice nuevo sobre una tabla con ≥ 10.000 trabajos terminales; si el `OR` sobre `running` caducado lo impide, dividir el reclamo en dos sondeos ordenados con la misma semántica. Fuente: CA-13; B-06.
- **Changelog**: Reclamar un trabajo de la cola deja de recorrer y ordenar todo lo pendiente: con decenas de miles de trabajos en cola pasa de unos 110 ms a menos de 1 ms por reclamo; el orden y la semántica no cambian.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real 0.19h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-14
- **Tipo**: db
- **Archivos**: `server/memory_platform/store_jobs.py`, `server/memory_platform/tests/test_queue_indexes.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_queue_indexes|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] El plan de `claim_job` sobre ≥ 10.000 trabajos terminales usa un índice nuevo y no un recorrido secuencial (`EXPLAIN (FORMAT JSON)` en la prueba)
- [x] Si se divide en dos sondeos, la semántica de prioridad, `available_at`, `created_at`, `id` y reconciliación es idéntica (prueba de equivalencia sobre una cola mixta)
- [x] Las pruebas de reclamo existentes (`test_jobs.py`, `test_worker.py`) siguen en verde

**Subtareas**
- [x] Sembrar 10.000 trabajos terminales y medir el plan actual
- [x] Decidir un sondeo o dos y anotarlo en `Notas`
- [x] Probar equivalencia de semántica
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store_jobs.py:92` (`ORDER BY priority, available_at, created_at, id` con `OR` sobre `running` caducado) y `:104` (reconciliación). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `d864b63387e1`.

### T-16 — `admin prune-tables` por lotes con `--dry-run` y ventanas por tabla

- **Descripción**: Añadir el subcomando `prune-tables` (por lotes, `--dry-run`) con ventanas configurables por tabla (P-03): `login_attempts` 30 d, `web_sessions` caducadas o revocadas 30 d, `audit_events` 365 d, `jobs` terminales `failed` sin recibo 90 d; `events` sin retención por defecto. Nunca en una migración. Fuente: CA-14; B-06; P-03.
- **Changelog**: Nuevo `admin prune-tables [--dry-run]` que borra por lotes las filas viejas de login_attempts (30 d), web_sessions caducadas o revocadas (30 d), audit_events (365 d) y trabajos fallidos huérfanos (90 d: sin recibo, no citados por un evento conservado y no de la versión actual de un documento o nota); `events` no se poda salvo ventana explícita; cada ejecución real deja su rastro en `audit_events`.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 0.61h (medido)
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-15
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_prune_tables.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_prune_tables|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `prune-tables --dry-run` informa de lo que borraría por tabla y no borra nada; sin `--dry-run` borra por lotes según las ventanas
- [x] Variables `MEMORY_RETENTION_*` por tabla con los defaults de P-03; `events` solo se poda si se activa su ventana explícitamente
- [x] Un lote fallido no deja la tabla a medias (cada lote es una transacción) y la operación es repetible
- [x] `admin` usa conexión directa, sin el `statement_timeout` de servicio
- [x] (revisión 1, n.º 1) La poda de `jobs` conserva el contrato de las herramientas MCP: no borra un trabajo citado por el recibo de un evento conservado, ni uno de la versión actual de su documento o nota, ni uno con recibo de proyección; las respuestas de `event_status`, `ingest_event` (reenvío), `document_status`, `get_job` y `backfill-chunks` son iguales antes y después
- [x] (revisión 1, n.º 4 y 5) Cada ejecución real deja una fila `retention_prune` en `audit_events` (después de podarla); los lotes avanzan con cursor por la clave en orden ascendente

**Subtareas**
- [x] Escribir primero las pruebas con filas sembradas (antiguas y recientes)
- [x] Implementar el subcomando y las ventanas
- [x] Añadir las claves a `config.py`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:240-321` (registro de subcomandos, `backup`, `restore-check`) y `schema.sql:7-19` (tablas). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `b7b669cad3b4`.

### T-17 — Invariantes de la retención: manifiesto, recibos y migraciones sin `DELETE`

- **Descripción**: Probar que podar no cambia lo que ven los clientes: `content_manifest()` de datos de memoria igual antes y después, ningún trabajo con recibo en `projection_receipts` se borra, ninguna migración contiene `DELETE`. Fuente: CA-14; R-04.
- **Changelog**: Interno: pruebas que fijan que podar las tablas no cambia lo que ven los clientes (manifiesto, embeddings y recibos intactos, `events` intacta por defecto) y que ninguna migración borra.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.14h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-16
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_prune_tables.py`, `server/memory_platform/tests/test_migrations_additive.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_prune_tables|test_migrations_additive|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `content_manifest()` (elementos, documentos, embeddings y recibos vigentes) es igual antes y después de `prune-tables`
- [x] Un trabajo `failed` con recibo en `projection_receipts` no se borra aunque supere la ventana (la clave foránea `schema.sql:20` lo protege y la prueba lo demuestra)
- [x] Una prueba recorre `MIGRATION_SOURCES` y falla si aparece `DELETE` (mutante comprobado)
- [x] `events` intacta con los valores por defecto

**Subtareas**
- [x] Sembrar datos con recibos y trabajos antiguos
- [x] Comparar manifiesto antes/después
- [x] Añadir el mutante `DELETE` a `test_migrations_additive.py`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `schema.sql:20` (`projection_receipts.job_id` referencia `jobs(id)`) y `scripts/deploy-memory.py:376` (uso de `content-manifest`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `35f5dbac93d8`.

### T-18 — Documentar índices, retención y ventanas

- **Descripción**: Documentar la retención (`prune-tables`, ventanas, `--dry-run`, por qué `events` no se poda por defecto) y la nota de cola en los manuales. Fuente: CA-14 (documentación); B-06.
- **Changelog**: Manuales: nueva sección «Poda de tablas» (`prune-tables`, ventanas, `--dry-run`, por qué `events` no se poda por defecto) y nota de los índices parciales de la cola con su ventana de bloqueo medida; las cinco variables de retención en la tabla de configuración.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.15h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-17
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`, `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista las `MEMORY_RETENTION_*` con sus defaults de P-03 y `docs/operations.md` explica `prune-tables --dry-run` y la excepción de `events`

**Criterios de aceptación**
- [x] Valores y nombres iguales a `config.py`
- [x] La nota de que `events` cambia respuestas visibles y se declara a la Iniciativa 7

**Subtareas**
- [x] Actualizar `docs/configuration.md`
- [x] Actualizar `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Estilo: secciones existentes de `docs/operations.md`. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `d12daa1a338b`.

### T-19 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: el mínimo de pruebas que exige la integración continua sube a 917; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.14h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-18
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`, `server/memory_platform/tests/test_native_runtime.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0060032d7a78`.

### T-20 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: R-04 (retención que cambia lo que ven los clientes). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 3; la poda de tablas conserva el contrato de las herramientas MCP y deja rastro en la auditoría.
- **Estado**: completado
- **Tiempo humano**: est. 7.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.00h (estimado) · real —
- **Supervisión**: est. 0.25h (≈25 % IA) · real —
- **Previsión IA**: 276 k in / 24 k out tok · ⚠️ verificar €
- **Dependencias**: T-19
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Cerrada en el intento 2 de 3 (intento 1: A+B+C+D; intento 2: A+B; resumen en `review.md`). `scope-check.py --base d23f4a7` exit 0; suite 925 en verde. Los revisores no tienen medición propia. Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 4 — Pool y plazos de conexión (C-03, B-02 y B-07)

**Estado**: completado · **Hito**: A · **Estimado**: 48.0h (40.0h base, de ellas 20.0h de revisión adversarial) · **Real**: — · **Coste est.**: 2.400 € · **Tokens est.**: 1600 k

### T-21 — Medición previa: consultas, conexiones y latencia por búsqueda

- **Descripción**: Medir antes del pool cuántas conexiones y consultas abre una búsqueda híbrida y su latencia, para comparar después. Fuente: CA-15, CA-18 (línea base); B-02.
- **Changelog**: Interno: nuevo medidor de conexiones y consultas por búsqueda híbrida; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 0.75h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.10h (estimado) · real 0.16h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 28 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/measure_connections.py`
- **Cubre (tests)**: —
- **Verificación**: `docker run --rm --network=none -e MEASURE_CONNECTIONS=1 -e MEASURE_REPEATS=30 kairos-test:i3p4 python -m memory_platform.tests.measure_connections` → una línea `MEASURE_CONNECTIONS {json}` con 7 conexiones y 49 consultas por búsqueda (fix1: el comando anterior no podía dar esa línea: el medidor no corre en el build) y, en el build `--target test`, `MEMORY_TEST_RESULT` sin fallos

**Criterios de aceptación**
- [x] La medición (conexiones por búsqueda, consultas por búsqueda, latencia p50) queda anotada en `Notas`, sobre PostgreSQL efímero
- [x] El script no es una prueba de la suite (no cambia el recuento)

**Subtareas**
- [x] Escribir el medidor sobre `Store` y la búsqueda híbrida
- [x] Anotar la cifra «antes» en `Notas`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store.py:24-30` (una conexión nueva por `transaction()`), `retrieval.py:87-148` (una transacción por capa) y `tests/measure_vector_candidates.py` (medidor existente fuera de la suite). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `5b68a093ed16`.

### T-22 — `psycopg_pool` en `Store.transaction()` con `MEMORY_POOL_*`

- **Descripción**: Tomar las conexiones de `Store.transaction()` de un `psycopg_pool.ConnectionPool` (versión fijada) con `MEMORY_POOL_MIN`/`MAX`/`TIMEOUT` (1 / 10 / 5 s a medir); los comandos de `admin` siguen con conexión directa y `store_surface.json` no cambia. Fuente: CA-15; B-02.
- **Changelog**: Las transacciones de la API y del worker reutilizan conexiones de un pool (MEMORY_POOL_MIN/MAX/TIMEOUT, 1/10/5 s): una búsqueda con el pool caliente ya no abre conexiones nuevas. Un `MEMORY_LEASE_SECONDS` fuera de 1-86400 impide arrancar.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 6h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.80h (estimado) · real 0.40h (medido)
- **Supervisión**: est. 0.20h (≈25 % IA) · real —
- **Previsión IA**: 221 k in / 19 k out tok · ⚠️ verificar €
- **Dependencias**: T-21
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store.py`, `server/memory_platform/config.py`, `server/memory_platform/app.py`, `server/memory_platform/worker.py`, `server/memory_platform/requirements.txt`, `server/memory_platform/tests/test_store_pool.py`, `server/memory_platform/store_pool.py`, `server/memory_platform/errors.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_pool|test_store_surface|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `Store.transaction()` toma conexiones del pool (`psycopg_pool` fijado por versión en `requirements.txt`); tras calentar, una búsqueda híbrida no abre conexiones nuevas (el conjunto de `pg_backend_pid()` es estable)
- [x] `store_surface.json` no cambia y `test_store_surface` pasa
- [x] El pool se cierra al apagar la API y el worker; `admin` usa conexión directa
- [x] El tamaño máximo del pool se razona frente a los hilos de `asyncio.to_thread` y queda en `Notas`

**Subtareas**
- [x] Escribir primero la prueba del conjunto de `pg_backend_pid()` (rojo)
- [x] Fijar `psycopg_pool` compatible con `psycopg 3.3.7` en `requirements.txt`
- [x] Integrar el pool en `Store.transaction()` y su ciclo de vida
- [x] Mantener `admin` con conexión directa
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-22).

### T-23 — `connect_timeout` y `statement_timeout` como opciones de conexión de servicio

- **Descripción**: Fijar `connect_timeout` (5 s) y `statement_timeout` (15.000 ms en la API, 30.000 ms en el worker) como opciones de las conexiones de servicio; `migrate`, `backfill-chunks`, `backup` y `content-manifest` no heredan el plazo. Fuente: CA-16, CA-17; B-07; R-02.
- **Changelog**: Las conexiones de la API y del worker llevan TCP keepalives y un plazo de conexión (MEMORY_CONNECT_TIMEOUT, 3 s) y un plazo de sentencia (MEMORY_STATEMENT_TIMEOUT_MS, 15.000 ms en la API y 30.000 en el worker): una consulta atascada la cancela el servidor.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 0.39h (medido)
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-22
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store.py`, `server/memory_platform/config.py`, `server/memory_platform/admin.py`, `server/memory_platform/tests/test_store_timeouts.py`, `server/memory_platform/store_pool.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_timeouts|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Una consulta de servicio con `pg_sleep` más larga que el plazo se cancela en el servidor y la conexión vuelve al pool utilizable
- [x] Con un DSN hacia un puerto que acepta y no responde (`FaultProxy.mute()`), el fallo llega en ≤ `MEMORY_CONNECT_TIMEOUT` + 1 s
- [x] `migrate`, `backfill-chunks` y `backup` se ejecutan con el plazo de la API activo en el entorno y no lo heredan (prueba)
- [x] Los `set_config` locales existentes siguen restaurando su valor previo (`store_documents.py:27-35`)

**Subtareas**
- [x] Escribir primero las pruebas de `pg_sleep` y servidor mudo (rojo)
- [x] Añadir las opciones a las conexiones de servicio y excluir `admin`
- [x] Comprobar `migrate` y `backfill-chunks` con el plazo activo en la API
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-23).

### T-24 — Errores 503 `store_timeout` y `store_busy` y su clasificación

- **Descripción**: Mapear `statement_timeout` agotado a 503 `store_timeout` y pool agotado (`MEMORY_POOL_TIMEOUT`) a 503 `store_busy` con `request_id`; el worker los clasifica como `StoreUnavailable`. Fuente: CA-16, CA-19; B-07.
- **Changelog**: Cuando la base no responde a tiempo, la API contesta 503 store_timeout (consulta cancelada por plazo) o 503 store_busy (sin conexión libre en MEMORY_POOL_TIMEOUT), con mensaje fijo y request_id; una caída o una conexión que se queda muda es service_unavailable. Una búsqueda con el pool saturado responde 503 store_busy en vez de un resultado parcial; `/health/ready` sigue en 200 con el pool lleno. `MEMORY_CONNECT_TIMEOUT` (3 s) debe quedar al menos 1 s por debajo de `MEMORY_POOL_TIMEOUT` o el proceso no arranca.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.50h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-23
- **Tipo**: backend
- **Archivos**: `server/memory_platform/app.py`, `server/memory_platform/errors.py`, `server/memory_platform/worker.py`, `server/memory_platform/tests/test_store_timeouts.py`, `server/memory_platform/tests/test_store_pool.py`, `server/memory_platform/mcp.py`, `mcp/tests/test_client.py`, `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md`, `server/memory_platform/store_pool.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_timeouts|test_store_pool|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] La API responde 503 `store_timeout` si PostgreSQL cancela por plazo, y la búsqueda sigue marcando la capa `unavailable` con `reason: timeout` como hoy
- [x] Con el pool agotado, una petición espera como máximo `MEMORY_POOL_TIMEOUT` y recibe 503 `store_busy` con `request_id`; no se cuelga
- [x] El worker trata ambos como `StoreUnavailable` (espera y reintenta, sin consumir intento) (precisado: decisión de la Fase 2 — 57014 en el worker es `store_error` transitorio; ver Notas)

**Subtareas**
- [x] Escribir primero las pruebas de pool agotado y plazo (rojo)
- [x] Añadir los dos códigos al manejador de errores
- [x] Enlazar con el clasificador de la Fase 2
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-24).

### T-25 — Pruebas de la clase entera con `FaultProxy`: plazo, pool y servidor mudo

- **Descripción**: Ejercitar con el arnés todas las rutas de datos nuevas (API y worker) con base lenta, muda o cortada, para cubrir la clase y no un caso. Fuente: CA-16, CA-17, CA-19; CA-34.
- **Changelog**: Interno: la API y el worker se prueban contra una base cortada, muda y lenta; si el worker pierde la concesión mientras reintenta escribir, comprueba antes si la escritura ya había entrado.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.58h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-24
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_store_faults.py`, `server/memory_platform/worker.py`, `server/memory_platform/tests/test_store_halfopen.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_faults|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] La API y el worker sobreviven a base cortada, muda y lenta en las rutas de lectura, escritura y búsqueda, con la respuesta documentada en cada caso
- [x] La conexión que sufrió el corte no vuelve al pool rota (siguiente petición correcta)
- [x] Mutante comprobado: quitar `statement_timeout`, `connect_timeout` o el plazo del pool deja una prueba en rojo

**Subtareas**
- [x] Tabla de rutas × fallo
- [x] Escribir las pruebas
- [x] Aplicar los mutantes en memoria
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-25).

### T-26 — Medición posterior del pool y defaults de `MEMORY_POOL_*`

- **Descripción**: Repetir la medición con el pool y fijar los valores por defecto del pool y de los plazos con la cifra. Fuente: CA-15 (medición); B-02.
- **Changelog**: Interno: medición posterior del pool; una búsqueda híbrida con el pool caliente abre 0 conexiones (antes 7) y la transacción mínima pasa de unos 15 ms a 1 ms; la latencia de la búsqueda completa no se pudo medir de forma fiable (varía con la carga de la máquina); los valores por defecto del pool se mantienen.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 0.75h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.10h (estimado) · real 0.08h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 28 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-25
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/measure_connections.py`, `server/memory_platform/config.py`
- **Cubre (tests)**: —
- **Verificación**: `docker run --rm --network=none -e MEASURE_CONNECTIONS=1 -e MEASURE_POOL=1 -e MEASURE_REPEATS=30 kairos-test:i3p4 python -m memory_platform.tests.measure_connections` → `"connections_per_search": 0.0` tras calentar (fix1: el comando anterior no podía dar esa línea) y, en el build `--target test`, `MEMORY_TEST_RESULT` sin fallos

**Criterios de aceptación**
- [x] Cifras «antes» y «después» anotadas en `Notas` (conexiones, consultas, latencia)
- [x] Defaults del pool justificados con la medición

**Subtareas**
- [x] Medir
- [x] Ajustar los defaults de `config.py` si la medición lo pide
- [x] `usage-meter start/close` de la tarea

**Notas**: Comparar con la línea base de la tarea de medición previa. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `f84e802454e3`.

### T-27 — Documentar pool, plazos y errores 503

- **Descripción**: Documentar `MEMORY_POOL_*`, `MEMORY_CONNECT_TIMEOUT`, `MEMORY_STATEMENT_TIMEOUT_MS`, los códigos `store_timeout`/`store_busy` y qué comandos de `admin` no heredan el plazo. Fuente: CA-15 a CA-19 (documentación).
- **Changelog**: Documentado cómo funcionan el pool de conexiones y los plazos de la base: las nueve variables nuevas (pool, plazos y `MEMORY_TCP_*`), los errores 503 store_busy y store_timeout y qué comandos de admin no heredan el plazo.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.11h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-26
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista las cinco variables con defaults iguales a `config.py` y `docs/operations.md` explica los dos 503

**Criterios de aceptación**
- [x] Defaults y códigos iguales al código
- [x] `docs/architecture.md` describe el pool

**Subtareas**
- [x] Actualizar los tres manuales
- [x] `usage-meter start/close` de la tarea

**Notas**: Estilo: `docs/configuration.md` (tabla de variables). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `f6ef40a83a74`.

### T-28 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: el mínimo de pruebas que exige la integración continua sube a 1006; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-16
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real 0.07h (medido)
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 18 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-27
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `62eb579e5974`.

### T-29 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Superficie expuesta a todas las peticiones: R-02 (plazo que corta trabajo legítimo) y pool compartido entre hilos; revisión a 1,0 ×. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 4; el pool y los plazos aguantan una base caída, muda o congelada.
- **Estado**: completado
- **Tiempo humano**: est. 20h (base) · real —
- **Tiempo IA (ejec.)**: est. 2.67h (estimado) · real —
- **Supervisión**: est. 0.67h (≈25 % IA) · real —
- **Previsión IA**: 736 k in / 64 k out tok · ⚠️ verificar €
- **Dependencias**: T-28
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Cerrada en el intento 2 de 3 (intento 1: A+B+C+D; intento 2: A+B; resumen en `review.md`). `scope-check.py --base 9416128` exit 0; suite 1006 en verde. Los revisores no tienen medición propia. Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 5 — Permisos por transacción (C-03, B-02)

**Estado**: completado · **Hito**: A · **Estimado**: 24.0h (20.0h base, de ellas 10.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.200 € · **Tokens est.**: 800 k

### T-30 — Caché de `_active` y de concesiones por proyecto válida hasta el `COMMIT`

- **Descripción**: Cachear la lectura de actor y clave y las concesiones por proyecto en el ámbito de la transacción, descartándola al `COMMIT`/`ROLLBACK`, para que una búsqueda sobre N proyectos lea actor y clave una sola vez. Fuente: CA-18; B-02; R-05.
- **Changelog**: Los permisos se leen una vez por transacción (la revocación vale desde la petición siguiente y también tras esperar un bloqueo: ingesta, publicación, borrado y reintento responden 401/403) y una base caída dentro de una capa de búsqueda da 503; `/health/ready` da 503 si el pool nunca entregó una conexión y 200 solo si ya entregó alguna y está saturado.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 1.05h (medido: 0.62 + 0.43 del cierre de la Fase 5)
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_auth.py`, `server/memory_platform/store.py`, `server/memory_platform/tests/test_auth_cache.py`, `server/memory_platform/auth_scope.py` (nuevo: el ciclo de vida de la caché; `store_auth.py` y `auth.py` se importan entre sí y no podía vivir en el primero), `server/memory_platform/auth.py`, `server/memory_platform/store_documents.py`, `server/memory_platform/store_vectors.py` (savepoints), `server/memory_platform/extended_store.py`, `server/memory_platform/corpus_answers.py` (releer tras `FOR SHARE`), `server/memory_platform/store_jobs.py`, `server/memory_platform/store_pool.py`, `server/memory_platform/retrieval.py`, `server/memory_platform/errors.py` (deuda de la Fase 4), `server/memory_platform/tests/test_store_phase4_debt.py` (nuevo), `server/memory_platform/tests/test_store_faults.py` (una expectativa cambia: ver Notas), `server/memory_platform/store_ingest.py` (fix1: releer tras esperar), `server/memory_platform/tests/test_auth_race.py` (nuevo, fix1: dos conexiones), `server/memory_platform/app.py` (fix2: comentario), `docs/architecture.md`, `docs/operations.md` (fix2: límite residual y tabla de rutas)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|test_auth|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos. Salida fix1 (build `kairos-test:i3p5`, 2026-11-16): `#30 81.17 test_bearer_revocation_primary_and_foreign_scope (memory_platform.tests.test_auth.AuthTests.test_bearer_revocation_primary_and_foreign_scope) ... ok` · `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1048}`

**Criterios de aceptación**
- [x] Una búsqueda sobre N proyectos ejecuta la lectura de actor y clave una sola vez por transacción (contador de consultas en la prueba)
- [x] Una clave revocada deja de valer en la petición siguiente (la caché no sobrevive al `COMMIT`)
- [x] La caché no se comparte entre peticiones que reutilizan la misma conexión del pool (prueba con dos actores seguidos)

**Subtareas**
- [x] Escribir primero las pruebas de contador y revocación (rojo)
- [x] Implementar la caché ligada al objeto de transacción
- [x] Limpiar en `COMMIT`, `ROLLBACK` y devolución al pool
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-30).

### T-31 — Pruebas de revocación, aislamiento entre peticiones y recorrido de las 86 transacciones

- **Descripción**: Cubrir la clase entera: revocación entre transacciones, dos actores en la misma conexión, y que ninguna de las rutas que usan `transaction()` salta la comprobación de permisos. Fuente: CA-18; R-05.
- **Changelog**: Interno: pruebas que recorren todas las rutas `/v1`, todos los métodos del almacén con actor y todas las transacciones del paquete para garantizar que una revocación vale en la petición siguiente.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.27h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-30
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_auth_cache.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Revocar una clave entre dos peticiones sobre la misma conexión devuelve 401/403 en la segunda (todas las rutas de lectura y escritura de `/v1` probadas con una tabla)
- [x] Mutante comprobado: dejar la caché viva tras `COMMIT` deja la prueba de revocación en rojo
- [x] La suite de permisos existente (`test_auth.py`, `test_privacy.py`) pasa sin cambios

**Subtareas**
- [x] Tabla de rutas × revocación
- [x] Escribir las pruebas
- [x] Aplicar el mutante
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-31).

### T-32 — Medición final de consultas por búsqueda y documentación

- **Descripción**: Medir de nuevo las consultas por búsqueda tras la caché y documentar el comportamiento de permisos por transacción. Fuente: CA-18 (medición y documentación).
- **Changelog**: Una búsqueda híbrida hace 14 consultas menos a la base (de 63 a 49 con el pool) y la documentación explica que los permisos se resuelven una vez por transacción y mueren con el `COMMIT`.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.18h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: docs
- **Archivos**: `server/memory_platform/tests/measure_connections.py`, `docs/architecture.md`, `docs/configuration.md`, `docs/operations.md` (la regla de clasificación y la medición), `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md` (lista de coordinación con la Iniciativa 7)
- **Cubre (tests)**: —
- **Verificación**: `docker run --rm --network=none -e MEASURE_CONNECTIONS=1 -e MEASURE_POOL=1 -e MEASURE_REPEATS=30 kairos-test:i3p5 python -m memory_platform.tests.measure_connections` → una línea `MEASURE_CONNECTIONS {json}` con menos consultas por búsqueda que la línea base de la Fase 4 (63 con el pool; el medidor no corre en el build: mismo ajuste que T-21/T-26) y, en el build `--target test`, `MEMORY_TEST_RESULT` sin fallos. Salida fix1 (2026-11-16): `MEASURE_CONNECTIONS {"auth_queries_per_search": 22.0, "connections_per_search": 0.0, "hits": 10, "pool": true, "pool_max": 10, "pool_queries_per_search": 14.0, "projects": 3, "queries_per_search": 49.0, "queries_without_pool_per_search": 35.0, "repeats": 30, "rows_per_table": 300, "transactions_per_search": 7.0, "warmup": 10}`

**Criterios de aceptación**
- [x] Cifras anotadas en `Notas`
- [x] `docs/architecture.md` explica que la caché muere con el `COMMIT`

**Subtareas**
- [x] Medir
- [x] Actualizar `docs/architecture.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-32).

### T-33 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: el mínimo de pruebas de la integración continua sube a 1054, el total final de la Fase 5.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.23h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-32
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md` (el recuento que repite)
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fases 1 a 5», T-33).

### T-34 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado máximo: la revocación no puede relajarse (R-05); revisión a 1,0 ×. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 5; la caché de permisos por transacción relee la base tras cada espera de bloqueo.
- **Estado**: completado
- **Tiempo humano**: est. 10h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.33h (estimado) · real —
- **Supervisión**: est. 0.33h (≈25 % IA) · real —
- **Previsión IA**: 368 k in / 32 k out tok · ⚠️ verificar €
- **Dependencias**: T-33
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Cerrada en el intento 2 de 3 (intento 1: A+B+C+D; intento 2: A+B+C; Minor del intento 2 corregidos en el cierre, commit 886388a; resumen en `review.md`). `scope-check.py --base 04822a0` exit 0; suite 1054 en verde. Los revisores no tienen medición propia. Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 6 — Copias locales: integridad, cifrado, retención y verificación (C-01)

**Estado**: completado · **Hito**: A · **Estimado**: 43.2h (36.0h base, de ellas 12.0h de revisión adversarial) · **Real**: — · **Coste est.**: 2.160 € · **Tokens est.**: 1440 k

### T-35 — Manifiesto `<copia>.json` y `admin verify-backup`

- **Descripción**: `admin backup` escribe, junto a cada copia, un manifiesto con sha256 del fichero tal como queda en disco, bytes, versión de esquema, hora, `encrypted` y recuentos de `store_fingerprints`; `admin verify-backup` recalcula el sha256 y falla con `backup_checksum_mismatch`. Fuente: CA-01; O-01.
- **Changelog**: Cada copia lleva un manifiesto <copia>.json (sha256, tamaño, esquema, hora, recuentos); `admin verify-backup` detecta un byte alterado, un truncado o un manifiesto ausente o manipulado.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.47h (estimado) · real 0.86h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 129 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/tests/test_admin.py`, `server/memory_platform/tests/test_backup_manifest.py`, `server/memory_platform/backup.py` (nuevo: manifiesto, escritura atómica y verificación; `admin.py` queda fino), `server/memory_platform/tests/test_backup_hardening.py` (nuevo, fix1)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_manifest|test_admin|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos Salida (2026-11-16): bucle rápido (imagen de pruebas + árbol de trabajo; la suite completa va en T-42) `Ran 57 tests ... OK`: test_admin, test_backup_manifest (12), test_store_timeouts; `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 57}`.

**Criterios de aceptación**
- [x] `backup` escribe `<copia>` y `<copia>.json` con los campos del manifiesto y `chmod 600`
- [x] `verify-backup` recalcula el sha256 y falla con `backup_checksum_mismatch` si se altera un byte (prueba)
- [x] Una copia sin manifiesto o con manifiesto ilegible falla con un error propio, sin traza con rutas sensibles

**Subtareas**
- [x] Escribir primero la prueba del byte alterado (rojo)
- [x] Añadir el manifiesto a `backup`
- [x] Implementar `verify-backup`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-35).

### T-36 — Cifrado `age` con destinatarios y `MEMORY_BACKUP_REQUIRE_ENCRYPTION`

- **Descripción**: Cifrar la copia con `age` y clave pública (`MEMORY_BACKUP_RECIPIENTS_FILE`); con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` y sin destinatarios falla sin dejar fichero. La imagen `operator` y la de pruebas incorporan `age` fijado por versión; la clave privada de prueba se genera en el test y nunca está en el contenedor del servidor. Fuente: CA-02, CA-08 (parte); S-06; P-01.
- **Changelog**: Las copias se cifran con age para los destinatarios de MEMORY_BACKUP_RECIPIENTS_FILE (el volcado en claro nunca toca el disco) y MEMORY_BACKUP_REQUIRE_ENCRYPTION=1 prohíbe copias en claro. Una copia descifrada se verifica contra el manifiesto de la cifrada con `admin verify-backup --manifest` o `admin restore-check --from-manifest <manifiesto>`; un valor inválido de MEMORY_BACKUP_REQUIRE_ENCRYPTION falla con `backup_config_invalid`.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 5.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.73h (estimado) · real 0.65h (medido)
- **Supervisión**: est. 0.18h (≈25 % IA) · real —
- **Previsión IA**: 202 k in / 18 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/Dockerfile`, `server/memory_platform/tests/test_backup_encryption.py`, `docker-compose.yml` (`init: true` en `memory-admin`, fix1), `server/memory_platform/tests/test_backup_restore.py`, `server/memory_platform/tests/test_backup_hardening.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_encryption|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos Salida (2026-11-16): bucle rápido `Ran 47 tests ... OK` (test_backup_encryption 15, test_backup_manifest 12, test_admin); `"errors": 0, "failures": 0, "skipped": 0`. Imagen `operator` construida: age 1.2.1-1+b5 (test: bookworm 1.1.1-1+b3).

**Criterios de aceptación**
- [x] Con una clave pública `age` de prueba, la copia no empieza por `PGDMP` ni contiene el texto de una fila sembrada, y solo se restaura tras descifrar con la clave privada del test
- [x] Con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` y sin destinatarios, `backup` falla nombrando `MEMORY_BACKUP_RECIPIENTS_FILE` y no deja fichero
- [x] El manifiesto marca `encrypted: true` y su sha256 es el del fichero cifrado (se verifica sin descifrar)
- [x] `age` queda fijado por versión (paquete de Debian bookworm o binario con sha256 verificado) en los targets `operator` y `test`; ninguna clave privada entra en el repositorio ni en una imagen

**Subtareas**
- [x] Comprobar la disponibilidad de `age` en bookworm y anotar la versión en `Notas`
- [x] Escribir primero las pruebas (rojo)
- [x] Implementar el cifrado y la exigencia de destinatarios
- [x] Añadir `age` a los targets `operator` y `test` del `Dockerfile`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-36).

### T-37 — `backup --prune --keep N` con ficheros señuelo

- **Descripción**: `backup --prune --keep N` conserva las N copias más recientes con manifiesto válido, nunca borra la última verificada ni ficheros sin el patrón propio, rechaza `N < 1` e informa de lo borrado. Default `MEMORY_BACKUP_KEEP=7`. Fuente: CA-03; O-01.
- **Changelog**: `admin backup --prune --keep N` verifica las N copias más recientes, borra sin recalcular las más antiguas propias y barre los parciales huérfanos; nunca toca otros ficheros y rechaza N < 1.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.45h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-36
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_backup_prune.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_prune|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos Salida (2026-11-16): bucle rápido `Ran 60 tests ... OK` (test_backup_prune 13, test_backup_manifest, test_backup_encryption, test_admin); 0 fallos, errores y omitidos.

**Criterios de aceptación**
- [x] Con ficheros señuelo (sin el patrón propio, con manifiesto inválido), solo se borran copias propias más antiguas que las N más recientes válidas
- [x] La última copia verificada nunca se borra y `N < 1` se rechaza con un error propio
- [x] El informe lista lo borrado y lo conservado

**Subtareas**
- [x] Escribir primero la prueba con señuelos (rojo)
- [x] Implementar `--prune --keep`
- [x] Añadir `MEMORY_BACKUP_KEEP`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-37).

### T-38 — `--backup-timeout` en el despliegue (O-03)

- **Descripción**: `scripts/deploy-memory.py` llama a `content-manifest`, `backup` y `verify-backup` con `--backup-timeout` (por defecto 3.600 s) en lugar del plazo de 120 s. Fuente: CA-04; O-03.
- **Changelog**: El despliegue da a la copia, al manifiesto de contenido y a su verificación el plazo `--backup-timeout` (3.600 s por defecto, hasta 24 h) y, si agotan el plazo, detiene y elimina su contenedor.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.23h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_isolation.py` (el doble `migrate_run` registra los plazos)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos Salida (2026-11-16): bucle rápido `Ran 44 tests ... OK` (test_deploy, test_deploy_isolation); 0 fallos, errores y omitidos. CA-04: `verify-backup` recibe el mismo plazo en T-39.

**Criterios de aceptación**
- [x] `test_deploy.py` comprueba que `content-manifest`, `backup` y `verify-backup` reciben `--backup-timeout` (3.600 s por defecto) y que `--backup-timeout 7200` se propaga
- [x] Las demás fases del despliegue conservan su plazo (`operator()` por defecto 120 s)

**Subtareas**
- [x] Escribir primero la prueba con el doble de `subprocess` (rojo)
- [x] Añadir `--backup-timeout` y pasarlo a las tres llamadas
- [x] `usage-meter start/close` de la tarea

**Notas**: Patrón: `deploy-memory.py:27` (`MIGRATE_TIMEOUT_SECONDS`), `:257-258` (`operator()` con `timeout=120`), `:376` y `:380` (llamadas), `tests/test_deploy.py` (dobles de `subprocess`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `9c7c6ae7de06`.

### T-39 — `--verify-backup`: restauración en PostgreSQL efímero antes de `migrate`

- **Descripción**: Opción de `deploy-memory.py` (activada por defecto en los ensayos) que restaura la copia previa en un contenedor PostgreSQL efímero del propio proyecto con base `memory_restore_<marca>`, compara `store_fingerprints`, aborta antes de `migrate` si difieren y elimina el contenedor; el informe registra resultado y duración. Fuente: CA-05; O-02.
- **Changelog**: El despliegue puede restaurar la copia previa en un PostgreSQL efímero y aislado, con contraseña propia, y comparar sus tablas con el manifiesto antes de migrar (cifrada: solo integridad).
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 0.82h (medido)
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-38, T-36
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/admin.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_isolation.py`, `server/memory_platform/tests/test_backup_restore.py` (nuevo: `restore-check --from-manifest`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy|test_deploy_isolation|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos Salida (2026-11-16): bucle rápido `Ran 84 tests ... OK` (test_deploy, test_deploy_isolation, test_backup_restore, test_admin); `"errors": 0, "failures": 0, "skipped": 0`.

**Criterios de aceptación**
- [x] Una prueba con dobles comprueba la secuencia: copia → contenedor efímero con nombre del proyecto → `restore-check` con `memory_restore_<marca>` → comparación → eliminación → `migrate`; una diferencia aborta antes de `migrate`
- [x] El contenedor efímero se elimina también si falla la comparación
- [x] Nunca escribe en la base del proyecto ni usa nombres `knowledge-graphs-*`; el informe registra resultado y duración

**Subtareas**
- [x] Escribir primero las pruebas con dobles (rojo)
- [x] Implementar la fase y su limpieza
- [x] Reutilizar `restore-check` y sus salvaguardas
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-39).

### T-40 — Ensayo aislado de `--verify-backup`

- **Descripción**: Ejecutar un ensayo aislado real con `--verify-backup` y comprobar el contenedor efímero, el aborto ante una diferencia y la limpieza. Fuente: CA-05 (ensayo).
- **Changelog**: Interno: ensayo aislado real de la verificación de copias antes de migrar (restauración, aborto ante una diferencia y limpieza).
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real 0.16h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/deploy-memory.py --project-name kairos-ops-a --embed-stub --verify-backup` → termina en 0 y el informe registra `verify_backup` con resultado y duración; después `docker ps -a --filter name=kairos-ops-a` y `docker volume ls --filter name=kairos-ops-a` muestran solo recursos propios, que se eliminan al terminar
  - `docker ps --filter name=knowledge-graphs` y `docker volume ls --filter name=knowledge-graphs` → idénticos antes y después
  - Salida fix2 (2026-11-16, tras fix1 y fix2; `kairos-ops-a`, puertos 28791/25174, `--embed-stub`, secretos sintéticos nuevos): (1) `--apply --fresh --roundtrip` → exit 0, `PASS roundtrip`, `chat_calls 0`; (2) `--apply --verify-backup` → exit 0, `PASS verify-backup: verified in 38.65 s`, fases `backup, verify_backup, migrate`, `verify_backup {status: verified, tables: 26, cleanup: complete}`; (3) copia con manifiesto alterado (`actors`) → `backup_restore_mismatch: ... actors`, `status: failed`, `cleanup: complete`, sin `migrate`; ningún `kairos-verify-*` (contenedor ni red) tras (2) ni (3). `docker ps -a`, `volume ls` y `network ls` con filtro `knowledge-graphs` antes y después: idénticos (15 contenedores, 7 volúmenes, 6 redes; `cmp` sin diferencias). Retirado por nombre exacto: 7 contenedores, 5 redes, 2 volúmenes, 6 imágenes `rehearsal-kairos-ops-a-*`, secretos y `.private/rehearsal-kairos-ops-a`; `--filter name=kairos-ops` → 0. No se tocó `knowledge-graphs-*`, el Ollama del host (11434) ni la base desplegada.

**Criterios de aceptación**
- [x] El ensayo usa el proyecto `kairos-ops-a`, nunca `knowledge-graphs`, ni el Ollama del host (`--embed-stub`)
- [x] El contenedor `memory_restore_*` no queda vivo tras el ensayo
- [x] Los recursos del ensayo se retiran con `docker compose -p kairos-ops-a down -v`

**Subtareas**
- [x] Anotar `docker ps`/`volume ls` de la instalación antes
- [x] Ejecutar el ensayo (primer plano, de uno en uno)
- [x] Retirar el proyecto aislado y comparar
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-40).

### T-41 — Documentar copias, cifrado, retención y verificación

- **Descripción**: Documentar `backup`, `verify-backup`, `MEMORY_BACKUP_*`, `--backup-timeout`, `--verify-backup` y la custodia de la clave privada fuera del VPS. Fuente: CA-01 a CA-05 (documentación); R-03.
- **Changelog**: La documentación explica el manifiesto, `verify-backup`, el cifrado con age, la retención, `--backup-timeout` y `--verify-backup`, y avisa de que perder la clave privada es perder las copias.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real 0.01h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-40, T-37
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista `MEMORY_BACKUP_RECIPIENTS_FILE`, `MEMORY_BACKUP_REQUIRE_ENCRYPTION` y `MEMORY_BACKUP_KEEP` con defaults iguales a `config.py`, y `docs/operations.md` exige custodiar la clave privada fuera del VPS Salida (2026-11-16): lectura: `docs/configuration.md` lista `MEMORY_BACKUP_RECIPIENTS_FILE` (sin valor), `MEMORY_BACKUP_REQUIRE_ENCRYPTION` (`0`) y `MEMORY_BACKUP_KEEP` (`7`) como `config.py`; `docs/operations.md` exige custodiar la clave privada fuera del VPS (comprobado por script).

**Criterios de aceptación**
- [x] Nombres y defaults iguales al código
- [x] La advertencia R-03 (clave privada perdida = copias perdidas) está explícita

**Subtareas**
- [x] Actualizar `docs/configuration.md`
- [x] Actualizar `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-41).

### T-42 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: la suite del servidor pasa a 1154 pruebas y la CI exige ese mínimo (subió con las pruebas de manifiesto, cifrado, retención, restauración verificada y sus correcciones).
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.18h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-41
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md` (recuento), `server/memory_platform/tests/test_auth_cache.py` (la lista revisada de transacciones incluye `create_backup`)
- **Cubre (tests)**: —
- **Verificación**: Salida (2026-11-16, fix2): `docker build -f server/memory_platform/Dockerfile --target test -t kairos-test:i3p6f2 .` (exit 0): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "environment": "isolated-container-build", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1154}`; `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `Ran 45 tests ... OK`. (Cierre de fase: 1122; fix1: 1145.)
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-42).

### T-43 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: cifrado correcto (nada en claro), clave privada fuera del servidor (R-03) y borrado de copias (retención). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 6; copias sin volcado en claro en disco, huellas lineales y barrido de parciales con cerrojo.
- **Estado**: completado
- **Tiempo humano**: est. 12h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.60h (estimado) · real —
- **Supervisión**: est. 0.40h (≈25 % IA) · real —
- **Previsión IA**: 442 k in / 38 k out tok · ⚠️ verificar €
- **Dependencias**: T-42
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de las fase 6», T-43).

## Fase 7 — Copia externa programada y runbook de restauración (C-01)

**Estado**: completado · **Hito**: A · **Estimado**: 28.8h (24.0h base, de ellas 8.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.440 € · **Tokens est.**: 960 k

### T-44 — `admin backup-cycle` con destinos `dir:` y `rclone:`

- **Descripción**: Subcomando que encadena `pg_dump` → cifrado → manifiesto → `verify-backup` → subida al destino (`dir:<ruta>` o `rclone:<remoto>:<ruta>`) → verificación del sha256 en destino → retención local y remota. `rclone` fijado por versión en `operator`. Ejecución opcional de `prune-tables` al final del ciclo. Fuente: CA-06; O-01; P-02.
- **Changelog**: `backup-cycle` solo envía copias cifradas (a un directorio o a un remoto `rclone`), las lee de vuelta, repara manifiestos cortados y no borra copias más nuevas; sin destinatarios se niega a arrancar.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 0.70h (medido)
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/Dockerfile`, `server/memory_platform/tests/test_backup_cycle.py`, `server/memory_platform/offsite.py` (módulo nuevo: destinos y ciclo; añadido), `server/memory_platform/observability.py` (las dos series de la copia externa; añadido, es de T-45)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_cycle|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos
  - Salida (2026-11-16; imagen `kairos-test:i3p6f2` con el árbol de trabajo montado y `rclone` 1.60.1 instalado; la suite completa y su `MEMORY_TEST_RESULT` se pegan en T-48): `test_backup_cycle` → `Ran 23 tests ... OK` (17 de T-44 y 6 de T-45), con las 3 de `rclone` ejecutadas; junto a `test_deploy`, `test_deploy_isolation` y `test_observability`: `DEVRUN 109 0 0 0` (pruebas, fallos, errores, omitidas).

**Criterios de aceptación**
- [x] Con un destino `dir:` en un directorio temporal, `backup-cycle` sube copia cifrada y manifiesto, verifica el sha256 en destino y aplica `MEMORY_BACKUP_REMOTE_KEEP` (30)
- [x] Con un remoto `rclone` de tipo `local` configurado por el test, hace lo mismo (el test se omite solo si `rclone` falta, y el recuento de la suite lo exige presente)
- [x] Ningún servicio de nube real ni credencial en el repositorio; la configuración del remoto vive en el test

**Subtareas**
- [x] Escribir primero las pruebas de `dir:` (rojo)
- [x] Implementar el ciclo y los dos destinos
- [x] Fijar `rclone` por versión en `operator`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de la fase 7», T-44).

### T-45 — Fallos del destino externo: `backup_offsite_failed`, métrica y reintento

- **Descripción**: Con el destino inaccesible, registrar `backup_offsite_failed` (tipo de destino, sin credenciales), poner la métrica a 0, reintentar en el ciclo siguiente y no borrar copias locales; una copia con sha256 distinto no sube ni borra nada. Fuente: CA-06; sha256 no coincide (manejo de errores).
- **Changelog**: Todo fallo del ciclo de copia externa (base, `pg_dump`, cifrado, verificación o destino) pone la métrica a 0 y registra `backup_cycle_failed` en el bucle; se conservan las copias locales y reintenta.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.50h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-44
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/observability.py`, `server/memory_platform/tests/test_backup_cycle.py`, `server/memory_platform/offsite.py` (el manejo vive en `run_cycle`; añadido)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_cycle|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos
  - Salida (2026-11-16, misma imagen y montaje que T-44): `test_backup_cycle` → `Ran 23 tests ... OK`; `OffsiteFailureTests` (6 pruebas: destino ausente con reintento, sha256 distinto en destino, copia local alterada, copia antigua alterada, credenciales, argumentos de `rclone`) en `ok`. La suite completa se pega en T-48.

**Criterios de aceptación**
- [x] Con el destino inaccesible: `backup_offsite_failed`, métrica a 0, reintento en el ciclo siguiente y copias locales intactas (prueba)
- [x] Con `backup_checksum_mismatch` en destino no se sube ni se borra nada
- [x] Los registros no incluyen credenciales del destino

**Subtareas**
- [x] Escribir primero las pruebas de fallo (rojo)
- [x] Implementar el manejo y la métrica
- [x] Comprobar la redacción de credenciales
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de la fase 7», T-45).

### T-46 — Servicio Compose `memory-backup` (perfil `backup`) sin clave privada

- **Descripción**: Añadir al `docker-compose.yml` el servicio opcional `memory-backup` (perfil `backup`, imagen `operator`, sin puertos publicados) que ejecuta `admin backup-cycle` cada `MEMORY_BACKUP_INTERVAL`. Ningún servicio monta la clave privada. Aviso: la instalación desplegada lo recoge solo en su próximo `up`. Fuente: CA-06, CA-08; P-02.
- **Changelog**: Servicio opcional `memory-backup` (perfil `backup`): copia externa cada 24 h, sin puertos ni clave privada; se documentan los permisos de `rclone.conf`. `backup --prune` tolera una poda concurrente.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.51h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-45
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_backup_service.py`, `docs/configuration.md`, `scripts/deploy-memory.py` (override del servicio nuevo; añadido), `.gitignore` (`backup-config/`, `offsite/`; añadido), `server/memory_platform/backup.py` y `server/memory_platform/tests/test_backup_prune.py` (deuda de la carrera de dos `--prune`; añadidos), `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md` (frase «Fase 7» en Coordinación; añadido)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_service|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos
  - Salida (2026-11-16, misma imagen y montaje): `test_backup_service` + `test_backup_prune` → `Ran 20 tests ... OK`; `docker compose -p kairos-ops-cfg -f docker-compose.yml --profile backup config --format json` → exit 0 (sin crear recursos), `memory-backup`: perfil `backup`, sin `ports`, secretos solo `memory_dsn`, `/config` de solo lectura; `docker ps -a --filter name=kairos-ops` → 0; `git diff --stat -- ollama-proxy` vacío. La suite completa se pega en T-48.

**Criterios de aceptación**
- [x] `docker-compose.yml` define `memory-backup` con perfil `backup`, `MEMORY_BACKUP_INTERVAL` (24 h por defecto), `MEMORY_BACKUP_DESTINATION`, `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` por defecto y sin puertos publicados
- [x] Una prueba sobre el YAML (y `docker compose -p kairos-ops-cfg config` en local, que no crea recursos) demuestra que ningún servicio monta una clave privada
- [x] `ollama-proxy/default.conf.template` y los demás ficheros que monta la instalación desplegada no cambian

**Subtareas**
- [x] Escribir primero la prueba sobre el YAML (rojo)
- [x] Añadir el servicio con perfil y variables
- [x] Documentar en `docs/configuration.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de la fase 7», T-46).

### T-47 — Runbook de restauración desde la copia externa y ensayo automatizado

- **Descripción**: Escribir en `docs/operations.md` un runbook ejecutable (descargar del destino → verificar sha256 → descifrar con la clave privada fuera del servidor → `restore-check` en base vacía `memory_restore*` → comparar manifiesto) y un script de ensayo aislado que lo sigue con un destino simulado y resultado `restored_and_content_verified`. Fuente: CA-07; criterio de cierre 1 del plan director.
- **Changelog**: Runbook de restauración y `scripts/rehearse-restore.py`: ensayo aislado que restaura en un PostgreSQL efímero nuevo, destruye la clave (también ante SIGTERM) y comprueba que no queda nada.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.47h (estimado) · real 0.29h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 129 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-46
- **Tipo**: devops
- **Archivos**: `docs/operations.md`, `scripts/rehearse-restore.py`, `scripts/tests/test_rehearse_restore.py`, `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md` (frase «Fase 7»; añadido)
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_restore.py` → `OK`
  - `python scripts/rehearse-restore.py --project-name kairos-ops-b --embed-stub` → salida con `restored_and_content_verified`; el proyecto `kairos-ops-b` se elimina al terminar y `docker ps --filter name=knowledge-graphs` queda idéntico
  - Salida original (2026-11-16, antes de fix1): 8 pruebas en `OK` y ensayo real en 11 min 44 s con `restored_and_content_verified` (26 tablas) y `knowledge-graphs-*` idéntico; superada por la salida de fix1.
  - Salida fix1 (2026-11-16): `python -m unittest discover -s scripts/tests -p test_rehearse_restore.py` → `Ran 16 tests ... OK`. `python -u scripts/rehearse-restore.py --project-name kairos-ops-b --embed-stub` → exit 0 en 427 s: `{"cleanup": "complete", "cycle": {"bytes": 73490, "copy": "kairos-cycle-20261116T213555925413Z.dump.age", "destination": "dir"}, "project": "kairos-ops-b", "restore": {"database": "memory_restore_150557dfc3af", "server": "ephemeral", "status": "restored_and_content_verified", "tables": 26}, "status": "restored_and_content_verified", "steps": ["deploy", "keys", "cycle", "download", "verify", "decrypt", "restore"], "verify": {"sha256": "9ced5d82…"}}`. `docker ps -a`, `volume ls` y `network ls` con filtro `knowledge-graphs` antes y después: idénticos (31 líneas, `cmp` sin diferencias); `--filter name=kairos-ops`: 0 contenedores, 0 volúmenes, 0 redes, 0 imágenes `rehearsal-kairos-ops-*`; el directorio temporal (clave incluida) y el servidor efímero (`kairos-ops-b-restore-pg-*`, con su red y su volumen) eliminados.

**Criterios de aceptación**
- [x] El ensayo descarga del destino simulado (directorio), verifica el sha256, descifra con una clave de prueba generada en el ensayo, ejecuta `restore-check` en un proyecto aislado vacío y compara el manifiesto
- [x] Cada paso del runbook de `docs/operations.md` es un comando ejecutable que el ensayo ejecuta, y la clave privada de prueba nunca entra en un contenedor del servidor
- [x] El resultado es `restored_and_content_verified` y el ensayo deja la evidencia en `Notas`

**Subtareas**
- [x] Escribir el runbook primero y el test del script con dobles (rojo)
- [x] Implementar el script de ensayo
- [x] Ejecutar el ensayo real (primer plano, de uno en uno)
- [x] Retirar el proyecto aislado y comprobar que nada de `knowledge-graphs-*` cambió
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de la fase 7», T-47).

### T-48 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: la suite del servidor pasa a 1195 pruebas y la CI exige ese mínimo; la imagen de pruebas ya no define `RCLONE_VERSION`, que rclone leía como su opción `--version`.
- **Cerrada**: 2026-11-16
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.57h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-47
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md` (recuento), `server/memory_platform/Dockerfile` (el ARG de rclone pasa a `DEBIAN_RCLONE_VERSION`; añadido), `server/memory_platform/tests/test_backup_service.py` y `server/memory_platform/tests/test_backup_cycle.py` (controles positivos de rclone y la prueba del ARG; añadidos)
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - Salida (2026-11-16, tercera ejecución, tras corregir el ARG): `docker build -f server/memory_platform/Dockerfile --target test --progress=plain -t kairos-test:i3p7 .` (exit 0): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "environment": "isolated-container-build", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1184}`; `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `Ran 45 tests ... OK`. Imagen `operator` construida aparte con el ARG nuevo (`rclone` 1.60.1+dfsg-4, `age` 1.2.1) y retirada por nombre. (Cierre de fase: 1154 → 1184.)
  - Salida fix1 (2026-11-16): `docker build -f server/memory_platform/Dockerfile --target test --progress=plain -t kairos-test:i3p7f1 .` (exit 0): `MEMORY_TEST_RESULT {"database": "PostgreSQL", "environment": "isolated-container-build", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1195}`; `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `Ran 45 tests ... OK`. (Corrección de la revisión de la Fase 7: 1184 → 1195.)

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de la fase 7», T-48).

### T-49 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: copias externas (sha256 antes de borrar nada), ausencia de credenciales y de clave privada montada. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 7; al destino externo solo salen copias cifradas y la métrica de la copia externa baja a 0 ante cualquier fallo del ciclo.
- **Estado**: completado
- **Tiempo humano**: est. 8h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.07h (estimado) · real —
- **Supervisión**: est. 0.27h (≈25 % IA) · real —
- **Previsión IA**: 294 k in / 26 k out tok · ⚠️ verificar €
- **Dependencias**: T-48
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-16 — notas de la fase 7», T-49).

## Fase 8 — Cierre del hito A: no perder datos ni parar

**Estado**: completado · **Hito**: A · **Estimado**: 7.2h (6.0h base, de ellas 0.0h de revisión adversarial) · **Real**: — · **Coste est.**: 360 € · **Tokens est.**: 240 k

### T-50 — Ensayo de cierre del hito A: restauración externa y caída de base con el worker en marcha

- **Descripción**: Crear `scripts/rehearse-reliable-operations.py` y ejecutar el ensayo aislado del hito A: runbook de restauración (criterio de cierre 1) y parada/arranque de `memory-postgres` con trabajos en cola (criterio de cierre 2). Fuente: CA-07, CA-37 (parte del hito A); criterios de cierre 1 y 2.
- **Changelog**: Interno: ensayo aislado del cierre del hito A (restauración, huellas con 30.000 embeddings, parada y arranque de la base con el worker en marcha) y cinco endurecimientos de la copia externa: métrica a 0 al rechazar el arranque, evento `backup_cycle_failed` si falla la retención local, copia que desaparece en una poda concurrente y subida desde el mismo descriptor sin seguir enlaces.
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.33h (estimado) · real 0.94h (medido)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 92 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_rehearse_reliable_operations.py`, `server/memory_platform/admin.py`, `server/memory_platform/offsite.py`, `server/memory_platform/backup.py`, `server/memory_platform/tests/test_backup_cycle.py`, `server/memory_platform/tests/test_backup_prune.py`, `docs/operations.md` (deuda de la revisión de la Fase 7 y medida de las huellas), `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md` (ítem «Fase 8» de Coordinación; añadido)
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_reliable_operations.py` → `OK`
  - `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-c --embed-stub --stage a` → `restored_and_content_verified` y `worker_survived_db_restart` con contador de reinicios igual y 0 trabajos `failed`
  - Salida (2026-11-16/17): `python -I -m unittest discover -s scripts/tests -p test_rehearse_reliable_operations.py` → `Ran 11 tests ... OK` (4 mutantes del script: 4 caen). Ensayo real (segundo intento; el primero cayó en `compose start memory-worker` por el `memory-migrate` ya retirado y se corrigió con `docker stop/start` por id) → exit 0: `{"cleanup": "complete", "project": "kairos-ops-c", "stage": "a", "status": "restored_and_content_verified", "restore": {"status": "restored_and_content_verified", "tables": 26, "server": "ephemeral"}, "cycle": {"bytes": 2235899, "destination": "dir"}, "seed": {"embeddings": 30000, "dims": 768}, "queue": {"events": 300, "pending_before_worker": 300}, "worker_survived_db_restart": {"restarts_before": 0, "restarts_after": 0, "same_start": true, "running": true, "running_while_down": true, "pending_at_stop": 256, "down_seconds": 30, "jobs": {"succeeded": 301}, "failed": 0}, "fingerprints": {"rows": 30001, "table_bytes": 132268032, "embeddings_seconds": 62.07, "all_tables_seconds": 56.34, "seconds_per_row": 0.002069, "megabytes_per_second": 2.1, "seconds_for_5_gb": 2519, "backup_timeout_seconds": 3600, "within_timeout": true}, "timings": {"backup_cycle_seconds": 93.1, "restore_step_seconds": 111.8}}`. `docker ps -a`, `volume ls`, `network ls` filtrados por `knowledge-graphs` (con `StartedAt` y reinicios), antes y después: idénticos; `kairos-ops` → 0 contenedores, 0 volúmenes, 0 redes y 0 imágenes `rehearsal-kairos-ops`; el Ollama del host sigue en 200.

**Criterios de aceptación**
- [x] Con trabajos en cola, parar y arrancar `memory-postgres` del ensayo: `memory-worker` no se reinicia por error propio (contador de reinicios igual), la cola se vacía y ningún trabajo queda `failed` por esa caída
- [x] El ensayo es de un solo proyecto aislado `kairos-ops-c`, sin recursos `knowledge-graphs-*` ni Ollama del host
- [x] La evidencia (salida, contadores) queda en `Notas`

**Subtareas**
- [x] Escribir el script por etapas (`--stage a|b|all`) y su prueba con dobles
- [x] Ejecutar la etapa A (primer plano, de uno en uno)
- [x] Retirar el proyecto aislado
- [x] `usage-meter start/close` de la tarea

**Notas**: Evidencia en `Verificación`. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e419ee5c56ac`.

### T-51 — Comprobaciones de cierre del hito A

- **Descripción**: Comprobar migraciones aditivas, diff aditivo de contratos frente a `contracts_base`, ausencia de referencias a `knowledge-graphs-*` y al puerto 11434 (salvo para rechazarlos), alcance declarado y suite. Fuente: CA-38 (parte del hito A).
- **Changelog**: Interno: la suite del servidor pasa a 1203 pruebas y la CI exige ese mínimo; comprobaciones de cierre del hito A (alcance, referencias prohibidas, migraciones y contratos aditivos).
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.62h (medido: 0.08 + 0.54 del fix1 de la revisión)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-50
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`, `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `README.md`, `docs/operations.md` (mínimo de la suite: 1203; añadidos), `docs/roadmap/2026-11-12-three-components/retro.md` y `docs/roadmap/CALIBRATION.md` (retro de la Iniciativa 2 commiteada en esta rama antes de la Fase 1, que `scope-check --base origin/main` ve; añadidos), `server/memory_platform/tests/test_worker.py` (prueba con 0,1 s de holgura que falló de forma intermitente en la CI del PR #4)
- **Cubre (tests)**: —
- **Verificación**:
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `grep -rn "knowledge-graphs-\|11434" scripts server/memory_platform/tests docker-compose.yml --include=*.py --include=*.yml` → solo apariciones que rechazan esos recursos (anotadas en `Notas`)
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Suite con 0 fallos y 0 omitidos; `test_migrations_additive` y `test_contract_additive` pasan
- [x] Ninguna referencia nueva a `knowledge-graphs-*` o 11434 salvo para rechazarlos
- [x] Revisión del hito: lectura del diff completo del hito A por una persona/lente distinta de la de cada fase, con hallazgos en `review.md`

**Subtareas**
- [x] Ejecutar `scope-check.py`
- [x] Buscar referencias prohibidas
- [x] Ejecutar la suite y los contratos
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-51).

### T-52 — Notas de cambio del hito A

- **Descripción**: Añadir al `CHANGELOG.md` y `CHANGELOG.es.md` (sección sin publicar) las novedades del hito A: copias verificadas y cifradas, worker resistente, pool y plazos, retención. Fuente: CA-38 (documentación del hito A).
- **Changelog**: Interno: las novedades del hito A (copias verificadas y cifradas, copia externa, runbook, worker resistente, pool y plazos, retención) quedan en el CHANGELOG en inglés y en español, sin versión nueva.
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.04h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-51
- **Tipo**: docs
- **Archivos**: `CHANGELOG.md`, `CHANGELOG.es.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: ambos CHANGELOG describen, en una frase por cambio visible, copias cifradas y verificadas, `store_unavailable`/`attempts_exhausted`, pool y plazos, `prune-tables` (ventanas) y la nota de que `events` no se poda por defecto

**Criterios de aceptación**
- [x] Los dos idiomas dicen lo mismo
- [x] La versión sigue siendo la del árbol (0.4.0) hasta la tarea de cierre

**Subtareas**
- [x] Redactar las entradas
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-52).

### T-53 — Pull request del hito A (solo con OK del usuario)

- **Descripción**: Abrir el PR del hito A desde `feat/reliable-operations` para que la Iniciativa 5 pueda empezar con A fusionado. El PR solo se abre con el OK expreso del usuario; la tarea no se marca hecha hasta que el PR exista. Fuente: P-09 (un PR por hito).
- **Changelog**: Interno: PR del hito A (#4) fusionado en `main`.
- **Estado**: completado
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.3h (estimado; incluye diagnosticar y corregir la prueba intermitente)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-52
- **Tipo**: devops
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/tasks.md`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view --json number,state,headRefName` → PR abierto desde `feat/reliable-operations` (`state: OPEN`)

**Criterios de aceptación**
- [x] Hay OK expreso del usuario anotado en `Notas`
- [x] El PR enlaza el ledger y lista los criterios de cierre 1 y 2 con su evidencia
- [x] La CI del PR está en verde o sus fallos explicados

**Subtareas**
- [x] Pedir el OK al usuario
- [x] Abrir el PR con el cuerpo y las evidencias
- [x] Anotar el número en `Notas`
- [x] `usage-meter start/close` de la tarea

**Notas**: OK expreso del usuario: «Fusiónalo cuando esté en verde» (abrir el PR de cada hito y fusionarlo con la CI en verde, merge commit, conservando la rama); esto sustituye al «No se hace merge» original. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `859ff3e36dd6`.

---

## Fase 9 — Compose: límites, healthchecks, rotación y `extra_hosts` (C-04)

**Estado**: completado · **Hito**: B · **Estimado**: 19.8h (16.5h base, de ellas 5.5h de revisión adversarial) · **Real**: — · **Coste est.**: 990 € · **Tokens est.**: 660 k

### T-54 — `mem_limit` y `cpus` configurables en todos los servicios

- **Descripción**: Declarar `mem_limit` y `cpus` en todos los servicios con variables `MEMORY_<SERVICIO>_MEM_LIMIT`/`_CPUS` y valores por defecto documentados para 32 GB locales y un VPS pequeño. Aviso: la instalación desplegada lo recoge solo en su próximo `up`. Fuente: CA-20; O-05; R-06.
- **Changelog**: `memory-backup` ya no sale a Internet salvo que el destino sea `rclone:` (se añade con un fichero Compose aparte) y todos los servicios llevan límites de memoria y CPU configurables (`MEMORY_<SERVICIO>_MEM_LIMIT`/`_CPUS`).
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.33h (estimado) · real 0.09h (medido)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 92 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`, `docs/configuration.md`, `docker-compose.backup-rclone.yml`, `server/memory_platform/Dockerfile`, `server/memory_platform/tests/test_backup_service.py`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Todos los servicios de `docker-compose.yml` declaran `mem_limit` y `cpus` configurables por variable (prueba sobre el YAML y `docker compose -p kairos-ops-cfg config` en local)
- [x] `docs/configuration.md` documenta los valores por defecto para 32 GB locales y para un VPS pequeño
- [x] `memory-postgres` y `memory-worker` no quedan con un límite que los mate durante el relleno (valor justificado en `Notas`)

**Subtareas**
- [x] Escribir primero la prueba sobre el YAML (rojo)
- [x] Añadir límites y variables
- [x] Documentar
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-54).

### T-55 — Rotación de logs en `ollama` y `memory-postgres` y `extra_hosts`

- **Descripción**: Hacer que `ollama` y `memory-postgres` hereden la rotación `json-file` (`max-size`, `max-file`) de `x-process` y añadir `extra_hosts: ["host.docker.internal:host-gateway"]` al servicio `ollama` (el VPS es Linux). Fuente: CA-22, CA-25; O-05, O-06.
- **Changelog**: `ollama`, `memory-postgres` y `memory-files` rotan sus logs como el resto de servicios y el proxy `ollama` resuelve `host.docker.internal` también en Linux (el VPS).
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.03h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Todos los servicios rotan logs con `json-file`, `max-size` y `max-file` (prueba sobre el YAML)
- [x] `ollama` declara `extra_hosts: ["host.docker.internal:host-gateway"]` y `docs/operations.md` explica el caso Linux
- [x] `ollama-proxy/default.conf.template` sin cambios (`git diff --stat` lo confirma)

**Subtareas**
- [x] Escribir primero la prueba (rojo)
- [x] Aplicar `x-process`/`logging` a los dos servicios
- [x] Añadir `extra_hosts` y la nota de Linux
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-55).

### T-56 — Latido del worker y healthcheck de `memory-worker`

- **Descripción**: El bucle del worker escribe `/tmp/kairos-worker-heartbeat` en cada vuelta (solo si `last_store_ok` es reciente: R-01) y `memory-worker` declara un healthcheck sobre el fichero; con el bucle parado, el contenedor pasa a `unhealthy` en ≤ plazo del último latido + `interval × retries`. Enmienda (revisión de la Fase 9, n.º 1; aprobada por el orquestador): el original decía «por antigüedad del fichero» y «≤ `interval × retries`»; el fichero guarda ahora el plazo del siguiente latido. Fuente: CA-21; O-05; R-01.
- **Changelog**: `memory-worker` pasa a `unhealthy` si su bucle se para o no alcanza la base durante unos minutos (latido en `/tmp/kairos-worker-heartbeat`, healthcheck cada 30 s).
- **Estado**: completado
- **Cerrada**: 2026-11-17
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real 0.10h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: backend
- **Archivos**: `server/memory_platform/worker.py`, `docker-compose.yml`, `server/memory_platform/tests/test_worker_heartbeat.py`, `docs/operations.md`, `server/memory_platform/tests/test_worker_db_down.py` (fix1, n.º 5: `last_store_ok` arranca en `None`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_worker_heartbeat|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Prueba unitaria con reloj inyectado: el latido avanza en cada vuelta sana y no avanza si la base lleva caída más que el umbral
- [x] `memory-worker` declara healthcheck por antigüedad de `/tmp/kairos-worker-heartbeat` (fichero en el `tmpfs` existente) con `interval × retries` documentados — Enmienda (revisión de la Fase 9, n.º 1, aprobada por el orquestador): el healthcheck compara con el reloj el plazo que guarda el fichero, no su antigüedad, y se documentan también el plazo del latido y su cota
- [x] El caso real de `unhealthy` con el bucle detenido se ejercita en el ensayo de la Fase 10

**Subtareas**
- [x] Escribir primero la prueba del latido (rojo)
- [x] Escribir el latido en el bucle (usa `last_store_ok` de la Fase 2)
- [x] Añadir el healthcheck al compose
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (3) — notas de T-56 y de las tareas T-61 a T-64», T-56).

### T-57 — Healthcheck de `memory-web`

- **Descripción**: Añadir healthcheck a `memory-web` con `GET /health/live` del proxy nginx. Fuente: CA-21; O-05.
- **Changelog**: `memory-web` tiene healthcheck (consulta `/health/live` del propio proxy), por lo que `docker compose ps` ya muestra si el portal responde.
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `memory-web` declara healthcheck contra `/health/live` y la prueba sobre el YAML lo comprueba
- [x] `web/nginx.conf` no cambia (la ruta ya existe en `:44`)

**Subtareas**
- [x] Escribir primero la prueba (rojo)
- [x] Añadir el healthcheck
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-57).

### T-58 — Documentar límites, healthchecks, rotación y `extra_hosts`

- **Descripción**: Completar `docs/configuration.md` y `docs/operations.md` con límites por servicio, healthchecks y el caso Linux de `host.docker.internal`. Fuente: CA-20, CA-21, CA-22, CA-25 (documentación).
- **Changelog**: Los manuales de configuración y de operación listan los límites por servicio, los healthchecks, la rotación de logs y el caso Linux de `host.docker.internal`.
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.03h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-56, T-57, T-55
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `server/memory_platform/tests/test_compose_limits.py`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista las variables `MEMORY_*_MEM_LIMIT`/`_CPUS` por servicio con valores por defecto

**Criterios de aceptación**
- [x] Variables y valores iguales a `docker-compose.yml`

**Subtareas**
- [x] Actualizar los dos manuales
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-58).

### T-59 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**: Interno: la suite del servidor pasa a 1228 pruebas (mínimo de la CI 1228).
- **Cerrada**: 2026-11-17
- **Estado**: completado
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.5h (estimado; cuatro pasadas de la suite)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-58
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md` (el recuento de pruebas que repite), `server/memory_platform/Dockerfile`, `server/memory_platform/tests/test_backup_encryption.py`, `server/memory_platform/tests/test_metrics.py` (la suite completa de la fase: el test stage copia los dos manuales que leen las pruebas nuevas; la búsqueda de claves privadas casa la clave real y no el prefijo que nombra `operations.md`; holgura en una prueba de plazo intermitente)
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [x] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [x] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [x] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: Tras el fix2: `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 1241}`; mínimo a 1241 en los cuatro sitios. archivadas en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7», T-59).

### T-60 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: R-06 (límites que matan servicios) y R-08 (ficheros que monta la instalación desplegada). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**: Interno: revisión adversarial de la fase 9; el healthcheck del worker sigue un plazo que escribe el propio latido, los `cpus` por defecto no impiden arrancar en ningún anfitrión y la guía de Ollama en Linux lo deja al alcance solo del proxy.
- **Estado**: completado
- **Tiempo humano**: est. 5.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.73h (estimado) · real 1.5h (estimado; cuatro intentos de revisión)
- **Supervisión**: est. 0.18h (≈25 % IA) · real —
- **Previsión IA**: 202 k in / 18 k out tok · ⚠️ verificar €
- **Dependencias**: T-59
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [x] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [x] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [x] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [x] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [x] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [x] Lente B: mutantes en memoria sobre cada control nuevo
- [x] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [x] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (4) — notas de tareas cerradas de las fases 1 a 9», T-60).

## Fase 10 — Despliegue: bloqueo, etiquetado y retroceso (C-04)

**Estado**: en-progreso · **Hito**: B · **Estimado**: 34.2h (28.5h base, de ellas 9.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.710 € · **Tokens est.**: 1140 k

### T-61 — Bloqueo exclusivo de despliegue y `--break-lock`

- **Descripción**: Fichero de bloqueo exclusivo en el directorio privado del proyecto con PID, host y hora; un segundo despliegue termina con `deployment_locked` sin ejecutar fases; un bloqueo con PID muerto se informa y solo se rompe con `--break-lock`. Fuente: CA-23; O-06.
- **Changelog**: Un segundo despliegue del mismo proyecto termina con `deployment_locked`; el bloqueo es del sistema operativo, no sigue enlaces simbólicos, no borra nada y avisa si el despliegue anterior no terminó.
- **Estado**: completado
- **Cerrada**: 2026-11-17
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.47h (estimado) · real 0.17h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 129 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_lock.py`, `scripts/rehearse-restore.py` (una línea: `deployment.lock` entra en `PRIVATE_FILES`, para que su limpieza reconozca el directorio privado del proyecto)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy_lock|test_deploy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Un segundo despliegue sobre el mismo proyecto termina con `deployment_locked` (PID y hora del dueño) sin ejecutar ninguna fase (doble de `subprocess` sin llamadas)
- [x] Un bloqueo con PID muerto se informa y solo se rompe con `--break-lock`
  - (enmienda, revisión de la fase 10, fix3 y fix4, con la delegación del usuario; el criterio de arriba no se reescribe: con el bloqueo del sistema operativo `--break-lock` ya no rompe nada y no es necesario ni siquiera para un fichero de otro equipo —si el sistema deja tomar el bloqueo se toma sin la opción, que solo nombra la toma—; lo que se «informa» es lo que un despliegue que no terminó dejó en el fichero, con un mensaje que no afirma que murió cuando el fichero es de otro equipo; el fichero de bloqueo debe ser normal y de un solo nombre.)
  - (enmendado en la revisión de la fase 10, fix2, n.º 3-5 y 8: el bloqueo pasa a ser del sistema operativo (`flock`/`msvcrt.locking`), que lo libera cuando el proceso muere; un dueño muerto de este equipo ya no deja nada que romper y el siguiente despliegue lo toma sin opciones; `--break-lock` queda solo para un fichero de bloqueo escrito por otro equipo. El criterio de arriba se conserva como se aprobó; véase la nota de enmienda de CA-23 en `spec.md`.)
- [x] El bloqueo se libera también si una fase falla o el proceso se interrumpe

**Subtareas**
- [x] Escribir primero las pruebas (rojo)
- [x] Implementar el bloqueo con creación exclusiva
- [x] Añadir `--break-lock`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (12) — notas de T-61 a T-65 hasta fix4», T-61).

### T-62 — Etiquetas locales `kairos-*:<versión>-<marca>` y registro en `deployment-status.json`

- **Descripción**: Etiquetar las imágenes locales antes de cada construcción (`kairos-*:<versión>-<marca>`), conservar las dos anteriores y registrar las etiquetas en `deployment-status.json`. Fuente: CA-24; O-06; P-08.
- **Changelog**: Cada despliegue etiqueta antes de construir las imágenes del último bueno como `kairos-*:<versión>-<marca>` y lo registra de forma duradera en `deployment-status.json`, aunque se interrumpa.
- **Estado**: completado
- **Cerrada**: 2026-11-17
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real 0.14h (medido)
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-61
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_rollback.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy_rollback|test_deploy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] Antes de construir, las imágenes vigentes se etiquetan `kairos-*:<versión>-<marca>` y `deployment-status.json` registra las etiquetas anterior y actual
  - (aclarado en la revisión de la fase 10, fix2, n.º 1-2: «las imágenes vigentes» son las del último despliegue que terminó bien (`images.good`, por id), no lo que haya en `:latest` ni lo que ejecuten los contenedores en ese momento.)
  - (enmendado en la revisión de la fase 10, n.º 6: «actual» se registra como el id de `:latest` tras construir (`images.current`) y su versión (`images.current_versions`); la imagen actual no tiene etiqueta hasta que el despliegue siguiente la etiqueta como `previous`, porque etiquetarla antes la haría pasar por «anterior» de sí misma.)
- [x] Se conservan las dos anteriores y las más antiguas se retiran (prueba con dobles)
- [x] Los nombres de imagen del despliegue aislado no coinciden con los de la instalación

**Subtareas**
- [x] Escribir primero las pruebas con dobles (rojo)
- [x] Implementar el etiquetado y el registro
- [x] Retirada de etiquetas antiguas
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (12) — notas de T-61 a T-65 hasta fix4», T-62).

### T-63 — `--rollback` sin migrar

- **Descripción**: `--rollback` vuelve a las etiquetas registradas sin migrar; sin etiquetas anteriores falla con `no_previous_images` sin tocar servicios. Se apoya en que las migraciones son aditivas. Fuente: CA-24; O-06; P-08.
- **Changelog**: `--rollback` restaura contenedores y `:latest` de la versión anterior sin migrar, también tras un despliegue interrumpido; sin imágenes anteriores falla con `no_previous_images` y no cambia nada.
- **Estado**: completado
- **Cerrada**: 2026-11-17
- **Tiempo humano**: est. 4.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.60h (estimado) · real 0.16h (medido)
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 166 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-62
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy_rollback.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy_rollback|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [x] `--rollback` recompone los servicios con las etiquetas anteriores del registro y no ejecuta `migrate` (prueba con dobles)
- [x] Sin etiquetas anteriores falla con `no_previous_images` y no cambia servicios
- [x] `docs/operations.md` explica el retroceso y su límite (imágenes, no datos)

**Subtareas**
- [x] Escribir primero las pruebas (rojo)
- [x] Implementar `--rollback`
- [x] Documentar
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (12) — notas de T-61 a T-65 hasta fix4», T-63).

### T-64 — Ensayo aislado de retroceso y de latido `unhealthy`

- **Descripción**: Ejecutar un ensayo aislado con dos despliegues etiquetados y `--rollback`, y comprobar que con el bucle del worker detenido el contenedor pasa a `unhealthy`. Fuente: CA-24, CA-21 (caso del ensayo).
- **Changelog**: Un ensayo aislado (`--stage rollback`) demuestra el retroceso de imágenes sin migrar y que `memory-worker` pasa a `unhealthy` con el bucle parado; un trabajo que pierde su concesión se cancela en vez de dejar al worker `unhealthy`.
- **Estado**: completado
- **Cerrada**: 2026-11-17
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real 0.57h (medido)
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-63, T-56
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_rehearse_reliable_operations.py`, `server/memory_platform/worker.py` (deuda n.º 6: cancelar el trabajo al perder la concesión), `server/memory_platform/tests/test_worker_heartbeat.py` (deudas n.º 6 y 7: pruebas y mutantes), `docs/operations.md` (el comportamiento nuevo del worker y la etapa del ensayo, E3)
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-d --embed-stub --stage rollback` → `rollback_ok` con `content-manifest` igual, una búsqueda correcta y `worker_unhealthy` en ≤ plazo del último latido + `interval × retries` (enmienda de la revisión de la Fase 9, n.º 1)
  - `docker ps --filter name=knowledge-graphs` y `docker volume ls --filter name=knowledge-graphs` → idénticos antes y después

**Criterios de aceptación**
- [x] Los servicios vuelven a las etiquetas anteriores sin migrar, `content-manifest` es igual y una búsqueda funciona
- [x] Con el bucle detenido, `memory-worker` pasa a `unhealthy` en ≤ `interval × retries` — Enmienda (revisión de la Fase 9, n.º 1, aprobada por el orquestador): en ≤ plazo del último latido + `interval × retries`
  - (enmienda, revisión de la fase 10, fix3 n.º 9, con la delegación del usuario; antes «aclarado» en fix2 n.º 7: la cota se deduce además de la duración de las sondas, porque Docker espera `interval` después de que cada una termina, y con sondas que agotan su plazo AMPLÍA la cota hasta ~20 s por encima del texto original; véase la enmienda de CA-21 en `spec.md`.)
- [x] Evidencia anotada en `Notas`; proyecto aislado retirado al terminar

**Subtareas**
- [x] Añadir la etapa `rollback` al script
- [x] Ejecutar el ensayo (primer plano, de uno en uno)
- [x] Retirar el proyecto
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (12) — notas de T-61 a T-65 hasta fix4», T-64).

### T-65 — Documentar bloqueo y retroceso

- **Descripción**: Documentar `deployment_locked`, `--break-lock`, las etiquetas locales y `--rollback`. Fuente: CA-23, CA-24 (documentación).
- **Changelog**: La guía de operaciones explica `deployment_locked`, `--break-lock`, las etiquetas locales de las imágenes y `--rollback` (con su límite: imágenes, no datos).
- **Estado**: completado
- **Cerrada**: 2026-11-17
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real 0.14h (medido)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-64
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `server/memory_platform/tests/test_deploy_rollback.py` (una prueba que compara los nombres y códigos del manual con los del script), `scripts/deploy-memory.py` (constantes `EXIT_LOCKED` y `EXIT_NO_PREVIOUS_IMAGES` para esa comparación)
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/operations.md` describe `deployment_locked`, `--break-lock`, las etiquetas `kairos-*:<versión>-<marca>`, `--rollback` y `no_previous_images`

**Criterios de aceptación**
- [x] Nombres y códigos iguales al script

**Subtareas**
- [x] Actualizar `docs/operations.md`
- [x] `usage-meter start/close` de la tarea

**Notas**: archivadas en `execution-history.md` (sección «Compactación 2026-11-17 (12) — notas de T-61 a T-65 hasta fix4», T-65).

### T-66 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-65
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [ ] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [ ] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [ ] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Cierra la fase: no se abre la revisión adversarial con la suite en rojo.

### T-67 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: el bloqueo no debe dejar despliegues colgados; el retroceso no debe migrar ni tocar datos. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 9.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.27h (estimado) · real —
- **Supervisión**: est. 0.32h (≈25 % IA) · real —
- **Previsión IA**: 350 k in / 30 k out tok · ⚠️ verificar €
- **Dependencias**: T-66
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [ ] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [ ] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [ ] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [ ] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [ ] Lente B: mutantes en memoria sobre cada control nuevo
- [ ] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [ ] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 11 — Sonda de ida y vuelta (C-06)

**Estado**: borrador · **Hito**: B · **Estimado**: 23.4h (19.5h base, de ellas 6.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.170 € · **Tokens est.**: 780 k

### T-68 — Proyecto `kairos-probe` y clave de alcance acotado

- **Descripción**: Aprovisionar el proyecto dedicado `kairos-probe` y una clave con alcance solo sobre él, sin tocar proyectos de usuarios. Fuente: CA-33; M-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/tests/test_probe_provisioning.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_probe_provisioning|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] La clave de la sonda solo tiene alcance sobre `kairos-probe` (una escritura en otro proyecto da 403, prueba)
- [ ] El aprovisionamiento es idempotente y no escribe en proyectos de usuarios
- [ ] La clave no se imprime en registros ni se guarda en el repositorio

**Subtareas**
- [ ] Escribir primero las pruebas (rojo)
- [ ] Implementar el aprovisionamiento idempotente
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:240-321` (subcomandos), `store_auth.py:36-77` (concesiones por proyecto) y la clave temporal de verificación de `deploy-memory.py --roundtrip`.

### T-69 — `admin probe`: escribir, esperar recibo `embed`, buscar, retirar

- **Descripción**: `admin probe` contra `/v1`: escribe un recuerdo sintético con marca única, espera su recibo `embed`, lo busca con la capa semántica, lo retira y mide cada etapa; un fallo en cualquier etapa termina con código ≠ 0, `probe_failed` con `stage` (`write`, `index`, `search`, `retire`) y `kairos_probe_success 0`, e intenta retirar lo escrito. Fuente: CA-30, CA-31; M-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-68
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/observability.py`, `server/memory_platform/tests/test_probe.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_probe|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Sobre un servidor sano la sonda termina en 0 y publica la duración de cada etapa
- [ ] Con el worker parado, falla en ≤ `MEMORY_PROBE_TIMEOUT` con `probe_failed`, `stage=index` y código ≠ 0, e intenta retirar lo escrito
- [ ] Tras una ejecución no quedan recuerdos activos de la sonda (solo retirados)
- [ ] El tiempo se mide con reloj inyectado en las pruebas (sin esperas reales)

**Subtareas**
- [ ] Escribir primero las pruebas (rojo)
- [ ] Implementar las cuatro etapas y su clasificación de fallos
- [ ] Publicar métricas `kairos_probe_*`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `scripts/memory-client.py` y `mcp/kairos_mcp` (clientes de `/v1`), `tests/chain_harness.py` (cadena en proceso) y `observability.py:189-213` (métricas). Defaults `MEMORY_PROBE_TIMEOUT` 120 s.

### T-70 — Pruebas de la sonda con worker real y worker parado

- **Descripción**: Probar la sonda de extremo a extremo con la cadena en proceso: sana, con worker parado, con búsqueda sin resultado, con base cortada, y que ningún test apunta a recursos `knowledge-graphs-*`. Fuente: CA-30, CA-31, CA-33.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-69
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_probe.py`, `server/memory_platform/tests/test_probe_provisioning.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_probe|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Cuatro escenarios cubiertos: sana, worker parado (`stage=index`), búsqueda sin resultado (`stage=search`) y base cortada con `FaultProxy`
- [ ] Mutante comprobado: quitar la retirada final o el control de etapa deja una prueba en rojo
- [ ] Un test recorre los ficheros de la sonda y falla si aparece `knowledge-graphs-` o el puerto 11434

**Subtareas**
- [ ] Tabla de escenarios
- [ ] Escribir las pruebas
- [ ] Aplicar mutantes
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/chain_harness.py`, `tests/fault_proxy.py` (Fase 1).

### T-71 — Documentar la sonda

- **Descripción**: Documentar `admin probe`, sus etapas, códigos de salida y variables en los manuales. Fuente: CA-30, CA-31 (documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real —
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 18 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-70
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/operations.md` describe las etapas, `probe_failed` y el aprovisionamiento de `kairos-probe`; `docs/configuration.md` lista `MEMORY_PROBE_TIMEOUT`

**Criterios de aceptación**
- [ ] Nombres y defaults iguales al código

**Subtareas**
- [ ] Actualizar los manuales
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: `docs/operations.md`.

### T-72 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-71
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [ ] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [ ] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [ ] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Cierra la fase: no se abre la revisión adversarial con la suite en rojo.

### T-73 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: la clave de la sonda es una credencial más (alcance mínimo) y la sonda no ensucia proyectos de usuarios. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.87h (estimado) · real —
- **Supervisión**: est. 0.22h (≈25 % IA) · real —
- **Previsión IA**: 239 k in / 21 k out tok · ⚠️ verificar €
- **Dependencias**: T-72
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [ ] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [ ] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [ ] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [ ] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [ ] Lente B: mutantes en memoria sobre cada control nuevo
- [ ] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [ ] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 12 — Cola atascada, servicio de sonda y `kairos doctor` (C-06)

**Estado**: borrador · **Hito**: B · **Estimado**: 23.4h (19.5h base, de ellas 6.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.170 € · **Tokens est.**: 780 k

### T-74 — `kairos_jobs_oldest_pending_seconds` y aviso de cola atascada

- **Descripción**: Publicar `kairos_jobs_oldest_pending_seconds` en `/metrics` y hacer que la sonda avise cuando supera `MEMORY_QUEUE_STUCK_SECONDS` (900 s). Añadir un fichero de reglas Prometheus de ejemplo. Fuente: CA-32; M-06; P-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/observability.py`, `server/memory_platform/admin.py`, `server/memory_platform/tests/test_observability.py`, `docs/examples/prometheus-rules.yml`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_observability|test_probe|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `/metrics` publica `kairos_jobs_oldest_pending_seconds` (0 con la cola vacía) leyendo solo `pending`, `running` y `unknown`, sin recorrer filas terminales
- [ ] La sonda avisa con `queue_stuck` cuando la antigüedad supera `MEMORY_QUEUE_STUCK_SECONDS` (prueba con reloj inyectado)
- [ ] `docs/examples/prometheus-rules.yml` contiene reglas de ejemplo para `kairos_probe_success`, antigüedad de cola y `kairos_jobs_failed`

**Subtareas**
- [ ] Escribir primero las pruebas (rojo)
- [ ] Añadir la métrica con el índice parcial de la Fase 3
- [ ] Añadir el aviso a la sonda y el fichero de reglas
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `observability.py:189-213` y `:205-208` (`kairos_jobs_queue_depth`, `kairos_jobs_failed`) y `tests/test_observability.py`. Canal de alerta (P-06): métrica, evento y código de salida; el envío a personas es de la Iniciativa 5.

### T-75 — Servicio Compose `memory-probe` (perfil propio)

- **Descripción**: Añadir el servicio opcional `memory-probe` (perfil propio, sin puertos publicados) que ejecuta la sonda cada `MEMORY_PROBE_INTERVAL` (300 s). Aviso: la instalación desplegada lo recoge solo en su próximo `up`. Fuente: CA-30; M-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-74
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `memory-probe` define perfil propio, `MEMORY_PROBE_INTERVAL`, límites, healthcheck y rotación de logs como el resto, sin puertos publicados
- [ ] La prueba sobre el YAML confirma que ningún servicio monta credenciales fuera de las variables documentadas
- [ ] Ningún fichero que monta la instalación desplegada cambia

**Subtareas**
- [ ] Escribir primero la prueba (rojo)
- [ ] Añadir el servicio
- [ ] Documentar variables
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `memory-backup` de la Fase 7 y `docker-compose.yml:31-85`.

### T-76 — `kairos doctor`: aviso de cola en disco del cliente

- **Descripción**: `kairos doctor` avisa cuando la cola en disco del cliente tiene capturas pendientes más antiguas que un umbral, sin telemetría del cliente al servidor. Fuente: CA-32; M-06; P-07.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: frontend
- **Archivos**: `client/lib/outbox.mjs`, `client/lib/mcp.mjs`, `client/tests/doctor-outbox.test.mjs`
- **Cubre (tests)**: —
- **Verificación**: `cd client && npm test` → 0 fallos, con las pruebas de `doctor-outbox` en verde

**Criterios de aceptación**
- [ ] `doctor` informa de la antigüedad de la cola en disco y avisa por encima del umbral (prueba con reloj inyectado)
- [ ] No envía nada al servidor (prueba sin red)
- [ ] La salida actual de `doctor` no cambia cuando no hay capturas pendientes

**Subtareas**
- [ ] Escribir primero la prueba (rojo)
- [ ] Leer la antigüedad en `outbox.mjs`
- [ ] Añadir el aviso a `doctor`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `client/lib/outbox.mjs:177` (cola en disco) y `client/lib/mcp.mjs` (`doctor`); tests en `client/tests/`. Cualquier test del cliente usa directorios temporales, nunca el perfil real.

### T-77 — Ensayo aislado: sonda con `memory-worker` parado

- **Descripción**: Añadir al script de ensayo la etapa `probe` y ejecutarla: sonda sana y sonda con `memory-worker` parado (criterio de cierre 3). Fuente: CA-31 (ensayo); criterio de cierre 3.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-74, T-75
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_rehearse_reliable_operations.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-e --embed-stub --stage probe` → `probe_ok` en sano y `probe_failed stage=index` con código ≠ 0 y `kairos_probe_success 0` con el worker parado
  - `docker ps --filter name=knowledge-graphs` → idéntico antes y después

**Criterios de aceptación**
- [ ] La sonda sana termina en 0; con `memory-worker` parado falla en ≤ `MEMORY_PROBE_TIMEOUT` con `stage=index`
- [ ] Evidencia anotada en `Notas`; proyecto aislado retirado

**Subtareas**
- [ ] Añadir la etapa `probe`
- [ ] Ejecutar (primer plano, de uno en uno)
- [ ] Retirar el proyecto
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: etapas `a` y `rollback` del mismo script. Restricción dura: nada `knowledge-graphs-*`.

### T-78 — Documentar cola atascada, reglas de ejemplo y `doctor`

- **Descripción**: Documentar `kairos_jobs_oldest_pending_seconds`, `MEMORY_QUEUE_STUCK_SECONDS`, el servicio `memory-probe`, las reglas de ejemplo y el aviso de `kairos doctor`. Fuente: CA-32 (documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-76, T-77
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`, `client/README.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: los manuales describen la métrica, el umbral, el servicio y el aviso de `doctor` con nombres iguales al código

**Criterios de aceptación**
- [ ] Nombres y defaults iguales al código

**Subtareas**
- [ ] Actualizar los manuales
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: `docs/operations.md`.

### T-79 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece). Incluye también `cd client && npm test` en verde. Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-78
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `client/package.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [ ] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [ ] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [ ] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Cierra la fase: no se abre la revisión adversarial con la suite en rojo.

### T-80 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: el aviso de cola no debe producir falsos positivos con la cola vacía. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.87h (estimado) · real —
- **Supervisión**: est. 0.22h (≈25 % IA) · real —
- **Previsión IA**: 239 k in / 21 k out tok · ⚠️ verificar €
- **Dependencias**: T-79
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [ ] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [ ] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [ ] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [ ] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [ ] Lente B: mutantes en memoria sobre cada control nuevo
- [ ] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [ ] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 13 — Abstención: señal absoluta, parámetro y contratos (C-05)

**Estado**: borrador · **Hito**: B · **Estimado**: 33.6h (28.0h base, de ellas 14.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.680 € · **Tokens est.**: 1120 k

### T-81 — Diseño de la señal de abstención: similitud semántica y `lexical_match`

- **Descripción**: Decidir y documentar cómo se expone la mejor similitud semántica a la fusión y cómo se combina con `lexical_match` y el estado `degraded`. La decisión se registra en `Notas` y en `docs/architecture.md`. Fuente: CA-27, CA-29; M-01.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real —
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/retrieval.py`, `server/memory_platform/store_vectors.py`, `docs/architecture.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/architecture.md` describe la señal (mejor similitud coseno por modelo, ningún `lexical_match`, `degraded` sin señal) y por qué no se usa el RRF

**Criterios de aceptación**
- [ ] La decisión cubre capa semántica ausente o `degraded` (sin señal: no abstiene), `abstain` sin umbral (`abstention: "uncalibrated"`) y preguntas cercanas al tema de un recuerdo
- [ ] Queda escrito qué métricas mediría la puerta (abstención correcta y falsa)

**Subtareas**
- [ ] Leer la fusión y la capa vectorial
- [ ] Prototipar la señal sobre datos sembrados y anotar la medición
- [ ] Redactar la decisión
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `retrieval.py:172-190` (fusión RRF por rango, no mide relevancia absoluta), `store_vectors.py:101`, `:408` (similitud coseno) y `Hit.lexical_match`.

### T-82 — Implementación: `abstain`, `MEMORY_ABSTAIN_THRESHOLDS` y `MEMORY_ABSTAIN_DEFAULT`

- **Descripción**: Implementar la abstención como parámetro opcional `abstain` y `MEMORY_ABSTAIN_DEFAULT` (`off` por defecto), con umbral por modelo (`MEMORY_ABSTAIN_THRESHOLDS`). Abstiene solo si la mejor similitud queda por debajo del umbral y ningún resultado tiene `lexical_match`: responde `abstained: true` e `items: []`. Fuente: CA-27, CA-29; M-01; P-04.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-81
- **Tipo**: backend
- **Archivos**: `server/memory_platform/retrieval.py`, `server/memory_platform/models.py`, `server/memory_platform/config.py`, `server/memory_platform/store_vectors.py`, `server/memory_platform/app.py`, `server/memory_platform/tests/test_abstention.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_abstention|test_retrieval|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con `abstain` activo y similitud por debajo del umbral sin `lexical_match`: `items: []` y `abstained: true`
- [ ] Sin `abstain` y con `MEMORY_ABSTAIN_DEFAULT=off` la respuesta es idéntica a la actual (prueba de no regresión por comparación campo a campo)
- [ ] Sin umbral para el modelo: la búsqueda responde normal y añade `abstention: "uncalibrated"`; con la capa semántica `degraded` nunca abstiene
- [ ] Una pregunta con `lexical_match` nunca abstiene

**Subtareas**
- [ ] Escribir primero las pruebas (rojo)
- [ ] Exponer la similitud a la fusión
- [ ] Implementar el parámetro, las variables y el campo
- [ ] Probar no regresión
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `models.py:160` (`Search`), `:200` (`SearchResult`), `app.py:397` (`search`), `config.py:232-235`, `:292-295` (lectura de variables) y `retrieval.py:106` (`search`). Cambio visible para clientes: aditivo y opcional.

### T-83 — Contratos aditivos: `abstain`, `abstained` y `abstention`

- **Descripción**: Añadir el parámetro `abstain` y los campos `abstained`/`abstention` como opcionales en `memory-platform.openapi.json` y `kairos-mcp.json` (incluido `result_schemas.search` con `additionalProperties: false`), regenerar `mcp/contract` y declararlo en los CHANGELOG con una nota para la Iniciativa 7. Fuente: CA-29; M-01; R-09.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-82
- **Tipo**: backend
- **Archivos**: `scripts/export-contracts.py`, `docs/contracts/memory-platform.openapi.json`, `docs/contracts/kairos-mcp.json`, `mcp/contract/kairos-mcp.json`, `mcp/tests/tool_cases.py`, `server/memory_platform/tests/test_contract_additive.py`, `server/memory_platform/tests/test_mcp_contract_copy.py`, `CHANGELOG.md`, `CHANGELOG.es.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_contract_additive|test_mcp_contract_copy|test_tool_endpoint_parity|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `abstain`, `abstained` y `abstention` son opcionales en ambos contratos y en `result_schemas.search`; `test_contract_additive.py` pasa
- [ ] `mcp/contract/kairos-mcp.json` es idéntico al exportado (`test_mcp_contract_copy`) y las 34 herramientas conservan correspondencia con su endpoint
- [ ] Los CHANGELOG declaran el cambio con una nota para la Iniciativa 7 (R-09: un cliente estricto rechazaría `abstained` si se activa por defecto)

**Subtareas**
- [ ] Regenerar con `scripts/export-contracts.py`
- [ ] Comprobar el diff aditivo frente a `contracts_base`
- [ ] Redactar la nota para la Iniciativa 7
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `scripts/export-contracts.py`, `tests/contracts_base/`, `tests/test_contract_additive.py`, `tests/test_mcp_contract_copy.py` y `tests/test_tool_endpoint_parity.py`. Contrato MCP solo aditivo (CLAUDE.md).

### T-84 — Pruebas de abstención y de no regresión por clase

- **Descripción**: Cubrir la clase entera: cada combinación de modelo con/sin umbral, capa semántica sana/`degraded`, con/sin `lexical_match` y `abstain` explícito/por defecto, y que la respuesta sin `abstain` no cambia. Fuente: CA-27, CA-29.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-83
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_abstention.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_abstention|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Tabla de combinaciones probada de extremo a extremo (API) y a nivel de servicio
- [ ] Mutante comprobado: quitar la comprobación de `lexical_match`, de `degraded` o del umbral deja una prueba en rojo
- [ ] La suite de recuperación existente (`test_retrieval.py`, `test_chunk_search.py`) pasa sin cambios

**Subtareas**
- [ ] Tabla de combinaciones
- [ ] Escribir las pruebas
- [ ] Aplicar mutantes
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/test_retrieval.py` y `tests/test_chunk_search.py`.

### T-85 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-84
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `docs/contracts/kairos-mcp.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [ ] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [ ] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [ ] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Cierra la fase: no se abre la revisión adversarial con la suite en rojo.

### T-86 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Superficie visible para clientes (revisión a 1,0 ×): contrato solo aditivo, respuesta idéntica sin `abstain`, R-09. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 14h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.87h (estimado) · real —
- **Supervisión**: est. 0.47h (≈25 % IA) · real —
- **Previsión IA**: 515 k in / 45 k out tok · ⚠️ verificar €
- **Dependencias**: T-85
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [ ] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [ ] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [ ] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [ ] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [ ] Lente B: mutantes en memoria sobre cada control nuevo
- [ ] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [ ] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 14 — Calibración de la abstención y puerta `retrieval-eval` (C-05)

**Estado**: borrador · **Hito**: B · **Estimado**: 33.6h (28.0h base, de ellas 14.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.680 € · **Tokens est.**: 1120 k

### T-87 — Conjunto `dataset-v1-negatives` (≥ 20 preguntas sin respuesta) y validación

- **Descripción**: Crear `dataset-v1-negatives.jsonl` (≥ 20 preguntas ES/EN sin respuesta, incluidas cercanas al tema de un recuerdo existente), versionado aparte de `dataset-v1.jsonl`, que no cambia, y validarlo con `check_dataset.py`. Fuente: CA-26; M-01.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real —
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/retrieval_eval/dataset-v1-negatives.jsonl`, `server/memory_platform/tests/retrieval_eval/check_dataset.py`, `server/memory_platform/tests/retrieval_eval/README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "check_dataset|MEMORY_TEST_RESULT"` → la validación del conjunto ampliado pasa y `MEMORY_TEST_RESULT` sin fallos
  - `git diff --stat -- server/memory_platform/tests/retrieval_eval/dataset-v1.jsonl` → sin cambios

**Criterios de aceptación**
- [ ] Hay ≥ 20 preguntas con `expected: []`, en ES y EN, y al menos 8 cercanas al tema de un recuerdo existente
- [ ] `dataset-v1.jsonl` (72 preguntas) no cambia y `check_dataset.py` valida ambos ficheros
- [ ] La procedencia y criterios de redacción quedan en el README de la puerta

**Subtareas**
- [ ] Redactar las preguntas
- [ ] Extender `check_dataset.py`
- [ ] Documentar la procedencia
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/retrieval_eval/dataset-v1.jsonl` (formato, 0 `expected: []`), `check_dataset.py` y `README.md`.

### T-88 — Métricas de abstención, `thresholds.json` y prueba de rojo en la CI

- **Descripción**: Ampliar `retrieval-eval` con abstención correcta en negativas y abstención falsa en positivas, con umbrales en `thresholds.json` (metas: ≥ 70 % y ≤ 5 %), mientras recall@5 ≥ 0,80 y MRR ≥ 0,60 siguen cumpliéndose; el trabajo de CI las exige y un umbral absurdo lo deja en rojo. Fuente: CA-27, CA-28; M-01; P-05.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real —
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-87, T-82
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/retrieval_eval/run.py`, `server/memory_platform/tests/retrieval_eval/thresholds.json`, `server/memory_platform/tests/retrieval_eval/test_metrics.py`, `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target retrieval-eval --progress=plain . 2>&1 | grep -E "abstention|gate"` → métricas de abstención dentro de los umbrales y la puerta `passed`
  - `docker build -f server/memory_platform/Dockerfile --target retrieval-eval ...` con el umbral de abstención en 0,99 → termina en rojo (`passed: false`)
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] Con el umbral del proveedor simulado, la puerta responde `items: []` y `abstained: true` en al menos el porcentaje acordado de las negativas y la abstención falsa en positivas no supera el tope, con recall@5 ≥ 0,80 y MRR ≥ 0,60
- [ ] El trabajo `retrieval-eval` de la CI exige las métricas de abstención; un umbral absurdo lo deja en rojo en una ejecución de prueba, anotada en `Notas`
- [ ] Un umbral o subconjunto ausente falla la puerta (`threshold_missing`/`subset_missing`, patrón existente)

**Subtareas**
- [ ] Escribir primero las pruebas de métricas en `test_metrics.py` (rojo)
- [ ] Añadir las métricas a `run.py` y los umbrales
- [ ] Ejecutar la puerta en verde y con 0,99 en rojo
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/retrieval_eval/run.py:109-120` (`threshold_missing`/`subset_missing`), `thresholds.json`, `fake_embeddings.py:1-8` (embeddings simulados) y `ci.yml` (trabajo `retrieval-eval`).

### T-89 — Medición del umbral de `nomic-embed-text` con un Ollama efímero y aislado (P-05)

- **Descripción**: Medir el umbral real con un Ollama efímero (contenedor y volumen propios, puerto distinto, desechados al terminar; nunca el Ollama del host en 11434). Si la descarga del modelo falla, el umbral queda `uncalibrated` y se mide en la Iniciativa 5. Fuente: CA-27 (umbral real); P-05; R-07.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.33h (estimado) · real —
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 92 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-88
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/retrieval_eval/measure_abstention.py`, `server/memory_platform/tests/retrieval_eval/thresholds.json`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m memory_platform.tests.retrieval_eval.measure_abstention --ollama-container kairos-ops-ollama-f --port 18434` (desde `server/`) → informe con el umbral por modelo, o `uncalibrated` si falla la descarga; `docker ps -a --filter name=kairos-ops-ollama` y `docker volume ls --filter name=kairos-ops-ollama` → vacíos al terminar
  - `curl -s http://127.0.0.1:11434/api/version` no se ejecuta ni se referencia en el script (`grep -n 11434` → solo para rechazarlo)

**Criterios de aceptación**
- [ ] El Ollama efímero usa nombre de contenedor y volumen propios, puerto distinto de 11434 y se elimina al terminar, incluso si falla
- [ ] El resultado es el umbral de `nomic-embed-text` medido sobre el conjunto ampliado o `uncalibrated` con el motivo; en ambos casos queda anotado en `Notas` y en `docs/configuration.md`
- [ ] Si queda `uncalibrated`, `MEMORY_ABSTAIN_THRESHOLDS` no incluye `nomic-embed-text` y la búsqueda devuelve `abstention: "uncalibrated"`

**Subtareas**
- [ ] Anotar `docker ps`/`volume ls` y confirmar que 11434 no se usa
- [ ] Escribir el medidor con limpieza garantizada (`try/finally`)
- [ ] Ejecutarlo (primer plano) y anotar el umbral o el motivo del fallo
- [ ] Reflejar el valor en `config.py` y `docs/configuration.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Restricción dura: no el Ollama del host. Descarga ≈ 270 MB solo en el contenedor desechable. Tarea de P-05 decidida por el orquestador (delegada por el usuario). Patrón: `tests/ollama_proxy_probe.py` (sondas aisladas de Ollama).

### T-90 — Pruebas de la puerta de abstención

- **Descripción**: Pruebas unitarias de las métricas de abstención y de la prueba de rojo, para que la puerta no se pueda debilitar sin que falle una prueba. Fuente: CA-28.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-89
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/retrieval_eval/test_metrics.py`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_metrics|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] Mutantes comprobados: quitar la métrica de abstención de `run.py` o del umbral deja `test_metrics.py` o `test_ci_workflow.py` en rojo
- [ ] El recuento de `test_metrics` sube y `retrieval-eval` sigue fuera de la suite

**Subtareas**
- [ ] Escribir pruebas
- [ ] Aplicar mutantes
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/retrieval_eval/test_metrics.py` (14 pruebas) y `scripts/tests/test_ci_workflow.py:272-326` (mutantes de CI).

### T-91 — Documentar la abstención y avisar a la Iniciativa 7

- **Descripción**: Documentar la abstención (parámetro, variables, umbral por modelo, `uncalibrated`) y dejar la nota para la Iniciativa 7 sobre el cambio visible y la activación futura por defecto. Fuente: CA-29 (documentación); P-04.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-90
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `docs/manual.md`, `CHANGELOG.md`, `CHANGELOG.es.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista `MEMORY_ABSTAIN_THRESHOLDS` y `MEMORY_ABSTAIN_DEFAULT` con defaults iguales a `config.py`, y los CHANGELOG llevan la nota para la Iniciativa 7

**Criterios de aceptación**
- [ ] La nota dice que la abstención sigue apagada por defecto y que activarla cambia lo que ve `custom-agents`

**Subtareas**
- [ ] Actualizar manuales y CHANGELOG
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: CHANGELOG de la Iniciativa 2.

### T-92 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-91
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `docs/contracts/kairos-mcp.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] `MEMORY_TEST_RESULT` con 0 fallos, 0 errores, 0 omitidos y `tests` ≥ 764 (≥ el recuento del cierre anterior)
- [ ] `KAIROS_MIN_TESTS` en `.github/workflows/ci.yml` y `MIN_FLOOR` en `scripts/tests/test_ci_workflow.py` igualan el recuento observado, y la tabla de `docs/operations.md` lo repite
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas`

**Subtareas**
- [ ] Ejecutar la suite completa (primer plano, un solo Docker a la vez) y anotar el recuento
- [ ] Subir `KAIROS_MIN_TESTS` y `MIN_FLOOR` (nunca bajar) y la tabla de `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `.github/workflows/ci.yml:17-20` y `scripts/tests/test_ci_workflow.py:290` (`MIN_FLOOR = 764`). Cierra la fase: no se abre la revisión adversarial con la suite en rojo.

### T-93 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: umbral calibrado con embeddings simulados (R-07), abstención falsa en positivas y ausencia de uso del Ollama del host; revisión a 1,0 ×. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 14h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.87h (estimado) · real —
- **Supervisión**: est. 0.47h (≈25 % IA) · real —
- **Previsión IA**: 515 k in / 45 k out tok · ⚠️ verificar €
- **Dependencias**: T-92
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de esta fase sin hallazgos Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] Sin hallazgos Critical/Important abiertos al cerrar; los Minor aceptados quedan listados con motivo
- [ ] Cada control nuevo de la fase tiene una prueba que falla al quitarlo (mutante comprobado, no supuesto)
- [ ] La suite completa sigue en verde tras las correcciones y `scope-check.py` sale con 0
- [ ] `usage-meter` abierto y cerrado por intento; los JSON están en `Notas`

**Subtareas**
- [ ] Lente A: leer el diff contra la spec (CA de la fase), `Archivos` y las restricciones duras
- [ ] Lente B: mutantes en memoria sobre cada control nuevo
- [ ] Corregir la clase entera de cada hallazgo y repetir hasta cero abiertos
- [ ] Registrar intentos en `review.md` y medir cada uno con `usage-meter`

**Notas**: Los intentos de corrección no suman horas nuevas: el presupuesto de la fase es el de esta tarea (calibra `CALIBRATION.md`).

---

## Fase 15 — Cierre del hito B: desplegar y detectar

**Estado**: borrador · **Hito**: B · **Estimado**: 2.4h (2.0h base, de ellas 0.0h de revisión adversarial) · **Real**: — · **Coste est.**: 120 € · **Tokens est.**: 80 k

### T-94 — Comprobaciones de cierre del hito B

- **Descripción**: Comprobar migraciones aditivas, diff aditivo de contratos, ausencia de referencias a `knowledge-graphs-*` y 11434, alcance declarado, `retrieval-eval` y suite. Fuente: CA-38 (parte del hito B).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `docker build -f server/memory_platform/Dockerfile --target retrieval-eval . 2>&1 | grep -i "passed"` → `passed: true`

**Criterios de aceptación**
- [ ] Suite con 0 fallos y 0 omitidos, `retrieval-eval` en verde, contratos y migraciones aditivos
- [ ] Ninguna referencia nueva a `knowledge-graphs-*` o 11434 salvo para rechazarlos
- [ ] Revisión del hito: lectura del diff completo del hito B con hallazgos en `review.md`

**Subtareas**
- [ ] Ejecutar `scope-check.py`
- [ ] Buscar referencias prohibidas
- [ ] Ejecutar suite y puerta
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: tarea de comprobaciones del hito A.

### T-95 — Pull request del hito B (solo con OK del usuario)

- **Descripción**: Abrir el PR del hito B desde `feat/reliable-operations`. El PR solo se abre con el OK expreso del usuario; la tarea no se marca hecha hasta que el PR exista. Fuente: P-09 (un PR por hito).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-94
- **Tipo**: devops
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/tasks.md`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view --json number,state,headRefName` → PR abierto desde `feat/reliable-operations` (`state: OPEN`)

**Criterios de aceptación**
- [ ] Hay OK expreso del usuario anotado en `Notas`
- [ ] El PR enlaza el ledger y el criterio de cierre 3 con su evidencia

**Subtareas**
- [ ] Pedir el OK al usuario
- [ ] Abrir el PR
- [ ] Anotar el número en `Notas`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Atribución de commits y PR: la del recordatorio del sistema. No se hace merge.

---

## Fase 16 — Cierre de la iniciativa: ensayo, CHANGELOG y versión 0.4.1

**Estado**: borrador · **Hito**: B · **Estimado**: 4.8h (4.0h base, de ellas 0.0h de revisión adversarial) · **Real**: — · **Coste est.**: 240 € · **Tokens est.**: 160 k

### T-96 — Ensayo aislado de cierre (CA-37): restauración, caída de base y sonda con worker parado

- **Descripción**: Ejecutar en un único proyecto Compose aislado el ensayo completo: runbook de restauración (CA-07), parada y arranque de `memory-postgres` con trabajos en cola y sonda con `memory-worker` parado (CA-31). Deja la evidencia en el ledger. Fuente: CA-37, CA-07, CA-31; criterios de cierre 1, 2 y 3.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_rehearse_reliable_operations.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-z --embed-stub --stage all` → `restored_and_content_verified`, `worker_survived_db_restart` (contador de reinicios igual, cola vacía, 0 trabajos `failed`) y `probe_failed stage=index`
  - `docker ps --filter name=knowledge-graphs` y `docker volume ls --filter name=knowledge-graphs` → idénticos antes y después

**Criterios de aceptación**
- [ ] Al parar y arrancar `memory-postgres` con trabajos en cola, `memory-worker` no se reinicia por error propio, la cola se vacía y ningún trabajo queda `failed` por esa caída
- [ ] El mismo ensayo ejecuta CA-07 y CA-31 y deja la salida en `Notas`
- [ ] Proyecto aislado retirado; nada `knowledge-graphs-*` ni Ollama del host

**Subtareas**
- [ ] Anotar recursos de la instalación antes
- [ ] Ejecutar el ensayo completo (primer plano, de uno en uno)
- [ ] Retirar el proyecto y comparar
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: etapas `a`, `rollback` y `probe` del script de las fases 8, 10 y 12.

### T-97 — Versión 0.4.1 de servidor, MCP y cliente y CHANGELOG

- **Descripción**: Subir `server/VERSION`, `mcp/VERSION` y `client/package.json` a 0.4.1 y pasar las entradas «sin publicar» de los CHANGELOG a la sección 0.4.1 (la 0.5.0 sigue reservada para retirar el MCP interno). Fuente: CA-38; P-10.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-96
- **Tipo**: docs
- **Archivos**: `server/VERSION`, `mcp/VERSION`, `client/package.json`, `client/package-lock.json`, `server/memory_platform/tests/test_versions.py`, `CHANGELOG.md`, `CHANGELOG.es.md`, `server/memory_platform/app.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_versions|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos
  - `cd client && npm test` → 0 fallos

**Criterios de aceptación**
- [ ] Las tres versiones valen 0.4.1 y `test_versions` pasa (comprueba que los CHANGELOG nombran la versión)
- [ ] Ambos CHANGELOG tienen la sección 0.4.1 con las entradas de los dos hitos y la nota para la Iniciativa 7
- [ ] Nada se publica

**Subtareas**
- [ ] Subir las tres versiones
- [ ] Actualizar los CHANGELOG
- [ ] Ejecutar la suite y `npm test`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/test_versions.py` y el cierre de la Iniciativa 2 (versión 0.4.0).

### T-98 — Comprobaciones finales (CA-38), manuales y estado del ledger

- **Descripción**: Comprobar migraciones aditivas, diff aditivo de ambos contratos frente a `contracts_base`, ausencia de referencias a `knowledge-graphs-*` y 11434, suite con 0 fallos y 0 omitidos, `retrieval-eval` en verde y manuales actualizados; marcar el plan y el ledger como completados y actualizar el índice. Fuente: CA-38; todos los CA.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-97
- **Tipo**: docs
- **Archivos**: `docs/architecture.md`, `docs/operations.md`, `docs/configuration.md`, `docs/roadmap/README.md`, `docs/roadmap/2026-11-15-reliable-operations/spec.md`, `docs/roadmap/2026-11-15-reliable-operations/evaluation.md`, `docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md`, `docs/roadmap/2026-11-15-reliable-operations/tasks.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python3 "$SHAREDKIT/ledger-lint.py" docs/roadmap/2026-11-15-reliable-operations/tasks.md` → exit 0
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] `docs/architecture.md`, `docs/operations.md`, `docs/configuration.md` y los CHANGELOG reflejan lo implementado
- [ ] Todos los CA de la spec tienen evidencia en `Notas` de su tarea
- [ ] La spec pasa a `implementada` y el índice del roadmap refleja el cierre

**Subtareas**
- [ ] Repasar los 38 CA contra las evidencias
- [ ] Actualizar manuales, spec e índice
- [ ] Ejecutar las comprobaciones finales
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: cierre de la Iniciativa 2 (`docs/roadmap/README.md`, spec `implementada`).

---

## Historial archivado

- 2026-11-15 · «Revisión de dos lentes — intento 1: Fase 1 (T-01..T-05): 3 Important, 4 Minor (T-01, T-02, T-03, T-04, T-05)» → [execution-history.md](execution-history.md) · SHA-256 `b4eb7fffcb4d331e41818669864cdc3828c91bdf163f8913b0b1489c1e4ca774`
- 2026-11-16 · «Revisión de dos lentes — intento 2: Fase 2 tras fix1 (T-07, T-09, T-10, T-11, T-12)» → [execution-history.md](execution-history.md) · SHA-256 `f855addba463e74bed860503006620e87e4a6e30ebe4ab0e709ff975a232d115`
- 2026-11-16 · «Revisión de dos lentes — intento 1: Fase 4 (T-21..T-28) (T-21, T-22, T-23, T-24, T-25, T-26, T-27, T-28)» → [execution-history.md](execution-history.md) · SHA-256 `7f213e9959ade269b413081593ec5f19474f05f2ecabcc48ad5e4b2111380d2e`
- 2026-11-16 · «Revisión de dos lentes — intento 1: Fase 5 (T-30..T-33) (T-30, T-31, T-32, T-33)» → [execution-history.md](execution-history.md) · SHA-256 `71140bcb0171ab5a63e75d39bd2a425b2099715951736841104ad8d7ca9fa6c7`
- 2026-11-17 · «Revisión de dos lentes — intento 1: Fase 7 (T-44..T-48) (T-44, T-45, T-46, T-47, T-48)» → [execution-history.md](execution-history.md) · SHA-256 `fc5c46f1983e5eb56bc5fcc773e4fe46cba80cea9e6b9d6f58cbe4158cefbd03`

## Revisión de dos lentes — intento 1: Fase 6 (T-35..T-42) (T-35, T-36, T-37, T-38, T-39, T-40, T-41, T-42)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 2: Fase 6 tras fix1 (T-35, T-36, T-37, T-39)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 3: Fase 6 tras fix2 (T-35, T-36, T-37, T-39, T-40, T-42)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 2: Fase 7 tras fix1 (T-44, T-45, T-46, T-47, T-48)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 — notas de las fases 8 y 9 y revisiones de las fases 6 y 7»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 1: Fase 9 (T-54..T-59) (T-54, T-55, T-56, T-57, T-58, T-59)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (2) — revisiones de la fase 9, intentos 1 a 3»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 2: Fase 9 tras fix1 (T-54, T-55, T-56, T-59)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (2) — revisiones de la fase 9, intentos 1 a 3»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 3: Fase 9 tras fix2 (T-54, T-55, T-56, T-59)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (2) — revisiones de la fase 9, intentos 1 a 3»); resumen de la fase en `review.md`.

## Revisión de dos lentes — intento 4: Fase 9 tras fix3 — ciclo 2, abierto con OK del usuario: «Las preguntas toma la mejor decisión» (T-54, T-55, T-56)

Lentes: A+C en un solo revisor (re-evalúan lo corregido en fix3). Diff `ce3b035..e71b70d`. Veredicto: n.º 1-5 del intento 3 cerrados; la aserción nueva sale `FAILED (failures=1)` sobre el manual de `ce3b035` y 21 OK sobre el actual; la receta de Linux es segura tal como está escrita (un solo socket IPv4 en la pasarela de `docker0`, orden lo → subred → descarte, `ufw` con aceptar antes de denegar); deuda n.º 6-7 en las Notas de T-64. Sin Critical ni Important: **fase cerrada en el intento 4** (primer intento del ciclo 2), salvo T-56, que espera su criterio de T-64. Suite 1241, 0 fallos (tras fix2; fix3 solo cambia el manual y una aserción, verificados con las pruebas que leen los manuales).

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | La mitigación de fijar la regla a la IP del contenedor `ollama` no pide volver a aplicarla al recrearlo (la IP vieja puede pasar a `memory-backup`) | T-55 | corregido (orquestador, en el cierre) | Lentes A+C N1 (CWE-1327 residual); `operations.md:407` |

## Revisión de dos lentes — intento 1: Fase 10 (T-61 a T-65) (T-61, T-62, T-63, T-64, T-65)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (5) — revisión de la fase 10, intento 1»). Resumen: lentes A+B+C+D; 1 Important (etiquetado desde `:latest`) y 10 Minor; n.º 1-8 y 10 corregidos en fix1 (`1b46eb4`, `508f209`), n.º 9 descartado (rebatido), n.º 11 deuda → T-66.


## Revisión de dos lentes — intento 2: Fase 10 tras fix1 (T-61, T-62, T-63, T-64, T-65)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (7) — revisión de la fase 10, intento 2»). Resumen: lentes B y A+C; 2 Important (destino del retroceso tomado de lo que corría antes y no del último despliegue bueno) y 6 Minor (bloqueo con ventana, Windows, JSON no objeto, gramática de tags, veredicto del ensayo, `.broken` huérfano); todos corregidos en fix2 (`c0764e5`, `9585bf3`, `9582280`, `16e2b51`).


## Revisión de dos lentes — intento 3: Fase 10 tras fix2 (T-61, T-62, T-63, T-64, T-65)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (8) — revisión de la fase 10, intento 3»). Resumen: lentes B y A+C; 2 Important (`:latest` desfasado tras `already_at_previous`; despliegue interrumpido sin registro de etiquetas) y 7 Minor (bloqueo: ventana tras `is_current`, TOCTOU de `remove_foreign`, `O_NOFOLLOW`; validación de ids y `TAG_MARK`; aviso de despliegue interrumpido; CA-21 como enmienda). Ciclo 2 abierto por el orquestador con la delegación del usuario («Las preguntas toma la mejor decisión»); fix3 corrige todo.


## Revisión de dos lentes — intento 4: Fase 10 tras fix3 — ciclo 2, abierto con OK del usuario: «Las preguntas toma la mejor decisión» (T-61, T-62, T-63, T-64, T-65)

Archivada en `execution-history.md` (sección «Compactación 2026-11-17 (10) — revisión de la fase 10, intento 4»). Resumen: lentes B y A+C; 1 Important (instalación sin `images.good`: una interrupción o fallo temprano pierde la referencia a la versión buena) y 8 Minor (señales en los manejadores, `migrate` huérfano, mensajes y notas de `--break-lock`, `interrupted` en `engine`, escapes de terminal, enlace duro); fix4 corrige todo.


## Revisión de dos lentes — intento 5: Fase 10 tras fix4 (T-61, T-62, T-63, T-65)

Lentes: B; A+C (diff `af7df9b..64f3861`, fix4). 133 OK en el anfitrión (2 omitidas); legacy 2×300×8 sin problemas atribuibles a fix4; `reap` con docker colgado vuelve a los 120 s; OneDrive y montajes de Docker Desktop dan `nlink` 1. Intento 4: n.º 1-6, 8 y 9 ✓; n.º 7 parcial. Sin Critical ni Important: **fase cerrada en el intento 5** (segundo del ciclo 2). Minor, todos corregidos en el cierre (fix5):

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | Sin registro y con servicios sin contenedor, `good` parcial: `--rollback` informa éxito con esos servicios en la build fallida y la marca `good` | T-62, T-63 | corregido (fix5) | Lente B n.º 3 (`rb4/legacy5.py`) |
| 2 | Minor | Señal entre el fin de `settle`/`apply` y `disarm()`: escapa de `main` sin liberar | T-61 | corregido (fix5) | Lente B n.º 1 (`rb4/signals5.py`) |
| 3 | Minor | Señal antes del SIG_IGN de `ignoring_signals` cancela el `reap` sin aviso | T-61 | corregido (fix5) | Lente B n.º 2 |
| 4 | Minor | Manual: en `engine` ya se guardó `in_progress` | T-65 | corregido (fix5) | Lente A n.º A-1 |
| 5 | Minor | Ítem (19): «antes de cualquier fase» frente a «tras `engine`» | T-65 | corregido (fix5) | Lente A n.º A-2 |
| 6 | Minor | `status` del estado sin escapar en stderr y `warnings` | T-62, T-63 | corregido (fix5) | Lente C n.º C-1 (CWE-150) |
