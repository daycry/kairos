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

## Fase 3 — Paridad REST /v1 (T-18 a T-26)

- **Fecha**: 2026-11-13
- **Lentes**: intento 1, A, B (con rendimiento) y C (forzada: endpoints nuevos con autorización); intento 2, A y B (con la seguridad del enrutado `{name:path}`); intento 3, A+B y C (activada por `nginx.conf`).
- **Veredicto**: cerrada en el intento 3 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**:
  - Suite: 573 tests al implementar, 591 tras el intento 1, 608 tras el intento 2 y 609 al cerrar; 0 omitidos y 0 llamadas a `/api/chat`.
  - CI en verde en los runs 43255304400, 43263594083, 43421685383 y 43422142841.
  - Contrato MCP: 34 herramientas idénticas; solo se añaden `x-kairos-endpoint` (con la traducción de cada argumento) y `x-kairos-translation`. OpenAPI: solo rutas nuevas. La línea base de contratos de 23ced03 se conserva byte a byte.
  - Seguridad: sin IDOR ni enumeración en los endpoints nuevos; el nginx del portal probado con 54 peticiones crudas, sin smuggling ni traversal, y `/metrics` cerrado.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | `x-kairos-endpoint` no describía cómo se traducen los argumentos (`includeClosed` se ignoraba en silencio, fechas con 422); el test de paridad escribía la petición REST a mano | Corregido: reglas por argumento y traductor genérico en el test |
| 1 | Minor | Fechas extremas con 503; paridad trivial de `get_tool_uses` y `corpus_answer_status`; nombres de corpus con `/` inalcanzables por REST | Corregidos |
| 1 | Minor | Las lecturas REST de observaciones no tienen tope de bytes | Deuda planificada para kairos-mcp (T-41 a T-44) |
| 2 | Important | `rebuild_corpus` sin versión leía de una lista cortada en 100, sin regla para el corpus inexistente ni para la carrera | Corregido: `GET …/corpus?name=` y regla de reintento |
| 2 | Minor | Gramática de `event_status` sin proyecto y `expected_version: 0` sin documentar en el contrato; el nginx del portal normalizaba `a/../b` | Corregidos |
| 3 | Minor | Log de nginx con la query string; lectura de corpus con clave de solo escritura; nombre con NUL → 503 | Corregidos al cerrar |
| 3 | Minor | Orden de errores distinto en casos de error de `rebuild_corpus`; `expected_version: 0` responde 409 sin llamar; `max:3` de reintentos; tests con menos alcance del que dicen | Deuda aceptada (Fase 5, T-41 a T-48) |

## Fase 4 — Esquema de observación (T-28 a T-34)

- **Fecha**: 2026-11-13
- **Lentes**: intento 1, A+B y C (activada por `memory_platform/Dockerfile`); intento 2, A+B y C (forzada, porque el Critical del intento 1 era de seguridad).
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**:
  - Suite: 630 tests al implementar, 638 tras el intento 1 y 639 al cerrar; 0 omitidos y 0 llamadas a `/api/chat`. Puerta offline en verde.
  - CI en verde en los runs 43437683851 y 43447573957.
  - Contrato MCP: 34 herramientas; solo se añade el campo opcional `payload.structured`. OpenAPI: solo adiciones. Sin migraciones (medido: el `payload` jsonb basta hasta unas 20 000 observaciones por proyecto).
  - Seguridad: el 422 `invalid_observation` no repite contenido (ruta con nombres del esquema, índices o `*`); `$ref` remotos no se resuelven; la privacidad existente recorre `structured`.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Critical | `uniqueItems` cuadrático: una lista de 8 000 elementos de tipos mezclados ocupaba 184 s de CPU con una clave de escritura | Corregido: listas de más de 50 elementos rechazadas en tiempo lineal antes de validar |
| 1 | Important | `remember` y `POST /v1/events` guardaban `payload.structured` sin validar | Corregido: validación única en `Store.ingest_event` |
| 1 | Minor | Extracción LLM con `structured` abierto; doc de privacidad; esquemas cargados en caliente; transitivas sin fijar | Corregidos |
| 2 | Minor | Coste superlineal acotado con elementos grandes; doc de privacidad incompleta | Corregidos al cerrar (`MAX_NODES` y doc) |

## Fase 5 — kairos-mcp (T-36 a T-49)

