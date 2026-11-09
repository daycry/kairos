# OpenCode: custom-agents aparece dos veces y una falla

## Reproducción y causa comprobada

El operador abrió el ensayo con `python kairos/scripts/accept-native-clients.py --open opencode` y vio dos entradas custom-agents. Se consultó la API de sólo lectura del servicio local de OpenCode, `GET /api/plugin`, autenticándose con su archivo de servicio sin imprimir la contraseña. Dos entradas devuelven el mismo ID `custom-agents`: una `state.status=active` y otra `state.status=failed`, con `state.error=Duplicate plugin ID: custom-agents`.

La configuración global `opencode.json` registra explícitamente `plugins/custom-agents` mediante una ruta absoluta de Windows con barras `/`. El mismo directorio está en la carpeta global de descubrimiento automático. El `package.json` identifica `custom-agents-hooks` y el módulo exporta `id: custom-agents`. El ensayo de Kairos sólo instala su adaptador `kairos-memory`; no añade una segunda declaración custom-agents.

OpenCode documenta el [descubrimiento automático de directorios locales](https://opencode.ai/v2/docs/plugins). El proyecto original tiene una [incidencia reproducida del mismo caso en Windows](https://github.com/anomalyco/opencode/issues/48706): una ruta explícita con barras `/` no se deduplica con la ruta descubierta y el segundo registro falla por ID repetido. La API local confirma ese síntoma; no se atribuye a un fallo de Kairos ni de la API de memoria.

## Reparación preparada

Desde la raíz del stack, con la interfaz de ensayo cerrada:

```powershell
# Sólo inspección; no escribe.
python kairos/scripts/repair-opencode-plugins.py

# Aplicación por el operador, con escritura en su configuración global.
python kairos/scripts/repair-opencode-plugins.py --apply

# Abrir de nuevo y revisar que custom-agents aparece una sola vez activo.
python kairos/scripts/accept-native-clients.py --open opencode
```

El script retira únicamente las declaraciones de texto que apuntan al directorio custom-agents ya descubierto automáticamente. Verifica la identidad del paquete y del módulo antes de editar. Conserva el plugin y el resto de la configuración. Si la entrada contiene opciones, se detiene para no perderlas. Rechaza enlaces/junctions en las rutas operadas, configuraciones JSON inválidas y cambios concurrentes detectados.

Antes de reemplazar el archivo guarda sus bytes originales en `opencode.json.kairos-before-<id>.bak`, junto al original. Escribe mediante temporal exclusivo y reemplazo; un error de permisos conserva el destino y la copia previa. La ejecución repetida devuelve `already_clean` sin crear copias adicionales. No reinicia el servicio compartido, modifica modelos, activa captura ni cambia claves.

Para recuperar la configuración, cerrar la interfaz y restaurar la copia exacta indicada por `backup_file` sobre `opencode.json`, conservando previamente cualquier cambio posterior. No se hace restauración automática que pueda sobrescribir cambios ajenos.

## Validación y estado

- Reproducción real: activo + fallido con `Duplicate plugin ID: custom-agents`, confirmado mediante API.
- Plan de reparación real: `repair_required`, una declaración redundante, `applied=false`.
- Hash previo del archivo: `5f2c19efc9d363aba0b538360805f3919ed31673473ee4b7b418b3e5497068ae`.
- Hash esperado tras retirar esa declaración: `3a1689520689222b217d5107e8e7becc3fbbd2aae41dc086435cd6a941b650c1`.
- `python -m unittest discover -s kairos/scripts/tests -v`: **27/27**. Seis regresiones nuevas comprueban plan sin mutación, conservación de ajustes/código/copia previa e idempotencia, rechazo de opciones, fallo de reemplazo, cambio concurrente e identidad errónea.

El operador aplicó después la reparación. La comprobación independiente confirmó `already_clean`, cero entradas redundantes y el hash posterior esperado; el hash de la copia previa coincide también. La API nativa del servicio OpenCode 2.0.12 devuelve ahora **una sola entrada custom-agents, activa y sin error**. La recarga automática bastó: no se reinició el servicio compartido. Evidencia: [opencode-plugin-repair.json](opencode-plugin-repair.json). Esto resuelve el doble registro, pero aún no acepta lectura, contexto o captura de Kairos en OpenCode.

La propuesta de conocimiento técnico queda pendiente de persistir en un servicio de curación configurado. Síntoma, causa comprobada, alternativa, regresiones y verificación real quedan en este informe; no se modifican memorias personales.
