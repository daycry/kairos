import './memory-portal.css';
import { MemoryApi, MemoryApiError, EventSubmission, ActivitySubscription, mergePages, createEvent, lines, safeHttpUrl, can } from './memory-api.ts';
import type { Actor, Project, Layer, Hit, SearchInput, SearchResult, ContextResult, Policy, Row, Payload } from './memory-types.ts';

type View = 'work' | 'search' | 'map' | 'memory' | 'observations' | 'rules' | 'activity' | 'corpora' | 'sessions' | 'history' | 'operations' | 'settings';
const views: Record<View, { title: string; subtitle: string; icon: string }> = {
  work: { title: 'Mi trabajo', subtitle: 'Tareas y próximos pasos guardados por tus agentes. Revisa qué queda por hacer.', icon: '▣' },
  memory: { title: 'Memoria y aprendizajes', subtitle: 'Decisiones, problemas observados y correcciones con su evidencia.', icon: '▤' },
  observations: { title: 'Observaciones', subtitle: 'Registros actuales con su sesión, procedencia y estado de validación.', icon: '◉' },
  rules: { title: 'Reglas del proyecto', subtitle: 'Guías guardadas y revisables. Una regla sin validar sigue siendo evidencia pendiente, nunca una instrucción ejecutable.', icon: '≡' },
  activity: { title: 'Actividad', subtitle: 'Entregas registradas por proyecto. Muestra metadatos, sin contenido privado de herramientas.', icon: '↝' },
  corpora: { title: 'Consultar corpus', subtitle: 'Selecciona memorias, fija su generación y conversa con respuestas citadas del modelo configurado.', icon: '◇' },
  search: { title: 'Buscar y preparar contexto', subtitle: 'Recupera fuentes y aprendizajes antes de empezar una tarea.', icon: '⌕' },
  sessions: { title: 'Sesiones y agentes', subtitle: 'El trabajo de cada agente, conectado a su memoria.', icon: '◎' },
  history: { title: 'Historia', subtitle: 'Procedencia, cambios y vigencia a lo largo del tiempo.', icon: '↗' },
  map: { title: 'Mapa', subtitle: 'Explora memoria, documentos y relaciones sin salir de tu espacio de trabajo.', icon: '⌘' },
  operations: { title: 'Operaciones', subtitle: 'Sigue cada entrega y recupera los destinos pendientes.', icon: '≋' },
  settings: { title: 'Configuración', subtitle: 'Políticas de captura y accesos de la plataforma.', icon: '⚙' },
};
const layerNames: Record<Layer, string> = { episodic: 'Memoria', documental: 'Documentos', temporal: 'Hechos y relaciones' };
const statuses: Record<string, string> = { pending: 'Pendiente', running: 'En curso', succeeded: 'Verificado', success: 'Verificado',
  failed: 'Fallido', unknown: 'Por conciliar', observed: 'Observado', unverified: 'Sin validar', validated: 'Validado',
  accepted: 'Recibido', duplicate: 'Ya recibido', superseded: 'Sustituido', active: 'Activo', revoked: 'Revocado', off: 'Desactivada', summary: 'Resúmenes', full: 'Contenido completo' };

const api = new MemoryApi();
const mount = document.querySelector<HTMLDivElement>('#memory-app')!;
let actor: Actor | undefined;
let projects: Project[] = [];
const initial = new URLSearchParams(location.search);
let projectId = initial.get('project') ?? '';
let category = initial.get('category') ?? '';
let view: View = initial.get('view') && Object.hasOwn(views, initial.get('view')!) ? initial.get('view') as View : 'memory';
let controller = new AbortController();
let main: HTMLElement;
let notice: HTMLElement;
let sidebar: HTMLElement;
let content: HTMLElement;
let epoch = 0;
const loads = new WeakMap<HTMLElement, AbortController>();
const activityCursors = new Map<string, string>();
let refreshLiveMemory: ((manual?: boolean) => Promise<boolean>) | undefined;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text?: string): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function button(text: string, action?: () => void, className = 'button'): HTMLButtonElement {
  const b = el('button', className, text); b.type = 'button'; if (action) b.addEventListener('click', action); return b;
}
function link(text: string, href: string, className = ''): HTMLAnchorElement { const a = el('a', className, text); a.href = href; return a; }
function brand(home = false): HTMLElement {
  const box = home ? link('', '/', 'wordmark') : el('div', 'wordmark');
  const icon = el('img'); icon.src = '/brand/kairos-mark.svg'; icon.alt = ''; icon.width = 34; icon.height = 34;
  box.append(icon, el('span', '', 'Kairos'));
  if (home) box.setAttribute('aria-label', 'Kairos, inicio');
  return box;
}
function badge(value: string, prefix = ''): HTMLElement {
  const span = el('span', 'badge'); span.dataset.status = value; span.textContent = `${prefix}${statuses[value] ?? value}`; return span;
}
function text(value: unknown, fallback = ''): string { return typeof value === 'string' || typeof value === 'number' ? String(value) : fallback; }
function list(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []; }
function date(value: unknown): string {
  const raw = text(value); const d = new Date(raw); return raw && !Number.isNaN(d.getTime()) ? new Intl.DateTimeFormat('es', { dateStyle: 'medium', timeStyle: 'short' }).format(d) : 'Fecha no disponible';
}
function payload(row: Row): Row {
  const body = row.body && typeof row.body === 'object' ? { ...row, ...row.body as Row } : row;
  return body.payload && typeof body.payload === 'object' ? { ...body, ...body.payload as Row } : body;
}
function rows(result: { items: Row[] }): Row[] { if (!Array.isArray(result.items)) throw new MemoryApiError(502, 'invalid_response'); return result.items; }
function scope(): string[] { return projectId ? [projectId] : projects.map(p => p.id); }
function has(permission: string): boolean { return !!actor && can(actor.scopes, permission); }
function admin(): boolean { return !!actor?.scopes.includes('admin'); }
function announce(message: string): void { notice.textContent = message; }
function formatError(error: unknown): string {
  if (error instanceof MemoryApiError) return `${error.message}${error.requestId ? ` Referencia: ${error.requestId}.` : ''}`;
  return error instanceof Error && !(error instanceof TypeError) ? error.message : 'No se pudo completar la acción. Vuelve a intentarlo.';
}
function failure(target: HTMLElement, error: unknown, retry?: () => void): void {
  target.replaceChildren(); const box = el('div', 'state error'); box.append(el('strong', '', 'No se pudo cargar'), el('p', '', formatError(error)));
  if (retry) box.append(button('Volver a intentar', retry, 'button secondary'));
  if (error instanceof MemoryApiError && error.status === 401) box.append(button('Volver a entrar', () => { actor = undefined; showLogin(); }, 'button secondary'));
  target.append(box); announce(formatError(error));
}
function empty(target: HTMLElement, title: string, message: string): void {
  const box = el('div', 'state empty'); box.append(el('span', 'empty-symbol', '◌'), el('h3', '', title), el('p', '', message)); target.append(box);
}
function panel(title: string, description?: string): HTMLElement {
  const p = el('section', 'panel'); p.append(el('h2', '', title)); if (description) p.append(el('p', 'muted', description)); return p;
}
function field(form: HTMLElement, label: string, options: { name: string; value?: string; type?: string; required?: boolean; max?: number; hint?: string; multiline?: boolean; choices?: [string, string][] } ): HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement {
  const wrapper = el('div', 'field'); const id = `field-${crypto.randomUUID()}`; const lab = el('label', '', label); lab.htmlFor = id;
  const input = options.choices ? el('select') : options.multiline ? el('textarea') : el('input'); input.id = id; input.name = options.name;
  if (input instanceof HTMLInputElement) input.type = options.type ?? 'text';
  if (input instanceof HTMLSelectElement) for (const [value, labelText] of options.choices!) { const option = el('option', '', labelText); option.value = value; input.append(option); }
  input.value = options.value ?? ''; input.required = !!options.required;
  if (options.max && !(input instanceof HTMLSelectElement)) input.maxLength = options.max;
  if (input instanceof HTMLTextAreaElement) input.rows = 4;
  wrapper.append(lab, input);
  if (options.hint) { const hint = el('p', 'hint', options.hint); hint.id = `${id}-hint`; input.setAttribute('aria-describedby', hint.id); wrapper.append(hint); }
  form.append(wrapper); return input;
}
function check(parent: HTMLElement, label: string, checked = false): HTMLInputElement {
  const lab = el('label', 'check'); const input = el('input'); input.type = 'checkbox'; input.checked = checked; lab.append(input, el('span', '', label)); parent.append(lab); return input;
}
function submitButton(form: HTMLFormElement, label: string): HTMLButtonElement { const b = button(label); b.type = 'submit'; form.append(b); return b; }
function formError(form: HTMLElement): HTMLElement { const p = el('p', 'form-status'); p.setAttribute('role', 'status'); form.append(p); return p; }
function selectedProjects(parent: HTMLElement): () => string[] {
  const f = el('fieldset', 'selection'); f.append(el('legend', '', 'Proyectos permitidos'));
  const fields = projects.map(project => ({ id: project.id, input: check(f, project.title, project.id === projectId) })); parent.append(f);
  return () => fields.filter(item => item.input.checked).map(item => item.id);
}
function selectedScopes(parent: HTMLElement): () => string[] {
  const f = el('fieldset', 'selection'); f.append(el('legend', '', 'Permisos'));
  const labels = [['read', 'Consultar'], ['write', 'Capturar memoria'], ['publish', 'Publicar documentos'], ['validate', 'Validar aprendizajes'], ['admin', 'Administrar']] as const;
  const fields = labels.map(([id, label]) => ({ id, input: check(f, label, id === 'read') })); parent.append(f);
  return () => fields.filter(item => item.input.checked).map(item => item.id);
}

