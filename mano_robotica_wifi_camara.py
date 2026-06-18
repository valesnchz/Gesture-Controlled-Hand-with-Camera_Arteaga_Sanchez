"""
=============================================================
 PROYECTO MANO ROBOTICA - TELEOPERACION INALAMBRICA (WIFI)
=============================================================
 Compatible con Python 3.13 + mediapipe >= 0.10.14
 
 ESTE SCRIPT CORRE EN TU COMPUTADORA:
 1. Lee el video en vivo de la ESP32-CAM por WiFi.
 2. Procesa la IA (MediaPipe) en la PC con pura matematica (sin TFLite).
 3. Manda las ordenes a los servos por WiFi de forma ultra-rapida sin lag.
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
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

# ─────────────────────────────────────────────────────────
#  1. CONFIGURACION WIFI (ESP32-CAM)
# ─────────────────────────────────────────────────────────
ESP32_IP = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
URL_COMANDO = f"http://{ESP32_IP}:82/dedos?estado="

# Cola de comandos de tamaño 1 para enviar siempre el estado más reciente y evitar retrasos
cola_comandos = queue.Queue(maxsize=1)

def hilo_transmisor():
    """Hilo de fondo persistente para enviar peticiones HTTP sin acumular lag."""
    while True:
        try:
            estado = cola_comandos.get()
            url = URL_COMANDO + estado
            # Enviamos la petición con un timeout corto
            with urllib.request.urlopen(url, timeout=0.15) as response:
                response.read()  # Cerramos la conexión rápido
        except Exception:
            pass
        finally:
            cola_comandos.task_done()

# Iniciar el hilo transmisor de fondo de inmediato
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
#  2. CONFIGURACION DEL MODELO DE MEDIAPIPE
# ─────────────────────────────────────────────────────────
MODELO_MP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

if not os.path.exists(MODELO_MP):
    print("\n[INFO] Descargando modelo 'hand_landmarker.task' de MediaPipe...")
    url_descarga = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    try:
        urllib.request.urlretrieve(url_descarga, MODELO_MP)
        print("[OK] Modelo descargado exitosamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo descargar el modelo: {e}")
        sys.exit(1)

# Variables globales para el callback de MediaPipe
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
print("[OK] MediaPipe Inicializado.")

# ─────────────────────────────────────────────────────────
#  3. DIBUJO Y ESTRUCTURA DE LA MANO
# ─────────────────────────────────────────────────────────
TIP_IDS = [4, 8, 12, 16, 20] # Puntas de los dedos (Pulgar, Indice, Medio, Anular, Menique)

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4), (0,5),(5,6),(6,7),(7,8),
    (9,10),(10,11),(11,12), (13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),(5,0)
]

def dist(p1, p2):
    """Calcula la distancia Euclidiana entre dos puntos."""
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

def dibujar_esqueleto(frame, landmarks, w, h):
    """Dibuja el esqueleto de la mano en pantalla."""
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    # Dibujar lineas
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 250, 120), 2)
    # Dibujar puntos
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  4. CONEXION A LA CAMARA WIFI DE LA ESP32-CAM
# ─────────────────────────────────────────────────────────
print(f"[INFO] Conectando al video stream en {URL_VIDEO}...")
cap = cv2.VideoCapture(URL_VIDEO)

if not cap.isOpened():
    print("[ERROR] No se pudo abrir la transmision de video de la ESP32-CAM.")
    print("        Asegurate de estar conectado a la red WiFi 'CamaraESP32'.")
    sys.exit(1)

cv2.namedWindow("Mano Robotica - ESP32-CAM", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Mano Robotica - ESP32-CAM", 640, 480)

# ── HISTERESIS PARA DEDOS MAS ESTABLES (EVITA TEMBLORES) ───
previous_fingers_state = [1, 1, 1, 1, 1]

# ─────────────────────────────────────────────────────────
#  5. BUCLE PRINCIPAL DE PROCESAMIENTO
# ─────────────────────────────────────────────────────────
ultimo_estado_enviado = ""
last_send_time = 0
send_interval = 0.05  # 50 ms entre envios (ahora mucho más rápido gracias al hilo de fondo)
timestamp_ms = 0
seguimiento_activo = True
last_hand_detected_time = time.time()  # Reloj para saber cuándo se fue la mano

print("\n=== ¡SISTEMA LISTO! ===")
print("Presiona ESPACIO para pausar/reanudar.")
print("Presiona 'q' para salir.")

while True:
    success, frame = cap.read()
    if not success:
        continue

    # Espejo e informacion del frame
    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]
    timestamp_ms += 33 # Aproximadamente 30 FPS

    state = "1,1,1,1,1" # Estado por defecto

    if seguimiento_activo:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detector.detect_async(mp_image, timestamp_ms)

        if ultimo_resultado and ultimo_resultado.hand_landmarks and len(ultimo_resultado.hand_landmarks) > 0:
            last_hand_detected_time = time.time()  # Actualizamos la última vez que vimos la mano
            
            for lm in ultimo_resultado.hand_landmarks:
                dibujar_esqueleto(frame, lm, w, h)
                
                # --- PURE MATH: CALCULO DE DEDOS ABIERTOS/CERRADOS ---
                fingers = []
                wrist = lm[0]

                # ── 1. Dedo Pulgar (Inclinacion lateral vs base meñique) ──
                thumb_dist = dist(lm[4], lm[17])
                thumb_base_dist = dist(lm[2], lm[17])
                if previous_fingers_state[0] == 1:
                    new_thumb = 0 if thumb_dist < (thumb_base_dist * 0.85) else 1
                else:
                    new_thumb = 1 if thumb_dist > (thumb_base_dist * 0.95) else 0
                fingers.append(new_thumb)

                # ── 2. Los otros 4 dedos (Indice, Medio, Anular, Menique) ──
                for i in range(1, 5):
                    # Distancia de la punta a la muñeca comparada con el nudillo a la muñeca
                    finger_diff = dist(lm[TIP_IDS[i]], wrist) - dist(lm[TIP_IDS[i]-2], wrist)
                    
                    if previous_fingers_state[i] == 1:
                        new_finger = 0 if finger_diff < -0.015 else 1
                    else:
                        new_finger = 1 if finger_diff > 0.035 else 0
                    fingers.append(new_finger)

                # Guardar el estado
                previous_fingers_state = fingers.copy()
                state = ",".join(map(str, fingers))

                # Mostrar informacion en pantalla
                cv2.putText(frame, f"Comando: {state}", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 180), 2, cv2.LINE_AA)
        else:
            # SI NO HAY MANO DETECTADA:
            # Esperamos un pequeño colchón de 0.3 segundos para no abrir bruscamente por parpadeos
            tiempo_sin_mano = time.time() - last_hand_detected_time
            if tiempo_sin_mano > 0.3:
                state = "1,1,1,1,1" # Regresa a palma extendida (todos abiertos) al salir de la cámara
                cv2.putText(frame, "Mano Ausente -> Palma Abierta", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 165, 255), 2, cv2.LINE_AA)
            else:
                # Mantener temporalmente el último estado para evitar saltos bruscos
                state = ",".join(map(str, previous_fingers_state))
                cv2.putText(frame, "Buscando mano...", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
    else:
        # SISTEMA PAUSADO:
        state = "1,1,1,1,1"  # Cuando está pausado, abre la mano para seguridad
        cv2.putText(frame, "SISTEMA PAUSADO (Mano Abierta)", (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 255), 2, cv2.LINE_AA)

    # --- TRANSMISION WIFI OPTIMIZADA ---
    current_time = time.time()
    if state != ultimo_estado_enviado and (current_time - last_send_time) > send_interval:
        enviar_orden_wifi(state)
        ultimo_estado_enviado = state
        last_send_time = current_time

    # Mostrar la interfaz visual
    cv2.imshow("Mano Robotica - ESP32-CAM", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):
        seguimiento_activo = not seguimiento_activo
        print(f"[INFO] Seguimiento: {'ACTIVADO' if seguimiento_activo else 'PAUSADO'}")

# ─────────────────────────────────────────────────────────
#  6. CERRAR TODO
# ─────────────────────────────────────────────────────────
print("\n[INFO] Enviando comando final de abrir mano antes de salir...")
enviar_orden_wifi("1,1,1,1,1")
time.sleep(0.5)

cap.release()
detector.close()
cv2.destroyAllWindows()
print("[OK] Programa cerrado correctamente.")
