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
| Fase 1 — Integración continua (C-01) | 7 | 8 | 88% | 0 / 18.0h | 0 / 2.3h | 0 / 0.6h | 0 / 578 k |
| Fase 2 — Servidor sin modelo de lenguaje (C-04) | 0 | 9 | 0% | 0 / 37.8h | 0 / 5.0h | 0 / 1.2h | 0 / 1245 k |
| Fase 3 — Paridad REST /v1 (C-02) | 0 | 10 | 0% | 0 / 36.0h | 0 / 5.1h | 0 / 1.3h | 0 / 1282 k |
| Fase 4 — Esquema de observación (C-05) | 0 | 8 | 0% | 0 / 37.8h | 0 / 4.8h | 0 / 1.2h | 0 / 1193 k |
| Fase 5 — kairos-mcp (C-03) | 0 | 15 | 0% | 0 / 68.4h | 0 / 10.1h | 0 / 2.5h | 0 / 2532 k |
| Fase 6 — Compatibilidad (C-07) | 0 | 6 | 0% | 0 / 23.4h | 0 / 3.0h | 0 / 0.8h | 0 / 757 k |
| Fase 7 — Estructura del repositorio (C-06) | 0 | 12 | 0% | 0 / 46.8h | 0 / 6.5h | 0 / 1.6h | 0 / 1614 k |
| Fase 8 — Integración final y revisión | 0 | 6 | 0% | 0 / 12.0h | 0 / 1.8h | 0 / 0.4h | 0 / 440 k |
| **TOTAL** | **7** | **74** | **9%** | **0 / 280.2h** | **0 / 38.6h** | **0 / 9.6h** | **0 / 9641 k** |

> **Imputación externa opcional.** El adaptador elegido recibe las mediciones disponibles y aplica su contrato de jornada, supervisión e idempotencia. No inventes tiempo real ni recalcules horas fuera de su dueño; sin integración los datos permanecen locales.

---

## Fase 1 — Integración continua (C-01)

**Estado**: en-progreso · **Estimado**: 18.0h (15.0h base) · **Real**: — · **Coste est.**: 900 € · **Tokens est.**: 578 k

### T-01 — Workflow `ci.yml` con el trabajo `server` y línea base de la suite

- **Descripción**: Crear `.github/workflows/ci.yml` con disparador `pull_request` (y `workflow_dispatch`) y el trabajo `server`, que ejecuta `docker build --target test -f memory_platform/Dockerfile` en `ubuntu-latest` con caché de capas. Registra la línea base de la suite (nº de tests, 0 fallos, 0 omitidos) en `Notas`. Fuente: CA-01, B-04, O-04; P-01.
- **Changelog**: Cada pull request y cada rama que se sube ejecutan en GitHub la suite completa del servidor en un contenedor aislado, y un fallo o una suite omitida deja la comprobación en rojo.
- **Estado**: completado
- **Cerrada**: 2026-11-12
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real 0.17h (medido, bloque T-01..T-04) + 0.13h (medido, corrección fix1 T-01..T-05)
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

**Notas**: Procedencia: spec CA-01, evaluación C-01. Patrones: la suite corre así en `memory_platform/Dockerfile:31` y `memory_platform/tests/run_postgres.py:18-57`; el resumen se imprime en `run_postgres.py:61`; los tests de `scripts/` viven en `scripts/tests/test_accept_native_clients.py`. No uses acciones con `push` en el nombre (`docker/build-push-action`): rompen la puerta de T-04; usa `run: docker build` sin caché de capas importada (T-05 retiró `actions/cache` y `--no-cache-filter`: reproducían la capa de la suite sin ejecutarla). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde. RED: test_ci_workflow (3 tests) falló con FileNotFoundError: .github/workflows/ci.yml · 2026-11-12. Línea base de la suite en local (docker build --target test, 521 s en local con las capas ya construidas; en CI, sin caché importada): MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": 483}; 483 es el número que comparan las demás tareas. usage-meter close three-components/T-01: 0.17 h IA medidas, abarca el bloque T-01..T-04 (se escribieron y comitearon juntas: commit ceeaa2d). Desviaciones: (1) por autorización del usuario del 2026-11-12 el workflow añade el disparador push con branches-ignore: main además de pull_request y workflow_dispatch (sin PR no hay otro modo de ejecutarlo, y workflow_dispatch exige el fichero en main); el criterio 'sin disparador push' pasa a 'sin push a main' y el test lo fija. (2) Desviación retirada en T-05: no hay caché de capas ni --no-cache-filter (la suite se construye sin caché importada); el paso 'The suite really ran' exige passed true, failures/errors/skipped 0 y tests >= KAIROS_MIN_TESTS (483) en el MEMORY_TEST_RESULT del log, y `test_ci_workflow.py` lo protege con mutantes (revisión intento 1, fix1). Revisión intento 1 (fix1): paso 'The suite really ran' protegido por tests con mutantes (borrarlo, `"failures": 0` -> `"failures"`) y comparación `tests >= KAIROS_MIN_TESTS` (483, un único sitio documentado en `env:`); acciones fijadas por SHA con la etiqueta en comentario (checkout 11d5960, setup-node 49933ea, setup-python a26af69; SHAs resueltos con `gh api repos/<acción>/git/ref/tags/<tag>`, todos `commit` directo) y `persist-credentials: false` en todos los checkout (ningún paso usa el token para git). RED: SuiteGateStepTests/SupplyChainTests fallaron (13 fallos de 32 tests: paso sin KAIROS_MIN_TESTS, acciones por etiqueta, checkout sin persist-credentials) · 2026-11-12. usage-meter close three-components/T-01-fix1: 0.13 h IA (medido; las ventanas fix1 de T-01..T-05 se abrieron y cerraron juntas).

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
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 sí tiene JSON (medido, en Notas)

**Subtareas**
- [x] Ampliar `test_ci_workflow.py` (rojo) con los tres trabajos
- [x] Añadir los trabajos al workflow
- [x] Anotar los tiempos locales de cada comando como referencia
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-01. Patrones: `memory_platform/Dockerfile:46-52` (target `retrieval-eval`), `packages/kairos-cli/package.json:9` (scripts `test`, `release:check`), `web/package.json:7` (script `test`), `memory_platform/Dockerfile.web:27-29` (target `test`). El target `retrieval-eval` instala paquetes con `apt-get` (riesgo del evaluador: depende de la red). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde. RED: AuxiliaryJobsTests falló con AssertionError: 'retrieval-eval' not found in {'server': ...} (3 fallos) · 2026-11-12. Verificación local: docker build --target retrieval-eval --no-cache-filter retrieval-eval -t kairos-eval:t02 → exit 0 en 118 s (RETRIEVAL_EVAL_RESULT con la puerta cumplida, proveedor fake-hashed-words-and-char-ngrams); npm test en packages/kairos-cli → 90 pass, 0 fail, 132 s. El resto (release:check, web, Dockerfile.web) se verifica en la ejecución de CI de T-05. Tiempo IA medido: incluido en T-01 (bloque T-01..T-04). Commit ceeaa2d. Revisión intento 1 (fix1): ver T-01 (SHAs y persist-credentials también en `retrieval-eval`, `client` y `web`). usage-meter close three-components/T-02-fix1: ventana compartida con T-01-fix1 (0.13 h IA, medido, no sumar).

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
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 sí tiene JSON (medido, en Notas)

**Subtareas**
- [x] Ampliar el test estructural (rojo)
- [x] Añadir el trabajo
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-01/CA-07. Patrones: `memory_platform/tests/test_contract_additive.py:28-40` (regla aditiva), `scripts/export-contracts.py:11-30`. Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde. RED: ContractsJobTests falló con AssertionError: 'contracts' not found · 2026-11-12. Desviación: el trabajo corre en el runner con Python 3.13 y no en la imagen de test, porque (a) esa imagen ya ejecuta test_contract_additive dentro del trabajo server y (b) su Python es 3.11 y los contratos versionados (CRLF, escritos con 3.13) difieren en la sangría de las docstrings: comprobado en local, la exportación desde la imagen difiere en 2 descripciones; el diff se hace con git diff --ignore-cr-at-eol. La exportación local con la imagen no se pudo usar como prueba directa porque el entorno local no tiene dependencias; se verifica en la ejecución de CI de T-05. Tiempo IA: incluido en T-01. Commit ceeaa2d. Revisión intento 1 (fix1): el trabajo `contracts` falla también con ficheros sin seguimiento o borrados en `docs/contracts` (`git status --porcelain --untracked-files=all` filtrado por `??`, ` D`, `D `, dentro de un `if`: un `! pipeline` no dispara `set -e`); no se usa 'status vacío' porque los contratos versionados son CRLF y el exportado en Linux es LF, así que `M` aparecería siempre y lo cubre `git diff --ignore-cr-at-eol`. Comprobado en un repo temporal: exit 0 limpio, exit 1 con `??` y con ` D`. El paso ya no dice 'initiative base': nombra `memory_platform/tests/contracts_base` (6008da0), que T-26 reasigna. RED: test_contracts_job_fails_on_untracked_or_deleted_contract_files y test_the_initiative_base_step_names_the_base_it_really_compares_with fallaron · 2026-11-12. usage-meter close three-components/T-03-fix1: ventana compartida con T-01-fix1 (0.13 h IA, medido, no sumar).

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
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 sí tiene JSON (medido, en Notas)

**Subtareas**
- [x] Escribir el test con un caso positivo y tres negativos sobre texto sintético
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-02/CA-30. Patrón: `memory_platform/tests/test_deploy_isolation.py:29-48` (rechaza el nombre de la instalación real). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde. RED: HygieneTests falló con NameError: name 'hygiene_violations' is not defined (10 errores) · 2026-11-12. Verde: python -m unittest discover -s scripts/tests -p test_ci_workflow.py → Ran 14 tests, OK. grep -nEi "secrets\.|docker push|npm publish|push: true|knowledge-graphs-" .github/workflows/ci.yml → sin coincidencias (exit 1). Cubre 1 caso positivo y 3 grupos negativos (secreto ajeno, publicación, recurso knowledge-graphs-*). Tiempo IA: incluido en T-01. Commit ceeaa2d. Revisión intento 1 (fix1): la puerta de higiene detecta además `toJSON(secrets)`, `permissions` distinto de `contents: read` (workflow y trabajo), `gh release`, `twine upload`, `${{ github.event.` dentro de `run:`, `--privileged`, `docker.sock`, `continue-on-error: true`, `|| true` e `if: false`, cada una con su caso negativo (32 tests en total). Las reglas nuevas se escribieron junto a su caso negativo y el workflow actual ya las cumplía, así que su rojo se comprobó con el texto sintético de cada caso. usage-meter close three-components/T-04-fix1: ventana compartida con T-01-fix1 (0.13 h IA, medido, no sumar).

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
- [x] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar — EXCEPCIÓN: sin JSON propio del tramo original (se midió solo en el bloque de T-01; tiempo (estimado)); la corrección fix1 sí tiene JSON (medido, en Notas)

**Subtareas**
- [x] Hacer `git push` de la rama y abrir el PR (acción visible: requiere confirmación del usuario si no está autorizada)
- [x] Diagnosticar los fallos de Linux uno a uno
- [x] Anotar enlace y tiempos
- [x] `usage-meter start/close` — EXCEPCIÓN: tiempo del tramo original (estimado), sin start/close propio

**Notas**: Procedencia: spec CA-01, R-08. Dependencia externa: Actions activas en el repositorio (P-01, decidida). Si el repositorio no admite el `push` o Actions no está activo, la tarea queda bloqueada, no se sustituye por una ejecución local. Clase: defecto de entorno (oráculo: el trabajo en rojo en CI antes de cada arreglo). Ejecución en verde en la rama: https://github.com/daycry/kairos/actions/runs/43202850710 (feat/three-components, commit 4b22aa5): 5 × success. Tiempos medidos en CI (ubuntu-latest): server 127 s (483 pruebas, 0 fallos/errores/omitidas, línea base igual), retrieval-eval 162 s, client 30 s, web 43 s, contracts 14 s (la hipótesis de la spec pasa a hecho medido). Primera ejecución verde: https://github.com/daycry/kairos/actions/runs/43200885564. Desviaciones: (1) sin PR, por autorización del usuario: ejecuciones por el disparador push (branches-ignore main). (2) La puesta en verde destapó tres defectos del propio workflow, corregidos con test en rojo antes (PipeFailureTests, test_the_suite_is_never_replayed_from_an_imported_cache, paso 'The gate really ran and passed'): a) la rama desechable mostró retrieval-eval en verde tras fallar su docker build, porque el shell por defecto es bash -e sin pipefail (run 43201411278): ahora defaults.run.shell: bash y set -euo pipefail; b) con --cache-from la última RUN del target test salió CACHED aunque se pasó --no-cache-filter y la suite no se ejecutó (run 43202142933, server en rojo por el paso de comprobación del registro): se quitó la caché de capas de actions/cache (la construcción limpia cuesta ~2 min); c) retrieval-eval ahora lee su RETRIEVAL_EVAL_RESULT con gate.passed true del registro. Ningún test se desactivó ni se omitió. Commits: ceeaa2d, 41ee014, 4b22aa5. Tiempo IA: usage-meter no devolvió medición para este tramo (null); estimado ~0.3h (estimado). Revisión intento 1 (fix1): ver T-01; el run de verificación de las correcciones se anota abajo. usage-meter close three-components/T-05-fix1: ventana compartida con T-01-fix1 (0.13 h IA, medido, no sumar). El tiempo IA real de T-05 sigue (estimado).

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

