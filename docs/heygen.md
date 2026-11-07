# HeyGen: generación de clips con audio

Implementado y revisado el 2026-11-07. Usa `heygen-video-1` mediante la API v3 para generar clips desde texto o una imagen pública y guardar el MP4 en el workspace. No publica en redes ni utiliza avatares, traducciones o Video Agent, que tienen otros precios.

## Conectar

1. En **Herramientas**, selecciona el proyecto y abre **HeyGen**.
2. Crea una API key en el [panel de HeyGen](https://platform.heygen.com/api-keys), con saldo de API y permisos `videos:read` y `videos:write`. Pégala únicamente en el formulario de clave.
3. Pulsa **Conectar HeyGen**. Hapic verifica la cuenta con `GET /v3/users/me` y la clave activa y sus permisos con `GET /v3/api_keys/self`. Solo entonces la cifra en el servidor, fuera del workspace y del contenedor Hermes.
4. En **Herramientas por agente**, habilita HeyGen y selecciona la cuenta. Community Manager la incluye habilitada; una única cuenta conectada completa automáticamente sus asignaciones vacías. Los demás perfiles pueden recibirla manualmente.
5. Si el runtime ya estaba iniciado, reinícialo desde la plataforma para cargar la nueva lista de herramientas.

Pide al agente, por ejemplo: «Genera un vídeo vertical de 5 segundos a 480p de una taza de café sobre una mesa, con sonido ambiente». El agente consulta el trabajo hasta terminar. También puedes abrir **Herramientas → HeyGen → Vídeos del proyecto**, pulsar **Actualizar lista** y **Consultar y guardar**. El MP4 guardado aparece en la conversación y en **Archivos**, con reproducción y descarga autenticadas. Reiniciar Hapic conserva los trabajos; consultar reanuda su seguimiento sin generar otra pieza.

## Alcance y costes

| Opción | Disponible |
| --- | --- |
| Duración | De 5 a 15 segundos enteros; predeterminado 5 |
| Resolución | 480p, 768p o 1080p; predeterminada 480p |
| Formato | 21:9, 16:9, 4:3, 1:1, 3:4 o 9:16; en 1080p solo 16:9 o 9:16 |
| Imagen opcional | URL HTTPS pública y directa; el resultado conserva su encuadre |
| Salida | MP4 con audio, hasta 100 MiB |

Referencia de precios consultada el 2026-11-07: 480p US$0,01/s; 768p US$0,018/s; 1080p US$0,04/s. Un clip predeterminado de 5 s a 480p tiene un coste estimado de US$0,05. La estimación local no acredita un cargo ni un saldo; la tarifa real depende de HeyGen. [Precios oficiales](https://help.heygen.com/en/articles/10060327-heygen-api-pricing-credits-explained).

## Herramientas

| Herramienta | Contrato |
| --- | --- |
| `heygen_generate_video` | `prompt` y `request_id` obligatorios; `duration`, `resolution`, `aspect_ratio` e `image_url` opcionales |
| `heygen_get_video` | `video_id`: el **id local** devuelto al generar; consulta el estado y guarda el MP4 al terminar |
| `heygen_list_videos` | Hasta 50 trabajos del propio agente y de su conexión actualmente asignada |

`request_id` admite de 8 a 80 letras, números, guiones y guiones bajos. Identifica una sola pieza: usar el mismo con otra cuenta o contenido se rechaza. Cada llamada comprueba pertenencia al proyecto, herramienta habilitada y conexión asignada; el modelo no elige el alcance.

## Persistencia y recuperación

La tabla `video_jobs` registra la solicitud, agente, conexión, id local, estado y coste estimado antes del POST facturable. El id local se usa como `Idempotency-Key` de HeyGen. Un trabajo aceptado se consulta con GET; repetir la herramienta de generación con el mismo `request_id` devuelve el registro existente.

Si se interrumpe el envío antes de recibir el id remoto, queda `submission_unknown`. Reutilizar el mismo `request_id`, contenido, cuenta y API key recupera el POST con la misma clave de idempotencia. Hapic limita esa recuperación a menos de 23 horas para mantenerse dentro de las 24 horas documentadas por HeyGen. Pasado el plazo, o si la clave rotó, exige comprobar el proveedor antes de crear otra pieza. No hay reintentos automáticos de generación.

`completed` significa que HeyGen terminó; solo `saved=true` confirma el archivo en disco. Si falla la descarga, consulta otra vez el mismo trabajo: se obtiene un enlace firmado actualizado sin regenerar. Solo se descargan HTTPS de dominios de HeyGen, sin redirecciones ni credenciales en el CDN. Se valida y escribe el MP4 atómicamente antes de adjuntarlo al chat.

Desconectar elimina la clave local y las asignaciones. Los MP4 guardados permanecen disponibles. Los trabajos aceptados pueden seguir procesándose y facturándose en HeyGen: desconectar Hapic no los cancela ni revoca la clave en el proveedor. Puedes revocarla desde el panel de HeyGen.

## Verificación

`tests/test_heygen.py` usa un transporte HTTP exclusivo de pruebas para verificar el contrato v3, cifrado, permisos, aislamiento, idempotencia concurrente y tras reinicios, envíos inciertos, errores redactados y recuperación de descargas. Comprueba adjuntos, archivos, autenticación y solicitudes Range. Las pruebas no realizan generaciones facturables ni acreditan conexión real sin credenciales del usuario.

Fuentes: [API key](https://developers.heygen.com/docs/api-key), [permisos de la clave](https://developers.heygen.com/reference/get-current-api-key) y [HeyGen Video](https://developers.heygen.com/docs/models/heygen-video).
