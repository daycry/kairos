# Calibración de estimaciones

Este es el histórico que `evaluator` lee para estimar. `usage-meter.py` toma la mediana de la columna `tokens/hora` como ratio calibrado y descarta las celdas marcadas `(estimado)`.

| Fecha | Slug | Desv. producción % | Desv. tokens % | tokens/hora (medido) | Causa principal | Ajuste sugerido |
|---|---|---|---|---|---|---|
| 2026-11-12 | 2026-11-09-retrieval-quality | −73 (cota inferior, faltan las Fases 6 y 8) | sin medir | **(estimado)** sin medición por tarea de tokens ni de horas: derivar el ratio sería circular | Bucles de revisión de 2 o 3 intentos por fase, replanificación por la auditoría y medición incompleta | Presupuestar la revisión adversarial como partida propia (unas 0,5 veces la implementación) y medir cada T-XX con `usage-meter` |

> Ratio vigente: sin muestras medidas (mediana de 0 muestras); se usa el valor por defecto de 300000 tokens/hora.
