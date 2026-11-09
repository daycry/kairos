"""Real browser E2E within a build-owned local PostgreSQL/HTTP environment.

QA_BLOB stdout records export evidence without Docker daemon volume access.
No sleeps/networkidle in browser assertions; selectors use accessible names.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import traceback
import uuid
from playwright.sync_api import sync_playwright, expect
from memory_platform.tests.e2e_fixture import start, BASE, PASSWORD

OUT=Path('/qa')
results=[]

def check(name, function, page):
    try:
        function()
        result={'title':name,'status':'passed'}
    except Exception as exc:
        result={'title':name,'status':'failed','error':str(exc)[:1600]}
        print(traceback.format_exc()[:1800],flush=True)
    path=OUT/(name+'.jpg')
    page.screenshot(path=str(path),type='jpeg',quality=25,full_page=False)
    if path.stat().st_size>25000:
        page.screenshot(path=str(path),type='jpeg',quality=10,full_page=False)
    result['screenshot']=path.name
    results.append(result)
    print('QA_CASE '+json.dumps({k:v for k,v in result.items() if k!='error'},ensure_ascii=False),flush=True)

def login(page,user='alice'):
    page.goto(BASE+'/portal.html?project=project-a')
    page.get_by_label('Usuario',exact=True).fill(user)
    page.get_by_label('Contraseña',exact=True).fill(PASSWORD)
    page.get_by_role('button',name='Entrar',exact=True).click()
    expect(page.get_by_role('button',name='Salir',exact=True)).to_be_visible()

def run_browser(store,admin):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context=browser.new_context(viewport={'width':1280,'height':900},locale='es-ES',timezone_id='Europe/Madrid')
        context.tracing.start(screenshots=True,snapshots=True,sources=True)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        requests=[]
        page.on('request',lambda r:requests.append(r.url))
        def public_site():
            page.goto(BASE+'/')
            expect(page.locator('h1')).to_contain_text('El contexto adecuado.')
            assert page.locator('#memory-app').count()==0
            assert 'Kairos' in page.locator('body').inner_text()
            assert not any('/memory-api/' in url or 'memory-map-' in url for url in requests)
            page.get_by_role('navigation',name='Navegación principal',exact=True).get_by_role('link',name='Documentación',exact=True).click()
            expect(page).to_have_url(BASE+'/docs/')
            expect(page.locator('h1')).to_contain_text('Todo lo necesario')
            for href in page.locator('.docs-navigation a').evaluate_all('(links)=>links.map(a=>a.getAttribute("href"))'):
                assert page.locator(href).count()==1
            assert not any('/memory-api/' in url for url in requests)
            for asset in ('kairos-logo.png', 'kairos-logo-dark.png', 'kairos-symbol.png'):
                response=context.request.get(BASE+'/brand/'+asset)
                assert response.status==200 and response.body().startswith(b'\x89PNG\r\n\x1a\n')
            page.goto(BASE+'/')
            page.keyboard.press('Tab')
            expect(page.get_by_role('link',name='Ir al contenido',exact=True)).to_be_focused()
            page.keyboard.press('Enter')
            expect(page).to_have_url(BASE+'/#contenido')
        check('E2E-08-public-home-docs-private-boundary',public_site,page)
        def public_mobile():
            page.set_viewport_size({'width':375,'height':812})
            page.goto(BASE+'/')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            summary=page.locator('.mobile-navigation > summary')
            summary.click()
            mobile=page.get_by_role('navigation',name='Navegación móvil',exact=True)
            expect(mobile.get_by_role('link',name='Documentación',exact=True)).to_be_visible()
            summary.press('Escape')
            expect(mobile).not_to_be_visible()
            expect(summary).to_be_focused()
            summary.click()
            mobile.get_by_role('link',name='Documentación',exact=True).click()
            expect(page.locator('h1')).to_contain_text('Todo lo necesario')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.goto(BASE+'/')
        check('E2E-09-public-mobile-menu-keyboard',public_mobile,page)
        page.set_viewport_size({'width':1280,'height':900})
        def public_login():
            page.goto(BASE+'/')
            page.get_by_role('link',name='Iniciar sesión',exact=False).first.click()
            expect(page).to_have_url(BASE+'/app/')
            expect(page.get_by_label('Usuario',exact=True)).to_be_visible()
            expect(page.get_by_label('Contraseña',exact=True)).to_be_visible()
            page.get_by_label('Usuario',exact=True).fill('alice')
            page.get_by_label('Contraseña',exact=True).fill(PASSWORD)
            page.get_by_role('button',name='Entrar',exact=True).click()
            expect(page.get_by_role('heading',name='Memoria y aprendizajes',exact=True)).to_be_visible()
            page.get_by_role('button',name='Salir',exact=True).click()
        check('E2E-10-home-login-memory-default',public_login,page)
        def auth():
            login(page)
            assert all('SECRETO B' not in x for x in [page.locator('body').inner_text()])
            assert context.cookies()[0]['httpOnly']
            assert page.evaluate('Object.keys(localStorage)') == []
            assert not any('memory-map-' in url or '3d-force' in url for url in requests)
            assert context.request.post(BASE+'/memory-api/v1/search',data={'project_ids':['project-a'],'q':''}).status==403
            me=context.request.get(BASE+'/memory-api/v1/auth/me').json()
            headers={'Origin':'http://invalid.local','X-CSRF-Token':me['csrf_token']}
            assert context.request.post(BASE+'/memory-api/v1/search',data={'project_ids':['project-a'],'q':''},headers=headers).status==403
            headers['Origin']=BASE
            assert context.request.post(BASE+'/memory-api/v1/search',data={'project_ids':['project-b'],'q':''},headers=headers).status==404
            page.reload()
            expect(page.get_by_role('button',name='Salir',exact=True)).to_be_visible()
        check('E2E-01-auth-acl-reload',auth,page)
        def work_board():
            from memory_platform.agent_store import AgentStore
            with store.transaction() as c:
                alice = c.execute("SELECT id FROM memory.actors WHERE username='alice'").fetchone()
            service = AgentStore(store)
            service.work_write({'id': alice['id'], 'credential_type': 'bootstrap'}, 'project-a', 'Entrega: "\u00c1rbol" \U0001f333',
                               {'task': 'Conservar nota:uno,dos', 'status': 'doing'}, 'qa-work-1', 0)
            page.goto(BASE+'/portal.html?project=project-a&view=work')
            expect(page.get_by_role('heading', name='Mi trabajo', exact=True)).to_be_visible()
            expect(page.get_by_role('heading', name='Entrega: "\u00c1rbol" \U0001f333', exact=True)).to_be_visible()
            page.get_by_text('Ver tareas y detalles', exact=True).click()
            expect(page.get_by_text('Conservar nota:uno,dos', exact=True)).to_be_visible()
            page.get_by_role('button', name='Completar', exact=True).click()
            expect(page.get_by_text('1 de 1 tareas finalizadas', exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_text('1 de 1 tareas finalizadas', exact=True)).to_be_visible()
            page.get_by_role('combobox', name='Estado del trabajo', exact=True).select_option('doing')
            expect(page.get_by_role('heading', name='Sin coincidencias', exact=True)).to_be_visible()
            page.get_by_role('combobox', name='Estado del trabajo', exact=True).select_option('done')
            expect(page.get_by_role('heading', name='Entrega: "\u00c1rbol" \U0001f333', exact=True)).to_be_visible()
            page.get_by_role('button', name='Memoria y aprendizajes', exact=True).click()
        check('E2E-11-work-mcp-domain-ui-persistence',work_board,page)
        def note():
            page.get_by_role('button',name='Nueva memoria',exact=False).click()
            d=page.get_by_role('dialog')
            # Inspect the real rendered controls before interacting.
            assert d.get_by_label('Proyecto',exact=True).evaluate('(s)=>s.tagName')=='SELECT'
            d.get_by_label('Título',exact=True).fill('Prueba <b>literal</b> ñ, memoria')
            d.get_by_label('Contenido y contexto aplicable',exact=True).fill('Evidencia sintética sin secretos. Persistencia después de recarga.')
            d.get_by_label('Sesión de origen',exact=True).fill('qa-session')
            d.get_by_label('Etiquetas',exact=True).fill('coma, conservada\nUnicode ñ')
            d.get_by_label('Categoría',exact=True).fill('Arquitectura')
            d.get_by_role('button',name='Guardar memoria',exact=True).click()
            expect(d.get_by_role('status')).to_contain_text('Recibido')
            page.keyboard.press('Escape')
            expect(d).not_to_be_visible()
            page.get_by_role('button',name='Memoria y aprendizajes',exact=True).click()
            expect(page.get_by_text('Prueba <b>literal</b> ñ, memoria',exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_text('Prueba <b>literal</b> ñ, memoria',exact=True)).to_be_visible()
            assert page.locator('b').count()==0
        check('E2E-02-note-persistence-unicode',note,page)
        def capture_off():
            page.goto(BASE+'/portal.html?project=capture-off&view=memory')
            page.get_by_role('button',name='Nueva memoria',exact=False).click()
            d=page.get_by_role('dialog')
            expect(d).to_contain_text('Captura desactivada')
            d.get_by_label('Título',exact=True).fill('Nota que no debe transmitirse')
            d.get_by_label('Contenido y contexto aplicable',exact=True).fill('No guardar con captura off')
            d.get_by_label('Sesión de origen',exact=True).fill('off-session')
            submitted=[]
            listener=lambda request:submitted.append(request.url) if request.url.endswith('/v1/events') else None
            page.on('request',listener)
            d.get_by_role('button',name='Guardar memoria',exact=True).click()
            expect(d.get_by_role('status')).to_contain_text('captura está desactivada')
            assert submitted==[]
            page.remove_listener('request',listener)
            page.keyboard.press('Escape')
        check('E2E-02-capture-off-no-transmission',capture_off,page)
        def correction_delete():
            from memory_platform.tests.test_store import event
            import uuid
            original=event('project-a',generate=False,payload={'title':'Aprendizaje anterior QA','content':'Regla antigua sintética'})
            store.ingest_event(admin,original)
            page.goto(BASE+'/portal.html?project=project-a&view=memory')
            page.get_by_role('button',name='Nueva memoria',exact=False).click()
            d=page.get_by_role('dialog')
            d.get_by_label('Tipo de memoria',exact=True).select_option('correction')
            d.get_by_label('Título',exact=True).fill('Corrección vigente QA')
            d.get_by_label('Contenido y contexto aplicable',exact=True).fill('La regla vigente usa leases.')
            d.get_by_label('Sesión de origen',exact=True).fill('qa-correction')
            d.get_by_label('Problema observado',exact=True).fill('Regla antigua incompleta')
            d.get_by_label('Corrección o decisión',exact=True).fill('Usar leases')
            d.get_by_label('Evidencia',exact=True).fill('fixture://correction')
            d.get_by_label('Elemento que corrige (opcional)',exact=True).fill(original['item_id'])
            assert 'validated' not in d.get_by_label('Estado de validación',exact=True).evaluate('(s)=>Array.from(s.options).map(o=>o.value)')
            d.get_by_role('button',name='Guardar memoria',exact=True).click()
            expect(d.get_by_role('status')).to_contain_text('Recibido')
            page.keyboard.press('Escape')
            page.reload()
            current=page.get_by_role('article').filter(has=page.get_by_role('heading',name='Corrección vigente QA',exact=True))
            expect(current).to_contain_text('Sustituye al elemento')
            expect(page.get_by_role('heading',name='Aprendizaje anterior QA',exact=True)).to_have_count(0)
            corrected=next(row for row in store.list_notes(admin,'project-a',100) if row['title']=='Corrección vigente QA')
            current.get_by_role('button',name='Retirar memoria',exact=True).click()
            d=page.get_by_role('dialog')
            d.get_by_role('button',name='Confirmar retirada',exact=True).click()
            expect(d.get_by_role('status')).to_contain_text('Retirada recibida')
            page.keyboard.press('Escape')
            page.reload()
            expect(page.get_by_role('heading',name='Corrección vigente QA',exact=True)).to_have_count(0)
            # Retry the original event cannot make its superseded version current.
            store.ingest_event(admin,original)
            assert not any(n['item_id']==original['item_id'] for n in store.search_items(admin,['project-a']))
            from memory_platform.errors import Conflict
            try:
                store.ingest_event(admin,event('project-a',item_id=corrected['item_id'],version=3,generate=False))
            except Conflict:
                pass
            else:
                raise AssertionError('Tombstone unexpectedly resurrected')
            page.get_by_role('button',name='Historia',exact=True).click()
            expect(page.get_by_role('heading',name='Corrección vigente QA',exact=True).first).to_be_visible()
        check('E2E-03-correction-authority-tombstone',correction_delete,page)
        def search_context():
            page.goto(BASE+'/portal.html?project=project-a&view=search')
            page.get_by_label('¿Qué necesitas resolver?',exact=True).fill('fencing')
            page.get_by_role('button',name='Buscar',exact=True).click()
            expect(page.get_by_role('heading',name='Fuentes recuperadas',exact=True)).to_be_visible()
            episodic=page.get_by_role('article').filter(has=page.get_by_text('Memoria',exact=True))
            source=episodic.get_by_role('button',name='Decisión de origen',exact=True)
            expect(source).to_be_visible()
            source.click()
            expect(page.get_by_role('dialog')).to_contain_text('fixture://source-a')
            page.keyboard.press('Escape')
            page.get_by_role('button',name='Preparar contexto para la tarea',exact=True).click()
            expect(page.get_by_role('heading',name='Contexto para tu tarea',exact=True)).to_be_visible()
            expect(page.get_by_text('Comprueba la evidencia antes de aplicar un aprendizaje',exact=True)).to_be_visible()
            assert 'SECRETO B' not in page.locator('body').inner_text()
        check('E2E-04-real-search-context-source',search_context,page)
        def fault_retry():
            page.route('**/memory-api/v1/notes?*',lambda route:route.abort('failed'))
            page.goto(BASE+'/portal.html?project=project-a&view=memory')
            expect(page.get_by_role('button',name='Reintentar carga',exact=True)).to_be_visible()
            page.unroute('**/memory-api/v1/notes?*')
            page.get_by_role('button',name='Reintentar carga',exact=True).click()
            expect(page.get_by_text('Decisión de origen',exact=True)).to_be_visible()
        check('E2E-04-injected-network-error-real-retry',fault_retry,page)
        def sessions_history():
            page.goto(BASE+'/portal.html?project=project-a&view=sessions')
            expect(page.get_by_role('heading',name='Sesiones y agentes',exact=True)).to_be_visible()
            expect(page.get_by_text('synthetic-session',exact=True)).to_be_visible()
            page.get_by_role('button',name='Ver memoria de esta sesión',exact=True).first.click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.keyboard.press('Escape')
            page.get_by_role('button',name='Historia',exact=True).click()
            expect(page.get_by_role('heading',name='Historia',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='Actualizar',exact=True)).to_be_enabled()
        check('E2E-03-sessions-history-provenance',sessions_history,page)
        def mapa():
            page.goto(BASE+'/portal.html?project=project-a&view=map')
            expect(page.get_by_role('button',name='Decisión de origen',exact=True)).to_be_visible()
            expect(page.locator('canvas')).to_be_visible(timeout=20000)
            assert 'SECRETO B' not in page.locator('body').inner_text()
            page.get_by_role('button',name='Decisión de origen',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('La proyección requiere fencing.')
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog')).not_to_be_visible()
        check('E2E-04-native-map-webgl-details',mapa,page)
        def mobile():
            page.set_viewport_size({'width':375,'height':812})
            page.goto(BASE+'/portal.html?project=project-a&view=memory')
            expect(page.get_by_role('button',name='Menú',exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.get_by_role('button',name='Menú',exact=True).click()
            expect(page.get_by_label('Filtrar proyectos',exact=True)).to_be_visible()
            page.get_by_label('Filtrar proyectos',exact=True).fill('inexistente')
            expect(page.get_by_role('complementary').get_by_text('Proyecto Alfa',exact=True)).not_to_be_visible()
        check('M-01-mobile-bounds-menu-filter',mobile,page)
        def operations():
            page.set_viewport_size({'width':1280,'height':900})
            page.goto(BASE+'/portal.html?project=project-a&view=operations')
            expect(page.get_by_text('Fallido',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='Reintentar pendientes',exact=True)).to_be_visible()
        check('E2E-05-real-pg-failed-job',operations,page)
        def pagination():
            from memory_platform.tests.test_store import event
            for index in range(55):
                store.ingest_event(admin,event('project-a',generate=False,payload={'title':f'Página sintética {index:02d}','content':'Contenido sintético para cursor real'}))
            expected=len(store.list_notes(admin,'project-a',100))
            page.goto(BASE+'/portal.html?project=project-a&view=memory')
            activity=page.get_by_role('region',name='Actividad en vivo',exact=True)
            # Let initial durable SSE history finish its automatic refresh.
            expect(activity.get_by_text('Memoria actualizada con la actividad recibida',exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_role('article')).to_have_count(50)
            more=page.get_by_role('button',name='Cargar más',exact=True)
            expect(more).to_be_visible()
            more.click()
            expect(page.get_by_role('article')).to_have_count(expected)
            expect(more).not_to_be_visible()
            titles=page.get_by_role('article').get_by_role('heading',level=3).all_text_contents()
            assert len(titles)==len(set(titles))
        check('E2E-06-real-pg-pagination',pagination,page)
        def activity_live():
            from memory_platform.tests.test_store import event
            page.goto(BASE+'/portal.html?project=project-a&view=memory')
            activity=page.get_by_role('region',name='Actividad en vivo',exact=True)
            expect(activity.get_by_text('Actividad en vivo conectada',exact=True)).to_be_visible(timeout=10000)
            expect(page.get_by_role('heading',name='Nueva memoria recibida por SSE',exact=True)).to_have_count(0)
            # A low UUID makes the new item part of the first real 50-row page.
            store.ingest_event(admin,event('project-a',item_id='00000000-0000-4000-8000-000000000001',generate=False,payload={'title':'Nueva memoria recibida por SSE','content':'Actualización automática desde PostgreSQL real'}))
            expect(page.get_by_role('heading',name='Nueva memoria recibida por SSE',exact=True)).to_be_visible(timeout=15000)
            expect(activity.get_by_text('Memoria actualizada con la actividad recibida',exact=True)).to_be_visible()
        check('E2E-07-real-sse-memory-refresh',activity_live,page)
        def logout():
            page.get_by_role('button',name='Salir',exact=True).click()
            expect(page.get_by_label('Usuario',exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_label('Usuario',exact=True)).to_be_visible()
            assert context.request.get(BASE+'/memory-api/v1/auth/me').status==401
            login(page,'reader')
            expect(page.get_by_role('button',name='Nueva memoria',exact=False)).to_have_count(0)
            me=context.request.get(BASE+'/memory-api/v1/auth/me').json()
            headers={'Origin':BASE,'X-CSRF-Token':me['csrf_token']}
            from memory_platform.tests.test_store import event
            assert context.request.post(BASE+'/memory-api/v1/events',data=event('project-a',generate=False),headers=headers).status==403
        check('E2E-01-logout-readonly-ui',logout,page)
        (OUT/'browser-errors.json').write_text(json.dumps(errors,ensure_ascii=False))
        context.tracing.stop(path=str(OUT/'trace.zip'))
        browser.close()

def run_feature_views(store, admin):
    """Real browser/API/PG; only the provider reply is a synthetic fixture."""
    from memory_platform.tests.test_store import event
    source = event('project-a', generate=False, payload={
        'title': 'Asterion: "Árbol" 🌳', 'content': 'Asterion preserves quoted evidence before projection.',
        'category': 'Asterion / API', 'tags': ['nota:uno,dos', 'dijo:"sí"'], 'source': {'uri': 'fixture://asterion'}})
    store.ingest_event(admin, source)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='es-ES')
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page(); login(page)

        def corpus():
            page.goto(BASE+'/portal.html?project=project-a&view=corpora')
            if page.locator('.corpus-builder').get_attribute('open') is None:
                page.get_by_text('Crear una selección de memorias', exact=True).click()
            page.get_by_label('Nombre de la selección', exact=True).fill('Asterion QA')
            page.get_by_label('Palabras de las memorias (opcional)', exact=True).fill('Asterion')
            page.get_by_role('button', name='Crear selección', exact=True).click()
            expect(page.get_by_text('Selección guardada. Prepárala antes de preguntar.', exact=True)).to_be_visible()
            page.get_by_role('button', name='Preparar corpus', exact=True).click()
            expect(page.get_by_text('Generación preparada. Puedes enviar una pregunta.', exact=True)).to_be_visible()
            page.get_by_label('Pregunta sobre este corpus', exact=True).fill('Asterion')
            page.get_by_role('button', name='Enviar al modelo', exact=True).click()
            expect(page.get_by_role('heading', name='Respuesta generada · Sin validar', exact=True)).to_be_visible()
            expect(page.locator('.corpus-answers article').last).to_be_focused()
            assert page.locator('.corpus-builder').get_attribute('open') is None
            expect(page.locator('blockquote')).to_contain_text('Asterion preserves quoted evidence')
            page.get_by_label('Pregunta sobre este corpus', exact=True).fill('Why?')
            page.get_by_role('button', name='Enviar al modelo', exact=True).click()
            expect(page.locator('.corpus-answers article')).to_have_count(2)
            revised = {**source, 'event_id': str(uuid.uuid4()), 'version': 2,
                       'payload': {**source['payload'], 'content': 'Asterion preserves revised evidence before projection.'}}
            store.ingest_event(admin, revised)
            page.get_by_role('button', name='Actualizar selección de fuentes', exact=True).click()
            expect(page.get_by_role('button', name='Enviar al modelo', exact=True)).to_be_disabled()
            expect(page.locator('.corpus-controls')).to_contain_text('Generación 2')
            page.get_by_role('button', name='Preparar corpus', exact=True).click()
            expect(page.get_by_role('button', name='Enviar al modelo', exact=True)).to_be_enabled()
        check('A06-corpus-grounded-followup-refresh', corpus, page)

        def rules():
            page.goto(BASE+'/portal.html?project=project-a&view=rules')
            page.get_by_role('button', name='＋ Nueva regla', exact=True).click()
            page.get_by_label('Título', exact=True).fill('Asterion rule: "sí", árbol 🌳')
            page.get_by_label('Contenido y contexto aplicable', exact=True).fill('Text <script>must stay text</script>')
            page.get_by_label('Sesión de origen', exact=True).fill('asterion-rules')
            page.get_by_role('button', name='Guardar memoria', exact=True).click()
            expect(page.get_by_text('Memoria recibida. Las proyecciones se verifican por separado.', exact=True)).to_be_visible()
            page.get_by_role('button', name='Cerrar', exact=True).click()
            page.get_by_role('button', name='Actualizar', exact=True).click()
            expect(page.get_by_role('heading', name='Asterion rule: "sí", árbol 🌳', exact=True)).to_be_visible()
            expect(page.locator('.list-area script')).to_have_count(0)
            page.goto(BASE+'/portal.html?project=project-a&view=observations&category=Asterion%20%2F%20API')
            expect(page.get_by_role('heading', name='Asterion: "Árbol" 🌳', exact=True)).to_be_visible()
            page.goto(BASE+'/portal.html?project=project-a&view=activity')
            expect(page.locator('.activity-card').first).to_be_visible()
        check('A06-rules-observations-category-activity', rules, page)

        def team():
            page.goto(BASE+'/portal.html?project=project-a&view=work')
            page.get_by_label('Visibilidad del trabajo', exact=True).select_option('team')
            page.get_by_text('Guardar una tarea', exact=True).click()
            page.get_by_label('Lista', exact=True).fill('Asterion team')
            page.get_by_label('Tarea', exact=True).fill('Conservar: "sí", árbol 🌳')
            page.get_by_label('Responsable (referencia de texto, opcional)', exact=True).fill('Inés')
            page.get_by_role('button', name='Guardar tarea', exact=True).click()
            expect(page.get_by_role('heading', name='Asterion team', exact=True)).to_be_visible()
            page.reload(); page.get_by_label('Visibilidad del trabajo', exact=True).select_option('team')
            expect(page.get_by_role('heading', name='Asterion team', exact=True)).to_be_visible()
            page.get_by_text('Ver tareas y detalles', exact=True).last.click()
            expect(page.get_by_text('assignee: Inés', exact=True)).to_be_visible()
        check('A06-manual-team-work-persistence', team, page)
        context.tracing.stop(path=str(OUT/'A06-feature-trace.zip')); browser.close()


def main():
    assert os.geteuid()!=0
    root=Path(tempfile.mkdtemp(prefix='memory-e2e-pg-'))
    subprocess.run(['initdb','-D',str(root/'data'),'-A','trust','--encoding=UTF8','--no-locale'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['pg_ctl','-D',str(root/'data'),'-l',str(root/'pg.log'),'-o',f'-h 127.0.0.1 -p 55432 -k {root}','-w','start'],check=True,stdout=subprocess.DEVNULL)
    try:
        subprocess.run(['createdb','-h','127.0.0.1','-p','55432','-U','postgres','memory_test'],check=True)
        store,admin,server=start('postgresql://postgres@127.0.0.1:55432/memory_test')
        if os.environ.get('KAIROS_FOCUSED_BROWSER') != '1':
            run_browser(store,admin)
        run_feature_views(store,admin)
        report={'environment':'isolated real Chromium + PostgreSQL + FastAPI, synthetic data','generation_provider':'synthetic_fixture_no_external_calls','browser':subprocess.check_output(['chromium','--version'],text=True).strip(),'results':results,'passed':sum(r['status']=='passed' for r in results),'failed':sum(r['status']=='failed' for r in results)}
        # Preserve individual real assertion outcomes in the JSON reporter shape.
        report['stats']={'expected':report['passed'],'unexpected':report['failed'],'flaky':0,'skipped':0}
        report['suites']=[{'title':'Real Chromium portal','specs':[{'title':r['title'],'file':'memory_platform/tests/e2e_portal.py','tests':[{'expectedStatus':'passed','results':[{'status':r['status'],**({'error':{'message':r['error']}} if 'error' in r else {})}]}]} for r in results]}]
        (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('QA_RESULT '+json.dumps({k:report[k] for k in ('browser','environment','passed','failed')},ensure_ascii=False),flush=True)
        exported={'E2E-04-native-map-webgl-details.jpg','M-01-mobile-bounds-menu-filter.jpg','E2E-04-real-search-context-source.jpg','E2E-08-public-home-docs-private-boundary.jpg','E2E-09-public-mobile-menu-keyboard.jpg','results.json','browser-errors.json'}
        for path in sorted(OUT.glob('*')):
            if path.name in exported and os.environ.get('KAIROS_QA_EXPORT') == '1':
                encoded=base64.b64encode(path.read_bytes()).decode()
                chunks=[encoded[i:i+4000] for i in range(0,len(encoded),4000)]
                for index,chunk in enumerate(chunks):
                    print('QA_BLOB '+json.dumps({'file':path.name,'part':index,'total':len(chunks),'data':chunk}),flush=True)
                    # Transport pacing only: never a browser assertion or wait.
                    time.sleep(1)
        if report['failed']:
            raise SystemExit(1)
    finally:
        if 'server' in locals():
            server.should_exit = True
            server.fixture_corpus_patch.stop()
        subprocess.run(['pg_ctl','-D',str(root/'data'),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
        assert root.parent==Path(tempfile.gettempdir()) and root.name.startswith('memory-e2e-pg-')
        shutil.rmtree(root)

if __name__=='__main__':
    main()
