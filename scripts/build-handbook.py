"""Render the product's own Markdown into an offline handbook and handoff archive."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata
import zipfile

PAGES = {'index.md': 'index.html', 'README.md': 'documentacion.html', 'RAG-INDEX.md': 'mantenimiento.html', 'manual.md': 'manual-kairos.html',
         'install.md': 'instalar-kairos.html', 'integration.md': 'custom-agents.html',
         'operations.md': 'operaciones.html', 'architecture.md': 'arquitectura.html',
         'extended-workflows.md': 'observaciones-equipo.html', 'corpus-generated-answers.md': 'consultas-corpus.html',
         'code-analysis.md': 'analisis-codigo.html', 'release-cli.md': 'entrega-cli.html',
         'server-install.md': 'servidor-desde-cero.html', 'configuration.md': 'configuracion.html'}
IMAGE_TYPES = {'.jpg', '.jpeg', '.png', '.webp'}
STYLE = '''
:root{color-scheme:light dark;font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--bg:#faf9f6;--ink:#242b2b;--line:#deded7;--accent:#11694f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}a{color:var(--accent);text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
header{padding:20px max(24px,calc((100% - 1200px)/2));border-bottom:1px solid var(--line)}header a{font-size:24px;font-weight:700;text-decoration:none}header p{margin:0;font-size:13px}
.layout{max-width:1200px;margin:auto;display:grid;grid-template-columns:230px minmax(0,1fr);gap:48px;padding:40px 24px}aside{font-size:14px;position:sticky;top:24px;align-self:start;max-height:90vh;overflow:auto}aside a,.mobile-toc a{display:block;padding:5px 0}main{min-width:0;max-width:850px}h1{font-size:clamp(28px,4vw,42px);line-height:1.15;letter-spacing:-.04em}h2{margin-top:48px;line-height:1.3}h3{margin-top:32px}p,li,a,code{overflow-wrap:anywhere}pre{overflow:auto;padding:20px;background:color-mix(in srgb,var(--ink) 5%,var(--bg));border:1px solid var(--line);border-radius:12px;max-width:100%}pre code{white-space:pre;overflow-wrap:normal;font-size:13px}code{font-size:.9em}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid var(--line);padding:10px;text-align:left}img{display:block;max-width:100%;height:auto;margin:24px 0;border:1px solid var(--line);border-radius:12px}blockquote{margin-left:0;border-left:3px solid var(--accent);padding-left:20px}.skip{position:absolute;left:-10000px}.skip:focus{left:20px;top:5px;background:var(--bg)}.mobile-toc{display:none}.repo-ref{font-family:monospace}.muted{opacity:.7}footer{border-top:1px solid var(--line);padding:24px;font-size:13px}
@media(max-width:760px){.layout{display:block;padding:24px 18px}.layout>aside{display:none}.mobile-toc{display:block;margin-bottom:28px;border:1px solid var(--line);border-radius:10px;padding:14px}summary{cursor:pointer}td,th{min-width:130px}h2{margin-top:32px}}
@media(prefers-color-scheme:dark){:root{--bg:#101717;--ink:#e1eae6;--line:#30403a;--accent:#99e3c8}}
'''


def render(source, navigation):
    from markdown_it import MarkdownIt
    parser = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = parser.parse(source)
    headings, used = [], set()
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            label = tokens[i+1].content
            slug = re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', label).encode('ascii', 'ignore').decode().lower()).strip('-') or 'seccion'
            unique, n = slug, 1
            while unique in used:
                n += 1
                unique = slug+'-'+str(n)
            used.add(unique)
            token.attrSet('id', unique)
            if token.tag == 'h2':
                headings.append((unique, label))
        for child in token.children or []:
            if child.type == 'link_open':
                href = child.attrGet('href') or ''
                if href.endswith('.md') or '.md#' in href:
                    path, _, anchor = href.partition('#')
                    name = PAGES.get(path.removeprefix('./'))
                    if name:
                        child.attrSet('href', name + ('#'+anchor if anchor else ''))
                    else:
                        child.attrs.pop('href', None)
                        child.attrSet('class', 'repo-ref')
                        child.attrSet('title', 'Archivo de la distribución de código')
                elif href in ('contracts/kairos-mcp.json', 'contracts/memory-platform.openapi.json'):
                    child.attrSet('href', Path(href).name)
                elif href.startswith('../'):
                    # Source files are in the distribution repository, not on
                    # the public web server. Keep their labels without a 404.
                    child.attrs.pop('href', None)
                    child.attrSet('class', 'repo-ref')
                    child.attrSet('title', 'Archivo de la distribución de código')
    title = next((tokens[i+1].content for i, t in enumerate(tokens) if t.type == 'heading_open' and t.tag == 'h1'), 'Kairos')
    if sum(t.type == 'heading_open' and t.tag == 'h1' for t in tokens) != 1:
        raise ValueError('Each handbook page requires exactly one H1')
    body = parser.renderer.render(tokens, parser.options, {})
    body = body.replace('<table>', '<div class="table-wrap"><table>').replace('</table>', '</table></div>')
    toc = ''.join('<a href="#'+key+'">'+html.escape(label)+'</a>' for key, label in headings)
    return ('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="no-referrer"><title>'+html.escape(title)+' · Kairos</title><style>'+STYLE+'</style>'
            '<a class="skip" href="#contenido">Ir al contenido</a><header><a href="index.html">Kairos</a><p>Memoria de agentes · Manual de producto</p></header>'
            '<div class="layout"><aside aria-label="Manuales">'+navigation+'<hr>'+toc+'</aside><main id="contenido">'
            '<details class="mobile-toc"><summary>En esta documentación</summary>'+navigation+toc+'</details>'+body+'</main></div>'
            '<footer>Documentación incluida en esta distribución. No necesita conexión a servicios externos.</footer></html>')


def build(root, output):
    output = output.absolute()
    for path in (output, *output.parents):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Handbook output cannot traverse symlinks or junctions')
    output.mkdir(parents=True, exist_ok=True)
    docs = root / 'docs'
    nav = ''.join('<a href="'+name+'">'+html.escape(label)+'</a>' for name, label in
                  [('index.html', 'Índice'), ('manual-kairos.html', 'Manual de uso'), ('servidor-desde-cero.html', 'Servidor desde cero'),
                   ('configuracion.html', 'Configuración'), ('instalar-kairos.html', 'Clientes'),
                   ('custom-agents.html', 'Integración'), ('observaciones-equipo.html', 'Observaciones y equipo'),
                   ('consultas-corpus.html', 'Consultas de corpus'), ('analisis-codigo.html', 'Análisis local'),
                   ('entrega-cli.html', 'Entrega CLI'), ('operaciones.html', 'Operación'), ('arquitectura.html', 'Arquitectura')])
    records = {}
    for source, destination in PAGES.items():
        data = render((docs/source).read_text(encoding='utf-8'), nav).encode('utf-8')
        (output/destination).write_bytes(data)
        records[destination] = hashlib.sha256(data).hexdigest()
    for source in sorted((docs/'contracts').glob('*.json')):
        data = source.read_bytes()
        json.loads(data)
        (output/source.name).write_bytes(data)
        records[source.name] = hashlib.sha256(data).hexdigest()
    # Screenshots referenced by the manuals. Only plain image files directly
    # under docs/assets/screenshots are copied; links and other types are refused.
    screenshots = docs/'assets'/'screenshots'
    images = sorted(screenshots.glob('*')) if screenshots.is_dir() else []
    for image in images:
        if image.is_symlink() or not image.is_file() or image.suffix.lower() not in IMAGE_TYPES:
            raise ValueError('Unexpected handbook asset: '+image.name)
        data = image.read_bytes()
        target = output/'assets'/'screenshots'/image.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records['assets/screenshots/'+image.name] = hashlib.sha256(data).hexdigest()
    if 'memory-platform.openapi.json' not in records or 'kairos-mcp.json' not in records:
        raise ValueError('Export native contracts before building the handbook')
    with zipfile.ZipFile(output/'kairos-custom-agents.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        # Public handoff is an allowlist of manuals and contracts. Project
        # roadmaps, private notes and knowledge candidates are never exported.
        sources = [docs/name for name in PAGES] + sorted((docs/'contracts').glob('*.json')) + images
        for source in sources:
            info = zipfile.ZipInfo('docs/'+source.relative_to(docs).as_posix(), (2026, 11, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
    (output/'manifest.json').write_text(json.dumps({'product': 'Kairos', 'files': records}, indent=2)+'\n', encoding='utf-8')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = build(root, args.output or root/'web/public/handbook')
    print('Kairos handbook generated: '+str(len(result))+' verified files.')
