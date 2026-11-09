import { MemoryApi, MemoryApiError } from './memory-api.ts';
import type { Project } from './memory-types.ts';

type Scalar = string | number | boolean | null;
interface WorkState { fields: Record<string, Scalar>; tasks: Record<string, Record<string, Scalar>> }
interface WorkList { list: string; version: number; hash: string; state: WorkState; updated_at: string; updated_by?: string }
interface WorkResponse { project: string; lists: WorkList[] }
interface Entry { project: Project; list: WorkList }

function element<K extends keyof HTMLElementTagNameMap>(tag: K, name = '', value?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag); node.className = name;
  if (value !== undefined) node.textContent = value;
  return node;
}
function text(value: Scalar | undefined): string { return value == null ? '' : String(value); }
function closed(task: Record<string, Scalar>): boolean { return task.status === 'done' || task.status === 'dropped'; }
function status(list: WorkList): string {
  if (list.state.fields.needs_input === true) return 'needs_input';
  const tasks = Object.values(list.state.tasks);
  if (list.state.fields.status === 'done' || list.state.fields.status === 'dropped' || (tasks.length && tasks.every(closed))) return 'done';
  return list.state.fields.status === 'doing' || tasks.some(task => task.status === 'doing') ? 'doing' : 'todo';
}
const labels: Record<string, string> = { todo: 'Por empezar', doing: 'En curso', needs_input: 'Necesita tu atención', done: 'Finalizado' };

