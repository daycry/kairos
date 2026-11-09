# Instalar el servidor desde cero

Esta guía instala una instancia nueva. Para actualizar una instalación con datos utiliza [operación y recuperación](operations.md). Para conectar un agente a un servidor que ya funciona utiliza [instalación de clientes](install.md).

## Requisitos

- Docker Desktop funcionando en Windows, o Docker Engine con Compose en un servidor Linux.
- Python 3.11 o posterior para los scripts del operador. El backend y sus dependencias se construyen dentro de Docker.
- Git y, si clonas mediante GitHub CLI, una sesión de `gh` con acceso al repositorio.
- Acceso de red para descargar las imágenes y dependencias durante la primera construcción.
- Un servidor Ollama accesible con los modelos configurados disponibles y, para modelos cloud, su sesión autorizada. El servicio `ollama` del Compose es un proxy hacia ese servidor; no instala ni descarga modelos por sí mismo.

Los accesos locales usan `5173` para la web y `8790` para la API. Comprueba que esos puertos estén libres. PostgreSQL no publica su puerto. Los volúmenes tienen nombres estables para conservar instalaciones existentes; no levantes otra copia del repositorio suponiendo que será una instancia independiente.

## Descargar y preparar la configuración

Desde una carpeta de trabajo:

```powershell
gh repo clone daycry/kairos
cd kairos
Copy-Item -LiteralPath .env.example -Destination .env
```

El repositorio contiene directamente `docker-compose.yml`, `.env.example`, `memory_platform`, `web`, `packages`, `scripts` y `docs`. No necesitas una segunda carpeta del producto dentro de la raíz.

Edita `.env` según la [referencia de configuración](configuration.md). En Windows, el ejemplo utiliza `C:/docker-secrets/knowledge-memory` para los secretos, fuera del repositorio. Conserva los modelos y el destino de Ollama si ya los tienes preparados. Los valores predeterminados de esta distribución son `beam:cloud` y `nomic-embed-text`; una instalación nueva debe comprobar que su proveedor permita usarlos.

En Linux, selecciona una ruta privada accesible para el operador y Docker, por ejemplo `/srv/kairos/secrets`, y configura esa misma ruta en `MEMORY_SECRETS_DIR`. El destino `host.docker.internal` del ejemplo está pensado para Docker Desktop: en otro entorno define un destino de Ollama que sea realmente accesible desde el contenedor.

No copies credenciales a `.env.example`, al README ni al repositorio. `.env` y `.private` están excluidos de Git.

## Primera instalación

Primero muestra el plan, sin iniciar servicios ni crear secretos:

```powershell
python scripts/deploy-memory.py
```

Sólo en una instalación nueva de Windows, aplica:

```powershell
python scripts/deploy-memory.py --apply --fresh --secret-dir C:/docker-secrets/knowledge-memory
```

En Linux utiliza la ruta que configuraste en `.env`:

```sh
python3 scripts/deploy-memory.py --apply --fresh --secret-dir /srv/kairos/secrets
```

El script comprueba Docker, prepara los archivos privados que falten, construye imágenes, inicia la base, aplica las migraciones y prepara el usuario inicial. No reemplaza secretos existentes. Si encuentra una instalación existente conserva sus datos y realiza una copia previa antes de migrar. No uses `--fresh` para eludir un problema con un volumen o unas credenciales.

La salida debe terminar con `Kairos deployment verified`. Si falla una fase, las posteriores no se ejecutan. Inspecciona el estado antes de repetir. Una construcción correcta o un HTTP 200 no sustituyen la verificación final de herramientas MCP y manifiestos documentales.

## Acceso inicial y primer proyecto

Abre `http://127.0.0.1:5173/`, entra en el panel `/app/` y utiliza el usuario inicial `admin`. La contraseña está en el archivo privado `bootstrap_password`; no hay una contraseña universal publicada. En tu propia terminal privada de Windows puedes leerla así:

```powershell
Get-Content -LiteralPath C:/docker-secrets/knowledge-memory/bootstrap_password
```

No pegues esa salida en chats, tickets o logs. En Windows restringe los permisos NTFS de la carpeta privada al operador y al acceso que necesite Docker Desktop.

Desde **Configuración** crea el proyecto, asigna permisos y decide su política de captura. La instalación no importa repositorios, conversaciones ni candidatos pendientes. La captura empieza desactivada en proyectos nuevos. Crea una clave limitada al proyecto y sigue [instalación de clientes](install.md) para conectar Claude Code, Codex u OpenCode.

Prueba una memoria sintética, comprueba su recibo y procesamiento y recupérala por su proyecto y procedencia. El [manual de usuario](manual.md) explica las vistas, filtros, reglas, trabajo y consultas.

## Instalar en un servidor remoto

Utiliza un nombre DNS y un proxy HTTPS. El ejemplo [Caddyfile.example](../memory_platform/Caddyfile.example) redirige hacia la web local. Mantén `5173` y `8790` enlazados a loopback; no expongas directamente PostgreSQL.

Configura `MEMORY_ALLOWED_ORIGINS` con el origen HTTPS exacto y `MEMORY_COOKIE_SECURE=1` antes de recrear los servicios. Un origen es el esquema y el dominio, sin rutas ni barra final. Para los clientes, la URL base será la dirección HTTPS del servidor y MCP estará en `/mcp/`; no necesitan acceso a carpetas remotas.

## Actualizar, comprobar y recuperar

En una instalación existente utiliza:

```powershell
python scripts/deploy-memory.py --apply
```

El procedimiento conserva configuración, secretos, modelos y volúmenes; no cambia la política de captura ni reenvía fuentes. Para diagnosticar sin modificar servicios:

```powershell
python scripts/diagnose-deployment.py
```

El despliegue registra su resultado privado en `.private/deployment-status.json`. Si cambiaste la contraseña de administrador, el verificador puede usar `--verify-key-file` con una clave existente de lectura para los proyectos necesarios. Las copias, restauraciones aisladas, recuperación de trabajos y problemas de conexión están documentados en [operación](operations.md).
