import cv2
import serial
import time
import math
import sys
import os
import urllib.request
import mediapipe as mp
from mediapipe.tasks.python        import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode


# └──────────────────────────────────────────────────────────┘
USAR_SERIAL   = True     # <- activado, ESP32 detectado en COM7
PUERTO_SERIAL = 'COM7'   # <- Silicon Labs CP210x (tu ESP32)
BAUD_RATE     = 9600

ser = None
MODO_SIMULACION = True

if USAR_SERIAL:
    try:
        ser = serial.Serial(PUERTO_SERIAL, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"[OK] Conectado al ESP32 en {PUERTO_SERIAL}")
        MODO_SIMULACION = False
    except Exception as e:
        print(f"[INFO] No se pudo conectar al ESP32 ({e})")
        print("[INFO] Modo simulacion activado.")
else:
    print("[SIM] Modo simulacion activo  (USAR_SERIAL = False)")

# ─────────────────────────────────────────────────────────
#  2. MODELO MEDIAPIPE TASKS
# ─────────────────────────────────────────────────────────
MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

if not os.path.exists(MODELO):
    print("\n[INFO] Falta el archivo 'hand_landmarker.task'. Primera vez ejecutando...")
    print("[INFO] Descargando modelo de MediaPipe automaticamente (espera un momento)...")
    url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
    try:
        urllib.request.urlretrieve(url, MODELO)
        print("[OK] Archivo descargado exitosamente.\n")
    except Exception as e:
        print(f"\n[ERROR] Falla al descargar: {e}")
        print("Asegurate de tener conexion a internet para la primera ejecucion.")
        sys.exit(1)

# Puntas de los dedos (indices del modelo de 21 puntos)
TIP_IDS = [4, 8, 12, 16, 20]

# Resultado compartido entre el callback y el bucle principal
ultimo_resultado = None

def on_result(result, output_image, timestamp_ms):
    global ultimo_resultado
    ultimo_resultado = result

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODELO),
    running_mode=RunningMode.LIVE_STREAM,
    num_hands=1,        # Solo una mano (una impresion 3D)
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    result_callback=on_result
)

detector = HandLandmarker.create_from_options(options)
print("[OK] Modelo MediaPipe cargado.")

# ─────────────────────────────────────────────────────────
#  3. CONEXIONES DEL ESQUELETO (para dibujar con OpenCV)
# ─────────────────────────────────────────────────────────
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),          # pulgar
    (0,5),(5,6),(6,7),(7,8),          # indice
    (9,10),(10,11),(11,12),           # medio
    (13,14),(14,15),(15,16),          # anular
    (0,17),(17,18),(18,19),(19,20),   # menique
    (5,9),(9,13),(13,17),(5,0),       # palma
]

def dibujar_mano(frame, landmarks, w, h):
    """Dibuja puntos y conexiones de la mano usando OpenCV puro."""
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    # Conexiones
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 200, 120), 2)
    # Puntos
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  4. CAMARA
# ─────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("[ERROR] No se pudo abrir la camara.")
    detector.close()
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print("[OK] Camara lista. Presiona 'q' para salir.\n")

