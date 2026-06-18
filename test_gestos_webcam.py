"""
=============================================================
 TEST DE GESTOS - Webcam local, sin WiFi, sin servos
 Solo muestra en pantalla qué gesto detecta MediaPipe
=============================================================
"""

import cv2
import math
import sys
import os
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

# ─────────────────────────────────────────────────────────
#  MEDIAPIPE
# ─────────────────────────────────────────────────────────
MODELO_MP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
if not os.path.exists(MODELO_MP):
    print(f"[ERROR] No se encontró '{MODELO_MP}'")
    sys.exit(1)

TIP_IDS = [4, 8, 12, 16, 20]
NOMBRES = ["Pulgar", "Indice", "Medio", "Anular", "Menique"]

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
#  DETECCION DE DEDOS
# ─────────────────────────────────────────────────────────
CONEXIONES = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (9,10),(10,11),(11,12),
    (13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),(5,0)
]

def dist(p1, p2):
    return math.sqrt((p1.x-p2.x)**2 + (p1.y-p2.y)**2 + (p1.z-p2.z)**2)

prev = [1, 1, 1, 1, 1]

def detectar_dedos(lm):
    global prev
    dedos = []
    # Pulgar
    td = dist(lm[4], lm[17])
    tb = dist(lm[2], lm[17])
    prev[0] = 0 if td < tb * 0.85 else 1 if td > tb * 0.95 else prev[0]
    dedos.append(prev[0])
    # Otros 4
    for i in range(1, 5):
        diff = dist(lm[TIP_IDS[i]], lm[0]) - dist(lm[TIP_IDS[i]-2], lm[0])
        if prev[i] == 1:
            prev[i] = 0 if diff < -0.015 else 1
        else:
            prev[i] = 1 if diff > 0.035 else 0
        dedos.append(prev[i])
    return dedos

def dibujar_mano(frame, landmarks, w, h):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in CONEXIONES:
        cv2.line(frame, pts[a], pts[b], (80, 220, 120), 2)
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  CAMARA LOCAL
# ─────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] No se pudo abrir la webcam.")
    sys.exit(1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

cv2.namedWindow("Test Gestos", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Test Gestos", 1280, 720)

timestamp_ms = 0
print("\n[OK] Listo. Presiona Q para salir.\n")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]
    timestamp_ms += 33

    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detector.detect_async(mp_image, timestamp_ms)

    # Fondo HUD
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 100), (15, 15, 30), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    if ultimo_resultado and ultimo_resultado.hand_landmarks:
        for lm in ultimo_resultado.hand_landmarks:
            dibujar_mano(frame, lm, w, h)
            dedos  = detectar_dedos(lm)
            abiertos = sum(dedos)

            # Gesto principal
            if abiertos == 5:
                gesto = "OPEN"
                color_g = (0, 255, 120)
            elif abiertos == 0:
                gesto = "CLOSE"
                color_g = (0, 80, 255)
            else:
                gesto = f"{abiertos}/5 dedos"
                color_g = (0, 200, 255)

            cv2.putText(frame, gesto, (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, color_g, 3)

            # Indicador por dedo
            for i, (nombre, val) in enumerate(zip(NOMBRES, dedos)):
                color = (0, 220, 100) if val else (60, 60, 220)
                icono = "▲" if val else "▼"
                cv2.putText(frame, f"{icono} {nombre}", (10 + i * 240, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

            # Estado binario en esquina
            estado = ",".join(map(str, dedos))
            cv2.putText(frame, estado, (w - 200, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2)

            print(f"\r  Gesto: {gesto:<12}  Estado: {estado}", end="", flush=True)
    else:
        cv2.putText(frame, "Sin mano detectada", (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 255), 2)

    cv2.imshow("Test Gestos", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
detector.close()
cv2.destroyAllWindows()
print("\n[OK] Listo.")