**Notas**: Procedencia: spec CA-03. El `push` de la rama desechable es una acción sobre el remoto: pedir confirmación si no está autorizada. Clase: capacidad nueva (verificación negativa de la red de seguridad). CERRADA TRAS EL BORRADO (2026-11-12): el orquestador borró la rama local y la remota `ci-red-probe` con autorización del usuario; el implementer no pudo hacerlo por el hook (`git branch -D`, `git push --delete`), que no se esquivó. Histórico del bloqueo: el rojo está probado, pero el hook de guardarraíles bloquea `git branch -D` (el `-d` se niega porque la rama no está fusionada) y `git push --delete`; no se ha esquivado. Pendiente de quien tenga permiso: `git push origin --delete ci-red-probe` y `git branch -D ci-red-probe` (la rama local y la remota existen; el worktree temporal se retiró salvo un directorio residual `.git/worktrees/wt-probe` con permiso denegado: `git worktree prune`). Rojo comprobado: https://github.com/daycry/kairos/actions/runs/43201411278 (commit 4ba0a7c con test_ci_red_probe.py y self.fail(): server failure; retrieval-eval aparecía en verde por el defecto de pipefail, corregido en T-05) y, con el workflow corregido, https://github.com/daycry/kairos/actions/runs/43202864405 (server failure y retrieval-eval failure; client, web y contracts success). `gh run list --branch ci-red-probe --limit 1` → conclusion failure. La rama no se fusionó (el merge fue de feat/three-components hacia ci-red-probe, nunca al revés). usage-meter: sin start/close propio (el tramo se midió dentro del conjunto T-01..T-07); estimado 0.1h (estimado).

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

**Notas**: Procedencia: spec CA-32, evaluación C-01 (documentación 1 h). Patrón: estructura de `docs/operations.md` existente. Clase: documentación (oráculo: lectura contra el workflow real). Sección 'Integración continua' en docs/operations.md (antes de 'Qué incluir en una incidencia'; fichero CRLF conservado) y párrafo en README.md (tabla de pruebas: 480 → 483). Verificación: grep -n "Integración continua" docs/operations.md → línea 233; ls de ci.yml, export-contracts.py, Dockerfile.web, package.json de client y web y test_contract_additive.py → todos existen; los comandos de la tabla coinciden con los del workflow (lectura). usage-meter close three-components/T-07: 0.01 h IA medidas. Commit eb4b453.

### T-08 — Revisión adversarial de la Fase 1

- **Descripción**: Revisión adversarial de la fase (≈ 0,5 × la implementación, lección de la retro): buscar huecos en la red de CI (trabajo que pasa sin ejecutar nada, caché que oculta fallos, secreto filtrable, comando distinto del local). Registrar hallazgos en `review.md` y cerrar los Critical/Important con su arreglo. Fuente: retro de `retrieval-quality`, R-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 5.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.69h (estimado) · real —
- **Supervisión**: est. 0.17h (≈25 % IA) · real —
- **Previsión IA**: 189 k in / 17 k out tok · ⚠️ verificar €
- **Dependencias**: T-01 … T-07
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md`, sección «Fase 1», sin hallazgos Critical/Important abiertos
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 1» con intentos, hallazgos y su estado
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] `usage-meter start/close` por cada intento de revisión
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Revisar el workflow contra CA-01…CA-03
- [ ] Probar un cambio que debería romper cada trabajo
- [ ] Registrar y cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: `docs/roadmap/2026-11-09-retrieval-quality/retro.md` (revisión como partida propia). No escribe en `testing/` (reservado a `qa`).

---

## Fase 2 — Servidor sin modelo de lenguaje (C-04)

**Estado**: borrador · **Estimado**: 37.8h (31.5h base) · **Real**: — · **Coste est.**: 1.890 € · **Tokens est.**: 1245 k

### T-09 — Interruptor `MEMORY_EXTRACT_ENABLED` en la ingesta con recibo aditivo

- **Descripción**: Añadir `MEMORY_EXTRACT_ENABLED` (por defecto `0`). Con la extracción apagada, un evento con `generate: true` se acepta (202) sin crear trabajo `extract` y el recibo lleva el campo aditivo `extraction: "disabled"`. Ajustar los tests que asumían `extract` para que lo activen explícitamente. Fuente: CA-14, P-03 (decidida), R-03.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.45h (estimado) · real —
- **Supervisión**: est. 0.11h (≈25 % IA) · real —
- **Previsión IA**: 125 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-05
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `memory_platform/store_ingest.py`, `memory_platform/models.py`, `memory_platform/tests/test_native.py`, `memory_platform/tests/test_store.py`, `memory_platform/tests/test_ingest_extract_switch.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t09 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build` anterior incluye el test nuevo `test_ingest_extract_switch` → `ok`

**Criterios de aceptación**
- [ ] Con la configuración por defecto, un evento `summary` con `generate: true` devuelve 202, no crea trabajo `extract` y el recibo contiene `extraction: "disabled"`
- [ ] Con `MEMORY_EXTRACT_ENABLED=1` el comportamiento actual no cambia (trabajo `extract` creado)
- [ ] `test_native.py` y `test_store.py` pasan con la extracción activada de forma explícita donde la usan
- [ ] El recibo no pierde ningún campo existente (solo se añade)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test nuevo en rojo (`generate: true` con la configuración por defecto)
- [ ] Añadir el ajuste en `Settings` y el filtro de `destinations`
- [ ] Añadir `extraction` al recibo
- [ ] Ajustar los tests de `test_native.py` y `test_store.py`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-14/P-03; CLI 0.3.0 envía `generate: true` en resúmenes (`packages/kairos-cli/lib/capture.mjs:84`). Patrón: el trabajo `extract` se decide en `memory_platform/store_ingest.py:183`; ajustes de `Settings` en `memory_platform/config.py:219-272`. Contrato de herramientas MCP: no cambia (solo el recibo crece). Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-10 — El worker no instancia el proveedor `extract` con la extracción apagada

- **Descripción**: Con `MEMORY_EXTRACT_ENABLED=0`, el worker no crea el proveedor `extract` (solo `embed`) y no reclama trabajos `extract` heredados sin dejarlos en estado ambiguo. Ajustar `test_worker.py` y `test_review_regressions.py`. Fuente: CA-14, CA-18, S-04.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.45h (estimado) · real —
- **Supervisión**: est. 0.11h (≈25 % IA) · real —
- **Previsión IA**: 125 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-09
- **Tipo**: backend
- **Archivos**: `memory_platform/worker.py`, `memory_platform/tests/test_worker.py`, `memory_platform/tests/test_review_regressions.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t10 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] `Worker` construido con la configuración por defecto no tiene el proveedor `extract` (test que inspecciona `providers`)
- [ ] Con la extracción activada el comportamiento y los tests actuales no cambian
- [ ] Un trabajo `extract` preexistente con la extracción apagada no llama a ningún proveedor y queda registrado con un motivo explícito (sin perderse)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo sobre `providers`
- [ ] Condicionar la creación del proveedor
- [ ] Definir y probar el trato del trabajo `extract` heredado (aditivo: no se borra)
- [ ] Ajustar los tests existentes
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-14. Patrón: `memory_platform/worker.py:82` (proveedores por defecto), `:107-131` (despacho por destino). Migraciones: ninguna (no se elimina el trabajo `extract`, se desactiva; alcance de la spec). Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-11 — `MEMORY_CORPUS_ANSWER=off` por defecto con error `corpus_answer_disabled`

- **Descripción**: Añadir `MEMORY_CORPUS_ANSWER` (por defecto `off`). Apagado, `corpus_answer` sigue en la lista de herramientas (34) y responde `corpus_answer_disabled` sin llamar a ningún proveedor; `corpus_answer_status` sigue leyendo respuestas ya guardadas. Fuente: CA-15, P-04 (decidida), D-4.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.39h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 107 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-10
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `memory_platform/corpus_answers.py`, `memory_platform/corpus_answer_tools.py`, `memory_platform/app.py`, `memory_platform/tests/test_corpus_answers.py`, `memory_platform/tests/test_corpus_gateway.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t11 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → sin diff (34 herramientas intactas)

**Criterios de aceptación**
- [ ] Por defecto `corpus_answer` devuelve `corpus_answer_disabled` y el proveedor simulado recibe 0 llamadas
- [ ] Con `MEMORY_CORPUS_ANSWER=on` y un modelo configurado, los 21 tests actuales de `test_corpus_answers.py` pasan
- [ ] `corpus_answer_status` lee respuestas ya guardadas con el interruptor apagado
- [ ] `docs/contracts/kairos-mcp.json` sigue con 34 herramientas (el contrato no cambia)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo del error y del proveedor sin llamadas
- [ ] Interruptor en `Settings` y en el servicio
- [ ] Activarlo en los tests existentes que lo necesitan
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-15/P-04. Patrón: llamada a `/api/chat` en `memory_platform/corpus_answers.py:101-105`; herramientas en `memory_platform/corpus_answer_tools.py:15-37`; ruta HTTP `…/answers` en `memory_platform/app.py:274-283`. Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-12 — `MEMORY_LLM_MODEL` sin valor por defecto y validación al arrancar; retirar `beam:cloud`

- **Descripción**: Quitar `beam:cloud` de `Settings`, de `docker-compose.yml` y de `docs/configuration.md`. `Settings.from_env()` falla con un mensaje que nombra `MEMORY_LLM_MODEL` si se activa `extract` o `corpus_answer` sin modelo. Fuente: CA-16, S-04, D-2.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.26h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-11
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `docker-compose.yml`, `docs/configuration.md`, `memory_platform/tests/test_providers.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -n "beam" memory_platform/config.py docker-compose.yml docs/configuration.md` → sin salida (exit 1)
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t12 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] `grep -n beam` no devuelve nada en `memory_platform/config.py`, `docker-compose.yml` ni `docs/configuration.md`
- [ ] `Settings.from_env()` con `MEMORY_EXTRACT_ENABLED=1` o `MEMORY_CORPUS_ANSWER=on` y sin `MEMORY_LLM_MODEL` lanza un error cuyo texto contiene `MEMORY_LLM_MODEL`
- [ ] Con ambos apagados, el arranque no exige modelo
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo de las tres combinaciones
- [ ] Eliminar el valor por defecto y añadir la validación
- [ ] Actualizar compose y manual
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-16/S-04. Patrón: valor por defecto en `memory_platform/config.py:219` y `:272`; `docker-compose.yml:9`; `docs/configuration.md:24`. Una instalación existente que aún dependa de `beam:cloud` debe fijar la variable: se anota en la nota de migración (T-55). Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-13 — Proxy de Ollama con lista de permitidos y `OLLAMA_ALLOW_CHAT`

- **Descripción**: Sustituir `location /` por una lista de permitidos: `/api/embed` y `/api/version` llegan al upstream; el resto responde 403 desde el proxy. `OLLAMA_ALLOW_CHAT=1` habilita además `/api/chat`. Probar con un upstream simulado en un proyecto Compose aislado. Fuente: CA-17, S-09, P-10 (decidida).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.39h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 107 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-12
- **Tipo**: devops
- **Archivos**: `ollama-proxy/default.conf.template`, `docker-compose.yml`, `memory_platform/tests/test_ollama_proxy.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s memory_platform/tests -p test_ollama_proxy.py` → `OK` (los casos que requieren Docker se ejecutan dentro del proyecto aislado `kairos-proxy-t13`)
  - `docker compose -p kairos-proxy-t13 down -v` → solo elimina recursos `kairos-proxy-t13_*`

**Criterios de aceptación**
- [ ] `/api/embed` y `/api/version` llegan al upstream simulado
- [ ] `/api/pull`, `/api/delete`, `/api/create`, `/api/chat` y `/api/generate` responden 403 sin llegar al upstream
- [ ] Con `OLLAMA_ALLOW_CHAT=1`, `/api/chat` llega
- [ ] La prueba usa un proyecto Compose con nombre distinto de `knowledge-graphs` y redes y volúmenes renombrados; no toca recursos `knowledge-graphs-*`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Escribir primero la prueba con upstream simulado (rojo: hoy todo pasa)
- [ ] Reescribir la plantilla nginx con `OLLAMA_ALLOW_CHAT`
- [ ] Verificar `nginx -t` de la plantilla renderizada
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-17/S-09/P-10. Patrón: `ollama-proxy/default.conf.template:15-25` (proxy completo), `docker-compose.yml:38-54` (servicio y redes). Cuidado: las redes y volúmenes tienen `name:` fijo (`docker-compose.yml:169-177`, riesgo R-09): el fichero override del proyecto aislado debe renombrarlos antes de `up`. Si la prueba con Docker no es posible en una máquina, el test estructural de `location` y `nginx -t` sigue siendo obligatorio. Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-14 — Proxy de Ollama sin root

- **Descripción**: Ejecutar el proxy de Ollama con un usuario sin privilegios (resto de S-09, incluido por P-10 decidida; partida +1 h sobre la evaluación). Fuente: S-09 segunda mitad, P-10.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.13h (estimado) · real —
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
- [ ] El contenedor del proxy corre con un UID distinto de 0 y escucha en un puerto no privilegiado o con capacidades mínimas
- [ ] La prueba de T-13 sigue en verde
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Comprobar la imagen base y el puerto 11434
- [ ] Configurar `user:` o imagen sin root
- [ ] Repetir la prueba aislada de T-13
- [ ] `usage-meter start/close`

**Notas**: Procedencia: P-10 (proxy sin root dentro del alcance). Diferencia con la evaluación: la evaluación lo dejó opcional fuera del total (+1 h base); este plan lo incluye. Patrón: `docker-compose.yml:38-54`. Mismas reglas de aislamiento que T-13. Clase: cambio (oráculo: la prueba de T-13 en verde antes y después).

### T-15 — Suite completa sin modelo configurado y espía de `/api/chat` (CA-18)

- **Descripción**: Probar que la suite pasa con `MEMORY_LLM_MODEL` sin definir y con un espía que falla ante cualquier llamada a `/api/chat`, y que el arranque de `memory-api` y `memory-worker` no la hace. Fuente: CA-18, D-2.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.39h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 107 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-12, T-13
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_no_llm.py`, `memory_platform/tests/run_postgres.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t15 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 y espía con 0 llamadas
  - `docker build` anterior incluye `test_no_llm` → `ok`

**Criterios de aceptación**
- [ ] La suite backend pasa con `MEMORY_LLM_MODEL` sin definir y el espía instalado
- [ ] El espía registra 0 llamadas a `/api/chat` durante la ingesta de un resumen con `generate: true`, el worker y `corpus_answer` apagado
- [ ] El arranque de `create_app` y del `Worker` no abre conexión a `/api/chat`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Crear el espía (servidor HTTP local que marca fallo ante `/api/chat`)
- [ ] Ejecutar la suite entera con el espía activo
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-18. Patrón: arnés `memory_platform/tests/run_postgres.py:30-35` (variables del entorno del test). El arranque en el proyecto aislado se repite en T-71. Clase: capacidad nueva (verificación negativa); oráculo: el espía falla si se llama.

### T-16 — Documentar la configuración sin modelo de lenguaje

- **Descripción**: Documentar `MEMORY_EXTRACT_ENABLED`, `MEMORY_CORPUS_ANSWER`, `MEMORY_LLM_MODEL` (sin valor por defecto), `OLLAMA_ALLOW_CHAT` y el trato de `generate: true`. Fuente: CA-32, C-04.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.26h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-15
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/corpus-generated-answers.md`, `docs/operations.md`, `CHANGELOG.md`, `CHANGELOG.es.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -c "MEMORY_EXTRACT_ENABLED\|MEMORY_CORPUS_ANSWER\|OLLAMA_ALLOW_CHAT" docs/configuration.md` → ≥ 3
  - lectura: valores por defecto coinciden con `memory_platform/config.py`

