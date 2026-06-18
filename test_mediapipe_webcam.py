"""
=============================================================
  TEST MEDIAPIPE - WEBCAM
=============================================================
  Prueba el detector de mano (21 puntos) con tu camara local.
  NO necesita ESP32 ni servos - solo tu webcam.

  Controles:
    ESPACIO  → Pausa / Reanuda el tracking
    Q        → Salir

  Lo que muestra en pantalla:
    - Esqueleto de la mano con los 21 puntos
    - Estado de cada dedo (abierto / cerrado)
    - Indice de cada punto clave (landmarks)
    - FPS en tiempo real
    - Confianza de deteccion
=============================================================
"""

# ── Silenciar mensajes de TensorFlow y telemetria de MediaPipe ──
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"]   = "3"   # oculta INFO, WARNING, ERROR de TF
os.environ["TF_ENABLE_ONEDNN_OPTS"]  = "0"   # desactiva oneDNN (evita ese WARNING)
os.environ["GLOG_minloglevel"]       = "3"   # oculta logs internos de MediaPipe
os.environ["MEDIAPIPE_DISABLE_GPU"]  = "1"   # fuerza CPU (mas estable en Windows)

import cv2
import time
import math
import sys
import os
import urllib.request
import mediapipe as mp
from mediapipe.tasks.python        import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

# ─────────────────────────────────────────────────────────
#  1. MODELO MEDIAPIPE  (se descarga solo la 1ra vez)
# ─────────────────────────────────────────────────────────
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

if not os.path.exists(MODEL):
    print("\n[INFO] Descargando modelo 'hand_landmarker.task'...")
    url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    try:
        urllib.request.urlretrieve(url, MODEL)
        print("[OK] Modelo descargado.\n")
    except Exception as e:
        print(f"[ERROR] No se pudo descargar: {e}")
        sys.exit(1)

# ─────────────────────────────────────────────────────────
#  2. CONFIGURACION DEL DETECTOR
# ─────────────────────────────────────────────────────────
TIP_IDS  = [4, 8, 12, 16, 20]   # Puntas de los 5 dedos
MCP_IDS  = [1, 5, 9, 13, 17]    # Nudillos base
NAMES    = ["Pulgar", "Indice", "Medio", "Anular", "Menique"]

last_result = None

def on_result(result, output_image, timestamp_ms):
    global last_result
    last_result = result

options = HandLandmarkerOptions(
    base_options              = BaseOptions(model_asset_path=MODEL),
    running_mode              = RunningMode.LIVE_STREAM,
    num_hands                 = 2,                   # detecta hasta 2 manos
    min_hand_detection_confidence = 0.5,
    min_hand_presence_confidence  = 0.5,
    min_tracking_confidence       = 0.5,
    result_callback           = on_result
)

detector = HandLandmarker.create_from_options(options)
print("[OK] MediaPipe listo.")

# ─────────────────────────────────────────────────────────
#  3. CONEXIONES DEL ESQUELETO
# ─────────────────────────────────────────────────────────
CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),           # pulgar
    (0,5),(5,6),(6,7),(7,8),           # indice
    (0,9),(9,10),(10,11),(11,12),      # medio
    (0,13),(13,14),(14,15),(15,16),    # anular
    (0,17),(17,18),(18,19),(19,20),    # menique
    (5,9),(9,13),(13,17),              # palma
]

# Colores por dedo (BGR)
FINGER_COLORS = [
    (255, 100,  50),   # pulgar  - naranja
    (255, 220,   0),   # indice  - amarillo
    ( 50, 220,  50),   # medio   - verde
    ( 50, 180, 255),   # anular  - azul claro
    (200,  80, 255),   # menique - violeta
]

SEGMENTS = [
    [(0,1),(1,2),(2,3),(3,4)],
    [(0,5),(5,6),(6,7),(7,8)],
    [(0,9),(9,10),(10,11),(11,12)],
    [(0,13),(13,14),(14,15),(15,16)],
    [(0,17),(17,18),(18,19),(19,20)],
]

