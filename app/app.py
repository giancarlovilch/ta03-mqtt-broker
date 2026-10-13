import os
import json
import time
import wave

os.environ["FLET_SECRET_KEY"] = "ta03-domotica-dev-key"

import flet as ft
import flet_audio_recorder as far
import flet_charts as fc
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

MQTT_SERVER = os.environ.get("MQTT_SERVER", "192.168.18.105")
MQTT_PORT = 1883
MQTT_USER = "esp32"
MQTT_PASS = "a12345A"
TOPIC_LUZ = "casa/sala/luz"
TOPIC_SEMAFORO = "oficina/semaforo"
TOPIC_DEMANDA = "oficina/demanda"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_SERVER, MQTT_PORT, keepalive=60)
client.loop_start()

DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
HISTORIAL_PATH = os.path.join(DATA_DIR, "historial.json")
NIVEL_DEMANDA = {"sin demanda": 0, "baja": 1, "media": 2, "alta": 3}


def cargar_historial():
    if os.path.exists(HISTORIAL_PATH):
        with open(HISTORIAL_PATH, "r") as f:
            return json.load(f)
    return []


def podar_historial(lista):
    limite = time.time() - 24 * 3600
    lista[:] = [h for h in lista if h["ts"] >= limite]


historial = cargar_historial()
podar_historial(historial)

ATENDIDOS_PATH = os.path.join(DATA_DIR, "atendidos.json")


def cargar_atendidos():
    if os.path.exists(ATENDIDOS_PATH):
        with open(ATENDIDOS_PATH, "r") as f:
            return json.load(f)
    return []


def podar_atendidos(lista):
    limite = time.time() - 24 * 3600
    lista[:] = [h for h in lista if h["ts"] >= limite]


atendidos = cargar_atendidos()
podar_atendidos(atendidos)


def registrar_atendido():
    atendidos.append({"ts": time.time()})
    podar_atendidos(atendidos)
    with open(ATENDIDOS_PATH, "w") as f:
        json.dump(atendidos, f)


def pcm_a_wav(pcm_path, wav_path, sample_rate=44100, channels=2, sample_width=2):
    with open(pcm_path, "rb") as f:
        pcm_data = f.read()
    with wave.open(wav_path, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)


def transcribir(wav_path):
    with open(wav_path, "rb") as f:
        resultado = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=f,
            language="es",
            response_format="text",
        )
    return resultado


HERRAMIENTAS = [
    {
        "type": "function",
        "function": {
            "name": "controlar_luz",
            "description": "Prende o apaga la luz de la sala",
            "parameters": {
                "type": "object",
                "properties": {
                    "estado": {
                        "type": "string",
                        "enum": ["ON", "OFF"],
                        "description": "ON para prender la luz, OFF para apagarla",
                    }
                },
                "required": ["estado"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "controlar_semaforo",
            "description": "Cambia el semaforo RGB de la oficina de admision, visible para los estudiantes afuera",
            "parameters": {
                "type": "object",
                "properties": {
                    "color": {
                        "type": "string",
                        "enum": ["ROJO", "VERDE"],
                        "description": "ROJO cuando la oficina esta ocupada/llena, VERDE cuando esta disponible o puede pasar el siguiente estudiante",
                    }
                },
                "required": ["color"],
            },
        },
    },
]


def decidir_accion(texto_usuario):
    respuesta = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": "Eres un asistente de domotica. Controlas dos cosas: "
                "1) una luz de sala (herramienta controlar_luz, ON/OFF). "
                "2) el semaforo de una oficina de admision universitaria (herramienta controlar_semaforo). "
                "Usa controlar_semaforo con color ROJO cuando el usuario diga que esta ocupado, lleno, "
                "que espere, o similar. Usa VERDE cuando diga que esta disponible, libre, que pase el "
                "siguiente estudiante, o similar. Si no pide nada relacionado, no uses ninguna herramienta.",
            },
            {"role": "user", "content": texto_usuario},
        ],
        tools=HERRAMIENTAS,
        tool_choice="auto",
    )

    mensaje = respuesta.choices[0].message
    if mensaje.tool_calls:
        for llamada in mensaje.tool_calls:
            argumentos = json.loads(llamada.function.arguments)
            if llamada.function.name == "controlar_luz":
                estado = argumentos["estado"]
                client.publish(TOPIC_LUZ, estado)
                return f"Luz: {estado}"
            elif llamada.function.name == "controlar_semaforo":
                color = argumentos["color"]
                client.publish(TOPIC_SEMAFORO, color)
                if color == "VERDE":
                    registrar_atendido()
                return f"Semaforo: {color}"
    return "No entendi ningun comando"


