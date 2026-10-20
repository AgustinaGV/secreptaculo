# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

`secreptáculo` es una pieza de tecnología multimedial: un sensor de proximidad ultrasónico conectado a una Raspberry Pi que detecta cuándo una persona se acerca o se aleja y, en función de eso, dispara y corta una "grabación". La grabación de audio es real: al arrancar se lanza `arecord` como subproceso (placa de sonido USB, `DISPOSITIVO_ENTRADA_AUDIO`) y cada secreto se guarda como `.wav` en `src/audios/`; al cortar se termina el proceso con `terminate()` para que el archivo quede bien cerrado. Además imprime mensajes de estado por consola (`INICIO GRABACIÓN`, cuenta regresiva, `FIN GRABACIÓN`, duración). Todavía no hay salida de audio. Hay un segundo sensor ultrasónico (`trigger=GPIO17`, `echo=GPIO27`), ya conectado y funcionando a nivel hardware (con divisor de tensión en echo), cuya incorporación al script está en curso, cuya función es disparar la reproducción de uno de los `.wav` ya grabados, elegido al azar. El parlante todavía no está cableado: ese es el punto de extensión natural.

Todo el proyecto es un único archivo: [src/secreptaculo.py](src/secreptaculo.py).

## Ejecutar

Corre en una Raspberry Pi con un sensor tipo HC-SR04 cableado a `trigger=GPIO23` y `echo=GPIO24` (ver línea 8).

```
python src/secreptaculo.py
```

`Ctrl+C` corta el loop de forma limpia (`KeyboardInterrupt` -> `sensor.close()` en el `finally`).

No hay build, ni linter configurado, ni tests, ni archivo de dependencias. La única dependencia externa es `gpiozero` (más su backend de pines, `RPi.GPIO` o `lgpio`), que solo funciona sobre hardware Raspberry Pi. En una máquina de escritorio el import de `gpiozero` falla o el sensor no inicializa: no se puede correr tal cual fuera de la Pi.

## Arquitectura

### Máquina de estados

El programa es un loop infinito que lee la distancia cada `INTERVALO_LECTURA` segundos y opera con dos estados, gobernados por la variable booleana `grabando`:

- `grabando = False`: espera. Si hay alguien dentro de `RANGO_GRABACION_CM` de forma sostenida durante `CONFIRMACION_SEGUNDOS`, pasa a `grabando = True`. Si la persona se aleja antes de cumplir ese tiempo, se cancela y se resetea el contador de confirmación.
- `grabando = True`: grabando. Si la persona sale de `RANGO_GRABACION_CM` durante `ESPERA_PARA_CORTAR` segundos seguidos, corta y vuelve a `grabando = False`. Si vuelve a entrar antes, se cancela el corte y la grabación "continúa".

Ambas transiciones tienen histéresis temporal (debounce): no reaccionan a una única lectura, sino a una condición sostenida, medida comparando `datetime.now()` contra un timestamp de inicio (`tiempo_confirmacion_desde`, `tiempo_fuera_desde`). Esto evita que un rebote del sensor arranque o corte la grabación.

Hay tres zonas de distancia: dentro de `RANGO_GRABACION_CM` ("cerca"), entre ese valor y `RANGO_ACERCAMIENTO_CM` ("alguien se acerca"), y más lejos ("nadie cerca").

### Parámetros

Los cinco parámetros de comportamiento son constantes en mayúsculas al tope del archivo (líneas 10-14): intervalo de lectura, los dos umbrales de distancia, y los dos tiempos de confirmación/corte. Ajustar la sensibilidad de la pieza se hace ahí, no tocando la lógica.

### Patrón de impresión por cambio

Las variables `ultimo_restantes_impreso` y `ultimo_restantes_confirmacion` guardan el último número de cuenta regresiva que se imprimió, para no repetir la misma línea en cada iteración del loop. Solo se imprime cuando el valor entero de segundos restantes cambia. Al entrar o salir de un estado, estas variables (junto con los timestamps) se resetean a `None`. Si se agrega estado nuevo, hay que mantener ese reseteo consistente.

## Convenciones

- Los mensajes de consola son parte de la obra, no logs de debug: están redactados con voz propia y lenguaje inclusivo ("usuarix", "se alejó de sensor"). Mantener ese registro al agregar mensajes.
- Comentarios y nombres de variables en español rioplatense.
