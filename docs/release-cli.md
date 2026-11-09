# CLI release preparation and public verification

The current source version is 0.2.0. A local package, a successful native-client test, and a public npm distribution are separate deliverables. This procedure never treats one as proof of another.

## Prepare without publishing

From `packages/kairos-cli`:

```powershell
npm test
node tests/npx-smoke.mjs
npm pack --ignore-scripts --offline --pack-destination ./artifacts
node tests/artifact-report.mjs ./artifacts/daycry-kairos-0.2.0.tgz
npm run release:check
```

`release:check` is also the `prepublishOnly` gate. It executes the complete imported test suite, performs real fresh-cache offline npx installation in an owned synthetic project, packages source without lifecycle scripts and verifies exact tarball contents against source bytes. It does **not** call `npm publish`, alter working project/client configurations, create a real key or contact a provider. A sandbox process-spawn denial is a failed/unavailable gate, not a passed test; run the gate in an environment that permits Node child processes. `Dockerfile.test` provides pinned Linux Node checks.

The artifact verifier derives the version and managed runtime file allowlist from current source. It validates tar headers, rejects links, duplicates, traversal and unexpected files, checks source equality and emits SHA-256 and SHA-512 integrity. It reports tests and registry availability as unverified because that command does not run them. Keep historical tarballs and their evidence immutable.

## Confirm account and scope separately

An authorized publisher must check `npm whoami --registry=https://registry.npmjs.org/` and their right to publish under `@daycry`. For an existing package, inspect `npm owner ls @daycry/kairos --registry=https://registry.npmjs.org/`; for a new scope/package, confirm organization membership and publication rights in npm. A package-name search or a logged-in account does not establish scope ownership.

Do not paste tokens, `.npmrc` contents, OTPs or account session data into reports. Prefer an interactive account flow or trusted publishing. Registry/authentication checks have not been established by this repository's local package tests.

After the reviewer has approved the exact artifact, license/provenance and ownership evidence, an authorized operator can publish that reviewed tarball with public scoped access. This document is not evidence that publication occurred. Do not overwrite an existing version; use a new version if any bytes change.

## Verify public distribution

After an authorized publication, verify the exact version anonymously and compare registry tarball bytes with the reviewed local artifact:

```powershell
node tests/registry-check.mjs 0.2.0 ./artifacts/daycry-kairos-0.2.0.tgz
```

This check reads no npm configuration or tokens. It uses only the official public HTTPS registry, rejects redirects, bounds responses and deadlines, checks package identity and SHA-512 integrity and optionally verifies byte-for-byte equality. Exit 2 means the exact version was not found; exit 1 means verification failed/unavailable. Neither result means the name is owned or available to this account.

Finally install the published **exact** version using a new npm cache and a synthetic project/key, with capture/context/code analysis off initially. Check version, installer preview, stable runtime, all three client configurations, idempotence and local doctor as in `tests/npx-smoke.mjs`. Record the exact registry integrity and test result before replacing local-tarball instructions with a public npx command. Do not use a moving `latest` tag as acceptance evidence.
