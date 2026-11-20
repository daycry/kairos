---
generacion:
  inicio: 2026-11-19T16:43:20Z
  fin: 2026-11-19T16:55:44Z
  fuente: medido
  fuente_id: src-8ffaaac4e3b9a11805b5148dbea387f65be01b42fba05cbf3ca54c4b799a95c8
  ventana_id: win-9840d34e6fd84938989d3f0f0be11e9b
  revision_medicion: 2
  medicion_persistida: true
  tokens_reales: { entrada: 60, salida: 61233, cache_creacion: 135560, cache_lectura: 3557746, respuestas: 30 }
  eur: null              # precioTokens no fiable; ejecuta la skill rates-verify
  horas_ia: 0.66
  duracion: 40m            # reloj: 12m
  ratio_usado: 300000      # default no calibrado
---

# 2026-11-19-access-control

> Evaluación de coste y conveniencia de la Iniciativa 4 del plan director, «Control de acceso y privacidad», para decidir si se planifica, en cuántos hitos y si necesita un paso de diseño previo.

| | |
|---|---|
| **Fecha** | 2026-11-19 |
| **Estado** | completado |
| **Prioridad global** | Alta |
| **Solicitante** | Daycry (plan director, Iniciativa 4; encargo del orquestador `/dev-cycle`) |
| **Spec** | [`spec.md`](spec.md) |
| **Plan** | [`improvement-plan.md`](improvement-plan.md) · [`tasks.md`](tasks.md) (borrador, 2026-11-20) |
| **Características evaluadas** | 8 |

---

## Cuadro de mando

| Métrica | Total estimado | Confianza |
|--------|----------------|-----------|
| Esfuerzo humano equivalente | **582 h** (485 h base +20 %), de las que 230,4 h son revisión adversarial | Media-Baja: las horas humanas no se han registrado en ninguna iniciativa |
| Tiempo IA (ejecución) | **77,7 h** nominales (64,7 h base +20 %) (+ 19,4 h supervisión); **≈ 50 h** si se repite la cota inferior de la Iniciativa 3 (−36 %) | Media-Baja |
| Coste | **29.100 €** de desarrollo + tokens IA ⚠️ verificar | Media-Baja (desarrollo) / sin cifra (tokens) |
| Tokens IA facturables | **~19,4 M** (in 17,86 M / out 1,55 M) | Baja |
| Multiplicador productividad | **×6,0** | — |
| Características | **8** (+ revisión adversarial, mediciones previas, revisión de hito e integración como líneas propias) | — |

> Horas humanas (lo que vale el trabajo) y horas IA (lo que tarda el ciclo) van por separado y no se suman (LES-007). El método de horas IA de la Iniciativa 3 acertó en el agregado de las fases con horas registradas (35,37 h reales frente a 35,8 h estimadas, −1 %), pero falló en el reparto: las ocho fases de implementación con horas sumaron 19,6 h de 29,4 h estimadas (67 %), y las de medición y cierre, 15,8 h de 6,4 h (2,5 veces). Aquí se mantiene el agregado y se cambia el reparto.

---

## Resumen ejecutivo

Se presupuestan los ocho bloques de la spec (43 criterios de aceptación): credenciales (C-01), login (C-02), límites por clave (C-03), redacción (C-04), identidad y extensibilidad (C-05), superficie de secretos (C-06), revisión de seguridad y cierre (C-07) y portal (C-08). El total es de **582 h humanas equivalentes (29.100 € con margen)** más tokens IA, con **~78 h nominales de ejecución IA**. Es un 41 % más que la Iniciativa 3 en horas base (485 h frente a 344 h) por tres motivos: hay interfaz de usuario con pruebas de navegador, cuatro de las ocho características y parte de una quinta están expuestas a entradas de clientes y se revisan a 1,0 veces la implementación, y las cuatro mediciones previas y la revisión del diff de cada hito llevan partida propia, como pide la retro de la Iniciativa 3.

El reconocimiento sobre `d20f54f` confirma los hechos de la spec y añade seis que cambian el coste o el diseño:

1. **Las «pruebas de navegador» que cita la spec no usan navegador.** `web/tests/` ejecuta el portal sobre un DOM escrito a mano en `node:vm` (65 casos). El navegador real está en otro sitio: `server/memory_platform/Dockerfile.e2e` y `tests/e2e_portal.py` (Playwright 1.55 con Chromium, 20 casos), que la CI no ejecuta y cuya última evidencia es del 2026-11-06.
2. **CA-42 restringe un comportamiento actual.** Hoy un administrador de proyecto que no es administrador global crea usuarios (`store_auth.py:171-175`) y un test lo exige (`test_api_limits.py:147-149`). La spec lo cuenta entre las acciones que deben responder 403.
3. **El portal no sabe quién es administrador global.** Decide con `scopes.includes('admin')` (`memory-portal.ts:75`) y `/v1/auth/me` no publica `is_admin` (`app.py:64-65`).
4. **El cliente descarta una captura tras cinco intentos** (`dispatcher.mjs:134`) y nunca espera más de 60 s (`:144`). Con una cuota diaria agotada, eso contradice el «sin pérdida» de CA-20. Además, el cliente habla con `kairos-mcp`, y la spec no dice cómo cruza `Retry-After` un error de herramienta «con la forma actual».
5. **CA-38 (a) falla hoy en al menos cinco sitios** que leen `project_grants` o `is_admin` fuera de `_active` y `_require`.
6. **Los permisos resueltos se guardan por transacción** (`auth_scope.py`, Iniciativa 3). Todo escritor nuevo de usuarios, sesiones, claves o permisos debe vaciar esa caché y registrarse en `test_auth_cache.py`.

Se propone partir en **tres hitos, un PR por hito**: **A «acceso que se puede retirar»** (C-01, C-02 y el test de CA-38; 189 h), **B «clientes acotados y secretos fuera»** (C-03, C-04, C-06; 222 h) y **C «portal, identidad y cierre»** (C-08, C-05, C-07 y la versión 0.4.2; 171 h). Veredicto: **go con condiciones**. Las condiciones son resolver CA-42, corregir en la spec la hipótesis de las pruebas de navegador y pasar por `architect` antes del plan.

---

## Requerimientos recibidos

Mapa de la spec (§Alcance y §Criterios de aceptación) a las características evaluadas. Cada característica es un bloque de la spec, con el mismo número.

