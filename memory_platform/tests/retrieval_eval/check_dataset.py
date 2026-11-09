"""Validate the synthetic retrieval dataset (schema, minimum counts) and print its SHA-256.

Standard library only: it runs on the host and inside the test container.
Usage: python -m memory_platform.tests.retrieval_eval.check_dataset <dataset.jsonl>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MINIMUMS = {'es': 20, 'en': 20, 'typo_id': 10, 'long': 10}
TOTAL_MINIMUM = 60
LONG_OFFSET = 8000


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


def main(argv):
    if len(argv) != 2:
        raise SystemExit('usage: check_dataset <dataset.jsonl>')
    records, digest = load(argv[1])
    counts, total, errors = validate(records)
    if errors:
        print('INVALID')
        for error in errors:
            print(' -', error)
        raise SystemExit(1)
    print('OK es=%(es)d en=%(en)d typo_id=%(typo_id)d long=%(long)d' % counts + f' total={total}')
    print('sha256 ' + digest)


if __name__ == '__main__':
    main(sys.argv)
