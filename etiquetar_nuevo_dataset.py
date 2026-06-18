import json
import cv2
import numpy as np
from pathlib import Path
import os

DATASET_DIR = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\nuevo_dataset")
CLASES = ["close", "index", "open"]
MARGIN_FACTOR = 0.15

SKIN_LOWER_1  = np.array([0,  20, 50],  dtype=np.uint8)
SKIN_UPPER_1  = np.array([25, 255, 255], dtype=np.uint8)
SKIN_LOWER_2  = np.array([170, 20, 50],  dtype=np.uint8)
SKIN_UPPER_2  = np.array([180, 255, 255], dtype=np.uint8)
MIN_AREA_PCT  = 0.03

def detectar_mano_piel(imagen_bgr):
    h_img, w_img = imagen_bgr.shape[:2]
    area_img = h_img * w_img
    hsv = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, SKIN_LOWER_1, SKIN_UPPER_1)
    mask2 = cv2.inRange(hsv, SKIN_LOWER_2, SKIN_UPPER_2)
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return None
    validos = [c for c in contours if cv2.contourArea(c) > area_img * MIN_AREA_PCT]
    if not validos: return None
    mayor = max(validos, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(mayor)
    mg_x = int(w * MARGIN_FACTOR)
    mg_y = int(h * MARGIN_FACTOR)
    x = max(0, x - mg_x)
    y = max(0, y - mg_y)
    w = min(w_img - x, w + 2 * mg_x)
    h = min(h_img - y, h + 2 * mg_y)
    return (float(x), float(y), float(w), float(h))

def procesar_carpeta(clase):
    carpeta = DATASET_DIR / clase
    if not carpeta.exists():
        return
    label_file = carpeta / "bounding_boxes.labels"
    imagenes = [f for f in carpeta.iterdir() if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
    if not imagenes:
        return
    bboxes = {}
    detectadas = 0
    for img_path in imagenes:
        img = cv2.imread(str(img_path))
        if img is None: continue
        h_img, w_img = img.shape[:2]
        bbox = detectar_mano_piel(img)
        if bbox is not None:
            x, y, w, h = bbox
            detectadas += 1
        else:
            x, y, w, h = 0.0, 0.0, float(w_img), float(h_img)
        bboxes[img_path.name] = [{"label": clase, "x": x, "y": y, "width": w, "height": h}]
    output = {"version": 1, "type": "bounding-box-labels", "boundingBoxes": bboxes}
    with open(label_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)
    print(f"Procesado {clase}: {detectadas}/{len(imagenes)} manos detectadas con exito.")

if __name__ == "__main__":
    for c in CLASES:
        procesar_carpeta(c)
    print("¡Proceso terminado!")
