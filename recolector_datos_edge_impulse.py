import cv2
import csv
import os
import time
import mediapipe as mp

from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker
from mediapipe.tasks.python.vision import HandLandmarkerOptions
from mediapipe.tasks.python.vision import RunningMode

# ─────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────
# Cambia esto según el gesto que vas a guardar en este momento.
# Ejemplos: "abierta", "cerrada", "pulgar_arriba", "pinza"
GESTO ="pinza"

# Usa 0 para probar con la cámara de tu laptop (RECOMENDADO PARA ESTA FASE)
URL_VIDEO = 0

# Si quisieras usar la ESP32-CAM pon la IP de tu placa, pero no es necesario ahora:
# URL_VIDEO = "http://192.168.4.1:81/stream"

ARCHIVO_CSV = "dataset_landmarks_mano.csv"

# Modelo de Mediapipe
MODELO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "hand_landmarker.task"
)

if not os.path.exists(MODELO):
    print("[ERROR] Falta el archivo hand_landmarker.task en la misma carpeta del script.")
    exit()

# ─────────────────────────────────────────────────────────
# CREAR/ABRIR CSV
# ─────────────────────────────────────────────────────────
# Crear columnas del CSV: x0, y0, z0, x1, y1, z1 ... x20, y20, z20, gesto
columnas = []
for i in range(21):
    columnas += [f"x{i}", f"y{i}", f"z{i}"]
columnas.append("gesto")

# Si el archivo no existe, crearlo y poner la cabecera
if not os.path.exists(ARCHIVO_CSV):
    with open(ARCHIVO_CSV, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columnas)

# ─────────────────────────────────────────────────────────
# INICIAR MEDIAPIPE Y CÁMARA
# ─────────────────────────────────────────────────────────
options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODELO),
    running_mode=RunningMode.IMAGE,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5
)

detector = HandLandmarker.create_from_options(options)
cap = cv2.VideoCapture(URL_VIDEO)

if not cap.isOpened():
    print("[ERROR] No se pudo abrir la cámara o el stream.")
    detector.close()
    exit()

print("[OK] Cámara abierta correctamente.")
print("========================================")
print(f"[INFO] GESTO ACTUAL: {GESTO}")
print("[INFO] Presiona 'g' para guardar una muestra de este gesto.")
print("[INFO] Presiona 'q' para salir.")
print("========================================")

contador_muestras = 0

while True:
    success, frame = cap.read()
    if not success:
        print("[WARNING] No se pudo leer frame.")
        time.sleep(0.1)
        continue

    # Acomodar frame
    frame = cv2.resize(frame, (320, 240))
    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = detector.detect(mp_image)

    h, w = frame.shape[:2]

    if result.hand_landmarks:
        landmarks = result.hand_landmarks[0]

        # Dibujar puntos de la mano
        for lm in landmarks:
            x = int(lm.x * w)
            y = int(lm.y * h)
            cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)

        cv2.putText(frame, f"Listo para: {GESTO} | Llevas: {contador_muestras}", (10, 25), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    else:
        cv2.putText(frame, f"No se detecta mano | Llevas: {contador_muestras}", (10, 25), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow("Captura de landmarks para Edge Impulse", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord("g"):
        if result.hand_landmarks:
            landmarks = result.hand_landmarks[0]
            fila = []
            for lm in landmarks:
                fila += [lm.x, lm.y, lm.z]
            fila.append(GESTO)

            with open(ARCHIVO_CSV, mode="a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(fila)

            contador_muestras += 1
            print(f"[OK] Muestra guardada: {GESTO} | Total: {contador_muestras}")
            time.sleep(0.15) # Pequeña pausa para no guardar 100 veces por accidente
        else:
            print("[INFO] No se guardó porque no hay mano detectada en este momento.")

    elif key == ord("q"):
        break

cap.release()
detector.close()
cv2.destroyAllWindows()
print("[OK] Recolección finalizada. Dataset guardado.")
