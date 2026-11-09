import type { Auth, MemoryEvent, Payload, Receipt } from './memory-types.ts';

const messages: Record<string, string> = {
  unauthorized: 'La sesión ha caducado. Vuelve a entrar.',
  forbidden: 'Tu acceso no permite esta acción.',
  capture_disabled: 'La captura está desactivada. Actívala en la política del proyecto antes de guardar memoria.',
  capture_off: 'La captura está desactivada. Actívala en la política del proyecto antes de guardar memoria.',
  conflict: 'La versión o el identificador ya cambió. Revisa el elemento antes de crear otra versión.',
  corpus_answer_budget_exceeded: 'Se ha alcanzado el presupuesto de admisión de este corpus. Reiniciar la conversación no restablece ese presupuesto.',
  corpus_answer_input_budget: 'La selección y el historial superan el tamaño admitido. Acota las fuentes o empieza una conversación nueva.',
  validation_error: 'Revisa los campos y sus límites antes de volver a enviar.',
  sensitive_source_requires_review: 'Esta corrección o fuente validada contiene datos sensibles. Revisa y retira esos datos antes de crear un nuevo envío.',
};

export class MemoryApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  constructor(status: number, code: string, requestId?: string) {
    const fallback = status === 401 ? messages.unauthorized : status === 403 ? messages.forbidden
      : status === 409 ? messages.conflict : status === 422 || status === 400 ? messages.validation_error
      : status === 503 ? 'El servicio no está disponible. Puedes volver a intentarlo.'
      : status === 0 ? 'No se pudo confirmar la respuesta del servidor. Comprueba la conexión y vuelve a intentar.'
      : 'No se pudo completar la solicitud. Puedes volver a intentarlo.';
    super(messages[code] ?? fallback);
    this.name = 'MemoryApiError'; this.status = status; this.code = code;
    this.requestId = requestId && /^[a-zA-Z0-9_-]{1,100}$/.test(requestId) ? requestId : undefined;
  }
}

/** Session cookie is owned by the browser; the anti-CSRF token exists only in memory. */
export class MemoryApi {
  private csrf = '';
  private readonly fetcher: typeof fetch;
  private readonly base: string;
  constructor(fetcher: typeof fetch = globalThis.fetch.bind(globalThis), base = '/memory-api') { this.fetcher = fetcher; this.base = base; }
  clearSession(): void { this.csrf = ''; }
  async request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    if (!path.startsWith('/v1/')) throw new Error('Unsupported API route');
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET' && this.csrf) headers['X-CSRF-Token'] = this.csrf;
    let response: Response;
    try {
      response = await this.fetcher(`${this.base}${path}`, { method, headers, credentials: 'include', cache: 'no-store',
        body: body === undefined ? undefined : JSON.stringify(body), signal });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error;
      throw new MemoryApiError(0, 'network_error');
    }
    let data: unknown;
    try { data = await response.json(); }
    catch { throw new MemoryApiError(response.ok ? 502 : response.status, 'invalid_response', response.headers.get('X-Request-ID') ?? undefined); }
    if (!response.ok) {
      const envelope = data && typeof data === 'object' ? data as Record<string, unknown> : {};
      const detail = envelope.error && typeof envelope.error === 'object' ? envelope.error as Record<string, unknown> : envelope;
      const requestId = detail.request_id ?? envelope.request_id ?? response.headers.get('X-Request-ID');
      if (response.status === 401) this.clearSession();
      throw new MemoryApiError(response.status, typeof detail.code === 'string' ? detail.code : 'request_failed', typeof requestId === 'string' ? requestId : undefined);
    }
    return data as T;
  }
  async authenticate(username?: string, password?: string, signal?: AbortSignal): Promise<Auth> {
    const result = await this.request<Auth>(username === undefined ? '/v1/auth/me' : '/v1/auth/login', username === undefined ? 'GET' : 'POST',
      username === undefined ? undefined : { username, password }, signal);
    if (!result.actor || !Array.isArray(result.actor.scopes) || typeof result.csrf_token !== 'string') throw new MemoryApiError(502, 'invalid_response');
    this.csrf = result.csrf_token;
    return result;
  }
  async logout(): Promise<void> { await this.request('/v1/auth/logout', 'POST'); this.clearSession(); }
}

/** One line is one value: commas, quotes, Unicode and internal spaces are data. */
export function lines(value: string): string[] { return [...new Set(value.split(/\r?\n/).map(item => item.trim()).filter(Boolean))]; }
export function safeHttpUrl(value: string): string | null {
  try { const url = new URL(value); return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null; }
  catch { return null; }
}
export function can(scopes: readonly string[], scope: string): boolean { return scopes.includes(scope) || scopes.includes('admin'); }

/** Freeze the exact event before transport. A lost response must retry this same object. */
export function createEvent(input: { projectId: string; sessionId: string; agentId: string; type: string; payload: Payload; itemId?: string; version?: number },
  uuid: () => string = () => crypto.randomUUID(), now: () => string = () => new Date().toISOString()): MemoryEvent {
  if (input.itemId && (!Number.isInteger(input.version) || input.version! < 2)) throw new Error('Una actualización necesita la siguiente versión (mínimo 2).');
  if (!input.projectId || !input.sessionId.trim() || !input.agentId.trim()) throw new Error('Selecciona un proyecto e indica sesión y agente.');
  return JSON.parse(JSON.stringify({ event_id: uuid(), item_id: input.itemId || uuid(), version: input.version ?? 1,
    project_id: input.projectId, session_id: input.sessionId.trim(), agent_id: input.agentId.trim(),
    event_type: input.type, occurred_at: now(), payload: input.payload })) as MemoryEvent;
}

