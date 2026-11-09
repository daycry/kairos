import { MemoryApi, MemoryApiError } from './memory-api.ts';
import { categoryColors, groupKey } from './map-colors.ts';
import type { SearchInput, Source } from './memory-types.ts';

export interface MemoryMapNode {
  id: string; name: string; type: 'memory' | 'document' | 'entity'; project_id: string;
  category?: string; tags?: string[]; ref?: string; validation_status?: string; source?: Source;
}
export interface MemoryMapLink { source: string; target: string; label: string; project_id: string; evidence_refs?: string[] }
export interface MemoryMapData {
  nodes: MemoryMapNode[]; links: MemoryMapLink[];
  stats: { nodes: number; links: number; memories: number; documents: number; entities: number };
  partial: boolean;
}
interface GraphInstance {
  graphData(data: { nodes: MemoryMapNode[]; links: MemoryMapLink[] }): GraphInstance;
  backgroundColor(value: string): GraphInstance;
  nodeLabel(value: (node: MemoryMapNode) => HTMLElement): GraphInstance;
  nodeColor(value: (node: MemoryMapNode) => string): GraphInstance;
  nodeVal(value: (node: MemoryMapNode) => number): GraphInstance;
  nodeOpacity(value: number): GraphInstance;
  linkColor(value: string): GraphInstance;
  linkWidth(value: number): GraphInstance;
  linkLabel(value: (link: MemoryMapLink) => HTMLElement): GraphInstance;
  onNodeClick(value: (node: MemoryMapNode) => void): GraphInstance;
  width(value: number): GraphInstance; height(value: number): GraphInstance;
  cooldownTicks(value: number): GraphInstance;
  enableNodeDrag(value: boolean): GraphInstance;
  zoomToFit(duration?: number, padding?: number): GraphInstance;
  pauseAnimation(): GraphInstance; resumeAnimation(): GraphInstance;
  _destructor?: () => void;
  renderer?: () => { dispose(): void; forceContextLoss?: () => void };
}
export interface MemoryMapOptions {
  target: HTMLElement; api: MemoryApi; input: SearchInput; signal: AbortSignal;
  openSource: (node: MemoryMapNode) => void; announce: (message: string) => void;
  loadRenderer?: () => Promise<{ default: unknown }>;
}
const typeNames: Record<MemoryMapNode['type'], string> = { memory: 'Memoria', document: 'Documento', entity: 'Entidad' };
const validationNames: Record<string, string> = { validated: 'Validado', observed: 'Observado', unverified: 'Sin validar', unknown: 'Estado desconocido' };

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text?: string): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag); n.className = className; if (text !== undefined) n.textContent = text; return n;
}
function button(label: string, action: () => void): HTMLButtonElement { const b = el('button', 'button secondary', label); b.type = 'button'; b.addEventListener('click', action); return b; }

/** Keep only links whose endpoints are in this response. Never join by a name across projects. */
export function graphSnapshot(data: MemoryMapData): MemoryMapData {
  if (!Array.isArray(data.nodes) || !Array.isArray(data.links)) throw new MemoryApiError(502, 'invalid_graph');
  const nodes = data.nodes.filter(node => typeof node.id === 'string' && typeof node.name === 'string' &&
    ['memory', 'document', 'entity'].includes(node.type) && typeof node.project_id === 'string').map(node => ({ ...node, tags: [...(node.tags ?? [])] }));
  const byId = new Map(nodes.map(node => [node.id, node]));
  if (byId.size !== nodes.length) throw new MemoryApiError(502, 'duplicate_graph_id');
  const links = data.links.filter(edge => typeof edge.source === 'string' && typeof edge.target === 'string' && typeof edge.label === 'string' &&
    byId.has(edge.source) && byId.has(edge.target) && byId.get(edge.source)!.project_id === edge.project_id && byId.get(edge.target)!.project_id === edge.project_id)
    .map(edge => ({ ...edge, evidence_refs: [...(edge.evidence_refs ?? [])] }));
  // Counters describe exactly this bounded snapshot, including omitted bad edges.
  return { nodes, links, stats: { nodes: nodes.length, links: links.length, memories: nodes.filter(n => n.type === 'memory').length,
    documents: nodes.filter(n => n.type === 'document').length, entities: nodes.filter(n => n.type === 'entity').length }, partial: !!data.partial || links.length !== data.links.length || nodes.length !== data.nodes.length };
}
export function mapColors(nodes: MemoryMapNode[]): Map<string, string> {
  const groups = new Map<string, { project: string; category: string; key: string; documents: number }>();
  for (const node of nodes) { const category = node.category || 'Sin categoría'; const key = groupKey(node.project_id, category); if (!groups.has(key)) groups.set(key, { key, project: node.project_id, category, documents: 0 }); groups.get(key)!.documents++; }
  const colors = categoryColors([...groups.values()]);
  return new Map(nodes.map(node => [node.id, colors.get(groupKey(node.project_id, node.category || 'Sin categoría')) ?? '#a4b3c5']));
}
export function graphNodeLabel(node: MemoryMapNode): HTMLElement {
  const label = el('div', 'map-tooltip'); label.append(el('strong', '', node.name), el('span', '', `${typeNames[node.type]} · ${node.project_id} · ${node.category || 'Sin categoría'}`)); return label;
}

