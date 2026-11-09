# Local parser decision

## Requirement

Provide bounded project-local source navigation without running project code or uploading a repository. The installed runtime must work independently of transient npx dependencies. A grammar-based AST is desirable, but cannot be claimed from lexical pattern matching.

| Candidate | Evidence | Decision |
| --- | --- | --- |
| Native Tree-sitter bindings | Platform-specific binaries/build chain complicate a copied standalone runtime. | Not adopted. |
| Web Tree-sitter plus selected WASM grammars | Official binding documentation supports standalone JS/WASM, `Parser.init`, `Language.load` and syntax trees. Microsoft publishes selected JS/TS/Python/PHP grammars in an MIT package. | Adopted runtime 0.25.10 and grammar distribution 0.3.1, acquired anonymously with registry SHA-512 checks. |
| Small in-repository lexical scanner | No dependencies, but incomplete grammar recognition and ambiguous syntax. | Rejected once verified WASM acquisition succeeded; no silent lexical fallback. |

Primary sources inspected on 2026-11-06:

- [Tree-sitter v0.25.10 web binding documentation](https://github.com/tree-sitter/tree-sitter/blob/v0.25.10/lib/binding_web/README.md).
- [Microsoft WASM package manifest](https://github.com/microsoft/vscode-tree-sitter-wasm/blob/main/package.json), observed version 0.3.1, MIT, selected grammar build dependencies.
- [Microsoft build repository](https://github.com/microsoft/vscode-tree-sitter-wasm).

Initial npm CLI/urllib acquisition was blocked and Docker acquisition was denied at the buildx lock. Anonymous direct Node HTTPS registry fetch subsequently succeeded. No npm configuration or credentials were inspected, and no scripts from downloaded dependencies ran. Only the official runtime JS/WASM and five grammar WASM binaries were extracted by explicit member allowlist, together with applicable MIT notices. `lib/vendor/tree-sitter/provenance.json` records registry distributions, SHA-512 integrity and per-file SHA-256. Microsoft uses grammar version ranges; precise grammar source revisions are not claimed from those binaries.

The stable installed runtime includes every parser/grammar/license/provenance file in `RUNTIME_FILES`; the installer hashes and validates their bytes. Tests exercise real parsing on all supported languages and TSX/Python from an installed runtime without npx `node_modules`. Parsing is isolated in a worker with a hard deadline and memory cap. The Linux Docker gate remains a separate check; a sandbox refusal to build is not a successful Linux test. Never replace accepted historical artifacts in place.
