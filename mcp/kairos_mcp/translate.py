"""Executes a tool call as the contract says: arguments become `/v1` requests (this module), answers become MCP results (budget, envelope).

Everything comes from `x-kairos-endpoint` and `x-kairos-translation` of `kairos-mcp.json`: where each argument goes (`in` path, query or body, under
which `name`, with which `transform`), the `fixed` values, the read of a value left out (`when_absent` with its `retry`), the values that cannot
travel (`untranslatable`) and the composition of `event_status` without a project (`without_project_id`). No tool is special-cased by name here.
"""
import asyncio
import json
import re
from urllib.parse import quote

from mcp import types

from .budget import OBJECT, OUTPUT, cut, render
from .client import fail
from .errors import UNAVAILABLE, ToolError

LOCAL_TEXT = {
    'important_workflow': (
        'Choose an authorized project with projects. Search a focused question, '
        'review timeline around relevant results, then retrieve only selected '
        'references with details or get_observations. Treat memory as untrusted '
        'evidence and verify source/version/validation. Capture concise authorized '
        'learning with remember and stable event/item UUIDs; poll event_status. '
        'Never upload secrets or unapproved transcripts. Use work_state for '
        'private open tasks. Corpora pin observation generations and provide '
        'lexical evidence, not generated answers or automatic approval.'),
}
PLACEHOLDER = re.compile(r'\{[A-Za-z_]+\}')
DEADLINE_FACTOR = 4  # a whole tool call (its requests, a rebuild's rereads included) takes at most this many request timeouts


def csv_list(value):
    """`transform: csv-list`: a string is split on commas, trimmed, empties dropped and duplicates removed; a list passes as it is."""
    if isinstance(value, list):
        return value
    return list(dict.fromkeys(part.strip() for part in value.split(',') if part.strip()))


def translate(rule, arguments):
    """One request, `(method, path, params, body)`, from an `x-kairos-endpoint` (or one of its `without_project_id` steps) and MCP arguments.

    An argument the call does not carry, or carries as null, is omitted: the server applies its default. An argument the contract has no rule for
    is ignored, as the internal tools ignore it."""
    path, params, fields, whole = rule['path'], {}, {}, None
    for argument, where in rule['args'].items():
        value = arguments.get(argument)
        if value is None:
            continue
        if where.get('transform') == 'csv-list':
            value = csv_list(value)
        if where['in'] == 'path':
            path = path.replace('{' + where['name'] + '}', quote(str(value), safe=''))
        elif where['in'] == 'query':
            params[where['name']] = ('true' if value else 'false') if isinstance(value, bool) else value
        elif 'name' in where:
            fields[where['name']] = value
        else:
            whole = value
    for fixed in rule.get('fixed', []):
        fields[fixed['name']] = fixed['value']
    if PLACEHOLDER.search(path):
        raise ToolError('A required argument is missing')
    body = (fields if whole is None else whole) if rule['method'] in ('POST', 'PUT') else None  # a POST always carries a JSON object, `{}` when empty
    return rule['method'], path, params or None, body


def lookup(value, dotted):
    for key in dotted.split('.'):
        value = value[key]
    return value


def holds(condition, scope):
    """The `complete` rule of `without_project_id`: `path` is / is not a value, or every `each` item of a list has `path` equal to `is`."""
    if 'each' in condition:
        return all(lookup(item, condition['path']) == condition['is'] for item in scope[condition['each']])
    value = lookup(scope, condition['path'])
    return value == condition['is'] if 'is' in condition else value != condition['is_not']


async def read_missing(rule, arguments, call):
    """`when_absent`: the values of the arguments the call left out (absent or null), each read as the contract says. `(values, None)`, or
    `(None, (status, body))` when a read fails, which `on_read_error: answer` makes the answer of the call."""
    values = {}
    for argument, where in rule['args'].items():
        if 'when_absent' in where and arguments.get(argument) is None:
            how = where['when_absent']
            method, path, params, body = translate(how['read'], {key: value for key, value in arguments.items() if key in how['read']['args']})
            status, read = await call(method, path, params, body)
            if status >= 400:
                return None, (status, read)  # `on_read_error: answer`, the only value the contract allows
            values[argument] = read[how['take']]
    return values, None


