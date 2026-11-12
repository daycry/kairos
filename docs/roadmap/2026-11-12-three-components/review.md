# Revisiones de three-components

Cada fase cierra con su revisión adversarial. El detalle de cada intento está en `tasks.md`, en las secciones «Revisión de dos lentes».

## Fase 1 — Integración continua (T-01 a T-07)

- **Fecha**: 2026-11-12
- **Lentes**: intento 1, A, B y C (C por la ruta `.github/workflows/`; D no aplica); intento 2, A y B+C; intento 3, A+B+C.
- **Veredicto**: cerrada en el intento 3 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**:
  - Run 43210843135: los 5 trabajos en verde y «Ran 39 tests» en `contracts`.
  - `server`: 483 tests, mínimo 483.
  - Rojo de T-06 en el run 43202864405.
  - Repositorio privado; permisos `contents: read`; sin secretos ni publicación.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | `contracts` no veía contratos borrados ni sin versionar | Corregido |
| 1 | Important | El paso que comprueba que la suite se ejecutó no tenía test | Corregido en el intento 2 (ver abajo) |
| 1 | Important | CA-01 pedía un PR y se verificó con `push` | Corregido: la autorización del usuario consta en `spec.md` y en el plan; el `pull_request` se ejercita en T-65 |
| 1 | Minor | La higiene se podía evadir; el token quedaba persistido; las acciones no estaban fijadas por SHA; había notas del ledger desfasadas | Corregidos |
| 2 | Important | La protección del paso de la suite solo buscaba texto | Corregido: test de comportamiento que ejecuta el script con 13 logs y 27 mutantes; el test corre en la CI |
| 2 | Minor | Mayúsculas en las reglas de expresiones; evasiones; referencias y nota de usage-meter | Corregidos |
| 3 | Minor | N1: el test no resuelve `defaults.run.shell` del trabajo | Deuda aceptada |
| 3 | Minor | N2: claves `env:` entre comillas o con espacio antes de `:` | Deuda aceptada |
| 3 | Minor | N3: un `echo` de un `MEMORY_TEST_RESULT` falso tras el build engaña a la puerta | Deuda aceptada |
| 3 | Minor | N4: evasiones restantes de la higiene (`set +eu`, `\|\| echo`, pasos en mapa en línea, `if: ${{ 0 }}`, `-v /:/host`, `seccomp=unconfined`) | Deuda aceptada |
| 3 | Minor | N5: falso positivo de la regla `if:` con `== false` | Deuda aceptada |

Las cinco deudas del intento 3 exigen editar el workflow a propósito, y cualquier edición pasa por la revisión de la fase que la haga. Se recogen para la Iniciativa 9 (mantenibilidad), o antes si una fase posterior toca `ci.yml`.
