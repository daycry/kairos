---
design: design.md
test-plan: test-plan.md
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
---

# 2026-11-19-access-control

> Control de acceso y privacidad de Kairos: credenciales que se pueden dar, acotar, renovar y retirar con efecto inmediato en todas las rutas; login que no se bloquea entre clientes; límites por clave; redacción de secretos ampliada y compartida entre servidor y cliente; guía de identidad probada; y toda la gestión de acceso en el portal (Iniciativa 4 del plan director).

| | |
|---|---|
| **Fecha** | 2026-11-20 |
| **Estado** | borrador |
| **Tipo** | Nueva Funcionalidad |
| **Prioridad** | Alta |
| **Solicitante** | Daycry (plan director, Iniciativa 4) |
| **Responsable** | Daycry |
| **Spec** | [`spec.md`](spec.md) — aprobada, 43 criterios (A-01 a A-08), decisiones confirmadas 1 a 9 |
| **Evaluación** | [`evaluation.md`](evaluation.md) — go con condiciones, 3 hitos, un PR por hito |
| **Diseño** | [`design.md`](design.md) — opción elegida O2 «Costuras de acceso»; decisiones comunes DC-1 a DC-10 |

---

## Cuadro de mando

| Métrica | Estimado | Real | Confianza |
|--------|---------|------|-----------|
| Tiempo humano | **616,2 h** (513,5 h base +20 %), de ellas 242,4 h de revisión adversarial | 0 h | Media-Baja |
| Tiempo IA (ejecución) | **82,8 h** (69,0 h base +20 %) (+ 20,7 h supervisión) | 0 h | Media-Baja |
| Coste total | **30.810 €** de desarrollo + tokens ⚠️ verificar | 0 € | Media-Baja (desarrollo) / sin cifra (tokens) |
| Tokens IA | **20,70 M** (in 19,04 M / out 1,66 M) | 0 | Baja |
| Multiplicador productividad | **×6,0** | — | — |
| Tareas | **106** en 18 fases y 3 hitos | 0 hechas | — |

> **Frente a la evaluación** (582 h, 29.100 €, 19,42 M tokens, 77,7 h IA): **+34,2 h, +1.710 €, +1,28 M tokens y +5,1 h IA**. El plan hereda las cifras por característica y no re-estima. La diferencia es el trabajo que la evaluación no contó y que el diseño (sección 6) dejó al planner:
>
> | Origen | Qué añade | Implementación (base) | Revisión (base) | Horas IA (base) | Tareas |
> |---|---|---|---|---|---|
> | O2 en C-05 | Cálculo y publicación de `capabilities` en `/v1/auth/me`, su test acción → ruta y la lista de módulos autorizados a escribir en `test_auth_cache.py` | +6,0 h | +3,0 h (0,5 ×) | +0,92 h | T-02 (1 h), T-72 (5 h) |
> | O2 en C-08 | Dos módulos de portal (`access-panel.ts`, `account-panel.ts`) y el DOM de frontera compartido entre tests | +8,0 h | +4,0 h (0,5 ×) | +1,23 h | T-74 (3 h); T-78, T-79 y T-84 a T-86 (5 h) |
> | Aclaración 2 del usuario (C-03) | Comando `admin set-key-limits` y forma de `api_keys.limits` | +3,0 h | +3,0 h (1,0 ×) | +0,62 h | T-57 |
> | Aclaración 3 del usuario (medición) | scrypt medido también en `memory-bootstrap` (256 MB) y `memory-admin` | +1,5 h | — | +1,50 h | T-01 |
> | **Total** | | **+18,5 h** | **+10,0 h** | **+4,27 h** | |
>
> Con margen: 28,5 h base × 1,2 = 34,2 h humanas (1.710 €) y 4,27 h × 1,2 = 5,1 h IA. C-01, C-02, C-04, C-06 y C-07 no cambian. Por hito: A 192,6 h (evaluación 189 h), B 229,2 h (222 h) y C 194,4 h (171 h). Horas humanas e IA no se suman (LES-007).

---

## Estimación por fase

