"""
=============================================================
 ROBOTIC HAND PROJECT
=============================================================
 Compatible with Python 3.13 + mediapipe >= 0.10.14
 Uses Tasks API + draws with OpenCV.

 Serial format sent: "1,0,1,1,0\n"
  Order: Thumb, Index, Middle, Ring, Pinky
  1 = open / extended
  0 = closed / bent
=============================================================
"""

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

# ─────────────────────────────────────────────────────────
#  1. SERIAL CONFIGURATION
# ─────────────────────────────────────────────────────────

USE_SERIAL   = True
SERIAL_PORT  = 'COM7'
BAUD_RATE    = 9600

ser = None
SIMULATION_MODE = True

if USE_SERIAL:
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"[OK] Connected to ESP32 on {SERIAL_PORT}")
        SIMULATION_MODE = False
    except Exception as e:
        print(f"[INFO] Could not connect to ESP32 ({e})")
        print("[INFO] Simulation mode activated.")
else:
    print("[SIM] Simulation mode active (USE_SERIAL = False)")

# ─────────────────────────────────────────────────────────
#  2. MEDIAPIPE TASKS MODEL
# ─────────────────────────────────────────────────────────
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

if not os.path.exists(MODEL):
    print("\n[INFO] Missing 'hand_landmarker.task' file. First time running...")
    print("[INFO] Downloading MediaPipe model automatically (please wait)...")
    url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
    try:
        urllib.request.urlretrieve(url, MODEL)
        print("[OK] File downloaded successfully.\n")
    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        print("Ensure you have an internet connection for the first run.")
        sys.exit(1)

# Finger tips (indices from the 21-point model)
TIP_IDS = [4, 8, 12, 16, 20]

last_result = None

def on_result(result, output_image, timestamp_ms):
    global last_result
    last_result = result

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL),
    running_mode=RunningMode.LIVE_STREAM,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    result_callback=on_result
)

detector = HandLandmarker.create_from_options(options)
print("[OK] MediaPipe model loaded.")

# ─────────────────────────────────────────────────────────
#  3. SKELETON CONNECTIONS (for OpenCV drawing)
# ─────────────────────────────────────────────────────────
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),          # thumb
    (0,5),(5,6),(6,7),(7,8),          # index
    (9,10),(10,11),(11,12),           # middle
    (13,14),(14,15),(15,16),          # ring
    (0,17),(17,18),(18,19),(19,20),   # pinky
    (5,9),(9,13),(13,17),(5,0),       # palm
]

def draw_hand(frame, landmarks, w, h):
    """Draws hand points and connections using pure OpenCV."""
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 200, 120), 2)
    for idx, (x, y) in enumerate(pts):
        color = (0, 255, 180) if idx in TIP_IDS else (255, 255, 255)
        cv2.circle(frame, (x, y), 5 if idx in TIP_IDS else 3, color, -1)

# ─────────────────────────────────────────────────────────
#  4. CAMERA
# ─────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("[ERROR] Could not open camera.")
    detector.close()
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print("[OK] Camera ready. Press 'q' to exit.\n")

cv2.namedWindow("Robotic Hand Project", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Robotic Hand Project", 1280, 720)

# ─────────────────────────────────────────────────────────
#  5. MAIN LOOP
# ─────────────────────────────────────────────────────────
last_state = "1,1,1,1,1" # Start open to maintain string tension
previous_fingers_state = [1, 1, 1, 1, 1] # Anti-vibration memory filter
timestamp_ms  = 0
tracking_active = True   # Controlled with SPACE

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        continue

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]
    timestamp_ms += 33   # simulate ~30 fps

    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detector.detect_async(mp_image, timestamp_ms)

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    if last_result and last_result.hand_landmarks:
        for idx, hand_landmarks in enumerate(last_result.hand_landmarks):
            draw_hand(frame, hand_landmarks, w, h)

            if last_result.handedness:
                detected_hand = last_result.handedness[idx][0].category_name
                # Mirroring fix
                real_hand_txt = "RIGHT" if detected_hand == "Left" else "LEFT"

                cv2.putText(frame, f"Controlling: {real_hand_txt} Hand",
                            (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 150, 50), 2, cv2.LINE_AA)

            lm    = hand_landmarks
            fingers = []

            def dist(p1, p2):
                return math.hypot(p1.x - p2.x, p1.y - p2.y)

            wrist = lm[0]

            # --- Mathematical Anti-Vibration Filter (Hysteresis) ---
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

            # --- PAUSE MODE ---
            if not tracking_active:
                state = "1,1,1,1,1"
                cv2.putText(frame, "=== SYSTEM PAUSED ===", (10, 160),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 255), 3, cv2.LINE_AA)

            if ser and state != last_state:
                try:
                    ser.write((state + '\n').encode('utf-8'))
                    last_state = state
                except Exception as e:
                    print(f"[ERROR] Serial: {e}")

            # --- HUD: finger indicators ---
            names = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
            for idx, (name, val) in enumerate(zip(names, fingers)):
                color = (0, 220, 100) if val else (60, 60, 200)
                icon = "^" if val else "v"
                cv2.putText(frame, f"{icon} {name}",
                            (10 + idx * 240, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)

            mode_txt = "SIM" if SIMULATION_MODE else "ESP32"
            cv2.putText(frame, f"[{mode_txt}]  {state}",
                        (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 180), 2, cv2.LINE_AA)

            cv2.putText(frame, f"Fingers:{sum(fingers)}/5",
                        (1050, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 220, 0), 2, cv2.LINE_AA)
    else:
        state = "1,1,1,1,1" # Keep open if no hand
        if ser and state != last_state:
            try:
                ser.write((state + '\n').encode('utf-8'))
                last_state = state
            except Exception: pass

        if not tracking_active:
            text = "SYSTEM PAUSED (Press SPACE)"
            color_t = (40, 40, 255)
        else:
            text = "Waiting for hand... (Fingers extended)"
            color_t = (100, 100, 255)

        cv2.putText(frame, text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, color_t, 2, cv2.LINE_AA)

    cv2.imshow("Robotic Hand Project", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        print("\n[INFO] Exiting...")
        break
    elif key == ord(' '):
        tracking_active = not tracking_active
        print(f"[INFO] Tracking: {'ACTIVATED' if tracking_active else 'PAUSED'}")

# ─────────────────────────────────────────────────────────
#  6. CLEANUP
# ─────────────────────────────────────────────────────────
cap.release()
detector.close()
cv2.destroyAllWindows()
if ser:
    ser.close()
    print("[OK] Serial connection closed.")
print("[OK] Program finished.")
