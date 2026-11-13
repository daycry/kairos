"""One table-driven check of the tools of a group: what request each tool becomes, what it answers, and how it fails (T-41 to T-44)."""
from dataclasses import dataclass, field

from kairos_mcp.errors import UNAVAILABLE
from support import BEARER, TOOLS, Harness

ENVELOPE = ('untrusted', 'warning')
FORBIDDEN = (403, {'error': {'code': 'forbidden', 'message': 'Operation not permitted'}, 'request_id': 'r'})


@dataclass
class Case:
    tool: str
    args: dict
    method: str
    route: str  # the path as it goes on the wire, percent-encoding included
    reply: dict  # the JSON the stub answers with
    query: dict = field(default_factory=dict)  # name -> list of string values
    body: object = None
    status: int = 200  # of the success reply


def plain(data):
    """The data of a call without the additive fields of the untrusted-data envelope (S-05, T-45), which have their own tests."""
    return {key: value for key, value in data.items() if key not in ENVELOPE} if isinstance(data, dict) else data


def exercise(test, cases):
    """For each case: the request is the declared one with the caller's header, the answer is the stub's, a 4xx is its message, an outage is generic."""
    for case in cases:
        endpoint = TOOLS[case.tool]['x-kairos-endpoint']
        with test.subTest(tool=case.tool, check='success'):
            with Harness({(case.method, case.route): (case.status, case.reply)}) as harness:
                result = harness.call(case.tool, case.args)
                test.assertFalse(result.error, result.text)
                test.assertEqual(plain(result.data()), case.reply)
                test.assertEqual(len(harness.stub.requests), 1)
                request = harness.stub.requests[0]
                test.assertEqual((request.method, request.route), (case.method, case.route))
                test.assertEqual(request.query, case.query)
                test.assertEqual(request.body, case.body)
                test.assertEqual(request.headers['authorization'], BEARER)
                test.assertEqual(case.method, endpoint['method'])  # the case follows the contract, not its own idea of the endpoint
        with test.subTest(tool=case.tool, check='4xx'):
            with Harness({(case.method, case.route): FORBIDDEN}) as harness:
                result = harness.call(case.tool, case.args)
                test.assertTrue(result.error)
                test.assertEqual(result.text, 'Error executing tool %s: Operation not permitted' % case.tool)
        with test.subTest(tool=case.tool, check='5xx'):
            with Harness({(case.method, case.route): (500, None)}) as harness:
                result = harness.call(case.tool, case.args)
                test.assertTrue(result.error)
                test.assertEqual(result.text, 'Error executing tool %s: %s' % (case.tool, UNAVAILABLE))
        with test.subTest(tool=case.tool, check='down'):
            with Harness({}, api_url='http://127.0.0.1:9', timeout=2.0) as harness:
                result = harness.call(case.tool, case.args)
                test.assertTrue(result.error)
                test.assertEqual(result.text, 'Error executing tool %s: %s' % (case.tool, UNAVAILABLE))
