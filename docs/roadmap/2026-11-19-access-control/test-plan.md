# Plan de pruebas — Control de acceso y privacidad (Iniciativa 4 de Kairos)

| | |
|---|---|
| **Estado** | borrador |
| **Plan** | [`improvement-plan.md`](improvement-plan.md) |
| **URL local** | n/a — el portal de pruebas vive dentro de la imagen `server/memory_platform/Dockerfile.e2e`, con API y base de fixture |

> **Restricción dura.** Ningún escenario se ejecuta contra el portal desplegado (`http://127.0.0.1:5173`) ni contra recursos `knowledge-graphs-*`. `qa` no apunta Playwright a una URL: ejecuta el arnés aislado del proyecto.

> **Dos niveles (spec A-08, diseño DC-9).** Un caso de CA-39 a CA-42 se da por verificado cuando pasa en los dos:
>
> | Nivel | Comando | Dónde corre |
> |---|---|---|
> | DOM de frontera | `cd web && npm run typecheck && npm test`; equivalente local de la CI: `docker build -f web/Dockerfile.test .` | CI y Docker local |
> | Chromium real | `docker build -f server/memory_platform/Dockerfile.e2e --target checks --progress=plain .`, tras construir las etiquetas `kairos-web:native-test` y `kairos-test:native` con los comandos que anota T-71 | Solo Docker local |
>
> La CI externa puede no ejecutarse: la ejecución local cierra el criterio y su salida se anota en el ledger.

## Automáticos (E2E — los ejecuta `qa` con Playwright)

Los cuatro escenarios son flujos de `server/memory_platform/tests/e2e_portal.py` (Playwright 1.55 con Chromium) sobre la siembra de `e2e_fixture.py`. Llevan el mismo ID que su criterio [GWT] de la spec.

### E2E-01 — CA-39 · Administrador global en «Usuarios»
- **Objetivo**: alta, cambio de permisos, deshabilitar, rehabilitar y cierre de sesiones desde el portal, con el efecto de CA-03, CA-04 y CA-05 en el servidor.
- **Precondiciones**: fixture con un administrador global, dos proyectos y un usuario con una sesión abierta en un segundo contexto de navegador.
- **Pasos**:
  1. Entrar como administrador global y abrir la pestaña «Usuarios».
  2. Dar de alta un usuario con permisos sobre un proyecto.
  3. Cambiar sus permisos por proyecto con el editor.
  4. Deshabilitarlo y aceptar la confirmación.
  5. Rehabilitarlo.
  6. Cerrar todas sus sesiones y aceptar la confirmación.
- **Aserciones**:
  - [ ] Cada acción se refleja en la lista sin recargar la página.
  - [ ] Deshabilitar y cerrar sesiones piden confirmación antes de actuar.
  - [ ] Tras deshabilitar, la sesión del usuario en el segundo contexto recibe 401 en su petición siguiente.
  - [ ] Tras rehabilitar, sus claves no revocadas vuelven a valer y sus sesiones no.
  - [ ] Tras cambiar los permisos, el proyecto retirado responde como un proyecto sin acceso.
- **Capturas esperadas**: lista tras el alta, diálogo de confirmación, usuario deshabilitado, editor de permisos.
- **Cubre tareas**: T-71, T-75, T-84, T-85, T-87, T-90

### E2E-02 — CA-40 · Cualquier usuario en «Mi cuenta»
- **Objetivo**: cambio de contraseña y cierre de las otras sesiones, con el efecto de CA-01 y CA-05.
- **Precondiciones**: fixture con un usuario sin el permiso `admin` en ningún proyecto y dos sesiones suyas (dos contextos de navegador).
- **Pasos**:
  1. Entrar y abrir «Mi cuenta» desde la barra superior.
  2. Enviar el formulario con la contraseña actual incorrecta.
  3. Enviar con una contraseña nueva de menos de 12 caracteres.
  4. Enviar con la actual correcta y una nueva válida.
  5. Abrir la lista de sesiones y cerrar las demás, aceptando la confirmación.
