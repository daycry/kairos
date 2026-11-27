---
generacion:
  inicio: 2026-11-20T09:02:13Z
  fin: 2026-11-20T09:35:36Z
  fuente: medido
  fuente_id: src-8ffaaac4e3b9a11805b5148dbea387f65be01b42fba05cbf3ca54c4b799a95c8
  ventana_id: win-dda81c1e73804eb983428ca6945fdc42
  revision_medicion: 1
  medicion_persistida: true
  tokens_reales: { entrada: 78, salida: 219170, cache_creacion: 620863, cache_lectura: 10449331, respuestas: 39 }
  eur: null               # precioTokens no fiable: ejecutar rates-verify
  horas_ia: 2.8
  duracion: 2h 48m         # reloj: 33m
  ratio_usado: 300000     # default no calibrado
  # ventana compartida con improvement-plan.md
verificacion: obligatoria   # cada T-XX lleva `- **Verificación**:`; lo exige ledger-lint (exit 1 si falta)
test-plan: test-plan.md
---

# Checklist de Tareas — Control de acceso y privacidad (Iniciativa 4 de Kairos)

| | |
|---|---|
| **Estado** | en-progreso |
| **Fecha** | 2026-11-20 |
| **Plan** | [`improvement-plan.md`](./improvement-plan.md) |
| **Diseño** | [`design.md`](./design.md) — opción O2 «Costuras de acceso» |

> **⚠️ Ledger canónico de progreso.** Este fichero es la **fuente única de verdad** del avance del plan. **Cualquier** implementador —el agente `implementer`, el chat principal, o un orquestador SDD externo— **debe** marcar aquí cada tarea (checkbox + estado) al completarla y actualizar el resumen. Los ledgers propios de otras herramientas son **espejo**, no fuente.

> **Cifras.** Por tarea, las horas humanas, IA y de supervisión (≈ 25 % de las horas IA) son **base** (sin margen) y estimadas; el coste de los tokens queda ⚠️ por verificar; las filas de fase y el resumen llevan el **+20 %** ya aplicado. Cada tarea y **cada intento de revisión** abre y cierra `usage-meter` y anota su JSON en `Notas`. El implementer no escribe en `docs/roadmap/**/testing/` (reservado a `qa`): las evidencias van al ledger o junto a los tests.

> **Restricciones duras (valen para todas las tareas).** Nada contra la base desplegada, ni contra contenedores, volúmenes o redes `knowledge-graphs-*`, ni contra el portal desplegado (`127.0.0.1:5173`). Migraciones solo aditivas: la versión 13 se define entera en T-06 y no se reabre. El contrato MCP (`docs/contracts/kairos-mcp.json`) no cambia. Nada se publica (`npm publish`, `docker push`). Docker en primer plano y de uno en uno; ensayos y mediciones en proyectos Compose `kairos-acc-*` desechables. Ningún secreto real en el repositorio ni en una imagen. `web/nginx.conf` y `docker-compose.yml` los usa la instalación desplegada: sus cambios le llegan en su próximo `up` (Iniciativa 5) y ninguna tarea recrea servicios reales. Fin de línea conservado (`.gitattributes` es `* -text`).

> **Protocolo de cierre de fase** (tareas «Cierre de fase»). (1) Ejecutar las suites que cita la tarea, en primer plano y de una en una. (2) Anotar `MEMORY_TEST_RESULT`. (3) Subir el mínimo al recuento observado, nunca bajarlo, en los **cuatro sitios**: `KAIROS_MIN_TESTS` de `.github/workflows/ci.yml` (con su comentario de historia), `MIN_FLOOR` de `scripts/tests/test_ci_workflow.py`, y «(N pruebas)» de `docs/operations.md` y de `README.md`. (4) La CI externa puede no ejecutarse: la ejecución local en Docker cierra el criterio y se anota en `Notas`. (5) Archivar las notas de la fase: `python3 "$SHAREDKIT/ledger-archive.py" docs/roadmap/2026-11-19-access-control --apply`.

> **Protocolo de revisión adversarial** (tareas «Revisión adversarial de la fase»). Dos lentes sobre el diff de la fase: A (contrato, seguridad, regresiones y alcance declarado, frente a los CA, los campos `Archivos` y las restricciones duras) y B (mutantes: cada control nuevo se quita y su prueba debe fallar). Cada hallazgo se corrige para la clase entera. Cada fix que añade comportamiento se revisa como código nuevo, con lentes completas sobre su diff (CA-35), y suma un intento. Cada intento abre y cierra `usage-meter` y deja una fila en `review.md`. La fase cierra sin Critical ni Important abiertos, con los Minor aceptados listados con su motivo y con las suites en verde; si un fix añade pruebas, se repite el protocolo de cierre y el mínimo vuelve a subir.

> **Tamaño del ledger.** Límite práctico de 245.000 bytes. Las notas de tarea son breves; el detalle va a `execution-history.md` al cerrar cada fase.

> **Dependencia externa (no es tarea):** los tres PR (T-34 hito A, T-70 hito B y T-106 hito C) solo se abren con el OK expreso del usuario; no se hacen merges ni se publica nada.

```curation-refs-v1
[
  {
    "candidate": "docs/knowledge/candidates/pending/2026-11-20-access-seams-server-capabilities.md",
    "sha256": "82c84969b6f7aa0f69e0aa780d2220973e11cbe43300506e3999469d7d9d7635"
  }
]
```

---

## Resumen de progreso

| Fase | Completadas | Total | Progreso | H. humanas (real/est) | H. IA ejec. (real/est) | Supervisión (real/est) | Tokens (real/est) |
|------|------------|-------|----------|-----------------------|------------------------|------------------------|-------------------|
| Fase 1 — Medición de scrypt y guarda del resolvedor (CA-09, CA-38 a) | 5 | 5 | 100% | 0 / 19.8h | 4.77 / 6.3h | 0 / 1.6h | 0 / 1570 k |
| Fase 2 — Esquema 13, scrypt y contraseñas (C-01) | 7 | 7 | 100% | 0 / 36.0h | 3.88 / 3.7h | 0 / 0.9h | 0 / 924 k |
| Fase 3 — Usuarios, permisos y sesiones (C-01) | 6 | 6 | 100% | 0 / 36.0h | 5.14 / 3.7h | 0 / 0.9h | 0 / 924 k |
| Fase 4 — Claves: caducidad, último uso, rotación y `kairos doctor` (C-01) | 6 | 7 | 85.7% | 0 / 48.0h | 1.90 / 4.9h | 0 / 1.2h | 0 / 1232 k |
| Fase 5 — Login que no se bloquea entre clientes (C-02) | 0 | 5 | 0% | 0 / 43.2h | 0 / 4.4h | 0 / 1.1h | 0 / 1109 k |
| Fase 6 — Cierre del hito A: acceso que se puede retirar | 0 | 4 | 0% | 0 / 9.6h | 0 / 3.5h | 0 / 0.9h | 0 / 873 k |
| Fase 7 — Mediciones del hito B y superficie de secretos (C-06) | 0 | 8 | 0% | 0 / 44.4h | 0 / 12.3h | 0 / 3.1h | 0 / 3082 k |
| Fase 8 — Redacción: casos compartidos, patrones y entropía (C-04) | 0 | 6 | 0% | 0 / 42.0h | 0 / 4.3h | 0 / 1.1h | 0 / 1078 k |
| Fase 9 — Redacción en todas las rutas y de extremo a extremo (C-04) | 0 | 5 | 0% | 0 / 34.8h | 0 / 3.6h | 0 / 0.9h | 0 / 893 k |
| Fase 10 — Límites en el servidor: clases, tasa, cuota y flujos (C-03) | 0 | 7 | 0% | 0 / 60.0h | 0 / 6.2h | 0 / 1.5h | 0 / 1540 k |
| Fase 11 — Límites en `kairos-mcp` y en el cliente (C-03) | 0 | 6 | 0% | 0 / 38.4h | 0 / 3.9h | 0 / 1.0h | 0 / 986 k |
| Fase 12 — Cierre del hito B: clientes acotados y secretos fuera | 0 | 4 | 0% | 0 / 9.6h | 0 / 3.5h | 0 / 0.9h | 0 / 873 k |
| Fase 13 — Capacidades del servidor y base del portal (C-05, C-08) | 0 | 7 | 0% | 0 / 35.7h | 0 / 3.7h | 0 / 0.9h | 0 / 916 k |
| Fase 14 — Portal: «Mi cuenta» y «Claves para agentes» (C-08) | 0 | 6 | 0% | 0 / 42.3h | 0 / 4.3h | 0 / 1.1h | 0 / 1086 k |
| Fase 15 — Portal: «Usuarios», alta delegada y paridad (C-08) | 0 | 9 | 0% | 0 / 54.6h | 0 / 5.6h | 0 / 1.4h | 0 / 1401 k |
| Fase 16 — Identidad: guía probada y extensibilidad (C-05) | 0 | 5 | 0% | 0 / 23.4h | 0 / 2.4h | 0 / 0.6h | 0 / 601 k |
| Fase 17 — Revisión del hito C y revisión de seguridad (C-07) | 0 | 5 | 0% | 0 / 27.0h | 0 / 5.3h | 0 / 1.3h | 0 / 1320 k |
| Fase 18 — Cierre del hito C y de la iniciativa: ensayo, versión 0.4.2 y PR | 0 | 4 | 0% | 0 / 11.4h | 0 / 1.2h | 0 / 0.3h | 0 / 293 k |
| **TOTAL** | **24** | **106** | **22.6%** | **0 / 616.2h** | **15.69 / 82.8h** | **0 / 20.7h** | **0 / 20700 k** |

> **Imputación externa opcional.** El adaptador elegido recibe las mediciones disponibles y aplica su contrato de jornada, supervisión e idempotencia. No inventes tiempo real ni recalcules horas fuera de su dueño; sin integración los datos permanecen locales.

---

## Fase 1 — Medición de scrypt y guarda del resolvedor (CA-09, CA-38 a)

**Estado**: completado · **Hito**: A · **Estimado**: 19.8h (16.5h base, de ellas 4h de revisión adversarial) · **Real**: 4.77h IA (medido; revisión del orquestador sin medir) · **Coste est.**: 990 € · **Tokens est.**: 1570 k

### T-01 — Medición previa de scrypt en `memory-api`, `memory-bootstrap` y `memory-admin` (CA-09)

- **Descripción**: Medir tiempo y memoria pico de una derivación scrypt con los candidatos `n=2^17, r=8, p=1` y `n=2^16, r=8, p=2` (y el actual `n=2^14`) dentro de los tres contenedores que derivan scrypt, cada uno con su `mem_limit`: `memory-api` (1 GB del VPS y 2 GB por defecto), `memory-bootstrap` (256 MB) y `memory-admin` (1 GB). Medir también si `hashlib.scrypt` libera el GIL y la memoria de la API en reposo. Fuente: CA-09; P-04; DC-5; R-02.
- **Changelog**: Interno: medición previa del coste de scrypt en los contenedores que lo derivan; confirma n=2^17.
- **Estado**: completado
- **Cerrada**: 2026-11-20
- **Tiempo humano**: est. 4.5h · real —
- **Tiempo IA (ejec.)**: est. 4.00h · real 0.38h (medido)
- **Supervisión**: est. 1.00h · real —
- **Previsión IA**: 1104 k in / 96 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/measure-scrypt.py`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md` (tabla «Valores medidos»), `docs/roadmap/2026-11-19-access-control/execution-history.md` (JSON de la medición; fichero nuevo del historial, añadido con nota), `scripts/tests/test_measure_scrypt.py` (fichero nuevo del fix1, gap 9, añadido con nota)
- **Cubre (tests)**: —
- **Verificación**: `python scripts/measure-scrypt.py --image-target operator` → JSON con una fila por contenedor y candidato (`seconds`, `peak_mb`, `fits`) y `gil_released`

**Criterios de aceptación**
- [x] La medición queda en `Notas` y en «Valores medidos» **antes** de T-07: parámetros definitivos, huecos de `MEMORY_LOGIN_CONCURRENCY` y si hay que subir `MEMORY_BOOTSTRAP_MEM_LIMIT`
- [x] Corre con `docker run --memory=<mem_limit> --network=none` sobre una imagen local, de uno en uno; nada `knowledge-graphs-*`
- [x] Si `n=2^17` no cabe en 256 MB, la decisión (subir el límite de `memory-bootstrap` o usar `n=2^16, p=2`) queda escrita con su motivo

**Subtareas**
- [x] Escribir el script (imagen `operator` local, un contenedor por límite)
- [x] Ejecutar y anotar las tres hipótesis de DC-5
- [x] Proponer valores y escribirlos en el plan

**Notas**: Estimada en 4 h IA: usa contenedores y repite mediciones (retro de la Iniciativa 3). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `da8fb402e7fe`.

### T-02 — Guarda del resolvedor: `is_admin`, excepciones cerradas y módulos autorizados a escribir (CA-38 a)

- **Descripción**: Ampliar el recorrido de `test_auth_cache.py:461` para que detecte toda lectura de `project_grants`, de los permisos de una clave y de `actors.is_admin` (en SQL y en accesos `['is_admin']` o `.get('is_admin')`) fuera del resolvedor, con la lista cerrada de excepciones de DC-1 y su justificación. Añadir la lista de módulos que pueden escribir las tablas de permisos: `store_auth.py`, `store_access.py`, `auth.py` y `probe.py` (1 h, coste extra de O2). Nace en rojo por los cuatro lectores de DC-1. Fuente: CA-38 (a); DC-1; D-02; design.md §O2.
- **Changelog**: Interno: una prueba comprueba que solo el resolvedor lee permisos y que solo cuatro módulos escriben las tablas de permisos y credenciales.
- **Estado**: completado
- **Cerrada**: 2026-11-20
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real 4.11h (medido; 0.13h la tarea y los fixes 1 a 12: 0.47, 0.19, 0.17, 0.54, 0.15, 0.29, 0.30, 0.60, 0.52, 0.27, 0.33 y 0.15h)
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_auth_cache.py`, `server/requirements-test.txt` (fichero nuevo del fix8: `pglast`, solo etapa `test`), `server/memory_platform/Dockerfile` (fix8, una línea `pip install` en la etapa `test`), `docs/roadmap/2026-11-19-access-control/design.md` (nota DC-1)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|MEMORY_TEST_RESULT"` → el test nuevo falla solo por los cuatro lectores de DC-1 (rojo esperado; verde en T-03)

**Criterios de aceptación**
- [x] Una lectura nueva fuera del resolvedor y de la lista deja el test en rojo, y cada excepción lleva su justificación en el propio test
- [x] Un `INSERT`, `UPDATE` o `DELETE` sobre `actors`, `project_grants`, `api_keys` o `web_sessions` fuera de los cuatro módulos deja el test en rojo (mutante comprobado)
- [x] El rojo inicial enumera exactamente los cuatro lectores de DC-1 y queda anotado como `RED:`

**Subtareas**
- [x] Recorrido de lectores con `is_admin` y excepciones
- [x] Lista de módulos escritores y mutante

**Notas**: `ResolverBoundaryTests` (5 pruebas, `test_auth_cache.py`) sustituye a `test_no_function_reads_the_permission_tables_...` (más laxa; el nuevo la subsume). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `9ed2198d0b03`. fix8 (intento 8, cambio de método aprobado por el usuario 2026-11-20): la guarda analiza cada literal SQL con el parser de PostgreSQL 17 (`pglast` 7.24; 7.x sigue la gramática de PG17 y 8.x la de PG18, y 7.24 es la última 7.x con rueda manylinux cp311) en lugar de regex. Se instala solo en la etapa `test` (`server/requirements-test.txt`); `api`, `operator` y `worker` no lo llevan: ver la comprobación en el informe de T-04. Del árbol salen lecturas y escrituras por tabla, `FOR SHARE` con su `OF`, fila completa de `actors` con alcance (consulta, CTE, subconsulta, `;`, alias con o sin comillas) y tabla no literal (centinela en el nombre, también como sufijo). `is_admin` sigue siendo cualquier literal que escriba la palabra. Lo que no parsea y nombra una tabla de la guarda o lleva un hueco es `unparseable SQL`. Cambios de semántica: un RETURNING de fila completa de un DML sobre `project_grants`/`api_keys` cuenta como lectura (pedido por el caso `UPDATE api_keys k ... RETURNING k.*`); `memory.%s` crudo es hueco (psycopg no liga identificadores); `memory."%s"`/`{}` entre comillas también. Cambian de lado solo falsos positivos o negativos de la regex: verde ahora `SELECT s.* ... JOIN actors a`, `count(p.*)`, el CTE y `;` con `RETURNING *` de otra tabla, `INSERT ... SELECT FROM actors a RETURNING *`, `COPY actors FROM STDIN`, `RETURNING s.*`/`k.*` ajenos, `DELETE FROM actors RETURNING a.*` con `a` sin definir, un hueco tras `;`; rojo ahora `DISTINCT ON (lower(trim(x))) *`, `"a"` con `AS "a"`, `CAST(a AS text)`, `((a)).*`, `IS DISTINCT FROM y, a.*`, `WITHIN GROUP ..., a.*`, `WHERE to_jsonb(a.*)`, `ORDER BY row(a.*)`, `note='admin update' ... RETURNING *`, `MERGE ... THEN UPDATE ... RETURNING *`, `$$ ' $$` y `E'\''` con `a.*`, `memory.api_{kind}`. Seis entradas nuevas de la lista cerrada con solo el kind `unparseable SQL` (SQL por fragmentos que no parsea entero): `admin.py` (`<module>`, `backfill_query`, `backfill_failed`, `backfill_remaining`), `store_jobs.py` (`<module>`) y `VectorsMixin._vector_candidates`; ninguna nombra una tabla de la guarda. Corpus de 3029 literales de todas las revisiones y del paquete frente a `b78f616` y `1c33aa2`: 6 pérdidas, todas falsos positivos de la lista anterior (arriba); ninguna detección real perdida. Coste, medido fuera de Docker (3 medidas, equipo con carga variable), antes (`1c33aa2`) -> ahora: escaneo en frío del paquete 0,44-0,56 s -> 0,28-0,34 s; clase `ResolverBoundaryTests` 4,9-6,1 s (16 pruebas) -> 3,8-4,3 s (17 pruebas). RED (contra `1c33aa2`, solo de fondo): test_a_whole_row... falló en 12 formas (IS DISTINCT FROM, WITHIN GROUP, `WHERE to_jsonb`, `ORDER BY row`, `note='admin update'`, MERGE THEN UPDATE, `$$ ' $$`, `E'\''`, DISTINCT ON anidado, `"a"`, CAST, `((a))`) y en los verdes (1); test_the_column... dio error por `memory.api_{kind}` y los huecos con `$$`/`E''` (1); test_the_parser_tells... falló por el kind nuevo `unparseable SQL` y las lecturas por RETURNING (cambio de API, 1). Verde: las 17 pruebas de `ResolverBoundaryTests` y la suite. usage-meter close access-control/T-02-fix8: 0.6 h IA (medido), 92 in / 74257 out tok. fix9 (intento 9, dentro del método del parser): corrección de la nota de fix8: «ninguna detección real perdida» no se sostenía para fragmentos. (1) Se analiza todo literal, ya relleno, que nombre con `\b` una tabla de la guarda o lleve un hueco no constante, sea cual sea su inicio (fragmentos, EXPLAIN, PREPARE, CALL, DECLARE, CREATE AS, SET LOCAL; el cuerpo de DO y un SQL en cadena, recursivamente); `_STATEMENT_START` desaparece. (2) Si no parsea (o excede 32 768 caracteres, el mayor literal del paquete tiene 1 896, o es demasiado profundo), informa `unparseable SQL` si nombra una tabla, cada tabla nombrada (lectura; `actors` como fila; escritura si una palabra de escritura la precede) y `unknown table` si hay hueco tras FROM/JOIN/INTO/UPDATE/TABLE/USING/TRUNCATE, `memory.` o coma tras un FROM; sin palabra de SQL o sin tabla ni hueco de tabla calla (los mensajes con f-string). Las seis exenciones de fix8 sobraban y se retiran: ninguna función del paquete queda roja por ello; entra `project_grants` en `provision_locked` (su `INSERT ... RETURNING 1` lee lo que devuelve). (3) El `%s` crudo es hueco (`memory.%s`, `"%s"`). (4) Tokenizador de una pasada lineal; `RecursionError` y cualquier excepción dan el informe de respaldo; una fuente demasiado profunda da `unparseable SQL` del módulo. (5) `RETURNING` de columnas de `api_keys`/`project_grants` es lectura; alias de un `JOIN` entre paréntesis y `TABLESAMPLE` cuentan; un hueco solo en la lista del SELECT con `actors` es `is_admin:row`; `U&"..."` decodificado a `is_admin` es lectura. Piezas constantes de una composición ya no se leen una a una. Corpus de 3150 literales de las 19 versiones del test y del paquete frente a `1c33aa2` y `8b1370a`: 9 y 6 pérdidas, todas falsos positivos: `RETURNING s.*`/`k.*` ajenos, `RETURNING *` de `INSERT ... SELECT`, `COPY actors FROM`, `RETURNING a.*` con `a` sin definir, `SELECT s.* ... JOIN actors`, prosa que nombra tablas (docstring y mensaje con `%s`), cinco `wr` de fix8 sin palabra de escritura (`SELECT ... FROM memory.api_keys`) y un cambio de kind (`FROM memory.{t} WHERE {cond} {extra}`: de `unparseable SQL` a `unknown table`, sigue rojo). Cifras medidas fuera de Docker, fix8 -> fix9: `'/**/'*16/20/22/24+'x'` 0,03/0,45/1,98/6,84 s -> 0,00 s; `'/**/'*5000+' FROM memory.api_keys'` >150 s -> 0,47 s; `'/*'*40000+' FROM memory.api_keys'` 0,09 s; `'/*'*10000`, `'$a$'*5000`, `"'"*10000`, `"E'"*5000` 0,00 s; `'FROM a, '*4000` y `'SELECT 1 FROM a '*4000` 0,02 s; 2000 `UPDATE ... RETURNING` 0,03 s; escaneo en frío del paquete 0,82-0,94 s -> 0,72-0,85 s; clase `ResolverBoundaryTests` (más pruebas) 9,9-10,3 s -> 9,0-10,3 s (máquina con carga). RED (contra `8b1370a`, solo de fondo): test_every_literal... falló en 12 formas (fragmentos, EXPLAIN, PREPARE, CALL, DECLARE, CREATE AS, SET LOCAL, `query_to_xml`, DO, escritura tras EXPLAIN/DO); test_more_forms... (alias de JOIN, TABLESAMPLE, RETURNING de columnas, hueco en el select, `U&`); test_the_guard_does_not_break... (anidamiento, literal enorme, fuente profunda, aperturas sin cerrar); test_the_parser_tells... (prosa con llaves y huecos); test_the_scans_stay_linear (`'/**/'*30`: más de 5 s). Verde: las 27 pruebas de las clases de guardas y la suite. usage-meter close access-control/T-02-fix9: 0.52 h IA (medido), 110 in / 64807 out tok. fix10 (intento 10): (1) sin puerta léxica: se parsea todo literal relleno de hasta 32 768 caracteres (los 1957 literales distintos del paquete tardan 0,16 s); los huecos de plantilla (`{}`, `{name}`, `{0}`, `%s`, `%(x)s`, `%d`) y los NUL son centinela y la posición de tabla la decide el árbol (`ONLY`, `COPY`, `TRUNCATE`, tras comentario, sufijo `api_{kind}`, `U&"..."` decodificado). Se retiran `_AFTER_SCHEMA`, `_HOLE_TABLE`, `_HOLE_AFTER_COMMA` y `_SQL_STRING`. Aserciones de fix8 restauradas con sus `{}` (`SELECT 1 FROM {}`, `memory.{}`, `memory."{}"`, `TRUNCATE {t}`, `SELECT {x}, 1 FROM ... WHERE a = {y}`); NO se restaura `SELECT {} FROM memory.embeddings e WHERE e.v {}` -> `unparseable SQL`, porque el punto 2 pide que un texto sin tabla vigilada y solo con huecos calle. (2) Parse fallido: solo cuenta si nombra una tabla vigilada con una palabra de SQL (`unparseable SQL` y cada tabla); solo huecos = prosa, silencio; el paquete no tiene prosa que nombre una tabla vigilada (0 funciones rojas). Se mantiene la exigencia de palabra de SQL para no marcar nombres sueltos como `'web_sessions'`. Límite declarado: un fragmento que no parsea cuyo único dato es un hueco de tabla no se ve (la composición que lo usa, si parsea entera, sí). Cambiaron de valor por ello: `f'SELECT 1 FROM memory.{t} WHERE {cond} {extra}'` ya no es `unknown table` (no parsea: dos huecos seguidos; el mutante ahora usa solo `{cond}`) y los tres `sql_dynamic` de fragmentos con hueco (`'SELECT x FROM \x00 WHERE (( '` y otros dos) pasan de verdadero a falso. (3) Todo texto dentro del árbol (`A_Const` de cadena, `DefElem` `as` de DO, CREATE FUNCTION y CREATE PROCEDURE) se vuelve a analizar, hasta 4 niveles, con respaldo. (4) `LOCK TABLE`, `ANALYZE` y `VACUUM` ya no son lectura; `ALTER TABLE`, `CREATE INDEX`, `RENAME` y `DROP` sobre `WRITE_TABLES` son escritura (nada del paquete pasa a rojo: el esquema vive en `schema.sql`). (5) Corpus de 3205 literales (19 versiones del test, el paquete en `main` y en HEAD) frente a `1c33aa2`, `8b1370a` y `c4f86c7`: 16, 7 y 16 pérdidas, ninguna real salvo el límite declarado de arriba; clases: falsos positivos de regex o de prosa (`RETURNING s.*` ajenos, `COPY actors FROM`, `only %s may write actors, ...`, el docstring de la guarda, `insert into {x} failed`, `cannot restore from {path}`), cinco `wr` de fix8 sin palabra de escritura, cambios de kind (`ALTER TABLE ... api_keys` de lectura a escritura; `LOCK`/`ANALYZE`/`VACUUM` de lectura a nada, a propósito) y el fragmento con hueco de tabla que no parsea (límite). (6) La fila 4 del intento 9 («corregido») no tenía RED en fix9: su mutante `%s` aplicado con `%` ya pasaba con fix8; lo que sí faltaba (`%s` crudo en una constante, `memory.%s` sin `%` visible) entra ahora en `sql_dynamic`. RED (contra `c4f86c7`, de fondo): test_templates_in_constants_prose... dio error en 9 formas (8 plantillas con hueco y `U&"api\\005fkeys"`); test_each_control... y test_the_parser_tells... fallaron por las aserciones restauradas con `{}`; test_every_literal... falló por `ALTER`/`LOCK`/recursión de cadenas. Verde: las 28 pruebas de las clases de guardas y la suite. usage-meter close access-control/T-02-fix10: 0.27 h IA (medido), 50 in / 32837 out tok. fix11 (intento 11, aprobado por el usuario 2026-11-23): (1) en un texto que no parsea (o de más de 32 768 caracteres, o con un comentario sin cerrar), `memory.` seguido de un hueco (`memory."<hueco>"`, `"memory".<hueco>`, `MEMORY.`, `memory.api_<hueco>`) es siempre `unknown table` y `memory.<tabla vigilada>` es siempre esa tabla (`unparseable SQL`, lectura, escritura si una palabra de escritura la precede), sin exigir palabra de SQL; sin `memory.` sigue la regla de la palabra de SQL. Mutantes (módulo nuevo y `Auth.login`): `WHERE {cond} {order}`, `ORDER BY {col} {direction}`, `SET {sets}`, `x {join}`, `IN %s`, `{verb} ... FROM memory.{t}`, `WHERE {col} {op} %s`, `MEMORY.`, `"memory".`, `memory."{t}"`, `memory.api_{t}`, la composición en dos pasos (f-string y `% TABLE`), `on = 'memory.api_keys k ON ...'` y el literal de más de 32 768 caracteres; los de fix10 también dentro de `Auth.login`; restaurado el mutante de fix9 con `{cond} {extra}`. Límite declarado: un nombre de tabla entero dinámico sin `memory.` (`FROM {}`) dentro de una sentencia que no parsea, `format('%I.%I', ...)` y `'memory.' || 'x'`. (2) Falsos positivos: en el respaldo `actors` es `is_admin:row` solo con `*`, `a.*`, `TABLE` o `COPY ... TO`; el `INTO` desnudo de PL/pgSQL ya no es escritura y se quitan los `RAISE`; `pglast.parse_plpgsql` no sirve (pide un CREATE FUNCTION completo y todas las variables declaradas), así que los cuerpos PL/pgSQL se leen como texto que no parsea (declarado); `ANALYZE`, `LOCK`, `VACUUM` y `COMMENT` con un hueco no son `unknown table`; `REFERENCES` y `LIKE` no son lectura. Declarado: la prosa que parsea como SQL (`f'table {x}'`) es tabla desconocida; el paquete no tiene ninguna (0 funciones rojas, 0 obsoletas). (3) `CREATE TRIGGER/RULE/POLICY`, `COMMENT ON`, `GRANT ... ON`, `ALTER ... SET SCHEMA`, `CREATE TABLE` y `DROP SCHEMA memory` sobre `WRITE_TABLES` son escritura. (4) Coste: el lexer del parser es cuadrático en el número de comentarios de bloque (`'/*'*16000` 1,71 s, `'/**/'*8000+' FROM memory.api_keys'` 0,46 s); los comentarios ya no se le dan y uno sin cerrar no se parsea: 0,009 y 0,012 s. `test_the_cost_grows_linearly_with_the_input` compara n y 4n (cota 8x o 0,5 s). (5) Nota de fix10 exacta: RED de fix10 = 9 errores (`test_templates...`: 8 plantillas y `U&`) y 3 fallos (`test_each_control...`, `test_every_literal...`, `test_the_parser_tells...`), sin contar motivos que no verifiqué; el commit `eb6f105` dice archivar «long notes» y solo archivó las secciones de revisión de los intentos 7-9: las notas largas de T-02 siguen en este ledger. Cambios de valor de aserciones: `sql_reads('SELECT FROM WHERE memory.actors ((')` pasa a `{unparseable}` (sin `*`); el bare `'memory.api_keys'` de la prueba del `%` pasa a `['api_keys', 'unparseable SQL']` (ahora es tabla por sí solo); `sql_dynamic('SELECT 1 FROM memory.api_\x00 WHERE ((')` pasa de falso a verdadero. Corpus de 3270 literales (19 versiones del test y el paquete en `main` y HEAD) frente a `c4f86c7` y `ce7fde1`: 45 y 34 pérdidas: `is_admin:row` de textos que nombran `actors` sin `*` (docstrings, plantillas, prosa, fragmentos), prosa con hueco, `INTO` de PL/pgSQL, y cambios de kind (DDL de lectura a escritura; LOCK/ANALYZE/VACUUM, REFERENCES y LIKE de lectura a nada, a propósito); ninguna lectura real de `api_keys`/`project_grants`/`is_admin` perdida. RED (contra `ce7fde1`, 19): 15 de las 16 subpruebas de `test_a_statement_that_does_not_parse...` (la de `project_grants` ya pasaba), 1 error de `test_every_literal...` (mutante de fix9 restaurado) y 3 pruebas (DDL, coste, falsos positivos). Verde: las 32 pruebas de las clases de guardas y la suite. usage-meter close access-control/T-02-fix11: 0.33 h IA (medido), 60 in / 39174 out tok. fix12 (intento 12, aprobado por el usuario 2026-11-23): corrección de la nota de fix11: su RED, en la salida de unittest, fue de `failures=18, errors=1` (19) con `test_every_literal...` como error; la revisión cuenta 20 con esa prueba como fallo: se deja constancia de las dos cuentas. (1) Se retira `_without_raise`: el texto de un `RAISE` se analiza como cualquier otro; un mensaje o cadena PL/pgSQL que nombre una tabla vigilada es falso positivo (rojo), declarado en el docstring y en la nota DC-1; el paquete no tiene ninguno (0 funciones rojas, 0 obsoletas). Mutantes en módulo nuevo y en `Auth.login`: `AS raise`, `-- raise the limit` (lectura y escritura), `/* raise if none */`, `'raise' AS action`, `RAISE NOTICE '%', (SELECT ... memory.api_keys)`. La aserción que fijaba el silencio (`DO $$ BEGIN RAISE NOTICE 'could not read from actors'; ...`) pasa de `set()` a `{unparseable SQL}`. (2) `--` termina también en `\r`; nombres, palabra de SQL y escritura se buscan en el texto sin comentarios (salvo un comentario de bloque sin cerrar: todo el texto); mutantes `-- note\r UPDATE ...` y `memory /*x*/ .api_keys k ON ... {a} {b}`; controles: ignorar `closed` y quitar `CreateStmt` hacen fallar `test_the_word_raise...` y `test_ddl...` (comprobado a mano con copias mutadas). (3) Límites declarados sin código: comentarios de bloque anidados, `a$x$` como cita con dólar, DDL de esquema completo (`GRANT ... ON ALL TABLES IN SCHEMA`, `ALTER SCHEMA`, `DROP OWNED`), `INHERITS (memory.actors)`, series de `+`/`-` cuadráticas en el lexer (acotadas por el tope), y el test de tiempo, que en la práctica es una cota de 0,5 s; docstring y nota DC-1 con las excepciones exactas de «siempre» y la cifra de `'/*' * 16000` como 1,7-1,8 s. (4) Corpus de 3286 literales frente a `ce7fde1` y `9e2243b`: 36 y 1 pérdidas. Frente a fix10 son las intencionadas de fix11 (`is_admin:row` de textos que nombran `actors` sin `*`, DDL de lectura a escritura, LOCK/ANALYZE/VACUUM, REFERENCES y LIKE, prosa con hueco, `INTO` de PL/pgSQL); frente a fix11 solo cambia `'100%% FROM %(t)s' % {'t': 'memory.api_keys'}`, un texto de Python (no SQL) cuyo nombre estaba dentro de unas llaves que ahora son hueco, y los casos `raise`, que pasan a rojo (no son pérdidas). RED (contra `9e2243b`, 9): 7 subpruebas de `test_the_word_raise...` (la del comentario sin cerrar ya pasaba con fix11), el cierre de esa prueba (`-- raise the limit` y `-- note\r` como escritura) y `test_the_report...` (la aserción cambiada). Verde: las 33 pruebas de las clases de guardas y la suite. usage-meter close access-control/T-02-fix12: 0.15 h IA (medido), 28 in / 16933 out tok.

