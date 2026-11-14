# Plan director de Kairos

- **Fecha**: 2026-11-10 · **Base**: rama `feat/retrieval-quality`
- **Origen**: [auditoría](audit.md) (43 hallazgos, IDs `B-`, `S-`, `O-`, `M-`) y análisis de claude-mem v15.15.1
- **Estado**: propuesta. Sustituye a las secciones 4 a 7 de `audit.md`. Cada iniciativa se ejecuta con `/dev-cycle` (spec, evaluación, plan y ledger propios); aquí se fijan alcance, orden y criterios de cierre.
- **Documento hermano**: [integración con custom-agents](custom-agents-integration.md)

## 1. Decisiones tomadas

| # | Decisión | Fecha |
|---|---|---|
| D-1 | Kairos corre en un VPS con Docker y se usa desde varias máquinas | 2026-11-10 |
| D-2 | El servidor no ejecuta modelos de lenguaje. Solo un modelo de embeddings local | 2026-11-10 |
| D-3 | La extracción de recuerdos la hace el cliente, en la máquina de quien trabaja, con su suscripción de Claude Code o Codex | 2026-11-10 |
| D-4 | `corpus_answer` pasa a opcional y desactivado por defecto | 2026-11-10 |
| D-5 | Servidor, MCP y cliente se separan en tres componentes | 2026-11-10 |
| D-6 | Kairos es el único sistema de memoria externo del plugin `custom-agents`; sustituye a Kwipu y Graphiti | 2026-11-10 |
| D-7 | En la búsqueda combinada, «validado» es una bonificación ajustable, no un orden absoluto | 2026-11-10 |

## 2. Arquitectura objetivo

Tres componentes con una sola dirección de dependencia: cliente → MCP → servidor. Ninguno importa código de otro; se hablan por contrato.

```
  Máquina de trabajo                                  VPS (Docker)
 ┌───────────────────────────────┐              ┌─────────────────────────────────┐
 │ Agente (Claude Code, Codex…)  │   MCP/HTTPS  │  kairos-mcp                     │
 │   └─ herramientas de memoria ─┼─────────────▶│  traduce herramienta → /v1      │
 │                               │              │  sin base de datos, sin estado  │
 │ kairos-client                 │              └──────────────┬──────────────────┘
 │   hooks → cola en disco       │   REST/HTTPS                │ REST interno
 │   observador (suscripción)    ├────────────────────────────▶│
 │   contexto de inicio          │              ┌──────────────▼──────────────────┐
 │                               │              │  kairos-server                  │
 │ custom-agents (plugin)        │   MCP/HTTPS  │  API /v1 · permisos · búsqueda  │
 │   adaptador `kairos`  ────────┼─────────────▶│  worker de embeddings           │
 └───────────────────────────────┘   (vía MCP)  │  PostgreSQL + pgvector          │
                                                └─────────────────────────────────┘
```

### 2.1 Responsabilidades

| Componente | Hace | No hace |
|---|---|---|
| **kairos-server** | API REST `/v1`; autenticación y permisos por proyecto; almacenamiento con versiones y validación; búsqueda híbrida; cola y worker de embeddings; copias y migraciones | Llamar a modelos de lenguaje; conocer clientes o arneses; exponer herramientas MCP |
| **kairos-mcp** | Publicar las herramientas MCP para agentes; traducir cada herramienta a una llamada `/v1` con la credencial de quien llama; marcar el contenido devuelto como dato no fiable | Acceder a la base de datos; tomar decisiones de permisos; guardar estado |
| **kairos-client** | Capturar la actividad con hooks sin bloquear al agente; cola de envío en disco; observador que convierte actividad en observaciones y resúmenes; inyectar contexto al inicio; adaptadores por arnés | Almacenar memoria de forma definitiva; decidir permisos |

### 2.2 Contratos

| Contrato | Fuente de verdad | Regla |
|---|---|---|
| REST `/v1` | `docs/contracts/memory-platform.openapi.json` | Solo aditivo; es el contrato canónico |
| MCP | `docs/contracts/kairos-mcp.json` | Solo aditivo; cada herramienta declara el endpoint `/v1` que la sirve; una prueba comprueba la correspondencia |
| Observación y resumen de sesión | Esquema JSON nuevo, versionado | Lo produce el cliente y lo valida el servidor |

### 2.3 Qué cambia respecto a hoy

