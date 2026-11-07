# Hapic

MVP local en español para organizar proyectos y trabajar con agentes Hermes persistentes. Interfaz React/Vite, control de gestión FastAPI, metadatos SQLite y un contenedor oficial Hermes por agente.

Los cinco bocetos previos están conservados en [docs/mockups](docs/mockups). La aplicación inicia vacía; los ejemplos de esos bocetos no se convierten en datos ni en estados de runtime.

## Documentación

- [Arquitectura](docs/architecture.md): componentes, datos, provisión y límites de acceso.
- [Auditoría multiagente y delegación](docs/multiagent-audit.md): diagnóstico, tareas persistentes, evidencias, pruebas y límites pendientes.
- [API y MCP](docs/api.md): rutas, sesión local, herramientas y errores.
- [Operación](docs/operations.md): arranque, credenciales, persistencia, copias y diagnóstico.
- [YouTube](docs/youtube.md): conexión OAuth, consultas reales y asignación a cualquier agente.
- [HeyGen](docs/heygen.md): API key por proyecto, generación de clips con audio y MP4 persistentes.
- [Community Manager e integración social](docs/community-manager.md): perfil disponible y evolución de otras funciones sociales.
- [Changelog](CHANGELOG.md): versiones y cambios pendientes de publicación.

## Ejecutar localmente en Windows

Requisitos: Python 3.14, Node 24 y pnpm 11. Docker Desktop con motor Linux se necesita para los agentes, pero no para usar la plataforma, crear organizaciones/proyectos o explorar perfiles.

```powershell
python -m venv --without-pip .venv
python -m pip --python .venv install -r requirements.lock
Set-Location frontend
pnpm install --frozen-lockfile
pnpm build
Set-Location ..
.\scripts\start.ps1
```

Abre http://127.0.0.1:8000. El script también acepta `-Port 8080`. Puedes iniciar directamente con `.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`.

Durante desarrollo: inicia el backend en 8000 y ejecuta `pnpm dev` dentro de `frontend`; Vite sirve en 5173 y reenvía `/api` al backend. El build de producción lo sirve FastAPI desde el mismo origen.

## Recorrido

El chat consulta el estado de ejecución del servidor cada tres segundos: recupera el indicador al recargar o volver a la conversación y actualiza el historial al terminar. Hapic muestra las tareas del equipo con responsable, objetivo y estado; los especialistas muestran sus propias tareas. Un aviso general permite volver a Hapic mientras el equipo trabaja desde otra sección. Se bloquea el envío cuando el servidor confirma un turno activo. Los turnos se registran en SQLite y los que estaban activos al reiniciar el servidor se señalan como interrumpidos. Una tarea `running` sin ejecución comprobada se muestra como pendiente de revisión, sin afirmar que siga trabajando ni reintentarse automáticamente.

1. Crea una organización y un proyecto desde la plataforma. Se guardan registros, pertenencia del operador local y carpetas reales. El proyecto recibe un perfil Hapic nuevo.
2. En Configuración, define la API key de OpenAI mediante el formulario dedicado. También puedes definir `OPENAI_API_KEY` en el entorno del servidor o en un archivo `.env` ignorado por Git. Nunca la pegues en el chat.
3. Inicia Docker Desktop. Abre Hapic y pulsa **Iniciar runtime**. Si ya hay key al crear un proyecto, se solicita su arranque automáticamente.
4. Pide crear un especialista UX, diseñador gráfico, arquitecto/planner, coder o community manager; también puedes ir a **Plantillas → Usar plantilla**. Hapic pregunta el nombre si falta y usa las herramientas MCP de provisión.
5. Abre el especialista, conversa y consulta archivos/actividad. Los entregables aparecen solo cuando se guardan de verdad.

Sin Docker o sin key, el chat de IA está deshabilitado. **Preparar** o **Usar plantilla** permite crear el perfil desde un formulario; no solicita inferencia ni simula mensajes de Hermes o contenedores activos.

## Oficina 3D de cada proyecto