| Fase | Hito | Tareas | Estimado (h, con margen) | De ellas, revisión (h) | Horas IA (con margen) | Tokens (in / out) | Coste € |
|------|------|--------|-------------|-----|-----|-------------------|---------|
| Fase 1 — Medición de scrypt y guarda del resolvedor (CA-09, CA-38 a) | A | 5 | 19,8 | 4,8 | 6,3 | 1444 k / 126 k | 990 |
| Fase 2 — Esquema 13, scrypt y contraseñas (C-01) | A | 7 | 36,0 | 18,0 | 3,7 | 850 k / 74 k | 1.800 |
| Fase 3 — Usuarios, permisos y sesiones (C-01) | A | 6 | 36,0 | 18,0 | 3,7 | 850 k / 74 k | 1.800 |
| Fase 4 — Claves: caducidad, último uso, rotación y `kairos doctor` (C-01) | A | 7 | 48,0 | 24,0 | 4,9 | 1133 k / 99 k | 2.400 |
| Fase 5 — Login que no se bloquea entre clientes (C-02) | A | 5 | 43,2 | 21,6 | 4,4 | 1020 k / 89 k | 2.160 |
| Fase 6 — Cierre del hito A: acceso que se puede retirar | A | 4 | 9,6 | 0,0 | 3,5 | 803 k / 70 k | 480 |
| Fase 7 — Mediciones del hito B y superficie de secretos (C-06) | B | 8 | 44,4 | 10,8 | 12,3 | 2835 k / 247 k | 2.220 |
| Fase 8 — Redacción: casos compartidos, patrones y entropía (C-04) | B | 6 | 42,0 | 21,0 | 4,3 | 992 k / 86 k | 2.100 |
| Fase 9 — Redacción en todas las rutas y de extremo a extremo (C-04) | B | 5 | 34,8 | 17,4 | 3,6 | 822 k / 71 k | 1.740 |
| Fase 10 — Límites en el servidor: clases, tasa, cuota y flujos (C-03) | B | 7 | 60,0 | 30,0 | 6,2 | 1417 k / 123 k | 3.000 |
| Fase 11 — Límites en `kairos-mcp` y en el cliente (C-03) | B | 6 | 38,4 | 19,2 | 3,9 | 907 k / 79 k | 1.920 |
| Fase 12 — Cierre del hito B: clientes acotados y secretos fuera | B | 4 | 9,6 | 0,0 | 3,5 | 803 k / 70 k | 480 |
| Fase 13 — Capacidades del servidor y base del portal (C-05, C-08) | C | 7 | 35,7 | 14,1 | 3,7 | 843 k / 73 k | 1.785 |
| Fase 14 — Portal: «Mi cuenta» y «Claves para agentes» (C-08) | C | 6 | 42,3 | 14,7 | 4,3 | 999 k / 87 k | 2.115 |
| Fase 15 — Portal: «Usuarios», alta delegada y paridad (C-08) | C | 9 | 54,6 | 21,0 | 5,6 | 1289 k / 112 k | 2.730 |
| Fase 16 — Identidad: guía probada y extensibilidad (C-05) | C | 5 | 23,4 | 7,8 | 2,4 | 553 k / 48 k | 1.170 |
| Fase 17 — Revisión del hito C y revisión de seguridad (C-07) | C | 5 | 27,0 | 0,0 | 5,3 | 1214 k / 106 k | 1.350 |
| Fase 18 — Cierre del hito C y de la iniciativa: ensayo, versión 0.4.2 y PR | C | 4 | 11,4 | 0,0 | 1,2 | 269 k / 24 k | 570 |
| **Total** | | **106** | **616,2 h** | **242,4 h** | **82,8 h** | **19043 k / 1658 k** | **30.810 €** |

Reparto por característica (horas base de implementación; entre paréntesis, la evaluación cuando difiere): C-05 26 h (20 h) en las fases 1, 13 y 16 · C-01 50 h en las fases 2, 3 y 4 · C-02 18 h en la fase 5 · C-06 18 h en la fase 7 · C-04 32 h en las fases 8 y 9 · C-03 41 h (38 h) en las fases 10 y 11 · C-08 64 h (56 h) en las fases 13, 14 y 15 · C-07 24 h en las fases 17 y 18 = 273 h. Mediciones previas 14,5 h (13 h). Revisión del diff de cada hito 12 h. Integración y cierres de hito 12 h. Revisión adversarial 202 h (192 h): 1,0 × C-01, C-02, C-03 y C-04 (141 h), 1,0 × la autorización de C-08 (14 h), 0,5 × el resto de C-08 (25 h), 0,5 × C-05 (13 h) y 0,5 × C-06 (9 h). Total 513,5 h base.

Cada fase de implementación termina con una tarea de cierre (suites y mínimo de pruebas en los cuatro sitios) y con su revisión adversarial como tarea propia. Cada hito termina con su ensayo aislado, la revisión de su diff completo (2,5 h IA) y su PR.

---

## Presupuesto económico

**Coste = (horas × tarifa) + coste de tokens de IA.** Todos los importes en **EUR**.

### Supuestos (ajustables)

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Tarifa de desarrollo | 50 €/h | Valor por defecto del kit (no hay `.claude/rates.json`) |
| Modelo IA asumido | Claude (familia vigente en el ciclo) | Igual que la evaluación |
| Precio input | ⚠️ verificar € / 1M tokens | Sin `precioTokens` fiable; ejecutar la skill `rates-verify` |
| Precio output | ⚠️ verificar € / 1M tokens | Ídem |
| Tipo de cambio | 1 USD = 0,92 € | Valor por defecto del kit |
| Margen de contingencia | 20 % | Sobre horas base humanas e IA, revisión incluida |
| Supervisión humana | 25 % de las horas IA | Valor por defecto |
| Ratio tokens→hora IA | 300.000 tok/h facturables | Default no calibrado: `CALIBRATION.md` no tiene ningún ratio medido |
| Tokens de implementación, revisión e integración | 30.800 facturables por hora humana base (92 % entrada / 8 % salida) | Heredado de la evaluación |
| Mediciones previas | 11,5 h IA (3,45 M tokens): CA-09 4,0 h, CA-16 4,0 h, CA-24 2,0 h y CA-27 1,5 h | Evaluación (10 h) más 1,5 h por los dos contenedores añadidos a CA-09 |
| Revisión del diff de cada hito | 2,5 h IA por hito (2,25 M tokens en total) | Evaluación; retro de la Iniciativa 3 (≥ 2 h) |
| Revisión adversarial | 1,0 × en C-01 a C-04 y en la autorización de C-08; 0,5 × en el resto | Retros de las Iniciativas 2 y 3 |