| ID | Característica | Requisito origen (ref.) | Clase | ¿Claro? |
|----|---------------|-------------------------|-------|---------|
| C-01 | Credenciales: contraseña, deshabilitar, permisos, sesiones, caducidad, rotación, último uso, scrypt | A-01 · S-03, S-07 · CA-01…CA-11 | Capacidad nueva + defecto | Parcial: CA-08 (cómo distingue `doctor` una clave caducada) y parámetros de scrypt provisionales (P-04) |
| C-02 | Login: solo fallos, IP real, cubo por IP | A-02 · S-02 · CA-12…CA-15 | Defecto | Sí |
| C-03 | Límites: tasa, cuota y tope de flujos por credencial | A-03 · S-08 · CA-16…CA-21 | Capacidad nueva **visible para clientes** | Ambiguo: dónde vive la cuota, exención de `kairos-mcp`, transporte de `Retry-After` y tope de intentos del cliente |
| C-04 | Redacción: patrones, entropía, casos compartidos | A-04 · S-01 · CA-22…CA-27 | Defecto + capacidad nueva **visible para clientes** | Sí; umbral y cota provisionales hasta medir |
| C-05 | Identidad: guía de alta y baja probada y extensibilidad del modelo de permisos | A-05 · P-01 · CA-28…CA-30, CA-38 | Documentación ejecutable + refactor | Ambiguo: qué es «decidir un acceso» en CA-38 (a) |
| C-06 | Superficie: directorio de secretos, permisos del fichero de clave, guarda de la red de inferencia | A-06 · S-10, S-11 · CA-31…CA-33 | Defecto | Sí |
| C-07 | Revisión de seguridad y cierre | A-07 · CA-34…CA-37 | Proceso | Sí |
| C-08 | Portal: «Mi cuenta», «Usuarios» y «Claves para agentes» | A-08 · P-02 · CA-39…CA-43 | Capacidad nueva en la interfaz | Ambiguo: qué arnés de navegador y alcance de «alta» en CA-42 |

**Hechos del reconocimiento** (con `fichero:línea`, sobre `d20f54f`; los de la spec no se repiten):

- **Autenticación**: el vencimiento de claves y sesiones se decide con `clock_timestamp()` en SQL (`auth.py:60`, `:69`; `store_auth.py:20`, `:25`). Un «reloj controlado» para caducidad y gracia exige fechar filas hacia atrás, no inyectar un reloj en Python.
- **Caché de permisos**: `_active` y `_require` guardan su respuesta en un diccionario que vive lo que la transacción (`auth_scope.py:16-54`). `invalidate_auth` aparece hoy en 9 módulos y `test_auth_cache.py` (568 líneas) recorre el paquete para comprobar que cada escritor la llama (`:371`).
- **Lectores de permisos fuera del resolvedor**: `auth.py:44-50` (compone `scopes` y `project_ids` del actor), `corpus_answers.py:140` y `extended_store.py:62` (bloqueos `FOR SHARE` previos a la segunda comprobación), `app.py:202` (`is_admin` para `/metrics`), `probe.py:678-793` (cuenta de servicio de la sonda) y `store_auth.py:101`, `:192`, `:211` (listados).
- **Gestión de usuarios**: `create_user` delega por proyecto con `_delegate` (`store_auth.py:160-175`); `list_users` exige administrador global (`:189`). No hay ruta que modifique un usuario.
- **Portal**: `memory-portal.ts` tiene 702 líneas y 75 kB; la vista de configuración entera se niega a quien no tiene el permiso `admin` (`:609`), así que «Mi cuenta» necesita una entrada nueva para cualquier usuario. Las pestañas actuales comparten una sola función, `accessSettings` (`:641-666`).
- **Pruebas del portal**: `web/Dockerfile.test` ejecuta `npm test` y `npm run build` (6 líneas); `web/tests/memory-portal.test.mjs` (335 líneas) define sus propias clases `Element`, `Input` y `Select`. El arnés de navegador real depende de las etiquetas locales `kairos-web:native-test` y `kairos-test:native` (`Dockerfile.e2e:1-2`); la CI solo comprueba que su fixture siembra (`test_e2e_fixture.py`).
- **Cliente**: cola con espera exponencial hasta 60 s y paso a `failed` con `capture_retry_limit` al quinto intento (`dispatcher.mjs:134-144`); ninguna referencia a `Retry-After` ni a 429 en `client/lib/`.
- **`kairos-mcp`**: un error de `/v1` llega al cliente como texto en un resultado `isError` (`mcp/kairos_mcp/tools.py:84`); el 401 es el único estado que se convierte en respuesta HTTP propia (`mcp/kairos_mcp/auth.py:60-93`).
- **Proxy web**: tres bloques `location` hacia la API (`/memory-api/`, `/v1/`, `/health/ready`) y ninguno envía `X-Forwarded-For` (`web/nginx.conf:50-78`). `/metrics` en modo `internal` responde 404 si la petición trae cualquier cabecera de proxy (`app.py:23`, `:196`): añadir `X-Forwarded-For` refuerza esa regla, no la rompe.
- **Arneses reutilizables**: `tests/fault_proxy.py`, `tests/nginx_portal_probe.py` (nginx real con un servidor simulado), `test_compose_limits.py` (aserciones sobre `docker compose config`), `scripts/rehearse-reliable-operations.py` (ensayo en Compose aislado).
- **Redacción**: el módulo del servidor (201 líneas) y el del cliente (89 líneas) son dos implementaciones paralelas del mismo analizador de asignaciones con comillas y escapes (`privacy.py:33-59`, `privacy.mjs:7-30`), una con `re` de Python y otra con `RegExp` de JavaScript.
- **Secretos**: el `MEMORY_SECRETS_DIR` configurado hoy está fuera del repositorio y de carpetas sincronizadas, así que CA-31 no rechazará la instalación actual. El repositorio sí está dentro de OneDrive, y con él `.private/`.
- **Tamaño de las suites**: 1.465 funciones de test en el servidor, 141 en `kairos-mcp`, 94 en el cliente y 65 en el portal.
- **Salud del código** (`code-health.py`, heurístico): los ficheros que más cambian y más pesan son `scripts/deploy-memory.py` (29 cambios en 90 días, 1.638 líneas), `server/memory_platform/admin.py` (19 cambios, 545 líneas) y `config.py` (12 cambios, 504 líneas). C-06 toca el primero y C-01 los otros dos. La cifra de duplicados del informe no es utilizable: cuenta copias sin versionar en `.private/` y `.claude/worktrees/`.

**Ambigüedades y problemas de la spec** (se presupuestan bajo el supuesto indicado; no se ha tocado la spec):