### T-03 — Lectores de permisos al resolvedor: `_describe`, `_visible_projects`, `_admin_somewhere` y `/metrics`

- **Descripción**: Mover al resolvedor de `store_auth.py` las cuatro lecturas que deciden fuera de él: `Auth._actor` delega en `_describe`, `list_projects` en `_visible_projects`, `list_keys` en `_admin_somewhere`, y `/metrics` en modo `admin` llama a `_global_admin` dentro de una transacción. Refactor sin cambio de comportamiento. Fuente: CA-38 (a); DC-1.
- **Changelog**: Interno: los permisos de una credencial, los proyectos visibles, el derecho a listar claves y el acceso a las métricas se deciden en un único punto del servidor, sin cambiar ninguna respuesta.
- **Estado**: completado
- **Cerrada**: 2026-11-20
- **Tiempo humano**: est. 3.5h · real —
- **Tiempo IA (ejec.)**: est. 0.36h · real 0.23h (medido)
- **Supervisión**: est. 0.09h · real —
- **Previsión IA**: 99 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-02
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_auth.py`, `server/memory_platform/auth.py`, `server/memory_platform/app.py`, `server/memory_platform/tests/test_auth_cache.py`, `server/memory_platform/tests/test_auth.py`, `server/memory_platform/tests/test_metrics.py`, `server/memory_platform/tests/store_surface.json`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|test_auth|test_metrics|test_api_limits|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] El test de T-02 pasa a verde sin ampliar la lista de excepciones
- [x] `/metrics` en modo `admin` deja de fiarse del `is_admin` del diccionario del actor y responde igual que antes
- [x] Las respuestas de `/v1/auth/me`, `/v1/projects` y `/v1/keys` no cambian; `store_surface.json` solo crece

**Subtareas**
- [x] Extraer las tres funciones
- [x] Cambiar `/metrics`
- [x] Suite

**Notas**: `store_auth.py` gana `_describe` (sale de `Auth._actor`, que ahora delega), `_visible_projects(c, actor)` (devuelve las filas antes del tope de 100) y `_admin_somewhere(c, actor)` (lanza Forbidden o devuelve `(key, every_key)`; `list_keys` ya no lee `is_admin` ni `project_grants`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `cae4fce4a166`.

### T-04 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor.
- **Changelog**: Interno: la CI exige ahora al menos 1601 pruebas del servidor.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real 0.05h (medido)
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-03
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [x] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [x] Suites, mínimo y archivo de las notas de la fase

**Notas**: fix12: `kairos-test:i4p1-fix12` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1601}`; mínimo 1601 en los cuatro sitios. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ae9f623810a4`.

### T-05 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 0,5 × la implementación. Superficie: el recorrido no debe poder esquivarse con alias de tabla, SQL compuesto o accesos indirectos a `is_admin`, y el refactor no cambia ninguna respuesta.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-04
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [x] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [x] Lentes A y B; corregir y repetir hasta cero abiertos

**Notas**: doce intentos con lentes A, B, C y D (tabla en `review.md`; detalle de los doce intentos en `execution-history.md`). Sin Critical ni Important abiertos tras el fix12. Desviación declarada del criterio «cada fix con su revisión completa»: el fix12 se verificó con una comprobación dirigida del orquestador en `kairos-test:i4p1-fix12` (los cinco casos `raise` en rojo, `memory.{t}` en rojo, prosa en verde, paquete `({}, [])`, `ResolverBoundaryTests` 27 OK) por decisión del usuario «Fix12 mínimo y cerrar» (2026-11-23). Límites de la guarda declarados en el docstring y en DC-1.

---

## Fase 2 — Esquema 13, scrypt y contraseñas (C-01)

**Estado**: completado · **Hito**: A · **Estimado**: 36.0h (30h base, de ellas 15h de revisión adversarial) · **Real**: 3.88h IA (medido; incluye 0.94h de fix1, 0.52h de fix2 medidas el 2026-11-26 en T-08 y T-11 y 0.76h de fix3 en T-10; las horas de fix2 del 2026-11-23 no constan; revisión T-12 del orquestador sin medir) · **Coste est.**: 1.800 € · **Tokens est.**: 924 k

### T-06 — Esquema 13: columnas e índices de los tres hitos, de una vez (CA-10)

- **Descripción**: Migración aditiva a la versión 13 con la lista cerrada de DC-6: en `api_keys`, `last_used_at`, `replaced_by`, `limits` (`jsonb`), `write_quota_day` y `write_quota_used`; en `web_sessions`, `created_at` y `client_ip`; índices `login_attempt_ip_time` y `web_session_actor`. Ningún hito posterior reabre la versión 13 ni crea la 14. Fuente: CA-10; DC-6; D-07; R-13.
- **Changelog**: El esquema pasa a la versión 13 con columnas e índices nuevos; actualizar desde 0.4.1 conserva usuarios, sesiones y claves.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real 0.26h (medido, incluye 0.09h de fix1)
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-05
- **Tipo**: db
- **Archivos**: `server/memory_platform/schema.sql`, `server/memory_platform/tests/test_migrations_additive.py`, `server/memory_platform/tests/schema_history.py`, `server/memory_platform/tests/test_queue_indexes.py` (añadido con nota: ajuste del recuento de índices a los de `jobs`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_migrations_additive|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Solo `ADD COLUMN` y `CREATE INDEX`, ninguna tabla nueva; `test_migrations_additive.py` pasa
- [x] Tras actualizar desde 0.4.1 con usuarios, sesiones y claves sembrados, todos siguen valiendo y las claves conservan «sin caducidad»
- [x] Lo creado coincide con DC-6 (prueba por catálogo, no por texto SQL)

**Subtareas**
- [x] Escribir la migración
- [x] Caso de actualización desde 0.4.1
- [x] Prueba por catálogo

**Notas**: RED: `AccessSchemaTests` (4 pruebas) falló con `AssertionError: 12 not greater than or equal to 13` y `None != (timestamp with time zone, YES, None)` · 2026-11-23. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `3f2cd66a81df`.

**Notas fix1** (revisión de la Fase 2, intento 1; medición única de fix1: 0.94h IA, medido, repartida por peso del cambio: T-06 0.09, T-07 0.10, T-08 0.19, T-09 0.42, T-10 0.14) · hueco 5 (commit 32bbec1): `test_the_upgrade_adds_exactly_what_dc6_lists_to_every_table_of_the_schema` (`test_migrations_additive.py:460`) compara el catálogo completo de `memory` antes y después de actualizar desde 0.4.1 con IGUALDAD: tablas, columnas (tipo, nulabilidad y valor por defecto), índices con su definición, restricciones con su definición, funciones, disparadores, extensiones y versiones; solo aparecen las siete columnas, los dos índices y la versión 13. RED (mutante en `schema.sql`, revertido con `git checkout`): una columna `audit_events.extra_column` y un índice `extra_index` en la 13 → `AssertionError: {('lo[468 chars]), ('memory_items', 'parent_hash'): … != {…}` (falla `columns`) · 2026-11-23. Decisión: `test_queue_indexes.py:82` sigue acotado a `jobs`: es la prueba de la versión 12 y lo que la 13 añade en otras tablas lo cierra la igualdad anterior. Verificación declarada, ejecutada en la suite completa con `kairos-test:i4p2-fix1` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1673}`: `test_migrations_additive` y `test_queue_indexes` en `ok`, 0 fallos y 0 omitidos.

### T-07 — `passwords.py`: scrypt con el coste medido, hash ficticio, techo y rehash (CA-09)

- **Descripción**: Sacar scrypt de `auth.py` a `server/memory_platform/passwords.py` con los parámetros que fijó T-01: `hash_password`, `verify_password` (rechaza parámetros guardados por encima del objetivo), hash ficticio con el coste objetivo y rehash transparente en el primer login correcto (`UPDATE … WHERE password_hash=<el leído>`; si falla, el login sigue). Fuente: CA-09; S-07; DC-5.
- **Changelog**: Las contraseñas se guardan con un scrypt más costoso; las antiguas se actualizan solas en el primer inicio de sesión correcto.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 2.5h · real —
- **Tiempo IA (ejec.)**: est. 0.26h · real 0.79h (medido, incluye 0.10h de fix1)
- **Supervisión**: est. 0.06h · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-01, T-06
- **Tipo**: backend
- **Archivos**: `server/memory_platform/passwords.py`, `server/memory_platform/auth.py`, `server/memory_platform/store_auth.py`, `server/memory_platform/tests/test_passwords.py`, `server/memory_platform/tests/test_auth.py`, `server/memory_platform/tests/__init__.py` (añadido con nota: la suite corre a n=2^14)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_passwords|test_auth|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Un hash nuevo usa los parámetros definitivos; uno antiguo verifica y queda sustituido tras el primer login correcto
- [x] Usuario inexistente o deshabilitado: una derivación de coste objetivo, igual que una contraseña incorrecta (contador de derivaciones, sin medir tiempos)
- [x] Parámetros guardados por encima del objetivo se rechazan sin derivar

**Subtareas**
- [x] Prueba en rojo
- [x] Mover scrypt y subir `maxmem`
- [x] Rehash en la transacción que abre la sesión

**Notas**: RED: `test_passwords` falló con `ImportError: cannot import name 'passwords' from 'memory_platform'` y, con el módulo y sin cablear `Auth.login`, `Lists differ: [] != [(1024, 8, 1), (131072, 8, 1)]` · 2026-11-23. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `0e2a218faee9`.

**Notas fix1** (revisión de la Fase 2, intento 1; medición única de fix1: 0.94h IA, medido, repartida por peso del cambio: T-06 0.09, T-07 0.10, T-08 0.19, T-09 0.42, T-10 0.14) · hueco 4 (commit de98682): `ProductionCostTests` (`test_passwords.py:104`): un subproceso que no importa el paquete de pruebas ve `TARGET == DEFAULT_PARAMS == (2**17, 8, 1)` y el AST de `passwords.py` asigna `TARGET = DEFAULT_PARAMS`, sin ningún otro módulo que reasigne `TARGET`. RED (mutante `TARGET = (2 ** 14, 8, 1)` en `passwords.py`, revertido): `AssertionError: Lists differ: [[16384, 8, 1], [131072, 8, 1]] != [[131072, 8, 1], [131072, 8, 1]]` y `AssertionError: '(2 ** 14, 8, 1)' != 'DEFAULT_PARAMS'` · 2026-11-23. Con fix1 `test_a_password_changed_while_the_login_derived_is_not_overwritten` espera ahora 401 y ninguna sesión (hueco 3). Verificación declarada en la suite completa con `kairos-test:i4p2-fix1` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1673}`: `test_passwords` y `test_auth` en `ok`, 0 fallos y 0 omitidos.

### T-08 — Tope de logins simultáneos: semáforo que una sola IP no puede llenar (CA-09)

- **Descripción**: Semáforo en memoria con `MEMORY_LOGIN_CONCURRENCY` huecos (valor de T-01) para toda derivación scrypt de la API: login, cambio de contraseña y alta de usuario. Una IP ocupa como mucho un hueco, en uso o en espera; espera acotada (tantas peticiones como huecos, 2 s); lleno responde 503 `login_busy` con `Retry-After` y no cuenta como fallo. `MemoryError` gana `retry_after` y `error()` añade la cabecera. Fuente: CA-09; DC-2; DC-5; R-02; invariante 3.
- **Changelog**: El inicio de sesión acota las verificaciones simultáneas; saturado responde 503 `login_busy` con `Retry-After`.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 2.5h · real —
- **Tiempo IA (ejec.)**: est. 0.26h · real 0.84h (medido, incluye 0.19h de fix1 y 0.06h de fix2)
- **Supervisión**: est. 0.06h · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-07
- **Tipo**: backend
- **Archivos**: `server/memory_platform/passwords.py`, `server/memory_platform/auth.py`, `server/memory_platform/app.py`, `server/memory_platform/config.py`, `server/memory_platform/errors.py`, `server/memory_platform/tests/test_passwords.py`, `docker-compose.yml`, `docs/configuration.md` (añadido con nota: fila de `MEMORY_LOGIN_CONCURRENCY`), `docs/roadmap/2026-11-19-access-control/design.md` (añadido con nota: orden de las tres rutas que derivan y límite de tiempo declarado en DC-5, revisión fase 2, intento 1, commit 6fe2ef5)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_passwords|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Con N logins simultáneos (N = huecos + 5) nunca hay más derivaciones a la vez que huecos (barrera y reloj inyectados, sin `sleep`) y el resto recibe 503 `login_busy`
- [x] Una misma IP no ocupa dos huecos; `login_busy` no suma al contador de fallos de la IP
- [x] El Compose define `MEMORY_LOGIN_CONCURRENCY` y, si T-01 lo pidió, el nuevo `MEMORY_BOOTSTRAP_MEM_LIMIT`

**Subtareas**
- [x] Prueba en rojo
- [x] Semáforo y espera acotada
- [x] 503 con `Retry-After`

**Notas**: RED: `GateTests` (8 pruebas) falló con `AttributeError: module 'memory_platform.passwords' has no attribute 'LoginGate'` · 2026-11-23. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `24f3010882f3`.

**Notas fix1** (revisión de la Fase 2, intento 1; medición única de fix1: 0.94h IA, medido, repartida por peso del cambio: T-06 0.09, T-07 0.10, T-08 0.19, T-09 0.42, T-10 0.14) · hueco 2 y mitad del hueco 8 (commits 43d3c20 y 827f643): `create_user` autoriza y rechaza el nombre repetido en una transacción de solo lectura, ANTES de derivar y de tomar el hueco; deriva fuera de toda transacción (`slot=`, la ruta da `passwords.GATE.hold(ip)`); inserta en otra que vuelve a autorizar y a comprobar el nombre, y un `UniqueViolation` es 409 (`store_auth.py:199-225`, `app.py:393`). `CreateUserOrderTests` (`test_access_password.py:277`, 5 pruebas): 403 y 409 con `spy.calls == []` y con la compuerta llena (no 503), sin transacción abierta durante la derivación, clave revocada durante la derivación = 401 sin usuario, nombre tomado durante la derivación = 409. RED: `Tuples differ: (503, 'login_busy', []) != (403, 'forbidden', [])` y `(503, 'login_busy', []) != (409, 'conflict', [])` · 2026-11-23. Mutantes (revertidos): derivar antes de autorizar → 3 rojas; sin segunda autorización → `test_a_key_revoked_while_the_password_was_derived_creates_nothing` roja. Verificación declarada en la suite completa con `kairos-test:i4p2-fix1` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1673}`: `test_passwords` (`GateTests`, `BusyLoginTests`) y `test_access_password` en `ok`, 0 fallos y 0 omitidos.

**Notas fix2** (revisión de la Fase 2, intento 2; 0.06h IA medidas en dos ventanas de `access-control/T-08`, 0.02 + 0.04) · hueco 4 (commit 098bdc0): `test_a_username_taken_between_the_last_check_and_the_insert_is_409_by_the_unique_violation` (`CreateUserOrderTests`, `test_access_password.py:355`) parchea `store_auth.new_id`, la llamada entre la segunda comprobación y el `INSERT`, para insertar el usuario rival en una conexión aparte; solo el `except UniqueViolation` de `create_user` puede convertirlo en 409. Comprueba 409 `conflict`, un único usuario (el rival) y ningún `user.created` nuevo. RED: la rama ya existía, así que el rojo es el del mutante «quitar el `except`» (copia de `server/memory_platform` fuera del repositorio, montada en `kairos-test:i4p2-fix1` sin red): `AssertionError: Tuples differ: (503, 'service_unavailable') != (409, 'conflict')` · 2026-11-26; con el código real, `CreateUserOrderTests` 6 pruebas OK. La primera ejecución dio además `AssertionError: 1 != 0` por un fallo de la propia prueba (el fixture ya audita un `user.created`); se corrigió comparando el recuento antes y después. Verificación declarada en la suite completa con `kairos-test:i4p2-fix2` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1686}`: `test_passwords` y `test_access_password` en `ok` (la prueba nueva, `409 Conflict` y `ok`), 0 fallos y 0 omitidos.

### T-09 — `store_access.py`: una puerta para los cambios de acceso y cambio de contraseña (CA-01)

- **Descripción**: Crear el mixin `server/memory_platform/store_access.py`, que `Store` hereda, con `_access_changed` (audita y vacía la caché de permisos) como final obligado de todo escritor nuevo. Primer escritor: `POST /v1/auth/password` (solo sesión y CSRF), que cambia la contraseña, revoca las demás sesiones del usuario y conserva la actual y las claves. Fuente: CA-01; S-03; design.md §O2; invariante 2; R-01.
- **Changelog**: Nuevo `POST /v1/auth/password`: cambia la contraseña y cierra las demás sesiones del usuario.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0.51h · real 0.47h (medido, incluye 0.42h de fix1)
- **Supervisión**: est. 0.13h · real —
- **Previsión IA**: 142 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-08
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_access.py`, `server/memory_platform/store.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/auth.py`, `server/memory_platform/tests/test_access_password.py`, `server/memory_platform/tests/test_auth_cache.py`, `server/memory_platform/tests/store_surface.json`, `docs/contracts/memory-platform.openapi.json`, `docs/roadmap/2026-11-19-access-control/design.md` (añadido con nota: recuento acotado por la clave primaria y su límite en DC-5, revisión fase 2, intento 2, hueco 2, commit 66c948e)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_password|test_auth_cache|test_store_surface|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Con la actual correcta: la antigua ya no inicia sesión, la nueva sí, la otra sesión recibe 401 en su petición siguiente y hay evento `password.changed`
- [x] Con la actual incorrecta no cambia nada y cuenta como fallo de login de esa IP; nueva de menos de 12 caracteres → 422 `invalid_password`
- [x] El escritor termina en `_access_changed` y lo ve el recorrido de `test_auth_cache.py:359`; con una clave, la ruta responde 403

**Subtareas**
- [x] Prueba en rojo (oráculo de A-01)
- [x] Mixin y `_access_changed`
- [x] Ruta, modelo y OpenAPI

**Notas**: RED: `test_access_password` falló con `AssertionError: 404 != 200` (la ruta no existía) y `AttributeError: ... no attribute '_access_changed'` · 2026-11-23. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `b5cb25d822eb`.

