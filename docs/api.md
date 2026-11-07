# API local y herramientas MCP

La URL predeterminada es `http://127.0.0.1:8000`. La API utiliza JSON y está diseñada para la interfaz local del MVP. No es una API pública multiusuario.

## Sesión

`GET /api/bootstrap` establece la cookie `hapic_session` (HttpOnly y SameSite Lax para permitir el retorno GET de Google OAuth) y devuelve un token `csrf`. Las operaciones que modifican datos requieren esa cookie y el encabezado `X-Hapic-CSRF`. Cuando se envía `Origin`, debe coincidir con el origen de la solicitud.

Los hosts de la interfaz y API se limitan a `localhost`, `127.0.0.1` y `::1`. Los endpoints MCP usan autenticación separada con Bearer token por agente y protección contra DNS rebinding.

## Endpoints

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/health` | Salud del control de gestión; no comprueba inferencia |
| GET | `/api/bootstrap` | Establecer sesión local y obtener CSRF |
| GET | `/api/state` | Organizaciones, proyectos y agentes autorizados; ajustes globales |
| GET | `/api/capabilities` | Conexión Docker y presencia/origen de la credencial, sin su valor |
| POST | `/api/organizations` | Crear organización: `{"name":"Estudio"}` |
| POST | `/api/organizations/{org_id}/projects` | Crear proyecto y perfil Hapic: `{"name":"Producto"}` |
| GET | `/api/templates/ux` | Plantilla UX, capacidades, entregables e instrucciones |
| GET | `/api/templates` | Catálogo UX, diseñador, arquitecto, coder y community manager, con recomendaciones |
| POST | `/api/projects/{project_id}/agents` | Crear perfil: `{"name":"Nora","template":"ux"}`; coder exige `planner_id` |
| POST | `/api/agents/{agent_id}/start` | Solicitar inicio o recreación del runtime |
| GET | `/api/agents/{agent_id}/runtime` | Estado actual y readiness de Hermes |
| GET | `/api/agents/{agent_id}/messages` | Historial visible de la plataforma |
| GET | `/api/agents/{agent_id}/events` | Hasta 100 eventos recientes |
| POST | `/api/agents/{agent_id}/chat` | Enviar turno con `content` y `request_id` único |
| GET | `/api/projects/{project_id}/tree` | Árbol real filtrado del proyecto |
| GET | `/api/projects/{project_id}/file?path=…` | Vista previa de documento permitido |
| GET | `/api/projects/{project_id}/image?path=…` | Imagen del workspace; `download=true` para descargar |
| PUT | `/api/settings/model` | Modelo y esfuerzo predeterminados para nuevos agentes |
| PUT | `/api/agents/{agent_id}/model` | Modelo y esfuerzo de un agente existente |
| PUT | `/api/settings/openai` | Guardar `api_key` en el servidor; nunca devuelve su valor |
| DELETE | `/api/settings/openai` | Eliminar la credencial guardada en archivo del servidor |
| GET | `/api/tools` | Catálogo de integraciones reutilizables |
| GET | `/api/settings/youtube` | Estado, origen (`file`, `server`, `none`), scopes y URI de retorno; sin secretos o ruta privada |
| PUT | `/api/settings/youtube` | Cargar el JSON OAuth web en `credentials` para el operador local; se rechaza cuando el servidor administra un archivo |
| GET | `/api/projects/{project_id}/tools` | Conexiones y asignaciones del proyecto autorizado |
| PUT | `/api/agents/{agent_id}/tools/{tool_id}` | Configurar `enabled` y `connection_id` para cualquier tipo de agente |
| POST | `/api/projects/{project_id}/connections/youtube/authorize` | Iniciar OAuth con estado por sesión/proyecto y PKCE |
| GET | `/api/connections/youtube/callback` | Consumir estado de un solo uso y verificar el canal en Google |
| DELETE | `/api/projects/{project_id}/connections/{connection_id}` | Revocar y desconectar el canal del proyecto |
| GET | `/api/projects/{project_id}/connections/{connection_id}/videos` | Página de vídeos real; `page_token` opcional |

El nivel de razonamiento admitido por la plataforma es `low`, `medium`, `high`, `xhigh` o `max`. La compatibilidad del modelo elegido también depende del proveedor.

Un turno puede incluir, por ejemplo:

```json
{
  "content": "Quiero crear un agente UX para este proyecto.",
  "request_id": "identificador-unico-del-turno"
}
```

Reutiliza un `request_id` solo para reintentar exactamente el mismo turno del mismo agente. Si cambia su identidad, la API devuelve `409`. Si hay un turno o provisión activos, también puede devolver `409`. Tras un fallo de transporte, la ejecución remota puede haber comenzado: revisa la actividad antes de repetir acciones con un identificador nuevo.

## Archivos

La ruta de vista previa es relativa al proyecto. Se rechazan rutas absolutas, traversal, enlaces simbólicos, uniones de Windows y nombres protegidos. No se previsualizan `config.yaml`, archivos de autenticación, secretos, logs ni bases de datos binarias.

Se permiten documentos y extensiones habituales de código (`.py`, `.ts`, `.tsx`, `.js`, `.sql`, etc.), hasta 256 000 bytes. La interfaz muestra el contenido como texto, sin ejecutar HTML o SVG. La ruta de imágenes admite PNG, JPEG, WebP y GIF hasta 20 MiB, verifica su firma y extensión, exige sesión y solo acepta workspaces. Rechaza imágenes dentro de perfiles Hermes y cachés.

Los mensajes incluyen `attachments: []`. Cada imagen registrada incluye `id`, `path` relativa al proyecto, `name`, `mime_type` y `url` del endpoint autenticado. La generación produce un mensaje `source: artifact` independiente de la respuesta final de Hermes, de modo que un fallo posterior no oculta el archivo guardado.

`template` admite `ux` (predeterminado por compatibilidad), `graphic-designer`, `architect`, `coder` y `community-manager`. Ejemplo: `{"name":"Lin","template":"coder","planner_id":"agt_…"}`. El arquitecto debe existir en el mismo proyecto. Community Manager no requiere `planner_id`: `{"name":"Alma","template":"community-manager"}`.

Community Manager incluye herramientas de archivos y YouTube de solo lectura, pendiente de un canal autorizado. La integración se puede asignar a cualquier agente desde Herramientas. Consulta [YouTube](youtube.md) para su configuración y los límites actuales; Instagram, publicación y respuestas siguen pendientes.

## MCP

El servidor MCP se monta en `/mcp/` mediante el SDK oficial de Python. Los tokens se crean por agente y no se entregan al navegador. Su identidad determina el proyecto y el rol; el modelo no puede ampliar ese alcance con argumentos.

| Herramienta | Agente autorizado | Entrada |
| --- | --- | --- |
| `get_ux_template` | Hapic | Sin argumentos de negocio |
| `create_ux_agent` | Hapic | `name` |
| `list_agent_templates` | Hapic | Sin argumentos de negocio |
| `list_project_agents` | Hapic | Sin argumentos; solo el proyecto autorizado |
| `create_specialist_agent` | Hapic | `name`, `template`, `planner_id` para coder |
| `project_list_files` | Especialistas | Sin argumentos de negocio |
| `project_read_file` | Especialistas | `path` relativa a su workspace |
| `project_write_file` | Especialistas | `path` y `content`; coder exige lectura del plan vigente |
| `generate_project_image` | UX y diseñador gráfico | `prompt`, `size` opcional; una imagen facturable guardada y adjunta |
| `publish_architecture_plan` | Arquitecto | `content` Markdown, hasta 256 KB |
| `get_architecture_plan` | Coder | Plan del arquitecto vinculado y revisión, sin argumentos |
| `youtube_get_channel` | Cualquier agente con YouTube habilitado y canal asignado | Sin argumentos |
| `youtube_list_videos` | Misma autorización por agente/proyecto | `max_results` 1–50, `page_token` opcional |
| `youtube_list_comments` | Misma autorización; valida el vídeo del canal | `video_id` opcional, `max_results` 1–50, `page_token` |
| `youtube_get_analytics` | Misma autorización por agente/proyecto | `start_date`, `end_date` YYYY-MM-DD, hasta 366 días |

Las herramientas se filtran en la configuración Hermes y se autorizan de nuevo en el servidor. Que `create_ux_agent` devuelva un perfil y trabajo en cola no significa que su contenedor esté listo; consulta el runtime.

## Errores

- `400`: nombre, ruta, ajuste o contenido no permitido.
- `401`: sesión o token MCP ausentes o inválidos.
- `403`: origen, host o CSRF no autorizado.
- `404`: recurso inexistente o sin pertenencia autorizada.
- `409`: turno ocupado o identidad de reintento incompatible.
- `422`: datos que no cumplen el esquema de entrada.
- `503`: Docker, Hermes, credencial o inferencia no disponibles.

Los errores de validación se redactan para evitar devolver valores de credenciales. Las respuestas de la API llevan `Cache-Control: no-store`.
