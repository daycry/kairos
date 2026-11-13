"""kairos-mcp serves the tools of `mcp/contract/kairos-mcp.json`, a copy of `docs/contracts/kairos-mcp.json` (CA-10, T-38).

The component cannot read the repository (its image is built from `mcp/` alone), so it carries a copy of the exported contract; this test,
on the server side where both files are in the image, is what keeps the copy from diverging.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs' / 'contracts' / 'kairos-mcp.json'
COPY = ROOT / 'mcp' / 'contract' / 'kairos-mcp.json'


class ContractCopyTests(unittest.TestCase):
    def test_the_copy_is_byte_for_byte_the_exported_contract(self):
        self.assertTrue(COPY.is_file(), 'mcp/contract/kairos-mcp.json is missing: copy docs/contracts/kairos-mcp.json after exporting')
        self.assertEqual(COPY.read_bytes(), DOCS.read_bytes())

    def test_the_copy_lists_34_tools_each_with_its_endpoint(self):
        tools = json.loads(COPY.read_text(encoding='utf-8'))['tools']
        self.assertEqual(len(tools), 34)
        self.assertEqual([tool['name'] for tool in tools], [tool['name'] for tool in json.loads(DOCS.read_text(encoding='utf-8'))['tools']])
        self.assertTrue(all('x-kairos-endpoint' in tool for tool in tools))


if __name__ == '__main__':
    unittest.main()
