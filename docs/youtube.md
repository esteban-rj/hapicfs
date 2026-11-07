# YouTube como herramienta reutilizable

Hapic incluye YouTube de **solo lectura**, accesible desde **Herramientas** y asignable a cualquier tipo de agente. Community Manager la tiene habilitada inicialmente; si el proyecto tiene un único canal conectado, lo selecciona por defecto. Con varios canales, el operador elige la conexión de cada agente.

## Configuración

1. Crea un proyecto de Google Cloud para Hapic y habilita YouTube Data API v3 y YouTube Analytics API. Cada cliente autoriza su propio canal; no necesita otro proyecto de Google Cloud.
2. En Google Auth Platform, configura público Externo y añade la cuenta propietaria del canal a los usuarios de prueba.
3. Declara `https://www.googleapis.com/auth/youtube.readonly` y `https://www.googleapis.com/auth/yt-analytics.readonly`.
4. Crea un cliente OAuth de tipo Aplicación web y registra exactamente `http://127.0.0.1:8000/api/connections/youtube/callback`. Con otro host o puerto, utiliza la URI que muestra Herramientas. `localhost` y `127.0.0.1` no se intercambian durante un flujo.
5. El administrador descarga el JSON y lo configura en el servidor, preferentemente como secreto de Docker según la sección siguiente. Para una instalación nativa también puede utilizar `HAPIC_YOUTUBE_CLIENT_FILE` o el formulario del operador local. Los endpoints se fijan en código a los oficiales de Google, ignorando los del archivo.
6. Selecciona un proyecto, pulsa **Conectar YouTube** y autoriza con la cuenta propietaria. Hapic verifica el canal devuelto por Google. Una cuenta sin canal o una respuesta con varios canales no completan la conexión; vuelve a autorizar seleccionando un canal concreto.