### Desglose

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 513,5 h × 50 €/h (273 h de características + 202 h de revisión + 14,5 h de mediciones + 12 h de revisión de hito + 12 h de integración) | 25.675 € |
| Margen de contingencia | +20 % sobre desarrollo base (102,7 h) | 5.135 € |
| Tokens IA (input) | 19,04 M tok × precio | ⚠️ verificar |
| Tokens IA (output) | 1,66 M tok × precio | ⚠️ verificar |
| **Total estimado (con margen)** | | **30.810 € + tokens ⚠️ verificar** |

> Las horas humanas nunca se han registrado en este proyecto: el importe es el valor nominal del trabajo, no un gasto previsto.

---

## Previsión de tokens (por fase)

Base: Claude (familia vigente); precios sin verificar.

| Fase | Input (tok) | Output (tok) | Total (tok) | Coste € |
|------|------------|-------------|-------------|---------|
| Fase 1 | 1444 k | 126 k | 1570 k | ⚠️ verificar |
| Fase 2 | 850 k | 74 k | 924 k | ⚠️ verificar |
| Fase 3 | 850 k | 74 k | 924 k | ⚠️ verificar |
| Fase 4 | 1133 k | 99 k | 1232 k | ⚠️ verificar |
| Fase 5 | 1020 k | 89 k | 1109 k | ⚠️ verificar |
| Fase 6 | 803 k | 70 k | 873 k | ⚠️ verificar |
| Fase 7 | 2835 k | 247 k | 3082 k | ⚠️ verificar |
| Fase 8 | 992 k | 86 k | 1078 k | ⚠️ verificar |
| Fase 9 | 822 k | 71 k | 893 k | ⚠️ verificar |
| Fase 10 | 1417 k | 123 k | 1540 k | ⚠️ verificar |
| Fase 11 | 907 k | 79 k | 986 k | ⚠️ verificar |
| Fase 12 | 803 k | 70 k | 873 k | ⚠️ verificar |
| Fase 13 | 843 k | 73 k | 916 k | ⚠️ verificar |
| Fase 14 | 999 k | 87 k | 1086 k | ⚠️ verificar |
| Fase 15 | 1289 k | 112 k | 1401 k | ⚠️ verificar |
| Fase 16 | 553 k | 48 k | 601 k | ⚠️ verificar |
| Fase 17 | 1214 k | 106 k | 1320 k | ⚠️ verificar |
| Fase 18 | 269 k | 24 k | 293 k | ⚠️ verificar |
| **Total** | **19043 k** | **1658 k** | **20701 k** | **⚠️ verificar** |

**Método de estimación:** se hereda el método de la evaluación. Implementación, revisión e integración: 30.800 tokens facturables por hora humana base. Mediciones y revisión de hito: horas IA propias × 300.000. Tokens facturables = entrada no cacheada + creación de caché + salida. Las cifras por tarea son orientativas; cada tarea y cada intento de revisión se miden con `usage-meter`.

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 616,2 h (513,5 h base +20 %) |
| Horas IA (ejecución) | 82,8 h (69,0 h base +20 %; supuesto: 20,70 M tok ÷ 300.000 tok/h) |
| Supervisión humana | 20,7 h (25 % de las horas IA) |
| **Horas totales (IA + supervisión)** | **103,5 h** |
| Horas ahorradas | 512,7 h |
| **Ahorro** | **83 %** |
| **Multiplicador de productividad** | **×6,0** |
| FTE equivalentes *(opcional)* | 3,2 |

> Horas con el margen del 20 % ya aplicado. Las horas IA son una estimación y no incluyen el reloj de la suite en contenedor, de los ensayos en Compose aislado ni de la construcción de las imágenes de Chromium, que se ejecutan de uno en uno. Si se repite la cota inferior de la Iniciativa 3 (−36 %), serían ≈ 53 h IA.

---

## Resumen ejecutivo

Kairos va a un VPS y lo usarán el usuario y de dos a cinco personas más, desde varias máquinas. Hoy el acceso se puede conceder, pero casi no se puede retirar ni renovar, un cliente puede dejar sin login a los demás y el filtro de secretos tiene huecos. Este plan lo corrige en tres hitos, con un PR por hito:

- **A «acceso que se puede retirar»** (fases 1 a 6): guarda del resolvedor de permisos, esquema 13 completo, scrypt reforzado, contraseña, usuarios, permisos, sesiones, claves con caducidad y rotación, y login que cuenta solo fallos y bloquea por IP real.
- **B «clientes acotados y secretos fuera»** (fases 7 a 12): superficie de secretos, redacción ampliada con casos compartidos y detector de entropía, y límites por clave en el servidor, en `kairos-mcp` y en el cliente.
- **C «portal, identidad y cierre»** (fases 13 a 18): `capabilities`, las tres secciones del portal, guía de identidad probada, revisión de seguridad y versión 0.4.2.

