---
design: n/a
test-plan: n/a (sin UI)
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
---

# 2026-11-12-three-components

> Separar Kairos en servidor, `kairos-mcp` y cliente con CI previa, paridad REST, servidor sin modelo de lenguaje, esquema de observación y estructura `server/`, `mcp/`, `client/`, `web/` (Iniciativa 2 del plan director).

| | |
|---|---|
| **Fecha** | 2026-11-12 |
| **Estado** | en-progreso |
| **Tipo** | Refactor |
| **Prioridad** | Alta |
| **Solicitante** | Daycry (plan director, Iniciativa 2) |
| **Responsable** | Daycry |
| **Spec** | [`spec.md`](spec.md) |
| **Evaluación** | [`evaluation.md`](evaluation.md) |
| **Diseño** | n/a (sin paso de diseño; las decisiones están en la spec, P-01 a P-11 decididas el 2026-11-12) |

---

## Cuadro de mando

| Métrica | Estimado | Real | Confianza |
|--------|---------|------|-----------|
| Tiempo humano | **280,2 h** (233,5 h base +20 %) | 0 h | Media |
| Tiempo IA (ejecución) | **38,6 h** (32,1 h base +20 %) (+ 9,6 h supervisión) | 0 h | Baja |
| Coste total | **14.010 €** de desarrollo + tokens ⚠️ verificar | 0 € | Media (desarrollo) / sin cifra (tokens) |
| Tokens IA | **9.64 M** (in 8.85 M / out 0.79 M) | 0 | Baja |
| Multiplicador productividad | **×5,8** | — | — |
| Tareas | **74** | 0 hechas | — |

> Frente a la evaluación (278,4 h, 13.920 €, 9,57 M tokens): **+1,8 h, +90 €, +0.07 M tokens**. Única diferencia: la decisión P-10 incluye el proxy de Ollama sin root (T-14, +1 h base) y su revisión (+0,5 h base). El resto de partidas hereda la evaluación sin cambios.

---

## Estimación por fase

| Fase | Estimado (h, con margen) | Tokens (in / out) | Coste € |
|------|-------------|-------------------|---------|
| Fase 1 — Integración continua (C-01) | 18,0 | 529 k / 49 k | 900 |
| Fase 2 — Servidor sin modelo de lenguaje (C-04) | 37,8 | 1146 k / 99 k | 1.890 |
| Fase 3 — Paridad REST /v1 (C-02) | 36,0 | 1178 k / 104 k | 1.800 |
| Fase 4 — Esquema de observación (C-05) | 37,8 | 1097 k / 96 k | 1.890 |
| Fase 5 — kairos-mcp (C-03) | 68,4 | 2316 k / 216 k | 3.420 |
| Fase 6 — Compatibilidad (C-07) | 23,4 | 696 k / 61 k | 1.170 |
| Fase 7 — Estructura del repositorio (C-06) | 46,8 | 1491 k / 123 k | 2.340 |
| Fase 8 — Integración final y revisión | 12,0 | 400 k / 40 k | 600 |
| **Total** | **280,2 h** | **8853 k / 788 k** | **14.010 €** |

Reparto por bloque de la evaluación (horas base de implementación): C-01 10 h · C-04 20 h (+1 h de P-10) · C-02 20 h · C-05 21 h · C-03 38 h · C-07 13 h · C-06 26 h = 149 h; revisión adversarial por fase 74,5 h (0,5 × implementación) más 3 h de revisión final; integración final 7 h. Total 233,5 h base.

---

## Presupuesto económico

**Coste = (horas × tarifa) + coste de tokens de IA.** Todos los importes en **EUR**.

### Supuestos (ajustables)

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Tarifa de desarrollo | 50 €/h | Valor por defecto del kit (sin `.claude/rates.json`) |
| Modelo IA asumido | Claude Opus (familia vigente en el ciclo) | Igual que la evaluación |
| Precio input | ⚠️ verificar € / 1M tokens | Sin `precioTokens` fiable; ejecutar la skill `rates-verify` |
| Precio output | ⚠️ verificar € / 1M tokens | Ídem |
| Tipo de cambio | 1 USD = 0,92 € | Valor por defecto del kit |
| Margen de contingencia | 20 % | Sobre horas base humanas e IA, revisión incluida |
| Supervisión humana | 25 % de las horas IA | Valor por defecto; probablemente corto (R-06) |
| Ratio tokens→hora IA | 300.000 tok/h | Valor no calibrado (heredado de la evaluación) |
| Revisión adversarial | 0,5 × implementación por fase | Retro de `retrieval-quality`; partida propia |