**Notas fix1** (revisión de la Fase 2, intento 1; medición única de fix1: 0.94h IA, medido, repartida por peso del cambio: T-06 0.09, T-07 0.10, T-08 0.19, T-09 0.42, T-10 0.14) · huecos 1, 3, 6 y 8 (commits 43d3c20 y 827f643). Hueco 1: `POST /v1/auth/password` admite como mucho 5 cambios correctos por usuario en 15 minutos (429 `too_many_attempts`, contados en `audit_events` `password.changed`, sin tabla nueva: la 13 no se reabre), decidido antes del hueco y recontado en la última transacción bajo `FOR NO KEY UPDATE` de la fila (`store_access.py:21-29, :53, :69-70`). RED: `Tuples differ: (503, 'login_busy', []) != (429, 'too_many_attempts', [])` y `200 != 429` · 2026-11-23. Hueco 3: `Auth.login` abre la sesión bajo `FOR SHARE` (`FOR NO KEY UPDATE` si sustituye un hash antiguo) sobre la fila del actor y exige el mismo hash y usuario habilitado, si no 401 sin sesión (`auth.py:77-82`); `LoginRaceTests` (`test_access_password.py:353`) con gancho en `passwords._derive` (`set_password` y `change_password`, con y sin rehash), usuario deshabilitado y transacción del escritor sin confirmar vista esperando en `pg_stat_activity`, sin `sleep`. RED: `AssertionError: Unauthorized not raised` (7 subpruebas) y `False is not true : the login did not wait for the transaction of the writer` (3). Hueco 6: la verificación del cambio usa `verify_password` (coste de SU hash), así que con hash antiguo hace `[OLD, TARGET]` y no `[OLD, TARGET, TARGET]` (RED `Lists differ: [(1024, 8, 1), (16384, 8, 1), (16384, 8, 1)] != [(1024, 8, 1), (16384, 8, 1)]`); la diferencia de tiempo con un usuario inexistente queda como límite transitorio declarado en `design.md` DC-5 (desaparece cuando cada cuenta entra una vez; `spec.md` no cambia). Hueco 8: 429 antes del hueco (`(503, 'login_busy', []) != (429, 'rate_limited', [])`), fallo de la contraseña actual con los mismos bloqueos consultivos de `Auth.login` (`auth.py:16-20`, `Lists differ: [] != [('login-ip:testclient',), ('login-user:ana',)]`) y recuento bajo el bloqueo (`(403, 'invalid_current_password') != (429, 'rate_limited')`). Mutantes (todos revertidos, cada uno en rojo con su prueba): sin cuenta antes del hueco, sin recuento final, sin bloqueo de la fila (`test_the_last_transaction_waits_for_a_change_that_has_not_committed_and_then_recounts`), sin bloqueos consultivos, sin recuento del fallo, hash no comparado en el login, usuario no comprobado, sin `FOR SHARE`, hueco alrededor de toda la llamada de la ruta, `check_login` en lugar de `verify_password`. Verificación declarada en la suite completa con `kairos-test:i4p2-fix1` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1673}`: `test_access_password`, `test_auth_cache` (la guarda) y `test_store_surface` en `ok`, 0 fallos y 0 omitidos. Guarda de T-02: sin cambios (el `UPDATE api_keys` de `set_password` y el `SELECT *` del login ya estaban cubiertos; el `SELECT *` con `FOR SHARE` va en línea dentro de `Auth.login`, que ya figura en `READ_EXCEPTIONS`).

**Notas fix2** (revisión de la Fase 2, intento 2; los RED y mutantes de fix2 se registraron el 2026-11-23 en la sesión que hizo los commits y aquí se vuelcan desde su registro; los mensajes de commit no traen las cifras de RED ni de mutantes, y la medición de horas de esa sesión no consta) · hueco 2 (commit 66c948e): el recuento de `password.changed` se acota por la clave primaria sin índice nuevo (`LAST_OLD_EVENT` recorre `id` hacia atrás hasta la primera fila anterior a la ventana y `RECENT_CHANGES` cuenta solo los `id` por encima), con la misma función en los dos recuentos del cambio; límite declarado en `design.md` DC-5. `RecentChangesCostTests` (`test_access_password.py:583`) ejecuta las sentencias reales con `EXPLAIN (ANALYZE, BUFFERS)`. RED: `'Seq Scan' unexpectedly found…` · 2026-11-23. EXPLAIN con 1 M de filas antiguas: recorrido completo 8 169 buffers y 169 ms → acotado 4 + 4 buffers y unos 0,04 ms (0,04 + 0,05 ms según DC-5). Mutantes (revertidos): suelo 0 en lugar del `id` antiguo → rojo; `ORDER BY id ASC` → rojo (el registro no conserva el recuento de fallos de estos dos); quitar el filtro `happened_at` del recuento → declarado equivalente (el suelo por `id` ya excluye las filas antiguas salvo en el margen de microsegundos del límite declarado), sin prueba que lo distinga. Hueco 3 (commit 6729b95): un login que encuentra el hash rehecho por otro login concurrente verifica una vez contra el hash nuevo, dentro del mismo hueco, y reintenta una sola vez; si no verifica o el hash vuelve a cambiar, 401 sin sesión (`auth.py`, bucle `for retried in (False, True)`). `LoginRetryTests` (`test_access_password.py:482`). RED: `{2: 'dict', 1: 'Unauthorized'}` (dos logins simultáneos con hash antiguo: el segundo recibía 401) · 2026-11-23. Mutantes (revertidos): siempre `FOR SHARE` → rojo; sin verificar en el reintento → 8 fallos; más de un reintento → rojo (el registro no conserva el recuento de fallos de estos dos). La línea de DC-5 sobre este reintento quedó PENDIENTE: el guardarraíl del rol implementer bloquea `design.md` (2026-11-26); texto propuesto en el informe al orquestador. Verificación declarada en la suite completa con `kairos-test:i4p2-fix2` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1686}`: `test_access_password`, `test_auth_cache` y `test_store_surface` en `ok`, 0 fallos y 0 omitidos.

### T-10 — `admin set-password --username --password-file` (CA-02)

- **Descripción**: Subcomando de recuperación del administrador sobre el mismo escritor de T-09, sin SQL propio en `admin.py` (DC-10): cambia la contraseña y revoca todas las sesiones del usuario. Fuente: CA-02; DC-10.
- **Changelog**: Nuevo `admin set-password`: el operador recupera una cuenta y cierra todas sus sesiones. `admin bootstrap`, `admin set-password` y los scripts de despliegue, aceptación y ensayo leen el fichero de contraseña igual: solo quitan un salto de línea final (ya no recortan espacios) y un fichero que no es UTF-8 o que empieza por BOM da `password_file_invalid`.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 1.5h · real —
- **Tiempo IA (ejec.)**: est. 0.15h · real 0.95h (medido, incluye 0.14h de fix1 y 0.76h de fix3)
- **Supervisión**: est. 0.04h · real —
- **Previsión IA**: 43 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-09
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/store_access.py`, `server/memory_platform/tests/test_admin.py`, `server/memory_platform/tests/test_auth_cache.py` (añadido con nota: `NOT_REQUEST_PATHS`), `server/memory_platform/tests/store_surface.json` (añadido con nota: método nuevo del store), `server/memory_platform/store_auth.py` (añadido con nota: bloqueo de `create_key`, revisión fase 2 intento 2, hueco 1), `docs/operations.md` (añadido con nota: lectura del fichero de secreto de `bootstrap`, hueco 5), `scripts/deploy-memory.py`, `scripts/accept-native-clients.py`, `scripts/rehearse-reliable-operations.py`, `scripts/tests/test_bootstrap_password_file.py`, `scripts/tests/test_rehearse_reliable_operations.py` (añadidos con nota: lectores de `secrets/bootstrap_password` con la regla de `password_from_file`, revisión fase 2 intento 3, gaps 1 y 2, fix3)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_admin|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Cambia la contraseña, revoca todas las sesiones y queda auditado
- [x] La salida y los logs no contienen la contraseña ni su hash (prueba sobre stdout, stderr y eventos)
- [x] `admin.py` no ejecuta SQL propio para ello

**Subtareas**
- [x] Prueba en rojo
- [x] Subcomando sobre el escritor del store

**Notas**: Cada fix en `admin.py` suma un intento de revisión completo (R-08). RED: `SetPasswordTests` falló con `AssertionError: 2 != 0 : usage: ... invalid choice` (el subcomando no existía) · 2026-11-23. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `46cffafad447`.

**Notas fix1** (revisión de la Fase 2, intento 1; medición única de fix1: 0.94h IA, medido, repartida por peso del cambio: T-06 0.09, T-07 0.10, T-08 0.19, T-09 0.42, T-10 0.14) · huecos 7 y 8 (commit 685975f): `admin set-password --revoke-keys` (por defecto conserva las claves) revoca todas las claves del usuario en la misma transacción por `store_access.py` (`set_password(..., revoke_keys=False)`, `store_access.py:77-92`, `admin.py:354-357, :518`); el escritor termina en `_access_changed` (`password.reset`, más `keys.revoked` si revocó) y la salida dice `keys_revoked`. `password_from_file` (`admin.py:336`) quita un único salto de línea final (LF o CRLF) y nada más, en lugar de `.strip()`; documentado en la ayuda y en `docs/operations.md` («Claves y acceso»). RED (contra la producción de 01e5e12 con las pruebas nuevas): `KeyError: 'keys_revoked'`, `KeyError: 'revoke_keys'`, `AssertionError: 2 != 0 : usage: …` y `AssertionError: False is not true` (3 subpruebas del fichero) · 2026-11-23. Mutantes (revertidos): `--revoke-keys` sin efecto → `test_the_keys_of_the_user_stay_unless_revoke_keys_is_given_and_then_only_that_users` roja; `.strip()` de vuelta → 3 subpruebas rojas. Sin secretos en la salida ni en los registros (`test_revoke_keys_prints_and_logs_no_secret`). Verificación declarada en la suite completa con `kairos-test:i4p2-fix1` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1673}`: `test_admin` (`SetPasswordTests`) en `ok`, 0 fallos y 0 omitidos.

