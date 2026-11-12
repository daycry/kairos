---
retro: retrieval-quality
fecha: 2026-11-12
---

# Retro — retrieval-quality

La iniciativa 1 del plan director cerró sus 38 tareas en 8 fases entre el 2026-11-09 y el 2026-11-12. Mejoró la búsqueda de forma medible: recall@5 pasó de 0,50 a 1,00 y el MRR, de 0,34 a 0,97. El contrato MCP no cambió. La comparación entre lo estimado y lo real **no es fiable**, porque la medición quedó incompleta.

## Estimado frente a real

| Partida | Estimado | Real registrado | Desviación | Fiabilidad |
|---|---|---|---|---|
| Horas humanas equivalentes | 173 h base (199,2 h con margen) | 0 h | — | Sin registro: el trabajo lo hizo la IA con supervisión puntual |
| Horas IA de ejecución | 26,03 h base | 7,13 h | −73 % | Baja: las Fases 6 y 8 no tienen tiempo medido |
| Supervisión | 6,5 h | sin registro | — | — |
| Tokens facturables | ~7,78 M | sin medir por tarea | — | Solo hay datos sueltos de subagentes: el implementador de la Fase 8 usó unos 409k tokens y su corrección, 133k |
| Coste | 9.960 € de desarrollo + tokens ⚠️ | sin cifra | — | No hay precio de tokens verificado |

La única cifra comparable, −73 % en horas IA, es una cota inferior del trabajo real y no una medida: faltan las Fases 6 y 8, que fueron las de más ciclos de revisión.

## Causas (confirmadas por el usuario el 2026-11-12)

1. **Bucles de revisión.** La revisión de dos lentes necesitó 2 o 3 intentos por fase, y cada vez encontró problemas importantes reales: en la Fase 8, la cola de `/metrics` que leía todos los trabajos fallidos. Corregir y volver a revisar costó casi tanto como implementar.
2. **Replanificación a mitad.** La auditoría de la plataforma y la decisión de usar un VPS cambiaron T-36 y T-38: no hubo despliegue local, sino un ensayo aislado. Además, la Fase 8 heredó deudas de las Fases 6 y 7 (R2, R3, N1 y N2).
3. **Sorpresas del modelo real.** La ejecución con Ollama real no se comportó igual que el proveedor simulado (`ca18:long`). Las mediciones reales, de unos 23 minutos por evaluación y hasta 414 s por documento largo, consumieron mucho tiempo de reloj.
4. **Medición incompleta.** `usage-meter` no se usó en todas las tareas, y por eso la comparación entre estimado y real no sirve para calibrar.

## Aprendizajes

- La revisión adversarial merece su coste: cazó defectos que la suite en verde no detectaba en todas las fases. Hay que presupuestarla como una partida propia, no como un margen.
- El proveedor simulado sirve para la puerta de regresión, pero no sustituye a una ejecución con el modelo real antes de dar por buena la calidad. Conviene hacerla antes, no en la última fase.
- Sin medición por tarea no hay calibración. La siguiente iniciativa debe abrir y cerrar `usage-meter` en cada `T-XX` y en cada intento de revisión.

## Ajuste sugerido

Estimar la revisión adversarial como una partida explícita de unas 0,5 veces la implementación de cada fase, para 2 o 3 intentos. Además, adelantar a la primera fase con semántica una ejecución contra el modelo real.

## Deuda que pasa a otras iniciativas

- Ajustar la fusión contra el modelo real (`ca18:long`) y repetir el ensayo con el árbol final: Iniciativa 5.
- Convertir el guardarraíl del arnés en una lista de permitidos, si el arnés se usa fuera de este equipo.
- Archivar el ledger (227 KB, cerca del tope de lectura de 256 KiB) con `ledger-archive.py`.
