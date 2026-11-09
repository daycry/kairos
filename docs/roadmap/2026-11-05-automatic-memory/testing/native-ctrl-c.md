# Ctrl+C al cerrar un cliente nativo

Fecha: 2026-11-06. Alcance: lanzador de aceptación, no API ni servicios desplegados.

1. **Reproducción.** El usuario confirmó que Claude se había abierto y la traza apareció después de pulsar Ctrl+C. La pila mostraba `subprocess.run → communicate → wait → WaitForSingleObject`. Se añadió una regresión que inyecta `KeyboardInterrupt` al ejecutar el hijo: antes del parche, la excepción escapó del lanzador y terminó el propio runner de unittest con traceback y exit 1.
2. **Aislamiento.** El cliente ya estaba iniciado; el padre esperaba su cierre. No es un error de arranque ni prueba de que el MCP haya fallado. El `except Exception` de `main()` no captura `KeyboardInterrupt`, que hereda de `BaseException`. No se consultaron transcripciones ni se cambiaron permisos, procesos ajenos o credenciales.
3. **Hipótesis probada.** Una interrupción de consola durante la espera del proceso hijo atraviesa la captura actual de errores. La inyección determinista y la confirmación del usuario coinciden con ese camino. La espera en sí es el comportamiento previsto para `--open`.
4. **Corrección.** `main()` captura específicamente `KeyboardInterrupt`, devuelve JSON `cancelled`, `native_acceptance=false` y exit 130. Una interrupción durante `--run` se guarda también en su estado privado con exit 130, reemplazando cualquier resultado anterior; el recolector no puede reutilizar un éxito previo para esa ejecución cancelada. No se captura indiscriminadamente `BaseException` ni se declara aceptada una UI simplemente por cerrarse.

Validación: **11/11 pruebas** del lanzador, incluidas las dos regresiones de cancelación, con `python -m unittest discover -s kairos/scripts/tests -v`. La reproducción usa procesos simulados y datos sintéticos; no sustituye la interacción real dentro de la UI del cliente.

Comprobación nativa posterior: Claude sigue listando `kairos` como pendiente de aprobación. La configuración preparada y la clave restringida se conservan. Para continuar se debe abrir la carpeta de ensayo, revisar/aprobar Kairos mediante `/mcp` y salir con `/exit`; después puede ejecutarse `--run claude`. Ctrl+C es una cancelación y ahora se informa sin traceback.

La propuesta de gotcha queda pendiente de persistir mediante un servicio de conocimiento configurado para este producto; no se crea memoria manual ni se promueve conocimiento. El diagnóstico y sus regresiones quedan en el ledger técnico.