Son 106 tareas en 18 fases. El plan respeta la opción O2 del diseño y sus diez decisiones comunes. Las cuatro mediciones previas van al principio de su hito, antes de fijar ningún valor numérico.

### Objetivos

- Toda credencial retirada (clave revocada, caducada o de un usuario deshabilitado; sesión cerrada) recibe 401 en la petición siguiente en `/v1`, en los dos `/mcp`, en un flujo abierto y en el portal (CA-01 a CA-11).
- Diez fallos de login de un cliente no bloquean a otro (CA-12 a CA-15).
- Cada clave tiene tasa, cuota diaria y tope de flujos; un 429 no hace perder capturas (CA-16 a CA-21).
- Las siete cadenas de S-01 no llegan a la base, a la cola del cliente ni a los logs (CA-22 a CA-27).
- Guía de alta y baja ejecutada por un test, y modelo de permisos ampliable solo con tablas o columnas nuevas (CA-28 a CA-30, CA-38).
- Directorio de secretos y fichero de clave validados (CA-31 a CA-33).
- Toda la gestión de acceso en el portal, con su equivalente por API o comando (CA-39 a CA-43).
- Revisión de seguridad sin hallazgos altos abiertos y cierre con contratos y migraciones solo aditivos (CA-34 a CA-37).

---

## Datos necesarios para un informe completo

- [x] **Requisitos funcionales** confirmados por el solicitante (spec `aprobada`; decisiones 1 a 9)
- [x] **Alcance** cerrado (spec §Alcance: dentro A-01 a A-08; fuera HTTPS, despliegue real, roles, OAuth y segundo factor)
- [x] **Criterios de éxito / métricas** acordados (CA-01 a CA-43 y los tres criterios de cierre del plan director)
- [x] **Accesos y credenciales** necesarios (ninguno: fixtures aislados y secretos sintéticos)
- [x] **Entornos** disponibles (PostgreSQL efímero del target `test`, proxy simulado y nginx real de prueba, Chromium en `Dockerfile.e2e`, proyectos Compose `kairos-acc-*`)
- [x] **Stakeholders** identificados (solicitante único; coordinación con la Iniciativa 7)
- [ ] **Dependencias externas** mapeadas: OK del usuario para los tres PR; la CI externa puede no ejecutarse; el VPS con una sola réplica de `memory-api` es hipótesis hasta la Iniciativa 5
- [x] **Restricciones** conocidas (sin pruebas contra lo desplegado, migraciones y contratos aditivos, nada publicado, Docker de uno en uno)
- [ ] **Tarifa/hora y supuestos de coste** confirmados (valor por defecto 50 €/h; precio de tokens ⚠️ verificar)
- [ ] **Valores numéricos definitivos**: se fijan en T-01, T-35, T-36 y T-37 (tabla «Valores medidos»)

### Valores medidos

Los rellenan las tareas de medición antes de que ninguna tarea fije un valor. Hasta entonces valen los provisionales de la spec.

| Valor | Provisional (spec) | Medido / definitivo | Margen declarado | Tarea |
|---|---|---|---|---|
| Coste de scrypt (`n`, `r`, `p`) | `n=2^17, r=8, p=1`; alternativa `n=2^16, p=2` | pendiente | — | T-01 |
| Huecos de `MEMORY_LOGIN_CONCURRENCY` | según la memoria medida | pendiente | pendiente | T-01 |
| `MEMORY_BOOTSTRAP_MEM_LIMIT` | 256 MB | pendiente | pendiente | T-01 |
| ¿`hashlib.scrypt` libera el GIL? Memoria de la API en reposo | hipótesis | pendiente | — | T-01 |
| Tasa y ráfaga por credencial (`MEMORY_RATE_LIMIT_*`) | sin valor | pendiente | pendiente | T-35 |
| Cubo de la clase `identity` | sin valor | pendiente | pendiente | T-35 |
| Cuota diaria (`MEMORY_WRITE_QUOTA_PER_DAY`) y lote de escritura | lote de 20 | pendiente | pendiente | T-35 |
| Flujos por credencial y global | 4 / 50 | pendiente | pendiente | T-35 |
| Umbral y longitud mínima del detector de entropía | sin valor | pendiente | objetivo: 0 redacciones en el corpus sin secretos | T-36 |
| Cota de tiempo de las reglas (servidor y cliente) | sin valor | pendiente | pendiente | T-37 |

---

## Análisis de impacto

