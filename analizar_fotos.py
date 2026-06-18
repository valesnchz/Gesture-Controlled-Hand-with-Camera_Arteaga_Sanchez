import cv2
import os
import glob
import numpy as np

def is_dark_or_blurry(folder_path):
    print("Analizando fotos en:", folder_path)
    search_path = os.path.join(folder_path, "**", "*.*")
    files = glob.glob(search_path, recursive=True)
    image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if not image_files:
        print("No se encontraron imagenes.")
        return
    results = []
    for file in image_files:
        if ".venv" in file or ".vscode" in file:
            continue
        img = cv2.imread(file)
        if img is None:
            continue
        brillo = np.mean(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        results.append({
            'file': file,
            'brillo': brillo,
            'blur': blur,
            'basename': os.path.basename(file)
        })
    oscuras = sorted(results, key=lambda x: x['brillo'])[:10]
    borrosas = sorted(results, key=lambda x: x['blur'])[:10]
    print("\n--- LAS 10 FOTOS MÁS OSCURAS ---")
    for r in oscuras:
        print(f"{r['basename']} (Brillo: {r['brillo']:.2f} / 255.0)")
    print("\n--- LAS 10 FOTOS MÁS BORROSAS ---")
    for r in borrosas:
        print(f"{r['basename']} (Borrosidad: {r['blur']:.2f})")

if __name__ == "__main__":
    is_dark_or_blurry(r"c:\Users\vales\.gemini\antigravity\scratch\mano_robotica")
