---
generacion:
  inicio: 2026-11-12T09:56:22Z
  fin: 2026-11-12T10:05:54Z
  fuente: medido
  fuente_id: src-8ffaaac4e3b9a11805b5148dbea387f65be01b42fba05cbf3ca54c4b799a95c8
  ventana_id: win-e6c46e835be446ba8e05994d4957863b
  revision_medicion: 1
  medicion_persistida: true
  tokens_reales: { entrada: 24, salida: 89388, cache_creacion: 112633, cache_lectura: 1378653 }
  eur: null
  horas_ia: 0.67
  duracion: 40m
  ratio_usado: 300000
  # ventana compartida con improvement-plan.md
verificacion: obligatoria   # cada T-XX lleva `- **Verificación**:`; lo exige ledger-lint (exit 1 si falta)
---

# Checklist de Tareas — Separación en tres componentes (Iniciativa 2 de Kairos)

| | |
|---|---|
| **Estado** | en-progreso |
| **Fecha** | 2026-11-12 |
| **Plan** | [`improvement-plan.md`](./improvement-plan.md) |
| **Diseño** | n/a |

> **⚠️ Ledger canónico de progreso.** Este fichero es la **fuente única de verdad** del avance del plan. **Cualquier** implementador —el agente `implementer`, el chat principal, o un orquestador SDD externo— **debe** marcar aquí cada tarea (checkbox + estado) al completarla y actualizar el resumen. Los ledgers propios de otras herramientas son **espejo**, no fuente.

> **Cifras.** Por tarea, las horas humanas, IA y supervisión son **base** (sin margen). Las filas de fase y el resumen llevan el **+20 %** de contingencia ya aplicado. Cada tarea abre y cierra `usage-meter` y anota su JSON en `Notas`. La comprobación de tests es siempre `docker build --target test -f memory_platform/Dockerfile -t kairos-test:<tag> .` (imprime `MEMORY_TEST_RESULT`; tras la Fase 7 cambia la ruta del Dockerfile) y `npm test` en `packages/kairos-cli` (luego `client/`). El implementer no escribe en `docs/roadmap/**/testing/` (reservado a `qa`): las evidencias van al ledger o junto a los tests.

> **Dependencia externa (no es tarea):** la Fase 7 (C-06) exige el PR #2 (`feat/retrieval-quality`) fusionado en `main` (P-09). **Restricciones:** nada contra la base desplegada ni contenedores, volúmenes o redes `knowledge-graphs-*`; migraciones solo aditivas; el contrato MCP solo crece; `store_surface.json` congelado; nada se publica; la CI no usa más secretos que `GITHUB_TOKEN`; EOL conservado (`.gitattributes` es `* -text`).

---

## Resumen de progreso

| Fase | Completadas | Total | Progreso | H. humanas (real/est) | H. IA ejec. (real/est) | Supervisión (real/est) | Tokens (real/est) |
|------|------------|-------|----------|-----------------------|------------------------|------------------------|-------------------|
| Fase 1 — Integración continua (C-01) | 8 | 8 | 100% | 0 / 18.0h | 0 / 2.3h | 0 / 0.6h | 0 / 578 k |
| Fase 2 — Servidor sin modelo de lenguaje (C-04) | 9 | 9 | 100% | 0 / 37.8h | 0 / 5.0h | 0 / 1.2h | 0 / 1245 k |
| Fase 3 — Paridad REST /v1 (C-02) | 10 | 10 | 100% | 0 / 36.0h | 0 / 5.1h | 0 / 1.3h | 0 / 1282 k |
| Fase 4 — Esquema de observación (C-05) | 8 | 8 | 100% | 0 / 37.8h | 0 / 4.8h | 0 / 1.2h | 0 / 1193 k |
| Fase 5 — kairos-mcp (C-03) | 15 | 15 | 100% | 0 / 68.4h | 0 / 10.1h | 0 / 2.5h | 0 / 2532 k |
| Fase 6 — Compatibilidad (C-07) | 6 | 6 | 100% | 0 / 23.4h | 0 / 3.0h | 0 / 0.8h | 0 / 757 k |
| Fase 7 — Estructura del repositorio (C-06) | 12 | 12 | 100% | 0 / 46.8h | 0 / 6.5h | 0 / 1.6h | 0 / 1614 k |
| Fase 8 — Integración final y revisión | 0 | 6 | 0% | 0 / 12.0h | 0 / 1.8h | 0 / 0.4h | 0 / 440 k |
| **TOTAL** | **68** | **74** | **91.9%** | **0 / 280.2h** | **0 / 38.6h** | **0 / 9.6h** | **0 / 9641 k** |

> **Imputación externa opcional.** El adaptador elegido recibe las mediciones disponibles y aplica su contrato de jornada, supervisión e idempotencia. No inventes tiempo real ni recalcules horas fuera de su dueño; sin integración los datos permanecen locales.

---

## Fase 1 — Integración continua (C-01)

**Estado**: completado · **Estimado**: 18.0h (15.0h base) · **Real**: — · **Coste est.**: 900 € · **Tokens est.**: 578 k

### T-01 — Workflow `ci.yml` con el trabajo `server` y línea base de la suite

- **Descripción**: Crear `.github/workflows/ci.yml` con disparador `pull_request` (y `workflow_dispatch`) y el trabajo `server`, que ejecuta `docker build --target test -f memory_platform/Dockerfile` en `ubuntu-latest` con caché de capas. Registra la línea base de la suite (nº de tests, 0 fallos, 0 omitidos) en `Notas`. Fuente: CA-01, B-04, O-04; P-01.
- **Changelog**: Cada pull request y cada rama que se sube ejecutan en GitHub la suite completa del servidor en un contenedor aislado, y un fallo o una suite omitida deja la comprobación en rojo.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real 0.17h (medido, bloque T-01..T-04) + 0.13h (medido, corrección fix1 T-01..T-05, solo la cifra) + 0.26h (medido, corrección fix2 T-01/T-04, ventana compartida con T-04-fix2, no sumar)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 85 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna (P-01 decidida: Actions activas, solo Linux)
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] Existe `.github/workflows/ci.yml` con el trabajo `server` y sin disparador `push`
- [x] `scripts/tests/test_ci_workflow.py` comprueba la estructura del workflow (trabajos, `runs-on`, comando del target `test`) sin dependencias externas
- [x] La línea base de la suite (`tests`, `failures`, `errors`, `skipped`) queda anotada en `Notas` de esta tarea: es el número que las demás tareas comparan
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Escribir primero `test_ci_workflow.py` (rojo: el workflow no existe)
- [x] Crear el workflow con el trabajo `server`
- [x] Ejecutar la suite local y anotar la línea base
- [x] `usage-meter start/close` de la tarea

**Notas**: Procedencia: spec CA-01, evaluación C-01. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `a05114d14f8e`.

### T-02 — Trabajos `retrieval-eval`, `client` y `web` del workflow