- **`server/memory_platform/`** — módulos nuevos `store_access.py`, `passwords.py` y `limits.py`; cambios en `store_auth.py`, `store.py`, `auth.py`, `app.py`, `mcp.py`, `activity.py`, `errors.py`, `models.py`, `admin.py`, `config.py`, `observability.py`, `privacy.py`, `store_ingest.py`, `store_documents.py`, `agent_store.py`, `extended_store.py`, `corpus_answers.py` y `schema.sql` (versión 13).
- **`mcp/kairos_mcp/`** — sin cambio de comportamiento; pruebas que fijan el texto del 429 y el contrato intacto.
- **`client/lib/`** — `mcp.mjs` (mensajes de límite, `doctor --online`, `credential.json`), `dispatcher.mjs` (el 429 no consume intentos), `privacy.mjs`, `files.mjs`, `errors.mjs`, `config.mjs` (versión).
- **`web/`** — módulos nuevos `src/access-panel.ts` y `src/account-panel.ts`; `src/memory-portal.ts` pasa a montarlos; `src/memory-api.ts`, `src/memory-types.ts`, `src/memory-portal.css`; `nginx.conf` envía `X-Forwarded-For`; `tests/boundary-dom.mjs` y tests por módulo.
- **`docker-compose.yml`**, **`scripts/deploy-memory.py`** — variables nuevas, sin `./secrets` por defecto, validación del directorio de secretos. La instalación desplegada recoge los cambios en su próximo `up`; ninguna tarea lo ejecuta.
- **`scripts/`** — `measure-scrypt.py`, `measure-request-profile.py`, `rehearse-access-control.py` y sus pruebas; `tests/test_portal_parity.py`.
- **`docs/contracts/`** — `memory-platform.openapi.json` crece de forma aditiva; `redaction-cases.json` nuevo; `kairos-mcp.json` no cambia.
- **`docs/`**, **`CHANGELOG*.md`**, versiones — guía `docs/identity.md`, `configuration.md`, `operations.md`, `architecture.md`, `integration.md`, `manual.md`, `server-install.md`; versión 0.4.2.
- **`.github/workflows/ci.yml`**, **`scripts/tests/test_ci_workflow.py`**, **`README.md`**, **`docs/operations.md`** — mínimo de la suite en cada cierre de fase.

---

## Cambios arquitectónicos

La arquitectura es la de [`design.md`](design.md), opción **O2 «Costuras de acceso»**. El plan no la rediseña; la reparte en tareas:

- **Tres costuras** (design §O2): `store_access.py` con `_access_changed` para todo cambio de acceso (T-09 y siguientes), `capabilities` en `/v1/auth/me` para lo que enseña el portal (T-72) y `limits.py` para los límites, con el estado en memoria del proceso y la cuota en `api_keys` (T-54 a T-58).
- **DC-1** resolvedor y lista cerrada de excepciones: T-02 y T-03, primeras tareas del hito A. **DC-2** un solo constructor del 429: nace en T-26 con el bloqueo de login y crece en el hito B. **DC-3** clases de ruta: T-54. **DC-4** el 429 es una espera en el cliente: T-61 y T-62. **DC-5** semáforo de logins: T-07 y T-08. **DC-6** esquema 13 de una vez: T-06. **DC-7** `doctor` y `credential.json`: T-21. **DC-8** «Mi cuenta» y alta delegada: T-78 y T-86. **DC-9** portal en dos niveles: T-71, T-74, T-80, T-81, T-87 y T-90. **DC-10** `admin` sobre los escritores del store: T-10, T-13 y T-57.
- **Orden** (evaluación): guarda de CA-38 → C-01 → C-02 (hito A); C-06 → C-04 → C-03 (hito B); C-08 → resto de C-05 → C-07 (hito C).
- **Decisiones que toma el plan**, dentro de lo que el diseño dejó al planner (sección 7):
  - `limits.py` nace en el hito A solo con el constructor del 429, porque el bloqueo de login por IP ya lo necesita (DC-2).
  - El fichero de casos de redacción es `docs/contracts/redaction-cases.json`, como propone el diseño.
  - El test de paridad de CA-43 vive en `scripts/tests/`, porque ninguna imagen de test contiene a la vez `web/src/` y `docs/contracts/`.
  - La revisión de seguridad de CA-34 se hace con las lentes del agente `reviewer`, no con `nemesis` (ver T-99 y el riesgo N-06).

---

## Archivos a crear/modificar

La tabla completa por fichero es la sección 5 de [`design.md`](design.md). Aquí va agrupada, con lo que el plan añade.