**Criterios de aceptación**
- [ ] Cada variable nueva aparece en `docs/configuration.md` con su valor por defecto real
- [ ] `docs/corpus-generated-answers.md` explica que `corpus_answer` está apagado por defecto y el error `corpus_answer_disabled`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Redactar según `docs-style.md`
- [ ] Comprobar cada valor contra `config.py`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Patrón: tablas de `docs/configuration.md`. Clase: documentación (oráculo: lectura contra el código).

### T-17 — Revisión adversarial de la Fase 2

- **Descripción**: Revisión adversarial: ¿queda algún camino que llame a `/api/chat`? ¿se pierde algún trabajo `extract` heredado? ¿el recibo aditivo rompe a un cliente? ¿el 403 del proxy se puede esquivar (rutas con `//`, mayúsculas, `/api/embed/..`)? Registrar y cerrar hallazgos. Fuente: retro, R-03.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 10.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.44h (estimado) · real —
- **Supervisión**: est. 0.36h (≈25 % IA) · real —
- **Previsión IA**: 397 k in / 35 k out tok · ⚠️ verificar €
- **Dependencias**: T-09 … T-16
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t17 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - lectura: `review.md`, sección «Fase 2», sin hallazgos Critical/Important abiertos

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 2» con intentos y hallazgos
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] Suite completa en verde tras cada arreglo
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Probar evasiones de la lista de permitidos
- [ ] Buscar llamadas a proveedores con `grep -rn "/api/chat" memory_platform`
- [ ] Cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro de `retrieval-quality`. No escribe en `testing/`.

---

## Fase 3 — Paridad REST /v1 (C-02)

**Estado**: borrador · **Estimado**: 36.0h (30.0h base) · **Real**: — · **Coste est.**: 1.800 € · **Tokens est.**: 1282 k

### T-18 — `POST …/corpora` acepta `date_start` y `date_end`

- **Descripción**: Añadir los campos opcionales `date_start` y `date_end` a `CorpusSelection` y pasarlos a `build_corpus`, como ya hace la herramienta. Fuente: CA-05; hallazgo de paridad `build_corpus` (parcial).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-17
- **Tipo**: backend
- **Archivos**: `memory_platform/models.py`, `memory_platform/app.py`, `memory_platform/tests/test_api.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t18 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] `POST …/corpora` con fechas filtra igual que la herramienta `build_corpus`
- [ ] Los campos son opcionales: ninguna petición existente cambia
- [ ] Hay test de acceso permitido, de lector sin permiso (403) y de proyecto ajeno
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo (el campo se ignora hoy)
- [ ] Añadir campos y su paso a `build_corpus`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Patrón: `CorpusSelection` en `memory_platform/models.py:37-44`; la herramienta pasa las fechas en `memory_platform/agent_tools.py:72`; ruta en `memory_platform/app.py:258`. Un campo `required` nuevo rompería `test_contract_additive.py:33-40`: ambos opcionales. Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-19 — Endpoint `/v1` de `capture_policy`

- **Descripción**: Crear un endpoint nuevo (`GET …/capture-policy`, ruta distinta de `…/policy`) que devuelve lo que devuelve `Store.capture_policy`. Fuente: CA-05; hallazgo de paridad «Falta».
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.29h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 80 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-18
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t19 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] El endpoint devuelve el mismo contenido que la herramienta `capture_policy` para el mismo proyecto y credencial
- [ ] Test de acceso permitido, lector sin permiso (403) y proyecto ajeno
- [ ] `GET …/policy` no cambia
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo (404 hoy)
- [ ] Añadir ruta, modelo de respuesta y permiso
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Patrón: `Store.capture_policy` en `memory_platform/store_auth.py:126-137`; `GET …/policy` ya existe y devuelve `get_policy` (`store_auth.py:121-124`): no se toca. Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-20 — Endpoint `/v1` de reconciliación de `event_status` por proyecto

- **Descripción**: Crear el endpoint que ejecuta `reconcile_capture` para un `project_id` y evita el N+1 de la herramienta compuesta. Fuente: CA-05; hallazgo «Parcial» de `event_status`; R-05.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-19
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t20 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] El endpoint devuelve la misma reconciliación que `event_status` con `project_id`
- [ ] Test de acceso permitido, 403 y proyecto ajeno
- [ ] `GET /v1/events/{id}` y `GET /v1/jobs/{id}` no cambian
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo
- [ ] Añadir ruta y respuesta
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05, R-05. Patrón: composición actual en `memory_platform/mcp.py:98-115`; `reconcile_capture` en `memory_platform/store_documents.py:258`; rutas `…/events` y `…/jobs` en `memory_platform/app.py:305`. Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-21 — Endpoints `/v1` de lectura de observaciones (`get_observations`, `observation_search`, `observation_context`)

- **Descripción**: Crear tres endpoints nuevos con la semántica de `AgentStore.observations`, en rutas distintas de `GET /v1/observations` (listado del portal). Fuente: CA-05; hallazgo «Falta (3)».
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.58h (estimado) · real —
- **Supervisión**: est. 0.14h (≈25 % IA) · real —
- **Previsión IA**: 160 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-20
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_agent_tools.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t21 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] Los tres endpoints devuelven lo mismo que su herramienta para igual credencial y argumentos
- [ ] `GET /v1/observations` conserva su semántica y respuesta (test de no regresión)
- [ ] Cada endpoint tiene test de acceso permitido, lector sin permiso (403) y proyecto ajeno
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo de los tres + de no regresión del listado
- [ ] Añadir rutas, modelos y permisos
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Patrón: `AgentStore.observations` en `memory_platform/agent_store.py:355`; el listado del portal en `memory_platform/app.py:353-355` (`PortalStore.page`) no se toca; `observation_context` en `memory_platform/agent_tools.py:127` (aviso ya existente). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-22 — Endpoint `/v1` de `query_corpus`

- **Descripción**: Crear el endpoint de consulta de un corpus (`query_corpus`) con la misma semántica que `AgentStore.query_corpus`. Fuente: CA-05; hallazgo «Falta».
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-21
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t22 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] El endpoint devuelve el mismo contenido que la herramienta para igual credencial y argumentos
- [ ] Test de acceso permitido, 403 y proyecto ajeno
- [ ] No llama a ningún modelo de lenguaje (usa el espía de T-15)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo
- [ ] Añadir ruta y modelo
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Patrón: `AgentStore.query_corpus` en `memory_platform/agent_store.py:345` (ya añade aviso de contenido no fiable). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-23 — Endpoint `/v1` de `team_search`

- **Descripción**: Crear el endpoint de búsqueda de trabajo de equipo (`team_search`). Fuente: CA-05; hallazgo «Falta».
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real —
- **Supervisión**: est. 0.05h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-22
- **Tipo**: backend
- **Archivos**: `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_api.py`, `memory_platform/tests/test_extended_gateway.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t23 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] El endpoint devuelve lo mismo que la herramienta `team_search`
- [ ] Test de acceso permitido, 403 y proyecto ajeno
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo
- [ ] Añadir ruta y modelo
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-05. Patrón: `ExtendedStore.team_search` en `memory_platform/extended_store.py:202`; rutas hermanas `…/team-work` y `…/team-brief` en `memory_platform/app.py:222-251`. Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-24 — `x-kairos-endpoint` por herramienta en el contrato MCP

- **Descripción**: Añadir el campo aditivo `x-kairos-endpoint` (`{method, path}` o `local` para `important_workflow`) a cada una de las 34 herramientas en el exportador y regenerar los contratos. Fuente: CA-04, plan director §2.2.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-23
- **Tipo**: backend
- **Archivos**: `scripts/export-contracts.py`, `docs/contracts/kairos-mcp.json`, `docs/contracts/memory-platform.openapi.json`, `memory_platform/tests/test_contract_additive.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t24 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → solo adiciones

**Criterios de aceptación**
- [ ] Cada herramienta de `tools` tiene `x-kairos-endpoint` con `method` y `path` presentes en `memory-platform.openapi.json`, o `local` (solo `important_workflow`)
- [ ] El contrato regenerado tiene 34 herramientas, mismo orden y ningún campo existente cambiado
- [ ] El MCP interno sigue listando las mismas herramientas (el campo se añade al contrato, no al protocolo)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo de CA-04
- [ ] Definir la tabla herramienta → endpoint en el exportador
- [ ] Regenerar contratos
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-04. Patrón: exportador en `scripts/export-contracts.py:11-30`; regla aditiva en `memory_platform/tests/test_contract_additive.py:28-40`. La tabla de correspondencia es la de la spec, §Arquitectura. Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-25 — Prueba de correspondencia: las 34 herramientas por el MCP interno y por `/v1` (CA-06)

- **Descripción**: Escenario sembrado en PostgreSQL aislado: llamar a cada herramienta por el MCP interno y a su endpoint por `/v1` con la misma credencial y argumentos, y comparar el contenido (salvo presupuesto de bytes y campos aditivos de S-05). Recorre las 34. Fuente: CA-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.43h (estimado) · real —
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
- [ ] La prueba recorre las 34 herramientas y falla si falta una
- [ ] El contenido devuelto es igual salvo presupuesto de bytes y campos aditivos
- [ ] Un endpoint ausente o con otra semántica hace fallar la prueba (mutación manual comprobada)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Sembrar el escenario
- [ ] Escribir el recorrido parametrizado
- [ ] Probar una mutación para ver el rojo
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-06. Patrón: arnés de herramientas en `memory_platform/tests/test_mcp.py` y `test_agent_tools.py`. Es la base de la comparación de C-03 (T-47/T-48). Clase: capacidad nueva (oráculo: rojo al quitar un endpoint).

### T-26 — Línea base de contratos en `23ced03` y diff aditivo de OpenAPI y MCP (CA-07, CA-29)

- **Descripción**: Guardar los contratos del commit `23ced03` como línea base de esta iniciativa y comprobar el diff aditivo de ambos contratos contra ella (la línea base anterior se conserva). Fuente: CA-07, CA-29.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real —
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 20 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-24
- **Tipo**: test
- **Archivos**: `memory_platform/tests/contracts_base_23ced03/`, `memory_platform/tests/test_contract_additive.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t26 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `git show 23ced03:docs/contracts/kairos-mcp.json | diff - memory_platform/tests/contracts_base_23ced03/kairos-mcp.json` → sin diferencias