1. **CA-42 frente a la delegación actual.** La lista de controles de administración incluye «alta», pero hoy un administrador de proyecto crea usuarios y `test_api_limits.py:147-149` lo exige. O se restringe (cambio de comportamiento de `/v1`, a declarar en el CHANGELOG y a la Iniciativa 7) o se mantiene la delegación y CA-42 excluye el alta. **Supuesto:** se mantiene la delegación y solo las acciones nuevas son del administrador global. Necesita decisión.
2. **Pruebas de navegador.** La hipótesis de la spec («`web/tests/` y `web/Dockerfile.test` admiten una API de fixture») es cierta, pero eso no es un navegador. **Supuesto:** los casos [GWT] de CA-39 a CA-42 se cubren en los dos niveles: DOM de frontera en `web/tests/` (CI) y Chromium real en `e2e_portal.py` (Docker local, con el equivalente local declarado, como pide el aprendizaje 4 de la retro de la Iniciativa 3).
3. **CA-20, «sin pérdida».** No dice si un 429 consume intentos del cliente ni cómo llega `Retry-After` a través de `kairos-mcp`. **Supuesto:** el 429 no consume intentos y el plazo viaja en el mensaje del error de herramienta con un formato estable, sin cambiar esquemas del contrato MCP.
4. **CA-08, «distingue clave caducada de clave inválida».** El servidor responde el mismo 401 a las dos (`auth.py:60`). **Supuesto:** `doctor` usa el `expires_at` que leyó en un `/v1/auth/me` anterior y lo guarda en su estado local; el 401 no cambia.
5. **CA-38 (a), «decidir un acceso».** Leído al pie de la letra falla hoy en cinco sitios. **Supuesto:** el test admite una lista cerrada y justificada (bloqueos `FOR SHARE`, listados, sonda) y `auth.py:44-50` y `app.py:202` se llevan al resolvedor.
6. **CA-18, dónde vive la cuota diaria.** La spec fija en memoria el cubo de tasa, no la cuota. En memoria, un reinicio de `memory-api` la pone a cero. **Supuesto:** contador en la base, con escritura agrupada.
7. **Esquema 13 en varios PR.** La columna de anulación por clave (C-03) y `last_used_at` (C-01) caen en hitos distintos. **Supuesto:** el hito A define todas las columnas de la versión 13.
8. **Frontmatter.** `design: n/a` deja de valer si se acepta el paso de diseño.

---

## Datos necesarios para una evaluación completa

- [x] **Requerimientos** completos: alcance cerrado por el plan director y por las decisiones P-01, P-02, P-03 y P-07 del usuario
- [ ] **Requerimientos sin ambigüedades**: ocho puntos abiertos, de los que el primero (CA-42) necesita decisión
- [x] **Alcance** de cada característica acotado (qué entra y qué no)
- [x] **Criterios de aceptación** por característica (CA-01…CA-43)
- [x] **Restricciones** confirmadas: fixtures aislados de PostgreSQL, HTTP y navegador; migraciones aditivas; contrato MCP conservado; versión 0.4.2; Docker de uno en uno; sin despliegue real
- [ ] **Dependencias externas**: nota a la Iniciativa 7 por los 429 y los rechazos nuevos; el VPS con una sola réplica de `memory-api` es hipótesis hasta la Iniciativa 5
- [x] **Contexto técnico** del proyecto disponible: reconocimiento hecho
- [ ] **Tarifa/hora y supuestos de coste**: sin `.claude/rates.json`; valores por defecto y precio de tokens ⚠️ verificar

---

## Supuestos económicos (ajustables)

**Coste = (horas × tarifa) + coste de tokens de IA.** Importes en **EUR**.

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Tarifa de desarrollo | 50 €/h | Valor por defecto del kit (no hay `.claude/rates.json`) |
| Modelo IA asumido | Claude (familia vigente en el ciclo) | Base de la previsión de tokens |
| Precio input | ⚠️ verificar € / 1M tokens | Sin `precioTokens` fiable; ejecuta la skill `rates-verify` |
| Precio output | ⚠️ verificar € / 1M tokens | Ídem |
| Tipo de cambio | 1 USD = 0,92 € | Valor por defecto del kit |
| Margen de contingencia | 20 % | Sobre horas base humanas e IA, revisión incluida |
| Supervisión humana | 25 % de las horas IA | Valor por defecto |
| Ratio tokens→hora IA | 300.000 tok/h facturables | **Default no calibrado**: `CALIBRATION.md` tiene tres filas, las tres `(estimado)`, sin ratio medido |
| Tokens totales | 40.000 facturables por hora humana base (92 % entrada / 8 % salida) | Método de la Iniciativa 3, que acertó en el agregado (−1 %) |
| Reparto de tokens | 3,0 M para mediciones (10 h IA) + 2,25 M para revisión de hito (7,5 h IA) + 30.800 por hora base en el resto | El agregado no cambia; cambia el reparto, según la retro de la Iniciativa 3 |
| Revisión adversarial | **1,0 ×** en C-01, C-02, C-03, C-04 y en la parte de autorización de C-08 (14 h); 0,5 × en C-05, C-06 y el resto de C-08 (42 h) | Retro de la Iniciativa 2: «el doble para servicios expuestos a entradas de clientes» |
| Tokens facturables | entrada no cacheada + creación de caché + salida | La lectura de caché no cuenta |

**Método de esfuerzo humano**: estimación por componentes sobre el código medido (rutas, subcomandos y pantallas a añadir, puntos de cambio con `fichero:línea`, tests existentes por área). Es un punto medio realista sin colchón; el margen se aplica después.

**Calibración aplicada**:

- **Agregado de horas IA.** En la Iniciativa 3 se estimaron 55,0 h y se midieron 35,37 h (−36 %, cota inferior: las fases 4 a 7 no tienen horas). En las fases con horas, 35,37 h frente a 35,8 h (−1 %). Es la primera fila que avala el método, así que la confianza del tiempo IA sube de Baja a Media-Baja. No sube más porque las `horas_ia` salen de los tokens con el ratio por defecto y solo hay una fila.
- **Reparto.** Las ocho fases de implementación de la Iniciativa 3 con horas (1, 2, 3, 9, 10, 11, 12 y 13) sumaron 19,6 h de 29,4 h estimadas, el 67 %, con mucha dispersión: de 0,83 h de 4,3 h en la fase 1 a 4,95 h de 3,1 h en la 11. Las de medición y cierre (8, 14, 15 y 16) sumaron 15,8 h de 6,4 h, con la fase 14 en 10,36 h de 4,5 h y la 15 en 3,51 h de 0,3 h. Por eso las mediciones y la revisión de hito tienen aquí horas IA propias y el resto baja de 40.000 a 30.800 tokens por hora base (el 77 %, algo por encima del 67 % observado).
- **Revisión del diff de cada hito, ≥ 2 h.** Se presupuestan 2,5 h IA por hito (7,5 h en tres hitos). En la Iniciativa 3 se estimaron 0,13 h y fueron 3,41 h.
- **Cada fix que añade comportamiento se revisa con lentes completas.** La revisión a 1,0 × cubre un intento más por fase en C-01, C-02, C-03 y C-04. En C-06, que toca `deploy-memory.py` (código de operación y el fichero que más cambia del repo), el planner debe sumar un intento de revisión por fix dentro de sus 9 h.
- **Tareas que miden o repiten la suite, ~4 h.** Cuatro mediciones previas con 10 h IA: perfil real del cliente (CA-16) 4 h, scrypt en el contenedor (CA-09) 2,5 h, entropía sobre el corpus (CA-24) 2 h y coste de las reglas (CA-27) 1,5 h. Solo la primera necesita la pila aislada completa y un cliente real; ninguna usa un modelo.
- **Medir antes de fijar metas.** Los valores de scrypt, tasa, cuota, flujos, umbral de entropía y cota de CA-27 siguen siendo provisionales en esta evaluación. Ninguna cifra del presupuesto depende de su valor final, salvo el riesgo R-02.
- **Revisión adversarial ≥ 0,5 × la implementación, el doble en servicios expuestos.** Aplicado por característica (ver la tabla anterior). La revisión supone 192 h base, el 83 % de las 232 h de implementación de C-01 a C-06 y C-08; en la Iniciativa 3 fue el 64 %.
- **Horas humanas.** Nunca se han registrado, así que el coste en euros no se puede calibrar: es el valor nominal del trabajo, no un gasto previsto.
- **Doctrina del plugin**: LES-001 y LES-009 (la revisión es la partida grande), LES-005 (con TDD la ejecución es más cara y la revisión más barata), LES-007 (horas humanas e IA por separado) y LES-008 (coste de proceso aparte).
- La memoria del proyecto (`docs/knowledge/`) no tiene lecciones de estimación aprobadas; hay dos candidatas pendientes de la retro de la Iniciativa 3, ya recogidas arriba. El diario no tiene ninguna entrada de esta iniciativa. No existe `docs/CONSTITUTION.md`.