async function boot(): Promise<void> {
  mount.replaceChildren(el('p', 'boot-status', 'Comprobando tu sesión…'));
  try { actor = (await api.authenticate()).actor; await loadProjects(); shell(); }
  catch (error) { showLogin(error instanceof MemoryApiError && error.status === 401 ? undefined : error); }
  finally { mount.setAttribute('aria-busy', 'false'); }
}
async function loadProjects(): Promise<void> {
  const result = await api.request<{ projects: Project[] }>('/v1/projects');
  if (!Array.isArray(result.projects)) throw new MemoryApiError(502, 'invalid_response');
  projects = result.projects;
  if (!projects.some(p => p.id === projectId)) projectId = '';
}
function showLogin(error?: unknown): void {
  controller.abort(); activityCursors.clear(); document.querySelectorAll('dialog').forEach(d => d.remove());
  mount.replaceChildren(); const screen = el('main', 'login-screen'); screen.id = 'main';
  const story = el('section', 'login-story'); story.append(brand(), el('span', 'eyebrow', 'CONTINUIDAD PARA TU TRABAJO'),
    el('h1', '', 'El siguiente paso empieza con lo aprendido.'), el('p', '', 'Memoria de agentes, fuentes documentales e historia. Un lugar para recuperar contexto, revisar evidencia y evitar repetir errores.'));
  const layers = el('div', 'login-layers'); for (const [name, desc] of [['01 · Memoria', 'Decisiones y aprendizajes'], ['02 · Documentos', 'Conocimiento con fuentes'], ['03 · Historia', 'Cambios y vigencia']]) { const row = el('div'); row.append(el('strong', '', name), el('span', '', desc)); layers.append(row); } story.append(layers);
  const box = el('section', 'login-box'); box.append(el('span', 'eyebrow', 'ESPACIO PRIVADO'), el('h2', '', 'Entra a tu memoria'), el('p', 'muted', 'Usa el acceso que te ha facilitado el administrador.'));
  const form = el('form'); const username = field(form, 'Usuario', { name: 'username', required: true, max: 128 }) as HTMLInputElement;
  username.autocomplete = 'username'; const password = field(form, 'Contraseña', { name: 'password', type: 'password', required: true, max: 1024 }) as HTMLInputElement; password.autocomplete = 'current-password';
  const status = formError(form); const send = submitButton(form, 'Entrar');
  if (error) status.textContent = formatError(error);
  form.addEventListener('submit', async e => { e.preventDefault(); send.disabled = true; status.textContent = 'Entrando…';
    try { actor = (await api.authenticate(username.value, password.value)).actor; password.value = ''; await loadProjects(); shell(); }
    catch (err) { status.textContent = formatError(err); }
    finally { send.disabled = false; }
  });
  box.append(form, el('p', 'hint', 'Tu sesión se conserva de forma segura en este navegador. Las claves para agentes se gestionan dentro del portal.'));
  screen.append(story, box); mount.append(screen); username.focus(); document.title = 'Entrar · Kairos';
}