| Hoy | Objetivo |
|---|---|
| MCP montado dentro del proceso de la API (`app.py:345`), con acceso directo al almacén | Proceso y contenedor propios, que solo llaman a `/v1` |
| El worker del servidor extrae con un modelo de lenguaje (`providers.py:52`, trabajo `extract`) | El cliente extrae; el servidor recibe observaciones ya estructuradas (`/v1/observations`) |
| Extracción sin estado: una llamada por evento con una instrucción de una línea | Observador con estado por sesión, tipos, conceptos, ficheros tocados, descarte de ruido y resumen de sesión |
| `corpus_answer` genera respuestas en el servidor | Opcional, apagado por defecto; el agente redacta a partir de `query_corpus` |
| Puertos solo en `127.0.0.1`, una máquina | HTTPS público, varios usuarios y máquinas |
| El CLI hace de puente MCP por stdio hacia `/mcp` | Se conserva como alternativa local; el camino principal es MCP remoto |

Se conserva sin cambios: el modelo de datos, las 34 herramientas y su contrato, las migraciones aditivas, la cola de envío en disco del cliente.

## 3. Iniciativas

Orden de ejecución. Las iniciativas 5 y 6 pueden ir en paralelo a partir del cierre de la 2.

| # | Iniciativa | Depende de | Tamaño |
|---|---|---|---|
| 0 | Protección inmediata | — | Horas |
| 1 | Cerrar `retrieval-quality` | 0 | M |
| 2 | Separación en tres componentes | 1 | L |
| 3 | Operación fiable | 2 | L |
| 4 | Control de acceso y privacidad | 2 | L |
| 5 | Despliegue en VPS | 3, 4 | M |
| 6 | Observador en el cliente | 2 | L |
| 7 | Integración con `custom-agents` | 5 (lectura real), 2 (modo sombra) | L |
| 8 | Recuerdos fiables y funcionalidades | 5, 6 | L |
| 9 | Mantenibilidad y distribución | En paralelo | M |

### Iniciativa 0 — Protección inmediata

- Subir a GitHub los commits pendientes de la rama.
- Copia manual de la base actual fuera del volumen y prueba de restauración en una base efímera (O-01, O-02).
- Comprobar que el directorio de secretos real está fuera del repositorio y de OneDrive (S-10).
- Corregir el README: instalación del CLI con `npm pack` o desde git (O-07).

**Cierre**: copia restaurada y comparada; rama subida.

**Estado (2026-11-12)**: cerrada. La rama está subida y el README usa `npm pack` (O-07, hecho en la Iniciativa 1). Los secretos reales están en `C:/docker-secrets/knowledge-memory`, fuera del repositorio y de OneDrive, y Git no sigue ningún fichero de secretos (S-10). La copia y la prueba de restauración (O-01, O-02) no se hacen: el usuario decidió el 2026-11-12 que los datos actuales no se migran a producción (decisión abierta 4).

### Iniciativa 1 — Cerrar `retrieval-quality` (fases 6 a 8)

Se retoma en `docs/roadmap/2026-11-09-retrieval-quality/` con estos ajustes:

| Tarea | Ajuste |
|---|---|
| T-27 | «Validado» como bonificación (D-7) y comprobación CA-35 en la puerta de evaluación |
| T-28 | Comprobar dimensiones del vector reutilizado (deuda de Fase 5); `has_vectors` como `EXISTS` y selección por identidades (B-09) |
| T-30, T-32 | El logging cubre todos los `except Exception` (B-01); métrica de saturación del semáforo de embeddings (B-14) |
| T-34 | Documentar las variables que faltan y las fases 3 a 5 (O-11, O-12) |
| T-36 | Medir con Ollama real solo embeddings: plazo de documentos largos y marcado de filas antiguas con índice HNSW |
| T-38 | **No se despliega en la instalación local.** Se sustituye por un ensayo completo en proyecto Compose aislado; el despliegue real es la Iniciativa 5 |

**Cierre**: puerta de evaluación en verde (recall@5 ≥ 0,80, MRR ≥ 0,60, CA-35), ensayo aislado completo.

### Iniciativa 2 — Separación en tres componentes

| Bloque | Contenido |
|---|---|
| Integración continua | Primero: workflow con la suite del backend, tests del CLI y del portal, y la puerta de evaluación (B-04, O-04). La separación se hace con red |
| Paridad REST | Cada herramienta MCP tiene su endpoint `/v1`; añadir los que falten (búsqueda y contexto de observaciones, consulta de corpus, estado de documentos); prueba de correspondencia herramienta ↔ endpoint |
| `kairos-mcp` | Paquete y contenedor propios; cliente HTTP hacia `/v1` con la credencial del llamante; sin acceso a la base ni secretos de base; mismas 34 herramientas y mismo contrato; envoltorio de dato no fiable en todas las lecturas (S-05) |
| Servidor sin modelo de lenguaje | El trabajo `extract` del servidor queda desactivado por defecto y `corpus_answer` opcional (D-2, D-4); el proxy de Ollama solo permite `/api/embed` y `/api/version` (S-09); se retira `beam:cloud` como valor por defecto |
| Esquema de observación | Esquema versionado de observación y resumen de sesión, validado al recibir; migración aditiva si hacen falta campos (tipo, conceptos, ficheros leídos y modificados) |
| Estructura del repositorio | `server/` (hoy `memory_platform/`), `mcp/`, `client/` (hoy `packages/kairos-cli/`), `web/`; cada uno con su imagen, sus tests y su versión |
| Compatibilidad | El montaje MCP dentro de la API se mantiene una versión con aviso de retirada; el puente stdio del CLI sigue funcionando |

