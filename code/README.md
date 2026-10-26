# secreptáculo

Script de control de las dos partes interactivas del altar `secreptáculo`: la "oreja", que graba los secretos, y la "boca", que los reproduce.

Ver [CLAUDE.md](CLAUDE.md) para el detalle de la arquitectura del código. Este README explica el funcionamiento desde el punto de vista de quien va a correrlo o ajustarlo.

## Qué hace

`src/secreptaculo.py` corre en loop indefinido, leyendo dos sensores ultrasónicos HC-SR04, uno por cada puerta.

Oreja: si alguien se queda cerca (10 cm o menos) 5 segundos seguidos, arranca a grabar con el micrófono (`arecord`) y guarda el secreto como `.wav` con fecha y hora en `src/audios/`. Si se aleja, espera 7 segundos antes de cortar (si vuelve antes, la grabación sigue sin interrupción). Al cortar, el archivo se recorta para descartar el tramo de espera: se conserva hasta el momento en que la persona se fue por última vez, más 2 segundos de margen.

Boca: si alguien se queda cerca 2 segundos seguidos, elige al azar uno de los secretos ya grabados (evitando repetir el último reproducido o el recién grabado) y lo reproduce entero con `aplay`, sin cortarse aunque la persona se aleje. Si al terminar la persona sigue cerca (a 20 cm o menos), la boca se bloquea para que no se le cuenten dos secretos seguidos: imprime un único mensaje (con la hora) y no reproduce nada más hasta que pasen 7 segundos seguidos sin nadie cerca. Ahí imprime "A la espera de nuevx usuarix" con la hora y vuelve a funcionar. Si mientras tanto alguien empieza a grabar en la oreja, el bloqueo se anula (contar un secreto tiene prioridad) y se imprime "El sensor/boca ya puede reproducir secretos de nuevo", también con la hora.

Mientras una de las dos partes está activa (grabando o reproduciendo), la otra no reacciona: son mutuamente excluyentes.

Avisos por consola: cada mensaje dice de qué sensor viene ("sensor/oreja" / "sensor/boca"). Los avisos de zona ("Alguien se acerca", "Nadie cerca") se imprimen solo cuando la zona cambia, no en cada lectura. Si alguien aparece directamente a 10 cm o menos, sin pasar antes por la zona de acercamiento (10 a 20 cm), igual se avisa "Alguien se acercó al sensor/oreja" (o "al sensor/boca") antes de que arranque la cuenta regresiva.

Estado de las pruebas: la grabación de punta a punta (audio guardado y reproducible) se probó en la Pi antes de los últimos cambios. Desde entonces se agregaron el recorte del silencio final, el bloqueo de la boca, la anulación del bloqueo al grabar y los umbrales nuevos (20 y 10 cm). Esos cambios se probaron en la Pi solo sin placa de sonido ni micrófono (sensores, mensajes y lógica), así que falta verificarlos con audio real. La reproducción está completa en el código, pero todavía no se puede escuchar porque el parlante no está cableado.

## Próximos pasos

- Cablear el parlante (todavía no está conectado), para poder escuchar la reproducción.
- Agregar un audio fijo que se reproduzca después del secreto aleatorio, para invitar a la persona a contar el suyo en la oreja.
- Eventualmente, que el script arranque solo al bootear la Pi.

## Requisitos

- Raspberry Pi (probado con Pi Zero 2 W) con Raspberry Pi OS.
- Librería `gpiozero` instalada, con su backend de pines (`RPi.GPIO` o `lgpio`).
- Dos sensores HC-SR04 cableados según el punto siguiente.
- `arecord` y `aplay` (paquete `alsa-utils`) y una placa de sonido USB. Los dispositivos se definen en `DISPOSITIVO_ENTRADA_AUDIO` y `DISPOSITIVO_SALIDA_AUDIO` (`plughw:1,0`); si cambian, revisar con `arecord -l` / `aplay -l`.

El script no corre fuera de una Raspberry Pi: `gpiozero` necesita el hardware GPIO real.

## Cableado

Sensor 1, oreja (graba): `trigger=GPIO23`, `echo=GPIO24`, con divisor de tensión resistivo en la línea de ECHO (dos resistencias de 10 kΩ) para bajar los 5V del sensor a un nivel seguro para el GPIO de la Pi (máximo 3.3V).

Sensor 2, boca (reproduce): `trigger=GPIO17`, `echo=GPIO27`, mismo esquema de divisor de tensión en el ECHO.

Parlante: sin cablear todavía.

## Cómo correrlo

```
python src/secreptaculo.py
```

Se corta con `Ctrl+C`. Al salir, cierra prolijamente cualquier proceso de audio en curso y libera los dos sensores.

## Parámetros

| Constante | Qué controla | Valor actual |
|---|---|---|
| `INTERVALO_LECTURA` | cada cuánto se lee cada sensor | 0.5 s |
| `RANGO_ACERCAMIENTO_CM` | distancia para avisar "se acerca" | 20 cm |
| `RANGO_GRABACION_CM` | distancia considerada "cerca" (se usa para grabar y para reproducir) | 10 cm |
| `CONFIRMACION_SEGUNDOS` | cuánto hay que quedarse cerca de la oreja antes de arrancar a grabar | 5 s |
| `CONFIRMACION_SEGUNDOS_BOCA` | cuánto hay que quedarse cerca de la boca antes de que empiece a hablar | 2 s |
| `ESPERA_PARA_CORTAR` | cuánto hay que alejarse antes de que corte la grabación | 7 s |
| `MARGEN_FINAL_SEGUNDOS` | cuánto se conserva después de que la persona se aleja, al recortar el silencio final de la grabación | 2 s |
| `ESPERA_REHABILITAR_BOCA` | cuántos segundos seguidos sin nadie cerca de la boca hacen falta para que vuelva a reproducir después de un secreto | 7 s |
| `DISPOSITIVO_ENTRADA_AUDIO` | placa de sonido desde la que graba `arecord` | `plughw:1,0` |
| `DISPOSITIVO_SALIDA_AUDIO` | placa de sonido por la que reproduce `aplay` | `plughw:1,0` |

Para cambiar la sensibilidad del dispositivo, alcanza con editar estos valores.