function shell(): void {
  mount.replaceChildren(); const layout = el('div', 'layout');
  sidebar = el('aside', 'sidebar'); sidebar.id = 'sidebar'; sidebar.append(brand(true), el('p', 'workspace-label', 'CONTINUIDAD PARA TUS AGENTES'));
  const nav = el('nav', 'navigation'); nav.setAttribute('aria-label', 'Vistas de memoria');
  for (const [id, meta] of Object.entries(views)) {
    const b = button('', () => navigate(id as View), 'nav-item'); b.dataset.view = id;
    const icon = el('span', 'nav-icon', meta.icon); icon.setAttribute('aria-hidden', 'true'); b.append(icon, el('span', '', id === 'search' ? 'Buscar y contexto' : meta.title)); nav.append(b);
  }
  sidebar.append(nav); const scopeBox = el('section', 'project-section'); scopeBox.append(el('h2', '', 'Proyectos'));
  const projectSearch = field(scopeBox, 'Filtrar proyectos', { name: 'project-filter', type: 'search' });
  const projectList = el('div', 'project-list');
  const renderProjects = () => {
    projectList.replaceChildren(); const all = button('Todos los proyectos autorizados', () => selectProject(''), 'project-item'); all.setAttribute('aria-pressed', String(!projectId)); projectList.append(all);
    const term = projectSearch.value.toLocaleLowerCase();
    for (const p of projects.filter(p => `${p.title} ${p.id}`.toLocaleLowerCase().includes(term))) {
      const details = el('details', 'project-tree'); details.open = p.id === projectId;
      const summary = el('summary', '', p.title); summary.title = p.id; details.append(summary);
      const choose = button('Todo el proyecto', () => selectProject(p.id), 'project-item'); choose.setAttribute('aria-pressed', String(p.id === projectId && !category)); details.append(choose);
      for (const cat of p.categories ?? []) { const b = button(cat, () => selectProject(p.id, cat), 'category-item'); b.setAttribute('aria-pressed', String(p.id === projectId && cat === category)); details.append(b); }
      projectList.append(details);
    }
    if (!projects.length) projectList.append(el('p', 'hint', 'No tienes proyectos asignados.'));
  };
  projectSearch.addEventListener('input', renderProjects); renderProjects(); scopeBox.append(projectList); sidebar.append(scopeBox);
  const foot = el('div', 'sidebar-footer'); foot.append(el('p', 'hint', 'Memoria, fuentes y mapa en un único espacio.')); sidebar.append(foot);
  const area = el('div', 'workspace'); const top = el('header', 'topbar');
  const menu = button('Menú', () => { const open = layout.classList.toggle('sidebar-open'); menu.setAttribute('aria-expanded', String(open)); }, 'button secondary menu-button'); menu.setAttribute('aria-controls', 'sidebar'); menu.setAttribute('aria-expanded', 'false');
  const identity = el('div', 'identity'); identity.append(el('span', 'avatar', (actor?.username ?? actor?.id ?? 'U').slice(0, 1).toUpperCase()), el('span', '', actor?.username ?? 'Usuario'));
  const logout = button('Salir', async () => { logout.disabled = true; controller.abort(); try { await api.logout(); actor = undefined; activityCursors.clear(); showLogin(); } catch (e) { announce(formatError(e)); logout.disabled = false; renderView(false); } }, 'button quiet');
  top.append(menu, el('span', 'topbar-label', 'TU ESPACIO DE TRABAJO'), identity, logout);
  main = el('main', 'main'); main.id = 'main'; main.tabIndex = -1;
  notice = el('div', 'live-status'); notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite');
  area.append(top, notice, main); layout.append(sidebar, area); mount.append(layout); renderView(false);
}
function selectProject(id: string, cat = ''): void { projectId = id; category = cat; writeUrl(); shell(); main.focus(); }
function writeUrl(): void {
  const p = new URLSearchParams(); p.set('view', view); if (projectId) p.set('project', projectId); if (category) p.set('category', category);
  history.pushState(null, '', `${location.pathname}?${p}`);
}
function navigate(next: View): void { view = next; writeUrl(); renderView(); document.querySelector('.layout')?.classList.remove('sidebar-open'); }
function renderView(focus = true): void {
  controller.abort(); controller = new AbortController(); epoch++; refreshLiveMemory = undefined; main.replaceChildren();
  sidebar.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(b => b.setAttribute('aria-current', b.dataset.view === view ? 'page' : 'false'));
  const heading = el('div', 'page-heading'); const textBox = el('div'); const current = projects.find(p => p.id === projectId);
  textBox.append(el('span', 'eyebrow', `${current?.title ?? 'TODOS LOS PROYECTOS'}${category ? ` / ${category}` : ''}`), el('h1', '', views[view].title), el('p', 'muted', views[view].subtitle)); heading.append(textBox);
  if (projects.length) {
    const actions = el('div', 'heading-actions');
    if (has('publish') && has('validate')) actions.append(button('Publicar documento', () => publishDialog(), 'button secondary'));
    if (has('write')) actions.append(button(view === 'rules' ? '＋ Nueva regla' : '＋ Nueva memoria', () => memoryDialog(undefined, view === 'rules'), 'button primary'));
    if (actions.childNodes.length) heading.append(actions);
  }
  main.append(heading);
  if (view === 'search') {
    const selected = projects.filter(p => !projectId || p.id === projectId);
    if (selected.length && selected.every(p => p.counts)) {
      const counters = el('div', 'counters'); counters.setAttribute('aria-label', 'Contenido gestionado por la plataforma');
      for (const [key, label] of [['notes', 'Memorias'], ['documents', 'Documentos gestionados'], ['sessions', 'Sesiones'], ['jobs', 'Operaciones']] as const) {
        const counter = el('div', 'counter'); counter.append(el('strong', '', selected.reduce((n, p) => n + p.counts![key], 0).toLocaleString('es')), el('span', '', label)); counters.append(counter);
      }
      main.append(counters, el('p', 'hint counter-hint', 'Recuento del contenido gestionado. Las fuentes externas se consultan al buscar y no están incluidas en estas cifras.'));
    }
  }
  content = el('div', 'view-content'); main.append(content); document.title = `${views[view].title} · Kairos`;
  if (projectId) activityView();
  if (focus) main.focus();
  if (!projects.length && view !== 'settings') {
    empty(content, 'Empieza con un proyecto', admin() ? 'Crea un proyecto en Configuración. La captura empieza desactivada.' : 'Pide al administrador acceso a un proyecto para consultar su memoria.');
    if (admin()) content.append(button('Crear proyecto', () => navigate('settings'))); return;
  }
  if (view === 'search') searchView();
  else if (view === 'map') mapView();
  else if (view === 'settings') settingsView();
  else if (view === 'corpora') {
    const signal = controller.signal;
    void import('./corpus-panel.ts').then(({ mountCorpusPanel }) => {
      if (!signal.aborted) mountCorpusPanel({ target: content, api, projects: projects.filter(p => !projectId || p.id === projectId), signal, writable: has('write'), category });
    }).catch(error => { if (!signal.aborted) failure(content, error); });
  }
  else if (view === 'work') {
    const signal = controller.signal;
    void import('./work-board.ts').then(({ mountWorkBoard }) => {
      if (!signal.aborted) mountWorkBoard({ target: content, api, projects: projects.filter(p => !projectId || p.id === projectId), signal, writable: has('write'), announce, category });
    }).catch(error => { if (!signal.aborted) failure(content, error); });
  }
  else listView(view);
}
function activityView(): void {
  const signal = controller.signal; const selected = projectId;
  const bar = el('section', 'activity-bar'); bar.setAttribute('aria-label', 'Actividad en vivo');
  const status = el('span', 'hint', 'Conectando actividad en vivo…'); const news = el('span', 'activity-news');
  news.setAttribute('role', 'status'); const update = button('Actualizar vista', () => { if (refreshLiveMemory) refreshLiveMemory(true); else renderView(false); }, 'button secondary'); update.hidden = true;
  const reconnect = button('Reconectar actividad', () => { try { feed.connect(); reconnect.hidden = true; } catch { status.textContent = 'La actividad en vivo no está disponible en este navegador.'; } }, 'button secondary'); reconnect.hidden = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const feed = new ActivitySubscription({ projectId: selected, signal, initialCursor: activityCursors.get(selected), saveCursor: cursor => activityCursors.set(selected, cursor),
    // Checking stream access must not renew the CSRF token underneath an
    // in-flight form submission. This authenticated read rechecks the session.
    refreshIdentity: () => api.request('/v1/projects', 'GET', undefined, signal),
    state: (value, code) => { if (signal.aborted) return; status.textContent = value === 'live' ? 'Actividad en vivo conectada' : value === 'connecting' ? 'Conectando actividad en vivo…' : value === 'reconnecting' ? 'Reconectando actividad…' : code === 'unauthorized' || code === 'forbidden' || code === 'not_found' ? 'Se ha detenido la actividad. Revisa tu sesión o el acceso al proyecto.' : 'La actividad está desconectada. Puedes reconectarla.'; reconnect.hidden = value !== 'stopped'; },
    receive: () => { if (signal.aborted) return; news.textContent = 'Hay actividad nueva'; update.hidden = false;
      if (refreshLiveMemory) { if (timer) clearTimeout(timer); timer = setTimeout(async () => {
        if (signal.aborted) return; news.textContent = 'Hay actividad nueva. Actualizando memoria…';
        const updated = await refreshLiveMemory?.(); if (signal.aborted) return;
        news.textContent = updated ? 'Memoria actualizada con la actividad recibida' : 'Hay actividad nueva. Vuelve a actualizar la lista.'; update.hidden = !!updated;
      }, 250); }
    } });
  signal.addEventListener('abort', () => { if (timer) clearTimeout(timer); }, { once: true });
  bar.append(status, news, update, reconnect); main.insertBefore(bar, content);
  try { feed.connect(); } catch { status.textContent = 'La actividad en vivo no está disponible en este navegador.'; reconnect.hidden = false; }
}
function mapView(): void {
  const form = el('form', 'panel'); const query = field(form, 'Buscar en el mapa', { name: 'map-query', type: 'search', max: 4000, hint: 'Opcional. El proyecto y la categoría seleccionados en la barra lateral delimitan el mapa.' });
  const layerField = el('fieldset', 'layers'); layerField.append(el('legend', '', 'Contenido del mapa'));
  const layers = (Object.keys(layerNames) as Layer[]).map(layer => ({ layer, input: check(layerField, layerNames[layer], true) }));
  form.append(layerField); const tags = field(form, 'Etiquetas del mapa', { name: 'map-tags', multiline: true, hint: 'Una etiqueta por línea. Puedes dejarlo vacío para incluir todas.' });
  submitButton(form, 'Aplicar al mapa'); const target = el('section', 'memory-map'); target.setAttribute('aria-label', 'Mapa del conocimiento'); content.append(form, target);
  const viewSignal = controller.signal; let mapController: AbortController | undefined; let generation = 0;
  viewSignal.addEventListener('abort', () => mapController?.abort(), { once: true });
  const draw = async () => {
    mapController?.abort(); mapController = new AbortController(); const signal = mapController.signal; const current = ++generation;
    const input: SearchInput = { project_ids: scope(), q: query.value, layers: layers.filter(l => l.input.checked).map(l => l.layer), categories: category ? [category] : [], tags: lines(tags.value), limit: 100 };
    if (!input.layers.length) { failure(target, new Error('Selecciona al menos una capa para el mapa.')); return; }
    if (input.project_ids.length > 20) { failure(target, new Error('Selecciona un proyecto de la barra lateral para acotar el mapa.')); return; }
    target.replaceChildren(el('p', 'loading', 'Preparando el mapa integrado…'));
    try {
      const { mountMemoryMap } = await import('./memory-map.ts');
      if (viewSignal.aborted || signal.aborted || current !== generation) return;
      mountMemoryMap({ target, api, input, signal, announce, openSource: node => {
        if (!node.ref) return;
        detailsDialog({ ref: node.ref, item_id: node.id, title: node.name, project_id: node.project_id,
          layer: node.type === 'document' ? 'documental' : node.type === 'memory' ? 'episodic' : 'temporal', excerpt: '', version: 0,
          validation_status: node.validation_status ?? 'unknown', source: node.source });
      } });
    } catch (error) { if (!signal.aborted && !viewSignal.aborted) failure(target, error, () => void draw()); }
  };
  form.addEventListener('submit', event => { event.preventDefault(); void draw(); }); void draw();
}
async function load(target: HTMLElement, action: (signal: AbortSignal) => Promise<void>, retry: () => void): Promise<void> {
  loads.get(target)?.abort(); const local = new AbortController(); loads.set(target, local);
  const viewSignal = controller.signal; const abort = () => local.abort(); viewSignal.addEventListener('abort', abort, { once: true });
  const signal = local.signal; const generation = epoch; target.setAttribute('aria-busy', 'true'); target.replaceChildren(el('p', 'loading', 'Cargando…'));
  try { await action(signal); }
  catch (error) { if (!signal.aborted && generation === epoch) failure(target, error, retry); }
  finally { viewSignal.removeEventListener('abort', abort); if (generation === epoch && loads.get(target) === local) target.setAttribute('aria-busy', 'false'); }
}