- **Aserciones**:
  - [ ] «Mi cuenta» es visible sin permisos de administración.
  - [ ] Cada error se muestra junto a su campo.
  - [ ] Los campos de contraseña quedan vacíos tras cada envío.
  - [ ] Tras el cambio, la otra sesión recibe 401 en su petición siguiente; la contraseña antigua ya no inicia sesión y la nueva sí.
  - [ ] La lista de sesiones marca la actual y se actualiza sin recargar.
- **Capturas esperadas**: error junto al campo, formulario vacío tras el éxito, lista de sesiones.
- **Cubre tareas**: T-71, T-75, T-78, T-80, T-81

### E2E-03 — CA-41 · «Claves para agentes»: caducidad, último uso y rotación
- **Objetivo**: crear claves con y sin caducidad y rotar una, con el efecto de CA-06 y CA-07.
- **Precondiciones**: fixture con un usuario con permiso para emitir claves sobre un proyecto.
- **Pasos**:
  1. Abrir la pestaña «Claves para agentes».
  2. Crear una clave sin caducidad.
  3. Crear otra con caducidad.
  4. Usar una de ellas contra la API de fixture.
  5. Rotar una clave con la gracia por defecto.
- **Aserciones**:
  - [ ] La lista muestra «sin caducidad» o la fecha, y el último uso tras el paso 4.
  - [ ] La clave creada o rotada se muestra una sola vez y desaparece del DOM al cerrar el aviso.
  - [ ] Tras rotar, la clave nueva vale y la antigua sigue valiendo dentro de la gracia.
  - [ ] Rotar sin gracia y revocar piden confirmación.
- **Capturas esperadas**: lista con las dos claves, aviso de clave mostrada una vez, lista tras la rotación.
- **Cubre tareas**: T-71, T-75, T-79, T-80, T-81

### E2E-04 — CA-42 · Delegación del alta y administración exclusiva del administrador global
- **Objetivo**: un administrador de proyecto da de alta personas para sus proyectos y no ve ni ejecuta la administración nueva.
- **Precondiciones**: fixture con un administrador de proyecto (no global), un usuario sin administración y una clave.
- **Pasos**:
  1. Entrar como administrador de proyecto y abrir «Usuarios».
  2. Dar de alta una persona para su proyecto, con permisos que él tiene.
  3. Llamar a mano, con su sesión, a las rutas de deshabilitar, sustituir permisos, listar usuarios y cerrar sesiones ajenas.
  4. Repetir una de esas llamadas sin token CSRF.
  5. Entrar como usuario sin administración y abrir la vista de configuración.
- **Aserciones**:
  - [ ] El administrador de proyecto ve el panel «Crear usuario» y ningún control de administración nuevo.
  - [ ] Tras el alta ve la confirmación y la lista de las altas de la visita; no se llama a `GET /v1/users`.
  - [ ] Cada llamada manual del paso 3 recibe 403.
  - [ ] La llamada sin CSRF se rechaza.
  - [ ] El usuario sin el permiso `admin` en ningún proyecto no ve ningún control de administración.
- **Capturas esperadas**: pestaña «Usuarios» del administrador de proyecto, confirmación del alta, vista del usuario sin administración.
- **Cubre tareas**: T-71, T-72, T-73, T-86, T-87, T-90

## Criterios [GWT] que cubren las suites (sin interfaz)

No los ejecuta `qa` con Playwright. Su evidencia es la `Verificación` de la tarea que los cierra, en `tasks.md`, más el ensayo aislado. Conservan el ID de la spec.

