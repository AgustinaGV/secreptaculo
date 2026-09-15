import subprocess
from pathlib import Path

from gpiozero import DistanceSensor
from datetime import datetime
from time import sleep

sensor = DistanceSensor(echo=24, trigger=23)

INTERVALO_LECTURA = 0.5        # segundos entre cada lectura del sensor
RANGO_ACERCAMIENTO_CM = 30     # distancia para avisar que alguien se acerca
RANGO_GRABACION_CM = 15        # distancia para considerar "cerca"
CONFIRMACION_SEGUNDOS = 5      # segundos que hay que permanecer cerca antes de arrancar a grabar
ESPERA_PARA_CORTAR = 10        # segundos fuera del rango de grabación antes de cortar

DISPOSITIVO_ENTRADA_AUDIO = "plughw:1,0"   # placa de sonido USB; revisar con `arecord -l` si cambia
CARPETA_SECRETOS = Path(__file__).resolve().parent / "audios"
CARPETA_SECRETOS.mkdir(exist_ok=True)

grabando = False
hora_inicio = None
tiempo_fuera_desde = None
ultimo_restantes_impreso = None
tiempo_confirmacion_desde = None
ultimo_restantes_confirmacion = None
proceso_grabacion = None


def detener_grabacion_audio(proceso):
    # SIGTERM en vez de matar el proceso a la fuerza: así arecord cierra el .wav con el header bien armado
    proceso.terminate()
    proceso.wait()

try:
    while True:
        distancia_cm = sensor.distance * 100
        en_zona_grabacion = distancia_cm <= RANGO_GRABACION_CM
        en_zona_acercamiento = RANGO_GRABACION_CM < distancia_cm <= RANGO_ACERCAMIENTO_CM

        if not grabando:
            if en_zona_grabacion:
                ahora = datetime.now()
                if tiempo_confirmacion_desde is None:
                    tiempo_confirmacion_desde = ahora
                    ultimo_restantes_confirmacion = CONFIRMACION_SEGUNDOS
                    print(f"La grabación va a empezar en {CONFIRMACION_SEGUNDOS} segundos")
                else:
                    transcurrido = (ahora - tiempo_confirmacion_desde).total_seconds()
                    if transcurrido >= CONFIRMACION_SEGUNDOS:
                        grabando = True
                        hora_inicio = datetime.now()
                        tiempo_fuera_desde = None
                        ultimo_restantes_impreso = None
                        tiempo_confirmacion_desde = None
                        ultimo_restantes_confirmacion = None
                        ruta_secreto = CARPETA_SECRETOS / f"secreto_{hora_inicio.strftime('%Y%m%d_%H%M%S')}.wav"
                        proceso_grabacion = subprocess.Popen([
                            "arecord", "-D", DISPOSITIVO_ENTRADA_AUDIO, "-f", "cd", "-t", "wav", str(ruta_secreto)
                        ])
                        print(f"INICIO GRABACIÓN - {hora_inicio.strftime('%H:%M:%S')}")
                        print(f"Guardando en {ruta_secreto}")
                    else:
                        restantes = int(CONFIRMACION_SEGUNDOS - transcurrido)
                        if restantes != ultimo_restantes_confirmacion:
                            print(f"La grabación va a empezar en {restantes} segundos")
                            ultimo_restantes_confirmacion = restantes
            else:
                if tiempo_confirmacion_desde is not None:
                    print("Se canceló el inicio de grabación porque usuarix se alejó")
                    tiempo_confirmacion_desde = None
                    ultimo_restantes_confirmacion = None
                if en_zona_acercamiento:
                    print("Alguien se acerca")
                else:
                    print("Nadie cerca aún.")
        else:
            ahora = datetime.now()
            if en_zona_grabacion:
                if tiempo_fuera_desde is not None:
                    print(f"Usuarix cerca del sensor nuevamente. La grabación continúa desde las {ahora.strftime('%H:%M:%S')}")
                tiempo_fuera_desde = None
                ultimo_restantes_impreso = None
            else:
                if tiempo_fuera_desde is None:
                    tiempo_fuera_desde = ahora
                    ultimo_restantes_impreso = ESPERA_PARA_CORTAR
                    print(f"Usuarix alejándose. Quedan {ESPERA_PARA_CORTAR} segundos para detener la grabación")
                else:
                    transcurrido = (ahora - tiempo_fuera_desde).total_seconds()
                    if transcurrido >= ESPERA_PARA_CORTAR:
                        hora_fin = ahora
                        duracion = (hora_fin - hora_inicio).total_seconds()
                        detener_grabacion_audio(proceso_grabacion)
                        proceso_grabacion = None
                        print("Fin de grabación, usuarix se alejó de sensor.")
                        print(f"FIN GRABACIÓN - {hora_fin.strftime('%H:%M:%S')}")
                        print(f"Cantidad de segundos grabados: {duracion:.1f}")
                        grabando = False
                        hora_inicio = None
                        tiempo_fuera_desde = None
                        ultimo_restantes_impreso = None
                    else:
                        restantes = int(ESPERA_PARA_CORTAR - transcurrido)
                        if restantes != ultimo_restantes_impreso:
                            print(f"Usuarix alejándose. Quedan {restantes} segundos para detener la grabación")
                            ultimo_restantes_impreso = restantes

        sleep(INTERVALO_LECTURA)
except KeyboardInterrupt:
    print("Programa detenido.")
finally:
    if proceso_grabacion is not None:
        detener_grabacion_audio(proceso_grabacion)
    sensor.close()