import sys
import json
import shutil
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

SRC_DIR = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\dataset_limpio_final")
DST_DIR = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\dataset_2_clases")

# Las dos clases más opuestas, perfectas para un modelo robusto y fácil.
CLASES_A_MANTENER = ["open", "close"]

def procesar_split(split):
    src_split = SRC_DIR / split
    dst_split = DST_DIR / split
    dst_split.mkdir(parents=True, exist_ok=True)
    
    # Leer labels originales
    with open(src_split / "bounding_boxes.labels", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    new_bboxes = {}
    count = 0
    aug_count = 0
    
    # Copiar imagenes y filtrar labels
    for file_path in src_split.glob("*.jpg"):
        clase = file_path.name.split("_")[0]
        
        if clase in CLASES_A_MANTENER:
            shutil.copy2(file_path, dst_split / file_path.name)
            
            if file_path.name in data["boundingBoxes"]:
                new_bboxes[file_path.name] = data["boundingBoxes"][file_path.name]
            count += 1
            
    # Guardar nuevos labels solo con las imágenes copiadas
    data["boundingBoxes"] = new_bboxes
    with open(dst_split / "bounding_boxes.labels", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        
    print(f"[{split.upper()}]")
    print(f"  Imagenes copiadas : {count}")
    print(f"  Augmentations excluidas: {aug_count}")

def main():
    print("=" * 50)
    print(" CREANDO DATASET DE 2 CLASES (SIN AUGMENTATION)")
    print("=" * 50)
    
    if DST_DIR.exists():
        shutil.rmtree(DST_DIR)
        
    procesar_split("training")
    print("-" * 50)
    procesar_split("testing")
    print("=" * 50)
    print(f"NUEVO DATASET CREADO EN:\n {DST_DIR}")

if __name__ == "__main__":
    main()
