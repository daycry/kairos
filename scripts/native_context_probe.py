"""Private, temporary context canaries for native acceptance (no transcripts)."""
from datetime import datetime,timezone
import hashlib
import json
import re
import urllib.error
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


def prompt(query_tag):
    if not re.fullmatch('kx[a-f0-9]{20}',query_tag):raise ValueError('Invalid context query tag')
    return (query_tag+' Prueba Kairos de contexto automatico. No uses ninguna herramienta, MCP, comando o lectura de archivos. '
        'Busca en el conocimiento de proyecto que ya recibiste al iniciar el turno el marcador cuyo prefijo literal es '
        'KAIROS_CONTEXT_PROOF:. Devuelve solamente ese marcador completo, incluido su sufijo, sin inventarlo. '
        'Si no esta en tu contexto, responde KAIROS_CONTEXT_MISSING.')


def state_path(h,private,client):
    if client not in h.CLIENTS:raise h.AcceptanceError('Invalid native client')
    return h.safe(private/('context-'+client+'.json'))


def event(meta,delete=False):
    payload=meta['payload'];hook='SessionEnd' if delete else 'Stop'
    capture_hash=digest({'project':meta['project_id'],'runtime':'native-context-probe',
        'session':meta['probe_session'],'event':hook,'payload':payload})
    return {'event_id':meta['delete_event_id'] if delete else meta['event_id'],
        'item_id':meta['item_id'],'version':2 if delete else 1,'project_id':meta['project_id'],
        'session_id':meta['probe_session'],'agent_id':'native-context-probe','generate':False,
        'event_type':'delete' if delete else 'summary','occurred_at':meta['delete_at'] if delete else meta['created_at_utc'],
        'capture':{'mode':'summary','hook_event':hook,'fingerprint':capture_hash},'payload':payload}


def receipt_matches(value,body):
    return isinstance(value,dict) and all(value.get(k)==body[k] for k in ['event_id','item_id','version']) and value.get('status')=='accepted' and value.get('jobs')==[] and value.get('capture_hash')==body['capture']['fingerprint']


def lookup(request,event_id):
    try:return request('/v1/events/'+event_id)
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise


def retire(h,private,client,request):
    path=state_path(h,private,client)
    if not path.exists():return {'status':'no_probe'}
    meta=json.loads(path.read_text(encoding='utf-8'))
    if meta.get('client')!=client or meta.get('project_id')!=h.PROJECT or meta.get('run_id')!=h.latest():
        raise h.AcceptanceError('Context probe ownership differs; nothing retired')
    if meta['phase']=='retired':
        if not receipt_matches(lookup(request,meta['delete_event_id']),event(meta,True)):
            raise h.AcceptanceError('Context retirement receipt no longer matches')
        return {'status':'retired','item_id':meta['item_id']}
    created=lookup(request,meta['event_id'])
    if created is None:
        if meta['phase'] in {'preflight','absent_verified'}:
            meta['phase']='absent_verified';h.save(path,meta)
            return {'status':'absent_verified'}
        if meta['phase']=='create_pending':
            # A timed-out POST may still commit after an initial 404. Replay
            # the exact journalled event idempotently, then retire it; never
            # leave a late orphan or invent a replacement identity.
            created=request('/v1/events',event(meta))
        else:raise h.AcceptanceError('Context creation receipt is absent; explicit reconciliation required')
    if not receipt_matches(created,event(meta)):
        raise h.AcceptanceError('Context probe creation receipt differs; nothing retired')
    if 'delete_at' not in meta:
        meta['delete_at']=datetime.now(timezone.utc).isoformat()
        h.save(path,meta)
    deletion=event(meta,True);previous=lookup(request,deletion['event_id'])
    if previous is None:
        notes=[row for row in h.verification_pages(request,'notes') if row.get('item_id')==meta['item_id']]
        if len(notes)!=1 or notes[0].get('version')!=1 or notes[0].get('agent_id')!='native-context-probe' or any(notes[0].get(k)!=v for k,v in meta['payload'].items()):
            raise h.AcceptanceError('Context probe was changed elsewhere; nothing retired')
        meta['phase']='retire_pending';h.save(path,meta)
        previous=request('/v1/events',deletion)
    if not receipt_matches(previous,deletion):raise h.AcceptanceError('Context probe retirement requires reconciliation')
    # Verify the server readback even after a successful write acknowledgement.
    if not receipt_matches(lookup(request,deletion['event_id']),deletion):raise h.AcceptanceError('Context probe retirement readback differs')
    meta['phase']='retired';meta['retired_at_utc']=datetime.now(timezone.utc).isoformat();h.save(path,meta)
    return {'status':'retired','item_id':meta['item_id']}


