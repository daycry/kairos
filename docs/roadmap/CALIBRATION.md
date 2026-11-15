# Calibración de estimaciones

Este es el histórico que `evaluator` lee para estimar. `usage-meter.py` toma la mediana de la columna `tokens/hora` como ratio calibrado y descarta las celdas marcadas `(estimado)`.

| Fecha | Slug | Desv. producción % | Desv. tokens % | tokens/hora (medido) | Causa principal | Ajuste sugerido |
|---|---|---|---|---|---|---|
| 2026-11-12 | 2026-11-09-retrieval-quality | −73 (cota inferior, faltan las Fases 6 y 8) | sin medir | **(estimado)** sin medición por tarea de tokens ni de horas: derivar el ratio sería circular | Bucles de revisión de 2 o 3 intentos por fase, replanificación por la auditoría y medición incompleta | Presupuestar la revisión adversarial como partida propia (unas 0,5 veces la implementación) y medir cada T-XX con `usage-meter` |
| 2026-11-15 | 2026-11-12-three-components | −66 (horas IA, cota inferior: 10,9 h medidas frente a 32,1 h estimadas) | sin medir | **(estimado)** horas medidas por tarea pero sin tokens por tarea: no hay ratio medido | Fase 5: el hallazgo de CPU de kairos-mcp reapareció como variante nueva en seis intentos de revisión | Presupuestar la revisión adversarial como partida propia (≥0,5 veces la implementación, el doble para servicios expuestos a clientes) y medir también los intentos de revisión |

> Ratio vigente: sin muestras medidas (mediana de 0 muestras); se usa el valor por defecto de 300000 tokens/hora.
