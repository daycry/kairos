"""T-69 (CA-10, CA-29): `tools/list` of kairos-mcp passes the rule of `test_contract_additive.py` against the contract of `23ced03`.

The server side (`server/` tests, `test_contract_additive.py`, class `ToolsListIdentityTests`) runs the same rule over the internal MCP and
over kairos-mcp and compares the two listings with each other; this file is the half that runs in the image of kairos-mcp alone, so it carries a copy of the
`23ced03` tool list (`contract_base_23ced03/`, kept byte for byte equal to the server's baseline by that same server-side test).
"""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # runs as `python -m unittest tests.test_contract_identity` too
from test_tools_list import additive_violations, make_client, rpc

BASE = json.loads((Path(__file__).parent / 'contract_base_23ced03' / 'kairos-mcp.json').read_text(encoding='utf-8'))['tools']
PUBLIC_KEYS = ('name', 'description', 'inputSchema', 'annotations')  # what a client sees of a tool
SINCE_BASE = ('semantic_budget_ms',)  # already in 23ced03: the one legitimate input of search and context added after 6008da0
OPTIONAL_STRUCTURED = 'structured'  # `payload.structured` (C-05) is the only property added to an existing schema since 23ced03


def public(tool):
    return {key: tool[key] for key in PUBLIC_KEYS}


def without_structured(tool):
    stripped = copy.deepcopy(tool)
    stripped['inputSchema'].get('$defs', {}).get('Payload', {}).get('properties', {}).pop(OPTIONAL_STRUCTURED, None)
    return stripped


def listed_tools():
    with make_client() as client:
        rpc(client, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}})
        return rpc(client, 'tools/list', number=2).json()['result']['tools']


class ContractIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.listed = listed_tools()

    def test_34_tools_in_the_order_of_the_baseline(self):
        self.assertEqual(len(BASE), 34)
        self.assertEqual([tool['name'] for tool in self.listed], [tool['name'] for tool in BASE])

    def test_the_listing_only_gains_against_the_baseline_of_23ced03(self):
        for listed, base in zip(self.listed, BASE):
            with self.subTest(tool=base['name']):
                self.assertEqual(additive_violations(public(base), public(listed)), [])

    def test_no_existing_key_changes_at_all_against_the_baseline(self):
        # `payload.structured` is the one property the schemas gained since 23ced03; with it taken out the tool is the baseline one, exactly.
        for listed, base in zip(self.listed, BASE):
            with self.subTest(tool=base['name']):
                self.assertEqual(public(without_structured(listed)), public(base))

    def test_a_minimal_change_of_a_description_makes_the_rule_fail(self):
        # The rule must see a one-character change: it is run over a copy of the listing with the last character of one description changed.
        for index in (0, len(self.listed) // 2, len(self.listed) - 1):
            mutated = copy.deepcopy(self.listed[index])
            mutated['description'] = mutated['description'][:-1] + ('!' if not mutated['description'].endswith('!') else '?')
            self.assertTrue(additive_violations(public(BASE[index]), public(mutated)), BASE[index]['name'])
        index = next(i for i, tool in enumerate(self.listed) if tool['inputSchema'].get('properties'))
        removed = copy.deepcopy(self.listed[index])
        removed['inputSchema']['properties'].pop(next(iter(removed['inputSchema']['properties'])))
        self.assertTrue(additive_violations(public(BASE[index]), public(removed)))


if __name__ == '__main__':
    unittest.main()
