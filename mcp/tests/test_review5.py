"""The corrections of the phase 5 review (attempt 5): a small call does not wait behind the large ones, and the large ones wait a bounded time (CWE-400).

Every call used to go through one FIFO limiter of worker threads, so a legitimate `search` of one element queued behind the validations of 256 KiB bodies
(2 s each) and, with the GIL shared, took longer than before the thread was introduced. Now an input with at most `INLINE_NODES` values is validated on the
loop (about 5 ms at the most for the worst schema of the contract, measured), a larger one goes to the single worker thread, and waits at most
`queue_seconds` for its turn before the service answers that it is unavailable, without reaching `/v1`."""
import asyncio
import threading
import time
import unittest
from unittest import mock

from mcp import types

from kairos_mcp.config import DEFAULT_VALIDATION_THREADS
from kairos_mcp.errors import UNAVAILABLE
from kairos_mcp.tools import INLINE_NODES, Checks, build_server, is_small
from support import CONTRACT, TOOLS
from test_review3 import contract_arrays, with_array
from test_review4 import call, remember_with_tags, with_heartbeat

SMALL_LATENCY_LIMIT = 0.3  # seconds: a small call took 2-70 s behind the large ones; it takes a few ms now
SMALL = {'q': 'x', 'project_ids': ['p'], 'layers': [1]}


def make_server(calls, **options):
    async def executor(name, arguments, authorization):
        calls.append(name)
        return types.CallToolResult(content=[types.TextContent(type='text', text='ok')])
    return build_server(CONTRACT, executor, **options)


async def timed(server, name, arguments):
    started = time.perf_counter()
    result = await call(server, name, arguments)
    return result, time.perf_counter() - started


class SmallCallsDoNotQueueTests(unittest.TestCase):
    def small_latency_with(self, larges, **options):
        calls = []
        server = make_server(calls, **options)

        async def scenario():
            big = [asyncio.create_task(call(server, 'remember', remember_with_tags(86000))) for _ in range(larges)]
            await asyncio.sleep(0.1)  # the large ones are in progress (or waiting for their turn)
            results = []
            for _ in range(3):
                results.append(await timed(server, 'search', {'q': 'x', 'project_ids': ['p']}))
                await asyncio.sleep(0.02)
            await asyncio.gather(*big)
            return results
        return asyncio.run(scenario()), calls

    def test_a_small_call_answers_at_once_with_large_ones_in_progress(self):
        for larges in (2, 6):
            with self.subTest(larges=larges):
                results, calls = self.small_latency_with(larges)
                for result, seconds in results:
                    self.assertFalse(result.isError, result.content[0].text)
                    self.assertLess(seconds, SMALL_LATENCY_LIMIT, 'a small call took %.3f s with %d large ones in progress' % (seconds, larges))
                self.assertEqual(calls.count('search'), 3)

    def test_the_loop_stays_free_with_the_small_calls_in_line(self):
        calls = []
        server = make_server(calls)
        results, worst, _ = asyncio.run(with_heartbeat([call(server, 'remember', remember_with_tags(86000))] + [call(server, 'search', SMALL) for _ in range(20)]))
        self.assertLess(worst, 0.2)


class LargeCallsWaitABoundedTimeTests(unittest.TestCase):
    def test_a_large_call_that_waits_too_long_gets_the_unavailable_error_and_never_reaches_the_api(self):
        """Deterministic: the first large call holds the only turn (its validation blocks on an event) until the others have been answered, so nothing
        depends on how long the runner takes to validate a body. Without the queue deadline the other three would wait for ever and the guard fails."""
        calls = []
        server = make_server(calls, validation_threads=1, queue_seconds=0.3)
        entered, release = threading.Event(), threading.Event()
        real_check = Checks.check

        def blocked_check(self, arguments):
            entered.set()
            release.wait(30)
            return real_check(self, arguments)

        async def scenario():
            first = asyncio.create_task(call(server, 'remember', remember_with_tags(20000)))
            while not entered.is_set():  # the first one is validating, so it owns the turn
                await asyncio.sleep(0.005)
            started = time.perf_counter()
            try:
                waiting = await asyncio.wait_for(asyncio.gather(*[call(server, 'remember', remember_with_tags(20000)) for _ in range(3)]), 10)
            finally:
                release.set()
            return await first, waiting, time.perf_counter() - started
        with mock.patch.object(Checks, 'check', blocked_check):
            first, waiting, seconds = asyncio.run(scenario())
        self.assertTrue(first.isError and first.content[0].text.startswith('Input validation error: '))  # the first one was validated, in its turn
        texts = [result.content[0].text for result in waiting]
        self.assertTrue(all(result.isError for result in waiting))
        self.assertEqual(texts, ['Error executing tool remember: ' + UNAVAILABLE] * 3)
        self.assertEqual(calls, [])
        self.assertLess(seconds, 6.0)  # the waiting ones left after 0.3 s, they did not wait for the validation of the first

    def test_large_calls_inside_the_deadline_are_all_validated_in_turn(self):
        calls = []
        server = make_server(calls, validation_threads=1, queue_seconds=30)
        async def scenario():
            return await asyncio.gather(*[call(server, 'remember', remember_with_tags(20000)) for _ in range(3)])
        results = asyncio.run(scenario())
        self.assertTrue(all(result.isError and result.content[0].text.startswith('Input validation error: ') for result in results))


def fastest(call, runs=3):
    """The best of a few runs: a single sample can carry a pause of the runner or of the GC that is not a cost of the code."""
    best = float('inf')
    for _ in range(runs):
        started = time.perf_counter()
        call()
        best = min(best, time.perf_counter() - started)
    return best


class InlinePathIsBoundedTests(unittest.TestCase):
    def test_the_threshold_separates_small_from_large_inputs_by_values_not_bytes(self):
        self.assertTrue(is_small(SMALL))
        self.assertTrue(is_small({}))
        self.assertTrue(is_small({'q': 'x' * 100000}))  # a long string is one value: validating it is not linear
        self.assertFalse(is_small({'ids': [''] * INLINE_NODES}))
        self.assertFalse(is_small(remember_with_tags(86000)))
        self.assertFalse(is_small({'a': {'b': [[[[1] * (INLINE_NODES + 1)]]]}}))
        self.assertTrue(is_small({'ids': [''] * (INLINE_NODES // 2)}))

    def test_measuring_is_bounded_too(self):
        big = {'ids': [[1, 2, 3]] * 1000000}
        self.assertLess(fastest(lambda: is_small(big)), 0.05)

    def test_the_worst_input_still_in_line_is_validated_in_milliseconds_in_every_array_of_the_contract(self):
        checks = {name: Checks(name, tool['inputSchema']) for name, tool in TOOLS.items()}
        worst = 0.0
        for name, path, invalid in contract_arrays():
            for element in (invalid, 1, ''):
                arguments = with_array(path, [element] * (INLINE_NODES - 10 - len(path)))
                if not is_small(arguments):
                    continue
                worst = max(worst, fastest(lambda: checks[name].check(arguments)))
        self.assertLess(worst, 0.05, 'validating in line took %.1f ms' % (worst * 1000))


class DefaultsTests(unittest.TestCase):
    def test_one_worker_thread_by_default(self):
        self.assertEqual(DEFAULT_VALIDATION_THREADS, 1)
        self.assertEqual(make_server([]).validation_threads, 1)


if __name__ == '__main__':
    unittest.main()