### Desglose

| Concepto | Cálculo | Importe |
|----------|---------|---------|
| Desarrollo (humano, base) | 233,5 h × 50 €/h | 11.675 € |
| Margen de contingencia | +20 % sobre desarrollo base (46,7 h) | 2.335 € |
| Tokens IA (input) | 8.85 M tok × precio | ⚠️ verificar |
| Tokens IA (output) | 0.79 M tok × precio | ⚠️ verificar |
| **Total estimado (con margen)** | | **14.010 € + tokens ⚠️ verificar** |

---

## Previsión de tokens (por fase)

Estimación del consumo de tokens por fase. Base: Claude Opus; precios sin verificar.

| Fase | Input (tok) | Output (tok) | Total (tok) | Coste € |
|------|------------|-------------|-------------|---------|
| Fase 1 | 529 k | 49 k | 578 k | ⚠️ verificar |
| Fase 2 | 1146 k | 99 k | 1245 k | ⚠️ verificar |
| Fase 3 | 1178 k | 104 k | 1282 k | ⚠️ verificar |
| Fase 4 | 1097 k | 96 k | 1193 k | ⚠️ verificar |
| Fase 5 | 2316 k | 216 k | 2532 k | ⚠️ verificar |
| Fase 6 | 696 k | 61 k | 757 k | ⚠️ verificar |
| Fase 7 | 1491 k | 123 k | 1614 k | ⚠️ verificar |
| Fase 8 | 400 k | 40 k | 440 k | ⚠️ verificar |
| **Total** | **8853 k** | **788 k** | **9641 k** | **⚠️ verificar** |

**Método de estimación:** se hereda la previsión por característica de la evaluación (C-01 370 k, C-04 760 k, C-02 870 k, C-05 760 k, C-03 1.750 k, C-07 490 k, C-06 1.080 k, integración 440 k) y se reparte entre las tareas por horas base; la revisión adversarial toma su parte de 2.800 k in / 250 k out proporcional a sus horas. Tokens facturables: entrada no cacheada + creación de caché + salida. Las cifras por tarea son orientativas y se calibran con `usage-meter` (cada tarea abre y cierra su medición).

---

## Productividad IA (humano vs. IA)

| KPI | Valor |
|-----|-------|
| Horas humanas estimadas | 280,2 h (233,5 h base +20 %) |
| Horas IA (ejecución) | 38,6 h (32,1 h base +20 %; supuesto: 9.64 M tok ÷ 300.000 tok/h) |
| Supervisión humana | 9,6 h (25 % de las horas IA) |
| **Horas totales (IA + supervisión)** | **48,2 h** |
| Horas ahorradas | 232,0 h |
| **Ahorro** | **83 %** |
| **Multiplicador de productividad** | **×5,8** |
| FTE equivalentes *(opcional)* | 1,4 |

> Horas con el margen del 20 % ya aplicado. Las horas IA son una estimación aproximada y no incluyen el tiempo de reloj de la suite en contenedor ni de la CI, que en `retrieval-quality` dominó el plazo real.

---

## Resumen ejecutivo

Se separa Kairos en tres componentes que solo se hablan por contrato: el servidor (`/v1`, permisos, almacenamiento y embeddings), `kairos-mcp` (publica las 34 herramientas y las traduce a `/v1` con la credencial de quien llama, sin acceso a la base) y el cliente (CLI con hooks y puente stdio). Antes se monta la integración continua como red de seguridad. El servidor deja de depender de un modelo de lenguaje, se añade un esquema versionado de observación y el repositorio pasa a `server/`, `mcp/`, `client/` y `web/`.

El plan sigue el orden aprobado C-01 → C-04 → C-02 → C-05 → C-03 → C-07 → C-06. Son 74 tareas pequeñas en 8 fases. Cada fase termina con su revisión adversarial como partida propia, y las verificaciones con un componente real (contenedor `kairos-mcp`, puente stdio en proyecto aislado) se hacen en las Fases 5 y 6, no al final. La Fase 8 cierra con la prueba de contrato, el contenedor sin credenciales de base, la suite sin modelo, el ensayo aislado y la revisión final.

### Objetivos