**Notas fix2** (revisión de la Fase 2, intento 2; los RED y mutantes de fix2 se registraron el 2026-11-23 en la sesión que hizo los commits y aquí se vuelcan desde su registro; los mensajes de commit no traen esas cifras ni qué cambia cada mutante, y la medición de horas de esa sesión no consta) · hueco 1 (commit 328a446): `create_key` bloquea con `FOR SHARE` la fila del actor propietario y, con la caché vacía, vuelve a comprobar la credencial; si `set-password --revoke-keys` confirma antes, la creación espera y da 401; si la creación confirma antes, el `UPDATE api_keys` espera y la revoca. `RevokeKeysRaceTests` (`test_admin.py:539`, 2 pruebas). RED: `AssertionError: False is not true : the creation did not wait for the transaction of set-password (no lock on the row of the owner)` y `AssertionError: False is not true : set-password did not wait for the creation in progress` · 2026-11-23. Mutantes (revertidos): M1 → 4 fallos; M2 → 2 fallos (el registro no conserva qué línea retira cada uno). Hueco 5 (commit c29b6a3): `bootstrap` y `set-password` leen el fichero de secreto con la única función `password_from_file` (quita un salto de línea final, LF o CRLF, y nada más); un fichero que no es UTF-8 es `password_file_invalid` sin bytes del contenido; documentado en `docs/operations.md`. Pruebas en `test_admin.py:73, :87, :100`. RED: 5 fallos y 2 errores · 2026-11-23 (sin mutantes registrados). Verificación declarada en la suite completa con `kairos-test:i4p2-fix2` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1686}`: `test_admin` en `ok`, 0 fallos y 0 omitidos.

**Notas fix3** (revisión de la Fase 2, intento 3, gaps 1 y 2; fuera del bucle por decisión del usuario «Fix3 pequeño y cerrar», 2026-11-26; medición propia de fix3: 0.76h IA, medido, ventana `access-control/T-10` 10:44-11:40 UTC, incluye la subida del mínimo de T-11) · gap 2 (commit 56737bf): `password_from_file` (`admin.py:336-353`) rechaza un fichero que empieza por la marca de orden de bytes de UTF-8 (`EF BB BF`) con `password_file_invalid: the file starts with a byte order mark; save it as UTF-8 without BOM`, sin bytes del secreto; un `U+FEFF` en otra posición sigue siendo parte de la contraseña. Decisión: error tipado y no quitar el BOM. Es la opción conservadora: no adivina si la marca es parte del secreto, el operador ve en el acto qué pasa y cómo arreglarlo, y no cambia en silencio la contraseña de nadie (una cuenta creada antes de 0.4.2 con un fichero con BOM tiene el `U+FEFF` dentro y sigue entrando si se escribe igual; quitarlo en `bootstrap` daría otra contraseña sin aviso). No cambia la spec ni `design.md` (amplía el error tipado que ya existía para un fichero no UTF-8), así que no es DECISIÓN ABIERTA. Prueba `test_a_secret_file_with_a_utf8_byte_order_mark_fails_without_a_byte_of_it` (`test_admin.py:100`, los dos comandos y el `U+FEFF` interior). RED: `AssertionError: '0' != 'password_file_invalid: the file starts with a byte order mark; save it as UTF-8 without BOM'` (bootstrap) y `TypeError: Mock.keys() returned a non-iterable` (set-password siguió hasta el store) · 2026-11-26. Mutantes (sobre copias, revertidos; `kairos-test:i4p2-fix2`, sin red): sin el control del BOM → 1 fallo y 1 error; BOM rechazado en cualquier posición → 1 fallo (el `U+FEFF` interior). Gap 1 (commit b068912): `deploy-memory.py` (ida y vuelta y `verify_runtime`), `accept-native-clients.py` y `rehearse-reliable-operations.py` ya no hacen `.read_text().strip()`: cada uno tiene una función mínima `bootstrap_password` que repite la regla de `password_from_file` (un salto final, nada más; no UTF-8 o BOM → `password_file_invalid` con el error de su script, `DeploymentError`, `AcceptanceError` o `RehearsalError`, sin encadenar el error de decodificación); el comentario apunta a `password_from_file`. No hay helper común a los tres (solo el ensayo carga `deploy-memory.py`, y de forma diferida), así que se duplica. Prueba nueva `scripts/tests/test_bootstrap_password_file.py` (4 pruebas, en el host): los mismos 11 casos válidos y 2 inválidos contra las tres copias y contra `password_from_file` compilada desde el fuente de `admin.py` (una copia que se aparta del servidor queda roja), el tipo de error de cada script y una guarda de fuente: ningún `scripts/*.py` lee `'bootstrap_password')` con `.read_text`/`.read_bytes` a mano y cada script llama a `bootstrap_password` el número de veces esperado. `test_rehearse_reliable_operations.py` parchea ahora `Path.read_bytes` en lugar de `Path.read_text` (2 líneas; el lector lee bytes). RED: `AttributeError: module 'kairos_bootstrap_password_deploy_memory_py' has no attribute 'bootstrap_password'` (setUpClass) · 2026-11-26; con las funciones y una llamada vuelta a `.strip()`, la guarda queda roja. Mutantes (sobre copias, revertidos): llamada de `run_roundtrip` vuelta a `.strip()` → `test_no_script_reads_the_bootstrap_password_file_by_hand` roja; ídem en `verify_runtime`, en `accept-native-clients.py` y en el ensayo → roja; sin el control del BOM en `accept-native-clients.py` → 2 fallos; error de decodificación encadenado en `deploy-memory.py` → 1 fallo; `password_from_file` del servidor que quita también un `\r` suelto → 1 fallo; el ensayo que quita además un blanco final → primero SOBREVIVIÓ (ningún caso acababa en blanco sin salto); añadidos los casos `b' no-break-but-spaces '` y `b'no-break-but-a-tab\t'` → 2 fallos. Lectores del fichero buscados (`git grep bootstrap_password`, más el árbol completo): los cuatro de arriba cambiados; `scripts/memory-admin.py` lo escribe (`write_once`, su `.strip()` solo comprueba que no esté vacío y el valor devuelto se descarta) y `scripts/diagnose-deployment.py` lo lee para tachar el secreto del diagnóstico (con `.strip()` el valor tachado es subcadena de la contraseña, así que sigue tachando): sin cambio; `web/` no lo lee (solo prosa en `web/dist`). Fuera del repositorio versionado queda `.private/verify-lifecycle-readonly.py` (ignorado por git) con `.strip()`: no se toca, se informa. Documentado en `docs/operations.md` («Claves y acceso»: el BOM, cómo guardar sin BOM en PowerShell 5.1 y 7, y que los scripts usan la misma regla). Verificación: `python -m unittest discover -s scripts/tests` → `Ran 196 tests … OK`; suite completa `kairos-test:i4p2-fix3` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1687}`; `test_admin` en `ok`, 0 fallos y 0 omitidos.

### T-11 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, contratos.
- **Changelog**: El esquema pasa a la versión 13; las contraseñas usan un scrypt más costoso con tope de verificaciones simultáneas; nuevos `POST /v1/auth/password` y `admin set-password`.
- **Estado**: completado
- **Cerrada**: 2026-11-23
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real 0.57h (medido, incluye 0.46h de fix2, con la espera de la suite)
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-10
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [x] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [x] Suites, mínimo y archivo de las notas de la fase

**Notas**: TDD n/a: cierre de fase, sin código. `kairos-test:i4p2` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1649}`; mínimo 1601 → 1649 en los cuatro sitios; `scripts/tests/test_ci_workflow.py` OK (48). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `8d17c3d44694`.

**Historia del mínimo** (revisión de la Fase 2, intento 2, hueco 8): 1601 → 1649 en el cierre de la fase (`kairos-test:i4p2`, arriba) → 1673 en fix1 (commit 04a329b: `kairos-test:i4p2-fix1` exit 0, `MEMORY_TEST_RESULT` 1673 pruebas, 0 fallos, 0 errores y 0 omitidos; el resultado de `test_ci_workflow.py` de esa subida no consta en el commit ni en el ledger) → 1686 en fix2 (commit c5ea395: `kairos-test:i4p2-fix2` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1686}`; las 13 pruebas nuevas son las 12 de fix2 de T-09 y T-10 más la del hueco 4 de T-08; `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `Ran 48 tests … OK`), en los cuatro sitios: `KAIROS_MIN_TESTS` de `ci.yml` (con su historia), `MIN_FLOOR`, `docs/operations.md` y `README.md:252`. → 1687 en fix3 (commit d38f243: `kairos-test:i4p2-fix3` (exit 0): `MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1687}`; la prueba nueva es la del BOM de `test_admin` (gap 2 del intento 3); las 4 de `scripts/tests/test_bootstrap_password_file.py` corren en el host y no cuentan en este mínimo; `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `Ran 48 tests … OK`; horas dentro de la medición de fix3 de T-10), en los cuatro sitios. `test_contract_additive` corrió dentro de la suite (no aparte en el host). TDD n/a: subida del mínimo, sin código.

### T-12 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: scrypt y el semáforo (agotamiento de memoria, bloqueo entre clientes, coste constante), la caché de permisos tras el cambio de contraseña y la migración 13.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: completado
- **Cerrada**: 2026-11-26
- **Tiempo humano**: est. 15h · real —
- **Tiempo IA (ejec.)**: est. 1.54h · real —
- **Supervisión**: est. 0.39h · real —
- **Previsión IA**: 425 k in / 37 k out tok · ⚠️ verificar €
- **Dependencias**: T-11
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [x] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [x] Lentes A y B; corregir y repetir hasta cero abiertos

**Notas**: tres intentos con lentes A, B, C y D (Opus 5.5 en el intento 3; tabla en `review.md`; detalle de los tres intentos en `execution-history.md`). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `7c9b53763a88`.

---

## Fase 3 — Usuarios, permisos y sesiones (C-01)

**Estado**: completado · **Hito**: A · **Estimado**: 36.0h (30h base, de ellas 15h de revisión adversarial) · **Real**: 5.14h IA (medido; incluye 0.91h del fix1 en T-13..T-17; revisión T-18 del orquestador sin medir) · **Coste est.**: 1.800 € · **Tokens est.**: 924 k

### T-13 — Deshabilitar y rehabilitar usuario: `PATCH /v1/users/{id}`, `admin disable-user` y `enable-user` (CA-03)

- **Descripción**: Escritor en `store_access.py`, ruta del administrador global y dos subcomandos `admin` sobre el mismo escritor (DC-10). Deshabilitar revoca las sesiones del usuario y deja sin valor sus claves mientras dure; rehabilitar devuelve las claves no revocadas, no las sesiones. Deshabilitarse a uno mismo o al último administrador activo responde 409; el actor de `admin` no choca con «nunca a uno mismo». No se borran usuarios. Fuente: CA-03; S-03; DC-10.
- **Changelog**: Nuevos `PATCH /v1/users/{id}`, `admin disable-user` y `admin enable-user`: al deshabilitar un usuario, sus sesiones y claves dejan de valer al instante.
- **Estado**: completado
- **Cerrada**: 2026-11-26
- **Tiempo humano**: est. 5.5h · real —
- **Tiempo IA (ejec.)**: est. 0.56h · real 4.01h (medido; incluye montar el arnés de pruebas dirigidas y de mutantes que reutilizan T-14 a T-16; fix1 de la fase 3: 0.44h)
- **Supervisión**: est. 0.14h · real —
- **Previsión IA**: 156 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-12
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_access.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/admin.py`, `server/memory_platform/tests/test_access_users.py`, `server/memory_platform/tests/test_admin.py`, `server/memory_platform/tests/test_auth_cache.py`, `server/memory_platform/tests/store_surface.json`, `docs/contracts/memory-platform.openapi.json`, `server/memory_platform/store_auth.py` (añadido con nota: fix1 de la fase 3, gap 1, bloqueo del delegante en `create_user`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_users|test_admin|test_auth_cache|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Con una sesión y dos claves: tras deshabilitar, las tres reciben 401 en su petición siguiente y el login responde como una contraseña incorrecta; al rehabilitar vuelven las claves no revocadas, no las sesiones
- [x] 409 al deshabilitarse a uno mismo o al último administrador activo, también con dos peticiones concurrentes y desde `admin` (código ≠ 0); eventos `user.disabled` y `user.enabled`
- [x] Los subcomandos tienen el mismo efecto y auditoría que la ruta, sin SQL propio en `admin.py`

**Subtareas**
- [x] Prueba en rojo
- [x] Escritor, ruta y subcomandos

**Notas**: Cada fix en `admin.py` suma un intento de revisión completo (R-08). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `81b71548536a`. fix1 de la fase 3 (gaps 1, 4, 5 y 11): `create_user` bloquea al delegante, `_set_disabled` bloquea al llamante, solo sesiones vivas, 403 antes de 422; 8 mutantes en rojo; 0.44 h IA (medido). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `3482376c4a7c`.

RED: `test_access_users + test_admin.DisableUserCommandTests (18 pruebas, 16 fallos y 5 errores)` falló con AssertionError: 404 != 200 : {"detail":"Not Found"} (la ruta no existía) y AttributeError: 'Store' object has no attribute 'operator_set_disabled' (RED original, devuelto al ledger desde execution-history.md: fix1 de la revisión de la fase 3, gap 8) · 2026-11-26.

RED: `fix1 fase 3: test_access_users.CreateUserRaceTests (4), CallerLockTests, ClosingSkipsTheExpiredSessionsTests (3) y DisableRouteTests.test_a_caller_that_is_not_the_global_administrator_gets_403_before_the_422_of_a_body_without_a_change` falló con AssertionError: False is not true : the creation did not wait for the row of its delegate (x2), the disabling/replacement did not wait for the creation in progress (x2), the disabling did not wait for the row of its caller; 2 != 1 (sessions_revoked con una caducada, x2); (False, True, True) != (False, False, True); 422 != 403 (x2) · 2026-11-26.

### T-14 — Sustituir permisos por proyecto: `PUT /v1/users/{id}/grants` (CA-04)

- **Descripción**: Escritor y ruta del administrador global que sustituyen los permisos por proyecto de un usuario. Sus claves quedan acotadas por esos permisos (`store_auth.py:76-82`). Fuente: CA-04; S-03.
- **Changelog**: Nuevo `PUT /v1/users/{id}/grants`: un administrador sustituye los permisos por proyecto de un usuario, con efecto en la petición siguiente.
- **Estado**: completado
- **Cerrada**: 2026-11-26
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real 1.05h (medido; fix1 de la fase 3: 0.09h)
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-13
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_access.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/tests/test_access_users.py`, `server/memory_platform/tests/test_auth_cache.py`, `docs/contracts/memory-platform.openapi.json`, `server/memory_platform/tests/store_surface.json` (añadido con nota: método nuevo `replace_grants` en la superficie de `Store`), `docs/operations.md` (añadido con nota: fix1 de la fase 3, formato de `grants.replaced`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_users|test_auth_cache|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] La petición siguiente de la sesión y de las claves del usuario sobre un proyecto retirado responde como un proyecto sin acceso (404 o 403, según el contrato actual)
- [x] Evento `grants.replaced` con los permisos anteriores y los nuevos
- [x] Proyectos o permisos inexistentes → 422, sin cambio parcial

**Subtareas**
- [x] Prueba en rojo
- [x] Escritor y ruta

**Notas**: RED: `test_access_users.GrantsTests (7 pruebas)` falló con AssertionError: 404 != 200 : {"detail":"Not Found"} (la ruta PUT /v1/users/{id}/grants no existía) y 404 != 422 en los cinco cuerpos inválidos · 2026-11-26. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `d126ae3b7b93`. fix1 de la fase 3 (gap 11 y formato de `grants.replaced` en `docs/operations.md`): 403 antes de 422; 1 mutante en rojo; 0.09 h IA (medido). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ab3af73eb5bd`.

RED: `fix1 fase 3: test_access_users.GrantsTests.test_a_caller_that_is_not_the_global_administrator_gets_403_before_the_422_of_a_project_named_twice` falló con AssertionError: 422 != 403 · 2026-11-26.

### T-15 — Sesiones: listar y cerrar las propias, cerrar las de otro usuario (CA-05)

- **Descripción**: La sesión guarda `client_ip` y `created_at`. Rutas para listar las sesiones propias (creación, caducidad, IP y cuál es la actual), cerrarlas todas menos la actual y, para el administrador global, listar (`GET /v1/users/{id}/sessions`, añadida en el fix1 por decisión del usuario, revisión de la fase 3, intento 1, gap 10) y cerrar todas las de un usuario. Fuente: CA-05, CA-42; DC-6.
- **Changelog**: Cada usuario ve y cierra sus sesiones; el administrador global lista y cierra las de otro usuario.
- **Estado**: completado
- **Cerrada**: 2026-11-26
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real 0.48h (medido; fix1 de la fase 3: 0.17h)
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-14
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_access.py`, `server/memory_platform/auth.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/tests/test_access_sessions.py`, `server/memory_platform/tests/test_auth_cache.py`, `docs/contracts/memory-platform.openapi.json`, `server/memory_platform/tests/store_surface.json` (añadido con nota: tres métodos nuevos en la superficie de `Store`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_sessions|test_auth_cache|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Cada sesión cerrada recibe 401 en su petición siguiente; la actual sigue valiendo
- [x] La lista no expone hashes ni tokens de sesión
- [x] Cerrar sesiones ajenas sin ser administrador global → 403; evento `sessions.revoked`

**Subtareas**
- [x] Prueba en rojo
- [x] Guardar `client_ip` al abrir sesión
- [x] Rutas y modelos

**Notas**: RED: `test_access_sessions (9 pruebas, contra el código de 407dac0)` falló con AssertionError: 404 != 200 : {"detail":"Not Found"} (rutas inexistentes), AttributeError: 'Store' object has no attribute 'list_own_sessions' y 0 != 1 (el login no guardaba client_ip) · 2026-11-26. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `16218c9a150b`. fix1 de la fase 3 (gaps 2, 6 y 10): `change_password` recomprueba la sesión bajo el bloqueo, `GET /v1/users/{id}/sessions`; 6 mutantes en rojo; 0.17 h IA (medido). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `57cd18c76dd0`.

RED: `fix1 fase 3: test_access_sessions (3 de cambio de contraseña desde una sesión cerrada, 2 de GET /v1/users/{id}/sessions, la de la clave con 403), test_store_surface y AccessRoutesTableTests.test_the_table_is_every_new_route_of_account_and_users` falló con AssertionError: {'changed': True} is not an instance of Unauthorized (x3); 404 != 200 y 404 != 403 (la ruta no existía); AttributeError: 'Store' object has no attribute 'list_user_sessions'; Lists differ (superficie); Items in the second set but not the first (tabla de rutas) · 2026-11-26.

### T-16 — Contrato y tabla de rutas de las acciones de acceso

- **Descripción**: Regenerar `memory-platform.openapi.json` con las rutas y modelos de T-09, T-13, T-14 y T-15, comprobar que el diff es aditivo y registrar cada ruta nueva en la tabla de rutas de `test_auth_cache.py:529` (401 con una credencial retirada). Fuente: CA-37; invariante 1; R-01.
- **Changelog**: El OpenAPI de `/v1` documenta las rutas nuevas de contraseña, usuarios, permisos y sesiones.
- **Estado**: completado
- **Cerrada**: 2026-11-26
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0.21h · real 0.24h (medido; fix1 de la fase 3: 0.07h)
- **Supervisión**: est. 0.05h · real —
- **Previsión IA**: 57 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-15
- **Tipo**: backend
- **Archivos**: `docs/contracts/memory-platform.openapi.json`, `scripts/export-contracts.py`, `server/memory_platform/tests/test_contract_additive.py`, `server/memory_platform/tests/test_auth_cache.py`, `server/memory_platform/app.py` (añadido con nota: `operationId` duplicado de `GET /v1/auth/sessions` corregido y una línea en blanco de más), `server/memory_platform/tests/test_access_users.py` y `server/memory_platform/tests/test_access_sessions.py` (añadidos con nota: solo líneas en blanco de más que dejaron las ediciones de la fase, commit 65a1919)
- **Cubre (tests)**: —
- **Verificación**:
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `python scripts/export-contracts.py && git diff --ignore-cr-at-eol --exit-code -- docs/contracts/kairos-mcp.json mcp/contract/kairos-mcp.json` → sin diferencias
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_auth_cache|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] `test_contract_additive.py` pasa para ambos contratos; `kairos-mcp.json` sin cambios
- [x] Cada ruta nueva responde 401 con una credencial revocada, caducada o de un usuario deshabilitado (tabla de rutas)
- [x] Toda acción con sesión que cambia estado exige origen permitido y token CSRF

**Subtareas**
- [x] Exportar contratos
- [x] Ampliar la tabla de rutas

**Notas**: RED: `test_auth_cache.AccessRoutesTableTests + test_contract_additive.test_t16_… (contra el código de cc44e76)` falló con AttributeError: 'Store' object has no attribute 'operator_set_disabled' y rutas ausentes del OpenAPI · 2026-11-26. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `ec14fd2dcb56`. fix1 de la fase 3 (gap 9): 401/403 en el OpenAPI de las rutas de sesiones; 1 mutante en rojo; 0.07 h IA (medido). Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `2e7f5ccc6455`.

Nota de RED (fix1 de la revisión de la fase 3, gap 8): ese RED se tomó contra `cc44e76` y no aísla el cambio propio de T-16. Su rojo propio era el `operationId` duplicado de `GET /v1/auth/sessions` que dejó T-15 (lo detecta la comprobación de `operationId` únicos de `test_t16_…`). No se rehace: el código ya está en la rama y la prueba lo cubre.

RED: `fix1 fase 3: test_contract_additive.test_t16_the_access_routes_are_in_the_openapi_and_their_bodies_only_have_optional_or_closed_fields (6 subpruebas 401/403)` falló con KeyError: '401' y KeyError: '403' en GET /v1/auth/sessions, POST /v1/auth/sessions/revoke-others y GET /v1/users/{id}/sessions · 2026-11-26.

### T-17 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: completado
- **Cerrada**: 2026-11-26
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real 0.27h (medido; la suite completa, 47 min de reloj, corre fuera de la medición de tokens; fix1 de la fase 3: 0.14h)
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-16
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`, `docs/roadmap/2026-11-09-retrieval-quality/spec.md` (añadido con nota: lo cambió el commit 6a0706f del orquestador, «Roadmap index: retrieval-quality marked implemented», hecho en esta rama durante la fase; ninguna tarea de la fase lo toca, se declara para que `scope-check --base main` lo cuente)
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [x] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [x] Suites, mínimo y archivo de las notas de la fase

**Notas**: Suite completa una vez, en primer plano, sobre `65a1919` (código de T-13 a T-16): `docker build -f server/memory_platform/Dockerfile --target test --progress=plain -t kairos-test:i4p3 .` → exit 0, `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0,… Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `bdee6a7e451f`.

RED: `fix1 fase 3: scripts.tests.test_ci_workflow.SuiteGateStepTests (2 pruebas, MIN_FLOOR ya en 1745 y ci.yml aún en 1728)` falló con AssertionError: Lists differ: ['KAIROS_MIN_TESTS 1728 is below the baseline 1745'] != [] · 2026-11-27.

fix1 (revisión de la fase 3, T-18 intento 1): suite completa una vez, en primer plano, sobre `4b80e6f` (código de los fix1 de T-13 a T-16): `docker build -f server/memory_platform/Dockerfile --target test --progress=plain -t kairos-test:i4p3-fix1 .` → exit 0, 1223 s, `MEMORY_TEST_RESULT {"database": "PostgreSQL", "database_version": "postgres (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)", "environment": "isolated-container-build", "errors": 0, "failures": 0, "llm_chat_calls": 0, "passed": true, "skipped": 0, "tests": 1745}` (+17: 10 en `test_access_users`, 7 en `test_access_sessions`). Mínimo 1728 → 1745 en los cuatro sitios, con su historia (`ci.yml`, `MIN_FLOOR`, `docs/operations.md`, `README.md:252`); `python -m unittest scripts.tests.test_ci_workflow` → Ran 48 tests, OK. Commit d6189ed. usage-meter `access-control/T-17`: 0.14 h IA (medido; la suite corre fuera de la medición de tokens).

### T-18 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: autorización de cada ruta nueva (403 con clave y con sesión no administradora, CSRF), carreras de «último administrador» y caché de permisos tras cada escritor.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 15h · real —
- **Tiempo IA (ejec.)**: est. 1.54h · real —
- **Supervisión**: est. 0.39h · real —
- **Previsión IA**: 425 k in / 37 k out tok · ⚠️ verificar €
- **Dependencias**: T-17
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [x] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [x] Lentes A y B; corregir y repetir hasta cero abiertos

**Notas**: dos intentos con lentes A, B, C y D en Opus 5.5 (tabla en `review.md`; detalle de los dos intentos en `execution-history.md`). Intento 1: 3 Important → fix1 (`b57b0df`..`3e6c4af`, suite 1745). Intento 2: sin Critical ni Important; 3 Minor: uno de ledger corregido por el orquestador, uno aceptado como límite del marco y uno diferido a T-22. Verificación: `scope-check.py --base main` exit 0 · `openapi-lint --diff` contra `cc44e76` 0 rompedores de 6 · `ledger-lint` 0 incoherencias.

---

## Fase 4 — Claves: caducidad, último uso, rotación y `kairos doctor` (C-01)

**Estado**: borrador · **Hito**: A · **Estimado**: 48.0h (40h base, de ellas 20h de revisión adversarial) · **Real**: — · **Coste est.**: 2.400 € · **Tokens est.**: 1232 k

### T-19 — Claves: caducidad opcional, `expires_at` visible y `last_used_at` (CA-06)

- **Descripción**: `KeyInput` admite `expires_at` opcional; sin él la clave no caduca (P-03). La lista de claves muestra `expires_at` y `last_used_at`, y `/v1/auth/me` añade, para una clave, `key: {id, name, prefix, expires_at}`. `last_used_at` se escribe desde el camino de autenticación como mucho una vez por minuto y clave, en transacción corta propia con `lock_timeout` corto; si no entra, se aplaza. En el hito B, T-56 integra esa escritura con la de la cuota. Fuente: CA-06; P-03; DC-7.
- **Changelog**: Una clave puede crearse con caducidad opcional; la lista de claves muestra su caducidad y su último uso, y `/v1/auth/me`, `expires_at`.
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 4.5h · real —
- **Tiempo IA (ejec.)**: est. 0.46h · real 0.71h (medido)
- **Supervisión**: est. 0.12h · real —
- **Previsión IA**: 128 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-18
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_auth.py`, `server/memory_platform/auth.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/tests/test_access_keys.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_keys|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [x] Sin caducidad la clave no caduca; con caducidad recibe 401 al vencer (fila fechada hacia atrás, sin `sleep`); una caducidad en el pasado al crear → 422
- [x] Las claves anteriores a la migración conservan «sin caducidad»; los campos nuevos son aditivos en el OpenAPI
- [x] Cien peticiones seguidas producen una sola escritura de `last_used_at` (reloj inyectado); un `FOR SHARE` sobre la fila no hace fallar la petición

**Subtareas**
- [x] Pruebas en rojo
- [x] Modelo, escritor, listados y escritura acotada

**Notas**: RED: `test_access_keys (10 pruebas, contra el código de e9646a5)` falló con KeyError: 'expires_at' y 'token' (la respuesta no traía la caducidad), KeyError: 'key' (`/v1/auth/me`), TypeError: Auth.__init__() got an unexpected keyword argument 'clock' y (422, 'invalid_request') != (422, 'invalid_key_expiry') · 2026-11-27. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6e6cb1c3af32`.

### T-20 — Rotación con gracia: `POST /v1/keys/{id}/rotate` (CA-07)

- **Descripción**: Escritor y ruta que emiten una clave nueva con el mismo nombre, proyectos y permisos, mostrada una sola vez. La antigua caduca al acabar la gracia (24 h por defecto; 0 = inmediata) y guarda `replaced_by`. Rotar una clave revocada, caducada o ya rotada y aún en gracia responde 409 y no emite clave. Fuente: CA-07; decisión 9.1.
- **Changelog**: Nuevo `POST /v1/keys/{id}/rotate`: emite una clave nueva y deja valer la antigua durante un periodo de gracia (24 h por defecto).
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 4.5h · real —
- **Tiempo IA (ejec.)**: est. 0.46h · real 0.89h (medido)
- **Supervisión**: est. 0.12h · real —
- **Previsión IA**: 128 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-19
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_access.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/tests/test_access_keys.py`, `server/memory_platform/tests/test_auth_cache.py`, `docs/contracts/memory-platform.openapi.json`, `server/memory_platform/tests/store_surface.json` (añadido con nota: el método nuevo `rotate_key` en la superficie de `Store`)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_keys|test_auth_cache|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] La antigua vale hasta el fin de la gracia y después recibe 401; con gracia 0, en la petición siguiente (filas fechadas hacia atrás)
- [x] 409 sin emitir clave al rotar una revocada, una caducada o una ya rotada en gracia, también con dos rotaciones concurrentes
- [x] La clave nueva solo aparece en la respuesta de la rotación; evento `key.rotated` sin el token

**Subtareas**
- [x] Prueba en rojo
- [x] Escritor con `replaced_by`
- [x] Ruta, modelo y OpenAPI

**Notas**: RED: `test_access_keys.RotationTests + test_auth_cache.AccessRoutesTableTests + RevocationTableTests (16 pruebas, contra el código de 00a8f82)` falló con AssertionError: 404 != 200 : {"detail":"Not Found"} (la ruta no existía), AttributeError: 'Store' object has no attribute 'rotate_key', KeyError: '/v1/keys/{key_id}/rotate' y la tabla de rutas sin la nueva · 2026-11-27. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `94da3960a503`.

### T-21 — `kairos doctor`: caducidad guardada, aviso a 14 días y «caducada» frente a «inválida» (CA-08)

- **Descripción**: `doctor --online` llama a `GET /v1/auth/me` con la clave y, con un 200, guarda `credential.json` en el directorio de estado del enlace (`key_id`, `prefix`, `expires_at`, `checked_at`; nunca la clave). El dato solo vale si su `prefix` coincide con el de la clave actual. Avisa a menos de 14 días del vencimiento; ante un 401 dice «clave caducada» si el dato vale y ya venció, y «clave inválida» en otro caso. Fuente: CA-08; DC-7; D-04.
- **Changelog**: `kairos doctor` avisa cuando una clave con caducidad vence en menos de 14 días y distingue una clave caducada de una inválida.
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real 0.02h (medido; el trabajo de la tarea está medido en la ventana de T-19, ver Notas)
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-20
- **Tipo**: client
- **Archivos**: `client/lib/mcp.mjs`, `client/lib/lifecycle-config.mjs`, `client/tests/mcp.test.mjs`, `client/README.md`
- **Cubre (tests)**: —
- **Verificación**: `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [x] Con reloj controlado y servidor simulado: avisa a menos de 14 días, no avisa sin caducidad y distingue «caducada» de «inválida» según el dato guardado
- [x] Otro fichero de clave (otro `prefix`) no hereda la caducidad
- [x] Ni los mensajes ni `credential.json` contienen la clave entera

**Subtareas**
- [x] Pruebas en rojo
- [x] Lectura de `/v1/auth/me` y `credential.json`
- [x] Mensajes de `doctor`

**Notas**: RED: `client/tests/mcp.test.mjs (4 pruebas nuevas de doctor, contra lib/mcp.mjs y lib/lifecycle-config.mjs de 00a8f82)` falló con SyntaxError: The requested module '../lib/lifecycle-config.mjs' does not provide an export named 'credentialFile' (no había lectura de `/v1/auth/me` ni `credential.json`) · 2026-11-27. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `6e6fe31c7a01`.

### T-22 — Matriz de revocación: `/v1`, los dos `/mcp`, un flujo abierto y la sesión del portal (CA-11)

- **Descripción**: Para una clave que responde 200 en `/v1`, en los dos `/mcp` (el de `kairos-mcp`, a través del proxy web) y con un flujo de actividad abierto, comprobar el 401 en la petición siguiente tras revocarla, caducarla y deshabilitar a su dueño, y el cierre del flujo en un sondeo más un margen. Incluye la sesión del portal cerrada o de un usuario deshabilitado. Fuente: CA-11; criterio de cierre 2 del plan director.
- **Changelog**: Interno: matriz de pruebas de revocación en todas las rutas.
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real 0.17h (medido; parte del trabajo está en las ventanas de T-19 y T-20, ver Notas)
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: T-21
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_revocation_matrix.py`, `server/memory_platform/tests/nginx_portal_probe.py`, `server/memory_platform/tests/chain_harness.py`, `server/memory_platform/tests/test_nginx_portal.py`, `server/memory_platform/store_auth.py`, `server/memory_platform/auth.py`, `server/memory_platform/tests/test_access_users.py` (añadidos con nota: revocar la clave o cerrar la sesión con que se hace un alta en curso no la detiene; revisión de la fase 3, intento 2, gap 1)
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_revocation_matrix|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [x] Tres causas (revocar, caducar, deshabilitar al dueño) × cuatro rutas → 401 en la petición siguiente; el flujo se cierra en un sondeo más un margen
- [x] Sesión del portal cerrada o de un usuario deshabilitado → 401
- [x] Mutante: quitar el vaciado de caché de un escritor deja en rojo el recorrido estático (`WritersEmptyTheCacheTests`); una caché que sobrevive a su transacción deja en rojo la matriz (texto corregido por el orquestador en la revisión de la fase 4, intento 1, gap 10: la caché vive una transacción y la matriz no puede ver el primer mutante)
- [x] Revocar la clave (`revoke_key`) o cerrar la sesión (logout) con que está en curso un `create_user` o un `create_key` bloquea la fila del dueño: el alta espera y falla con 401 sin crear nada; prueba en los dos órdenes y mutante (revisión de la fase 3, intento 2, gap 1)

**Subtareas**
- [x] Montar la matriz sobre los arneses existentes
- [x] Flujo abierto con sondeo controlado
- [x] Mutante

**Notas**: Confirma la hipótesis de la spec: el `/mcp` interno autentica con las mismas funciones que `/v1`.

**Notas**: RED: `test_access_users.CredentialEndRaceTests (2 pruebas, 8 casos: clave o sesión × alta de clave o de usuario × dos órdenes, contra el código de 28a6cd3)` falló con AssertionError: False is not true : the creation did not wait for the end of its credential (×4) y the end of the credential did not wait for the creation in progress (×4) · 2026-11-27. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `16897903c2fd`.

### T-23 — Documentar credenciales: contraseña, usuarios, sesiones, claves y scrypt

- **Descripción**: `docs/configuration.md` (`MEMORY_LOGIN_CONCURRENCY` y el coste de scrypt medido), `docs/operations.md` (recuperación del administrador, deshabilitar, rotar, y la deuda declarada del ataque de login desde muchas IP, a cargo del proxy de la Iniciativa 5) y `client/README.md` (`doctor --online`). Fuente: CA-37; DC-5.
- **Changelog**: Los manuales explican el cambio de contraseña, la baja de usuarios, las sesiones, la caducidad y la rotación de claves.
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 1.5h · real —
- **Tiempo IA (ejec.)**: est. 0.15h · real 0.03h (medido; el borrador está en la ventana de T-20)
- **Supervisión**: est. 0.04h · real —
- **Previsión IA**: 43 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-22
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `client/README.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: variables y valores iguales a `config.py` y a «Valores medidos»; cada comando `admin` citado existe con esas opciones

**Criterios de aceptación**
- [x] Nombres y valores coinciden con `config.py`
- [x] `docs/operations.md` explica la recuperación del administrador y qué significa cada 401, 409 y 503 nuevo

**Subtareas**
- [x] Redactar y cotejar con el código

**Notas**: TDD n/a: documentación. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `c243050854b9`.

### T-24 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, cliente, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: completado
- **Cerrada**: 2026-11-27
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real 0.08h (medido; la suite completa, 33 min de reloj, corre fuera de la medición de tokens)
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-23
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd client && npm test` → `fail 0`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [x] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [x] Suites, mínimo y archivo de las notas de la fase

**Notas**: TDD n/a: cierre de fase. Detalle archivado: [execution-history.md](execution-history.md) · SHA-256 `8cdb1bd0d57d`.

### T-25 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: rotación (carreras, gracia, `replaced_by`), caducidad, `last_used_at` en el camino de autenticación, `credential.json` sin secreto y huecos de la matriz de revocación.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: en-progreso
- **Tiempo humano**: est. 20h · real —
- **Tiempo IA (ejec.)**: est. 2.05h · real —
- **Supervisión**: est. 0.51h · real —
- **Previsión IA**: 567 k in / 49 k out tok · ⚠️ verificar €
- **Dependencias**: T-24
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 5 — Login que no se bloquea entre clientes (C-02)

**Estado**: borrador · **Hito**: A · **Estimado**: 43.2h (36h base, de ellas 18h de revisión adversarial) · **Real**: — · **Coste est.**: 2.160 € · **Tokens est.**: 1109 k

### T-26 — Login: contar solo los fallos y bloquear por IP con `Retry-After` (CA-12, CA-13)

- **Descripción**: `login_attempts` solo recibe fallos; un acierto no cuenta ni borra los de su IP. Bloqueo solo por IP de cliente: `MEMORY_LOGIN_MAX_FAILURES` en `MEMORY_LOGIN_WINDOW` (10 en 15 min) → 429 `rate_limited` con `Retry-After`, decidido antes del semáforo de T-08 y de scrypt. Lo construye `server/memory_platform/limits.py`, que nace aquí solo con el constructor único del 429 (DC-2) y crece en el hito B. Los fallos por usuario se publican como `login_user_failures`, sin bloquear (P-05). El recuento es correcto con logins concurrentes y usa el índice `login_attempt_ip_time`. Fuente: CA-12, CA-13, CA-15; S-02; DC-2; DC-5.
- **Changelog**: El inicio de sesión cuenta solo los fallos y bloquea por IP de cliente (10 fallos en 15 min, 429 con `Retry-After`); ya no bloquea por nombre de usuario.
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h · real —
- **Tiempo IA (ejec.)**: est. 0.67h · real —
- **Supervisión**: est. 0.17h · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-25
- **Tipo**: backend
- **Archivos**: `server/memory_platform/auth.py`, `server/memory_platform/limits.py`, `server/memory_platform/passwords.py`, `server/memory_platform/app.py`, `server/memory_platform/config.py`, `server/memory_platform/observability.py`, `server/memory_platform/tests/test_login_limits.py`, `server/memory_platform/tests/test_auth.py`, `server/memory_platform/tests/test_auth_race.py`, `server/memory_platform/tests/test_observability.py`, `server/memory_platform/tests/test_prune_tables.py`, `server/memory_platform/store_access.py`, `server/memory_platform/tests/test_access_password.py`, `docs/contracts/memory-platform.openapi.json`, `server/memory_platform/tests/test_contract_additive.py` (añadidos con nota: 429 de `POST /v1/auth/password` sin `Retry-After` (revisión fase 2, intento 2, gap 6; intento 3, gap 5); 404 y esquema `Error` en el OpenAPI (revisión fase 3, intento 2))
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_login_limits|test_auth|test_auth_race|test_observability|test_prune_tables|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Treinta logins correctos seguidos desde la misma IP no producen 429
- [ ] Diez fallos desde la IP `a` para U: el login correcto de U desde la IP `b` responde 200 y el undécimo de `a` recibe 429 con `Retry-After` ≥ 1
- [ ] Veinte fallos concurrentes de una IP no dejan pasar más de diez verificaciones; una IP bloqueada no deriva scrypt ni ocupa hueco
- [ ] `login_user_failures` se publica sin bloquear; ningún registro guarda la contraseña; `prune-tables` sigue purgando `login_attempts`
- [ ] Los 429 de `POST /v1/auth/password` (`rate_limited` y `too_many_attempts`, `store_access.py`) salen del constructor único de DC-2 con `Retry-After` ≥ 1 (revisión de la fase 2, intento 2, gap 6)
- [ ] El OpenAPI publica el 404 de `GET /v1/users/{id}/sessions` y el esquema `Error` declara el sobre real `{code, message}` (revisión de la fase 3, intento 2, fuera de lente)

**Subtareas**
- [ ] Pruebas en rojo (oráculo de A-02) y de carrera
- [ ] Contador de fallos, cubo por IP, métrica y variables

### T-27 — IP real del cliente: `MEMORY_TRUSTED_PROXIES` y `X-Forwarded-For` en nginx (CA-14)

- **Descripción**: La API toma la dirección no fiable más a la derecha de `X-Forwarded-For`, y solo si el par inmediato pertenece a `MEMORY_TRUSTED_PROXIES`; vacía, ignora la cabecera y se comporta como hoy. `web/nginx.conf` envía la cabecera en sus tres bloques hacia la API y el Compose define la variable con sus redes internas. Los dos ficheros los usa la instalación desplegada: ninguna tarea ejecuta su `up` (R-07). Fuente: CA-14; S-02; R-07.
- **Changelog**: Nueva `MEMORY_TRUSTED_PROXIES`: detrás del proxy web, la API registra la IP real del cliente; el proxy envía `X-Forwarded-For`.
- **Estado**: borrador
- **Tiempo humano**: est. 5.5h · real —
- **Tiempo IA (ejec.)**: est. 0.56h · real —
- **Supervisión**: est. 0.14h · real —
- **Previsión IA**: 156 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-26
- **Tipo**: backend
- **Archivos**: `server/memory_platform/app.py`, `server/memory_platform/auth.py`, `server/memory_platform/config.py`, `web/nginx.conf`, `docker-compose.yml`, `server/memory_platform/tests/test_client_ip.py`, `server/memory_platform/tests/test_nginx_routes.py`, `server/memory_platform/tests/test_compose_limits.py`, `docs/configuration.md`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_client_ip|test_nginx_routes|test_compose_limits|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Un `X-Forwarded-For` de un par que no es de confianza se ignora: ni esquiva el bloqueo ni bloquea a otra IP
- [ ] Con dos proxies de confianza encadenados se toma la dirección no fiable más a la derecha; una cabecera mal formada cae en la IP del par
- [ ] `/metrics` en modo `internal` sigue respondiendo 404 a través del proxy; una lista de proxies inválida impide arrancar con un error claro
- [ ] Los manuales documentan `MEMORY_TRUSTED_PROXIES`, `MEMORY_LOGIN_MAX_FAILURES` y `MEMORY_LOGIN_WINDOW`, cómo leer el 429 de login y el riesgo de una lista mal configurada

**Subtareas**
- [ ] Pruebas en rojo
- [ ] IP real en la API, nginx y Compose
- [ ] Manuales

**Notas**: Revisión fase 2, intento 2, gap 7 (diferido aquí y a T-55): el hueco por IP de la compuerta de T-08 lo toman el login, `POST /v1/auth/password` y `POST /v1/users` (`app.py`, `request.client.host`); tras nginx todos comparten hoy la IP del proxy, así que un admin de proyecto que encadena altas autorizadas ocupa el hueco de todos. La IP real de esta tarea debe llegar también a esas dos rutas, no solo al login, para que cada cliente ocupe solo el hueco de su IP.

### T-28 — Pruebas de login con proxy simulado y nginx real (CA-13, CA-14)

- **Descripción**: Casos de extremo a extremo: proxy HTTP simulado delante de la API, dos proxies encadenados y la configuración real de `web/nginx.conf` con `nginx_portal_probe.py`. El cliente A falla diez veces a través del proxy y el cliente B, desde otra IP, entra. Fuente: CA-13, CA-14; criterio de cierre 3 del plan director.
- **Changelog**: Interno: pruebas de login a través del proxy.
- **Estado**: borrador
- **Tiempo humano**: est. 5.5h · real —
- **Tiempo IA (ejec.)**: est. 0.56h · real —
- **Supervisión**: est. 0.14h · real —
- **Previsión IA**: 156 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-27
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_login_proxy.py`, `server/memory_platform/tests/nginx_portal_probe.py`, `server/memory_platform/tests/test_nginx_portal.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_login_proxy|test_nginx_portal|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] A través de nginx real, la API registra la IP del cliente y no la del proxy
- [ ] CA-13 completo a través del proxy: B recibe 200 y el undécimo intento de A, 429 con `Retry-After`
- [ ] Mutante: quitar la cabecera de `web/nginx.conf` o la comprobación del par de confianza deja la prueba en rojo

**Subtareas**
- [ ] Proxy simulado y encadenado
- [ ] Caso con nginx real
- [ ] Mutantes

### T-29 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-28
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-30 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: suplantación de IP por cabecera, bloqueo de terceros, enumeración de usuarios por tiempo o por respuesta y el orden bloqueo → semáforo → scrypt.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 18h · real —
- **Tiempo IA (ejec.)**: est. 1.85h · real —
- **Supervisión**: est. 0.46h · real —
- **Previsión IA**: 510 k in / 44 k out tok · ⚠️ verificar €
- **Dependencias**: T-29
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 6 — Cierre del hito A: acceso que se puede retirar

**Estado**: borrador · **Hito**: A · **Estimado**: 9.6h (8h base) · **Real**: — · **Coste est.**: 480 € · **Tokens est.**: 873 k

### T-31 — Ensayo aislado del hito A: revocación en todas las rutas y login que no bloquea a otro

- **Descripción**: Crear `scripts/rehearse-access-control.py` (etapas `a`, `b` y `all`) y ejecutar la etapa `a` en un proyecto Compose desechable `kairos-acc-a`: una clave revocada deja de funcionar en `/v1` y en los dos `/mcp`, una sesión cerrada deja de valer en el portal, y diez fallos de login de un cliente no bloquean a otro. Fuente: CA-11, CA-13; criterios de cierre 2 y 3 del plan director.
- **Changelog**: Interno: ensayo aislado del hito A (revocación en todas las rutas y login entre clientes).
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0.21h · real —
- **Supervisión**: est. 0.05h · real —
- **Previsión IA**: 57 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-30
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-access-control.py`, `scripts/tests/test_rehearse_access_control.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_access_control.py` → `OK`
  - `python scripts/rehearse-access-control.py --project-name kairos-acc-a --embed-stub --stage a` → `revoked_everywhere` y `login_not_blocked_across_clients`

**Criterios de aceptación**
- [ ] Un solo proyecto `kairos-acc-a`, retirado al acabar; nada `knowledge-graphs-*`
- [ ] La salida con las dos marcas queda en `Notas`
- [ ] Si recrea un servicio, usa los mismos `-f` de Compose con que se creó (gotcha pendiente `2026-11-19-compose-recreate-loses-overrides.md`)

**Subtareas**
- [ ] Script por etapas y su prueba con dobles
- [ ] Ejecutar la etapa `a` en primer plano
- [ ] Retirar el proyecto

### T-32 — Revisión del diff completo del hito A

- **Descripción**: Lentes completas sobre el diff entero del hito (`git diff main...HEAD`), no fase a fase: interacciones entre fases, alcance declarado, restricciones duras y deuda aceptada. Partida propia de ≥ 2 h IA. Cada fix se revisa como código nuevo. Fuente: retro de la Iniciativa 3; CA-35.
- **Changelog**: Interno: revisión del diff completo del hito A.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 2.50h · real —
- **Supervisión**: est. 0.62h · real —
- **Previsión IA**: 690 k in / 60 k out tok · ⚠️ verificar €
- **Dependencias**: T-31
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --stat main...HEAD` → rango y recuento de ficheros iguales a los que cita `review.md`
  - lectura: sección «Hito A — diff completo» de `review.md` sin Critical ni Important abiertos, con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Hito A — diff completo» con el rango revisado y cero Critical/Important abiertos
- [ ] Cada fix pasó por lentes completas y suma su intento medido; suites en verde tras las correcciones

**Subtareas**
- [ ] Lentes completas sobre el diff entero
- [ ] Corregir la clase entera y revisar cada fix

### T-33 — Comprobaciones de cierre y notas de cambio del hito A

- **Descripción**: Comprobar migraciones solo aditivas (la versión 13 no se reabre), diff aditivo de ambos contratos, `kairos-mcp.json` sin cambios, ningún ensayo ni prueba contra recursos `knowledge-graphs-*` y suites con 0 fallos y 0 omitidos. Escribir las entradas del hito en los dos CHANGELOG, bajo «Sin publicar», y repasar la frase «Coordinación» del plan: rutas nuevas, campos de `/v1/auth/me`, bloqueo de login por IP, 503 `login_busy` y `MEMORY_TRUSTED_PROXIES`. Fuente: CA-10, CA-37.
- **Changelog**: Interno: comprobaciones de cierre y notas de cambio del hito A.
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h · real —
- **Tiempo IA (ejec.)**: est. 0.15h · real —
- **Supervisión**: est. 0.04h · real —
- **Previsión IA**: 43 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-32
- **Tipo**: test
- **Archivos**: `CHANGELOG.md`, `CHANGELOG.es.md`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `python scripts/export-contracts.py && git diff --ignore-cr-at-eol --exit-code -- docs/contracts/kairos-mcp.json mcp/contract/kairos-mcp.json` → sin diferencias
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `cd client && npm test` → `fail 0`
  - lectura: los dos CHANGELOG listan lo mismo y cada ítem del hito en «Coordinación» tiene su entrada

**Criterios de aceptación**
- [ ] `test_migrations_additive.py` y `test_contract_additive.py` pasan; mismas herramientas MCP
- [ ] CA-01 a CA-15 y CA-38 (a) tienen evidencia en `Notas` de su tarea
- [ ] Mismas entradas en los dos idiomas; no cambia la versión ni se publica nada

**Subtareas**
- [ ] Comprobaciones, de una en una
- [ ] CHANGELOG y «Coordinación»

### T-34 — Pull request del hito A (solo con OK del usuario)

- **Descripción**: Abrir el PR del hito A desde `feat/access-control`, solo con el OK expreso del usuario; la tarea no se cierra hasta que el PR exista. Sin merges ni publicación. Fuente: evaluación (un PR por hito).
- **Changelog**: Interno: PR del hito A.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-33
- **Tipo**: devops
- **Archivos**: `docs/roadmap/2026-11-19-access-control/tasks.md`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view --json number,state,headRefName` → PR abierto desde `feat/access-control` (`state: OPEN`)

**Criterios de aceptación**
- [ ] OK expreso del usuario anotado en `Notas`
- [ ] El PR enlaza el ledger y lista los criterios de cierre 2 y 3 del plan director con su evidencia; CI en verde o equivalente local anotado

**Subtareas**
- [ ] Pedir el OK y abrir el PR
- [ ] Anotar el número en `Notas`

---

## Fase 7 — Mediciones del hito B y superficie de secretos (C-06)

**Estado**: borrador · **Hito**: B · **Estimado**: 44.4h (37h base, de ellas 9h de revisión adversarial) · **Real**: — · **Coste est.**: 2.220 € · **Tokens est.**: 3082 k

### T-35 — Medición previa del perfil real de peticiones del cliente (CA-16)

- **Descripción**: En un proyecto Compose aislado `kairos-acc-m`, medir peticiones por minuto (pico y media), escrituras por día y flujos abiertos de: una sesión con hooks, una reindexación, la sonda `memory-probe` y una publicación como la de custom-agents. Contar aparte las lecturas `/v1/auth/me` de `kairos-mcp`. Fuente: CA-16; P-06; R-03.
- **Changelog**: Interno: medición previa del perfil de peticiones.
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 4.00h · real —
- **Supervisión**: est. 1.00h · real —
- **Previsión IA**: 1104 k in / 96 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/measure-request-profile.py`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md` (tabla «Valores medidos»)
- **Cubre (tests)**: —
- **Verificación**: `python scripts/measure-request-profile.py --project-name kairos-acc-m --embed-stub` → JSON con `peak_per_minute`, `writes_per_day` y `open_streams` por escenario

**Criterios de aceptación**
- [ ] Queda en `Notas` y en «Valores medidos» **antes** de T-54: tasa, ráfaga, cuota diaria, lote de escritura, cubo de la clase `identity` y topes de flujos, cada uno con su margen declarado sobre el pico
- [ ] La sonda y la reindexación no agotan los valores propuestos, o llevan una anulación por clave propuesta
- [ ] Proyecto aislado retirado al acabar; nada `knowledge-graphs-*`

**Subtareas**
- [ ] Script con los cuatro escenarios
- [ ] Ejecutar en primer plano y anotar
- [ ] Proponer valores y margen

**Notas**: Estimada en 4 h IA: necesita la pila aislada completa y un cliente real.

### T-36 — Medición previa del detector de entropía sobre un corpus sin secretos (CA-24)

- **Descripción**: Prototipo del detector conservador (alta entropía solo junto a un nombre o contexto de secreto) y medición de su tasa de redacción sobre `docs/` y `retrieval_eval/dataset-v1.jsonl`, para varios umbrales y longitudes mínimas. Fuente: CA-24; P-07.
- **Changelog**: Interno: medición previa del detector de entropía.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 2.00h · real —
- **Supervisión**: est. 0.50h · real —
- **Previsión IA**: 552 k in / 48 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/measure_redaction.py`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md` (tabla «Valores medidos»)
- **Cubre (tests)**: —
- **Verificación**: `PYTHONPATH=server python -m memory_platform.tests.measure_redaction --mode entropy --corpus docs --dataset server/memory_platform/tests/retrieval_eval/dataset-v1.jsonl` → JSON con `redacted` por umbral y los fragmentos afectados

**Criterios de aceptación**
- [ ] Umbral y longitud mínima propuestos en «Valores medidos», con la tasa medida (objetivo: 0 redacciones en el corpus sin secretos)
- [ ] Hashes sha256, UUID, SHA de commit y rutas del corpus no se redactan con el umbral propuesto

**Subtareas**
- [ ] Prototipo y barrido de umbrales
- [ ] Anotar y proponer

### T-37 — Medición previa del coste de las reglas con entrada adversaria (CA-27)

- **Descripción**: Medir el tiempo de las reglas actuales y de los patrones candidatos con entradas adversarias del tamaño máximo admitido, en `privacy.py` y en `client/lib/privacy.mjs`, y proponer la cota de CA-27. Detectar los patrones con retroceso costoso antes de implementarlos. Fuente: CA-27; R-05.
- **Changelog**: Interno: medición previa del coste de la redacción.
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 1.50h · real —
- **Supervisión**: est. 0.38h · real —
- **Previsión IA**: 414 k in / 36 k out tok · ⚠️ verificar €
- **Dependencias**: T-36
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/measure_redaction.py`, `client/tests/measure-redaction.mjs`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md` (tabla «Valores medidos»)
- **Cubre (tests)**: —
- **Verificación**:
  - `PYTHONPATH=server python -m memory_platform.tests.measure_redaction --mode cost` → JSON con `seconds` por patrón y tamaño
  - `node client/tests/measure-redaction.mjs` → el mismo JSON para el cliente

**Criterios de aceptación**
- [ ] Cota propuesta en «Valores medidos» para servidor y cliente, con el tamaño máximo usado y el peor caso medido
- [ ] Ningún patrón candidato crece de forma superlineal; el que lo haga queda reescrito o descartado antes de T-44

**Subtareas**
- [ ] Entradas adversarias por patrón
- [ ] Medir en los dos módulos y proponer la cota

### T-38 — `secrets_dir_unsafe`: el despliegue rechaza un directorio de secretos inseguro (CA-31)

- **Descripción**: `scripts/deploy-memory.py` valida `MEMORY_SECRETS_DIR`/`--secret-dir` antes de cualquier fase y sin efectos: aborta con `secrets_dir_unsafe` si está dentro del repositorio o de una carpeta sincronizada conocida (OneDrive, Dropbox, iCloud, Google Drive), resolviendo enlaces simbólicos. Fuente: CA-31; S-10; R-08.
- **Changelog**: El despliegue aborta con `secrets_dir_unsafe` si el directorio de secretos está dentro del repositorio o de una carpeta sincronizada.
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real —
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: devops
- **Archivos**: `scripts/deploy-memory.py`, `server/memory_platform/tests/test_deploy.py`, `server/memory_platform/tests/test_deploy_isolation.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_deploy|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Dentro del repo o de OneDrive, Dropbox, iCloud o Google Drive (rutas de Windows, macOS y Linux, con enlaces simbólicos) → `secrets_dir_unsafe` antes de la primera fase y sin escribir nada
- [ ] Un directorio externo válido despliega igual que hoy
- [ ] Mutante: quitar la validación deja la prueba en rojo

**Subtareas**
- [ ] Prueba en rojo (oráculo de A-06)
- [ ] Validación sin efectos antes de las fases
- [ ] Detección de carpetas sincronizadas

**Notas**: Cada fix en `deploy-memory.py` suma un intento de revisión completo (evaluación; R-08).

### T-39 — Compose sin `./secrets`, `.private/` sin secretos y guarda de la red `inference` (CA-31, CA-33)

- **Descripción**: `docker-compose.yml` deja de caer en `./secrets`: sin `MEMORY_SECRETS_DIR` falla con un mensaje claro (el cambio llega a la instalación en su próximo `up`; hoy ya define la variable, R-07). Un test comprueba que nada de lo que el despliegue escribe en `.private/` contiene un secreto (P-08). Otro, sobre `docker compose config`, que la red `inference` es interna, que solo la usan el proxy de Ollama, `memory-api` y `memory-worker`, que solo el proxy tiene salida y que todo puerto publicado está en `127.0.0.1`. Fuente: CA-31, CA-33; S-10; P-08.
- **Changelog**: El Compose ya no usa `./secrets` por defecto: `MEMORY_SECRETS_DIR` es obligatorio.
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real —
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: T-38
- **Tipo**: devops
- **Archivos**: `docker-compose.yml`, `scripts/deploy-memory.py`, `server/memory_platform/tests/test_compose_limits.py`, `server/memory_platform/tests/test_deploy.py`, `docs/configuration.md`, `docs/server-install.md`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_compose_limits|test_deploy|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] `docker compose config` sin `MEMORY_SECRETS_DIR` falla con un mensaje que nombra la variable
- [ ] Lo que el despliegue escribe en `.private/` no contiene secretos (dobles de `subprocess` y valores centinela)
- [ ] El test falla si un servicio nuevo entra en `inference` o si un puerto se publica fuera de `127.0.0.1` (mutantes sobre una copia del Compose)
- [ ] Los manuales dicen que el directorio es obligatorio y externo, y describen `secrets_dir_unsafe`

**Subtareas**
- [ ] Pruebas en rojo, Compose y mensaje
- [ ] Guarda de `inference` y manuales

### T-40 — Permisos del fichero de clave: `key_file_too_open` en POSIX y aviso de `doctor` en Windows (CA-32)

- **Descripción**: En POSIX el cliente falla con `key_file_too_open`, sin enviar nada, si grupo u otros tienen permisos sobre el fichero de clave. En Windows, `kairos doctor` avisa, en el mejor esfuerzo, de ACL abiertas (`icacls`) o de una clave en una carpeta sincronizada (P-09). Fuente: CA-32; S-11; P-09.
- **Changelog**: El cliente rechaza en POSIX un fichero de clave legible por otros (`key_file_too_open`); en Windows, `kairos doctor` avisa.
- **Estado**: borrador
- **Tiempo humano**: est. 5.5h · real —
- **Tiempo IA (ejec.)**: est. 0.56h · real —
- **Supervisión**: est. 0.14h · real —
- **Previsión IA**: 156 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-39
- **Tipo**: client
- **Archivos**: `client/lib/files.mjs`, `client/lib/mcp.mjs`, `client/lib/errors.mjs`, `client/tests/mcp.test.mjs`, `client/tests/install.test.mjs`, `client/README.md`
- **Cubre (tests)**: M-02
- **Verificación**: `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Modo `0644` o `0640` → `key_file_too_open` y ninguna petición sale (servidor simulado sin llamadas); `0600` funciona
- [ ] En Windows el aviso no bloquea y un fallo de `icacls` no rompe `doctor`
- [ ] Ningún mensaje contiene la clave; `client/README.md` describe `key_file_too_open` y el aviso de Windows

**Subtareas**
- [ ] Pruebas en rojo y comprobación POSIX
- [ ] Aviso de Windows

### T-41 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, cliente.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-40
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-42 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 0,5 × la implementación. Superficie: evasión de la validación del directorio (enlaces, mayúsculas, rutas UNC, unidades), fugas de la clave en mensajes y regresiones del despliegue.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 9h · real —
- **Tiempo IA (ejec.)**: est. 0.92h · real —
- **Supervisión**: est. 0.23h · real —
- **Previsión IA**: 255 k in / 22 k out tok · ⚠️ verificar €
- **Dependencias**: T-41
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

**Notas**: Suma un intento de revisión completo por cada fix en `deploy-memory.py` (evaluación).

---

## Fase 8 — Redacción: casos compartidos, patrones y entropía (C-04)

**Estado**: borrador · **Hito**: B · **Estimado**: 42.0h (35h base, de ellas 17.5h de revisión adversarial) · **Real**: — · **Coste est.**: 2.100 € · **Tokens est.**: 1078 k

### T-43 — Fichero de casos de redacción compartido y sus dos ejecutores (CA-22)

- **Descripción**: Crear `docs/contracts/redaction-cases.json` (entrada, qué debe desaparecer y qué debe conservarse) con al menos 40 casos: las siete cadenas de S-01, los patrones actuales y al menos 15 que no deben redactarse (sha256, UUID, SHA de commit, rutas, identificadores). Lo ejecutan la suite del servidor y la del cliente. Nace en rojo en las dos. Fuente: CA-22; S-01.
- **Changelog**: Interno: casos de redacción compartidos por servidor y cliente.
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0.51h · real —
- **Supervisión**: est. 0.13h · real —
- **Previsión IA**: 142 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-37
- **Tipo**: test
- **Archivos**: `docs/contracts/redaction-cases.json`, `server/memory_platform/tests/test_redaction_cases.py`, `server/memory_platform/Dockerfile`, `client/tests/redaction-cases.test.mjs`, `client/package.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_redaction_cases|MEMORY_TEST_RESULT"` → rojo solo en los casos de S-01 (esperado hasta T-44)
  - `cd client && npm test` → rojo solo en los casos de S-01 (esperado hasta T-45)

**Criterios de aceptación**
- [ ] ≥ 40 casos, de ellos ≥ 15 de «no redactar»; las dos suites validan la forma del fichero
- [ ] Un caso nuevo sin implementar deja en rojo las dos suites (comprobado añadiendo y retirando uno)
- [ ] Todas las cadenas son sintéticas

**Subtareas**
- [ ] Escribir los casos (oráculo de A-04)
- [ ] Ejecutor del servidor y `COPY` en la imagen de test
- [ ] Ejecutor del cliente

### T-44 — Patrones nuevos en el servidor (`privacy.py`) (CA-23)

- **Descripción**: Añadir a `privacy.py` los patrones de S-01: nombres `*_KEY`, `*_PASS` y afines; prefijos `sk_live_`, `sk_test_`, `rk_live_`, `glpat-`, `hf_`, `npm_` y la clave propia `mp_`; `curl -u`/`--user`; `Authorization: Basic`. Trabajo acotado desde el primer intento, sin retroceso costoso y dentro de la cota de T-37. `redact_log` usa las mismas reglas. Fuente: CA-23; S-01; R-05.
- **Changelog**: El servidor redacta más formatos de secreto: `*_KEY`, `*_PASS`, `sk_live_`, `glpat-`, `hf_`, `npm_`, `mp_`, `curl -u` y `Authorization: Basic`.
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h · real —
- **Tiempo IA (ejec.)**: est. 0.36h · real —
- **Supervisión**: est. 0.09h · real —
- **Previsión IA**: 99 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-43
- **Tipo**: backend
- **Archivos**: `server/memory_platform/privacy.py`, `server/memory_platform/observability.py`, `server/memory_platform/tests/test_privacy.py`, `server/memory_platform/tests/test_redaction_cases.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_privacy|test_redaction_cases|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Los casos de S-01 pasan en el servidor y ningún caso «no redactar» se redacta
- [ ] Una clave `mp_…` no sobrevive a `redact` ni a `redact_log`
- [ ] Cada patrón tiene su mutante: quitarlo deja un caso en rojo

**Subtareas**
- [ ] Patrones con trabajo acotado
- [ ] Mutantes

### T-45 — Patrones nuevos en el cliente (`privacy.mjs`) y fin de la divergencia de `sk-` (CA-23)

- **Descripción**: Los mismos patrones en `client/lib/privacy.mjs`, con `sk-` unificado (hoy exige 32 caracteres en el servidor y 24 en el cliente; el fichero de casos fija el criterio). Las diferencias entre `re` y `RegExp` se cubren con casos límite. Fuente: CA-23; S-01.
- **Changelog**: El cliente redacta los mismos formatos de secreto que el servidor antes de escribir en disco o enviar.
- **Estado**: borrador
- **Tiempo humano**: est. 4.5h · real —
- **Tiempo IA (ejec.)**: est. 0.46h · real —
- **Supervisión**: est. 0.12h · real —
- **Previsión IA**: 128 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-44
- **Tipo**: client
- **Archivos**: `client/lib/privacy.mjs`, `client/tests/redaction-cases.test.mjs`, `client/tests/capture.test.mjs`, `docs/contracts/redaction-cases.json`
- **Cubre (tests)**: —
- **Verificación**: `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] El fichero compartido pasa entero en el cliente
- [ ] `sk-` se comporta igual en los dos módulos (caso límite de longitud en el fichero)
- [ ] Casos límite de `re` frente a `RegExp` (multilínea, Unicode, comillas y escapes) con el mismo resultado

**Subtareas**
- [ ] Patrones en JavaScript
- [ ] Unificar `sk-`
- [ ] Casos límite

### T-46 — Detector de entropía conservador y cota de tiempo, en servidor y cliente (CA-24, CA-27)

- **Descripción**: Implementar el detector con el umbral y la longitud mínima de T-36: redacta una cadena de alta entropía solo junto a un nombre o contexto de secreto; nunca hashes, UUID, SHA de commit ni rutas. Un test pasa a las reglas definitivas una entrada adversaria del tamaño máximo admitido y comprueba la cota de T-37 en los dos módulos, por trabajo y con un margen de tiempo amplio. Fuente: CA-24, CA-27; P-07; R-05; R-10.
- **Changelog**: Un detector conservador redacta cadenas de alta entropía solo cuando van junto a un nombre o contexto de secreto.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-45
- **Tipo**: backend
- **Archivos**: `server/memory_platform/privacy.py`, `client/lib/privacy.mjs`, `docs/contracts/redaction-cases.json`, `server/memory_platform/tests/test_privacy.py`, `server/memory_platform/tests/measure_redaction.py`, `client/tests/capture.test.mjs`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_privacy|test_redaction_cases|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `cd client && npm test` → `fail 0`
  - `PYTHONPATH=server python -m memory_platform.tests.measure_redaction --mode entropy --corpus docs --dataset server/memory_platform/tests/retrieval_eval/dataset-v1.jsonl` → 0 redacciones con la implementación final

**Criterios de aceptación**
- [ ] Ningún caso «no redactar» de CA-22 se redacta con el umbral definitivo; la medición repetida da 0 redacciones en el corpus sin secretos
- [ ] Entrada adversaria de tamaño máximo dentro de la cota, en servidor y cliente
- [ ] Mutante: un patrón con retroceso cuadrático deja el test de cota en rojo

**Subtareas**
- [ ] Detector en los dos módulos y casos nuevos en el fichero compartido
- [ ] Test de cota y mutante

### T-47 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, cliente.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-46
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-48 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: denegación de servicio por expresiones regulares, divergencias entre `re` y `RegExp`, falsos positivos sobre hashes y rutas, y secretos que escapan por codificación, comillas o saltos de línea.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 17.5h · real —
- **Tiempo IA (ejec.)**: est. 1.80h · real —
- **Supervisión**: est. 0.45h · real —
- **Previsión IA**: 496 k in / 43 k out tok · ⚠️ verificar €
- **Dependencias**: T-47
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

**Notas**: El primer fix de un hallazgo de CPU pide trabajo acotado, vía rápida y prueba de tamaño máximo (retro de la Iniciativa 2).

---

## Fase 9 — Redacción en todas las rutas y de extremo a extremo (C-04)

**Estado**: borrador · **Hito**: B · **Estimado**: 34.8h (29h base, de ellas 14.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.740 € · **Tokens est.**: 893 k

### T-49 — Tabla ruta → comportamiento y un test por ruta que guarda texto (CA-25)

- **Descripción**: Escribir en `docs/operations.md` la tabla de las rutas de `/v1` que guardan texto (eventos, notas, documentos, estado de trabajo, trabajo de equipo y respuestas de corpus) con su comportamiento, redactar o rechazar, y un test por ruta que lo comprueba con un secreto nuevo. Un recorrido falla si una ruta que guarda texto no está en la tabla. Fuente: CA-25; hecho 4 de la spec.
- **Changelog**: Los patrones nuevos se aplican en todas las rutas que guardan texto: las capturas se redactan; los documentos y el estado de trabajo con un secreto se rechazan.
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real —
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: T-48
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_ingest.py`, `server/memory_platform/store_documents.py`, `server/memory_platform/agent_store.py`, `server/memory_platform/extended_store.py`, `server/memory_platform/corpus_answers.py`, `server/memory_platform/tests/test_redaction_routes.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_redaction_routes|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Las seis familias de rutas redactan o rechazan según la tabla
- [ ] Una clave `mp_…` no queda guardada por ninguna ruta (consulta directa a la base de pruebas)
- [ ] Una ruta nueva que guarde texto sin fila en la tabla deja el recorrido en rojo

**Subtareas**
- [ ] Tabla y recorrido
- [ ] Un test por familia de rutas

### T-50 — Las siete cadenas de S-01 de extremo a extremo: cola del cliente, base y logs (CA-23)

- **Descripción**: Para cada cadena de S-01 dentro de una captura, el secreto no aparece en la salida del cliente ni en el fichero de su cola, ni en la base tras recibirla el servidor, ni en una línea de log. Fuente: CA-23.
- **Changelog**: Interno: prueba de extremo a extremo de la redacción.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-49
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_redaction_routes.py`, `server/memory_platform/tests/test_observability.py`, `client/tests/capture.test.mjs`, `client/tests/dispatcher.test.mjs`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_redaction_routes|test_observability|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Siete cadenas × cuatro sitios (salida del cliente, cola en disco, base y log) sin rastro del secreto
- [ ] El recibo indica la redacción, como hoy

**Subtareas**
- [ ] Casos del cliente
- [ ] Casos del servidor y de log

### T-51 — Rechazos con los códigos actuales, contrato MCP intacto y nota a la Iniciativa 7 (CA-26)

- **Descripción**: Comprobar que los rechazos nuevos de documentos y estado de trabajo usan los códigos actuales (`sensitive_source_requires_review` u homólogo) y que `kairos-mcp.json` no cambia. Declarar el cambio de comportamiento en `CHANGELOG*.md` con nota para la Iniciativa 7 (más rechazos para quien publica) y documentar los patrones en `docs/configuration.md`. Fuente: CA-26; R-12.
- **Changelog**: Aviso para integraciones: con los patrones nuevos, más documentos y estados de trabajo con secretos se rechazan, con los códigos de error actuales.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-50
- **Tipo**: backend
- **Archivos**: `server/memory_platform/tests/test_redaction_routes.py`, `mcp/tests/tool_cases.py`, `CHANGELOG.md`, `CHANGELOG.es.md`, `docs/configuration.md`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_redaction_routes|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `python scripts/export-contracts.py && git diff --ignore-cr-at-eol --exit-code -- docs/contracts/kairos-mcp.json mcp/contract/kairos-mcp.json` → sin diferencias
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [ ] Ningún código de error nuevo en `/v1` ni en el contrato MCP por la redacción
- [ ] Ambos CHANGELOG declaran el cambio con la nota para la Iniciativa 7, y la frase «Coordinación» del plan lo recoge
- [ ] `docs/configuration.md` lista los patrones y el criterio del detector de entropía

**Subtareas**
- [ ] Tests de códigos
- [ ] CHANGELOG y nota
- [ ] Manual

### T-52 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, cliente, `kairos-mcp`, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-51
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd client && npm test` → `fail 0`
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-53 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: rutas que guardan texto sin pasar por la redacción, secretos en logs y en mensajes de error, y rechazos que rompen a un cliente existente.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 14.5h · real —
- **Tiempo IA (ejec.)**: est. 1.49h · real —
- **Supervisión**: est. 0.37h · real —
- **Previsión IA**: 411 k in / 36 k out tok · ⚠️ verificar €
- **Dependencias**: T-52
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 10 — Límites en el servidor: clases, tasa, cuota y flujos (C-03)

**Estado**: borrador · **Hito**: B · **Estimado**: 60.0h (50h base, de ellas 25h de revisión adversarial) · **Real**: — · **Coste est.**: 3.000 € · **Tokens est.**: 1540 k

### T-54 — `limits.py`: clases de ruta y recorrido que exige una clase por operación (DC-3)

- **Descripción**: Tabla cerrada `operation_id → clase` en `limits.py`: `exempt` (`/health/*`, `/metrics`, login y logout), `identity` (`GET /v1/auth/me`), `read`, `write` y `stream`. No se clasifica por método HTTP: `/v1/search` y `/v1/context` son `POST` de lectura. Un test recorre las rutas de la aplicación y las herramientas del MCP interno y falla si alguna no tiene clase. Fuente: CA-17, CA-20; DC-3.
- **Changelog**: Interno: cada operación queda clasificada para los límites.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-35
- **Tipo**: backend
- **Archivos**: `server/memory_platform/limits.py`, `server/memory_platform/app.py`, `server/memory_platform/mcp.py`, `server/memory_platform/tests/test_limits.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_limits|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Toda operación de `/v1` y toda herramienta del MCP interno tiene clase; una ruta nueva sin clase deja el test en rojo
- [ ] `GET /v1/auth/me` es `identity`; `/health/*`, `/metrics`, login y logout son `exempt`

**Subtareas**
- [ ] Tabla y recorrido (patrón `RouteTableTests`)

### T-55 — Cubo de fichas por credencial: 429 `rate_limited` con `Retry-After` (CA-17)

- **Descripción**: Cubo de fichas en memoria por identificador de credencial (`key_id` o `session_id`), con `MEMORY_RATE_LIMIT_*` (valores de T-35; `0` desactiva) y cubo propio para la clase `identity`. Se cobra después de autenticar, desde `identity()` (`app.py:159-170`) y `AuthenticatedMCP` (`mcp.py:187-211`); una petición sin credencial válida recibe 401 antes y no crea estado. Mensaje fijo `Rate limit exceeded [code=rate_limited retry_after=N]`. Reloj inyectado. Fuente: CA-17; S-08; DC-2; DC-3.
- **Changelog**: Límite de tasa por credencial, activo por defecto: al superarlo, 429 `rate_limited` con `Retry-After`; `0` lo desactiva.
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real —
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: T-54
- **Tipo**: backend
- **Archivos**: `server/memory_platform/limits.py`, `server/memory_platform/app.py`, `server/memory_platform/mcp.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_limits.py`, `server/memory_platform/tests/test_mcp.py`, `docker-compose.yml`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_limits|test_mcp|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] K1 supera su tasa y recibe 429 `rate_limited` con `Retry-After` mientras K2 sigue en 200 en el mismo intervalo
- [ ] `/health/*` y el login no dependen del límite de ninguna clave; agotar el cubo `identity` no gasta el de trabajo
- [ ] Un token inventado recibe 401 y no crea estado; el mapa de cubos está acotado (tamaño comprobado en la prueba)
- [ ] El `/mcp` interno responde el 429 con la cabecera `Retry-After`

**Subtareas**
- [ ] Prueba en rojo (oráculo de A-03)
- [ ] Cubo con reloj inyectado
- [ ] Enganche en `/v1` y en el MCP interno

**Notas**: Revisión fase 2, intento 2, gap 7 (diferido aquí y a T-27): la tasa por credencial es el límite por actor que acota a un admin de proyecto que encadena `POST /v1/users` autorizados; se cobra en `identity()`, antes de que la ruta tome el hueco de la compuerta de T-08, así que el 429 llega sin ocupar hueco ni derivar.

### T-56 — Cuota diaria de escrituras por clave, en `api_keys` y con escritura agrupada (CA-18)

- **Descripción**: Contador en memoria que parte de `write_quota_day` y `write_quota_used` y se guarda en transacción corta propia, con `lock_timeout` corto, en los cuatro casos del diseño (lote lleno, de tamaño fijado en T-35; cuota alcanzada; un minuto; apagado). `MEMORY_WRITE_QUOTA_PER_DAY`; día UTC; 429 `quota_exceeded` con `Retry-After` hasta las 00:00 UTC. Las escrituras del MCP interno cobran en `stored()`. Integra el `last_used_at` de T-19. Fuente: CA-18; D-03; design.md §«Cuota en O1 y O2».
- **Changelog**: Cuota diaria de escrituras por clave: al agotarla, las escrituras reciben 429 `quota_exceeded` y las lecturas siguen.
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h · real —
- **Tiempo IA (ejec.)**: est. 0.67h · real —
- **Supervisión**: est. 0.17h · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-55
- **Tipo**: backend
- **Archivos**: `server/memory_platform/limits.py`, `server/memory_platform/store_auth.py`, `server/memory_platform/auth.py`, `server/memory_platform/app.py`, `server/memory_platform/mcp.py`, `server/memory_platform/config.py`, `server/memory_platform/tests/test_limits_quota.py`, `docker-compose.yml`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_limits_quota|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Cuota agotada: 429 `quota_exceeded` en escrituras y 200 en lecturas; se restablece al cambiar el día UTC (reloj inyectado)
- [ ] Tras reiniciar el proceso sobre el PostgreSQL aislado, la clave agotada sigue en 429 y las demás pierden como mucho un lote, de tamaño declarado
- [ ] Un `FOR SHARE` sobre la fila de la clave no hace fallar la petición: la escritura de uso se aplaza

**Subtareas**
- [ ] Pruebas en rojo, con reinicio del proceso
- [ ] Contador y escritura agrupada
- [ ] Cobro en `/v1` y en `stored()`

### T-57 — `admin set-key-limits` y forma de `api_keys.limits` (CA-18)

- **Descripción**: Definir y validar la forma de `limits` (`jsonb` con tasa, ráfaga, cuota diaria y flujos; `NULL` = valores globales) y el comando `admin set-key-limits`, única vía para fijar la anulación por clave: sin control en el portal ni ruta en `/v1` (excepción declarada). Coste extra de la aclaración 2 del 2026-11-20. Fuente: CA-18; decisión 9.2; design.md §7.
- **Changelog**: Nuevo `admin set-key-limits`: el operador fija límites propios para una clave, por ejemplo la de la sonda.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-56
- **Tipo**: backend
- **Archivos**: `server/memory_platform/admin.py`, `server/memory_platform/limits.py`, `server/memory_platform/store_access.py`, `server/memory_platform/tests/test_admin.py`, `server/memory_platform/tests/test_limits_quota.py`, `docs/operations.md`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_admin|test_limits_quota|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] La anulación por clave prevalece sobre el valor global en tasa, cuota y flujos; `--clear` vuelve a `NULL`
- [ ] Un `limits` mal formado se rechaza al escribirlo; si ya está en la base, se ignora con un evento de log y no impide autenticar
- [ ] El OpenAPI no gana ninguna ruta para ello; el cambio queda auditado

**Subtareas**
- [ ] Prueba en rojo
- [ ] Validación de la forma
- [ ] Subcomando sobre el store

**Notas**: Cada fix en `admin.py` suma un intento de revisión completo (R-08).

### T-58 — Tope de flujos por credencial y global, y métricas de los rechazos (CA-19, CA-21)

- **Descripción**: Concesiones en memoria por flujo, con `MEMORY_STREAMS_PER_CREDENTIAL` y `MEMORY_STREAMS_MAX` (provisional 4 y 50, a confirmar con T-35), que caducan a los 25 s que dura un flujo más un margen; el hueco se libera en el `finally` del generador y al terminar la respuesta. 429 `too_many_streams` con `Retry-After` hasta que caduque la concesión más antigua de la credencial. `/metrics` publica los rechazos por motivo (`rate_limited`, `quota_exceeded`, `too_many_streams`, `login_busy`), sin etiqueta por clave; el evento de log lleva `key_id`, nunca el token. Fuente: CA-19, CA-21; S-08; design.md §«Flujos en O1 y O2».
- **Changelog**: Tope de flujos de actividad abiertos por credencial y global (429 `too_many_streams`); `/metrics` cuenta los rechazos por límite, por motivo.
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real —
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: T-57
- **Tipo**: backend
- **Archivos**: `server/memory_platform/limits.py`, `server/memory_platform/activity.py`, `server/memory_platform/app.py`, `server/memory_platform/config.py`, `server/memory_platform/observability.py`, `server/memory_platform/tests/test_limits_streams.py`, `server/memory_platform/tests/test_observability.py`, `server/memory_platform/tests/test_metrics.py`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_limits_streams|test_observability|test_metrics|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Por encima del tope por credencial → 429 `too_many_streams`; el tope global también se aplica
- [ ] Un flujo cerrado, también por desconexión del cliente, libera su hueco; un hueco perdido se libera solo al caducar (reloj inyectado)
- [ ] Contador por motivo sin etiquetas de clave ni de usuario; el evento de log lleva `key_id` y nunca el token

**Subtareas**
- [ ] Pruebas en rojo y concesiones con caducidad
- [ ] Contadores y evento

### T-59 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-58
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-60 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: agotamiento de memoria del limitador, exenciones suplantables, doble cobro entre `/v1` y el MCP interno, cuota perdida en reinicios y fugas de huecos de flujo.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 25h · real —
- **Tiempo IA (ejec.)**: est. 2.57h · real —
- **Supervisión**: est. 0.64h · real —
- **Previsión IA**: 708 k in / 62 k out tok · ⚠️ verificar €
- **Dependencias**: T-59
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 11 — Límites en `kairos-mcp` y en el cliente (C-03)

**Estado**: borrador · **Hito**: B · **Estimado**: 38.4h (32h base, de ellas 16h de revisión adversarial) · **Real**: — · **Coste est.**: 1.920 € · **Tokens est.**: 986 k

### T-61 — El 429 a través de `kairos-mcp` y en `MCPTransport.call` (CA-20)

- **Descripción**: `kairos-mcp` no cambia de comportamiento: un test fija que el error de herramienta es `Error executing tool remember: Rate limit exceeded [code=rate_limited retry_after=17]`, con la forma `isError` actual, y que su lectura `/v1/auth/me` cae en la clase `identity` (si se agota, no rechaza la petición). En el cliente, `MCPTransport.call` compara el texto del error, entero, con los tres mensajes fijos y lanza un `KairosError` con código y plazo (acotado entre 1 s y 24 h más un margen); reconoce también un 429 HTTP con `Retry-After`. No busca el patrón dentro del texto. Fuente: CA-20; DC-2; DC-3; DC-4; D-01.
- **Changelog**: Un 429 llega a través de `kairos-mcp` como error de herramienta con un mensaje estable (código y plazo), y el cliente lo entiende.
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0.51h · real —
- **Supervisión**: est. 0.13h · real —
- **Previsión IA**: 142 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-60
- **Tipo**: client
- **Archivos**: `mcp/kairos_mcp/client.py`, `mcp/tests/test_limits.py`, `mcp/tests/stub_api.py`, `client/lib/mcp.mjs`, `client/lib/errors.mjs`, `client/tests/mcp.test.mjs`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `python scripts/export-contracts.py && git diff --ignore-cr-at-eol --exit-code -- docs/contracts/kairos-mcp.json mcp/contract/kairos-mcp.json` → sin diferencias
  - `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Los tres mensajes fijos pasan sin tocar por `kairos-mcp` con la forma `isError`; los dos ficheros del contrato MCP no cambian; una `tools/call` cuenta una vez
- [ ] En el cliente, los tres mensajes exactos y el 429 HTTP producen un `KairosError` con código y plazo acotado (también con plazos cero, negativos, enormes o no numéricos)
- [ ] Un error que contiene el patrón dentro de otro texto se trata como hoy (`mcp_tool_rejected`)

**Subtareas**
- [ ] Tests de `kairos-mcp` que fijan el texto
- [ ] Pruebas en rojo y reconocimiento por cadena entera en el cliente

### T-62 — Cola del cliente: un 429 es una espera y no un intento (CA-20)

- **Descripción**: `Dispatcher.tick` trata el error de límite aparte: devuelve `attempts` a su valor anterior, no suma `failures`, fija `next_attempt_at` con el plazo y detiene todos los envíos hasta entonces, porque el límite es de la clave y no de la captura. Una captura limitada nunca pasa a `failed`. Fuente: CA-20; DC-4; R-04.
- **Changelog**: Ante un 429, el cliente conserva la captura en su cola y reintenta tras el plazo, sin consumir intentos ni perderla.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-61
- **Tipo**: client
- **Archivos**: `client/lib/dispatcher.mjs`, `client/lib/outbox.mjs`, `client/tests/dispatcher.test.mjs`
- **Cubre (tests)**: —
- **Verificación**: `cd client && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Una captura limitada más de cinco veces seguidas no pasa a `failed` con `capture_retry_limit` y se entrega cuando el límite se levanta (reloj controlado)
- [ ] Durante el plazo no sale ningún envío; `status()` muestra el código y `capture_queue_stale` sigue avisando de la cola parada
- [ ] Un error que no es de límite consume intentos como hoy

**Subtareas**
- [ ] Pruebas en rojo
- [ ] Rama de límite en `tick`

### T-63 — Pruebas de extremo a extremo del 429: cuota agotada, cadena `kairos-mcp` y contratos (CA-20)

- **Descripción**: Cola del cliente con una cuota diaria agotada (plazo de horas) y con una tasa superada, a través de la cadena servidor → `kairos-mcp` en proceso (`chain_harness.py`); una sola fuente de los tres mensajes para las pruebas del servidor y del cliente; `test_contract_additive.py` para ambos contratos. Fuente: CA-20.
- **Changelog**: Interno: pruebas de extremo a extremo de los 429.
- **Estado**: borrador
- **Tiempo humano**: est. 4.5h · real —
- **Tiempo IA (ejec.)**: est. 0.46h · real —
- **Supervisión**: est. 0.12h · real —
- **Previsión IA**: 128 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-62
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_chain_limits.py`, `server/memory_platform/tests/chain_harness.py`, `client/tests/dispatcher.test.mjs`, `docs/contracts/examples/**`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_chain_limits|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `cd client && npm test` → `fail 0`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [ ] Con la cuota agotada, la captura sigue en la cola y se entrega al cambiar el día (reloj controlado), sin duplicados
- [ ] El mensaje que emite el servidor es, byte a byte, el que compara el cliente
- [ ] `test_contract_additive.py` pasa para ambos contratos

**Subtareas**
- [ ] Caso de cadena con cuota agotada
- [ ] Fuente única de los tres mensajes

### T-64 — Documentar los límites y avisar a la Iniciativa 7

- **Descripción**: `docs/configuration.md` (`MEMORY_RATE_LIMIT_*`, `MEMORY_WRITE_QUOTA_PER_DAY`, `MEMORY_STREAMS_*`, valores medidos y margen), `docs/operations.md` (cómo leer cada 429 y `admin set-key-limits`), `docs/integration.md` (qué hace un cliente ante cada código) y nota para la Iniciativa 7 en los CHANGELOG. Fuente: CA-16, CA-26; P-06.
- **Changelog**: Aviso para integraciones: los límites por clave están activos por defecto; un cliente debe respetar `Retry-After` ante `rate_limited`, `quota_exceeded` y `too_many_streams`.
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0.21h · real —
- **Supervisión**: est. 0.05h · real —
- **Previsión IA**: 57 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-63
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `docs/integration.md`, `CHANGELOG.md`, `CHANGELOG.es.md`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: variables y valores iguales a `config.py` y a «Valores medidos»; los tres mensajes fijos citados literalmente; nota a la Iniciativa 7 en ambos CHANGELOG

**Criterios de aceptación**
- [ ] Variables, valores por defecto y margen coinciden con `config.py` y con la medición de T-35
- [ ] La frase «Coordinación» del plan recoge los códigos, los mensajes fijos y los valores por defecto

**Subtareas**
- [ ] Manuales
- [ ] CHANGELOG y «Coordinación»

### T-65 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, cliente, `kairos-mcp`, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-64
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd client && npm test` → `fail 0`
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-66 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × la implementación. Superficie: texto capturado que imita un mensaje de límite, capturas perdidas o duplicadas, colas que no se reanudan y cambios accidentales del contrato MCP.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 16h · real —
- **Tiempo IA (ejec.)**: est. 1.64h · real —
- **Supervisión**: est. 0.41h · real —
- **Previsión IA**: 453 k in / 39 k out tok · ⚠️ verificar €
- **Dependencias**: T-65
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 12 — Cierre del hito B: clientes acotados y secretos fuera

**Estado**: borrador · **Hito**: B · **Estimado**: 9.6h (8h base) · **Real**: — · **Coste est.**: 480 € · **Tokens est.**: 873 k

### T-67 — Ensayo aislado del hito B: límites por clave, captura sin pérdida y secretos fuera

- **Descripción**: Etapa `b` de `scripts/rehearse-access-control.py` en `kairos-acc-b`: K1 recibe 429 mientras K2 sigue en 200; una captura limitada por una cuota agotada se entrega al levantarse el límite; las siete cadenas de S-01 no llegan a la base ni a los logs de los contenedores; el despliegue rechaza un directorio de secretos dentro del repo. Fuente: CA-17, CA-20, CA-23, CA-31.
- **Changelog**: Interno: ensayo aislado del hito B (límites, cola del cliente y redacción).
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0.21h · real —
- **Supervisión**: est. 0.05h · real —
- **Previsión IA**: 57 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-66
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-access-control.py`, `scripts/tests/test_rehearse_access_control.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_access_control.py` → `OK`
  - `python scripts/rehearse-access-control.py --project-name kairos-acc-b --embed-stub --stage b` → `limits_isolated`, `capture_kept_under_429`, `secrets_not_stored` y `secrets_dir_rejected`

**Criterios de aceptación**
- [ ] Las cuatro marcas quedan en `Notas`
- [ ] Un solo proyecto `kairos-acc-b`, retirado al acabar; nada `knowledge-graphs-*`
- [ ] El cliente del ensayo es el del árbol, con su cola en un directorio temporal

**Subtareas**
- [ ] Etapa `b` y su prueba con dobles
- [ ] Ejecutar en primer plano
- [ ] Retirar el proyecto

### T-68 — Revisión del diff completo del hito B

- **Descripción**: Lentes completas sobre el diff entero del hito (`git diff main...HEAD`; con el hito A ya fusionado, solo lo posterior a su fusión), no fase a fase: interacciones entre fases, alcance declarado, restricciones duras y deuda aceptada. Partida propia de ≥ 2 h IA. Cada fix se revisa como código nuevo. Fuente: retro de la Iniciativa 3; CA-35.
- **Changelog**: Interno: revisión del diff completo del hito B.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 2.50h · real —
- **Supervisión**: est. 0.62h · real —
- **Previsión IA**: 690 k in / 60 k out tok · ⚠️ verificar €
- **Dependencias**: T-67
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --stat main...HEAD` → rango y recuento de ficheros iguales a los que cita `review.md`
  - lectura: sección «Hito B — diff completo» de `review.md` sin Critical ni Important abiertos, con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Hito B — diff completo» con el rango revisado y cero Critical/Important abiertos
- [ ] Cada fix pasó por lentes completas y suma su intento medido; suites en verde tras las correcciones

**Subtareas**
- [ ] Lentes completas sobre el diff entero
- [ ] Corregir la clase entera y revisar cada fix

### T-69 — Comprobaciones de cierre y notas de cambio del hito B

- **Descripción**: Comprobar migraciones solo aditivas (la versión 13 no se reabre), diff aditivo de ambos contratos, `kairos-mcp.json` sin cambios, ningún ensayo ni prueba contra recursos `knowledge-graphs-*` y suites con 0 fallos y 0 omitidos. Escribir las entradas del hito en los dos CHANGELOG, bajo «Sin publicar», y repasar la frase «Coordinación» del plan: los tres 429 con sus mensajes fijos y valores por defecto, rechazos nuevos por redacción, `key_file_too_open`, `secrets_dir_unsafe` y el Compose sin `./secrets`, con la nota a la Iniciativa 7. Fuente: CA-10, CA-37.
- **Changelog**: Interno: comprobaciones de cierre y notas de cambio del hito B.
- **Estado**: borrador
- **Tiempo humano**: est. 1.5h · real —
- **Tiempo IA (ejec.)**: est. 0.15h · real —
- **Supervisión**: est. 0.04h · real —
- **Previsión IA**: 43 k in / 4 k out tok · ⚠️ verificar €
- **Dependencias**: T-68
- **Tipo**: test
- **Archivos**: `CHANGELOG.md`, `CHANGELOG.es.md`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `python scripts/export-contracts.py && git diff --ignore-cr-at-eol --exit-code -- docs/contracts/kairos-mcp.json mcp/contract/kairos-mcp.json` → sin diferencias
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `cd client && npm test` → `fail 0`
  - lectura: los dos CHANGELOG listan lo mismo y cada ítem del hito en «Coordinación» tiene su entrada

**Criterios de aceptación**
- [ ] `test_migrations_additive.py` y `test_contract_additive.py` pasan; mismas herramientas MCP
- [ ] CA-16 a CA-27 y CA-31 a CA-33 tienen evidencia en `Notas` de su tarea
- [ ] Mismas entradas en los dos idiomas; no cambia la versión ni se publica nada

**Subtareas**
- [ ] Comprobaciones, de una en una
- [ ] CHANGELOG y «Coordinación»

### T-70 — Pull request del hito B (solo con OK del usuario)

- **Descripción**: Abrir el PR del hito B desde `feat/access-control`, solo con el OK expreso del usuario; la tarea no se cierra hasta que el PR exista. Sin merges ni publicación. Fuente: evaluación (un PR por hito).
- **Changelog**: Interno: PR del hito B.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-69
- **Tipo**: devops
- **Archivos**: `docs/roadmap/2026-11-19-access-control/tasks.md`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view --json number,state,headRefName` → PR abierto desde `feat/access-control` (`state: OPEN`)

**Criterios de aceptación**
- [ ] OK expreso del usuario anotado en `Notas`
- [ ] El PR enlaza el ledger y lista los hallazgos S-01, S-08, S-10 y S-11 cerrados con su evidencia; CI en verde o equivalente local anotado

**Subtareas**
- [ ] Pedir el OK y abrir el PR
- [ ] Anotar el número en `Notas`

---

## Fase 13 — Capacidades del servidor y base del portal (C-05, C-08)

**Estado**: borrador · **Hito**: C · **Estimado**: 35.7h (29.75h base, de ellas 11.75h de revisión adversarial) · **Real**: — · **Coste est.**: 1.785 € · **Tokens est.**: 916 k

### T-71 — Arnés de Chromium: ejecutarlo tal cual y anotar su estado (R-06)

- **Descripción**: Primera tarea del portal: construir las etiquetas locales `kairos-web:native-test` y `kairos-test:native` y ejecutar `Dockerfile.e2e` sin cambios (su última evidencia es del 2026-11-06). Anotar los comandos exactos y el estado; reparar lo mínimo para volver a verde. Fuente: R-06; DC-9.
- **Changelog**: Interno: arnés de navegador real recuperado.
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0.21h · real —
- **Supervisión**: est. 0.05h · real —
- **Previsión IA**: 57 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: test
- **Archivos**: `server/memory_platform/Dockerfile.e2e`, `server/memory_platform/tests/e2e_portal.py`, `server/memory_platform/tests/e2e_fixture.py`, `server/memory_platform/tests/test_e2e_fixture.py`
- **Cubre (tests)**: E2E-01, E2E-02, E2E-03, E2E-04
- **Verificación**: `docker build -f server/memory_platform/Dockerfile.e2e --target checks --progress=plain .` → exit 0 con los casos existentes (Docker local)

**Criterios de aceptación**
- [ ] Los comandos de construcción de las dos etiquetas quedan en `Notas`; los reutilizan T-81 y T-90
- [ ] Los casos actuales pasan, o cada fallo queda explicado y reparado

**Subtareas**
- [ ] Construir las etiquetas
- [ ] Ejecutar tal cual y anotar el estado
- [ ] Reparar lo mínimo

### T-72 — `capabilities` en `/v1/auth/me` y su test acción → ruta (O2)

- **Descripción**: El resolvedor calcula `capabilities` y `/v1/auth/me` las publica: acciones de instancia (`users.list`, `users.manage`, `projects.create`, `account.password`, `account.sessions`) y, por proyecto, los permisos que la credencial puede delegar. Una tabla cerrada capacidad → rutas en la prueba comprueba que una capacidad ausente implica 403 y que toda ruta de administración figura bajo alguna capacidad. Sustituye al `is_admin` que presupuestó la evaluación (1,5 h); las otras 5 h son coste extra de O2. Fuente: CA-38 (b); design.md §O2 y §6; D-05, D-06.
- **Changelog**: `/v1/auth/me` publica `capabilities`: las acciones que la credencial puede ejecutar y los permisos que puede delegar por proyecto.
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h · real —
- **Tiempo IA (ejec.)**: est. 0.67h · real —
- **Supervisión**: est. 0.17h · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: backend
- **Archivos**: `server/memory_platform/store_access.py`, `server/memory_platform/store_auth.py`, `server/memory_platform/app.py`, `server/memory_platform/models.py`, `server/memory_platform/tests/test_capabilities.py`, `server/memory_platform/tests/test_auth_cache.py`, `docs/contracts/memory-platform.openapi.json`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_capabilities|test_auth_cache|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`

**Criterios de aceptación**
- [ ] Administrador global con sesión, administrador de proyecto, usuario sin administración y clave reciben cada uno sus capacidades; una clave nunca recibe `users.list` ni `users.manage`
- [ ] Capacidad ausente → 403 en cada una de sus rutas, para cada perfil; una ruta de acceso nueva sin capacidad deja el test en rojo
- [ ] Mutante: publicar una capacidad de más no abre la ruta; el cálculo vive en el resolvedor y el campo es aditivo en el OpenAPI

**Subtareas**
- [ ] Prueba en rojo y cálculo en el resolvedor
- [ ] Tabla capacidad → rutas, recorrido por perfil y mutante

### T-73 — Autorización de las rutas nuevas: 403 y CSRF por ruta, y delegación intacta (CA-42)

- **Descripción**: Tests de servidor: deshabilitar y rehabilitar, sustituir permisos, listar o cerrar sesiones ajenas y listar usuarios responden 403 a una sesión que no es de administrador global y a cualquier clave. Toda acción con sesión que cambia estado exige origen permitido y token CSRF. `POST /v1/users` conserva la delegación: `test_api_limits.py:147-149` sigue pasando sin tocarlo. Fuente: CA-42; decisión 6.
- **Changelog**: Interno: pruebas de autorización de las rutas de administración nuevas.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-72
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_access_authz.py`
- **Cubre (tests)**: E2E-04
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_access_authz|test_api_limits|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Matriz ruta × perfil (administrador global, administrador de proyecto, usuario y clave) con 403 donde corresponde
- [ ] Cada ruta que cambia estado con sesión falla sin CSRF o con un origen no permitido
- [ ] `test_api_limits.py` no se modifica

**Subtareas**
- [ ] Matriz de perfiles
- [ ] Casos de CSRF y origen

**Notas**: añadido con nota (fix1 de la revisión de la fase 3, gap 10, decisión del usuario 2026-11-26): la ruta `GET /v1/users/{id}/sessions` (listar sesiones ajenas, CA-42) ya existe. Es solo para el administrador global con sesión (403 a una clave y a un no administrador) y tiene sus pruebas en `test_access_sessions.py`. La matriz de esta tarea la incluye como una ruta más de administración.

### T-74 — DOM de frontera compartido entre los tests del portal (O2)

- **Descripción**: Sacar las clases `Element`, `Input` y `Select` y la API de fixture de `web/tests/memory-portal.test.mjs` a `web/tests/boundary-dom.mjs`, para que los tests de los módulos nuevos las compartan. Sin cambio de casos. Coste extra de O2. Fuente: design.md §O2 «Portal en módulos»; DC-9.
- **Changelog**: Interno: los tests del portal comparten un mismo DOM de pruebas.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: ninguna
- **Tipo**: frontend
- **Archivos**: `web/tests/boundary-dom.mjs`, `web/tests/memory-portal.test.mjs`, `web/tests/corpus-panel.test.mjs`
- **Cubre (tests)**: —
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Los 65 casos actuales del portal pasan sin cambiar ninguna aserción
- [ ] El DOM compartido cubre lo que necesitan los paneles nuevos: diálogo de confirmación, casillas por permiso y campos de contraseña

**Subtareas**
- [ ] Extraer el DOM y la API de fixture
- [ ] Suite del portal en verde

### T-75 — Portal: métodos de `memory-api.ts` y tipos de las rutas nuevas

- **Descripción**: Métodos de cliente para contraseña, usuarios (deshabilitar, permisos, sesiones), sesiones propias y claves (caducidad, rotación), y tipo `Actor` con `capabilities` y `key`. Solo operaciones presentes en `memory-platform.openapi.json`. Fuente: CA-43; P-02.
- **Changelog**: Interno: el cliente HTTP del portal conoce las rutas nuevas de acceso.
- **Estado**: borrador
- **Tiempo humano**: est. 2h · real —
- **Tiempo IA (ejec.)**: est. 0.21h · real —
- **Supervisión**: est. 0.05h · real —
- **Previsión IA**: 57 k in / 5 k out tok · ⚠️ verificar €
- **Dependencias**: T-72
- **Tipo**: frontend
- **Archivos**: `web/src/memory-api.ts`, `web/src/memory-types.ts`, `web/tests/memory-api.test.mjs`
- **Cubre (tests)**: E2E-01, E2E-02, E2E-03
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Cada método llama a su ruta `/v1` con el cuerpo y el CSRF esperados
- [ ] `npm run typecheck` sin errores

**Subtareas**
- [ ] Pruebas en rojo
- [ ] Métodos y tipos

### T-76 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, portal, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-75
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - `docker build -f web/Dockerfile.test .` → exit 0 (equivalente local de la CI del portal)

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-77 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × en la autorización y 0,5 × en el resto la implementación. Superficie: capacidades que no coinciden con lo que el servidor comprueba, rutas de administración accesibles con una clave o sin CSRF, y regresión de la delegación del alta.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 11.75h · real —
- **Tiempo IA (ejec.)**: est. 1.21h · real —
- **Supervisión**: est. 0.30h · real —
- **Previsión IA**: 333 k in / 29 k out tok · ⚠️ verificar €
- **Dependencias**: T-76
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 14 — Portal: «Mi cuenta» y «Claves para agentes» (C-08)

**Estado**: borrador · **Hito**: C · **Estimado**: 42.3h (35.25h base, de ellas 12.25h de revisión adversarial) · **Real**: — · **Coste est.**: 2.115 € · **Tokens est.**: 1086 k

### T-78 — «Mi cuenta»: vista `account`, cambio de contraseña y sesiones (CA-40)

- **Descripción**: Crear `web/src/account-panel.ts`, cargado como `corpus-panel.ts` (`memory-portal.ts:228`), con la vista `account` y su entrada junto a «Salir», visible para cualquier sesión con `account.password`; no vive en `settingsView`. Formulario de cambio de contraseña con los errores junto al campo y los campos vacíos tras enviar. Lista de sesiones propias (creación, caducidad, IP y cuál es la actual) y cierre de las demás con el diálogo de confirmación existente (`memory-portal.ts:693-696`). Fuente: CA-40, CA-05; DC-8; D-06.
- **Changelog**: El portal tiene una sección «Mi cuenta» para cambiar la contraseña y cerrar las demás sesiones.
- **Estado**: borrador
- **Tiempo humano**: est. 7h · real —
- **Tiempo IA (ejec.)**: est. 0.72h · real —
- **Supervisión**: est. 0.18h · real —
- **Previsión IA**: 198 k in / 17 k out tok · ⚠️ verificar €
- **Dependencias**: T-77
- **Tipo**: frontend
- **Archivos**: `web/src/account-panel.ts`, `web/src/memory-portal.ts`, `web/tests/account-panel.test.mjs`
- **Cubre (tests)**: E2E-02, M-01
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Cualquier sesión ve «Mi cuenta», también sin el permiso `admin` en ningún proyecto; el panel se pinta solo según `capabilities`
- [ ] Contraseña actual incorrecta y nueva demasiado corta se muestran junto a su campo; los campos de contraseña quedan vacíos tras enviar, con éxito o con error
- [ ] La lista de sesiones se actualiza sin recargar; cerrar pide confirmación y la sesión actual no se cierra desde ahí

**Subtareas**
- [ ] Pruebas de DOM en rojo
- [ ] Módulo, montaje, formulario y sesiones

### T-79 — «Claves para agentes» en `access-panel.ts`: caducidad, último uso y rotación (CA-41)

- **Descripción**: Crear `web/src/access-panel.ts` con la pestaña «Claves para agentes», que sale de `accessSettings` (`memory-portal.ts:641-670`): caducidad opcional al crear, columnas de caducidad («sin caducidad» o la fecha) y de último uso, y rotación con gracia. Revocar y rotar sin gracia piden confirmación. La clave nueva se muestra una sola vez. Fuente: CA-41; DC-8; design.md §O2.
- **Changelog**: La pestaña «Claves para agentes» permite crear claves con caducidad, ver su último uso y rotarlas.
- **Estado**: borrador
- **Tiempo humano**: est. 7h · real —
- **Tiempo IA (ejec.)**: est. 0.72h · real —
- **Supervisión**: est. 0.18h · real —
- **Previsión IA**: 198 k in / 17 k out tok · ⚠️ verificar €
- **Dependencias**: T-78
- **Tipo**: frontend
- **Archivos**: `web/src/access-panel.ts`, `web/src/memory-portal.ts`, `web/tests/access-panel.test.mjs`, `web/tests/memory-portal.test.mjs`
- **Cubre (tests)**: E2E-03, M-01
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] La lista muestra «sin caducidad» o la fecha, y el último uso
- [ ] La clave creada o rotada se muestra una sola vez y desaparece del DOM al cerrar el aviso
- [ ] Crear, listar y revocar claves se comportan como antes para quien ya los usaba

**Subtareas**
- [ ] Pruebas en rojo
- [ ] Mover la pestaña al módulo
- [ ] Caducidad, último uso y rotación

### T-80 — Tests de DOM de frontera de «Mi cuenta» y «Claves para agentes» (CA-40, CA-41)

- **Descripción**: Unos doce casos sobre el DOM compartido: controles por perfil, ruta y cuerpo de cada acción, errores junto al campo, campos vacíos tras enviar y lista actualizada. Fuente: CA-40, CA-41; DC-9.
- **Changelog**: Interno: pruebas de DOM de las secciones «Mi cuenta» y «Claves para agentes».
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-79
- **Tipo**: test
- **Archivos**: `web/tests/account-panel.test.mjs`, `web/tests/access-panel.test.mjs`, `web/tests/boundary-dom.mjs`
- **Cubre (tests)**: E2E-02, E2E-03
- **Verificación**:
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - `docker build -f web/Dockerfile.test .` → exit 0 (equivalente local de la CI del portal)

**Criterios de aceptación**
- [ ] CA-40 y CA-41 cubiertos en el nivel de DOM de frontera, con sus casos de error; equivalente local anotado si la CI no se ejecuta

**Subtareas**
- [ ] Casos por perfil
- [ ] Casos de error y de lista

### T-81 — Chromium real: siembra del fixture y flujos de «Mi cuenta» y «Claves» (CA-40, CA-41)

- **Descripción**: `e2e_fixture.py` siembra usuarios, permisos y claves para los cuatro flujos, y `test_e2e_fixture.py` lo comprueba en la CI. Flujos de Chromium contra API y base de fixture: cambio de contraseña con el 401 real de una segunda sesión, cierre de sesiones, creación con y sin caducidad y rotación. Solo Docker local; el resultado se anota en el ledger. Fuente: CA-40, CA-41; DC-9.
- **Changelog**: Interno: flujos de navegador real de «Mi cuenta» y «Claves para agentes».
- **Estado**: borrador
- **Tiempo humano**: est. 4.5h · real —
- **Tiempo IA (ejec.)**: est. 0.46h · real —
- **Supervisión**: est. 0.12h · real —
- **Previsión IA**: 128 k in / 11 k out tok · ⚠️ verificar €
- **Dependencias**: T-80
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/e2e_portal.py`, `server/memory_platform/tests/e2e_fixture.py`, `server/memory_platform/tests/test_e2e_fixture.py`, `server/memory_platform/Dockerfile.e2e`
- **Cubre (tests)**: E2E-02, E2E-03
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile.e2e --target checks --progress=plain .` → exit 0 con los flujos nuevos (Docker local; etiquetas según T-71)
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_e2e_fixture|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Los dos flujos pasan en Chromium con sesión y CSRF reales
- [ ] `test_e2e_fixture.py` pasa en la suite del servidor
- [ ] La salida queda en `Notas`

**Subtareas**
- [ ] Sembrar el fixture
- [ ] Flujo de CA-40
- [ ] Flujo de CA-41

### T-82 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, portal.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-81
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - `docker build -f web/Dockerfile.test .` → exit 0 (equivalente local de la CI del portal)

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-83 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × en la entrada de «Mi cuenta» y 0,5 × en el resto la implementación. Superficie: secretos que permanecen en el DOM (contraseñas, clave recién emitida), acciones sin confirmación y controles que el portal decide por su cuenta.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 12.25h · real —
- **Tiempo IA (ejec.)**: est. 1.26h · real —
- **Supervisión**: est. 0.31h · real —
- **Previsión IA**: 347 k in / 30 k out tok · ⚠️ verificar €
- **Dependencias**: T-82
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 15 — Portal: «Usuarios», alta delegada y paridad (C-08)

**Estado**: borrador · **Hito**: C · **Estimado**: 54.6h (45.5h base, de ellas 17.5h de revisión adversarial) · **Real**: — · **Coste est.**: 2.730 € · **Tokens est.**: 1401 k

### T-84 — «Usuarios»: deshabilitar, rehabilitar y cerrar sesiones (CA-39)

- **Descripción**: Pestaña «Usuarios» en `access-panel.ts` para quien tiene `users.manage`: estado de cada usuario, deshabilitar y rehabilitar, y cerrar todas sus sesiones, con confirmación antes de deshabilitar o cerrar. La lista refleja cada acción sin recargar. Fuente: CA-39; DC-8.
- **Changelog**: La pestaña «Usuarios» permite deshabilitar y rehabilitar usuarios y cerrar sus sesiones.
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0.51h · real —
- **Supervisión**: est. 0.13h · real —
- **Previsión IA**: 142 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-83
- **Tipo**: frontend
- **Archivos**: `web/src/access-panel.ts`, `web/src/memory-portal.ts`, `web/tests/access-panel.test.mjs`
- **Cubre (tests)**: E2E-01, M-01
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Cada acción se refleja en la lista sin recargar y pide confirmación antes de deshabilitar o cerrar sesiones
- [ ] No se ofrece deshabilitarse a uno mismo; el 409 del servidor se muestra como un error legible

**Subtareas**
- [ ] Pruebas en rojo (oráculo de A-08)
- [ ] Lista con estado
- [ ] Acciones con confirmación

### T-85 — «Usuarios»: editor de permisos por proyecto (CA-39)

- **Descripción**: Editor que muestra los permisos por proyecto de un usuario y los sustituye con `PUT /v1/users/{id}/grants`. Ofrece solo proyectos y permisos existentes y muestra el resultado sin recargar. Fuente: CA-39, CA-04.
- **Changelog**: Un administrador edita desde el portal los permisos por proyecto de cada usuario.
- **Estado**: borrador
- **Tiempo humano**: est. 5.5h · real —
- **Tiempo IA (ejec.)**: est. 0.56h · real —
- **Supervisión**: est. 0.14h · real —
- **Previsión IA**: 156 k in / 14 k out tok · ⚠️ verificar €
- **Dependencias**: T-84
- **Tipo**: frontend
- **Archivos**: `web/src/access-panel.ts`, `web/tests/access-panel.test.mjs`
- **Cubre (tests)**: E2E-01, M-01
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] El cuerpo enviado es la sustitución completa, no un parche parcial
- [ ] Cancelar no cambia nada; un 422 se muestra junto al editor

**Subtareas**
- [ ] Pruebas en rojo
- [ ] Editor por proyecto
- [ ] Envío y refresco

### T-86 — Alta delegada según `capabilities` y `memory-portal.ts` como mero montaje (CA-42)

- **Descripción**: El administrador de proyecto ve «Usuarios» solo con el panel «Crear usuario», que ofrece los proyectos y permisos que puede delegar, tomados de `capabilities`. Tras el alta ve una confirmación y la lista de las altas de esa visita, en memoria (DC-8). `memory-portal.ts` solo monta los dos módulos y deja de decidir con `scopes.includes('admin')`. `GET /v1/users` no cambia. Fuente: CA-42; CA-38 (b); DC-8; D-05.
- **Changelog**: Un administrador de proyecto da de alta personas para sus proyectos desde el portal; el resto de la administración solo la ve el administrador general.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-85
- **Tipo**: frontend
- **Archivos**: `web/src/access-panel.ts`, `web/src/memory-portal.ts`, `web/tests/access-panel.test.mjs`, `web/tests/memory-portal.test.mjs`
- **Cubre (tests)**: E2E-04
- **Verificación**: `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] El administrador de proyecto ve el alta y ningún control de administración nuevo; un usuario sin `admin` en ningún proyecto no ve ningún control de administración
- [ ] `memory-portal.ts` no decide por `scopes` ni por `is_admin` (búsqueda en el test)
- [ ] La lista de altas de la visita se pierde al recargar y no llama a `GET /v1/users`

**Subtareas**
- [ ] Pruebas en rojo por perfil
- [ ] Panel de alta delegada
- [ ] Retirar las decisiones por `scopes`

### T-87 — Tests de DOM de frontera de «Usuarios»: perfiles × controles (CA-39, CA-42)

- **Descripción**: Unos trece casos: qué controles ve cada perfil (administrador global, administrador de proyecto y usuario sin administración), cada acción llama a su ruta con su cuerpo, confirmaciones y lista actualizada. Fuente: CA-39, CA-42; DC-9.
- **Changelog**: Interno: pruebas de DOM de la pestaña «Usuarios» por perfil.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-86
- **Tipo**: test
- **Archivos**: `web/tests/access-panel.test.mjs`, `web/tests/memory-portal.test.mjs`, `web/tests/boundary-dom.mjs`
- **Cubre (tests)**: E2E-01, E2E-04
- **Verificación**:
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - `docker build -f web/Dockerfile.test .` → exit 0 (equivalente local de la CI del portal)

**Criterios de aceptación**
- [ ] CA-39 y CA-42 cubiertos en el nivel de DOM de frontera, con los tres perfiles; equivalente local anotado si la CI no se ejecuta

**Subtareas**
- [ ] Matriz de perfiles
- [ ] Casos de acción y confirmación

### T-88 — Tabla de paridad portal ↔ `/v1` ↔ `admin` y su test (CA-43)

- **Descripción**: Crear `docs/identity.md` con la tabla de paridad: cada acción del portal con su operación de `/v1`, su capacidad y, donde exista, su comando `admin`, más la excepción declarada de `admin set-key-limits`. Un test, en el host, comprueba que el portal solo llama a operaciones presentes en `memory-platform.openapi.json` y que ninguna acción de la tabla carece de operación. Fuente: CA-43; P-02.
- **Changelog**: La guía de identidad incluye la tabla de equivalencias entre cada acción del portal, su operación de `/v1` y su comando `admin`.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-87
- **Tipo**: test
- **Archivos**: `docs/identity.md`, `docs/index.md`, `scripts/tests/test_portal_parity.py`, `.github/workflows/ci.yml`
- **Cubre (tests)**: —
- **Verificación**: `python -m unittest discover -s scripts/tests -p test_portal_parity.py` → `OK`

**Criterios de aceptación**
- [ ] Toda llamada del portal a `/v1` corresponde a una operación del OpenAPI
- [ ] Quitar una ruta del OpenAPI o añadir una llamada sin operación deja el test en rojo
- [ ] La tabla lleva la columna de capacidad y la excepción de `admin set-key-limits`

**Subtareas**
- [ ] Tabla de paridad
- [ ] Test en `scripts/tests/` (lee `web/src/` y `docs/contracts/`)
- [ ] Paso de CI con su equivalente local

**Notas**: El test vive en `scripts/tests/` porque las imágenes de test del portal y del servidor no contienen a la vez `web/src/` y `docs/contracts/`.

### T-89 — Estilos, accesibilidad y manual de las tres secciones del portal

- **Descripción**: Estilos de «Mi cuenta», «Claves para agentes» y «Usuarios» con los patrones existentes; accesibilidad básica (etiquetas asociadas, foco visible, errores con `aria-describedby` y diálogo de confirmación navegable con teclado) y la sección del portal en `docs/manual.md`. Fuente: CA-39, CA-40, CA-41; CA-37.
- **Changelog**: El manual describe las secciones «Mi cuenta», «Usuarios» y «Claves para agentes» del portal, que se usan también con teclado.
- **Estado**: borrador
- **Tiempo humano**: est. 3.5h · real —
- **Tiempo IA (ejec.)**: est. 0.36h · real —
- **Supervisión**: est. 0.09h · real —
- **Previsión IA**: 99 k in / 9 k out tok · ⚠️ verificar €
- **Dependencias**: T-88
- **Tipo**: frontend
- **Archivos**: `web/src/memory-portal.css`, `web/src/access-panel.ts`, `web/src/account-panel.ts`, `docs/manual.md`
- **Cubre (tests)**: M-01
- **Verificación**:
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - lectura: `docs/manual.md` describe las tres secciones con los nombres de control reales y quién ve cada una

**Criterios de aceptación**
- [ ] Cada campo tiene etiqueta y cada error se asocia a su campo; las tres secciones se recorren solo con teclado
- [ ] `docs/manual.md` describe las tres secciones y quién ve cada una

**Subtareas**
- [ ] Estilos y etiquetas
- [ ] Manual

### T-90 — Chromium real: flujos de «Usuarios» y de la delegación (CA-39, CA-42)

- **Descripción**: Flujos de Chromium. Como administrador global: alta, cambio de permisos, deshabilitar (con el 401 real de la sesión del usuario afectado), rehabilitar y cerrar sesiones. Como administrador de proyecto: alta delegada sin ver los controles nuevos y 403 al llamar a sus rutas a mano. Solo Docker local. Fuente: CA-39, CA-42; DC-9.
- **Changelog**: Interno: flujos de navegador real de «Usuarios» y de la delegación del alta.
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h · real —
- **Tiempo IA (ejec.)**: est. 0.26h · real —
- **Supervisión**: est. 0.06h · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-89
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/e2e_portal.py`, `server/memory_platform/tests/e2e_fixture.py`
- **Cubre (tests)**: E2E-01, E2E-04
- **Verificación**: `docker build -f server/memory_platform/Dockerfile.e2e --target checks --progress=plain .` → exit 0 con los flujos nuevos (Docker local; etiquetas según T-71)

**Criterios de aceptación**
- [ ] Los dos flujos pasan en Chromium con sesión y CSRF reales; la salida queda en `Notas`

**Subtareas**
- [ ] Flujo de CA-39
- [ ] Flujo de CA-42

### T-91 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, portal, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-90
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - `docker build -f web/Dockerfile.test .` → exit 0 (equivalente local de la CI del portal)

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-92 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 1,0 × en la delegación y la paridad y 0,5 × en el resto la implementación. Superficie: controles de administración visibles o accionables por quien no debe, decisiones de permiso en el portal, inyección de HTML con nombres de usuario o de clave y llamadas a rutas fuera del OpenAPI.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 17.5h · real —
- **Tiempo IA (ejec.)**: est. 1.80h · real —
- **Supervisión**: est. 0.45h · real —
- **Previsión IA**: 496 k in / 43 k out tok · ⚠️ verificar €
- **Dependencias**: T-91
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 16 — Identidad: guía probada y extensibilidad (C-05)

**Estado**: borrador · **Hito**: C · **Estimado**: 23.4h (19.5h base, de ellas 6.5h de revisión adversarial) · **Real**: — · **Coste est.**: 1.170 € · **Tokens est.**: 601 k

### T-93 — Guía de identidad: modelo y ocho procedimientos de alta y baja (CA-28)

- **Descripción**: Completar `docs/identity.md` con el modelo (un usuario por persona, una clave por máquina y otra por integración, permisos mínimos por proyecto) y pasos ejecutables, por el portal y por API o comando, para: alta de persona, de máquina y de integración, rotación, baja de máquina, baja de persona, portátil perdido y recuperación del administrador. Fuente: CA-28; A-05.
- **Changelog**: Nueva guía de identidad: cómo dar de alta y de baja personas, máquinas e integraciones, por el portal, por API o por comando.
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0.51h · real —
- **Supervisión**: est. 0.13h · real —
- **Previsión IA**: 142 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-92
- **Tipo**: docs
- **Archivos**: `docs/identity.md`, `docs/index.md`, `docs/RAG-INDEX.md`, `docs/integration.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: ocho procedimientos, cada uno con su vía de portal y su vía de API o comando, y comandos que existen con esas opciones

**Criterios de aceptación**
- [ ] Los ocho procedimientos tienen pasos copiables por las dos vías
- [ ] Cada paso de portal cita un control real y cada comando, una opción real

**Subtareas**
- [ ] Redactar el modelo
- [ ] Redactar los ocho procedimientos
- [ ] Enlazar desde el índice

### T-94 — Test que sigue la guía de principio a fin y compatibilidad de claves (CA-29, CA-30)

- **Descripción**: Sobre un servidor de pruebas recién inicializado, un test ejecuta los pasos de la guía: usuario, clave de máquina sobre un proyecto y clave de integración con `read`, `publish` y `validate`. Cada clave hace lo suyo, ninguna alcanza otro proyecto (404) ni ejerce un permiso que no tiene (403), y tras las bajas todas reciben 401. La clave de integración supera la comprobación `health` de custom-agents (`projects` y `capture_policy`) y una clave emitida en 0.4.1 sigue valiendo. Fuente: CA-29, CA-30.
- **Changelog**: Interno: una prueba ejecuta la guía de identidad de principio a fin.
- **Estado**: borrador
- **Tiempo humano**: est. 5h · real —
- **Tiempo IA (ejec.)**: est. 0.51h · real —
- **Supervisión**: est. 0.13h · real —
- **Previsión IA**: 142 k in / 12 k out tok · ⚠️ verificar €
- **Dependencias**: T-93
- **Tipo**: test
- **Archivos**: `server/memory_platform/tests/test_identity_guide.py`, `server/memory_platform/tests/test_migrations_additive.py`, `docs/identity.md`, `server/memory_platform/Dockerfile`
- **Cubre (tests)**: —
- **Verificación**: `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_identity_guide|test_migrations_additive|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos

**Criterios de aceptación**
- [ ] Cada clave hace lo suyo; 404 fuera de su proyecto, 403 sin el permiso y 401 tras las bajas
- [ ] Cambiar un comando de la guía sin cambiar el test, o al revés, lo deja en rojo
- [ ] La clave de integración obtiene `projects` y `capture_policy`; una clave de 0.4.1 autentica igual tras la migración 13

**Subtareas**
- [ ] Prueba en rojo (oráculo de A-05) y cotejo guía ↔ test
- [ ] Casos de `health` y de clave anterior

### T-95 — Nota de extensibilidad en `docs/architecture.md` (CA-38 c)

- **Descripción**: Nota de diseño a partir de DC-1: cómo se añadirían roles o grupos, inicio de sesión único y operaciones en bloque solo con tablas o columnas nuevas, sin cambiar el significado de las actuales, y qué cambia en el resolvedor y en `capabilities`. Describe además las tres costuras de O2 (`store_access.py`, `capabilities` y `limits.py`) y la hipótesis de una sola réplica. Fuente: CA-38 (c); P-01; DC-1.
- **Changelog**: `docs/architecture.md` explica el modelo de acceso y cómo ampliarlo con roles, grupos o inicio de sesión único sin romper lo existente.
- **Estado**: borrador
- **Tiempo humano**: est. 2.5h · real —
- **Tiempo IA (ejec.)**: est. 0.26h · real —
- **Supervisión**: est. 0.06h · real —
- **Previsión IA**: 71 k in / 6 k out tok · ⚠️ verificar €
- **Dependencias**: T-94
- **Tipo**: docs
- **Archivos**: `docs/architecture.md`
- **Cubre (tests)**: —
- **Verificación**: lectura: tres ampliaciones, cada una con sus tablas nuevas y lo que cambia en el código; ninguna cambia el significado de una columna actual

**Criterios de aceptación**
- [ ] Las tres ampliaciones quedan descritas solo con tablas o columnas nuevas
- [ ] La nota cita ficheros y funciones reales del resolvedor

**Subtareas**
- [ ] Redactar la nota
- [ ] Cotejar con el código

### T-96 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-95
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

### T-97 — Revisión adversarial de la fase (dos lentes)

- **Descripción**: Protocolo de revisión adversarial (cabecera), a 0,5 × la implementación. Superficie: pasos de la guía que no funcionan o conceden más permisos que los mínimos, y comandos que imprimen secretos.
- **Changelog**: Interno: revisión adversarial de la fase.
- **Estado**: borrador
- **Tiempo humano**: est. 6.5h · real —
- **Tiempo IA (ejec.)**: est. 0.67h · real —
- **Supervisión**: est. 0.17h · real —
- **Previsión IA**: 184 k in / 16 k out tok · ⚠️ verificar €
- **Dependencias**: T-96
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: `review.md` de la fase sin Critical ni Important abiertos y con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Sin Critical ni Important abiertos; cada control nuevo con su mutante comprobado y cada fix con su revisión completa

**Subtareas**
- [ ] Lentes A y B; corregir y repetir hasta cero abiertos

---

## Fase 17 — Revisión del hito C y revisión de seguridad (C-07)

**Estado**: borrador · **Hito**: C · **Estimado**: 27.0h (22.5h base) · **Real**: — · **Coste est.**: 1.350 € · **Tokens est.**: 1320 k

### T-98 — Revisión del diff completo del hito C

- **Descripción**: Lentes completas sobre el diff entero del hito (`git diff main...HEAD`; con los hitos A y B ya fusionados, solo lo posterior a la fusión del B), no fase a fase: interacciones entre fases, alcance declarado, restricciones duras y deuda aceptada. Partida propia de ≥ 2 h IA. Cada fix se revisa como código nuevo. Fuente: retro de la Iniciativa 3; CA-35.
- **Changelog**: Interno: revisión del diff completo del hito C.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 2.50h · real —
- **Supervisión**: est. 0.62h · real —
- **Previsión IA**: 690 k in / 60 k out tok · ⚠️ verificar €
- **Dependencias**: T-97
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --stat main...HEAD` → rango y recuento de ficheros iguales a los que cita `review.md`
  - lectura: sección «Hito C — diff completo» de `review.md` sin Critical ni Important abiertos, con una fila por intento
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente

**Criterios de aceptación**
- [ ] `review.md` tiene la sección «Hito C — diff completo» con el rango revisado y cero Critical/Important abiertos
- [ ] Cada fix pasó por lentes completas y suma su intento medido; suites en verde tras las correcciones

**Subtareas**
- [ ] Lentes completas sobre el diff entero
- [ ] Corregir la clase entera y revisar cada fix

### T-99 — Revisión de seguridad independiente del diff completo y de la superficie de acceso (CA-34)

- **Descripción**: La hace el agente `reviewer` con contexto fresco, distinto del implementador, con las lentes completas y foco de seguridad, sobre el diff de toda la iniciativa (los tres hitos, desde `c858fa5`) y la superficie de acceso: autenticación, sesiones, claves, límites, redacción y secretos. Severidades A/M/B de la auditoría. Valida la nota de CA-38 (c). Se usan las lentes y no `nemesis`: CA-34 pide `review.md` en la iniciativa y revisión sobre el diff, y el DAST de `nemesis` apunta a entornos locales, donde también vive la instalación desplegada. Fuente: CA-34; criterio de cierre 1 del plan director.
- **Changelog**: Interno: revisión de seguridad independiente de toda la iniciativa.
- **Estado**: borrador
- **Tiempo humano**: est. 8h · real —
- **Tiempo IA (ejec.)**: est. 0.82h · real —
- **Supervisión**: est. 0.21h · real —
- **Previsión IA**: 227 k in / 20 k out tok · ⚠️ verificar €
- **Dependencias**: T-98
- **Tipo**: review
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `git diff --stat c858fa5...HEAD` → el rango y el recuento de ficheros coinciden con los que cita `review.md`
  - lectura: sección «Revisión de seguridad» de `review.md` con una fila por hallazgo (A/M/B), cero altos abiertos y decisión en cada medio

**Criterios de aceptación**
- [ ] Cero hallazgos de severidad alta abiertos; cada hallazgo medio tiene decisión registrada
- [ ] La revisión cubre las seis áreas de la superficie y los siete hallazgos de la auditoría en alcance, con `fichero:línea`
- [ ] El revisor no es el implementador y su medición de `usage-meter` consta

**Subtareas**
- [ ] Despachar la revisión con contexto fresco
- [ ] Registrar hallazgos con severidad y evidencia
- [ ] Validar la nota de extensibilidad

### T-100 — Fixes de la revisión de seguridad, revisados como código nuevo (CA-35)

- **Descripción**: Corregir cada hallazgo para la clase entera, con su prueba en rojo antes. Cada fix pasa por las mismas lentes que una fase y queda anotado en el ledger con su intento. Las 6 h son un supuesto (R-09). Fuente: CA-35; retro de la Iniciativa 3, aprendizaje 1.
- **Changelog**: Correcciones de la revisión de seguridad.
- **Estado**: borrador
- **Tiempo humano**: est. 6h · real —
- **Tiempo IA (ejec.)**: est. 0.62h · real —
- **Supervisión**: est. 0.15h · real —
- **Previsión IA**: 170 k in / 15 k out tok · ⚠️ verificar €
- **Dependencias**: T-99
- **Tipo**: backend
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`, `docs/roadmap/2026-11-19-access-control/tasks.md` (los ficheros de cada fix se añaden aquí al conocerse)
- **Cubre (tests)**: —
- **Verificación**:
  - lectura: cada fix tiene en `review.md` su fila de revisión con lentes completas
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0

**Criterios de aceptación**
- [ ] Cada fix tiene una prueba que falla sin él y su revisión con lentes completas anotada
- [ ] Ningún alto abierto; los medios, corregidos o con decisión
- [ ] El campo `Archivos` de esta tarea lista lo tocado

**Subtareas**
- [ ] Prueba en rojo por hallazgo
- [ ] Corregir la clase entera
- [ ] Revisar cada fix como código nuevo

### T-101 — Matriz hallazgo → test que falla si se retira su control (CA-36)

- **Descripción**: Para S-01, S-02, S-03, S-07, S-08, S-10 y S-11: al menos un test por hallazgo que falla al retirar su control, comprobado con un mutante. La matriz queda en `review.md`. Fuente: CA-36.
- **Changelog**: Interno: matriz hallazgo → prueba.
- **Estado**: borrador
- **Tiempo humano**: est. 4h · real —
- **Tiempo IA (ejec.)**: est. 0.41h · real —
- **Supervisión**: est. 0.10h · real —
- **Previsión IA**: 113 k in / 10 k out tok · ⚠️ verificar €
- **Dependencias**: T-100
- **Tipo**: test
- **Archivos**: `docs/roadmap/2026-11-19-access-control/review.md`, `server/memory_platform/tests/test_review_regressions.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_review_regressions|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - lectura: matriz de siete filas en `review.md` con test, `fichero:línea` del control y evidencia del mutante

**Criterios de aceptación**
- [ ] Siete hallazgos, cada uno con su test y la evidencia del mutante (control retirado → rojo)
- [ ] La matriz cita el test y el `fichero:línea` del control

**Subtareas**
- [ ] Mutante por hallazgo
- [ ] Escribir la matriz

### T-102 — Cierre de fase: suites y subida del mínimo

- **Descripción**: Protocolo de cierre de fase (cabecera) con las suites: servidor, cliente, portal, `kairos-mcp`, contratos.
- **Changelog**: Interno: cierre de fase.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-101
- **Tipo**: test
- **Archivos**: `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py`, `docs/operations.md`, `README.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `python -m unittest discover -s scripts/tests -p test_ci_workflow.py` → `OK`
  - `cd client && npm test` → `fail 0`
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `cd web && npm run typecheck && npm test` → `fail 0`
  - `docker build -f web/Dockerfile.test .` → exit 0 (equivalente local de la CI del portal)

**Criterios de aceptación**
- [ ] Suites con 0 fallos y 0 omitidos; el mínimo iguala el recuento observado en los cuatro sitios y el equivalente local queda anotado

**Subtareas**
- [ ] Suites, mínimo y archivo de las notas de la fase

---

## Fase 18 — Cierre del hito C y de la iniciativa: ensayo, versión 0.4.2 y PR

**Estado**: borrador · **Hito**: C · **Estimado**: 11.4h (9.5h base) · **Real**: — · **Coste est.**: 570 € · **Tokens est.**: 293 k

### T-103 — Ensayo aislado de cierre: los tres criterios del plan director

- **Descripción**: Etapa `all` de `scripts/rehearse-access-control.py` en un proyecto Compose desechable `kairos-acc-c`, con el portal incluido: (1) una clave revocada deja de funcionar en `/v1`, en los dos `/mcp` y en el portal; (2) diez fallos de login de un cliente no bloquean a otro; (3) la revisión de seguridad no tiene hallazgos altos abiertos (lectura de `review.md`). Fuente: CA-11, CA-13, CA-34; criterios de cierre 1, 2 y 3 del plan director.
- **Changelog**: Interno: ensayo aislado de cierre de la iniciativa.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-102
- **Tipo**: devops
- **Archivos**: `scripts/rehearse-access-control.py`, `scripts/tests/test_rehearse_access_control.py`
- **Cubre (tests)**: —
- **Verificación**:
  - `python -m unittest discover -s scripts/tests -p test_rehearse_access_control.py` → `OK`
  - `python scripts/rehearse-access-control.py --project-name kairos-acc-c --embed-stub --stage all` → `revoked_everywhere`, `login_not_blocked_across_clients` y las cuatro marcas de la etapa `b`
  - lectura: `review.md` sin hallazgos de severidad alta abiertos

**Criterios de aceptación**
- [ ] Los tres criterios del plan director tienen su evidencia en `Notas`
- [ ] La revocación se comprueba también con la sesión del portal del ensayo
- [ ] Proyecto retirado al acabar (`docker ps -a --filter name=kairos-acc` vacío); nada `knowledge-graphs-*`

**Subtareas**
- [ ] Etapa `all` con el portal
- [ ] Ejecutar en primer plano
- [ ] Retirar el proyecto

### T-104 — Versión 0.4.2 de servidor, MCP y cliente y CHANGELOG

- **Descripción**: Subir a 0.4.2 `server/VERSION`, `mcp/VERSION`, `client/package.json` y `VERSION` de `client/lib/config.mjs` (con `COMPATIBLE_VERSIONS`), y cerrar la sección `[0.4.2]` en `CHANGELOG.md` y `CHANGELOG.es.md` con los tres hitos y las notas para la Iniciativa 7. La 0.5.0 sigue reservada. Nada se publica. Fuente: P-10; CA-37.
- **Changelog**: Versión 0.4.2 de servidor, MCP y cliente.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-103
- **Tipo**: docs
- **Archivos**: `server/VERSION`, `mcp/VERSION`, `client/package.json`, `client/lib/config.mjs`, `server/memory_platform/tests/test_versions.py`, `mcp/tests/test_health.py`, `CHANGELOG.md`, `CHANGELOG.es.md`, `README.md`, `client/README.md`, `mcp/README.md`, `docs/install.md`, `docs/release-cli.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep -E "test_versions|MEMORY_TEST_RESULT"` → nombradas en `ok`; 0 fallos y 0 omitidos
  - `cd client && npm test` → `fail 0`
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`

**Criterios de aceptación**
- [ ] Los cuatro sitios dicen 0.4.2 y `test_versions.py` lo exige
- [ ] Ambos CHANGELOG cierran `[0.4.2]` con los tres hitos y la nota a la Iniciativa 7
- [ ] Sin `npm publish` ni `docker push`

**Subtareas**
- [ ] Prueba de versión en rojo
- [ ] Subir versiones
- [ ] Cerrar la sección de los CHANGELOG

### T-105 — Comprobaciones finales (CA-37), manuales y estado del ledger

- **Descripción**: Migraciones solo aditivas; diff aditivo de `memory-platform.openapi.json` y `kairos-mcp.json` frente a su base, con las mismas herramientas MCP; ninguna prueba contra recursos `knowledge-graphs-*`; nada publicado; suites de servidor, MCP, cliente y portal con 0 fallos y 0 omitidos; manuales al día. Repasar los 43 CA contra sus evidencias; la spec pasa a `implementada`, el plan y el ledger a `completado` y el índice se actualiza. Fuente: CA-37; todos los CA.
- **Changelog**: Los manuales de configuración, operación y arquitectura reflejan el control de acceso y la privacidad de la 0.4.2.
- **Estado**: borrador
- **Tiempo humano**: est. 3h · real —
- **Tiempo IA (ejec.)**: est. 0.31h · real —
- **Supervisión**: est. 0.08h · real —
- **Previsión IA**: 85 k in / 7 k out tok · ⚠️ verificar €
- **Dependencias**: T-104
- **Tipo**: docs
- **Archivos**: `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md`, `docs/roadmap/README.md`, `docs/roadmap/2026-11-19-access-control/spec.md`, `docs/roadmap/2026-11-19-access-control/evaluation.md`, `docs/roadmap/2026-11-19-access-control/design.md`, `docs/roadmap/2026-11-19-access-control/improvement-plan.md`, `docs/roadmap/2026-11-19-access-control/tasks.md`, `docs/roadmap/2026-11-19-access-control/test-plan.md`
- **Cubre (tests)**: —
- **Verificación**:
  - `python3 "$SHAREDKIT/ledger-lint.py" docs/roadmap/2026-11-19-access-control/tasks.md` → exit 0
  - `python3 "$SHAREDKIT/scope-check.py" docs/roadmap/2026-11-19-access-control` → exit 0
  - `docker build -f server/memory_platform/Dockerfile --target test --progress=plain . 2>&1 | grep MEMORY_TEST_RESULT` → 0 fallos, errores y omitidos; `tests` ≥ mínimo vigente
  - `PYTHONPATH=server python -m unittest memory_platform.tests.test_contract_additive` → `OK`
  - `python scripts/export-contracts.py && git diff --ignore-cr-at-eol --exit-code -- docs/contracts/kairos-mcp.json mcp/contract/kairos-mcp.json` → sin diferencias
  - `docker build -f mcp/Dockerfile -t kairos-mcp:acc mcp/ && docker run --rm kairos-mcp:acc python -m unittest discover -s tests` → `OK`
  - `cd client && npm test` → `fail 0`
  - `cd web && npm run typecheck && npm test` → `fail 0`

**Criterios de aceptación**
- [ ] Los 43 CA tienen evidencia en `Notas` de su tarea; los verificados solo en local lo dicen
- [ ] `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md` y los CHANGELOG reflejan lo implementado
- [ ] La spec pasa a `implementada` y el índice del roadmap refleja el cierre

**Subtareas**
- [ ] Repasar los 43 CA
- [ ] Actualizar manuales, spec e índice
- [ ] Ejecutar las comprobaciones finales

### T-106 — Pull request del hito C (solo con OK del usuario)

- **Descripción**: Abrir el PR del hito C desde `feat/access-control`, solo con el OK expreso del usuario; la tarea no se cierra hasta que el PR exista. Sin merges ni publicación. Fuente: evaluación (un PR por hito).
- **Changelog**: Interno: PR del hito C.
- **Estado**: borrador
- **Tiempo humano**: est. 0.5h · real —
- **Tiempo IA (ejec.)**: est. 0.05h · real —
- **Supervisión**: est. 0.01h · real —
- **Previsión IA**: 14 k in / 1 k out tok · ⚠️ verificar €
- **Dependencias**: T-105
- **Tipo**: devops
- **Archivos**: `docs/roadmap/2026-11-19-access-control/tasks.md`
- **Cubre (tests)**: —
- **Verificación**: `gh pr view --json number,state,headRefName` → PR abierto desde `feat/access-control` (`state: OPEN`)

**Criterios de aceptación**
- [ ] OK expreso del usuario anotado en `Notas`
- [ ] El PR enlaza el ledger y lista el criterio de cierre 1 del plan director y el ensayo de cierre con su evidencia; CI en verde o equivalente local anotado

**Subtareas**
- [ ] Pedir el OK y abrir el PR
- [ ] Anotar el número en `Notas`


## Historial archivado

- 2026-11-20 · «Revisión de dos lentes — intento 1: Fase 1 (T-01, T-02, T-03, T-04) — 3 Important en la guarda del resolvedor» → [execution-history.md](execution-history.md) · SHA-256 `a37dcddb59e0706358e4e4c6b171b2272f20ca701253d5c5469f475d42b90d34`
- 2026-11-20 · «Revisión de dos lentes — intento 2: Fase 1 (fix1) (T-01, T-02, T-03, T-04) — 2 Important en la guarda» → [execution-history.md](execution-history.md) · SHA-256 `8afb08dbc55ca7728102849e7bda1edd9c163d9fd702c905a634e0d1c78522c9`
- 2026-11-20 · «Revisión de dos lentes — intento 3: Fase 1 (fix2) (T-01, T-02, T-03, T-04) — 1 Important abierto: decisión del usuario» → [execution-history.md](execution-history.md) · SHA-256 `b9839f14c7158d1e7e69f18a15ec56d131c36ddac604fb3284a4afddafbb2734`
- 2026-11-20 · «Revisión de dos lentes — intento 4: Fase 1 (fix3, fuera del bucle) (T-01, T-02, T-03, T-04) — 3 Important en silencios heredados» → [execution-history.md](execution-history.md) · SHA-256 `aba50bf35a1563a8f13cf927f1823daf42771103c8e98915128eeb98e609413c`
- 2026-11-20 · «Revisión de dos lentes — intento 5: Fase 1 (fix4, fuera del bucle) (T-01, T-02, T-03, T-04) — 3 Important en los silencios de escritura» → [execution-history.md](execution-history.md) · SHA-256 `bc7b12d6dadcabf32b3ba7dc1167800982bb60767d8016097395f9dd0f89aef1`
- 2026-11-20 · «Revisión de dos lentes — intento 6: Fase 1 (fix5, fuera del bucle) (T-01, T-02, T-03, T-04) — 1 Important residual del principio de fix5» → [execution-history.md](execution-history.md) · SHA-256 `07472db88488c1f633829a690480a8a48379b8c0cf864f879da2b67b9e548414`
- 2026-11-23 · «Revisión de dos lentes — intento 7: Fase 1 (fix6, fuera del bucle) (T-01, T-02, T-03, T-04) — 2 Important: una regresión y un recorrido que no es lineal» → [execution-history.md](execution-history.md) · SHA-256 `69cb6654ce1cf8a4ee799671f02356160810566abc2db8e6fcbdfc53cc5f435c`
- 2026-11-23 · «Revisión de dos lentes — intento 8: Fase 1 (fix7, fuera del bucle) (T-01, T-02, T-03, T-04) — 3 Important: regresiones del escáner por regex» → [execution-history.md](execution-history.md) · SHA-256 `d49813abdb4197adfbec78930d14d66716db7b2941c69f8128d8f561905a0612`
- 2026-11-23 · «Revisión de dos lentes — intento 9: Fase 1 (fix8, parser de PostgreSQL) (T-01, T-02, T-03, T-04) — 3 Important en qué literales se analizan» → [execution-history.md](execution-history.md) · SHA-256 `8b920809ae26d99c92e860a8bf91dd273f875e2699fd228bb8552667a9f54013`
- 2026-11-23 · «Revisión de dos lentes — intento 10: Fase 1 (fix9) (T-01, T-02, T-03, T-04) — 2 Important en la puerta léxica y el respaldo» → [execution-history.md](execution-history.md) · SHA-256 `8179056aa28d19a1df996033c7df50b60b07a89e1f00e0f3a1f60412f2208575`
- 2026-11-23 · «Revisión de dos lentes — intento 11: Fase 1 (fix10) (T-01, T-02, T-03, T-04) — 1 Important: sentencias completas con tabla dinámica y huecos de cláusula» → [execution-history.md](execution-history.md) · SHA-256 `573aef42c452b7e89333ce006829a1a040db517dc0a9cb6c3a4eaf47818cfcc0`
- 2026-11-26 · «Revisión de dos lentes — intento 1: Fase 2 (T-06, T-07, T-08, T-09, T-10, T-11) — 5 Important: semáforo sin tope para sesiones, carrera del login, coste sin fijar» → [execution-history.md](execution-history.md) · SHA-256 `9449f3fda926ec4f05eabf3374711fe6c008ab47951a99d0b0fc8ecf93266697`
- 2026-11-26 · «Revisión de dos lentes — intento 2: Fase 2 (fix1) (T-06, T-07, T-08, T-09, T-10, T-11) — 2 Important: clave creada durante `--revoke-keys`, recuento sin índice» → [execution-history.md](execution-history.md) · SHA-256 `f9ffe76e2ecd9b085eb8c0fe197d2a1cfba9dc31772deeb545fa112752a3a05c`
- 2026-11-27 · «Revisión de dos lentes — intento 12: Fase 1 (fix11) (T-01, T-02, T-03, T-04) — 1 Important: la retirada de RAISE» → [execution-history.md](execution-history.md) · SHA-256 `1bca766ffaff62849ab9e7ecb074d4fad8d6eafa8c0fd1bf2bcae1ef6a39194f`
- 2026-11-27 · «Revisión de dos lentes — intento 3: Fase 2 (fix2) (T-06, T-07, T-08, T-09, T-10, T-11) — sin Critical ni Important; 6 Minor» → [execution-history.md](execution-history.md) · SHA-256 `c01d7449717046602020417abca565bc6ce748de1aeb5ed5f3620f55d592f7ff`
- 2026-11-27 · «Revisión de dos lentes — intento 1: Fase 3 (T-13, T-14, T-15, T-16, T-17) — 3 Important: alta en carrera con la revocación, cambio de contraseña desde una sesión cerrada, fines de línea» → [execution-history.md](execution-history.md) · SHA-256 `4e2c3669d547113c2b102dcaa40567268c65c975f56e940c0bc3656799a71542`
- 2026-11-27 · «Revisión de dos lentes — intento 2: Fase 3 (fix1) (T-13, T-14, T-15, T-16, T-17) — sin Critical ni Important; 3 Minor» → [execution-history.md](execution-history.md) · SHA-256 `a469127c2e6b20fb6d2d4887f289f114630c180034a590e7b52bf38463796d99`

## Revisión de dos lentes — intento 1: Fase 4 (T-19, T-20, T-21, T-22, T-23, T-24) — 2 Important: rotación de una clave ajena por un admin de proyecto, bloqueo del llamante sin prueba

Lentes: A+B+C+D (Opus 5.5) sobre `e9646a5..c84e1cf`; solo B ejecutó Docker, con `kairos-test:i4p4` sin red y PostgreSQL efímero. B: carreras de la rotación frente a revocación, `set-password --revoke-keys`, deshabilitar o cerrar la credencial del llamante, y dos rotaciones, correctas en los dos órdenes (sondas C1-C8); estrés de 8 hilos × 30 s (1 755 operaciones) sin interbloqueos; el aplazamiento de `last_used_at` deja la conexión del pool sana; 93 pruebas dirigidas OK; cliente 105/105. A: todos los criterios de T-19..T-24 cumplidos salvo el texto del mutante de T-22; `openapi-lint --diff` 0 rompedores de 1; `kairos-mcp.json` intacto; mínimo 1771 = 1745 + 26 en los cuatro sitios; fines de línea conservados. D: la comprobación del minuto va en memoria; sin anidar conexiones.

| # | Grado | Gap | Tarea | Corrección | Evidencia |
|---|---|---|---|---|---|
| 1 | Important | Un administrador de proyecto rota la clave de otro usuario (con proyectos y permisos que él cubre) y recibe un token que actúa como ese usuario: `_delegate` no mira al dueño, la nueva conserva el `actor_id` y el token vuelve al llamante; lee los datos privados del dueño en el proyecto (`work-state`, corpus) y lo que hace queda a nombre del dueño; la máquina del dueño sigue en gracia sin notarlo (lente C; B fuera de lente) | T-20 | pendiente (decisión del usuario) | `store_access.py:273, :283, :289`; `agent_store.py:202, :242, :252` · CWE-639, CWE-269 |
| 2 | Important | Ningún test protege el bloqueo de la fila del llamante en `rotate_key`: con el mutante `[found['actor_id']]` pasan los 178 tests de acceso; una revocación de la clave con que se rota quedaría sin esperar y la rotación entregaría un token nuevo (lente B) | T-20 | pendiente | `store_access.py:270`; mutante m1 en `scratchpad/p4a1-B/mutants.out` |
| 3 | Minor | La rotación responde 404 antes de autorizar: una credencial cualquiera distingue un id de clave existente (403) de uno inventado (404); `revoke_key` ya lo hacía; ids UUID4, no enumerables (lente C) | T-20 | pendiente | `store_access.py:267-269` · CWE-204 |
| 4 | Minor | `revoke_key` y `rotate_key` toman los bloqueos (fila del dueño; fila de la clave) antes de autorizar: un llamante sin permiso sobre la clave serializa las peticiones del dueño en cada intento; acotado (lente C) | T-22, T-20 | pendiente | `store_auth.py:290-293`; `store_access.py:270-273` · CWE-400 |
| 5 | Minor | `expires_at` (o la vida heredada) más allá del año 9999 en UTC: `DataError` sin gestionar → 503 `service_unavailable`; una clave con `9999-12-31` ya no se puede rotar (lente B) | T-19, T-20 | pendiente | `store_access.py:284`; `store_auth.py:258`; `models.py:88` |
| 6 | Minor | Ningún test protege el bloqueo de la fila del llamante en `revoke_key` (mutante m3 sobrevive) (lente B) | T-22 | pendiente | `store_auth.py:290` |
| 7 | Minor | La vida heredada se suma como `interval` de días: con un `TimeZone` de sesión con horario de verano la clave nueva dura ±1 h (3624 h en UTC frente a 3623 h en Europe/Madrid); hoy el servidor va en UTC (lente B) | T-20 | pendiente | `store_access.py:284` |
| 8 | Minor | `last_used_at` con el pool saturado: el touch espera conexión hasta `MEMORY_POOL_TIMEOUT` (5 s), no 50 ms, y como el reloj del proceso solo avanza si la escritura entra, cada petición de la clave lo reintenta (una espera de conexión más por petición y un aviso por petición); igual con un `FOR SHARE` largo sobre la clave (50 ms por petición) (lentes D, A y B) | T-19 | pendiente | `auth.py:53-66` |
| 9 | Minor | `probe.valid_key` actualiza `last_used_at` de la clave del probe solo por comprobarla (lente D, fuera de lente) | T-19 | pendiente | `probe.py:742-744` |
| 10 | Minor | El criterio «Mutante: quitar el vaciado de caché de un escritor deja la matriz en rojo» estaba marcado aunque su texto no se cumple (la caché vive una transacción); la protección existe por el recorrido estático y por la matriz con la caché que sobrevive a su transacción (lente A) | T-22 | corregido (orquestador, en este commit): texto del criterio y R-01 del plan con su changelog | `tasks.md` T-22; `improvement-plan.md` R-01 |
| 11 | Minor | El ledger superaba su límite práctico de 245 000 bytes (247 140) (lente A) | T-24 | parcial (orquestador, en este commit): sección del intento 2 de la fase 3 archivada (−6 KB); esta sección lo devuelve a 250 042 bytes, se archiva al cerrar la fase | `tasks.md`; `execution-history.md` |

Fuera de lente, sin fila: `docs/operations.md` no recomienda gracia 0 al rotar una clave comprometida (lente C); `test_mcp…test_semantic_budget_ms` falló una vez por plazo de reloj en T-22 (posible prueba inestable; lente A).
