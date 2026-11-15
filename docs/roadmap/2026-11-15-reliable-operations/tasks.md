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
| Fase 1 — Arnés de fallos y tests de límites (C-07) | 0 | 6 | 0% | 0 / 32.4h | 0 / 4.3h | 0 / 1.1h | 0 / 1080 k |
| Fase 2 — Worker resistente a la caída de base (C-02, B-03) | 0 | 7 | 0% | 0 / 27.0h | 0 / 3.6h | 0 / 0.9h | 0 / 900 k |
| Fase 3 — Cola: índices parciales y retención de tablas (C-02, B-06) | 0 | 7 | 0% | 0 / 27.0h | 0 / 3.6h | 0 / 0.9h | 0 / 900 k |
| Fase 4 — Pool y plazos de conexión (C-03, B-02 y B-07) | 0 | 9 | 0% | 0 / 48.0h | 0 / 6.4h | 0 / 1.6h | 0 / 1600 k |
| Fase 5 — Permisos por transacción (C-03, B-02) | 0 | 5 | 0% | 0 / 24.0h | 0 / 3.2h | 0 / 0.8h | 0 / 800 k |
| Fase 6 — Copias locales: integridad, cifrado, retención y verificación (C-01) | 0 | 9 | 0% | 0 / 43.2h | 0 / 5.8h | 0 / 1.4h | 0 / 1440 k |
| Fase 7 — Copia externa programada y runbook de restauración (C-01) | 0 | 6 | 0% | 0 / 28.8h | 0 / 3.8h | 0 / 1.0h | 0 / 960 k |
| Fase 8 — Cierre del hito A: no perder datos ni parar | 0 | 4 | 0% | 0 / 7.2h | 0 / 1.0h | 0 / 0.2h | 0 / 240 k |
| Fase 9 — Compose: límites, healthchecks, rotación y `extra_hosts` (C-04) | 0 | 7 | 0% | 0 / 19.8h | 0 / 2.6h | 0 / 0.7h | 0 / 660 k |
| Fase 10 — Despliegue: bloqueo, etiquetado y retroceso (C-04) | 0 | 7 | 0% | 0 / 34.2h | 0 / 4.6h | 0 / 1.1h | 0 / 1140 k |
| Fase 11 — Sonda de ida y vuelta (C-06) | 0 | 6 | 0% | 0 / 23.4h | 0 / 3.1h | 0 / 0.8h | 0 / 780 k |
| Fase 12 — Cola atascada, servicio de sonda y `kairos doctor` (C-06) | 0 | 7 | 0% | 0 / 23.4h | 0 / 3.1h | 0 / 0.8h | 0 / 780 k |
| Fase 13 — Abstención: señal absoluta, parámetro y contratos (C-05) | 0 | 6 | 0% | 0 / 33.6h | 0 / 4.5h | 0 / 1.1h | 0 / 1120 k |
| Fase 14 — Calibración de la abstención y puerta `retrieval-eval` (C-05) | 0 | 7 | 0% | 0 / 33.6h | 0 / 4.5h | 0 / 1.1h | 0 / 1120 k |
| Fase 15 — Cierre del hito B: desplegar y detectar | 0 | 2 | 0% | 0 / 2.4h | 0 / 0.3h | 0 / 0.1h | 0 / 80 k |
| Fase 16 — Cierre de la iniciativa: ensayo, CHANGELOG y versión 0.4.1 | 0 | 3 | 0% | 0 / 4.8h | 0 / 0.6h | 0 / 0.2h | 0 / 160 k |
| **TOTAL** | **0** | **98** | **0%** | **0 / 412.8h** | **0 / 55.0h** | **0 / 13.8h** | **0 / 13760 k** |

> **Imputación externa opcional.** El adaptador elegido recibe las mediciones disponibles y aplica su contrato de jornada, supervisión e idempotencia. No inventes tiempo real ni recalcules horas fuera de su dueño; sin integración los datos permanecen locales.

---

## Fase 1 — Arnés de fallos y tests de límites (C-07)

