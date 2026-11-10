# Integración de Kairos en `custom-agents`

- **Fecha**: 2026-11-10
- **Plugin analizado**: `custom-agents` 3.2.3 (rama `fix/plugin-audit-remediation`, con trabajo sin comitear)
- **Estado**: propuesta para el repositorio del plugin. Este documento vive en el repositorio de Kairos hasta que se abra la iniciativa allí.
- **Documento hermano**: [plan director de Kairos](plan.md) (Iniciativa 7)

## 1. Objetivo y decisiones

Kairos pasa a ser el único sistema de memoria externo del plugin y sustituye a Kwipu y Graphiti. La memoria local del plugin (`docs/knowledge/` en git) sigue siendo la de serie y la fuente de verdad. El plugin se conecta a Kairos por MCP sobre HTTPS.

| Regla del plugin | Cómo se respeta |
|---|---|
| El Markdown en git es la única fuente (ADR-018) | Kairos es una proyección reconstruible con `rebuild` |
| Solo el Curator aprueba conocimiento | Solo se publica lo que está en `approved/`, ligado a su hash |
| Los hooks no hacen red | Lectura y escritura pasan por el router y la cola recuperable |
| Funciona en Claude Code, Codex y OpenCode | El adaptador usa un cliente HTTP propio con la biblioteca estándar, no el MCP del arnés |
| Degradar en vez de bloquear | Sin Kairos, el plugin sigue con la memoria local |

## 2. Reparto de responsabilidades

La integración sigue la separación de Kairos en servidor, MCP y cliente.

| Capa | Quién | Qué hace |
|---|---|---|
| Conocimiento curado (doctrina) | **Plugin**, adaptador `kairos` | Publica lo aprobado como documentos validados; lo retira; reconstruye; lo consulta |
| Episodios de sesión | **kairos-client** | Captura la sesión, la convierte en observaciones y resúmenes, y la envía. El plugin no captura sesiones hacia Kairos |
| Estado de tareas del ciclo | **Plugin**, adaptador de eventos | Proyecta `task.*` y `review.*` al tablero de equipo de Kairos (opcional, última fase) |
| Herramientas de memoria para el agente | **kairos-mcp**, declarado por el usuario | El agente llama a `search`, `context`, `timeline` directamente |

Esto resuelve la doble captura: el diario local del plugin (`journal`) no se envía a Kairos; los episodios los aporta `kairos-client`. `/doctor` avisa si falta `kairos-client` en un proyecto con Kairos activo.

```
 custom-agents                               Kairos (VPS)
 ┌──────────────────────────────┐
 │ docs/knowledge/approved/     │  publish    ┌────────────┐      ┌───────────────┐
 │   └─ knowledge-sync.py ──────┼────────────▶│            │      │               │
 │ knowledge-find.py --intent ──┼──  read  ──▶│ kairos-mcp ├─/v1─▶│ kairos-server │
 │ eventos task.* / review.* ───┼─ opcional ─▶│            │      │               │
 └──────────────────────────────┘             └────────────┘      └───────▲───────┘
 kairos-client (hooks, observador) ─────────────── REST /v1 ──────────────┘
```

## 3. Correspondencia con el contrato del adaptador

Fichero nuevo `skills/knowledge-services/backends/kairos.py`. No toca el núcleo.

| Función del contrato | Herramienta de Kairos | Comportamiento |
|---|---|---|
| `health` | `projects`, `capture_policy` | Alcanza el servidor, la clave es válida y tiene `publish` y `validate` en el proyecto |
| `plan` | `document_manifest` | Compara los hashes de `approved/` con el manifiesto remoto: qué publicar, actualizar y retirar. Sin reenvíos a ciegas |
| `apply` | `publish_document` | Envía el Markdown exacto con su SHA-256 y la evidencia de la decisión del Curator; idempotente por hash y versión |
| `verify` | `document_status` | Confirma versión, hash y que los trabajos de indexado terminaron |
| `rebuild` | `document_manifest` + `publish_document` + `revoke_document` | Deja el proyecto remoto igual que `approved/` |
| `revoke` | `revoke_document` | Retira con lápida usando la siguiente versión remota |
| `puede_leer` / `consultar` | `search`, `context`, `details`, `timeline` | Devuelve aciertos con `id`, `estado`, `evidencia` y ruta canónica local; si no hay nada relevante, lo dice |
| `modo` | — | `off`, `shadow`, `read`, igual que Graphiti |

Correspondencia de identidades: un proyecto de Kairos por repositorio; el identificador de documento es el ID canónico del plugin (`<proyecto>.LES-012`); la categoría de `taxonomy.json` va como categoría y etiquetas.

## 4. Cambios en el plugin

### 4.1 Piezas nuevas

| Pieza | Ruta | Nota |
|---|---|---|
| Cliente MCP genérico | `agent-kits/shared/mcp_client.py` | Extraído de `backends/graphiti.py`; streamable HTTP con la biblioteca estándar; añade autenticación bearer |
| Adaptador | `skills/knowledge-services/backends/kairos.py` | Las seis funciones obligatorias y las de lectura |
| Capacidad | `agent-kits/shared/capabilities.py` | Registro de `kairos` con salud, paso de `/setup` y comprobación de `/doctor` |
| Configuración | `.claude/knowledge-services/taxonomy.json` | `backends.kairos` (`endpoint`, `project_id`, `api_key_env`, `allow_remote`) y `routing.kairos` por categoría |
| Enlace | `.claude/integrations.json` | `purpose: "knowledge"` con `knowledge.check/publish/read/rebuild` |
| Referencia | `skills/knowledge-services/references/kairos.md` | Alta, modos, degradación |
| Decisión | `docs/knowledge/` (ADR nuevo) | Sustituye a ADR-020 y ADR-021; mantiene ADR-018 |

