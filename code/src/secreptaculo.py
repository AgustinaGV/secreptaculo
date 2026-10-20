import random
import subprocess
from pathlib import Path

from gpiozero import DistanceSensor
from datetime import datetime
from time import sleep

sensor_oreja = DistanceSensor(echo=24, trigger=23)
sensor_boca = DistanceSensor(echo=17, trigger=25)

INTERVALO_LECTURA = 0.5        # segundos entre cada lectura de los sensores
RANGO_ACERCAMIENTO_CM = 30     # distancia para avisar que alguien se acerca
RANGO_GRABACION_CM = 15        # distancia para considerar "cerca" (se usa para grabar y para reproducir)
CONFIRMACION_SEGUNDOS = 5      # segundos que hay que permanecer cerca de la oreja antes de arrancar a grabar
CONFIRMACION_SEGUNDOS_BOCA = 2 # segundos que hay que permanecer cerca de la boca antes de que empiece a hablar
ESPERA_PARA_CORTAR = 10        # segundos fuera del rango de grabación antes de cortar

DISPOSITIVO_ENTRADA_AUDIO = "plughw:1,0"   # placa de sonido USB; revisar con `arecord -l` si cambia
DISPOSITIVO_SALIDA_AUDIO = "plughw:1,0"    # misma placa; revisar con `aplay -l` si cambia
CARPETA_SECRETOS = Path(__file__).resolve().parent / "audios"
CARPETA_SECRETOS.mkdir(exist_ok=True)

grabando = False
hora_inicio = None
tiempo_fuera_desde = None
ultimo_restantes_impreso = None
proceso_grabacion = None

reproduciendo = False
hora_inicio_reproduccion = None
proceso_reproduccion = None
ultimo_reproducido = None   # último secreto elegido, para no repetirlo dos veces seguidas

# Estado de la cuenta regresiva de "permanencia sostenida" de cada sensor. Es la
# misma máquina de estados para los dos (oreja y boca), solo cambian los segundos
# de confirmación y qué pasa al cumplirse, así que cada uno tiene su propio
# diccionario en vez de duplicar las variables sueltas.
estado_confirmacion_oreja = {"desde": None, "ultimo_restantes": None}
estado_confirmacion_boca = {"desde": None, "ultimo_restantes": None}


def hubo_permanencia_sostenida(en_rango, segundos_confirmacion, estado, texto_cuenta_regresiva, texto_cancelado):
    """
    Devuelve True en la vuelta del loop en la que usuarix completó
    `segundos_confirmacion` segundos seguidos dentro del rango de distancia
    (`en_rango`, ya calculado por quien llama). Si usuarix se aleja antes de
    completar la espera, cancela la cuenta e imprime `texto_cancelado`.

    `estado` guarda, por sensor, desde cuándo se está contando y cuál fue el
    último número de segundos restantes impreso (para no repetir el mismo
    mensaje en cada vuelta del loop).

    `texto_cuenta_regresiva` es una función que recibe los segundos restantes
    y devuelve el mensaje a imprimir; se usa tanto al arrancar la cuenta como
    en cada actualización, así cada sensor puede tener su propia voz.
    """
    if not en_rango:
        if estado["desde"] is not None:
            print(texto_cancelado)
            estado["desde"] = None
            estado["ultimo_restantes"] = None
        return False

    ahora = datetime.now()
    if estado["desde"] is None:
        estado["desde"] = ahora
        estado["ultimo_restantes"] = segundos_confirmacion
        print(texto_cuenta_regresiva(segundos_confirmacion))
        return False

    transcurrido = (ahora - estado["desde"]).total_seconds()
    if transcurrido >= segundos_confirmacion:
        estado["desde"] = None
        estado["ultimo_restantes"] = None
        return True

    restantes = int(segundos_confirmacion - transcurrido)
    if restantes != estado["ultimo_restantes"]:
        print(texto_cuenta_regresiva(restantes))
        estado["ultimo_restantes"] = restantes
    return False


def detener_proceso_audio(proceso):
    # SIGTERM en vez de matar el proceso a la fuerza: así arecord cierra el .wav con el header bien armado
    proceso.terminate()
    proceso.wait()


def elegir_secreto_al_azar():
    """
    Devuelve la ruta de un secreto al azar de CARPETA_SECRETOS, evitando repetir
    el último reproducido y evitando el más recién grabado (para no exponer de
    entrada el secreto que alguien acaba de dejar). Si no hay ningún secreto
    guardado, devuelve None.
    """
    archivos = sorted(CARPETA_SECRETOS.glob("*.wav"))
    if not archivos:
        return None

    mas_reciente = archivos[-1]
    candidatos = [a for a in archivos if a != ultimo_reproducido and a != mas_reciente]
    if not candidatos:
        # Con pocos secretos guardados puede no quedar ningún candidato que
        # cumpla las dos exclusiones a la vez: se prioriza no repetir el
        # recién grabado por sobre no repetir el último reproducido.
        candidatos = [a for a in archivos if a != mas_reciente]
    if not candidatos:
        candidatos = archivos

    return random.choice(candidatos)


