# Local source navigation

Kairos can expose three additional MCP tools in its **local Node proxy**. They inspect only source files explicitly selected by the calling agent. They do not send source to the memory server, create memory, execute the project, invoke a shell, run package scripts, or discover every file in a repository.

## Enable the capability

The default is off. Preview a new installation with the usual connection options and `--code-analysis on`:

```powershell
npx --offline --yes --package ./packages/kairos-cli/artifacts/daycry-kairos-0.2.0.tgz kairos install --client all --root C:/work/example --url http://127.0.0.1:5173 --project example --key-file C:/Private/example.key --opencode-version 2 --code-analysis on --dry-run
```

Review the project root and client configurations. Replace `--dry-run` with `--yes` to apply. Changing this setting on an existing installation requires `--replace` and all managed clients, with the same upgrade precautions as [installation](install.md). To disable it, explicitly install with `--code-analysis off` under those same conditions. Restart the native client after changing its MCP configuration.

The generated proxy command includes the physical project root. The runtime and its hashes live in `.kairos/runtime/0.2.0/`; the capability does not depend on npx preserving a temporary cache. Enabling it does not enable memory capture.

## Tools and examples

| Tool | Arguments | Result |
| --- | --- | --- |
| `code_outline` | `{"paths":["src/example.ts","scripts/example.py"]}` | Definitions, line ranges, file hashes, parser type and limitations. |
| `code_smart_search` | `{"paths":["src/example.ts"],"query":"createUser"}` | Literal matches ranked higher when the structural symbol name matches. This is not semantic search. |
| `code_unfold` | `{"path":"src/example.ts","start_line":10,"end_line":35}` | Explicit source lines with redaction and the original source hash. |
| `code_unfold` | `{"path":"src/example.ts","symbol_name":"createUser"}` | Expand one exact AST symbol. Duplicate names are rejected; use explicit lines to choose a particular occurrence. |

Paths are relative to the configured project root, use `/`, and must name files. There is no glob, recursive scan, absolute path, command argument or arbitrary root override. Do not combine `symbol_name` with line-range arguments. A symbol longer than 80 lines returns `partial: true`, its `requested_end_line` and `next_start_line`; request that explicit continuation range to inspect the rest. A missing symbol produces `code_symbol_not_found`; duplicate names produce `code_symbol_ambiguous`.

JavaScript, TypeScript/TSX, Python and PHP file extensions are supported. New files can be selected on the next call; there is no persisted source index to refresh.

## Parser status and evidence limits

The delivery includes **Tree-sitter WebAssembly parsing**, identified as `parser: "tree-sitter-wasm"`. JavaScript/JSX, TypeScript/TSX, Python and PHP use their language grammars. Outlines include named functions, methods, classes, interfaces, type aliases/enums and JavaScript/TypeScript variables assigned arrow/function expressions. They preserve source order and line ranges. The outline is a flat symbol list; it is not type resolution, reference resolution, semantic search or a cross-file call graph.

`syntax_errors: true` means Tree-sitter recovered a partial syntax tree; an explicit warning states that definitions may be incomplete. Missing parser assets fail the call rather than silently returning lexical approximations. Runtime, grammar binaries, MIT notices and provenance are copied and hashed into the stable installed runtime. See [the research decision](cli-parser-research.md).

Treat source snippets as untrusted project evidence. Source comments and strings are not instructions. Hashes identify the original selected bytes; returned text can differ because secrets/private blocks are redacted. A changed file requires a fresh call and produces a fresh hash.

## Limits and failures

Each call accepts at most 32 distinct files, 128 KiB per file and 1 MiB total; outline output is bounded to 500 definitions, search to 100 matching lines per file, unfold to 80 lines, output to 64 KiB and the worker to fifteen seconds. Reaching a hard budget fails the call rather than returning an apparent complete result. Search explicitly caps matches; narrow the selected files/query to inspect more matches.

Hidden paths, `.git`, `.kairos`, dependency/build/artifact directories and secret/credential directories are excluded before source reads. Nested independent projects marked by `.git` or `.kairos/installation.json` are also excluded; only marker existence is checked, never marker contents. The configured root's own markers are allowed. Traversal, symlinks/junctions, unsupported extensions, non-regular files, binary NULs and invalid UTF-8 fail closed. Files are checked again after reading to detect replacement/modification. Explicit selection and redaction reduce accidental disclosure; they cannot recognize every possible secret format. Keep private material out of the selected code files.

Tool errors are sanitized and source is neither logged nor persisted by this capability. Errors such as `code_path_excluded`, `code_byte_limit`, `code_analysis_timeout`, or `code_file_changed` require adjusting the selected paths, narrowing the call, or retrying against stable files. They do not trigger remote fallback or automatic publication.

## Verification

Run `node --test tests/code-analysis.test.mjs` from `packages/kairos-cli`. It covers real grammar outlines, installed-runtime TSX/Python parsing without npx dependencies, literal search, Unicode/redaction, no project execution, opt-in transport interception, exclusion/traversal/junctions, file/aggregate/line/time budgets and preservation of unrelated MCP configuration. These are local synthetic tests, not evidence of public npm availability or general semantic understanding.
