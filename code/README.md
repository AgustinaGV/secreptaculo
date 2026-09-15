# secreptáculo

Script de control para el sensor de la oreja del altar `secreptáculo`: detecta cuándo usuarix se acerca y, si se queda cerca el tiempo suficiente, simula el inicio y el corte de una grabación.

Ver [CLAUDE.md](CLAUDE.md) para el detalle de la arquitectura del código. Este README explica el funcionamiento desde el punto de vista de quien va a correrlo o ajustarlo.

## Qué hace

`src/secreptaculo.py` corre en loop indefinido, midiendo la distancia con un sensor ultrasónico HC-SR04. Según esa distancia, distingue tres situaciones:

- Nadie cerca: no pasa nada.
- Alguien se acerca (entre 15 y 30 cm): avisa por consola.
- Alguien está cerca (15 cm o menos): si se mantiene ahí 5 segundos seguidos, arranca la "grabación".

Una vez arrancada, la grabación sigue mientras usuarix esté cerca. Si se aleja, hay una espera de 15 segundos antes de cortar (si vuelve antes de que se cumplan, la grabación sigue sin interrupción). Al cortar, imprime la hora de inicio, la hora de fin y la duración total.

Por ahora la grabación es simulada: el script no captura audio todavía, solo imprime los mensajes de estado por consola. La captura real del secreto (desde el micrófono corbatero) y su almacenamiento son el próximo paso.

## Requisitos

- Raspberry Pi (probado con Pi Zero 2 W) con Raspberry Pi OS.
- Librería `gpiozero` instalada, con su backend de pines (`RPi.GPIO` o `lgpio`).
- Un sensor HC-SR04 cableado según el punto siguiente.

El script no corre fuera de una Raspberry Pi: `gpiozero` necesita el hardware GPIO real.

## Cableado

El sensor va a `trigger=GPIO23`, `echo=GPIO24` (numeración BCM), con un divisor de tensión resistivo en la línea de ECHO (dos resistencias de 10 kΩ) para bajar los 5V de salida del sensor a un nivel seguro para el GPIO de la Pi, que tolera hasta 3.3V.

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
| `ESPERA_PARA_CORTAR` | cuánto hay que alejarse antes de que corte | 15 s |

Para cambiar la sensibilidad del sensor, alcanza con editar estos valores.
