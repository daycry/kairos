import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from memory_platform.privacy import sanitize_payload
from memory_platform.store import Store
from memory_platform.mcp import AuthenticatedMCP

results = []
secret = 'V7m9R2t5N8q3C6b1K4w0Z9s2D5h8J6p3'
for name in ['DB_PASSWORD','AWS_SECRET_ACCESS_KEY','GITHUB_TOKEN']:
    value,_ = sanitize_payload({'content': name+'='+secret})
    assert secret in value['content']
results.append({'id': 'I-9-server','confirmed': True,'evidence': 'Synthetic prefixed .env assignments survive server sanitization.'})

class Connection:
    def __init__(self): self.destinations=[]
    def execute(self,sql,values): self.destinations.append(values[6])

connection=Connection()
Store('unused',embedding_enabled=True)._jobs(connection,'fixture',str(uuid4()),1,'a'*64,'item',[],'upsert')
assert connection.destinations == ['embed']
results.append({'id': 'I-2','confirmed': True,'evidence': 'With the production embedding flag, _jobs adds embed for an item even with no extraction destinations. SQL execution was replaced by an owned recorder; no database/provider called.'})

async def blocking_auth_probe():
    class Auth:
        def authenticate_bearer(self,token):
            time.sleep(0.1)
            return {'id': 'fixture'}
    async def app(scope,receive,send): pass
    async def receive(): return {'type': 'http.request','body': b''}
    async def send(message): pass
    middleware=AuthenticatedMCP(app,Auth())
    scope={'type': 'http','method': 'GET','path': '/mcp/','headers': [(b'authorization',b'Bearer synthetic-fixture')]}
    started=time.monotonic()
    task=asyncio.create_task(middleware(scope,receive,send))
    await asyncio.sleep(0.01)
    delay=time.monotonic()-started
    await task
    assert delay >= 0.09
    return round(delay,3)

delay=asyncio.run(blocking_auth_probe())
results.append({'id': 'I-7','confirmed': True,'evidence': 'A 100ms synchronous authentication stand-in delays an independent event-loop timer for at least 90ms. This proves the scheduling issue, not production throughput.', 'observed_delay_seconds': delay})
print(json.dumps({'source': 'synthetic local reproduction; no servers or providers','results': results},indent=2))