function searchView(): void {
  const form = el('form', 'search-panel panel'); const searchLine = el('div', 'search-line');
  const query = field(searchLine, '¿Qué necesitas resolver?', { name: 'q', type: 'search', max: 4000, required: true, hint: 'Describe la tarea, una decisión o el problema que quieres evitar.' });
  const go = submitButton(form, 'Buscar'); searchLine.append(go); form.prepend(searchLine);
  const filters = el('div', 'search-filters'); const layerField = el('fieldset', 'layers'); layerField.append(el('legend', '', 'Capas de conocimiento'));
  const chosen = (Object.keys(layerNames) as Layer[]).map(layer => ({ layer, input: check(layerField, layerNames[layer], true) })); filters.append(layerField);
  const details = el('details', 'advanced-filters'); details.append(el('summary', '', 'Categoría y etiquetas'));
  const cat = field(details, 'Categoría', { name: 'category', value: category, max: 200 });
  const tags = field(details, 'Etiquetas', { name: 'tags', multiline: true, hint: 'Una etiqueta por línea. Las comas y las comillas forman parte de la etiqueta.' }); filters.append(details); form.append(filters);
  const actions = el('div', 'search-actions'); const contextButton = button('Preparar contexto para la tarea', () => { if (form.reportValidity()) void run(true); }, 'button secondary');
  const reset = button('Limpiar filtros', () => { query.value = ''; cat.value = ''; tags.value = ''; chosen.forEach(c => c.input.checked = true); result.replaceChildren(); empty(result, 'Busca en tu conocimiento', 'Consulta las tres capas o prepara un contexto acotado para tu siguiente tarea.'); query.focus(); }, 'button quiet'); actions.append(contextButton, reset); form.append(actions);
  const result = el('section', 'results'); result.setAttribute('aria-label', 'Resultados de recuperación'); content.append(form, result);
  empty(result, 'Conecta la tarea con lo que ya sabes', 'Busca memoria, documentos y hechos temporales. Cada resultado conserva su origen y su estado de validación.');
  let searchController: AbortController | undefined; let request = 0;
  controller.signal.addEventListener('abort', () => searchController?.abort(), { once: true });
  const run = async (contextMode: boolean) => {
    searchController?.abort(); searchController = new AbortController(); const signal = searchController.signal; const requestId = ++request;
    const input: SearchInput = { project_ids: scope(), q: query.value, layers: chosen.filter(c => c.input.checked).map(c => c.layer), categories: cat.value ? [cat.value] : [], tags: lines(tags.value), limit: 20 };
    if (!input.layers.length) { result.replaceChildren(); failure(result, new Error('Selecciona al menos una capa de conocimiento.')); return; }
    result.setAttribute('aria-busy', 'true'); result.replaceChildren(el('p', 'loading', contextMode ? 'Preparando contexto con fuentes…' : 'Buscando en las capas seleccionadas…'));
    go.disabled = true; contextButton.disabled = true;
    try {
      const response = await api.request<SearchResult | ContextResult>(contextMode ? '/v1/context' : '/v1/search', 'POST', contextMode ? { ...input, max_chars: 12000 } : input, signal);
      if (signal.aborted || requestId !== request) return;
      if (!Array.isArray(response.items)) throw new MemoryApiError(502, 'invalid_response');
      result.replaceChildren(); const summary = el('div', 'results-heading'); summary.append(el('h2', '', contextMode ? 'Contexto para tu tarea' : 'Fuentes recuperadas'), el('span', 'result-count', `${response.items.length} resultados recibidos`)); result.append(summary);
      backendStatus(result, response.backends, response.partial);
      if (contextMode) {
        const responseContext = response as ContextResult;
        const advice = el('div', 'callout'); advice.append(el('strong', '', 'Comprueba la evidencia antes de aplicar un aprendizaje'), el('p', '', 'Observado y sin validar describen experiencias, no reglas aprobadas. Una corrección puede sustituir información anterior.'));
        for (const warning of responseContext.warnings ?? []) advice.append(el('p', '', warning)); result.append(advice);
        if (responseContext.context) { const contextBox = el('section', 'context-text panel'); contextBox.append(el('h3', '', 'Contexto recuperado'), el('pre', 'prose', responseContext.context)); result.append(contextBox); }
      }
      if (!response.items.length) empty(result, 'No hay coincidencias', 'Prueba otra descripción, amplía las capas o revisa el proyecto seleccionado.');
      else for (const hit of response.items) result.append(hitCard(hit));
      announce(`${response.items.length} resultados${response.partial ? '. Hay capas no disponibles.' : '.'}`);
    } catch (e) { if (!signal.aborted) failure(result, e, () => void run(contextMode)); }
    finally { if (requestId === request) { go.disabled = false; contextButton.disabled = false; result.setAttribute('aria-busy', 'false'); } }
  };
  form.addEventListener('submit', e => { e.preventDefault(); void run(false); });
}
function backendStatus(parent: HTMLElement, backends: SearchResult['backends'] = {}, partial = false): void {
  const row = el('div', 'backend-status');
  for (const [name, value] of Object.entries(backends ?? {})) row.append(badge(text(value.status, 'unknown'), `${layerNames[name as Layer] ?? name}: `));
  if (partial) row.append(el('span', 'partial-label', 'Resultados parciales · alguna capa no ha respondido')); if (row.childNodes.length) parent.append(row);
}
function source(parent: HTMLElement, sourceValue: unknown): void {
  if (!sourceValue || typeof sourceValue !== 'object') return;
  const s = sourceValue as Row; const uri = text(s.uri); if (!uri) return;
  const row = el('p', 'source-line'); row.append(el('span', 'muted', 'Fuente: ')); const url = safeHttpUrl(uri);
  if (url) { const a = link(text(s.label, uri), url); a.target = '_blank'; a.rel = 'noopener noreferrer'; row.append(a); }
  else row.append(el('span', '', text(s.label, uri)));
  if (s.sha256) row.append(el('span', 'source-hash', ` · SHA-256 ${text(s.sha256)}`)); parent.append(row);
}
function hitCard(hit: Hit): HTMLElement {
  const card = el('article', 'result-card'); const meta = el('div', 'card-meta'); meta.append(badge(hit.layer, layerNames[hit.layer] ? '' : 'Capa: ')); meta.firstElementChild!.textContent = layerNames[hit.layer] ?? hit.layer;
  meta.append(el('span', '', projects.find(p => p.id === hit.project_id)?.title ?? hit.project_id), badge(hit.validation_status), el('span', '', `Versión ${hit.version}`)); if (hit.superseded) meta.append(badge('superseded')); card.append(meta);
  const title = el('h3'); title.append(button(hit.title || 'Sin título', () => detailsDialog(hit), 'title-button')); card.append(title, el('p', 'excerpt', hit.excerpt));
  if (hit.category || hit.tags?.length) { const tags = el('div', 'tags'); if (hit.category) tags.append(el('span', 'category-label', hit.category)); for (const tag of hit.tags ?? []) tags.append(el('span', 'tag', tag)); card.append(tags); }
  source(card, hit.source); return card;
}
function dialog(title: string, subtitle?: string): { dialog: HTMLDialogElement; body: HTMLElement; status: HTMLElement } {
  const d = el('dialog', 'dialog'); const top = el('header', 'dialog-heading'); const heading = el('h2', '', title); heading.id = `dialog-${crypto.randomUUID()}`; d.setAttribute('aria-labelledby', heading.id);
  top.append(heading, button('Cerrar', () => { const event = new Event('cancel', { cancelable: true }); if (d.dispatchEvent(event)) d.close(); }, 'button quiet')); const body = el('div', 'dialog-body'); if (subtitle) body.append(el('p', 'muted', subtitle)); const status = el('p', 'form-status'); status.setAttribute('role', 'status');
  d.append(top, body, status); document.body.append(d); const trigger = document.activeElement as HTMLElement | null;
  d.addEventListener('close', () => { d.remove(); trigger?.focus(); }, { once: true }); d.showModal(); return { dialog: d, body, status };
}
function detailsDialog(hit: Hit): void {
  const { dialog: d, body } = dialog(hit.title || 'Detalle de la fuente'); const abort = new AbortController(); d.addEventListener('close', () => abort.abort(), { once: true });
  const retrieve = async () => {
    body.replaceChildren(el('p', 'loading', 'Abriendo la fuente…'));
    try {
      const response = await api.request<{ items: Row[]; truncated?: boolean }>('/v1/details', 'POST', { refs: [hit.ref], max_chars: 16000 }, abort.signal);
      if (abort.signal.aborted) return; body.replaceChildren(); const items = rows(response);
      if (!items.length) { empty(body, 'Fuente no disponible', 'Puede haber cambiado de versión o haber sido retirada. Vuelve a buscar.'); return; }
      for (const raw of items) { const item = payload(raw); body.append(badge(text(item.validation_status, hit.validation_status)), el('p', 'hint', `${text(item.project_id, hit.project_id)} · Versión ${text(item.version, String(hit.version))}`));
        if (item.superseded) body.append(el('p', 'callout', 'Esta versión fue sustituida. Consulta la corrección vigente antes de aplicarla.'));
        for (const [key, label] of [['problem', 'Problema observado'], ['correction', 'Corrección'], ['content', 'Contenido']] as const) if (item[key]) body.append(el('h3', '', label), el('pre', 'prose', text(item[key])));
        const evidence = list(item.evidence); body.append(el('h3', '', 'Evidencia')); if (evidence.length) { const ul = el('ul', 'evidence'); evidence.forEach(e => ul.append(el('li', '', e))); body.append(ul); } else body.append(el('p', 'muted', 'No hay evidencia adjunta a este resultado.'));
        source(body, item.source ?? hit.source);
      }
      if (response.truncated) body.append(el('p', 'callout', 'Se ha alcanzado el límite de detalle de esta consulta. El contenido mostrado es parcial.'));
      if (hit.layer === 'documental' && hit.version > 0 && has('publish')) body.append(button('Retirar este documento', () => removeDocumentDialog(hit), 'button quiet danger'));
    } catch (e) { if (!abort.signal.aborted) failure(body, e, () => void retrieve()); }
  }; void retrieve();
}
function publishDialog(): void {
  const { dialog: d, body, status } = dialog('Publicar un documento', 'Publica una fuente validada en el espacio gestionado de este proyecto. Su recepción y su indexación se comprueban por separado.');
  const form = el('form'); const fields = el('fieldset', 'form-fields');
  const project = field(fields, 'Proyecto', { name: 'document_project', required: true, value: projectId || projects[0].id, choices: projects.map(p => [p.id, p.title]) });
  const title = field(fields, 'Título', { name: 'document_title', required: true, max: 500 });
  const contentField = field(fields, 'Contenido', { name: 'document_content', required: true, multiline: true, max: 200000 });
  const origin = field(fields, 'Referencia de origen', { name: 'document_source', required: true, max: 2000 });
  fields.append(el('p', 'hint', 'La huella de la fuente se calcula a partir del contenido que envías. Conserva la referencia al documento original.'));
  const categoryField = field(fields, 'Categoría', { name: 'document_category', max: 200, value: category });
  const tags = field(fields, 'Etiquetas', { name: 'document_tags', multiline: true, hint: 'Una etiqueta por línea.' });
  const evidence = field(fields, 'Evidencia de validación', { name: 'document_evidence', required: true, multiline: true, hint: 'Una referencia por línea. La validación conserva la identidad de quien publica.' });
  form.append(fields); const send = submitButton(form, 'Publicar documento'); body.append(form);
  let snapshot: { project: string; document: Row } | undefined; let busy = false; let completed = false;
  d.addEventListener('cancel', e => { if (busy || (snapshot && !completed && !confirm('La publicación aún no está confirmada. Comprueba sus operaciones antes de crear otra. ¿Cerrar el formulario?'))) e.preventDefault(); });
  form.addEventListener('submit', async e => { e.preventDefault(); send.disabled = true; busy = true;
    try {
      if (!snapshot) {
        const refs = lines(evidence.value); if (!refs.length) throw new Error('Añade evidencia de la validación.');
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(contentField.value)))].map(byte => byte.toString(16).padStart(2, '0')).join('');
        snapshot = { project: project.value, document: { document_id: crypto.randomUUID(), version: 1, title: title.value, content: contentField.value,
          category: categoryField.value, tags: lines(tags.value), source: { uri: origin.value, sha256: hash }, validation: { status: 'validated', evidence: refs, validated_by: actor!.id } } };
      }
      fields.disabled = true; status.textContent = 'Enviando documento…';
      const receipt = await api.request<Row>(`/v1/projects/${encodeURIComponent(snapshot.project)}/documents`, 'POST', snapshot.document);
      if (receipt.item_id !== snapshot.document.document_id || receipt.version !== 1 || !Array.isArray(receipt.jobs)) throw new MemoryApiError(502, 'invalid_receipt');
      completed = true; send.hidden = true; status.textContent = `Documento recibido · ${receipt.jobs.length} trabajos asociados. Consulta su publicación e indexación en Operaciones.`;
      body.append(button('Ver operaciones', () => { d.close(); navigate('operations'); }, 'button secondary'));
    } catch (error) { status.textContent = formatError(error); if (snapshot) { send.textContent = 'Reintentar la misma publicación'; status.textContent += ` Se conserva el documento ${text(snapshot.document.document_id)} con la versión 1.`; } send.disabled = false; }
    finally { busy = false; }
  });
}
function removeDocumentDialog(hit: Hit): void {
  const { body, status } = dialog('Retirar documento', 'La fuente se excluye de las lecturas centrales y se registra su retirada de los destinos gestionados.');
  body.append(el('p', '', hit.title), el('p', 'hint', `Proyecto ${hit.project_id} · Nueva versión ${hit.version + 1}`));
  const remove = button('Confirmar retirada', async () => { remove.disabled = true;
    try { await api.request(`/v1/projects/${encodeURIComponent(hit.project_id)}/documents/${encodeURIComponent(hit.item_id)}?version=${hit.version + 1}`, 'DELETE');
      remove.hidden = true; status.textContent = 'Retirada recibida. Comprueba el estado de las proyecciones en Operaciones.';
    } catch (error) { status.textContent = formatError(error); remove.textContent = 'Reintentar la misma retirada'; remove.disabled = false; }
  }, 'button danger'); body.append(remove);
}