export class EventSubmission {
  private event?: MemoryEvent;
  private receipt?: Receipt;
  private running = false;
  get pending(): MemoryEvent | undefined { return this.event; }
  async submit(api: MemoryApi, build: () => MemoryEvent): Promise<Receipt> {
    if (this.running) throw new Error('El envío sigue en curso.');
    if (this.receipt) return this.receipt;
    this.event ??= createSnapshot(build());
    this.running = true;
    try {
      const receipt = await api.request<Receipt>('/v1/events', 'POST', this.event);
      if (receipt.event_id !== this.event.event_id || receipt.item_id !== this.event.item_id || receipt.version !== this.event.version ||
        !['accepted', 'duplicate', 'superseded'].includes(receipt.status) || !Array.isArray(receipt.jobs)) throw new MemoryApiError(502, 'invalid_receipt');
      this.receipt = receipt;
      return receipt;
    } finally { this.running = false; }
  }
}
function createSnapshot(event: MemoryEvent): MemoryEvent { return JSON.parse(JSON.stringify(event)) as MemoryEvent; }

export interface Activity { event_id: string; project_id: string; event_type?: string; ref?: string; created_at?: string }
export interface ActivityOptions {
  projectId: string; signal: AbortSignal; receive: (activity: Activity) => void;
  state: (state: 'connecting' | 'live' | 'reconnecting' | 'stopped', code?: string) => void;
  refreshIdentity: () => Promise<unknown>; factory?: (url: string, init: EventSourceInit) => EventSource;
  initialCursor?: string; saveCursor?: (cursor: string) => void;
}
/** One project, one cookie-authenticated connection. Native reconnects retain Last-Event-ID. */
export class ActivitySubscription {
  private source?: EventSource;
  private cursor = '';
  private generation = 0;
  private disposed = false;
  private seen = new Set<string>();
  private readonly options: ActivityOptions;
  constructor(options: ActivityOptions) { this.options = options; this.cursor = options.initialCursor ?? ''; options.signal.addEventListener('abort', () => this.dispose(), { once: true }); }
  connect(): void {
    if (this.disposed || this.options.signal.aborted) return;
    this.source?.close(); const generation = ++this.generation;
    const query = new URLSearchParams({ project_id: this.options.projectId }); if (this.cursor) query.set('cursor', this.cursor);
    const source = (this.options.factory ?? ((url, init) => new EventSource(url, init)))(`/memory-api/v1/activity?${query}`, { withCredentials: true }); this.source = source;
    let normalEnd = false; let failed = false;
    const current = () => !this.disposed && generation === this.generation && !this.options.signal.aborted;
    this.options.state('connecting');
    source.addEventListener('open', () => { if (current()) { normalEnd = false; this.options.state('live'); } });
    source.addEventListener('activity', event => {
      if (!current()) return; const message = event as MessageEvent;
      try {
        const value = JSON.parse(message.data) as Activity;
        if (value.project_id !== this.options.projectId || typeof value.event_id !== 'string') return;
        if (message.lastEventId) { this.cursor = message.lastEventId; this.options.saveCursor?.(this.cursor); }
        if (this.seen.has(value.event_id)) return; this.seen.add(value.event_id);
        if (this.seen.size > 500) this.seen.delete(this.seen.values().next().value!);
        // Explicitly whitelist metadata. Body or titles accidentally added by a server are discarded.
        this.options.receive({ event_id: value.event_id, project_id: value.project_id,
          event_type: typeof value.event_type === 'string' ? value.event_type : undefined,
          ref: typeof value.ref === 'string' ? value.ref : undefined, created_at: typeof value.created_at === 'string' ? value.created_at : undefined });
      } catch { /* Malformed metadata never enters the UI. */ }
    });
    source.addEventListener('end', () => { if (current()) normalEnd = true; });
    source.addEventListener('error', event => {
      if (!current() || failed) return;
      const message = event as MessageEvent; let code = 'activity_unavailable';
      if (typeof message.data === 'string') { try { const value = JSON.parse(message.data); if (typeof value.error?.code === 'string') code = value.error.code; } catch { /* Public fallback below. */ } }
      else if (normalEnd) { normalEnd = false; this.options.state('reconnecting'); return; }
      failed = true; source.close(); this.options.state('stopped', code);
      // Exactly one identity check per failed connection; no automatic auth retry loop.
      void this.options.refreshIdentity().catch(() => undefined);
    });
  }
  dispose(): void { if (this.disposed) return; this.disposed = true; this.generation++; this.source?.close(); this.source = undefined; }
}

export function mergePages<T extends Record<string, unknown>>(current: T[], incoming: T[], collection: string): T[] {
  const identity = (row: T): string => `${String(row.project_id ?? '')}:${String(collection === 'history' ? row.event_id ?? row.id : collection === 'sessions' ? row.session_id ?? row.id : row.item_id ?? row.id ?? row.job_id ?? row.event_id)}`;
  const result = new Map(current.map(row => [identity(row), row]));
  for (const row of incoming) {
    const key = identity(row); const old = result.get(key);
    if (!old || Number(row.version ?? 0) >= Number(old.version ?? 0)) result.set(key, row);
  }
  return [...result.values()];
}