---

## Evaluación por característica

### C-01 — Credenciales (S-03, S-07)

- **Requisito origen**: A-01; CA-01…CA-11. Criterio de cierre 2 del plan director (CA-11).
- **Clase / primer oráculo**: capacidad nueva + defecto · tras cambiar la contraseña, otra sesión del mismo usuario recibe 401.
- **Descripción**: siete rutas nuevas de `/v1` (contraseña, usuario deshabilitado, permisos, sesiones propias y ajenas, rotación) y tres subcomandos de `admin`; caducidad opcional al crear una clave y `last_used_at`; scrypt reforzado con rehash al iniciar sesión y logins simultáneos acotados; versión de esquema 13; matriz de revocación en las cuatro rutas y en un flujo abierto.
- **Complejidad**: Alta.
- **Esfuerzo**: 50 h base (60 h con margen) · confianza Media. Desglose: cambio de contraseña con revocación y auditoría 4 h; `set-password`, `disable-user` y `enable-user` 3 h; deshabilitar y rehabilitar con las reglas de «uno mismo» y «último administrador» 4 h; sustituir permisos 3 h; sesiones 3,5 h; caducidad, `expires_at` y `last_used_at` 4 h; rotación con gracia 4 h; aviso de `kairos doctor` 3 h; scrypt (parámetros, `maxmem`, rehash, hash ficticio, tope de simultáneos y su test de memoria) 4 h; migración 13 y test de actualización desde 0.4.1 3 h; matriz de CA-11 con el proxy web en Compose aislado 6 h; modelos y OpenAPI 2 h; tests unitarios 5 h; documentación 1,5 h.
- **Previsión IA**: 1,42 M in / 0,12 M out tok (5,1 h IA base) · ⚠️ verificar €.
- **Coste**: (60 h × 50 €/h) + tokens = **3.000 € + tokens**.
- **Impacto / áreas afectadas**: `auth.py`, `store_auth.py`, `app.py`, `models.py`, `admin.py`, `config.py`, `schema.sql`, `client/lib/mcp.mjs` (`doctor`), `test_auth*.py`, `test_admin.py`, `test_migrations_additive.py`, `docs/contracts/memory-platform.openapi.json`.
- **Dependencias y prerequisitos**: medición de scrypt (CA-09) y test de CA-38 (a) antes de añadir rutas; lista completa de columnas del esquema 13.
- **Riesgos**: R-01 (un escritor nuevo que no vacía la caché de permisos deja viva una revocación dentro de su transacción); R-02 (scrypt con `n=2^17` son unos 128 MB por verificación en un contenedor de 1 GB, y el login no exige credencial); `admin.py` y `config.py` son ficheros que cambian mucho (19 y 12 cambios en 90 días); `last_used_at` añade una escritura al camino de autenticación.
- **Incógnitas / preguntas abiertas**: P-04; CA-08 (ambigüedad 4); qué datos lleva la lista de sesiones (hoy `web_sessions` solo guarda identificador, hashes y fechas).

### C-02 — Login (S-02)

- **Requisito origen**: A-02; CA-12…CA-15. Criterio de cierre 3 del plan director (CA-13).
- **Clase / primer oráculo**: defecto · diez fallos desde la IP `a` no impiden el login correcto del mismo usuario desde la IP `b`.
- **Descripción**: contar solo los fallos; bloqueo por IP de cliente con `Retry-After`; `MEMORY_TRUSTED_PROXIES` y lectura de `X-Forwarded-For` desde la derecha; nginx envía la cabecera; fallos por usuario como métrica.
- **Complejidad**: Media.
- **Esfuerzo**: 18 h base (21,6 h con margen) · confianza Media-Alta. Desglose: contador de fallos, cubo, `Retry-After`, métrica y variables 4 h; IP real y proxies de confianza en la API y en nginx 5 h; tests con proxy simulado, dos proxies encadenados y nginx real 6 h; concurrencia del registro de fallos 2 h; documentación 1 h.
- **Previsión IA**: 0,51 M in / 0,04 M out tok (1,8 h IA base) · ⚠️ verificar €.
- **Coste**: (21,6 h × 50 €/h) + tokens = **1.080 € + tokens**.
- **Impacto / áreas afectadas**: `auth.py:74-93`, `app.py:206-213`, `config.py`, `observability.py`, `web/nginx.conf`, `docker-compose.yml`, `test_nginx_*.py`, `docs/configuration.md`.
- **Dependencias y prerequisitos**: ninguna. El tope de logins simultáneos de C-01 comparte la ruta.
- **Riesgos**: R-07 (`web/nginx.conf` lo monta la instalación desplegada: el cambio le llega en su próximo `up`); una lista de proxies mal configurada vuelve a dejar a todos los clientes con la misma IP o permite suplantarla.
- **Incógnitas / preguntas abiertas**: ninguna bloqueante.

### C-03 — Límites por clave (S-08), visible para clientes

- **Requisito origen**: A-03; CA-16…CA-21.
- **Clase / primer oráculo**: capacidad nueva visible para clientes · K1 recibe 429 mientras K2 sigue en 200.
- **Descripción**: cubo de fichas por credencial en memoria, cuota diaria de escrituras, tope de flujos por credencial y global, anulación por clave; `kairos-mcp` traduce el 429; el cliente conserva la captura y respeta `Retry-After`; métricas por motivo.
- **Complejidad**: Alta (cuatro componentes: API, `kairos-mcp`, cliente y contrato).
- **Esfuerzo**: 38 h base (45,6 h con margen) · confianza Media-Baja. Desglose: cubo, configuración y anulación por clave 6 h; punto de enganche y exenciones (`/health/*`, login, validación de `kairos-mcp`) 4 h; cuota diaria 5 h; tope de flujos y liberación al desconectar 4 h; cola del cliente (429 sin consumir intentos, `Retry-After`) 6 h; traducción en `kairos-mcp` 2 h; métricas y log 2 h; tests (reloj controlado, dos claves, flujos, contratos aditivos) 7 h; documentación y nota a la Iniciativa 7 2 h.
- **Previsión IA**: 1,08 M in / 0,09 M out tok (3,9 h IA base) · ⚠️ verificar €.
- **Coste**: (45,6 h × 50 €/h) + tokens = **2.280 € + tokens**.
- **Impacto / áreas afectadas**: `app.py`, `activity.py`, `config.py`, `observability.py`, `schema.sql`, `mcp/kairos_mcp/tools.py` y `translate.py`, `client/lib/dispatcher.mjs` y `outbox.mjs`, `test_contract_additive.py`, `CHANGELOG*.md`.
- **Dependencias y prerequisitos**: medición del perfil del cliente (CA-16); diseño previo (ver «Recomendación»).
- **Riesgos**: R-03 (diseño abierto en cuatro puntos); R-04 (el cliente descarta la captura al quinto intento); R-10 (tests con ventanas y periodos).
- **Incógnitas / preguntas abiertas**: P-06; ambigüedades 3 y 6; cómo se reconoce la lectura `/v1/auth/me` de `kairos-mcp` sin una cabecera que cualquiera pueda enviar, dado que `kairos-mcp` no tiene credencial propia.

