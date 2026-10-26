import random
import subprocess
import wave
from pathlib import Path

from gpiozero import DistanceSensor
from datetime import datetime
from time import sleep

sensor_oreja = DistanceSensor(echo=24, trigger=23)
sensor_boca = DistanceSensor(echo=27, trigger=17)

INTERVALO_LECTURA = 0.5        # segundos entre cada lectura de los sensores
RANGO_ACERCAMIENTO_CM = 20     # distancia para avisar que alguien se acerca
RANGO_GRABACION_CM = 10        # distancia para considerar "cerca" (se usa para grabar y para reproducir)
CONFIRMACION_SEGUNDOS = 5      # segundos que hay que permanecer cerca de la oreja antes de arrancar a grabar
CONFIRMACION_SEGUNDOS_BOCA = 2 # segundos que hay que permanecer cerca de la boca antes de que empiece a hablar
ESPERA_PARA_CORTAR = 7        # segundos fuera del rango de grabación antes de cortar
MARGEN_FINAL_SEGUNDOS = 2      # segundos que se conservan después de que usuarix se aleja, al recortar el silencio del final
ESPERA_REHABILITAR_BOCA = 7    # segundos seguidos sin nadie cerca de la boca para que vuelva a reproducir después de haber reproducido un secreto

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
boca_bloqueada = False      # True si terminó un secreto y usuarix sigue cerca: no se le cuenta un segundo seguido
bloqueo_lejos_desde = None  # desde cuándo no hay nadie cerca de la boca, mientras está bloqueada

# Estado de la cuenta regresiva de "permanencia sostenida" de cada sensor. Es la
# misma máquina de estados para los dos (oreja y boca), solo cambian los segundos
# de confirmación y qué pasa al cumplirse, así que cada uno tiene su propio
# diccionario en vez de duplicar las variables sueltas.
estado_confirmacion_oreja = {"desde": None, "ultimo_restantes": None}
estado_confirmacion_boca = {"desde": None, "ultimo_restantes": None}

# Última zona informada por consola de cada sensor ("lejos", "acercamiento" o
# "cerca"), para imprimir solo cuando cambia y no en cada vuelta del loop.
ultima_zona_informada = {"oreja": None, "boca": None}


def reiniciar_confirmacion(estado):
    estado["desde"] = None
    estado["ultimo_restantes"] = None


def informar_zona(sensor, zona):
    """
    Imprime la zona en la que está usuarix respecto de `sensor` ("oreja" o
    "boca") solo si cambió desde la última vez que se informó.
    """
    if ultima_zona_informada[sensor] == zona:
        return
    ultima_zona_informada[sensor] = zona
    if zona == "acercamiento":
        print(f"Alguien se acerca al sensor/{sensor}")
    elif zona == "lejos":
        print(f"Nadie cerca del sensor/{sensor}")


def informar_llegada_directa(sensor, en_rango, estado):
    """
    Si usuarix aparece directamente dentro del rango de `sensor`, sin haber
    pasado antes por la zona de acercamiento, la cuenta regresiva arrancaría
    sin ningún aviso previo: acá se avisa que alguien se acercó. Hay que
    llamarla antes de `hubo_permanencia_sostenida`, para que el aviso salga
    antes que el primer mensaje de la cuenta.
    """
    if en_rango and estado["desde"] is None and ultima_zona_informada[sensor] in (None, "lejos"):
        print(f"Alguien se acercó al sensor/{sensor}")


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