**Criterios de aceptación**
- [ ] Existe la línea base `23ced03` con ambos contratos tal como estaban en ese commit (`git show 23ced03:docs/contracts/...`)
- [ ] El test de aditividad pasa contra ambas líneas base
- [ ] Ninguna ruta, operación, campo, valor por defecto ni `required` eliminado o cambiado
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Extraer los contratos con `git show 23ced03:…`
- [ ] Parametrizar el test
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-29 (commit de inicio `23ced03`). Patrón: `memory_platform/tests/contracts_base/` y `test_contract_additive.py:1-40`. Los ficheros base se copian byte a byte (EOL conservado: `.gitattributes` es `* -text`). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-27 — Revisión adversarial de la Fase 3

- **Descripción**: Revisión adversarial: permisos de cada endpoint nuevo (lector, proyecto ajeno, clave sin permiso), fuga de datos entre proyectos, ruta nueva que pise una existente, diff aditivo trampa (campo `required` camuflado) y semántica distinta entre herramienta y endpoint. Fuente: retro, R-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 10.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.37h (estimado) · real —
- **Supervisión**: est. 0.34h (≈25 % IA) · real —
- **Previsión IA**: 378 k in / 34 k out tok · ⚠️ verificar €
- **Dependencias**: T-18 … T-26
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t27 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - lectura: `review.md`, sección «Fase 3», sin hallazgos Critical/Important abiertos

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 3»
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] Suite completa y diff aditivo en verde
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Probar cada endpoint con las tres credenciales de prueba
- [ ] Comparar rutas antes y después de la fase
- [ ] Cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 4 — Esquema de observación (C-05)

**Estado**: borrador · **Estimado**: 37.8h (31.5h base) · **Real**: — · **Coste est.**: 1.890 € · **Tokens est.**: 1193 k

### T-28 — Esquemas JSON `observation.v1` y `session-summary.v1`

- **Descripción**: Diseñar los dos esquemas (JSON Schema 2020-12) con `schema_version`. Observación: tipo, título, hechos con cita literal, narrativa, conceptos, ficheros leídos y modificados. Resumen: petición, investigado, aprendido, hecho y siguiente. Fijar límites de longitud y `additionalProperties: false`. Fuente: CA-19, R-04.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.48h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 133 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-27
- **Tipo**: contratos
- **Archivos**: `docs/contracts/observation.v1.schema.json`, `docs/contracts/session-summary.v1.schema.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -c "import json;[json.load(open(f,encoding='utf-8')) for f in ('docs/contracts/observation.v1.schema.json','docs/contracts/session-summary.v1.schema.json')]"` → exit 0
  - lectura: los campos coinciden con CA-19

**Criterios de aceptación**
- [ ] Ambos ficheros son JSON válido, declaran `$schema` 2020-12 y `schema_version`
- [ ] La observación declara los siete campos pedidos y el resumen los cinco
- [ ] Cada campo de texto tiene límite de longitud
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Redactar los esquemas desde el plan director (Iniciativa 6) y el modelo de observación
- [ ] Validar que son JSON Schema válidos con el validador independiente de T-29
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-19, plan director §Iniciativa 2 y 6. Patrón: `Event` genérico con `payload` libre en `memory_platform/models.py:106-117` (los esquemas no lo sustituyen). Riesgo R-04: el diseño puede requerir una v2 en la Iniciativa 6; el versionado lo permite. Clase: capacidad nueva (el oráculo son los ejemplos de T-29).

### T-29 — Ejemplos válidos e inválidos y validador independiente (CA-21)

- **Descripción**: Versionar ejemplos válidos e inválidos junto a los esquemas y validarlos con un validador independiente del servidor (un test en `scripts/tests` que no importa `memory_platform`). Fuente: CA-21.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-28
- **Tipo**: test
- **Archivos**: `docs/contracts/examples/observation.v1/`, `docs/contracts/examples/session-summary.v1/`, `scripts/tests/test_contract_examples.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_contract_examples.py` → `OK`
  - `grep -n "memory_platform" scripts/tests/test_contract_examples.py` → sin salida

**Criterios de aceptación**
- [ ] Cada esquema tiene ≥ 3 ejemplos válidos y ≥ 5 inválidos (campo faltante, campo sobrante, límite excedido, tipo erróneo, versión desconocida)
- [ ] El validador independiente acepta los válidos y rechaza los inválidos
- [ ] El test no importa `memory_platform`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Escribir los ejemplos (rojo: aún no hay validador)
- [ ] Escribir el test con el validador independiente
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-21. El mismo conjunto se reutiliza en T-31 con el validador del servidor. Si no hay un validador JSON Schema disponible en la máquina de desarrollo, el validador independiente corre dentro de un contenedor desechable (sin red hacia servicios desplegados). Clase: capacidad nueva.

### T-30 — Dependencia fijada y módulo de validación de esquemas en el servidor