# Ventana redimensionable (puedes arrastrar las esquinas)
cv2.namedWindow("Proyecto Mano Robotica - Valesska", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Proyecto Mano Robotica - Valesska", 1280, 720)

# ─────────────────────────────────────────────────────────
#  5. BUCLE PRINCIPAL
# ─────────────────────────────────────────────────────────
ultimo_estado = "1,1,1,1,1" # Vuelve a usar el estado abierto para mantener tension de hilos
estado_dedos_anterior = [1, 1, 1, 1, 1] # Filtro Anti-Vibracion de Memoria
timestamp_ms  = 0
seguimiento_activo = True   # Controlado con ESPACIO

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        continue

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]
    timestamp_ms += 33   # simula ~30 fps

    # Enviar frame al detector (asincrono)
    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detector.detect_async(mp_image, timestamp_ms)

    # ── HUD: fondo semitransparente para el HUD ────────────────
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    if ultimo_resultado and ultimo_resultado.hand_landmarks:
        for idx, hand_landmarks in enumerate(ultimo_resultado.hand_landmarks):
            dibujar_mano(frame, hand_landmarks, w, h)

            # --- Informacion de la Mano Detectada ---
            # Ojo: por el modo espejo de la camara, MediaPipe ve la Derecha real como "Left"
            if ultimo_resultado.handedness:
                mano_detectada = ultimo_resultado.handedness[idx][0].category_name
                mano_real_txt = "DERECHA" if mano_detectada == "Left" else "IZQUIERDA"

                # Muestra en pantalla que mano esta tomando el control
                cv2.putText(frame, f"Controlando con: Mano {mano_real_txt}",
                            (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 150, 50), 2, cv2.LINE_AA)

            lm    = hand_landmarks
            dedos = []

            # -------------------------------------------------------------
            #  LOGICA DE DISTANCIA 3D (No importa como rotes la mano)
            # -------------------------------------------------------------
            def dist(p1, p2):
                return math.hypot(p1.x - p2.x, p1.y - p2.y)

            # Punto de referencia: la muneca (0)
            muneca = lm[0]

            # --- Filtro Anti-Vibracion Matematico (Histeresis) ---
            # Esto evita "titubeos/vibraciones" en caso de que la camara tiemble.
            # Solo cambiara de estado si hay un movimiento intencional firme.
            
            # --- Pulgar ---
            base_menique = lm[17]
            dif_pulgar = dist(lm[TIP_IDS[0]], base_menique) - dist(lm[TIP_IDS[0]-1], base_menique)
            
            if estado_dedos_anterior[0] == 1:
                # Si esta abierto, tienes que cerrarlo decididamente para considerarlo 0
                nuevo_pulgar = 0 if dif_pulgar < -0.005 else 1
            else:
                # Si esta cerrado, tienes que abrirlo decididamente para considerarlo 1
                nuevo_pulgar = 1 if dif_pulgar > 0.02 else 0
                
            dedos.append(nuevo_pulgar)

            # --- Otros 4 dedos ---
            for i in range(1, 5):
                dif_dedo = dist(lm[TIP_IDS[i]], muneca) - dist(lm[TIP_IDS[i]-2], muneca)
                
                if estado_dedos_anterior[i] == 1:
                    nuevo_dedo = 0 if dif_dedo < -0.015 else 1
                else:
                    nuevo_dedo = 1 if dif_dedo > 0.035 else 0
                    
                dedos.append(nuevo_dedo)

            # Guardamos estado para el siguiente frame
            estado_dedos_anterior = dedos.copy()
            estado = ",".join(map(str, dedos))

            # --- MODO PAUSA ---
            if not seguimiento_activo:
                estado = "1,1,1,1,1"  # Retiene los dedos abiertos para la tension de los hilos
                cv2.putText(frame, "=== SISTEMA PAUSADO ===", (10, 160),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 255), 3, cv2.LINE_AA)

            # Enviar por serial cuando cambia el estado
            if ser and estado != ultimo_estado:
                try:
                    ser.write((estado + '\n').encode('utf-8'))
                    ultimo_estado = estado
                except Exception as e:
                    print(f"[ERROR] Serial: {e}")

            # --- HUD: indicadores de dedos ---
            nombres = ["Pulgar", "Indice", "Medio", "Anular", "Menique"]
            for idx, (nombre, val) in enumerate(zip(nombres, dedos)):
                color = (0, 220, 100) if val else (60, 60, 200)
                icono = "^" if val else "v"
                cv2.putText(frame, f"{icono} {nombre}",
                            (10 + idx * 240, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)

            modo_txt = "SIM" if MODO_SIMULACION else "ESP32"
            cv2.putText(frame, f"[{modo_txt}]  {estado}",
                        (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 180), 2, cv2.LINE_AA)

            cv2.putText(frame, f"Dedos:{sum(dedos)}/5",
                        (1050, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 220, 0), 2, cv2.LINE_AA)
    else:
        # --- MANTENER ABIERTA SI NO HAY MANO ---
        estado = "1,1,1,1,1" # Mantiene todo abierto
        if ser and estado != ultimo_estado:
            try:
                ser.write((estado + '\n').encode('utf-8'))
                ultimo_estado = estado
            except Exception: pass

        # Textos de estado HUD
        if not seguimiento_activo:
            texto = "SISTEMA PAUSADO (Presiona ESPACIO)"
            color_t = (40, 40, 255)
        else:
            texto = "Esperando mano... (Dedos extendidos)"
            color_t = (100, 100, 255)

        cv2.putText(frame, texto, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, color_t, 2, cv2.LINE_AA)

    cv2.imshow("Proyecto Mano Robotica - Valesska", frame)

    tecla = cv2.waitKey(1) & 0xFF
    if tecla == ord('q'):
        print("\n[INFO] Saliendo...")
        break
    elif tecla == ord(' '):  # Tecla ESPACIO
        seguimiento_activo = not seguimiento_activo
        print(f"[INFO] Seguimiento: {'ACTIVADO' if seguimiento_activo else 'PAUSADO'}")

# ─────────────────────────────────────────────────────────
#  6. LIMPIEZA
# ─────────────────────────────────────────────────────────
cap.release()
detector.close()
cv2.destroyAllWindows()
if ser:
    ser.close()
    print("[OK] Conexion serial cerrada.")
print("[OK] Programa finalizado.")
