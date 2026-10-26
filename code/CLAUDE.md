# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

`secreptáculo` es una pieza de tecnología multimedial: dos sensores de proximidad ultrasónicos conectados a una Raspberry Pi, uno por puerta del altar. El de la "oreja" detecta cuándo alguien se acerca y, si se queda cerca el tiempo suficiente, graba un secreto real con el micrófono (`arecord` como subproceso) y lo guarda como `.wav` en `src/audios/`. El de la "boca" detecta proximidad y, tras una espera más corta, elige un secreto al azar entre los ya grabados y lo reproduce (`aplay` como subproceso). Las dos partes son mutuamente excluyentes: mientras una está activa, la otra no reacciona. El parlante de salida todavía no está cableado físicamente, así que la reproducción no se puede escuchar todavía aunque el código ya esté completo.

Todo el proyecto es un único archivo: [src/secreptaculo.py](src/secreptaculo.py).

## Ejecutar

```
python src/secreptaculo.py
```

`Ctrl+C` corta el loop de forma limpia: cierra cualquier proceso de audio en curso (grabación o reproducción) y libera los dos sensores en el `finally`.

No hay build, ni linter configurado, ni tests, ni archivo de dependencias. Depende de `gpiozero` (más su backend de pines, `RPi.GPIO` o `lgpio`) y de `arecord`/`aplay` (paquete `alsa-utils`), todo ya instalado de fábrica en la imagen de Raspberry Pi OS usada. Solo corre sobre hardware Raspberry Pi real: en una máquina de escritorio el import de `gpiozero` falla o los sensores no inicializan.

## Arquitectura

### Dos sensores, un mismo patrón de máquina de estados

`sensor_oreja` (`trigger=GPIO23`, `echo=GPIO24`) y `sensor_boca` (`trigger=GPIO17`, `echo=GPIO27`) comparten la misma lógica de "permanencia sostenida": hay que estar dentro de `RANGO_GRABACION_CM` durante un número de segundos de confirmación sin irse, o se cancela la cuenta. Esa lógica está extraída en `hubo_permanencia_sostenida()`, parametrizada por los segundos de confirmación, el estado propio de cada sensor (un diccionario con `desde` y `ultimo_restantes`) y los mensajes a imprimir, para no duplicar la máquina de estados entre los dos sensores y poder darle a cada uno su propia voz en consola.

- Oreja: `CONFIRMACION_SEGUNDOS` (5s) antes de arrancar a grabar. Mientras graba, si usuarix se aleja hay `ESPERA_PARA_CORTAR` (7s) antes de cortar; si vuelve antes, la grabación sigue sin interrupción. Al cortar, `recortar_silencio_final()` recorta el .wav hasta el último momento en que usuarix se alejó más `MARGEN_FINAL_SEGUNDOS` (2s), para no guardar el tramo de espera.
- Boca: `CONFIRMACION_SEGUNDOS_BOCA` (2s) antes de reproducir. Una vez que arranca, el secreto se reproduce entero sin cortarse aunque usuarix se aleje (a diferencia de la grabación). Si al terminar el secreto usuarix sigue a `RANGO_ACERCAMIENTO_CM` o menos, `boca_bloqueada` pasa a True, se imprime un único mensaje de bloqueo (con la hora) y la boca no cuenta ni reproduce nada más (tampoco imprime avisos de zona) hasta que haya `ESPERA_REHABILITAR_BOCA` (7s) seguidos con la lectura por encima de `RANGO_ACERCAMIENTO_CM`; cualquier lectura cerca reinicia esa espera. Ahí se imprime "A la espera de nuevx usuarix" con la hora y vuelve a reaccionar. La idea es que una misma persona escuche un solo secreto y después grabe el suyo. Si la oreja empieza a grabar mientras la boca está bloqueada, el bloqueo se anula (contar un secreto tiene prioridad) y se imprime "El sensor/boca ya puede reproducir secretos de nuevo", también con la hora. Limitación conocida y aceptada: el sensor solo mide distancia y no distingue personas. Si la persona A escuchó un secreto y sigue parada frente a la boca mientras la persona B graba el suyo en la oreja, al terminar esa grabación A todavía está ahí y la boca le reproduce otro secreto. Se decidió no resolverlo en el código.

### Exclusión mutua

Todo el bloque de la oreja corre envuelto en `if not reproduciendo`, y todo el bloque de la boca en `if not grabando`. Si un lado está activo, el otro no se procesa esa vuelta del loop (ni lee el sensor, ni imprime nada), hasta que el que estaba activo termina.

### Avisos de zona por consola

Cada sensor tiene tres zonas: "lejos", "acercamiento" (entre `RANGO_GRABACION_CM` y `RANGO_ACERCAMIENTO_CM`) y "cerca". `informar_zona(sensor, zona)` imprime el aviso solo cuando la zona cambió respecto de la última informada (`ultima_zona_informada`, un diccionario con una entrada por sensor), y todos los mensajes nombran el sensor ("sensor/oreja" o "sensor/boca"). `informar_llegada_directa()` se llama antes de `hubo_permanencia_sostenida()` y avisa "Alguien se acercó al sensor/oreja" (o "al sensor/boca") cuando usuarix aparece directo en la zona "cerca" sin haber pasado por "acercamiento". Cuando un lado se activa (empieza a grabar o a reproducir) se reinicia la cuenta de confirmación del otro con `reiniciar_confirmacion()`, para que no quede una cuenta vieja que se dispare apenas termina.

### Selección de secretos

`elegir_secreto_al_azar()` busca los `.wav` en `CARPETA_SECRETOS` (`src/audios/`) y elige uno al azar evitando repetir el último reproducido (`ultimo_reproducido`) y el más recién grabado (para no exponer de entrada el secreto que alguien acaba de dejar). Si no hay ningún secreto guardado, imprime un mensaje de error y no reproduce nada.

### Procesos de audio

`proceso_grabacion` y `proceso_reproduccion` guardan la referencia al subproceso de `arecord`/`aplay` en curso. `detener_proceso_audio()` los corta con `terminate()` (no con `kill`), para que el archivo o la reproducción cierren prolijamente. La reproducción, a diferencia de la grabación, no se corta manualmente por distancia: se chequea en cada vuelta del loop si el proceso ya terminó solo (`poll()`).

## Convenciones

- Los mensajes de consola son parte de la obra, no logs de debug: están redactados con voz propia y lenguaje inclusivo ("usuarix"). Mantener ese registro al agregar mensajes nuevos.
- Comentarios y nombres de variables en español rioplatense.
- Al tocar el pin de un sensor, verificar contra el cableado físico real antes de asumir nada: ya pasó que el código quedó con un pin viejo de una sesión de diagnóstico y no coincidía con el cableado actual.
