# Fallo de arranque al simplificar redes

## Reproducción

El despliegue creó una copia de 157.558 bytes y aplicó la migración. `docker compose up` se detuvo durante la fase `start`. API, web, trabajador y proxy existentes terminaron con código 0; PostgreSQL siguió sano. Los servicios no llegaron a usar las nuevas imágenes. No se ejecutó la verificación final.

El diagnóstico de sólo lectura mostró que los contenedores seleccionados habían perdido sus conexiones a dos redes, mientras que otros consumidores seguían conectados. No había una traza de caída de la aplicación nueva. El informe anterior ocultaba el stderr de Compose; se corrigió por separado para conservar un diagnóstico acotado y redactado.

## Hipótesis y prueba

La definición nueva omitía `driver: bridge` en dos redes que anteriormente lo declaraban. Aunque el driver efectivo de Docker sea el mismo, el hash persistido de Compose conserva la presencia del campo. La implementación oficial explica el cálculo y la secuencia de recreación: [NetworkHash](https://github.com/docker/compose/blob/main/internal/confighash/hash.go) y [reconciliación de redes](https://github.com/docker/compose/blob/main/pkg/compose/reconcile.go). La fuente de main se usa como explicación; la comprobación del host se basa en los hashes observados, no en asumir que cualquier versión se comporta igual.

Se reprodujeron exactamente los dos hashes registrados en el host:

| Red | Definición original | Campo omitido |
|---|---|---|
| `webui` | `a34c5a4e713eec0a05343cc7032bc678d660fff906b23d5244b3cc54d450b071` | `7a1fa64f4e1dccd3fe419fce2c74867568ba8b9543068ff67b79b48dbc1ac1ba` |
| `inference` | `b98bb704e368c5d52ba904a5e3e77ea065bddc46c517dcde08a1e8613eb392c2` | `64f6ed42b3f4190880217bd3429f01882dc4a8f821f556b7a2492fe2f2d0b685` |

Los hashes de `memory-data` y `egress` ya coincidían con sus definiciones sin driver explícito; no se cambiaron. Así se evita convertir la corrección en otra recreación innecesaria.

## Corrección y regresión

Se restauró `driver: bridge` sólo en `webui` e `inference`. La regresión falló con el hash nuevo de `webui` antes de la corrección y pasa después con los hashes registrados. El script compara las definiciones y topología de las redes existentes antes de construir imágenes, migrar o arrancar servicios. Una divergencia se detiene en `configuration`, conservando los servicios que estén activos.

No se ejecuta `network rm`, no se desconectan otros consumidores y no se borran volúmenes. Los logs de fallo se redactan antes de recortarlos, para no exponer fragmentos de una contraseña en el límite del registro.

Las siete regresiones operativas pasan en el host. La recuperación final requiere volver a arrancar y comprobar el servicio: un test de hashes no acredita que el despliegue ya haya terminado. El estado vigente se conserva en el ledger y en el informe privado de despliegue.

Propuesta de conocimiento técnico pendiente de persistir mediante el servicio de curación: mantener la presencia de campos en redes compartidas y comprobar su hash antes de una migración de Compose. No se ha promovido automáticamente a conocimiento aprobado.