def recortar_silencio_final(ruta, segundos_utiles):
    """
    Corta el .wav en `segundos_utiles`, descartando lo que sigue (el tramo de
    espera en el que usuarix ya se había alejado). Devuelve la duración final.
    """
    try:
        with wave.open(str(ruta), "rb") as original:
            parametros = original.getparams()
            cuadros = min(int(segundos_utiles * original.getframerate()), original.getnframes())
            datos = original.readframes(cuadros)
            duracion = cuadros / original.getframerate()
        with wave.open(str(ruta), "wb") as recortado:
            recortado.setparams(parametros)
            recortado.writeframes(datos)
        return duracion
    except (wave.Error, EOFError, OSError) as error:
        print(f"No se pudo recortar el silencio del final: {error}")
        return None


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
                informar_llegada_directa("oreja", en_zona_grabacion, estado_confirmacion_oreja)
                completo = hubo_permanencia_sostenida(
                    en_rango=en_zona_grabacion,
                    segundos_confirmacion=CONFIRMACION_SEGUNDOS,
                    estado=estado_confirmacion_oreja,
                    texto_cuenta_regresiva=lambda s: f"La grabación va a empezar en {s} segundos",
                    texto_cancelado="Se canceló el inicio de grabación: usuarix se alejó del sensor/oreja",
                )
                if completo:
                    grabando = True
                    hora_inicio = datetime.now()
                    tiempo_fuera_desde = None
                    ultimo_restantes_impreso = None
                    ultima_zona_informada["oreja"] = "cerca"
                    reiniciar_confirmacion(estado_confirmacion_boca)
                    # Contar un secreto tiene prioridad sobre el bloqueo de la boca
                    boca_estaba_bloqueada = boca_bloqueada
                    boca_bloqueada = False
                    bloqueo_lejos_desde = None
                    ultima_zona_informada["boca"] = None
                    ruta_secreto = CARPETA_SECRETOS / f"secreto_{hora_inicio.strftime('%Y%m%d_%H%M%S')}.wav"
                    proceso_grabacion = subprocess.Popen([
                        "arecord", "-D", DISPOSITIVO_ENTRADA_AUDIO, "-f", "cd", "-t", "wav", str(ruta_secreto)
                    ])
                    print(f"INICIO GRABACIÓN - {hora_inicio.strftime('%H:%M:%S')}")
                    print(f"Guardando en {ruta_secreto}")
                    if boca_estaba_bloqueada:
                        print(f"El sensor/boca ya puede reproducir secretos de nuevo - {hora_inicio.strftime('%H:%M:%S')}")
                elif en_zona_grabacion:
                    ultima_zona_informada["oreja"] = "cerca"
                else:
                    informar_zona("oreja", "acercamiento" if en_zona_acercamiento else "lejos")
            else:
                ahora = datetime.now()
                if en_zona_grabacion:
                    if tiempo_fuera_desde is not None:
                        print(f"Usuarix cerca del sensor/oreja nuevamente. La grabación continúa desde las {ahora.strftime('%H:%M:%S')}")
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
                            segundos_utiles = (tiempo_fuera_desde - hora_inicio).total_seconds() + MARGEN_FINAL_SEGUNDOS
                            detener_proceso_audio(proceso_grabacion)
                            proceso_grabacion = None
                            duracion = recortar_silencio_final(ruta_secreto, segundos_utiles)
                            if duracion is None:
                                duracion = (hora_fin - hora_inicio).total_seconds()
                            print("Fin de grabación, usuarix se alejó del sensor/oreja")
                            print(f"FIN GRABACIÓN - {hora_fin.strftime('%H:%M:%S')}")
                            print(f"Cantidad de segundos grabados (sin el silencio final): {duracion:.1f}")
                            grabando = False
                            hora_inicio = None
                            tiempo_fuera_desde = None
                            ultimo_restantes_impreso = None
                            ultima_zona_informada["oreja"] = None
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

            if boca_bloqueada:
                # Terminó un secreto y usuarix sigue cerca: no se reproduce otro
                # hasta que haya `ESPERA_REHABILITAR_BOCA` segundos seguidos sin
                # nadie cerca de la boca. Cualquier lectura cerca reinicia la espera.
                if distancia_boca_cm > RANGO_ACERCAMIENTO_CM:
                    ahora = datetime.now()
                    if bloqueo_lejos_desde is None:
                        bloqueo_lejos_desde = ahora
                    elif (ahora - bloqueo_lejos_desde).total_seconds() >= ESPERA_REHABILITAR_BOCA:
                        boca_bloqueada = False
                        bloqueo_lejos_desde = None
                        ultima_zona_informada["boca"] = "lejos"
                        print(f"A la espera de nuevx usuarix - {ahora.strftime('%H:%M:%S')}")
                else:
                    bloqueo_lejos_desde = None
            elif not reproduciendo:
                informar_llegada_directa("boca", en_zona_cerca_boca, estado_confirmacion_boca)
                completo_boca = hubo_permanencia_sostenida(
                    en_rango=en_zona_cerca_boca,
                    segundos_confirmacion=CONFIRMACION_SEGUNDOS_BOCA,
                    estado=estado_confirmacion_boca,
                    texto_cuenta_regresiva=lambda s: f"El sensor/boca va a hablar en {s} segundos",
                    texto_cancelado="Se canceló: usuarix se alejó antes de que el sensor/boca empezara a hablar",
                )
                if completo_boca:
                    secreto_elegido = elegir_secreto_al_azar()
                    if secreto_elegido is None:
                        print("Error. Todavía no hay secretos guardados, no hay nada para reproducir")
                    else:
                        reproduciendo = True
                        hora_inicio_reproduccion = datetime.now()
                        ultimo_reproducido = secreto_elegido
                        ultima_zona_informada["boca"] = "cerca"
                        reiniciar_confirmacion(estado_confirmacion_oreja)
                        proceso_reproduccion = subprocess.Popen([
                            "aplay", "-D", DISPOSITIVO_SALIDA_AUDIO, str(secreto_elegido)
                        ])
                        print(f"EL SENSOR/BOCA EMPIEZA A HABLAR - {hora_inicio_reproduccion.strftime('%H:%M:%S')}")
                        print(f"Reproduciendo {secreto_elegido.name}")
                elif en_zona_cerca_boca:
                    ultima_zona_informada["boca"] = "cerca"
                else:
                    informar_zona("boca", "acercamiento" if en_zona_acercamiento_boca else "lejos")
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
                    ultima_zona_informada["boca"] = None
                    proceso_reproduccion = None
                    hora_inicio_reproduccion = None
                    if distancia_boca_cm <= RANGO_ACERCAMIENTO_CM:
                        boca_bloqueada = True
                        bloqueo_lejos_desde = None
                        print(f"FIN DE REPRODUCCIÓN. Alguien sigue cerca del sensor/boca, pero no se cuentan dos secretos seguidos a mismx usuarix - {hora_fin_reproduccion.strftime('%H:%M:%S')}")

        sleep(INTERVALO_LECTURA)
except KeyboardInterrupt:
    print("Programa detenido")
finally:
    if proceso_grabacion is not None:
        detener_proceso_audio(proceso_grabacion)
    if proceso_reproduccion is not None:
        detener_proceso_audio(proceso_reproduccion)
    sensor_oreja.close()
    sensor_boca.close()