function listView(kind: Exclude<View, 'work' | 'search' | 'map' | 'settings' | 'corpora'>): void {
  const area = el('section', 'list-area'); const toolbar = el('div', 'list-toolbar');
  const label = el('p', 'muted', ''); const filter = field(toolbar, kind === 'sessions' ? 'Filtrar sesiones cargadas por sesión o agente' : 'Filtrar elementos cargados', { name: 'list-filter', type: 'search' });
  toolbar.append(button('Actualizar', () => void retrieve(false), 'button secondary'));
  const pageActions = el('div', 'page-actions'); const pageStatus = el('p', 'form-status'); pageStatus.setAttribute('role', 'status');
  const more = button('Cargar más', () => void retrieve(true), 'button secondary'); more.hidden = true;
  const retry = button('Reintentar carga', () => void retrieve(lastAppend), 'button secondary'); retry.hidden = true; pageActions.append(more, retry, pageStatus);
  content.append(toolbar, label, area, pageActions);
  const endpoint = kind === 'memory' ? 'notes' : kind === 'operations' ? 'jobs' : kind === 'activity' ? 'activity-log' : kind;
  const selected = scope(); const viewSignal = controller.signal; const cursors = new Map<string, string | null>(); const remaining = new Set<string>();
  let allRows: Row[] = []; let pending: AbortController | undefined; let generation = 0; let lastAppend = false;
  let loading = false; let loadFailed = false;
  viewSignal.addEventListener('abort', () => pending?.abort(), { once: true });
  const render = () => {
    area.replaceChildren(); const needle = filter.value.toLocaleLowerCase(); const filtered = allRows.filter(row => JSON.stringify(row).toLocaleLowerCase().includes(needle));
    label.textContent = `${filtered.length} elementos visibles · ${allRows.length} cargados${remaining.size ? ' · hay más páginas' : ''}`;
    if (!filtered.length) { empty(area, allRows.length ? 'Ningún elemento coincide' : kind === 'operations' ? 'Sin operaciones registradas' : kind === 'sessions' ? 'Todavía no hay sesiones' : 'Todavía no hay memoria aquí', allRows.length ? 'Prueba otro filtro.' : kind === 'operations' ? 'Los trabajos aparecerán al recibir memoria o publicar documentos.' : 'La captura se activa por proyecto. Las sesiones y sus aprendizajes aparecerán cuando los clientes envíen eventos.'); return; }
    for (const row of filtered) area.append(kind === 'operations' ? jobCard(row, () => void retrieve(false)) : kind === 'sessions' ? sessionCard(row) : kind === 'activity' ? activityCard(row) : memoryCard(row, kind === 'history'));
    announce(`${filtered.length} elementos visibles.`);
  };
  const retrieve = async (append: boolean) => {
    pending?.abort(); pending = new AbortController(); const signal = pending.signal; const current = ++generation; lastAppend = append;
    loading = true;
    more.disabled = true; retry.hidden = true; pageStatus.textContent = append ? 'Cargando la página siguiente…' : 'Actualizando lista…';
    if (!allRows.length) area.replaceChildren(el('p', 'loading', 'Cargando…')); area.setAttribute('aria-busy', 'true');
    try {
    if (selected.length > 20) throw new Error('Selecciona un proyecto para acotar la lista (máximo 20 proyectos por carga).');
    const batches: {id: string; items: Row[]; cursor: string | null; more: boolean}[] = []; const errors: string[] = [];
    const pendingIds = selected.filter(id => !append || remaining.has(id)); let next = 0;
    await Promise.all(Array.from({length: Math.min(4, pendingIds.length)}, async () => {
      while (next < pendingIds.length && !signal.aborted) {
        const id = pendingIds[next++];
        try {
          const query = new URLSearchParams({ project_id: id, limit: '50' }); if (category) query.set('category', category);
          if (append && cursors.get(id)) query.set('cursor', cursors.get(id)!);
          const result = await api.request<{ items: Row[]; next_cursor?: string | null; has_more?: boolean }>(`/v1/${endpoint}?${query}`, 'GET', undefined, signal);
          if (result.has_more && (typeof result.next_cursor !== 'string' || !result.next_cursor)) throw new MemoryApiError(502, 'invalid_page');
          batches.push({id, items: rows(result).map(row => ({...row, project_id: row.project_id ?? id})), cursor: result.next_cursor ?? null, more: !!result.has_more});
        } catch (error) { if (!signal.aborted) errors.push(`${projects.find(p => p.id === id)?.title ?? id}: ${formatError(error)}`); }
      }
    }));
    if (signal.aborted || viewSignal.aborted || current !== generation) return false;
    if (!append) { for (const batch of batches) { cursors.delete(batch.id); remaining.delete(batch.id); } }
    for (const batch of batches) { cursors.set(batch.id, batch.cursor); if (batch.more) remaining.add(batch.id); else remaining.delete(batch.id); }
    allRows = mergePages(append ? allRows : allRows.filter(row => !batches.some(batch => batch.id === row.project_id)), batches.flatMap(batch => batch.items), endpoint).sort((a, b) => {
      const left = payload(a); const right = payload(b);
      const timeA = new Date(text(left.occurred_at ?? left.started_at ?? left.created_at)).getTime();
      const timeB = new Date(text(right.occurred_at ?? right.started_at ?? right.created_at)).getTime();
      return (Number.isFinite(timeB) ? timeB : 0) - (Number.isFinite(timeA) ? timeA : 0);
    }); render(); loadFailed = !!errors.length; more.hidden = !remaining.size; retry.hidden = !errors.length;
    pageStatus.textContent = errors.length ? `Carga parcial. ${errors.join(' · ')}` : append ? 'Página añadida.' : ''; return !errors.length;
    } catch (error) {
      if (!signal.aborted && !viewSignal.aborted && current === generation) { loadFailed = true; if (!allRows.length) area.replaceChildren(); pageStatus.textContent = formatError(error); retry.hidden = false; }
      return false;
    } finally { if (!viewSignal.aborted && current === generation) { loading = false; more.disabled = false; area.setAttribute('aria-busy', 'false'); } }
  };
  // Background history must not abort pagination, hide an error's retry button
  // or silently retry a failed request while the user is choosing an action.
  if (kind === 'memory' || kind === 'observations' || kind === 'rules' || kind === 'activity') refreshLiveMemory = (manual = false) => !manual && (loading || loadFailed) ? Promise.resolve(false) : retrieve(false);
  filter.addEventListener('input', render); void retrieve(false);
}
function memoryCard(raw: Row, historical = false): HTMLElement {
  const row = payload(raw); const card = el('article', historical ? 'result-card timeline-card' : 'result-card'); const meta = el('div', 'card-meta');
  meta.append(el('span', '', text(row.project_id)), badge(text(row.event_type ?? row.type, 'note')), badge(text(row.validation_status, 'unverified')), el('span', '', date(row.occurred_at ?? row.updated_at ?? row.created_at)));
  card.append(meta, el('h3', '', text(row.title, 'Memoria sin título')), el('p', 'excerpt', text(row.content ?? row.excerpt)));
  const tags = list(row.tags); if (tags.length) { const labels = el('div', 'card-meta'); labels.setAttribute('aria-label', 'Etiquetas'); for (const tag of tags) labels.append(el('span', 'badge', tag)); card.append(labels); }
  if (row.problem) card.append(el('p', 'problem', `Problema: ${text(row.problem)}`)); if (row.correction) card.append(el('p', '', `Corrección: ${text(row.correction)}`));
  const evidence = list(row.evidence); card.append(el('p', 'hint', evidence.length ? `Evidencia: ${evidence.join(' · ')}` : 'Sin evidencia adjunta'));
  const provenance = el('p', 'hint', `${row.agent_id ? `Agente: ${text(row.agent_id)} · ` : ''}${row.session_id ? `Sesión: ${text(row.session_id)} · ` : ''}Versión: ${text(row.version, 'no disponible')}`); card.append(provenance); source(card, row.source);
  if (row.supersedes || row.superseded) card.append(el('p', 'callout', row.superseded ? 'Esta memoria fue sustituida.' : `Sustituye al elemento ${text(row.supersedes)}.`));
  const actions = el('div', 'card-actions'); if (row.ref) actions.append(button('Abrir fuente', () => detailsDialog(row as unknown as Hit), 'button secondary'));
  if (!historical && has('write') && row.item_id && Number.isInteger(Number(row.version))) {
    actions.append(button('Crear siguiente versión', () => memoryDialog(row), 'button secondary'), button('Retirar memoria', () => deleteDialog(row), 'button quiet danger'));
  }
  if (actions.childNodes.length) card.append(actions); return card;
}
function activityCard(row: Row): HTMLElement {
  const card = el('article', 'result-card activity-card');
  const meta = el('div', 'card-meta'); meta.append(el('span', '', text(row.project_id)), badge(text(row.event_type, 'event')), el('span', '', date(row.created_at)));
  card.append(meta, el('h3', '', `Entrega ${text(row.event_id)}`), el('p', 'hint', `Referencia: ${text(row.ref)}`),
    el('p', 'hint', 'Registro de entrega; no implica extracción terminada ni validación del contenido.'));
  return card;
}
function sessionCard(row: Row): HTMLElement {
  const card = el('article', 'result-card'); const id = text(row.session_id ?? row.id); card.append(el('div', 'card-meta', text(row.project_id)), el('h3', '', id || 'Sesión sin identificador'),
    el('p', '', `Agente: ${text(row.agent_id, list(row.agent_ids).join(', ') || 'No indicado')}`), el('p', 'hint', `${date(row.started_at ?? row.created_at ?? row.occurred_at)}${row.ended_at ? ` → ${date(row.ended_at)}` : ''}`));
  if (row.summary) card.append(el('p', 'excerpt', text(row.summary)));
  card.append(button('Ver memoria de esta sesión', async () => {
    const { body, dialog: d } = dialog(`Sesión ${id}`); const abort = new AbortController(); d.addEventListener('close', () => abort.abort(), { once: true });
    let cursor: string | undefined; let loaded: Row[] = []; let busy = false;
    const retrieve = async () => { if (busy) return; busy = true; const previous = cursor;
      if (!loaded.length) body.replaceChildren(el('p', 'loading', 'Cargando memoria de la sesión…'));
      try {
        const params = new URLSearchParams({project_id: text(row.project_id), session_id: id, limit: '50'}); if (cursor) params.set('cursor', cursor);
        const response = await api.request<{items: Row[]; has_more?: boolean; next_cursor?: string}>(`/v1/notes?${params}`, 'GET', undefined, abort.signal);
        if (abort.signal.aborted) return;
        if (response.has_more && !response.next_cursor) throw new MemoryApiError(502, 'invalid_page');
        loaded = mergePages(loaded, rows(response), 'notes'); cursor = response.has_more ? response.next_cursor : undefined; body.replaceChildren();
        if (!loaded.length) empty(body, 'Esta sesión no tiene memoria vigente', 'El filtro se aplica a todas las notas del proyecto antes de paginar.');
        else loaded.forEach(note => body.append(memoryCard(note)));
        if (response.has_more) body.append(button('Cargar más de esta sesión', () => void retrieve(), 'button secondary'));
      } catch (e) { cursor = previous; if (!abort.signal.aborted) { if (!loaded.length) failure(body, e, () => void retrieve()); else { body.append(el('p', 'callout', formatError(e)), button('Reintentar página de sesión', () => void retrieve(), 'button secondary')); } } }
      finally { busy = false; }
    }; await retrieve();
  }, 'button secondary')); return card;
}
function jobCard(row: Row, refresh: () => void): HTMLElement {
  const card = el('article', 'result-card job-card'); const status = text(row.state ?? row.status, 'unknown'); const header = el('div', 'card-meta'); header.append(badge(status), el('span', '', `Destino: ${text(row.destination ?? row.backend ?? row.target, 'No indicado')}`));
  card.append(header, el('h3', '', text(row.kind ?? row.type ?? row.operation, 'Proyección de memoria')), el('p', 'hint', `Proyecto: ${text(row.project_id)} · Versión: ${text(row.version, '—')} · Intentos: ${text(row.attempts, '0')}`), el('p', 'hint', `Operación: ${text(row.id ?? row.job_id)}`));
  if (row.error_code || row.last_error_code) card.append(el('p', 'job-error', `Error: ${text(row.error_code ?? row.last_error_code)}`));
  if (status === 'unknown') card.append(el('p', 'callout', 'El destino puede haber recibido el contenido. La conciliación comprueba el resultado antes de volver a enviarlo.'));
  if (has('write') && ['failed', 'unknown', 'pending'].includes(status)) {
    const retry = button(status === 'unknown' ? 'Conciliar resultado' : 'Reintentar pendientes', async () => { retry.disabled = true; const feedback = el('p', 'form-status'); feedback.setAttribute('role', 'status'); card.append(feedback);
      try { await api.request(`/v1/jobs/${encodeURIComponent(text(row.id ?? row.job_id))}/retry`, 'POST'); announce('Operación solicitada. Comprueba su nuevo estado.'); refresh(); }
      catch (e) { feedback.textContent = formatError(e); retry.disabled = false; }
    }, 'button secondary'); card.append(retry);
  }
  return card;
}

