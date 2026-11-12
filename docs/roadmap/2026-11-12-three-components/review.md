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

## Fase 2 — Servidor sin modelo de lenguaje (T-09 a T-16)

- **Fecha**: 2026-11-12
- **Lentes**: intento 1, A, B, C y D (C por `docker-compose.yml` y `memory_platform/Dockerfile`; D por `memory_platform/worker.py`); intento 2, A y B (B con la comprobación de autorización de `corpus_answer`); intento 3, A+B.
- **Veredicto**: cerrada en el intento 3 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**:
  - Suite: 525 tests al implementar, 528 tras el intento 1 y 529 tras el intento 2; 0 omitidos y 0 llamadas a `/api/chat`.
  - CI en verde en los runs 43226845251, 43227856810, 43233832269 y 43240152321.
  - Contrato MCP: 34 herramientas, sin cambios en `docs/contracts/` ni en `store_surface.json`.
  - Proxy de Ollama: la Lente C lo levantó en un proyecto aislado y probó 19 peticiones con 5 valores de `OLLAMA_ALLOW_CHAT`; ninguna evasión llegó a una ruta no permitida.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | El fixture de las pruebas e2e del portal fallaba con `IndexError`: daba por hecho que un evento con `generate` crea un trabajo | Corregido; un test de la suite cubre la siembra |
| 1 | Minor | El espía de `/api/chat` solo ve los tests que leen la configuración del entorno; el texto decía «cualquier llamada» | Corregido el texto; la garantía de CA-18 es `test_no_llm` |
| 1 | Minor | Con `corpus_answer` apagado, un reintento con un `request_id` guardado no leía la respuesta | Corregido |
| 1 | Minor | `/api/embed` acepta cualquier modelo del Ollama del host | Deuda aceptada (Iniciativa 5) |
| 1 | Minor | Docstring desplazado en `test_fts_language.py`; trabajos `unknown` reintentados sin test | Corregidos |
| 2 | Minor | El reintento con la función apagada no comparaba la huella de la petición; el test de acceso denegado no probaba un segundo actor real; la documentación no lo describía | Corregidos |
| 3 | Minor | La huella incluye `MEMORY_LLM_MODEL`: si se vacía al apagar, el reintento da conflicto | Deuda aceptada; documentado, con `corpus_answer_status` como vía de lectura |