/** Owns all renderer state and subscriptions. Calling dispose never leaves a GPU loop alive. */
export function mountMemoryMap(options: MemoryMapOptions): { dispose(): void; refresh(): Promise<void> } {
  const { target, signal, api } = options;
  let disposed = false; let request = 0; let requestController: AbortController | undefined;
  let graph: GraphInstance | undefined; let observer: ResizeObserver | undefined;
  let data: MemoryMapData | undefined; let mode: 'graph' | 'list' = 'graph';
  let graphToken = 0; let selectedId = '';
  const controls = el('div', 'map-toolbar');
  const retry = button('Actualizar mapa', () => void refresh());
  const fit = button('Centrar mapa', () => graph?.zoomToFit(0, 45)); fit.disabled = true;
  const switchView = button('Usar vista de lista', () => { mode = mode === 'graph' ? 'list' : 'graph'; switchView.textContent = mode === 'graph' ? 'Usar vista de lista' : 'Mostrar mapa 3D'; if (data) render(data); });
  controls.append(retry, fit, switchView);
  const state = el('div', 'map-status'); state.setAttribute('role', 'status');
  const body = el('div', 'map-body'); target.replaceChildren(controls, state, body);
  function disposeGraph(): void {
    graphToken++; observer?.disconnect(); observer = undefined; fit.disabled = true;
    if (graph) { const old = graph; graph = undefined; old.pauseAnimation();
      if (old._destructor) old._destructor(); else { old.renderer?.().dispose(); old.renderer?.().forceContextLoss?.(); }
    }
  }
  function dispose(): void { if (disposed) return; disposed = true; requestController?.abort(); disposeGraph(); signal.removeEventListener('abort', dispose); document.removeEventListener('visibilitychange', visibility); }
  function visibility(): void { if (document.hidden) graph?.pauseAnimation(); else graph?.resumeAnimation(); }
  signal.addEventListener('abort', dispose, { once: true }); document.addEventListener('visibilitychange', visibility);
  function open(node: MemoryMapNode): void { selectedId = node.id; if (node.ref) options.openSource(node); else state.textContent = 'Esta entidad no tiene una ficha propia. Abre la evidencia de una de sus relaciones.'; }
  function render(snapshot: MemoryMapData): void {
    disposeGraph(); body.replaceChildren();
    const colors = mapColors(snapshot.nodes); const counters = el('div', 'map-counters');
    for (const [key, label] of [['memories', 'Memorias'], ['documents', 'Documentos'], ['entities', 'Entidades'], ['links', 'Relaciones']] as const) {
      const count = el('div', 'counter'); count.append(el('strong', '', snapshot.stats[key].toLocaleString('es')), el('span', '', label)); counters.append(count);
    }
    body.append(counters, el('p', 'hint', 'Cifras de este mapa acotado (hasta 100 elementos solicitados). Las líneas representan relaciones con su procedencia; el color identifica proyecto y categoría, no validación.'));
    if (snapshot.partial) body.append(el('p', 'callout', 'Mapa parcial: parte de las fuentes o relaciones no está disponible.'));
    if (!snapshot.nodes.length) { body.append(el('div', 'state', 'No hay elementos para este ámbito. Amplía la categoría o guarda memoria con su fuente.')); return; }
    const legend = el('div', 'map-legend'); const groups = new Set<string>();
    for (const node of snapshot.nodes) { const key = groupKey(node.project_id, node.category || 'Sin categoría'); if (groups.has(key)) continue; groups.add(key);
      const item = el('span', 'map-legend-item'); const swatch = el('span', 'map-swatch'); swatch.style.backgroundColor = colors.get(node.id)!; swatch.setAttribute('aria-hidden', 'true'); item.append(swatch, el('span', '', `${node.project_id} / ${node.category || 'Sin categoría'}`)); legend.append(item);
    } body.append(legend);
    if (mode === 'graph') { const canvas = el('div', 'memory-map-canvas'); canvas.setAttribute('aria-hidden', 'true'); body.append(canvas); void renderGraph(snapshot, colors, canvas); }
    const accessible = el('section', 'map-accessible panel'); accessible.setAttribute('aria-label', 'Elementos y relaciones del mapa'); accessible.append(el('h2', '', 'Elementos y relaciones'), el('p', 'hint', 'Esta lista permite recorrer todo el mapa con teclado. Abre un elemento o la evidencia de una relación para consultar su fuente.'));
    const filterId = `map-filter-${crypto.randomUUID()}`; const filterLabel = el('label', '', 'Filtrar elementos del mapa'); filterLabel.htmlFor = filterId;
    const filter = el('input'); filter.id = filterId; filter.type = 'search'; filter.name = 'map-node-filter';
    const list = el('div', 'map-node-list'); const links = el('div', 'map-edge-list');
    const byId = new Map(snapshot.nodes.map(node => [node.id, node]));
    const drawList = () => {
      list.replaceChildren(); links.replaceChildren(); const query = filter.value.toLocaleLowerCase();
      const visible = snapshot.nodes.filter(node => `${node.name} ${node.project_id} ${node.category ?? ''} ${(node.tags ?? []).join(' ')}`.toLocaleLowerCase().includes(query)); const ids = new Set(visible.map(n => n.id));
      for (const node of visible) {
        const row = el('article', 'map-node-row'); const swatch = el('span', 'map-swatch'); swatch.style.backgroundColor = colors.get(node.id)!; swatch.setAttribute('aria-hidden', 'true');
        const heading = el('h3'); const choose = button(node.name, () => open(node)); choose.className = 'title-button'; heading.append(choose);
        row.append(swatch, heading, el('p', 'hint', `${typeNames[node.type]} · ${node.project_id} · ${node.category || 'Sin categoría'} · ${validationNames[node.validation_status ?? 'unknown'] ?? 'Estado desconocido'}`)); list.append(row);
      }
      const edges = snapshot.links.filter(edge => ids.has(edge.source) && ids.has(edge.target));
      links.append(el('h3', '', `${edges.length} relaciones visibles`));
      for (const edge of edges) {
        const row = el('article', 'map-edge-row'); row.append(el('p', '', `${byId.get(edge.source)!.name} → ${edge.label} → ${byId.get(edge.target)!.name}`), el('p', 'hint', `Proyecto: ${edge.project_id}`));
        const evidence = edge.evidence_refs ?? [];
        if (evidence.length) evidence.forEach((ref, index) => row.append(button(`Abrir evidencia ${index + 1}`, () => options.openSource({ id: ref, ref, name: `Evidencia: ${edge.label}`, type: 'entity', project_id: edge.project_id }))));
        else row.append(el('p', 'hint', 'Sin referencia de evidencia disponible.')); links.append(row);
      }
      if (!visible.length) list.append(el('p', 'hint', 'Ningún elemento coincide con el filtro.'));
    };
    filter.addEventListener('input', drawList); accessible.append(filterLabel, filter, list, links); body.append(accessible); drawList();
  }
  async function renderGraph(snapshot: MemoryMapData, colors: Map<string, string>, canvas: HTMLElement): Promise<void> {
    const current = graphToken; state.textContent = 'Preparando el mapa. La lista ya está disponible.';
    let instance: GraphInstance | undefined;
    try {
      const module = await (options.loadRenderer ?? (() => import('3d-force-graph')))();
      if (disposed || signal.aborted || current !== graphToken) return;
      const Constructor = module.default as new (target: HTMLElement) => GraphInstance;
      instance = new Constructor(canvas); graph = instance;
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      instance.backgroundColor('#080c14').nodeLabel(graphNodeLabel).nodeColor(node => colors.get(node.id) ?? '#a4b3c5')
        .nodeVal(node => node.type === 'entity' ? 1.5 : 3).nodeOpacity(.95).linkColor('#91a8b8').linkWidth(.65)
        .linkLabel(edge => el('span', 'map-tooltip', edge.label)).onNodeClick(open).cooldownTicks(reduced ? 0 : 100).enableNodeDrag(!reduced)
        .width(canvas.clientWidth || 600).height(canvas.clientHeight || 440)
        .graphData({ nodes: snapshot.nodes.map(n => ({ ...n })), links: snapshot.links.map(edge => ({ ...edge })) });
      observer = new ResizeObserver(() => { if (!disposed && graph === instance) instance!.width(canvas.clientWidth).height(canvas.clientHeight); }); observer.observe(canvas);
      fit.disabled = false; if (document.hidden) instance.pauseAnimation();
      canvas.addEventListener('webglcontextlost', () => {
        if (disposed || current !== graphToken) return; disposeGraph(); canvas.replaceChildren(el('p', 'map-fallback', 'La vista 3D no está disponible. Puedes seguir usando la lista de elementos y relaciones.')); state.textContent = 'Se ha perdido la vista 3D. La lista conserva el mismo mapa.';
      }, { once: true });
      state.textContent = selectedId ? 'Mapa actualizado. La selección conserva su referencia de origen.' : 'Mapa listo. Selecciona un elemento o recorre la lista para abrir su fuente.';
    } catch {
      if (disposed || signal.aborted || current !== graphToken) return;
      disposeGraph(); canvas.replaceChildren(el('p', 'map-fallback', 'La vista 3D no está disponible en este navegador. El mismo contenido está en la lista de elementos y relaciones.'));
      state.textContent = 'Puedes usar la lista o volver a intentar la vista 3D.';
      canvas.append(button('Reintentar vista 3D', () => { if (data) render(data); }));
    }
  }
  async function refresh(): Promise<void> {
    if (disposed || signal.aborted) return; requestController?.abort(); requestController = new AbortController(); const local = requestController; const current = ++request;
    disposeGraph(); state.textContent = 'Cargando los elementos del mapa…'; body.replaceChildren(); target.setAttribute('aria-busy', 'true'); retry.disabled = true;
    try {
      const response = await api.request<MemoryMapData>('/v1/graph', 'POST', { ...options.input, limit: 100 }, local.signal);
      if (disposed || local.signal.aborted || current !== request) return; data = graphSnapshot(response); render(data);
      if (mode === 'list' || !data.nodes.length) state.textContent = data.nodes.length ? 'Lista del mapa actualizada.' : 'Sin elementos en este ámbito.';
      options.announce(`${data.stats.nodes} elementos y ${data.stats.links} relaciones recibidas.`);
    } catch (error) {
      if (disposed || local.signal.aborted || current !== request) return;
      state.textContent = error instanceof MemoryApiError ? `${error.message}${error.requestId ? ` Referencia: ${error.requestId}.` : ''}` : 'No se pudo cargar el mapa. Vuelve a intentarlo.';
      body.append(el('p', 'state error', 'El mapa no se ha podido recuperar.'), button('Volver a intentar', () => void refresh()));
    } finally { if (!disposed && current === request) { target.setAttribute('aria-busy', 'false'); retry.disabled = false; } }
  }
  if (!signal.aborted) void refresh(); else dispose();
  return { dispose, refresh };
}
