import { MemoryApi, MemoryApiError, lines } from './memory-api.ts';
import type { Project } from './memory-types.ts';

interface Corpus { name: string; version: number; count: number; primed: boolean; session_id: string | null; hash: string }
interface Answer { request_id: string; status: string; session_id: string; generation: number; model: string; reserved_token_units: number; error_code?: string | null;
  input_tokens?: number; output_tokens?: number; result?: {answer: string; citations: {ref: string; quote: string}[]} | null }
const node = <K extends keyof HTMLElementTagNameMap>(tag: K, text?: string) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
function field(form: HTMLElement, label: string, name: string, multiline = false): HTMLInputElement | HTMLTextAreaElement {
  const wrap = node('label'); wrap.className = 'field'; const input = multiline ? node('textarea') : node('input'); input.name = name; input.maxLength = 4000;
  wrap.append(node('span', label), input); form.append(wrap); return input;
}
function button(label: string, action: () => void): HTMLButtonElement { const b = node('button', label); b.type = 'button'; b.className = 'button secondary'; b.addEventListener('click', action); return b; }
function error(value: unknown): string { return value instanceof MemoryApiError || value instanceof Error ? value.message : 'No se pudo completar la consulta.'; }

/** Explicit model generation; opening this page never starts a provider request. */
export function mountCorpusPanel({target, api, projects, signal, writable, category}: {
  target: HTMLElement; api: MemoryApi; projects: Project[]; signal: AbortSignal; writable: boolean; category: string;
}): void {
  const controls = node('section'); controls.className = 'panel corpus-controls';
  controls.append(node('h2', 'Memorias seleccionadas, respuestas con fuentes'), node('p', 'El corpus es privado a tu usuario. Crear o preparar una selección no llama al modelo. Cada pregunta enviada solicita una generación; las respuestas siguen sin validar.'));
  if (projects.length !== 1) { controls.append(node('p', 'Selecciona un proyecto en la barra lateral para gestionar sus corpus.')); target.replaceChildren(controls); return; }
  const project = projects[0]; const prefix = `/v1/projects/${encodeURIComponent(project.id)}/corpora`;
  const status = node('p'); status.className = 'form-status'; status.setAttribute('role', 'status');
  const corpusLabel = node('label'); corpusLabel.className = 'field'; const select = node('select'); select.name = 'corpus'; corpusLabel.append(node('span', 'Corpus guardado'), select);
  const detail = node('p'); detail.className = 'hint'; const output = node('section'); output.className = 'corpus-answers'; output.setAttribute('aria-label', 'Respuestas citadas');
  let corpora: Corpus[] = []; let busy = false; let uncertain: {name: string; question: string; request_id: string; expected_session_id: string; expected_generation: number} | undefined;
  const current = () => corpora.find(c => c.name === select.value);
  const sync = () => { const c = current(); detail.textContent = c ? `${c.count} memorias · Generación ${c.version} · ${c.primed ? 'Preparado' : 'Necesita preparación'} · ${c.hash}` : 'Todavía no hay corpus. Crea una selección explícita.';
    ask.disabled = busy || !!uncertain || !writable || !c?.primed || !c.session_id; prime.disabled = fresh.disabled = rebuild.disabled = busy || !!uncertain || !writable || !c;
    select.disabled = refresh.disabled = busy || !!uncertain; reconcile.hidden = !uncertain; reconcile.disabled = busy; create.disabled = busy || !!uncertain || !writable;
  };
  const load = async (selected?: string) => { const response = await api.request<{items: Corpus[]}>(prefix, 'GET', undefined, signal);
    if (signal.aborted) return; if (!Array.isArray(response.items)) throw new MemoryApiError(502, 'invalid_response'); corpora = response.items; select.replaceChildren();
    for (const c of corpora) { const option = node('option', c.name); option.value = c.name; select.append(option); }
    if (selected && corpora.some(c => c.name === selected)) select.value = selected;
    builder.open = corpora.length === 0; sync();
  };
  const prepare = async (freshSession: boolean) => { const c = current(); if (!c || busy || uncertain) return; busy = true; sync(); status.textContent = 'Preparando generación…';
    try { await api.request(`${prefix}/${encodeURIComponent(c.name)}/prime`, 'POST', {fresh: freshSession}, signal); if (!signal.aborted) { await load(c.name); output.replaceChildren(); status.textContent = freshSession ? 'Conversación reiniciada. El presupuesto acumulado se conserva.' : 'Generación preparada. Puedes enviar una pregunta.'; } }
    catch (e) { if (!signal.aborted) status.textContent = error(e); } finally { busy = false; if (!signal.aborted) sync(); }
  };
  const prime = button('Preparar corpus', () => void prepare(false)); const fresh = button('Nueva conversación', () => void prepare(true));
  const rebuild = button('Actualizar selección de fuentes', () => { const c = current(); if (!c || busy || uncertain || !writable) return; busy = true; sync();
    status.textContent = 'Reaplicando filtros a las fuentes vigentes…';
    void api.request(`${prefix}/${encodeURIComponent(c.name)}/rebuild`, 'POST', {force: false, expected_version: c.version}, signal)
      .then(async () => { if (!signal.aborted) { await load(c.name); output.replaceChildren(); status.textContent = 'Selección actualizada. Prepara la generación antes de preguntar. Una pérdida de más de la mitad requiere revisión explícita por MCP.'; } })
      .catch(e => { if (!signal.aborted) status.textContent = error(e); }).finally(() => { busy = false; if (!signal.aborted) sync(); });
  });
  const refresh = button('Actualizar corpus', () => { if (!busy && !uncertain) void load(select.value).catch(e => { status.textContent = error(e); }); });
  const form = node('form'); const name = field(form, 'Nombre de la selección', 'corpus-name'); name.maxLength = 200; name.required = true;
  const query = field(form, 'Palabras de las memorias (opcional)', 'corpus-query'); const tags = field(form, 'Etiquetas exactas, una por línea (opcional)', 'corpus-tags', true);
  form.append(node('p', `Se seleccionan hasta 500 memorias vigentes del proyecto.${category ? ` Categoría activa: ${category}.` : ''} Los documentos externos no se incorporan automáticamente.`));
  const create = node('button', 'Crear selección'); create.type = 'submit'; create.className = 'button secondary';
  // The submit handler alone owns mutations, including keyboard submission.
  form.append(create);
  form.addEventListener('submit', async e => { e.preventDefault(); if (busy || uncertain || !writable || !name.value.trim()) return; busy = true; sync(); status.textContent = 'Guardando selección…';
    try { await api.request(prefix, 'POST', {name: name.value.trim(), query: query.value, concepts: lines(tags.value), types: category ? [category] : [], limit: 500}, signal);
      if (!signal.aborted) { await load(name.value.trim()); status.textContent = 'Selección guardada. Prepárala antes de preguntar.'; } }
    catch (e) { if (!signal.aborted) status.textContent = error(e); } finally { busy = false; if (!signal.aborted) sync(); }
  });
  const builder = node('details'); builder.className = 'corpus-builder'; builder.open = true;
  builder.append(node('summary', 'Crear una selección de memorias'), form);
  const questionForm = node('form'); const question = field(questionForm, 'Pregunta sobre este corpus', 'corpus-question', true); question.required = true;
  const ask = node('button', 'Enviar al modelo'); ask.type = 'submit'; ask.className = 'button primary'; questionForm.append(ask);
  const show = (answer: Answer) => {
    if (answer.status === 'failed' || answer.status === 'invalidated') {
      uncertain = undefined;
      status.textContent = answer.status === 'invalidated' ? 'La generación o sus fuentes cambiaron. Actualiza el corpus y vuelve a prepararlo; no se reutilizará esta respuesta.' : `La generación terminó con un fallo.${answer.error_code ? ` Código: ${answer.error_code}.` : ''} No se reenvía automáticamente. Revisa la consulta y el presupuesto antes de solicitar otra.`;
      if (answer.status === 'invalidated') { const c = current(); if (c) c.primed = false; }
      return;
    }
    if (answer.status !== 'completed' && answer.status !== 'no_evidence') { status.textContent = `Resultado ${answer.status}. Se conserva ${answer.request_id}; comprueba el estado sin reenviar.`; return; }
    uncertain = undefined; const card = node('article'); card.className = 'result-card';
    card.append(node('h3', answer.status === 'no_evidence' ? 'No hay evidencia suficiente' : 'Respuesta generada · Sin validar'));
    if (answer.result) { card.append(node('p', answer.result.answer)); for (const citation of answer.result.citations) { const quote = node('blockquote', citation.quote); card.append(quote, node('p', citation.ref)); } }
    card.append(node('p', `Modelo: ${answer.model} · Generación ${answer.generation} · Reserva ${answer.reserved_token_units} unidades de admisión. No es un coste facturado.`));
    output.append(card); status.textContent = 'Consulta terminada. Revisa las citas y contrasta la respuesta.';
    card.tabIndex = -1; card.focus({preventScroll: true}); card.scrollIntoView({block: 'nearest'});
  };
  const reconcile = button('Comprobar consulta pendiente', () => { if (!uncertain || busy) return; const intent = uncertain; busy = true; sync();
    void api.request<Answer>(`${prefix}/${encodeURIComponent(intent.name)}/answers/${encodeURIComponent(intent.request_id)}`, 'GET', undefined, signal)
      .then(result => { if (!signal.aborted) show(result); }).catch(e => { if (!signal.aborted) status.textContent = error(e); })
      .finally(() => { busy = false; if (!signal.aborted) sync(); }); });
  questionForm.addEventListener('submit', async e => { e.preventDefault(); const c = current(); if (!c?.primed || !c.session_id || busy || uncertain || !writable || !question.value.trim()) return;
    uncertain = {name: c.name, question: question.value.trim(), request_id: crypto.randomUUID(), expected_session_id: c.session_id, expected_generation: c.version}; const intent = uncertain;
    busy = true; sync(); status.textContent = 'El modelo está preparando una respuesta con las fuentes seleccionadas…';
    try { const {name: selectedName, ...body} = intent; const result = await api.request<Answer>(`${prefix}/${encodeURIComponent(selectedName)}/answers`, 'POST', body, signal); if (!signal.aborted) show(result); }
    catch (e) { if (!signal.aborted) status.textContent = `${error(e)} Conserva el identificador ${intent.request_id}. Comprueba el estado antes de enviar otra pregunta.`; }
    finally { busy = false; if (!signal.aborted) sync(); }
  });
  select.addEventListener('change', () => { output.replaceChildren(); sync(); });
  controls.append(corpusLabel, detail, prime, fresh, rebuild, refresh, builder, questionForm, reconcile, status);
  target.replaceChildren(controls, output); sync(); void load().catch(e => { if (!signal.aborted) status.textContent = error(e); });
}