- Integración continua en verde con `server`, `retrieval-eval`, `mcp`, `client`, `web` y `contracts`, sin más secreto que `GITHUB_TOKEN` (CA-01 a CA-03).
- 34 herramientas MCP con endpoint `/v1` o marcadas `local`, y contrato solo aditivo respecto de `23ced03` (CA-04 a CA-07, CA-29).
- `kairos-mcp` sin importar código del servidor, arrancable sin credenciales de base y con el mismo contrato que el MCP interno (CA-08 a CA-13).
- Servidor que arranca y pasa la suite completa sin ningún modelo de lenguaje configurado (CA-14 a CA-18).
- Esquemas `observation.v1` y `session-summary.v1` validados cuando el evento declara `schema_version` (CA-19 a CA-22).
- Estructura `server/`, `mcp/`, `client/`, `web/` con `store_surface.json` intacto y `npm pack` idéntico (CA-23 a CA-26); MCP interno con aviso de retirada y puente stdio operativo (CA-27, CA-28).

---

## Datos necesarios para un informe completo

- [x] **Requisitos funcionales** confirmados por el solicitante (spec `aprobada`; P-01 a P-11 decididas el 2026-11-12)
- [x] **Alcance** cerrado (qué entra y qué NO: spec §Alcance)
- [x] **Criterios de éxito / métricas** acordados (CA-01 a CA-32)
- [x] **Accesos y credenciales** necesarios (solo `GITHUB_TOKEN` en CI; ninguna credencial de la instalación local)
- [x] **Entornos** disponibles (PostgreSQL efímero del target `test`; proyecto Compose aislado con nombre distinto de `knowledge-graphs`)
- [x] **Stakeholders** identificados (solicitante único)
- [ ] **Dependencias externas** mapeadas: PR #2 fusionado en `main` antes de la Fase 7 (P-09) y GitHub Actions activas (P-01, decidida); pendiente de confirmar la fusión
- [x] **Restricciones** conocidas (sin pruebas contra la base desplegada, migraciones y contrato aditivos, nada publicado)
- [ ] **Tarifa/hora y supuestos de coste** confirmados (valor por defecto 50 €/h; precio de tokens ⚠️ verificar)

---

## Análisis de impacto

- **`memory_platform/`** (→ `server/memory_platform/` en la Fase 7) — `app.py` (7 endpoints nuevos, `corpora` con fechas), `models.py`, `config.py` (interruptores y `MEMORY_LLM_MODEL`), `worker.py`, `store_ingest.py`, `corpus_answers.py`, `mcp.py`, `agent_tools.py`, `extended_tools.py` (envoltorio S-05, cabeceras de retirada), `extended_store.py` (validación de esquema), `requirements.txt` (validador fijado), `Dockerfile`.
- **`mcp/`** (nuevo) — paquete `kairos_mcp`: cliente `httpx`, herramientas generadas desde `docs/contracts/kairos-mcp.json`, Dockerfile sin `psycopg`, tests propios.
- **`packages/kairos-cli/`** (→ `client/`) — solo rutas y empaquetado (`lib/config.mjs:11`); sin cambios funcionales; versión 0.4.0 sin publicar.
- **`web/`** — recibe `Dockerfile` y `nginx.conf` (`/mcp` → `memory-mcp`); el portal solo cambia de sitio, sin interfaz nueva.
- **`ollama-proxy/`** — lista de permitidos `/api/embed`, `/api/version`; `OLLAMA_ALLOW_CHAT`; sin root.
- **`docker-compose.yml`** — servicio `memory-mcp` en red propia, sin `beam:cloud`.
- **`docs/contracts/`** — `x-kairos-endpoint`, esquemas `observation.v1` y `session-summary.v1`, ejemplos.
- **`scripts/`** — `export-contracts.py`, `deploy-memory.py`, puerta congelada y sus rutas.
- **`.github/workflows/ci.yml`** (nuevo) — CI sin publicar ni secretos.

---

## Cambios arquitectónicos