| Archivo | Acción | Propósito |
|---------|--------|-----------|
| `server/memory_platform/{store_access,passwords,limits}.py` | Crear | Escritores de acceso y `capabilities`; scrypt y semáforo; clases de ruta, tasa, cuota, flujos y 429 |
| `server/memory_platform/{store_auth,store,auth,app,mcp,activity,errors,models,admin,config,observability}.py` | Modificar | Resolvedor ampliado, rutas nuevas, cobro de límites, IP real, subcomandos `admin`, métricas |
| `server/memory_platform/{privacy,store_ingest,store_documents,agent_store,extended_store,corpus_answers}.py` | Modificar | Patrones nuevos, detector de entropía y redacción en todas las rutas que guardan texto |
| `server/memory_platform/schema.sql` | Modificar | Versión 13: columnas e índices de DC-6, sin tablas nuevas |
| `server/memory_platform/tests/test_{passwords,access_password,access_users,access_sessions,access_keys,revocation_matrix,login_limits,client_ip,login_proxy,limits,limits_quota,limits_streams,chain_limits,redaction_cases,redaction_routes,capabilities,access_authz,identity_guide}.py`, `measure_redaction.py` | Crear | Pruebas por área y medición de la redacción |
| `server/memory_platform/tests/{test_auth_cache,test_migrations_additive,test_contract_additive,test_admin,test_privacy,test_compose_limits,test_deploy,test_versions,e2e_portal,e2e_fixture,test_e2e_fixture,store_surface.json}` | Modificar | Guardas, migración 13, contratos, despliegue, Chromium y superficie del store (solo crece) |
| `mcp/kairos_mcp/client.py`, `mcp/tests/{test_limits,stub_api,tool_cases,test_health}.py` | Modificar | Texto estable del 429 y contrato intacto |
| `client/lib/{mcp,dispatcher,outbox,privacy,files,errors,lifecycle-config,config}.mjs`, `client/tests/*.test.mjs`, `client/tests/{redaction-cases.test,measure-redaction}.mjs`, `client/package.json` | Modificar/Crear | 429 como espera, `doctor`, redacción, permisos del fichero de clave, versión |
| `web/src/{access-panel,account-panel}.ts`, `web/tests/{boundary-dom,access-panel.test,account-panel.test}.mjs` | Crear | Módulos del portal y sus pruebas sobre el DOM compartido |
| `web/src/{memory-portal,memory-api,memory-types}.ts`, `web/src/memory-portal.css`, `web/tests/*.test.mjs`, `web/nginx.conf` | Modificar | Montaje, cliente HTTP, tipos, estilos y `X-Forwarded-For` |
| `docker-compose.yml`, `scripts/deploy-memory.py` | Modificar | Variables nuevas, sin `./secrets`, `secrets_dir_unsafe` |
| `scripts/{measure-scrypt,measure-request-profile,rehearse-access-control}.py`, `scripts/tests/{test_rehearse_access_control,test_portal_parity}.py` | Crear | Mediciones, ensayos aislados y paridad portal ↔ OpenAPI |
| `docs/contracts/memory-platform.openapi.json`, `docs/contracts/redaction-cases.json` | Modificar/Crear | Contrato aditivo y casos de redacción compartidos |
| `docs/identity.md` | Crear | Guía de identidad con la tabla de paridad |
| `docs/{configuration,operations,architecture,integration,manual,server-install,index}.md`, `CHANGELOG*.md`, `README.md` | Modificar | Manuales, notas de cambio y mínimo de pruebas |
| `.github/workflows/ci.yml`, `scripts/tests/test_ci_workflow.py` | Modificar | `KAIROS_MIN_TESTS` y `MIN_FLOOR` en cada cierre de fase |
| `server/VERSION`, `mcp/VERSION`, `client/package.json`, `client/lib/config.mjs` | Modificar | Versión 0.4.2 |

No se aplican `interop/**` ni las piezas de `docs/agents/CONTRACTS.md`: este repositorio no es el kit de agentes. Ninguna tarea escribe en `docs/roadmap/**/testing/`.

---

## Dependencias y prerequisitos

- **Orden entre fases:** 1 → 2 → … → 18. Hito A = fases 1 a 6; hito B = fases 7 a 12; hito C = fases 13 a 18. La fase 2 necesita la medición de T-01 y la guarda de T-02. Las fases 3 y 4 necesitan `store_access.py` (T-09). La fase 5 necesita el semáforo (T-08). Las fases 8 a 11 necesitan las mediciones de la fase 7. La fase 10 usa las columnas `limits` y `write_quota_*` creadas en T-06. Las fases 14 y 15 necesitan las rutas del hito A, `capabilities` (T-72) y el DOM compartido (T-74). La fase 16 necesita la tabla de paridad (T-88).
- **Externa:** OK expreso del usuario para abrir cada PR (T-34, T-70 y T-106); sin merges a `main` ni publicación.
- **Externa:** la CI de GitHub puede no ejecutarse. Cada criterio «en la CI» tiene su equivalente local en Docker.
- **Hipótesis a confirmar pronto:** scrypt con el coste objetivo cabe en `memory-bootstrap` (T-01); `hashlib.scrypt` libera el GIL (T-01); el `/mcp` interno autentica con las mismas funciones que `/v1` (T-22); el arnés de Chromium vuelve a verde con poco trabajo (T-71); `store_surface.json` admite métodos nuevos (T-09).
- **Memoria técnica:** el ADR propuesto por el diseño (`docs/knowledge/candidates/pending/2026-11-20-access-seams-server-capabilities.md`, SHA-256 `82c84969…7635`) está registrado en el bloque `curation-refs-v1` de `tasks.md`, a la espera de `knowledge-curator`. Las dos propuestas pendientes de la retro de la Iniciativa 3 se aplican como reglas del plan: cada fix se revisa como código nuevo y un servicio se recrea con los mismos `-f` de Compose.
- **Coordinación:** los cambios visibles para clientes se declaran a la Iniciativa 7 en los CHANGELOG. Son: (1) 429 `rate_limited`, `quota_exceeded` y `too_many_streams` con `Retry-After`, activos por defecto (`0` los desactiva), con los mensajes fijos `Rate limit exceeded [code=rate_limited retry_after=N]`, `Daily write quota exceeded […]` y `Too many activity streams […]`, que a través de `kairos-mcp` llegan como error de herramienta `isError` (T-55 a T-58, T-61, T-64); (2) más rechazos de documentos y de estado de trabajo con secretos, con los códigos actuales (`sensitive_source_requires_review` u homólogo), y más texto redactado en capturas (T-44 a T-51); (3) login: cuenta solo fallos, bloquea por IP y no por usuario, y puede responder 503 `login_busy` (T-08, T-26); (4) campos nuevos y opcionales en `/v1/auth/me` (`key`, `capabilities`) y en la lista de claves (`expires_at`, `last_used_at`), y rutas nuevas de `/v1` (T-09 a T-20, T-72); (5) `MEMORY_TRUSTED_PROXIES` y `X-Forwarded-For` en el proxy web (T-27); (6) cliente 0.4.2: el 429 no consume intentos, `doctor --online` lee `/v1/auth/me` y guarda `credential.json`, y `key_file_too_open` en POSIX (T-21, T-40, T-62); (7) despliegue: `secrets_dir_unsafe` y Compose sin `./secrets` por defecto (T-38, T-39). El contrato MCP (`kairos-mcp.json`) no cambia. Cada cierre de hito (T-33, T-69, T-104) repasa esta frase y la completa con los códigos, eventos y variables que hayan aparecido.