### C-04 — Redacción (S-01), visible para clientes

- **Requisito origen**: A-04; CA-22…CA-27.
- **Clase / primer oráculo**: defecto + capacidad nueva · el fichero de casos compartido con las siete cadenas de S-01 falla en las dos suites.
- **Descripción**: fichero de casos (≥ 40, con ≥ 15 que no deben redactarse) leído por servidor y cliente; patrones nuevos en los dos módulos; detector de entropía conservador; tabla ruta → comportamiento con un test por ruta; cota de tiempo con entrada adversaria.
- **Complejidad**: Media-Alta.
- **Esfuerzo**: 32 h base (38,4 h con margen) · confianza Media. Desglose: fichero de casos y sus dos ejecutores 5 h; patrones en Python y en JavaScript 7 h; detector de entropía 3 h; tabla de rutas y seis familias de tests 6 h; CA-23 de extremo a extremo (cola del cliente, base y log) 4 h; test de cota 1 h; unificar la divergencia de `sk-` 1 h; tests adicionales 3 h; CHANGELOG, nota a la Iniciativa 7 y documentación 2 h.
- **Previsión IA**: 0,91 M in / 0,08 M out tok (3,3 h IA base) · ⚠️ verificar €.
- **Coste**: (38,4 h × 50 €/h) + tokens = **1.920 € + tokens**.
- **Impacto / áreas afectadas**: `privacy.py`, `client/lib/privacy.mjs`, `store_ingest.py`, `store_documents.py`, `agent_store.py`, `extended_store.py`, `corpus_answers.py`, `observability.py` (`redact_log`), `test_privacy.py`, `client/tests/capture.test.mjs`, fichero de casos nuevo.
- **Dependencias y prerequisitos**: mediciones de entropía (CA-24) y de coste (CA-27).
- **Riesgos**: R-05 (consumo de CPU con expresiones regulares sobre texto no fiable, la misma clase que llevó seis intentos de revisión en la fase 5 de la Iniciativa 2); dos implementaciones que pueden divergir en casos límite de `re` y `RegExp`; más rechazos de documentos y de estado de trabajo para quien publica.
- **Incógnitas / preguntas abiertas**: umbral de entropía y cota de CA-27, provisionales hasta medir.

### C-05 — Identidad y extensibilidad (P-01)

- **Requisito origen**: A-05; CA-28…CA-30 y CA-38.
- **Clase / primer oráculo**: documentación ejecutable + refactor · el test que sigue la guía no existe.
- **Descripción**: guía con ocho procedimientos, por el portal y por API o comando; test que la sigue de principio a fin; test que recorre el paquete y comprueba que solo el resolvedor decide accesos; nota de diseño de las ampliaciones futuras.
- **Complejidad**: Media.
- **Esfuerzo**: 20 h base (24 h con margen) · confianza Media. Desglose: guía 5 h; tests de CA-29 y CA-30 5 h; test de recorrido y traslado de los lectores externos al resolvedor 7 h; nota de diseño en `docs/architecture.md` 3 h.
- **Previsión IA**: 0,57 M in / 0,05 M out tok (2,1 h IA base) · ⚠️ verificar €.
- **Coste**: (24 h × 50 €/h) + tokens = **1.200 € + tokens**.
- **Impacto / áreas afectadas**: `docs/` (guía nueva, `architecture.md`), `auth.py:44-50`, `app.py:202`, `store_auth.py`, test nuevo junto a `test_auth_cache.py`.
- **Dependencias y prerequisitos**: el test de CA-38 (a) va **antes** que C-01, para que las rutas nuevas nazcan bajo la regla; la guía y sus tests van después de C-08, porque citan pasos del portal y la tabla de paridad de CA-43.
- **Riesgos**: R-11 (sin una definición de «decidir un acceso», la revisión discutirá cada excepción).
- **Incógnitas / preguntas abiertas**: ambigüedad 5.

### C-06 — Superficie de secretos (S-10, S-11)

- **Requisito origen**: A-06; CA-31…CA-33.
- **Clase / primer oráculo**: defecto · el despliegue acepta un directorio de secretos dentro del repo; el cliente acepta una clave con modo `0644`.
- **Descripción**: `secrets_dir_unsafe` antes de cualquier fase; Compose sin `./secrets` por defecto; test de `.private/`; `key_file_too_open` en POSIX y aviso de `doctor` en Windows; guarda de la red `inference`.
- **Complejidad**: Baja-Media.
- **Esfuerzo**: 18 h base (21,6 h con margen) · confianza Media-Alta. Desglose: validación del directorio y detección de carpetas sincronizadas 6 h; test de `.private/` 2 h; permisos del fichero de clave y lectura de ACL en Windows 5 h; test sobre `docker compose config` 2 h; tests y documentación 3 h.
- **Previsión IA**: 0,51 M in / 0,04 M out tok (1,8 h IA base) · ⚠️ verificar €.
- **Coste**: (21,6 h × 50 €/h) + tokens = **1.080 € + tokens**.
- **Impacto / áreas afectadas**: `scripts/deploy-memory.py:1123-1129`, `docker-compose.yml:337-339`, `client/lib/files.mjs:64-71`, `client/lib/mcp.mjs` (`doctor`), `test_deploy*.py`, `test_compose_limits.py`.
- **Dependencias y prerequisitos**: ninguna. Es independiente del resto.
- **Riesgos**: R-08 (`deploy-memory.py` es el fichero que más cambia y los fixes encadenados del hito B de la Iniciativa 3 fueron en código de despliegue); R-07 (quitar el valor por defecto del Compose afecta al próximo `up` de la instalación, que hoy sí define la variable).
- **Incógnitas / preguntas abiertas**: P-08, P-09; fiabilidad de leer ACL con `icacls` (mejor esfuerzo).

### C-07 — Revisión de seguridad y cierre

