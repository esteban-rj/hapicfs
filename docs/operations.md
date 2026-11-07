# Operación local

Consulta primero el [README](../README.md) para instalar dependencias y arrancar la plataforma.

## Arranque con Docker

En Windows, inicia Docker Desktop con motor Linux y ejecuta:

```powershell
.\scripts\start-docker.ps1
```

Si la instalación de WSL o de Virtual Machine Platform requiere reinicio, reinicia Windows antes de comprobar el motor. Tener `docker.exe` no garantiza que el daemon responda.

En Linux, desde la raíz del repositorio:

```bash
export HAPIC_HOST_DATA_DIR="$(pwd)/.hapic"
mkdir -p "$HAPIC_HOST_DATA_DIR"
docker compose up --build -d
```

`HAPIC_HOST_DATA_DIR` debe ser la ruta absoluta que interpreta el daemon Docker. No es la ruta `/data` del interior del control de gestión. Se monta en `/data` y se utiliza para calcular los volúmenes de agentes nuevos. El despliegue inicial fue verificado con Docker Desktop en Windows; las instrucciones Linux requieren validación en ese entorno.

## Comprobaciones

```powershell
docker version
docker compose version
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

La salud de FastAPI solo confirma el control de gestión. En la interfaz, abre el agente y comprueba **Runtime real**. El estado disponible exige que la API autenticada de Hermes responda `status: ok`; el primer turno comprueba el acceso efectivo al modelo.

## Credencial de OpenAI

En la plataforma: **Configuración → Conexión con OpenAI → API key → Guardar credencial**.

También se admite `OPENAI_API_KEY` en el entorno del servidor o en `.env`. Cuando está definida en el entorno, la UI informa de su origen y no permite reemplazarla desde el formulario. Compose interpola la variable para el control de gestión.

No incluyas la key en chats, comandos guardados, incidencias ni capturas. La API solo devuelve si está configurada y su origen.

Para rotarla, guarda la nueva key en su origen y reinicia los agentes desde la interfaz para recrear sus entornos. Eliminar el archivo de credencial del servidor no revoca la key en OpenAI ni borra el entorno de contenedores existentes.

## Ciclo de vida de contenedores

Para cargar el cliente OAuth de YouTube en el servidor, usa `./scripts/start-docker.sh "/ruta/privada/google-oauth.json"` en macOS/Linux o `scripts/start-docker.ps1 -YouTubeClientJson 'C:\ruta\privada\google-oauth.json'` en Windows. Activa el secreto de `compose.youtube.yaml` exclusivamente en el control de gestión; los clientes conectan sus canales sin subir archivos. También se puede iniciar el servidor nativo con `HAPIC_YOUTUBE_CLIENT_FILE` apuntando al archivo privado. Consulta [YouTube](youtube.md#credenciales-administradas-en-docker) para el despliegue y la rotación.

Compose administra el control de gestión. Los contenedores Hermes se crean dinámicamente y siguen un ciclo de vida independiente. `docker compose stop` no detiene por sí solo esos agentes.

Para detener un agente concreto, identifica su nombre en **Runtime real** y ejecuta `docker stop` con ese nombre exacto. Para recrearlo, usa **Iniciar runtime** o **Reiniciar runtime** en la UI. La recreación conserva los directorios montados del perfil y del workspace.

No elimines `.hapic/` para reiniciar la plataforma. No borres volúmenes o carpetas como método de recuperación.

## Copia de seguridad y restauración

Una copia completa requiere `.hapic/`, incluidos `platform.db`, todos los perfiles, workspaces y `secrets/`. La clave maestra local es necesaria para descifrar las credenciales y los tokens.

Detén el control de gestión y los agentes antes de copiar sus archivos para obtener una copia coherente de las bases SQLite. Protege la copia como información sensible y guárdala fuera de Git.

Al restaurar:

1. Recupera `.hapic/` completo, conservando sus permisos y su clave maestra.
2. Configura `HAPIC_HOST_DATA_DIR` con la ruta absoluta restaurada.
3. Inicia la plataforma y comprueba organizaciones, proyectos y archivos.
4. Recrea los runtimes desde la UI si los contenedores originales ya no existen o se cambió de máquina.

Un directorio que solo contenga el workspace no recupera memoria, historial ni credenciales.

## Actualizar imágenes y dependencias

El valor inicial de `HERMES_IMAGE` es `nousresearch/hermes-agent:stable`. Para un despliegue reproducible, fija una versión o digest probado en `.env`; no guardes allí claves si vas a compartir ese archivo.

Antes de cambiar la imagen, realiza una copia coherente de los datos. Reconstruye el control de gestión con `docker compose up --build -d` y recrea los agentes cuando corresponda. Los contenedores existentes conservan su imagen hasta recrearse.

Las dependencias de la interfaz se fijan en `frontend/pnpm-lock.yaml`; las de Python, en `requirements.lock`. Si se actualizan, usa un entorno virtual limpio, ejecuta los checks y regenera el lock de Python con `scripts/freeze.py` cuando sea necesario.

## Diagnóstico

Para aplicar herramientas nuevas a un agente existente, recréalo con **Reiniciar runtime** después de actualizar el control de gestión. Conserva su memoria, historial y workspace.

La generación de imágenes usa `HAPIC_IMAGE_MODEL` (predeterminado `gpt-image-2.5-flare`), configurado en el entorno del servidor y Compose. Necesita acceso a ese modelo con la key de OpenAI guardada. Los errores informan el código HTTP sin copiar respuestas sensibles del proveedor. No reintentes automáticamente una generación con resultado incierto: puede haberse facturado.

Los PNG se guardan en el workspace del agente y se incluyen en la copia completa de `.hapic/`. Una descripción de imagen o un enlace inventado por un turno anterior no permite recuperar un archivo que nunca se generó. Para un coder sin plan, pide al arquitecto vinculado que publique primero el plan con su herramienta.

| Síntoma | Comprobación |
| --- | --- |
| `docker` no se reconoce | Reabre la terminal después de instalar Docker Desktop y revisa su PATH |
| Cliente presente, daemon detenido | Inicia Docker Desktop; comprueba WSL2, virtualización y reinicios pendientes |
| Puerto 8000 ocupado | Comprueba si ya está ejecutándose el servidor nativo o Compose antes de iniciar otro |
| Credencial pendiente | Configúrala en el formulario dedicado o en el entorno del servidor |
| API Hermes lista, turno rechazado | Comprueba acceso al modelo, permisos y saldo de OpenAI; revisa el HTTP informado |
| Provisión interrumpida | Consulta actividad y runtime; vuelve a solicitar el inicio desde la UI |
| Archivo ausente del explorador | Comprueba el workspace del agente, el tipo de archivo y si está protegido |

Los logs de Docker pueden contener información sensible. Revísalos localmente y redacta cualquier dato privado antes de compartirlos.

## Validación sin consumo de API

```powershell
$env:HAPIC_DATA_DIR = Join-Path (Get-Location) ('.hapic/test-local-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --basetemp "$env:HAPIC_DATA_DIR/tmp"
Set-Location frontend
pnpm build
```

Los tests usan almacenamiento temporal y dobles de Docker/Hermes; no solicitan inferencia facturable. Una prueba de enlaces simbólicos puede omitirse en Windows cuando no hay permiso para crearlos. Las pruebas reales de inferencia deben habilitarse conscientemente y mantenerse separadas del entorno de trabajo.
