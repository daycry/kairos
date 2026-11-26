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

## Fase 2 — Esquema 13, scrypt y contraseñas (T-06 a T-12)

- **Fecha**: 2026-11-23 a 2026-11-26
- **Lentes**: A, B, C y D en los tres intentos (C por `auth`, `password`, `docker-compose.yml` y `ci.yml`; D por `schema.sql`, caché y migraciones). Intento 3 con Opus 5.5 por petición del usuario. Las lentes ejecutaron solo imágenes locales de pruebas (`kairos-test:i4p2`, `-fix1`, `-fix2`) sin red, con PostgreSQL efímero dentro del contenedor.
- **Veredicto**: cerrada. El intento 3 no dejó Critical ni Important. Sus seis Minor quedaron así: tres de ledger corregidos por el orquestador, uno aceptado como límite declarado en DC-5 y dos corregidos en el fix3. El fix3 se verificó con una comprobación dirigida, no con una ronda completa, por decisión del usuario («Fix3 pequeño y cerrar», 2026-11-26).
- **Evidencia**: suite del servidor 1687 tests, 0 fallos, errores y omitidos (`kairos-test:i4p2-fix3`); `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1687; `scope-check.py --base main` exit 0; `openapi-lint --diff` contra `c926f7a` sin cambios rompedores (solo `/v1/auth/password`); `kairos-mcp.json` sin cambios en la fase; migración 13 aditiva y cerrada. Comprobación dirigida del fix3: BOM inicial y bytes no UTF-8 dan `password_file_invalid` sin bytes del secreto; los espacios se conservan y solo se quita un salto final; `scripts/tests/test_bootstrap_password_file.py` 4 OK.

| Intento | Diff | Important | Hallazgo principal | Estado |
|---|---|---|---|---|
| 1 | `c926f7a..d5986db` | 5 | Cambio de contraseña sin tope acaparando el semáforo; `create_user` derivaba antes de autorizar; carrera entre login y cambio de contraseña; coste de producción sin fijar por test; DC-6 probado como «contiene» | Fix1, OK del usuario («5 Important + Minors») |
| 2 | `01e5e12..c9b6dae` | 2 | Clave creada en paralelo a `set-password --revoke-keys`; recuento de cambios recorriendo `audit_events` entera | Corregido (fix2, en dos sesiones) |
| 3 | `22de18e..682d5f5` | 0 | Lectores del fichero de secreto en los scripts; BOM; coste del recuento con el volumen de la ventana | Fix3 fuera del bucle y comprobación dirigida, OK del usuario |

### Decisiones del usuario

- `admin set-password --revoke-keys`: por defecto conserva las claves; con la opción las revoca en la misma transacción (2026-11-23).
- Notas de límite en DC-5 escritas por el orquestador, porque el implementador no puede editar el diseño («Hazlo tú», 2026-11-26).

### Límites declarados (DC-5)

- Con un hash anterior, el login tarda distinto que con un usuario inexistente; desaparece cuando cada cuenta entra una vez.
- El recuento de cambios de contraseña está acotado por la clave primaria: un margen de microsegundos en el borde de la ventana, y un coste que crece con los eventos de auditoría de los últimos 15 minutos (unos 128 ms con 100 000). Lo resolvería un índice por `happened_at` en una versión 14.
- En la carrera con otro login que rehízo el hash, un intento hace dos derivaciones (reintento único).

### Diferido a otras tareas

- `Retry-After` en los 429 de `POST /v1/auth/password` → T-26 (criterio añadido).
- Altas de usuario encadenadas por un admin de proyecto que ocupan el hueco de la IP del proxy → T-27 (IP real) y T-55 (tasa por credencial).
- `login_attempts` cuenta también los logins correctos → T-26 (solo fallos).

## Fase 3 — Usuarios, permisos y sesiones (T-13 a T-18)

- **Fecha**: 2026-11-26 a 2026-11-27
- **Lentes**: A, B, C y D en Opus 5.5 en los dos intentos (C por `auth`, `sessions` y `users`; D por caché y bloqueos). Las lentes ejecutaron solo imágenes locales de pruebas (`kairos-test:i4p3`, `-fix1`) sin red, con PostgreSQL efímero dentro del contenedor.
- **Veredicto**: cerrada. El intento 2 no dejó Critical ni Important. De sus tres Minor, uno de ledger lo corrigió el orquestador, uno se acepta como límite del marco y uno se difiere a T-22.
- **Evidencia**: suite del servidor 1745 tests, 0 fallos, errores y omitidos (`kairos-test:i4p3-fix1`); `KAIROS_MIN_TESTS` y `MIN_FLOOR` 1745; `scope-check.py --base main` exit 0; `openapi-lint --diff` contra `cc44e76` 0 rompedores de 6 (solo rutas nuevas); `kairos-mcp.json` sin cambios; guarda de T-02 con tres excepciones nuevas declaradas en DC-1; carga de 1 905 operaciones de acceso concurrentes sin interbloqueos.

| Intento | Diff | Important | Hallazgo principal | Estado |
|---|---|---|---|---|
| 1 | `cc44e76..baef4b6` | 3 | Alta de usuario en carrera con la deshabilitación del delegante; cambio de contraseña desde una sesión ya cerrada; fines de línea CRLF convertidos | Fix1, OK del usuario («Important + Minors baratos») |
| 2 | `baef4b6..3e6c4af` | 0 | Revocar la clave o cerrar la sesión con que se hace un alta no la detiene; 422 de Pydantic antes del 403; trazabilidad de la ruta nueva | Cerrada: un Minor corregido, uno aceptado y uno diferido |

### Decisiones del usuario (2026-11-26)

- Fix1 con los Important y los Minor baratos.
- `grants.replaced` mantiene en `resource_id` el JSON canónico `{user, before, after}`; formato documentado en `docs/operations.md`.
- Ruta nueva `GET /v1/users/{id}/sessions`, solo para el administrador global (CA-42).
- Nota de DC-1 con las tres excepciones nuevas de la guarda, escrita por el orquestador («Hazlo tú»).

### Límites declarados

- Un cuerpo que no pasa la validación de FastAPI (tipo o permiso inexistente) responde 422 antes de comprobar la autorización. Los 422 que decide el store salen después del 403.
- Al deshabilitar, cambiar o fijar la contraseña solo se cierran las sesiones vivas; las caducadas quedan como están, porque ya no autentican y nada reescribe `expires_at`.

### Diferido a otras tareas

- Revocar la clave o cerrar la sesión con que está en curso un `create_user` o un `create_key` → T-22 (criterio y ficheros añadidos).
- 404 de `GET /v1/users/{id}/sessions` y sobre `{code, message}` del esquema `Error` en el OpenAPI → T-26 (criterio añadido).