- **Requisito origen**: A-07; CA-34…CA-37. Criterio de cierre 1 del plan director (CA-34).
- **Clase / primer oráculo**: proceso.
- **Descripción**: revisión de seguridad independiente sobre el diff completo y la superficie de acceso, con `review.md`; cada fix revisado como código nuevo; matriz hallazgo → test que falla si se retira el control; cierre con contratos, suites, manuales, CHANGELOG y versión 0.4.2.
- **Complejidad**: Media.
- **Esfuerzo**: 24 h base (28,8 h con margen) · confianza Media-Baja. Desglose: revisión de seguridad de la superficie de acceso 8 h; fixes y su revisión con lentes completas 6 h; matriz de siete hallazgos con prueba de retirada 4 h; cierre (contratos, 0 omitidos, tres manuales, CHANGELOG en dos idiomas, versión en servidor, MCP y cliente) 6 h.
- **Previsión IA**: 0,68 M in / 0,06 M out tok (2,5 h IA base) · ⚠️ verificar €.
- **Coste**: (28,8 h × 50 €/h) + tokens = **1.440 € + tokens**.
- **Impacto / áreas afectadas**: `review.md`, `tasks.md`, `docs/configuration.md`, `docs/operations.md`, `docs/architecture.md`, `CHANGELOG*.md`, `VERSION`, `docs/contracts/*.json`.
- **Dependencias y prerequisitos**: todas las demás características.
- **Riesgos**: R-09 (el número de hallazgos no se conoce de antemano; las 6 h de fixes son un supuesto). No lleva multiplicador de revisión: ya es revisión.
- **Incógnitas / preguntas abiertas**: ninguna.

### C-08 — Portal (P-02)

- **Requisito origen**: A-08; CA-39…CA-43.
- **Clase / primer oráculo**: capacidad nueva en la interfaz · la prueba de navegador que deshabilita un usuario no encuentra el control.
- **Descripción**: sección «Mi cuenta» para cualquier usuario; pestaña «Usuarios» con deshabilitar, rehabilitar, permisos por proyecto y cierre de sesiones; pestaña «Claves para agentes» con caducidad, último uso y rotación; controles ocultos a quien no es administrador global; tabla de paridad con `/v1` y `admin`.
- **Complejidad**: Alta.
- **Esfuerzo**: 56 h base (67,2 h con margen) · confianza Media-Baja. Desglose: `is_admin` en `/v1/auth/me` y acceso a «Mi cuenta» 3 h; «Mi cuenta» 6 h; «Usuarios», con el editor de permisos por proyecto 10 h; «Claves» 6 h; métodos y tipos de `memory-api.ts` 2 h; tests de DOM de frontera, unos 25 casos 8 h; navegador real (recuperar el arnés y cuatro flujos) 9 h; tests de servidor de CA-42 (403 y CSRF por ruta) 4 h; tabla y test de paridad 4 h; estilos y accesibilidad 3 h; documentación 1 h.
- **Previsión IA**: 1,59 M in / 0,14 M out tok (5,7 h IA base) · ⚠️ verificar €.
- **Coste**: (67,2 h × 50 €/h) + tokens = **3.360 € + tokens**.
- **Impacto / áreas afectadas**: `web/src/memory-portal.ts`, `memory-api.ts`, `memory-types.ts`, `memory-portal.css`, `web/tests/memory-portal.test.mjs` y `memory-api.test.mjs`, `server/memory_platform/tests/e2e_portal.py` y `e2e_fixture.py`, `Dockerfile.e2e`, `app.py:64-65`.
- **Dependencias y prerequisitos**: C-01 (todas sus rutas); decisión sobre CA-42 (ambigüedad 1).
- **Riesgos**: R-06 (el arnés de Chromium lleva sin ejecutarse desde el 2026-11-06 y el portal ha cambiado en dos iniciativas; cada ejecución construye dos imágenes); el DOM de frontera hay que ampliarlo para cada control nuevo; `memory-portal.ts` es un único fichero de 75 kB con líneas muy largas, donde un cambio pequeño produce un diff difícil de revisar.
- **Incógnitas / preguntas abiertas**: ambigüedades 1 y 2; si el navegador real entra en la CI o se queda como comprobación local declarada.

### Líneas transversales (no son características, pero se presupuestan aparte)

| Línea | Base | Con margen | Coste | Tokens (in / out) | Horas IA base | Motivo |
|---|---|---|---|---|---|---|
| Revisión adversarial | 192 h | 230,4 h | 11.520 € | 5,44 M / 0,47 M | 19,7 h | 1,0 × C-01, C-02, C-03 y C-04 (138 h) + C-08 (14 h a 1,0 × y 42 h a 0,5 × = 35 h) + 0,5 × C-05 y C-06 (19 h) |
| Mediciones previas | 13 h | 15,6 h | 780 € | 2,76 M / 0,24 M | 10,0 h | CA-16 (4 h IA), CA-09 (2,5 h), CA-24 (2 h), CA-27 (1,5 h): retro de la Iniciativa 3 |
| Revisión del diff de cada hito | 12 h | 14,4 h | 720 € | 2,07 M / 0,18 M | 7,5 h | 3 hitos × 2,5 h IA (≥ 2 h): retro de la Iniciativa 3 |
| Integración y cierres de hito | 12 h | 14,4 h | 720 € | 0,34 M / 0,03 M | 1,2 h | Suite completa, contratos regenerados, ledger archivado y PR, en tres hitos |
| Proceso (spec, evaluación, diseño y plan) | — | — | tokens | medido en `generacion:` | — | LES-008: coste de proceso aparte |

---

## Comparativa

Ordenada por el orden de trabajo recomendado. La columna de revisión es la parte de la línea «Revisión adversarial» que corresponde a cada característica; los tokens suman implementación y revisión.

| # | Característica | Hito | Complejidad | Horas (con margen) | Revisión asociada (con margen) | Coste € (desarrollo, sin revisión) | Tokens | Riesgo | Prioridad | Confianza |
|---|---------------|------|-------------|-------|-------|---------|--------|--------|-----------|-----------|
| C-01 | Credenciales | A | Alta | 60 h | 60 h | 3.000 € | 3,08 M | Alto | Crítica | Media |
| C-02 | Login | A | Media | 21,6 h | 21,6 h | 1.080 € | 1,11 M | Medio | Crítica | Media-Alta |
| C-03 | Límites por clave | B | Alta | 45,6 h | 45,6 h | 2.280 € | 2,34 M | Alto | Alta | Media-Baja |
| C-04 | Redacción | B | Media-Alta | 38,4 h | 38,4 h | 1.920 € | 1,97 M | Medio-Alto | Alta | Media |
| C-06 | Superficie de secretos | B | Baja-Media | 21,6 h | 10,8 h | 1.080 € | 0,83 M | Bajo-Medio | Media | Media-Alta |
| C-08 | Portal | C | Alta | 67,2 h | 42 h | 3.360 € | 2,80 M | Alto | Alta | Media-Baja |
| C-05 | Identidad y extensibilidad | A y C | Media | 24 h | 12 h | 1.200 € | 0,92 M | Medio | Alta | Media |
| C-07 | Revisión de seguridad y cierre | C | Media | 28,8 h | — | 1.440 € | 0,74 M | Medio | Crítica | Media-Baja |
| — | Revisión adversarial | A, B y C | — | 230,4 h | (es la suma de la columna) | 11.520 € | (incluidos arriba) | — | — | Media |
| — | Mediciones previas | A y B | — | 15,6 h | — | 780 € | 3,00 M | — | — | Media |
| — | Revisión del diff de hito | A, B y C | — | 14,4 h | — | 720 € | 2,25 M | — | — | Media |
| — | Integración y cierres | A, B y C | — | 14,4 h | — | 720 € | 0,37 M | — | — | Media |
| | **Total** | | | **582 h** | | **29.100 €** | **19,42 M** | | | |

