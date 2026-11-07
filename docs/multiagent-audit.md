# Auditoría y plan incremental

Inspección del código: 7 de noviembre de 2026. No se toma el historial de verificación del README como prueba de esta sesión.

## Diagnóstico previo a cambios

| Componente | Qué hace hoy | Evidencia | Limitación | Mejora |
| --- | --- | --- | --- | --- |
| Entrada | React llama al chat FastAPI; sesión local y CSRF | app.create_app, ruta chat | Respuesta completa, sin streaming | Exponer tareas persistentes |
| Coordinador | Crea perfiles y consulta catálogo | Service.tool, templates/hapic/SOUL.md | No envía trabajo a especialistas | Delegación explícita acotada |
| Especialistas | UX, gráfico, arquitecto, coder, comunidad | templates.py:tools_for | Perfiles no equivalen a ejecución comprobada | Reutilizarlos antes de añadir roles |
| Ejecución | Hermes real en Docker, HTTP Responses | DockerRuntime.start/chat | Depende de Docker, key y modelo; terminal deshabilitada | Registrar bloqueo sin éxito ficticio |
| Archivos | Escrituras atómicas, workspace por agente | Service.tool, safe_path | No compila ni prueba lo generado | Evidencias con hash y revisión separada |
| Plan compartido | Arquitecto publica, coder lee revisión | architecture_plan, publish_architecture_plan | Dependencia manual, resto del contexto aislado | Contratos y dependencias persistentes |
| Memoria | SQLite de plataforma, perfiles Hermes separados | Store, runtime.prepare | Operador local, no autenticación multiusuario | Mantener alcance por proyecto |
| Recuperación | Idempotencia por turno y locks en memoria | app.chat | No hay cola durable de tareas ni recuperación automática | Estado durable, sin repetir efectos ambiguos |
| Límites | 30 turnos Hermes, timeout HTTP 600 s | runtime.prepare/chat | Sin presupuesto monetario o token agregado | Límite de tareas y llamadas; presupuesto real pendiente |
| Credenciales | Fernet, tokens por agente, filtrado de rutas | Store.secret/token, Service.scope | Control de gestión posee socket Docker | Conservar permisos; no añadir shell local |
| Integraciones | Images y YouTube tienen clientes reales | images.py, youtube.py | Pruebas usan dobles; no prueban proveedor vivo | Separar integración local de validación externa |

## Agentes actuales

Todos reciben texto por Responses y devuelven texto; archivos solo existen tras herramientas exitosas. Modelo y esfuerzo se guardan por agente. Todos los especialistas tienen listar/leer/escribir en su workspace; ninguno tiene terminal.

| Agente | Responsabilidad y herramientas adicionales | Dependencias y verificación posible |
| --- | --- | --- |
| Hapic | Provisión de especialistas y catálogo | Docker/key para inferencia; no delegaba turnos |
| UX | Flujos, brief, documentos; Images | Archivos locales comprobables; imagen requiere proveedor |
| Diseño gráfico | Brief y PNG mediante Images | Validación de formato/bytes; calidad visual requiere revisión |
| Arquitecto | Plan, publish_architecture_plan | Publicación y revisión SHA comprobables localmente |
| Coder | Implementar, get_architecture_plan | Arquitecto obligatorio; escritura bloqueada hasta leer revisión actual |
| Community Manager | Borradores, YouTube opcional de lectura | OAuth/canal asignado para datos reales; no publicación |

La carencia principal es implementación de coordinación y herramientas, no solo prompts. No existen agentes separados de QA, seguridad, datos o juegos; inicialmente serán responsabilidades del plan y revisión, sin crear perfiles decorativos.

## Arquitectura propuesta y prioridades

Conservar FastAPI, SQLite, Hermes, perfiles y MCP. Añadir tareas con objetivo/contexto, agente, dependencias, archivos esperados, estado, resultado y evidencia. Solo Hapic coordina; especialistas no delegan, evitando ciclos. Dependencias solo hacia tareas existentes del mismo proyecto. Ejecutar una tarea por llamada, sin reintentos automáticos tras timeout ambiguo. No introducir shell sin aislamiento y permisos definidos.

Primera entrega: crear/listar/ejecutar tareas desde MCP, persistencia y evidencia de archivos. Una entrega del modelo será `delivered`, nunca `verified` por sí sola. Siguiente: runner aislado, verificadores ejecutables y presupuesto por uso real; después scheduler paralelo, preguntas persistentes y UI. El paralelismo se pospone hasta resolver conflictos entre workspaces y recursos compartidos.

Para «quiero crear un juego», preguntar plataforma y restricciones esenciales agrupadas; proponer prototipo web local pequeño con supuestos reversibles. Arquitecto publica plan, coder lo lee y entrega HTML/JS e instrucciones. No añadir marketing ni infraestructura. La jugabilidad requiere navegador y pruebas de interacción; presencia y hash de HTML no la demuestran.

## Implementación y pruebas de esta sesión