- **Orden C-01 → C-04 → C-02 → C-05 → C-03 → C-07 → C-06** (aprobado): la CI es la red; C-04 reduce superficie antes de duplicar herramientas; C-02 crea los endpoints de C-03; C-06 va al final y con el PR #2 fusionado.
- **Herramientas de kairos-mcp generadas desde el contrato** (P-05): la identidad de esquemas se cumple por construcción y `mcp/` no importa código del servidor. Si `mcp==1.27.1` no admite `inputSchema` arbitrario, T-38 se detiene y se pide decisión.
- **`x-kairos-endpoint`** por herramienta (campo aditivo): una prueba lo compara con el OpenAPI exportado.
- **Solo `Authorization: Bearer`** reenviado a `/v1` (P-08); las sesiones con cookie quedan en el MCP interno.
- **Envoltorio S-05 con campos aditivos** `untrusted` y `warning` (P-02), sin alterar el texto: el CLI parsea el texto como JSON (`dispatcher.mjs:15-20`).
- **Extracción apagada por defecto** con recibo aditivo `extraction: "disabled"` (P-03); `corpus_answer` apagado pero listado (P-04); `MEMORY_LLM_MODEL` sin valor por defecto.
- **Proxy de Ollama con lista de permitidos** y sin root (P-10).
- **`schema_version` solo se valida cuando viene** (P-11).
- **Paquete Python `memory_platform` conservado** dentro de `server/` (P-06); versiones 0.4.0 y retirada del MCP interno en 0.5.0 (P-07).
- **Cada paso con la suite completa** y `store_surface.json` congelado; los movimientos de ficheros van en commits separados de los cambios de contenido.

---

## Archivos a crear/modificar

| Archivo | Acción | Propósito |
|---------|--------|-----------|
| `.github/workflows/ci.yml` | Crear | CI con seis trabajos, sin secretos ni publicación |
| `scripts/tests/test_ci_workflow.py` | Crear | Estructura e higiene del workflow |
| `mcp/**` | Crear | Componente `kairos-mcp` (paquete, Dockerfile, tests, contrato copiado) |
| `docs/contracts/observation.v1.schema.json`, `session-summary.v1.schema.json`, `examples/**` | Crear | Esquemas versionados y ejemplos |
| `memory_platform/tests/contracts_base_23ced03/` | Crear | Línea base de contratos de la iniciativa |
| `memory_platform/{app,models,config,worker,store_ingest,corpus_answers,mcp,agent_tools,extended_tools,extended_store}.py` | Modificar | Endpoints, interruptores, envoltorio, validación, retirada |
| `memory_platform/schemas.py` | Crear | Validador de esquemas de observación |
| `ollama-proxy/default.conf.template` | Modificar | Lista de permitidos y `OLLAMA_ALLOW_CHAT` |
| `docker-compose.yml`, `memory_platform/nginx.conf` | Modificar | Servicio `memory-mcp`, `/mcp` hacia él, sin `beam:cloud` |
| `scripts/export-contracts.py`, `scripts/deploy-memory.py`, `scripts/diagnose-deployment.py` | Modificar | `x-kairos-endpoint`, servicio nuevo, rutas |
| `memory_platform/` → `server/memory_platform/`; `packages/kairos-cli/` → `client/`; `Dockerfile.web`, `nginx.conf` → `web/` | Mover | Estructura final (Fase 7) |
| `docs/*.md`, `README.md`, `CHANGELOG*.md`, `docs/roadmap/2026-11-12-three-components/review.md` | Modificar/Crear | Manuales, nota de migración y revisiones |

No se aplican `interop/**` ni las piezas de `docs/agents/CONTRACTS.md`: este repositorio no es el kit de agentes. Ninguna tarea escribe en `docs/roadmap/**/testing/`.

---

## Dependencias y prerequisitos

- **Externa (no es tarea):** el PR #2 (`feat/retrieval-quality`) debe estar fusionado en `main` antes de la Fase 7 (C-06, P-09); T-57 lo comprueba y no empieza sin ello.
- **Externa:** GitHub Actions activas en el repositorio (P-01, decidida) para T-05, T-06 y T-65. El `push` de la rama y de la rama desechable son acciones sobre el remoto: confirmación del usuario si no están autorizadas.
- Orden entre fases: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8; C-03 necesita los endpoints de C-02 y C-07 necesita C-03.
- Hipótesis a confirmar pronto: el SDK `mcp==1.27.1` admite `inputSchema` arbitrario (T-38) y la suite cabe en el tiempo de un trabajo de CI (T-05).

---

## Criterios de aceptación (global)

