# Contracts

| File | What it is |
|---|---|
| `memory-platform.openapi.json` | OpenAPI of the REST API, exported by `scripts/export-contracts.py` |
| `kairos-mcp.json` | The 34 MCP tools with their input schemas and `x-kairos-*` extensions, exported by the same script |
| `observation.v1.schema.json` | JSON Schema 2020-12 of a structured observation |
| `session-summary.v1.schema.json` | JSON Schema 2020-12 of a structured session summary |
| `examples/<schema>/valid/`, `examples/<schema>/invalid/` | Examples that must be accepted / rejected by the matching schema |

The first two are generated: do not edit them by hand. The schemas and examples are
hand-written and versioned: a change that is not backwards compatible gets a new name
(`observation.v2`), never an edit of `v1`.

## Structured observations

A client that wants the server to check an observation puts the document in
`payload.structured` of the event it sends to `POST /v1/observations` (or to the
`observation_add` tool). The document carries its own `schema_version`, which selects the
schema. A mismatch is a 422 `invalid_observation` with the JSON path of the first error
and no content. An event without `payload.structured` is not validated. The limits are
in the schema files (`maxLength`, `maxItems`); `docs/integration.md` lists them.

## Validate a document locally

```bash
python -c "import json,sys,jsonschema;s=json.load(open('docs/contracts/observation.v1.schema.json',encoding='utf-8'));jsonschema.Draft202012Validator(s).validate(json.load(open(sys.argv[1],encoding='utf-8')))" my-observation.json
python -m unittest discover -s scripts/tests -p test_contract_examples.py
```

The second command checks every example with `jsonschema`, a validator that shares no
code with the server; the server's own test runs the same examples through its module.
