"""
=============================================================
 ROBOTIC HAND PROJECT - WIRELESS TELEOPERATION (WIFI)
=============================================================
 Compatible with Python 3.13 + mediapipe >= 0.10.14
 
 THIS SCRIPT RUNS ON YOUR COMPUTER:
 1. Reads the live video stream from the ESP32-CAM over WiFi.
 2. Processes Hand AI (MediaPipe) on the PC using pure mathematics (no TFLite needed).
 3. Sends commands to the servos over WiFi ultra-fast and lag-free.
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
#  1. WIFI CONFIGURATION (ESP32-CAM)
# ─────────────────────────────────────────────────────────
ESP32_IP = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
URL_COMANDO = f"http://{ESP32_IP}:82/dedos?estado="

# Command queue of size 1 to always send the newest state and prevent latency
cola_comandos = queue.Queue(maxsize=1)

def hilo_transmisor():
    """Persistent background thread to send HTTP requests without accumulating lag."""
    while True:
        try:
            estado = cola_comandos.get()
            url = URL_COMANDO + estado
            # Send request with a short timeout
            with urllib.request.urlopen(url, timeout=0.15) as response:
                response.read()  # Close connection quickly
        except Exception:
            pass
        finally:
            cola_comandos.task_done()

# Start background transmitter thread immediately
threading.Thread(target=hilo_transmisor, daemon=True).start()

def enviar_orden_wifi(estado):
    """Inserts the new state into the queue, replacing the previous one if full."""
    if cola_comandos.full():
        try:
            cola_comandos.get_nowait()
            cola_comandos.task_done()
        except queue.Empty:
            pass
    cola_comandos.put(estado)

# ─────────────────────────────────────────────────────────
#  2. MEDIAPIPE MODEL CONFIGURATION
# ─────────────────────────────────────────────────────────
MODELO_MP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

if not os.path.exists(MODELO_MP):
    print("\n[INFO] Downloading MediaPipe 'hand_landmarker.task' model...")
    url_descarga = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    try:
        urllib.request.urlretrieve(url_descarga, MODELO_MP)
        print("[OK] Model downloaded successfully.")
    except Exception as e:
        print(f"[ERROR] Could not download the model: {e}")
        sys.exit(1)

# Global variables for MediaPipe callback
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
print("[OK] MediaPipe Initialized.")

# ─────────────────────────────────────────────────────────
#  3. DRAWING & HAND STRUCTURE
# ─────────────────────────────────────────────────────────
TIP_IDS = [4, 8, 12, 16, 20] # Finger tips (Thumb, Index, Middle, Ring, Pinky)

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4), (0,5),(5,6),(6,7),(7,8),
    (9,10),(10,11),(11,12), (13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),(5,0)
]

def dist(p1, p2):
    """Calculates the Euclidean distance between two points."""
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

def dibujar_esqueleto(frame, landmarks, w, h):
    """Draws the hand skeleton on screen."""
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    # Draw lines
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 250, 120), 2)
    # Draw points
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  4. CONNECTION TO ESP32-CAM WIFI CAMERA
# ─────────────────────────────────────────────────────────
print(f"[INFO] Connecting to video stream at {URL_VIDEO}...")
cap = cv2.VideoCapture(URL_VIDEO)

if not cap.isOpened():
    print("[ERROR] Could not open video stream from the ESP32-CAM.")
    print("        Make sure you are connected to the 'CamaraESP32' WiFi network.")
    sys.exit(1)

cv2.namedWindow("Mano Robotica - ESP32-CAM", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Mano Robotica - ESP32-CAM", 640, 480)

# ── HYSTERESIS FOR STABLE FINGER DETECTION (PREVENTS JITTER) ───
previous_fingers_state = [1, 1, 1, 1, 1]

# ─────────────────────────────────────────────────────────
#  5. MAIN PROCESSING LOOP
# ─────────────────────────────────────────────────────────
ultimo_estado_enviado = ""
last_send_time = 0
send_interval = 0.05  # 50 ms send interval (ultra-fast thanks to the background thread)
timestamp_ms = 0
seguimiento_activo = True
last_hand_detected_time = time.time()  # Timer to detect when the hand left the frame

print("\n=== SYSTEM READY! ===")
print("Press SPACEBAR to pause/resume.")
print("Press 'q' to exit.")

while True:
    success, frame = cap.read()
    if not success:
        continue

    # Mirror frame and get info
    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]
    timestamp_ms += 33 # Approximately 30 FPS

    state = "1,1,1,1,1" # Default state

    if seguimiento_activo:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detector.detect_async(mp_image, timestamp_ms)

        if ultimo_resultado and ultimo_resultado.hand_landmarks and len(ultimo_resultado.hand_landmarks) > 0:
            last_hand_detected_time = time.time()  # Update the last time the hand was detected
            
            for lm in ultimo_resultado.hand_landmarks:
                dibujar_esqueleto(frame, lm, w, h)
                
                # --- PURE MATH: OPEN/CLOSED FINGER CALCULATION ---
                fingers = []
                wrist = lm[0]

                # ── 1. Thumb finger (Lateral tilt vs pinky base) ──
                thumb_dist = dist(lm[4], lm[17])
                thumb_base_dist = dist(lm[2], lm[17])
                if previous_fingers_state[0] == 1:
                    new_thumb = 0 if thumb_dist < (thumb_base_dist * 0.85) else 1
                else:
                    new_thumb = 1 if thumb_dist > (thumb_base_dist * 0.95) else 0
                fingers.append(new_thumb)

                # ── 2. The other 4 fingers (Index, Middle, Ring, Pinky) ──
                for i in range(1, 5):
                    # Distance from tip to wrist compared to knuckle to wrist
                    finger_diff = dist(lm[TIP_IDS[i]], wrist) - dist(lm[TIP_IDS[i]-2], wrist)
                    
                    if previous_fingers_state[i] == 1:
                        new_finger = 0 if finger_diff < -0.015 else 1
                    else:
                        new_finger = 1 if finger_diff > 0.035 else 0
                    fingers.append(new_finger)

                # Save state
                previous_fingers_state = fingers.copy()
                state = ",".join(map(str, fingers))

                # Display info on screen
                cv2.putText(frame, f"Command: {state}", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 180), 2, cv2.LINE_AA)
        else:
            # IF NO HAND DETECTED:
            # Wait a 0.3s cushion to prevent sudden opening due to temporary tracking blinks
            tiempo_sin_mano = time.time() - last_hand_detected_time
            if tiempo_sin_mano > 0.3:
                state = "1,1,1,1,1" # Return to extended palm (all open) when hand leaves frame
                cv2.putText(frame, "Hand Absent -> Palm Open", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 165, 255), 2, cv2.LINE_AA)
            else:
                # Temporarily keep the last state to avoid sudden jumps
                state = ",".join(map(str, previous_fingers_state))
                cv2.putText(frame, "Searching for hand...", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
    else:
        # SYSTEM PAUSED:
        state = "1,1,1,1,1"  # When paused, open hand for safety
        cv2.putText(frame, "SYSTEM PAUSED (Hand Open)", (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 255), 2, cv2.LINE_AA)

    # --- OPTIMIZED WIFI TRANSMISSION ---
    current_time = time.time()
    if state != ultimo_estado_enviado and (current_time - last_send_time) > send_interval:
        enviar_orden_wifi(state)
        ultimo_estado_enviado = state
        last_send_time = current_time

    # Show visual interface
    cv2.imshow("Mano Robotica - ESP32-CAM", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):
        seguimiento_activo = not seguimiento_activo
        print(f"[INFO] Tracking: {'ACTIVE' if seguimiento_activo else 'PAUSED'}")

# ─────────────────────────────────────────────────────────
#  6. CLOSE EVERYTHING
# ─────────────────────────────────────────────────────────
print("\n[INFO] Sending final open hand command before exiting...")
enviar_orden_wifi("1,1,1,1,1")
time.sleep(0.5)

cap.release()
detector.close()
cv2.destroyAllWindows()
print("[OK] Program closed successfully.")
