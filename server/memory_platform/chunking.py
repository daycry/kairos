"""Pure text chunker for embeddings. No I/O, no database, no provider.

A resource is embedded as `embedding_text(title, content)`; each fragment is the interval `[char_start, char_end)` of that
string. Fragments follow paragraph and heading boundaries when one exists in the second half of the window, otherwise a
line, a sentence, a word and finally a hard cut. Consecutive fragments overlap by at least `overlap` characters, so the
intervals cover the text without gaps and none is blank (a run of blanks joins the fragment before it); the cap (`maximum`) is explicit: past it `truncated` is true and `covered_chars`
says where the coverage stops. Nothing is cut silently.
"""
from __future__ import annotations

from typing import NamedTuple

from .config import chunk_settings


class Chunk(NamedTuple):
    ordinal: int
    char_start: int
    char_end: int

    def text(self, full: str) -> str:
        return full[self.char_start:self.char_end]


class Chunks(list):
    """The fragments of one text plus what they leave out: `truncated` is true when the cap stopped the coverage."""
    truncated = False
    covered_chars = 0


def embedding_text(title, content) -> str:
    """The exact string that is embedded (and that fragment offsets refer to)."""
    return str(title if title is not None else '') + '\n' + str(content if content is not None else '')


def _break(text, start, hard_end, size):
    """End of the fragment that starts at `start`: the best boundary in the second half of the window."""
    low = start + size // 2
    window_end = hard_end
    heading = text.rfind('\n#', low, window_end)
    if heading != -1:
        return heading + 1  # the heading opens the next fragment
    paragraph = text.rfind('\n\n', low, window_end)
    if paragraph != -1:
        return paragraph + 2
    line = text.rfind('\n', low, window_end)
    if line != -1:
        return line + 1
    sentence = max(text.rfind(mark, low, window_end) for mark in ('. ', '? ', '! '))
    if sentence != -1:
        return sentence + 2
    word = max(text.rfind(' ', low, window_end), text.rfind('\t', low, window_end))
    if word != -1:
        return word + 1
    return hard_end


def _next_start(text, start, end, overlap):
    """Start of the next fragment: `overlap` characters back from `end`, moved earlier to a word start (more overlap, never less)."""
    candidate = end - overlap
    floor = max(start + 1, candidate - 80)
    for index in range(candidate - 1, floor - 1, -1):
        if text[index].isspace():
            return index + 1
    return candidate


def chunk_text(text, size=None, overlap=None, maximum=None) -> Chunks:
    default_size, default_overlap, default_maximum = chunk_settings()
    size = default_size if size is None else size
    overlap = default_overlap if overlap is None else overlap
    maximum = default_maximum if maximum is None else maximum
    if size < 1 or overlap < 0 or overlap * 2 >= size or maximum < 1:
        raise ValueError('chunk size must be positive, overlap below half of it and maximum at least 1')
    result = Chunks()
    if not isinstance(text, str) or not text.strip():
        return result
    length, start = len(text), 0
    while True:
        end = length if length - start <= size else _break(text, start, start + size, size)
        if not text[start:end].strip():
            # A run of blanks the size of a fragment: never a fragment of its own (it could not be embedded). The previous fragment
            # absorbs it up to the next visible character, where the next fragment starts; with no previous one this fragment
            # starts at 0 and ends after the first visible text (the embedder trims it).
            visible = start
            while visible < length and text[visible].isspace():
                visible += 1
            if visible >= length:
                last = result[-1]
                result[-1] = Chunk(last.ordinal, last.char_start, length)
                result.covered_chars = length
                break
            if result:
                last = result[-1]
                result[-1] = Chunk(last.ordinal, last.char_start, visible)
                start = visible
            end = length if length - visible <= size else _break(text, visible, visible + size, size)
        result.append(Chunk(len(result), start, end))
        result.covered_chars = end
        if end >= length:
            break
        if len(result) >= maximum:
            result.truncated = True
            break
        start = _next_start(text, start, end, overlap)
    return result
