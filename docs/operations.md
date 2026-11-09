# Operación y recuperación

Última actualización: 2026-11-06.

## Identidad y datos existentes

El código mantenido está directamente en la raíz del repositorio. Ejecuta `python scripts/deploy-memory.py --apply` desde esa raíz. Los ejemplos históricos que anteponen `kairos/` pertenecen a la disposición anterior del workspace; no son un segundo producto ni otra definición Compose activa.

Una reubicación de código no migra automáticamente las instalaciones de clientes que vinculan una raíz física, ni sus colas privadas. Los proyectos consumidores que no se hayan movido mantienen su configuración. Para ensayos nativos preparados en una ruta retirada, crea un ensayo nuevo en lugar de editar a mano los enlaces o reutilizar una outbox bajo otra raíz. Conserva las evidencias anteriores con su fecha y ámbito originales.

El archivo [docker-compose.yml](../docker-compose.yml) es la definición de esta distribución. Conserva la identidad de infraestructura `knowledge-graphs` y los nombres de volúmenes existentes para no crear una base vacía al cambiar la carpeta del producto. El directorio de código y el nombre de un volumen no son lo mismo.

No ejecutes `down -v`, limpiezas de volúmenes ni una restauración sobre la base de producción como parte de una actualización ordinaria. Mantén las credenciales, modelos, proyectos, políticas y puertos existentes. La captura permanece según la política de cada proyecto; desplegar no autoriza activarla.

La actualización del 5 de noviembre añade `capture_policy` y un argumento opcional `project_id` a `event_status`; no necesita migración adicional ni reindexación. Despliega y verifica el servidor antes de activar los hooks nuevos en consumidores. Una comprobación `doctor --online` con automatización configurada detecta un servidor que todavía no ofrece ese contrato. Las colas locales anteriores y sus recibos deben conservarse. Cambiar el servidor o la identidad del proyecto crea otra partición local; no copies a ciegas una cola a otra conexión. Los modos, estados y recuperación local están en [instalación](install.md).

La ampliación del 6 de noviembre añade tablas de trabajo compartido y consultas generadas mediante migraciones aditivas. Conserva las listas privadas, memorias, documentos, identidades y hashes anteriores. No requiere reindexar ni reenviar fuentes. El despliegue verifica las nuevas herramientas de observaciones, equipo y corpus: un servidor anterior con sólo las herramientas básicas no se considera actualizado. El panel debe mostrar **Observaciones**, **Reglas del proyecto**, **Actividad** y **Consultar corpus** después de actualizar su imagen. El análisis local de código requiere actualizar explícitamente el runtime del cliente; desplegar la web no modifica los proyectos consumidores.

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
