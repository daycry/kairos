"""The services of the domain, called through kairos-mcp (T-48, CA-11).

`test_agent_tools.py` and `test_extended_tools.py` call `AgentStore` and `ExtendedStore` directly. Their chain variants call the same methods, with the same
arguments, on `ChainAgentStore` and `ChainExtendedStore`: each call is a tool call through kairos-mcp (MCP -> `/v1` -> the same stores) that answers the
parsed data and raises the domain exception the service raises, so the bodies of the tests do not change. A tool carries the message of a refusal and
not its class: the class is recovered from the messages the server itself defines (`refusal_classes`).
"""
import json
from pathlib import Path
import re

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import Conflict, Forbidden, MemoryError, NotFound, Unauthorized
from memory_platform.tests.chain_harness import ChainClient

ACCEPT = 'application/json, text/event-stream'
SERVER_DIR = Path(__file__).resolve().parents[1]
RENAMED = {'date_start': 'dateStart', 'date_end': 'dateEnd'}  # the names the build_corpus tool gives the filters of the service


def refusal_classes():
    """The class of each refusal message, read from the server: MCP carries the message only, the test needs `Conflict` or `Forbidden` back."""
    table = {'Authentication required': Unauthorized, 'Operation not permitted': Forbidden, 'Resource not found': NotFound, 'Conflicting event or version': Conflict}
    for source in SERVER_DIR.glob('*.py'):
        text = source.read_text(encoding='utf-8')
        for name, kind in (('Conflict', Conflict), ('Forbidden', Forbidden)):
            for message in re.findall(name + r"\('((?:[^'\\]|\\.)+)'\)", text):
                table.setdefault(message, kind)
    return table


class ChainSession:
    """One kairos-mcp over one server application over the store of the test, and a key per actor (made by the admin of the test)."""

    def __init__(self, store, admin):
        self.store, self.admin, self.tokens, self.refusals = store, admin, {}, refusal_classes()
        self.client = ChainClient(create_app(Settings('unused'), store=store, auth=Auth(store)))
        self.client.__enter__()

    def close(self):
        self.client.__exit__(None, None, None)

    def token(self, actor, project):
        if (actor['id'], project) not in self.tokens:
            made = self.store.create_key(self.admin, {'name': 'chain ' + actor['id'][:8], 'project_ids': [project], 'scopes': ['read', 'write']})
            if actor['id'] != self.admin['id']:
                with self.store.transaction() as c:  # only an admin delegates a key: the key is then handed to the actor the test speaks for
                    c.execute('UPDATE memory.api_keys SET actor_id=%s WHERE id=%s', (actor['id'], made['id']))
            self.tokens[(actor['id'], project)] = made['token']
        return self.tokens[(actor['id'], project)]

    def call(self, actor, scope, tool, /, **arguments):  # positional-only: `project`, `tool` and `name` are arguments of the tools too
        """`scope` is the project the key of the call is for; `arguments` are the arguments of the tool (which may carry their own `project`)."""
        arguments = {key: value for key, value in arguments.items() if value is not None}
        response = self.client.chain.post('/mcp/', headers={'Authorization': 'Bearer ' + self.token(actor, scope), 'Accept': ACCEPT},
                                          json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': tool, 'arguments': arguments}})
        if response.status_code == 401:
            raise Unauthorized()
        result = response.json()['result']
        text = result['content'][0]['text']
        if result.get('isError'):
            message = re.sub(r'^Error executing tool \w+: ', '', text)
            kind = self.refusals.get(message)
            if kind in (Unauthorized, NotFound):
                raise kind()
            raise kind(message) if kind else MemoryError('refused', message, 400)
        structured = result.get('structuredContent')
        if isinstance(structured, dict) and set(structured) == {'result'} and isinstance(structured['result'], str):
            return json.loads(structured['result'])
        return structured if isinstance(structured, dict) else json.loads(text)


class ChainAgentStore:
    def __init__(self, session):
        self.session = session

    def call(self, actor, scope, tool, /, **arguments):
        return self.session.call(actor, scope, tool, **arguments)

    def work_write(self, actor, project, list, fields, request_id, expected_version=None):
        return self.call(actor, project, 'work_state_write', project=project, list=list, fields=fields, request_id=request_id, expected_version=expected_version)

    def work_read(self, actor, project, list=None, include_closed=False):
        return self.call(actor, project, 'work_state_read', project=project, list=list, includeClosed=include_closed)

    def build_corpus(self, actor, project, name, description='', **filters):
        return self.call(actor, project, 'build_corpus', project=project, name=name, description=description, **{RENAMED.get(key, key): value for key, value in filters.items()})

    def list_corpora(self, actor, project):
        return self.call(actor, project, 'list_corpora', project=project)

    def prime_corpus(self, actor, project, name, fresh=False):
        return self.call(actor, project, 'reprime_corpus' if fresh else 'prime_corpus', project=project, name=name)

    def query_corpus(self, actor, project, name, question, limit=10):
        return self.call(actor, project, 'query_corpus', project=project, name=name, question=question, limit=limit)

    def rebuild_corpus(self, actor, project, name, force=False, expected_version=None):
        return self.call(actor, project, 'rebuild_corpus', project=project, name=name, force=force, expected_version=expected_version)

    def observations(self, actor, project, query='', ids=None, limit=None):
        if ids is not None:
            return self.call(actor, project, 'get_observations', projectId=project, ids=ids)
        return self.call(actor, project, 'observation_search', projectId=project, query=query, limit=limit)


class ChainExtendedStore(ChainAgentStore):
    def observation_add(self, actor, event):
        return self.call(actor, event['project_id'], 'observation_add', event=event)

    def observation_record_event(self, actor, event):
        return self.call(actor, event['project_id'], 'observation_record_event', event=event)

    def get_tool_uses(self, actor, project, session_id=None, tool=None, limit=20, cursor=None):
        return self.call(actor, project, 'get_tool_uses', project=project, session_id=session_id, tool=tool, limit=limit, cursor=cursor)

    def team_write(self, actor, project, list, fields, request_id, expected_version=None):
        return self.call(actor, project, 'team_work_write', project=project, list=list, fields=fields, request_id=request_id, expected_version=expected_version)

    def team_read(self, actor, project, list=None, include_closed=False):
        return self.call(actor, project, 'team_work_read', project=project, list=list, include_closed=include_closed)

    def team_search(self, actor, project, query='', limit=20):
        return self.call(actor, project, 'team_search', project=project, query=query, limit=limit)

    def team_brief(self, actor, project, limit=20):
        return self.call(actor, project, 'team_brief', project=project, limit=limit)
