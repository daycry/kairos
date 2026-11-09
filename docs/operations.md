# Operación y recuperación

Última actualización: 2026-11-09.

## Identidad y datos existentes

El código mantenido está directamente en la raíz del repositorio. Ejecuta `python scripts/deploy-memory.py --apply` desde esa raíz. Los ejemplos históricos que anteponen `kairos/` pertenecen a la disposición anterior del workspace; no son un segundo producto ni otra definición Compose activa.

Una reubicación de código no migra automáticamente las instalaciones de clientes que vinculan una raíz física, ni sus colas privadas. Los proyectos consumidores que no se hayan movido mantienen su configuración. Para ensayos nativos preparados en una ruta retirada, crea un ensayo nuevo en lugar de editar a mano los enlaces o reutilizar una outbox bajo otra raíz. Conserva las evidencias anteriores con su fecha y ámbito originales.

El archivo [docker-compose.yml](../docker-compose.yml) es la definición de esta distribución. Conserva la identidad de infraestructura `knowledge-graphs` y los nombres de volúmenes existentes para no crear una base vacía al cambiar la carpeta del producto. El directorio de código y el nombre de un volumen no son lo mismo.

No ejecutes `down -v`, limpiezas de volúmenes ni una restauración sobre la base de producción como parte de una actualización ordinaria. Mantén las credenciales, modelos, proyectos, políticas y puertos existentes. La captura permanece según la política de cada proyecto; desplegar no autoriza activarla.

La actualización del 5 de noviembre añade `capture_policy` y un argumento opcional `project_id` a `event_status`; no necesita migración adicional ni reindexación. Despliega y verifica el servidor antes de activar los hooks nuevos en consumidores. Una comprobación `doctor --online` con automatización configurada detecta un servidor que todavía no ofrece ese contrato. Las colas locales anteriores y sus recibos deben conservarse. Cambiar el servidor o la identidad del proyecto crea otra partición local; no copies a ciegas una cola a otra conexión. Los modos, estados y recuperación local están en [instalación](install.md).

La ampliación del 6 de noviembre añade tablas de trabajo compartido y consultas generadas mediante migraciones aditivas. Conserva las listas privadas, memorias, documentos, identidades y hashes anteriores. No requiere reindexar ni reenviar fuentes. El despliegue verifica las nuevas herramientas de observaciones, equipo y corpus: un servidor anterior con sólo las herramientas básicas no se considera actualizado. El panel debe mostrar **Observaciones**, **Reglas del proyecto**, **Actividad** y **Consultar corpus** después de actualizar su imagen. El análisis local de código requiere actualizar explícitamente el runtime del cliente; desplegar la web no modifica los proyectos consumidores.

La instalación local ejecuta esta ampliación desde el 9 de noviembre de 2026: el despliegue completó sus diez fases, hizo copia antes de migrar y verificó 34 herramientas, 2 proyectos y 21 documentos. El registro está en [activación](roadmap/2026-11-06-functional-parity/testing/activation.json).

Antes de actualizar, revisa [el ledger y sus evidencias](roadmap/2026-11-06-functional-parity/tasks.md). Las pruebas aisladas no acreditan que estas imágenes estén activas en tu instalación. La publicación del paquete npm y su instalación pública se verifican por separado en [entrega CLI](release-cli.md).

## Servicios y preparación

| Servicio | Función |
|---|---|
| `memory-postgres` | Persistencia central |
| `memory-migrate` | Aplicación de esquema antes de arrancar la API |
| `memory-bootstrap` | Preparación explícita de usuario inicial y proyectos permitidos |
| `memory-api` | HTTP y MCP autenticados |
| `memory-worker` | Trabajos asíncronos y representaciones derivadas |
| `memory-web` | Web pública, documentación, panel y entrada del cliente |
| `memory-admin` | Herramientas administrativas con acceso al volumen de copias |
| `memory-files` | Inicialización acotada del directorio de copias, sin red ni recorrido recursivo |
| `ollama` | Entrada interna al servidor de modelos configurado |

La base no publica su puerto al exterior. Web y API escuchan en loopback en `5173` y `8790`. Para uso remoto prepara una entrada HTTPS y un origen permitido; no basta con sustituir loopback por una IP pública.

