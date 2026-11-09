"""Pure chunker: full coverage without gaps, configured overlap, hard cap and short text (CA-24, pure part)."""
import random
import unittest

from memory_platform.chunking import chunk_text, embedding_text
from memory_platform.config import chunk_settings


def prose(length, seed=1):
    generator = random.Random(seed)
    words = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota', 'kappa', 'lambda', 'sigma']
    paragraphs, total = [], 0
    while total < length:
        text = ' '.join(generator.choice(words) for _ in range(generator.randint(20, 120))) + '.'
        paragraphs.append(text)
        total += len(text) + 2
    return '\n\n'.join(paragraphs)[:length]


class ChunkingTests(unittest.TestCase):
    def assert_covers(self, text, chunks, overlap):
        self.assertEqual([c.ordinal for c in chunks], list(range(len(chunks))))
        self.assertEqual(chunks[0].char_start, 0)
        self.assertEqual(chunks[-1].char_end, len(text))
        for previous, current in zip(chunks, chunks[1:]):
            self.assertLess(current.char_start, previous.char_end, 'a gap would leave text that no fragment embeds')
            self.assertGreaterEqual(previous.char_end - current.char_start, overlap)
            self.assertGreater(current.char_start, previous.char_start)
        for chunk in chunks:
            self.assertEqual(chunk.text(text), text[chunk.char_start:chunk.char_end])

    def test_fifty_thousand_characters_are_covered_without_gaps_and_with_the_configured_overlap(self):
        text = prose(50000)
        self.assertEqual(len(text), 50000)
        chunks = chunk_text(text)
        self.assert_covers(text, chunks, 200)
        self.assertTrue(all(c.char_end - c.char_start <= 1500 for c in chunks))
        self.assertFalse(chunks.truncated)
        self.assertEqual(chunks.covered_chars, 50000)
        self.assertGreater(len(chunks), 30)

    def test_text_without_any_separator_is_cut_hard_and_still_covered(self):
        text = 'x' * 9000
        chunks = chunk_text(text, size=1000, overlap=100)
        self.assert_covers(text, chunks, 100)

    def test_two_hundred_thousand_characters_produce_at_most_two_hundred_fragments(self):
        text = prose(200000, seed=2)
        chunks = chunk_text(text)
        self.assertLessEqual(len(chunks), 200)
        self.assert_covers(text, chunks, 200)
        self.assertFalse(chunks.truncated)

    def test_the_cap_is_explicit_never_silent(self):
        text = prose(400000, seed=3)
        chunks = chunk_text(text, maximum=200)
        self.assertEqual(len(chunks), 200)
        self.assertTrue(chunks.truncated)
        self.assertLess(chunks.covered_chars, len(text))
        self.assertEqual(chunks[-1].char_end, chunks.covered_chars)

    def test_short_text_is_a_single_fragment(self):
        for text in ('Single sentence.', 'x' * 1500):
            chunks = chunk_text(text)
            self.assertEqual([(c.ordinal, c.char_start, c.char_end) for c in chunks], [(0, 0, len(text))])
            self.assertFalse(chunks.truncated)

    def test_a_run_of_blanks_never_becomes_a_fragment_and_the_coverage_stays_whole(self):
        """Gap 3: no fragment may be blank (a blank input cannot be embedded)."""
        cases = {'blank run longer than a fragment': 'T\nintro\n' + '\n' * 4000 + 'fin',
                 'trailing blanks': 'T\nintro ' + 'x' * 100 + '\n' * 5000,
                 'leading blanks': '\n' + ' ' * 5000 + 'visible text after the blanks',
                 'two runs': 'a' * 900 + ' ' * 3000 + 'b' * 900 + '\n' * 3000 + 'c' * 900}
        for name, text in cases.items():
            chunks = chunk_text(text, size=1500, overlap=200)
            self.assertTrue(chunks, name)
            self.assertTrue(all(chunk.text(text).strip() for chunk in chunks), name)
            self.assertEqual([c.ordinal for c in chunks], list(range(len(chunks))), name)
            self.assertEqual((chunks[0].char_start, chunks[-1].char_end), (0, len(text)), name)
            for previous, current in zip(chunks, chunks[1:]):
                self.assertGreater(current.char_start, previous.char_start, name)
                self.assertLessEqual(current.char_start, previous.char_end, name)  # no gap
            self.assertFalse(chunks.truncated, name)
        text = cases['blank run longer than a fragment']
        self.assertEqual([chunk.text(text).strip()[:5] for chunk in chunk_text(text)][-1], 'fin')

    def test_empty_text_has_no_fragments(self):
        self.assertEqual(list(chunk_text('')), [])
        self.assertEqual(list(chunk_text('  \n ')), [])

    def test_breaks_prefer_headings_and_paragraphs_over_the_middle_of_a_word(self):
        body = '\n\n'.join(('# Heading %d\n\n' % n) + ('palabra ' * 150).strip() for n in range(12))
        chunks = chunk_text(body, size=1500, overlap=200)
        for chunk in chunks[:-1]:
            boundary = body[chunk.char_end - 1:chunk.char_end + 1]
            self.assertTrue(boundary[0].isspace() or boundary[1].isspace() or boundary[0] in '.\n', repr(boundary))

    def test_embedding_text_is_title_newline_content(self):
        self.assertEqual(embedding_text('Title', 'Body'), 'Title\nBody')
        self.assertEqual(embedding_text(None, 'Body'), '\nBody')

    def test_parameters_are_validated(self):
        self.assertEqual(chunk_settings({}), (1500, 200, 200))
        self.assertEqual(chunk_settings({'MEMORY_CHUNK_CHARS': '1000', 'MEMORY_CHUNK_OVERLAP': '100', 'MEMORY_CHUNK_MAX': '50'}), (1000, 100, 50))
        for environ in ({'MEMORY_CHUNK_CHARS': '100'}, {'MEMORY_CHUNK_CHARS': '9000'}, {'MEMORY_CHUNK_OVERLAP': '800'},
                        {'MEMORY_CHUNK_MAX': '0'}, {'MEMORY_CHUNK_MAX': '9999'}, {'MEMORY_CHUNK_CHARS': 'x'}):
            with self.assertRaises(ValueError, msg=environ):
                chunk_settings(environ)
        with self.assertRaises(ValueError):
            chunk_text('text', size=100, overlap=60)


if __name__ == '__main__':
    unittest.main()