### 4.2 Credenciales

- La clave nunca está en el repositorio. `taxonomy.json` guarda solo el nombre de la variable de entorno (`api_key_env`), siguiendo el precedente de `graphiti_providers.py`.
- Una clave por máquina y por integración, con alcance al proyecto y permisos `read`, `publish` y `validate`.
- `allow_remote: true` exige HTTPS. El cliente rechaza credenciales dentro de la URL y redirecciones.
- `/setup` explica cómo crear la clave en Kairos; no la crea ni la guarda.

### 4.3 Lectura

- `knowledge-find.py --intent` consulta Kairos solo si `router.intents.<intent>` lo activa. Si falla o tarda, vuelve a la búsqueda local e indica el motivo.
- El bloque de memoria de `SessionStart` sigue siendo local, sin red. El contexto de sesión de Kairos lo inyecta `kairos-client`.
- Todo lo que llega de Kairos se trata como dato no fiable y se presenta delimitado, con su estado de validación.

### 4.4 Retirada de Kwipu y Graphiti

| Paso | Contenido |
|---|---|
| 1 | Adaptador `kairos` en `shadow` junto a los actuales; se comparan resultados de lectura |
| 2 | Comparación función por función con lo que hoy sirve Graphiti (grafo de entidades, consulta temporal, `group_id`). **Pendiente de verificar** |
| 3 | Lectura real desde Kairos; Kwipu y Graphiti quedan con aviso de retirada |
| 4 | Versión mayor del plugin: se eliminan `backends/markdown_export.py`, `backends/graphiti*.py`, sus funciones en `capabilities.py` y sus pasos de `/setup` |

No hay migración de datos: todo se reconstruye desde el Markdown.

### 4.5 Convenciones del plugin que aplican

Python solo con biblioteca estándar; rutas resueltas por búsqueda en las seis raíces; test antes que código; `lint_plugin.py`; evals positivo y negativo; `SKILL.md` de 200 líneas como máximo; saneado con `redact.py`; exportación a Codex y OpenCode con `export-interop.py --check`; duplicaciones declaradas en `copias.json`.

## 5. Qué necesita Kairos

| Requisito | Estado | Iniciativa de Kairos |
|---|---|---|
| Contrato MCP estable y solo aditivo | Hecho | — |
| Publicación idempotente por hash y versión, manifiesto y lápidas | Hecho | — |
| `kairos-mcp` como componente propio, accesible por HTTPS | Pendiente | 2 y 5 |
| Contenido marcado como no fiable en todas las lecturas | Pendiente | 2 (S-05) |
| Abstención: respuesta «nada relevante» | Pendiente | 3 (M-01) |
| Caducidad y rotación de claves; una clave por integración | Pendiente | 4 |
| Copias probadas y worker tolerante a fallos | Pendiente | 3 |
| Guía de alta: proyecto por repositorio y clave con `publish` y `validate` | Pendiente | 1 (T-34) |
| Búsqueda semántica y troceado en producción | Pendiente | 5 |

## 6. Fases

| Fase | Contenido | Requisito previo en Kairos | Riesgo |
|---|---|---|---|
| A | Cliente MCP genérico con bearer; adaptador `kairos` con `health`, `plan`, `apply`, `verify`, `revoke`, `rebuild`; modo `shadow`; tests con un servidor simulado | Contrato actual (puede empezar ya) | Bajo |
| B | Capacidad en `/setup` y `/doctor`; configuración; referencia; ADR | — | Bajo |
| C | Publicación real contra Kairos en el VPS; `rebuild` de un proyecto piloto; verificación de manifiestos | Iniciativas 2 y 5 | Bajo: reconstruible |
| D | Lectura en `shadow`: comparar con la búsqueda local y con Graphiti | Iniciativa 3 (abstención) y S-05 | Medio |
| E | Lectura real (`read`); aviso de retirada de Kwipu y Graphiti | D sin regresiones | Medio |
| F | Versión mayor: retirada de Kwipu y Graphiti | E estable | Rompedor para quien los use |
| G | Opcional: eventos `task.*` y `review.*` al tablero de equipo de Kairos | — | Bajo |

## 7. Criterios de cierre

1. `knowledge-sync.py --backend kairos --check` sale en verde contra el VPS y `--rebuild` deja el manifiesto remoto idéntico a `approved/`.
2. Retirar una entrada local la retira en Kairos con lápida y deja de aparecer en la búsqueda.
3. Con Kairos caído, `knowledge-find.py` responde con la búsqueda local e indica el motivo; ningún comando del ciclo se bloquea.
4. Ninguna credencial aparece en el repositorio, en la configuración ni en la salida de los comandos.
5. La integración funciona igual en Claude Code, Codex y OpenCode (`export-interop.py --check` en verde).
6. Tras la fase F no queda código ni configuración de Kwipu o Graphiti, y el ADR nuevo lo registra.

## 8. Incógnitas

- Paridad con Graphiti, función por función (paso 2 de la retirada).
- Si `capabilities.py` admite registrar una capacidad nueva sin modificar ese fichero.
- Contenido de `phase4-knowledge-gate.md` y `knowledge-check-governed.md`: no revisados.
- La rama `fix/plugin-audit-remediation` tiene trabajo sin comitear y un PR en borrador: la integración parte de ahí cuando se cierre.
