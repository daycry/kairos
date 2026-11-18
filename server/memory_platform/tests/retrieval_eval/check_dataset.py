"""Validate the synthetic retrieval dataset (schema, minimum counts) and print its SHA-256.

Standard library only: it runs on the host and inside the test container.
Usage: python -m memory_platform.tests.retrieval_eval.check_dataset <dataset.jsonl> [<dataset-v1-negatives.jsonl>]
A file made only of questions is read as the set of questions without an answer (T-87, CA-26) and checked with validate_negatives.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MINIMUMS = {'es': 20, 'en': 20, 'typo_id': 10, 'long': 10}
TOTAL_MINIMUM = 60
LONG_OFFSET = 8000
NEGATIVE_SUBSET = 'negative'
NEGATIVE_MINIMUM = 20
NEGATIVE_LANGUAGE_MINIMUM = 8
NEGATIVE_NEAR_MINIMUM = 8


def load(path):
    raw = Path(path).read_bytes()
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    return records, hashlib.sha256(raw).hexdigest()


def validate(records):
    """Return (counts, errors); errors is empty when the dataset is valid."""
    errors, counts = [], {key: 0 for key in MINIMUMS}
    corpus, questions, seen = {}, [], set()
    for record in records:
        kind, key = record.get('type'), record.get('id')
        if kind not in ('memory', 'document', 'question') or not isinstance(key, str) or key in seen:
            errors.append(f'invalid or duplicate record: {key!r}')
            continue
        seen.add(key)
        if kind == 'question':
            questions.append(record)
        else:
            if not all(isinstance(record.get(field), str) and record[field].strip() for field in ('title', 'content', 'lang')):
                errors.append(f'{key}: title, content and lang are required')
            corpus[key] = record
    for question in questions:
        key = question['id']
        if question.get('subset') not in MINIMUMS:
            errors.append(f'{key}: unknown subset {question.get("subset")!r}')
            continue
        counts[question['subset']] += 1
        if not isinstance(question.get('q'), str) or not question['q'].strip():
            errors.append(f'{key}: empty question')
        expected = question.get('expected')
        if not isinstance(expected, list) or not expected or any(ref not in corpus for ref in expected):
            errors.append(f'{key}: needs at least one valid expected reference')
        elif question['subset'] == 'long' and any(corpus[ref]['type'] != 'document' or len(corpus[ref]['content']) <= LONG_OFFSET for ref in expected):
            errors.append(f'{key}: long questions must point at documents longer than {LONG_OFFSET} characters')
    for subset, minimum in MINIMUMS.items():
        if counts[subset] < minimum:
            errors.append(f'subset {subset}: {counts[subset]} < {minimum}')
    if len(questions) < TOTAL_MINIMUM:
        errors.append(f'total: {len(questions)} < {TOTAL_MINIMUM}')
    return counts, len(questions), errors


def validate_negatives(records, corpus_records=()):
    """Return (counts, total, errors) of the questions without an answer (T-87, CA-26): at least 20, in Spanish and English, at least 8 of them
    near the topic of a memory or document that exists, expected: [], subset negative, and no id shared with corpus_records (dataset-v1)."""
    errors, counts, seen = [], {'es': 0, 'en': 0, 'near': 0}, {r.get('id') for r in corpus_records}
    for record in records:
        key = record.get('id')
        if record.get('type') != 'question' or not isinstance(key, str) or key in seen:
            errors.append(f'invalid, duplicate or corpus record: {key!r}')
            continue
        seen.add(key)
        if record.get('subset') != NEGATIVE_SUBSET:
            errors.append(f'{key}: subset must be {NEGATIVE_SUBSET!r}')
        if record.get('expected') != []:
            errors.append(f'{key}: a question without an answer needs expected: []')
        if not isinstance(record.get('q'), str) or not record['q'].strip():
            errors.append(f'{key}: empty question')
        if record.get('lang') not in ('es', 'en'):
            errors.append(f'{key}: lang must be es or en')
        else:
            counts[record['lang']] += 1
        if not isinstance(record.get('near'), bool):
            errors.append(f'{key}: near must be true or false')
        elif record['near']:
            counts['near'] += 1
    if len(records) < NEGATIVE_MINIMUM:
        errors.append(f'total: {len(records)} < {NEGATIVE_MINIMUM}')
    for lang in ('es', 'en'):
        if counts[lang] < NEGATIVE_LANGUAGE_MINIMUM:
            errors.append(f'language {lang}: {counts[lang]} < {NEGATIVE_LANGUAGE_MINIMUM}')
    if counts['near'] < NEGATIVE_NEAR_MINIMUM:
        errors.append(f'near the topic of an existing record: {counts["near"]} < {NEGATIVE_NEAR_MINIMUM}')
    return counts, len(records), errors


def is_negative_set(records):
    return bool(records) and all(record.get('type') == 'question' for record in records)


def main(argv):
    if len(argv) < 2:
        raise SystemExit('usage: check_dataset <dataset.jsonl> [<dataset-v1-negatives.jsonl>]')
    invalid = False
    loaded = [(path, *load(path)) for path in argv[1:]]
    # The ids of the questions without an answer are checked against the corpus whatever the order of the arguments (review phase 14, B4).
    corpus = [record for _, records, _ in loaded if not is_negative_set(records) for record in records]
    for path, records, digest in loaded:
        if is_negative_set(records):
            counts, total, errors = validate_negatives(records, corpus)
            summary = 'OK negatives es=%(es)d en=%(en)d near=%(near)d' % counts + f' total={total}'
        else:
            counts, total, errors = validate(records)
            summary = 'OK es=%(es)d en=%(en)d typo_id=%(typo_id)d long=%(long)d' % counts + f' total={total}'
        if errors:
            invalid = True
            print(f'INVALID {path}')
            for error in errors:
                print(' -', error)
            continue
        print(summary)
        print('sha256 ' + digest)
    if invalid:
        raise SystemExit(1)


if __name__ == '__main__':
    main(sys.argv)
