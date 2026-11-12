# Informe de QA — retrieval-quality (sin UI)

Fecha: 2026-11-12 · Rama `feat/retrieval-quality` · HEAD `923c827`

ℹ️ **sin UI por diseño (`test-plan: n/a (sin UI)`)**. No hay Playwright, URL ni E2E; el guardrail local no aplica porque no se ejecutó nada contra ninguna URL. La puerta de cobertura NO se ha ejecutado: se ha aceptado la declaración (no es «cobertura OK»).

## Puertas
- `ledger-lint.py`: exit 0, 0 incoherencias duras, 4 avisos (Verificación > 2000 caracteres en T-35, T-36 y T-38; ledger de 227 KB, cerca del tope de 256 KiB, conviene `ledger-archive.py`).
- `coverage-check.py`: exit 0, reconoce el marcador (`test_plan_na: true`, `marcador_no_canonico: null`, `rutas_ui: []`, `rutas_ui_degradado: null`). Eximidos (`eximidos_exigidos: true`): CA-01, CA-02, CA-07, CA-08, CA-15, CA-16, CA-17, CA-19, CA-20, CA-21, CA-24, CA-30. Su evidencia es el campo `Verificación` de la tarea que los cierra en `tasks.md`, no un E2E.
- `qa-gate.py` sobre `testing/raw/results.json`: **exit 1**, `{"verdict": "NO-VERDE", "reason": "sin resultados: results.json no existe (la ausencia de evidencia es rojo)"}`. Es esperado: la puerta evalúa resultados Playwright y aquí no existen. No es un fallo de la iniciativa, pero tampoco un verde del gate.

## Veredicto
Sin UI: **no aplica verde/rojo E2E**. Las puertas deterministas aplicables (ledger-lint, coverage-check) pasan con exit 0. El gate E2E queda NO-VERDE por ausencia de resultados, declarado, no ocultado.

## Evidencia reutilizada (no repetida en esta QA)
- 38/38 tareas `completado` en `tasks.md`; revisión final en `review.md`.
- Última suite (nota de T-37): `MEMORY_TEST_RESULT` 483 tests, 0 fallos, 0 omitidos; puerta offline con `gate.passed: true`.
- Evidencias de medida en este directorio (`final-eval-*.json`, `rehearsal-final.json`, `hnsw-recall.json`, etc.).

## Checklist manual
Sin `M-xx` (no hay test-plan). No se tocó la base desplegada ni contenedores, volúmenes o redes `knowledge-graphs-*`.