**Cierre**: `kairos-mcp` pasa la misma prueba de contrato que hoy pasa el MCP interno; el contenedor MCP arranca sin credenciales de base; el servidor arranca y pasa la suite sin ningún modelo de lenguaje configurado; contrato solo aditivo.

**Riesgo**: es un refactor grande sobre código denso. Se hace con la superficie de `Store` congelada (`store_surface.json`) y en pasos pequeños, cada uno con la suite completa.

### Iniciativa 3 — Operación fiable

| Bloque | Contenido | Cubre |
|---|---|---|
| Copias | `backup --prune --keep N` con sha256, cifrado con clave externa, plazo propio, `--verify-backup` en el despliegue, copia externa programada, runbook de restauración | O-01, O-02, O-03, S-06 |
| Worker | Distinguir errores de base de errores de proveedor, reintento con espera, tope de intentos al reclamar, índice parcial de cola, retención de tablas | B-03, B-05, B-06 |
| Conexiones y plazos | Pool de conexiones, `statement_timeout` y `connect_timeout` por defecto, actor y permisos resueltos una vez por transacción | B-02, B-07 |
| Despliegue | Límites de recursos, healthchecks, rotación de logs, bloqueo de despliegue, retroceso de imágenes, `extra_hosts` | O-05, O-06 |
| Abstención | Umbral de relevancia y respuesta «nada relevante», calibrado con la puerta | M-01 |
| Sonda | Prueba periódica de ida y vuelta (escribir, indexar, buscar, retirar) y alerta de cola atascada | M-06 |
| Tests | Worker con base caída, concesión expirada y trabajo venenoso; límites sin cobertura; tests frágiles | B-15 |

**Cierre**: restauración probada desde la copia externa; el worker sobrevive a una caída de base en el ensayo; la sonda detecta un worker parado.

### Iniciativa 4 — Control de acceso y privacidad

| Bloque | Contenido | Cubre |
|---|---|---|
| Credenciales | Cambio de contraseña con revocación de sesiones, deshabilitar usuario, retirar permisos, caducidad y rotación de claves, scrypt reforzado | S-03, S-07 |
| Login | Contar solo fallos, IP real desde el proxy de confianza, cubos separados, purga | S-02 |
| Límites | Cuota y tasa por clave, tope de flujos abiertos | S-08 |
| Redacción | Patrones ampliados, detector de entropía, prueba compartida servidor y cliente. Se aplica en el cliente antes del observador y en el servidor al recibir | S-01 |
| Identidad | Un usuario por persona, una clave por máquina y otra por integración, con alcance por proyecto; guía de alta y baja | — |
| Superficie | Validación del directorio de secretos, permisos del fichero de clave, red de inferencia privada | S-10, S-11 |

**Cierre**: revisión de seguridad sin hallazgos altos; una clave revocada deja de funcionar en todas las rutas; diez fallos de un cliente no bloquean a otro.

### Iniciativa 5 — Despliegue en VPS

| Bloque | Contenido |
|---|---|
| Exposición | Proxy con TLS y renovación automática; solo 443; rutas `/v1`, `/mcp` y portal; cortafuegos |
| Embeddings | `nomic-embed-text` en el Ollama del VPS, dimensionado para CPU; sin ningún modelo de lenguaje |
| Servidor | Endurecimiento del host, actualizaciones, alertas, copia externa cifrada programada |
| Migración | Copia verificada de la instalación local, restauración en el VPS, comparación de manifiestos, corte |
| Ensayo | Despliegue completo en entorno de pruebas antes del corte; prueba de restauración |
| Observabilidad | Métricas en red interna, paneles mínimos y alertas (enlaza con la Fase 7 de la Iniciativa 1) |

**Cierre**: los clientes de dos máquinas distintas escriben y buscan contra el VPS por HTTPS; restauración probada en el VPS. Requiere autorización expresa del usuario antes del corte.

### Iniciativa 6 — Observador en el cliente

El núcleo que hoy le falta a Kairos, tomado del diseño de claude-mem.