---

## Criterios de aceptación (global)

- [ ] Una credencial retirada recibe 401 en la petición siguiente en `/v1`, en los dos `/mcp`, en un flujo abierto y en el portal, demostrado en el ensayo aislado (CA-01 a CA-11; criterio de cierre 2 del plan director)
- [ ] Diez fallos de login de un cliente no bloquean a otro, a través del proxy web (CA-12 a CA-15; criterio de cierre 3)
- [ ] Límites por clave medidos y activos; un 429 no pierde capturas; el contrato MCP no cambia (CA-16 a CA-21)
- [ ] Redacción ampliada con casos compartidos por servidor y cliente, detector conservador y cota medida (CA-22 a CA-27)
- [ ] Guía de identidad ejecutada por un test y extensibilidad comprobable (CA-28 a CA-30, CA-38)
- [ ] Superficie de secretos acotada (CA-31 a CA-33)
- [ ] Toda la gestión de acceso en el portal, probada en los dos niveles, con paridad frente al OpenAPI (CA-39 a CA-43)
- [ ] Revisión de seguridad con cero hallazgos altos abiertos; cada fix revisado como código nuevo; cada hallazgo con su test (CA-34 a CA-36; criterio de cierre 1)
- [ ] Migraciones y contratos solo aditivos, nada contra recursos `knowledge-graphs-*`, nada publicado, suites con 0 fallos y 0 omitidos, versión 0.4.2 (CA-37)

### Mapa criterio → tareas

CA-35 lo cubren todas las tareas de revisión y CA-37 todos los cierres de fase y de hito; se listan sus tareas principales.

| CA | Tareas |
|----|--------|
| CA-01 | T-09 |
| CA-02 | T-10 |
| CA-03 | T-13 |
| CA-04 | T-14 |
| CA-05 | T-15 |
| CA-06 | T-19 |
| CA-07 | T-20 |
| CA-08 | T-21 |
| CA-09 | T-01, T-07, T-08 |
| CA-10 | T-06, T-33 |
| CA-11 | T-16, T-22, T-31, T-103 |
| CA-12 | T-26 |
| CA-13 | T-26, T-28, T-31, T-103 |
| CA-14 | T-27, T-28 |
| CA-15 | T-26, T-27 |
| CA-16 | T-35, T-64 |
| CA-17 | T-54, T-55, T-67 |
| CA-18 | T-56, T-57 |
| CA-19 | T-58 |
| CA-20 | T-54, T-61, T-62, T-63, T-67 |
| CA-21 | T-58 |
| CA-22 | T-43 |
| CA-23 | T-44, T-45, T-50, T-67 |
| CA-24 | T-36, T-46 |
| CA-25 | T-49 |
| CA-26 | T-51, T-64, T-69 |
| CA-27 | T-37, T-46 |
| CA-28 | T-93 |
| CA-29 | T-94 |
| CA-30 | T-94 |
| CA-31 | T-38, T-39, T-67 |
| CA-32 | T-40 |
| CA-33 | T-39 |
| CA-34 | T-99, T-100, T-103 |
| CA-35 | T-32, T-68, T-98, T-100 y las 15 revisiones de fase |
| CA-36 | T-101 |
| CA-37 | T-33, T-69, T-104, T-105, los tres PR y los 15 cierres de fase |
| CA-38 | T-02, T-03, T-72, T-86, T-95, T-99 |
| CA-39 | T-71, T-74, T-84, T-85, T-87, T-89, T-90 |
| CA-40 | T-71, T-74, T-78, T-80, T-81, T-89 |
| CA-41 | T-71, T-74, T-79, T-80, T-81, T-89 |
| CA-42 | T-71, T-72, T-73, T-74, T-86, T-87, T-90 |
| CA-43 | T-75, T-88 |

---

## Riesgos y mitigaciones