**Corte propuesto en hitos, un PR por hito** (no quita alcance). La revisión se asigna al hito de cada característica.

| Hito | Contenido | Criterios de cierre del plan director | Implementación (base) | Revisión (base) | Mediciones, integración y revisión de hito (base) | Total con margen |
|---|---|---|---|---|---|---|
| A · acceso que se puede retirar | Test de CA-38 (a) (7 h de C-05), C-01, C-02; esquema 13 completo; medición de scrypt | 2 (revocación en todas las rutas, CA-11) y 3 (el login no se bloquea entre clientes, CA-13) | 75 h | 71,5 h | 11 h | **189 h · 9.450 €** |
| B · clientes acotados y secretos fuera | C-03, C-04, C-06; mediciones de perfil, entropía y coste; nota a la Iniciativa 7 | — (cierra S-01, S-08, S-10 y S-11) | 88 h | 79 h | 18 h | **222 h · 11.100 €** |
| C · portal, identidad y cierre | C-08, resto de C-05 (13 h), C-07; versión 0.4.2 | 1 (revisión de seguridad sin hallazgos altos, CA-34) | 93 h | 41,5 h | 8 h | **171 h · 8.550 €** |

> Suma de los tres hitos: 485 h base, 582 h y 29.100 € con margen. El hito B es el mayor y el único con cambios visibles para clientes; si su diff resulta difícil de revisar, C-06 puede adelantarse al hito A sin dependencias (A pasaría a 221,4 h y B a 189,6 h).

---

## Presupuesto total

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 485 h × 50 €/h (256 h de características + 192 h de revisión + 13 h de mediciones + 12 h de revisión de hito + 12 h de integración) | 24.250 € |
| Margen de contingencia | +20 % sobre desarrollo base (97 h) | 4.850 € |
| Tokens IA (input) | 17,86 M tok × precio input | ⚠️ verificar |
| Tokens IA (output) | 1,55 M tok × precio output | ⚠️ verificar |
| **Total estimado (con margen)** | 29.100 € + (17,86 × P_in + 1,55 × P_out) €, con P en €/1M tokens | **29.100 € + tokens ⚠️ verificar** |

> Variantes fuera del total. Si C-08 se revisa entera a 1,0 ×, la revisión sube 21 h base (+1.260 € con margen). Si el alta de usuarios pasa a ser solo del administrador global (ambigüedad 1), C-01 sube unas 3 h base por el cambio de comportamiento, sus tests y su nota (+360 € con margen y revisión). El paso de diseño con `architect` es coste de proceso y no está en el total.

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 582 h (485 h base) |
| Horas IA (ejecución) | 77,7 h (64,7 h base = 19,42 M tokens facturables ÷ 300.000 tok/h) |
| Supervisión humana | 19,4 h (25 % de 77,7 h) |
| **Horas totales (IA + supervisión)** | **97,1 h** |
| Horas ahorradas | 484,9 h |
| **Ahorro** | **83 %** |
| **Multiplicador de productividad** | **×6,0** |
| FTE equivalentes *(opcional)* | 3,0 |

> Horas con el margen del 20 % ya aplicado. Si se repite la cota inferior de la Iniciativa 3 (−36 %), las horas IA serían ≈ 49,7 h y la supervisión ≈ 12,4 h. No se aplica a la cifra nominal porque en las fases con horas registradas la desviación fue del −1 %. Las horas IA no incluyen el reloj de la suite en contenedor, de los ensayos en Compose aislado ni de la construcción de las imágenes de Chromium, que se ejecutan de uno en uno. Para que esta iniciativa calibre, cada `T-XX` **y cada intento de revisión** deben abrir y cerrar `usage-meter`, y conviene anotar las horas humanas de supervisión, que siguen sin registrarse.

---

## Recomendación

- **Veredicto**: **go con condiciones**, en tres hitos.
  1. **Decidir CA-42** antes del plan: el alta de usuarios, ¿sigue delegada a los administradores de proyecto o pasa a ser solo del administrador global? Es la única pregunta que puede necesitar al usuario.
  2. **Corregir en la spec la hipótesis de las pruebas de navegador** y declarar los dos niveles: DOM de frontera en `web/tests/` (CI) y Chromium real en `e2e_portal.py` (Docker local, con su equivalente local declarado en CA-37 y CA-39 a CA-42).
  3. **Pasar por `architect` antes de `planner`** (ver más abajo) y enmendar con su resultado las ambigüedades 3 a 7.
  4. **Medir primero en cada hito**: scrypt al empezar el A; perfil del cliente, entropía y coste de las reglas al empezar el B. Los valores numéricos siguen provisionales hasta entonces.
  5. **`usage-meter` por tarea y por intento de revisión**, con el ledger archivado al cerrar cada fase.
- **Paso de diseño con `architect`: recomendado.** La spec tiene `design: n/a` y deja al plan cinco decisiones que afectan a varios componentes a la vez. Tomarlas dentro de una fase es lo que produjo los bucles de revisión de las Iniciativas 2 y 3. Coste estimado: de 1 a 1,5 h IA, fuera del total.
  - **Frontera del resolvedor de permisos (CA-38).** Qué funciones «alimentan» a `_active` y `_require`, qué hacen los cinco lectores externos, cómo se expone `is_admin` al portal y cómo entrarían roles, grupos e inicio de sesión único solo con tablas nuevas. Es además un entregable (CA-38 c) y condiciona todas las rutas de C-01.
  - **Arquitectura de los límites (C-03).** Punto de enganche común para `/v1` y el `/mcp` interno, estado en memoria o en base para la cuota, exención de la validación de `kairos-mcp` sin una cabecera suplantable, transporte de `Retry-After` hasta el cliente sin tocar el contrato MCP y trato del tope de cinco intentos de la cola.
  - **scrypt y logins simultáneos (C-01).** Semáforo o cola, qué responde cuando está lleno y cómo evitar que el propio tope sirva para dejar sin login a los demás.
  - **Esquema 13 de una vez.** Lista completa de columnas e índices de los tres hitos, y qué datos necesita la lista de sesiones.
  - **Estrategia de pruebas del portal (C-08).** Qué se prueba en cada nivel y si el arnés de Chromium entra en la CI.
- **Quick wins** (bajo coste, alto valor):
  - C-06 (18 h base): independiente del resto, cierra S-10 y S-11.
  - C-02 (18 h base): cierra S-02 y el criterio de cierre 3 del plan director.
  - Dentro de C-01, caducidad al crear una clave y deshabilitar un usuario (unas 8 h base): el esquema y la autenticación ya los respetan, solo falta quien los escriba.
  - Dentro de C-04, el fichero de casos compartido con las siete cadenas de S-01 (unas 12 h base): cierra el oráculo de S-01 antes de abordar la entropía.