La configuración de [config.py](../memory_platform/config.py) rechaza orígenes remotos sin HTTPS o sin cookie segura. Revisa los nombres `MEMORY_ALLOWED_ORIGINS`, `MEMORY_COOKIE_SECURE`, `MEMORY_SECRETS_DIR`, `OLLAMA_UPSTREAM`, `MEMORY_LLM_MODEL` y `MEMORY_EMBEDDING_MODEL`. Los secretos se leen desde archivos; no documentes sus valores.

## Imagen PostgreSQL

`memory-postgres` ya no usa la imagen oficial directamente: Compose la construye con la etapa `postgres-pgvector` de [`memory_platform/Dockerfile`](../memory_platform/Dockerfile) y la etiqueta `kairos-postgres:latest`. La etapa parte de `postgres:17-bookworm@sha256:839fbb5a…` (el digest se declara una sola vez, en el Dockerfile) e instala el paquete PGDG `postgresql-17-pgvector` en una versión fijada (`ARG PGVECTOR_VERSION`, hoy `0.8.7-1.pgdg12+1`). La suite de pruebas usa la misma etapa, así que producción y pruebas comparten binarios.

- **Volumen existente:** la versión mayor sigue siendo 17 y la base el mismo digest, de modo que `knowledge-graphs_memory-postgres-data` se reutiliza sin `pg_upgrade`. El ensayo de despliegue lo comprobó arrancando la imagen nueva sobre un volumen creado con la anterior.
- **Subir la versión de pgvector:** si PGDG retira la versión fijada el build falla, a propósito. Consulta `apt-cache madison postgresql-17-pgvector` dentro de la imagen base, cambia `PGVECTOR_VERSION` de forma consciente y repite el ensayo antes de desplegar.
- **Orden de fases:** la fase `build` también construye esta imagen y la fase `database` arranca PostgreSQL con ella **antes** de la copia de seguridad. La copia previa a la migración se hace, por tanto, con los binarios nuevos; es un dump lógico y no depende del paquete.
- **Quién crea la extensión:** `admin migrate` ejecuta `CREATE EXTENSION vector WITH SCHEMA public` con el rol de la DSN. En la imagen oficial ese rol (`memory`, el `POSTGRES_USER`) es superusuario de arranque, así que no hace falta nada más. Un rol sin ese privilegio hace fallar la migración antes de cambiar nada (lo cubre una prueba) y no deja columnas ni versión a medias.
- **Qué añade la migración:** versión de esquema 8, aditiva: columnas `embedding` y `dims` en `memory.embeddings`, relleno desde la columna original `vector`, un disparador que completa `embedding` cuando algo escribe solo `vector`, y un índice HNSW parcial por cada modelo/dimensión de `MEMORY_VECTOR_INDEXES` (ver [configuración](configuration.md#búsqueda-vectorial-pgvector)). No borra ni modifica la columna `vector`.
- **Coste de la primera migración y ventana de bloqueo (R-06):** la migración añade `dims` como columna generada (reescribe la tabla), rellena `embedding` y construye el índice HNSW dentro de una única transacción, con `ACCESS EXCLUSIVE` sobre `memory.embeddings` de principio a fin: durante ese tiempo no se pueden buscar vectores ni completar trabajos de embedding. Medido en un PostgreSQL de pruebas aislado (vectores de 768 dimensiones, `maintenance_work_mem` 256 MB, construcción en serie): 20,000 filas → 54.4 s (la tabla con sus índices pasa de 165 MB a 327 MB, de los que 78 MB son el HNSW); 50,000 filas → 113.8 s (413 MB → 818 MB; HNSW 195 MB). Es una referencia, no una garantía (`testing/migration-cost.json` de la iniciativa): el tiempo crece al menos linealmente con las filas y depende del disco y de la CPU; la instalación actual tiene del orden de 21 documentos. Una ejecución posterior de `admin migrate` omite todo el bloque pgvector y tarda décimas de segundo (0.09 s y 0.2 s en la medición) sin tomar bloqueos exclusivos; solo se construye un índice nuevo si falta en `pg_indexes`. No se usa `CREATE INDEX CONCURRENTLY` porque no puede ejecutarse dentro de la transacción única de `migrate` (que es lo que garantiza que un fallo no deje nada a medias) y la ventana de `ACCESS EXCLUSIVE` solo existe en la primera migración (ver más abajo qué ocurre al añadir un par a `MEMORY_VECTOR_INDEXES`).
- **Añadir un modelo o dimensión a `MEMORY_VECTOR_INDEXES` en una base ya migrada:** `admin migrate` construye ese HNSW con un bloqueo `SHARE` sobre `memory.embeddings`, que **bloquea las escrituras de embeddings** (los `complete_job` de embedding esperan; las búsquedas siguen leyendo) mientras dura la construcción. Planifícalo como la primera migración, con una ventana, y mide antes con tus datos.
- **Cuándo deja de caber el grafo en memoria:** el HNSW es rápido mientras su grafo cabe en `maintenance_work_mem`. A 768 dimensiones, `m = 16` y 256 MB eso son unas 6,5·10^4 filas (cifra aproximada, no medida en esta instalación): por encima, la construcción pasa a ser mucho más lenta que la extrapolación lineal de la medición anterior (que llega a 50.000 filas). En ese caso sube `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM` (por ejemplo `1GB`) antes de migrar.
- **Si `migrate` agota los 3600 s:** el despliegue se detiene en esa fase y no declara éxito, pero el contenedor `memory-admin` puede seguir vivo y la transacción de PostgreSQL seguir ejecutándose. En la instancia afectada, comprueba `docker ps` (contenedor `*-memory-admin-run-*`) y, en la base, `SELECT pid, state, wait_event_type, query_start, left(query, 80) FROM pg_stat_activity WHERE datname = 'agent_memory'`. No lances otra migración ni mates el proceso hasta saber si ha terminado (la transacción es atómica: o queda todo o nada).
- **Cuándo ocurre:** la fase `migrate` del despliegue se ejecuta **antes** de `start`: durante ese bloqueo siguen activos los servicios de la versión anterior (el despliegue no los sustituye hasta `start`), así que sus búsquedas semánticas y trabajos de embedding esperan a que termine la migración o fallan por sus propios plazos. Planifica la ventana con la cifra anterior, o detén `memory-worker` y avisa del corte. La fase `migrate` tiene su propio plazo de 3600 s (no los 120 s de las demás) y lo registra como `migrate_timeout_seconds` en el informe.
- **Memoria y memoria compartida:** la migración fija `maintenance_work_mem` en 256 MB (configurable con `MEMORY_MIGRATION_MAINTENANCE_WORK_MEM`) y construye los índices en serie (`max_parallel_maintenance_workers = 0`). No se aumenta `shm_size` de `memory-postgres`: sin trabajadores paralelos la construcción no usa `/dev/shm` (64 MB por defecto en un contenedor, insuficiente para una construcción paralela grande), y el resto del uso diario de PostgreSQL tampoco lo necesita; se evita así cambiar la definición del contenedor de producción.

## Desplegar

Desde la raíz del producto, previsualiza primero el procedimiento:

```powershell
python scripts/deploy-memory.py
```

Para aplicarlo a la instalación existente:

```powershell
python scripts/deploy-memory.py --apply
```

Sin `--apply`, el script sólo imprime un plan. Con `--apply`, comprueba el motor antes de crear archivos o cambiar servicios, exige los volúmenes originales y rechaza arrancar una base vacía como sustituta. Conserva secretos existentes, prepara las imágenes, comprueba los documentos y sus hashes UTF-8, crea un dump antes de migrar y compara el manifiesto canónico después. No importa ni vuelve a enviar fuentes.

Al final realiza llamadas MCP reales: inicialización, catálogo, proyectos y manifiestos documentales completos con paginación, UUID, versión, hash y retirada. La copia y el resultado quedan en `.private/deployment-status.json`, excluido de Git. Un fallo detiene las fases siguientes y no declara éxito parcial. No modifica políticas de captura, modelos o puertos. Si la base cambia durante la comprobación, exige conciliación en vez de atribuir automáticamente la discrepancia al despliegue.

La verificación usa una sesión temporal de `admin`, leída del archivo privado de bootstrap, y la cierra. Si cambiaste esa contraseña, usa `--verify-key-file C:\\ruta-privada\\clave` con una clave existente de lectura para todos los proyectos. El script no crea una clave adicional ni imprime su contenido.

Sólo para una instalación realmente nueva, utiliza `--fresh --secret-dir <directorio-privado>` junto con `--apply`. Esto permite preparar archivos que no existan y hacer el bootstrap una sola vez; no reemplaza contraseñas existentes. No uses `--fresh` para eludir un problema con los volúmenes de la instalación actual.

Lee la salida completa y comprueba su resultado final. El script es la fuente para las fases y argumentos exactos de despliegue. No lances una segunda actualización mientras otra siga procesando. Si se interrumpe, verifica el estado real de contenedores y migración antes de repetir.

La limpieza de código y la recreación de contenedores son operaciones distintas. Que una imagen se construya no demuestra que la instalación esté usando esa imagen. Antes de declarar una entrega aplicada, registra la imagen activa y realiza la comprobación funcional siguiente.

El informe privado conserva `previous_images`, las identidades inmutables de las imágenes de API, trabajador y web antes de construir. Si falla después de recrear servicios, conserva ese informe y el dump. El procedimiento no revierte automáticamente la base ni borra sus tablas. El operador puede preparar un override de Compose apuntando a esas identidades y arrancar sólo los servicios afectados con `--no-build --no-deps`; antes debe comprobar que la versión anterior admite el esquema aditivo vigente. Para recuperar datos, utiliza primero la restauración aislada descrita más abajo. No restaures el dump sobre producción para resolver un fallo únicamente de web.

### Ensayar un despliegue en una instancia aislada

Antes de tocar la instalación real, ensaya el cambio con datos sintéticos en otra instancia:

```powershell
python scripts/deploy-memory.py --apply --project-name kairos-rehearsal --secret-dir <directorio-privado-sintetico> --api-port 18790 --web-port 15173
```

Un `--project-name` distinto de `knowledge-graphs` genera un override de Compose en `.private/rehearsal-<proyecto>/` que cambia el nombre del proyecto, volúmenes, redes, imágenes (siempre `rehearsal-<proyecto>-<servicio>:latest`, nunca una etiqueta de la instalación) y puertos. Usa solo el fichero `memory-platform.env` de esa carpeta (obligatorio; se prepara con `scripts/memory-admin.py prepare --env-output`), pasa siempre `--env-file` para que Compose no cargue el `.env` raíz, y descarta del entorno del proceso toda variable `MEMORY_*`, `COMPOSE_*` y `KAIROS*`. El script rechaza nombres que coincidan con (o contengan) `knowledge-graphs`, los puertos 5173 y 8790, una carpeta `.private/rehearsal-<proyecto>` que contenga ficheros que el ensayo no creó, y cualquier etiqueta generada que coincida con una del Compose. Para ensayar una actualización, prepara antes el estado anterior (imagen y código previos con datos sintéticos) en ese mismo proyecto; para destruirlo, comprueba primero con `docker compose -p <proyecto> config` que todos los nombres empiezan por el proyecto y ejecuta `down -v` solo con ese `-p`.

### Si el despliegue se detiene en `start`

La fase `start` espera a que todos los servicios estén sanos. El caso más habitual es el proxy `ollama` en estado `unhealthy`: su comprobación consulta `/api/version` y recibe `502 Bad Gateway` porque el servidor Ollama de destino (`OLLAMA_UPSTREAM`, por defecto `host.docker.internal:11434`) no está en marcha.

1. Comprueba el estado: `docker compose ps` y `docker logs --tail 20 knowledge-graphs-ollama-1`. Un `connect() failed (111: Connection refused)` confirma que no hay servidor en el destino.
2. Arranca Ollama en el equipo de destino y comprueba que responde: `http://127.0.0.1:11434/api/version` desde ese equipo.
3. Confirma que los modelos configurados están disponibles (`ollama list`): `MEMORY_LLM_MODEL` y `MEMORY_EMBEDDING_MODEL`.
4. Repite `python scripts/deploy-memory.py --apply`. Hará una copia nueva antes de migrar; la migración ya aplicada es aditiva y no se repite de forma destructiva.

Mientras Ollama no responda, la API puede seguir aceptando operaciones, pero los trabajos de extracción y embeddings quedarán pendientes o fallarán; revísalos después en **Operaciones**.

## Comprobar una instalación

1. Comprueba salud de base, migración y API y que web y trabajador están activos.
2. Abre la web pública, documentación y acceso al panel.
3. Entra con una cuenta de prueba autorizada y revisa proyectos y políticas.
4. Con el cliente MCP, comprueba `projects`, búsqueda y apertura de detalle.
5. En un proyecto con captura autorizada, guarda una memoria de prueba y espera sus trabajos.
6. Recupérala de nuevo y verifica su ID, versión, contenido y procedencia.
7. Publica una fuente de prueba aprobada si el alcance requiere publicación; verifica hash y trabajos con `document_status`.
8. Revisa errores pendientes y descarta duplicados antes de cerrar la entrega.

`/health/ready` es la sonda de preparación usada por Compose. No demuestra por sí sola que el modelo responda, que se hayan generado embeddings ni que el contenido esperado exista. Los contadores de una tabla tampoco prueban su contenido: conserva IDs y hashes de aceptación.

## Inspección y copia de base

Las herramientas administrativas reales están en [admin.py](../memory_platform/admin.py). Ejecutan acciones contra la base configurada sin imprimir credenciales. Desde la raíz y con el entorno privado preparado, los comandos de Compose utilizan el perfil administrativo:

```powershell
docker compose --profile memory-admin run --rm --no-deps memory-admin inspect
docker compose --profile memory-admin run --rm --no-deps memory-admin backup --output /backups/kairos-2026-11-04.dump
```

El destino de la copia está dentro del volumen administrativo `memory-backups`. El comando rechaza sobrescribir un archivo existente. Elige un nombre nuevo y conserva la salida de tamaño y estado, sin secretos. Además de la copia de base, conserva de forma protegida la configuración necesaria para restaurarla y el material de credenciales; el dump no sustituye ese inventario.

Para sacar el archivo del volumen a un repositorio de copias externo, utiliza el procedimiento de tu infraestructura y comprueba permisos y checksum. No conviertas un volumen de copias en el único lugar donde vive una copia de producción.

## Probar una restauración sin sobrescribir producción

El subcomando `restore-check` exige una base distinta, recién creada y vacía, cuyo nombre empiece por `memory_restore`. La DSN del destino se suministra mediante un fichero privado montado en el contenedor administrativo.

```text
restore-check --backup /backups/kairos-2026-11-04.dump --target-dsn-file /run/secrets/restore_dsn
```

Este fragmento es el argumento del programa administrativo, no una orden completa que monte el secreto. El operador debe crear y autorizar el destino aislado y proporcionar el archivo mediante su configuración de infraestructura. No añadas contraseñas a la consola para completar el ejemplo.

La implementación rechaza el destino original y cualquier destino con tablas de aplicación. Ejecuta `pg_restore` con parada ante errores y compara las huellas del contenido restaurado con la base de origen. Realiza esta comprobación con una copia consistente y controla escrituras concurrentes: si el origen cambia después del dump, las huellas pueden diferir sin que ello pruebe corrupción del archivo.

Una prueba de restauración correcta demuestra que esa copia puede recuperarse en ese destino. Un retorno a producción requiere decidir ventana, acceso y credenciales; no se automatiza aquí una sustitución de la base activa.

## Retroceso de pgvector

**El retroceso no es simétrico.** Una vez creadas la extensión y las columnas, una imagen PostgreSQL sin pgvector no puede restaurar un dump posterior a la migración: el dump contiene `CREATE EXTENSION vector` y falla con `extension "vector" is not available`. En cambio, el código anterior sí funciona sobre la base migrada, porque la columna original `vector` sigue siendo la fuente y la escribe también la versión nueva. Elige según lo que haya fallado.

1. **Mantener la imagen nueva con el código anterior** (lo habitual). El informe privado conserva `previous_images` (identidades inmutables de API, worker y web). Prepara un override de Compose que apunte a ellas y arranca solo esos servicios:

   ```powershell
   docker compose -f docker-compose.yml -f <override-con-previous_images>.yml --profile memory up -d --no-build --no-deps memory-api memory-worker memory-web
   ```

   El código anterior lee y escribe `vector`; el disparador `memory.embedding_sync` rellena `embedding` en cada fila nueva, de modo que al volver a la versión nueva no queda ningún vector sin indexar. `admin migrate` del código anterior es idempotente sobre la base migrada. Coste conocido: algunas consultas del código anterior hacen `SELECT e.*` y ahora arrastran también `embedding` (como texto), así que leen del orden de 2 veces más datos por fila; no cambia resultados y desaparece al volver a la versión nueva (deuda aceptada).

2. **Volver a la imagen PostgreSQL anterior** (solo si el problema está en la imagen). Usa la copia hecha **antes** de migrar (`/backups/kairos-before-<fecha>.dump`), nunca una posterior, y restáurala en una instancia nueva, sin tocar el volumen en uso:

   ```text
   docker run -d --name memory-postgres-previa -e POSTGRES_USER=memory -e POSTGRES_DB=agent_memory -e POSTGRES_PASSWORD_FILE=/run/secrets/pw -v <secreto>:/run/secrets/pw:ro -v <volumen-nuevo>:/var/lib/postgresql/data postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5
   pg_restore --dbname=<destino> --no-owner --no-acl --exit-on-error /backups/kairos-before-<fecha>.dump
   ```

   Lo escrito después de esa copia **se pierde** en esta vía. Después comprueba `content-manifest` y `store_fingerprints` contra los de antes de migrar. No restaures sobre el volumen de producción.

Los dos caminos se ensayaron en la instancia aislada del despliegue (`testing/rollback-rehearsal.json` de la iniciativa): el código anterior devolvió el mismo `content-manifest` y buscó y escribió vectores sobre la base migrada; la copia previa se restauró en la imagen sin pgvector con `store_fingerprints` idénticos; y el dump posterior a la migración falló en esa imagen con el error citado.

## Recuperar operaciones de memoria

Una desconexión tras enviar puede dejar el resultado incierto. Usa la identidad estable del evento o documento y consulta su estado. Para documentos, compara el manifiesto con el ledger emisor, recorriendo su paginación. El procedimiento de conciliación está en [integración](integration.md).

No recrees el evento con otro UUID, no borres su outbox para empezar de cero y no publiques otra copia sólo porque un trabajo tarde. Los estados `failed` y `unknown` requieren actuaciones diferentes: el segundo puede haber producido efecto. Conserva recibos, hashes y versiones hasta confirmación.

Para fallos de modelo, revisa disponibilidad del servidor, sesión de nube si corresponde y el código de error sanitizado del trabajo. Cambiar modelo o desactivar procesamiento no es una recuperación neutra. Corrige la causa y reintenta de forma acotada conservando los datos originales.

## Claves y acceso

Las claves se muestran una vez al crearlas. Para rotación, crea una nueva con los mismos permisos mínimos necesarios, actualiza el fichero privado del cliente, comprueba una consulta y revoca la anterior. No revoques primero si eso deja al integrador sin un medio de recuperar la operación.

El bootstrap crea el acceso inicial; no es un comando documentado de restablecimiento universal. No lo presentes como cambio de contraseña garantizado para un usuario existente. Las contraseñas y DSN se manejan por archivos privados, nunca pegadas en documentación o incidencias.

## Monitorización y rendimiento

Observa latencia, tamaño de cola, intentos y errores del trabajador, salud de base y disponibilidad del modelo. Usa la misma consulta y los mismos datos para comparar rendimiento antes y después. No atribuyas mejoras a una optimización si cambió el ámbito o número de documentos.

En la web, reduce proyectos, capas y categorías para acotar recuperación y mapa. Utiliza vista de lista si el renderizado 3D limita el equipo. No aumentes indiscriminadamente concurrencia y tiempos de espera: pueden ocultar saturación y multiplicar solicitudes al servidor de modelos.

Los límites de petición, proveedor, lease e intentos están centralizados en `Settings`. Consulta el código y el entorno activo antes de modificarlos. Un timeout de consulta y el timeout de un trabajo de embeddings son límites diferentes.

## Qué incluir en una incidencia

Fecha y zona horaria, versión de distribución y cliente, servicio, proyecto, ID de elemento/evento/trabajo, versión y código de error. Añade los hashes esperados y observados si el problema es documental. Redacta logs antes de compartirlos; excluye cookies, claves, contraseñas, DSN y contenido privado.

Los comandos de esta guía se documentan a partir del código; redactar esta guía no ha ejecutado despliegues, copias, restauraciones ni mutaciones de datos.
