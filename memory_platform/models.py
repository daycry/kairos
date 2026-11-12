"""Strict request and response types matching the reviewed API contract."""
from typing import Any, Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Error(Model):
    error: dict[str, Any]
    request_id: str

class Source(Model):
    uri: Annotated[str, Field(max_length=2000)]
    sha256: Annotated[str, Field(pattern='^[a-f0-9]{64}$')] | None = None
    label: Annotated[str, Field(max_length=300)] | None = None

class ProjectInput(Model):
    id: Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]
    title: Annotated[str, Field(max_length=200)]
    capture_mode: Literal['off', 'summary', 'full'] | None = None
    temporal_projection: bool | None = None

class Policy(Model):
    capture_mode: Literal['off', 'summary', 'full']
    temporal_projection: bool

class Login(Model):
    username: Annotated[str, Field(max_length=128)]
    password: Annotated[str, Field(max_length=1024)]

class CapturePolicy(Model):
    project_id: str
    capture_mode: Literal['off', 'summary', 'full']
    capture_allowed: bool

class WorkStateChange(Model):
    list: Annotated[str, Field(min_length=1, max_length=200)]
    fields: Annotated[dict[str, Any], Field(min_length=1, max_length=32)]
    request_id: Annotated[str, Field(min_length=1, max_length=200)]
    expected_version: Annotated[int, Field(ge=0, le=2_147_483_646)] | None = None

class CorpusSelection(Model):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ''
    query: Annotated[str, Field(max_length=4000)] = ''
    types: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)
    concepts: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)
    files: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)
    date_start: Annotated[str, Field(max_length=100)] | None = None
    date_end: Annotated[str, Field(max_length=100)] | None = None
    limit: Annotated[int, Field(ge=1, le=500)] = 500

class CorpusPrime(Model):
    fresh: bool = False

class CorpusRebuild(Model):
    expected_version: Annotated[int, Field(ge=1, le=2_147_483_646)]
    force: bool = False

class CorpusAnswerRequest(Model):
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    request_id: Annotated[str, Field(min_length=1, max_length=200)]
    expected_session_id: Annotated[str, Field(min_length=1, max_length=200)]
    expected_generation: Annotated[int, Field(ge=1)]

class Actor(Model):
    id: str
    username: str | None = None
    scopes: Annotated[list[Literal['read', 'write', 'admin', 'publish', 'validate']], Field(max_length=100)]
    project_ids: Annotated[list[Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]], Field(max_length=100)]

class Auth(Model):
    actor: Actor
    csrf_token: str

class KeyInput(Model):
    name: Annotated[str, Field(max_length=128)]
    project_ids: Annotated[list[Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]], Field(max_length=100)]
    scopes: Annotated[list[Literal['read', 'write', 'admin', 'publish', 'validate']], Field(max_length=5)]

class UserInput(Model):
    username: Annotated[str, Field(max_length=128)]
    password: Annotated[str, Field(max_length=1024)]
    project_ids: Annotated[list[Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]], Field(max_length=100)]
    scopes: Annotated[list[Literal['read', 'write', 'admin', 'publish', 'validate']], Field(max_length=5)]

class Fact(Model):
    subject: Annotated[str, Field(min_length=1, max_length=300)]
    predicate: Annotated[str, Field(min_length=1, max_length=200)]
    object: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence_quote: Annotated[str, Field(min_length=1, max_length=4000)]
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

class Payload(Model):
    facts: Annotated[list[Fact], Field(max_length=30)] = Field(default_factory=list)
    title: Annotated[str, Field(max_length=500)]
    content: Annotated[str, Field(max_length=100000)]
    category: Annotated[str, Field(max_length=200)] | None = None
    tags: Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=64)] | None = None
    source: Source | None = None
    problem: Annotated[str, Field(max_length=10000)] | None = None
    correction: Annotated[str, Field(max_length=10000)] | None = None
    evidence: Annotated[list[Annotated[str, Field(max_length=4000)]], Field(max_length=20)] | None = None
    validation_status: Literal['observed', 'unverified', 'validated'] | None = None
    supersedes: UUID | None = None

class AutomaticCapture(Model):
    mode: Literal['summary','full']
    hook_event: Literal['SessionStart','SessionEnd','UserPromptSubmit','PostToolUse','PostToolUseFailure','Stop','SubagentStop','PreCompact','PostCompact']
    fingerprint: Annotated[str, Field(pattern='^[a-f0-9]{64}$')]

class Event(Model):
    capture: AutomaticCapture | None = None
    generate: bool = False
    event_id: UUID
    project_id: Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]
    session_id: Annotated[str, Field(max_length=200)]
    agent_id: Annotated[str, Field(max_length=200)]
    event_type: Literal['note', 'summary', 'learning', 'correction', 'session_start', 'session_end', 'delete']
    occurred_at: AwareDatetime
    item_id: UUID
    version: Annotated[int, Field(ge=1)]
    payload: Payload

