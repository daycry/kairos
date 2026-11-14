# Kairos — instrucciones para agentes

## Ledger canónico

El progreso de un plan se registra en `docs/roadmap/<fecha>-<slug>/tasks.md`; cualquier implementador debe marcar ahí cada tarea; los ledgers propios son espejo, no fuente.

## Restricciones operativas

- Nunca ejecutes pruebas destructivas contra la base de datos desplegada; usa fixtures aislados de PostgreSQL, HTTP y navegador.
- Las migraciones son aditivas: no borres tablas, columnas ni volúmenes existentes.
- Conserva el contrato de las herramientas MCP existentes (`docs/contracts/kairos-mcp.json`).
