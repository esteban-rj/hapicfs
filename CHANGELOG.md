# Changelog

Este archivo registra los cambios del proyecto. Las versiones siguen el esquema `MAJOR.MINOR.PATCH`.

## Sin publicar — 2026-11-07

### Oficinas 3D por proyecto

- Oficina Three.js bajo demanda desde cada tarjeta, el proyecto seleccionado o su menú lateral, inspirada en `hermes-game-studio/hermes-office-3d`.
- Diorama con puestos y personajes para el equipo real del proyecto, distribución adaptable y acceso a las conversaciones existentes.
- Cámara orbital, zoom, vista superior y pantalla completa; diseño móvil, navegación por teclado y lista accesible cuando falla WebGL.
- Animaciones vinculadas a ejecución confirmada, sin iniciar runtimes ni enviar mensajes al abrir la vista; recursos gráficos liberados al cerrar.
- Pruebas de aislamiento y estados, y recorrido en navegador con FastAPI/SQLite temporales y sin credenciales de proveedores.

### Comunicación por voz

- Micrófono en la conversación de todos los agentes, grabaciones de hasta 60 segundos, transcripción revisable y envío al chat existente con identidad estable de reintento.
- Transcripción OpenAI Audio con la key del servidor, validación de formato y límite de 8 MiB, errores redactados y audio sin persistencia local.
- Consultas de estado por voz o botón, disponibles durante tareas activas y sin inferencia; distinguen ejecución confirmada, cola, interrupciones y runtime desconectado.
- Lectura en español de respuestas de voz y estado, reproducción manual del historial y cancelación al cambiar de conversación.
- Verificación: 123 pruebas de servidor y 4 de interpretación de voz aprobadas; build TypeScript/Vite correcto. Chrome con micrófono virtual comprobó grabación real de MediaRecorder, revisión, estado durante tareas dictadas, lectura, reintentos sin duplicación, permisos denegados, cancelación, cambio de agente, límite de 60 segundos y panel móvil. Proveedor de transcripción y runtime ficticios; sin llamadas facturables ni prueba de reconocimiento con voz real.
- Ejecución local: integración con los cambios existentes de inicio de sesión, caducidad de sesiones y conexión de YouTube. Suite combinada de 151 pruebas aprobadas y compilación Docker correcta, conservando los datos y contenedores de agentes existentes.
- Integración con `main`: se conservan oficinas 3D, temas y errores legibles de la API. Pruebas de oficina adaptadas a la sesión autenticada; 151 pruebas del servidor, 14 unitarias de interfaz, cuatro recorridos de navegador y compilación aprobados.

### HeyGen y vídeos persistentes

- Conexión por API key cifrada por proyecto, con verificación de cuenta, clave activa y permisos de lectura/generación mediante la API v3.
- HeyGen asignable a cualquier agente y preseleccionado en Community Manager; migración aditiva que conserva asignaciones deshabilitadas y perfiles existentes.
- Herramientas MCP para generar clips con audio desde texto o imagen pública, consultar trabajos y recuperar los vídeos del propio agente y cuenta asignada.
- Trabajos persistentes con clave de idempotencia estable, protección ante reintentos concurrentes y recuperación de envíos inciertos sin crear otra solicitud.
- MP4 guardados atómicamente en el workspace, adjuntos del chat, reproducción y descarga autenticadas en Archivos y seguimiento desde Herramientas.
- Corregida la validación de MP4 `iso5`/`iso6` de HeyGen para guardar, reproducir y recuperar vídeos completados sin repetir su generación.
- Valor inicial de 5 segundos, 480p y formato vertical; estimación de coste visible y límite de 15 segundos.
- Verificación del formulario, asignación automática, MCP y reproducción completa de un MP4 en una instalación temporal con proveedor ficticio; sin errores de consola ni llamadas facturables. La conexión con HeyGen real requiere la clave del usuario.

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

- La interfaz muestra un mensaje comprensible cuando el servidor responde con un error en texto o una respuesta JSON no válida, en lugar de mostrar `Unexpected token`.
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