- **Fecha**: 2026-11-14
- **Lentes**: intentos 1 y 2, A+B y C+D en dos revisores; intentos 3 a 6, A+B+C+D en un revisor (D forzada desde el intento 3, porque el gap abierto era de rendimiento). El ciclo 2 (intentos 4 a 6) se abrió con el OK del usuario tras el intento 3.
- **Veredicto**: cerrada en el intento 6, sin hallazgos Critical ni Important abiertos.
- **Evidencia**:
  - Suite backend: 727 tests al implementar y 743 desde fix1; 0 omitidos y 0 llamadas a `/api/chat`. Suite de `mcp/`: 99, 113, 116, 123, 128 y 136 tests.
  - CI en verde en los runs 43543867333, 43551205331, 43574788571, 43579158717 y 43583624763.
  - Humo del contenedor: `PASS health 200; tools 34`.
  - Contrato MCP: 34 herramientas, nombres y esquemas idénticos; solo cambian claves `x-kairos-*` (`send_instead` en `rebuild_corpus`, `untrusted: true` en `query_corpus`).

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Esquema recompilado en cada `tools/call`; UUID en otra forma con 404; respuesta de más de 8 MiB como no disponible; `GET …/corpus` exigía `write` | Corregidos en fix1 |
| 1 | Minor | Segmentos `.`/`..`; `tools/list` con cualquier Bearer; `trust_env`; paridad documentada de más; orden de errores de `rebuild_corpus`; enteros `20.0`; tests en cadena sin `null`; `query_corpus` sin envoltorio S-05; 200 sin objeto; test de plazo dependiente del tiempo | Corregidos en fix1 |
| 2 | Important | La validación recorría todos los errores (60 000 ids: 11 s de bloqueo) | Corregido en fix2 (16 errores como máximo) |
| 2 | Minor | Pico de memoria de 5-7x con el tope de 96 MiB; comentario del tope; diferencia de 401 sin documentar | Corregidos (tope de 64 MiB, `mem_limit: 1g`, documentación) |
| 3 | Important | `anyOf` materializaba todos los errores de cada rama (13,8-28,8 s) | Corregido en fix3 (ciclo 2) |
| 4 | Important | Con elementos válidos y un fallo exterior, el array se recorría en el event loop (1,5-2,5 s) | Corregido en fix4 (validación en un hilo con concurrencia acotada) |
| 5 | Important | Las llamadas pequeñas hacían cola detrás de las grandes | Corregido en fix5 (vía rápida hasta 1000 valores y plazo de cola de 5 s) |
| 6 | Minor | Cifras de la doc que no eran de HTTP; test de tiempos frágil | Corregidos al cerrar |
| — | Residual | El CPU de un solo proceso es un techo que un cliente con muchas peticiones grandes puede alcanzar | Documentado: corresponde al proxy o al rate limiting del operador |

## Fase 6 — Compatibilidad (T-51 a T-55)

- **Fecha**: 2026-11-14
- **Lentes**: A+B y C (activada por `nginx.conf` y `docker-compose.yml`) en dos revisores.
- **Veredicto**: cerrada en el intento 1 de 3, sin hallazgos Critical ni Important.
- **Evidencia**:
  - Suite: 756 tests al implementar y 757 al cerrar; 0 omitidos y 0 llamadas a `/api/chat`. CI 43591247077 en verde.
  - nginx real con stubs (35 rutas crudas y la sonda de 17 casos): sin traversal ni smuggling por `/mcp`; `/metrics` cerrado; `nginx -t` en verde tras el cierre.
  - Contrato MCP sin cambios; Compose solo añade una red, una dependencia y `MEMORY_MOUNT_MCP` con valor por defecto compatible.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Minor | El MCP interno sigue accesible en `/memory-api/mcp/` y los textos decían lo contrario; la cookie del portal llegaba a kairos-mcp | Corregidos al cerrar |
| 1 | Minor | Formato no estándar de `Deprecation`/`Sunset`; 307 de `POST /mcp` sin cabeceras | Documentados; la fecha de retirada la decide el usuario |
| 1 | Minor | Sin prueba de extremo a extremo CLI → nginx → kairos-mcp | Deuda para la Fase 8 (T-72) |

## Fase 7 — Estructura del repositorio (T-57 a T-67)

- **Fecha**: 2026-11-14
- **Lentes**: intento 1, A+B y C+D en dos revisores (el selector activa C y D por la CI, el Compose y los Dockerfiles); intento 2, A+B sobre las correcciones.
- **Veredicto**: cerrada en el intento 2 de 3, sin hallazgos Critical ni Important abiertos.
- **Evidencia**:
  - Movimientos solo de movimiento: 128, 53 y 2 renombrados al 100 % sin líneas cambiadas; EOL sin cambios.
  - Suite del servidor: 757 tests en la línea base y 759 al cerrar; 0 omitidos y 0 llamadas a `/api/chat`. `store_surface.json` idéntico; `npm pack` con los mismos 34 ficheros.
  - `docker compose config` frente a la base: solo cambian las 6 líneas `dockerfile:`; redes, volúmenes, nombres y puertos iguales.
  - CI en verde en los runs 43617300808 y 43620955201; cierre: la ejecución del push del commit de cierre.
  - Contrato MCP sin cambios.

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | Órdenes de los manuales que ya no funcionaban desde la raíz con el paquete en `server/` | Corregido en fix1 (`PYTHONPATH=server`) |
| 1 | Minor | Verificación de T-60 con la puerta antigua; test de tiempos de la Fase 5 inestable en CI; sin test de actualización desde 0.3.0 | Corregidos en fix1 |
| 1 | Minor | Merge de `main` en lugar de rebase; `client/.npm-cache` en la imagen de tests (anterior a la fase) | Deuda aceptada |
| 2 | Minor | Evidencia de T-60 con `python -I`; bucle de espera sin tope en el test nuevo | Corregidos al cerrar |