function memoryDialog(existing?: Row, rule = false): void {
  const editing = !!existing; const old = existing ? payload(existing) : undefined;
  const { dialog: d, body, status } = dialog(editing ? 'Crear siguiente versión' : rule ? 'Nueva regla del proyecto' : 'Nueva memoria', rule ? 'Guarda una guía con procedencia. Su validación exige permiso y evidencia; el texto no se ejecuta como una instrucción.' : 'Guarda una experiencia con su origen. El registro de una nota no la convierte en conocimiento aprobado.');
  const form = el('form', 'memory-form'); const fields = el('fieldset'); fields.className = 'form-fields';
  const project = field(fields, 'Proyecto', { name: 'project', required: true, value: text(existing?.project_id, projectId || projects[0]?.id), choices: projects.map(p => [p.id, p.title]) });
  if (editing) project.disabled = true;
  const type = field(fields, 'Tipo de memoria', { name: 'event_type', required: true, value: text(old?.event_type, 'note'), choices: [['note', 'Nota'], ['learning', 'Aprendizaje'], ['correction', 'Corrección'], ['summary', 'Resumen de sesión']] });
  const title = field(fields, 'Título', { name: 'title', required: true, value: text(old?.title), max: 500 });
  const contentField = field(fields, 'Contenido y contexto aplicable', { name: 'content', required: true, multiline: true, value: text(old?.content), max: 100000 });
  fields.append(el('p', 'hint', 'Puedes marcar fragmentos como <private>…</private>. El servidor oculta esos fragmentos y aplica sus reglas de detección antes de guardar o procesar; revisa siempre el texto porque no identifica todos los datos sensibles. El formulario permanece en la memoria de esta página hasta el envío.'));
  const row = el('div', 'field-grid'); const session = field(row, 'Sesión de origen', { name: 'session_id', required: true, max: 200, value: text(existing?.session_id) });
  const agent = field(row, 'Agente o autor', { name: 'agent_id', required: true, max: 200, value: text(existing?.agent_id, actor?.username ?? actor?.id) }); fields.append(row);
  const problem = field(fields, 'Problema observado', { name: 'problem', multiline: true, max: 10000, value: text(old?.problem) });
  const correction = field(fields, 'Corrección o decisión', { name: 'correction', multiline: true, max: 10000, value: text(old?.correction) });
  const evidence = field(fields, 'Evidencia', { name: 'evidence', multiline: true, value: list(old?.evidence).join('\n'), hint: 'Una referencia por línea: prueba, incidencia o fuente que permite comprobar el aprendizaje.' });
  const validation = field(fields, 'Estado de validación', { name: 'validation_status', value: text(old?.validation_status, 'unverified'), choices: [['unverified', 'Sin validar'], ['observed', 'Observado'], ...(has('validate') ? [['validated', 'Validado'] as [string, string]] : [])] });
  if (!validation.value) validation.value = 'unverified';
  const cat = field(fields, 'Categoría', { name: 'category', max: 200, value: text(old?.category, category) });
  const tags = field(fields, 'Etiquetas', { name: 'tags', multiline: true, value: list(old?.tags).join('\n'), hint: 'Una etiqueta por línea. Conserva comas, comillas y acentos.' });
  const origin = old?.source && typeof old.source === 'object' ? old.source as Row : {};
  const uri = field(fields, 'Referencia de origen', { name: 'source_uri', max: 2000, value: text(origin.uri), hint: 'URL o identificador de la fuente. No se ejecuta ni se interpreta como una instrucción.' });
  const supersedes = field(fields, 'Elemento que corrige (opcional)', { name: 'supersedes', value: text(old?.supersedes), hint: 'Identificador del aprendizaje anterior que esta corrección sustituye.' });
  if (editing) fields.append(el('p', 'callout', `Elemento ${text(existing?.item_id)} · Versión actual ${text(existing?.version)} → nueva versión ${Number(existing?.version) + 1}`));
  const policy = el('p', 'hint'); const policyText = () => { const p = projects.find(p => p.id === project.value); policy.textContent = p?.capture_mode === 'off' ? 'Captura desactivada en este proyecto. Un administrador debe activarla en Configuración antes de guardar.' : 'La política del servidor decide qué captura admite este proyecto.'; }; project.addEventListener('change', policyText); policyText(); fields.append(policy);
  form.append(fields); const send = submitButton(form, editing ? 'Guardar siguiente versión' : 'Guardar memoria');
  const abandon = button('Descartar intento y cerrar', () => { if (confirm('Se descartará este formulario. Si se perdió una respuesta, comprueba la memoria antes de crear otro registro.')) d.close(); }, 'button quiet'); abandon.hidden = true; form.append(abandon); body.append(form);
  const submission = new EventSubmission(); let busy = false;
  d.addEventListener('cancel', e => { if (busy || (submission.pending && !send.hidden && !confirm('El envío aún no está confirmado. Cerrar descarta el intento conservado en esta página. Comprueba la memoria antes de crear otro registro.'))) e.preventDefault(); });
  form.addEventListener('submit', async e => { e.preventDefault(); send.disabled = true; busy = true; status.textContent = 'Enviando memoria…';
    try {
      const receipt = await submission.submit(api, () => {
        if (projects.find(p => p.id === project.value)?.capture_mode === 'off') throw new Error('La captura está desactivada en este proyecto. Un administrador debe activarla en Configuración antes de guardar memoria.');
        if ((type.value === 'learning' || type.value === 'correction') && (!problem.value.trim() || !correction.value.trim())) throw new Error('Indica el problema observado y su corrección para guardar un aprendizaje.');
        if (validation.value === 'validated' && !lines(evidence.value).length) throw new Error('Un aprendizaje validado necesita evidencia.');
        const p: Payload = { title: title.value, content: contentField.value, category: cat.value, tags: [...new Set([...lines(tags.value), ...(rule ? ['kairos:rule'] : [])])], validation_status: validation.value,
          problem: problem.value, correction: correction.value, evidence: lines(evidence.value) };
        if (uri.value) p.source = { uri: uri.value }; if (supersedes.value) p.supersedes = supersedes.value;
        return createEvent({ projectId: project.value, sessionId: session.value, agentId: agent.value, type: type.value, payload: p,
          itemId: editing ? text(existing?.item_id) : undefined, version: editing ? Number(existing?.version) + 1 : 1 });
      });
      fields.disabled = true; send.hidden = true; abandon.hidden = true;
      if (receipt.redacted) for (const input of [title, contentField, session, agent, problem, correction, evidence, cat, tags, uri, supersedes]) input.value = '';
      status.textContent = `${receipt.redacted ? 'Memoria guardada con datos privados ocultos. ' : ''}${statuses[receipt.status]} · Versión ${receipt.version}. ${receipt.jobs.length} trabajos asociados; su estado se comprueba en Operaciones.`;
      body.append(button('Ver operaciones', () => { d.close(); navigate('operations'); }, 'button secondary')); announce('Memoria recibida. Las proyecciones se verifican por separado.');
    } catch (err) {
      status.textContent = formatError(err); send.disabled = false;
      if (submission.pending) { fields.disabled = true; send.textContent = 'Reintentar el mismo envío'; abandon.hidden = false; status.textContent += ` Se conserva el envío ${submission.pending.event_id} y su contenido para evitar duplicados.`; }
    } finally { busy = false; }
  });
}
function deleteDialog(row: Row): void {
  const { dialog: d, body, status } = dialog('Retirar memoria', 'La memoria dejará de aparecer en las consultas centrales. Las proyecciones se retirarán mediante operaciones verificables.');
  body.append(el('p', '', text(row.title)), el('p', 'hint', `Elemento ${text(row.item_id)} · Se enviará la versión ${Number(row.version) + 1}.`));
  const submission = new EventSubmission(); const remove = button('Confirmar retirada', async () => { remove.disabled = true;
    try {
      const receipt = await submission.submit(api, () => createEvent({ projectId: text(row.project_id), sessionId: text(row.session_id, 'portal-retirada'), agentId: text(actor?.username ?? actor?.id), type: 'delete', itemId: text(row.item_id), version: Number(row.version) + 1,
        payload: { title: text(row.title, 'Retirada de memoria'), content: '' } }));
      status.textContent = `Retirada recibida · Versión ${receipt.version}. Revisa las proyecciones en Operaciones.`; remove.hidden = true; renderView(false);
    } catch (e) { status.textContent = formatError(e); remove.disabled = false; remove.textContent = 'Reintentar la misma retirada'; }
  }, 'button danger'); body.append(remove, button('Cancelar', () => d.close(), 'button secondary'));
}

