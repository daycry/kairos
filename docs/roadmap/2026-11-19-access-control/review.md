# Revisiones de access-control

Cada fase cierra con su revisión adversarial. El detalle de cada intento está en `tasks.md` y en `execution-history.md`, en las secciones «Revisión de dos lentes».

## Fase 1 — Medición de scrypt y guarda del resolvedor (T-01 a T-05)

- **Fecha**: 2026-11-20 a 2026-11-23
- **Lentes**: A, B, C y D en los doce intentos (C por la ruta `auth` y `.github/workflows/ci.yml`; D por `test_auth_cache.py` y `measure-scrypt.py`). Desde el fix8, las lentes ejecutaron solo las imágenes locales de pruebas, sin red.
- **Veredicto**: cerrada tras el fix12, sin hallazgos Critical ni Important abiertos. Los intentos 3 a 12 quedaron fuera del bucle de tres por decisión expresa del usuario en cada uno. El fix12 se verificó con una comprobación dirigida, también por decisión del usuario («Fix12 mínimo y cerrar», 2026-11-23), no con una ronda completa de cuatro lentes.
- **Evidencia**: suite del servidor 1601 tests, 0 fallos, errores y omitidos (`kairos-test:i4p1-fix12`); `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1601; `scope-check.py --base main` exit 0. Comprobación dirigida del fix12 en `kairos-test:i4p1-fix12` sin red: los cinco casos con `raise` del intento 12 dan lectura de `api_keys`/`project_grants`; `memory.{t}` con huecos de cláusula da `unknown table`; la prosa con hueco calla; el paquete real da `({}, [])` y `[]`; `ResolverBoundaryTests` 27 pruebas, OK.
- **Lo que cambió el método**: la guarda de T-02 interpretaba SQL con expresiones regulares y no convergía (siete correcciones, cada una con regresiones). Con el OK del usuario («Cambia», 2026-11-20) pasó al parser real de PostgreSQL 17 (`pglast==7.24`, solo en la etapa `test`). Los escritores legítimos de `is_admin` se declaran por función en la lista cerrada («Haz el fix», 2026-11-20).

| Intento | Diff | Important | Hallazgo principal | Estado |
|---|---|---|---|---|
| 1 | `f54318e..de26620` | 3 | Guarda: `probe.py` exento entero; SQL compuesto invisible; `is_admin` indirecto | Corregido (fix1) |
| 2 | fix1 | 2 | La excepción de `login` admitía cualquier `is_admin`; `%` sin `memory.` | Corregido (fix2) |
| 3 | fix2 | 1 | El filtro de palabra SQL perdió lecturas de `is_admin` | Fix3 fuera del bucle, OK del usuario |
| 4 | fix3 | 3 | Silencios heredados: `%(is_admin)s`, clave de diccionario, `RETURNING` | Fix4 acotado, OK del usuario |
| 5 | fix4 | 3 | Silencios de escritura sobre `actors` (`SET (…)`, `RETURNING`, upsert) | Fix5: excepción por función, OK del usuario |
| 6 | fix5 | 1 | Borrado de `RETURNING` antes de buscar la fila completa | Corregido (fix6) |
| 7 | fix6 | 2 | Regresión de `DISTINCT ON`; recorrido del FROM no lineal | Corregido (fix7) |
| 8 | fix7 | 3 | Regresiones del escáner por regex (literales, `IS DISTINCT FROM`, coste) | Cambio de método a `pglast` (fix8), OK del usuario |
| 9 | fix8 | 3 | Qué literales se analizan; exenciones que tapaban tablas; regex exponencial | Corregido (fix9) |
| 10 | fix9 | 2 | Puerta léxica: plantillas en constante y `U&`; prosa como `unknown table` | Corregido (fix10) |
| 11 | fix10 | 1 | Sentencias completas con `memory.{t}` y huecos de cláusula | Fix11 (regla `memory.`), OK del usuario |
| 12 | fix11 | 1 | El borrado de `RAISE` escondía tablas vigiladas | Fix12 mínimo y comprobación dirigida, OK del usuario |

### Límites declarados de la guarda

En el docstring de `ResolverBoundaryTests` y en la nota DC-1 de `design.md`:

- Dentro de una función de la lista cerrada, cualquier `is_admin` pasa.
- Un nombre de tabla entero dinámico sin `memory.` dentro de una sentencia que no parsea no se ve.
- La composición dentro del SQL (`format('%I…')`, `||`) no se resuelve.
- Los cuerpos PL/pgSQL se leen como texto.
- Los comentarios de bloque anidados y `a$x$` no siguen exactamente al lexer.
- El DDL de esquema completo e `INHERITS (memory.actors)` no se clasifican.
- Un mensaje de `RAISE` o prosa que nombre una tabla vigilada da falso positivo.
- Las series de `+`/`-` son cuadráticas en el lexer, acotadas por el tope de 32 768 caracteres.

### Pendiente para la revisión de seguridad del hito

- `_load_active` acepta `credential_type: 'bootstrap'` sin comprobar credencial; hoy ningún camino HTTP lo produce (intento 1, lente C).
- `prune_tables` deja un evento `retention_prune` por ejecución y no uno por sesión borrada (decisión abierta, sin cambio).