La configuración del cliente OAuth es global para esta instalación; conexiones y asignaciones pertenecen al proyecto. Cambiar a otro Client ID exige desconectar los canales existentes. Fuentes: [autorización](https://developers.google.com/youtube/data/guides/authentication), [cliente web](https://developers.google.com/identity/protocols/oauth2/web-server), [Analytics](https://developers.google.com/youtube/analytics/reference/reports/query).

## Credenciales administradas en Docker

El JSON pertenece a la aplicación Hapic. Lo configura el administrador una vez en el servidor; los clientes solo autorizan sus canales en Google. Guarda el archivo en una ubicación privada fuera del código y limita su lectura al operador. No lo incluyas en la imagen ni en Git.

En macOS/Linux, con el motor Docker activo:

```sh
./scripts/start-docker.sh "/ruta/privada/google-oauth.json"
```

En Windows:

```powershell
.\scripts\start-docker.ps1 -YouTubeClientJson 'C:\ruta\privada\google-oauth.json'
```

Los scripts activan `compose.youtube.yaml` además de `compose.yaml`. También puedes usar Compose directamente:

```sh
export HAPIC_HOST_DATA_DIR="$(pwd)/.hapic"
export HAPIC_YOUTUBE_CLIENT_JSON="/ruta/privada/google-oauth.json"
docker compose -f compose.yaml -f compose.youtube.yaml up --build -d
```

Compose monta el JSON como `/run/secrets/youtube_oauth_client` exclusivamente en el servicio `hapic`. `HAPIC_YOUTUBE_CLIENT_FILE` indica al backend dónde leerlo. No se añade al contexto de construcción, al entorno de Hermes ni a sus montajes. Los secretos basados en archivo de Compose son montajes del archivo del host: protege y conserva el original. [Secretos de Compose](https://docs.docker.com/compose/how-tos/use-secrets/).

Con esta configuración, Herramientas muestra **Configuración administrada por el servidor** y no ofrece cargar JSON. La API también impide reemplazar las credenciales desde el formulario. Un archivo ausente, inválido o de otro cliente OAuth con canales activos bloquea la conexión, sin recurrir silenciosamente a credenciales antiguas. El archivo se lee al utilizar la integración; si cambias el montaje de Docker, recrea el contenedor conservando `.hapic`. Se necesita el mismo Client ID para conservar las autorizaciones existentes.

Sin el archivo de despliegue opcional, Compose sigue funcionando para proyectos que no utilizan YouTube. El formulario de carga se conserva para el operador local de instalaciones nativas; ese JSON se cifra en el almacenamiento del servidor. Esta configuración no introduce usuarios o roles remotos: la plataforma sigue limitada al operador local.

## Uso

Al volver de Google aparecen nombre y estado del canal. **Ver vídeos** consulta una página real de su lista de subidas, con paginación y visibilidad. YouTube Studio abre la administración oficial. Esta versión no sube archivos, edita, publica, programa ni responde comentarios.

En **Herramientas por agente**, habilita YouTube, selecciona un canal del mismo proyecto y guarda. Se actualiza la configuración Hermes en disco; si el agente ya tenía contenedor, reinicia su runtime para descubrir la nueva lista de herramientas. La deshabilitación y los cambios de conexión se comprueban inmediatamente en el servidor, aunque el runtime conserve una lista anterior.

La migración añade tablas y la asignación inicial de Community Managers existentes, sin reemplazar asignaciones configuradas o deshabilitadas. Conserva SOUL, memoria y workspaces. Las instrucciones actuales se envían en cada turno. Docker y una credencial de inferencia siguen siendo necesarios para conversar; cargar credenciales, conectar y consultar vídeos desde la interfaz no requieren Docker.

| Herramienta MCP | Entrada | Resultado |
| --- | --- | --- |
| `youtube_get_channel` | Sin argumentos | Identidad, descripción y estadísticas del canal asignado |
| `youtube_list_videos` | `max_results` 1–50 y `page_token` opcional | Vídeos del canal y `next_page_token` |
| `youtube_list_comments` | `video_id` opcional, `max_results` 1–50 y `page_token` | Comentarios principales; se comprueba la pertenencia del vídeo al canal |
| `youtube_get_analytics` | `start_date`, `end_date` YYYY-MM-DD | Informe diario: vistas, minutos vistos, duración media y suscriptores ganados/perdidos; hasta 366 días, sin fechas futuras |

Las respuestas identifican fuente, canal y fecha de consulta; Analytics conserva columnas y periodo. Un dato ausente no equivale a cero. El contador de respuestas de un comentario no indica que se hayan leído todas. Los textos externos son datos no confiables y no autorizan acciones o cambios de permisos.

## Persistencia y autorización

SQLite incorpora `connections`, `agent_tools` y `oauth_states`. Los tokens quedan cifrados en `.hapic/secrets/<connection-id>-oauth.enc`. No se montan en Hermes, no se devuelven al navegador y no se escriben en workspaces, mensajes o logs. Las consultas solicitadas por un agente sí se incorporan al contexto de inferencia.

OAuth usa PKCE S256 y un `state` aleatorio de un solo uso, almacenado como SHA-256 y vinculado a sesión/proyecto, con diez minutos de validez. El verificador se cifra. La cookie es HttpOnly y SameSite Lax para el retorno GET desde Google; las mutaciones conservan CSRF y comprobación de origen. Los access logs omiten parámetros del callback.

La renovación se serializa por conexión. Si Google rechaza el acceso, el canal solicita nueva autorización; los errores no incluyen cuerpos o credenciales del proveedor. **Desconectar** solicita revocación a Google, elimina los tokens y desasigna el canal. Google puede invalidar otras conexiones de Hapic autorizadas con la misma cuenta. Si Google no confirma la revocación, no se anuncia éxito y se conserva la conexión para reintentar. Una desconexión cancela los flujos pendientes del proyecto, incluso con un intercambio ya en curso.

## Validación y límites

`tests/test_youtube.py` utiliza un transporte HTTP exclusivo de pruebas: comprueba OAuth, PKCE, sesión, estado, cifrado, identidad, renovación concurrente, errores, aislamiento, asignaciones, paginación, comentarios, Analytics, MCP y desconexión. No consume APIs reales ni inferencia facturable. La conexión de un canal real requiere cargar el JSON y completar personalmente el consentimiento de Google; los dobles no acreditan una conexión real.

En una app Externa con estado Testing, los refresh tokens de estos permisos caducan a los siete días. Para clientes de forma continuada, prepara producción y la verificación OAuth aplicable. [Caducidad](https://developers.google.com/identity/protocols/oauth2#expiration).

Hapic sigue siendo local para un operador. Esta integración no añade login remoto multiusuario ni expone el servidor. Los clientes remotos necesitan un despliegue con permisos propios y callback HTTPS.
