"""
=============================================================
 MANO ROBOTICA - SIN MODELO (MediaPipe pura matematica)
=============================================================
 Lee el video de la ESP32-CAM, detecta los 5 dedos con
 MediaPipe y manda el estado a los servos por UDP.
 No necesita ningun modelo TFLite.
=============================================================
"""

import cv2
import time
import math
import sys
import os
import socket
import threading
import queue
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

# ─────────────────────────────────────────────────────────
#  CONFIGURACION
# ─────────────────────────────────────────────────────────
ESP32_IP  = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
UDP_PORT  = 82

# ─────────────────────────────────────────────────────────
#  ENVIO UDP (hilo de fondo, sin bloquear el bucle)
# ─────────────────────────────────────────────────────────
cola_udp = queue.Queue(maxsize=1)
sock     = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def hilo_udp():
    while True:
        try:
            msg = cola_udp.get()
            sock.sendto(msg.encode(), (ESP32_IP, UDP_PORT))
        except Exception:
            pass
        finally:
            cola_udp.task_done()

threading.Thread(target=hilo_udp, daemon=True).start()

def enviar(estado):
    if cola_udp.full():
        try:
            cola_udp.get_nowait()
            cola_udp.task_done()
        except queue.Empty:
            pass
    cola_udp.put(estado)

# ─────────────────────────────────────────────────────────
#  MEDIAPIPE
# ─────────────────────────────────────────────────────────
MODELO_MP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
if not os.path.exists(MODELO_MP):
    print(f"[ERROR] No se encontró '{MODELO_MP}'")
    sys.exit(1)

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
print("[OK] MediaPipe listo.")

# ─────────────────────────────────────────────────────────
#  DIBUJO DE LA MANO
# ─────────────────────────────────────────────────────────
CONEXIONES = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (9,10),(10,11),(11,12),
    (13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),(5,0)
]

def dibujar_mano(frame, landmarks, w, h):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in CONEXIONES:
        cv2.line(frame, pts[a], pts[b], (80, 220, 120), 2)
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  DETECCION DE DEDOS (matematica pura)
# ─────────────────────────────────────────────────────────
def dist(p1, p2):
    return math.sqrt((p1.x-p2.x)**2 + (p1.y-p2.y)**2 + (p1.z-p2.z)**2)

prev_fingers = [1, 1, 1, 1, 1]

def detectar_dedos(lm):
    global prev_fingers
    fingers = []
    wrist = lm[0]

    # Pulgar (compara distancia punta vs base meñique)
    td = dist(lm[4], lm[17])
    tb = dist(lm[2], lm[17])
    if prev_fingers[0] == 1:
        new = 0 if td < tb * 0.85 else 1
    else:
        new = 1 if td > tb * 0.95 else 0
    fingers.append(new)

    # Índice, Medio, Anular, Meñique
    for i in range(1, 5):
        diff = dist(lm[TIP_IDS[i]], wrist) - dist(lm[TIP_IDS[i]-2], wrist)
        if prev_fingers[i] == 1:
            new = 0 if diff < -0.015 else 1
        else:
            new = 1 if diff > 0.035 else 0
        fingers.append(new)

    prev_fingers = fingers.copy()
    return fingers

# ─────────────────────────────────────────────────────────
#  CAMARA
# ─────────────────────────────────────────────────────────
print(f"[INFO] Conectando a {URL_VIDEO} ...")
cap = cv2.VideoCapture(URL_VIDEO)

if not cap.isOpened():
    print("[ERROR] No se pudo abrir el stream.")
    print("        Conéctate al WiFi 'CamaraESP32' primero.")
    sys.exit(1)

cv2.namedWindow("Mano Robotica", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Mano Robotica", 680, 520)

# ─────────────────────────────────────────────────────────
#  BUCLE PRINCIPAL
# ─────────────────────────────────────────────────────────
timestamp_ms   = 0
ultimo_enviado = ""
last_send      = 0
INTERVALO      = 0.05   # 50 ms entre envíos
pausado        = False
ultimo_detectado_t = time.time()

print("\n=== LISTO ===")
print("SPACE → pausar/reanudar")
print("Q     → salir\n")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]
    timestamp_ms += 33

    estado = "1,1,1,1,1"   # por defecto: mano abierta

    if not pausado:
        rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detector.detect_async(mp_image, timestamp_ms)

        if ultimo_resultado and ultimo_resultado.hand_landmarks:
            ultimo_detectado_t = time.time()
            for lm in ultimo_resultado.hand_landmarks:
                dibujar_mano(frame, lm, w, h)
                fingers = detectar_dedos(lm)
                estado  = ",".join(map(str, fingers))

                # Colores por dedo
                abiertos = sum(fingers)
                color = (0, 255, 120) if abiertos >= 4 else \
                        (0, 165, 255) if abiertos >= 2 else \
                        (0, 60, 255)
                cv2.putText(frame, f"Dedos: {estado}", (10, 38),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        else:
            sin_mano = time.time() - ultimo_detectado_t
            if sin_mano > 0.4:
                estado = "1,1,1,1,1"
                cv2.putText(frame, "Sin mano -> abierta", (10, 38),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 200, 255), 2)
            else:
                estado = ",".join(map(str, prev_fingers))
                cv2.putText(frame, "Buscando mano...", (10, 38),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 200, 200), 2)
    else:
        estado = "1,1,1,1,1"
        cv2.putText(frame, "PAUSADO  (SPACE = reanudar)", (10, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (50, 50, 255), 2)

    # Enviar si cambió
    now = time.time()
    if estado != ultimo_enviado and (now - last_send) > INTERVALO:
        enviar(estado)
        ultimo_enviado = estado
        last_send = now

    cv2.imshow("Mano Robotica", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):
        pausado = not pausado
        print(f"[INFO] {'PAUSADO' if pausado else 'REANUDADO'}")

# ─────────────────────────────────────────────────────────
#  CERRAR
# ─────────────────────────────────────────────────────────
print("\n[INFO] Cerrando... enviando mano abierta.")
try:
    sock.sendto("1,1,1,1,1".encode(), (ESP32_IP, UDP_PORT))
except Exception:
    pass
time.sleep(0.3)
cap.release()
detector.close()
sock.close()
cv2.destroyAllWindows()
print("[OK] Listo.")
