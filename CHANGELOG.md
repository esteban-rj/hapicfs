# Changelog

Este archivo registra los cambios del proyecto. Las versiones siguen el esquema `MAJOR.MINOR.PATCH`.

## Sin publicar — 2026-11-06

### YouTube y herramientas reutilizables

- Credenciales OAuth administradas por archivo del servidor (`HAPIC_YOUTUBE_CLIENT_FILE`), override de Compose con secreto exclusivo de Hapic y lanzadores macOS/Linux/Windows. El formulario se oculta y su API se bloquea cuando el archivo es administrado por el despliegue.
- Sección Herramientas con carga cifrada del JSON OAuth web, conexiones por proyecto y asignación de YouTube a cualquier agente.
- Community Manager incluye YouTube de solo lectura; migración aditiva para perfiles existentes sin reemplazar asignaciones guardadas.
- OAuth de Google con PKCE S256, estado de un solo uso ligado a sesión/proyecto, identidad de canal comprobada y parámetros del callback excluidos de logs.
- Renovación serializada de tokens, nueva autorización tras rechazo y desconexión con revocación y borrado de credenciales locales.
- Cuatro herramientas MCP: canal, vídeos con paginación, comentarios e informes diarios; validación de proyecto, agente, canal y vídeo en servidor.
- Pruebas HTTP con un doble exclusivo de Google; conexión con una cuenta real pendiente de que el usuario cargue el JSON y autorice su canal.
- Verificación actual en macOS: 42 pruebas aprobadas y build TypeScript/Vite correcto; configuraciones Compose base y con secreto validadas, interfaz de Herramientas comprobada en navegador sin errores de consola.

### Añadido

- Selector de modelos en Configuración y en cada conversación, con nombres legibles y conservación de modelos personalizados ya guardados.
- Templates de diseñador gráfico, arquitecto/planner y coder, además del especialista UX existente.
- Perfil Community Manager para Instagram y YouTube, creable por interfaz y MCP, con estrategia, calendario, copys, guiones, respuestas propuestas y métricas aportadas.
- Propuesta documentada de Instagram y de publicación/programación social; YouTube de lectura se implementa en esta revisión.
- Catálogo con creación desde la interfaz, selección de proyecto y recomendaciones de modelo.
- Herramientas de Hapic para consultar templates, listar agentes y crear especialistas.
- Vinculación de coder a arquitecto del mismo proyecto; publicación y lectura del plan compartido con revisión SHA-256.
- Escritura del coder condicionada a haber leído el plan vigente; extensiones de código y pruebas.
- Generación mediante OpenAI Images, PNG persistente, adjunto de chat, vista previa y descarga autenticada.
- Migración aditiva de `planner_id` y tabla de imágenes, conservando los datos existentes.

### Corregido

- El chat muestra imágenes adjuntas y referencias Markdown a imágenes locales del workspace.
- Se guarda el archivo antes de anunciar éxito; el adjunto persiste aunque falle después Hermes.
- El explorador reconoce PNG, JPEG, WebP y GIF válidos, además de documentos de texto.

### Verificación

- Pruebas de catálogo, permisos, planes vigentes, contrato Images API, persistencia, descarga y fallos posteriores con dobles locales. Sin llamadas facturables adicionales.
- Verificación anterior en Windows: 17 pruebas aprobadas, 1 omitida por permisos de enlaces simbólicos; incluía creación idempotente de Community Manager mediante MCP, persistencia de borradores y denegación de herramientas ajenas al perfil.
- Build TypeScript/Vite correcto con el catálogo de cinco especialistas, incluido Community Manager.
- Verificación en navegador del catálogo, creación de coder vinculado y carga de imágenes en chat y Archivos con una imagen local de prueba.
- Actualización de Compose y de los dos runtimes existentes, con readiness comprobado y conservación de organizaciones, proyectos, agentes y mensajes.

## [0.1.0] - 2026-11-02

### Añadido

- Dashboard local en español con navegación por organizaciones, proyectos, agentes, plantillas y configuración.
- Alta de organizaciones y proyectos con metadatos SQLite y carpetas persistentes.
- Perfil Hapic propio por proyecto y plantilla UX versionada con instrucciones, método de trabajo y entregables.
- Creación de especialistas UX mediante herramientas MCP limitadas al proyecto y flujo guiado explícito cuando no hay IA disponible.
- Conversaciones y actividad persistentes, explorador del árbol real y vista previa de documentos de texto.
- Modelo `gpt-6.1-sol` y razonamiento `xhigh` por defecto, configurables globalmente y por agente.
- Integración con Hermes mediante `/v1/responses`, proveedor `openai-api` y transporte `codex_responses`.
- Provisionador Docker con un contenedor por agente, perfiles y workspaces separados, comprobación autenticada de readiness y límites de recursos.
- Imagen Docker del control de gestión, configuración Compose y scripts de arranque para Windows.
- Cinco bocetos de referencia conservados en `docs/mockups/`.
- Documentación de instalación, arquitectura, API y operación local.

### Seguridad

- Formulario dedicado para la API key de OpenAI, cifrado local con Fernet y respuestas sin valores de credenciales.
- Sesión local con cookie HttpOnly, control de origen, CSRF y validación de pertenencia de organización.
- Tokens MCP independientes por agente y autorización de herramientas en servidor.
- Validación de rutas, rechazo de enlaces y exclusión de secretos, logs y configuración sensible del explorador.
- Plantillas limpias: no se copian memorias privadas, sesiones ni credenciales de otros agentes.
- Datos operativos, claves, archivos de entorno y diagnósticos excluidos de Git.

### Verificado

- Build TypeScript/Vite y pruebas automatizadas de API, persistencia, secretos, alcance MCP y contratos de Docker/Hermes.
- Recorrido de onboarding, archivos y configuración en navegador, incluida una vista móvil sin desbordamiento horizontal.
- Ejecución real de `hello-world`, build y arranque de Hapic en Compose, montaje persistente de Windows y readiness de contenedores oficiales Hermes.
- Respuestas reales de Hermes registradas durante el uso local con la credencial configurada en servidor.

### Limitaciones

- Uso local con un operador; sin autenticación remota multiusuario ni roles empresariales completos.
- El historial de la interfaz y el historial interno de Hermes se almacenan por separado.
- Los agentes se administran dinámicamente y no forman parte del ciclo de vida de los servicios Compose.
- La comprobación adicional de creación conversacional con dos llamadas facturables en QA no se ejecutó.
- Una prueba de enlaces simbólicos puede omitirse si Windows no permite crearlos.
- Sin WhatsApp, llamadas, comunicación entre proyectos, Kubernetes ni publicación en hosting externo.