- **Costosas / a valorar**:
  - C-08 (56 h base y la confianza más baja): es la decisión P-02 del usuario, «todo en el portal». El arnés de navegador real es la mayor incógnita.
  - C-01 (50 h base, once criterios): es la base de todo lo demás; su riesgo es la caché de permisos.
  - C-03 (38 h base): la de diseño más abierto y la que toca los cuatro componentes.
  - La revisión adversarial (192 h base) es la partida mayor, el 40 % del total.
- **Orden sugerido**: test de CA-38 (a) → C-01 → C-02 (hito A) → C-06 → C-04 → C-03 (hito B) → C-08 → resto de C-05 → C-07 (hito C).
  - El test de CA-38 va primero para que ninguna ruta nueva decida permisos por su cuenta.
  - C-01 antes que C-02: comparten `auth.login`, y el tope de logins simultáneos debe existir antes de recontar los fallos.
  - En el hito B, C-06 abre por ser independiente y C-03 cierra por ser la de más diseño y la que depende de la medición más larga.
  - C-08 necesita las rutas de C-01; la guía de C-05 necesita los pasos del portal y la tabla de paridad de CA-43.
- **Fuera de alcance recomendado**: lo que ya excluye la spec. No se recomienda quitar ningún bloque: los tres criterios de cierre del plan director quedan repartidos entre los hitos A y C, y el B cierra cuatro hallazgos de la auditoría.

---

## Riesgos transversales

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **R-01 Caché de permisos sin vaciar**: un escritor nuevo (contraseña, deshabilitar, permisos, sesiones, rotación) que no llama a `invalidate_auth` deja viva una credencial retirada dentro de su transacción | Media | Alto | Registrar cada escritor nuevo en `test_auth_cache.py`; CA-11 prueba la revocación en las cuatro rutas; revisión a 1,0 × |
| **R-02 scrypt agota la memoria**: unos 128 MB por verificación con `n=2^17` en un contenedor de 1 GB, y el login no exige credencial; el tope de simultáneos puede servir a su vez para bloquear a otros | Media | Alto | Medir antes de fijar (CA-09); alternativa `n=2^16, p=2` (P-04); diseño del tope con `architect`; test con N = tope + 5 |
| **R-03 Diseño abierto de los límites**: cuota que se pierde al reiniciar, lectura de `kairos-mcp` que cuenta doble o exención que cualquiera puede invocar | Alta | Medio | Paso de diseño previo; medición del perfil real (CA-16); `0` desactiva cada límite (P-06) |
| **R-04 El cliente descarta capturas con un 429**: paso a `failed` al quinto intento y espera máxima de 60 s (`dispatcher.mjs:134-144`) | Alta | Alto | El 429 no consume intentos y fija `next_attempt_at` con `Retry-After`; test de cola con una cuota diaria agotada |
| **R-05 Redacción que consume CPU o rechaza de más**: expresiones regulares sobre texto no fiable en un proceso único; más rechazos de documentos | Media | Alto | Cota medida (CA-27) con entrada adversaria en los dos módulos; pedir en el primer fix trabajo acotado y prueba de tamaño máximo (aprendizaje 1 de la retro de la Iniciativa 2); ≥ 15 casos «no redactar»; nota a la Iniciativa 7 |
| **R-06 Arnés de navegador sin mantener**: `e2e_portal.py` no se ejecuta en la CI, su última evidencia es del 2026-11-06 y depende de etiquetas de imagen locales | Alta | Medio | Primera tarea de C-08: ejecutarlo tal cual y anotar su estado; 9 h presupuestadas; decidir con `architect` si entra en la CI |
| **R-07 Ficheros del árbol que usa la instalación desplegada**: `web/nginx.conf` y `docker-compose.yml` (aprendizaje 3 de la retro de la Iniciativa 2) | Media | Alto | `MEMORY_TRUSTED_PROXIES` vacío se comporta como hoy; el Compose avisa en lugar de caer en `./secrets`; ensayos con nombre de proyecto propio; CA-37 comprueba que nada apunta a `knowledge-graphs-*` |
| **R-08 Fixes encadenados en código de operación**: `deploy-memory.py` (29 cambios en 90 días, 1.638 líneas) y `admin.py` (19 cambios, 545 líneas) | Media | Medio | Cada fix se revisa con lentes completas y suma un intento (CA-35); validación del directorio antes de cualquier fase, sin efectos |
| **R-09 Bucles de revisión**: hasta seis intentos en una fase de la Iniciativa 2 y cinco en una de la 3 | Alta | Medio | Revisión como partida propia (230,4 h con margen); corregir la clase entera en el primer fix; `usage-meter` por intento |
| **R-10 Tests con tiempo**: caducidad, gracia, ventanas, cuotas y `Retry-After`; el vencimiento se decide con `clock_timestamp()` en SQL | Alta | Medio | Fechar filas hacia atrás para caducidad y gracia; reloj inyectado en el cubo y la cuota; nada de `sleep` para esperar un estado |
| **R-11 CA-38 sin definición operativa**: cinco lectores de permisos fuera del resolvedor | Media | Medio | Definir en el diseño qué es «decidir un acceso» y la lista cerrada de excepciones, antes del test |
| **R-12 Cambio de comportamiento no declarado**: restringir el alta de usuarios (CA-42) o los rechazos nuevos de la redacción | Media | Medio | Decisión explícita sobre CA-42; CHANGELOG y nota a la Iniciativa 7 (CA-26); el contrato MCP no cambia |
| **R-13 Esquema 13 reabierto entre hitos** | Media | Bajo | Todas las columnas en el hito A; `test_migrations_additive.py` en cada cierre |

---

## Siguiente paso

Para **ejecutar** lo aprobado, se recomienda primero el paso de diseño con **`architect`** sobre las cinco decisiones de «Recomendación», y después generar el plan con el agente **`planner`**, que crea `improvement-plan.md` y `tasks.md` en `docs/roadmap/2026-11-19-access-control/`. Se recomienda aprobar **las ocho características**, en tres hitos con un PR cada uno: A (test de CA-38 → C-01 → C-02), B (C-06 → C-04 → C-03) y C (C-08 → resto de C-05 → C-07). El `planner` hereda horas y costes por característica y no re-estima desde cero. Además:

- presupuesta la revisión por fase (1,0 × en C-01 a C-04 y en la parte de autorización de C-08; 0,5 × en el resto);
- pone las cuatro mediciones como tareas propias al principio de su hito (10 h IA en total);
- pone la revisión del diff de cada hito como tarea propia de 2,5 h IA;
- suma un intento de revisión por cada fix en `deploy-memory.py` y `admin.py`;
- exige `usage-meter` por `T-XX` y por intento de revisión;
- actualiza la fila **Plan** de esta evaluación y el campo `plan:` de la spec.

---

## Changelog

- 2026-11-19 — Creación (evaluator). Estado `en-revision`. La spec no se ha modificado, por indicación del orquestador: su campo `evaluacion:` y su aviso de cabecera siguen en «pendiente» hasta que el orquestador los enlace.