/** The board displays persisted work, never inferred presence or invented progress. */
export function mountWorkBoard(options: {
  target: HTMLElement; api: MemoryApi; projects: Project[]; signal: AbortSignal;
  writable: boolean; announce: (message: string) => void; category?: string;
}): void {
  const { target, api, projects, signal, writable, announce } = options;
  let entries: Entry[] = []; let filter = 'all'; let query = ''; let generation = 0;
  const toolbar = element('section', 'work-toolbar'); toolbar.setAttribute('aria-label', 'Filtrar trabajo');
  const search = element('input'); search.type = 'search'; search.placeholder = 'Buscar una tarea o lista…'; search.setAttribute('aria-label', 'Buscar trabajo');
  const choose = element('select'); choose.setAttribute('aria-label', 'Estado del trabajo');
  for (const [value, name] of [['all', 'Todos los estados'], ...Object.entries(labels)]) {
    const option = element('option', '', name); option.value = value; choose.append(option);
  }
  const refresh = element('button', 'button secondary', 'Actualizar trabajo'); refresh.type = 'button';
  const visibility = element('select'); visibility.setAttribute('aria-label', 'Visibilidad del trabajo');
  for (const [value, label] of [['private', 'Mi trabajo privado'], ['team', 'Trabajo del equipo']]) { const option = element('option', '', label); option.value = value; visibility.append(option); }
  const access = element('p', 'hint', 'Las listas privadas sólo son visibles para tu usuario. El trabajo del equipo es visible para lectores del proyecto.');
  const summary = element('p', 'hint'); summary.setAttribute('role', 'status');
  const errors = element('div', 'work-errors'); errors.setAttribute('role', 'status');
  const cards = element('section', 'work-grid'); cards.setAttribute('aria-label', 'Listas de trabajo');
  toolbar.append(search, choose, visibility, refresh); target.replaceChildren(toolbar, access, summary, errors, cards);

  function render(): void {
    cards.replaceChildren();
    const categorized = entries.filter(entry => !options.category || entry.list.state.fields.category === options.category || Object.values(entry.list.state.tasks).some(task => task.category === options.category));
    const shown = categorized.filter(entry => (filter === 'all' || status(entry.list) === filter) &&
      [entry.project.title, entry.list.list, ...Object.keys(entry.list.state.tasks)].join(' ').toLocaleLowerCase('es').includes(query));
    const tasks = shown.reduce((n, entry) => n + Object.keys(entry.list.state.tasks).length, 0);
    summary.textContent = `${shown.length} de ${entries.length} listas · ${tasks} tareas guardadas. El estado no indica agentes conectados.${options.category ? ' Sólo listas con esa categoría explícita.' : ''}`;
    if (!shown.length) {
      const empty = element('div', 'state empty'); empty.append(element('h2', '', entries.length ? 'Sin coincidencias' : 'Tu siguiente paso, con contexto'),
        element('p', '', entries.length ? 'Prueba otra búsqueda o estado.' : 'Los agentes pueden guardar tareas con work_state_write por MCP. Aquí verás el trabajo pendiente y podrás revisar lo que ya terminaron.'));
      cards.append(empty); return;
    }
    for (const entry of shown) {
      const { list, project } = entry; const currentStatus = status(list);
      const mutationPath = `/v1/projects/${encodeURIComponent(project.id)}/${visibility.value === 'team' ? 'team-work' : 'work-state'}`;
      const card = element('article', 'work-card'); const top = element('div', 'work-card-top');
      const badge = element('span', 'work-status', labels[currentStatus]); badge.dataset.status = currentStatus;
      top.append(element('span', 'work-project', project.title), element('span', 'badge', visibility.value === 'team' ? 'Equipo' : 'Privado'), badge);
      const heading = element('h2', '', list.list); const description = text(list.state.fields.description ?? list.state.fields.summary);
      card.append(top, heading); if (description) card.append(element('p', 'muted', description));
      const items = Object.entries(list.state.tasks); const completed = items.filter(([, task]) => closed(task)).length;
      if (items.length) {
        const progress = element('progress'); progress.max = items.length; progress.value = completed; progress.setAttribute('aria-label', `${completed} de ${items.length} tareas finalizadas`);
        card.append(progress, element('p', 'hint', `${completed} de ${items.length} tareas finalizadas`));
      }
      const detail = element('details', 'work-detail'); detail.append(element('summary', '', 'Ver tareas y detalles'));
      for (const [name, task] of items) {
        const row = element('div', 'work-task'); const title = element('div');
        title.append(element('strong', '', name), element('span', 'hint', task.status === 'dropped' ? 'Descartada' : labels[text(task.status)] ?? 'Por empezar'));
        row.append(title);
        for (const [key, value] of Object.entries(task)) {
          if (key !== 'status' && value != null) title.append(element('p', 'hint', `${key}: ${text(value)}`));
        }
        if (writable && project.capture_mode !== 'off' && !closed(task)) {
          const done = element('button', 'button quiet', 'Completar'); done.type = 'button';
          // Keep the exact intent after an uncertain delivery. Never allocate a
          // second request ID while retrying this button's operation.
          let intent: { list: string; fields: { task: string; status: string }; request_id: string; expected_version: number } | undefined;
          done.addEventListener('click', async () => {
            intent ??= { list: list.list, fields: { task: name, status: 'done' }, request_id: crypto.randomUUID(), expected_version: list.version };
            done.disabled = true;
            try {
              await api.request(mutationPath, 'POST', intent, signal);
              if (signal.aborted) return;
              intent = undefined; announce('Tarea guardada como finalizada.'); await reload();
            } catch (error) {
              if (signal.aborted) return;
              done.textContent = 'Reintentar confirmación';
              announce(error instanceof MemoryApiError ? error.message : 'No se pudo confirmar la actualización. Reintenta la misma operación.');
            } finally { done.disabled = false; }
          });
          row.append(done);
        }
        detail.append(row);
      }
      const fields = element('dl', 'work-fields');
      for (const [key, value] of Object.entries(list.state.fields)) {
        if (value == null || key === 'description' || key === 'summary') continue;
        fields.append(element('dt', '', key), element('dd', '', text(value)));
      }
      if (fields.childNodes.length) detail.append(fields);
      if (!items.length && !fields.childNodes.length) detail.append(element('p', 'hint', 'Esta lista todavía no contiene tareas.'));
      card.append(detail);
      const footer = element('div', 'work-card-footer');
      const updated = new Date(list.updated_at); footer.append(element('span', '', `Versión ${list.version}`), element('span', '', Number.isNaN(updated.getTime()) ? '' : new Intl.DateTimeFormat('es', {dateStyle: 'medium', timeStyle: 'short'}).format(updated)));
      if (list.updated_by) footer.append(element('span', '', `Última edición: ${list.updated_by}`));
      card.append(footer); cards.append(card);
    }
  }

  async function reload(): Promise<void> {
    const current = ++generation; const endpoint = visibility.value === 'team' ? 'team-work' : 'work-state'; refresh.disabled = true; errors.replaceChildren(); cards.setAttribute('aria-busy', 'true');
    summary.textContent = 'Cargando trabajo guardado…';
    if (projects.length > 20) {
      summary.textContent = 'Selecciona un proyecto para acotar el trabajo.'; refresh.disabled = false; cards.setAttribute('aria-busy', 'false'); return;
    }
    const results: Entry[][] = []; let next = 0;
    await Promise.all(Array.from({ length: Math.min(4, projects.length) }, async () => {
      while (next < projects.length && !signal.aborted && current === generation) {
        const index = next++; const project = projects[index];
        try {
          const result = await api.request<WorkResponse>(`/v1/projects/${encodeURIComponent(project.id)}/${endpoint}?include_closed=true`, 'GET', undefined, signal);
          if (!Array.isArray(result.lists) || result.project !== project.id) throw new MemoryApiError(502, 'invalid_response');
          results[index] = result.lists.filter(list => list.state && list.state.fields && list.state.tasks).map(list => ({ project, list }));
        } catch (error) {
          if (signal.aborted || current !== generation) return;
          errors.append(element('p', 'callout', `${project.title}: ${error instanceof MemoryApiError ? error.message : 'No se pudo leer el trabajo.'}`));
        }
      }
    }));
    if (signal.aborted || current !== generation) return;
    entries = results.flat().sort((a, b) => b.list.updated_at.localeCompare(a.list.updated_at));
    render(); refresh.disabled = false; cards.setAttribute('aria-busy', 'false');
  }
  if (writable && projects.some(p => p.capture_mode !== 'off')) {
    const details = element('details', 'panel work-create'); details.append(element('summary', '', 'Guardar una tarea'));
    const form = element('form'); const fields = element('fieldset'); fields.className = 'field-grid';
    const input = (label: string, name: string, max = 200) => {
      const wrap = element('label', 'field'); const item = element('input'); item.name = name; item.maxLength = max;
      wrap.append(element('span', '', label), item); fields.append(wrap); return item;
    };
    const projectLabel = element('label', 'field'); const project = element('select'); project.name = 'work-project';
    projectLabel.append(element('span', '', 'Proyecto de la tarea'), project); fields.append(projectLabel);
    for (const p of projects.filter(p => p.capture_mode !== 'off')) { const option = element('option', '', p.title); option.value = p.id; project.append(option); }
    const name = input('Lista', 'work-list'); name.required = true;
    const task = input('Tarea', 'work-task', 300); task.required = true;
    const description = input('Descripción (opcional)', 'work-description', 2000);
    const owner = input('Responsable (referencia de texto, opcional)', 'work-owner');
    const state = element('p', 'form-status'); state.setAttribute('role', 'status');
    const send = element('button', 'button primary', 'Guardar tarea'); send.type = 'submit';
    let pending: {path: string; body: {list: string; fields: Record<string, Scalar>; expected_version: number; request_id: string}} | undefined; let busy = false;
    form.append(fields, element('p', 'hint', 'Se guardará en la visibilidad seleccionada arriba. Una lista nueva empieza en versión 1; una lista existente exige su versión actual.'), send, state);
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (busy || signal.aborted || (!pending && (!name.value.trim() || !task.value.trim()))) return;
      pending ??= {path: `/v1/projects/${encodeURIComponent(project.value)}/${visibility.value === 'team' ? 'team-work' : 'work-state'}`,
        body: {list: name.value.trim(), fields: {task: task.value.trim(), status: 'todo', description: description.value, assignee: owner.value, ...(options.category ? {category: options.category} : {})},
          expected_version: entries.find(e => e.project.id === project.value && e.list.list === name.value.trim())?.list.version ?? 0, request_id: crypto.randomUUID()}};
      busy = true; fields.disabled = visibility.disabled = true; send.disabled = true; state.textContent = 'Guardando la misma operación…';
      try { await api.request(pending.path, 'POST', pending.body, signal); if (signal.aborted) return;
        pending = undefined; fields.disabled = visibility.disabled = false; send.textContent = 'Guardar tarea'; state.textContent = 'Tarea guardada.'; task.value = ''; await reload();
      } catch (error) { if (!signal.aborted) { send.textContent = 'Reintentar la misma tarea'; state.textContent = `${error instanceof MemoryApiError ? error.message : 'No se pudo confirmar.'} Se conserva la operación. Actualiza y revisa la lista antes de iniciar otro intento distinto.`; } }
      finally { busy = false; send.disabled = false; }
    });
    details.append(form); target.append(details);
  }
  search.addEventListener('input', () => { query = search.value.trim().toLocaleLowerCase('es'); render(); });
  choose.addEventListener('change', () => { filter = choose.value; render(); });
  visibility.addEventListener('change', () => { entries = []; cards.replaceChildren(); void reload(); });
  refresh.addEventListener('click', () => void reload()); void reload();
}