def run(h,secret_dir,client,model=None):
    run_id=h.latest();private=h.private_directory(secret_dir,run_id)
    with h.capture_operation(private):
        activation=h.capture_file(private,client)
        if not activation.exists() or json.loads(activation.read_text(encoding='utf-8'))['status']!='enabled':
            raise h.AcceptanceError('Enable summary capture for this test client first')
        path=state_path(h,private,client)
        if path.exists() and json.loads(path.read_text(encoding='utf-8'))['phase'] not in {'retired','absent_verified'}:
            raise h.AcceptanceError('An earlier context probe needs --retire-context before another test')
        attempt=uuid.uuid4().hex;tag='kx'+uuid.uuid4().hex[:20];marker='KAIROS_CONTEXT_PROOF:'+uuid.uuid4().hex
        created=datetime.now(timezone.utc).isoformat()
        content=json.dumps({'summary':tag+' '+marker},sort_keys=True,separators=(',',':'))
        meta={'run_id':run_id,'client':client,'project_id':h.PROJECT,'attempt_id':attempt,'phase':'preflight',
            'created_at_utc':created,'query_tag':tag,'marker':marker,'marker_sha256':hashlib.sha256(marker.encode()).hexdigest(),
            'item_id':str(uuid.uuid4()),'event_id':str(uuid.uuid4()),'delete_event_id':str(uuid.uuid4()),
            'probe_session':'acceptance:'+run_id+':'+client+':'+attempt,
            'payload':{'title':tag+' Kairos automatic context acceptance probe','content':content,'category':'native-acceptance-probe',
                'tags':['native-acceptance-probe','capture:summary'],'facts':[],'validation_status':'validated',
                'evidence':['Synthetic acceptance canary generated by the operator-authorized native test; not project knowledge.'],
                'source':{'uri':'kairos-test://context/'+attempt,'sha256':hashlib.sha256(content.encode()).hexdigest()}}}
        # All private files must be writable before the first remote mutation.
        h.save(path,meta)
        for suffix in ['.context.jsonl','.context.stderr']:
            with h.safe(private/(client+suffix)).open('w',encoding='utf-8'):pass
        h.save(private/(client+'.context.status.json'),{'client':client,'status':'preparing','context_attempt':attempt,'exit_code':None,'timed_out':False})
        # Validate CLI/model arguments before inserting the canary.
        h.command(client,h.fixture(run_id,client),model=model,context_test={'query_tag':tag,'attempt_id':attempt})
        with h.administrator(secret_dir) as request:
            meta['phase']='create_pending';h.save(path,meta)
            try:
                body=event(meta);ack=request('/v1/events',body)
                if not receipt_matches(ack,body) or not receipt_matches(lookup(request,body['event_id']),body):
                    raise h.AcceptanceError('Context probe creation requires reconciliation')
                meta['phase']='created';h.save(path,meta)
                # This run uses a fresh native session. Its prompt contains the
                # search tag, never the unpredictable marker's suffix.
                result=h.run(secret_dir,client,model=model,context_test={'query_tag':tag,'attempt_id':attempt})
            finally:
                # The journal is saved BEFORE each mutation. If a response is
                # lost, --retire-context reconciles these exact UUIDs, not a new probe.
                retirement=retire(h,private,client,request)
        return dict(result,probe_retirement=retirement['status'],next='--collect; verify automatic context and lifecycle persistence separately')