Los riesgos R-01 a R-13 de la evaluación y los de la sección 6 del diseño siguen vigentes; se resume dónde los trata el plan. Los N-xx son propios del plan.

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| R-01 Caché de permisos sin vaciar en un escritor nuevo | Media | Alto | `_access_changed` por construcción (T-09); recorrido y lista de módulos (T-02); matriz de revocación con mutante (T-22); revisión a 1,0 × |
| R-02 scrypt agota la memoria o no cabe en `memory-bootstrap` | Media | Alto | Medición en los tres contenedores antes de fijar (T-01); semáforo (T-08); test con N = huecos + 5 |
| R-03 / R-04 Límites mal dimensionados o capturas perdidas con un 429 | Alta | Alto | Perfil real medido (T-35); `0` desactiva; el 429 no consume intentos (T-62); cadena de extremo a extremo (T-63) |
| R-05 Redacción que consume CPU o rechaza de más | Media | Alto | Coste medido antes de implementar (T-37); cota con mutante (T-46); ≥ 15 casos «no redactar» (T-43); nota a la Iniciativa 7 (T-51) |
| R-06 Arnés de Chromium sin mantener desde el 2026-11-06 | Alta | Medio | Primera tarea del portal (T-71), antes de escribir ningún flujo |
| R-07 Ficheros que usa la instalación desplegada (`web/nginx.conf`, `docker-compose.yml`) | Media | Alto | `MEMORY_TRUSTED_PROXIES` vacío se comporta como hoy; ninguna tarea ejecuta `up` real; ensayos `kairos-acc-*` |
| R-08 / R-09 Fixes encadenados y bucles de revisión | Alta | Medio | Revisión como partida propia (242,4 h); cada fix, lentes completas; un intento más por fix en `deploy-memory.py` y `admin.py` |
| R-10 Tests con tiempo | Alta | Medio | Reloj inyectado en `limits.py` y `passwords.py`; filas fechadas hacia atrás; sin `sleep` |
| R-13 Esquema 13 reabierto entre hitos | Media | Bajo | Lista cerrada de DC-6 en T-06; `test_migrations_additive.py` en cada cierre de hito |
| N-01 Las horas IA de ensayos y cierres salen del método por tokens (0,1 a 0,3 h) y en la Iniciativa 3 se multiplicaron por 2,5 | Alta | Bajo | Mediciones y revisión de hito ya llevan horas propias; los ensayos reutilizan un solo script por etapas; el desvío se mide por tarea |
| N-02 `tasks.md` nace con 182.305 bytes (límite práctico 245.000; aviso de `ledger-lint` a 183.500) | Alta | Medio | Notas breves; cada cierre de fase archiva con `ledger-archive.py`; el cierre y la revisión de fase usan protocolos de cabecera |
| N-03 Una medición contradice un valor provisional de la spec (scrypt no cabe, la sonda agota la cuota) | Media | Medio | La decisión se toma y se escribe en la propia tarea de medición; solo se replanifica si cambia un criterio observable |
| N-04 El hito C concentra el extra de O2 (+19,5 h base) y la confianza más baja (portal y Chromium) | Media | Medio | Módulos pequeños y DOM compartido antes de las secciones (T-74); autorización revisada a 1,0 × |
| N-05 Tres PR desde la misma rama: si un PR no se fusiona antes de empezar el hito siguiente, el diff de la revisión de hito crece | Media | Bajo | T-68 y T-98 declaran su rango; T-99 revisa la iniciativa entera desde `c858fa5` |
| N-06 La revisión de seguridad no incluye pruebas dinámicas | Media | Medio | Lentes sobre el diff y la superficie, más la matriz hallazgo → test (T-101) y el ensayo de cierre (T-103); un pentest con `nemesis` queda para la Iniciativa 5, con el VPS como objetivo autorizado |
| N-07 `store_surface.json` estuvo congelado en la Iniciativa 3 y los escritores nuevos lo amplían | Baja | Bajo | Solo crece; cada tarea que añade métodos lo declara en `Archivos` |

---

## Métricas de éxito

- Las 106 tareas cerradas con su `Verificación` ejecutada y su medición de `usage-meter`, también cada intento de revisión.
- Los tres criterios de cierre del plan director demostrados en el ensayo aislado de T-103.
- Suite del servidor: `tests` ≥ 1570 y creciente, 0 fallos, 0 errores, 0 omitidos; mínimo igual en los cuatro sitios en cada cierre.
- Revisiones por fase y por hito con 0 hallazgos Critical/Important abiertos; revisión de seguridad con 0 altos.
- Todos los valores de «Valores medidos» fijados antes de su primera tarea de implementación.
- Horas IA reales frente a las 82,8 h estimadas, para la cuarta fila de `CALIBRATION.md`.

---

## Changelog del plan

| Fecha | Cambio | Autor |
|-------|--------|-------|
| 2026-11-20 | Creación del plan a partir de `spec.md` (aprobada), `evaluation.md` (go con condiciones) y `design.md` (aprobado, O2): 106 tareas en 18 fases y 3 hitos. Hereda las cifras de la evaluación y declara +34,2 h por O2 y por dos aclaraciones del usuario | planner |

---

## Siguiente paso

Con el **OK del plan** del usuario (puerta de control), el agente **`implementer`** lo ejecuta fase a fase sobre `feat/access-control`, marcando `tasks.md` como **ledger canónico** (checkbox + estado por tarea). Al terminar, handoff a `qa`, que ejecuta [`test-plan.md`](test-plan.md) con el arnés aislado del proyecto, y cierre con `documenter`.
