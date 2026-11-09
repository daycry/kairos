# Resultado de la revisión 2 y correcciones 0.1.2

Fecha: 2026-11-05. Informe independiente: [claude-review-2.md](claude-review-2.md). Claude CLI realizó 41 lecturas/búsquedas durante 483,5 segundos, sobre 138 archivos cuyo contenido se verificó sin cambios. Confirmó las correcciones anteriores y reportó un Important nuevo, seis Minor nuevos y dos límites pendientes. No encontró Critical dentro de su alcance; no revisó en detalle portal, despliegue ni backups y no ejecutó pruebas. No se presenta como auditoría completa.

## Contraste y parche

| Observación | Resultado y evidencia |
|---|---|
| N-1 — daemon antiguo vivo | Confirmado con el **tarball 0.1.0 original**, SHA-256 `0493bf2cf035ef7bd32ae03fa28102ed39eff4a3f5d684e421e1bd920cd2973f`. Ahora previsualización y aplicación rechazan un propietario activo antes de modificar archivos. IPC declara schema/version y rechaza endpoints antiguos sin contactar ni renovar su actividad; `doctor` lo diagnostica. Prueba con daemon 0.1.0 real: manifiesto intacto, ningún lanzamiento concurrente, cierre explícito y migración exacta de una entrega original pendiente. |
| N-2 — rechazo de escritura frena el lote | Confirmado. Las excepciones de cada fila ahora fijan su espera sin abortar las demás filas del lote. Una entrega incierta sigue conciliándose antes de repetir exactamente la misma operación. Regresión: una escritura rechazada y otra aceptada en el mismo lote. |
| N-3 — retirada con captura apagada | Confirmado. `queue-retire --event-id UUID --yes` admite `pending`, `unknown` y `failed`, mediante daemon autenticado si existe o con bloqueo exclusivo local si no existe. Funciona sin reactivar captura ni contexto. El recibo de retirada se conserva; no borra la memoria remota y no garantiza ausencia remota de un `unknown`. |
| N-4 — cuerpo corrupto bloquea contexto | Confirmado para cuerpos ausentes, JSON/hash inválidos o tamaño excesivo. Se aísla sólo la fila como `failed/capture_source_corrupt`; no se reenvía ni reconstruye su contenido. Retirada local explícita y contexto continúan. Metadatos globales corruptos, rutas enlazadas o tipos de archivo inseguros siguen deteniendo la apertura. Prueba conjunta de cuerpo ausente y sobredimensionado, contexto activo, posterior desactivación y retirada offline. |
| N-5 — consultas sin índices apropiados | Confirmados los índices ausentes. Migración 5 aditiva: índices por proyecto para actividad/historial, búsqueda de recibo vigente y orden de memorias recientes. La consulta vacía usa rango constante, evitando calcular rank léxico para todo el proyecto. `EXPLAIN ANALYZE` con 100.000 eventos sintéticos confirma uso de los índices de actividad e historial. No se ha medido ese volumen en producción ni el plan masivo de cada consulta restante. DDL espera como máximo cinco segundos por bloqueo y falla explícitamente si no lo obtiene. |
| N-6 — aliases y credenciales URL | Confirmado en ambos filtros. Se reconocen `PGPASSWORD`, sufijo `PWD` y userinfo `scheme://user:password@host`, incluido usuario vacío y esquemas compuestos. Pruebas de texto, JSON, captura, metadatos y controles de URL pública, email y placeholders. No se promete reconocimiento universal. |
| N-7 — suplantación del listener IPC | **Fixed en el límite comprobado.** La reproducción anterior recibió texto privado, aprendió el nonce enviado como Bearer e inyectó contexto. Ahora el secreto del endpoint nunca se transmite. Peticiones y respuestas usan AES-256-GCM, claves separadas por dirección, IV aleatorio y AAD ligada a versión, binding, ruta, dirección e identidad fresca de petición. Se valida también el endpoint explícito; no hay fallback a texto plano. |

N-7 se corrigió en el codec compartido de `lifecycle.mjs`, utilizado por hooks, adaptadores y operadores. El mínimo completo debía proteger tanto confidencialidad de la petición como autenticidad de la respuesta: firmar con un secreto que se enviase como Bearer no habría bastado. No se añadieron dependencias. Los permisos privados del archivo de endpoint siguen siendo requisito: otro proceso con acceso al secreto del mismo usuario queda fuera de ese límite.

Se hicieron investigación y revisión del candidato en dos pases independientes de sólo lectura. El segundo no identificó bypass del IPC revisado, pero sí dos defectos residuales reproducibles: URL con password y usuario vacío; y cuerpo excesivamente grande que no llegaba al aislamiento de corrupción. Se corrigieron y añadieron a las regresiones. La eliminación sólo actúa sobre un fichero regular de nombre gestionado, con ruta comprobada; no usa borrado recursivo ni sigue enlaces.

Los seis endpoints IPC se prueban contra un listener falso: no recibe marcador privado ni secreto y no puede aportar una respuesta aceptada. También se prueban respuesta reutilizada en otra petición/ruta, tag de petición manipulado, endpoints antiguos, límites de tamaño y recorrido legítimo de captura/contexto. La salida del hook ante indisponibilidad sigue siendo no bloqueante para la tarea del agente.

