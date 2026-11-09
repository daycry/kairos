# Evidencia de pruebas: retrieval-quality

## Puerta `retrieval-eval` (Fase 1, C-01)

Puerta de calidad separada de la suite de regresión. Usa un PostgreSQL efímero dentro del build
de Docker y el proveedor de embeddings simulado (sin red, sin la base desplegada).

```bash
# Puerta como target de build (el build necesita red para las capas apt-get)
docker build --progress=plain --target retrieval-eval -f memory_platform/Dockerfile .

# Misma puerta sin red, sobre la imagen de test
docker build --target test -f memory_platform/Dockerfile -t kairos-test:rq .
docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 kairos-test:rq python -m memory_platform.tests.run_postgres
```

Advertencia: `docker build --network=none` NO funciona (falla en `apt-get` de las capas previas); la ejecución sin red
se hace con `docker run --network=none`. El informe no afirma «sin red»: registra `network_interfaces` y
`network_observation`, una observación local de `/sys/class/net` (sin ninguna conexión saliente), fuera de la
comparación de determinismo. La puerta se niega a ejecutarse si hay variables libpq que redirijan la conexión
(`PGHOSTADDR`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGSERVICE`, `PGSERVICEFILE`, `PGSYSCONFDIR`) y conecta con `hostaddr=127.0.0.1`.

- Sale con código 1 si no se cumplen los umbrales de `memory_platform/tests/retrieval_eval/thresholds.json`.
- Imprime `RETRIEVAL_EVAL_RESULT {json}` en el log del build (recall@1/5/10 y MRR por capa y subconjunto).
- Ejecuta la evaluación dos veces y registra `deterministic` (CA-03).

Ficheros:

- `baseline.json`: línea base sobre el código previo a C-03..C-06 (nace en rojo, CA-02). Copia idéntica en
  `memory_platform/tests/retrieval_eval/baseline.json`, que es la que usa la puerta para medir la ganancia por subconjunto.
- `dataset-v1.sha256`: hash congelado de `dataset-v1.jsonl` (`sha256sum -c dataset-v1.sha256`).

Regenerar la línea base solo si cambia el dataset (nuevo `dataset-v2`): extraer la línea
`RETRIEVAL_EVAL_RESULT` del log, guardarla con `json.dumps(indent=2, sort_keys=True)` en ambos sitios y
registrar el nuevo hash. Nunca se reescribe `dataset-v1.jsonl`.