function settingsView(): void {
  if (!admin()) { empty(content, 'Configuración administrada', 'Tu acceso no incluye administración. Pide a un administrador cambios de política o acceso.'); return; }
  const tabs = el('nav', 'settings-tabs'); tabs.setAttribute('aria-label', 'Configuración'); const area = el('div');
  const show = (section: string) => { area.replaceChildren(); for (const child of tabs.querySelectorAll('button')) child.setAttribute('aria-current', child.dataset.section === section ? 'page' : 'false');
    if (section === 'projects') projectSettings(area); else accessSettings(area, section === 'keys');
  };
  for (const [id, title] of [['projects', 'Proyectos y políticas'], ['keys', 'Claves para agentes'], ['users', 'Usuarios']]) { const b = button(title, () => show(id), 'button secondary'); b.dataset.section = id; tabs.append(b); }
  content.append(tabs, area); show('projects');
}
function projectSettings(area: HTMLElement): void {
  const grid = el('div', 'settings-grid'); const create = panel('Crear proyecto', 'La memoria empieza con la captura desactivada. Puedes activarla después de revisar la política.');
  const form = el('form'); const id = field(form, 'Identificador', { name: 'id', required: true, max: 64, hint: 'Minúsculas, números, guiones y guiones bajos.' }) as HTMLInputElement; id.pattern = '[a-z0-9][a-z0-9_-]{0,63}';
  const title = field(form, 'Nombre del proyecto', { name: 'title', required: true, max: 200 }); const formStatus = formError(form); const send = submitButton(form, 'Crear proyecto'); create.append(form);
  form.addEventListener('submit', async e => { e.preventDefault(); send.disabled = true; try { await api.request('/v1/projects', 'POST', { id: id.value, title: title.value, capture_mode: 'off', temporal_projection: false }); await loadProjects(); formStatus.textContent = 'Proyecto creado. Selecciónalo para configurar la política.'; id.value = ''; title.value = ''; shell(); navigate('settings'); } catch (err) { formStatus.textContent = formatError(err); } finally { send.disabled = false; } });
  const policy = panel('Política de captura', 'La activación permite recibir los tipos de memoria elegidos. El contenido completo necesita consentimiento adicional en cada cliente.');
  if (!projects.length) empty(policy, 'Sin proyectos', 'Crea el primer proyecto para configurar su captura.');
  else {
    const selector = field(policy, 'Proyecto', { name: 'policy-project', value: projectId || projects[0].id, choices: projects.map(p => [p.id, p.title]) }); const policyArea = el('div'); policy.append(policyArea);
    let request = 0; const read = async () => { const current = ++request; policyArea.replaceChildren(el('p', 'loading', 'Cargando política…'));
      try { const p = await api.request<Policy>(`/v1/projects/${encodeURIComponent(selector.value)}/policy`, 'GET', undefined, controller.signal); if (current !== request || controller.signal.aborted || !policyArea.isConnected) return; policyArea.replaceChildren();
        const f = el('form'); const capture = field(f, 'Memoria que se puede capturar', { name: 'capture_mode', value: p.capture_mode, choices: [['off', 'Desactivada'], ['summary', 'Resúmenes y aprendizajes'], ['full', 'Contenido completo (opt-in)']] });
        const temporal = check(f, 'Conservar hechos y relaciones de los nuevos eventos', p.temporal_projection); const consent = check(f, 'He revisado la captura de contenido completo y su consentimiento explícito en los clientes.', false);
        const feedback = formError(f); const save = submitButton(f, 'Guardar política'); f.addEventListener('submit', async e => { e.preventDefault();
          if (capture.value === 'full' && !consent.checked) { feedback.textContent = 'Confirma la revisión del consentimiento para activar contenido completo.'; return; }
          save.disabled = true; try { const saved = await api.request<Policy>(`/v1/projects/${encodeURIComponent(selector.value)}/policy`, 'PUT', { capture_mode: capture.value, temporal_projection: temporal.checked });
            const cached = projects.find(p => p.id === selector.value); if (cached) cached.capture_mode = saved.capture_mode; feedback.textContent = 'Política guardada.';
          } catch (error) { feedback.textContent = formatError(error); } finally { save.disabled = false; }
        }); policyArea.append(f);
      } catch (e) { if (current === request && !controller.signal.aborted) failure(policyArea, e, () => void read()); }
    }; selector.addEventListener('change', () => void read()); void read();
  }
  grid.append(create, policy); area.append(grid);
}
function accessSettings(area: HTMLElement, keys: boolean): void {
  if (keys) {
    const onboarding = panel('Conectar un agente', 'Configura una sola dirección de la plataforma y una clave limitada a sus proyectos. La plataforma reúne las tres capas y se encarga de consultar los servicios internos.');
    const gateway = new URL('/memory-api', location.origin).href;
    const endpoint = field(onboarding, 'Dirección de la plataforma', { name: 'agent-endpoint', value: gateway, hint: 'Usa una dirección HTTPS accesible desde el equipo del agente. En esta instalación, esta es la misma entrada que utiliza el portal.' }) as HTMLInputElement;
    endpoint.readOnly = true;
    onboarding.append(el('p', 'hint', 'Conexión MCP: /mcp. API HTTP: /v1. Ambas usan la misma dirección y credencial. La captura se activa por proyecto y cliente.'));
    const copyStatus = formError(onboarding);
    onboarding.append(button('Copiar dirección', async () => { try { await navigator.clipboard.writeText(gateway); copyStatus.textContent = 'Dirección copiada.'; } catch { endpoint.select(); copyStatus.textContent = 'Dirección seleccionada. Usa Copiar en el navegador.'; } }, 'button secondary'));
    area.append(onboarding);
  }
  const create = panel(keys ? 'Crear clave para un agente' : 'Crear usuario', keys ? 'La clave se muestra una sola vez. Limita los proyectos y permisos a lo que necesita el agente.' : 'Cada usuario entra con contraseña. Sus proyectos y permisos delimitan el acceso.');
  const form = el('form'); const name = field(form, keys ? 'Nombre de la clave' : 'Nombre de usuario', { name: keys ? 'name' : 'username', required: true, max: 128 });
  const password = keys ? undefined : field(form, 'Contraseña inicial', { name: 'password', type: 'password', required: true, max: 1024 }) as HTMLInputElement;
  if (password) { password.autocomplete = 'new-password'; password.minLength = 12; }
  const getProjects = selectedProjects(form); const getScopes = selectedScopes(form); const feedback = formError(form); const send = submitButton(form, keys ? 'Crear clave' : 'Crear usuario'); create.append(form);
  const listing = panel(keys ? 'Claves emitidas' : 'Usuarios de la instancia'); const listArea = el('div'); listing.append(button('Actualizar lista', () => void retrieve(), 'button secondary'), listArea);
  area.append(create, listing);
  const endpoint = keys ? 'keys' : 'users';
  const retrieve = async () => {
    const signal = controller.signal; listArea.replaceChildren(el('p', 'loading', 'Cargando accesos…'));
    try { const response = await api.request<{ items: Row[] }>(`/v1/${endpoint}`, 'GET', undefined, signal); if (signal.aborted || !listArea.isConnected) return; listArea.replaceChildren();
      const items = rows(response); if (!items.length) empty(listArea, keys ? 'Sin claves emitidas' : 'Sin usuarios en esta lista', 'Los accesos creados aparecerán aquí.');
      for (const row of items) {
        const item = el('article', 'access-row'); item.append(el('h3', '', text(row.name ?? row.username, 'Acceso sin nombre')), el('p', 'hint', `Proyectos: ${list(row.project_ids).join(', ') || 'Ninguno'} · Permisos: ${list(row.scopes).join(', ') || 'Ninguno'}`));
        if (keys) { const revoked = !!(row.revoked_at || row.revoked); item.append(badge(revoked ? 'revoked' : 'active'));
          if (!revoked) item.append(button('Revocar clave', () => revokeDialog(row, retrieve), 'button quiet danger'));
        } listArea.append(item);
      }
    } catch (e) { if (!signal.aborted && listArea.isConnected) failure(listArea, e, () => void retrieve()); }
  };
  form.addEventListener('submit', async e => { e.preventDefault(); const ids = getProjects(); const scopes = getScopes(); if (!ids.length || !scopes.length) { feedback.textContent = 'Selecciona al menos un proyecto y un permiso.'; return; }
    send.disabled = true;
    try {
      const body = keys ? { name: name.value, project_ids: ids, scopes } : { username: name.value, password: password!.value, project_ids: ids, scopes };
      const response = await api.request<Row>(`/v1/${endpoint}`, 'POST', body);
      if (keys) {
        const secret = text(response.key ?? response.token ?? response.secret);
        if (!secret) throw new MemoryApiError(502, 'missing_key');
        keyDialog(secret); feedback.textContent = 'Clave creada. Guárdala antes de cerrar el diálogo.';
      } else { password!.value = ''; feedback.textContent = 'Usuario creado.'; }
      name.value = ''; await retrieve();
    } catch (err) { feedback.textContent = formatError(err); if (keys) feedback.textContent += ' Si la respuesta se perdió, revisa la lista antes de crear otra clave.'; }
    finally { send.disabled = false; }
  }); void retrieve();
}
function keyDialog(secret: string): void {
  const { dialog: d, body, status } = dialog('Guarda la clave ahora', 'Se muestra una sola vez. Compártela únicamente con el cliente autorizado y guárdala en su almacén de secretos.');
  const fieldSecret = field(body, 'Clave del agente', { name: 'new-key', value: secret, multiline: true }) as HTMLTextAreaElement; fieldSecret.readOnly = true; fieldSecret.spellcheck = false; fieldSecret.autocomplete = 'off';
  body.append(button('Copiar clave', async () => { try { await navigator.clipboard.writeText(fieldSecret.value); status.textContent = 'Clave copiada.'; } catch { fieldSecret.select(); status.textContent = 'Seleccionada. Usa la opción Copiar de tu navegador.'; } }, 'button secondary'));
  d.addEventListener('close', () => { fieldSecret.value = ''; secret = ''; }, { once: true });
}
function revokeDialog(row: Row, refresh: () => Promise<void>): void {
  const { dialog: d, body, status } = dialog('Revocar clave', `El agente que use «${text(row.name)}» perderá el acceso. Esta acción no borra su memoria.`);
  const revoke = button('Confirmar revocación', async () => { revoke.disabled = true; try { await api.request(`/v1/keys/${encodeURIComponent(text(row.id ?? row.key_id))}`, 'DELETE'); await refresh(); d.close(); announce('Clave revocada.'); } catch (e) { status.textContent = formatError(e); revoke.disabled = false; } }, 'button danger'); body.append(revoke);
}

window.addEventListener('popstate', () => {
  if (!actor) return; const p = new URLSearchParams(location.search); const v = p.get('view'); view = v && Object.hasOwn(views, v) ? v as View : 'memory';
  projectId = projects.some(project => project.id === p.get('project')) ? p.get('project')! : ''; category = p.get('category') ?? ''; shell();
});
void boot();
