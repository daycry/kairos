"""Bounded, deterministic capture redaction; not a universal secret detector.

Only explicit private blocks and recognizable credential formats are covered.
Approved sources are reviewed, never silently rewritten by this module.
"""
import copy
import re
import json

from .errors import MemoryError

MAX_TEXT=1_048_576
PRIVATE='[PRIVADO]'
REDACTED='[REDACTADO]'
_CANDIDATE=re.compile(r'<\s*/?\s*private\b',re.IGNORECASE)
_TAG=re.compile(r'<\s*(/?)\s*private\s*>',re.IGNORECASE)
_PEM=re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----')
_PEM_BEGIN=re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----')
_OPENAI=re.compile(r'(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])')
_AWS=re.compile(r'(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])')
_BEARER=re.compile(r'\bBearer[ \t]+(?:eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|[A-Za-z0-9._~+/=-]{24,})',re.IGNORECASE)
_PROVIDER=re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{16,}|AIza[A-Za-z0-9_-]{30,})')
_JWT=re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}')
_DSN=re.compile(r'''\b[A-Za-z][A-Za-z0-9+.-]*://[^\s/@"'<>]*:[^\s/@"'<>]*@[^\s"'<>]+''')
_SECRET_NAME=re.compile(r'(?:^|_)(?:password|passwd|pwd|passphrase|secret|token|credentials?|api_?key|access_?key(?:_id)?|secret_access_key|access_token|client_secret|private_key|connection_string|authorization|cookie|dsn)$|^pgpassword$',re.IGNORECASE)
_NAMES=re.compile(r'''(?<![A-Za-z0-9_.-])((?:\\*["'])?((?:[A-Za-z_]|\\+u[0-9a-fA-F]{4})(?:[A-Za-z0-9_.-]|\\+u[0-9a-fA-F]{4}){0,127})(?:\\*["'])?\s*[:=]\s*)''')
_SAFE_VALUE=re.compile(r'^(?:\[(?:REDACTED|REDACTADO)\]|REDACTED|REDACTADO|changeme|replace[_ -]?me|example-placeholder-value|<(?:REDACTED|SECRET|PASSWORD|TOKEN|API_KEY|YOUR_[A-Z_]+)>|\$\{[A-Za-z_][A-Za-z0-9_]*\})$',re.IGNORECASE)

