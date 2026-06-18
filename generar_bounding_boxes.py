"""
generar_bounding_boxes.py
=========================
Genera automaticamente el archivo bounding_boxes.labels para Edge Impulse.
Estrategia: deteccion de piel por color HSV + contornos con OpenCV.
No requiere modelos externos ni compatibilidad con mediapipe.

Uso: python generar_bounding_boxes.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import cv2
import numpy as np
from pathlib import Path

# ──────────────────────────────────────────
# CONFIGURACION
# ──────────────────────────────────────────
DATASET_DIR   = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\dataset_limpio_final")
CLASES        = ["close", "index", "open"]
MARGIN_FACTOR = 0.15   # 15% de margen alrededor de la deteccion

# Rangos HSV para deteccion de piel (cubre tonos claros y medios)
SKIN_LOWER_1  = np.array([0,  20, 50],  dtype=np.uint8)
SKIN_UPPER_1  = np.array([25, 255, 255], dtype=np.uint8)
SKIN_LOWER_2  = np.array([170, 20, 50],  dtype=np.uint8)
SKIN_UPPER_2  = np.array([180, 255, 255], dtype=np.uint8)

# Area minima del contorno para ser considerado mano (% del area total)
MIN_AREA_PCT  = 0.03   # al menos 3% del area de la imagen


def detectar_mano_piel(imagen_bgr: np.ndarray):
    """
    Detecta la mano por segmentacion de color de piel.
    Retorna (x, y, w, h) con margen o None si no detecta.
    """
    h_img, w_img = imagen_bgr.shape[:2]
    area_img     = h_img * w_img

    # Convertir a HSV
    hsv = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2HSV)

    # Mascara de piel (dos rangos para cubrir rojos/naranjas)
    mask1 = cv2.inRange(hsv, SKIN_LOWER_1, SKIN_UPPER_1)
    mask2 = cv2.inRange(hsv, SKIN_LOWER_2, SKIN_UPPER_2)
    mask  = cv2.bitwise_or(mask1, mask2)

    # Morfologia para limpiar ruido
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=1)

    # Encontrar contornos
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Filtrar por area minima y quedarse con el mayor
    validos = [c for c in contours if cv2.contourArea(c) > area_img * MIN_AREA_PCT]
    if not validos:
        return None

    mayor = max(validos, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(mayor)

    # Agregar margen
    mg_x = int(w * MARGIN_FACTOR)
    mg_y = int(h * MARGIN_FACTOR)
    x = max(0, x - mg_x)
    y = max(0, y - mg_y)
    w = min(w_img - x, w + 2 * mg_x)
    h = min(h_img - y, h + 2 * mg_y)

    return (float(x), float(y), float(w), float(h))


def procesar_split(split: str):
    carpeta    = DATASET_DIR / split
    label_file = carpeta / "bounding_boxes.labels"

    imagenes = sorted([
        f for f in carpeta.iterdir()
        if f.is_file()
        and f.suffix.lower() in [".jpg", ".jpeg", ".png"]
        and any(f.name.lower().startswith(c + "_") for c in CLASES)
    ])

    print(f"\n  Procesando {split}/ -> {len(imagenes)} imagenes...")

    bboxes     = {}
    detectadas = 0
    fallidas   = 0
    fallidas_nombres = []

    for i, img_path in enumerate(imagenes):
        clase = img_path.name.split("_")[0]
        img   = cv2.imread(str(img_path))

        if img is None:
            fallidas += 1
            continue

        h_img, w_img = img.shape[:2]
        bbox = detectar_mano_piel(img)

        if bbox is not None:
            x, y, w, h = bbox
            detectadas += 1
        else:
            # Fallback: bbox = imagen completa
            x, y, w, h = 0.0, 0.0, float(w_img), float(h_img)
            fallidas += 1
            fallidas_nombres.append(img_path.name)

        bboxes[img_path.name] = [{"label": clase, "x": x, "y": y, "width": w, "height": h}]

        # Progreso
        if (i + 1) % 25 == 0 or (i + 1) == len(imagenes):
            pct = (i + 1) / len(imagenes) * 100
            print(f"    [{i+1:3d}/{len(imagenes)}] {pct:.0f}%  detectadas:{detectadas}  fallback:{fallidas}")

    # Guardar archivo
    output = {"version": 1, "type": "bounding-box-labels", "boundingBoxes": bboxes}
    with open(label_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    print(f"\n  Guardado: {label_file}")
    print(f"  Detectadas : {detectadas}")
    print(f"  Fallback   : {fallidas}")
    if fallidas_nombres:
        print(f"  Imagenes con fallback (bbox imagen completa):")
        for n in fallidas_nombres[:10]:
            print(f"    - {n}")
        if len(fallidas_nombres) > 10:
            print(f"    ... y {len(fallidas_nombres)-10} mas")

    return detectadas, fallidas


def main():
    print("=" * 62)
    print("  GENERAR BOUNDING BOXES - DETECCION POR COLOR DE PIEL")
    print("=" * 62)

    if not DATASET_DIR.exists():
        print(f"\n[ERROR] No existe: {DATASET_DIR}")
        print("  Ejecuta primero: python limpiar_y_aumentar_dataset.py")
        return

    tot_det = tot_fall = 0
    for split in ["training", "testing"]:
        d, f = procesar_split(split)
        tot_det  += d
        tot_fall += f

    total = tot_det + tot_fall
    print("\n" + "=" * 62)
    print("  RESUMEN")
    print("=" * 62)
    print(f"  Total procesadas : {total}")
    print(f"  Detectadas       : {tot_det}  ({tot_det/total*100:.1f}%)")
    print(f"  Fallback bbox    : {tot_fall}  ({tot_fall/total*100:.1f}%)")
    print(f"\n[LISTO] Archivos generados en:")
    print(f"  {DATASET_DIR / 'training' / 'bounding_boxes.labels'}")
    print(f"  {DATASET_DIR / 'testing'  / 'bounding_boxes.labels'}")
    print(f"\nSube training/ y testing/ a Edge Impulse.")


if __name__ == "__main__":
    main()