def verification(h,private,client,request):
    path=state_path(h,private,client);status_path=h.safe(private/(client+'.context.status.json'))
    if not path.exists() or not status_path.exists():return {'status':'not_run'}
    meta=json.loads(path.read_text(encoding='utf-8'));status=json.loads(status_path.read_text(encoding='utf-8'))
    if meta.get('client')!=client or meta.get('project_id')!=h.PROJECT or meta.get('run_id')!=h.latest():raise h.AcceptanceError('Context probe ownership mismatch')
    if meta['phase']!='retired' or status.get('context_attempt')!=meta['attempt_id'] or status.get('exit_code')!=0 or status.get('timed_out'):
        return {'status':'needs_review','reason':'probe_or_native_run_incomplete'}
    if not re.fullmatch('KAIROS_CONTEXT_PROOF:[a-f0-9]{32}',meta.get('marker','')) or hashlib.sha256(meta['marker'].encode()).hexdigest()!=meta.get('marker_sha256'):
        raise h.AcceptanceError('Context marker metadata differs')
    if meta['marker'] not in meta['payload']['content'] or meta['query_tag'] not in meta['payload']['content'] or hashlib.sha256(meta['payload']['content'].encode()).hexdigest()!=meta['payload']['source']['sha256']:
        raise h.AcceptanceError('Context probe content differs')
    if datetime.fromisoformat(status['started_at_utc'])<datetime.fromisoformat(meta['created_at_utc']):return {'status':'needs_review','reason':'stale_native_run'}
    rows=h.read_packets(h.safe(private/(client+'.context.jsonl')))
    evidence=h.summarize(client,rows)
    if evidence['native_errors'] or has_tools(rows):return {'status':'needs_review','reason':'native_error_or_tool_use'}
    answer=assistant_text(client,rows)
    if meta['marker'] not in answer:return {'status':'needs_review','reason':'automatic_marker_not_observed'}
    if not receipt_matches(lookup(request,meta['event_id']),event(meta)) or not receipt_matches(lookup(request,meta['delete_event_id']),event(meta,True)):
        return {'status':'needs_review','reason':'probe_receipt_mismatch'}
    session=h.native_session(client,rows)
    return {'status':'accepted','client':client,'project_id':h.PROJECT,'session_id':session,'started_at_utc':status['started_at_utc'],
        'attempt_id':meta['attempt_id'],'marker_sha256':meta['marker_sha256'],'tool_calls':0,'probe_item_id':meta['item_id'],
        'probe_create_event_id':meta['event_id'],'probe_delete_event_id':meta['delete_event_id'],'probe_retired':True,'raw_content_exported':False}


def has_tools(rows):
    for row in rows:
        if row.get('type')=='error' or row.get('part',{}).get('type')=='tool':return True
        if row.get('type') in {'tool_use','item.started'} and (row.get('type')=='tool_use' or row.get('item',{}).get('type') not in {'agent_message','reasoning','error'}):return True
        if row.get('type')=='item.completed' and row.get('item',{}).get('type') not in {'agent_message','reasoning','error'}:return True
        if any(block.get('type')=='tool_use' for block in row.get('message',{}).get('content',[]) if isinstance(block,dict)):return True
    return False


def assistant_text(client,rows):
    output=[]
    for row in rows:
        if client=='codex' and row.get('type')=='item.completed' and row.get('item',{}).get('type')=='agent_message':output.append(row['item'].get('text',''))
        elif client=='opencode' and row.get('type')=='text':output.append(row.get('part',{}).get('text',''))
        elif client=='claude' and row.get('type')=='assistant':output.extend(block.get('text','') for block in row.get('message',{}).get('content',[]) if isinstance(block,dict) and block.get('type')=='text')
    return '\n'.join(text for text in output if isinstance(text,str))