`backend/tasks.py:Tasks` añade almacenamiento SQLite, contratos acotados, autorización exclusiva del coordinador, dependencias del mismo proyecto y ejecución de un especialista por llamada. `create` permite solo dependencias ya existentes, evitando ciclos. `run` limita el turno a 240 segundos, un intento y 64 KB de contexto de dependencias; comprueba archivos no vacíos y calcula SHA-256. No ejecuta código arbitrario. Los archivos esperados pueden existir previamente: la evidencia demuestra presencia actual, no autoría, frescura ni corrección funcional.

Estados: `planned`, `running`, `blocked`, `failed`, `delivered`. No se emite `verified` sin un verificador independiente. Los resultados y los contratos se conservan en SQLite. La cancelación guarda `failed`; una caída abrupta puede dejar `running`, visible al reiniciar y sin replay. Se recupera inspeccionando avances y creando una tarea explícita con el trabajo restante. Es recuperación supervisada, no reanudación automática de procesos.

`backend/app.py:create_app` publica MCP `create_task`, `list_tasks`, `run_task` y HTTP `GET /api/projects/{project_id}/tasks` con controles existentes de sesión/proyecto. `backend/templates.py:tools_for` los habilita solo para Hapic. `templates/hapic/SOUL.md` explica autonomía, preguntas esenciales, permisos y diferencia entre entrega y verificación. `Service.__init__` inicializa la tabla sin borrar datos anteriores. `scripts/start.ps1` ignora workspaces pnpm externos para instalar/compilar este frontend.

La base local inspeccionada contenía un solo Hapic registrado en `provisioning`, sin especialistas. No se modificaron sus mensajes, memorias ni credenciales. Docker respondió versión 29.9.2; eso no demuestra readiness de Hermes. No se hicieron llamadas facturables ni consultas OAuth reales. Los proveedores usados por las pruebas son dobles, exclusivamente en tests. La compilación real del frontend pasó.

`tests/test_tasks.py` cubre entrega con evidencias y persistencia, bloqueo por dependencias, aislamiento por proyecto, rechazo de traversal/delegación por especialistas, fallo con error redactado, conservación de avances, recuperación explícita y cancelación. El caso de juego usa respuestas de inferencia programadas pero herramientas reales de arquitecto y coder para publicar/leer el plan y escribir HTML e instrucciones. No es una prueba de calidad de planificación del modelo ni una partida en navegador. La suite existente comprueba además herramientas de los otros perfiles y contratos de Images/YouTube mediante dobles.

Resultado final: **47 pruebas aprobadas**, una advertencia de deprecación de Starlette/TestClient con httpx, en 20,54 s. `pnpm --ignore-workspace build` completó TypeScript y Vite correctamente. `git diff --check` pasó. La ejecución inicial dentro del aislamiento quedó bloqueada y se detuvo; la suite final se ejecutó fuera del aislamiento de sockets, sin proveedores reales.

## Iniciar y probar

Desde la raíz, ejecutar `.\scripts\start.ps1`; abrir http://127.0.0.1:8000. Dependencias instaladas en `.venv` y frontend compilado. Para recompilar: en frontend, `pnpm --ignore-workspace build`. Para pruebas: `.\.venv\Scripts\python.exe -m pytest -q --basetemp .hapic/test-nuevo`. Usar una carpeta temporal nueva; TestClient puede necesitar ejecución fuera del sandbox de sockets de Windows.

Configurar la key en Configuración, iniciar Docker y reiniciar el runtime de Hapic desde la plataforma para actualizar la lista MCP. Las instrucciones del coordinador se leen en cada turno. Pedir «quiero crear un juego». Responder plataforma/restricciones cuando sean esenciales. Hapic debe crear o reutilizar arquitecto/coder, iniciar sus runtimes, persistir tareas y ejecutar primero el plan y después el código. Consultar `list_tasks` en el chat o la ruta HTTP desde una sesión local autenticada. `delivered` no cierra la aceptación funcional: revisar el HTML en Archivos, abrirlo localmente y probar los criterios del plan.

Si una herramienta falla, comprobar `failed`, inspeccionar archivos conservados y pedir a Hapic una tarea de recuperación limitada al trabajo pendiente. Una tarea `running` tras caída no se relanza automáticamente. No tomar el silencio como permiso para repetir efectos inciertos.

## Pendientes por prioridad

1. Runner aislado con pruebas ejecutables y navegador para verificar jugabilidad; validación real con Hermes/modelo. Hoy no se puede prometer una versión jugable verificada de extremo a extremo.
2. Presupuesto agregado real de tokens/coste, límite por objetivo y cancelación remota confirmada. El timeout local no garantiza que el proveedor detenga trabajo remoto. El máximo actual de 100 tareas por proyecto es una protección básica, no un presupuesto monetario.
3. Recuperación con leases durables y reconciliación de efectos; scheduler paralelo solo para tareas independientes y sin conflictos de escritura.
4. Preguntas/aprobaciones persistentes, estados de verificación y UI de tareas. Hoy la política de preguntas está en instrucciones, no en una máquina de permisos por objetivo.
5. QA como capacidad ejecutable antes de añadir especialistas de seguridad, datos o juegos. Validar integración de perfiles existentes con proveedores reales cuando haya autorización y presupuesto.
