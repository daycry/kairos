# Correcciones de la revisión independiente

Fecha: 2026-11-05. Distribución del cliente: 0.1.1, paquete local, sin publicación npm. Este informe describe fuentes y pruebas aisladas; no afirma que la nueva versión esté desplegada ni aceptada dentro de los tres clientes. El informe original permanece intacto en [claude-review.md](claude-review.md); [review-triage.md](review-triage.md) conserva las reproducciones anteriores al parche.

## Resultado por observación

| ID | Corrección y evidencia |
|---|---|
| I-1 | Instalación, validación y lanzamiento del daemon usan el Node físico registrado. El runtime anfitrión de OpenCode puede ser distinto. Regresión sin `send` inyectado: adaptador, IPC y launcher con ejecutable anfitrión diferente. Falta aceptación interactiva de OpenCode real. |
| I-2 | Los eventos automáticos técnicos no crean trabajos `embed`; los aprendizajes derivados, notas manuales y documentos conservan ese destino. Sonda con embeddings activados: nota de control, una llamada medida; evento técnico, cero llamadas adicionales medidas, tras pérdida de respuesta y recarga. |
| I-3 | Outbox v2 separa cuerpos privados y journal de metadatos, mantiene presupuestos incrementales y checkpoints periódicos. Compacta sólo recibos terminales sin cuerpo. Una identidad que ya no está en caché se concilia remotamente mediante fingerprint antes de admitirse. Pruebas con límite de dos registros, cuatro eventos, reapertura, cuerpos pendientes y migración v1. |
| I-4 | Espera por registro, lotes pequeños con rotación y fase `failed` fuera del sondeo automático. Cinco intentos como máximo. `queue-retry` y `queue-retire` requieren UUID y `--yes`. Los aceptados fallidos sólo vuelven a consultar recibos; no se reenvía su fuente ni se relanza un trabajo central. Regresiones de política degradada, fuentes nuevas frente a cola atascada y reintento de recibo fallido. |
| I-5 | La fusión conserva la posición del grupo propio y el orden de hooks ajenos. Añadir un hook después ya no provoca drift; alterar el handler propio sigue rechazándose. |
| I-6 | Contexto automático con términos alternativos y exclusión `agent-activity` antes del límite léxico. La búsqueda normal mantiene AND por defecto. Caso PostgreSQL con pregunta larga, una fuente pertinente y ocho eventos técnicos; Unicode, tags y procedencia conservados. No equivale a una evaluación de relevancia sobre todos los proyectos. |
| I-7 | Autenticación y comprobación CSRF síncronas pasan a un hilo; la identidad de contexto se instala/restaura en la tarea ASGI. Prueba determinista de autenticación lenta y coroutine independiente. No se ha incorporado un pool sin medición de conexiones/carga. |
| I-8 | Actualización explícita 0.1.0 → 0.1.1 con `--replace` para todos los clientes gestionados, runtime anterior conservado y recuperación de cambio parcial. Versiones desconocidas rechazadas. La operación requiere cerrar clientes/dispatcher anterior; no se admite convivencia sobre una cola. |
| I-9 | Clasificador común por sufijo de clave en cliente/servidor, asignaciones prefijadas, claves camelCase, JSON estructurado/serializado y claves con escapes Unicode, tokens habituales y valores con comas/punto y coma. Regresiones de texto, árbol, cola y tablas de evento/versión/vigente. Los documentos aprobados continúan rechazando datos sensibles sin alterar sus hashes. |

## Privacidad y compatibilidad

Resultado del parche de privacidad: **fixed en los límites reconocidos y probados**. La entrada controlada era texto o estructuras de herramienta que llegaban al saneamiento del cliente y del servidor; asignaciones como `DB_PASSWORD` sobrevivían y podían persistir. Se corrigieron ambos helpers compartidos antes de sus copias durables. No se añadió una decodificación universal ni se afirma detectar secretos arbitrarios.

La investigación y la revisión de candidato se realizaron en dos pases independientes de sólo lectura. El segundo detectó tres regresiones concretas: el valor predeterminado `facts=[]` añadido por Pydantic invalidaba el fingerprint de los eventos nativos; una clave JSON con escape Unicode no se reconocía; una asignación dotenv podía dejar el sufijo después de coma/punto y coma. Se reprodujeron y corrigieron con regresiones. El fingerprint usa el payload explícitamente enviado antes de defaults; el recibo conserva `capture_hash`.

