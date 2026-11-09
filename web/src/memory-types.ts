export type Scope = 'read' | 'write' | 'admin' | 'publish' | 'validate';
export type Layer = 'episodic' | 'documental' | 'temporal';
export interface Actor { id: string; username?: string; scopes: Scope[]; project_ids: string[] }
export interface Auth { actor: Actor; csrf_token: string }
export interface Project { id: string; title: string; categories?: string[]; capture_mode?: string; counts?: { notes: number; documents: number; sessions: number; jobs: number } }
export interface Policy { capture_mode: 'off' | 'summary' | 'full'; temporal_projection: boolean }
export interface Source { uri: string; label?: string; sha256?: string }
export interface Hit {
  ref: string; layer: Layer; project_id: string; item_id: string; title: string;
  excerpt: string; version: number; validation_status: string; source?: Source;
  category?: string; tags?: string[]; superseded?: boolean; content?: string;
  evidence?: string[]; problem?: string; correction?: string;
}
export interface SearchInput { project_ids: string[]; q: string; layers: Layer[]; categories: string[]; tags: string[]; limit: number }
export interface SearchResult { items: Hit[]; backends: Record<string, { status?: string; [key: string]: unknown }>; partial: boolean }
export interface ContextResult extends SearchResult { context?: string; warnings?: string[]; max_chars?: number }
export interface Payload {
  title: string; content: string; category?: string; tags?: string[]; source?: Source;
  problem?: string; correction?: string; evidence?: string[];
  validation_status?: string; supersedes?: string;
}
export interface MemoryEvent {
  event_id: string; project_id: string; session_id: string; agent_id: string;
  event_type: string; occurred_at: string; item_id: string; version: number; payload: Payload;
}
export interface Receipt { event_id: string; item_id: string; version: number; status: 'accepted' | 'duplicate' | 'superseded'; jobs: string[]; redacted?: boolean }
export type Row = Record<string, unknown>;
