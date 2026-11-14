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
EXPORTER = Path(__file__).parents[3] / 'scripts' / 'export-contracts.py'
BASE_23CED03 = HERE / 'contracts_base_23ced03'
BASELINES = {'6008da0': BASE, '23ced03': BASE_23CED03}  # the contracts of the commit each initiative started from; both are kept
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


BUDGET_TOOLS = ('search', 'context')
ENDPOINT_KEY = 'x-kairos-endpoint'  # added by C-02: where each tool lives in `/v1` (CA-04)


def without_budget(tool):
    """The tool with only `semantic_budget_ms` taken out of its input schema (the one input added after the base commit)."""
    stripped = json.loads(json.dumps(tool))
    stripped['inputSchema']['properties'].pop('semantic_budget_ms', None)
    return stripped


def without_structured(tool):
    """The tool with only the optional `payload.structured` of C-05 taken out of the event schema it embeds (`$defs.Payload`)."""
    stripped = json.loads(json.dumps(tool))
    stripped['inputSchema'].get('$defs', {}).get('Payload', {}).get('properties', {}).pop('structured', None)
    return stripped


def endpoints(declared):
    """Every `{method, path}` object inside a declaration, nested ones included."""
    found = [declared] if 'path' in declared else []
    for value in declared.values():
        if isinstance(value, dict):
            found.extend(endpoints(value))
    return found


def without_endpoint(tool):
    """The tool with only the additive `x-kairos-endpoint` taken out (the one top-level key added by C-02)."""
    return {key: value for key, value in tool.items() if key != ENDPOINT_KEY}


