# Revisión final de retrieval-quality (T-37)

- **Fecha**: 2026-11-12
- **Alcance**: Fase 8 (T-34, T-35, T-36 y T-38) sobre la base `cae1e13`. Las Fases 1 a 7 se revisaron en su propio ciclo; sus tablas están en `tasks.md`.
- **Lentes**: A (conformidad), B (corrección), C (seguridad) y D (rendimiento). C se activó por `docker-compose.yml` y D por el código de métricas y trabajos.
- **Intentos**: 2 de 3. El trazado completo está en `tasks.md`, en «Revisión de dos lentes — intento 1 y 2: Fase 8».

## Veredicto

No queda ningún hallazgo Critical ni Important abierto. La Fase 8 y la iniciativa pueden cerrarse.

| Comprobación | Resultado |
|---|---|
| Contrato MCP (`docs/contracts/kairos-mcp.json`) | Sin cambios; 34 herramientas |
| Migraciones | Solo aditivas; esquema v11 con un índice parcial; `test_migrations_additive` lo vigila |
| Puertas y umbrales | Ninguno relajado; `thresholds.json` y `baseline.json` intactos |
| Puerta offline | `gate.passed: true`; recall@5 1,00 y MRR 0,9715 con fusión |
| Puerta con Ollama real | Pasa todo salvo `ca18:long` (ver la decisión de abajo) |
| Fugas en logs y métricas (R-08) | Ninguna: los loggers de terceros nunca bajan de INFO; las etiquetas de métricas tienen valores cerrados; los informes no contienen secretos |
| Base desplegada | No se tocó: todas las pruebas usaron contenedores y bases aislados |

## Decisión del usuario sobre CA-18 con el modelo real

Con `nomic-embed-text`, una de las 12 preguntas de documentos largos queda en 2.ª posición. Por eso el MRR fusionado de ese subconjunto es 0,958, frente a 1,00 de la capa semántica sola. El usuario decidió el 2026-11-12 aceptarlo como deuda. CA-18 y la puerta offline no cambian. El ajuste de la fusión con el modelo real pasa a la Iniciativa 5 (búsqueda semántica en producción en el VPS).

## Hallazgos

| Intento | Grado | Hallazgo | Estado |
|---|---|---|---|
| 1 | Important | La consulta de profundidad de cola leía todas las filas `failed` y la documentación decía lo contrario | Corregido: la cola pasa de 96,7 ms a 0,16 ms con 500.000 trabajos |
| 1 | Minor | El guardarraíl del Ollama desplegado se evadía con otras grafías del host | Corregido |
| 1 | Minor | `test_migrations_additive` no veía DDL dentro de literales, `DELETE` en Python ni `ALTER` de varias cláusulas | Corregido |
| 1 | Minor | La ventana de bloqueo del índice v11 no estaba documentada | Corregido: 384 ms medidos con 500.000 trabajos |
| 1 | Minor | El ensayo de T-38 se hizo antes de las correcciones | Corregido: la nota de T-38 explica que los cambios posteriores no tocan el esquema ni el despliegue |
| 1 | Minor | Atribución de deudas al plan director; CA-18 ausente de `architecture.md` | Corregido |
| 2 | Minor | Comentarios de `n2-measure.py` y del ledger que contradecían la medición | Corregido |
| 2 | Minor | La serie `failed` de `kairos_jobs_queue_depth` no incluye los destinos `other` | Documentado en `operations.md` |
| 2 | Minor | El guardarraíl sigue siendo una lista de exclusión sin resolución DNS (IP de la LAN, `192.168.65.254`, nombres que resuelven al equipo) | Deuda aceptada; límite documentado en `operations.md` y en `run.py` |
| 2 | Minor | Un `--` dentro de un literal SQL oculta el DDL que le sigue en `test_migrations_additive` | Deuda aceptada: hoy no hay ningún caso en `schema.sql` |

## Deuda que pasa a otras iniciativas

- Ajustar la fusión contra el modelo real (`ca18:long`), en la Iniciativa 5.
- Ensayar de nuevo el despliegue con el árbol final antes del corte en el VPS, en la Iniciativa 5.
- Guardarraíl del arnés por lista de permitidos (solo nombres de contenedor), si el arnés se usa fuera de este equipo.
