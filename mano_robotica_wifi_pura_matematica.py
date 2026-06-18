import cv2
import time
import math
import sys
import os
import urllib.request
import threading
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

# ─────────────────────────────────────────────────────────
#  1. WIFI CONFIGURATION
# ─────────────────────────────────────────────────────────
ESP32_IP = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
URL_COMMAND = f"http://{ESP32_IP}:82/dedos?estado="

def send_wifi_command(state):
    try:
        urllib.request.urlopen(URL_COMMAND + state, timeout=0.2)
    except Exception as e:
        print(f"[ERROR WIFI] No llega la señal al ESP32: {e}")

# ─────────────────────────────────────────────────────────
#  2. MEDIAPIPE MODEL
# ─────────────────────────────────────────────────────────
MODEL_MP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

if not os.path.exists(MODEL_MP):
    print(f"\n[ERROR] Missing '{MODEL_MP}'")
    sys.exit(1)

TIP_IDS = [4, 8, 12, 16, 20]
latest_result = None

def on_result(result, output_image, timestamp_ms):
    global latest_result
    latest_result = result

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_MP),
    running_mode=RunningMode.LIVE_STREAM,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    result_callback=on_result
)

detector = HandLandmarker.create_from_options(options)

# ─────────────────────────────────────────────────────────
#  3. DRAWING FUNCTIONS
# ─────────────────────────────────────────────────────────
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4), (0,5),(5,6),(6,7),(7,8),
    (9,10),(10,11),(11,12), (13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20), (5,9),(9,13),(13,17),(5,0)
]

def draw_hand(frame, landmarks, w, h):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 200, 120), 2)
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  4. CAMERA SETUP & MAIN LOOP
# ─────────────────────────────────────────────────────────
cv2.namedWindow("Hand Tracking", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Hand Tracking", 1280, 960)

print("[INFO] Connecting to Local Camera...")
cap = cv2.VideoCapture(0)

last_sent_state = ""
timestamp_ms  = 0
last_send_time = 0
send_interval = 0.1
previous_fingers_state = [1, 1, 1, 1, 1]
is_paused = False

while True:
    success, frame = cap.read()
    if not success: 
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "Local Camera disconnected", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    else:
        frame = cv2.flip(frame, 1)

    h, w  = frame.shape[:2]
    timestamp_ms += 33   

    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detector.detect_async(mp_image, timestamp_ms)

    state = "1,1,1,1,1" # Open by default

    if is_paused:
        cv2.putText(frame, "=== SYSTEM PAUSED ===", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 3)
        state = "1,1,1,1,1" # Force open when paused
    else:
        if latest_result and latest_result.hand_landmarks:
            for hand_landmarks in latest_result.hand_landmarks:
                draw_hand(frame, hand_landmarks, w, h)
                lm = hand_landmarks
                fingers = []

                def dist(p1, p2):
                    return math.hypot(p1.x - p2.x, p1.y - p2.y)

                wrist = lm[0]
                
                # --- Math Filter (Pure MediaPipe) ---
                # Thumb
                pinky_base = lm[17]
                thumb_diff = dist(lm[TIP_IDS[0]], pinky_base) - dist(lm[TIP_IDS[0]-1], pinky_base)
                if previous_fingers_state[0] == 1:
                    new_thumb = 0 if thumb_diff < -0.005 else 1
                else:
                    new_thumb = 1 if thumb_diff > 0.02 else 0
                fingers.append(new_thumb)

                # Other 4 fingers
                for i in range(1, 5):
                    finger_diff = dist(lm[TIP_IDS[i]], wrist) - dist(lm[TIP_IDS[i]-2], wrist)
                    if previous_fingers_state[i] == 1:
                        new_finger = 0 if finger_diff < -0.015 else 1
                    else:
                        new_finger = 1 if finger_diff > 0.035 else 0
                    fingers.append(new_finger)

                previous_fingers_state = fingers.copy()
                state = ",".join(map(str, fingers))

                cv2.putText(frame, f"Command: {state}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "Looking for hand...", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

    # Send over WiFi if changed
    current_time = time.time()
    if state != last_sent_state and (current_time - last_send_time) > send_interval:
        threading.Thread(target=send_wifi_command, args=(state,), daemon=True).start()
        last_sent_state = state
        last_send_time = current_time

    cv2.imshow("Hand Tracking", frame)
    
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'): 
        break
    elif key == ord(' '): # Spacebar
        is_paused = not is_paused
        print(f"[INFO] System {'PAUSED' if is_paused else 'RESUMED'}")

# --- EXIT ROUTINE ---
print("[INFO] Sending final OPEN command before exiting...")
try:
    urllib.request.urlopen(URL_COMMAND + "1,1,1,1,1", timeout=1.0)
except Exception:
    pass

if cap is not None:
    cap.release()
detector.close()
cv2.destroyAllWindows()
print("[OK] Program finished.")
