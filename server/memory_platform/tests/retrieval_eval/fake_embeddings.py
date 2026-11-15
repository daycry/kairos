"""Deterministic offline embedding provider for the retrieval-eval gate.

Same interface as ``memory_platform.providers.Embeddings.embed``. Each informative word and each character
trigram of it (padded with boundary marks) is hashed with SHA-256 into a signed bucket, so equal or
similar spelling produces similar vectors: no network, no model, no randomness (nothing depends on
PYTHONHASHSEED). It measures the retrieval pipeline (ranking, fusion,
truncation), not the quality of a real embedding model.
"""
from __future__ import annotations

import hashlib
import re

from memory_platform.providers import ProviderError

STOPWORDS = frozenset('''a al an and are as at be by de del el en es for in is la las lo los of on or para por que se
the to un una y with con'''.split())
MODEL_DIMENSIONS = {'fake-2d': 2}
DEFAULT_DIMENSIONS = 768
TEXT_LIMIT = 8000  # same cut as the real provider


def dimensions_for(model):
    return MODEL_DIMENSIONS.get(model, DEFAULT_DIMENSIONS)


def _bucket(token, dimensions):
    digest = hashlib.sha256(token.encode('utf-8')).digest()
    return int.from_bytes(digest[:4], 'big') % dimensions, 1.0 if digest[4] & 1 else -1.0


def ngrams(token, size=3):
    padded = '<' + token + '>'
    return [padded[i:i + size] for i in range(max(len(padded) - size + 1, 1))]


def vectorize(text, dimensions=DEFAULT_DIMENSIONS):
    tokens = [t for t in re.findall(r'\w+', text.lower()) if t not in STOPWORDS and len(t) > 1]
    vector = [0.0] * dimensions
    for token in tokens or [text.lower()]:
        for feature in ['w:' + token] + ['n:' + gram for gram in ngrams(token)]:
            index, sign = _bucket(feature, dimensions)
            vector[index] += sign
    if not any(vector):  # cancelling buckets (tiny dimensions): fall back to a fixed unit direction
        vector[0] = 1.0
    return vector


class FakeEmbeddings:
    def __init__(self, settings):
        self.settings = settings

    async def embed(self, text, query=False):
        if not isinstance(text, str) or not text.strip():
            raise ProviderError('embedding_empty_input')
        model = self.settings.embedding_model
        return {'embedding': vectorize(text[:TEXT_LIMIT], dimensions_for(model)), 'model': model, 'verified': True}

    async def embed_many(self, texts, query=False):
        """Same interface as ``Embeddings.embed_many`` (the fragments of one text): one deterministic vector per input."""
        if not isinstance(texts, (list, tuple)) or not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
            raise ProviderError('embedding_empty_input')
        model = self.settings.embedding_model
        return {'embeddings': [vectorize(text[:TEXT_LIMIT], dimensions_for(model)) for text in texts], 'model': model, 'verified': True}