try:
    while True:
        distancia_oreja_cm = sensor_oreja.distance * 100
        en_zona_grabacion = distancia_oreja_cm <= RANGO_GRABACION_CM
        en_zona_acercamiento = RANGO_GRABACION_CM < distancia_oreja_cm <= RANGO_ACERCAMIENTO_CM

        # Mientras la boca está reproduciendo un secreto, la oreja no reacciona:
        # las dos partes del ritual son mutuamente excluyentes.
        if not reproduciendo:
            if not grabando:
                completo = hubo_permanencia_sostenida(
                    en_rango=en_zona_grabacion,
                    segundos_confirmacion=CONFIRMACION_SEGUNDOS,
                    estado=estado_confirmacion_oreja,
                    texto_cuenta_regresiva=lambda s: f"La grabación va a empezar en {s} segundos",
                    texto_cancelado="Se canceló el inicio de grabación porque usuarix se alejó",
                )
                if completo:
                    grabando = True
                    hora_inicio = datetime.now()
                    tiempo_fuera_desde = None
                    ultimo_restantes_impreso = None
                    ruta_secreto = CARPETA_SECRETOS / f"secreto_{hora_inicio.strftime('%Y%m%d_%H%M%S')}.wav"
                    proceso_grabacion = subprocess.Popen([
                        "arecord", "-D", DISPOSITIVO_ENTRADA_AUDIO, "-f", "cd", "-t", "wav", str(ruta_secreto)
                    ])
                    print(f"INICIO GRABACIÓN - {hora_inicio.strftime('%H:%M:%S')}")
                    print(f"Guardando en {ruta_secreto}")
                elif not en_zona_grabacion:
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
                            detener_proceso_audio(proceso_grabacion)
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

        # Mientras la oreja está grabando, la boca no reacciona: mismo motivo
        # que arriba, al revés.
        if not grabando:
            distancia_boca_cm = sensor_boca.distance * 100
            en_zona_cerca_boca = distancia_boca_cm <= RANGO_GRABACION_CM
            en_zona_acercamiento_boca = RANGO_GRABACION_CM < distancia_boca_cm <= RANGO_ACERCAMIENTO_CM

            if not reproduciendo:
                completo_boca = hubo_permanencia_sostenida(
                    en_rango=en_zona_cerca_boca,
                    segundos_confirmacion=CONFIRMACION_SEGUNDOS_BOCA,
                    estado=estado_confirmacion_boca,
                    texto_cuenta_regresiva=lambda s: f"La boca va a hablar en {s} segundos",
                    texto_cancelado="Se canceló: usuarix se alejó antes de que la boca empezara a hablar",
                )
                if completo_boca:
                    secreto_elegido = elegir_secreto_al_azar()
                    if secreto_elegido is None:
                        print("Error. Todavía no hay secretos guardados, no hay nada para reproducir.")
                    else:
                        reproduciendo = True
                        hora_inicio_reproduccion = datetime.now()
                        ultimo_reproducido = secreto_elegido
                        proceso_reproduccion = subprocess.Popen([
                            "aplay", "-D", DISPOSITIVO_SALIDA_AUDIO, str(secreto_elegido)
                        ])
                        print(f"LA BOCA EMPIEZA A HABLAR - {hora_inicio_reproduccion.strftime('%H:%M:%S')}")
                        print(f"Reproduciendo {secreto_elegido.name}")
                elif not en_zona_cerca_boca:
                    if en_zona_acercamiento_boca:
                        print("Alguien se acerca a la boca")
                    else:
                        print("Nadie cerca de la boca.")
            else:
                # Ya está reproduciendo un secreto: se deja terminar entero,
                # sin importar que usuarix se aleje (a diferencia de la
                # grabación, acá no hay corte por distancia). Solo se chequea
                # si el proceso de aplay ya terminó solo.
                if proceso_reproduccion.poll() is not None:
                    hora_fin_reproduccion = datetime.now()
                    duracion_reproduccion = (hora_fin_reproduccion - hora_inicio_reproduccion).total_seconds()
                    print(f"FIN REPRODUCCIÓN - {hora_fin_reproduccion.strftime('%H:%M:%S')}")
                    print(f"Cantidad de segundos reproducidos: {duracion_reproduccion:.1f}")
                    reproduciendo = False
                    proceso_reproduccion = None
                    hora_inicio_reproduccion = None

        sleep(INTERVALO_LECTURA)
except KeyboardInterrupt:
    print("Programa detenido.")
finally:
    if proceso_grabacion is not None:
        detener_proceso_audio(proceso_grabacion)
    if proceso_reproduccion is not None:
        detener_proceso_audio(proceso_reproduccion)
    sensor_oreja.close()
    sensor_boca.close()
