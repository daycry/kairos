"""The exported contracts only GROW (CA-29, CA-33): `matched_chunk` is optional and the 34 MCP tools are untouched.

`contracts_base/` holds the contracts of the commit the initiative started from (6008da0, before `matched_chunk`); the
exporter output is compared against it with a strictly additive rule.
"""
import importlib.util
import json
from pathlib import Path
import unittest

from memory_platform import models
from memory_platform.retrieval import hit

HERE = Path(__file__).parent
BASE = HERE / 'contracts_base'
EXPORTER = Path(__file__).parents[2] / 'scripts' / 'export-contracts.py'
EXPECTED_TOOLS = 34


def load_exporter():
    spec = importlib.util.spec_from_file_location('kairos_export_contracts', EXPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layout(value):
    """Strings compare without layout: tool descriptions are docstrings, and Python 3.13 strips their indentation while 3.12 (the test image) keeps it."""
    return ' '.join(value.split()) if isinstance(value, str) else value


def additive_violations(base, new, path='$'):
    """What the new contract removed or changed with respect to the base one (empty = purely additive).

    Mappings may gain keys. Sequences keep their length and order (a tool list cannot lose or reorder a tool); `required`
    lists must be identical, because a new required field would break existing callers. Scalars (types, defaults, text) are equal
    (text modulo whitespace layout, see `layout`).
    """
    if isinstance(base, dict):
        if not isinstance(new, dict):
            return [f'{path}: was an object']
        found = []
        for key, value in base.items():
            if key not in new:
                found.append(f'{path}.{key}: removed')
            else:
                found.extend(additive_violations(value, new[key], f'{path}.{key}'))
        return found
    if isinstance(base, list):
        if not isinstance(new, list) or len(new) != len(base):
            return [f'{path}: list changed length']
        if path.endswith('.required'):
            return [] if new == base else [f'{path}: required fields changed']
        found = []
        for index, (old, current) in enumerate(zip(base, new)):
            found.extend(additive_violations(old, current, f'{path}[{index}]'))
        return found
    return [] if layout(base) == layout(new) else [f'{path}: {base!r} became {new!r}']


class ContractAdditiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exported = load_exporter().contracts()
        cls.base = {path.name: json.loads(path.read_text(encoding='utf-8')) for path in BASE.glob('*.json')}

    def test_the_rule_detects_removals_changes_and_new_required_fields(self):
        base = {'tools': [{'name': 'a', 'inputSchema': {'required': ['x'], 'properties': {'x': {'default': True}}}}]}
        grown = json.loads(json.dumps(base))
        grown['tools'][0]['inputSchema']['properties']['y'] = {'type': 'string'}
        grown['extra'] = {'new': 1}
        self.assertEqual(additive_violations(base, grown), [])
        for damage in (lambda v: v['tools'].append({'name': 'b'}),
                       lambda v: v['tools'].pop(),
                       lambda v: v['tools'][0]['inputSchema']['properties']['x'].update(default=False),
                       lambda v: v['tools'][0]['inputSchema']['properties'].pop('x'),
                       lambda v: v['tools'][0]['inputSchema']['required'].append('y'),
                       lambda v: v['tools'][0].update(name='renamed')):
            broken = json.loads(json.dumps(grown))
            damage(broken)
            self.assertTrue(additive_violations(base, broken), broken)

    def test_the_base_snapshot_is_the_contract_before_matched_chunk(self):
        self.assertEqual(set(self.base), {'kairos-mcp.json', 'memory-platform.openapi.json'})
        self.assertNotIn('matched_chunk', json.dumps(self.base))
        self.assertEqual(len(self.base['kairos-mcp.json']['tools']), EXPECTED_TOOLS)

    def test_ca33_the_exported_contracts_only_gain_and_still_have_thirty_four_tools(self):
        for name, value in self.exported.items():
            self.assertEqual(additive_violations(self.base[name], json.loads(json.dumps(value))), [], name)
        tools = self.exported['kairos-mcp.json']['tools']
        self.assertEqual(len(tools), EXPECTED_TOOLS)
        self.assertEqual([tool['name'] for tool in tools], [tool['name'] for tool in self.base['kairos-mcp.json']['tools']])

    def test_ca29_matched_chunk_is_an_optional_field_of_the_exported_search_result(self):
        mcp = self.exported['kairos-mcp.json']['result_schemas']['search']
        for hit_schema in (mcp['$defs']['Hit'], self.exported['memory-platform.openapi.json']['components']['schemas']['Hit']):
            self.assertIn('matched_chunk', hit_schema['properties'])
            self.assertNotIn('matched_chunk', hit_schema.get('required', []))
        definition = mcp['$defs']['MatchedChunk']
        self.assertEqual(sorted(definition['properties']), ['char_end', 'char_start', 'ordinal'])
        self.assertEqual(sorted(definition['required']), ['char_end', 'char_start', 'ordinal'])
        # Fields of the public hit that were already optional keep that status.
        self.assertTrue({'ref', 'layer', 'project_id', 'item_id', 'title', 'excerpt'}.issubset(set(mcp['$defs']['Hit']['required'])))

    def test_ca29_hits_without_a_fragment_omit_the_field_and_ref_keeps_its_format(self):
        plain = hit({'ref': 'documental:p:i:1', 'layer': 'documental', 'project_id': 'p', 'item_id': 'i', 'title': 'T', 'excerpt': 'x', 'validation_status': 'validated', 'version': 1})
        self.assertNotIn('matched_chunk', plain)
        chunked = hit(dict(plain, matched_chunk={'ordinal': 3, 'char_start': 100, 'char_end': 200}))
        self.assertEqual(chunked['matched_chunk'], {'ordinal': 3, 'char_start': 100, 'char_end': 200})
        self.assertEqual(chunked['ref'], plain['ref'])
        with self.assertRaises(Exception):
            hit(dict(plain, matched_chunk={'ordinal': -1, 'char_start': 0, 'char_end': 1}))

    def test_the_search_tool_still_has_its_previous_input_contract(self):
        before = next(tool for tool in self.base['kairos-mcp.json']['tools'] if tool['name'] == 'search')
        after = next(tool for tool in self.exported['kairos-mcp.json']['tools'] if tool['name'] == 'search')
        self.assertEqual(before, after)
        self.assertIs(after['inputSchema']['properties']['semantic']['default'], True)  # the existing default is not touched

    def test_the_models_module_defines_the_field_once(self):
        self.assertIn('matched_chunk', models.Hit.model_fields)
        self.assertIs(models.Hit.model_fields['matched_chunk'].is_required(), False)


if __name__ == '__main__':
    unittest.main()