Cada tarjeta de proyecto tiene un botón **Oficina 3D**. También puedes abrirla desde **Abrir oficina 3D** dentro del proyecto o desde su menú lateral. La oficina se carga únicamente al solicitarla; navegar por proyectos o conversaciones no descarga Three.js ni inicia una escena.

La vista está inspirada en [Hermes Office 3D](https://github.com/esteban-rj/hermes-game-studio/tree/main/hermes-office-3d), adaptada a los datos de Hapic: nombre del proyecto, un puesto y personaje por agente real, sala común y panel del proyecto. Los puestos crecen con el equipo y solo aparecen agentes de ese proyecto y organización. No necesita modelos, imágenes ni recursos remotos.

Arrastra para girar, usa la rueda o pellizca para acercar, o utiliza los controles de cámara y vista superior. Selecciona un personaje, su puesto o una persona de la lista y pulsa **Abrir conversación** para entrar en su chat existente. **Salir de la oficina** o Escape cierra la escena y libera sus recursos gráficos. En móvil, la lista del equipo aparece debajo de la oficina. Si WebGL no está disponible, la lista y el acceso a las conversaciones siguen funcionando.

La actividad usa la consulta existente al servidor: solo se anima un agente cuando su turno o tarea tiene ejecución confirmada. Un runtime registrado como `running` no se presenta por sí solo como trabajo activo. Abrir la oficina no inicia runtimes ni envía mensajes.

Pruebas desde `frontend`: `pnpm test` comprueba aislamiento, distribución y estados. `pnpm test:office` construye la interfaz y prueba el flujo con FastAPI y SQLite temporales, sin credenciales de proveedores. Requiere las dependencias Python del proyecto y Chromium instalado mediante `pnpm exec playwright install chromium`; puedes indicar otro Python con `HAPIC_TEST_PYTHON` y un Chrome existente con `HAPIC_TEST_BROWSER`. Las capturas quedan en `artifacts/`.

## Comunicación por voz

Abre la conversación de cualquier agente y pulsa **Hablar**. Permite el micrófono, dicta una tarea o pregunta y pulsa **Terminar**; cada grabación admite hasta 60 segundos y 8 MB. Revisa o corrige la transcripción y pulsa **Enviar**. El mensaje se envía al mismo chat de Hermes, con su historial y modelo habituales. El agente debe estar conectado y libre para recibir tareas nuevas.

Preguntas breves como **«¿cómo vas?»**, **«¿cuál es tu estado?»** o **«¿qué estás haciendo?»** se proponen como **Consulta de estado**. Puedes cambiar ese selector antes de enviar. El botón **Consultar estado** también funciona mientras el agente trabaja o sin una conexión de IA: consulta el runtime, los turnos y las tareas del servidor sin iniciar inferencia ni interrumpir el trabajo. En Hapic incluye el equipo; en los especialistas solo sus propias tareas. Los registros sin ejecución comprobada se indican como pendientes de revisión.

**Leer respuestas** reproduce las respuestas a mensajes de voz y las consultas de estado usando la voz en español disponible en el navegador. Puedes detener la reproducción o pulsar **Escuchar respuesta** en el historial. Si el navegador no permite la lectura automática, utiliza el botón Escuchar.

El micrófono necesita HTTPS o `localhost`, un navegador con `getUserMedia` y `MediaRecorder` que admita WebM o MP4, y la key de OpenAI configurada en el servidor. Una dirección HTTP privada de la red WiFi no habilita el micrófono; utiliza HTTPS para acceder desde otro dispositivo. Al cancelar o cambiar de agente se cierra el micrófono y se descarta la grabación pendiente. Al terminar, el audio se envía a OpenAI para transcripción mediante `gpt-transcribe` (configurable con `HAPIC_TRANSCRIPTION_MODEL`) y puede tener coste. Hapic no conserva archivos de audio; solo guarda en el chat el texto que envías. La lectura utiliza el servicio de voz del navegador o sistema operativo, que puede depender de su proveedor. Consulta la [guía oficial de transcripción](https://developers.openai.com/api/docs/guides/speech-to-text).

## Especialistas, planes e imágenes

**Entorno de desarrollo** aparece en **Herramientas → Herramientas por agente**. Se habilita por defecto para coders nuevos y existentes (se conservan las desactivaciones explícitas) y puede asignarse a cualquier agente. Después de cambiar una asignación, reinicia el runtime para actualizar su lista MCP. Los scripts `start-docker.ps1` y `start-docker.sh` construyen `hapic-runner:local`; con Compose directo o servidor nativo, ejecuta antes `docker build -t hapic-runner:local -f runner/Dockerfile runner`.

`development_run` ejecuta comandos con Python 3.14, Node 24 y npm, devuelve código de salida y hasta 20000 caracteres de logs y detiene el contenedor al agotar el plazo (1–120 segundos). Cada comando usa un contenedor nuevo con solo el workspace del agente persistente, usuario sin privilegios, raíz de solo lectura, límites de CPU/memoria/procesos y sin tokens ni socket Docker. Puede acceder a la red para instalar dependencias; no constituye un aislamiento de red. Usa `.venv` dentro del workspace para paquetes Python. El coder debe leer el plan vigente antes de ejecutar o escribir.

`development_preview` permite `start`, `status` y `stop`. El servidor debe escuchar en `0.0.0.0:3000`; la herramienta devuelve una URL publicada solo en `127.0.0.1` del PC. La vista previa expira tras una hora. No es alojamiento público: no permite por sí sola que jugadores entren desde otras redes. Estar `running` tampoco demuestra que la aplicación funcione; hay que comprobar la página y sus pruebas. Al desactivar Entorno de desarrollo se detiene su vista previa.

En el chat de cualquier agente conectado, **Adjuntar imagen** permite seleccionar hasta tres imágenes PNG, JPEG o WebP de hasta 8 MB cada una. Revisa las miniaturas, escribe qué necesitas analizar y envía el mensaje. También puedes enviar solo la imagen para obtener una descripción. Los adjuntos se conservan en el historial y en el workspace del agente; al enviar se transmite su contenido al modelo a través de Hermes. La interpretación requiere un modelo con visión y puede tener coste de inferencia. No identifica con certeza fuentes tipográficas exactas ni detalles ilegibles. Los vídeos y documentos no se admiten como adjuntos.

| Plantilla | Trabajo |
| --- | --- |
| UX | Brief, flujos, wireframes, accesibilidad e imágenes solicitadas |
| Diseñador gráfico | Brief visual y generación real de PNG guardados y adjuntos al chat |
| Arquitecto / Planner | Arquitectura y plan compartido con tareas, archivos, contratos y validación |
| Coder | Implementación en archivos siguiendo el plan del arquitecto vinculado |
| Community Manager | Estrategia, calendario, copys, guiones, propuestas de respuesta y análisis de métricas aportadas |

**HeyGen** está disponible en **Herramientas**: conecta la API key del proyecto y asigna la cuenta a tus agentes. Community Manager la incluye preseleccionada. Genera clips con audio de 5 a 15 segundos desde texto o una imagen pública; el MP4 queda guardado y adjunto al chat, con reproducción y descarga en Archivos. Por defecto usa 5 s, 480p y formato vertical (estimación US$0,05). Los trabajos y reintentos se identifican para evitar duplicar generaciones; consulta la [guía de HeyGen](docs/heygen.md). Si el runtime ya estaba iniciado, reinícialo para cargar las nuevas herramientas.

El Community Manager prepara borradores para Instagram y YouTube con memoria y archivos propios. Incluye **YouTube de solo lectura**: conecta un canal desde **Herramientas**, consulta vídeos, comentarios y métricas y asigna el canal a los agentes que elijas. Cualquier tipo de agente puede integrarla. El administrador configura el JSON OAuth en el servidor, por ejemplo como secreto de Docker con `./scripts/start-docker.sh "/ruta/privada/google-oauth.json"`; cada cliente solo autoriza su canal desde Google. La [guía de YouTube](docs/youtube.md) detalla configuración, permisos y alcance. Instagram, publicación, programación y respuestas siguen pendientes.

Crea primero el arquitecto y después el coder, seleccionando ese arquitecto del mismo proyecto. El arquitecto publica mediante `publish_architecture_plan`; el coder usa `get_architecture_plan` antes de escribir. Si el plan cambia, debe volver a leerlo. Para el planner se recomienda un modelo de capacidad media a superior (`gpt-6.1-sol`, esfuerzo `high` para trabajo complejo); las preferencias globales se conservan y pueden ajustarse en cada conversación. El coder puede escribir código y pruebas, pero no dispone de terminal para ejecutarlas.

`generate_project_image` utiliza la key guardada y OpenAI Images. El modelo de imagen predeterminado es `gpt-image-2.5-flare`, configurable en el servidor con `HAPIC_IMAGE_MODEL`; es independiente del modelo conversacional. Cada llamada genera una imagen y puede tener coste. El PNG se guarda primero en `agents/<id>/workspace/images/`, luego se registra un adjunto del chat. Se conserva incluso si falla la respuesta final de Hermes. Las imágenes tienen vista previa y descarga en **Archivos**. No se descargan URLs arbitrarias ni se depende de enlaces temporales del proveedor.

El modelo inicial es `gpt-6.1-sol` y el esfuerzo `xhigh`. Ambos se pueden elegir mediante selectores para agentes nuevos en Configuración y para un agente existente desde el compositor. El selector de modelos ofrece nombres legibles y conserva los identificadores personalizados ya guardados. Los cambios por agente se envían en el siguiente turno mediante `provider: openai-api` y `model_options.reasoning_effort`. No se usa la suscripción ni se importan credenciales de Codex.

## Ejecutar con Docker Compose

Con Docker Desktop activo:

```powershell
.\scripts\start-docker.ps1
```

El script fija `HAPIC_HOST_DATA_DIR` a la ruta absoluta de `.hapic` y ejecuta `docker compose up --build -d`. En Linux, exporta esa variable con una ruta absoluta y usa `docker compose up --build -d`. Solo se publica `127.0.0.1:8000`.

Compose ejecuta el control de gestión. Los contenedores de agentes se crean dinámicamente a partir de `nousresearch/hermes-agent:stable`, en la red `hapic-net`; cada uno recibe exclusivamente sus dos volúmenes persistentes y tokens propios. `HERMES_IMAGE` permite fijar una versión o digest tras validar esa imagen. El primer arranque puede tardar por la descarga de la imagen oficial.

El control de gestión tiene acceso al socket Docker para provisionar contenedores: es un componente de confianza con privilegios sobre el motor. Los agentes nunca reciben ese socket. No expongas este MVP local como SaaS público; requiere autenticación multiusuario y endurecimiento adicional antes de ese paso.

## Persistencia y límites de acceso

```text
.hapic/
  platform.db                          # organizaciones, pertenencia, proyectos, agentes, mensajes, actividad
  secrets/                             # clave de cifrado y credenciales/tokens cifrados; fuera del explorador
  organizations/<org-id>/
    organization.json
    projects/<project-id>/
      project.json
      workspace/plans/<planner-id>/plan.md  # plan compartido por cada arquitecto
      agents/<agent-id>/
        hermes/                        # HERMES_HOME → /opt/data
          SOUL.md
          config.yaml
          memories/MEMORY.md
          memories/USER.md
          skills/
          state.db                     # aparece cuando lo crea el runtime Hermes
        workspace/                     # → /workspace; código y documentos del agente
          images/                      # PNG persistentes generados por la herramienta
```

La memoria resumida de Hermes y su historial completo no son lo mismo: `memories/` contiene contexto persistente y `state.db` conserva sesiones/historial de Hermes. La plataforma conserva además los mensajes visibles en su SQLite. No copia memorias, sesiones ni credenciales de agentes anteriores al aplicar una plantilla.

La pertenencia de organización se valida en servidor. Cada token MCP identifica un agente y su proyecto, sin aceptar un proyecto arbitrario del modelo. Las herramientas de archivos operan en el workspace propio; el plan se comparte mediante una herramienta dedicada con los coders vinculados. Se rechazan rutas absolutas, traversal, enlaces, secretos y configuración sensible. Las imágenes se sirven por una ruta autenticada que comprueba formato, tamaño y pertenencia al workspace.

La key se cifra con Fernet y una clave maestra local. Nunca se devuelve por API, ni se guarda en localStorage, ni se incluye en errores de validación. El maestro y los datos están ignorados por Git. Un administrador del equipo o del motor Docker puede acceder a secretos del proceso/contenedor; el cifrado local no sustituye un gestor de secretos multiusuario. Al rotar la key, reinicia los agentes; eliminarla del servidor no borra el entorno de contenedores ya creados.

Los datos y el estado se guardan localmente. Las consultas, memoria/contexto necesario y resultados de herramientas usados en cada turno se envían a OpenAI para inferencia. No se promete que todos los datos permanezcan en el equipo.

## Integración oficial

- [Hermes: integración programática](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration): API HTTP, SSE y núcleo `AIAgent` real.
- [Hermes: API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server): `/v1/responses`, conversaciones persistentes, idempotencia y selección de modelo por petición.
- [Hermes: proveedores](https://hermes-agent.nousresearch.com/docs/integrations/providers): `openai-api` con API key, separado de `openai-codex` OAuth.
- [Hermes: perfiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles): un `HERMES_HOME` por agente, independiente del directorio de trabajo.
- [Hermes: Docker](https://hermes-agent.nousresearch.com/docs/user-guide/docker): imagen oficial, `/opt/data` y supervisión del gateway.
- [OpenAI: GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol): `xhigh` admitido; function calling exige Responses API.
- [OpenAI: generación de imágenes](https://developers.openai.com/api/docs/guides/image-generation): Images API y resultados base64 guardados como PNG.

La configuración fija explícitamente `model.api_mode: codex_responses`, el nombre del transporte Responses de Hermes, hacia `https://api.openai.com/v1`. La UI no infiere compatibilidad por el nombre del endpoint público de Hermes. El cliente verifica `/health/detailed` autenticado y `status: ok` antes de marcar el runtime disponible. El acceso real al modelo se verifica en el primer turno, no mediante una simple comprobación de Docker.

## Pruebas y alcance verificado

```powershell
$env:HAPIC_DATA_DIR = Join-Path (Get-Location) ('.hapic/test-local-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --basetemp .hapic/test-local
Set-Location frontend
pnpm build
```

En un sandbox Windows que bloquee sockets, las pruebas ASGI/TestClient y el servidor pueden requerir ejecución autorizada fuera de ese aislamiento. No se cambia el firewall ni las protecciones globales.

Las pruebas cubren persistencia, valores por defecto, CSRF/origen, pertenencia, secretos cifrados, errores redactados, rutas, permisos y protocolo MCP, plantillas, modelos, idempotencia y contrato `/v1/responses`; también planes de arquitecto/coder e imágenes persistentes. La suite de YouTube verifica OAuth con PKCE y estado ligado a sesión, asignaciones por agente y proyecto, renovación, consultas y desconexión. Los dobles de Docker/Hermes, Images y Google se utilizan solo en pruebas; no son un modo de ejecución de producción. No se realizan llamadas facturables. La prueba de enlace simbólico puede omitirse cuando Windows no concede permiso.

**Verificación local de despliegue:** después de instalar Docker Desktop y WSL2 y reiniciar Windows, el motor Linux ejecutó un contenedor `hello-world` real. La imagen de Hapic se construyó y Compose la inició con estado `healthy` en `127.0.0.1:8000`, conservando el almacenamiento existente. Se comprobó un montaje real de Windows desde el provisionador y las APIs autenticadas de dos contenedores oficiales Hermes (Hapic y UX). Sus perfiles tienen `state.db` y directorios de memoria persistentes. La plataforma ya registra respuestas reales de Hermes usando la credencial configurada por el usuario, con `gpt-6.1-sol` y `xhigh`.

La creación conversacional se comprueba con dobles en los tests. No se ejecutó una prueba adicional de QA con dos llamadas facturables a OpenAI. Los diagnósticos locales se guardan en `artifacts/`, que está excluido de Git.

Fuera de este MVP: login remoto multiusuario, roles empresariales completos, comunicación entre proyectos, WhatsApp, llamadas, Kubernetes y hosting externo.