| Criterio | Qué comprueba | Prueba | Tareas | Ensayo |
|---|---|---|---|---|
| CA-01 | Cambio de contraseña: la otra sesión recibe 401 | `test_access_password.py` | T-09 | — |
| CA-03 | Deshabilitar: sesión y claves reciben 401; rehabilitar devuelve las claves | `test_access_users.py`, `test_admin.py` | T-13 | — |
| CA-07 | Rotación con gracia y sus 409 | `test_access_keys.py` | T-20 | — |
| CA-11 | Revocación en `/v1`, los dos `/mcp`, un flujo abierto y el portal | `test_revocation_matrix.py` | T-22 | T-31, T-103 |
| CA-13 | Diez fallos de A no bloquean a B, a través del proxy web | `test_login_limits.py`, `test_login_proxy.py` | T-26, T-28 | T-31, T-103 |
| CA-17 | K1 recibe 429 mientras K2 sigue en 200 | `test_limits.py` | T-55 | T-67 |
| CA-23 | Las siete cadenas de S-01 no aparecen en el cliente, la cola, la base ni los logs | `test_redaction_cases.py`, `test_redaction_routes.py`, `client/tests/` | T-44, T-45, T-50 | T-67 |
| CA-29 | El test que sigue la guía de identidad | `test_identity_guide.py` | T-94 | — |

## Manuales (M — los realiza una persona)

### M-01 — Revisión visual y de teclado de las tres secciones del portal
- **Qué revisar**: «Mi cuenta», «Usuarios» y «Claves para agentes» en el portal del arnés aislado: coherencia visual con el resto del portal, textos en español claros, foco visible, recorrido completo con teclado y diálogos de confirmación comprensibles.
- **Por qué no se automatiza**: es juicio visual y de usabilidad; el DOM de frontera no pinta y Chromium solo comprueba comportamiento.
- **Criterio de aceptación**:
  - [ ] Las tres secciones siguen el estilo del portal y no rompen la maquetación en una ventana estrecha.
  - [ ] Cada acción destructiva explica su efecto antes de confirmar.
  - [ ] Todo control se alcanza y se acciona con teclado.
- **Cubre tareas**: T-78, T-79, T-84, T-85, T-89

### M-02 — Aviso de `kairos doctor` en Windows con un fichero de clave abierto
- **Qué revisar**: en un equipo Windows, con un fichero de clave de prueba (clave sintética) con ACL abiertas o dentro de una carpeta sincronizada, `kairos doctor` avisa y no bloquea (CA-32, P-09).
- **Por qué no se automatiza**: depende de ACL reales de Windows y de `icacls`; la suite solo lo cubre con dobles.
- **Criterio de aceptación**:
  - [ ] `doctor` muestra el aviso y termina sin error.
  - [ ] El mensaje no contiene la clave.
- **Cubre tareas**: T-40

## Bloques opcionales no incluidos

- **API-xx (smoke con curl):** no se incluye. Las rutas nuevas de `/v1` se prueban en la suite del servidor con PostgreSQL aislado, y no hay una URL local contra la que `qa` pueda lanzar `curl` sin tocar la instalación desplegada. Se puede añadir sobre un proyecto `kairos-acc-*` si el usuario lo pide.
- **A11Y-xx (axe-core):** no se incluye; nadie lo ha pedido. La accesibilidad básica queda en M-01.

## Cobertura (tarea → escenarios)

| Tarea | Cubierta por |
|-------|--------------|
| T-40 | M-02 |
| T-71 | E2E-01, E2E-02, E2E-03, E2E-04 |
| T-73 | E2E-04 |
| T-75 | E2E-01, E2E-02, E2E-03 |
| T-78 | E2E-02, M-01 |
| T-79 | E2E-03, M-01 |
| T-80 | E2E-02, E2E-03 |
| T-81 | E2E-02, E2E-03 |
| T-84 | E2E-01, M-01 |
| T-85 | E2E-01, M-01 |
| T-86 | E2E-04 |
| T-87 | E2E-01, E2E-04 |
| T-89 | M-01 |
| T-90 | E2E-01, E2E-04 |