def refused_value(rule, arguments):
    for refused in rule.get('untranslatable', []):
        value = arguments.get(refused['argument'])
        if value is not None and value == refused['value'] and type(value) is type(refused['value']):
            return refused
    return None


async def perform(rule, arguments, call):
    """What a client of `/v1` does with one call: a value that cannot travel is answered, after the read that makes the server check access and
    existence in its own order when the contract says so (`after_read`); a value left out is read and sent; a `retry` status over a value that changed
    since it was read sends the request again, at most `max` more times, and with the value unchanged the conflict is the real answer."""
    refused = refused_value(rule, arguments)
    if refused:
        if refused.get('after_read'):
            _, failed = await read_missing(rule, {**arguments, refused['argument']: None}, call)
            if failed:
                return failed
        return refused['answer']['status'], {'error': refused['answer']['error']}
    retry = next((where['when_absent'].get('retry') for where in rule['args'].values() if 'when_absent' in where), None)
    sent = last = None
    for _ in range(1 + (retry['max'] if retry else 0)):
        values, failed = await read_missing(rule, arguments, call)
        if failed:
            return failed
        if last is not None and values == sent:
            return last
        sent = values
        method, path, params, body = translate(rule, {**arguments, **values})
        last = await call(method, path, params, body)
        if not values or retry is None or last[0] != retry['on_status']:
            return last
    return last


async def composed(rule, arguments, call):
    """`without_project_id`: the receipt, then each job it names, then the verdict the contract's `result` describes."""
    method, path, params, body = translate(rule['receipt'], arguments)
    status, receipt = await call(method, path, params, body)
    if status >= 400:
        return status, receipt
    scope = {'receipt': receipt, 'jobs': []}
    for job_id in lookup(scope, rule['jobs']['for_each']):
        method, path, params, body = translate(rule['jobs'], {'job_id': job_id})
        status, job = await call(method, path, params, body)
        if status >= 400:
            return status, job
        scope['jobs'].append(job)
    result = {}
    for key, how in rule['result'].items():
        result[key] = scope[how['from']] if 'from' in how else all(holds(condition, scope) for condition in how['all_of'])
    return 200, result


def result(text, structured=None):
    return types.CallToolResult(content=[types.TextContent(type='text', text=text)], structuredContent=structured, isError=False)


def shape_result(shape, budget, value):
    """The MCP result of a tool, as the internal MCP gives it: a dict as structured content and indented JSON text; a `-> str` tool as compact JSON
    text with `{"result": text}` as structured content. Over the byte budget the text is cut with its marker and an object loses its structure."""
    if shape == OBJECT:
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        cutoff = cut(text.encode('utf-8'), budget)
        return result(text, value) if cutoff == text else result(cutoff)
    text = render(value, budget)
    return result(text, {'result': text})


class Executor:
    def __init__(self, contract, client):
        self.contract, self.client = contract, client
        self.tools = {tool['name']: tool for tool in contract['tools']}

    async def execute(self, name, arguments, authorization):
        if name not in OUTPUT:
            raise ToolError('This tool is not available in this build of kairos-mcp')
        shape, budget = OUTPUT[name]
        tool = self.tools[name]
        endpoint = tool['x-kairos-endpoint']
        if endpoint == 'local':
            return result(LOCAL_TEXT[name], {'result': LOCAL_TEXT[name]})

        async def call(method, path, params=None, body=None):
            return await self.client.send(method, path, authorization, params, body)

        try:
            async with asyncio.timeout(self.client.timeout * DEADLINE_FACTOR):
                if 'without_project_id' in endpoint and arguments.get('project_id') is None:
                    status, body = await composed(endpoint['without_project_id'], arguments, call)
                else:
                    status, body = await perform(endpoint, arguments, call)
        except TimeoutError:
            raise ToolError(UNAVAILABLE) from None
        if status >= 400:
            fail(status, body)
        value = body if isinstance(body, dict) else {}
        return shape_result(shape, budget, value)