- [ ] CI en verde en el PR con `server`, `retrieval-eval`, `mcp`, `client`, `web` y `contracts`; rojo comprobado en rama desechable (CA-01, CA-03); sin más secreto que `GITHUB_TOKEN` (CA-02)
- [ ] Las 34 herramientas con `x-kairos-endpoint` válido o `local`; prueba de correspondencia sobre las 34 (CA-04 a CA-07)
- [ ] `kairos-mcp` sin `memory_platform`, sin `psycopg`, `health` 200 sin credenciales de base, `tools/list` idéntico al contrato, tests de comportamiento MCP pasan por la cadena (CA-08 a CA-13)
- [ ] Suite completa sin modelo de lenguaje y proxy con lista de permitidos (CA-14 a CA-18)
- [ ] Esquemas validados y ejemplos coherentes; migración aditiva o ninguna (CA-19 a CA-22, CA-30)
- [ ] Estructura final con `store_surface.json` intacto, `npm pack` idéntico y versiones 0.4.0 (CA-23 a CA-26)
- [ ] MCP interno con `Deprecation`/`Sunset` y puente stdio operativo (CA-27, CA-28)
- [ ] Contrato solo aditivo respecto de `23ced03` (CA-29)
- [ ] Ensayo aislado de los tres componentes sin llamadas a modelos de lenguaje (CA-31)
- [ ] Suite con 0 fallos y 0 omitidos, `retrieval-eval` con los umbrales vigentes y manuales actualizados (CA-32)

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| R-01 Identidad del contrato en kairos-mcp (descripciones, anotaciones, `required`) | Media | Alto | Generar desde `kairos-mcp.json`; T-38 con spike del SDK, T-69 con la misma regla en ambos MCP |
| R-02 S-05 rompe al CLI 0.3.0 | Media | Alto | Campos aditivos; `npm test` del CLI en T-45 y T-46 |
| R-03 Apagar `extract` cambia la captura de resúmenes del CLI | Alta | Medio | Evento aceptado y recibo marcado (T-09); nota de migración (T-55) |
| R-04 Esquema de observación prematuro | Media | Medio | Validar solo con `schema_version`; versionado para una v2 |
| R-06 Bucles de revisión adversarial | Alta | Medio | Revisión como partida propia por fase; `usage-meter` por tarea e intento; supervisión por encima del 25 % |
| R-07 Conflictos de renombrado con el PR #2 | Media | Medio | Fase 7 al final, tras fusionar el PR #2; `git mv` en commits sin cambios de contenido |
| R-08 CI en Linux con tiempos no medidos | Media | Medio | Fase 1 primero, con 2 h para ponerla en verde (T-05) |
| R-09 Tocar recursos desplegados con Compose | Baja | Alto | Proyecto aislado con override que renombra redes y volúmenes; `docker ps`/`volume ls` antes y después; CA-30 en T-04 |
| **N-01** La puerta congelada vive en `testing/` de una iniciativa cerrada y el implementer no escribe en `testing/` | Media | Medio | T-60 pide aprobación de `qa` o genera una copia junto al ledger |
| **N-02** El ensayo aislado (T-72) necesita que `deploy-memory.py` conozca `memory-mcp`; la evaluación no lo presupuestó aparte | Media | Medio | Incluido en T-40 (2 h de Compose); si falta tiempo se amplía T-72 y se declara |
| **N-03** Revisión final de solo 3 h por ajustarse al total de la evaluación | Media | Medio | Se apoya en las revisiones de fase; se reserva supervisión por encima del 25 % |
| **N-04** El proxy sin root (P-10) añade +1,8 h y +90 € sobre la evaluación | Alta | Bajo | Declarado en el cuadro de mando |

---

## Métricas de éxito

- Cada una de las 74 tareas cerrada con su `Verificación` ejecutada y su medición de `usage-meter`.
- Revisiones adversariales por fase con 0 hallazgos Critical/Important abiertos al cierre.
- Suite backend: `tests` igual o mayor que la línea base de T-01, 0 fallos, 0 errores, 0 omitidos, sin modelo configurado.
- Horas IA reales frente a las 38,6 h estimadas, para calibrar `CALIBRATION.md`.

---

## Changelog del plan

| Fecha | Cambio | Autor |
|-------|--------|-------|
| 2026-11-12 | Creación del plan a partir de `spec.md` (aprobada) y `evaluation.md` (go del usuario). Incluye P-10 completa (proxy sin root, +1 h base) | planner |

---

## Siguiente paso

Con el **OK del plan** del usuario (puerta de control), el agente **`implementer`** lo ejecuta fase a fase sobre `feat/three-components`, marcando `tasks.md` como **ledger canónico** (checkbox + estado por tarea). Al terminar, handoff a `qa` y cierre con `documenter`; con `test-plan: n/a (sin UI)` en el frontmatter, `qa` corre sus puertas deterministas y sale limpio sin pedir test-plan (ADR-017).
