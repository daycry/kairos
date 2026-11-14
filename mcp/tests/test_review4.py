"""The corrections of the phase 5 review (attempt 4): validating the input of a call does not block the event loop (CWE-400).

An array whose elements are valid but for one outer failure (`maxItems`) costs the same as a valid one of its size, 15-25 microseconds per element:
86 000 elements are 1.5-2.5 s of pure Python. The cost is linear and cannot be cut, so the validation runs in a worker thread (jsonschema is pure Python and
releases the GIL every switch interval) with a small, configurable limit of concurrent validations, and the event loop keeps answering."""
import asyncio
import copy
import time
import unittest

from mcp import types

from kairos_mcp.config import DEFAULT_VALIDATION_THREADS, from_env
from kairos_mcp.tools import build_server
from support import CONTRACT, TOOLS
from test_tools_t41 import EVENT

LOOP_DELAY_LIMIT = 0.2  # seconds: generous; the loop used to stall 1.5-2.5 s, and answers in a few tens of ms now
HEARTBEAT = 0.005


def remember_with_tags(count):
    event = copy.deepcopy(EVENT)
    event['payload'] = dict(event.get('payload', {}))
    event['payload']['tags'] = [''] * count  # 258 KB for 86 000; the only error is `maxItems`
    return {'event': event}


async def call(server, name, arguments):
    request = types.CallToolRequest(method='tools/call', params=types.CallToolRequestParams(name=name, arguments=arguments))
    return (await server.request_handlers[types.CallToolRequest](request)).root


async def with_heartbeat(coroutines):
    """Runs the calls while a task measures how late the event loop wakes it up; returns `(results, worst delay, seconds)`."""
    worst, running = 0.0, True

    async def beat():
        nonlocal worst
        while running:
            before = time.perf_counter()
            await asyncio.sleep(HEARTBEAT)
            worst = max(worst, time.perf_counter() - before - HEARTBEAT)

    task = asyncio.create_task(beat())
    await asyncio.sleep(0.05)
    started = time.perf_counter()
    results = await asyncio.gather(*coroutines)
    elapsed = time.perf_counter() - started
    running = False
    await task
    return results, worst, elapsed


class EventLoopStaysFreeTests(unittest.TestCase):
    def setUp(self):
        async def executor(name, arguments, authorization):
            return types.CallToolResult(content=[types.TextContent(type='text', text='ok')])
        self.executor = executor

    def test_a_huge_invalid_call_does_not_stall_the_event_loop(self):
        server = build_server(CONTRACT, self.executor)
        results, worst, elapsed = asyncio.run(with_heartbeat([call(server, 'remember', remember_with_tags(86000))]))
        self.assertTrue(results[0].isError)
        self.assertTrue(results[0].content[0].text.startswith('Input validation error: '))
        self.assertGreater(elapsed, 0.2)  # the work is real (it is not skipped): only it does not run on the loop
        self.assertLess(worst, LOOP_DELAY_LIMIT, 'the event loop was late %.3f s' % worst)

    def test_a_huge_get_observations_call_does_not_stall_the_event_loop_either(self):
        server = build_server(CONTRACT, self.executor)
        arguments = {'projectId': 'p', 'ids': [''] * 87000}  # `maxItems` 100: refused, but only after reading every element
        results, worst, _ = asyncio.run(with_heartbeat([call(server, 'get_observations', arguments)]))
        self.assertTrue(results[0].isError)
        self.assertLess(worst, LOOP_DELAY_LIMIT, 'the event loop was late %.3f s' % worst)

    def test_concurrent_validations_are_bounded_by_the_configured_limit(self):
        server = build_server(CONTRACT, self.executor, validation_threads=1)
        results, worst, _ = asyncio.run(with_heartbeat([call(server, 'remember', remember_with_tags(20000)) for _ in range(4)]))
        self.assertTrue(all(result.isError for result in results))
        self.assertLess(worst, LOOP_DELAY_LIMIT)
        self.assertEqual(server.validation_threads, 1)

    def test_a_normal_call_still_works_and_keeps_the_text(self):
        server = build_server(CONTRACT, self.executor)
        refused = asyncio.run(call(server, 'search', {'q': 'x', 'project_ids': ['p'], 'layers': [1]}))
        self.assertTrue(refused.isError)
        self.assertTrue(refused.content[0].text.startswith('Input validation error: '))
        accepted = asyncio.run(call(server, 'projects', {}))
        self.assertFalse(accepted.isError)


class ConfigurationTests(unittest.TestCase):
    def test_the_limit_has_a_default_and_is_validated(self):
        base = {'KAIROS_API_URL': 'http://x'}
        self.assertEqual(from_env(base).validation_threads, DEFAULT_VALIDATION_THREADS)
        self.assertEqual(from_env({**base, 'KAIROS_VALIDATION_THREADS': '3'}).validation_threads, 3)
        for bad in ('0', '-1', 'x', '1.5', '65'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                from_env({**base, 'KAIROS_VALIDATION_THREADS': bad})


if __name__ == '__main__':
    unittest.main()
