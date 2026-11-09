# OpenCode: proveedor rechaza el modelo antes de llamar a Kairos

La prueba real iniciada el 2026-11-06 a las 09:58:18 UTC terminó con exit code 1, sin timeout. El stream contiene step_start y error, ninguna llamada MCP y stderr vacío. Error estructurado: `provider.auth`, HTTP **403**, modelo no disponible. No se exporta el mensaje privado completo.

Sesión: `ses_e4fb48837ffeMen5g1ePO7GhJA`. La API nativa de mensajes de esa sesión identifica el modelo seleccionado como `opencode/crouton-alpha-free`. La API de modelo predeterminado confirma ese mismo modelo. El historial local de selección reciente contiene otro modelo, pero no prueba que fuera el utilizado por esta ejecución: por eso se contrastó la sesión concreta.

El doble registro global de custom-agents se había reparado y verificado previamente: [opencode-plugin-repair.json](opencode-plugin-repair.json). El error actual ocurre antes de las llamadas controladas projects/context. No demuestra un fallo del MCP de Kairos ni permite aceptar la integración de OpenCode. Tampoco permite afirmar que una credencial esté mal escrita; el proveedor devuelve 403 y clasifica la indisponibilidad bajo provider.auth.

## Repetición con selección explícita

Hay que indicar un modelo que el operador tenga disponible en OpenCode. La [documentación oficial de modelos](https://opencode.ai/v2/docs/models/) describe `/models` y `opencode run --model proveedor/modelo`: la selección para una ejecución no modifica el valor predeterminado.

El helper acepta ahora la misma selección, limitada al ensayo acotado de OpenCode:

```powershell
# Sustituir PROVEEDOR/MODELO por un identificador real elegido por el operador.
python kairos/scripts/accept-native-clients.py --run opencode --model PROVEEDOR/MODELO
python kairos/scripts/accept-native-clients.py --collect
```

No cambia la configuración global, el modelo del servidor de Kairos, autenticación ni permisos. Sin `--model` conserva el comportamiento anterior; no busca otro proveedor ni reintenta modelos por su cuenta. El parámetro se rechaza en otros clientes, en la apertura interactiva o si no tiene formato válido. El modelo explícito queda como metadato de esa ejecución en `explicit_test_model`.

El recolector incorpora `native_errors` con tipo y código HTTP, sin contenido privado. No marca lectura aceptada si hay un error nativo aunque aparecieran llamadas anteriores. Tres regresiones nuevas cubren selección limitada a un comando, rechazo anterior al lanzamiento y error de proveedor sin exportación de texto. Total de scripts: **30/30 pruebas**.

Resultado posterior: el operador autorizó un modelo gratuito y ejecutó el ensayo con `opencode/big-pickle`. La sesión de las 10:19 UTC terminó exit 0 y completó projects/context. Se acepta lectura tras corregir el reconocimiento de Code Mode del recolector; [evidencia y regresiones](native-opencode-read.md). No se ha activado captura de OpenCode ni se han tocado credenciales.
