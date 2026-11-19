---
retro: reliable-operations
fecha: 2026-11-19
---

# Retro — reliable-operations

Iniciativa 3 del plan director: «Operación fiable». Cerrada el 2026-11-19 con 98 de 98 tareas y la spec `implementada`. Se entregó en dos PR, uno por hito, los dos fusionados en `main` con la CI en verde: [daycry/kairos#4](https://github.com/daycry/kairos/pull/4) (hito A, «no perder datos ni parar») y [daycry/kairos#5](https://github.com/daycry/kairos/pull/5) (hito B, «desplegar y detectar», con la versión 0.4.1; merge commit `d5be496`).

## Estimado frente a real

| Medida | Estimado | Real | Desviación |
|---|---|---|---|
| Horas IA de ejecución (TOTAL del ledger) | 55,0 h | 35,37 h (68 anotaciones `(medido)` y 9 `(estimado)` en el ledger) | −36 %, cota inferior: las fases 4 a 7 no tienen horas en su fila |
| Horas IA de las fases con horas registradas (todas salvo 4-7) | 35,8 h | 35,37 h | −1 % |
| Horas humanas | 412,8 h (base) | sin registrar | — |
| Coste | 20.640 € + tokens (⚠️ verificar) | sin cifra: no hay horas humanas ni precio de tokens verificado (`eur: null`) | — |
| Tokens | 13,76 M | 4,02 M facturables medidos con `usage-meter`, solo en 13 tareas de las fases 13 a 16 (sin contar los fix de T-94, que ya caben en su ventana) | no comparable: medición parcial |
| Calendario | 16 fases, 2 hitos | 5 días (2026-11-15 a 2026-11-19) | — |

Las `horas_ia` de `usage-meter` salen de los tokens con el ratio por defecto (300.000 tokens/hora): 1.023.355 tokens facturables de T-94 dan 3,41 h. Por eso esta iniciativa **no aporta un ratio tokens/hora medido**: derivarlo de esas horas sería circular.

### Desviación por fase (horas IA, real/estimado)

| Fase | Real/est. | Intentos de revisión | Nota |
|---|---|---|---|
| 1 Arnés de fallos | 0,83 / 4,3 | 2 | — |
| 2 Worker y caída de base | 2,10 / 3,6 | 3 | — |
| 3 Cola e índices | 0,99 / 3,6 | 2 | — |
| 4-7 Pool, permisos, copias, copia externa | — / 19,2 | 2, 2, 3, 2 | Sin horas en la fila de la fase |
| 8 Cierre del hito A | 1,06 / 1,0 | revisión del hito | — |
| 9 Compose | 0,27 / 2,6 | 4 (ciclo 2) | Horas probablemente incompletas para 4 intentos |
| 10 Despliegue | 5,48 / 4,6 | 5 (ciclo 2) | — |
| 11 Sonda | 4,95 / 3,1 | 2 | — |
| 12 Cola atascada y `doctor` | 2,62 / 3,1 | 1 | — |
| 13 Abstención | 2,36 / 4,5 | 2 | — |
| 14 Calibración de la abstención | **10,36 / 4,5** | 2 | T-89 (Ollama efímero) 4,58 h y T-92 (suite) 3,75 h |
| 15 Cierre del hito B | **3,51 / 0,3** | 3 + fix3 fuera del bucle | T-94: 3,41 h frente a 0,13 h |
| 16 Cierre de la iniciativa | 0,84 / 0,6 | 1 | — |

## Causas (respuestas del usuario, 2026-11-19)

- **Desviación principal: «Correcciones en cadena».** En el cierre del hito B, cada corrección de la recreación de `memory-probe` y `memory-backup` abrió un hallazgo Important nuevo:
  - El fix1 recreaba `memory-backup` solo con `docker-compose.yml`, y así perdía el override de `rclone` (N1).
  - El fix2 leía la etiqueta de Compose, pero imprimía una orden manual incompleta. Además, en un ensayo podía recrear con la imagen y el volumen de la instalación (R3-1 y R3-2).
  - Hizo falta un fix3 fuera del bucle de tres intentos, por decisión del usuario.
- **Incógnita más cara: «Metas de abstención».** El 70 % de abstención correcta con ≤ 5 % de falsa no se podía cumplir con el proveedor simulado de la CI ni con `nomic-embed-text`. Hubo que enmendar P-05 y CA-27 con metas por proveedor, y el modelo real quedó `uncalibrated` y diferido a la Iniciativa 5.
- **Qué se haría distinto: «Revisar el fix entero».** Cada fix de una revisión debe pasar por la misma lupa que la fase: casos límite de los servicios operadores y ensayos. No basta con una relectura dirigida a su hallazgo.

## Aprendizajes

1. **Un fix de revisión es código nuevo y se revisa como tal.** Los tres hallazgos Important del cierre del hito B los introdujeron fixes anteriores, no las fases. La revisión de un fix necesita el mismo nivel que la de la fase: lentes completas sobre su diff y casos límite de ensayo frente a instalación. Propuesta de lección en `docs/knowledge/candidates/` (ver más abajo).
2. **Recrear un servicio de Compose con solo el fichero base pierde sus overrides.** Para conservar lo que tenía, `up --force-recreate` debe recibir los mismos `-f` con que se creó el contenedor. Están en la etiqueta `com.docker.compose.project.config_files`. Propuesta de gotcha en `docs/knowledge/candidates/` (ver más abajo).
3. **Medir antes de fijar metas numéricas en la spec.** Las metas de abstención se aprobaron sin una medición previa con el modelo real ni con el simulado, y ninguno podía cumplirlas. Una meta que depende de un modelo se fija tras una medición exploratoria o se aprueba como provisional.
4. **La CI externa puede no ejecutarse.** Durante el hito B, GitHub Actions rechazó todos los trabajos por facturación, y la verificación se sostuvo con la suite local en Docker. Un criterio que dice «en la CI» necesita un equivalente local declarado. CA-28 se dio por verificado en local y se anotó así en la spec.
5. **La compactación del ledger fue trabajo recurrente.** `tasks.md` rozó el límite de 245.000 bytes en cada fase: llegó a 31 secciones de compactación en el historial, más una pasada de `ledger-archive.py`. Archivar las notas de cada fase al cerrarla, con `ledger-archive.py`, evita hacerlo bajo presión.

## Ajuste sugerido

- Presupuestar la revisión del diff completo de cada hito como partida propia, de al menos 2 h. En esta iniciativa se estimaron 0,13 h y llevó 3,41 h.
- Si la fase toca operación (despliegue, recreación de servicios, overrides de Compose), sumar un intento de revisión completo por cada fix.
- Las tareas que miden con modelos reales o corren la suite completa varias veces, como T-89 y T-92, llevaron entre 3,75 h y 4,58 h: estimarlas en unas 4 h.

## Propuestas de memoria técnica (pendientes de `knowledge-curator`)

Estado: [actualizado]. Las dos propuestas están en `candidates/pending/`, a la espera de `knowledge-curator`. Ninguna es todavía memoria aprobada.

| Tipo | Candidato | SHA-256 |
|---|---|---|
| Gotcha | `docs/knowledge/candidates/pending/2026-11-19-compose-recreate-loses-overrides.md` | `17d5ea1dce0a173634ab347ec17efff7baed8dc7ce543a6761ba1947fada64c9` |
| Lección | `docs/knowledge/candidates/pending/2026-11-19-review-fixes-like-new-code.md` | `5331f610f5e50660cafc2d3a58982ed0aefd19cafe37a3cb1998d81fa93cbecd` |