class Receipt(Model):
    capture_hash: Annotated[str, Field(pattern='^[a-f0-9]{64}$')] | None = None
    redacted: bool | None = None
    extraction: Literal['disabled'] | None = None
    event_id: UUID
    item_id: UUID
    version: int
    status: Literal['accepted', 'duplicate', 'superseded']
    jobs: Annotated[list[str], Field(max_length=20)]

class DocumentValidation(Model):
    status: Literal['validated']
    evidence: Annotated[list[Annotated[str, Field(max_length=4000)]], Field(max_length=20)]
    validated_by: Annotated[str, Field(max_length=200)]

class Document(Model):
    document_id: UUID
    version: Annotated[int, Field(ge=1)]
    title: Annotated[str, Field(max_length=500)]
    content: Annotated[str, Field(max_length=200000)]
    category: Annotated[str, Field(max_length=200)] | None = None
    tags: Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=64)] | None = None
    source: Source
    validation: DocumentValidation

class Search(Model):
    match_mode: Literal['all','any'] = 'all'
    exclude_categories: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)] = []
    semantic: bool = True
    semantic_budget_ms: Annotated[int, Field(strict=True, ge=1, le=600000, description='Optional: milliseconds the semantic layer may take, never more than the configured embeddings query deadline; when it runs out the lexical answer is returned with degraded timeout')] | None = None
    project_ids: Annotated[list[Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]], Field(max_length=20, min_length=1)]
    q: Annotated[str, Field(max_length=4000)]
    layers: Annotated[list[Literal['episodic', 'documental', 'temporal']], Field(max_length=3)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    categories: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)] | None = None
    tags: Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=64)] | None = None

class MatchedChunk(Model):
    """The fragment that answered a semantic hit. Offsets are Unicode code points (not bytes or UTF-16 units) into title + newline + content."""
    ordinal: Annotated[int, Field(ge=0, description='Position of the fragment among those of the resource, from 0')]
    char_start: Annotated[int, Field(ge=0, description='First code point of the fragment (Unicode code points of title + newline + content)')]
    char_end: Annotated[int, Field(ge=1, description='Code point after the last one of the fragment (end-exclusive)')]

class Hit(Model):
    index_status: Literal['pending', 'ready'] | None = None
    ref: str
    layer: Literal['episodic', 'documental', 'temporal']
    project_id: Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]
    item_id: str
    title: str
    excerpt: str
    source: Source | None = None
    validation_status: Literal['observed', 'unverified', 'validated', 'unknown']
    version: Annotated[int, Field(ge=1)]
    category: str | None = None
    tags: Annotated[list[str], Field(max_length=64)] | None = None
    superseded: bool | None = None
    lexical_match: Literal['trigram'] | None = None  # present only on hits added by the trigram fallback (approximate title match)
    matched_chunk: MatchedChunk | None = Field(None, description='Fragment that answered this semantic hit, present only when it is not the whole text; offsets are Unicode code points of title + newline + content')  # present only on semantic hits answered by a fragment that is not the whole text; offsets in Unicode code points of title+newline+content

class Degraded(Model):
    """Present when only the semantic layer fell short of what was asked: the lexical answer is complete and valid, but it is not the hybrid one."""
    layer: Literal['semantic']
    reason: Literal['timeout', 'provider_error', 'store_error', 'no_vectors', 'embeddings_disabled'] = Field(description='timeout: the embeddings query deadline (or the request semantic_budget_ms) ran out; provider_error: the embeddings provider failed; store_error: the database failed while searching vectors (both with status unavailable, partial true); no_vectors: nothing is embedded for these projects; embeddings_disabled: the server runs without embeddings (status off)')

class SearchResult(Model):
    items: Annotated[list[Hit], Field(max_length=100)]
    backends: dict[str, Any]
    partial: bool
    degraded: Degraded | None = Field(None, description='Optional: present only when the semantic layer alone fell short; `partial` keeps its meaning')

class Details(Model):
    refs: Annotated[list[Annotated[str, Field(max_length=4000)]], Field(max_length=20, min_length=1)]
    max_chars: Annotated[int, Field(ge=100, le=32000)] = 16000

class Context(Model):
    match_mode: Literal['all','any'] = 'all'
    exclude_categories: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)] = []
    semantic: bool = True
    semantic_budget_ms: Annotated[int, Field(strict=True, ge=1, le=600000, description='Optional: milliseconds the semantic layer may take, never more than the configured embeddings query deadline; when it runs out the lexical answer is returned with degraded timeout')] | None = None
    project_ids: Annotated[list[Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]], Field(max_length=20, min_length=1)]
    q: Annotated[str, Field(max_length=4000)]
    layers: Annotated[list[Literal['episodic', 'documental', 'temporal']], Field(max_length=3)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    max_chars: Annotated[int, Field(ge=100, le=32000)] = 16000
    categories: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)] | None = None
    tags: Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=64)] | None = None

class Timeline(Model):
    project_ids: Annotated[list[Annotated[str, Field(pattern='^[a-z0-9][a-z0-9_-]{0,63}$')]], Field(min_length=1, max_length=20)]
    anchor_ref: Annotated[str, Field(max_length=4000)] | None = None
    before: AwareDatetime | None = None
    after: AwareDatetime | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20
