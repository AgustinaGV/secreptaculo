# secreptáculo

Script de control de la "oreja" del altar `secreptáculo`, el sensor que graba los audios: detecta cuándo usuarix se acerca y, si se queda cerca el tiempo suficiente, graba su secreto y corta la grabación cuando se aleja.

Ver [CLAUDE.md](CLAUDE.md) para el detalle de la arquitectura del código. Este README explica el funcionamiento desde el punto de vista de quien va a correrlo o ajustarlo.

## Qué hace

`src/secreptaculo.py` corre en loop indefinido, midiendo la distancia con un sensor ultrasónico HC-SR04. Según esa distancia, distingue tres situaciones:

- Nadie cerca: no pasa nada.
- Alguien se acerca (entre 15 y 30 cm): avisa por consola.
- Alguien está cerca (15 cm o menos): si se mantiene ahí 5 segundos seguidos, arranca la "grabación".

Una vez arrancada, la grabación sigue mientras usuarix esté cerca. Si se aleja, hay una espera de 10 segundos antes de cortar (si vuelve antes de que se cumplan, la grabación sigue sin interrupción). Al cortar, imprime la hora de inicio, la hora de fin y la duración total. Habría que reducir un poco más esa espera.

La grabación es real: al arrancar, el script lanza `arecord` con la placa de sonido USB (micrófono corbatero) y guarda cada secreto como un `.wav` con fecha y hora (`secreto_AAAAMMDD_HHMMSS.wav`) en la carpeta `src/audios/`. Al cortar, o al salir con `Ctrl+C`, cierra el archivo correctamente. Probado en la Pi: funciona.

## Segundo sensor

Hay un segundo sensor ultrasónico, ya conectado y funcionando a nivel hardware, cuya función es disparar la reproducción de uno de los audios guardados. Su incorporación al script está en curso: la versión de `src/secreptaculo.py` commiteada hasta ahora solo lee el primer sensor.

## Próximos pasos

- Cablear el parlante (todavía no está conectado).
- Incorporar el segundo sensor al script (en curso).
- Completar la parte de salida de audio: que el segundo sensor dispare la reproducción de uno de los audios grabados, elegido al azar, y que el sonido salga por el parlante.
- Reducir `ESPERA_PARA_CORTAR`.

## Requisitos

- Raspberry Pi (probado con Pi Zero 2 W) con Raspberry Pi OS.
- Librería `gpiozero` instalada, con su backend de pines (`RPi.GPIO` o `lgpio`).
- Dos sensores HC-SR04 cableados según el punto siguiente.
- `arecord` (paquete `alsa-utils`) y una placa de sonido USB con micrófono. El dispositivo se define en `DISPOSITIVO_ENTRADA_AUDIO` (`plughw:1,0`); si cambia, revisar con `arecord -l`.

El script no corre fuera de una Raspberry Pi: `gpiozero` necesita el hardware GPIO real.

## Cableado

Sensor 1 (graba): `trigger=GPIO23`, `echo=GPIO24` (numeración BCM), con un divisor de tensión resistivo en la línea de ECHO (dos resistencias de 10 kΩ) para bajar los 5V de salida del sensor a un nivel seguro para el GPIO de la Pi, que tolera hasta 3.3V.

Sensor 2 (dispara la reproducción): `trigger=GPIO17` (pin físico 11), `echo=GPIO27` (pin físico 13), también con divisor de tensión en la línea de ECHO. Su incorporación al código está en curso.

Parlante: sin cablear.

## Cómo correrlo

```
python src/secreptaculo.py
```

Se corta con `Ctrl+C`. Al salir, libera el sensor correctamente (no hace falta matar el proceso a la fuerza).

## Parámetros

Todos los tiempos y distancias que definen la sensibilidad del dispositivo están como constantes al principio del archivo:

| Constante | Qué controla | Valor actual |
|---|---|---|
| `INTERVALO_LECTURA` | cada cuánto se lee el sensor | 0.5 s |
| `RANGO_ACERCAMIENTO_CM` | distancia para avisar "se acerca" | 30 cm |
| `RANGO_GRABACION_CM` | distancia considerada "cerca" | 15 cm |
| `CONFIRMACION_SEGUNDOS` | cuánto hay que quedarse cerca antes de arrancar a grabar | 5 s |
| `ESPERA_PARA_CORTAR` | cuánto hay que alejarse antes de que corte | 10 s (a reducir) |
| `DISPOSITIVO_ENTRADA_AUDIO` | placa de sonido desde la que graba `arecord` | `plughw:1,0` |

Para cambiar la sensibilidad del sensor, alcanza con editar estos valores.
