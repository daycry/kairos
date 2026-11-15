---
retro: three-components
fecha: 2026-11-15
---

# Retro — three-components

Iniciativa 2 del plan director: Kairos separado en servidor, kairos-mcp y cliente, más la web. Cerrada el 2026-11-14 con 74 de 74 tareas, la revisión final en el intento 2 de 3 y el PR #3 fusionado en `main` (141e615) con la CI en verde.

## Estimado frente a real

| Medida | Estimado | Real | Desviación |
|---|---|---|---|
| Horas IA de ejecución (suma de las 74 tareas) | 32,1 h | 10,9 h medidas en 58 tareas con `usage-meter` (las demás constan como «incluido en» otra) | −66 % (cota inferior del real: varias correcciones comparten ventana y no se suman) |
| Horas humanas | 233,5 h (base) | sin registrar | — |
| Tokens | 9,64 M | sin medir por tarea; los revisores solo constan en la telemetría de los subagentes | — |
| Calendario | 8 fases | 3 días (2026-11-12 a 2026-11-14) | — |

La medición por tarea funcionó en esta iniciativa (en `retrieval-quality` no se midió), pero sigue sin cubrir dos cosas: los tokens de cada tarea y el coste de la revisión adversarial, que fue la partida más cara.

## Revisión adversarial por fase

| Fase | Intentos | Important encontrados | Nota |
|---|---|---|---|
| 1 Integración continua | 2 | sí | El disparador `pull_request` quedó sin ejercitar hasta el PR #3 |
| 2-4 Paridad, servidor sin modelo, esquemas | 1-2 | pocos | — |
| 5 kairos-mcp | 6 (2 ciclos) | 5 (uno por intento hasta el 5.º) | El mismo problema de CPU reapareció con variantes nuevas |
| 6 Compatibilidad | 1 | 0 | — |
| 7 Estructura | 2 | 1 (manuales) | — |
| 8 y final | 2 | 2 (README, PR) | — |

## Causa principal

**La fase 5 (respuesta del usuario: «La fase 5 (CPU)»).** La validación de entrada de kairos-mcp tuvo un hallazgo Important de consumo de CPU (CWE-400) en cada intento, y cada corrección cerraba solo la variante que se había señalado: recompilar el esquema, recorrer todos los errores, ramas de `anyOf`, bloqueo del event loop, cola detrás de las llamadas grandes. Hizo falta un segundo ciclo de revisión con el OK del usuario.

## Aprendizajes

1. **Corregir la clase entera, no la variante.** En un servicio Python de un solo proceso, un hallazgo de CPU no se cierra hasta que el trabajo está acotado, fuera del event loop, con vía rápida para entradas pequeñas y con plazo de espera. Pedir las cuatro cosas en la primera corrección y declarar como deuda el techo de CPU residual, que corresponde al proxy o al rate limiting del operador.
2. **Las pruebas con tiempos fallan en CI.** Dos tests de la fase 5 tuvieron que reescribirse (mejor de 3 ejecuciones, después un `threading.Event` determinista) porque fallaban en runners lentos.
3. **Un despliegue vivo que monta ficheros del árbol de trabajo se rompe con los cambios de la rama.** El proxy de Ollama desplegado montaba su plantilla desde el repositorio y entró en bucle tras T-13. Antes de cambiar un fichero montado hay que comprobar qué contenedores lo usan.
4. **Los criterios que dependen de una acción externa (abrir un PR) se marcaron antes de que ocurriera.** La revisión final lo detectó. Esos criterios se cierran solo con la evidencia de la acción.

## Ajuste sugerido

Presupuestar la revisión adversarial como partida propia (al menos 0,5 veces la implementación, y el doble para servicios expuestos a entradas de clientes) y medir con `usage-meter` también los intentos de revisión, que siguen sin medición propia.