- **Descripción**: Añadir un validador JSON Schema con versión exacta a `requirements.txt` y un módulo que carga los esquemas de `docs/contracts/` y devuelve el primer error con su ruta JSON, sin eco del contenido. Fuente: CA-20, CA-21; riesgo de superficie de dependencias (B-19).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-29
- **Tipo**: backend
- **Archivos**: `memory_platform/requirements.txt`, `memory_platform/schemas.py`, `memory_platform/tests/test_observation_schema.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t30 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] La dependencia nueva está fijada con versión exacta
- [ ] El módulo valida los ejemplos de T-29 con el mismo resultado que el validador independiente
- [ ] El error devuelto contiene la ruta JSON y no contiene valores del contenido
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo con los ejemplos
- [ ] Añadir dependencia y módulo
- [ ] Reconstruir la imagen de test y comprobar la suite
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-20/CA-21, evaluación C-05. Patrón: dependencias fijadas en `memory_platform/requirements.txt` (p. ej. `mcp==1.27.1` en la línea 6). Los esquemas deben estar disponibles dentro de la imagen: `Dockerfile` copia hoy solo `memory_platform` y algunos scripts (`memory_platform/Dockerfile:25-30`), así que se decide aquí cómo llegan (copiar `docs/contracts/*.schema.json` a la imagen). Clase: capacidad nueva → primer oráculo: test en rojo que describe el comportamiento (se anota `RED:` con su salida) y después en verde.

### T-31 — Validación en `POST /v1/observations` y `observation_record_event` con `invalid_observation`

- **Descripción**: Cuando el evento declara `schema_version`, validarlo contra el esquema: 202 si valida y 422 `invalid_observation` (con la ruta del error y sin eco del contenido) si falta un campo, sobra uno o excede un límite. Sin `schema_version`, todo sigue igual (P-11). Fuente: CA-20, P-11 (decidida).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.48h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 133 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-30
- **Tipo**: backend
- **Archivos**: `memory_platform/extended_store.py`, `memory_platform/app.py`, `memory_platform/models.py`, `memory_platform/tests/test_extended_gateway.py`, `memory_platform/tests/test_api.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t31 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] Una observación `observation.v1` válida da 202; una inválida (falta campo, campo sobrante, límite excedido) da 422 `invalid_observation` con la ruta JSON y sin el contenido
- [ ] Un evento sin `schema_version` se acepta como hoy (test de no regresión)
- [ ] Una `schema_version` desconocida da 422 `invalid_observation`
- [ ] Los ejemplos de T-29 dan el mismo resultado en el servidor y en el validador independiente
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo (válido, inválido, sin versión, versión desconocida)
- [ ] Integrar la validación en la ingesta de observaciones
- [ ] Mapear el error a 422 con el formato `{error:{code,message}}`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-20/P-11. Patrón: ingesta de observaciones en `memory_platform/extended_store.py` (`observation_add`, `observation_record_event`); formato de error `{error:{code,message}}` en `memory_platform/app.py` (manejador de errores) y `mcp.py:48-55`. El CLI 0.3.0 no envía `schema_version`: ruta antigua intacta. Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-32 — Decisión de migración aditiva para conceptos y ficheros (CA-22)

- **Descripción**: Comprobar si el `payload` jsonb basta para filtrar por conceptos y ficheros. Si basta, cerrar la tarea sin migración con la medida como evidencia; si hace falta un índice, escribir una migración solo aditiva. Fuente: CA-22, CA-30; hipótesis de la spec.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.36h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 100 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: db
- **Archivos**: `memory_platform/schema.sql`, `memory_platform/tests/test_migrations_additive.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t32 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `grep -niE "DROP|TRUNCATE|DELETE|ALTER .* TYPE" memory_platform/schema.sql` → sin coincidencias nuevas respecto de `23ced03` (`git diff 23ced03 -- memory_platform/schema.sql`)

**Criterios de aceptación**
- [ ] La decisión (con medida de plan de consulta sobre datos sintéticos) queda en `Notas`
- [ ] Si hay migración, `test_migrations_additive.py` pasa y `content_manifest().sha256` es igual antes y después
- [ ] Ninguna migración contiene `DROP`, `TRUNCATE`, `DELETE` ni `ALTER … TYPE`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Medir una consulta por concepto y por fichero sobre datos sintéticos
- [ ] Decidir; si procede, escribir la migración aditiva con su test
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-22, hipótesis del `payload` jsonb (`memory_platform/schema.sql:13`). Patrón: `memory_platform/tests/test_migrations_additive.py` y `test_pgvector_migration.py`. Restricción: migraciones solo aditivas; nunca contra la base desplegada, solo el PostgreSQL efímero del target `test`. Clase: capacidad nueva condicionada (puede cerrarse sin cambio).

### T-33 — Tests de límites del esquema y de la ruta sin `schema_version`

- **Descripción**: Completar los tests de CA-20: cada límite de longitud, `additionalProperties`, tipos, sin eco del contenido en el 422 y compatibilidad con el payload que envía el CLI 0.3.0. Fuente: CA-20, P-11.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.24h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 67 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_observation_schema.py`, `memory_platform/tests/test_extended_gateway.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t33 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] Hay un caso por cada límite y por cada tipo de error
- [ ] El cuerpo del 422 no contiene ningún valor del contenido enviado (prueba con un valor centinela)
- [ ] El payload real del CLI 0.3.0 (sin `schema_version`) se acepta
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Escribir los casos
- [ ] Tomar el payload del CLI desde `packages/kairos-cli/lib/capture.mjs`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-20. Patrón: `packages/kairos-cli/lib/capture.mjs:84`. Clase: capacidad nueva (cobertura).

### T-34 — Documentar el esquema de observación

- **Descripción**: Documentar los esquemas, el uso de `schema_version`, el error `invalid_observation` y cómo validar un ejemplo en local. Fuente: CA-32, C-05.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.24h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 67 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-33
- **Tipo**: docs
- **Archivos**: `docs/integration.md`, `docs/extended-workflows.md`, `docs/contracts/README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -n "observation.v1" docs/integration.md` → ≥ 1 coincidencia
  - lectura: los límites citados coinciden con los esquemas

**Criterios de aceptación**
- [ ] La doc cita ambos esquemas y su ruta real
- [ ] Explica que sin `schema_version` no se valida (P-11)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Redactar según `docs-style.md`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Clase: documentación.

### T-35 — Revisión adversarial de la Fase 4

- **Descripción**: Revisión adversarial: ¿un esquema permite inyectar contenido sin límite? ¿el 422 filtra contenido? ¿la dependencia nueva amplía la superficie? ¿la migración (si existe) es de verdad aditiva? Fuente: retro, R-04, R-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 10.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 1.44h (estimado) · real —
- **Supervisión**: est. 0.36h (≈25 % IA) · real —
- **Previsión IA**: 397 k in / 35 k out tok · ⚠️ verificar €
- **Dependencias**: T-28 … T-34
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t35 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - lectura: `review.md`, sección «Fase 4», sin hallazgos Critical/Important abiertos

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 4»
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Probar payloads hostiles (profundidad, tamaño, Unicode)
- [ ] Cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 5 — kairos-mcp (C-03)

**Estado**: borrador · **Estimado**: 68.4h (57.0h base) · **Real**: — · **Coste est.**: 3.420 € · **Tokens est.**: 2532 k

### T-36 — Andamiaje del paquete `mcp/` (`kairos_mcp`), Dockerfile sin base de datos y `health`

- **Descripción**: Crear el paquete `mcp/` con servidor ASGI, `GET /health/live`, versión 0.4.0 (P-07), `requirements.txt` sin `psycopg` y Dockerfile propio con usuario sin privilegios; añadir el trabajo `mcp` a la CI. Fuente: CA-08, CA-24 (parte), spec §Arquitectura.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.46h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 126 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/__init__.py`, `mcp/kairos_mcp/app.py`, `mcp/requirements.txt`, `mcp/Dockerfile`, `mcp/VERSION`, `mcp/tests/test_health.py`, `.github/workflows/ci.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/` → exit 0
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/ && docker run --rm kairos-mcp:t36 python -m unittest discover -s tests` → `OK`
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/ && docker run --rm kairos-mcp:t36 pip list` no contiene `psycopg`

**Criterios de aceptación**
- [ ] `mcp/` no instala `psycopg` ni lleva variables `MEMORY_DSN*` ni secretos
- [ ] `GET /health/live` responde 200 en el test
- [ ] El trabajo `mcp` existe en el workflow y el test estructural lo comprueba
- [ ] La imagen se construye con `docker build -f mcp/Dockerfile -t kairos-mcp:t36 mcp/`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test de `health` en rojo
- [ ] Crear paquete, requisitos y Dockerfile
- [ ] Añadir el trabajo `mcp` a la CI y al test estructural
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-08/CA-09. Patrón de Dockerfile y usuario 10001: `memory_platform/Dockerfile:1-10`; SDK `mcp==1.27.1` en `memory_platform/requirements.txt:6`. El contexto de la imagen es `mcp/` y no puede copiar código de `memory_platform` (CA-08). Clase: capacidad nueva.

### T-37 — Cliente HTTP hacia `/v1`: credencial, errores, plazos y registro sin secretos

- **Descripción**: Cliente `httpx` con conexión persistente: reenvía `Authorization: Bearer` tal cual, traduce `{error:{code,message}}` a `ValueError(message)`, devuelve `Memory service temporarily unavailable` ante 5xx, plazo o caída, aplica `KAIROS_API_TIMEOUT` (30 s) y nunca guarda ni registra la credencial. Sin cabecera o con esquema distinto de `Bearer`, 401 sin llamar a `/v1`. Fuente: CA-12, P-08 (decidida), R-05.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 5.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.77h (estimado) · real —
- **Supervisión**: est. 0.19h (≈25 % IA) · real —
- **Previsión IA**: 211 k in / 20 k out tok · ⚠️ verificar €
- **Dependencias**: T-36
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/client.py`, `mcp/kairos_mcp/errors.py`, `mcp/tests/test_client.py`, `mcp/tests/stub_api.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker run --rm kairos-mcp:t37 python -m unittest discover -s tests` → `OK` (tras `docker build -f mcp/Dockerfile -t kairos-mcp:t37 mcp/`)

**Criterios de aceptación**
- [ ] 4xx con `{error:{code,message}}` falla con `message` igual que el MCP interno
- [ ] 5xx, plazo agotado y caída dan `Memory service temporarily unavailable`
- [ ] Sin `Authorization` o con esquema distinto de `Bearer`: 401 con el cuerpo de hoy y 0 llamadas a `/v1`
- [ ] El token sintético aparece 0 veces en los logs durante los tests
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Escribir `stub_api.py` (servidor `/v1` simulado) y los tests en rojo
- [ ] Implementar el cliente
- [ ] Test que busca el token sintético en los logs capturados
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-12/P-08. Patrón de errores y mensaje: `memory_platform/mcp.py:48-55`; 401 en `memory_platform/mcp.py:194-207`. Latencia: R-05. Clase: capacidad nueva.

### T-38 — Servidor MCP con `tools/list` generado desde `kairos-mcp.json` (P-05, CA-10)

- **Descripción**: Montar el servidor MCP de bajo nivel que sirve las 34 herramientas desde el contrato (nombre, descripción, `inputSchema`, anotaciones, orden) en `streamable-http` `/mcp/`. Comprobar primero la hipótesis de que `mcp==1.27.1` permite `inputSchema` arbitrario; si no, escalar al usuario antes de pasar a copiar modelos (alternativa de la spec). Fuente: CA-10, P-05, R-01.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.46h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 126 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-37
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/contract.py`, `mcp/contract/kairos-mcp.json`, `mcp/tests/test_tools_list.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t38 mcp/ && docker run --rm kairos-mcp:t38 python -m unittest discover -s tests` → `OK`, incluido `test_tools_list`

**Criterios de aceptación**
- [ ] `tools/list` devuelve las 34 herramientas en el mismo orden y con los mismos `name`, `description`, `inputSchema` y `annotations` que `docs/contracts/kairos-mcp.json`, con la regla de `test_contract_additive.py`
- [ ] La copia `mcp/contract/kairos-mcp.json` es idéntica a `docs/contracts/kairos-mcp.json` (test de igualdad)
- [ ] Si el SDK no lo permite, la tarea queda bloqueada con la evidencia y se pide decisión
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Spike del SDK de bajo nivel y anotar el resultado
- [ ] Test en rojo de `tools/list`
- [ ] Implementar el registro desde el contrato
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/P-05/R-01, hipótesis del SDK (spec §Supuestos). Patrón: regla de comparación en `memory_platform/tests/test_contract_additive.py:28-40`; la lista de herramientas la sirve hoy `memory_platform/mcp.py:20-63`. Como `mcp/` no puede importar el servidor, el contrato se copia dentro de `mcp/` y un test garantiza que no diverge. Clase: capacidad nueva (oráculo: igualdad con el contrato).

### T-39 — Arranque real del contenedor `kairos-mcp` contra un servidor aislado (verificación temprana)

- **Descripción**: Verificación temprana con un componente real (lección de la retro): arrancar el contenedor `kairos-mcp` con solo `KAIROS_API_URL` contra el servidor `/v1` simulado en un proyecto Compose aislado `kairos-mcp-smoke`, sin variables `MEMORY_DSN*`, sin secretos y sin la red `memory-data`; pedir `GET /health/live` y `tools/list` reales. Fuente: CA-09, retro.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.46h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 126 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-38
- **Tipo**: mcp
- **Archivos**: `mcp/tests/smoke_container.py`, `mcp/tests/compose.smoke.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `python mcp/tests/smoke_container.py` → `PASS health 200; tools 34` y exit 0
  - `docker ps -a -q --filter name=knowledge-graphs-` antes y después → idéntico (no se toca la instalación)

**Criterios de aceptación**
- [ ] El contenedor arranca solo con `KAIROS_API_URL` y `GET /health/live` responde 200
- [ ] `tools/list` por HTTP devuelve las 34 herramientas
- [ ] El proyecto aislado usa solo recursos `kairos-mcp-smoke_*` y se elimina al terminar
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Escribir el fichero Compose aislado (red y volúmenes con nombre de proyecto)
- [ ] Escribir el script de humo
- [ ] Ejecutar y limpiar el proyecto
- [ ] `usage-meter start/close`

**Notas**: Procedencia: retro (verificación con componente real pronto), CA-09. Patrón de aislamiento: `scripts/deploy-memory.py:45-66` (`--project-name` distinto de `knowledge-graphs`). Prohibido: contenedores, redes o volúmenes `knowledge-graphs-*`. Clase: capacidad nueva (oráculo: el humo falla sin el contenedor).

### T-40 — Servicio Compose `memory-mcp` en red propia, sin `memory-data` ni secretos (CA-09)

- **Descripción**: Añadir el servicio `memory-mcp` (imagen `kairos-mcp`) a una red nueva compartida solo con `memory-api`, sin `memory-data`, `inference`, `secrets` ni DSN; hacer que `deploy-memory.py` y el diagnóstico conozcan el servicio nuevo para el ensayo de T-72. Fuente: CA-09, spec §Arquitectura (Compose).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real —
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 84 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `scripts/deploy-memory.py`, `scripts/diagnose-deployment.py`, `memory_platform/tests/test_deploy.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t40 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker compose -p kairos-cfg-t40 config --format json` → `services.memory-mcp` sin `secrets` ni `memory-data` en `networks`

**Criterios de aceptación**
- [ ] `docker compose -p kairos-cfg-t40 config` muestra `memory-mcp` sin `secrets` ni la red `memory-data`
- [ ] `deploy-memory.py --dry-run` incluye el servicio nuevo
- [ ] Los tests de despliegue existentes pasan
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo sobre el `config` renderizado
- [ ] Añadir servicio, red y variables
- [ ] Actualizar el script de despliegue y el diagnóstico
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-09. Patrón: `docker-compose.yml:114-131` (`memory-api`), `:169-173` (redes, nombres fijos: R-09). `config` no crea nada; no se ejecuta `up` aquí. Clase: capacidad nueva (cambio de infraestructura).

### T-41 — Herramientas del grupo `mcp.py` (12) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp las 12 herramientas de `mcp.py` y su traducción a `/v1`. Fuente: CA-10, CA-11, spec §Arquitectura (tabla de paridad).
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real —
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 84 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t41.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t41 mcp/ && docker run --rm kairos-mcp:t41 python -m unittest discover -s tests` → `OK`, 12 herramientas probadas

**Criterios de aceptación**
- [ ] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [ ] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [ ] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [ ] Las herramientas de este grupo: `projects`, `remember`, `publish_document`, `document_status`, `document_manifest`, `revoke_document`, `search`, `details`, `context`, `timeline`, `event_status`, `capture_policy`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo contra `stub_api.py`
- [ ] Implementar la traducción herramienta → llamada
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/CA-11. Patrón: herramientas en `memory_platform/mcp.py:68-172`; `event_status` usa el endpoint de T-20 y `capture_policy` el de T-19. Clase: capacidad nueva (oráculo: igualdad de salida con el MCP interno, comprobada en T-47/T-48).

### T-42 — Herramientas del grupo `agent_tools.py` (13) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp las 13 herramientas de `agent_tools.py`, incluida `important_workflow` como `local`, y los presupuestos de salida. Fuente: CA-10, CA-11.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 105 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-41
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t42.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t42 mcp/ && docker run --rm kairos-mcp:t42 python -m unittest discover -s tests` → `OK`, 13 herramientas probadas

**Criterios de aceptación**
- [ ] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [ ] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [ ] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [ ] Las herramientas de este grupo: `work_state_write`, `work_state_read`, `list_corpora`, `build_corpus`, `rebuild_corpus`, `prime_corpus`, `reprime_corpus`, `query_corpus`, `get_observations`, `observation_search`, `observation_context`, `observation_generation_status`, `important_workflow` (local)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo contra `stub_api.py`
- [ ] Implementar la traducción herramienta → llamada
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/CA-11. Patrón: `memory_platform/agent_tools.py:48-146`; presupuestos en `agent_tools.py:15-16`; texto fijo de `important_workflow` en `agent_tools.py:135-146` (sin endpoint). `build_corpus` usa las fechas de T-18. Clase: capacidad nueva (oráculo: igualdad de salida con el MCP interno, comprobada en T-47/T-48).

### T-43 — Herramientas del grupo `extended_tools.py` (7) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp las 7 herramientas de `extended_tools.py`. Fuente: CA-10, CA-11.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.23h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 63 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-42
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t43.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t43 mcp/ && docker run --rm kairos-mcp:t43 python -m unittest discover -s tests` → `OK`, 7 herramientas probadas

**Criterios de aceptación**
- [ ] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [ ] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [ ] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [ ] Las herramientas de este grupo: `observation_add`, `observation_record_event`, `get_tool_uses`, `team_work_write`, `team_work_read`, `team_brief`, `team_search`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo contra `stub_api.py`
- [ ] Implementar la traducción herramienta → llamada
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/CA-11. Patrón: `memory_platform/extended_tools.py:24-76`; `team_search` usa el endpoint de T-23. Clase: capacidad nueva (oráculo: igualdad de salida con el MCP interno, comprobada en T-47/T-48).

### T-44 — Herramientas del grupo `corpus_answer_tools.py` (2) traducidas a `/v1`

- **Descripción**: Implementar en kairos-mcp `corpus_answer` y `corpus_answer_status`, incluido el error `corpus_answer_disabled` que llega del servidor. Con esto quedan las 34. Fuente: CA-10, CA-11, P-04.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.15h (estimado) · real —
- **Supervisión**: est. 0.04h (≈25 % IA) · real —
- **Previsión IA**: 42 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-43
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/tools.py`, `mcp/kairos_mcp/budget.py`, `mcp/tests/test_tools_t44.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t44 mcp/ && docker run --rm kairos-mcp:t44 python -m unittest discover -s tests` → `OK`, 2 herramientas probadas y recuento total de 34

**Criterios de aceptación**
- [ ] Cada herramienta llama al endpoint declarado en su `x-kairos-endpoint`, con la misma cabecera y los argumentos validados contra su `inputSchema`
- [ ] El resultado respeta el presupuesto de bytes (`NORMAL_BYTES`/`DETAIL_BYTES`)
- [ ] Un caso de éxito, uno de 4xx y uno de caída por herramienta contra el servidor simulado
- [ ] Las herramientas de este grupo: `corpus_answer`, `corpus_answer_status`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo contra `stub_api.py`
- [ ] Implementar la traducción herramienta → llamada
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-10/P-04. Patrón: `memory_platform/corpus_answer_tools.py:15-37`. Al cierre, `tools/list` y la tabla de correspondencia cubren las 34 sin huecos. Clase: capacidad nueva (oráculo: igualdad de salida con el MCP interno, comprobada en T-47/T-48).

### T-45 — Envoltorio de dato no fiable (S-05) en las herramientas de lectura de kairos-mcp

- **Descripción**: Añadir `untrusted: true` y `warning` como campos aditivos al objeto JSON de respuesta de todas las herramientas con `readOnlyHint=True`, sin delimitar ni alterar el texto existente. Fuente: CA-13, P-02 (decidida), S-05, R-02.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 105 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-44
- **Tipo**: mcp
- **Archivos**: `mcp/kairos_mcp/untrusted.py`, `mcp/kairos_mcp/tools.py`, `mcp/tests/test_untrusted.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t45 mcp/ && docker run --rm kairos-mcp:t45 python -m unittest discover -s tests` → `OK`, incluido `test_untrusted`
  - `cd packages/kairos-cli && npm test` → pasa sin cambios (`dispatcher.test.mjs`, `mcp.test.mjs`)

**Criterios de aceptación**
- [ ] Todas las herramientas de lectura devuelven `untrusted` y `warning`; los campos existentes no cambian
- [ ] Las herramientas de escritura no los añaden
- [ ] El texto de la herramienta sigue siendo JSON parseable (`JSON.parse` del CLI)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo parametrizado por `readOnlyHint`
- [ ] Implementar el envoltorio
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-13/P-02/R-02. Patrón: el CLI parsea el texto como JSON en `packages/kairos-cli/lib/dispatcher.mjs:15-20`; avisos preexistentes en `memory_platform/retrieval.py:243`, `agent_tools.py:127`, `extended_store.py:227`, `agent_store.py:345`. La lista de lecturas sale de las anotaciones del contrato, no de una lista a mano. Clase: capacidad nueva.

### T-46 — Envoltorio S-05 en el MCP interno (lecturas) con el CLI 0.3.0 intacto

- **Descripción**: Aplicar el mismo envoltorio aditivo a las herramientas de lectura del MCP interno, con una sola función compartida por las cuatro tablas de herramientas. Fuente: CA-13, S-05, P-02.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 105 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-45
- **Tipo**: backend
- **Archivos**: `memory_platform/mcp.py`, `memory_platform/agent_tools.py`, `memory_platform/extended_tools.py`, `memory_platform/corpus_answer_tools.py`, `memory_platform/tests/test_untrusted_internal.py`, `docs/contracts/kairos-mcp.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t46 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `cd packages/kairos-cli && npm test` → pasa sin cambios

**Criterios de aceptación**
- [ ] Las herramientas de lectura del MCP interno devuelven `untrusted` y `warning`; el resto de campos no cambia
- [ ] `test_mcp.py`, `test_agent_tools.py` y `test_extended_tools.py` pasan (ajustados solo donde comparan el objeto completo)
- [ ] El contrato `kairos-mcp.json` regenerado solo tiene adiciones
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo parametrizado
- [ ] Aplicar el envoltorio de forma centralizada
- [ ] Regenerar contratos y comprobar el diff aditivo
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-13/P-02. Patrón: `memory_platform/mcp.py:20-63` (`safe`, `stored`) como punto común; herramientas de lectura en `mcp.py:68-172`, `agent_tools.py:48-146`, `extended_tools.py:24-76`. Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-47 — Arnés en cadena: kairos-mcp → servidor, ASGI en proceso sobre PostgreSQL aislado

- **Descripción**: Arnés de pruebas que monta kairos-mcp contra la app del servidor por transporte ASGI en proceso, sobre el PostgreSQL efímero del target `test`, sin red y sin importar código del servidor desde `mcp/` (el arnés vive en el lado del servidor). Fuente: CA-11.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.61h (estimado) · real —
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 168 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-46
- **Tipo**: test
- **Archivos**: `memory_platform/tests/chain_harness.py`, `mcp/tests/test_chain_smoke.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t47 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01 (incluye el humo de la cadena)
  - `grep -rn "memory_platform" mcp/ --include=*.py` → sin coincidencias

**Criterios de aceptación**
- [ ] El arnés permite llamar a una herramienta por la cadena kairos-mcp → servidor con las mismas credenciales de prueba
- [ ] `mcp/` sigue sin importar `memory_platform` (el test de CA-08 pasa)
- [ ] Un caso de humo de la cadena (`projects`, `remember`, `search`) pasa
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Diseñar el puente ASGI (dónde vive el arnés para respetar CA-08)
- [ ] Test en rojo de la cadena mínima
- [ ] Implementar
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-11, §Pruebas (modo ASGI en proceso). Patrón: arnés `memory_platform/tests/run_postgres.py:30-35` (PostgreSQL efímero) y tests de gateway `memory_platform/tests/test_corpus_gateway.py`. Clase: capacidad nueva.

### T-48 — Los 7 ficheros de tests de comportamiento MCP contra la cadena (CA-11)

- **Descripción**: Ejecutar los siete ficheros de tests del MCP interno también contra la cadena kairos-mcp → servidor, con los mismos resultados salvo los campos aditivos de S-05. Fuente: CA-11, CA-12, CA-13.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.61h (estimado) · real —
- **Supervisión**: est. 0.15h (≈25 % IA) · real —
- **Previsión IA**: 168 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-47
- **Tipo**: test
- **Archivos**: `memory_platform/tests/test_mcp.py`, `memory_platform/tests/test_mcp_write.py`, `memory_platform/tests/test_agent_tools.py`, `memory_platform/tests/test_extended_tools.py`, `memory_platform/tests/test_corpus_gateway.py`, `memory_platform/tests/test_extended_gateway.py`, `memory_platform/tests/test_work_gateway.py`, `memory_platform/tests/chain_harness.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t48 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build` anterior imprime `tests` ≥ línea base de T-01 más los casos de la cadena

**Criterios de aceptación**
- [ ] Los siete ficheros pasan con el MCP interno y con la cadena, con los mismos resultados salvo `untrusted` y `warning`
- [ ] Con una clave sin permiso de lectura la herramienta falla con el mismo mensaje que el MCP interno; sin credencial, 401
- [ ] El recuento de tests del MCP interno no baja (ningún test desactivado)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Parametrizar los siete ficheros por modo (interno / cadena)
- [ ] Corregir las diferencias reales de kairos-mcp (no los tests)
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-11. Patrón: los siete ficheros ya existen y dan el oráculo. Clase: refactor de pruebas con paridad de comportamiento (oráculo: el mismo test en verde por las dos vías).

### T-49 — Documentar `kairos-mcp`

- **Descripción**: Documentar el componente: variables `KAIROS_API_URL` y `KAIROS_API_TIMEOUT`, credencial Bearer, envoltorio S-05, errores y cómo ejecutar sus tests. Fuente: CA-32, C-03.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.31h (estimado) · real —
- **Supervisión**: est. 0.08h (≈25 % IA) · real —
- **Previsión IA**: 84 k in / 8 k out tok · ⚠️ verificar €
- **Dependencias**: T-48
- **Tipo**: docs
- **Archivos**: `mcp/README.md`, `docs/architecture.md`, `docs/integration.md`, `docs/configuration.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -c "KAIROS_API_URL\|KAIROS_API_TIMEOUT" mcp/README.md docs/configuration.md` → ≥ 2
  - lectura: valores y rutas citados coinciden con el código

**Criterios de aceptación**
- [ ] `mcp/README.md` describe arranque, variables y límites
- [ ] `docs/architecture.md` explica los tres componentes y quién habla con quién
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Redactar según `docs-style.md`
- [ ] Comprobar cada variable contra el código
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Clase: documentación.

### T-50 — Revisión adversarial de la Fase 5

- **Descripción**: Revisión adversarial del núcleo de la iniciativa: ¿diverge algún `inputSchema`, descripción o anotación del contrato? ¿se filtra la credencial a logs o a `/v1` de otra forma? ¿una herramienta de lectura se escapa del envoltorio? ¿`mcp/` importa servidor por una vía indirecta? ¿hay N+1 o plazos sin tope? Fuente: retro, R-01, R-02, R-05, R-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 19.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 2.61h (estimado) · real —
- **Supervisión**: est. 0.65h (≈25 % IA) · real —
- **Previsión IA**: 719 k in / 64 k out tok · ⚠️ verificar €
- **Dependencias**: T-36 … T-49
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t50 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `python mcp/tests/smoke_container.py` → `PASS health 200; tools 34`
  - lectura: `review.md`, sección «Fase 5», sin hallazgos Critical/Important abiertos

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 5»
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] Suite backend, suite de `mcp/` y humo del contenedor (T-39) en verde tras cada arreglo
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Fuzzing de argumentos contra el `inputSchema`
- [ ] Buscar el token sintético en logs y respuestas
- [ ] Repetir `smoke_container.py`
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro (hallazgos reales en todas las fases). No escribe en `testing/`.

---

## Fase 6 — Compatibilidad (C-07)

**Estado**: borrador · **Estimado**: 23.4h (19.5h base) · **Real**: — · **Coste est.**: 1.170 € · **Tokens est.**: 757 k

### T-51 — `MEMORY_MOUNT_MCP` y cabeceras `Deprecation`/`Sunset` del MCP interno

- **Descripción**: Añadir `MEMORY_MOUNT_MCP` (por defecto `1`). Montado, cada respuesta del MCP interno lleva `Deprecation` y `Sunset` con la versión de retirada (0.5.0, P-07) y se emite el evento de log `mcp_legacy_used` sin datos del usuario; con `0`, `/mcp` en `memory-api` responde 404. Fuente: CA-27, P-07.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 104 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-50
- **Tipo**: backend
- **Archivos**: `memory_platform/config.py`, `memory_platform/mcp.py`, `memory_platform/app.py`, `memory_platform/tests/test_mcp_legacy.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t51 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] Con el valor por defecto, los tests actuales del MCP interno pasan y las respuestas llevan `Deprecation` y `Sunset`
- [ ] Con `MEMORY_MOUNT_MCP=0`, `/mcp` responde 404
- [ ] El log `mcp_legacy_used` no contiene credencial, argumentos ni contenido
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Tests en rojo (cabeceras, 404, log)
- [ ] Implementar interruptor y cabeceras en el montaje
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-27/P-07. Patrón: montaje en `memory_platform/app.py:400-401` y `memory_platform/mcp.py:214-225`; etiquetas de montaje del log en `app.py:54-62`. Clase: cambio de comportamiento → primer oráculo: test en rojo que fija el comportamiento nuevo; los tests que asumían el anterior se ajustan en la misma tarea.

### T-52 — `/mcp` del proxy web hacia kairos-mcp y Compose

- **Descripción**: Enrutar `/mcp` del proxy web a `memory-mcp` (hoy a `memory-api`) y declarar la dependencia en Compose; el MCP interno sigue accesible en `memory-api:8790/mcp` durante la versión. Fuente: CA-27, CA-28, P-07.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 104 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-51
- **Tipo**: devops
- **Archivos**: `memory_platform/nginx.conf`, `docker-compose.yml`, `memory_platform/tests/test_nginx_routes.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile.web -t kairos-web-test:t52 .` → exit 0 (`nginx -t`)
  - `python -m unittest discover -s memory_platform/tests -p test_nginx_routes.py` → `OK`

**Criterios de aceptación**
- [ ] `nginx -t` valida la configuración con `/mcp` apuntando a `memory-mcp`
- [ ] `memory-web` depende de `memory-mcp` y `docker compose config` del proyecto aislado lo refleja
- [ ] `/mcp` conserva el comportamiento de plazos y buffers que tenía
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test estructural de la ruta (rojo)
- [ ] Cambiar `nginx.conf` y Compose
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-27/P-07. Patrón: `memory_platform/nginx.conf:56-60` (`/mcp` hoy hacia `memory-api`); target `test` de `memory_platform/Dockerfile.web:24-26` sustituye el upstream para `nginx -t`. Clase: cambio (oráculo: `nginx -t` y el test de ruta).

### T-53 — Puente stdio del CLI contra kairos-mcp en proyecto aislado (CA-28)

- **Descripción**: Hacer que el target `lifecycle-test` ejercite el puente stdio del CLI contra kairos-mcp (no contra el MCP interno), en un proyecto Compose aislado, sin tocar el CLI. Fuente: CA-28, P-07.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.38h (estimado) · real —
- **Supervisión**: est. 0.09h (≈25 % IA) · real —
- **Previsión IA**: 104 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-52
- **Tipo**: test
- **Archivos**: `memory_platform/tests/lifecycle_probe.py`, `memory_platform/Dockerfile`, `packages/kairos-cli/tests/lifecycle.test.mjs`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle:t53 .` → exit 0
  - `cd packages/kairos-cli && npm test` → pasa sin cambios

**Criterios de aceptación**
- [ ] El puente stdio inicializa y lista las herramientas contra kairos-mcp a través de `/mcp/` del proxy
- [ ] El target `lifecycle-test` pasa
- [ ] `REQUIRED_TOOLS` está presente en lo que lista kairos-mcp
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test en rojo (el probe sigue usando el MCP interno)
- [ ] Añadir kairos-mcp a la cadena del probe
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-28. Patrón: puente en `packages/kairos-cli/lib/mcp.mjs:33` (`baseURL + '/mcp/'`), `REQUIRED_TOOLS` en `mcp.mjs:7-8`; target `lifecycle-test` en `memory_platform/Dockerfile:63-66`; probe en `memory_platform/tests/lifecycle_probe.py`. Verificación con componente real, temprana (lección de la retro). Clase: capacidad nueva.

### T-54 — `kairos doctor` contra kairos-mcp en proyecto aislado

- **Descripción**: Comprobar que `kairos doctor` funciona contra kairos-mcp en el proyecto aislado (herramientas requeridas y versión). Fuente: CA-28.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.25h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 69 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-53
- **Tipo**: test
- **Archivos**: `memory_platform/tests/lifecycle_probe.py`, `packages/kairos-cli/tests/lifecycle.test.mjs`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle:t54 .` → exit 0 con el caso de `doctor`

**Criterios de aceptación**
- [ ] `kairos doctor` informa de las herramientas requeridas presentes contra kairos-mcp
- [ ] El resultado queda en el ledger como evidencia, sin escribir en `testing/`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Añadir el caso al probe
- [ ] Ejecutar el target y anotar la salida en `Notas`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-28. Patrón: `doctor` y `REQUIRED_TOOLS` en `packages/kairos-cli/lib/mcp.mjs:7-8`, `:113`. Clase: capacidad nueva (cobertura).

### T-55 — Nota de migración y retirada del MCP interno

- **Descripción**: Escribir la nota de migración: el MCP interno queda en desuso y se retira en 0.5.0, `/mcp` pasa a kairos-mcp, cabeceras `Deprecation`/`Sunset`, evento `mcp_legacy_used`, `MEMORY_LLM_MODEL` obligatorio solo si se activa extracción o respuestas, y el trato de `generate: true`. Fuente: CA-27, CA-32, R-03.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.25h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 69 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: docs
- **Archivos**: `docs/integration.md`, `docs/operations.md`, `CHANGELOG.md`, `CHANGELOG.es.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -c "MEMORY_MOUNT_MCP\|0.5.0" docs/integration.md CHANGELOG.md` → ≥ 2
  - lectura: coincide con T-12, T-09 y T-51

**Criterios de aceptación**
- [ ] La nota cita la versión de retirada, las cabeceras, el log y el interruptor `MEMORY_MOUNT_MCP`
- [ ] Avisa del cambio de captura de resúmenes (R-03) y de `beam:cloud`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Redactar según `docs-style.md`
- [ ] Comprobar cada variable contra el código
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-27/CA-32, R-03. Clase: documentación.

### T-56 — Revisión adversarial de la Fase 6

- **Descripción**: Revisión adversarial: ¿el 404 con `MEMORY_MOUNT_MCP=0` cubre subrutas? ¿las cabeceras salen también en errores y streaming? ¿el log filtra algo? ¿el puente del CLI sigue funcionando con la ruta antigua? Fuente: retro, R-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.89h (estimado) · real —
- **Supervisión**: est. 0.22h (≈25 % IA) · real —
- **Previsión IA**: 246 k in / 22 k out tok · ⚠️ verificar €
- **Dependencias**: T-51 … T-55
- **Tipo**: revisión
- **Archivos**: `docs/roadmap/2026-11-12-three-components/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t56 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - lectura: `review.md`, sección «Fase 6», sin hallazgos Critical/Important abiertos

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 6»
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Probar subrutas y métodos con el interruptor apagado
- [ ] Cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 7 — Estructura del repositorio (C-06)

**Estado**: borrador · **Estimado**: 46.8h (39.0h base) · **Real**: — · **Coste est.**: 2.340 € · **Tokens est.**: 1614 k

### T-57 — Línea base previa al movimiento: recibo de la puerta congelada y recuento

- **Descripción**: Antes de mover nada, registrar en el ledger: recuento de la suite, hash de `store_surface.json`, lista de `npm pack --dry-run` del cliente y resultado de la puerta congelada. Es el oráculo de todo el bloque. Fuente: CA-25, CA-26, P-09.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.14h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 38 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: PR #2 fusionado en `main` (externa, P-09), T-56
- **Tipo**: refactor
- **Archivos**: `memory_platform/tests/store_surface.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `gh pr view 2 --json state --jq .state` → `MERGED`
  - `docker build --target test -f memory_platform/Dockerfile -t kairos-test:t57 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `sha256sum memory_platform/tests/store_surface.json` → valor anotado

**Criterios de aceptación**
- [ ] Quedan anotados `tests`, `sha256` de `store_surface.json`, la lista de `npm pack --dry-run` y el recibo de la puerta congelada
- [ ] El PR #2 consta como fusionado en `main` y la rama está rebasada sobre él
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Comprobar la fusión del PR #2 (`gh pr view 2 --json state`)
- [ ] Ejecutar la suite y la puerta y anotar los valores
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-25/CA-26, P-09. Dependencia externa (no tarea): fusión del PR #2; si no está fusionado, el bloque no empieza. Patrón: puerta congelada `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py:26`, `:45`, `:77`. Clase: refactor (línea base del oráculo).

### T-58 — `git mv memory_platform server/memory_platform` en un commit solo de movimiento

- **Descripción**: Mover el directorio con `git mv` en un commit que no cambia contenido, conservando el nombre del paquete (P-06) y los finales de línea. Este commit deja el árbol sin compilar a propósito; T-59 lo repara en el paso siguiente. Fuente: CA-23, P-06, R-07.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.14h (estimado) · real —
- **Supervisión**: est. 0.03h (≈25 % IA) · real —
- **Previsión IA**: 38 k in / 3 k out tok · ⚠️ verificar €
- **Dependencias**: T-57
- **Tipo**: refactor
- **Archivos**: `server/memory_platform/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --cached -M --stat | tail -1` → solo renombrados, 0 inserciones y 0 borrados
  - `git log --follow --oneline -1 -- server/memory_platform/app.py` → muestra historia anterior al movimiento

**Criterios de aceptación**
- [ ] `git log --follow` conserva la historia de un fichero movido
- [ ] `git diff --stat -M` del commit muestra solo renombrados (100 % de similitud) y 0 líneas cambiadas
- [ ] Los EOL de cada fichero no cambian (`.gitattributes` es `* -text`)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] `git mv memory_platform server/memory_platform`
- [ ] Comprobar similitud y EOL
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23, P-06, R-07. Los commits de movimiento y de ajuste se separan para que la revisión vea un renombrado limpio. Sin copias del código ni de `.pyc`. Clase: refactor (oráculo: similitud 100 %). Pasos T-58 y T-59 se cierran como un único paso verde de suite.

### T-59 — Dockerfiles, Compose y rutas del servidor tras el movimiento

- **Descripción**: Ajustar contextos `COPY`, rutas de los targets (`api`, `operator`, `worker`, `test`, `retrieval-eval`, `lifecycle-test`), Compose y scripts a la nueva ubicación. El comando de verificación pasa a `-f server/memory_platform/Dockerfile` o `-f server/Dockerfile` según se decida al cerrar (se anota). Fuente: CA-23, CA-25.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.55h (estimado) · real —
- **Supervisión**: est. 0.14h (≈25 % IA) · real —
- **Previsión IA**: 154 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-58
- **Tipo**: refactor
- **Archivos**: `server/memory_platform/Dockerfile`, `docker-compose.yml`, `server/memory_platform/tests/run_postgres.py`, `.github/workflows/ci.yml`, `scripts/*.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t59 .` → `MEMORY_TEST_RESULT` con `tests` igual a T-57, 0 fallos, 0 errores, 0 omitidos
  - `sha256sum server/memory_platform/tests/store_surface.json` → igual que T-57

**Criterios de aceptación**
- [ ] Todos los targets del Dockerfile construyen desde la nueva ruta
- [ ] `docker compose config` resuelve las imágenes y contextos
- [ ] La suite tiene `tests` idéntico a la línea base de T-57 y `store_surface.json` no cambia
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Actualizar `COPY` y contextos
- [ ] Actualizar Compose y scripts
- [ ] Ejecutar la suite completa
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-25. Patrón: `memory_platform/Dockerfile:5-9` y `:25-30` (rutas copiadas), `:63-66` (target `lifecycle-test`). El nombre del paquete Python no cambia, así que los 391 usos de `memory_platform` en imports no se tocan (P-06). Clase: refactor (oráculo: misma suite en verde antes y después).

### T-60 — Puerta congelada, scripts y herramientas con las rutas nuevas

- **Descripción**: Actualizar la puerta congelada y los scripts que fijan `memory_platform` o `packages` para que apunten a `server/` y `client/`, con el recibo de la puerta actualizada. Nota: la puerta vive en `testing/` de una iniciativa cerrada; se edita con aprobación de `qa` o se genera una copia junto al ledger (no se escribe en `testing/` de esta iniciativa). Fuente: CA-25, evaluación C-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.41h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 115 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-59
- **Tipo**: refactor
- **Archivos**: `docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`, `scripts/deploy-memory.py`, `scripts/export-contracts.py`, `scripts/memory-admin.py`, `scripts/memory-client.py`, `scripts/diagnose-deployment.py`, `scripts/tests/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `python docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py` → `PASS` con las rutas nuevas
  - `python scripts/export-contracts.py && git diff --stat docs/contracts` → sin diff
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t60 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01

**Criterios de aceptación**
- [ ] La puerta congelada apunta a las rutas nuevas y genera un recibo
- [ ] `scripts/*.py` no contiene rutas antiguas (`grep`)
- [ ] `python scripts/export-contracts.py` produce los contratos sin diff
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] `grep -rn "memory_platform/\|packages/kairos-cli" scripts docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py`
- [ ] Actualizar rutas
- [ ] Ejecutar la puerta
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec §Arquitectura (estructura final) y CA-25. Patrón: `frozen-source-gate.py:26`, `:45`, `:77`. Los recibos históricos de iniciativas cerradas que citan `memory_platform/` no se reescriben (evaluación C-06). Clase: refactor.

### T-61 — `git mv packages/kairos-cli client` en un commit solo de movimiento

- **Descripción**: Mover el CLI con `git mv` en un commit sin cambios de contenido. Fuente: CA-23, CA-26.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.07h (estimado) · real —
- **Supervisión**: est. 0.02h (≈25 % IA) · real —
- **Previsión IA**: 19 k in / 2 k out tok · ⚠️ verificar €
- **Dependencias**: T-60
- **Tipo**: refactor
- **Archivos**: `client/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --cached -M --stat | tail -1` → solo renombrados
  - `git log --follow --oneline -1 -- client/lib/mcp.mjs` → historia anterior al movimiento

**Criterios de aceptación**
- [ ] `git log --follow` conserva la historia de un fichero movido
- [ ] El commit muestra solo renombrados al 100 %
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] `git mv packages/kairos-cli client`
- [ ] Comprobar similitud
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-26. Clase: refactor (oráculo: similitud 100 %). Se cierra junto con T-62 en un único paso verde.

### T-62 — Rutas del cliente: `RUNTIME_FILES`, Dockerfile.test, `release:check` y `npm pack` idéntico

- **Descripción**: Ajustar `RUNTIME_FILES`, el Dockerfile de test, las rutas del target `lifecycle-test` y la CI al nuevo `client/`. El contenido empaquetado no cambia. Fuente: CA-26, CA-23.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.49h (estimado) · real —
- **Supervisión**: est. 0.12h (≈25 % IA) · real —
- **Previsión IA**: 135 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-61
- **Tipo**: refactor
- **Archivos**: `client/lib/config.mjs`, `client/package.json`, `client/Dockerfile.test`, `client/tests/release-check.mjs`, `server/memory_platform/Dockerfile`, `.github/workflows/ci.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `cd client && npm test` → pasa
  - `cd client && npm run release:check` → exit 0
  - `cd client && npm pack --dry-run --json` → lista de `files` idéntica a la anotada en T-57
  - `docker build --target lifecycle-test -f server/memory_platform/Dockerfile -t kairos-lifecycle:t62 .` → exit 0

**Criterios de aceptación**
- [ ] `npm pack --dry-run` del cliente produce la misma lista de ficheros que la línea base de T-57
- [ ] `npm run release:check` pasa
- [ ] `npm test` en `client/` pasa sin cambios en los tests
- [ ] `lifecycle-test` pasa
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Ajustar `config.mjs:11` y rutas
- [ ] Comparar `npm pack --dry-run` con la línea base
- [ ] Ejecutar `npm test`, `release:check` y `lifecycle-test`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-26. Patrón: `packages/kairos-cli/lib/config.mjs:11` (`RUNTIME_FILES`), `package.json:9` (scripts). Nada se publica en npm: solo `--dry-run`, no `npm publish`. Clase: refactor (oráculo: la misma lista de `npm pack` antes y después).

### T-63 — Imagen web: `Dockerfile.web` y `nginx.conf` a `web/`

- **Descripción**: Mover `Dockerfile.web` y `nginx.conf` a `web/`, ajustar contextos y Compose, y conservar los targets `runtime`, `test` y `final`. Fuente: CA-23, CA-24.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.28h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 77 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-62
- **Tipo**: refactor
- **Archivos**: `web/Dockerfile`, `web/nginx.conf`, `docker-compose.yml`, `.github/workflows/ci.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f web/Dockerfile -t kairos-web-test:t63 .` → exit 0
  - `cd web && npm run typecheck && npm test && npm run build` → exit 0

**Criterios de aceptación**
- [ ] La imagen web se construye desde `web/` y su target `test` pasa (`nginx -t`)
- [ ] Compose y CI apuntan a las rutas nuevas
- [ ] El contenido servido no cambia
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] `git mv` en commit aparte
- [ ] Ajustar `COPY` y contextos
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-24. Patrón: `memory_platform/Dockerfile.web:1-28`, `memory_platform/nginx.conf:43-62`. El portal solo cambia de sitio (sin interfaz nueva). Clase: refactor (oráculo: mismo `nginx -t` y misma build).

### T-64 — Versión, imagen y orden de tests de cada componente (CA-24)

- **Descripción**: Declarar versión 0.4.0 en `server`, `mcp` y `client` (sin publicar, P-07) y dejar para cada componente su imagen o Dockerfile y el comando de tests que ejecuta la CI. Fuente: CA-24, P-07.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 3.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.41h (estimado) · real —
- **Supervisión**: est. 0.10h (≈25 % IA) · real —
- **Previsión IA**: 115 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-63
- **Tipo**: refactor
- **Archivos**: `server/VERSION`, `mcp/VERSION`, `client/package.json`, `web/package.json`, `CHANGELOG.md`, `CHANGELOG.es.md`, `server/memory_platform/tests/test_versions.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t64 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `cd client && node -p "require('./package.json').version"` → `0.4.0`

**Criterios de aceptación**
- [ ] Cada componente declara su versión (server 0.4.0, mcp 0.4.0, client 0.4.0)
- [ ] Cada componente tiene Dockerfile (o imagen) y un comando de tests documentado y presente en la CI
- [ ] `test_versions.py` comprueba coherencia entre versión y changelog
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Test de versiones en rojo
- [ ] Fijar versiones y changelogs
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-24/P-07. Patrón: versión actual del CLI `packages/kairos-cli/package.json:3` (0.3.0) y `memory_platform/tests/test_versions.py`. Nada se publica. Clase: cambio (oráculo: test de versiones).

### T-65 — Rutas de la CI tras el movimiento

- **Descripción**: Actualizar los trabajos de la CI a las rutas finales y comprobar que el test estructural y la puerta de higiene (T-04) siguen en verde; ejecución verde en el PR. Fuente: CA-24.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.28h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 77 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-64
- **Tipo**: devops
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `gh run list --branch feat/three-components --limit 1 --json conclusion` → `success`

**Criterios de aceptación**
- [ ] Los seis trabajos (`server`, `retrieval-eval`, `mcp`, `client`, `web`, `contracts`) usan rutas nuevas y terminan en verde en el PR
- [ ] El test estructural y la puerta de higiene pasan
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Actualizar rutas
- [ ] Empujar y comprobar la ejecución
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-24. Dependencia: Actions activas (P-01). Clase: cambio (oráculo: ejecución en verde).

### T-66 — Manuales con la estructura de tres componentes

- **Descripción**: Actualizar rutas y descripciones en los manuales a `server/`, `mcp/`, `client/` y `web/`. Fuente: CA-32, evaluación C-06.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 4.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.55h (estimado) · real —
- **Supervisión**: est. 0.14h (≈25 % IA) · real —
- **Previsión IA**: 154 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-65
- **Tipo**: docs
- **Archivos**: `README.md`, `docs/architecture.md`, `docs/install.md`, `docs/operations.md`, `docs/integration.md`, `docs/configuration.md`, `docs/server-install.md`, `docs/release-cli.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `grep -rn "packages/kairos-cli" README.md docs/*.md` → sin salida
  - lectura: comandos citados válidos contra el árbol nuevo

**Criterios de aceptación**
- [ ] Ningún manual vigente cita `memory_platform/` ni `packages/kairos-cli` como ruta actual (los recibos de iniciativas cerradas quedan como históricos)
- [ ] Los comandos citados existen
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] `grep -rn "packages/kairos-cli\|memory_platform/" README.md docs --include=*.md` fuera de `docs/roadmap`
- [ ] Corregir y comprobar comandos
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Clase: documentación (oráculo: grep + lectura).

### T-67 — Recibo final de la estructura: suite, `store_surface.json`, historia y `npm pack`

- **Descripción**: Con todos los movimientos hechos, registrar en el ledger: suite completa con `tests` idéntico a T-57, `store_surface.json` sin cambios, `git log --follow` de un fichero de cada componente, la puerta congelada actualizada y `npm pack` idéntico. Fuente: CA-23, CA-25, CA-26.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.28h (estimado) · real —
- **Supervisión**: est. 0.07h (≈25 % IA) · real —
- **Previsión IA**: 77 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-66
- **Tipo**: refactor
- **Archivos**: `server/memory_platform/tests/store_surface.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t67 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `ls -d memory_platform packages/kairos-cli` → `No such file or directory` ×2
  - `sha256sum server/memory_platform/tests/store_surface.json` → igual que T-57

**Criterios de aceptación**
- [ ] `tests` igual a la línea base, 0 fallos, 0 errores, 0 omitidos
- [ ] `store_surface.json` byte a byte igual (hash de T-57)
- [ ] No existen `memory_platform/` ni `packages/kairos-cli` en la raíz; existen `server/`, `mcp/`, `client/`, `web/`
- [ ] `git log --follow` conserva la historia de un fichero movido de cada uno
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Ejecutar la suite y la puerta
- [ ] Comparar hash, lista de `npm pack` y recuento
- [ ] Anotar el recibo en `Notas`
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-23/CA-25/CA-26. Los recibos van al ledger, no a `testing/` (reservado a `qa`). Clase: refactor (cierre de oráculo).

### T-68 — Revisión adversarial de la Fase 7

- **Descripción**: Revisión adversarial: referencias a rutas antiguas en scripts, Dockerfiles, hooks, CI y docs; `git mv` con cambios de contenido camuflados; EOL alterados; ficheros que dejaron de empaquetarse; recursos `knowledge-graphs-*` referenciados. Fuente: retro, R-07, R-06.
- **Changelog**: 
- **Estado**: borrador
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

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Fase 7»
- [ ] 0 hallazgos Critical o Important abiertos
- [ ] Suite, puerta y `npm pack` en verde tras cada arreglo
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] `git diff -M --stat 23ced03..HEAD` y búsqueda de rutas antiguas
- [ ] Comparar EOL con `git ls-files --eol`
- [ ] Cerrar hallazgos
- [ ] `usage-meter start/close` por intento

**Notas**: Procedencia: retro. No escribe en `testing/`.

---

## Fase 8 — Integración final y revisión

**Estado**: borrador · **Estimado**: 12.0h (10.0h base) · **Real**: — · **Coste est.**: 600 € · **Tokens est.**: 440 k

### T-69 — Prueba de contrato de kairos-mcp idéntica a la del MCP interno

- **Descripción**: Ejecutar la misma regla de `test_contract_additive.py` sobre `tools/list` del MCP interno y de kairos-mcp, y sobre el contrato regenerado contra la línea base de `23ced03`. Fuente: cierre de la Iniciativa 2 del plan director, CA-10, CA-29.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.15h (estimado) · real —
- **Supervisión**: est. 0.04h (≈25 % IA) · real —
- **Previsión IA**: 40 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-68
- **Tipo**: test
- **Archivos**: `mcp/tests/test_contract_identity.py`, `server/memory_platform/tests/test_contract_additive.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t69 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `docker build -f mcp/Dockerfile -t kairos-mcp:t69 mcp/ && docker run --rm kairos-mcp:t69 python -m unittest tests.test_contract_identity` → `OK`

**Criterios de aceptación**
- [ ] Ambos MCP pasan la misma prueba con 34 herramientas, mismo orden y mismo contenido (`name`, `description`, `inputSchema`, `annotations`)
- [ ] El contrato regenerado solo tiene adiciones respecto de `23ced03`
- [ ] Un cambio mínimo en una descripción de kairos-mcp hace fallar la prueba (comprobado)
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Parametrizar la regla para ambos orígenes
- [ ] Mutación manual para ver el rojo
- [ ] `usage-meter start/close`

**Notas**: Procedencia: plan director, cierre de la Iniciativa 2; spec CA-10/CA-29. Patrón: `test_contract_additive.py:28-40`. Clase: capacidad nueva (verificación de cierre).

### T-70 — Contenedor MCP arrancado sin credenciales de base (cierre)

- **Descripción**: Arrancar el contenedor `kairos-mcp` con solo `KAIROS_API_URL`, sin `MEMORY_DSN*`, secretos ni red `memory-data`, y comprobar `GET /health/live` y la salida de `docker compose config` del proyecto aislado. Fuente: CA-09, cierre del plan director.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.15h (estimado) · real —
- **Supervisión**: est. 0.04h (≈25 % IA) · real —
- **Previsión IA**: 40 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-69
- **Tipo**: test
- **Archivos**: `mcp/tests/smoke_container.py`, `mcp/tests/compose.smoke.yml`
- **Cubre (tests)**: —
- **Verificación**:
  - `python mcp/tests/smoke_container.py` → `PASS health 200; tools 34`
  - `docker compose -p kairos-final-t70 config --format json` → `memory-mcp` sin `secrets` ni `memory-data`

**Criterios de aceptación**
- [ ] `GET /health/live` responde 200
- [ ] `docker compose config` muestra el servicio sin `secrets` ni `memory-data`
- [ ] El proyecto aislado se elimina al terminar y no se toca ningún recurso `knowledge-graphs-*`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Ejecutar `smoke_container.py` en el árbol final
- [ ] Anotar la salida
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-09, cierre del plan director. Repite el humo de T-39 sobre el árbol ya reestructurado. Clase: verificación de cierre (misma prueba en verde).

### T-71 — Servidor arrancado y suite pasada sin ningún modelo de lenguaje (cierre)

- **Descripción**: En el árbol final, ejecutar la suite completa con `MEMORY_LLM_MODEL` sin definir y el espía de `/api/chat`, y comprobar el arranque aislado de `memory-api` y `memory-worker` sin llamadas a `/api/chat`. Fuente: CA-18, cierre del plan director.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real —
- **Supervisión**: est. 0.06h (≈25 % IA) · real —
- **Previsión IA**: 60 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-70
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_no_llm.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build --target test -f server/memory_platform/Dockerfile -t kairos-test:t71 .` → imprime `MEMORY_TEST_RESULT` con `"passed": true`, `failures` 0, `errors` 0, `skipped` 0 y `tests` ≥ la línea base de T-01
  - `env -u MEMORY_LLM_MODEL docker compose -p kairos-nollm-t71 up -d memory-api memory-worker` (con override aislado) y consulta del espía → 0 llamadas

**Criterios de aceptación**
- [ ] La suite pasa con 0 fallos y 0 omitidos sin modelo configurado
- [ ] El espía registra 0 llamadas a `/api/chat`, también durante el arranque aislado de `memory-api` y `memory-worker`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Ejecutar la suite con el espía
- [ ] Arrancar `api` y `worker` en el proyecto aislado `kairos-nollm-t71` y anotar el espía
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-18, cierre del plan director. Prohibido: base desplegada y recursos `knowledge-graphs-*`; todo en el proyecto aislado con el override que renombra redes y volúmenes (R-09). Clase: verificación de cierre.

### T-72 — Ensayo aislado con `scripts/deploy-memory.py --project-name` y los tres componentes (CA-31)

- **Descripción**: Ensayo completo en proyecto Compose aislado con `memory-postgres`, `memory-api`, `memory-worker`, `memory-mcp`, `memory-web` y un proveedor de embeddings simulado: un cliente MCP escribe una observación, espera su indexado y la busca por kairos-mcp, sin que el servidor llame a ningún modelo de lenguaje. Fuente: CA-31, CA-30.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 2.0h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.29h (estimado) · real —
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

**Criterios de aceptación**
- [ ] La observación escrita por kairos-mcp se encuentra por búsqueda tras el indexado
- [ ] El servidor no hizo ninguna llamada a un modelo de lenguaje (espía en 0)
- [ ] Ningún contenedor, volumen o red `knowledge-graphs-*` fue direccionado; el proyecto se elimina al terminar
- [ ] La evidencia queda anotada en el ledger y junto al test, no en `testing/`
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Comprobar con `--dry-run` los comandos y nombres aislados
- [ ] Ejecutar el ensayo con `--project-name kairos-three-t72` y puertos distintos de los reales
- [ ] Anotar el resultado y limpiar
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-31/CA-30, R-09. Patrón: `scripts/deploy-memory.py:45-66` (validación de aislamiento y rechazo del nombre de la instalación) y `:460-472` (`--project-name`, `--dry-run`); `memory_platform/tests/test_deploy_isolation.py:29-48`. Nunca contra la instalación local. Clase: capacidad nueva (verificación de cierre).

### T-73 — Cierre: suite, `retrieval-eval` y manuales (CA-32)

- **Descripción**: Ejecutar la suite completa y `retrieval-eval` con los umbrales vigentes, regenerar los contratos y comprobar que los manuales describen los tres componentes y la retirada del MCP interno. Fuente: CA-32, cierre del plan director.
- **Changelog**: 
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h (base) · real —
- **Tiempo IA (ejec.)**: est. 0.22h (estimado) · real —
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

**Criterios de aceptación**
- [ ] Suite con 0 fallos y 0 omitidos; `retrieval-eval` cumple recall@5 ≥ 0,80 y MRR ≥ 0,60
- [ ] Los seis manuales describen los tres componentes y la retirada del MCP interno
- [ ] Contratos regenerados sin diff y solo aditivos
- [ ] `usage-meter start/close` ejecutado; JSON anotado en `Notas` al cerrar

**Subtareas**
- [ ] Ejecutar suite y evaluación
- [ ] Revisar los manuales contra CA-32
- [ ] `usage-meter start/close`

**Notas**: Procedencia: spec CA-32. Clase: verificación de cierre.

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
