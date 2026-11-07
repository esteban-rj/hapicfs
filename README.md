# Hapic

MVP local en español para organizar proyectos y trabajar con agentes Hermes persistentes. Interfaz React/Vite, control de gestión FastAPI, metadatos SQLite y un contenedor oficial Hermes por agente.

Los cinco bocetos previos están conservados en [docs/mockups](docs/mockups). La aplicación inicia vacía; los ejemplos de esos bocetos no se convierten en datos ni en estados de runtime.

## Documentación

- [Arquitectura](docs/architecture.md): componentes, datos, provisión y límites de acceso.
- [API y MCP](docs/api.md): rutas, sesión local, herramientas y errores.
- [Operación](docs/operations.md): arranque, credenciales, persistencia, copias y diagnóstico.
- [YouTube](docs/youtube.md): conexión OAuth, consultas reales y asignación a cualquier agente.
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

1. Crea una organización y un proyecto desde la plataforma. Se guardan registros, pertenencia del operador local y carpetas reales. El proyecto recibe un perfil Hapic nuevo.
2. En Configuración, define la API key de OpenAI mediante el formulario dedicado. También puedes definir `OPENAI_API_KEY` en el entorno del servidor o en un archivo `.env` ignorado por Git. Nunca la pegues en el chat.
3. Inicia Docker Desktop. Abre Hapic y pulsa **Iniciar runtime**. Si ya hay key al crear un proyecto, se solicita su arranque automáticamente.
4. Pide crear un especialista UX, diseñador gráfico, arquitecto/planner, coder o community manager; también puedes ir a **Plantillas → Usar plantilla**. Hapic pregunta el nombre si falta y usa las herramientas MCP de provisión.
5. Abre el especialista, conversa y consulta archivos/actividad. Los entregables aparecen solo cuando se guardan de verdad.

Sin Docker o sin key, el chat de IA está deshabilitado. **Preparar** o **Usar plantilla** permite crear el perfil desde un formulario; no solicita inferencia ni simula mensajes de Hermes o contenedores activos.

## Especialistas, planes e imágenes

| Plantilla | Trabajo |
| --- | --- |
| UX | Brief, flujos, wireframes, accesibilidad e imágenes solicitadas |
| Diseñador gráfico | Brief visual y generación real de PNG guardados y adjuntos al chat |
| Arquitecto / Planner | Arquitectura y plan compartido con tareas, archivos, contratos y validación |
| Coder | Implementación en archivos siguiendo el plan del arquitecto vinculado |
| Community Manager | Estrategia, calendario, copys, guiones, propuestas de respuesta y análisis de métricas aportadas |

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
