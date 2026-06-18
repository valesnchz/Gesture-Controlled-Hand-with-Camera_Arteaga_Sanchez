"""
=============================================================
 PROYECTO MANO ROBOTICA - TELEOPERACION WIFI
=============================================================
 Compatible con Python 3.13 + mediapipe >= 0.10.14
 
 ESTE SCRIPT ES LA VERSION INALAMBRICA (SIN CABLES USB).
 1. Lee el video directamente desde la ESP32-CAM por WiFi.
 2. Procesa la IA (MediaPipe) en tu computadora.
 3. Manda las ordenes a los motores por WiFi.
=============================================================
"""

import cv2
import time
import math
import sys
import os
import urllib.request
import threading
import queue
import socket
import mediapipe as mp
from mediapipe.tasks.python        import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

# ─────────────────────────────────────────────────────────
#  1. CONFIGURACION WIFI
# ─────────────────────────────────────────────────────────

ESP32_IP = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
UDP_PORT = 82

# Socket UDP
sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cola_comandos = queue.Queue(maxsize=1)

def hilo_transmisor():
    """Hilo de fondo para transmitir comandos UDP de forma ultra rápida."""
    while True:
        try:
            estado = cola_comandos.get()
            sock_udp.sendto(estado.encode('utf-8'), (ESP32_IP, UDP_PORT))
        except Exception:
            pass
        finally:
            cola_comandos.task_done()

# Iniciar hilo transmisor
threading.Thread(target=hilo_transmisor, daemon=True).start()

def enviar_orden_wifi(estado):
    """Inserta el nuevo estado en la cola, reemplazando el anterior si estaba lleno."""
    if cola_comandos.full():
        try:
            cola_comandos.get_nowait()
            cola_comandos.task_done()
        except queue.Empty:
            pass
    cola_comandos.put(estado)

# ─────────────────────────────────────────────────────────
#  2. MODELOS (MEDIAPIPE + EDGE IMPULSE AI)
# ─────────────────────────────────────────────────────────

# Modelo 1: MediaPipe (Para detectar los puntos x,y,z)
MODELO_MP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

# Modelo 2: Edge Impulse (Para clasificar el gesto)
# ¡ASEGURATE DE QUE EL NOMBRE COINCIDA CON TU ARCHIVO .TFLITE!
MODELO_AI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelo_mano.tflite")

if not os.path.exists(MODELO_MP):
    print(f"\n[ERROR] Falta '{MODELO_MP}'")
    sys.exit(1)

try:
    from tflite_runtime.interpreter import Interpreter
    interpreter = Interpreter(model_path=MODELO_AI)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    print("[OK] IA de Edge Impulse cargada correctamente.")
except Exception as e:
    print(f"\n[ERROR] No se pudo cargar la IA: {e}")
    print("        Asegúrate de instalar: pip install tflite-runtime")
    sys.exit(1)

# Mapeo de clases (Edge Impulse las ordena alfabéticamente)
# 0: close, 1: index, 2: open
CLASES = ["close", "index", "open"]

TIP_IDS = [4, 8, 12, 16, 20]
ultimo_resultado = None

def on_result(result, output_image, timestamp_ms):
    global ultimo_resultado
    ultimo_resultado = result

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODELO_MP),
    running_mode=RunningMode.LIVE_STREAM,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    result_callback=on_result
)

detector = HandLandmarker.create_from_options(options)
print("[OK] Detector de MediaPipe listo.")

# ─────────────────────────────────────────────────────────
#  3. FUNCIONES DE APOYO
# ─────────────────────────────────────────────────────────

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4), (0,5),(5,6),(6,7),(7,8),
    (9,10),(10,11),(11,12), (13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),(5,0)
]

def normalize_landmarks(landmarks):
    """Normaliza los puntos igual que como entrenamos la IA."""
    coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks])
    wrist = coords[0].copy()
    coords_centered = coords - wrist
    dist_0_9 = np.linalg.norm(coords_centered[9])
    if dist_0_9 > 1e-6:
        coords_norm = coords_centered / dist_0_9
    else:
        coords_norm = coords_centered
    return coords_norm.flatten().astype(np.float32)

def dibujar_mano(frame, landmarks, w, h):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 200, 120), 2)
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

import numpy as np

# ─────────────────────────────────────────────────────────
#  4. CAMARA WIFI
# ─────────────────────────────────────────────────────────

cap = cv2.VideoCapture(URL_VIDEO)
if not cap.isOpened():
    print("[ERROR] No se pudo abrir el video WiFi.")
    sys.exit(1)

cv2.namedWindow("IA Mano Robotica", cv2.WINDOW_NORMAL)
cv2.resizeWindow("IA Mano Robotica", 640, 480)

# ─────────────────────────────────────────────────────────
#  5. BUCLE PRINCIPAL
# ─────────────────────────────────────────────────────────

ultimo_estado = ""
timestamp_ms  = 0
seguimiento_activo = True
ultimo_envio = 0
intervalo_envio = 0.1  # 100 ms para estabilidad

while True:
    success, frame = cap.read()
    if not success: continue

    frame = cv2.resize(frame, (320, 240))
    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]
    timestamp_ms += 33   

    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detector.detect_async(mp_image, timestamp_ms)

    if ultimo_resultado and ultimo_resultado.hand_landmarks:
        for hand_landmarks in ultimo_resultado.hand_landmarks:
            dibujar_mano(frame, hand_landmarks, w, h)

            # --- INFERENCIA CON IA ---
            # 1. Normalizar puntos
            input_data = normalize_landmarks(hand_landmarks)
            input_data = np.expand_dims(input_data, axis=0)

            # 2. Correr el modelo
            interpreter.set_tensor(input_details[0]['index'], input_data)
            interpreter.invoke()
            output_data = interpreter.get_tensor(output_details[0]['index'])
            
            # 3. Obtener el resultado
            idx_clase = np.argmax(output_data)
            gesto_detectado = CLASES[idx_clase]
            confianza = output_data[0][idx_clase]

            # 4. Mapear gesto a comando del robot
            # open  -> 1,1,1,1,1
            # close -> 0,0,0,0,0
            # index -> 1,0,1,1,1 (ejemplo: solo el indice levantado)
            if gesto_detectado == "open":
                estado = "1,1,1,1,1"
            elif gesto_detectado == "close":
                estado = "0,0,0,0,0"
            elif gesto_detectado == "index":
                estado = "1,0,1,1,1" # Ajusta segun como quieras mover los servos
            else:
                estado = "1,1,1,1,1"

            # Enviar comando si cambió y paso el tiempo
            tiempo_actual = time.time()
            if estado != ultimo_estado and (tiempo_actual - ultimo_envio) > 0.05:
                enviar_orden_wifi(estado)
                ultimo_estado = estado
                ultimo_envio = tiempo_actual

            # Mostrar info en pantalla
            cv2.putText(frame, f"IA: {gesto_detectado} ({confianza:.2f})", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow("IA Mano Robotica", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
detector.close()
cv2.destroyAllWindows()
print("[OK] Programa finalizado.")