Controles legítimos: prosa, acentos, emoji, tags con comas, JSON que contiene claves `constructor` como texto, placeholders exactos, notas manuales, documentos aprobados y sus hashes, reintentos con recibo original. Los campos estructurados peligrosos de un árbol de captura siguen rechazándose. Autorización y aislamiento no se relajan.

M-1: el servidor aplica la política actual a capturas automáticas tipadas y tags heredados. Verifica el fingerprint y limita el cuerpo de `summary` a metadatos técnicos admitidos; los reintentos ya aceptados conservan su resultado. No se presume poder identificar semánticamente una transcripción disfrazada de nota manual. M-5: el worker conserva el código público de `MemoryError` sin convertirlo en `provider_error` ni reintentar un error determinista.

## Rendimiento, formatos y límites restantes

S-1: la documentación vigente confirma `command` con `args` en Claude Code y las opciones de hooks usadas en Codex. Se ajustó `SessionEnd` de Codex al máximo de tres segundos. Fuentes: [Claude Code](https://code.claude.com/docs/en/hooks), [Codex](https://learn.chatgpt.com/docs/hooks). El contrato documentado y los procesos de hook sintéticos no sustituyen confianza y aceptación dentro de cada cliente.

S-2: el servidor deja de cargar todos los payloads y vectores en una lista Python. Usa cursor PostgreSQL de lotes de 128, retiene hasta cien identidades mejor puntuadas y vuelve a comprobar permiso y versión al cargar los contenidos ganadores. Regresión real: 1.500 candidatos, 768 dimensiones y 10.000 caracteres de contenido por documento; pico Python inferior a 20 MiB. Es una cota de esa prueba con `tracemalloc`, no una garantía de RSS, memoria PostgreSQL, latencia o capacidad de producción. Se conserva el tope de 10.000 candidatos por orden estable; si se supera, la respuesta ahora declara `partial`. No es ANN ni vecino global garantizado.

S-3: todos los intentos de adquisición usan una guarda exclusiva durante la recuperación de lock. La prueba fuerza otro adquirente en el punto de intercalado del propietario obsoleto y verifica rechazo; no es un ensayo prolongado de múltiples procesos en producción. Una caída manteniendo la guarda requiere recuperación explícita con clientes detenidos. No se borra automáticamente una guarda de propietario incierto.

M-2/M-3/M-6: manuales corregidos sobre espera IPC, Node registrado, actualización y diferencia entre MCP básico y hooks optativos. M-4: OpenCode V1 entrega contexto por su hook de texto de sistema; se conserva delimitado como datos no confiables con procedencia. No se declara eliminado el riesgo de instrucciones maliciosas mediante un simple aviso; aceptación del comportamiento del agente pendiente.

## Validación del candidato

Comandos desde la raíz de Kairos:

```powershell
node packages/kairos-cli/tests/run.mjs
docker build -f packages/kairos-cli/Dockerfile.test -t kairos-cli-test:native .
docker build --target test -f memory_platform/Dockerfile -t kairos-memory-tests .
docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle-tests .
python scripts/export-contracts.py
python scripts/build-handbook.py
```

Resultado observado: cliente Windows 59/59; cliente Linux 59/59; smoke npx offline para tres clientes, conexión básica y hooks; servidor 139/139 sobre PostgreSQL 17.11, cero skips; hook Node real → IPC autenticado → MCP → PostgreSQL con un único evento tras pérdida de respuesta, proveedor instrumentado y control positivo. Son datos sintéticos y bases temporales; no se llamó al proveedor real ni se capturó contenido del usuario. El paquete de dieciocho archivos coincide byte a byte con los fuentes: [package-0.1.1.json](package-0.1.1.json).

Los scripts `review-triage.py/mjs` prueban el comportamiento previo; ahora pueden fallar porque sus expectativas describen los defectos. Las regresiones del candidato están en las suites normales, especialmente `test_review_regressions.py`, `test_embeddings.py`, `test_retrieval.py` y los tests de captura, dispatcher, instalación y ciclo de vida del CLI.

Pendientes separados: segunda revisión de Claude del candidato; aplicar/leer de vuelta la nueva versión del servidor; aceptación interactiva en Claude Code, Codex y OpenCode; publicación npm y funcionalidades A-02 a A-08. El contenido actual y la captura desactivada de los proyectos existentes se conservan.