def tool_differences(base, new, path='$'):
    """Exact comparison of two tool definitions (text modulo layout): any added, removed or changed key is a difference."""
    if isinstance(base, dict) and isinstance(new, dict):
        found = [f'{path}.{key}: added' for key in new if key not in base] + [f'{path}.{key}: removed' for key in base if key not in new]
        for key in base:
            if key in new:
                found.extend(tool_differences(base[key], new[key], f'{path}.{key}'))
        return found
    if isinstance(base, list) and isinstance(new, list):
        if len(base) != len(new):
            return [f'{path}: list changed length']
        return [item for index, (old, current) in enumerate(zip(base, new)) for item in tool_differences(old, current, f'{path}[{index}]')]
    return [] if layout(base) == layout(new) and type(base) is type(new) else [f'{path}: {base!r} became {new!r}']


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

    def test_every_tool_keeps_its_exact_contract_except_the_optional_budget_of_search_and_context(self):
        # Exact equality (not only "additive"): a key that restricts the input (`maximum`, `additionalProperties`, `minLength`,
        # `dependentRequired`...) would pass an additive rule and still break callers. The one legitimate change of the 34 tools
        # is the optional `semantic_budget_ms` of `search` and `context` (review of phase 6): it is taken out and the rest compared.
        before = {tool['name']: tool for tool in self.base['kairos-mcp.json']['tools']}
        after = {tool['name']: tool for tool in self.exported['kairos-mcp.json']['tools']}
        self.assertEqual(list(before), list(after))
        for name in before:
            current = without_endpoint(without_structured(without_budget(after[name]) if name in BUDGET_TOOLS else after[name]))
            self.assertEqual(tool_differences(before[name], current), [], name)
        for name in BUDGET_TOOLS:
            schema = after[name]['inputSchema']
            self.assertEqual(set(schema['properties']) - set(before[name]['inputSchema']['properties']), {'semantic_budget_ms'}, name)
            self.assertNotIn('semantic_budget_ms', schema.get('required', []), name)
        self.assertIs(after['search']['inputSchema']['properties']['semantic']['default'], True)  # the existing default is not touched

    def test_structured_is_an_optional_object_in_every_tool_that_embeds_the_event(self):
        # C-05 (P-11): the new `payload.structured` never becomes required and appears wherever the event schema does.
        carriers = [tool for tool in self.exported['kairos-mcp.json']['tools'] if 'Payload' in tool['inputSchema'].get('$defs', {})]
        self.assertGreaterEqual({tool['name'] for tool in carriers}, {'observation_add', 'observation_record_event'})
        for tool in carriers:
            payload = tool['inputSchema']['$defs']['Payload']
            self.assertIn('structured', payload['properties'], tool['name'])
            self.assertNotIn('structured', payload.get('required', []), tool['name'])
        schemas = self.exported['memory-platform.openapi.json']['components']['schemas']
        self.assertNotIn('structured', schemas['Payload'].get('required', []))

    def test_ca04_every_tool_declares_an_endpoint_that_exists_in_the_openapi_or_is_local(self):
        paths = self.exported['memory-platform.openapi.json']['paths']
        tools = self.exported['kairos-mcp.json']['tools']
        self.assertEqual(len(tools), EXPECTED_TOOLS)
        local = []
        for tool in tools:
            declared = tool.get(ENDPOINT_KEY)
            self.assertIsNotNone(declared, tool['name'] + ' has no ' + ENDPOINT_KEY)
            if declared == 'local':
                local.append(tool['name'])
                continue
            self.assertTrue({'method', 'path'} <= set(declared), tool['name'])
            for endpoint in endpoints(declared):  # the endpoint itself and the alternatives it names (`event_status` without a project)
                self.assertIn(endpoint['path'], paths, tool['name'])
                self.assertIn(endpoint['method'].lower(), paths[endpoint['path']], tool['name'])
        self.assertEqual(local, ['important_workflow'])
        # the seven endpoints C-02 created are the ones their tools declare
        declared = {tool['name']: tool[ENDPOINT_KEY] for tool in tools}
        self.assertEqual({key: declared['capture_policy'][key] for key in ('method', 'path')}, {'method': 'GET', 'path': '/v1/projects/{project_id}/capture-policy'})
        self.assertEqual(declared['query_corpus']['path'], '/v1/projects/{project_id}/corpora/{name}/query')
        self.assertEqual(declared['team_search']['path'], '/v1/projects/{project_id}/team-search')
        self.assertEqual({key: declared['get_observations'][key] for key in ('method', 'path')}, {'method': 'POST', 'path': '/v1/projects/{project_id}/observations/get'})
        # the existing operations are not renamed: the declared endpoints never point at the portal listing
        self.assertNotEqual(declared['observation_search']['path'], '/v1/observations')

    def test_ca07_ca29_the_exported_contracts_only_gain_against_every_baseline_and_keep_every_tool_exact_against_the_latest(self):
        for commit, directory in BASELINES.items():
            base = {path.name: json.loads(path.read_text(encoding='utf-8')) for path in directory.glob('*.json')}
            self.assertEqual(set(base), {'kairos-mcp.json', 'memory-platform.openapi.json'}, commit)
            self.assertEqual(len(base['kairos-mcp.json']['tools']), EXPECTED_TOOLS, commit)
            for name, value in self.exported.items():
                self.assertEqual(additive_violations(base[name], json.loads(json.dumps(value))), [], (commit, name))
            self.assertEqual([tool['name'] for tool in self.exported['kairos-mcp.json']['tools']], [tool['name'] for tool in base['kairos-mcp.json']['tools']], commit)
        # `23ced03` already had the optional budget of search and context: against it, no existing key of any tool changes at all
        latest = {tool['name']: tool for tool in json.loads((BASE_23CED03 / 'kairos-mcp.json').read_text(encoding='utf-8'))['tools']}
        self.assertTrue(all('semantic_budget_ms' in latest[name]['inputSchema']['properties'] for name in BUDGET_TOOLS))
        for tool in self.exported['kairos-mcp.json']['tools']:
            self.assertEqual(tool_differences(latest[tool['name']], without_endpoint(without_structured(tool))), [], tool['name'])
        # the existing routes keep their operations: every (path, method) of the baseline is still there with its parameters and body
        base_paths = json.loads((BASE_23CED03 / 'memory-platform.openapi.json').read_text(encoding='utf-8'))['paths']
        paths = self.exported['memory-platform.openapi.json']['paths']
        for path, operations in base_paths.items():
            for method, operation in operations.items():
                self.assertEqual(paths[path][method].get('parameters'), operation.get('parameters'), (path, method))
                self.assertEqual(paths[path][method].get('requestBody'), operation.get('requestBody'), (path, method))
        self.assertGreater(len(paths), len(base_paths))  # C-02 added the new ones

    def test_the_exact_check_rejects_a_restricting_key_anywhere_in_a_tool(self):
        before = next(tool for tool in self.base['kairos-mcp.json']['tools'] if tool['name'] == 'search')
        exported = next(tool for tool in self.exported['kairos-mcp.json']['tools'] if tool['name'] == 'search')
        self.assertEqual(tool_differences(before, without_endpoint(without_budget(exported))), [])
        for name, damage in (('maximum', lambda s: s['properties']['limit'].update(maximum=3)),
                             ('additionalProperties', lambda s: s.update(additionalProperties=False)),
                             ('minLength', lambda s: s['properties']['q'].update(minLength=5)),
                             ('dependentRequired', lambda s: s.update(dependentRequired={'layers': ['q']}))):
            broken = json.loads(json.dumps(exported))
            damage(broken['inputSchema'])
            self.assertTrue(tool_differences(before, without_endpoint(without_budget(broken))), name)

    def test_the_models_module_defines_the_field_once(self):
        self.assertIn('matched_chunk', models.Hit.model_fields)
        self.assertIs(models.Hit.model_fields['matched_chunk'].is_required(), False)


if __name__ == '__main__':
    unittest.main()
