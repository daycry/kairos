# Web verification

The final application snapshot passed **65/65 Node tests**, TypeScript checking,
and the Vite production build. Versions, exact source hashes and built-file hashes
are recorded in [web-build.json](web-build.json). Tests executed in the existing
isolated `kairos-web-test:native` image with current sources copied to a temporary
directory and the image's locked dependencies. No host dependency installation
or production service was required.

The maintained real-browser suite passed **20/20 flows** using Chromium
156.0.8078.79, fresh PostgreSQL and the actual FastAPI application. See
[browser/results.json](browser/results.json) and
[browser/evidence-manifest.json](browser/evidence-manifest.json). Coverage includes:

- Authentication, authorization, reload, read-only access and capture disabled.
- Notes, Unicode/tags, correction authority, withdrawal, sessions and provenance.
- Search/context, graph details, pagination, manual retry and live activity.
- Private work state, shared manual tasks, attribution and persistence.
- Corpus selection/priming, exact citations, follow-up continuity, refreshed source
  generation and explicit re-priming.
- Collapsed corpus creation controls and focus/scroll to a completed answer.
- Rules, observations, project categories and metadata-only activity.

Browser generation uses a **fixture-only synthetic provider response**. These
checks exercise the real domain, API, database and UI, not external model quality
or latency. Actual configured-provider acceptance has separate corpus evidence.
The fixture patch is limited to the owned test server and is stopped at teardown.

The latest generated public manuals passed **24/24 Chromium checks**: twelve HTML
pages at widths 1280 and 375, including navigation, a unique heading, mobile
contents disclosure and no horizontal page overflow. No browser errors or external
requests occurred. The final documentation-only update was checked separately,
without repeating unchanged application flows. Use
[browser/handbook-latest-results.json](browser/handbook-latest-results.json) and
[browser/handbook-source.json](browser/handbook-source.json) for the exact latest
manual hashes. Earlier handbook artifacts remain intact with the UI snapshot.

## Reproduction

The normal isolated web gate, from the product root, is:

```sh
docker build -f web/Dockerfile.test -t kairos-web-test:native .
```

When the test image already exists, [run-web-gate.sh](run-web-gate.sh) copies
mounted current web sources to `/tmp/current-web`, runs `npm test` and
`npm run build`, and exports the compiled files plus
[write-web-receipt.mjs](write-web-receipt.mjs)'s source/build receipt. Mount the
current web directory read-only at `/candidate`, this testing directory read-only
at `/evidence-root`, and an owned output directory at `/evidence`.

[run-browser-gate.py](run-browser-gate.py) runs the maintained browser suite and
manual checks in the existing `kairos-e2e:native` image. It requires read-only
mounts for current backend sources at `/candidate/memory_platform`, compiled web
with its build receipt at `/candidate-dist`, and freshly generated manuals at
`/candidate-handbook`. Mount an owned empty output directory at
`/candidate-evidence`, set `PYTHONPATH=/candidate`, and invoke Python on the runner.
Use `--network none`; HTTP and PostgreSQL are owned temporary loopback fixtures.
The runner caps exported evidence at 64 MiB and each file at 16 MiB, and copies
file contents without changing OneDrive directory permissions or attributes.

For a documentation-only update, [run-handbook-gate.py](run-handbook-gate.py)
rechecks the current generated manuals and writes separate `handbook-latest-*`
artifacts and their source manifest. It does not overwrite the prior UI receipt.

The additional feature flows live in
`memory_platform/tests/e2e_portal.py`; their synthetic provider is in
`memory_platform/tests/e2e_fixture.py`. Set `KAIROS_FOCUSED_BROWSER=1` only when
deliberately rerunning those three feature flows; the final 20-flow receipt used
the complete suite.

## Visual evidence

[A06-corpus-visible-answer.jpg](browser/A06-corpus-visible-answer.jpg) is an
unedited frame extracted from the final feature trace, immediately before the
source-refresh action. It shows the collapsed builder and both cited answers in
view. Its exact trace frame and hash are recorded beside it in
[A06-corpus-visible-answer.json](browser/A06-corpus-visible-answer.json).

Screenshots and the two bounded Playwright traces contain synthetic fixture data
only. They do not establish a deployment, an npm publication, or acceptance by
native desktop clients.
