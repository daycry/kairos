# retrieval-eval: retrieval quality gate

Measures recall@1/5/10 and MRR of `Retrieval.search` against a synthetic, deterministic dataset.
It is a separate gate (`docker build --target retrieval-eval`), not part of the backend test suite.

- `dataset-v1.jsonl`: one JSON record per line (`memory`, `document` or `question`). All text is
  synthetic; nothing comes from a deployed database. Subsets: `es` (Spanish with inflected forms),
  `en` (control), `typo_id` (misspellings and identifier variants) and `long` (the answer sits after
  character 8,000 of a long document). The file is frozen: its SHA-256 is recorded next to the
  baseline in the initiative `testing/` folder. Never edit it; create `dataset-v2.jsonl` instead.
- `dataset-v1-negatives.jsonl` (T-87, CA-26): 24 questions **without an answer** (`expected: []`, subset `negative`), versioned apart from `dataset-v1.jsonl`, which does not change
  (its SHA-256 is the one in `baseline.json`; `test_metrics` checks it). They are asked against the corpus of `dataset-v1`: 12 Spanish and 12 English, 12 of them `near` the topic of an
  existing memory or document (same area, different fact: attachment sizes, schema approvals, cache replicas, password rules, billing, backup failure alerts) and 12 unrelated to the corpus
  (cooking, sport, travel, science). Provenance: written by hand for this gate, synthetic, with no text from a deployed database; each `near` question names a topic the corpus
  touches but whose answer it does not hold, so a good system answers "nothing relevant". Writing criteria: short keyword or question style like the positives, no copy of a corpus sentence,
  `near` questions may share a word with a record (a lexical hit protects them from abstaining, which is the product's rule and is measured, not hidden). The file is frozen like
  `dataset-v1.jsonl`: a change of the set is a new `dataset-v2-negatives.jsonl` and a new measurement. `check_dataset.py` accepts both files and validates the negatives (at least 20, at
  least 8 per language, at least 8 `near`, unique ids, none shared with `dataset-v1`).
- `thresholds.json`: fused recall@5 >= 0.80, fused MRR >= 0.60 and, for the `es`, `typo_id` and
  `long` subsets a gain of at least 15 recall@5 points over the baseline (decision P-06). All checks are
  mandatory; the gain needs a baseline recorded on the same dataset hash. A retrieval backend that is not
  `ok` (or a `partial` result) fails the gate as `backend_unavailable:<layer>` instead of scoring recall 0.
  The `abstention` block (T-88, CA-27; amended 2026-11-18 after the user's decision "12 de 24 en la CI") holds the goals of the abstention measurement, **per provider**:
  `min_correct_rate` 0.70 and `max_false_rate` 0.05 are the goals of a REAL model (`abstention.models.<model>` holds its calibrated cosine threshold; today it is `{}` because
  `nomic-embed-text` reaches neither goal, see `docs/configuration.md`). `abstention.simulated` has the goals and the threshold of the offline provider used by the CI:
  `threshold` 0.2022, `min_correct_rate` 0.50 (12 of the 24 negatives) and `max_false_rate` 0.05. They are lower on purpose (R-07): the simulated embeddings do not reflect a real
  model's quality (with them 70 % correct abstention needs 6.9 % false abstention, measured), so the simulated goals are a regression guard of the retrieval pipeline, not a quality
  claim. `test_metrics` pins the values (0.50, 0.05 and the presence of `threshold`): lowering or deleting one of them fails a test. A missing goal or threshold fails the gate as
  `threshold_missing:abstention.<key>`; a question whose best cosine could not be measured fails it as `abstention_measurement_errors`.
- `check_dataset.py`: validates schema and minimum counts, prints the SHA-256.
- `fake_embeddings.py`: deterministic provider (`embed` and `embed_many`) hashing words and character trigrams (SHA-256), no network. It measures the
  retrieval pipeline, not model quality; the real Ollama run is a separate, explicit step.
- `run.py`: loads the dataset into the harness PostgreSQL, indexes it by running the queued embed jobs through the real `Worker` (fragments of 1,500 characters with a 200-character overlap, batches, atomic completion; a job that does not finish aborts the run), runs each layer and writes the report.
  It resolves `MEMORY_DSN` like libpq and refuses to run unless it equals `MEMORY_TEST_DSN` and points to
  `127.0.0.1:55432/memory_test` (no `service`, no redirecting query parameters). It validates the dataset on load.
- `test_metrics.py`: hand-computed metric cases and gate/DSN/determinism checks, part of the regular suite.

Run from the repository root: `PYTHONPATH=server python -m memory_platform.tests.retrieval_eval.check_dataset server/memory_platform/tests/retrieval_eval/dataset-v1.jsonl server/memory_platform/tests/retrieval_eval/dataset-v1-negatives.jsonl`