**Estado**: en-progreso · **Hito**: A · **Estimado**: 32.4h (27.0h base, de ellas 9.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.620 € · **Tokens est.**: 1080 k

### T-01 — Arnés `FaultProxy`: proxy TCP cortable delante del PostgreSQL efímero

- **Descripción**: Crear un proxy TCP en proceso que se interpone entre el código y el PostgreSQL efímero y permite cortar, restaurar y dejar «mudo» el destino por orden explícito (sin esperas). Es el oráculo de C-02 y C-03. Fuente: CA-34; B-15.
- **Changelog**: Interno: arnés de pruebas que corta, restaura o silencia la conexión con la base para probar caídas; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 4.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.60h (estimado) · real 0.05h (medido)
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

**Notas**: Patrón: `tests/run_postgres.py:30-31` (PostgreSQL efímero en `127.0.0.1:55432`, `MEMORY_TEST_DSN`) y `tests/llm_spy.py` / `tests/chain_services.py` (servidores en proceso con `.start()`/`.stop()`). Aprendizaje 2 de la retro: nada de `sleep` para esperar un estado. — CIERRE: usage-meter {inicio 15:18:35Z, fin 15:19:51Z, horas_ia 0.05, duracion 3m, medido}. Verificación (dev, módulo test_fault_proxy en imagen kairos-dev:i3p1): 7 tests ok, DEV_RESULT 7 0 0 0; suite completa en T-05. RED: test_fault_proxy falló con ModuleNotFoundError (fault_proxy no existía) · 2026-11-15

### T-02 — Tests de `body_too_large`, `/v1/users`, `/health/ready` y `work_budget_exceeded`

- **Descripción**: Añadir pruebas que fallan si se retira el control: 413 `body_too_large`, `/v1/users` (permitido, sin permiso, ajeno), `/health/ready` (listo y no listo) y 409 `work_budget_exceeded`. Fuente: CA-35; B-15.
- **Changelog**: Interno: pruebas que fallan si se quita el límite de cuerpo, el permiso de usuarios, la comprobación de disponibilidad o el presupuesto de trabajo; no cambia el comportamiento del producto.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real 0.25h (medido)
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

**Notas**: Patrón: `app.py:36` (`body_too_large`), `agent_store.py:186` (`work_budget_exceeded`), `tests/test_observability.py:216` (caso 503 de `/health/ready` ya existente: se reutiliza el estilo, no se duplica). La ruta `/v1/users` se localiza en `app.py`. — CIERRE: usage-meter {inicio 15:19:51Z, fin 15:30:54Z, horas_ia 0.25, duracion 15m, medido}. Verificación (dev, imagen kairos-dev:i3p1): test_api_limits 22 tests ok, DEV_RESULT 22 0 0 0; suite completa en T-05. RED/mutantes aplicados en copia temporal del paquete (producción intacta): M1 BodyLimit sin tope -> 3 FAIL (413 por Content-Length, por trozos y un byte sobre el límite); M2 list_users sin _global_admin -> 2 FAIL (administrador de proyecto y clave admin listan usuarios); M3 /health/ready sin 503 not_ready -> 2 FAIL + 1 ERROR; M4 umbrales de presupuesto subidos a 10**6/10**9 -> 1 FAIL + 1 ERROR. /v1/users: caso ajeno devuelve 403 o 404 según la regla de _require (404 si el proyecto no es suyo).

### T-03 — Tests de esquema por catálogo y comportamiento, no por texto SQL

- **Descripción**: Sustituir los tests que trocean `schema.sql` por marcador o comparan texto SQL por comprobaciones sobre el catálogo (`information_schema`, `pg_indexes`) o el comportamiento, sin bajar el recuento. Fuente: CA-36; B-15.
- **Changelog**: Interno: las pruebas de migración parten de un esquema histórico fijo y comprueban el catálogo en vez de trocear el texto de schema.sql, así añadir índices no las rompe.
- **Estado**: completado
- **Cerrada**: 2026-11-15
- **Tiempo humano**: est. 6h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.80h (estimado) · real 0.42h (medido)
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

**Notas**: Patrón: `tests/test_chunk_schema.py:13-21` (`SCHEMA`, «schema.sql exactly as the previous release left the database»), `tests/test_fts_migration.py:11`, `tests/test_pgvector_migration.py:12`, `tests/test_migrations_additive.py:12-19` (`MIGRATION_SOURCES`). El nuevo `schema.sql` (versión 12) llegará en la Fase 3: estos tests no deben romperse al añadir índices. — CIERRE: usage-meter {inicio 15:30:55Z, fin 15:42:01Z, horas_ia 0.42, duracion 25m, medido}. Verificación (dev, imagen kairos-dev:i3p1): test_chunk_schema + test_fts_migration + test_pgvector_migration + test_migrations_additive 32 tests ok, DEV_RESULT 32 0 0 0. Recuento: antes 7+7+10+6=30, ahora 7+7+10+8=32 (no baja; +2). DESVIACIÓN (Archivos ampliado): fichero nuevo tests/schema_history.py con el texto congelado de las versiones 5, 8 y 9 (historia inmutable; ya no se lee schema.sql para construir la versión anterior; el fixture se sigue comprobando por catálogo). Los asserts de versiones pasan de range(1,12) exacto a contiguo 1..N con N>=11 (no se rompen con la versión 12 de la Fase 3). Los tests de bloqueo por sección (trozo de schema.sql) pasan a medirse con pg_locks al final de la transacción de migrate (helper migration_locks): comprueban que la segunda migración no bloquea ni reconstruye los objetos de la versión (tabla de fragmentos e índices, índices de idioma); LÍMITE declarado: ya no se aísla el bloqueo de la sección sobre documents/memory_items (las versiones 2 y 3 ya los bloquean). Los tests de aditividad por texto de sección pasan a instantánea de catálogo antes/después (catalog_snapshot/additive_violations); el escaneo estático de DROP/DELETE sobre las fuentes de migración se conserva a propósito. Mutantes (copia temporal del paquete): schema.sql con DROP INDEX al final -> 5 FAIL (3 de catálogo, ca34 estático, catálogo repetido); con DELETE de la versión 8 -> 8 FAIL + 1 ERROR (incluye el escaneo estático y los de versiones contiguas).

### T-04 — Pruebas de concesión expirada y ayudante para caducarla

- **Descripción**: Dejar caracterizado el comportamiento actual de reclamo con concesión expirada (sin cambiarlo) y un ayudante `expire_lease` en el arnés, que usarán C-02 (trabajo venenoso, CA-12) y los tests de base caída. Fuente: CA-34 (concesión expirada y trabajo venenoso); B-15.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_job_leases.py`, `server/memory_platform/tests/fault_proxy.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_job_leases|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Hay pruebas de que un trabajo `running` con concesión expirada se reclama de nuevo y se cuenta un intento (comportamiento actual, `store_jobs.py:92`, `:105`)
- [ ] `expire_lease(store, job_id)` caduca la concesión sin esperas reales
- [ ] Las pruebas no cambian código de producción

**Subtareas**
- [ ] Escribir las pruebas de caracterización
- [ ] Añadir `expire_lease` al arnés
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/test_jobs.py` (reclamo y reintento) y `store_jobs.py:89-192`. La prueba de trabajo venenoso (CA-12) se escribe en rojo en la Fase 2.

### T-05 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real —
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 18 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-03, T-02, T-04
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

### T-06 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Superficie: el arnés no debe poder tocar bases fuera del PostgreSQL efímero. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 9h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.20h (estimado) · real —
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

## Fase 2 — Worker resistente a la caída de base (C-02, B-03)

**Estado**: borrador · **Hito**: A · **Estimado**: 27.0h (22.5h base, de ellas 7.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.350 € · **Tokens est.**: 900 k

### T-07 — Clase `StoreUnavailable` y clasificación de errores de base

- **Descripción**: Introducir `StoreUnavailable` para `psycopg.OperationalError`/`InterfaceError` (y, más adelante, agotamiento del pool) y un clasificador que distinga «la base no responde» de «el proveedor falló». Fuente: CA-10, CA-11; B-03.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/errors.py`, `server/memory_platform/store.py`, `server/memory_platform/tests/test_store_unavailable.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_unavailable|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `StoreUnavailable` y un `is_store_unavailable(exc)` cubren `OperationalError`, `InterfaceError` y cortes de conexión a mitad de consulta con el `FaultProxy`
- [ ] Un error de proveedor (`provider_error`) nunca se clasifica como base no disponible, y al revés (prueba de ambos caminos)
- [ ] El mensaje registrado nunca incluye el DSN ni la contraseña

**Subtareas**
- [ ] Escribir primero las pruebas con `FaultProxy` (rojo)
- [ ] Implementar clase y clasificador
- [ ] Probar la redacción del DSN
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `errors.py` (jerarquía de errores del servidor) y `store.py:24-30` (único punto de `psycopg.connect`). Clase entera: todas las rutas de error de base, no un caso (aprendizaje 1 de la retro).

### T-08 — Reclamo resiliente: espera exponencial con jitter y `MEMORY_WORKER_DB_BACKOFF_MAX`

- **Descripción**: Meter `claim_job` dentro del control de errores de `run_once`/`run` con espera exponencial con jitter y tope (`MEMORY_WORKER_DB_BACKOFF_MAX`, 60 s); registrar `store_unavailable` sin DSN y seguir vivo. El `Worker` expone el instante del último acceso correcto a la base (lo usa el latido en la Fase 9). Fuente: CA-10; B-03.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real —
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-07
- **Tipo**: backend
- **Archivos**: `server/memory_platform/worker.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_worker_db_down.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_worker_db_down|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con la base cortada, `Worker.run()` no termina tras N reclamos fallidos (prueba con `FaultProxy`, reloj y espera inyectados)
- [ ] Las esperas crecen con jitter y se detienen en `MEMORY_WORKER_DB_BACKOFF_MAX`; al `restore()` el worker procesa la cola
- [ ] Se registra `store_unavailable` sin DSN ni contraseña
- [ ] `Worker.last_store_ok` avanza solo con accesos correctos (R-01: una caída larga no parece sana)

**Subtareas**
- [ ] Escribir primero la prueba con la base cortada (rojo: `run()` termina)
- [ ] Mover `claim_job` dentro del control de errores (`worker.py:91`)
- [ ] Implementar espera, jitter y tope con reloj inyectado
- [ ] Añadir `MEMORY_WORKER_DB_BACKOFF_MAX` a `config.py`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `worker.py:78-184` (`run_once`, `run`; `claim_job` fuera del `try` en `:91`, `run()` en `:178-184`). Aprendizaje 2: relojes inyectados o `threading.Event`, sin esperas reales.

### T-09 — Un fallo de base al completar o fallar un trabajo no cambia su estado

- **Descripción**: Si la base cae durante `complete_job` o `fail_job`, el trabajo no pasa a `failed`, no recibe `provider_error` ni consume intento; vuelve a ser reclamable al expirar la concesión. Fuente: CA-09, CA-11; B-03.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-08
- **Tipo**: backend
- **Archivos**: `server/memory_platform/worker.py`, `server/memory_platform/tests/test_worker_db_down.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_worker_db_down|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con la base cortada durante `complete_job`, el trabajo no queda `failed` ni con `provider_error`, y tras `restore()` se completa en una reclamación posterior (prueba con `FaultProxy` y `expire_lease`)
- [ ] Los errores de proveedor reintentables conservan su política actual (`worker.py:148-160`) y los de base no incrementan `attempts` más allá del reclamo ya contado (prueba que compara ambos caminos)
- [ ] Si `fail_job` también falla por base caída, el worker sigue vivo

**Subtareas**
- [ ] Escribir primero la prueba de ambos caminos (rojo)
- [ ] Separar `except StoreUnavailable` del `except Exception` de `worker.py:165-168`
- [ ] Verificar con la base cortada en `complete_job` y en `fail_job`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `worker.py:145` (`complete_job`), `:148-160` (política de reintento del proveedor), `:165-168` (`except Exception` → `fail_job(..., 'provider_error')`).

### T-10 — Tope al reclamar: `attempts_exhausted` en el trabajo venenoso

- **Descripción**: Un trabajo `running` con concesión expirada y `attempts ≥ max_attempts` pasa a `failed` con `attempts_exhausted` en la misma transacción de reclamo, en lugar de reclamarse; `retry_job` lo reactiva. Fuente: CA-12; B-05.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-09
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_jobs.py`, `server/memory_platform/tests/test_job_leases.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_job_leases|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Un trabajo venenoso (concesión expirada, `attempts ≥ max_attempts`) queda `failed` con `attempts_exhausted` y deja de reclamarse (prueba escrita en rojo antes del cambio)
- [ ] `retry_job` (`store_jobs.py:68-78`) lo devuelve a `pending` y vuelve a procesarse
- [ ] Es visible en `kairos_jobs_failed`
- [ ] La semántica de reconciliación (`unknown`, `needs_reconciliation`, `store_jobs.py:104`) no cambia (pruebas existentes en verde)

**Subtareas**
- [ ] Escribir primero la prueba de trabajo venenoso (rojo)
- [ ] Aplicar el tope en `claim_job` (`store_jobs.py:92`, `:105`)
- [ ] Comprobar `retry_job` y la métrica
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store_jobs.py:89-192` (`claim_job`, `renew_lease`, `_current_job`, `complete_job`, `fail_job`); `observability.py:205-208` (`kairos_jobs_failed`).

### T-11 — Documentar el comportamiento del worker sin base

- **Descripción**: Documentar `MEMORY_WORKER_DB_BACKOFF_MAX`, el comportamiento sin base y `attempts_exhausted` en los manuales. Fuente: CA-10, CA-12 (documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-10
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista `MEMORY_WORKER_DB_BACKOFF_MAX` con su default y `docs/operations.md` explica `store_unavailable` y `attempts_exhausted` con `retry_job`

**Criterios de aceptación**
- [ ] Ambos manuales describen el comportamiento real (nombres y valores iguales a `config.py`)

**Subtareas**
- [ ] Actualizar `docs/configuration.md`
- [ ] Actualizar `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: `docs/operations.md` ya tiene una sección de cola y trabajos (`kairos_jobs_failed`).

### T-12 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-11
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

### T-13 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: el reclamo y su reconciliación son delicados; R-01 (esperas que esconden una caída). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
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

## Fase 3 — Cola: índices parciales y retención de tablas (C-02, B-06)

**Estado**: borrador · **Hito**: A · **Estimado**: 27.0h (22.5h base, de ellas 7.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.350 € · **Tokens est.**: 900 k

### T-14 — Migración aditiva de esquema 12: índices parciales de cola

- **Descripción**: Añadir la versión de esquema 12 con un índice parcial `(priority, available_at, created_at, id) WHERE state IN ('pending','unknown')` y otro parcial para `running` por `lease_until`, solo con `CREATE INDEX IF NOT EXISTS`. Fuente: CA-13; B-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: db
- **Archivos**: `server/memory_platform/schema.sql`, `server/memory_platform/tests/test_migrations_additive.py`, `server/memory_platform/tests/test_queue_indexes.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_queue_indexes|test_migrations_additive|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Una base migrada hasta la versión 11 llega a la 12 con los dos índices y sin tocar filas ni columnas
- [ ] `test_migrations_additive.py` pasa y no hay `DROP`, `DELETE` ni `ALTER ... DROP` en la migración
- [ ] Una base nueva y una migrada tienen el mismo catálogo de índices (prueba por catálogo)

**Subtareas**
- [ ] Escribir primero la prueba de catálogo (rojo)
- [ ] Añadir la versión 12 al final de `schema.sql`
- [ ] Comprobar migración desde la 11
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `schema.sql:7-19` (índice actual `(state, available_at)` en `:19`) y `:214-228` (bloque de la versión 11 como forma de registrar una versión nueva). Los tests por catálogo de la Fase 1 sostienen este cambio.

### T-15 — `EXPLAIN` de `claim_job` sobre 10.000 trabajos y, si hace falta, dos sondeos

- **Descripción**: Comprobar con `EXPLAIN (FORMAT JSON)` que `claim_job` usa un índice nuevo sobre una tabla con ≥ 10.000 trabajos terminales; si el `OR` sobre `running` caducado lo impide, dividir el reclamo en dos sondeos ordenados con la misma semántica. Fuente: CA-13; B-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-14
- **Tipo**: db
- **Archivos**: `server/memory_platform/store_jobs.py`, `server/memory_platform/tests/test_queue_indexes.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_queue_indexes|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] El plan de `claim_job` sobre ≥ 10.000 trabajos terminales usa un índice nuevo y no un recorrido secuencial (`EXPLAIN (FORMAT JSON)` en la prueba)
- [ ] Si se divide en dos sondeos, la semántica de prioridad, `available_at`, `created_at`, `id` y reconciliación es idéntica (prueba de equivalencia sobre una cola mixta)
- [ ] Las pruebas de reclamo existentes (`test_jobs.py`, `test_worker.py`) siguen en verde

**Subtareas**
- [ ] Sembrar 10.000 trabajos terminales y medir el plan actual
- [ ] Decidir un sondeo o dos y anotarlo en `Notas`
- [ ] Probar equivalencia de semántica
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store_jobs.py:92` (`ORDER BY priority, available_at, created_at, id` con `OR` sobre `running` caducado) y `:104` (reconciliación). Hipótesis de la spec: un índice parcial sirve; si no, dos sondeos.

### T-16 — `admin prune-tables` por lotes con `--dry-run` y ventanas por tabla

- **Descripción**: Añadir el subcomando `prune-tables` (por lotes, `--dry-run`) con ventanas configurables por tabla (P-03): `login_attempts` 30 d, `web_sessions` caducadas o revocadas 30 d, `audit_events` 365 d, `jobs` terminales `failed` sin recibo 90 d; `events` sin retención por defecto. Nunca en una migración. Fuente: CA-14; B-06; P-03.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-15
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_prune_tables.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_prune_tables|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `prune-tables --dry-run` informa de lo que borraría por tabla y no borra nada; sin `--dry-run` borra por lotes según las ventanas
- [ ] Variables `MEMORY_RETENTION_*` por tabla con los defaults de P-03; `events` solo se poda si se activa su ventana explícitamente
- [ ] Un lote fallido no deja la tabla a medias (cada lote es una transacción) y la operación es repetible
- [ ] `admin` usa conexión directa, sin el `statement_timeout` de servicio

**Subtareas**
- [ ] Escribir primero las pruebas con filas sembradas (antiguas y recientes)
- [ ] Implementar el subcomando y las ventanas
- [ ] Añadir las claves a `config.py`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:240-321` (registro de subcomandos, `backup`, `restore-check`) y `schema.sql:7-19` (tablas). P-03: `events` lo leen `event_status`, la actividad y `get_tool_uses` (`store_documents.py:252-329`): borrarlo cambia respuestas visibles; declarar a la Iniciativa 7 si se activa.

### T-17 — Invariantes de la retención: manifiesto, recibos y migraciones sin `DELETE`

- **Descripción**: Probar que podar no cambia lo que ven los clientes: `content_manifest()` de datos de memoria igual antes y después, ningún trabajo con recibo en `projection_receipts` se borra, ninguna migración contiene `DELETE`. Fuente: CA-14; R-04.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-16
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_prune_tables.py`, `server/memory_platform/tests/test_migrations_additive.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_prune_tables|test_migrations_additive|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `content_manifest()` (elementos, documentos, embeddings y recibos vigentes) es igual antes y después de `prune-tables`
- [ ] Un trabajo `failed` con recibo en `projection_receipts` no se borra aunque supere la ventana (la clave foránea `schema.sql:20` lo protege y la prueba lo demuestra)
- [ ] Una prueba recorre `MIGRATION_SOURCES` y falla si aparece `DELETE` (mutante comprobado)
- [ ] `events` intacta con los valores por defecto

**Subtareas**
- [ ] Sembrar datos con recibos y trabajos antiguos
- [ ] Comparar manifiesto antes/después
- [ ] Añadir el mutante `DELETE` a `test_migrations_additive.py`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `schema.sql:20` (`projection_receipts.job_id` referencia `jobs(id)`) y `scripts/deploy-memory.py:376` (uso de `content-manifest`).

### T-18 — Documentar índices, retención y ventanas

- **Descripción**: Documentar la retención (`prune-tables`, ventanas, `--dry-run`, por qué `events` no se poda por defecto) y la nota de cola en los manuales. Fuente: CA-14 (documentación); B-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-17
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista las `MEMORY_RETENTION_*` con sus defaults de P-03 y `docs/operations.md` explica `prune-tables --dry-run` y la excepción de `events`

**Criterios de aceptación**
- [ ] Valores y nombres iguales a `config.py`
- [ ] La nota de que `events` cambia respuestas visibles y se declara a la Iniciativa 7

**Subtareas**
- [ ] Actualizar `docs/configuration.md`
- [ ] Actualizar `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: secciones existentes de `docs/operations.md`.

### T-19 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-18
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

### T-20 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: R-04 (retención que cambia lo que ven los clientes). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
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

## Fase 4 — Pool y plazos de conexión (C-03, B-02 y B-07)

**Estado**: borrador · **Hito**: A · **Estimado**: 48.0h (40.0h base, de ellas 20.0h de revisión adversarial) · **Real**: — · **Coste est.**: 2.400 € · **Tokens est.**: 1600 k

### T-21 — Medición previa: consultas, conexiones y latencia por búsqueda

- **Descripción**: Medir antes del pool cuántas conexiones y consultas abre una búsqueda híbrida y su latencia, para comparar después. Fuente: CA-15, CA-18 (línea base); B-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 0.75h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.10h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 28 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/measure_connections.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "MEASURE_CONNECTIONS|MEMORY_TEST_RESULT"` → una línea `MEASURE_CONNECTIONS` con conexiones y consultas por búsqueda y `MEMORY_TEST_RESULT` sin fallos

**Criterios de aceptación**
- [ ] La medición (conexiones por búsqueda, consultas por búsqueda, latencia p50) queda anotada en `Notas`, sobre PostgreSQL efímero
- [ ] El script no es una prueba de la suite (no cambia el recuento)

**Subtareas**
- [ ] Escribir el medidor sobre `Store` y la búsqueda híbrida
- [ ] Anotar la cifra «antes» en `Notas`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store.py:24-30` (una conexión nueva por `transaction()`), `retrieval.py:87-148` (una transacción por capa) y `tests/measure_vector_candidates.py` (medidor existente fuera de la suite).

### T-22 — `psycopg_pool` en `Store.transaction()` con `MEMORY_POOL_*`

- **Descripción**: Tomar las conexiones de `Store.transaction()` de un `psycopg_pool.ConnectionPool` (versión fijada) con `MEMORY_POOL_MIN`/`MAX`/`TIMEOUT` (1 / 10 / 5 s a medir); los comandos de `admin` siguen con conexión directa y `store_surface.json` no cambia. Fuente: CA-15; B-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 6h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.80h (estimado) · real —
- **Supervisión**: est. 0.20h (≈25 % IA) · real —
- **Previsión IA**: 221 k in / 19 k out tok · ⚠️ verificar €
- **Dependencias**: T-21
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store.py`, `server/memory_platform/config.py`, `server/memory_platform/app.py`, `server/memory_platform/worker.py`, `server/memory_platform/requirements.txt`, `server/memory_platform/tests/test_store_pool.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_pool|test_store_surface|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `Store.transaction()` toma conexiones del pool (`psycopg_pool` fijado por versión en `requirements.txt`); tras calentar, una búsqueda híbrida no abre conexiones nuevas (el conjunto de `pg_backend_pid()` es estable)
- [ ] `store_surface.json` no cambia y `test_store_surface` pasa
- [ ] El pool se cierra al apagar la API y el worker; `admin` usa conexión directa
- [ ] El tamaño máximo del pool se razona frente a los hilos de `asyncio.to_thread` y queda en `Notas`

**Subtareas**
- [ ] Escribir primero la prueba del conjunto de `pg_backend_pid()` (rojo)
- [ ] Fijar `psycopg_pool` compatible con `psycopg 3.3.7` en `requirements.txt`
- [ ] Integrar el pool en `Store.transaction()` y su ciclo de vida
- [ ] Mantener `admin` con conexión directa
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store.py:24-30` (único `psycopg.connect`), `requirements.txt:5` (`psycopg 3.3.7`), `tests/test_store_surface.py` + `store_surface.json` (congelado). Hipótesis de la spec: `psycopg_pool` es compatible con `to_thread`; si no, detenerse y pedir decisión.

### T-23 — `connect_timeout` y `statement_timeout` como opciones de conexión de servicio

- **Descripción**: Fijar `connect_timeout` (5 s) y `statement_timeout` (15.000 ms en la API, 30.000 ms en el worker) como opciones de las conexiones de servicio; `migrate`, `backfill-chunks`, `backup` y `content-manifest` no heredan el plazo. Fuente: CA-16, CA-17; B-07; R-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-22
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store.py`, `server/memory_platform/config.py`, `server/memory_platform/admin.py`, `server/memory_platform/tests/test_store_timeouts.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_timeouts|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Una consulta de servicio con `pg_sleep` más larga que el plazo se cancela en el servidor y la conexión vuelve al pool utilizable
- [ ] Con un DSN hacia un puerto que acepta y no responde (`FaultProxy.mute()`), el fallo llega en ≤ `MEMORY_CONNECT_TIMEOUT` + 1 s
- [ ] `migrate`, `backfill-chunks` y `backup` se ejecutan con el plazo de la API activo en el entorno y no lo heredan (prueba)
- [ ] Los `set_config` locales existentes siguen restaurando su valor previo (`store_documents.py:27-35`)

**Subtareas**
- [ ] Escribir primero las pruebas de `pg_sleep` y servidor mudo (rojo)
- [ ] Añadir las opciones a las conexiones de servicio y excluir `admin`
- [ ] Comprobar `migrate` y `backfill-chunks` con el plazo activo en la API
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store_documents.py:21-35` y `store_vectors.py:351-356` (`statement_timeout` locales), `config.py:232` (`request_timeout`: el plazo de consulta queda por debajo). Aprendizaje 2: el servidor mudo es `FaultProxy.mute()`, sin esperas arbitrarias.

### T-24 — Errores 503 `store_timeout` y `store_busy` y su clasificación

- **Descripción**: Mapear `statement_timeout` agotado a 503 `store_timeout` y pool agotado (`MEMORY_POOL_TIMEOUT`) a 503 `store_busy` con `request_id`; el worker los clasifica como `StoreUnavailable`. Fuente: CA-16, CA-19; B-07.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-23
- **Tipo**: backend
- **Archivos**: `server/memory_platform/app.py`, `server/memory_platform/errors.py`, `server/memory_platform/worker.py`, `server/memory_platform/tests/test_store_timeouts.py`, `server/memory_platform/tests/test_store_pool.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_timeouts|test_store_pool|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] La API responde 503 `store_timeout` si PostgreSQL cancela por plazo, y la búsqueda sigue marcando la capa `unavailable` con `reason: timeout` como hoy
- [ ] Con el pool agotado, una petición espera como máximo `MEMORY_POOL_TIMEOUT` y recibe 503 `store_busy` con `request_id`; no se cuelga
- [ ] El worker trata ambos como `StoreUnavailable` (espera y reintenta, sin consumir intento)

**Subtareas**
- [ ] Escribir primero las pruebas de pool agotado y plazo (rojo)
- [ ] Añadir los dos códigos al manejador de errores
- [ ] Enlazar con el clasificador de la Fase 2
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `app.py` (manejador de errores y `request_id`), `errors.py` y `retrieval.py:113-115`, `:146-148` (`asyncio.timeout` sobre `to_thread`, que no cancela la consulta).

### T-25 — Pruebas de la clase entera con `FaultProxy`: plazo, pool y servidor mudo

- **Descripción**: Ejercitar con el arnés todas las rutas de datos nuevas (API y worker) con base lenta, muda o cortada, para cubrir la clase y no un caso. Fuente: CA-16, CA-17, CA-19; CA-34.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-24
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_store_faults.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_store_faults|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] La API y el worker sobreviven a base cortada, muda y lenta en las rutas de lectura, escritura y búsqueda, con la respuesta documentada en cada caso
- [ ] La conexión que sufrió el corte no vuelve al pool rota (siguiente petición correcta)
- [ ] Mutante comprobado: quitar `statement_timeout`, `connect_timeout` o el plazo del pool deja una prueba en rojo

**Subtareas**
- [ ] Tabla de rutas × fallo
- [ ] Escribir las pruebas
- [ ] Aplicar los mutantes en memoria
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/fault_proxy.py` (Fase 1) y `tests/test_api.py` (cliente de prueba de la API).

### T-26 — Medición posterior del pool y defaults de `MEMORY_POOL_*`

- **Descripción**: Repetir la medición con el pool y fijar los valores por defecto del pool y de los plazos con la cifra. Fuente: CA-15 (medición); B-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 0.75h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.10h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 28 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-25
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/measure_connections.py`, `server/memory_platform/config.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "MEASURE_CONNECTIONS|MEMORY_TEST_RESULT"` → conexiones por búsqueda = 0 tras calentar y `MEMORY_TEST_RESULT` sin fallos

**Criterios de aceptación**
- [ ] Cifras «antes» y «después» anotadas en `Notas` (conexiones, consultas, latencia)
- [ ] Defaults del pool justificados con la medición

**Subtareas**
- [ ] Medir
- [ ] Ajustar los defaults de `config.py` si la medición lo pide
- [ ] `usage-meter start/close` de la tarea

**Notas**: Comparar con la línea base de la tarea de medición previa.

### T-27 — Documentar pool, plazos y errores 503

- **Descripción**: Documentar `MEMORY_POOL_*`, `MEMORY_CONNECT_TIMEOUT`, `MEMORY_STATEMENT_TIMEOUT_MS`, los códigos `store_timeout`/`store_busy` y qué comandos de `admin` no heredan el plazo. Fuente: CA-15 a CA-19 (documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-26
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista las cinco variables con defaults iguales a `config.py` y `docs/operations.md` explica los dos 503

**Criterios de aceptación**
- [ ] Defaults y códigos iguales al código
- [ ] `docs/architecture.md` describe el pool

**Subtareas**
- [ ] Actualizar los tres manuales
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: `docs/configuration.md` (tabla de variables).

### T-28 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real —
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 18 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-27
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

### T-29 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Superficie expuesta a todas las peticiones: R-02 (plazo que corta trabajo legítimo) y pool compartido entre hilos; revisión a 1,0 ×. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
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

## Fase 5 — Permisos por transacción (C-03, B-02)

**Estado**: borrador · **Hito**: A · **Estimado**: 24.0h (20.0h base, de ellas 10.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.200 € · **Tokens est.**: 800 k

### T-30 — Caché de `_active` y de concesiones por proyecto válida hasta el `COMMIT`

- **Descripción**: Cachear la lectura de actor y clave y las concesiones por proyecto en el ámbito de la transacción, descartándola al `COMMIT`/`ROLLBACK`, para que una búsqueda sobre N proyectos lea actor y clave una sola vez. Fuente: CA-18; B-02; R-05.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_auth.py`, `server/memory_platform/store.py`, `server/memory_platform/tests/test_auth_cache.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|test_auth|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Una búsqueda sobre N proyectos ejecuta la lectura de actor y clave una sola vez por transacción (contador de consultas en la prueba)
- [ ] Una clave revocada deja de valer en la petición siguiente (la caché no sobrevive al `COMMIT`)
- [ ] La caché no se comparte entre peticiones que reutilizan la misma conexión del pool (prueba con dos actores seguidos)

**Subtareas**
- [ ] Escribir primero las pruebas de contador y revocación (rojo)
- [ ] Implementar la caché ligada al objeto de transacción
- [ ] Limpiar en `COMMIT`, `ROLLBACK` y devolución al pool
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `store_auth.py:36-53` (`_active`: actor y clave) y `:60-77` (`_require`: concesiones por proyecto), `store.py:24-30`. R-05: la revocación no puede relajarse.

### T-31 — Pruebas de revocación, aislamiento entre peticiones y recorrido de las 86 transacciones

- **Descripción**: Cubrir la clase entera: revocación entre transacciones, dos actores en la misma conexión, y que ninguna de las rutas que usan `transaction()` salta la comprobación de permisos. Fuente: CA-18; R-05.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-30
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_auth_cache.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Revocar una clave entre dos peticiones sobre la misma conexión devuelve 401/403 en la segunda (todas las rutas de lectura y escritura de `/v1` probadas con una tabla)
- [ ] Mutante comprobado: dejar la caché viva tras `COMMIT` deja la prueba de revocación en rojo
- [ ] La suite de permisos existente (`test_auth.py`, `test_privacy.py`) pasa sin cambios

**Subtareas**
- [ ] Tabla de rutas × revocación
- [ ] Escribir las pruebas
- [ ] Aplicar el mutante
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `tests/test_auth.py` y `tests/test_privacy.py`; 86 usos de `transaction()` (spec §Contexto 7).

### T-32 — Medición final de consultas por búsqueda y documentación

- **Descripción**: Medir de nuevo las consultas por búsqueda tras la caché y documentar el comportamiento de permisos por transacción. Fuente: CA-18 (medición y documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: docs
- **Archivos**: `server/memory_platform/tests/measure_connections.py`, `docs/architecture.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "MEASURE_CONNECTIONS|MEMORY_TEST_RESULT"` → menos consultas por búsqueda que la línea base de la Fase 4 y `MEMORY_TEST_RESULT` sin fallos

**Criterios de aceptación**
- [ ] Cifras anotadas en `Notas`
- [ ] `docs/architecture.md` explica que la caché muere con el `COMMIT`

**Subtareas**
- [ ] Medir
- [ ] Actualizar `docs/architecture.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Línea base: la tarea de medición previa de la Fase 4.

### T-33 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-32
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

### T-34 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado máximo: la revocación no puede relajarse (R-05); revisión a 1,0 ×. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
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

## Fase 6 — Copias locales: integridad, cifrado, retención y verificación (C-01)

**Estado**: borrador · **Hito**: A · **Estimado**: 43.2h (36.0h base, de ellas 12.0h de revisión adversarial) · **Real**: — · **Coste est.**: 2.160 € · **Tokens est.**: 1440 k

### T-35 — Manifiesto `<copia>.json` y `admin verify-backup`

- **Descripción**: `admin backup` escribe, junto a cada copia, un manifiesto con sha256 del fichero tal como queda en disco, bytes, versión de esquema, hora, `encrypted` y recuentos de `store_fingerprints`; `admin verify-backup` recalcula el sha256 y falla con `backup_checksum_mismatch`. Fuente: CA-01; O-01.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.47h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 129 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/tests/test_admin.py`, `server/memory_platform/tests/test_backup_manifest.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_manifest|test_admin|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `backup` escribe `<copia>` y `<copia>.json` con los campos del manifiesto y `chmod 600`
- [ ] `verify-backup` recalcula el sha256 y falla con `backup_checksum_mismatch` si se altera un byte (prueba)
- [ ] Una copia sin manifiesto o con manifiesto ilegible falla con un error propio, sin traza con rutas sensibles

**Subtareas**
- [ ] Escribir primero la prueba del byte alterado (rojo)
- [ ] Añadir el manifiesto a `backup`
- [ ] Implementar `verify-backup`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:286-294` (`pg_dump --format=custom`, `chmod 600`), `:23-47` (`store_fingerprints`, `pg_environment`) y `:295-313` (`restore-check`). Fixtures en `tests/test_admin.py`.

### T-36 — Cifrado `age` con destinatarios y `MEMORY_BACKUP_REQUIRE_ENCRYPTION`

- **Descripción**: Cifrar la copia con `age` y clave pública (`MEMORY_BACKUP_RECIPIENTS_FILE`); con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` y sin destinatarios falla sin dejar fichero. La imagen `operator` y la de pruebas incorporan `age` fijado por versión; la clave privada de prueba se genera en el test y nunca está en el contenedor del servidor. Fuente: CA-02, CA-08 (parte); S-06; P-01.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.73h (estimado) · real —
- **Supervisión**: est. 0.18h (≈25 % IA) · real —
- **Previsión IA**: 202 k in / 18 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/Dockerfile`, `server/memory_platform/tests/test_backup_encryption.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_encryption|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con una clave pública `age` de prueba, la copia no empieza por `PGDMP` ni contiene el texto de una fila sembrada, y solo se restaura tras descifrar con la clave privada del test
- [ ] Con `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` y sin destinatarios, `backup` falla nombrando `MEMORY_BACKUP_RECIPIENTS_FILE` y no deja fichero
- [ ] El manifiesto marca `encrypted: true` y su sha256 es el del fichero cifrado (se verifica sin descifrar)
- [ ] `age` queda fijado por versión (paquete de Debian bookworm o binario con sha256 verificado) en los targets `operator` y `test`; ninguna clave privada entra en el repositorio ni en una imagen

**Subtareas**
- [ ] Comprobar la disponibilidad de `age` en bookworm y anotar la versión en `Notas`
- [ ] Escribir primero las pruebas (rojo)
- [ ] Implementar el cifrado y la exigencia de destinatarios
- [ ] Añadir `age` a los targets `operator` y `test` del `Dockerfile`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `Dockerfile:16` (`FROM api AS operator`) y `:34-66` (target `test`, que debe contar con `age` para los tests). Hipótesis de la spec: `age` en bookworm; si no, binario oficial con sha256 verificado. R-03: la clave privada nunca está en el host.

### T-37 — `backup --prune --keep N` con ficheros señuelo

- **Descripción**: `backup --prune --keep N` conserva las N copias más recientes con manifiesto válido, nunca borra la última verificada ni ficheros sin el patrón propio, rechaza `N < 1` e informa de lo borrado. Default `MEMORY_BACKUP_KEEP=7`. Fuente: CA-03; O-01.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-36
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_backup_prune.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_prune|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con ficheros señuelo (sin el patrón propio, con manifiesto inválido), solo se borran copias propias más antiguas que las N más recientes válidas
- [ ] La última copia verificada nunca se borra y `N < 1` se rechaza con un error propio
- [ ] El informe lista lo borrado y lo conservado

**Subtareas**
- [ ] Escribir primero la prueba con señuelos (rojo)
- [ ] Implementar `--prune --keep`
- [ ] Añadir `MEMORY_BACKUP_KEEP`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:240-321` (registro de argumentos y salida de los subcomandos).

### T-38 — `--backup-timeout` en el despliegue (O-03)

- **Descripción**: `scripts/deploy-memory.py` llama a `content-manifest`, `backup` y `verify-backup` con `--backup-timeout` (por defecto 3.600 s) en lugar del plazo de 120 s. Fuente: CA-04; O-03.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `test_deploy.py` comprueba que `content-manifest`, `backup` y `verify-backup` reciben `--backup-timeout` (3.600 s por defecto) y que `--backup-timeout 7200` se propaga
- [ ] Las demás fases del despliegue conservan su plazo (`operator()` por defecto 120 s)

**Subtareas**
- [ ] Escribir primero la prueba con el doble de `subprocess` (rojo)
- [ ] Añadir `--backup-timeout` y pasarlo a las tres llamadas
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `deploy-memory.py:27` (`MIGRATE_TIMEOUT_SECONDS`), `:257-258` (`operator()` con `timeout=120`), `:376` y `:380` (llamadas), `tests/test_deploy.py` (dobles de `subprocess`). El script no se ejecuta contra la instalación real.

### T-39 — `--verify-backup`: restauración en PostgreSQL efímero antes de `migrate`

- **Descripción**: Opción de `deploy-memory.py` (activada por defecto en los ensayos) que restaura la copia previa en un contenedor PostgreSQL efímero del propio proyecto con base `memory_restore_<marca>`, compara `store_fingerprints`, aborta antes de `migrate` si difieren y elimina el contenedor; el informe registra resultado y duración. Fuente: CA-05; O-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-38, T-36
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/admin.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_isolation.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy|test_deploy_isolation|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Una prueba con dobles comprueba la secuencia: copia → contenedor efímero con nombre del proyecto → `restore-check` con `memory_restore_<marca>` → comparación → eliminación → `migrate`; una diferencia aborta antes de `migrate`
- [ ] El contenedor efímero se elimina también si falla la comparación
- [ ] Nunca escribe en la base del proyecto ni usa nombres `knowledge-graphs-*`; el informe registra resultado y duración

**Subtareas**
- [ ] Escribir primero las pruebas con dobles (rojo)
- [ ] Implementar la fase y su limpieza
- [ ] Reutilizar `restore-check` y sus salvaguardas
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:295-313` (`restore-check` solo en bases `memory_restore*` vacías), `deploy-memory.py:296-410` (fases) y `tests/test_deploy_isolation.py:43-99` (override con nombres propios).

### T-40 — Ensayo aislado de `--verify-backup`

- **Descripción**: Ejecutar un ensayo aislado real con `--verify-backup` y comprobar el contenedor efímero, el aborto ante una diferencia y la limpieza. Fuente: CA-05 (ensayo).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/deploy-memory.py --project-name kairos-ops-a --embed-stub --verify-backup` → termina en 0 y el informe registra `verify_backup` con resultado y duración; después `docker ps -a --filter name=kairos-ops-a` y `docker volume ls --filter name=kairos-ops-a` muestran solo recursos propios, que se eliminan al terminar
  - `docker ps --filter name=knowledge-graphs` y `docker volume ls --filter name=knowledge-graphs` → idénticos antes y después

**Criterios de aceptación**
- [ ] El ensayo usa el proyecto `kairos-ops-a`, nunca `knowledge-graphs`, ni el Ollama del host (`--embed-stub`)
- [ ] El contenedor `memory_restore_*` no queda vivo tras el ensayo
- [ ] Los recursos del ensayo se retiran con `docker compose -p kairos-ops-a down -v`

**Subtareas**
- [ ] Anotar `docker ps`/`volume ls` de la instalación antes
- [ ] Ejecutar el ensayo (primer plano, de uno en uno)
- [ ] Retirar el proyecto aislado y comparar
- [ ] `usage-meter start/close` de la tarea

**Notas**: Restricción dura: nada contra la base desplegada ni recursos `knowledge-graphs-*`. Patrón: ensayos de la Iniciativa 2 (`scripts/deploy-memory.py --project-name`).

### T-41 — Documentar copias, cifrado, retención y verificación

- **Descripción**: Documentar `backup`, `verify-backup`, `MEMORY_BACKUP_*`, `--backup-timeout`, `--verify-backup` y la custodia de la clave privada fuera del VPS. Fuente: CA-01 a CA-05 (documentación); R-03.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.27h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 74 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-40, T-37
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista `MEMORY_BACKUP_RECIPIENTS_FILE`, `MEMORY_BACKUP_REQUIRE_ENCRYPTION` y `MEMORY_BACKUP_KEEP` con defaults iguales a `config.py`, y `docs/operations.md` exige custodiar la clave privada fuera del VPS

**Criterios de aceptación**
- [ ] Nombres y defaults iguales al código
- [ ] La advertencia R-03 (clave privada perdida = copias perdidas) está explícita

**Subtareas**
- [ ] Actualizar `docs/configuration.md`
- [ ] Actualizar `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: sección de copias de `docs/operations.md:128-201`.

### T-42 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-41
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

### T-43 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: cifrado correcto (nada en claro), clave privada fuera del servidor (R-03) y borrado de copias (retención). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
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

## Fase 7 — Copia externa programada y runbook de restauración (C-01)

**Estado**: borrador · **Hito**: A · **Estimado**: 28.8h (24.0h base, de ellas 8.0h de revisión adversarial) · **Real**: — · **Coste est.**: 1.440 € · **Tokens est.**: 960 k

### T-44 — `admin backup-cycle` con destinos `dir:` y `rclone:`

- **Descripción**: Subcomando que encadena `pg_dump` → cifrado → manifiesto → `verify-backup` → subida al destino (`dir:<ruta>` o `rclone:<remoto>:<ruta>`) → verificación del sha256 en destino → retención local y remota. `rclone` fijado por versión en `operator`. Ejecución opcional de `prune-tables` al final del ciclo. Fuente: CA-06; O-01; P-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.67h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/config.py`, `server/memory_platform/Dockerfile`, `server/memory_platform/tests/test_backup_cycle.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_cycle|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con un destino `dir:` en un directorio temporal, `backup-cycle` sube copia cifrada y manifiesto, verifica el sha256 en destino y aplica `MEMORY_BACKUP_REMOTE_KEEP` (30)
- [ ] Con un remoto `rclone` de tipo `local` configurado por el test, hace lo mismo (el test se omite solo si `rclone` falta, y el recuento de la suite lo exige presente)
- [ ] Ningún servicio de nube real ni credencial en el repositorio; la configuración del remoto vive en el test

**Subtareas**
- [ ] Escribir primero las pruebas de `dir:` (rojo)
- [ ] Implementar el ciclo y los dos destinos
- [ ] Fijar `rclone` por versión en `operator`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `admin.py:286-313` (`backup`, `restore-check`) y las piezas de F6 (manifiesto, `age`, `--prune`). Hipótesis: `rclone` disponible en bookworm; si no, binario oficial con sha256 verificado. Nada se sube a un proveedor real.

### T-45 — Fallos del destino externo: `backup_offsite_failed`, métrica y reintento

- **Descripción**: Con el destino inaccesible, registrar `backup_offsite_failed` (tipo de destino, sin credenciales), poner la métrica a 0, reintentar en el ciclo siguiente y no borrar copias locales; una copia con sha256 distinto no sube ni borra nada. Fuente: CA-06; sha256 no coincide (manejo de errores).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-44
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/observability.py`, `server/memory_platform/tests/test_backup_cycle.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_cycle|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Con el destino inaccesible: `backup_offsite_failed`, métrica a 0, reintento en el ciclo siguiente y copias locales intactas (prueba)
- [ ] Con `backup_checksum_mismatch` en destino no se sube ni se borra nada
- [ ] Los registros no incluyen credenciales del destino

**Subtareas**
- [ ] Escribir primero las pruebas de fallo (rojo)
- [ ] Implementar el manejo y la métrica
- [ ] Comprobar la redacción de credenciales
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `observability.py:189-213` (métricas) y `:205-208` (gauges de cola).

### T-46 — Servicio Compose `memory-backup` (perfil `backup`) sin clave privada

- **Descripción**: Añadir al `docker-compose.yml` el servicio opcional `memory-backup` (perfil `backup`, imagen `operator`, sin puertos publicados) que ejecuta `admin backup-cycle` cada `MEMORY_BACKUP_INTERVAL`. Ningún servicio monta la clave privada. Aviso: la instalación desplegada lo recoge solo en su próximo `up`. Fuente: CA-06, CA-08; P-02.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-45
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_backup_service.py`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_backup_service|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `docker-compose.yml` define `memory-backup` con perfil `backup`, `MEMORY_BACKUP_INTERVAL` (24 h por defecto), `MEMORY_BACKUP_DESTINATION`, `MEMORY_BACKUP_REQUIRE_ENCRYPTION=1` por defecto y sin puertos publicados
- [ ] Una prueba sobre el YAML (y `docker compose -p kairos-ops-cfg config` en local, que no crea recursos) demuestra que ningún servicio monta una clave privada
- [ ] `ollama-proxy/default.conf.template` y los demás ficheros que monta la instalación desplegada no cambian

**Subtareas**
- [ ] Escribir primero la prueba sobre el YAML (rojo)
- [ ] Añadir el servicio con perfil y variables
- [ ] Documentar en `docs/configuration.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `docker-compose.yml:31-85` (`x-process`, rotación de logs) y `:154` (`memory-mcp`); `tests/test_deploy_isolation.py:43-48` (lectura del compose con `yaml.safe_load`). R-08: no se despliega nada.

### T-47 — Runbook de restauración desde la copia externa y ensayo automatizado

- **Descripción**: Escribir en `docs/operations.md` un runbook ejecutable (descargar del destino → verificar sha256 → descifrar con la clave privada fuera del servidor → `restore-check` en base vacía `memory_restore*` → comparar manifiesto) y un script de ensayo aislado que lo sigue con un destino simulado y resultado `restored_and_content_verified`. Fuente: CA-07; criterio de cierre 1 del plan director.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.47h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 129 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-46
- **Tipo**: devops
- **Archivos**: `docs/operations.md`, `scripts/rehearse-restore.py`, `scripts/tests/test_rehearse_restore.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_restore.py` → `OK`
  - `python scripts/rehearse-restore.py --project-name kairos-ops-b --embed-stub` → salida con `restored_and_content_verified`; el proyecto `kairos-ops-b` se elimina al terminar y `docker ps --filter name=knowledge-graphs` queda idéntico

**Criterios de aceptación**
- [ ] El ensayo descarga del destino simulado (directorio), verifica el sha256, descifra con una clave de prueba generada en el ensayo, ejecuta `restore-check` en un proyecto aislado vacío y compara el manifiesto
- [ ] Cada paso del runbook de `docs/operations.md` es un comando ejecutable que el ensayo ejecuta, y la clave privada de prueba nunca entra en un contenedor del servidor
- [ ] El resultado es `restored_and_content_verified` y el ensayo deja la evidencia en `Notas`

**Subtareas**
- [ ] Escribir el runbook primero y el test del script con dobles (rojo)
- [ ] Implementar el script de ensayo
- [ ] Ejecutar el ensayo real (primer plano, de uno en uno)
- [ ] Retirar el proyecto aislado y comprobar que nada de `knowledge-graphs-*` cambió
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `scripts/deploy-memory.py` (`--project-name`, `--embed-stub`), `admin.py:295-313` (`restore-check`) y `docs/operations.md:128-201`. Restricción dura: nada contra la base ni el Ollama del host.

### T-48 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-47
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

### T-49 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: copias externas (sha256 antes de borrar nada), ausencia de credenciales y de clave privada montada. Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
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

## Fase 8 — Cierre del hito A: no perder datos ni parar

**Estado**: borrador · **Hito**: A · **Estimado**: 7.2h (6.0h base, de ellas 0.0h de revisión adversarial) · **Real**: — · **Coste est.**: 360 € · **Tokens est.**: 240 k

### T-50 — Ensayo de cierre del hito A: restauración externa y caída de base con el worker en marcha

- **Descripción**: Crear `scripts/rehearse-reliable-operations.py` y ejecutar el ensayo aislado del hito A: runbook de restauración (criterio de cierre 1) y parada/arranque de `memory-postgres` con trabajos en cola (criterio de cierre 2). Fuente: CA-07, CA-37 (parte del hito A); criterios de cierre 1 y 2.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.33h (estimado) · real —
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 92 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_rehearse_reliable_operations.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_reliable_operations.py` → `OK`
  - `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-c --embed-stub --stage a` → `restored_and_content_verified` y `worker_survived_db_restart` con contador de reinicios igual y 0 trabajos `failed`

**Criterios de aceptación**
- [ ] Con trabajos en cola, parar y arrancar `memory-postgres` del ensayo: `memory-worker` no se reinicia por error propio (contador de reinicios igual), la cola se vacía y ningún trabajo queda `failed` por esa caída
- [ ] El ensayo es de un solo proyecto aislado `kairos-ops-c`, sin recursos `knowledge-graphs-*` ni Ollama del host
- [ ] La evidencia (salida, contadores) queda en `Notas`

**Subtareas**
- [ ] Escribir el script por etapas (`--stage a|b|all`) y su prueba con dobles
- [ ] Ejecutar la etapa A (primer plano, de uno en uno)
- [ ] Retirar el proyecto aislado
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `scripts/tests/test_rehearsal_three_components.py` (ensayo de la Iniciativa 2) y `scripts/deploy-memory.py` (`--project-name`, `--embed-stub`, `--roundtrip`). R-10: ensayos agrupados.

### T-51 — Comprobaciones de cierre del hito A

- **Descripción**: Comprobar migraciones aditivas, diff aditivo de contratos frente a `contracts_base`, ausencia de referencias a `knowledge-graphs-*` y al puerto 11434 (salvo para rechazarlos), alcance declarado y suite. Fuente: CA-38 (parte del hito A).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-50
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-15-reliable-operations` → exit 0
  - `grep -rn "knowledge-graphs-\|11434" scripts server/memory_platform/tests docker-compose.yml --include=*.py --include=*.yml` → solo apariciones que rechazan esos recursos (anotadas en `Notas`)
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] Suite con 0 fallos y 0 omitidos; `test_migrations_additive` y `test_contract_additive` pasan
- [ ] Ninguna referencia nueva a `knowledge-graphs-*` o 11434 salvo para rechazarlos
- [ ] Revisión del hito: lectura del diff completo del hito A por una persona/lente distinta de la de cada fase, con hallazgos en `review.md`

**Subtareas**
- [ ] Ejecutar `scope-check.py`
- [ ] Buscar referencias prohibidas
- [ ] Ejecutar la suite y los contratos
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `test_contract_additive.py` y `contracts_base` / `contracts_base_23ced03`.

### T-52 — Notas de cambio del hito A

- **Descripción**: Añadir al `CHANGELOG.md` y `CHANGELOG.es.md` (sección sin publicar) las novedades del hito A: copias verificadas y cifradas, worker resistente, pool y plazos, retención. Fuente: CA-38 (documentación del hito A).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-51
- **Tipo**: docs
- **Archivos**: `CHANGELOG.md`, `CHANGELOG.es.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: ambos CHANGELOG describen, en una frase por cambio visible, copias cifradas y verificadas, `store_unavailable`/`attempts_exhausted`, pool y plazos, `prune-tables` (ventanas) y la nota de que `events` no se poda por defecto

**Criterios de aceptación**
- [ ] Los dos idiomas dicen lo mismo
- [ ] La versión sigue siendo la del árbol (0.4.0) hasta la tarea de cierre

**Subtareas**
- [ ] Redactar las entradas
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: formato de `CHANGELOG.md` de la Iniciativa 2.

### T-53 — Pull request del hito A (solo con OK del usuario)

- **Descripción**: Abrir el PR del hito A desde `feat/reliable-operations` para que la Iniciativa 5 pueda empezar con A fusionado. El PR solo se abre con el OK expreso del usuario; la tarea no se marca hecha hasta que el PR exista. Fuente: P-09 (un PR por hito).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-52
- **Tipo**: devops
- **Archivos**: `docs/roadmap/2026-11-15-reliable-operations/tasks.md`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view --json number,state,headRefName` → PR abierto desde `feat/reliable-operations` (`state: OPEN`)

**Criterios de aceptación**
- [ ] Hay OK expreso del usuario anotado en `Notas`
- [ ] El PR enlaza el ledger y lista los criterios de cierre 1 y 2 con su evidencia
- [ ] La CI del PR está en verde o sus fallos explicados

**Subtareas**
- [ ] Pedir el OK al usuario
- [ ] Abrir el PR con el cuerpo y las evidencias
- [ ] Anotar el número en `Notas`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Atribución de commits y PR: la del recordatorio del sistema. No se hace merge.

---

## Fase 9 — Compose: límites, healthchecks, rotación y `extra_hosts` (C-04)

**Estado**: borrador · **Hito**: B · **Estimado**: 19.8h (16.5h base, de ellas 5.5h de revisión adversarial) · **Real**: — · **Coste est.**: 990 € · **Tokens est.**: 660 k

### T-54 — `mem_limit` y `cpus` configurables en todos los servicios

- **Descripción**: Declarar `mem_limit` y `cpus` en todos los servicios con variables `MEMORY_<SERVICIO>_MEM_LIMIT`/`_CPUS` y valores por defecto documentados para 32 GB locales y un VPS pequeño. Aviso: la instalación desplegada lo recoge solo en su próximo `up`. Fuente: CA-20; O-05; R-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.33h (estimado) · real —
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 92 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Todos los servicios de `docker-compose.yml` declaran `mem_limit` y `cpus` configurables por variable (prueba sobre el YAML y `docker compose -p kairos-ops-cfg config` en local)
- [ ] `docs/configuration.md` documenta los valores por defecto para 32 GB locales y para un VPS pequeño
- [ ] `memory-postgres` y `memory-worker` no quedan con un límite que los mate durante el relleno (valor justificado en `Notas`)

**Subtareas**
- [ ] Escribir primero la prueba sobre el YAML (rojo)
- [ ] Añadir límites y variables
- [ ] Documentar
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `docker-compose.yml:154` (`mem_limit` en `memory-mcp`) y `tests/test_deploy_isolation.py:43-48` (lectura del compose). R-08: no tocar `ollama-proxy/default.conf.template` (lo monta `docker-compose.yml:48`).

### T-55 — Rotación de logs en `ollama` y `memory-postgres` y `extra_hosts`

- **Descripción**: Hacer que `ollama` y `memory-postgres` hereden la rotación `json-file` (`max-size`, `max-file`) de `x-process` y añadir `extra_hosts: ["host.docker.internal:host-gateway"]` al servicio `ollama` (el VPS es Linux). Fuente: CA-22, CA-25; O-05, O-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Todos los servicios rotan logs con `json-file`, `max-size` y `max-file` (prueba sobre el YAML)
- [ ] `ollama` declara `extra_hosts: ["host.docker.internal:host-gateway"]` y `docs/operations.md` explica el caso Linux
- [ ] `ollama-proxy/default.conf.template` sin cambios (`git diff --stat` lo confirma)

**Subtareas**
- [ ] Escribir primero la prueba (rojo)
- [ ] Aplicar `x-process`/`logging` a los dos servicios
- [ ] Añadir `extra_hosts` y la nota de Linux
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `docker-compose.yml:36-38` (`x-process`), `:41-85` (servicios sin rotación), `:45` (`OLLAMA_UPSTREAM` con `host.docker.internal`).

### T-56 — Latido del worker y healthcheck de `memory-worker`

- **Descripción**: El bucle del worker escribe `/tmp/kairos-worker-heartbeat` en cada vuelta (solo si `last_store_ok` es reciente: R-01) y `memory-worker` declara un healthcheck por antigüedad del fichero; con el bucle parado, el contenedor pasa a `unhealthy` en ≤ `interval × retries`. Fuente: CA-21; O-05; R-01.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.40h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 110 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: backend
- **Archivos**: `server/memory_platform/worker.py`, `docker-compose.yml`, `server/memory_platform/tests/test_worker_heartbeat.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_worker_heartbeat|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Prueba unitaria con reloj inyectado: el latido avanza en cada vuelta sana y no avanza si la base lleva caída más que el umbral
- [ ] `memory-worker` declara healthcheck por antigüedad de `/tmp/kairos-worker-heartbeat` (fichero en el `tmpfs` existente) con `interval × retries` documentados
- [ ] El caso real de `unhealthy` con el bucle detenido se ejercita en el ensayo de la Fase 10

**Subtareas**
- [ ] Escribir primero la prueba del latido (rojo)
- [ ] Escribir el latido en el bucle (usa `last_store_ok` de la Fase 2)
- [ ] Añadir el healthcheck al compose
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `worker.py:178-184` (`run`), `docker-compose.yml:32-33` (`tmpfs` y sistema de ficheros de solo lectura) y `:170-194` (servicios sin healthcheck). Aprendizaje 2: reloj inyectado.

### T-57 — Healthcheck de `memory-web`

- **Descripción**: Añadir healthcheck a `memory-web` con `GET /health/live` del proxy nginx. Fuente: CA-21; O-05.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `server/memory_platform/tests/test_compose_limits.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `memory-web` declara healthcheck contra `/health/live` y la prueba sobre el YAML lo comprueba
- [ ] `web/nginx.conf` no cambia (la ruta ya existe en `:44`)

**Subtareas**
- [ ] Escribir primero la prueba (rojo)
- [ ] Añadir el healthcheck
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `web/nginx.conf:44` (`location = /health/live`) y `docker-compose.yml:170-194`.

### T-58 — Documentar límites, healthchecks, rotación y `extra_hosts`

- **Descripción**: Completar `docs/configuration.md` y `docs/operations.md` con límites por servicio, healthchecks y el caso Linux de `host.docker.internal`. Fuente: CA-20, CA-21, CA-22, CA-25 (documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 37 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-56, T-57, T-55
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/configuration.md` lista las variables `MEMORY_*_MEM_LIMIT`/`_CPUS` por servicio con valores por defecto

**Criterios de aceptación**
- [ ] Variables y valores iguales a `docker-compose.yml`

**Subtareas**
- [ ] Actualizar los dos manuales
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: tablas de `docs/configuration.md`.

### T-59 — Cierre de fase: suite completa y subida del mínimo

- **Descripción**: Ejecuta la suite completa del servidor, anota el recuento `MEMORY_TEST_RESULT` y sube `KAIROS_MIN_TESTS` y `MIN_FLOOR` al número observado (la suite solo crece).  Fuente: Puerta de fase; CA-38 (suite con 0 fallos y 0 omitidos).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-58
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

### T-60 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Revisión adversarial del diff de la fase con dos lentes: A (contrato, seguridad, regresiones, alcance declarado) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cuidado: R-06 (límites que matan servicios) y R-08 (ficheros que monta la instalación desplegada). Cada hallazgo se corrige para la clase entera y se anota con intento y evidencia en `review.md`; cada intento abre y cierra `usage-meter`. Fuente: Lección de la retro de la Iniciativa 2: la revisión es partida propia (0,5 × la implementación; 1,0 × en C-03 y C-05).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 5.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.73h (estimado) · real —
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

## Fase 10 — Despliegue: bloqueo, etiquetado y retroceso (C-04)

**Estado**: borrador · **Hito**: B · **Estimado**: 34.2h (28.5h base, de ellas 9.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.710 € · **Tokens est.**: 1140 k

### T-61 — Bloqueo exclusivo de despliegue y `--break-lock`

- **Descripción**: Fichero de bloqueo exclusivo en el directorio privado del proyecto con PID, host y hora; un segundo despliegue termina con `deployment_locked` sin ejecutar fases; un bloqueo con PID muerto se informa y solo se rompe con `--break-lock`. Fuente: CA-23; O-06.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.47h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 129 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_lock.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy_lock|test_deploy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Un segundo despliegue sobre el mismo proyecto termina con `deployment_locked` (PID y hora del dueño) sin ejecutar ninguna fase (doble de `subprocess` sin llamadas)
- [ ] Un bloqueo con PID muerto se informa y solo se rompe con `--break-lock`
- [ ] El bloqueo se libera también si una fase falla o el proceso se interrumpe

**Subtareas**
- [ ] Escribir primero las pruebas (rojo)
- [ ] Implementar el bloqueo con creación exclusiva
- [ ] Añadir `--break-lock`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `deploy-memory.py:296-410` (secuencia de fases) y el directorio privado del proyecto (`deployment-status.json`, `docs/operations.md:186`). El script no se ejecuta contra la instalación real.

### T-62 — Etiquetas locales `kairos-*:<versión>-<marca>` y registro en `deployment-status.json`

- **Descripción**: Etiquetar las imágenes locales antes de cada construcción (`kairos-*:<versión>-<marca>`), conservar las dos anteriores y registrar las etiquetas en `deployment-status.json`. Fuente: CA-24; O-06; P-08.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real —
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-61
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_rollback.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy_rollback|test_deploy|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] Antes de construir, las imágenes vigentes se etiquetan `kairos-*:<versión>-<marca>` y `deployment-status.json` registra las etiquetas anterior y actual
- [ ] Se conservan las dos anteriores y las más antiguas se retiran (prueba con dobles)
- [ ] Los nombres de imagen del despliegue aislado no coinciden con los de la instalación

**Subtareas**
- [ ] Escribir primero las pruebas con dobles (rojo)
- [ ] Implementar el etiquetado y el registro
- [ ] Retirada de etiquetas antiguas
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `deploy-memory.py:236-258` y `:296-410` (construcción y estado) y `docker-compose.yml:69-198` (imágenes `:latest`).

### T-63 — `--rollback` sin migrar

- **Descripción**: `--rollback` vuelve a las etiquetas registradas sin migrar; sin etiquetas anteriores falla con `no_previous_images` sin tocar servicios. Se apoya en que las migraciones son aditivas. Fuente: CA-24; O-06; P-08.
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.60h (estimado) · real —
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 166 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-62
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy_rollback.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy_rollback|MEMORY_TEST_RESULT"` → pruebas nombradas en `ok` y `MEMORY_TEST_RESULT` con 0 fallos, errores y omitidos

**Criterios de aceptación**
- [ ] `--rollback` recompone los servicios con las etiquetas anteriores del registro y no ejecuta `migrate` (prueba con dobles)
- [ ] Sin etiquetas anteriores falla con `no_previous_images` y no cambia servicios
- [ ] `docs/operations.md` explica el retroceso y su límite (imágenes, no datos)

**Subtareas**
- [ ] Escribir primero las pruebas (rojo)
- [ ] Implementar `--rollback`
- [ ] Documentar
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: `docs/operations.md:186`, `:201` (el código anterior funciona sobre la base migrada) y la tarea de etiquetado.

### T-64 — Ensayo aislado de retroceso y de latido `unhealthy`

- **Descripción**: Ejecutar un ensayo aislado con dos despliegues etiquetados y `--rollback`, y comprobar que con el bucle del worker detenido el contenedor pasa a `unhealthy`. Fuente: CA-24, CA-21 (caso del ensayo).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 4h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.53h (estimado) · real —
- **Supervisión**: est. 0.13h (≈25 % IA) · real —
- **Previsión IA**: 147 k in / 13 k out tok · ⚠️ verificar €
- **Dependencias**: T-63, T-56
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_rehearse_reliable_operations.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/rehearse-reliable-operations.py --project-name kairos-ops-d --embed-stub --stage rollback` → `rollback_ok` con `content-manifest` igual, una búsqueda correcta y `worker_unhealthy` en ≤ `interval × retries`
  - `docker ps --filter name=knowledge-graphs` y `docker volume ls --filter name=knowledge-graphs` → idénticos antes y después

**Criterios de aceptación**
- [ ] Los servicios vuelven a las etiquetas anteriores sin migrar, `content-manifest` es igual y una búsqueda funciona
- [ ] Con el bucle detenido, `memory-worker` pasa a `unhealthy` en ≤ `interval × retries`
- [ ] Evidencia anotada en `Notas`; proyecto aislado retirado al terminar

**Subtareas**
- [ ] Añadir la etapa `rollback` al script
- [ ] Ejecutar el ensayo (primer plano, de uno en uno)
- [ ] Retirar el proyecto
- [ ] `usage-meter start/close` de la tarea

**Notas**: Patrón: la etapa `a` creada en la Fase 8. Restricción dura: nada `knowledge-graphs-*`, ni Ollama del host.

### T-65 — Documentar bloqueo y retroceso

- **Descripción**: Documentar `deployment_locked`, `--break-lock`, las etiquetas locales y `--rollback`. Fuente: CA-23, CA-24 (documentación).
- **Changelog**:
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.20h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 55 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-64
- **Tipo**: docs
- **Archivos**: `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `docs/operations.md` describe `deployment_locked`, `--break-lock`, las etiquetas `kairos-*:<versión>-<marca>`, `--rollback` y `no_previous_images`

**Criterios de aceptación**
- [ ] Nombres y códigos iguales al script

**Subtareas**
- [ ] Actualizar `docs/operations.md`
- [ ] `usage-meter start/close` de la tarea

**Notas**: Estilo: secciones de despliegue de `docs/operations.md:128-201`.

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