## Concurrencia semántica y autenticación

S-2b motivó una corrección acotada: ejecutor separado de dos hilos para escaneo semántico y dos plazas de admisión por servicio Retrieval. Un timeout no libera una plaza hasta que el trabajo haya terminado realmente. El Store comprueba el deadline por lote y fija timeout SQL. Se conserva el fallback léxico parcial; no se cambia el modelo, el vector ni el orden de candidatos.

Regresión determinista: dos búsquedas semánticas siguen ejecutándose después de caducar la respuesta; una tercera no entra al escaneo y el ejecutor de autenticación continúa disponible. Esto prueba aislamiento y límites, no p95 ni capacidad de producción. El coseno continúa siendo exacto en Python sobre como máximo 10.000 candidatos por identidad; no hay ANN ni garantía de vecino global fuera de ese conjunto.

Mediciones aisladas del candidato: actividad 0,097 ms e historial 0,068 ms de ejecución SQL sobre 100.000 eventos, con buffers del contenedor de prueba. No incluyen HTTP, autenticación ni UI. La prueba de memoria con 1.500 vectores de 768 dimensiones y documentos de 10.000 caracteres observó aproximadamente 6,8 MB de pico Python (`tracemalloc`), no RSS ni memoria de PostgreSQL. No se extrapolan a producción.

## Validación y reproducción

Pruebas normales: servidor 141/141 con PostgreSQL 17.11 y cero skips; cliente Windows y Linux 64/64; npx offline de los tres clientes. Datos, credenciales y proveedores de esas pruebas son sintéticos. La sonda hook → IPC → MCP → PostgreSQL conserva una única entrega tras pérdida de respuesta, con embeddings activados, una llamada de control y cero llamadas adicionales para el evento técnico. Regresiones principalmente en `tests/lifecycle.test.mjs`, `dispatcher.test.mjs`, `capture.test.mjs`, `test_privacy.py`, `test_retrieval.py` y `test_review_regressions.py`.

Para repetir la actualización con el artefacto anterior, verifica el hash indicado y extrae su contenido en una carpeta temporal privada. Desde la raíz de Kairos ejecuta:

```powershell
node packages/kairos-cli/tests/legacy-upgrade.mjs RUTA_AL_PAQUETE_0.1.0_EXTRAIDO
```

La ruta debe contener `package.json`, `bin/` y `lib/` del paquete, sin otro nivel `package/`. La prueba crea sus propias carpetas temporales y daemon loopback; no toca clientes instalados ni llama al proveedor. No se sustituye el artefacto original por ficheros actuales con la versión cambiada.

Comandos adicionales:

```powershell
node packages/kairos-cli/tests/run.mjs
docker build -f packages/kairos-cli/Dockerfile.test -t kairos-cli-test:native .
docker build --target test -f memory_platform/Dockerfile -t kairos-memory-tests .
docker build --target lifecycle-test -f memory_platform/Dockerfile -t kairos-lifecycle-tests .
python scripts/export-contracts.py
python scripts/build-handbook.py
```

## Entrega y límites

Cliente preparado: 0.1.2. Publicación npm y aceptación interactiva en Claude Code, Codex y OpenCode siguen pendientes. El recorrido sintético no cierra S-1 ni el comportamiento del agente ante contexto no confiable de OpenCode V1. Los formularios, herramientas y corpus pendientes del ledger nativo no se convierten en paridad completa por pasar estas pruebas.

Se mantiene el informe original como evidencia histórica. Las correcciones posteriores tienen sus propias pruebas y revisión focalizada; no se atribuye a Claude una aprobación de código que no leyó. Portal y scripts de entrega siguen fuera del alcance independiente declarado, aunque las suites existentes de aplicación, backup/restore y despliegue se ejecutan sobre PostgreSQL aislado.

No se han cambiado políticas de captura, credenciales, modelos, puertos ni datos de servicios activos. La aplicación del nuevo servidor y su lectura de vuelta se registran por separado; antes de habilitar captura deben completarse la aceptación nativa y las mediciones del entorno objetivo.

Actualización de entrega: el operador completó las diez fases y la lectura independiente del 2026-11-05 a las 20:26 UTC verificó el servidor y la documentación publicados. Catálogo MCP de 24 herramientas, dos proyectos, 21 documentos leídos individualmente con hash UTF-8 exacto, títulos y tags como listas; contexto documental autorizado en ambos proyectos, sin resultado parcial ni semántica/proveedor. Las tres páginas de manifiesto avanzaron sin duplicados. Diez archivos públicos de manuales/contratos coinciden con sus SHA-256 locales y ambas políticas permanecen `off`. El hash global coincide con la versión previa. No se escribió conocimiento ni se pidió generación/embeddings durante la lectura; sólo se abrió y cerró una sesión de verificación. Evidencia: [rollout-0.1.2.json](rollout-0.1.2.json). Esto no instala el cliente local ni sustituye la aceptación interactiva pendiente.