def main(page: ft.Page):
    page.title = "Control de Luz"

    estado = ft.Text("Presiona el microfono y habla")
    demanda_texto = ft.Text("Demanda: esperando datos...", size=18, weight=ft.FontWeight.BOLD)

    grafico = fc.LineChart(
        data_series=[fc.LineChartData(points=[], curved=True, color=ft.Colors.BLUE, stroke_width=3)],
        min_y=0,
        max_y=3,
        left_axis=fc.ChartAxis(label_size=30, title=ft.Text("Nivel (0-3)")),
        bottom_axis=fc.ChartAxis(label_size=30, title=ft.Text("Minutos atras")),
        height=250,
    )

    ventana_minutos = 60

    def redibujar_grafico():
        ahora = time.time()
        limite = ahora - ventana_minutos * 60
        puntos = [
            fc.LineChartDataPoint(x=(h["ts"] - ahora) / 60, y=h["nivel"])
            for h in historial
            if h["ts"] >= limite
        ]
        grafico.data_series = [
            fc.LineChartData(points=puntos, curved=True, color=ft.Colors.BLUE, stroke_width=3)
        ]
        grafico.min_x = -ventana_minutos
        grafico.max_x = 0
        page.update()

    def cambiar_ventana(minutos):
        nonlocal ventana_minutos
        ventana_minutos = minutos
        redibujar_grafico()
        redibujar_atendidos()

    botones_ventana = ft.Row(
        [
            ft.TextButton("Ultimos 60 min", on_click=lambda e: cambiar_ventana(60)),
            ft.TextButton("Ultimas 6 horas", on_click=lambda e: cambiar_ventana(360)),
            ft.TextButton("Ultimas 24 horas", on_click=lambda e: cambiar_ventana(1440)),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    NUM_BARRAS = 30

    def contar_por_ventana(eventos, minutos):
        ahora = time.time()
        ancho = minutos // NUM_BARRAS
        grupos = []
        for i in range(NUM_BARRAS):
            min_hasta = (NUM_BARRAS - 1 - i) * ancho
            min_desde = min_hasta + ancho
            desde = ahora - min_desde * 60
            hasta = ahora - min_hasta * 60
            cantidad = sum(1 for e in eventos if desde <= e["ts"] < hasta)
            grupos.append(
                fc.BarChartGroup(
                    x=-min_desde,
                    rods=[fc.BarChartRod(to_y=cantidad, color=ft.Colors.GREEN, width=5)],
                )
            )
        return grupos

    grafico_atendidos = fc.BarChart(
        groups=contar_por_ventana(atendidos, ventana_minutos),
        min_y=0,
        left_axis=fc.ChartAxis(label_size=30, title=ft.Text("Atendidos")),
        bottom_axis=fc.ChartAxis(label_size=30, title=ft.Text("Minutos atras")),
        height=200,
    )

    def redibujar_atendidos():
        grafico_atendidos.groups = contar_por_ventana(atendidos, ventana_minutos)
        grafico_atendidos.min_x = -ventana_minutos
        grafico_atendidos.max_x = 0
        page.update()

    async def actualizar_demanda(valor: str):
        demanda_texto.value = f"Demanda afuera: {valor}"
        redibujar_grafico()
        page.update()

    def al_recibir_mensaje(mqtt_client, userdata, message):
        if message.topic == TOPIC_DEMANDA:
            valor = message.payload.decode()
            nivel = NIVEL_DEMANDA.get(valor, 0)
            historial.append({"ts": time.time(), "nivel": nivel})
            podar_historial(historial)
            with open(HISTORIAL_PATH, "w") as f:
                json.dump(historial, f)
            try:
                page.run_task(actualizar_demanda, valor)
            except Exception as ex:
                print(f"No se pudo actualizar la pantalla (sesion probablemente cerrada): {ex}")

    client.on_message = al_recibir_mensaje
    resultado_sub = client.subscribe(TOPIC_DEMANDA)
    print(f"Suscripcion a {TOPIC_DEMANDA}: {resultado_sub}, client.is_connected()={client.is_connected()}")

    audio_rec = far.AudioRecorder()
    page.services.append(audio_rec)

    grabando = False
    boton_mic = ft.IconButton(icon=ft.Icons.MIC, icon_size=80)

    color_semaforo = "ROJO"
    boton_semaforo = ft.IconButton(icon=ft.Icons.CIRCLE, icon_color=ft.Colors.RED, icon_size=60)

    def alternar_semaforo(e):
        nonlocal color_semaforo
        color_semaforo = "VERDE" if color_semaforo == "ROJO" else "ROJO"
        client.publish(TOPIC_SEMAFORO, color_semaforo)
        boton_semaforo.icon_color = ft.Colors.GREEN if color_semaforo == "VERDE" else ft.Colors.RED
        if color_semaforo == "VERDE":
            registrar_atendido()
            redibujar_atendidos()
        page.update()

    boton_semaforo.on_click = alternar_semaforo

    async def alternar_grabacion(e):
        nonlocal grabando
        if not grabando:
            if await audio_rec.has_permission():
                upload_url = page.get_upload_url("grabacion.pcm", 60)
                await audio_rec.start_recording(
                    configuration=far.AudioRecorderConfiguration(encoder=far.AudioEncoder.PCM16BITS),
                    upload=far.AudioRecorderUploadSettings(upload_url=upload_url, file_name="grabacion.pcm"),
                )
                grabando = True
                boton_mic.icon = ft.Icons.STOP
                estado.value = "Grabando... toca de nuevo para terminar"
                page.update()
            else:
                estado.value = "No se otorgo permiso de microfono"
                page.update()
        else:
            await audio_rec.stop_recording()
            grabando = False
            boton_mic.icon = ft.Icons.MIC
            estado.value = "Subiendo grabacion..."
            page.update()

    boton_mic.on_click = alternar_grabacion

    async def procesar_grabacion():
        pcm_path = os.path.join(UPLOADS_DIR, "grabacion.pcm")
        wav_path = os.path.join(UPLOADS_DIR, "grabacion.wav")
        pcm_a_wav(pcm_path, wav_path)

        estado.value = "Transcribiendo..."
        page.update()

        texto = transcribir(wav_path)
        estado.value = f"Dijiste: {texto}\nProcesando..."
        page.update()

        resultado = decidir_accion(texto)
        estado.value = f"Dijiste: {texto}\n{resultado}"
        redibujar_atendidos()
        page.update()

    async def actualizar_estado(mensaje: str):
        estado.value = mensaje
        page.update()

    def archivo_subido(e: far.AudioRecorderUploadEvent):
        try:
            if e.error:
                page.run_task(actualizar_estado, f"Error al subir: {e.error}")
            elif e.progress is not None and e.progress >= 1:
                page.run_task(procesar_grabacion)
        except Exception as ex:
            print(f"No se pudo procesar la grabacion (sesion probablemente cerrada): {ex}")

    audio_rec.on_upload = archivo_subido

    page.add(
        estado,
        ft.Row([boton_mic, boton_semaforo], alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        demanda_texto,
        botones_ventana,
        grafico,
        ft.Divider(),
        ft.Text("Atendidos por hora", size=18, weight=ft.FontWeight.BOLD),
        grafico_atendidos,
    )

    redibujar_grafico()
    redibujar_atendidos()


ft.run(main, upload_dir=UPLOADS_DIR)