# ─────────────────────────────────────────────────────────
#  4. FUNCIONES DE DIBUJO
# ─────────────────────────────────────────────────────────
def dist2d(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)

def draw_skeleton(frame, lm, w, h, show_indices=True):
    """Dibuja el esqueleto con colores por dedo."""
    pts = [(int(l.x * w), int(l.y * h)) for l in lm]

    # Lineas coloreadas por dedo
    for finger_idx, segments in enumerate(SEGMENTS):
        color = FINGER_COLORS[finger_idx]
        for a, b in segments:
            cv2.line(frame, pts[a], pts[b], color, 2, cv2.LINE_AA)

    # Palma (blanco)
    for a, b in [(5,9),(9,13),(13,17)]:
        cv2.line(frame, pts[a], pts[b], (200, 200, 200), 2, cv2.LINE_AA)

    # Puntos
    for idx, (x, y) in enumerate(pts):
        is_tip = idx in TIP_IDS
        is_wrist = idx == 0
        if is_tip:
            # Punta del dedo: circulo grande + borde blanco
            finger_n = TIP_IDS.index(idx)
            cv2.circle(frame, (x, y), 9, FINGER_COLORS[finger_n], -1)
            cv2.circle(frame, (x, y), 9, (255, 255, 255), 1)
        elif is_wrist:
            cv2.circle(frame, (x, y), 8, (255, 255, 255), -1)
            cv2.circle(frame, (x, y), 8, (100, 100, 100), 1)
        else:
            cv2.circle(frame, (x, y), 4, (220, 220, 220), -1)

        # Mostrar numero del landmark
        if show_indices:
            cv2.putText(frame, str(idx), (x + 6, y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.28, (255, 255, 180), 1, cv2.LINE_AA)

def get_finger_states(lm, prev_state):
    """
    Calcula que dedos estan abiertos (1) o cerrados (0)
    usando la misma logica geometrica del proyecto real.
    Incluye filtro de histeresis anti-temblor.
    """
    fingers = []

    # ── Pulgar ──────────────────────────────────────────
    pinky_base = lm[17]
    diff_thumb = dist2d(lm[4], pinky_base) - dist2d(lm[3], pinky_base)
    if prev_state[0] == 1:
        new_t = 0 if diff_thumb < -0.005 else 1
    else:
        new_t = 1 if diff_thumb >  0.020 else 0
    fingers.append(new_t)

    # ── Otros 4 dedos ────────────────────────────────────
    wrist = lm[0]
    for i in range(1, 5):
        diff = dist2d(lm[TIP_IDS[i]], wrist) - dist2d(lm[TIP_IDS[i]-2], wrist)
        if prev_state[i] == 1:
            new_f = 0 if diff < -0.015 else 1
        else:
            new_f = 1 if diff >  0.035 else 0
        fingers.append(new_f)

    return fingers

def draw_hud(frame, fingers, hand_label, confidence, w, h):
    """Dibuja el panel de informacion de los dedos."""
    panel_h = 90
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, panel_h), (10, 12, 20), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    # Etiqueta de la mano
    cv2.putText(frame, f"MANO: {hand_label}  (conf: {confidence:.2f})",
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 220, 255), 1, cv2.LINE_AA)

    # Indicadores por dedo
    for i, (name, val) in enumerate(zip(NAMES, fingers)):
        color  = FINGER_COLORS[i] if val else (60, 60, 80)
        icon   = "▲" if val else "▼"
        label  = f"{icon} {name}"
        x_pos  = 10 + i * (w // 5)
        # Fondo del dedo
        bg_col = (30, 50, 30) if val else (50, 30, 30)
        cv2.rectangle(frame, (x_pos - 4, 32), (x_pos + 120, 58), bg_col, -1)
        cv2.putText(frame, label, (x_pos, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

    # Comando que se enviaria al robot
    cmd = ",".join(map(str, fingers))
    open_count = sum(fingers)
    cv2.putText(frame, f"Comando robot: [{cmd}]   Dedos abiertos: {open_count}/5",
                (10, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 180), 1, cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
#  5. CAMARA
# ─────────────────────────────────────────────────────────
print("[INFO] Abriendo camara... (presiona Q para salir, ESPACIO para pausar)")
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("[ERROR] No se puede abrir la camara.")
    detector.close()
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

cv2.namedWindow("Test MediaPipe - Webcam", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Test MediaPipe - Webcam", 1280, 720)

# ─────────────────────────────────────────────────────────
#  6. BUCLE PRINCIPAL
# ─────────────────────────────────────────────────────────
timestamp_ms = 0
paused       = False
show_indices = True   # Toggle con tecla I

# Estado anterior por mano (para histeresis)
prev_states = {0: [1,1,1,1,1], 1: [1,1,1,1,1]}

# FPS
fps_counter = 0
fps_display = 0.0
fps_timer   = time.time()

while cap.isOpened():
    ok, frame = cap.read()
    if not ok:
        continue

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]
    timestamp_ms += 33   # ~30 fps simulados

    # ── Inferencia MediaPipe ──────────────────────────────
    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    if not paused:
        detector.detect_async(mp_image, timestamp_ms)

    # ── FPS ──────────────────────────────────────────────
    fps_counter += 1
    elapsed = time.time() - fps_timer
    if elapsed >= 1.0:
        fps_display = fps_counter / elapsed
        fps_counter = 0
        fps_timer   = time.time()

    # ── Resultados ───────────────────────────────────────
    if last_result and last_result.hand_landmarks and not paused:
        for hand_idx, (lm, handedness) in enumerate(
                zip(last_result.hand_landmarks, last_result.handedness)):

            # Nombre real de la mano (correccion espejo)
            raw_label  = handedness[0].category_name
            real_label = "DERECHA" if raw_label == "Left" else "IZQUIERDA"
            confidence = handedness[0].score

            # Esqueleto
            draw_skeleton(frame, lm, w, h, show_indices=show_indices)

            # Estado de dedos con histeresis
            fingers = get_finger_states(lm, prev_states[hand_idx])
            prev_states[hand_idx] = fingers

            # HUD (solo para la primera mano para no solapar)
            if hand_idx == 0:
                draw_hud(frame, fingers, real_label, confidence, w, h)

    elif paused:
        # Mensaje de pausa
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), (30, 10, 10), -1)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
        cv2.putText(frame, "⏸  PAUSADO  (ESPACIO para reanudar)",
                    (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 255), 2, cv2.LINE_AA)
    else:
        # Sin mano detectada
        cv2.putText(frame, "Buscando mano...  (acerca tu mano a la camara)",
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (100, 100, 255), 2, cv2.LINE_AA)

    # ── Info esquina superior derecha ────────────────────
    cv2.putText(frame, f"FPS: {fps_display:.1f}",
                (w - 130, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 180), 2, cv2.LINE_AA)

    # ── Leyenda de controles ─────────────────────────────
    cv2.putText(frame, "[Q] Salir  [ESPACIO] Pausar  [I] Ocultar/Mostrar indices",
                (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1, cv2.LINE_AA)

    cv2.imshow("Test MediaPipe - Webcam", frame)

    # ── Teclas ───────────────────────────────────────────
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == ord('Q'):
        break
    elif key == ord(' '):
        paused = not paused
        print(f"[INFO] {'PAUSADO' if paused else 'REANUDADO'}")
    elif key == ord('i') or key == ord('I'):
        show_indices = not show_indices
        print(f"[INFO] Indices de landmarks: {'VISIBLES' if show_indices else 'OCULTOS'}")

# ─────────────────────────────────────────────────────────
#  7. LIMPIEZA
# ─────────────────────────────────────────────────────────
cap.release()
detector.close()
cv2.destroyAllWindows()
print("[OK] Programa cerrado.")