| Bloque | Contenido |
|---|---|
| Observador con estado | Una conversación por sesión con un modelo barato que recibe los eventos en orden y devuelve observaciones; se recicla al superar un tamaño |
| Esquema | Observación: tipo, título, hechos con cita literal, narrativa, conceptos, ficheros leídos y modificados. Resumen de sesión: petición, investigado, aprendido, hecho, siguiente. Opción de descartar ruido (cubre M-04) |
| Proveedores | Suscripción de Claude Code (Claude Agent SDK, lanza el `claude` local), suscripción de Codex, clave de API, Ollama local; elegible por arnés |
| Aislamiento | El observador no tiene herramientas ni permisos; directorio confinado; sin servidores MCP |
| Control de gasto | Máximo de observadores simultáneos, pausa al acercarse al límite del plan, eventos de solo lectura hacia un modelo más simple, apagado por configuración |
| Entrega | La cola en disco existente transporta observaciones y resúmenes; reintento con espera; nunca bloquea al agente |
| Contexto de inicio | Índice de observaciones y resúmenes recientes del proyecto y del ámbito de usuario, con presupuesto de tokens (cubre el punto 10 y M-07) |
| Modos | Instrucciones del observador configurables por idioma y dominio; modo en español |
| Arneses | Claude Code, Codex y OpenCode |

**Cierre**: una sesión real produce observaciones estructuradas y un resumen en el VPS sin que el servidor llame a ningún modelo; con el servidor caído no se pierde ninguna captura; conjunto etiquetado para medir la calidad de la extracción.

**Decisiones abiertas**: modelo por defecto del observador; si se reutiliza código de claude-mem (Apache-2.0 desde mayo de 2026, conservando avisos) o se reimplementa.

### Iniciativa 7 — Integración con `custom-agents`

Descrita en [custom-agents-integration.md](custom-agents-integration.md).

### Iniciativa 8 — Recuerdos fiables y funcionalidades pendientes

Orden por dependencias.

| Orden | Contenido | Cubre |
|---|---|---|
| 1 | `memory_feedback` (herramienta 35): qué resultados se usaron, ignoraron o corrigieron | Punto 8 |
| 2 | Conjunto de evaluación con uso real y medida de la calidad de extracción | M-05 |
| 3 | Vigencia anclada a evidencia: fichero, commit y fecha; marca «posiblemente obsoleto» | M-02 |
| 4 | Puntuación con recencia, validación y uso | Punto 6 |
| 5 | Casi-duplicados y contradicciones: detección sobre la búsqueda vectorial; resolución por sustitución o marca de conflicto. El juicio lo aporta un agente cliente, no el servidor | Punto 5, M-03 |
| 6 | Ciclo de vida y revisión por categoría | Punto 7 |
| 7 | Consolidación periódica: la ejecuta un agente cliente programado; el resultado entra sin validar | Punto 9 |

### Iniciativa 9 — Mantenibilidad y distribución

- Canal del cliente mientras npm siga bloqueado: versión publicada en GitHub con el paquete adjunto (O-07).
- Cliente: reparación del bloqueo de la cola, detección de ruta de Node obsoleta, matriz Windows, macOS y Linux (O-08, O-09).
- Portal: plazo en las peticiones, lint, prueba de accesibilidad, dividir el fichero principal (O-10).
- Servidor: migraciones numeradas con una fuente única y readiness que exija versión (B-11), configuración única (B-12), protocolo explícito entre almacenes (B-16), purga de work-state (B-13), `graph_data` y N+1 (B-08, B-10), código muerto y formato (B-17, B-18), lock de dependencias con hashes (B-19).
- Documentación: runbooks, notas de migración y changelog separados; CONTRIBUTING y LICENSE; retros de las iniciativas cerradas (O-12, O-13).

## 4. Restricciones permanentes

- Nunca se ejecutan pruebas contra la base desplegada; fixtures aislados.
- Migraciones solo aditivas.
- El contrato de las herramientas MCP existentes se conserva.
- El despliegue real y el corte al VPS requieren autorización expresa.
- No se publica nada en registros externos sin el usuario.

## 5. Decisiones abiertas

1. Modelo por defecto del observador (Iniciativa 6).
2. Reutilizar código de claude-mem o reimplementar.
3. Cuántas personas usarán Kairos: condiciona el alcance de la gestión de usuarios (Iniciativa 4).
4. ~~Migrar los datos de la instalación local o empezar de cero en el VPS (Iniciativa 5).~~ **Decidido el 2026-11-12**: los datos actuales no se migran a producción; el VPS empieza de cero.
5. Retirada de Kwipu y Graphiti: versión mayor inmediata o periodo con aviso (Iniciativa 7).
