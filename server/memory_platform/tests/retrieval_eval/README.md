# retrieval-eval: retrieval quality gate

Measures recall@1/5/10 and MRR of `Retrieval.search` against a synthetic, deterministic dataset.
It is a separate gate (`docker build --target retrieval-eval`), not part of the backend test suite.

- `dataset-v1.jsonl`: one JSON record per line (`memory`, `document` or `question`). All text is
  synthetic; nothing comes from a deployed database. Subsets: `es` (Spanish with inflected forms),
  `en` (control), `typo_id` (misspellings and identifier variants) and `long` (the answer sits after
  character 8,000 of a long document). The file is frozen: its SHA-256 is recorded next to the
  baseline in the initiative `testing/` folder. Never edit it; create `dataset-v2.jsonl` instead.
- `thresholds.json`: fused recall@5 >= 0.80, fused MRR >= 0.60 and, for the `es`, `typo_id` and
  `long` subsets a gain of at least 15 recall@5 points over the baseline (decision P-06). All checks are
  mandatory; the gain needs a baseline recorded on the same dataset hash. A retrieval backend that is not
  `ok` (or a `partial` result) fails the gate as `backend_unavailable:<layer>` instead of scoring recall 0.
- `check_dataset.py`: validates schema and minimum counts, prints the SHA-256.
- `fake_embeddings.py`: deterministic provider (`embed` and `embed_many`) hashing words and character trigrams (SHA-256), no network. It measures the
  retrieval pipeline, not model quality; the real Ollama run is a separate, explicit step.
- `run.py`: loads the dataset into the harness PostgreSQL, indexes it by running the queued embed jobs through the real `Worker` (fragments of 1,500 characters with a 200-character overlap, batches, atomic completion; a job that does not finish aborts the run), runs each layer and writes the report.
  It resolves `MEMORY_DSN` like libpq and refuses to run unless it equals `MEMORY_TEST_DSN` and points to
  `127.0.0.1:55432/memory_test` (no `service`, no redirecting query parameters). It validates the dataset on load.
- `test_metrics.py`: hand-computed metric cases and gate/DSN/determinism checks, part of the regular suite.

Run: `python -m memory_platform.tests.retrieval_eval.check_dataset memory_platform/tests/retrieval_eval/dataset-v1.jsonl`
