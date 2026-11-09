# Ensayo nativo de las 12:34 UTC y candidato 0.1.3

## Resultado real recibido

Las llamadas de lectura projects/context terminaron correctamente en Claude, Codex y OpenCode. Codex y OpenCode respondieron `KAIROS_CONTEXT_MISSING` en sus pruebas sin herramientas. Ambos marcadores se retiraron: sus recibos de creación y retirada están aceptados. El ensayo no acepta contexto automático por obtener exit 0.

Con lectura mediante la clave del ensayo, los eventos persistidos son:

| Ejecución | Evidencia observada |
| --- | --- |
| Claude anterior | Los cuatro eventos de ciclo de vida ya verificados |
| Codex, contexto 12:34:16 UTC | SessionStart y UserPromptSubmit; faltan Stop y SessionEnd |
| Codex, lectura 12:34:43 UTC | SessionStart; no se acepta el ciclo completo |
| OpenCode, contexto 12:35:22 UTC | Sin eventos de esa sesión |
| OpenCode, lectura 12:35:39 UTC | Sin eventos de esa sesión |

No se reconstruyen registros que el cliente no entregó ni se reenvían los episodios anteriores. Los resultados completos sin contenido privado siguen en `native-client-acceptance.json`.

## Causas comprobadas y alcance de las correcciones

**Recolector:** cada comprobación abría otra sesión web administrativa. La API limita los inicios de sesión a diez en quince minutos, incluidos los correctos, por lo que varias recogidas produjeron HTTP 429. No se modifica ni debilita ese control. El recolector usa ahora la clave de lectura existente del ensayo, con rutas GET acotadas a notas, historial y recibos. La lectura posterior recuperó la verificación positiva de Claude y distinguió los eventos ausentes de los errores de autenticación del recolector.

**OpenCode 2:** `ctx.session.get` devuelve una respuesta con `data`. El adaptador 0.1.2 buscaba `location` directamente en la envoltura y omitía los envíos por no poder resolver su carpeta. La API nativa confirma la localización de la sesión y el formato documentado incluye esa envoltura. La regresión `OpenCode V2 unwraps the native session data envelope before scope checks` falló antes del cambio (`undefined` en vez de contexto) y pasó después. La corrección desenvuelve `response.data ?? response` antes de aplicar el control de pertenencia; las sesiones ajenas siguen excluidas. También se conserva la forma directa y el adaptador V1.

**Codex:** la salida nativa contiene el aviso `running async SessionEnd hook synchronously`. Es una normalización documentada, no una llamada a herramientas; el recolector deja de contarla como tal y conserva un diagnóstico. Otros errores nativos siguen siendo errores, sin exportar sus mensajes privados. En el runtime 0.1.3, Stop y SessionEnd ya son síncronos y tienen ocho segundos para completar la admisión local; no esperan generación de modelos. Esto elimina el aviso de SessionEnd y establece un orden explícito de cierre.

El dispatcher de Codex no respondía al comprobarlo después de la ejecución. El ensayo prepara ahora el worker mediante el runtime instalado antes de lanzar el cliente, como proceso hermano y no como hijo de uno de sus hooks. Si la preparación falla, actualiza el estado de la prueba y no abre el cliente. Es una medida de aislamiento del ciclo de vida; **todavía no se ha probado que resuelva todos los síntomas nativos de Codex**, ni se atribuye una causa única al marcador ausente. La nueva ejecución debe confirmar contexto y ambos eventos finales antes de cerrar el criterio.

La comprobación directa y de sólo lectura de Dispatcher.context con los parámetros de la prueba devuelve contexto; tampoco se reprodujo un rechazo por el límite de caracteres. No se cambian límites de contexto ni saneado basándose en esas hipótesis descartadas.

## Distribución y validación

- Runtime local **0.1.3**, no publicado en npm. El tarball 0.1.2 se conserva sin modificaciones.
- 56/56 pruebas de scripts Python.
- 67/67 pruebas del cliente en Windows, sin skips. Se ejecutaron en un proceso (`--experimental-test-isolation=none`) porque la creación del proceso de aislamiento del runner fue rechazada con EPERM en esta sesión. Incluyen IPC real y actualización/recuperación desde 0.1.0 y 0.1.2.
- `npm pack --offline`, con caché propia del workspace: 18 archivos cotejados byte por byte con las fuentes.
- Instalación real mediante npm exec offline del tarball en una carpeta sintética para los tres clientes; doctor local configurado, exit 0, sin comprobación de red ni claves reales.
- Paquete: [package-0.1.3.json](package-0.1.3.json). La configuración y la confianza nativas no se deducen de estos tests.

No cambia la API, el esquema de datos, los modelos, los puertos o los contenedores. El nuevo helper permite refrescar sólo los runtimes de ensayo reutilizando sus claves, sin volver a activar ni crear otras. El intento desde esta sesión se detuvo por PermissionError en el bloqueo privado, antes de modificar los ensayos reales.

## Aplicar y repetir

Cierra las sesiones nativas de ensayo. Desde la raíz del stack:

```powershell
python kairos/scripts/accept-native-clients.py --refresh-runtime codex
python kairos/scripts/accept-native-clients.py --refresh-runtime opencode
python kairos/scripts/accept-native-clients.py --open codex
```

Los dos primeros deben devolver `runtime_refreshed`, versión 0.1.3. Si el instalador detecta un propietario activo, conserva los archivos y espera a que el dispatcher anterior termine por inactividad; no borres sus locks. Dentro de Codex, revisa de nuevo los hooks de Kairos con `/hooks` porque cambió su definición y su ruta de runtime. Sal normalmente.

```powershell
python kairos/scripts/accept-native-clients.py --run-context codex
python kairos/scripts/accept-native-clients.py --run codex
python kairos/scripts/accept-native-clients.py --run-context opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --run opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --collect
```

No repitas `--enable-capture`: los dos ensayos ya están en summary. Tampoco es necesario reconstruir Docker. Si cualquier comando falla, conserva su salida y detén esa secuencia. Recuperación de un marcador pendiente: `--retire-context CLIENT`.

La aceptación global y C-08 continúan abiertos hasta contrastar la repetición y resolver las incidencias registradas, incluida la cancelación de Stop en la ejecución anterior de Claude. La propuesta técnica queda documentada aquí y pendiente del servicio de curación configurado; no se escriben memorias personales.