- **Descripción**: Añadir al workflow tres trabajos: `retrieval-eval` (target `retrieval-eval`, proveedor simulado, umbrales recall@5 ≥ 0,80 y MRR ≥ 0,60), `client` (`npm test` y `npm run release:check` en `packages/kairos-cli`) y `web` (`typecheck`, `test`, `build` en `web/` más el target `test` de `Dockerfile.web`). Fuente: CA-01; R-08 (puesta en verde en Linux).
- **Changelog**: La CI comprueba además la puerta de calidad de recuperación (recall@5 y MRR), las pruebas y la comprobación de publicación del cliente, y el typecheck, las pruebas y el build del portal.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real 0h (incluido en T-01)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 85 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK` con los 4 trabajos (`server`, `retrieval-eval`, `client`, `web`)
  - `docker build --target retrieval-eval -f memory_platform/Dockerfile -t kairos-eval:t02 .` → termina con exit 0 (umbrales cumplidos)

**Criterios de aceptación**
- [x] El workflow declara los trabajos `retrieval-eval`, `client` y `web`, cada uno con su comando exacto, y el test estructural los comprueba
- [x] `retrieval-eval` usa el proveedor simulado y no contacta con ningún servicio externo salvo los espejos de `apt-get` del target
- [x] Cada trabajo tiene `timeout-minutes` explícito
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 lleva solo la cifra medida de 0,13 h, sin JSON

**Subtareas**
- [x] Ampliar `test_ci_workflow.py` (rojo) con los tres trabajos
- [x] Añadir los trabajos al workflow
- [x] Anotar los tiempos locales de cada comando como referencia
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-01. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `4a3fa75c2bbd`.

### T-03 — Trabajo `contracts` (diff aditivo de ambos contratos)

- **Descripción**: Añadir el trabajo `contracts`: ejecuta `test_contract_additive` en la imagen de test y comprueba que `docs/contracts/*.json` coinciden con lo que exporta `scripts/export-contracts.py` (sin diff). Fuente: CA-01, CA-07, CA-29.
- **Changelog**: La CI falla si los contratos MCP y REST de Kairos pierden o cambian algo respecto a la base de la iniciativa, o si los ficheros versionados no coinciden con los exportados.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.12h (estimado) · real 0h (incluido en T-01)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 34 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-01
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK` con el trabajo `contracts`

**Criterios de aceptación**
- [x] El trabajo `contracts` falla si el contrato exportado difiere del versionado o si el diff contra la línea base no es aditivo
- [x] No necesita red ni servicios desplegados
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 lleva solo la cifra medida de 0,13 h, sin JSON

**Subtareas**
- [x] Ampliar el test estructural (rojo)
- [x] Añadir el trabajo
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-01/CA-07. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c2b350e8430b`.

### T-04 — Puerta de higiene del workflow: sin secretos, sin publicar, sin servicios desplegados

- **Descripción**: Fijar la comprobación de CA-02 como test: el workflow no referencia más secreto que `GITHUB_TOKEN`, no contiene `docker push`, `npm publish` ni `push: true`, y no menciona recursos `knowledge-graphs-*`. Fuente: CA-02, CA-30; restricción «la CI no usa más secretos que `GITHUB_TOKEN`».
- **Changelog**: La CI rechaza mecánicamente cualquier secreto distinto de GITHUB_TOKEN, cualquier publicación de imágenes o paquetes y cualquier referencia a los recursos de la instalación desplegada.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.06h (estimado) · real 0h (incluido en T-01)
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 17 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-02
- **Tipo**: test
- **Archivos**: `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `grep -nEi "secrets\.|docker push|npm publish|push: true|knowledge-graphs-" .github/workflows/ci.yml` → solo líneas con `GITHUB_TOKEN` o ninguna

**Criterios de aceptación**
- [x] El test falla si se introduce `secrets.X` distinto de `GITHUB_TOKEN`, `docker push`, `npm publish` o `knowledge-graphs-`
- [x] Con el workflow actual el test pasa
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 lleva solo la cifra medida de 0,13 h, sin JSON

**Subtareas**
- [x] Escribir el test con un caso positivo y tres negativos sobre texto sintético
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-02/CA-30. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `dcdc672b9bec`.

### T-05 — Puesta en verde del PR (CA-01) y enlace de la ejecución en el ledger

- **Descripción**: Abrir o actualizar el PR de `feat/three-components` y dejar los trabajos `server`, `retrieval-eval`, `client`, `web` y `contracts` en verde en `ubuntu-latest`. Corregir las diferencias Linux/Docker Desktop que afloren. Anotar en `Notas` el enlace de la ejecución y los tiempos medidos. Fuente: CA-01; R-08.
- **Changelog**: Los cinco trabajos de la CI (servidor, calidad de recuperación, cliente, portal y contratos) terminan en verde en Linux y un fallo del build ya no puede dejar un trabajo en verde.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.25h (estimado) · real 0.3h (estimado)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 68 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-03, T-04
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`, `docs/roadmap/2026-11-12-three-components/spec.md`, `docs/roadmap/2026-11-12-three-components/improvement-plan.md` (nota de CA-01 y autorización de push del usuario, gap 3 de la revisión de la Fase 1; editadas por el orquestador)
- **Cubre (tests)**: —
- **Verificación**:
  - `gh run list --branch feat/three-components --limit 1 --json conclusion,workflowName` → `conclusion: success`
  - `gh run view <id> --json jobs --jq '.jobs[].conclusion'` → 5 × `success`

**Criterios de aceptación**
- [x] Los cinco trabajos terminan en verde en el PR de esta rama; enlace anotado en `Notas`
- [x] Los tiempos de cada trabajo en CI quedan anotados (la hipótesis de la spec pasa a hecho medido)
- [x] Ningún test se desactiva ni se marca como omitido para conseguir el verde
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (el usage-meter no devolvió medición para este tramo, null; tiempo (estimado), no es el del bloque de T-01); la corrección fix1 lleva solo la cifra medida de 0,13 h, sin JSON

**Subtareas**
- [x] Hacer `git push` de la rama y abrir el PR (acción visible: requiere confirmación del usuario si no está autorizada)
- [x] Diagnosticar los fallos de Linux uno a uno
- [x] Anotar enlace y tiempos
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-01, R-08. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `a60bbaaf5a2f`.

### T-06 — Prueba de rojo en rama desechable (CA-03)

- **Descripción**: En una rama desechable que no se fusiona, introducir un test que falla a propósito y comprobar que el trabajo correspondiente queda en rojo; borrar la rama. Anotar el enlace de la ejecución. Fuente: CA-03.
- **Changelog**: 
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.12h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 34 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-05
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `gh run list --branch ci-red-probe --limit 1 --json conclusion` → `conclusion: failure`
  - `git branch -a --list '*ci-red-probe*'` → vacío

**Criterios de aceptación**
- [x] La ejecución de la rama desechable deja en rojo el trabajo `server` (enlace en `Notas`)
- [x] La rama se borra y no se fusiona; `git branch -a` no la lista al cerrar
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio (tiempo (estimado) 0.1h, ver Notas)

**Subtareas**
- [x] Crear rama `ci-red-probe`, añadir un test con `self.fail()`, empujar
- [x] Comprobar el rojo y anotar el enlace
- [x] Borrar la rama local y remota
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `257c3f3e4da9`.

### T-07 — Documentar la CI en `docs/operations.md`

- **Descripción**: Añadir a `docs/operations.md` una sección «Integración continua»: qué trabajos hay, cómo reproducir cada uno en local, tiempos medidos y política de no publicar ni usar secretos. Fuente: CA-01, CA-32.
- **Changelog**: La documentación de operación describe la integración continua: los cinco trabajos, cómo repetir cada uno en local, sus tiempos medidos y la política de no publicar ni usar secretos.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.06h (estimado) · real 0.01h (medido)
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 17 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-05
- **Tipo**: docs
- **Archivos**: `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -n "Integración continua\|Continuous integration" docs/operations.md` → al menos 1 coincidencia
  - lectura: cada comando citado en la sección coincide con el del workflow

**Criterios de aceptación**
- [x] La sección lista los cinco trabajos con su comando local equivalente
- [x] Las rutas y comandos citados existen (`ls` de cada uno)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Redactar según `docs-style.md`
- [x] Comprobar los comandos citados
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32, evaluación C-01 (documentación 1 h). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ac8832a3d43a`.

### T-08 — Revisión adversarial de la Fase 1

- **Descripción**: Revisión adversarial de la fase (≈ 0,5 × la implementación, lección de la retro): buscar huecos en la red de CI (trabajo que pasa sin ejecutar nada, caché que oculta fallos, secreto filtrable, comando distinto del local). Registrar hallazgos en `review.md` y cerrar los Critical/Important con su arreglo. Fuente: retro de `retrieval-quality`, R-06.
- **Changelog**: Las comprobaciones de la integración continua se revisaron de forma adversarial en tres intentos y resisten modificaciones deliberadas del workflow.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 5.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.69h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 189 k in / 17 k out tok · ⚠️ verificar €
- **Dependencias**: T-01 … T-07
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: `review.md`, sección «Fase 1», sin hallazgos Critical/Important abiertos · `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK` · Evidencia (2026-11-12): `review.md` sección «Fase 1»; 3 intentos (lentes A, B, C; luego A y B+C; luego A+B+C); sin Critical/Important abiertos; 5 Minor del intento 3 como deuda aceptada. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2a8346a41989`.

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 1» con intentos, hallazgos y su estado
- [x] 0 hallazgos Critical o Important abiertos
- [x] `usage-meter start/close` por cada intento de revisión — EXCEPCIÓN: los intentos de revisión no se midieron con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin medición propia (estimado)

**Subtareas**
- [x] Revisar el workflow contra CA-01…CA-03
- [x] Probar un cambio que debería romper cada trabajo
- [x] Registrar y cerrar hallazgos
- [x] `usage-meter start/close` por intento

**Notas**: Procedencia: `docs/roadmap/2026-11-09-retrieval-quality/retro.md` (revisión como partida propia). No escribe en `testing/` (reservado a `qa`).

---

## Fase 2 — Servidor sin modelo de lenguaje (C-04)

**Estado**: completado · **Estimado**: 37.8h (31.5h base) · **Real**: — · **Coste est.**: 1.890 € · **Tokens est.**: 1245 k

### T-09 — Interruptor `MEMORY_EXTRACT_ENABLED` en la ingesta con recibo aditivo

- **Descripción**: Añadir `MEMORY_EXTRACT_ENABLED` (por defecto `0`). Con la extracción apagada, un evento con `generate: true` se acepta (202) sin crear trabajo `extract` y el recibo lleva el campo aditivo `extraction: "disabled"`. Ajustar los tests que asumían `extract` para que lo activen explícitamente. Fuente: CA-14, P-03 (decidida), R-03.
- **Changelog**: Con la configuración por defecto, un resumen con `generate: true` se acepta con 202 sin crear trabajo de extracción y el recibo lo indica con `extraction: "disabled"`; el resto del recibo no cambia.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.45h (estimado) · real 1.34h (medido: 1.25 h de la ventana win-271d361e de las 12:03Z a las 13:23Z, que cubre T-09..T-16 en bloque, más 0.09 h de la ventana única `T-09-fix1` de las correcciones del intento 1 de la Fase 2, que cubre también las de T-10, T-11 y T-15: no sumar a las demás)
- **Supervisión**: est. 0.11h (≈25 % IA) · real —
- **Previsión IA**: 125 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-05
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `memory_platform/store_ingest.py`, `memory_platform/models.py`, `memory_platform/tests/test_native.py`, `memory_platform/tests/test_store.py`, `memory_platform/tests/test_ingest_extract_switch.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_embeddings.py`, `memory_platform/tests/test_fts_language.py`, `memory_platform/tests/test_jobs.py`, `memory_platform/tests/test_metrics.py`, `memory_platform/tests/test_portal_collections.py`, `memory_platform/tests/test_privacy.py`, `memory_platform/tests/live_probe.py`, `memory_platform/worker.py`, `memory_platform/app.py`, `memory_platform/tests/e2e_fixture.py`, `memory_platform/tests/test_e2e_fixture.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t09 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build` anterior incluye el test nuevo `test_ingest_extract_switch` → `ok`

**Criterios de aceptación**
- [x] Con la configuración por defecto, un evento `summary` con `generate: true` devuelve 202, no crea trabajo `extract` y el recibo contiene `extraction: "disabled"`
- [x] Con `MEMORY_EXTRACT_ENABLED=1` el comportamiento actual no cambia (trabajo `extract` creado)
- [x] `test_native.py` y `test_store.py` pasan con la extracción activada de forma explícita donde la usan
- [x] El recibo no pierde ningún campo existente (solo se añade)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test nuevo en rojo (`generate: true` con la configuración por defecto)
- [x] Añadir el ajuste en `Settings` y el filtro de `destinations`
- [x] Añadir `extraction` al recibo
- [x] Ajustar los tests de `test_native.py` y `test_store.py`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-14/P-03; CLI 0.3.0 envía `generate: true` en resúmenes (`packages/kairos-cli/lib/capture.mjs:84`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `1d90a8be7a07`.


RED: `memory_platform/tests/test_ingest_extract_switch.py` falló con AttributeError: 'Settings' object has no attribute 'extract_enabled'; KeyError: 'extraction'; AssertionError: ['embed', 'extract'] != ['embed'] (fuentes de HEAD, 3 fallos y 5 errores de 11 junto con T-10) · 2026-11-12.

### T-10 — El worker no instancia el proveedor `extract` con la extracción apagada

- **Descripción**: Con `MEMORY_EXTRACT_ENABLED=0`, el worker no crea el proveedor `extract` (solo `embed`) y no reclama trabajos `extract` heredados sin dejarlos en estado ambiguo. Ajustar `test_worker.py` y `test_review_regressions.py`. Fuente: CA-14, CA-18, S-04.
- **Changelog**: El worker ya no crea el proveedor de extracción por defecto; un trabajo de extracción que ya estaba en cola no se pierde: queda fallido con el motivo `extraction_disabled` y se puede reintentar al activar la extracción.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.45h (estimado) · real 0.10h (medido, ventana win-25cfb04d abierta a las 13:12Z; solape con T-09, no sumar)
- **Supervisión**: est. 0.11h (≈25 % IA) · real —
- **Previsión IA**: 125 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-09
- **Tipo**: backend
- **Archivos**: `memory_platform/worker.py`, `memory_platform/tests/test_worker.py`, `memory_platform/tests/test_review_regressions.py`, `memory_platform/observability.py`, `memory_platform/tests/test_native_runtime.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t10 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] `Worker` construido con la configuración por defecto no tiene el proveedor `extract` (test que inspecciona `providers`)
- [x] Con la extracción activada el comportamiento y los tests actuales no cambian
- [x] Un trabajo `extract` preexistente con la extracción apagada no llama a ningún proveedor y queda registrado con un motivo explícito (sin perderse)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo sobre `providers`
- [x] Condicionar la creación del proveedor
- [x] Definir y probar el trato del trabajo `extract` heredado (aditivo: no se borra)
- [x] Ajustar los tests existentes
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-14. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `49f44cff78c4`.


RED: `memory_platform/tests/test_worker.py::ExtractionSwitchTests` falló con AssertionError: Expected 'Ollama' to not have been called. Called 1 times.; TypeError: Settings.__init__() got an unexpected keyword argument 'extract_enabled' (fuentes de HEAD) · 2026-11-12.

### T-11 — `MEMORY_CORPUS_ANSWER=off` por defecto con error `corpus_answer_disabled`

- **Descripción**: Añadir `MEMORY_CORPUS_ANSWER` (por defecto `off`). Apagado, `corpus_answer` sigue en la lista de herramientas (34) y responde `corpus_answer_disabled` sin llamar a ningún proveedor; `corpus_answer_status` sigue leyendo respuestas ya guardadas. Fuente: CA-15, P-04 (decidida), D-4.
- **Changelog**: `corpus_answer` viene apagada: sigue en la lista de las 34 herramientas pero responde `corpus_answer_disabled` sin llamar a ningún modelo, y `corpus_answer_status` sigue leyendo las respuestas ya guardadas.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.39h (estimado) · real 0.28h (medido: 0.10 h de la ventana win-62f2662a abierta a las 13:12Z, solape con T-09, más 0.18 h de la ventana única T-11-fix2 de las correcciones del intento 2)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 107 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-10
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `memory_platform/corpus_answers.py`, `memory_platform/corpus_answer_tools.py`, `memory_platform/app.py`, `memory_platform/tests/test_corpus_answers.py`, `memory_platform/tests/test_corpus_gateway.py`, `memory_platform/tests/test_corpus_answers.py`, `docs/corpus-generated-answers.md`, `docs/configuration.md`, `CHANGELOG.md`, `CHANGELOG.es.md` (nota: documentación de la corrección del intento 2, gap 3)
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t11 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `python scripts/export-contracts.py && git diff --stat docs/contracts` → sin diff (34 herramientas intactas) Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `624ad06adb50`.

**Criterios de aceptación**
- [x] Por defecto `corpus_answer` devuelve `corpus_answer_disabled` y el proveedor simulado recibe 0 llamadas
- [x] Con `MEMORY_CORPUS_ANSWER=on` y un modelo configurado, los 21 tests actuales de `test_corpus_answers.py` pasan
- [x] `corpus_answer_status` lee respuestas ya guardadas con el interruptor apagado
- [x] `docs/contracts/kairos-mcp.json` sigue con 34 herramientas (el contrato no cambia)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo del error y del proveedor sin llamadas
- [x] Interruptor en `Settings` y en el servicio
- [x] Activarlo en los tests existentes que lo necesitan
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-15/P-04. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `93441aef60ee`.


RED: `memory_platform/tests/test_corpus_answers.py::CorpusAnswerSwitchTests` falló con AssertionError: MemoryError not raised; AssertionError: 200 != 403 en test_corpus_gateway (fuentes de HEAD) · 2026-11-12.

### T-12 — `MEMORY_LLM_MODEL` sin valor por defecto y validación al arrancar; retirar `beam:cloud`

- **Descripción**: Quitar `beam:cloud` de `Settings`, de `docker-compose.yml` y de `docs/configuration.md`. `Settings.from_env()` falla con un mensaje que nombra `MEMORY_LLM_MODEL` si se activa `extract` o `corpus_answer` sin modelo. Fuente: CA-16, S-04, D-2.
- **Changelog**: `MEMORY_LLM_MODEL` ya no tiene modelo por defecto: solo es obligatorio si se activa la extracción o las respuestas generadas, y sin él el arranque falla nombrando la variable.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.26h (estimado) · real 0.10h (medido, ventana win-df73ad0f abierta a las 13:12Z; solape con T-09, no sumar)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-11
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `docker-compose.yml`, `docs/configuration.md`, `memory_platform/tests/test_providers.py`
- **Cubre (tests)**: —
- **Verificación**: `grep -n "beam" memory_platform/config.py docker-compose.yml docs/configuration.md` → sin salida (exit 1) · `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t12 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `f1f0b05d4223`.

**Criterios de aceptación**
- [x] `grep -n beam` no devuelve nada en `memory_platform/config.py`, `docker-compose.yml` ni `docs/configuration.md`
- [x] `Settings.from_env()` con `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on` y sin `MEMORY_LLM_MODEL` lanza un error cuyo texto contiene `MEMORY_LLM_MODEL`
- [x] Con ambos apagados, el arranque no exige modelo
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo de las tres combinaciones
- [x] Eliminar el valor por defecto y añadir la validación
- [x] Actualizar compose y manual
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-16/S-04. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c636b005540c`.


RED: `memory_platform/tests/test_providers.py::ModelRequirementTests` falló con AssertionError: ValueError not raised (extraccion, corpus, modelo en blanco); AssertionError: 'beam:cloud' != ''; 'beam' unexpectedly found en config.py (fuentes de HEAD) · 2026-11-12.

### T-13 — Proxy de Ollama con lista de permitidos y `OLLAMA_ALLOW_CHAT`

- **Descripción**: Sustituir `location /` por una lista de permitidos: `/api/embed` y `/api/version` llegan al upstream; el resto responde 403 desde el proxy. `OLLAMA_ALLOW_CHAT=1` habilita además `/api/chat`. Probar con un upstream simulado en un proyecto Compose aislado. Fuente: CA-17, S-09, P-10 (decidida).
- **Changelog**: El proxy de Ollama solo deja pasar `/api/embed` y `/api/version`; el resto (descargar, borrar, crear, generar) recibe 403 desde el propio proxy, y `OLLAMA_ALLOW_CHAT=1` habilita además `/api/chat`.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.39h (estimado) · real 0.10h (medido, ventana win-5a3a64c5 abierta a las 13:12Z; solape con T-09, no sumar)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 107 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-12
- **Tipo**: devops
- **Archivos**: `ollama-proxy/default.conf.template`, `docker-compose.yml`, `memory_platform/tests/test_ollama_proxy.py`, `memory_platform/Dockerfile`, `memory_platform/tests/ollama_proxy_probe.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s memory_platform/tests -p test_ollama_proxy.py` → `OK` (los casos que requieren Docker se ejecutan dentro del proyecto aislado `kairos-proxy-t13`)
  - `docker compose -p kairos-proxy-t13 down -v` → solo elimina recursos `kairos-proxy-t13_*`

**Criterios de aceptación**
- [x] `/api/embed` y `/api/version` llegan al upstream simulado
- [x] `/api/pull`, `/api/delete`, `/api/create`, `/api/chat` y `/api/generate` responden 403 sin llegar al upstream
- [x] Con `OLLAMA_ALLOW_CHAT=1`, `/api/chat` llega
- [x] La prueba usa un proyecto Compose con nombre distinto de `knowledge-graphs` y redes y volúmenes renombrados; no toca recursos `knowledge-graphs-*`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Escribir primero la prueba con upstream simulado (rojo: hoy todo pasa)
- [x] Reescribir la plantilla nginx con `OLLAMA_ALLOW_CHAT`
- [x] Verificar `nginx -t` de la plantilla renderizada
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-17/S-09/P-10. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `1bc09a5a1c0a`.


RED: `memory_platform/tests/test_ollama_proxy.py` falló con KeyError: 'OLLAMA_ALLOW_CHAT'; KeyError: 'user'; AssertionError: 'return 403' not found (3 fallos y 4 errores de 14); la sonda contra la plantilla anterior: status 200, expected 403 en pull, delete, create, generate, chat y las evasiones · 2026-11-12.

### T-14 — Proxy de Ollama sin root

- **Descripción**: Ejecutar el proxy de Ollama con un usuario sin privilegios (resto de S-09, incluido por P-10 decidida; partida +1 h sobre la evaluación). Fuente: S-09 segunda mitad, P-10.
- **Changelog**: El proxy de Ollama ya no corre como root: usa el usuario sin privilegios `nginx`, sin capacidades y con el sistema de ficheros en solo lectura.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real 0.10h (medido, ventana win-48eb447a abierta a las 13:12Z; solape con T-09, no sumar)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 36 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-13
- **Tipo**: devops
- **Archivos**: `ollama-proxy/default.conf.template`, `docker-compose.yml`, `ollama-proxy/Dockerfile`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker compose -p kairos-proxy-t14 -f docker-compose.yml -f <override aislado> exec ollama id -u` → distinto de `0`
  - `python -m unittest discover -s memory_platform/tests -p test_ollama_proxy.py` → `OK`

**Criterios de aceptación**
- [x] El contenedor del proxy corre con un UID distinto de 0 y escucha en un puerto no privilegiado o con capacidades mínimas
- [x] La prueba de T-13 sigue en verde
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Comprobar la imagen base y el puerto 11434
- [x] Configurar `user:` o imagen sin root
- [x] Repetir la prueba aislada de T-13
- [x] `usage-meter start/close`

**Notas**: Procedencia: P-10 (proxy sin root dentro del alcance). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ea2f38c3e45b`.


RED: `memory_platform/tests/test_ollama_proxy.py::ComposeServiceTests` falló con KeyError: 'user'; la sonda con la plantilla de T-13 y sin user: imprimio proxy uid: 0 (the proxy runs as root) · 2026-11-12.

### T-15 — Suite completa sin modelo configurado y espía de `/api/chat` (CA-18)

- **Descripción**: Probar que la suite pasa con `MEMORY_LLM_MODEL` sin definir y con un espía que falla ante cualquier llamada a `/api/chat`, y que el arranque de `memory-api` y `memory-worker` no la hace. Fuente: CA-18, D-2.
- **Changelog**: La suite del servidor corre sin modelo de lenguaje configurado y con un espía que falla si algo llama a `/api/chat`; el recibo de la suite informa de las llamadas (siempre 0).
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.39h (estimado) · real 0.10h (medido, ventana win-4403e522 abierta a las 13:12Z; solape con T-09, no sumar)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 107 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-12, T-13
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_no_llm.py`, `memory_platform/tests/run_postgres.py`, `memory_platform/tests/llm_spy.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t15 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 y espía con 0 llamadas
  - `docker build` anterior incluye `test_no_llm` → `ok`

**Criterios de aceptación**
- [x] La suite backend pasa con `MEMORY_LLM_MODEL` sin definir y el espía instalado
- [x] El espía registra 0 llamadas a `/api/chat` durante la ingesta de un resumen con `generate: true`, el worker y `corpus_answer` apagado
- [x] El arranque de `create_app` y del `Worker` no abre conexión a `/api/chat`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Crear el espía (servidor HTTP local que marca fallo ante `/api/chat`)
- [x] Ejecutar la suite entera con el espía activo
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-18. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6336d15e3b31`.


RED: `memory_platform/tests/test_no_llm.py` falló con AssertionError: 'beam:cloud' != ''; KeyError: 'extraction'; AssertionError: 200 != 403 (corpus_answer llego al proveedor) (3 fallos y 2 errores de 6, fuentes de HEAD) · 2026-11-12.

### T-16 — Documentar la configuración sin modelo de lenguaje

- **Descripción**: Documentar `MEMORY_EXTRACT_ENABLED`, `MEMORY_CORPUS_ANSWER`, `MEMORY_LLM_MODEL` (sin valor por defecto), `OLLAMA_ALLOW_CHAT` y el trato de `generate: true`. Fuente: CA-32, C-04.
- **Changelog**: La documentación describe el servidor sin modelo de lenguaje: las variables `MEMORY_EXTRACT_ENABLED`, `MEMORY_CORPUS_ANSWER`, `MEMORY_LLM_MODEL` y `OLLAMA_ALLOW_CHAT`, el trato de `generate: true`, el proxy cerrado y su sonda.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.26h (estimado) · real 0.10h (medido, ventana win-fbfba66a abierta a las 13:12Z; solape con T-09, no sumar)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-15
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/corpus-generated-answers.md`, `docs/operations.md`, `CHANGELOG.md`, `CHANGELOG.es.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -c "MEMORY_EXTRACT_ENABLED\|MEMORY_CORPUS_ANSWER\|OLLAMA_ALLOW_CHAT" docs/configuration.md` → ≥ 3
  - lectura: valores por defecto coinciden con `memory_platform/config.py`

**Criterios de aceptación**
- [x] Cada variable nueva aparece en `docs/configuration.md` con su valor por defecto real
- [x] `docs/corpus-generated-answers.md` explica que `corpus_answer` está apagado por defecto y el error `corpus_answer_disabled`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Redactar según `docs-style.md`
- [x] Comprobar cada valor contra `config.py`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `b3877fda111e`.

### T-17 — Revisión adversarial de la Fase 2

- **Descripción**: Revisión adversarial: ¿queda algún camino que llame a `/api/chat`? ¿se pierde algún trabajo `extract` heredado? ¿el recibo aditivo rompe a un cliente? ¿el 403 del proxy se puede esquivar (rutas con `//`, mayúsculas, `/api/embed/..`)? Registrar y cerrar hallazgos. Fuente: retro, R-03.
- **Changelog**: El servidor sin modelo de lenguaje se revisó de forma adversarial en tres intentos (conformidad, defectos, seguridad del proxy y rendimiento del worker) sin hallazgos Critical ni Important abiertos.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 10.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.44h (estimado) · real —
- **Supervisión**: est. 0.36h (≈25 % IA) · real —
- **Previsión IA**: 397 k in / 35 k out tok · ⚠️ verificar €
- **Dependencias**: T-09 … T-16
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t17 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · lectura: `review.md`, sección «Fase 2», sin hallazgos Critical/Important abiertos · Evidencia (2026-11-12): `review.md` sección «Fase 2»; 3 intentos (A+B+C+D; A y B; A+B). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2a84e4c1ff24`.

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 2» con intentos y hallazgos
- [x] 0 hallazgos Critical o Important abiertos
- [x] Suite completa en verde tras cada arreglo
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: los intentos de revisión no se midieron con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado)

**Subtareas**
- [x] Probar evasiones de la lista de permitidos
- [x] Buscar llamadas a proveedores con `grep -rn "/api/chat" memory_platform`
- [x] Cerrar hallazgos
- [x] `usage-meter start/close` por intento — EXCEPCIÓN: ver el criterio anterior

**Notas**: Procedencia: retro de `retrieval-quality`. No escribe en `testing/`.

---

## Fase 3 — Paridad REST /v1 (C-02)

**Estado**: completado · **Estimado**: 36.0h (30.0h base) · **Real**: — · **Coste est.**: 1.800 € · **Tokens est.**: 1282 k

### T-18 — `POST …/corpora` acepta `date_start` y `date_end`

- **Descripción**: Añadir los campos opcionales `date_start` y `date_end` a `CorpusSelection` y pasarlos a `build_corpus`, como ya hace la herramienta. Fuente: CA-05; hallazgo de paridad `build_corpus` (parcial).
- **Changelog**: `POST /v1/projects/{id}/corpora` acepta `date_start` y `date_end` opcionales y filtra por fechas igual que la herramienta `build_corpus`; las peticiones sin ellos no cambian.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real 0.20h (medido: 0.15h ventana win-1d16767d, 14:54Z-15:12Z + 0.05h corrección fix1)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-17
- **Tipo**: backend
- **Archivos**: `memory_platform/models.py`, `memory_platform/app.py`, `memory_platform/tests/test_api.py`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/agent_store.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t18 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] `POST …/corpora` con fechas filtra igual que la herramienta `build_corpus`
- [x] Los campos son opcionales: ninguna petición existente cambia
- [x] Hay test de acceso permitido, de lector sin permiso (403) y de proyecto ajeno
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo (el campo se ignora hoy)
- [x] Añadir campos y su paso a `build_corpus`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `a63bee2b91d6`.


RED: `memory_platform/tests/test_api.py::ParityEndpointTests::test_build_corpus_accepts_date_start_and_date_end_like_the_tool` falló con AssertionError: 422 != 200 (campos date_start/date_end rechazados por extra=forbid) contra las fuentes de HEAD · 2026-11-12.

Corrección intento 1 (gap 2, 16539ea): `agent_store.corpus_filters` captura `OverflowError` además de `ValueError` (fechas válidas extremas → 422 `Invalid ISO date filter`); test REST y MCP `test_extreme_valid_dates_are_invalid_input_through_the_endpoint_and_the_tool`. usage-meter three-components/T-18-fix1: 0.05 h IA (medido, win-4c1e82fe). Suite: 591 tests, 0 fallos, 0 omitidos, `llm_chat_calls` 0.

### T-19 — Endpoint `/v1` de `capture_policy`

- **Descripción**: Crear un endpoint nuevo (`GET …/capture-policy`, ruta distinta de `…/policy`) que devuelve lo que devuelve `Store.capture_policy`. Fuente: CA-05; hallazgo de paridad «Falta».
- **Changelog**: Nuevo `GET /v1/projects/{id}/capture-policy`: responde si la clave puede capturar en el proyecto y con qué modo de captura, igual que la herramienta `capture_policy`; `GET …/policy` no cambia.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.29h (estimado) · real 0.05h (medido, ventana win-e2c0d4fa, 15:15Z-15:20Z)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 80 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-18
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t19 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] El endpoint devuelve el mismo contenido que la herramienta `capture_policy` para el mismo proyecto y credencial
- [x] Test de acceso permitido, lector sin permiso (403) y proyecto ajeno
- [x] `GET …/policy` no cambia
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo (404 hoy)
- [x] Añadir ruta, modelo de respuesta y permiso
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `f7f4e66ca385`.


RED: `memory_platform/tests/test_api.py::ParityEndpointTests::test_capture_policy_endpoint_returns_what_the_tool_returns` falló con AssertionError: 404 != 200 ({"detail":"Not Found"}: la ruta capture-policy no existe) contra las fuentes de HEAD · 2026-11-12.

### T-20 — Endpoint `/v1` de reconciliación de `event_status` por proyecto

- **Descripción**: Crear el endpoint que ejecuta `reconcile_capture` para un `project_id` y evita el N+1 de la herramienta compuesta. Fuente: CA-05; hallazgo «Parcial» de `event_status`; R-05.
- **Changelog**: Nuevo `GET /v1/projects/{id}/events/{event_id}/status`: reconcilia un evento por proyecto en una sola llamada (recibo, trabajos y `complete`, o `found: false`), igual que `event_status` con `project_id`.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real 0.04h (medido, ventana win-41e2d9a8, 15:20Z-15:26Z)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-19
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t20 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] El endpoint devuelve la misma reconciliación que `event_status` con `project_id`
- [x] Test de acceso permitido, 403 y proyecto ajeno
- [x] `GET /v1/events/{id}` y `GET /v1/jobs/{id}` no cambian
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo
- [x] Añadir ruta y respuesta
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05, R-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `dcc43e27c623`.


RED: `memory_platform/tests/test_api.py::ParityEndpointTests::test_event_status_by_project_reconciles_like_the_tool_in_one_call` falló con AssertionError: 404 != 200 ({"detail":"Not Found"}: la ruta events/{id}/status no existe) contra las fuentes de HEAD · 2026-11-12.

### T-21 — Endpoints `/v1` de lectura de observaciones (`get_observations`, `observation_search`, `observation_context`)

- **Descripción**: Crear tres endpoints nuevos con la semántica de `AgentStore.observations`, en rutas distintas de `GET /v1/observations` (listado del portal). Fuente: CA-05; hallazgo «Falta (3)».
- **Changelog**: Tres lecturas nuevas bajo `/v1/projects/{id}/observations/` (`get`, `search`, `context`) devuelven lo mismo que las herramientas `get_observations`, `observation_search` y `observation_context`; `GET /v1/observations` sigue sirviendo el listado del portal.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.58h (estimado) · real 0.10h (medido, ventana win-f438c3ad, 15:26Z-15:35Z)
- **Supervisión**: est. 0.14h (≈25 % IA) · real —
- **Previsión IA**: 160 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-20
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_agent_tools.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t21 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] Los tres endpoints devuelven lo mismo que su herramienta para igual credencial y argumentos
- [x] `GET /v1/observations` conserva su semántica y respuesta (test de no regresión)
- [x] Cada endpoint tiene test de acceso permitido, lector sin permiso (403) y proyecto ajeno
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo de los tres + de no regresión del listado
- [x] Añadir rutas, modelos y permisos
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0a3ebfcf7c6d`.


RED: `memory_platform/tests/test_api.py::ParityEndpointTests::test_observation_reads_return_what_the_three_tools_return_and_the_portal_listing_is_untouched` falló con AssertionError: 404 != 200 ({"detail":"Not Found"}: las rutas observations/get, search y context no existen) contra las fuentes de HEAD · 2026-11-12.

### T-22 — Endpoint `/v1` de `query_corpus`

- **Descripción**: Crear el endpoint de consulta de un corpus (`query_corpus`) con la misma semántica que `AgentStore.query_corpus`. Fuente: CA-05; hallazgo «Falta».
- **Changelog**: Nuevo `POST /v1/projects/{id}/corpora/{name}/query`: consulta un corpus ya preparado y devuelve la misma evidencia léxica que la herramienta `query_corpus`, sin llamar a ningún modelo de lenguaje.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real 0.05h (medido: 0.04h ventana win-7f7ac855, 15:36Z-15:42Z + 0.01h corrección fix1; la corrección fix2 va en el bloque de T-24)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-21
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/nginx.conf`, `memory_platform/tests/test_nginx_portal.py`, `memory_platform/tests/nginx_portal_probe.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t22 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] El endpoint devuelve el mismo contenido que la herramienta para igual credencial y argumentos
- [x] Test de acceso permitido, 403 y proyecto ajeno
- [x] No llama a ningún modelo de lenguaje (usa el espía de T-15)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo
- [x] Añadir ruta y modelo
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `a90b0934b9df`.


RED: `memory_platform/tests/test_api.py::ParityEndpointTests::test_query_corpus_returns_what_the_tool_returns_without_a_language_model` falló con AssertionError: 404 != 409 (la ruta corpora/{name}/query no existe) contra las fuentes de HEAD · 2026-11-12.

Corrección intento 1 (gap 4, 16539ea): las cinco rutas `…/corpora/{name}/…` pasan a `{name:path}` (un nombre con `/` enviado como `%2F` llega a query, prime, rebuild, answers y status; OpenAPI sigue mostrando `{name}`, contrato OpenAPI sin diferencias); test `test_a_corpus_name_with_a_slash_is_reached_by_every_route_with_a_name_like_the_tool` y casos `*_slash` en la paridad. usage-meter three-components/T-22-fix1: 0.01 h IA (medido, win-7a3127dc).

Corrección intento 2 (gap 5, 9030645): `location /memory-api/` de `memory_platform/nginx.conf` ya no usa `proxy_pass` con URI (decodificaba `%2F` y resolvía `//` y `..`: `a%2F..%2Fb` llegaba como `b`): reescribe `$request_uri` quitando el prefijo (`rewrite ^ $request_uri; rewrite ^/memory-api/(.*)$ /$1 break;`) y pasa `$uri` sin normalizar a un `upstream memory_api` con nombre (un `proxy_pass` con variable y host suelto exigiría `resolver`); la query va intacta. Probado con el nginx fijado de `Dockerfile.web` y un eco (`memory_platform/tests/nginx_portal_probe.py`, 15 casos, `PORTAL_PROBE_RESULT {"cases": 15, "failures": []}`): antes `a%2F..%2Fb`→`b`, `a//b`→`a/b`, `a/../b`→`b`; ahora los cuatro llegan tal cual; `/memory-api/metrics`, `//metrics`, `%2Fmetrics`, `%6Detrics`, `x%2F..%2Fmetrics` y `v1/%2e%2e/metrics` siguen en 404 (la regla de `/metrics` se evalúa sobre la URI normalizada y va antes); `/v1/`, `/mcp`, `/health/ready`, `/memory-api/` y `/memory-api/health/ready` sin cambios. Test estático `memory_platform/tests/test_nginx_portal.py` (4 tests, sin Docker). `memory_platform/nginx.conf` y los dos ficheros nuevos entran en `Archivos` de T-22: el gap lo pedía y no estaban declarados. usage-meter three-components/T-22-fix2: bloque compartido con T-24 y T-25, 0.36 h IA (medido), contado en T-24.

### T-23 — Endpoint `/v1` de `team_search`

- **Descripción**: Crear el endpoint de búsqueda de trabajo de equipo (`team_search`). Fuente: CA-05; hallazgo «Falta».
- **Changelog**: Nuevo `GET /v1/projects/{id}/team-search`: busca en el trabajo de equipo del proyecto con los mismos resultados que la herramienta `team_search`.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real 0.05h (medido, ventana win-dfc5ac09, 15:42Z-15:47Z)
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-22
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_extended_gateway.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t23 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [x] El endpoint devuelve lo mismo que la herramienta `team_search`
- [x] Test de acceso permitido, 403 y proyecto ajeno
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo
- [x] Añadir ruta y modelo
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `8b9b3b4cb136`.


RED: `memory_platform/tests/test_api.py::ParityEndpointTests::test_team_search_returns_what_the_tool_returns` falló con AssertionError: 404 != 200 (la ruta team-search no existe) contra las fuentes de HEAD · 2026-11-12.

### T-24 — `x-kairos-endpoint` por herramienta en el contrato MCP

- **Descripción**: Añadir el campo aditivo `x-kairos-endpoint` (`{method, path}` o `local` para `important_workflow`) a cada una de las 34 herramientas en el exportador y regenerar los contratos. Fuente: CA-04, plan director §2.2.
- **Changelog**: Cada una de las 34 herramientas del contrato MCP declara en `x-kairos-endpoint` el método y la ruta `/v1` que la sirve (`local` para `important_workflow`); los demás campos del contrato no cambian.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real 0.61h (medido: 0.09h ventana win-1a8fa55c, 15:47Z-15:52Z + 0.16h corrección fix1 + 0.36h corrección fix2, un bloque de 11:26Z-11:54Z que cubre T-22, T-24 y T-25 y se cuenta una sola vez aquí)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-23
- **Tipo**: backend
- **Archivos**: `scripts/export-contracts.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/tests/test_contract_additive.py`, `memory_platform/tests/test_tool_endpoint_parity.py`, `memory_platform/app.py`, `memory_platform/agent_store.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t24 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → solo adiciones

**Criterios de aceptación**
- [x] Cada herramienta de `tools` tiene `x-kairos-endpoint` con `method` y `path` presentes en `memory-platform.openapi.json`, o `local` (solo `important_workflow`)
- [x] El contrato regenerado tiene 34 herramientas, mismo orden y ningún campo existente cambiado
- [x] El MCP interno sigue listando las mismas herramientas (el campo se añade al contrato, no al protocolo)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo de CA-04
- [x] Definir la tabla herramienta → endpoint en el exportador
- [x] Regenerar contratos
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-04. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `27436754209c`.


RED: `memory_platform/tests/test_contract_additive.py::ContractAdditiveTests::test_ca04_every_tool_declares_an_endpoint_that_exists_in_the_openapi_or_is_local` falló con AssertionError: unexpectedly None : projects has no x-kairos-endpoint contra las fuentes de HEAD · 2026-11-12.

Corrección intento 1 (gap 1, 16539ea): `x-kairos-endpoint` pasa a `{method, path, args, [fixed], [without_project_id]}`: `args` lista TODOS los argumentos de la herramienta (`in` path/query/body, `name` REST, `transform: csv-list` para `types/concepts/files`, cuerpo completo si no hay `name`), `fixed` (`fresh: true` de `reprime_corpus`), `when_absent` (lectura + pick) para `rebuild_corpus.expected_version`, y `without_project_id` con la composición y la regla `complete` (recibo `superseded` nunca completo) de `event_status`; reglas generales en la clave nueva `x-kairos-translation` de `kairos-mcp.json`. Decisión: NO se relaja `CorpusRebuild` en el servidor (su `required` ya está en la línea base 6008da0 y quitarlo no es aditivo: lo probó `test_contract_additive`), por eso el contrato declara la transformación; `expected_version: 0` no es traducible (la herramienta da conflicto, el endpoint 422: ambos rechazan). `types` como cadena: transformación declarada, el endpoint sigue aceptando solo listas. Comentario del exportador corregido. Contrato: 34 herramientas, OpenAPI sin cambios, kairos-mcp.json solo gana claves. usage-meter three-components/T-24-fix1: 0.16 h IA (medido, win-bf9902fd). PARADA POR ORDEN DEL USUARIO tras el commit 16539ea; quedan: CI del commit (push), comprobar diff aditivo contra 33fd830 con scope-check y el cierre de la revisión (intento 2).

Corrección intento 2 (gaps 1, 2 y 3, 9030645): (1) NUEVO `GET /v1/projects/{project_id}/corpus?name=…` (`kairos_corpus`, `AgentStore.corpus_receipt`, compone `store._require` y una consulta: `store_surface.json` intacto): devuelve el recibo del corpus (con `version`), 404 `not_found` si el nombre no es del actor, permiso `read` o, si no, `write` (`rebuild_corpus` solo pide `write`, así que una clave que puede reconstruir puede leer la versión que compara); el nombre va en la query (sin ambigüedad de rutas: una ruta `…/corpora/{name:path}` GET chocaría con `answers/{request_id}`) y sin cota de longitud (la herramienta no la tiene: un nombre largo es NotFound, no 422). `rebuild_corpus.when_absent` pasa a `{read: GET …/corpus con project y name, take: version, on_read_error: answer, retry: {on_status: 409, reread: true, only_if_value_changed: true, max: 3}}`: sin `expected_version` (ausente o `null`) se lee el corpus por nombre (ya no hay corte de 100) y se envía su versión; un 404 de la lectura es la respuesta de la llamada (el NotFound de la herramienta); si el POST da 409 porque otro rebuild cambió la versión entre la lectura y el POST, se relee y, solo si la versión cambió, se reenvía (hasta 3 veces más; la herramienta nunca da ese 409 porque solo toma el cerrojo de la fila); con la versión sin cambios el 409 es real (reconstruir quitaría más de la mitad sin `force`) y es la respuesta. (2) `x-kairos-translation` documenta `when_absent` completo (`null` cuenta como omitido), `untranslatable` y la gramática de `without_project_id` (`for_each`, cada elemento es el valor del argumento de su `args`, `result.from`, `all_of`, `{path,is}`, `{path,is_not}`, `{each,path,is}`; lista vacía cumple); el paso `jobs` lleva `args: {job_id: path}` y el test ya no hace `.replace('{job_id}', …)`. (3) `rebuild_corpus.untranslatable` declara `expected_version: 0` con la respuesta que el cliente da sin llamar: 409 `conflict` «Corpus version changed» (la herramienta con un corpus existente da exactamente ese mensaje; REST daba 422). Contratos regenerados con Python 3.13 (imagen `python:3.13-slim`, EOL CRLF preservado): `kairos-mcp.json` 34 herramientas, solo cambian claves `x-kairos-*`; OpenAPI solo añade la ruta `/corpus`. `memory_platform/app.py` y `memory_platform/agent_store.py` entran en `Archivos` de T-24. No se relajó `CorpusRebuild` ni `test_contract_additive`. usage-meter three-components/T-24-fix2: 0.36 h IA (medido, win-8bdab525, 11:26Z-11:54Z; las ventanas T-25-fix2 y T-22-fix2 abiertas a la vez dan la misma cifra y no se suman). Verificación fix2: MEMORY_TEST_RESULT {"database": "PostgreSQL", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 608} (docker build --target test, rc 0, kairos-test:i2p3fix2); puerta offline `--network=none -e MEMORY_RETRIEVAL_EVAL=1` rc 0, `RETRIEVAL_EVAL_RESULT` gate passed; CI run 43421685383 sobre 9030645, 5/5 en verde (retrieval-eval, web, server, contracts, client).

### T-25 — Prueba de correspondencia: las 34 herramientas por el MCP interno y por `/v1` (CA-06)

- **Descripción**: Escenario sembrado en PostgreSQL aislado: llamar a cada herramienta por el MCP interno y a su endpoint por `/v1` con la misma credencial y argumentos, y comparar el contenido (salvo presupuesto de bytes y campos aditivos de S-05). Recorre las 34. Fuente: CA-06.
- **Changelog**: Una prueba recorre las 34 herramientas MCP y compara su respuesta con la del endpoint `/v1` que declara el contrato, con la misma clave y los mismos argumentos; una ruta que falte o cambie de contenido la pone en rojo.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.43h (estimado) · real 0.48h (medido: 0.18h ventana win-65490a67, 15:52Z-16:02Z + 0.30h corrección fix1; la corrección fix2 va en el bloque de T-24)
- **Supervisión**: est. 0.11h (≈25 % IA) · real —
- **Previsión IA**: 120 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-24
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_tool_endpoint_parity.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t25 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build` anterior incluye `test_tool_endpoint_parity` con 34 casos → `ok`

**Criterios de aceptación**
- [x] La prueba recorre las 34 herramientas y falla si falta una
- [x] El contenido devuelto es igual salvo presupuesto de bytes y campos aditivos
- [x] Un endpoint ausente o con otra semántica hace fallar la prueba (mutación manual comprobada)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Sembrar el escenario
- [x] Escribir el recorrido parametrizado
- [x] Probar una mutación para ver el rojo
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-06. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `08c9d95a8f6f`.


RED: `memory_platform/tests/test_tool_endpoint_parity.py::ToolEndpointParityTests::test_parity_team_search` falló con mutación (ruta team-search renombrada a team-find en app.py): ERROR test_parity_team_search, la ruta declarada responde 404; con limit=1 fijo en observation_search: FAIL test_parity_observation_search · 2026-11-12.

Corrección intento 1 (gaps 1 y 3, 16539ea): el test ya no escribe la petición REST: `translate` genérico construye la petición desde los argumentos MCP y el contrato (incluye `when_absent` y la composición de `event_status`); 44 casos (todas las herramientas, más includeClosed con tarea cerrada, dateStart/dateEnd, types en cadena, rebuild sin expected_version, get_tool_uses con PostToolUse sembrado y contenido no vacío, event_status sin proyecto con recibo `superseded`, `corpus_answer_status` sobre una respuesta guardada, nombres con `/`); test estático de que cada argumento de cada herramienta tiene regla y apunta a una operación/parámetro/campo reales de OpenAPI; 6 tests de mutación (contrato por nombre → el test falla): ROJO demostrado con includeClosed, dateStart, types sin transform, project de get_tool_uses, `complete` sin la regla superseded y rebuild sin `when_absent`. usage-meter three-components/T-25-fix1: 0.30 h IA (medido, win-2d190371). Suite `kairos-test:i2p3fix`: 591 tests, 0 fallos, 0 omitidos, `llm_chat_calls` 0; puerta offline exit 0.

Corrección intento 2 (gap 1, 9030645): `perform`/`read_missing` (el cliente genérico del test) implementan `when_absent` con la lectura por nombre, el error de la lectura como respuesta, `untranslatable` y el reintento; se quita el `assert len(found)==1`. Casos nuevos (48): `rebuild_corpus_null` (`expected_version: null`), `rebuild_corpus_missing` (nombre inexistente: NotFound en ambos lados, mismo mensaje), `rebuild_corpus_zero` (409 «Corpus version changed» en ambos lados sin llamar a REST) y `rebuild_corpus_late`; test `…beyond_the_first_hundred_of_the_list` (105 corpus de relleno insertados por SQL —el presupuesto es 32—, el corpus `zz-late` queda fuera de la primera página de `list_corpora` —`truncated` true— y la paridad se cumple; los rellenos se borran en `finally`); test `…lands_between_the_read_and_the_post…` (otra reconstrucción sube la versión entre la lectura y el POST: éxito con versión 2 y mismo recibo que la herramienta; sin la regla `retry` el mismo choque es el 409); `RetryRuleTests` (6 tests sobre un servidor guionizado: reenvía con la versión cambiada, como máximo 3 veces más, el 409 con versión igual es la respuesta sin segundo POST, una carrera que se asienta es éxito, la lectura fallida no hace POST, versión dada se envía tal cual y 0 se responde sin llamada). El test de contrato exige `args` en el paso `jobs`. usage-meter: bloque de T-24-fix2. Verificación fix2: MEMORY_TEST_RESULT {"database": "PostgreSQL", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 608} (docker build --target test, rc 0, kairos-test:i2p3fix2); puerta offline `--network=none -e MEMORY_RETRIEVAL_EVAL=1` rc 0, `RETRIEVAL_EVAL_RESULT` gate passed; CI run 43421685383 sobre 9030645, 5/5 en verde (retrieval-eval, web, server, contracts, client).

### T-26 — Línea base de contratos en `23ced03` y diff aditivo de OpenAPI y MCP (CA-07, CA-29)

- **Descripción**: Guardar los contratos del commit `23ced03` como línea base de esta iniciativa y comprobar el diff aditivo de ambos contratos contra ella (la línea base anterior se conserva). Fuente: CA-07, CA-29.
- **Changelog**: La suite fija como línea base los contratos del commit `23ced03` junto a la anterior y comprueba que el OpenAPI y el contrato MCP actuales solo han crecido respecto a ambas.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real 0.92h (medido, ventana win-c0828e46, 16:03Z-16:07Z)
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 20 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-24
- **Tipo**: test
- **Archivos**: `memory_platform/tests/contracts_base_23ced03/`, `memory_platform/tests/test_contract_additive.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t26 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `git show 23ced03:docs/contracts/kairos-mcp.json | diff - memory_platform/tests/contracts_base_23ced03/kairos-mcp.json` → sin diferencias Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `fe3923146b03`.

**Criterios de aceptación**
- [x] Existe la línea base `23ced03` con ambos contratos tal como estaban en ese commit (`git show 23ced03:docs/contracts/...`)
- [x] El test de aditividad pasa contra ambas líneas base
- [x] Ninguna ruta, operación, campo, valor por defecto ni `required` eliminado o cambiado
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Extraer los contratos con `git show 23ced03:…`
- [x] Parametrizar el test
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-29 (commit de inicio `23ced03`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0588667d10d5`.


RED: `memory_platform/tests/test_contract_additive.py::ContractAdditiveTests::test_ca07_ca29_the_exported_contracts_only_gain_against_every_baseline_and_keep_every_tool_exact_against_the_latest` falló con AssertionError: Items in the second set but not the first (sin el directorio contracts_base_23ced03 la línea base no existe: el test falla antes de añadirla) · 2026-11-12.

### T-27 — Revisión adversarial de la Fase 3

- **Descripción**: Revisión adversarial: permisos de cada endpoint nuevo (lector, proyecto ajeno, clave sin permiso), fuga de datos entre proyectos, ruta nueva que pise una existente, diff aditivo trampa (campo `required` camuflado) y semántica distinta entre herramienta y endpoint. Fuente: retro, R-06.
- **Changelog**: La paridad REST /v1 se revisó de forma adversarial en tres intentos (conformidad, defectos, permisos y el nginx del portal) sin hallazgos Critical ni Important abiertos.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 10.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.37h (estimado) · real —
- **Supervisión**: est. 0.34h (≈25 % IA) · real —
- **Previsión IA**: 378 k in / 34 k out tok · ⚠️ verificar €
- **Dependencias**: T-18 … T-26
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t27 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · lectura: `review.md`, sección «Fase 3», sin hallazgos Critical/Important abiertos · Evidencia (2026-11-13): `review.md` sección «Fase 3»; 3 intentos (A, B+D y C forzada; A y B; A+B y C). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `96c08cc3699b`.

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 3»
- [x] 0 hallazgos Critical o Important abiertos
- [x] Suite completa y diff aditivo en verde
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: los intentos de revisión no se midieron con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado)

**Subtareas**
- [x] Probar cada endpoint con las tres credenciales de prueba
- [x] Comparar rutas antes y después de la fase
- [x] Cerrar hallazgos
- [x] `usage-meter start/close` por intento — EXCEPCIÓN: ver el criterio anterior

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 4 — Esquema de observación (C-05)

**Estado**: completado · **Estimado**: 37.8h (31.5h base) · **Real**: — · **Coste est.**: 1.890 € · **Tokens est.**: 1193 k

### T-28 — Esquemas JSON `observation.v1` y `session-summary.v1`

- **Descripción**: Diseñar los dos esquemas (JSON Schema 2020-12) con `schema_version`. Observación: tipo, título, hechos con cita literal, narrativa, conceptos, ficheros leídos y modificados. Resumen: petición, investigado, aprendido, hecho y siguiente. Fijar límites de longitud y `additionalProperties: false`. Fuente: CA-19, R-04.
- **Changelog**: Se publican los esquemas JSON observation.v1 y session-summary.v1, con sus campos y límites de longitud, para estructurar observaciones y resúmenes de sesión.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.48h (estimado) · real 0.54h (medido, ventana win-42c5948835094fc69f44558c748aa232, bloque T-28..T-34; JSON del cierre: `usage-meter close three-components/T-28`)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 133 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-27
- **Tipo**: contratos
- **Archivos**: `docs/contracts/observation.v1.schema.json`, `docs/contracts/session-summary.v1.schema.json`
- **Cubre (tests)**: —
- **Verificación**: `python -c "import json;[json.load(open(f,encoding='utf-8')) for f in ('docs/contracts/observation.v1.schema.json','docs/contracts/session-summary.v1.schema.json')]"` → exit 0 · lectura: los campos coinciden con CA-19 · Evidencia (2026-11-13): `python -c "import json;[json.load(open(f,encoding='utf-8')) for f in (...)]"` exit 0; `Draft202012Validator.check_schema` acepta ambos; lectura:… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2e13f308a3fc`.

**Criterios de aceptación**
- [x] Ambos ficheros son JSON válido, declaran `$schema` 2020-12 y `schema_version`
- [x] La observación declara los siete campos pedidos y el resumen los cinco
- [x] Cada campo de texto tiene límite de longitud
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Redactar los esquemas desde el plan director (Iniciativa 6) y el modelo de observación
- [x] Validar que son JSON Schema válidos con el validador independiente de T-29
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-19, plan director §Iniciativa 2 y 6. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e8aab00a743b`.

### T-29 — Ejemplos válidos e inválidos y validador independiente (CA-21)

- **Descripción**: Versionar ejemplos válidos e inválidos junto a los esquemas y validarlos con un validador independiente del servidor (un test en `scripts/tests` que no importa `memory_platform`). Fuente: CA-21.
- **Changelog**: Cada esquema incluye ejemplos válidos e inválidos que se comprueban con un validador independiente del servidor.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real incluida en la ventana win-42c5948835094fc69f44558c748aa232 de T-28 (bloque T-28..T-34, medido; solape, no sumar)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-28
- **Tipo**: test
- **Archivos**: `docs/contracts/examples/observation.v1/`, `docs/contracts/examples/session-summary.v1/`, `scripts/tests/test_contract_examples.py`
- **Cubre (tests)**: —
- **Verificación**: `python -m unittest discover -s scripts/tests -p test_contract_examples.py` → `OK` · `grep -n "memory_platform" scripts/tests/test_contract_examples.py` → sin salida · Evidencia (2026-11-13): `python -m unittest discover -s scripts/tests -p test_contract_examples.py` → `Ran 4 tests ... Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `832b15e186d2`.

**Criterios de aceptación**
- [x] Cada esquema tiene ≥ 3 ejemplos válidos y ≥ 5 inválidos (campo faltante, campo sobrante, límite excedido, tipo erróneo, versión desconocida)
- [x] El validador independiente acepta los válidos y rechaza los inválidos
- [x] El test no importa `memory_platform`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Escribir los ejemplos (rojo: aún no hay validador)
- [x] Escribir el test con el validador independiente
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-21. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e808466fb3d3`.

RED: `scripts/tests/test_contract_examples.py` (3 de 4 tests) falló con `FileNotFoundError: ... docs/contracts/observation.v1.schema.json` (esquemas apartados temporalmente, el validador no tenía contra qué comprobar) · 2026-11-13.

### T-30 — Dependencia fijada y módulo de validación de esquemas en el servidor

- **Descripción**: Añadir un validador JSON Schema con versión exacta a `requirements.txt` y un módulo que carga los esquemas de `docs/contracts/` y devuelve el primer error con su ruta JSON, sin eco del contenido. Fuente: CA-20, CA-21; riesgo de superficie de dependencias (B-19).
- **Changelog**: El servidor incluye un módulo que valida documentos contra los esquemas y devuelve la ruta JSON del primer error sin reproducir el contenido.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real incluida en la ventana win-42c5948835094fc69f44558c748aa232 de T-28 (bloque T-28..T-34, medido; solape, no sumar)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-29
- **Tipo**: backend
- **Archivos**: `memory_platform/requirements.txt`, `memory_platform/schemas.py`, `memory_platform/tests/test_observation_schema.py`, `memory_platform/Dockerfile`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t30 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · Evidencia (2026-11-13): Build del estado de T-30 (dffb667 sin los cambios de T-31): `MEMORY_TEST_RESULT` tests 613, failures 0, errors 0, skipped 0, `"passed": true`, `llm_chat_calls` 0; `pip… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `a99f5265e81b`.

**Criterios de aceptación**
- [x] La dependencia nueva está fijada con versión exacta
- [x] El módulo valida los ejemplos de T-29 con el mismo resultado que el validador independiente
- [x] El error devuelto contiene la ruta JSON y no contiene valores del contenido
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo con los ejemplos
- [x] Añadir dependencia y módulo
- [x] Reconstruir la imagen de test y comprobar la suite
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-20/CA-21, evaluación C-05. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `68231bbef4a8`.

RED: `memory_platform/tests/test_observation_schema.py` falló con `ImportError: cannot import name 'schemas' from 'memory_platform'` (el módulo no existía) · 2026-11-13.

### T-31 — Validación en `POST /v1/observations` y `observation_record_event` con `invalid_observation`

- **Descripción**: Cuando el evento declara `schema_version`, validarlo contra el esquema: 202 si valida y 422 `invalid_observation` (con la ruta del error y sin eco del contenido) si falta un campo, sobra uno o excede un límite. Sin `schema_version`, todo sigue igual (P-11). Fuente: CA-20, P-11 (decidida).
- **Changelog**: POST /v1/observations y observation_add validan payload.structured contra su esquema: 422 invalid_observation con la ruta del error; un evento sin structured se acepta como siempre.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.48h (estimado) · real incluida en la ventana win-42c5948835094fc69f44558c748aa232 de T-28 (bloque T-28..T-34, medido; solape, no sumar)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 133 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-30
- **Tipo**: backend
- **Archivos**: `memory_platform/extended_store.py`, `memory_platform/store_ingest.py`, `memory_platform/providers.py`, `memory_platform/tests/test_providers.py`, `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_extended_gateway.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_contract_additive.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t31 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · Evidencia (2026-11-13): Suite `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p4 .` (rama feat/three-components tras bf3e5b8): `MEMORY_TEST_RESULT` tests 630,… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `909fa535e26f`.

**Criterios de aceptación**
- [x] Una observación `observation.v1` válida da 202; una inválida (falta campo, campo sobrante, límite excedido) da 422 `invalid_observation` con la ruta JSON y sin el contenido
- [x] Un evento sin `schema_version` se acepta como hoy (test de no regresión)
- [x] Una `schema_version` desconocida da 422 `invalid_observation`
- [x] Los ejemplos de T-29 dan el mismo resultado en el servidor y en el validador independiente
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo (válido, inválido, sin versión, versión desconocida)
- [x] Integrar la validación en la ingesta de observaciones
- [x] Mapear el error a 422 con el formato `{error:{code,message}}`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-20/P-11. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `36c26e57519d`.

RED: `memory_platform/tests/test_extended_gateway.py::ValidatedEventTests` (2 tests) falló con `AttributeError: 'Payload' object has no attribute 'structured'` (cambios de `models.py`/`extended_store.py` revertidos) · 2026-11-13.

### T-32 — Decisión de migración aditiva para conceptos y ficheros (CA-22)

- **Descripción**: Comprobar si el `payload` jsonb basta para filtrar por conceptos y ficheros. Si basta, cerrar la tarea sin migración con la medida como evidencia; si hace falta un índice, escribir una migración solo aditiva. Fuente: CA-22, CA-30; hipótesis de la spec.
- **Changelog**: Filtrar observaciones por concepto o fichero no requiere migración: el payload jsonb basta a la escala medida y no se añade ningún índice.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real incluida en la ventana win-42c5948835094fc69f44558c748aa232 de T-28 (bloque T-28..T-34, medido; solape, no sumar)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/tests/test_migrations_additive.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t32 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `grep -niE "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → sin coincidencias nuevas respecto de `23ced03` (`git diff 23ced03 -- memory_platform/schema.sql`) · Evidencia… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `5ce547dc9f84`.

**Criterios de aceptación**
- [x] La decisión (con medida de plan de consulta sobre datos sintéticos) queda en `Notas`
- [x] Si hay migración, `test_migrations_additive.py` pasa y `content_manifest().sha256` es igual antes y después
- [x] Ninguna migración contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Medir una consulta por concepto y por fichero sobre datos sintéticos
- [x] Decidir; si procede, escribir la migración aditiva con su test
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-22, hipótesis del `payload` jsonb (`memory_platform/schema.sql:13`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `5b49a1881120`.

### T-33 — Tests de límites del esquema y de la ruta sin `schema_version`

- **Descripción**: Completar los tests de CA-20: cada límite de longitud, `additionalProperties`, tipos, sin eco del contenido en el 422 y compatibilidad con el payload que envía el CLI 0.3.0. Fuente: CA-20, P-11.
- **Changelog**: Los límites del esquema, la ausencia de eco del contenido en el 422 y el payload del CLI 0.3.0 sin schema_version quedan cubiertos por tests.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.24h (estimado) · real incluida en la ventana win-42c5948835094fc69f44558c748aa232 de T-28 (bloque T-28..T-34, medido; solape, no sumar)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 67 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_observation_schema.py`, `memory_platform/tests/test_extended_gateway.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t33 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · Evidencia (2026-11-13): Suite `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p4 .` (rama feat/three-components tras bf3e5b8): `MEMORY_TEST_RESULT` tests 630,… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e8cf75844bae`.

**Criterios de aceptación**
- [x] Hay un caso por cada límite y por cada tipo de error
- [x] El cuerpo del 422 no contiene ningún valor del contenido enviado (prueba con un valor centinela)
- [x] El payload real del CLI 0.3.0 (sin `schema_version`) se acepta
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Escribir los casos
- [x] Tomar el payload del CLI desde `packages/kairos-cli/lib/capture.mjs`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-20. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `609dd91a4be8`.

RED: los casos de límites son cobertura de una capacidad ya implementada en T-30/T-31, con el esquema como oráculo; la primera ejecución en la imagen falló en 5 puntos que corrigieron los tests (ejemplo equivocado como base, huella de captura inválida, mensaje MCP sin código, contrato exacto de herramientas y 413 en lugar de 422) · 2026-11-13.

### T-34 — Documentar el esquema de observación

- **Descripción**: Documentar los esquemas, el uso de `schema_version`, el error `invalid_observation` y cómo validar un ejemplo en local. Fuente: CA-32, C-05.
- **Changelog**: La documentación describe los esquemas observation.v1 y session-summary.v1, el error invalid_observation y cómo validar un ejemplo en local.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.24h (estimado) · real incluida en la ventana win-42c5948835094fc69f44558c748aa232 de T-28 (bloque T-28..T-34, medido; solape, no sumar)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 67 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-33
- **Tipo**: docs
- **Archivos**: `docs/integration.md`, `docs/extended-workflows.md`, `docs/contracts/README.md`
- **Cubre (tests)**: —
- **Verificación**: `grep -n "observation.v1" docs/integration.md` → ≥ 1 coincidencia · lectura: los límites citados coinciden con los esquemas · Evidencia (2026-11-13): `grep -n "observation.v1" docs/integration.md` → coincidencias en las líneas 161, 164 y 168 (sección «Observaciones estructuradas con esquema versionado»); lectura: los límites citados (200, 20 000, 20×500/2 000, 20×100, 50×500, 5×4 000) coinciden… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `9a47d4bd4c81`.

**Criterios de aceptación**
- [x] La doc cita ambos esquemas y su ruta real
- [x] Explica que sin `schema_version` no se valida (P-11)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Redactar según `docs-style.md`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `8a07c40c9590`.

### T-35 — Revisión adversarial de la Fase 4

- **Descripción**: Revisión adversarial: ¿un esquema permite inyectar contenido sin límite? ¿el 422 filtra contenido? ¿la dependencia nueva amplía la superficie? ¿la migración (si existe) es de verdad aditiva? Fuente: retro, R-04, R-06.
- **Changelog**: El esquema de observación se revisó de forma adversarial en dos intentos: se cerró un bloqueo de CPU con listas largas en `structured` y la validación cubre ahora todas las rutas de ingesta, también `remember` y `POST /v1/events`.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 10.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.44h (estimado) · real —
- **Supervisión**: est. 0.36h (≈25 % IA) · real —
- **Previsión IA**: 397 k in / 35 k out tok · ⚠️ verificar €
- **Dependencias**: T-28 … T-34
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t35 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · lectura: `review.md`, sección «Fase 4», sin hallazgos Critical/Important abiertos · Evidencia (2026-11-13): `review.md` sección «Fase 4»; 2 intentos (A+B y C; A+B+C forzada). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `f3d9e9f4bbd9`.

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 4»
- [x] 0 hallazgos Critical o Important abiertos
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: los intentos de revisión no se midieron con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado)

**Subtareas**
- [x] Probar payloads hostiles (profundidad, tamaño, Unicode)
- [x] Cerrar hallazgos
- [x] `usage-meter start/close` por intento — EXCEPCIÓN: ver el criterio anterior

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 5 — kairos-mcp (C-03)

**Estado**: completado · **Estimado**: 68.4h (57.0h base) · **Real**: — · **Coste est.**: 3.420 € · **Tokens est.**: 2532 k

### T-36 — Andamiaje del paquete `mcp/` (`kairos_mcp`), Dockerfile sin base de datos y `health`

- **Descripción**: Crear el paquete `mcp/` con servidor ASGI, `GET /health/live`, versión 0.4.0 (P-07), `requirements.txt` sin `psycopg` y Dockerfile propio con usuario sin privilegios; añadir el trabajo `mcp` a la CI. Fuente: CA-08, CA-24 (parte), spec §Arquitectura.
- **Changelog**: Hay un componente nuevo, kairos-mcp (0.4.0), con su propia imagen sin base de datos ni secretos y un sondeo de vida en /health/live; la CI lo construye y prueba.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.46h (estimado) · real 0.25h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 126 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/__init__.py`, `mcp/kairos_mcp/app.py`, `mcp/requirements.txt`, `mcp/Dockerfile`, `mcp/VERSION`, `mcp/tests/test_health.py`, `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `mcp/.dockerignore`, `mcp/contract/.keep`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/` → exit 0 · `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/ && docker run --rm kairos-mcp:t36 python -m unittest discover -s tests` → `OK` · `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/ && docker run --rm kairos-mcp:t36 pip list` no contiene `psycopg` · Evidencia (2026-11-13): build `kairos-mcp:t36` exit 0; `docker run --rm… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2c1b9fd3eb3c`.

**Criterios de aceptación**
- [x] `mcp/` no instala `psycopg` ni lleva variables `MEMORY_DSN*` ni secretos
- [x] `GET /health/live` responde 200 en el test
- [x] El trabajo `mcp` existe en el workflow y el test estructural lo comprueba
- [x] La imagen se construye con `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test de `health` en rojo
- [x] Crear paquete, requisitos y Dockerfile
- [x] Añadir el trabajo `mcp` a la CI y al test estructural
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-08/CA-09. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `075074c5b78e`.

RED: `mcp/tests/test_health.py` falló con 4 errores: ModuleNotFoundError kairos_mcp.app y FileNotFoundError mcp/Dockerfile y mcp/VERSION · 2026-11-13.

### T-37 — Cliente HTTP hacia `/v1`: credencial, errores, plazos y registro sin secretos

- **Descripción**: Cliente `httpx` con conexión persistente: reenvía `Authorization: Bearer` tal cual, traduce `{error:{code,message}}` a `ValueError(message)`, devuelve `Memory service temporarily unavailable` ante 5xx, plazo o caída, aplica `KAIROS_API_TIMEOUT` (30 s) y nunca guarda ni registra la credencial. Sin cabecera o con esquema distinto de `Bearer`, 401 sin llamar a `/v1`. Fuente: CA-12, P-08 (decidida), R-05.
- **Changelog**: kairos-mcp reenvía la credencial Bearer de quien llama a /v1, traduce sus errores al mismo mensaje que el MCP interno, responde Memory service temporarily unavailable ante caídas, plazos y 5xx, y no deja la credencial en los logs.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 5.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.77h (estimado) · real 0.15h (medido)
- **Supervisión**: est. 0.19h (≈25 % IA) · real —
- **Previsión IA**: 211 k in / 20 k out tok · ⚠️ verificar €
- **Dependencias**: T-36
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/client.py`, `mcp/kairos_mcp/errors.py`, `mcp/tests/test_client.py`, `mcp/tests/stub_api.py`, `mcp/kairos_mcp/auth.py`, `mcp/kairos_mcp/config.py`, `mcp/kairos_mcp/logs.py`
- **Cubre (tests)**: —
- **Verificación**: `docker run --rm kairos-mcp:t37 python -m unittest discover -s tests` → `OK` (tras `docker build -f mcp/Dockerfile -t kairos-mcp:t37 mcp/`) · Evidencia (2026-11-13): `docker build -f mcp/Dockerfile -t kairos-mcp:t37 mcp/` y `docker run --rm kairos-mcp:t37 python -m unittest discover -s tests` -> Ran 24 tests, OK (el token sintetico aparece 0 veces en los logs con todos los loggers en DEBUG). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `83710f02e551`.

**Criterios de aceptación**
- [x] 4xx con `{error:{code,message}}` falla con `message` igual que el MCP interno
- [x] 5xx, plazo agotado y caída dan `Memory service temporarily unavailable`
- [x] Sin `Authorization` o con esquema distinto de `Bearer`: 401 con el cuerpo de hoy y 0 llamadas a `/v1`
- [x] El token sintético aparece 0 veces en los logs durante los tests
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Escribir `stub_api.py` (servidor `/v1` simulado) y los tests en rojo
- [x] Implementar el cliente
- [x] Test que busca el token sintético en los logs capturados
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-12/P-08. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `045ea546aa0c`.


RED: `mcp/tests/test_client.py` falló con 17 errores: ModuleNotFoundError kairos_mcp.client y kairos_mcp.auth · 2026-11-13.

### T-38 — Servidor MCP con `tools/list` generado desde `kairos-mcp.json` (P-05, CA-10)

- **Descripción**: Montar el servidor MCP de bajo nivel que sirve las 34 herramientas desde el contrato (nombre, descripción, `inputSchema`, anotaciones, orden) en `streamable-http` `/mcp/`. Comprobar primero la hipótesis de que `mcp==1.27.1` permite `inputSchema` arbitrario; si no, escalar al usuario antes de pasar a copiar modelos (alternativa de la spec). Fuente: CA-10, P-05, R-01.
- **Changelog**: kairos-mcp sirve por streamable-http en /mcp/ las mismas 34 herramientas del contrato, con los mismos nombres, descripciones, esquemas de entrada y anotaciones que el MCP interno.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.46h (estimado) · real 0.10h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 126 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-37
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/contract.py`, `mcp/contract/kairos-mcp.json`, `mcp/tests/test_tools_list.py`, `mcp/kairos_mcp/app.py`, `mcp/kairos_mcp/budget.py`, `mcp/kairos_mcp/translate.py`, `mcp/tests/test_client.py`, `memory_platform/tests/test_mcp_contract_copy.py`, `memory_platform/Dockerfile`, `mcp/contract/.keep`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t38 mcp/ && docker run --rm kairos-mcp:t38 python -m unittest discover -s tests` → `OK`, incluido `test_tools_list` · Evidencia (2026-11-13): `docker build -f mcp/Dockerfile -t kairos-mcp:t38 mcp/ && docker run --rm kairos-mcp:t38 python -m unittest discover -s tests` -> Ran 35 tests, OK (incluye test_tools_list con SDK mcp 1.27.1);… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `8335b0c1ac02`.

**Criterios de aceptación**
- [x] `tools/list` devuelve las 34 herramientas en el mismo orden y con los mismos `name`, `description`, `inputSchema` y `annotations` que `docs/contracts/kairos-mcp.json`, con la regla de `test_contract_additive.py`
- [x] La copia `mcp/contract/kairos-mcp.json` es idéntica a `docs/contracts/kairos-mcp.json` (test de igualdad)
- [x] Si el SDK no lo permite, la tarea queda bloqueada con la evidencia y se pide decisión
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Spike del SDK de bajo nivel y anotar el resultado
- [x] Test en rojo de `tools/list`
- [x] Implementar el registro desde el contrato
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/P-05/R-01, hipótesis del SDK (spec §Supuestos). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `23793acc0a99`.


RED: `mcp/tests/test_tools_list.py` falló con fallos y errores: create_app sin /mcp/ ni allowed_origins (setUpClass: initialize no devuelve result) · 2026-11-13.

### T-39 — Arranque real del contenedor `kairos-mcp` contra un servidor aislado (verificación temprana)

- **Descripción**: Verificación temprana con un componente real (lección de la retro): arrancar el contenedor `kairos-mcp` con solo `KAIROS_API_URL` contra el servidor `/v1` simulado en un proyecto Compose aislado `kairos-mcp-smoke`, sin variables `MEMORY_DSN*`, sin secretos y sin la red `memory-data`; pedir `GET /health/live` y `tools/list` reales. Fuente: CA-09, retro.
- **Changelog**: El contenedor kairos-mcp arranca solo con KAIROS_API_URL (sin base de datos, sin secretos) y responde /health/live y la lista de 34 herramientas; hay un humo reproducible en un proyecto Compose aislado.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.46h (estimado) · real 0.04h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 126 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-38
- **Tipo**: mcp
- **Archivos**: `mcp/tests/smoke_container.py`, `mcp/tests/compose.smoke.yml`
- **Cubre (tests)**: —
- **Verificación**: `python mcp/tests/smoke_container.py` → `PASS health 200; tools 34` y exit 0 · `docker ps -a -q --filter name=knowledge-graphs-` antes y después → idéntico (no se toca la instalación) · Evidencia (2026-11-13): `KAIROS_SMOKE_PROJECT=kairos-i2p5-mcp-smoke python mcp/tests/smoke_container.py` -> `PASS health 200; tools 34`, rc 0; `docker ps -a -q --filter name=knowledge-graphs-` antes y despues… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `016360d547b3`.

**Criterios de aceptación**
- [x] El contenedor arranca solo con `KAIROS_API_URL` y `GET /health/live` responde 200
- [x] `tools/list` por HTTP devuelve las 34 herramientas
- [x] El proyecto aislado usa solo recursos `kairos-mcp-smoke_*` y se elimina al terminar
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Escribir el fichero Compose aislado (red y volúmenes con nombre de proyecto)
- [x] Escribir el script de humo
- [x] Ejecutar y limpiar el proyecto
- [x] `usage-meter start/close`

**Notas**: Procedencia: retro (verificación con componente real pronto), CA-09. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `851398dd03ab`.


RED: `mcp/tests/smoke_container.py` falló con salio con 1: `missing ...compose.smoke.yml` (sin el proyecto Compose el humo falla) · 2026-11-13.

### T-40 — Servicio Compose `memory-mcp` en red propia, sin `memory-data` ni secretos (CA-09)

- **Descripción**: Añadir el servicio `memory-mcp` (imagen `kairos-mcp`) a una red nueva compartida solo con `memory-api`, sin `memory-data`, `inference`, `secrets` ni DSN; hacer que `deploy-memory.py` y el diagnóstico conozcan el servicio nuevo para el ensayo de T-72. Fuente: CA-09, spec §Arquitectura (Compose).
- **Changelog**: El stack Compose incluye el servicio memory-mcp, en una red interna que solo comparte con memory-api (sin base de datos, sin secretos), y el despliegue y el diagnostico lo conocen.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real 0.53h (medido)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 84 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `scripts/deploy-memory.py`, `scripts/diagnose-deployment.py`, `memory_platform/tests/test_deploy.py`, `memory_platform/Dockerfile`, `memory_platform/tests/ollama_proxy_probe.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t40 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `docker compose -p kairos-cfg-t40 config --format json` → `services.memory-mcp` sin `secrets` ni `memory-data` en `networks` · Evidencia (2026-11-13): build `--target test`… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `1de1473802c1`.

**Criterios de aceptación**
- [x] `docker compose -p kairos-cfg-t40 config` muestra `memory-mcp` sin `secrets` ni la red `memory-data`
- [x] `deploy-memory.py --dry-run` incluye el servicio nuevo
- [x] Los tests de despliegue existentes pasan
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo sobre el `config` renderizado
- [x] Añadir servicio, red y variables
- [x] Actualizar el script de despliegue y el diagnóstico
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-09. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `76be16b40ae0`.


RED: `memory_platform/tests/test_deploy.py::McpServiceTests` falló con KeyError: 'memory-mcp' en setUpClass (el compose no tenia el servicio) · 2026-11-13.

### T-41 — Herramientas del grupo `mcp.py` (12) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp las 12 herramientas de `mcp.py` y su traducción a `/v1`. Fuente: CA-10, CA-11, spec §Arquitectura (tabla de paridad).
- **Changelog**: kairos-mcp atiende ya las 12 herramientas basicas (proyectos, remember, documentos, busqueda, contexto, estado de eventos y politica de captura) traduciendolas a /v1 con la credencial de quien llama.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 84 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t41.py`, `mcp/kairos_mcp/translate.py`, `mcp/tests/support.py`, `mcp/tests/tool_cases.py`, `mcp/tests/test_review1.py`, `mcp/tests/test_review2.py` (nota: añadido en el fix2 del intento 2, el test de la validación acotada), `mcp/tests/test_review3.py` (nota: añadido en el fix3 del ciclo nuevo tras el intento 3, la regresión de cada array del contrato), `mcp/tests/test_review4.py` (nota: añadido en el fix4 del ciclo 2 tras el intento 4, la regresión del latido del event loop con la validación en un hilo), `mcp/tests/test_review5.py` (nota: añadido en el fix5 del ciclo 2 tras el intento 5, la regresión de la latencia de una llamada pequeña con validaciones grandes en curso y del plazo de la cola)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t41 mcp/ && docker run --rm kairos-mcp:t41 python -m unittest discover -s tests` → `OK`, 12 herramientas probadas · Evidencia (2026-11-13): `docker build -f mcp/Dockerfile -t kairos-mcp:t41 mcp/ && docker run --rm kairos-mcp:t41 python -m unittest discover -s tests` -> Ran 46 tests, OK (12 herramientas: exito, 4xx, 5xx y caida cada una; event_status… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ebb541a56e22`.

**Criterios de aceptación**
- [x] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [x] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [x] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [x] Las herramientas de este grupo: `projects`, `remember`, `publish_document`, `document_status`, `document_manifest`, `revoke_document`, `search`, `details`, `context`, `timeline`, `event_status`, `capture_policy`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo contra `stub_api.py`
- [x] Implementar la traducción herramienta → llamada
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/CA-11. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `d44de46b9da8`.


RED (fix1, intento 1 de la Fase 5): `mcp/tests/test_review1.py` falló con 18 fallos y 1 error (esquema recompilado por petición, UUID sin guiones/llaves/`urn:` sin normalizar, respuesta de 9 MiB → UNAVAILABLE, `..` sin codificar, `initialize` y `tools/list` sin comprobar la credencial, `trust_env`, enteros `20.0`, `query_corpus` sin envoltorio, un 200 con lista como éxito) · 2026-11-14. Sin rojo previo observado en `memory_platform/tests/test_chain_review1.py` (se escribió con la corrección y compara ambos MCP; el rojo de esos casos es el de `test_review1.py`) y en los tests de paridad: su primer verde fue sobre el diseño ya corregido.

RED: `mcp/tests/test_tools_t41.py` falló con 52 fallos y 5 errores: las herramientas respondian `This tool is not available in this build of kairos-mcp` (tabla OUTPUT vacia) · 2026-11-13.

### T-42 — Herramientas del grupo `agent_tools.py` (13) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp las 13 herramientas de `agent_tools.py`, incluida `important_workflow` como `local`, y los presupuestos de salida. Fuente: CA-10, CA-11.
- **Changelog**: kairos-mcp atiende ya las 13 herramientas de agente (listas de trabajo, corpus y observaciones, con important_workflow local) con los mismos topes de bytes que el MCP interno; rebuild_corpus da el mismo error que la herramienta montada en los casos limite.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real 0.25h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 105 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-41
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t42.py`, `scripts/export-contracts.py`, `docs/contracts/kairos-mcp.json`, `mcp/contract/kairos-mcp.json`, `memory_platform/agent_store.py`, `memory_platform/tests/test_tool_endpoint_parity.py`, `mcp/tests/tool_cases.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t42 mcp/ && docker run --rm kairos-mcp:t42 python -m unittest discover -s tests` → `OK`, 13 herramientas probadas · Evidencia (2026-11-13): mcp: `docker build -f mcp/Dockerfile -t kairos-mcp:t42 mcp/ && docker run --rm kairos-mcp:t42 python -m unittest discover -s tests` -> Ran 64 tests, OK. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6eba8a746254`.

**Criterios de aceptación**
- [x] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [x] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [x] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [x] Las herramientas de este grupo: `work_state_write`, `work_state_read`, `list_corpora`, `build_corpus`, `rebuild_corpus`, `prime_corpus`, `reprime_corpus`, `query_corpus`, `get_observations`, `observation_search`, `observation_context`, `observation_generation_status`, `important_workflow` (local)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo contra `stub_api.py`
- [x] Implementar la traducción herramienta → llamada
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/CA-11. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `81f21c0beb0a`.


RED: `mcp/tests/test_tools_t42.py` falló con 13 herramientas respondian `This tool is not available in this build of kairos-mcp` (fallos de exito/4xx/5xx/caida, presupuestos y rebuild_corpus) · 2026-11-13.

### T-43 — Herramientas del grupo `extended_tools.py` (7) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp las 7 herramientas de `extended_tools.py`. Fuente: CA-10, CA-11.
- **Changelog**: kairos-mcp atiende ya las 7 herramientas de observaciones y trabajo de equipo (observation_add, observation_record_event, get_tool_uses y team_*), con el tope de 256 KiB del MCP interno.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.23h (estimado) · real 0.01h (medido)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 63 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-42
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t43.py`, `mcp/tests/support.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t43 mcp/ && docker run --rm kairos-mcp:t43 python -m unittest discover -s tests` → `OK`, 7 herramientas probadas · Evidencia (2026-11-13): `docker build -f mcp/Dockerfile -t kairos-mcp:t44 mcp/ && docker run --rm kairos-mcp:t44 python -m unittest discover -s tests` -> Ran 77 tests, OK (7 herramientas: exito, 4xx, 5xx y caida; presupuesto DETAIL de… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `45e915477581`.

**Criterios de aceptación**
- [x] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [x] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [x] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [x] Las herramientas de este grupo: `observation_add`, `observation_record_event`, `get_tool_uses`, `team_work_write`, `team_work_read`, `team_brief`, `team_search`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo contra `stub_api.py`
- [x] Implementar la traducción herramienta → llamada
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/CA-11. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `b7ff2ef7039d`.


RED: `mcp/tests/test_tools_t43.py` falló con 33 fallos y 1 error: las 7 herramientas respondian `This tool is not available in this build of kairos-mcp` · 2026-11-13.

### T-44 — Herramientas del grupo `corpus_answer_tools.py` (2) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp `corpus_answer` y `corpus_answer_status`, incluido el error `corpus_answer_disabled` que llega del servidor. Con esto quedan las 34. Fuente: CA-10, CA-11, P-04.
- **Changelog**: kairos-mcp sirve ya las 34 herramientas, incluidas corpus_answer y corpus_answer_status, y con corpus_answer apagado el cliente recibe el mismo error corpus_answer_disabled que con el MCP interno.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.15h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.04h (≈25 % IA) · real —
- **Previsión IA**: 42 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-43
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t44.py`, `mcp/tests/support.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t44 mcp/ && docker run --rm kairos-mcp:t44 python -m unittest discover -s tests` → `OK`, 2 herramientas probadas y recuento total de 34 · Evidencia (2026-11-13): `docker build -f mcp/Dockerfile -t kairos-mcp:t44 mcp/ && docker run --rm kairos-mcp:t44 python -m unittest discover -s tests` -> Ran 77 tests, OK, incluido el recuento total: la tabla de… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `7cc1dbc9dfb3`.

**Criterios de aceptación**
- [x] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [x] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [x] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [x] Las herramientas de este grupo: `corpus_answer`, `corpus_answer_status`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo contra `stub_api.py`
- [x] Implementar la traducción herramienta → llamada
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/P-04. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e96eb1d1902b`.


RED: `mcp/tests/test_tools_t44.py` falló con 11 fallos y 1 error: las 2 herramientas respondian `This tool is not available in this build of kairos-mcp` y OUTPUT no cubria los 34 · 2026-11-13.

### T-45 — Envoltorio de dato no fiable (S-05) en las herramientas de lectura de kairos-mcp

- **Descripción**: Añadir `untrusted: true` y `warning` como campos aditivos al objeto JSON de respuesta de todas las herramientas con `readOnlyHint=True`, sin delimitar ni alterar el texto existente. Fuente: CA-13, P-02 (decidida), S-05, R-02.
- **Changelog**: Las herramientas de lectura de kairos-mcp devuelven ahora dos campos nuevos, untrusted: true y warning, para que el agente trate lo recuperado como dato y no como instrucciones; los campos existentes no cambian.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 105 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-44
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/untrusted.py`, `mcp/kairos_mcp/tools.py`, `mcp/tests/test_untrusted.py`, `mcp/kairos_mcp/translate.py`, `mcp/tests/test_tools_t42.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f mcp/Dockerfile -t kairos-mcp:t45 mcp/ && docker run --rm kairos-mcp:t45 python -m unittest discover -s tests` → `OK`, incluido `test_untrusted` · `cd packages/kairos-cli && npm test` → pasa sin cambios (`dispatcher.test.mjs`, `mcp.test.mjs`) · Evidencia (2026-11-13): `docker build -f mcp/Dockerfile -t kairos-mcp:t45 mcp/ && docker run --rm kairos-mcp:t45 python -m unittest… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `5c44e2e28f18`.

**Criterios de aceptación**
- [x] Todas las herramientas de lectura devuelven `untrusted` y `warning`; los campos existentes no cambian
- [x] Las herramientas de escritura no los añaden
- [x] El texto de la herramienta sigue siendo JSON parseable (`JSON.parse` del CLI)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo parametrizado por `readOnlyHint`
- [x] Implementar el envoltorio
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-13/P-02/R-02. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c9704d4074b8`.


RED: `mcp/tests/test_untrusted.py` falló con 1 fallo y 25 errores: las respuestas de lectura no traian `untrusted` ni `warning` (KeyError) · 2026-11-13.

### T-46 — Envoltorio S-05 en el MCP interno (lecturas) con el CLI 0.3.0 intacto

- **Descripción**: Aplicar el mismo envoltorio aditivo a las herramientas de lectura del MCP interno, con una sola función compartida por las cuatro tablas de herramientas. Fuente: CA-13, S-05, P-02.
- **Changelog**: El MCP interno añade tambien untrusted: true y warning a todas sus herramientas de lectura, igual que kairos-mcp, sin cambiar ningun campo existente ni el contrato de las 34 herramientas.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real 0.66h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 105 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-45
- **Tipo**: backend
- **Archivos**: `memory_platform/mcp.py`, `memory_platform/agent_tools.py`, `memory_platform/extended_tools.py`, `memory_platform/corpus_answer_tools.py`, `memory_platform/tests/test_untrusted_internal.py`, `docs/contracts/kairos-mcp.json`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_mcp_write.py`, `memory_platform/tests/test_tool_endpoint_parity.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t46 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `cd packages/kairos-cli && npm test` → pasa sin cambios · Evidencia (2026-11-13): `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p5 .` (con T-46, T-47 y T-48… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `088a6c5aed71`.

**Criterios de aceptación**
- [x] Las herramientas de lectura del MCP interno devuelven `untrusted` y `warning`; el resto de campos no cambia
- [x] `test_mcp.py`, `test_agent_tools.py` y `test_extended_tools.py` pasan (ajustados solo donde comparan el objeto completo)
- [x] El contrato `kairos-mcp.json` regenerado solo tiene adiciones
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo parametrizado
- [x] Aplicar el envoltorio de forma centralizada
- [x] Regenerar contratos y comprobar el diff aditivo
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-13/P-02. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `56c90758834b`.


RED: `memory_platform/tests/test_untrusted_internal.py` falló con KeyError: 'untrusted' en todas las herramientas de lectura y AttributeError: agent_tools sin `untrusted` · 2026-11-13.

### T-47 — Arnés en cadena: kairos-mcp → servidor, ASGI en proceso sobre PostgreSQL aislado

- **Descripción**: Arnés de pruebas que monta kairos-mcp contra la app del servidor por transporte ASGI en proceso, sobre el PostgreSQL efímero del target `test`, sin red y sin importar código del servidor desde `mcp/` (el arnés vive en el lado del servidor). Fuente: CA-11.
- **Changelog**: Hay un arnes de pruebas que monta kairos-mcp delante del servidor en el mismo proceso, sobre PostgreSQL aislado, para comprobar que las herramientas dan por la cadena lo mismo que el MCP interno.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.61h (estimado) · real 0.43h (medido)
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 168 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-46
- **Tipo**: test
- **Archivos**: `memory_platform/tests/chain_harness.py`, `memory_platform/tests/test_chain_smoke.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t47 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 (incluye el humo de la cadena) · `grep -rn "memory_platform" mcp/ --include=*.py` → sin coincidencias · Evidencia (2026-11-13): `docker build --target test ... Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `b0ff4d16005d`.

**Criterios de aceptación**
- [x] El arnés permite llamar a una herramienta por la cadena kairos-mcp → servidor con las mismas credenciales de prueba
- [x] `mcp/` sigue sin importar `memory_platform` (el test de CA-08 pasa)
- [x] Un caso de humo de la cadena (`projects`, `remember`, `search`) pasa
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Diseñar el puente ASGI (dónde vive el arnés para respetar CA-08)
- [x] Test en rojo de la cadena mínima
- [x] Implementar
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-11, §Pruebas (modo ASGI en proceso). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `67092d5c5ecb`.


RED: `memory_platform/tests/test_chain_smoke.py` falló con ModuleNotFoundError: No module named 'memory_platform.tests.chain_harness' · 2026-11-13.

### T-48 — Los 7 ficheros de tests de comportamiento MCP contra la cadena (CA-11)

- **Descripción**: Ejecutar los siete ficheros de tests del MCP interno también contra la cadena kairos-mcp → servidor, con los mismos resultados salvo los campos aditivos de S-05. Fuente: CA-11, CA-12, CA-13.
- **Changelog**: Los tests de comportamiento del MCP se ejecutan ahora tambien por la cadena kairos-mcp -> servidor con los mismos resultados; kairos-mcp devuelve 413 con cuerpos grandes, 401 con claves revocadas y nunca el texto de un error interno.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.61h (estimado) · real incluida en las ventanas de T-46 y T-47 (medido, solape; no sumar)
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 168 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-47
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_mcp.py`, `memory_platform/tests/test_mcp_write.py`, `memory_platform/tests/test_agent_tools.py`, `memory_platform/tests/test_extended_tools.py`, `memory_platform/tests/test_corpus_gateway.py`, `memory_platform/tests/test_extended_gateway.py`, `memory_platform/tests/test_work_gateway.py`, `memory_platform/tests/chain_harness.py`, `memory_platform/tests/chain_services.py`, `memory_platform/tests/test_chain_retry.py`, `mcp/kairos_mcp/limits.py`, `mcp/kairos_mcp/config.py`, `mcp/kairos_mcp/app.py`, `mcp/kairos_mcp/auth.py`, `mcp/kairos_mcp/translate.py`, `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/logs.py`, `mcp/tests/test_limits.py`, `mcp/tests/test_unauthorized.py`, `mcp/tests/test_robustness.py`, `memory_platform/tests/test_chain_review1.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t48 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `docker build` anterior imprime `tests` ≥ línea base de T-01 más los casos de la cadena · Evidencia (2026-11-13): `docker build --target test ... Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `54942fcd9862`.

**Criterios de aceptación**
- [x] Los siete ficheros pasan con el MCP interno y con la cadena, con los mismos resultados salvo `untrusted` y `warning`
- [x] Con una clave sin permiso de lectura la herramienta falla con el mismo mensaje que el MCP interno; sin credencial, 401
- [x] El recuento de tests del MCP interno no baja (ningún test desactivado)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Parametrizar los siete ficheros por modo (interno / cadena)
- [x] Corregir las diferencias reales de kairos-mcp (no los tests)
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-11. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `25f5f015547d`.


RED: `memory_platform/tests/test_mcp_write.py::MCPBoundaryChainTests` falló con AssertionError 200 != 413 (cuerpo grande) y 200 != 401 (clave revocada) en las variantes chain; KeyError 'jobs' filtrado como texto de la herramienta · 2026-11-13.

### T-49 — Documentar `kairos-mcp`

- **Descripción**: Documentar el componente: variables `KAIROS_API_URL` y `KAIROS_API_TIMEOUT`, credencial Bearer, envoltorio S-05, errores y cómo ejecutar sus tests. Fuente: CA-32, C-03.
- **Changelog**: La documentacion describe kairos-mcp: su arranque y variables (KAIROS_API_URL, KAIROS_API_TIMEOUT, KAIROS_ALLOWED_ORIGINS, KAIROS_MAX_BODY_BYTES), la credencial Bearer, el dato no fiable, los errores y los topes, y la arquitectura de los tres componentes.
- **Estado**: completado
- **Cerrada**: 2026-11-13
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 84 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-48
- **Tipo**: docs
- **Archivos**: `mcp/README.md`, `docs/architecture.md`, `docs/integration.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**: `grep -c "KAIROS_API_URL\|KAIROS_API_TIMEOUT" mcp/README.md docs/configuration.md` → ≥ 2 · lectura: valores y rutas citados coinciden con el código · Evidencia (2026-11-13): `grep -c "KAIROS_API_URL|KAIROS_API_TIMEOUT" mcp/README.md docs/configuration.md` -> 4 y 2 (>= 2); lectura: variables, puerto 8791, plazo 30 s (4 x por llamada), tope 262144 B, 32768/262144 B, mensajes de error y rutas… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2f52e72d450d`.

**Criterios de aceptación**
- [x] `mcp/README.md` describe arranque, variables y límites
- [x] `docs/architecture.md` explica los tres componentes y quién habla con quién
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Redactar según `docs-style.md`
- [x] Comprobar cada variable contra el código
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6c45a6b3297e`.

### T-50 — Revisión adversarial de la Fase 5

- **Descripción**: Revisión adversarial del núcleo de la iniciativa: ¿diverge algún `inputSchema`, descripción o anotación del contrato? ¿se filtra la credencial a logs o a `/v1` de otra forma? ¿una herramienta de lectura se escapa del envoltorio? ¿`mcp/` importa servidor por una vía indirecta? ¿hay N+1 o plazos sin tope? Fuente: retro, R-01, R-02, R-05, R-06.
- **Changelog**: kairos-mcp se revisó de forma adversarial en seis intentos y dos ciclos: valida la entrada sin bloquear el servicio ni hacer esperar a las llamadas pequeñas, acepta UUID en cualquier forma, recorta respuestas grandes y marca `query_corpus` como dato no fiable.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 19.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 2.61h (estimado) · real —
- **Supervisión**: est. 0.65h (≈25 % IA) · real —
- **Previsión IA**: 719 k in / 64 k out tok · ⚠️ verificar €
- **Dependencias**: T-36 … T-49
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t50 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `python mcp/tests/smoke_container.py` → `PASS health 200; tools 34` · lectura: `review.md`, sección «Fase 5», sin hallazgos Critical/Important abiertos · Evidencia (2026-11-14): `review.md`… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2355b12fb146`.

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 5»
- [x] 0 hallazgos Critical o Important abiertos
- [x] Suite backend, suite de `mcp/` y humo del contenedor (T-39) en verde tras cada arreglo
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: los intentos de revisión no se midieron con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado); las correcciones sí (T-41-fix1..fix5)

**Subtareas**
- [x] Fuzzing de argumentos contra el `inputSchema`
- [x] Buscar el token sintético en logs y respuestas
- [x] Repetir `smoke_container.py`
- [x] `usage-meter start/close` por intento — EXCEPCIÓN: ver el criterio anterior

**Notas**: Procedencia: retro (hallazgos reales en todas las fases). No escribe en `testing/`.

---

## Fase 6 — Compatibilidad (C-07)

**Estado**: completado · **Estimado**: 23.4h (19.5h base) · **Real**: — · **Coste est.**: 1.170 € · **Tokens est.**: 757 k

### T-51 — `MEMORY_MOUNT_MCP` y cabeceras `Deprecation`/`Sunset` del MCP interno

- **Descripción**: Añadir `MEMORY_MOUNT_MCP` (por defecto `1`). Montado, cada respuesta del MCP interno lleva `Deprecation` y `Sunset` con la versión de retirada (0.5.0, P-07) y se emite el evento de log `mcp_legacy_used` sin datos del usuario; con `0`, `/mcp` en `memory-api` responde 404. Fuente: CA-27, P-07.
- **Changelog**: El MCP interno deja de ser obligatorio: con MEMORY_MOUNT_MCP=0 /mcp de la API responde 404, y mientras siga montado (valor por defecto) marca cada respuesta como en desuso (Deprecation, Sunset 0.5.0).
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real 0.37h (medido)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 104 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-50
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `memory_platform/mcp.py`, `memory_platform/app.py`, `memory_platform/tests/test_mcp_legacy.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t51 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · Evidencia (2026-11-14): suite backend `MEMORY_TEST_RESULT` tests 749, failures 0, errors 0, skipped 0, passed true, `llm_chat_calls` 0 (kairos-test:i2p6; 743 + 6 de test_mcp_legacy); tests de… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ad6b8be99152`.

**Criterios de aceptación**
- [x] Con el valor por defecto, los tests actuales del MCP interno pasan y las respuestas llevan `Deprecation` y `Sunset`
- [x] Con `MEMORY_MOUNT_MCP=0`, `/mcp` responde 404
- [x] El log `mcp_legacy_used` no contiene credencial, argumentos ni contenido
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Tests en rojo (cabeceras, 404, log)
- [x] Implementar interruptor y cabeceras en el montaje
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-27/P-07. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2134dfb96e44`.


RED: `memory_platform/tests/test_mcp_legacy.py` falló con 6 tests: 3 failures y 2 errors (sin cabeceras Deprecation/Sunset, sin evento mcp_legacy_used, Settings sin mount_mcp) · 2026-11-14.

### T-52 — `/mcp` del proxy web hacia kairos-mcp y Compose

- **Descripción**: Enrutar `/mcp` del proxy web a `memory-mcp` (hoy a `memory-api`) y declarar la dependencia en Compose; el MCP interno sigue accesible en `memory-api:8790/mcp` durante la versión. Fuente: CA-27, CA-28, P-07.
- **Changelog**: El /mcp del proxy web (puerto 5173) ahora lo sirve kairos-mcp en lugar del MCP interno de la API; el puente del CLI no cambia, y memory-web espera a memory-mcp.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real 0.01h (medido)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 104 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-51
- **Tipo**: devops
- **Archivos**: `memory_platform/nginx.conf`, `docker-compose.yml`, `memory_platform/tests/test_nginx_routes.py`, `memory_platform/Dockerfile.web`, `memory_platform/tests/test_nginx_portal.py`, `memory_platform/tests/test_deploy.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile.web -t kairos-web-test:t52 .` → exit 0 (`nginx -t`) · `python -m unittest discover -s memory_platform/tests -p test_nginx_routes.py` → `OK` · Evidencia (2026-11-14): `docker build --target test -f memory_platform/Dockerfile.web -t kairos-web-test:t52 .` exit 0, `nginx: configuration file /tmp/nginx-test.conf test is successful`; `python… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0d4eb2de7c98`.

**Criterios de aceptación**
- [x] `nginx -t` valida la configuración con `/mcp` apuntando a `memory-mcp`
- [x] `memory-web` depende de `memory-mcp` y `docker compose config` del proyecto aislado lo refleja
- [x] `/mcp` conserva el comportamiento de plazos y buffers que tenía
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test estructural de la ruta (rojo)
- [x] Cambiar `nginx.conf` y Compose
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-27/P-07. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `41cbea948d9e`.


RED: `memory_platform/tests/test_nginx_routes.py` falló con 7 tests: 3 failures y 1 error (/mcp apuntaba a memory-api:8790, Dockerfile.web sin sustituir memory-mcp, memory-web sin depends_on memory-mcp ni red mcp) · 2026-11-14.

### T-53 — Puente stdio del CLI contra kairos-mcp en proyecto aislado (CA-28)

- **Descripción**: Hacer que el target `lifecycle-test` ejercite el puente stdio del CLI contra kairos-mcp (no contra el MCP interno), en un proyecto Compose aislado, sin tocar el CLI. Fuente: CA-28, P-07.
- **Changelog**: La prueba de ciclo de vida del CLI (puente stdio y hooks) se ejecuta ahora contra kairos-mcp y no contra el MCP interno, y comprueba sus 34 herramientas y las requeridas por el CLI.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real 0.18h (medido)
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 104 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-52
- **Tipo**: test
- **Archivos**: `memory_platform/tests/lifecycle_probe.py`, `memory_platform/Dockerfile`, `packages/kairos-cli/tests/lifecycle.test.mjs`, `memory_platform/tests/nginx_portal_probe.py`, `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle:t53 .` → exit 0 · `cd packages/kairos-cli && npm test` → pasa sin cambios · Evidencia (2026-11-14): RED (2026-11-14): con el probe apuntado al MCP interno, `docker run` de kairos-test:i2p6 con node y el CLI montados falla en `the bridge reached {"name": "Kairos", "version": "1.27.1"}` (SDK del servidor, no… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `264aa28ac436`.

**Criterios de aceptación**
- [x] El puente stdio inicializa y lista las herramientas contra kairos-mcp a través de `/mcp/` del proxy
- [x] El target `lifecycle-test` pasa
- [x] `REQUIRED_TOOLS` está presente en lo que lista kairos-mcp
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test en rojo (el probe sigue usando el MCP interno)
- [x] Añadir kairos-mcp a la cadena del probe
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-28. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `d7275d0d25be`.

### T-54 — `kairos doctor` contra kairos-mcp en proyecto aislado

- **Descripción**: Comprobar que `kairos doctor` funciona contra kairos-mcp en el proyecto aislado (herramientas requeridas y versión). Fuente: CA-28.
- **Changelog**: kairos doctor --online se comprueba contra kairos-mcp: informa de las 34 herramientas, sin ninguna requerida ausente, y del proyecto autorizado.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.25h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 69 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-53
- **Tipo**: test
- **Archivos**: `memory_platform/tests/lifecycle_probe.py`, `packages/kairos-cli/tests/lifecycle.test.mjs`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle:t54 .` → exit 0 con el caso de `doctor` · Evidencia (2026-11-14): `docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle:t54 .` exit 0 (suite 756 tests, 0 failures, 0 errors, 0 skipped); salida del caso doctor (sin escribir en testing/): doctor ready, doctor_tools 34,… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `57b5137eee11`.

**Criterios de aceptación**
- [x] `kairos doctor` informa de las herramientas requeridas presentes contra kairos-mcp
- [x] El resultado queda en el ledger como evidencia, sin escribir en `testing/`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Añadir el caso al probe
- [x] Ejecutar el target y anotar la salida en `Notas`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-28. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0edbbf16d4ce`.


RED: `memory_platform/tests/lifecycle_probe.py (caso doctor)` falló con TDD parcial: el caso doctor se escribio junto al de T-53 en el mismo probe; su aserción no corrió en rojo por separado (con el probe apuntado al MCP interno falla antes, en la identidad del servidor); primera ejecucion completa en verde · 2026-11-14.

### T-55 — Nota de migración y retirada del MCP interno

- **Descripción**: Escribir la nota de migración: el MCP interno queda en desuso y se retira en 0.5.0, `/mcp` pasa a kairos-mcp, cabeceras `Deprecation`/`Sunset`, evento `mcp_legacy_used`, `MEMORY_LLM_MODEL` obligatorio solo si se activa extracción o respuestas, y el trato de `generate: true`. Fuente: CA-27, CA-32, R-03.
- **Changelog**: Nota de migracion publicada: el MCP interno queda en desuso y se retira en la 0.5.0, /mcp del proxy pasa a kairos-mcp, y se documentan MEMORY_MOUNT_MCP, el evento mcp_legacy_used y el cambio en la captura de resumenes.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.25h (estimado) · real 0.00h (medido)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 69 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: docs
- **Archivos**: `docs/integration.md`, `docs/operations.md`, `CHANGELOG.md`, `CHANGELOG.es.md`, `docs/architecture.md`, `docs/configuration.md`, `docker-compose.yml`
- **Cubre (tests)**: —
- **Verificación**: `grep -c "MEMORY_MOUNT_MCP\|0.5.0" docs/integration.md CHANGELOG.md` → ≥ 2 · lectura: coincide con T-12, T-09 y T-51 · Evidencia (2026-11-14): grep -c de MEMORY_MOUNT_MCP o 0.5.0: docs/integration.md 3, CHANGELOG.md 1 (suma 4 >= 2); lectura contra T-12 (MEMORY_LLM_MODEL solo con extraccion o respuestas, sin beam:cloud), T-09 (generate:true aceptado, sin trabajo extract, recibo extraction disabled)… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `95d810f8eba8`.

**Criterios de aceptación**
- [x] La nota cita la versión de retirada, las cabeceras, el log y el interruptor `MEMORY_MOUNT_MCP`
- [x] Avisa del cambio de captura de resúmenes (R-03) y de `beam:cloud`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Redactar según `docs-style.md`
- [x] Comprobar cada variable contra el código
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-27/CA-32, R-03. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `043d67dffed5`.

### T-56 — Revisión adversarial de la Fase 6

- **Descripción**: Revisión adversarial: ¿el 404 con `MEMORY_MOUNT_MCP=0` cubre subrutas? ¿las cabeceras salen también en errores y streaming? ¿el log filtra algo? ¿el puente del CLI sigue funcionando con la ruta antigua? Fuente: retro, R-06.
- **Changelog**: La compatibilidad con el MCP interno se revisó de forma adversarial: `/mcp` de la web ya no reenvía la cookie de sesión del portal a kairos-mcp, y la documentación avisa de que el MCP interno sigue accesible en `/memory-api/mcp/` hasta poner `MEMORY_MOUNT_MCP=0`.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 6.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.89h (estimado) · real —
- **Supervisión**: est. 0.22h (≈25 % IA) · real —
- **Previsión IA**: 246 k in / 22 k out tok · ⚠️ verificar €
- **Dependencias**: T-51 … T-55
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t56 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · lectura: `review.md`, sección «Fase 6», sin hallazgos Critical/Important abiertos · Evidencia (2026-11-14): `review.md` sección «Fase 6»; 1 intento (A+B y C en dos revisores). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0cccd19c5e33`.

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 6»
- [x] 0 hallazgos Critical o Important abiertos
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: el intento de revisión no se midió con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado)

**Subtareas**
- [x] Probar subrutas y métodos con el interruptor apagado
- [x] Cerrar hallazgos
- [x] `usage-meter start/close` por intento — EXCEPCIÓN: ver el criterio anterior

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 7 — Estructura del repositorio (C-06)

**Estado**: completado · **Estimado**: 46.8h (39.0h base) · **Real**: — · **Coste est.**: 2.340 € · **Tokens est.**: 1614 k

### T-57 — Línea base previa al movimiento: recibo de la puerta congelada y recuento

- **Descripción**: Antes de mover nada, registrar en el ledger: recuento de la suite, hash de `store_surface.json`, lista de `npm pack --dry-run` del cliente y resultado de la puerta congelada. Es el oráculo de todo el bloque. Fuente: CA-25, CA-26, P-09.
- **Changelog**: Se registró la línea base (tests, superficie del almacén, contenido del paquete del CLI) antes de reorganizar el repositorio; sin cambios de comportamiento.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.14h (estimado) · real 0.25h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 38 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: PR #2 fusionado en `main` (externa, P-09), T-56
- **Tipo**: refactor
- **Archivos**: `memory_platform/tests/store_surface.json`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view 2 --json state --jq .state` → `MERGED` · `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t57 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `sha256sum memory_platform/tests/store_surface.json` → valor anotado · Evidencia (2026-11-14): `gh pr view 2 --json state --jq .state` →… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2dae3585de1c`.

**Criterios de aceptación**
- [x] Quedan anotados `tests`, `sha256` de `store_surface.json`, la lista de `npm pack --dry-run` y el recibo de la puerta congelada
- [x] El PR #2 consta como fusionado en `main` y la rama está rebasada sobre él — evidencia: la rama parte de `main` por merge (788682d fusiona `origin/main`), no por rebase, para no reescribir historia ni forzar el push
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Comprobar la fusión del PR #2 (`gh pr view 2 --json state`)
- [x] Ejecutar la suite y la puerta y anotar los valores
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-25/CA-26, P-09. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `985747ea32bd`.

### T-58 — `git mv memory_platform server/memory_platform` en un commit solo de movimiento

- **Descripción**: Mover el directorio con `git mv` en un commit que no cambia contenido, conservando el nombre del paquete (P-06) y los finales de línea. Este commit deja el árbol sin compilar a propósito; T-59 lo repara en el paso siguiente. Fuente: CA-23, P-06, R-07.
- **Changelog**: El servidor pasa a vivir en `server/` (movimiento sin cambios de contenido; el paquete Python sigue llamándose `memory_platform`).
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.14h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 38 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-57
- **Tipo**: refactor
- **Archivos**: `server/memory_platform/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --cached -M --stat | tail -1` → solo renombrados, 0 inserciones y 0 borrados
  - `git log --follow --oneline -1 -- server/memory_platform/app.py` → muestra historia anterior al movimiento
  - Evidencia (2026-11-14): Commit 66677ae: `git show -M --stat` → 128 files changed, 0 insertions(+), 0 deletions(-), todos `rename … (100%)` (0 con similitud menor); `git log --follow --oneline -2 -- server/memory_platform/app.py` → 66677ae y 5b54d5e (T-51, anterior al movimiento). EOL intactos: similitud 100 % byte a byte y `.gitattributes` `* -text`. Oráculo: similitud 100 %; el árbol queda sin construir a propósito hasta T-59 (que cierra con la suite en verde).

**Criterios de aceptación**
- [x] `git log --follow` conserva la historia de un fichero movido
- [x] `git diff --stat -M` del commit muestra solo renombrados (100 % de similitud) y 0 líneas cambiadas
- [x] Los EOL de cada fichero no cambian (`.gitattributes` es `* -text`)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] `git mv memory_platform server/memory_platform`
- [x] Comprobar similitud y EOL
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23, P-06, R-07. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `59c630705f37`.

### T-59 — Dockerfiles, Compose y rutas del servidor tras el movimiento

- **Descripción**: Ajustar contextos `COPY`, rutas de los targets (`api`, `operator`, `worker`, `test`, `retrieval-eval`, `lifecycle-test`), Compose y scripts a la nueva ubicación. El comando de verificación pasa a `-f server/memory_platform/Dockerfile` o `-f server/Dockerfile` según se decida al cerrar (se anota). Fuente: CA-23, CA-25.
- **Changelog**: Quien despliega construye el servidor desde `server/memory_platform/Dockerfile`; los servicios, nombres, volúmenes y redes de Compose no cambian y los tests del servidor corren igual desde la nueva ruta.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.55h (estimado) · real 0.16h (medido)
- **Supervisión**: est. 0.14h (≈25 % IA) · real —
- **Previsión IA**: 154 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-58
- **Tipo**: refactor
- **Archivos**: `server/memory_platform/Dockerfile`, `docker-compose.yml`, `server/memory_platform/tests/run_postgres.py`, `.github/workflows/ci.yml`, `scripts/*.py`, `server/memory_platform/tests/**`, `server/memory_platform/schemas.py`, `scripts/tests/**`, `mcp/README.md`, `mcp/requirements.txt`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t59 .` → `MEMORY_TEST_RESULT` con `tests` igual a T-57, 0 fallos, 0 errores, 0 omitidos · `sha256sum server/memory_platform/tests/store_surface.json` → igual que T-57 · Evidencia (2026-11-14): `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:i2p7 .` rc 0 y `docker run --rm… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `fdc075a65498`.

**Criterios de aceptación**
- [x] Todos los targets del Dockerfile construyen desde la nueva ruta
- [x] `docker compose config` resuelve las imágenes y contextos
- [x] La suite tiene `tests` idéntico a la línea base de T-57 y `store_surface.json` no cambia
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Actualizar `COPY` y contextos
- [x] Actualizar Compose y scripts
- [x] Ejecutar la suite completa
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-25. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `60f0a26dd9e2`.

### T-60 — Puerta congelada, scripts y herramientas con las rutas nuevas

- **Descripción**: Actualizar la puerta congelada y los scripts que fijan `memory_platform` o `packages` para que apunten a `server/` y `client/`, con el recibo de la puerta actualizada. Nota: la puerta vive en `testing/` de una iniciativa cerrada; se edita con aprobación de `qa` o se genera una copia junto al ledger (no se escribe en `testing/` de esta iniciativa). Fuente: CA-25, evaluación C-06.
- **Changelog**: La puerta de verificación aislada (código congelado en un contenedor sin red) acepta la estructura `server/`, `mcp/` y los contratos; los scripts de operación importan el servidor desde `server/`.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.41h (estimado) · real 0.06h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 115 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-59
- **Tipo**: refactor
- **Archivos**: `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`, `scripts/frozen-source-gate.py`, `scripts/deploy-memory.py`, `scripts/export-contracts.py`, `scripts/memory-admin.py`, `scripts/memory-client.py`, `scripts/diagnose-deployment.py`, `scripts/tests/**`, `scripts/frozen_evidence.py`
- **Cubre (tests)**: —
- **Verificación**: `docker run --rm --network=none --user postgres -v <git archive de HEAD>:/candidate:ro -v ./scripts:/gate:ro -v <directorio de recibo fuera del repo>:/test-output kairos-test:<etiqueta> python /gate/frozen-source-gate.py` (copia `scripts/frozen-source-gate.py`, con `scripts/frozen_evidence.py` al lado; la puerta de `docs/roadmap/2026-11-06-functional-parity/testing/` es la histórica y ya no sirve con `server/`) → `KAIROS_FROZEN_SOURCE` y `MEMORY_TEST_RESULT` con `passed` true · `python scripts/export-contracts.py && git diff --stat docs/contracts` → sin diff · `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t60 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `1ee32160206f`.

**Criterios de aceptación**
- [x] La puerta congelada apunta a las rutas nuevas y genera un recibo
- [x] `scripts/*.py` no contiene rutas antiguas (`grep`) — evidencia: sin `memory_platform/` antiguo en T-60; la de `packages/kairos-cli` de `accept-native-clients.py` se cambió en T-62, tras mover el cliente
- [x] `python scripts/export-contracts.py` produce los contratos sin diff
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] `grep -rn "memory_platform/\|packages/kairos-cli" scripts docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`
- [x] Actualizar rutas
- [x] Ejecutar la puerta
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec §Arquitectura (estructura final) y CA-25. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `3deb2e0cf44a`. Corrección de la revisión (intento 1, fix1): la `Verificación` apunta ahora a la copia de `scripts/`. La puerta importa `frozen_evidence` (guarda el recibo con hash y escritura exclusiva); su original vive en `testing/` de la iniciativa cerrada de paridad funcional, carpeta de `qa` que el hook impide escribir, así que se copió a `scripts/frozen_evidence.py` (copia exacta) y el import ya no necesita `PYTHONPATH` (el directorio del script es `sys.path[0]`). Evidencia: `cd scripts && python -c "import ast;ast.parse(open('frozen-source-gate.py').read());import frozen_evidence"` → ok (sin `-I`: en Python 3.13 `-I` implica `-P` y no añade el directorio actual a `sys.path`; dentro de la puerta, `python /gate/frozen-source-gate.py` añade `/gate` y no le afecta).

### T-61 — `git mv packages/kairos-cli client` en un commit solo de movimiento

- **Descripción**: Mover el CLI con `git mv` en un commit sin cambios de contenido. Fuente: CA-23, CA-26.
- **Changelog**: El CLI de Kairos pasa a vivir en `client/` (movimiento sin cambios de contenido; el paquete sigue siendo `@daycry/kairos`).
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real 0.02h (medido)
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 19 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-60
- **Tipo**: refactor
- **Archivos**: `client/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --cached -M --stat | tail -1` → solo renombrados
  - `git log --follow --oneline -1 -- client/lib/mcp.mjs` → historia anterior al movimiento
  - Evidencia (2026-11-14): Commit ba954b4: `git show -M --stat` → 53 files changed, 0 insertions(+), 0 deletions(-); `git show -M --summary --format=` → todos `rename … (100%)` (0 con similitud menor; los 6 binarios `.wasm` figuran con `- -` en numstat y también al 100 %); `git log --follow --oneline -2 -- client/lib/mcp.mjs` → ba954b4 y 7f116d0 (anterior al movimiento). EOL intactos (100 % byte a byte, `.gitattributes` `* -text`). Oráculo: similitud 100 %; el árbol queda sin ajustar a propósito hasta T-62.

**Criterios de aceptación**
- [x] `git log --follow` conserva la historia de un fichero movido
- [x] El commit muestra solo renombrados al 100 %
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] `git mv packages/kairos-cli client`
- [x] Comprobar similitud
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-26. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `a622ab52c389`.

### T-62 — Rutas del cliente: `RUNTIME_FILES`, Dockerfile.test, `release:check` y `npm pack` idéntico

- **Descripción**: Ajustar `RUNTIME_FILES`, el Dockerfile de test, las rutas del target `lifecycle-test` y la CI al nuevo `client/`. El contenido empaquetado no cambia. Fuente: CA-26, CA-23.
- **Changelog**: El CLI se prueba y empaqueta desde `client/` con el mismo paquete npm de antes (los mismos 34 ficheros, mismos tamaños); `npm test`, `release:check` y la prueba de ciclo de vida siguen en verde.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.49h (estimado) · real 0.08h (medido)
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 135 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-61
- **Tipo**: refactor
- **Archivos**: `client/lib/config.mjs`, `client/package.json`, `client/Dockerfile.test`, `client/tests/release-check.mjs`, `server/memory_platform/Dockerfile`, `.github/workflows/ci.yml`, `.gitignore`, `scripts/accept-native-clients.py`, `scripts/frozen-source-gate.py`, `scripts/tests/test_ci_workflow.py`, `server/memory_platform/tests/lifecycle_probe.py`, `server/memory_platform/tests/test_extended_gateway.py`
- **Cubre (tests)**: —
- **Verificación**: `cd client && npm test` → pasa · `cd client && npm run release:check` → exit 0 · `cd client && npm pack --dry-run --json` → lista de `files` idéntica a la anotada en T-57 · `docker build --target lifecycle-test -f server/memory_platform/Dockerfile -t kairos-lifecycle:t62 .` → exit 0 · Evidencia (2026-11-14): `cd client && npm test` → tests 90, pass 90, fail 0. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ce250b7a6821`.

**Criterios de aceptación**
- [x] `npm pack --dry-run` del cliente produce la misma lista de ficheros que la línea base de T-57
- [x] `npm run release:check` pasa
- [x] `npm test` en `client/` pasa sin cambios en los tests
- [x] `lifecycle-test` pasa
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Ajustar `config.mjs:11` y rutas
- [x] Comparar `npm pack --dry-run` con la línea base
- [x] Ejecutar `npm test`, `release:check` y `lifecycle-test`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-26. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2ed4364f7f49`.

### T-63 — Imagen web: `Dockerfile.web` y `nginx.conf` a `web/`

- **Descripción**: Mover `Dockerfile.web` y `nginx.conf` a `web/`, ajustar contextos y Compose, y conservar los targets `runtime`, `test` y `final`. Fuente: CA-23, CA-24.
- **Changelog**: La imagen del portal se construye desde `web/Dockerfile` y usa `web/nginx.conf`; el contenido servido y la configuración de nginx no cambian y Compose conserva el servicio `memory-web`.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.28h (estimado) · real 0.17h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 77 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-62
- **Tipo**: refactor
- **Archivos**: `web/Dockerfile`, `web/nginx.conf`, `docker-compose.yml`, `.github/workflows/ci.yml`, `server/memory_platform/Dockerfile`, `server/memory_platform/Dockerfile.e2e`, `server/memory_platform/tests/**`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f web/Dockerfile -t kairos-web-test:t63 .` → exit 0 · `cd web && npm run typecheck && npm test && npm run build` → exit 0 · Evidencia (2026-11-14): Movimiento f00c763 (`Dockerfile.web` → `web/Dockerfile`, `nginx.conf` → `web/nginx.conf`, ambos 100 %, 0 líneas). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `666f33d4db11`.

**Criterios de aceptación**
- [x] La imagen web se construye desde `web/` y su target `test` pasa (`nginx -t`)
- [x] Compose y CI apuntan a las rutas nuevas
- [x] El contenido servido no cambia
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] `git mv` en commit aparte
- [x] Ajustar `COPY` y contextos
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-24. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c47e7ea83605`.

### T-64 — Versión, imagen y orden de tests de cada componente (CA-24)

- **Descripción**: Declarar versión 0.4.0 en `server`, `mcp` y `client` (sin publicar, P-07) y dejar para cada componente su imagen o Dockerfile y el comando de tests que ejecuta la CI. Fuente: CA-24, P-07.
- **Changelog**: Servidor, kairos-mcp y CLI declaran la versión 0.4.0 (sin publicar nada); el CLI 0.4.0 sigue aceptando instalaciones de la 0.3.0 y anteriores, y la CI sube el mínimo de tests a 759.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.41h (estimado) · real 0.34h (medido)
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 115 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-63
- **Tipo**: refactor
- **Archivos**: `server/VERSION`, `mcp/VERSION`, `client/package.json`, `web/package.json`, `CHANGELOG.md`, `CHANGELOG.es.md`, `server/memory_platform/tests/test_versions.py`, `client/lib/config.mjs`, `scripts/tests/test_ci_workflow.py`, `.github/workflows/ci.yml`, `server/memory_platform/Dockerfile`, `scripts/frozen-source-gate.py`, `client/tests/lifecycle.test.mjs`
- **Cubre (tests)**: —
- **Verificación**: `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t64 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 · `cd client && node -p "require('./package.json').version"` → `0.4.0` · Evidencia (2026-11-14): RED (antes de implementar): `PYTHONPATH=server python -m unittest… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `3a045069a4fa`.

**Criterios de aceptación**
- [x] Cada componente declara su versión (server 0.4.0, mcp 0.4.0, client 0.4.0)
- [x] Cada componente tiene Dockerfile (o imagen) y un comando de tests documentado y presente en la CI
- [x] `test_versions.py` comprueba coherencia entre versión y changelog
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Test de versiones en rojo
- [x] Fijar versiones y changelogs
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-24/P-07. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `9e8f1fcb7e8c`. Corrección de la revisión (fix1): `client/tests/lifecycle.test.mjs` recorre ahora también la actualización 0.3.0 → 0.4.0 (`previous` = 0.3.0 junto a 0.1.0–0.1.5): `npm test` en `client/` rc 0, 91 tests, `upgrade from 0.3.0 preserves old files and recovers a partial switch` ✔; `npm pack --dry-run` → 0.4.0, 34 ficheros, 669.2 kB (igual que antes).


RED: `server/memory_platform/tests/test_versions.py::ComponentVersionTests` falló con FileNotFoundError: server/VERSION (2 errores) antes de declarar las versiones · 2026-11-14.

### T-65 — Rutas de la CI tras el movimiento

- **Descripción**: Actualizar los trabajos de la CI a las rutas finales y comprobar que el test estructural y la puerta de higiene (T-04) siguen en verde; ejecución verde en el PR. Fuente: CA-24.
- **Changelog**: La integración continua construye cada componente desde sus rutas nuevas (`server/`, `mcp/`, `client/`, `web/`) y los seis trabajos terminan en verde en la rama.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.28h (estimado) · real 0.13h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 77 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-64
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `mcp/tests/test_review5.py`
- **Cubre (tests)**: —
- **Verificación**: `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK` · `gh run list --branch feat/three-components --limit 1 --json conclusion` → `success` · Evidencia (2026-11-14): `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → Ran 45 OK (incluye `ComponentTests` y el mínimo 759). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6389acf79363`.

**Criterios de aceptación**
- [x] Los seis trabajos (`server`, `retrieval-eval`, `mcp`, `client`, `web`, `contracts`) usan rutas nuevas y terminan en verde en el PR
- [x] El test estructural y la puerta de higiene pasan
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Actualizar rutas
- [x] Empujar y comprobar la ejecución
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-24. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `e08f4fe533e7`. Corrección de la revisión (fix1): `test_a_large_call_that_waits_too_long…` dependía del tiempo (run de CI 43617679410: `len(busy)` 2 en vez de 3 con `queue_seconds=0.3`). Ahora la primera llamada grande retiene el único turno con un validador bloqueado en un `threading.Event` (parche de `Checks.check`), las otras tres vencen su plazo de 0.3 s y solo entonces se libera; nada depende de lo que tarde la validación. Rojo con el código roto (`move_on_after(None)` en `tools.py`, restaurado tras la prueba): `LargeCallsWaitABoundedTimeTests` → `TimeoutError`, FAILED (errors=1); verde con el bueno: `test_review5` 5 ejecuciones seguidas OK (8 tests cada una) y suite completa de `mcp/` `Ran 136 tests` OK.

### T-66 — Manuales con la estructura de tres componentes

- **Descripción**: Actualizar rutas y descripciones en los manuales a `server/`, `mcp/`, `client/` y `web/`. Fuente: CA-32, evaluación C-06.
- **Changelog**: Los manuales describen la estructura de tres componentes (`server/`, `mcp/`, `client/`, `web/`): rutas, órdenes de construcción y pruebas, y la versión 0.4.0 del CLI, con una tabla de componentes en el README.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.55h (estimado) · real 0.03h (medido)
- **Supervisión**: est. 0.14h (≈25 % IA) · real —
- **Previsión IA**: 154 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-65
- **Tipo**: docs
- **Archivos**: `README.md`, `docs/architecture.md`, `docs/install.md`, `docs/operations.md`, `docs/integration.md`, `docs/configuration.md`, `docs/server-install.md`, `docs/release-cli.md`, `client/README.md`, `docs/RAG-INDEX.md`, `docs/code-analysis.md`, `docs/corpus-generated-answers.md`, `docs/extended-workflows.md`, `docs/manual.md`, `server/memory_platform/tests/retrieval_eval/README.md`, `docs/extended-workflows.md`
- **Cubre (tests)**: —
- **Verificación**: `grep -rn "packages/kairos-cli" README.md docs/*.md` → sin salida · lectura: comandos citados válidos contra el árbol nuevo · Evidencia (2026-11-14): `grep -rn "packages/kairos-cli" README.md docs/*.md client/README.md mcp/README.md` → sin salida. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ee4aa462333f`.

**Criterios de aceptación**
- [x] Ningún manual vigente cita `memory_platform/` ni `packages/kairos-cli` como ruta actual (los recibos de iniciativas cerradas quedan como históricos)
- [x] Los comandos citados existen
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] `grep -rn "packages/kairos-cli\|memory_platform/" README.md docs --include=*.md` fuera de `docs/roadmap`
- [x] Corregir y comprobar comandos
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `745f31637737`. Corrección de la revisión (fix1): barrido de `python -m memory_platform`, `memory_platform/` sin `server/`, `packages/kairos-cli` y `Dockerfile.web` en README, `docs/*.md` (fuera de `docs/roadmap/`), `mcp/README.md` y READMEs del servidor. Corregidas (desde la raíz: `PYTHONPATH=server`, igual que la CI): `docs/operations.md` fila `contracts` y la sonda `ollama_proxy_probe`; `docs/extended-workflows.md` (`unittest test_extended_*`); `server/memory_platform/tests/retrieval_eval/README.md` (orden y ruta del dataset `server/memory_platform/tests/retrieval_eval/dataset-v1.jsonl`); `long_doc_measure` aclarado «dentro del arnés (`PYTHONPATH=/app/server`)». Las de `admin backfill-chunks`, `run_postgres`, `stale_measure` y las de `docker build`/`docker run` corren dentro de la imagen (`WORKDIR /app`, `PYTHONPATH=/app/server` en la etapa de test) y quedan como estaban; `packages/kairos-cli` y `Dockerfile.web` no aparecen en ningún manual vigente. Verificado sin Docker: `PYTHONPATH=server python -m memory_platform.tests.retrieval_eval.check_dataset <dataset-v1.jsonl>` → `OK es=24 en=24 typo_id=12 long=12 total=72`; `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → 11 tests OK; import de `ollama_proxy_probe`, `test_extended_tools` y `test_extended_gateway` OK (los dos últimos necesitan PostgreSQL para ejecutarse; la sonda necesita Docker). EOL CRLF de `docs/operations.md` conservado. usage-meter three-components/T-66-fix1 (cubre también T-60/T-64/T-65-fix1): 0.16 h IA (medido).

### T-67 — Recibo final de la estructura: suite, `store_surface.json`, historia y `npm pack`

- **Descripción**: Con todos los movimientos hechos, registrar en el ledger: suite completa con `tests` idéntico a T-57, `store_surface.json` sin cambios, `git log --follow` de un fichero de cada componente, la puerta congelada actualizada y `npm pack` idéntico. Fuente: CA-23, CA-25, CA-26.
- **Changelog**: La reorganización del repositorio queda verificada: misma suite (más 2 tests de versiones), misma superficie del almacén y mismo contenido del paquete npm del CLI que antes de mover nada.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.28h (estimado) · real 0.11h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 77 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-66
- **Tipo**: refactor
- **Archivos**: `server/memory_platform/tests/store_surface.json`, `scripts/frozen-source-gate.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t67 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `ls -d memory_platform packages/kairos-cli` → `No such file or directory` ×2
  - `sha256sum server/memory_platform/tests/store_surface.json` → igual que T-57
  - Evidencia (2026-11-14): HEAD ee593bb. Suite: `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t67 .` rc 0 y `docker run --rm --network=none kairos-test:t67 python -m memory_platform.tests.run_postgres` rc 0: MEMORY_TEST_RESULT tests 759 (línea base 757 + 2 de `ComponentVersionTests`), failures 0, errors 0, skipped 0, llm_chat_calls 0. `sha256sum server/memory_platform/tests/store_surface.json` → 83c27763460c342acac9a1deda71a75dbd3cc94b0fa0d1fcc2e12c04e80e4b00 = T-57. `ls -d memory_platform packages/kairos-cli` → No such file or directory ×2; existen server, mcp, client, web. `git log --follow`: server/memory_platform/app.py → 66677ae y 5b54d5e; client/lib/mcp.mjs → ba954b4 y 7f116d0; web/nginx.conf → f00c763 y 66677ae; mcp/Dockerfile → f6d02de y 66677ae. Puerta congelada (copia `scripts/frozen-source-gate.py`, git archive de HEAD, --network=none): source_sha256 c3c5fd28851a8f0c4642342d1abdf87ead9e2034841103584f73624988865255, file_count 275, MEMORY_TEST_RESULT tests 759, 0 failures, 0 errors, 0 skipped, passed true (la línea base comparable de T-57 era 757 tests, 271 ficheros; la roja sin tocar, 669/195/3). npm pack --dry-run del cliente: @daycry/kairos 0.4.0, 34 ficheros, mismas rutas (sha256 de la lista f879ab10…882f = T-57), 669218 bytes (669212 + 6: versión y README). `npm run release:check` rc 0 (al segundo intento; el primero falló en tests/run.mjs, flaky en el host, pasa suelto). lifecycle-test rc 0; `nginx -t` del target test de web/Dockerfile ok; web: 65 tests (T-63). mcp: 136 tests OK (T-64). CI en verde en 607f7a8 (T-65). `scope-check.py … --base 788682d` exit 0 (0 fuera de alcance). `ledger-lint` exit 0.

**Criterios de aceptación**
- [x] `tests` igual a la línea base, 0 fallos, 0 errores, 0 omitidos
- [x] `store_surface.json` byte a byte igual (hash de T-57)
- [x] No existen `memory_platform/` ni `packages/kairos-cli` en la raíz; existen `server/`, `mcp/`, `client/`, `web/`
- [x] `git log --follow` conserva la historia de un fichero movido de cada uno
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Ejecutar la suite y la puerta
- [x] Comparar hash, lista de `npm pack` y recuento
- [x] Anotar el recibo en `Notas`
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-25/CA-26. Los recibos van al ledger, no a `testing/` (reservado a `qa`). Clase: refactor (cierre de oráculo). Los recibos van al ledger, no a `testing/`. Corrección de la puerta durante el recibo: `copy` creaba mal los ficheros sueltos bajo un directorio no copiado entero (`web/nginx.conf`); ahora crea el directorio padre. Archivos añadido con nota: `scripts/frozen-source-gate.py`. Avisos a recordar: el test `test_timed_out_vectors_keep_bounded_slots_without_starving_authentication` falló una vez en la puerta de la línea base bajo carga y `release:check` del CLI falla de forma intermitente en este host; ambos pasan al repetir. usage-meter three-components/T-67: 0.11 h IA (medido, win-8fdf17a7fe8f4a3a8b69b0eade67a99e). CI: runs de la rama 43613535562 (607f7a8) y 43617300808 (d914eed), ambos success con los seis trabajos; el PR sigue para la Fase 8 con autorización.

### T-68 — Revisión adversarial de la Fase 7

- **Descripción**: Revisión adversarial: referencias a rutas antiguas en scripts, Dockerfiles, hooks, CI y docs; `git mv` con cambios de contenido camuflados; EOL alterados; ficheros que dejaron de empaquetarse; recursos `knowledge-graphs-*` referenciados. Fuente: retro, R-07, R-06.
- **Changelog**: La nueva estructura del repositorio (`server/`, `mcp/`, `client/`, `web/`) se revisó de forma adversarial: los manuales indican `PYTHONPATH=server` en las órdenes que se lanzan desde la raíz y la CI vuelve a ser estable.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 13.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.79h (estimado) · real —
- **Supervisión**: est. 0.45h (≈25 % IA) · real —
- **Previsión IA**: 492 k in / 44 k out tok · ⚠️ verificar €
- **Dependencias**: T-57 … T-67
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t68 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `grep -rln "packages/kairos-cli" --include=*.py --include=*.mjs --include=*.yml --include=Dockerfile* . ` fuera de `docs/roadmap` → vacío
  - lectura: `review.md`, sección «Fase 7», sin hallazgos Critical/Important abiertos
  - Evidencia (2026-11-14): `review.md` sección «Fase 7»; 2 intentos. Intento 1 (A+B y C+D en dos revisores): 1 Important (órdenes de los manuales sin `PYTHONPATH=server`) y 5 Minor; C+D sin hallazgos. fix1 (86b8d7a, 70c8f25, e9ff45d, b9c2c3a, 7ab69ad) corrige el Important y 3 Minor; 2 Minor quedan como deuda aceptada (merge en lugar de rebase; `client/.npm-cache` en la imagen de tests, anterior a la fase). Intento 2 (A+B): todo lo corregido ✓, sin Critical/Important; los 2 Minor nuevos (evidencia de T-60 con `-I`, bucle de espera sin tope en `test_review5`) los corrigió el orquestador en el commit de cierre. Suite del servidor: 759 tests, 0 failures, 0 errors, 0 skipped, `llm_chat_calls` 0 (trabajo `server` de CI 43620955201 sobre 7ab69ad; el cierre no toca `server/`). `npm pack` 34 ficheros; `scripts/tests` 112 OK; mcp 136 OK; `test_review5` 8 OK tras el cierre. CI del cierre: la ejecución del push del commit de cierre. Rutas antiguas: `grep` de `packages/kairos-cli` fuera de `docs/roadmap` vacío. EOL: 0 cambios en los ficheros tocados (`git ls-files --eol`).

**Criterios de aceptación**
- [x] `review.md` tiene la sección «Fase 7»
- [x] 0 hallazgos Critical o Important abiertos
- [x] Suite, puerta y `npm pack` en verde tras cada arreglo
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: los intentos de revisión no se midieron con usage-meter; los tokens de los revisores constan solo en la telemetría de los subagentes (estimado); la corrección sí (T-66-fix1, 0.16 h medido)

**Subtareas**
- [x] `git diff -M --stat 23ced03..HEAD` y búsqueda de rutas antiguas
- [x] Comparar EOL con `git ls-files --eol`
- [x] Cerrar hallazgos
- [x] `usage-meter start/close` por intento — EXCEPCIÓN: ver el criterio anterior

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 8 — Integración final y revisión

**Estado**: borrador · **Estimado**: 12.0h (10.0h base) · **Real**: — · **Coste est.**: 600 € · **Tokens est.**: 440 k

### T-69 — Prueba de contrato de kairos-mcp idéntica a la del MCP interno

- **Descripción**: Ejecutar la misma regla de `test_contract_additive.py` sobre `tools/list` del MCP interno y de kairos-mcp, y sobre el contrato regenerado contra la línea base de `23ced03`. Fuente: cierre de la Iniciativa 2 del plan director, CA-10, CA-29.
- **Changelog**: Una prueba de contrato comprueba que el MCP interno y kairos-mcp ofrecen las mismas 34 herramientas, con el mismo contenido y solo adiciones respecto de la línea base anterior.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.15h (estimado) · real 0.13h (medido)
- **Supervisión**: est. 0.04h (≈25 % IA) · real —
- **Previsión IA**: 40 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-68
- **Tipo**: test
- **Archivos**: `mcp/tests/test_contract_identity.py`, `server/memory_platform/tests/test_contract_additive.py`, `mcp/tests/contract_base_23ced03/kairos-mcp.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t69 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t69 mcp/ && docker run --rm kairos-mcp:t69 python -m unittest tests.test_contract_identity` → `OK`
  - Evidencia (2026-11-14): `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t69 .` → `MEMORY_TEST_RESULT` passed true, tests 764 (759 + 5 nuevas), failures 0, errors 0, skipped 0, llm_chat_calls 0. `docker run --rm kairos-mcp:t69 python -m unittest tests.test_contract_identity` → 4 tests OK; suite completa de mcp en la imagen: 140 tests OK. Mutación comprobada: cambiar una letra de la descripción de `projects` en `mcp/contract/kairos-mcp.json` pone en rojo dos pruebas (2 FAIL, `$.description: ... became ...`); revertido (sin diff).

**Criterios de aceptación**
- [x] Ambos MCP pasan la misma prueba con 34 herramientas, mismo orden y mismo contenido (`name`, `description`, `inputSchema`, `annotations`)
- [x] El contrato regenerado solo tiene adiciones respecto de `23ced03`
- [x] Un cambio mínimo en una descripción de kairos-mcp hace fallar la prueba (comprobado)
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Parametrizar la regla para ambos orígenes
- [x] Mutación manual para ver el rojo
- [x] `usage-meter start/close`

**Notas**: Procedencia: plan director, cierre de la Iniciativa 2; spec CA-10/CA-29. Patrón: `test_contract_additive.py:28-40`. Clase: capacidad nueva (verificación de cierre). usage-meter three-components/T-69: 0.13 h IA (medido, win-873b11b182fa4e23bb6614adf0b3b99d). La regla (`additive_violations`/`tool_differences`) se ejecuta sobre el `tools/list` vivo del MCP interno y de kairos-mcp (clase `ToolsListIdentityTests`, lado servidor) y sobre kairos-mcp contra una copia de la línea base `23ced03` (`mcp/tests/contract_base_23ced03/`, byte a byte igual a la del servidor, comprobado por un test); `payload.structured` es lo único añadido a un esquema desde `23ced03`. Contrato sin cambios; sin cambios visibles para clientes.

### T-70 — Contenedor MCP arrancado sin credenciales de base (cierre)

- **Descripción**: Arrancar el contenedor `kairos-mcp` con solo `KAIROS_API_URL`, sin `MEMORY_DSN*`, secretos ni red `memory-data`, y comprobar `GET /health/live` y la salida de `docker compose config` del proyecto aislado. Fuente: CA-09, cierre del plan director.
- **Changelog**: El contenedor de kairos-mcp arranca y responde con solo la dirección de la API: sin credenciales de base de datos, secretos ni acceso a la red de datos, y esa condición queda comprobada con la configuración real de Compose.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.15h (estimado) · real 0.03h (medido)
- **Supervisión**: est. 0.04h (≈25 % IA) · real —
- **Previsión IA**: 40 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-69
- **Tipo**: test
- **Archivos**: `mcp/tests/smoke_container.py`, `mcp/tests/compose.smoke.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `python mcp/tests/smoke_container.py` → `PASS health 200; tools 34`
  - `docker compose -p kairos-final-t70 config --format json` → `memory-mcp` sin `secrets` ni `memory-data`
  - Evidencia (2026-11-14): `KAIROS_SMOKE_PROJECT=kairos-final-t70 python mcp/tests/smoke_container.py` → `PASS config: memory-mcp has networks ['mcp'], no secrets, no volumes, no DSN` y `PASS health 200; tools 34`, exit 0. `docker compose -p kairos-final-t70 --profile memory config --format json` (con `.env.example`): `memory-mcp` sin `secrets`, sin volúmenes, sin red `memory-data`/`inference` y sin variable DSN (entorno: `KAIROS_API_URL`, `KAIROS_API_TIMEOUT`, `KAIROS_ALLOWED_ORIGINS`, `KAIROS_MAX_BODY_BYTES`, `KAIROS_VALIDATION_THREADS`). Tras la prueba: 0 contenedores, redes, volúmenes e imágenes `kairos-final-t70`; `docker volume ls -q --filter name=knowledge-graphs_` (7) y `docker ps --filter name=knowledge-graphs` (4) idénticos antes y después.

**Criterios de aceptación**
- [x] `GET /health/live` responde 200
- [x] `docker compose config` muestra el servicio sin `secrets` ni `memory-data`
- [x] El proyecto aislado se elimina al terminar y no se toca ningún recurso `knowledge-graphs-*`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Ejecutar `smoke_container.py` en el árbol final
- [x] Anotar la salida
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-09, cierre del plan director. Repite el humo de T-39 sobre el árbol ya reestructurado. Clase: verificación de cierre (misma prueba en verde). usage-meter three-components/T-70: 0.03 h IA (medido, win-7b5357bb845146aa814436dabd77f94a). `smoke_container.py` gana `check_service_configuration()` (la comprobación de `docker compose config` sobre el `docker-compose.yml` real, sin crear nada). Aviso para T-72: con `-p <proyecto>` el compose base conserva los nombres fijos `knowledge-graphs_mcp`, `knowledge-graphs_inference` y `knowledge-graphs_webui` para esas redes; el aislamiento depende del override que escribe `deploy-memory.py`. Sin cambios visibles para clientes.

### T-71 — Servidor arrancado y suite pasada sin ningún modelo de lenguaje (cierre)

- **Descripción**: En el árbol final, ejecutar la suite completa con `MEMORY_LLM_MODEL` sin definir y el espía de `/api/chat`, y comprobar el arranque aislado de `memory-api` y `memory-worker` sin llamadas a `/api/chat`. Fuente: CA-18, cierre del plan director.
- **Changelog**: El servidor arranca, ingiere e indexa sin ningún modelo de lenguaje configurado, y un ensayo aislado lo demuestra: el proveedor simulado no recibió ni una llamada de chat.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real 0.46h (medido)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-70
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_no_llm.py`, `scripts/deploy-memory.py`, `server/memory_platform/tests/llm_spy.py`, `scripts/tests/test_rehearsal_three_components.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t71 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `env -u MEMORY_LLM_MODEL docker compose -p kairos-nollm-t71 up -d memory-api memory-worker` (con override aislado) y consulta del espía → 0 llamadas
  - Evidencia (2026-11-14): `env -u MEMORY_LLM_MODEL docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t71 .` → `MEMORY_TEST_RESULT` passed true, tests 764, failures 0, errors 0, skipped 0, `llm_chat_calls` 0. Arranque aislado: `python scripts/deploy-memory.py --apply --fresh --project-name kairos-nollm-t71 --api-port 18791 --web-port 15174 --secret-dir <temporal> --embed-stub` → fases engine…verify, `PASS no language model: chat calls 0; embed calls 0`, exit 0 (en el intento 1 la fase verify falló: ver Notas). Con la pila arriba: `MEMORY_LLM_MODEL` vacío y `MEMORY_EXTRACT_ENABLED=0` en memory-api y memory-worker; espía `{"chat_calls": 0, "embed_calls": 0, "requests": 71}` (los 71 son las sondas de salud `/api/version` del proxy); el proxy apuntaba a `embed-stub:11434` con `OLLAMA_ALLOW_CHAT=1`, de modo que una llamada de chat habría llegado al espía y se habría contado. Limpieza: 0 contenedores, redes, volúmenes e imágenes `kairos-nollm-t71`; `docker volume ls -q --filter name=knowledge-graphs_` (7) y `docker ps --filter name=knowledge-graphs` (4) idénticos antes y después. `scripts/tests` 124 OK.

**Criterios de aceptación**
- [x] La suite pasa con 0 fallos y 0 omitidos sin modelo configurado
- [x] El espía registra 0 llamadas a `/api/chat`, también durante el arranque aislado de `memory-api` y `memory-worker`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Ejecutar la suite con el espía
- [x] Arrancar `api` y `worker` en el proyecto aislado `kairos-nollm-t71` y anotar el espía
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-18, cierre del plan director. Prohibido: base desplegada y recursos `knowledge-graphs-*`; todo en el proyecto aislado con el override que renombra redes y volúmenes (R-09). Clase: verificación de cierre. usage-meter three-components/T-71: 0.46 h IA (medido, win-57be818ae623470baa823d697c2b7531). Hallazgos del ensayo, corregidos aquí porque T-72 los necesita: (1) el compose base pone `OLLAMA_UPSTREAM` en `host.docker.internal:11434` (el Ollama del host) y un ensayo aislado lo habría usado; `deploy-memory.py --embed-stub` (solo proyectos aislados) añade un servicio `embed-stub` (imagen api, `memory_platform.tests.llm_spy`, vectores deterministas de 768 dimensiones, `GET /__spy`) en las redes `inference` y `egress` y pasa `OLLAMA_UPSTREAM`/`OLLAMA_ALLOW_CHAT=1` solo en el entorno de ese proceso; (2) `verify_runtime` iba por sesión de portal, pero `/mcp/` de nginx es kairos-mcp, que solo admite Bearer y no recibe la cookie: ahora crea una clave de lectura temporal para los proyectos del manifiesto, la usa en `/mcp/` y la revoca antes de cerrar la sesión; sin proyectos informa `mcp_checked: false`; (3) `--dry-run` existe como sinónimo explícito del valor por defecto (el plan por defecto ya era dry-run; sin `--apply` no se ejecuta nada). Archivos añadidos con nota: `scripts/deploy-memory.py`, `server/memory_platform/tests/llm_spy.py`, `scripts/tests/test_rehearsal_three_components.py`. Cambios visibles para el despliegue: nuevas opciones `--embed-stub`, `--roundtrip` (T-72) y `--dry-run` de `deploy-memory.py` y verificación por Bearer; el proyecto instalado no cambia (las opciones nuevas lo rechazan).

### T-72 — Ensayo aislado con `scripts/deploy-memory.py --project-name` y los tres componentes (CA-31)

- **Descripción**: Ensayo completo en proyecto Compose aislado con `memory-postgres`, `memory-api`, `memory-worker`, `memory-mcp`, `memory-web` y un proveedor de embeddings simulado: un cliente MCP escribe una observación, espera su indexado y la busca por kairos-mcp, sin que el servidor llame a ningún modelo de lenguaje. Fuente: CA-31, CA-30.
- **Changelog**: Un ensayo aislado recorre los tres componentes de punta a punta: el CLI escribe una observación por la entrada web y kairos-mcp, la encuentra por búsqueda y el servidor no llama a ningún modelo de lenguaje.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.29h (estimado) · real 0.03h (medido)
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 80 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-71
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `scripts/tests/test_rehearsal_three_components.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python scripts/deploy-memory.py --project-name kairos-three-t72 --api-port 18790 --web-port 15173 --dry-run` → lista fases y nombres `kairos-three-t72_*`
  - `python scripts/deploy-memory.py --project-name kairos-three-t72 --api-port 18790 --web-port 15173` → salida con `PASS` de la ida y vuelta y exit 0
  - `docker volume ls -q --filter name=knowledge-graphs_memory` antes y después → idéntico
  - Evidencia (2026-11-14): `python scripts/deploy-memory.py --project-name kairos-three-t72 --api-port 18790 --web-port 15173 --dry-run --embed-stub --roundtrip` → plan con las fases engine…verify, roundtrip y el servicio `embed-stub`, volúmenes `kairos-three-t72_*` (el comando del plan sin `--apply` ya era dry-run; no existía `--dry-run`, ahora es un sinónimo explícito). Ensayo: `python scripts/deploy-memory.py --apply --fresh --project-name kairos-three-t72 --api-port 18790 --web-port 15173 --secret-dir <temporal> --embed-stub --roundtrip` → exit 0, salida: `PASS roundtrip: {"chat_calls": 0, "embed_calls": 1, "found_layer": "episodic", "found_ref": "episodic:rehearsal:<item>:1", "hosts": {"foreign": 421, "ip": 200, "localhost": 200}, "receipt": ["event_id", "item_id", "jobs", "status", "version"], "server": "Kairos", "tools": 34}` y `PASS no language model: chat calls 0; embed calls 1`. Espía final `{"chat_calls": 0, "embed_calls": 1, "requests": 71}` (el resto, sondas de salud del proxy). `memory-mcp` solo en la red `kairos-three-t72_mcp`. Antes y después: `docker volume ls -q --filter name=knowledge-graphs_` (7 volúmenes) y `docker ps --filter name=knowledge-graphs` (4 contenedores) idénticos; 0 contenedores, redes, volúmenes e imágenes `kairos-three-t72` y `rehearsal-kairos-three-t72-*` al terminar; `.private/rehearsal-kairos-three-t72` y los secretos sintéticos borrados. `scripts/tests` 124 OK.

**Criterios de aceptación**
- [x] La observación escrita por kairos-mcp se encuentra por búsqueda tras el indexado
- [x] El servidor no hizo ninguna llamada a un modelo de lenguaje (espía en 0)
- [x] Ningún contenedor, volumen o red `knowledge-graphs-*` fue direccionado; el proyecto se elimina al terminar
- [x] La evidencia queda anotada en el ledger y junto al test, no en `testing/`
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Comprobar con `--dry-run` los comandos y nombres aislados
- [x] Ejecutar el ensayo con `--project-name kairos-three-t72` y puertos distintos de los reales
- [x] Anotar el resultado y limpiar
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-31/CA-30, R-09. Patrón: `scripts/deploy-memory.py:45-66` (validación de aislamiento y rechazo del nombre de la instalación) y `:460-472` (`--project-name`, `--dry-run`); `memory_platform/tests/test_deploy_isolation.py:29-48`. Nunca contra la instalación local. Clase: capacidad nueva (verificación de cierre). usage-meter three-components/T-72: 0.03 h IA (medido, win-ae5a2d8b43624918bd503ba948be354a). SALDA LA DEUDA DE LA FASE 6 (review.md, «Fase 6», hallazgo 5): hay una prueba CLI → nginx (`memory-web`, `/mcp`) → kairos-mcp real → `/v1` → PostgreSQL con procesos reales (`kairos mcp --url http://127.0.0.1:15173` lanzado desde `client/`), y la paridad de `allowed_hosts` con el `Host` que reenvía nginx se comprueba por petición: `127.0.0.1:15173` y `localhost:15173` → 200, `evil.example` → 421. Primer intento del ensayo: `remember` devolvió «Capture is disabled for this project» porque la política de captura por defecto es `off` (un proyecto nuevo no captura): el ensayo ahora fija `capture_mode: full` con `PUT /v1/projects/rehearsal/policy` (la creación del proyecto no la fija) y tolera el proyecto ya existente en un reintento. Corregido también (T-71): `verify_runtime` pasaba por sesión de portal, que `nginx` no reenvía a kairos-mcp. docs/operations.md documenta `--embed-stub`, `--roundtrip` y la verificación por Bearer; advierte de no usar `docker compose -p … down` desde la raíz porque el compose base fija los nombres `knowledge-graphs_inference|webui|mcp`. La limpieza se hizo por etiqueta/nombre del proyecto del ensayo, nunca con el compose base. Sin cambios visibles para clientes; despliegue: opciones nuevas del script (ver T-71).

### T-73 — Cierre: suite, `retrieval-eval` y manuales (CA-32)

- **Descripción**: Ejecutar la suite completa y `retrieval-eval` con los umbrales vigentes, regenerar los contratos y comprobar que los manuales describen los tres componentes y la retirada del MCP interno. Fuente: CA-32, cierre del plan director.
- **Changelog**: Los manuales de instalación y configuración explican ya los tres componentes (servidor, kairos-mcp y cliente) y la retirada del MCP interno en la 0.5.0, y la suite y la evaluación de recuperación pasan.
- **Estado**: completado
- **Cerrada**: 2026-11-14
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real 0.07h (medido)
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-72
- **Tipo**: test
- **Archivos**: `README.md`, `docs/architecture.md`, `docs/configuration.md`, `docs/operations.md`, `docs/install.md`, `docs/integration.md`, `docs/contracts/*.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t73 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build --target retrieval-eval -f server/memory_platform/Dockerfile -t kairos-eval:t73 .` → exit 0
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → sin diff
  - Evidencia (2026-11-14): `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t73 .` → `MEMORY_TEST_RESULT` passed true, tests 764, failures 0, errors 0, skipped 0, `llm_chat_calls` 0. `docker build --target retrieval-eval -f server/memory_platform/Dockerfile -t kairos-eval:t73 .` → exit 0, `RETRIEVAL_EVAL_RESULT` gate passed true, failures [], capa fusionada recall@5 1.0 (umbral 0.80) y MRR 0.9715 (umbral 0.60) sobre 72 consultas, `product_database_accessed` false. Contratos: la exportación en la imagen de pruebas (Python 3.11/3.12, no 3.13) de `memory-platform.openapi.json` es idéntica byte a byte (sin CR) a la versionada, y la de `kairos-mcp.json` es igual salvo el formato de los docstrings (esperado: la CI exporta con 3.13 y compara con `git diff --ignore-cr-at-eol`); `git status --short docs/contracts` vacío (sin cambios) y las pruebas aditivas contra `6008da0` y `23ced03` están en la suite. Manuales contra CA-32: README.md («Los tres componentes… 0.4.0»), docs/architecture.md («Tres componentes») y docs/integration.md («Migración: el MCP interno queda en desuso y se retira en la 0.5.0») y docs/operations.md ya los describían; docs/install.md no mencionaba kairos-mcp ni la retirada y docs/configuration.md no nombraba los tres componentes: ambos ganan un apartado/párrafo.

**Criterios de aceptación**
- [x] Suite con 0 fallos y 0 omitidos; `retrieval-eval` cumple recall@5 ≥ 0,80 y MRR ≥ 0,60
- [x] Los seis manuales describen los tres componentes y la retirada del MCP interno
- [x] Contratos regenerados sin diff y solo aditivos
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [x] Ejecutar suite y evaluación
- [x] Revisar los manuales contra CA-32
- [x] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Clase: verificación de cierre. usage-meter three-components/T-73: 0.07 h IA (medido, win-ba66daafe6bf47098080ea9eef8626f5). `docs/install.md` (CRLF conservado): sección «Los tres componentes y la ruta MCP» (el instalador sigue necesitando solo la dirección base y la clave; el MCP interno `:8790/mcp/` y `/memory-api/mcp/` se retira en la 0.5.0; reinstalar con `install --replace`). `docs/configuration.md`: párrafo de apertura con los tres componentes. Sin cambios en contratos ni visibles para clientes. La línea base del servidor de la imagen de pruebas sigue siendo 764 tests (759 + 5 de T-69).

### T-74 — Revisión final de la iniciativa

- **Descripción**: Revisión adversarial final de toda la iniciativa contra CA-01…CA-32 y las restricciones: contrato solo aditivo, migraciones aditivas, nada publicado, ningún recurso `knowledge-graphs-*` tocado, un solo secreto en CI (`GITHUB_TOKEN`), EOL conservado. Esta revisión es la más corta (3 h): se apoya en las revisiones de fase y reserva supervisión por encima del 25 % (R-06).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.44h (estimado) · real —
- **Supervisión**: est. 0.11h (≈25 % IA) · real —
- **Previsión IA**: 120 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-69 … T-73
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`, `docs/roadmap/2026-11-12-three-components/tasks.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python "C:/Users/46066917X/.claude/plugins/cache/daycry/custom-agents/3.3.0/agent-kits/shared/ledger-lint.py" docs/roadmap/2026-11-12-three-components/tasks.md` → exit 0
  - lectura: `review.md`, sección «Final», sin hallazgos Critical/Important abiertos

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Final» con una tabla CA-01…CA-32 → evidencia
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] El ledger no tiene tareas en estado distinto de `completado` o `cancelado` con motivo autorizado
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Recorrer los 32 criterios con su evidencia
- [ ] Cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro de `retrieval-quality`, plan director (cierre). No escribe en `testing/`.

---

## Revisión de dos lentes — intento 1: Fase 1 (CI) — workflow, higiene, verde y rojo comprobados, documentación (T-01, T-02, T-03, T-04, T-05, T-06, T-07)

Lentes: A+B+C (C por la ruta `.github/workflows/`; D no aplica). Puerta previa: `scope-check --base be2a948` exit 0. Los cinco trabajos ejecutaron de verdad sus suites en el run 43202850710 (483 tests, `gate.passed: true`, 90 tests del CLI, 65 del portal, 8 de contrato); el rojo de T-06 está probado en el run 43202864405. Repositorio privado; permisos `contents: read`, sin secretos ni publicación. La rama `ci-red-probe` la borró el orquestador con autorización del usuario (2026-11-12), después de que un hook se lo impidiera al implementer.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | `contracts` usa `git diff --exit-code`, que no ve ficheros sin seguimiento: un `git rm` de un contrato versionado, o un contrato nuevo sin versionar, deja el trabajo en verde | T-03 | corregido (intento 1): `git status --porcelain --untracked-files=all` sobre `docs/contracts` falla con `??` o borrados; nombre del paso corregido | Lentes A y B; `ci.yml:116-118`, reproducido en el scratchpad |
| 2 | Important | El paso «The suite really ran and nothing was skipped» no tiene test: borrarlo o debilitar `"failures": 0` deja los 16 tests en verde; tampoco compara `tests` con la línea base de 483 | T-01, T-05 | corregido (intento 1): 7 tests con mutantes protegen el paso; mínimo `KAIROS_MIN_TESTS: '483'` en `env:`; la CI imprime `tests=483 minimum=483` | Lente B (mutantes en memoria); Lente A; `test_ci_workflow.py:60-64`, `ci.yml:37-44` |
| 3 | Important | CA-01 pide verde «en el PR»; se cerró con un run `push` y el disparador `pull_request` nunca se ha ejecutado. La autorización del usuario consta solo en Notas, no en la spec ni en el plan | T-05, T-01 | corregido (intento 1, orquestador): la autorización del usuario (push sin PR, sin merges ni publicación) queda en la nota de CA-01 de `spec.md` y en la dependencia externa de `improvement-plan.md`; el `pull_request` se ejercita en T-65 | Lente A; `spec.md:157`, `tasks.md:198` |
| 4 | Minor | La puerta de higiene se evade: `toJSON(secrets)`, `permissions` ampliados, `gh release create`/`twine upload`, `${{ github.event.* }}` en `run:`, `--privileged` o el socket de Docker, `continue-on-error`, `\|\| true`, `if: false` | T-04 | corregido (intento 1): reglas nuevas con su caso negativo (32 tests) | Lentes B y C (CWE-532, 250, 693, 94); `test_ci_workflow.py:27-46`, `:110-122` |
| 5 | Minor | `actions/checkout` deja el `GITHUB_TOKEN` en `.git/config` (`persist-credentials` por defecto) | T-01..T-03 | corregido (intento 1): `persist-credentials: false` en los 5 checkouts | Lente C (CWE-522); `ci.yml:83-89`, `:107-112` |
| 6 | Minor | Acciones fijadas por etiqueta y no por SHA | T-01..T-03 | corregido (intento 1): `checkout`, `setup-node` y `setup-python` fijados por SHA con la etiqueta en comentario | Lente C (CWE-829); `ci.yml:31,68,84,108` |
| 7 | Minor | Notas de T-01 citan `--no-cache-filter` y «caché de capas», que T-05 retiró; criterios de usage-meter marcados [x] sin JSON en T-02..T-05; el paso de `contracts` dice «initiative base» pero compara con `contracts_base` (6008da0) | T-01..T-05 | corregido (intento 1): Notas de T-01 al día; criterio de usage-meter con «EXCEPCIÓN: sin JSON propio, tiempo (estimado)»; T-06 `completado` | Lentes A y B; `tasks.md:60,87,111,141,171,201`; `ci.yml:113` |

Referencias actualizadas tras las correcciones (intento 2, `fix2`; las celdas de la tabla no se reescriben): gap 1 `ci.yml:133-141`; gap 2 `test_ci_workflow.py:460-517` (suite-gate), `ci.yml:19,44-54`; gap 3 `spec.md:157`, `tasks.md:198`; gap 4 `test_ci_workflow.py:31-44,90-132` (reglas), `:588-638` (casos negativos); gap 5 `ci.yml:36-38,61-63,79-81,97-99,123-125`; gap 6 `ci.yml:36,61,79,82,97,100,123,126`; gap 7 `tasks.md:60,87,111,141,171,201`, `ci.yml:131`.

## Revisión de dos lentes — intento 2: Fase 1 (CI) — re-evaluación de las correcciones del intento 1 (T-01, T-03, T-04, T-05, T-06)

Lentes: A y B+C (una lente fresca para corrección y seguridad), re-evaluando solo las correcciones del intento 1. Verificados ✓: gaps 1 (contratos sin seguimiento o borrados, reproducido en repositorio de prueba), 3 (autorización de CA-01 coherente con el texto literal del usuario), 4 parcial, 5 (`persist-credentials: false` en los 5 checkouts), 6 (SHAs comprobados con `gh api`), 7, y T-06 `completado` (`ci-red-probe` no existe en local ni en el remoto). Runs 43205352926 y 43205872004: 5/5 trabajos en success, `tests=483 minimum=483`. `scope-check --base be2a948` exit 0. Ninguna puerta relajada.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | La protección del paso de la suite solo busca texto: borrar la comparación `test "${tests:-0}" -ge "$KAIROS_MIN_TESTS"`, cambiarla a `-ge 0`, añadir `\|\| :` o `\|\| exit 0`, comentar `grep -q '"skipped": 0'` o redefinir `KAIROS_MIN_TESTS: '0'` en el `env:` del trabajo deja los 32 tests en verde | T-01, T-05 | corregido (intento 2): test de comportamiento que ejecuta el `run:` del paso con `bash -e -o pipefail` sobre 13 logs sintéticos y resuelve `KAIROS_MIN_TESTS` con la precedencia de GitHub; tabla de 27 mutantes, todos detectados; `test_ci_workflow.py` corre ahora en el trabajo `contracts` («Ran 39 tests», run 43210843135) | Lentes A y B+C (mutantes en memoria); `test_ci_workflow.py:221-229`, `:251`, `:257`; `ci.yml:44-54` |
| 2 | Minor | `toJSON\(` distingue mayúsculas; las expresiones de GitHub no (`toJson(secrets)`, la forma documentada, pasa) | T-04 | corregido (intento 2): reglas sin distinción de mayúsculas | Lente B+C (CWE-532); `test_ci_workflow.py:89` |
| 3 | Minor | Evasiones abiertas de la higiene: `\|\| :`, `\|\| exit 0`, `set +e`, `if: ${{ false }}`, `continue-on-error: ${{ true }}`, `${{ github.head_ref }}` en `run:`, `--cap-add SYS_ADMIN`, `--pid=host` | T-04 | corregido (intento 2): evasiones cerradas con caso negativo; ninguna expresión `${{ github.* }}` o `${{ inputs.* }}` en `run:` (lista blanca vacía) | Lente B+C (CWE-693, CWE-94, CWE-250); `test_ci_workflow.py:31-32`, `:98` |
| 4 | Minor | Las referencias `fichero:línea` de la tabla del intento 1 apuntan a líneas anteriores a las correcciones | — | corregido (intento 2): línea «Referencias actualizadas tras las correcciones» bajo la tabla del intento 1 | Lente A; tabla del intento 1 |
| 5 | Minor | El criterio de usage-meter dice «JSON (medido, en Notas)» y en Notas solo está la cifra; T-05 atribuye su medición al bloque de T-01, que no la incluye | T-02..T-05 | corregido (intento 2): la excepción dice «solo la cifra medida de 0,13 h, sin JSON»; T-05 estimada (null) | Lente A; `tasks.md:111,141,171,201,209` |

## Revisión de dos lentes — intento 3: Fase 1 (CI) — re-evaluación de las correcciones del intento 2 (T-01, T-04, T-05)

Lentes: A+B+C en una sola lente fresca, re-evaluando solo las correcciones del intento 2. Verificados ✓: gap 1 (39 tests en local con Git bash; mutantes nuevos `GITHUB_ENV`, `-gt` y `exit 0` detectados; `grep -c` equivalente; leer otro log falla en cerrado; en Linux no se salta en silencio), gaps 2 y 3 (sin falsos positivos sobre el workflow actual), gap 4 (`tasks.md:2359`), gap 5 (ventanas fix2 con el mismo inicio: «compartida, no sumar» es honesto). Run 43210843135 sobre 6abc193: 5/5 trabajos en success, «Ran 39 tests» en `contracts`, `tests=483 minimum=483`. `scope-check --base be2a948` exit 0. Sin gaps Critical ni Important: **la Fase 1 cierra**. Informe: `review.md`.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Minor | El test no resuelve `defaults.run.shell` del trabajo: `shell: bash {0}` a nivel de trabajo deja el paso sin `-e` y los 39 tests siguen en verde | T-01 | deuda aceptada → Iniciativa 9 o la próxima fase que toque `ci.yml` | `test_ci_workflow.py:388`, `:199-200` |
| N2 | Minor | `env_dict` solo reconoce claves sin comillas: `"KAIROS_MIN_TESTS": '0'` en el `env:` del trabajo sobrevive | T-01 | deuda aceptada → ídem | `test_ci_workflow.py:272-286`, `:326` |
| N3 | Minor | Un `echo` de un `MEMORY_TEST_RESULT` falso añadido al log tras el build engaña a la puerta (CWE-693) | T-01 | deuda aceptada → ídem | `ci.yml:43`; `test_ci_workflow.py:357-361` |
| N4 | Minor | Evasiones restantes de la higiene: `set +eu`, `\|\| echo x`, pasos en mapa en línea con `continue-on-error`/`if`, `if: ${{ 0 }}`/`null`/`''`/`1 == 2`, `docker run -v /:/host`, `--security-opt seccomp=unconfined` (CWE-693, CWE-250) | T-04 | deuda aceptada → ídem | `test_ci_workflow.py:38,40-41,93-98` |
| N5 | Minor | Falso positivo: `if: github.event.pull_request.draft == false` se rechaza como «if disabled» (no afecta al workflow actual) | T-04 | deuda aceptada → ídem | `test_ci_workflow.py:94` |

## Revisión de dos lentes — intento 1: Fase 2 (servidor sin modelo de lenguaje) — lentes A+B+C+D (T-09, T-10, T-11, T-12, T-13, T-14, T-15, T-16)

Veredicto: **1 Important abierto** → vuelve al implementador (intento 2 de 3). Lentes: A+B+C+D (C por `docker-compose.yml` y `memory_platform/Dockerfile`; D por `memory_platform/worker.py`). A: todos los criterios de T-09..T-16 ✓ con evidencia; scope-check 0 fuera; contrato 34 herramientas sin diff. C: sonda propia del proxy (`kairos-proxy-lensc`, 19 peticiones × 5 valores de `OLLAMA_ALLOW_CHAT`), sin hallazgos. D: sin hallazgos (los `extract` heredados fallan una vez, no reintentables; consulta de fallidos sigue en el índice parcial).

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | `memory_platform/tests/e2e_fixture.py:38-40` asume que un evento con `generate` crea trabajo; con la extracción apagada por defecto `jobs == []` e `IndexError`: el fixture del e2e del portal (`Dockerfile.e2e`) no arranca y desaparece el trabajo `failed` sintético | T-09 | corregido (de1e229) | Lente B, traza `store.py:19` → `test_store.py:39` → `store_ingest.py:187` |
| 2 | Minor | El espía de `/api/chat` solo ve los tests que usan `Settings.from_env()`; `run_postgres.py` lo describe como «any call fails the run». La garantía de CA-18 la da `test_no_llm` | T-15 | corregido (4dabeba) | Lentes A y B: `run_postgres.py:54-60`, `config.py:227` |
| 3 | Minor | Con `MEMORY_CORPUS_ANSWER=off`, reintentar `corpus_answer` con un `request_id` ya guardado responde `corpus_answer_disabled` en vez de leer la operación | T-11 | corregido (3be1f57) | Lente B: `corpus_answers.py:248-250`, `corpus_answer_tools.py:24` |
| 4 | Minor | `/api/embed` acepta cualquier `model`, incluidos modelos `:cloud` del Ollama del host; no lo introduce este diff (antes todo estaba abierto) y el origen es la red interna | T-13 | deuda aceptada (Iniciativa 5, despliegue) | Lente C |
| 5 | Minor | `test_fts_language.py:70,85`: la línea nueva va delante del docstring, que deja de serlo | T-09 | corregido (de1e229) | Lente A (fuera de lente) |
| 6 | Minor | Trabajos `extract` en estado `unknown` reintentados: confirmar que el worker los cierra con `extraction_disabled` | T-10 | verificado, sin cambio de código; test añadido (52e596e) | Lente A (fuera de lente), `store_jobs.py:77` |

Verificación de las correcciones: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p2fix .` → MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 528} sobre 4dabeba (3 tests nuevos). Gap 4 queda como deuda aceptada, sin tocar.

## Revisión de dos lentes — intento 2: Fase 2 (servidor sin modelo de lenguaje) — correcciones del intento 1 (T-09, T-10, T-11, T-15)

Veredicto: **sin Critical ni Important**. Lentes: A y B (B con la comprobación de autorización de T-11; `review-lens-select --base 0f17106` no activa C ni D). Las cinco correcciones del intento 1 están verificadas: A reconstruyó la suite (`MEMORY_TEST_RESULT` 528, 0 skipped, `llm_chat_calls` 0) y `scope-check --base 31d288d` da exit 0; B reprodujo los caminos en un contenedor aislado (`kairos-lensb2-probe`, 22 tests OK). Sin hueco CWE-639: `status` filtra por `actor_id` y `corpus_id`. CI de las correcciones: run 43233832269 sobre 7ccb41f, 5 trabajos en verde.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | Con `MEMORY_CORPUS_ANSWER=off`, reutilizar un `request_id` con otra pregunta o sesión devuelve la respuesta guardada como `completed`, sin comparar `request_hash` (encendida da `Conflict`) | T-11 | corregido (ec7e750) | Lente B: `corpus_answers.py:251-252` frente a `:164-174`, probe `lb2/probe_lb2.py` |
| 2 | Minor | El test de acceso denegado usa un actor inexistente (`Unauthorized` 401) y no prueba el aislamiento entre actores con permiso sobre el proyecto | T-11 | corregido (ec7e750) | Lentes A y B: `test_corpus_answers.py:339-341` |
| 3 | Minor | La documentación dice que con `off` toda llamada falla; ahora un `request_id` guardado se lee | T-11 | corregido (ec7e750) | Lente A: `docs/corpus-generated-answers.md:14-17`, `docs/configuration.md:26,38`, `CHANGELOG*.md:14` |
| 4 | Minor | El run de CI de las correcciones no constaba en el ledger | T-09..T-15 | corregido (este veredicto) | run 43233832269 |

## Revisión de dos lentes — intento 3: Fase 2 (servidor sin modelo de lenguaje) — correcciones Minor del intento 2 (T-11)

Veredicto: **sin Critical ni Important; la Fase 2 cierra en el intento 3 de 3**. Lentes: A+B en un solo revisor (C y D no aplican al diff `7ccb41f..8e933e8`). La huella de `_stored` es una copia literal de la de `_reserve`; la autorización no se debilita y un actor ajeno recibe `corpus_answer_disabled` exista o no el `request_id`. `scope-check --base 31d288d` exit 0. Suite: `MEMORY_TEST_RESULT` 529, 0 skipped, `llm_chat_calls` 0 (ec7e750); CI run 43240152321 en verde.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | Con `off`, la huella del reintento incluye `MEMORY_LLM_MODEL`; si el operador lo vacía o cambia al apagar, repetir la misma petición da `Conflict` en vez de la respuesta guardada. Sin pérdida de datos: `corpus_answer_status` la lee | T-11 | deuda aceptada en el código; la documentación (`docs/corpus-generated-answers.md`, `docs/configuration.md`, `CHANGELOG*.md`) lo dice y remite a `corpus_answer_status` (commit de cierre de la fase) | `corpus_answers.py:250-251`, `test_corpus_answers.py:332`; recálculo de `digest` con modelo `''` frente a `synthetic-model`: distinto |

## Revisión de dos lentes — intento 1: Fase 3 (paridad REST /v1) (T-18, T-19, T-20, T-21, T-22, T-23, T-24, T-25, T-26)

Veredicto: **1 Important abierto** → vuelve al implementador (intento 2 de 3). Lentes: A, B (con rendimiento: D se activó solo por la ruta `scripts/export-contracts.py`) y C (forzada por el orquestador: endpoints nuevos con autorización). A: T-18..T-26 ✓; `openapi-lint --diff` 0 rompedores; contrato MCP idéntico a 33fd830 sin `x-kairos-endpoint`; línea base 23ced03 idéntica byte a byte; suite reproducida (573, 0 skipped). C: sin IDOR, sin enumeración por 404/403, sin SQLi. B: sin N+1 ni conflictos de enrutado.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | `x-kairos-endpoint` no describe cómo se traducen los argumentos; el exportador dice «by name» y es falso: `includeClosed` (se ignora en silencio y omite tareas cerradas), `dateStart`/`dateEnd` (422 por `extra=forbid`), `types` como cadena, `expected_version` opcional/0 en `rebuild_corpus` (422), `project` en query como `project_id` en `get_tool_uses`, `jobId`→`{job_id}`, `event`/`document` envueltos, regla `complete` de `without_project_id`. El test de paridad escribe la petición REST a mano y no lo caza. Bloquea la Fase 5 (kairos-mcp traduce desde el contrato) | T-24, T-25 | corregido (16539ea) | Lente B (`export-contracts.py:13-14,28,31,39,46`, `app.py:213,279`, `models.py:63`; app FastAPI mínima: `?includeClosed=true` → 200 con `False`); Lente A gap 3 (`test_tool_endpoint_parity.py:247`) |
| 2 | Minor | Fechas extremas válidas (`0001-01-01T00:00:00+01:00`, `9999-12-31T23:59:59-01:00`) lanzan `OverflowError` no capturado → 503 en vez de 422 | T-18 | corregido (16539ea) | Lente B: `agent_store.py:144-149` |
| 3 | Minor | Paridad trivial de `get_tool_uses` (sin eventos PostToolUse sembrados, `items` vacío) y `corpus_answer_status` comparado solo en la ruta de error | T-25 | corregido (16539ea) | Lente A: `test_tool_endpoint_parity.py:162,171,238-240` |
| 4 | Minor | Un corpus con `/` en el nombre no se alcanza por `POST …/corpora/{name}/query` (404; por MCP sí). Mismo patrón que ya tenían prime, rebuild y answers | T-22 | corregido (16539ea) | Lente B: `app.py:301` |
| 5 | Minor | Las lecturas REST de observaciones no tienen el tope de bytes de la herramienta MCP (32 KB / 256 KB); CWE-770 | T-21 | deuda planificada: el presupuesto de bytes lo aplica kairos-mcp (T-41..T-44, `mcp/kairos_mcp/budget.py`); la paridad exacta se mantiene mientras no haya truncado | Lente C: `app.py:250-266`, `agent_tools.py:15-27,44-47` |

## Revisión de dos lentes — intento 2: Fase 3 (paridad REST /v1) — correcciones del intento 1 (T-18, T-22, T-24, T-25)

Veredicto: **1 Important abierto** → vuelve al implementador (intento 3 de 3, el último). Lentes: A y B (B con la comprobación de seguridad del enrutado `{name:path}`; el selector no activa C, y D solo por la ruta `scripts/export-contracts.py`). A: las 33 herramientas remotas tienen regla para cada argumento y cuadran con `app.py`/`models.py`; contrato idéntico a 33fd830 y 23ced03 salvo `x-kairos-*`; OpenAPI byte a byte igual; suite reproducida (591, 0 skipped, `llm_chat_calls` 0); `scope-check --base 33fd830` exit 0. B: sin conflictos de sufijo ni fuga entre actores (14 URL de borde con FastAPI 0.141.1/Starlette 1.6.0); `OverflowError` cubierto en REST y MCP. CI de las correcciones: run 43263594083 sobre 606c305, 5/5 en verde.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | `rebuild_corpus` sin `expected_version`: `when_absent` toma la versión de `list_corpora`, que corta en 100 corpus, y no dice qué hacer si el nombre no aparece (la herramienta da 404). Con un rebuild concurrente entre lectura y POST, REST da 409 y la herramienta no. CA-06 diverge | T-24, T-25 | corregido (9030645): endpoint de lectura por nombre `GET …/corpus?name=`, 404 = NotFound de la herramienta, reintento declarado en el contrato; tests con corpus fuera de la primera página, nombre inexistente, `null`, 0 y la carrera | Lente A (`export-contracts.py:73-75`, `agent_store.py:242-243`, `test_tool_endpoint_parity.py:217-218`); Lente B gaps 2 y 3 |
| 2 | Minor | La gramática de `without_project_id` (`for_each`, `result.from`, `all_of`, `each`/`path`/`is`/`is_not`) no está en `x-kairos-translation`; el paso `jobs` no dice que cada elemento va a `{job_id}` (el test lo hace a mano); `expected_version: null` frente a «omitted» ambiguo | T-24 | corregido (9030645): `x-kairos-translation` documenta la gramática y `null` = omitido; `jobs` lleva `args: {job_id}` y el test dejó el `.replace` | Lente A: `export-contracts.py:52,94-99`, `test_tool_endpoint_parity.py:229` |
| 3 | Minor | `expected_version: 0` no traducible (herramienta 409, REST 422) solo está en el exportador y el ledger, no en el contrato JSON | T-24 | corregido (9030645): `untranslatable` en `rebuild_corpus` con la respuesta 409 «Corpus version changed» y caso de paridad `rebuild_corpus_zero` | Lente A |
| 4 | Minor | Faltaba el run de CI de las correcciones en el ledger | T-24, T-25 | corregido (este veredicto) | run 43263594083 |
| 5 | Minor | El nginx del portal (`location /memory-api/`, `proxy_pass` con URI) decodifica `%2F` y resuelve `//` y `..`: nombres de corpus como `a/../b` llegan como `b` (solo dentro del mismo actor; por `/v1/` llegan intactos). Antes daban 404 | T-22 | corregido (9030645): `/memory-api/` reescribe `$request_uri` y pasa la URI sin normalizar; sonda `nginx_portal_probe.py` (15 casos) y test estático `test_nginx_portal.py` | Lente B: `memory_platform/nginx.conf`, `web/src/memory-api.ts:36`; probado con `kairos-web` y un eco |
| 6 | Minor | El exportador con Python 3.11 (el de la imagen) genera `description` sin dedent y no coincide con el `kairos-mcp.json` comiteado (generado con 3.13): la regeneración no es reproducible en la imagen | T-24 | descartado (rebatido): el trabajo `contracts` de la CI fija Python 3.13 (`.github/workflows/ci.yml:128`) y regenera con `scripts/export-contracts.py` (`:135`); la regeneración es reproducible donde se comprueba. La imagen de test no regenera contratos | Lente A (fuera de lente) |

## Revisión de dos lentes — intento 3: Fase 3 (paridad REST /v1) — correcciones del intento 2 (T-22, T-24, T-25)

Veredicto: **sin Critical ni Important; la Fase 3 cierra en el intento 3 de 3**. Lentes: A+B en un revisor y C (el selector la activa por `memory_platform/nginx.conf`; D solo por la ruta del exportador, cubierta en A+B). A+B: la lectura por nombre resuelve el corte de 100, el NotFound y la carrera (las versiones solo crecen; `only_if_value_changed` separa el 409 real del de carrera); contrato idéntico a 33fd830 salvo `x-kairos-*`; OpenAPI solo añade `/corpus`; `scope-check --base 33fd830` exit 0; CI 43421685383 y 43422142841 en verde (5/5). C: 54 peticiones crudas contra el nginx fijado (1.31.6) con la conf nueva y la de 606c305: sin smuggling, sin inyección de cabeceras, sin traversal; `/metrics` cerrado en todas las grafías; `/v1/`, `/mcp` y `/health/ready` idénticas. Suite tras las correcciones del orquestador: 609, 0 skipped, `llm_chat_calls` 0.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | La lectura previa de `rebuild_corpus` invierte el orden de errores de la herramienta: clave de solo lectura con nombre inexistente → REST 404, herramienta 403 | T-24 | deuda aceptada (los casos con éxito coinciden; afecta solo al código de error) | Lente A+B: `agent_store.py:249-255` frente a `:223,288` |
| 2 | Minor | Nombre en blanco, de más de 200 bytes o con NUL en `GET …/corpus` → 404 o 503 en vez del 422 de la herramienta | T-24 | corregido (commit de cierre): `corpus_receipt` valida el nombre con `text()` como la herramienta; test con NUL, blanco y `'é'*150` → 422 | Lente A+B: `agent_store.py:253`, `app.py:117-120` |
| 3 | Minor | `GET …/corpus` aceptaba una clave con solo `write`; ninguna otra operación de corpus lo permite (CWE-863) | T-24 | corregido (commit de cierre): exige `read`; test con clave `['write']` → 403 `forbidden` | Lente C: `agent_store.py:249-252` |
| 4 | Minor | El access log `safe` guardaba la query string de `/memory-api/` (el `rewrite` mete `?args` en `$uri`) (CWE-532) | T-22 | corregido (commit de cierre): `map $request_uri $safe_path` sin query; test estático en `test_nginx_portal.py` | Lente C: `nginx.conf:7,48`, comprobado en el log |
| 5 | Minor | `untranslatable` de `expected_version: 0` responde 409 sin llamar, aunque la herramienta daría 404/403/422 según corpus y permiso | T-24 | deuda aceptada (caso degenerado: la herramienta tampoco puede tener éxito) | Lente A+B: `export-contracts.py:81-83` |
| 6 | Minor | `max:3` deja un caso (cuatro rebuilds que cambian el contenido entre lectura y POST) en que la herramienta tiene éxito y REST da 409; no documentado | T-24 | deuda aceptada (para kairos-mcp, T-41..T-44, que puede documentarlo o elevar el tope) | Lente A+B: `kairos-mcp.json` 2042-2047 |
| 7 | Minor | Tests que prometen más de lo que comprueban: `…hides_other_actors` sin segundo actor; `perform` no lee `reread`/`only_if_value_changed`; el 409 real solo con servidor guionizado | T-25 | deuda aceptada (para T-47/T-48, la cadena completa MCP→REST) | Lente A+B: `test_tool_endpoint_parity.py:494-500,131-161` |
| 8 | Minor | El ledger no recogía el run 43422142841 | T-24, T-25 | corregido (este veredicto) | `gh run view`: 5/5 en verde |
| 9 | Minor | Rutas que antes se normalizaban (`/x/../memory-api/...`, `//memory-api/...`) ahora dan 400 | T-22 | aceptado: cambio funcional deliberado, sin impacto de seguridad; el portal no genera esas rutas | Lente C (fuera de lente) |

## Revisión de dos lentes — intento 1: Fase 4 (esquema de observación) (T-28, T-29, T-30, T-31, T-32, T-33, T-34)

Veredicto: **2 gaps bloqueantes (1 Critical, 1 Important); vuelve al implementer**. Lentes: A+B en un revisor y C (activada por `memory_platform/Dockerfile`). A: todos los criterios de T-28..T-34 ✓ salvo la doc de T-34 (gaps 2 y 5); contrato MCP con 34 herramientas, +42/-0; OpenAPI +13/-0; sin migraciones. `scope-check --base 3f15c0d` exit 0.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Critical | DoS por `uniqueItems` cuadrático (CWE-407/400): `iter_errors` evalúa `uniqueItems` sobre el array entero aunque supere `maxItems`; con tipos mezclados compara todos los pares. 8 000 elementos (39 KB) → 184 s de CPU con una clave `write` | T-30, T-31 | corregido en fd80bd0: `_oversized_array` recorre el documento en tiempo lineal y rechaza todo array mayor que el mayor `maxItems` de los esquemas (50, leído de ellos) con `maxItems` y la ruta (claves desconocidas como `*`), antes de `iter_errors` | Lente C: `schemas.py:63`; `observation.v1.schema.json` (`concepts`, `files_read`, `files_modified`); medido con jsonschema 4.26.0 |
| 2 | Important | `remember` y `POST /v1/events` guardan `payload.structured` sin validarlo, aunque el contrato (`kairos-mcp.json:605`) y `docs/integration.md` dicen que se valida | T-31, T-34 | corregido en 0d4c90e: `Store.ingest_event` valida `structured` antes de cualquier escritura (punto común de `/v1/events`, `remember`, observaciones); no hay más inserciones de eventos en la ingesta (la otra `INSERT INTO memory.events` es la generada por el worker, sin payload de cliente) | Lentes A+B y C: `app.py:343-345`, `mcp.py:75-84`, `store_ingest.py:95-140` |
| 3 | Minor | La extracción LLM opcional envía `Payload.model_json_schema()` como `format`, ahora con `structured` abierto; si el modelo lo emite, `_materialize_extract` lo guarda sin validar | T-31 | corregido en a7f617a y 0d4c90e: `extraction_format()` quita `structured` del `format`, el resultado del modelo lo excluye y `_materialize_extract` lo descarta | Lente A+B: `providers.py:75,80,88`, `store_ingest.py:58-85` |
| 4 | Minor | `sanitize_payload` no limpia `structured`: un `<private>` ahí rechaza el evento (422 `sensitive_source_requires_review`) en vez de redactarse; la doc promete «las mismas reglas» | T-34 | corregido en 1bd3b54: opción simple y segura, la doc dice que `structured` no se redacta y que un dato sensible dentro rechaza el evento (422 `sensitive_source_requires_review`); test que lo fija (0d4c90e) | Lente A+B: `privacy.py:143-163,184-201` |
| 5 | Minor | Esquemas cargados en la primera petición: si faltan, el servidor arranca sano y responde 503 en caliente | T-30 | corregido en 0d4c90e: `schemas.load_all()` en `create_app` (el worker no usa los esquemas); test con `MEMORY_SCHEMA_DIR` vacío | Lente A+B: `schemas.py:30-35` |
| 6 | Minor | Dependencias transitivas de `jsonschema` (`attrs`, `jsonschema-specifications`, `referencing`, `rpds-py`) sin fijar (CWE-1357) | T-30 | corregido en 1bd3b54: `attrs==26.1.0`, `jsonschema-specifications==2025.9.1`, `referencing==0.37.0`, `rpds-py==2026.9.1` (versiones de `pip list` en la imagen) | Lente C: `requirements.txt:7` |

### Corrección del intento 1 (implementer, 2026-11-13; el veredicto no cambia, T-35 sigue abierta)

RED: `test_observation_schema.LimitTests.test_a_huge_array_is_rejected_in_linear_time_before_uniqueItems_runs` falló con `AssertionError: 97.35 not less than 1.0 : concepts`; en la imagen sobre HEAD 28ee9e4 con los tests nuevos fallaron además 6 tests: `StructuredIngestRouteTests` (`/v1/events` y `remember` aceptaban `structured` inválido, array enorme, arranque sin esquemas, `structured` del modelo guardado), `test_extraction_never_offers_nor_keeps_structured` (`'structured' unexpectedly found` en el `format`) y `test_the_array_bound_is_the_largest_maxItems_of_the_schemas` (`AttributeError`) · 2026-11-13.

- Evidencia: `docker build --no-cache --target test -f memory_platform/Dockerfile -t kairos-test:i2p4fix1 .` → `MEMORY_TEST_RESULT` tests 638, failures 0, errors 0, skipped 0, `"passed": true`, `llm_chat_calls` 0. Puerta offline (`--network=none -e MEMORY_RETRIEVAL_EVAL=1`) → exit 0, `gate.passed` true. Contratos sin cambios (el esquema de `Payload` no cambia; `test_contract_additive` verde en la suite).
- Mediciones (usage-meter, ventana solapada, no sumar): `T-30-fix1` 0,24h (medido), `T-31-fix1` 0,03h (medido), `T-34-fix1` 0,03h (medido).
- Decisión gap 4: documentar el rechazo en lugar de redactar. Redactar `structured` cambiaría un documento ya validado (podría romper límites o `facts` literales) y obligaría a revalidar; el rechazo es lo más simple y seguro y no pierde datos sensibles en silencio.
- Decisión gap 1: un array mayor que el mayor `maxItems` se rechaza aunque esté bajo una clave desconocida (la regla que se informa es `maxItems`, no `additionalProperties`); es una cota de tamaño, no de esquema.
- Cambio visible para clientes MCP: ninguno en herramientas ni contrato (34 herramientas). `remember` ahora responde error 422 `invalid_observation` si `payload.structured` no cumple su esquema (antes lo guardaba); un array de más de 50 elementos dentro de `structured` se rechaza con `maxItems`.

## Revisión de dos lentes — intento 2: Fase 4 (esquema de observación), correcciones (T-30, T-31, T-34)

Veredicto: **sin Critical ni Important; la Fase 4 cierra en el intento 2 de 3**. Lentes: A+B y C en un revisor (C forzada: el Critical del intento 1 era de seguridad; el selector no la activaba sobre 28ee9e4..HEAD). Los 6 gaps del intento 1, cerrados: `_oversized_array` recorre el documento en tiempo lineal antes de `iter_errors`; `Store.ingest_event` valida antes de cualquier escritura y es el punto común de todas las rutas (la otra inserción en `memory.events` es la del worker, sin payload de cliente); extracción sin `structured`; esquemas cargados en `create_app`; transitivas fijadas (`pip check` limpio). Contrato sin cambios en 28ee9e4..HEAD. CI 43447573957 en verde. Suite tras el cierre: 639, 0 skipped, `llm_chat_calls` 0.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Minor | Coste superlineal acotado: la cota de arrays es global (50) y `uniqueItems` sigue comparando pares de elementos grandes no ordenables; 50 listas de 49×49 enteros (240 KB) → 2,38 s de CPU, de 6 a 12 veces un evento legítimo (CWE-407) | T-30 | corregido (commit de cierre): `MAX_NODES = 1000` valores por documento antes de jsonschema, 422 `maxNodes` en la raíz (un documento en todos sus límites tiene 189); test con el caso del revisor < 1 s (RED: 3,86 s con el código anterior) | Lente C: `schemas.py:85,113` |
| N2 | Minor | La doc prometía siempre `sensitive_source_requires_review` y que los `facts` se redactan; un `<private>` sin cerrar da `invalid_private_block`, un PEM incompleto `invalid_private_key_block` y un `fact` con secreto se descarta | T-34 | corregido (commit de cierre): `docs/integration.md` nombra los tres códigos, el descarte de `facts` y el límite `maxNodes` | Lente A+B: `privacy.py:65,127,150-160` |

## Revisión de dos lentes — intento 1: Fase 5 (kairos-mcp) (T-36, T-37, T-38, T-39, T-40, T-41, T-42, T-43, T-44, T-45, T-46, T-47, T-48, T-49)

Veredicto: **4 gaps Important, sin Critical; vuelve al implementer**. Lentes: A, B, C y D (C por `ci.yml`, `docker-compose.yml`, `mcp/Dockerfile`, `mcp/kairos_mcp/auth.py`, `memory_platform/Dockerfile`; D por `translate.py`, `auth.py`, `export-contracts.py`). A: todos los criterios de T-36..T-49 ✓; contrato idéntico a 7f464bd salvo `x-kairos-*`; copia de `mcp/contract/` idéntica; deudas de la Fase 3 resueltas. B: suite 727 y 99 de mcp/ en verde (`kairos-test:i2p5revb`). C: credencial solo hacia `KAIROS_API_URL`, sin fugas en logs ni errores, compose `internal`, CI con `contents: read` y acciones por SHA. `scope-check --base 7f464bd` exit 0.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | Cada `tools/call` recompila el JSON Schema de entrada (`validate_input=True` → `jsonschema.validate` con `check_schema`): 40-56 ms de CPU síncrona en `remember`/`observation_add` en el event loop de un solo worker; provocable con cualquier `Bearer` y argumentos inválidos, sin llegar a /v1 (CWE-400) | T-41..T-44 | corregido en a30a02e: `Checks` (`tools.py`) compila el esquema de cada herramienta una vez al construir el servidor (`validator_for` + `check_schema` + instancia) y `call_tool(validate_input=False)` valida con ella; mismo texto `Input validation error: <best_match>` que el SDK (comprobado en las 34 herramientas). Test: `PrecompiledValidationTests` (0 llamadas a `jsonschema.validate` y a `check_schema` por petición) | Lente D: `mcp/kairos_mcp/tools.py:45`; medido 38-56 ms frente a 0,01-0,2 ms precompilado |
| 2 | Important | Un UUID en mayúsculas, sin guiones o con llaves no se encuentra por kairos-mcp (404) y sí por el MCP interno, que normaliza con `UUID` | T-41 | corregido en a30a02e y 60936d6: kairos-mcp parsea los argumentos `format: uuid` (los lee del contrato, sin nombres de herramienta) con un modelo pydantic `<herramienta>Arguments` y envía la forma canónica en minúsculas; un UUID inválido da el texto del MCP interno (comprobado en cadena contra él). Además `/v1/events/{id}` y `/v1/projects/{p}/documents/{id}` aceptan cualquier forma de `uuid.UUID` (`canonical_id` de `app.py`; un valor que no es UUID sigue sin encontrarse, mismo 404) para cualquier cliente REST; `revoke` ya normalizaba. Tests: mayúsculas, sin guiones, llaves y `urn:uuid:` por la cadena (`test_chain_review1.py`) y en el stub (`test_review1.py`) | Lente B: `translate.py:55`; `mcp.py:113,130`; `app.py:350,368` |
| 3 | Important | Una respuesta de /v1 de más de 8 MiB (p. ej. `get_observations` con 90 observaciones de 100 000 caracteres) da «Memory service temporarily unavailable» de forma determinista, en vez de recortarse con marcador como en el interno | T-40, T-42 | corregido en a30a02e: el tope de respuesta de `/v1` sube de 8 a 96 MiB (lo máximo que el servidor produce: `observation_search` con 200 observaciones de 100 000 caracteres × 4 bytes = 80 MB) y la respuesta se recorta con el marcador por el presupuesto de bytes de su herramienta, como en el interno. Test: 90 observaciones de 100 000 caracteres (9 MiB) → resultado con marcador y ≤ 262 144 bytes | Lente B: `client.py:10,64` |
| 4 | Important | `GET /v1/projects/{p}/corpus` exige ahora `write`: una clave de solo lectura ya no puede leer su corpus (antes 200, ahora 403); el comentario dice lo contrario y no está documentado. El orden de errores de `rebuild_corpus` debe resolverse en la traducción, no en el endpoint de lectura | T-42 | corregido en 60936d6 y a30a02e: `corpus_receipt` vuelve a pedir solo `read` (como la Fase 3; test: claves `['read']` → 200, `['write']` → 403, `['read','write']` → 200). El orden de errores de `rebuild_corpus` se resuelve en la traducción, solo con claves `x-kairos-*`: `when_absent.send_instead_on_status` ({404, 422} → la petición va con la versión 2147483646, que ningún corpus tiene) y `untranslatable.send_instead` (0 → 2147483646), de modo que el endpoint de reconstrucción responde 403/422/404 en el orden de la herramienta y, para un corpus del actor, `Corpus version changed` sin reconstruir. Equivale a la herramienta para claves `read`, `write` y `read+write`, con y sin versión (paridad y cadena) | Lentes A y C: `agent_store.py:246,253` |
| 5 | Minor | `.` o `..` en un argumento de ruta se normaliza como segmento de punto y la petición va a otra ruta de /v1 (siempre con la credencial del llamante; hoy 404/405) (CWE-22/20) | T-41..T-44 | corregido en a30a02e: `segment()` codifica `.` y `..` como `%2E`; tests en el stub (`/v1/jobs/%2E%2E`) y en cadena (404 igual al interno) | Lentes B y C: `translate.py:55-56` |
| 6 | Minor | `initialize` y `tools/list` responden a cualquier `Bearer`; el MCP interno valida la credencial antes (CWE-306) | T-37, T-39 | corregido en a30a02e: `RequireBearer` comprueba la credencial con `GET /v1/auth/me` en cualquier POST que no sea `tools/call` (`initialize`, `tools/list`, `ping`, notificaciones, lotes) y `important_workflow` hace la misma comprobación; 401 solo si la API responde 401 (una API caída no rechaza). `tools/call` no paga ninguna petición extra. Tests: stub y cadena (clave desconocida → 401 en ambos MCP) | Lente C: `auth.py:44-51` |
| 7 | Minor | `httpx.AsyncClient` con `trust_env=True`: un proxy inyectado por Docker recibiría el Bearer (CWE-522) | T-37 | corregido en a30a02e: `httpx.AsyncClient(..., trust_env=False)`; test con `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` en el entorno (sin montajes de proxy y `trust_env` falso) | Lente C: `client.py:43` |
| 8 | Minor | La doc afirma igualdad con el interno que no se da: kairos-mcp añade `structuredContent` en las 12 herramientas de `mcp.py` y su 401 no lleva `request_id` ni `X-Request-ID` | T-37, T-49 | corregido en 2c5d8fc: se documentan las diferencias exactas (`mcp/README.md`, `docs/integration.md`): `structuredContent` también en las 12 herramientas básicas y 401 sin cabecera `X-Request-ID` (mismo cuerpo, `request_id` vacío); no se igualan (cambiaría el contrato de salida del MCP interno). Se documentan además la normalización de argumentos, la comprobación de credencial y el nuevo tope | Lente A: `mcp/README.md:34,51`; `budget.py:12-13`; `errors.py:16` |
| 9 | Minor | Orden de errores de `rebuild_corpus` con nombre inválido: clave de solo lectura y `name: "  "` → herramienta 403, cadena 422 | T-42 | corregido en 60936d6 y a30a02e: mismo mecanismo que el 4 (lectura 422 → versión 2147483646): con clave de solo lectura el nombre `  `, con NUL o de 150 caracteres da el 403 de la herramienta; con escritura, el error del nombre. Tests: paridad y cadena (`test_the_order_of_errors_for_a_blank_or_invalid_name…`, 3 tipos de clave × 3 nombres × 3 versiones) | Lente A: `agent_store.py:251-253` frente a `:283-284` |
| 10 | Minor | Enteros con forma float (`20.0`, `0.0`): en query viajan como `"20.0"` (422) y `untranslatable` no reconoce `0.0`; el interno los acepta | T-42, T-43 | corregido en a30a02e: los enteros con forma float (`20.0`, `0.0`) pasan a `int` antes de la query y de `untranslatable` (esquema del contrato: tipo `integer`, también dentro de `anyOf`); tests en el stub y en cadena (`limit: 20.0`, `expected_version: 0.0` y `1.0`) con el mismo resultado que el interno | Lente B: `translate.py:57,96` |
| 11 | Minor | `ChainSession.call` quita los argumentos `None`: los tests en cadena nunca envían un null explícito | T-48 | corregido en 3b0294a: `ChainSession.call` envía lo que se le da (un `None` es un `null` explícito); los envoltorios de los servicios (`ChainAgentStore.call`) siguen omitiendo lo que el test no dio. Casos nuevos en cadena: `event_status` con `project_id: null`, `rebuild_corpus` y `work_state_write` con `expected_version: null`, y la prueba de que el `null` viaja | Lente B: `chain_services.py:58` |
| 12 | Minor | `query_corpus` devuelve contenido recuperado (spec.md:44) pero, al estar anotada como escritura, no lleva el envoltorio S-05 | T-45, T-46 | corregido en 60936d6 y a30a02e: `query_corpus` pasa a `reading=True` en el MCP interno y el contrato lo marca con `untrusted: true` en su `x-kairos-endpoint` (la anotación de escritura no cambia); kairos-mcp aplica el envoltorio según esa marca, sin lista de nombres. Tests actualizados (`test_api`, `test_untrusted_internal`, `test_untrusted`) y nuevo en cadena (misma respuesta con envoltorio en ambos MCP) | Lente B (fuera de lente) |
| 13 | Minor | Un 200 de /v1 con cuerpo que no es objeto (array o vacío) se convierte en éxito `{untrusted, warning}` en vez de fallar; `test_robustness.py:252` lo fija | T-41 | corregido en a30a02e: un éxito de `/v1` con cuerpo que no es objeto (lista, vacío, texto) es `Memory service temporarily unavailable` y un evento de log `answer_not_an_object`; `test_robustness.py` y `test_review1.py` lo fijan | Lente A (fuera de lente): `translate.py:198` |
| 14 | Minor | El test de plazo de `test_client.py:92` depende de los tiempos del host (falla en un host lento) | T-37 | corregido en 3b0294a: el test usa un manejador que espera un `threading.Event` que el test libera después; basta con que la llamada vuelva con la respuesta aún retenida, sin márgenes de tiempo del host | Lente A (fuera de lente) |

Corrección del intento 1 (fix1, commits 60936d6, a30a02e, 3b0294a, 2c5d8fc, ec3ae02, 300173c; veredicto y T-50 sin tocar, sin intento 2): los 14 gaps están corregidos, ninguno como deuda. Detalle en la columna Corrección. Decisiones: (a) el orden de errores de `rebuild_corpus` no se resuelve en el endpoint de lectura sino en la traducción: el cliente no puede pedir el permiso de escritura por otra vía barata, así que cuando la lectura de la versión da 404/422, y para `expected_version: 0`, envía la reconstrucción con la versión 2147483646 (el máximo del esquema, que ningún corpus tiene) y es el propio servidor quien responde 403, 422 o 404 en el orden de la herramienta y, para un corpus del actor, `Corpus version changed` sin reconstruir (el diseño anterior de «lectura primero» exigía `write` en `GET …/corpus`); omitir la versión no servía: `CorpusRebuild` la exige y el 422 del modelo llega antes que el 403. `after_read` y `answer` desaparecen de `untranslatable` y se sustituyen por `send_instead`; todo dentro de `x-kairos-*` (el contrato sigue con 34 herramientas, nombres y esquemas idénticos; `test_contract_additive` sin tocar). (b) UUID: se normaliza en kairos-mcp, que da el mismo texto de error que el interno, y además en los dos endpoints `/v1` que tomaban el identificador como texto, de forma tolerante (un valor que no es UUID sigue siendo un 404), para que cualquier cliente REST tenga la misma paridad. (c) Tope de respuesta 96 MiB: por encima de lo máximo que el servidor produce (80 MB), con el pico de memoria de una sola respuesta del orden de 3x; el presupuesto de bytes de la herramienta la recorta. (d) El contrato marca `query_corpus` con `untrusted: true` en su `x-kairos-endpoint` (no se cambia su anotación de escritura).

Cambios visibles para un cliente MCP de kairos-mcp: `initialize`, `tools/list` y `important_workflow` ya no responden a cualquier `Bearer` (401 si `/v1` rechaza la clave); un UUID en mayúsculas, sin guiones o con llaves vale, y uno inválido da el texto de validación del MCP interno (`1 validation error for <tool>Arguments …`); `20.0` vale como `20`; `query_corpus` trae `untrusted` y `warning`; una respuesta de hasta 96 MiB se recorta con el marcador (antes, más de 8 MiB era `Memory service temporarily unavailable`); un 200 sin objeto es un fallo; `rebuild_corpus` con clave de solo lectura da siempre el 403 de la herramienta, también con nombre inválido. En REST: `GET /v1/projects/{p}/corpus` vuelve a pedir solo `read`; `/v1/events/{id}` y `/v1/projects/{p}/documents/{id}` aceptan un UUID en cualquier forma. Diferencias que se documentan y no se igualan: `structuredContent` en las 12 herramientas básicas y el 401 sin `X-Request-ID`.

usage-meter three-components/T-41-fix1: 1.06 h IA (medido, ventana 2026-11-14T00:38Z-01:53Z). Verificación fix1: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p5fix1 .` rc 0, MEMORY_TEST_RESULT {"database": "PostgreSQL", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 743} (727 + 16 tests nuevos; una primera ejecución falló en 3 tests de `query_corpus` por el envoltorio, que se actualizaron); `docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:i2p5fix1 python -m memory_platform.tests.run_postgres` rc 0, `RETRIEVAL_EVAL_RESULT` gate passed; tests de `mcp/` dentro de esa imagen (`cd /app/mcp && python -m unittest discover -s tests`): Ran 113 tests, OK (99 + 14); `KAIROS_MIN_TESTS` y `MIN_FLOOR` a 743 (`test_ci_workflow.py`: 42 tests OK). Contratos regenerados con Python 3.13 (`python:3.13-slim`, EOL CRLF preservado), copia en `mcp/contract/` idéntica, OpenAPI sin cambios. CI run 43543867333 sobre 300173c: 6/6 en verde (mcp, retrieval-eval, client, server, web, contracts). scope-check `--base 7f464bd` exit 0, ledger-lint exit 0. Imágenes `kairos-test:i2p5fix1` y `kairos-mcp:i2p5fix1` borradas.

## Revisión de dos lentes — intento 2: Fase 5 (kairos-mcp), correcciones (T-36, T-41, T-42, T-46, T-47, T-48, T-49)

Veredicto: **1 Important abierto; la Fase 5 no cierra en el intento 2 de 3**. Lentes: A+B en un revisor y C+D en otro (el selector activa las dos sobre 57f9902..HEAD). A+B: los 14 gaps del intento 1 cerrados con evidencia, sin defectos nuevos; contrato aditivo (34 herramientas, idéntico a 57f9902 sin `x-kairos-*`, copia byte a byte); `test_review1` + `test_client` 32 OK; CI 43543867333 6/6. C+D: cerrados 2, 3 (funcional), 4/9, 5, 6, 7 y 13; el 1 sigue abierto con otra causa.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| N1 | Important | El escenario del gap 1 sigue abierto: la validación precompilada hace `best_match(iter_errors(...))`, que recorre todos los errores (unos 190 µs por elemento, lineal, sin parar en `maxItems`) en el event loop del único worker, antes de cualquier llamada a /v1 y con cualquier Bearer; `get_observations` con `ids:[1]*60000` (120 KB, bajo el tope de 256 KiB) bloquea el loop 11,4 s con 0 llamadas a /v1; el interno (pydantic) la rechaza en 2,4 ms (CWE-400) | T-41..T-44 | Corregido en 728b7a3 (T-41 fix2). Opción elegida: acotar a `ERROR_LIMIT = 16` los errores que recibe `best_match` (`itertools.islice` sobre `iter_errors`, que es perezoso), y no las precomprobaciones por esquema (reimplementarían `maxItems`/`maxLength` a mano y cambiarían el orden de errores) ni mover a un hilo (sigue consumiendo CPU sin tope). Coste del rechazo: del orden de milisegundos con cualquier tamaño; el de una petición válida no cambia (sin errores no hay tope que aplicar). Mensaje: idéntico en todos los casos con pocos errores (test contra `jsonschema.validate`, y `test_review1` sobre las 34 herramientas); solo con más de 16 fallos puede nombrar otro error que el SDK (un elemento en vez de `maxItems` en `ids:[1]*60000`); documentado en `mcp/README.md` y `docs/integration.md`. Tests `mcp/tests/test_review2.py`: rojo antes (`ids:[1]*60000` 6,1 s y 120 000 elementos por HTTP, ambos > 1 s), verde después | Lente C+D: `mcp/kairos_mcp/tools.py:68-70,102`; `m5.py` por ASGI con latido del loop |
| N2 | Minor | El tope de 96 MiB sin streaming da un pico de 5-7x la respuesta (no ~3x como dice la decisión (c)) y `json.loads`/`json.dumps` de la respuesta entera corren síncronos en el loop; `memory-mcp` sin `mem_limit` (CWE-770) | T-40, T-42 | Corregido en 4270362 (T-40 fix2) y 5188dd7. Tope de respuesta de 96 a 64 MiB (el máximo real es ~52 MB, no 80); `mem_limit: 1g` en `memory-mcp` (documentado en `docs/configuration.md`; test `ComposeLimitsTests` en `scripts/tests/test_ci_workflow.py`, rojo antes, verde después). Mover `json.loads`/`json.dumps` a un hilo se descarta con medición: `json` mantiene el GIL durante la llamada y el latido del loop se retrasa lo mismo que dura la llamada (50 MB: loads 1,1 s con lag 0,62 s; dumps 1,4 s con lag 1,38 s en un hilo); el bloqueo real es de 1 a 2 s a 52 MB, lo que acota el tope más bajo. Decisión (c) corregida abajo: el factor de pico es ~5x, no ~3x | Lente C+D: `client.py:13,17-22,68`, `translate.py:165-172`, `budget.py:34`; 80 MB → pico 560 MB, 4,3 s de bloqueo |
| N3 | Minor | La justificación del tope en `client.py:10-12` (80 MB) ignora `facts`/`evidence`; sin efecto con el límite de cuerpo por defecto (máximo real ~52 MB) | T-40 | Corregido en 4270362 (T-40 fix2): el comentario de `client.py` cuenta `facts` y `evidence`, dice ~52 MB reales (medidos por la revisión), 64 MiB de tope, el pico de ~5x y por qué no se usa un hilo; coherente con N2 | Lente A+B |
| N4 | Minor | Un `tools/call` que no llega a /v1 (argumentos o UUID inválidos, herramienta desconocida) responde a cualquier Bearer con el error de validación, donde el interno daría 401; no filtra nada (esquemas públicos) pero el README no lo dice | T-49 | Documentado en 5188dd7 (T-49 fix2), sin cambiar el diseño: nueva viñeta en `mcp/README.md` (sección Credencial) y en las diferencias de `docs/integration.md` (CRLF respetado) | Lente A+B; diseño aprobado en el intento 1 (gap 6) |

Corrección del intento 2 (fix2, commits 728b7a3, 4270362, 5188dd7; veredicto y T-50 sin tocar, sin intento 3): los 4 gaps están corregidos, ninguno como deuda. Decisión (c) del intento 1, corregida: el tope de respuesta es 64 MiB (no 96) sobre un máximo real de ~52 MB, y el pico de memoria de una respuesta es del orden de 5x (no 3x): se acota con `mem_limit: 1g` en `memory-mcp` y el bloqueo de 1 a 2 s del parseo a ese tamaño se acepta (un hilo no lo libera por el GIL, medido).

Cambios visibles para un cliente MCP de kairos-mcp: una entrada inválida con más de 16 fallos de esquema puede dar en `Input validation error: …` el mensaje de otro error que el del SDK (los casos con pocos errores, idénticos); el tope de respuesta baja de 96 a 64 MiB (una respuesta mayor es `Memory service temporarily unavailable`; el servidor no produce más de ~52 MB); sin cambios en el contrato MCP, en `tools/list` ni en los límites de cuerpo.

usage-meter three-components/T-41-fix2: 0.35 h IA (medido, ventana 2026-11-14T02:33Z-03:18Z). Verificación fix2: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p5fix2 .` rc 0; `docker run --rm --network=none kairos-test:i2p5fix2 python -m memory_platform.tests.run_postgres` rc 0, MEMORY_TEST_RESULT {"database": "PostgreSQL", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 743} (sin tests nuevos en el servidor: `KAIROS_MIN_TESTS` y `MIN_FLOOR` siguen en 743); tests de `mcp/` dentro de esa imagen: Ran 116 tests, OK (113 + 3 de `test_review2.py`); `scripts/tests/test_ci_workflow.py`: Ran 43 tests, OK (42 + `ComposeLimitsTests`). Rojo observado antes del código: `test_review2` 2 fallos (6,1 s con 60 000 elementos; 120 000 por HTTP) y `ComposeLimitsTests` sin `mem_limit`. Imagen `kairos-test:i2p5fix2` borrada.

CI run 43551205331 sobre 43b9abd (el run 43551140116 de e355ce1 se canceló al empujar el siguiente commit): 6/6 en verde (contracts, web, mcp, server, client, retrieval-eval). scope-check `--base 7f464bd` exit 0, ledger-lint exit 0 (0 incoherencias).

## Revisión de dos lentes — intento 3: Fase 5 (kairos-mcp), correcciones del intento 2 (T-40, T-41, T-42, T-49)

Veredicto: **1 Important abierto tras el intento 3 de 3; el bucle se detiene y la decisión pasa al usuario** (seguir con un ciclo nuevo, re-planificar o aceptar como deuda). Lentes: A+B+C+D en un revisor (D forzada: el gap abierto era de rendimiento; el selector activa C). N2, N3 y N4 cerrados; contrato aditivo (34 herramientas, idéntico a 57f9902 sin `x-kairos-*`, copias byte a byte); `test_review2` 3 OK; paridad del texto con el SDK con pocos errores (3/3).

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | N1 sigue abierto: el `islice` de `refusal` solo acota los errores de primer nivel; en jsonschema 4.26.0 `_keywords.anyOf` hace `list(validator.descend(...))` por rama y materializa todos los errores antes de dar el primero. 15 arrays del contrato están dentro de un `anyOf` (`search.layers`, `context.layers`/`exclude_categories`, `build_corpus.files/concepts/types`, `tags`/`evidence` de `remember`, `observation_add`, `observation_record_event`, `publish_document`), varios sin `maxItems`. `search {"layers":[1]*60000}` con cualquier Bearer bloquea el loop 13,8 s extremo a extremo; 120 000 elementos (240 KB) 28,8 s. Afirmaciones falsas de «lazy»/«milisegundos» en `tools.py:16-18`, `mcp/README.md:69`, `docs/integration.md:98`; `test_review2` solo prueba `get_observations` (sin `anyOf`) (CWE-400) | T-40, T-41 | Corregido en e162867 (T-41 fix3): `tools.py` extiende el validador con un `anyOf` (`bounded_any_of`) que lee como máximo 16 errores por rama (`islice(descend)`) y conserva el `ValidationError` con `context` y el mismo mensaje; `ERROR_LIMIT` sigue acotando `best_match`. Recorrido de las palabras clave del contrato (`type`, `anyOf`, `items`, `additionalProperties`, `pattern`, `format`, cotas, `$ref`): solo `anyOf` materializa errores. Afirmaciones corregidas en `tools.py`, `mcp/README.md:69` y `docs/integration.md:98` (CRLF respetado) | Lente A+B+C+D: `mcp/kairos_mcp/tools.py:76,104`; `n1.py`, `n1b.py` en el scratchpad |
| 2 | Minor | Con 3-4 respuestas máximas simultáneas el `mem_limit: 1g` puede reiniciar `memory-mcp`; documentado en `docs/configuration.md:91` | T-40 | aceptado (documentado) | Lente A+B+C+D: pico medido 4,0x con 36,6 MB |

Corrección del ciclo nuevo tras el intento 3 (fix3, commit e162867; veredicto y T-50 sin tocar, sin intento 4): el gap 1 está corregido. Rojo observado antes del código: `test_review3` 13 fallos de rendimiento en 22 arrays, más 1 error del Harness (todas las ramas con `anyOf`: de 2,7 a 6,0 s con unos 120 000 elementos inválidos por array, p. ej. `search.layers` 2,7 s, `remember.event.payload.evidence` 6,0 s, y la petición del revisor por el servidor 3,7 s; los arrays sin `anyOf` ya pasaban). Tras el código: el peor de los 22 arrays del contrato (hallados recorriendo los esquemas, con `$ref` resueltos) cuesta 27 ms con 120 000 elementos; 15 000 propiedades de más o una clave y un valor de 100 000 caracteres, menos de 50 ms en las 34 herramientas; una entrada válida cuesta lo mismo (172 ms para 20 000 elementos, unos 8 µs cada uno). La paridad del texto con el SDK con pocos errores (0, 1 y 3 elementos inválidos en cada array, más escalares) se comprueba en `test_review3`.

Cambio visible para un cliente MCP de kairos-mcp: ninguno nuevo en el contrato ni en `tools/list`; el texto `Input validation error: …` sigue idéntico al del SDK con hasta 16 fallos por rama de `anyOf` (antes, con cualquier número en una rama), y los errores de una entrada inválida enorme dentro del tope de cuerpo ya no se materializan (la afirmación «se rechaza en milisegundos» era incompleta: el coste de recorrer la entrada es lineal en su tamaño, igual que el de una entrada válida, y se corrige en fix4: fuera del event loop y con concurrencia acotada).

usage-meter three-components/T-41-fix3: 0.2 h IA (medido, ventana 2026-11-14T07:45Z-08:14Z). Verificación fix3: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p5fix3 .` rc 0; `docker run --rm --network=none kairos-test:i2p5fix3 python -m memory_platform.tests.run_postgres` rc 0, MEMORY_TEST_RESULT {"database": "PostgreSQL", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 743} (sin tests nuevos en el servidor: `KAIROS_MIN_TESTS` y `MIN_FLOOR` siguen en 743); tests de `mcp/` dentro de esa imagen: Ran 123 tests, OK (116 + 7 de `test_review3.py`). Imagen `kairos-test:i2p5fix3` borrada. CI run 43574788571 sobre e162867: 6/6 en verde (client, contracts, server, retrieval-eval, web, mcp).

## Revisión de dos lentes — intento 4: Fase 5 kairos-mcp, ciclo nuevo: anyOf acotado — ciclo 2, abierto con OK del usuario: «Seguir - respuesta del usuario a la pregunta tras el intento 3, 2026-11-14» (T-40, T-41)

Veredicto: **el gap 1 del intento 3 (errores materializados en `anyOf`) queda cerrado; sale 1 Important nuevo, residual del mismo escenario, y la Fase 5 no cierra en el intento 4 (ciclo 2, 1 de 3)**. Lentes: A+B+C+D en un revisor. Evidencia del cierre: `bounded_any_of` (`tools.py:24-32,78`) se aplica también tras `$ref` (en 4.26 `descend` conserva la clase extendida); en el contrato solo `anyOf` materializaba (`oneOf` no aparece); `search layers [1]*60000` 19 ms (antes 13,8 s), `[1]*120000` 33 ms; 2460 entradas hostiles de ~256 KiB en las 34 herramientas con elementos inválidos ≤ 0,07 s en reposo; fuzz de 20 400 entradas sin discrepancias de validez con `jsonschema.validate` y sin diferencias de texto con ≤ 16 errores; `test_review3` 7 OK y 13 FAIL + 1 ERROR con el `tools.py` de 946a79c; contrato aditivo intacto.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | Con elementos válidos y un solo fallo exterior (`maxItems`, `required`) hay menos de 16 errores, `islice` agota `iter_errors` y la validación recorre todo el array (15-25 µs por elemento) en el event loop, con cualquier Bearer: `remember` con `payload.tags:[""]*86000` (258 KB, único error `maxItems` 64) bloquea 1,5-2,5 s, también por el servidor; `get_observations ids:[""]*87000` 1,2-1,5 s. Es el coste de una entrada válida del mismo tamaño, pero `mcp/README.md:69` y el ledger afirman «se rechaza en milisegundos» (CWE-400) | T-41, T-49 | corregido en fix4 (218b482): la validación (`Checks.check`: `refusal` + normalización) corre en un hilo con `anyio.to_thread.run_sync` y un `CapacityLimiter` de `KAIROS_VALIDATION_THREADS` (2 por defecto, de 1 a 64; nuevo en `config.py`, `app.py`, Compose, `docs/configuration.md`, `mcp/README.md`); texto `Input validation error: …` y contrato intactos; `mcp/README.md` y `docs/integration.md` dicen ahora la verdad medida; detalle en el párrafo «Corrección del ciclo 2 tras el intento 4» | Lente A+B+C+D: `mcp/kairos_mcp/tools.py:90`; `r4/maxitems.py` en el scratchpad |
| 2 | Minor | El ledger dice «24 arrays» y «14 fallos de 24 subpruebas»; `test_review3` recorre 22 arrays (13 FAIL de rendimiento + 1 del Harness) | T-41 | corregido en fix4 (218b482 y el commit del ledger): las dos cifras del párrafo de fix3 pasan a 22 arrays y «13 fallos de rendimiento + 1 error del Harness» | `len(contract_arrays())` = 22 |

Corrección del ciclo 2 tras el intento 4 (fix4, commit 218b482; veredicto y T-50 sin tocar, sin intento 5): los dos gaps están corregidos. Medición previa (jsonschema 4.26, Python 3.13): el coste de validar es lineal y no se puede acotar sin rechazar entradas válidas, porque una entrada válida del mismo tamaño cuesta lo mismo (`remember` con `payload.tags:[""]*86000`, 258 KB, único error `maxItems`: 1,6 s bloqueando el loop); jsonschema es Python puro y cede el GIL, así que el hilo funciona. Rojo observado antes del código: `test_review4` (nuevo, 5 pruebas): con un latido del loop cada 5 ms, el peor retraso fue 1,68 s con `remember tags [""]*86000`, 1,08 s con `get_observations ids [""]*87000` y 1,00 s con 4 `remember` concurrentes; todos contra el umbral de 0,2 s. Tras el código: retraso máximo del loop 42 ms en Windows y 11 ms en la imagen Linux de pruebas (antes 1,64 s y 0,48 s); con 6 `remember` simultáneos de 86 000 elementos, 155 ms y 64 ms con 2 hilos (el tiempo total sube, de 1,6 s por entrada a 16 s los seis en Windows y 4,5 s en Linux: es el CPU acotado). Coste del salto al hilo en una llamada normal (`search` válido, mediana de 300): Windows 1,06 ms frente a 0,11 ms en línea; Linux (imagen de pruebas) 0,29 ms frente a 0,06 ms, es decir +0,23 ms por llamada, despreciable frente al viaje a `/v1`. Cambio visible para un operador: variable `KAIROS_VALIDATION_THREADS` (opcional, 2 por defecto, de 1 a 64; Compose la pasa) documentada en `docs/configuration.md` y `mcp/README.md`; la validación de entradas grandes ya no frena el resto de peticiones, pero cada una sigue costando CPU lineal en su tamaño (hasta unos 2 s para 256 KiB) y las que superan el límite esperan su turno. Para un cliente MCP: ninguno (contrato, `tools/list` y texto `Input validation error: …` idénticos). La afirmación «se rechaza en milisegundos» de `mcp/README.md` y la del párrafo de fix3 se corrigen; `docs/integration.md` no la decía literalmente y ahora lleva la explicación del coste lineal fuera del loop con concurrencia acotada.

usage-meter three-components/T-41-fix4: 0.23 h IA (medido, ventana 2026-11-14T08:39Z-09:09Z). Verificación fix4: `docker build --target test -f memory_platform/Dockerfile -t kairos-test:i2p5fix4 .` rc 0; `docker run --rm --network=none kairos-test:i2p5fix4 python -m memory_platform.tests.run_postgres` rc 0, MEMORY_TEST_RESULT {"database": "PostgreSQL", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 743} (sin tests nuevos en el servidor: `KAIROS_MIN_TESTS` y `MIN_FLOOR` siguen en 743); tests de `mcp/` dentro de esa imagen: Ran 128 tests, OK (123 + 5 de `test_review4.py`). Imagen `kairos-test:i2p5fix4` borrada. CI run 43579158717 sobre 218b482: 6/6 en verde (client, contracts, server, retrieval-eval, web, mcp).

## Revisión de dos lentes — intento 6: Fase 5 kairos-mcp, vía rápida y plazo de cola (T-41, T-49)

Veredicto: **sin Critical ni Important; la Fase 5 cierra en el intento 6 (3 de 3 del ciclo 2)**. Lentes: A+B+C+D en un revisor. N1 cerrado: la vía rápida (`tools.py:165-166`) valida antes de pedir turno; por HTTP real, peor muestra de una llamada pequeña con N grandes de 256 KiB en curso (67d3d01 / b93dc87 / HEAD): N=2 0,92 / 1,14 / 0,07-0,11 s; N=6 5,4 / 5,3 / 0,11-0,14 s; N=40 73,0 / 36,4 / 1,6-4,0 s. 5003 entradas «pequeñas» hostiles en las 34 herramientas: peor 11,6 ms en línea; `is_small` acotado (pila explícita); el plazo cubre solo la espera; cancelaciones (anyio y desconexiones HTTP reales) sin hilos ni limiters en mal estado; mismo texto de saturación; `test_review5` falla con b93dc87 (5 fallos, 2 errores); contrato aditivo intacto. Una inundación de entradas «pequeñas» pesadas no empeora respecto a antes: es el techo de CPU residual documentado (proxy o rate limiting del operador).

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| M1 | Minor | Cifras de la doc que no eran de HTTP: «0,3 ms de mediana, como sin carga» es el tiempo del handler (por HTTP 64-125 ms de mediana, 6-15 ms sin carga; con 40 cuerpos a la vez la primera tarda 1,6-4 s), y «5 ms como máximo» sale de elementos vacíos (con contenido real hasta ~15 ms); el párrafo del fix5 compara el 0,3 ms con medidas HTTP | T-41, T-49 | corregido (commit de cierre): `mcp/README.md`, `docs/integration.md` y el comentario de `tools.py` dan las cifras HTTP y el máximo con contenido real; este veredicto corrige la comparación del párrafo del fix5 | Lente A+B+C+D: `r6/load6.py`, `r6/inline3.py` |
| M2 | Minor | `test_review5` tomaba el máximo de ~66 muestras sueltas con umbral de 50 ms: picos de 51-78 ms en Windows con el código correcto | T-41 | corregido (commit de cierre): `fastest()` toma el mejor de 3 ejecuciones por medida; `test_review5` 8 OK en Windows | Lente A+B+C+D: `test_review5.py:107-123` |

## Historial archivado

- 2026-11-14 · «Revisión de dos lentes — intento 5: Fase 5 kairos-mcp, validación fuera del event loop (T-41, T-49)» → [execution-history.md](execution-history.md) · SHA-256 `de257f7dcf5bcdcf26d183a712f4ec36bfaa72d12fda03e749a837580eac6925`

## Revisión de dos lentes — intento 1: Fase 6 compatibilidad (T-51, T-52, T-53, T-54, T-55)

Veredicto: **sin Critical ni Important; la Fase 6 cierra en el intento 1 de 3**. Lentes: A+B en un revisor y C en otro (el selector activa C por `nginx.conf`/`docker-compose.yml`). A+B: todos los criterios de T-51..T-55 con evidencia (el 2.º de T-53, compuesto); tests nuevos fallan con 977cc29 y pasan con HEAD; archivado del ledger sin pérdidas (10/10 líneas en `execution-history.md`); `compose config` refleja redes y dependencias. C: nginx real con stubs, 35 rutas crudas: sin traversal ni smuggling por `/mcp`, `/metrics` y `/health/ready` iguales en todas las grafías, límite de cuerpo 256k = `KAIROS_MAX_BODY_BYTES`, red `mcp` sigue `internal`, `MEMORY_MOUNT_MCP` falla en cerrado con valores raros, `mcp_legacy_used` sin credencial ni contenido. Suite tras el cierre: 757, 0 skipped, `llm_chat_calls` 0.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | El comentario de `nginx.conf`, el docstring de `test_nginx_routes` y la doc afirmaban que el MCP interno ya no pasa por el proxy; sigue en `5173/memory-api/mcp/` (prefijo genérico, existente desde antes), con la sesión del portal (CWE-668) | T-52 | corregido (commit de cierre): comentario, docstring, `integration.md` y `operations.md` lo dicen y remiten a `MEMORY_MOUNT_MCP=0` | Lente C: nginx real, `/memory-api/mcp/` → api `/mcp/` con cookie |
| 2 | Minor | `location /mcp` reenviaba la cookie `memory_session` a kairos-mcp, que no la usa (CWE-200, defensa en profundidad) | T-52 | corregido (commit de cierre): `proxy_set_header Cookie "";` y test `test_the_portal_session_cookie_is_not_forwarded_to_kairos_mcp`; `nginx -t` exit 0 | Lente C: `nginx.conf:67-72` |
| 3 | Minor | `Deprecation: true` y `Sunset: 0.5.0` no siguen el formato de fecha de RFC 9745/8594 (CA-27 pide la versión; ningún cliente conocido lee la cabecera) | T-51 | documentado (commit de cierre) en `integration.md`; la elección de fecha queda para el usuario | Lente A+B: `mcp.py:215,232` |
| 4 | Minor | `POST /mcp` sin barra da la 307 del router sin `Deprecation`/`Sunset` ni `mcp_legacy_used` | T-51 | documentado (commit de cierre); deuda aceptada: quien sigue la redirección recibe las cabeceras en `/mcp/` | Lente A+B: `mcp.py:248` |
| 5 | Minor | Ninguna prueba recorre CLI → nginx → kairos-mcp real (el probe va directo; la sonda de nginx usa stubs); la paridad de `allowed_hosts` con el Host reenviado solo se ve leyendo el código | T-53 | deuda aceptada para la Fase 8 (ensayo de integración final, T-72) | Lente A+B: `lifecycle_probe.py:93,124`, `nginx_portal_probe.py:25-35` |

## Revisión de dos lentes — intento 1: Fase 7 estructura del repositorio (T-57, T-58, T-59, T-60, T-61, T-62, T-63, T-64, T-65, T-66, T-67)

Veredicto: **1 Important (T-66) y 5 Minor; sin Critical**. Lentes: A+B en un revisor y C+D en otro (el selector activa C y D por `ci.yml`, `docker-compose.yml` y los Dockerfiles). A+B: movimientos R100 con 0 líneas (66677ae 128, ba954b4 53, f00c763 2); EOL sin cambios en los 28 ficheros tocados; T-68..T-74 idénticos a 788682d y `execution-history.md` solo crece; `docker compose config` resuelve las rutas nuevas; `scripts/tests` 112 OK; CI 43617300808 6/6. C+D: sin hallazgos: `.dockerignore` y contextos sin cambios, imágenes sin root y sin ficheros nuevos, `web/nginx.conf` R100, `compose config` frente a 788682d difiere solo en 6 líneas `dockerfile:`, CI con los mismos permisos y acciones fijadas, `npm pack` 34 ficheros.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | Órdenes de los manuales que ya no funcionan desde la raíz con el paquete en `server/` (`python -m memory_platform.tests.ollama_proxy_probe` → `ModuleNotFoundError`) | T-66 | corregido (86b8d7a): `PYTHONPATH=server` como en la CI en `operations.md`, `extended-workflows.md` y el README de `retrieval_eval` | Lente A+B: `docs/operations.md:243,262`, `docs/extended-workflows.md:136`, `retrieval_eval/README.md:23` |
| 2 | Minor | La `Verificación` de T-60 mandaba ejecutar la puerta de `functional-parity/testing/`, que falla con la estructura nueva; la copia de `scripts/` dependía de `frozen_evidence` del `testing/` de qa | T-60 | corregido (70c8f25): `Verificación` con la copia de `scripts/` y `frozen_evidence.py` copiado junto a ella | Lente A+B: `tasks.md:1996`, `scripts/frozen-source-gate.py:20-21` |
| 3 | Minor | `test_review5` (plazo de cola) dependía del tiempo: run 43617679410 rojo en `mcp` | T-65 | corregido (e9ff45d): la primera llamada retiene el turno con un `threading.Event`; rojo sin el plazo, 5/5 verde | Lente A+B: `mcp/tests/test_review5.py:70-85` |
| 4 | Minor | T-57 pedía rebasar la rama sobre el PR #2; se fusionó `main` (788682d) para no forzar el push | T-57 | deuda aceptada: anotado en T-57; el árbol es el mismo | Lente A+B: `tasks.md:1910` |
| 5 | Minor | Ningún test cubría la actualización 0.3.0 → 0.4.0 anunciada | T-64 | corregido (b9c2c3a): 0.3.0 en el bucle de `lifecycle.test.mjs`; `npm test` 91 OK | Lente A+B: `client/tests/lifecycle.test.mjs:86` |
| 6 | Minor | `client/.npm-cache/` entra en la imagen de tests (`COPY client/`) porque ningún `.dockerignore` lo excluye; existía antes de la fase y no contiene tokens | T-62 | deuda aceptada (fuera de las lentes; anterior a 788682d) | Lente C+D: `client/Dockerfile.test` |

## Revisión de dos lentes — intento 2: Fase 7 correcciones del intento 1 (T-60, T-64, T-65, T-66)

Veredicto: **sin Critical ni Important; la Fase 7 cierra en el intento 2 de 3**. Lente A+B (C/D no aplican: las correcciones no tocan seguridad ni rendimiento). Los cuatro gaps corregidos ✓: sin órdenes `python -m memory_platform` ejecutables desde la raíz sin `PYTHONPATH=server` (las restantes corren en la imagen, `PYTHONPATH=/app/server`); `check_dataset` OK total=72; CRLF conservado; `scripts/frozen_evidence.py` con el mismo SHA-256 que el de `testing/`; `test_review5` determinista (5/5 OK, `release.set()` en `finally`) y `tools.py` sin cambios; `upgrade from 0.3.0` en verde (91/91); CI 43620955201 6/6; ningún criterio `[x]` reescrito.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Minor | La evidencia de las Notas de T-60 (`python -I -c "...import frozen_evidence"`) no se reproduce en Python 3.13: `-I` implica `-P` y no añade el directorio actual | T-60 | corregido (commit de cierre): la nota usa `python -c` y explica por qué la puerta real no se ve afectada | Lente A+B: `tasks.md:2010` |
| 2 | Minor | `while not entered.is_set()` en el test nuevo no tenía tope: si la primera llamada terminara sin validar, el test se colgaría hasta el límite del trabajo de CI | T-65 | corregido (commit de cierre): tope de 10 s y fallo explícito si la primera llamada termina antes de validar | Lente A+B: `mcp/tests/test_review5.py:87` |