def secret_name(key):
    key=re.sub(r'\\+u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),key)
    return bool(_SECRET_NAME.search(re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',key).replace('.','_').replace('-','_')))

def _assignments(text):
    position=0; parts=[]; changed=False
    for match in _NAMES.finditer(text):
        if match.start()<position or not secret_name(match[2]):
            continue
        begin=match.end(); end=begin
        if re.match(r'''(?:\[(?:REDACTED|REDACTADO)\]|\$\{[A-Za-z_][A-Za-z0-9_]*\})(?=$|[\s,;&}\]"'])''',text[begin:],re.IGNORECASE):
            continue
        quote=re.match(r'''(\\*)(["'])''',text[begin:])
        if quote:
            begin+=len(quote[0]); end=begin
            while end<len(text):
                if text[end]==quote[2]:
                    slashes=0; at=end-1
                    while at>=begin and text[at]=='\\': slashes+=1; at-=1
                    if slashes>=len(quote[1]) and (slashes-len(quote[1]))%(2*(len(quote[1])+1))==0:
                        break
                end+=1
            if end==len(text):
                raise MemoryError('invalid_secret_assignment','Secret assignments must have balanced quotes',422)
            end-=len(quote[1])
        else:
            while end<len(text) and not re.match(r'''[\r\n&}\]"']''',text[end]): end+=1
        if end<=begin or _SAFE_VALUE.fullmatch(text[begin:end]):
            continue
        parts.extend([text[position:begin],REDACTED]); position=end; changed=True
    return ''.join(parts)+text[position:],changed


def strip_private(text):
    if not isinstance(text,str) or len(text)>MAX_TEXT:
        raise MemoryError('invalid_capture_text','Capture text exceeds its supported bound',422)
    parts=[]
    position=0
    depth=0
    changed=False
    for candidate in _CANDIDATE.finditer(text):
        tag=_TAG.match(text,candidate.start())
        if not tag:
            raise MemoryError('invalid_private_block','Private blocks must use balanced private tags',422)
        if not tag.group(1):
            if depth==0:
                parts.append(text[position:tag.start()])
            depth+=1
        else:
            if depth==0:
                raise MemoryError('invalid_private_block','Private blocks must use balanced private tags',422)
            depth-=1
            if depth==0:
                parts.append(PRIVATE)
                position=tag.end()
                changed=True
    if depth:
        raise MemoryError('invalid_private_block','Private blocks must use balanced private tags',422)
    parts.append(text[position:])
    return ''.join(parts),changed


def _json_clean(value,nesting):
    nodes=0; changed=False
    def visit(item,depth=0):
        nonlocal nodes,changed
        nodes+=1
        if nodes>10000 or depth>16:
            raise MemoryError('invalid_capture_text','Privacy input exceeds its supported bound',422)
        if isinstance(item,str):
            clean,redacted=_sanitize_text(item,nesting); changed|=redacted; return clean
        if isinstance(item,list): return [visit(child,depth+1) for child in item]
        if isinstance(item,dict):
            output={}
            for key,child in item.items():
                if secret_name(key) and child is not None and child!='' and not (isinstance(child,str) and _SAFE_VALUE.fullmatch(child)):
                    output[key]=REDACTED; changed=True
                else: output[key]=visit(child,depth+1)
            return output
        return item
    return visit(value),changed

def _sanitize_text(text,nesting=0):
    if nesting>8:
        raise MemoryError('invalid_capture_text','Serialized privacy input is too deeply nested',422)
    text,changed=strip_private(text)
    if re.match(r'^\s*[{[\"]',text):
        try: decoded=json.loads(text)
        except (ValueError,RecursionError): pass
        else:
            clean,redacted=_json_clean(decoded,nesting+1)
            if redacted: return json.dumps(clean,ensure_ascii=False,separators=(',',':')),True
    for pattern in (_PEM,_OPENAI,_AWS,_BEARER,_PROVIDER,_JWT,_DSN):
        def replacement(match):
            return REDACTED
        updated=pattern.sub(replacement,text)
        changed=changed or updated!=text
        text=updated
    if _PEM_BEGIN.search(text):
        raise MemoryError('invalid_private_key_block','Private key blocks must be complete before redaction',422)
    updated,assigned=_assignments(text)
    return updated,changed or assigned


def sanitize_payload(payload):
    result=copy.deepcopy(payload)
    changed=False
    def sanitize(value):
        nonlocal changed
        if isinstance(value,str):
            updated,redacted=_sanitize_text(value)
            changed=changed or redacted
            return updated
        return value
    for key in ('title','content','problem','correction'):
        if key in result:
            result[key]=sanitize(result[key])
    for key in ('evidence','tags'):
        if isinstance(result.get(key),list):
            result[key]=[sanitize(value) for value in result[key]]
    facts=[]
    for fact in result.get('facts',[]) or []:
        drop=False
        if isinstance(fact,dict):
            for key in ('subject','predicate','object','evidence_quote'):
                if isinstance(fact.get(key),str):
                    cleaned,redacted=_sanitize_text(fact[key])
                    drop=drop or redacted
                    fact[key]=cleaned
        if drop:
            changed=True
            continue
        facts.append(fact)
    if 'facts' in result:
        result['facts']=facts
    if result.get('source') is not None:
        try:
            sensitive=has_sensitive(result['source'])
        except MemoryError as exc:
            if exc.code not in {'invalid_private_block','invalid_private_key_block'}:
                raise
            sensitive=True
        if sensitive:
            raise MemoryError('sensitive_source_requires_review','Sensitive source metadata requires privacy review',422)
    return result,changed


def redact_log(text):
    """One string for a log line, with the capture rules applied. Never raises: text the rules cannot parse is hidden whole."""
    try:
        return _sanitize_text(str(text)[:2000])[0]
    except (MemoryError,RecursionError):
        return REDACTED


def has_sensitive(value):
    pending=[(value,0)]
    visited=0
    while pending:
        current,depth=pending.pop()
        visited+=1
        if visited>10000 or depth>16:
            raise MemoryError('invalid_capture_text','Privacy input exceeds its supported bound',422)
        if isinstance(current,str) and _sanitize_text(current)[1]:
            return True
        if isinstance(current,dict):
            for key,item in current.items():
                if secret_name(str(key)) and item is not None and item!='' and not (isinstance(item,str) and _SAFE_VALUE.fullmatch(item)):
                    return True
            pending.extend((item,depth+1) for item in current.values())
        elif isinstance(current,(list,tuple)):
            pending.extend((item,depth+1) for item in current)
    return False
