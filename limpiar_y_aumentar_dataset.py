import sys
import os
import shutil
import random
import math
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ──────────────────────────────────────────────
# CONFIGURACION
# ──────────────────────────────────────────────
SOURCE_DIR    = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\Fotos_biomecanica_project_final-export")
OUTPUT_DIR    = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\dataset_limpio_final")
DISCARDED_DIR = Path(r"C:\Users\vales\.gemini\antigravity\scratch\mano_robotica\dataset_descartadas")

CLASES            = ["close", "index", "open"]
TRAIN_RATIO       = 0.80
TEST_RATIO        = 0.20
BAD_SIZE_BYTES    = 4000   # imagenes < 4000 bytes = oscuras/no distinguibles
TARGET_PER_CLASS  = 160    # objetivo de imagenes totales por clase

random.seed(42)
np.random.seed(42)


# ──────────────────────────────────────────────
# CALIDAD DE IMAGEN
# ──────────────────────────────────────────────
def es_valida(filepath: Path):
    """Devuelve (True, '') o (False, razon)."""
    size = filepath.stat().st_size
    if size < BAD_SIZE_BYTES:
        return False, f"muy_pequena_{size}bytes"

    img = cv2.imread(str(filepath))
    if img is None:
        return False, "no_legible"

    gris    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brillo  = gris.mean()
    varianza = gris.std()

    if brillo < 25:
        return False, f"muy_oscura_brillo{brillo:.0f}"
    if varianza < 8:
        return False, f"sin_variacion_std{varianza:.0f}"

    return True, ""


# ──────────────────────────────────────────────
# DATA AUGMENTATION
# ──────────────────────────────────────────────
def aumentar(img: np.ndarray):
    """Genera 8 variantes de una imagen. Devuelve lista de np.ndarray."""
    h, w  = img.shape[:2]
    out   = []

    # 1) Flip horizontal
    out.append(cv2.flip(img, 1))

    # 2) Brillo +30%
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.30, 0, 255)
    out.append(cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR))

    # 3) Brillo -20%
    hsv2 = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv2[:, :, 2] = np.clip(hsv2[:, :, 2] * 0.80, 0, 255)
    out.append(cv2.cvtColor(hsv2.astype(np.uint8), cv2.COLOR_HSV2BGR))

    # 4) Rotacion +10 grados
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 10, 1.0)
    out.append(cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT))

    # 5) Rotacion -10 grados
    M2 = cv2.getRotationMatrix2D((w / 2, h / 2), -10, 1.0)
    out.append(cv2.warpAffine(img, M2, (w, h), borderMode=cv2.BORDER_REFLECT))

    # 6) Zoom in 10%
    mg = int(min(h, w) * 0.10)
    crop = img[mg: h - mg, mg: w - mg]
    out.append(cv2.resize(crop, (w, h)))

    # 7) Ruido gaussiano suave
    noise = np.random.normal(0, 8, img.shape).astype(np.int16)
    out.append(np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8))

    # 8) Flip + rotacion combinados
    flip = cv2.flip(img, 1)
    M3   = cv2.getRotationMatrix2D((w / 2, h / 2), 8, 1.0)
    out.append(cv2.warpAffine(flip, M3, (w, h), borderMode=cv2.BORDER_REFLECT))

    return out


# ──────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────
def recopilar(clase: str):
    """Junta todas las imagenes de training y testing para una clase."""
    imgs = []
    for split in ["training", "testing"]:
        folder = SOURCE_DIR / split
        imgs += [
            f for f in folder.iterdir()
            if f.is_file()
            and f.name.lower().startswith(f"{clase}_")
            and f.suffix.lower() in [".jpg", ".jpeg", ".png"]
        ]
    return imgs

_file_counter = 0

def ts():
    """Timestamp + contador global para garantizar nombres unicos."""
    global _file_counter
    _file_counter += 1
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{_file_counter:05d}"


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print("=" * 62)
    print("   LIMPIEZA + AUGMENTATION + SPLIT 80/20")
    print("=" * 62)

    # Limpiar y crear carpetas de salida
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    for split in ["training", "testing"]:
        (OUTPUT_DIR / split).mkdir(parents=True, exist_ok=True)
    DISCARDED_DIR.mkdir(parents=True, exist_ok=True)

    resumen = {}

    for clase in CLASES:
        print(f"\n>>> CLASE: {clase.upper()}")
        print("-" * 40)

        todas      = recopilar(clase)
        buenas     = []
        descartadas = []

        for p in todas:
            ok, razon = es_valida(p)
            if ok:
                buenas.append(p)
            else:
                descartadas.append((p, razon))

        print(f"  Encontradas : {len(todas)}")
        print(f"  Validas     : {len(buenas)}")
        print(f"  Descartadas : {len(descartadas)}")

        # Guardar descartadas para revision
        desc_folder = DISCARDED_DIR / clase
        desc_folder.mkdir(exist_ok=True)
        for p, razon in descartadas:
            shutil.copy2(p, desc_folder / f"[{razon}]_{p.name}")

        if not buenas:
            print(f"  AVISO: Sin imagenes validas para {clase}. Saltando.")
            continue

        # ── Data augmentation ──────────────────────
        faltan   = max(0, TARGET_PER_CLASS - len(buenas))
        aug_imgs = []

        if faltan > 0:
            print(f"  Generando {faltan} imagenes aumentadas...")
            cargadas = [cv2.imread(str(p)) for p in buenas if cv2.imread(str(p)) is not None]
            idx = 0
            while len(aug_imgs) < faltan:
                base     = cargadas[idx % len(cargadas)]
                variantes = aumentar(base)
                for v in variantes:
                    if len(aug_imgs) >= faltan:
                        break
                    aug_imgs.append(v)
                idx += 1
            print(f"  Augmentation OK: +{len(aug_imgs)} imagenes")
        else:
            print(f"  No necesita augmentation ({len(buenas)} imagenes disponibles)")

        # ── Calcular split 80/20 ───────────────────
        total_final = len(buenas) + len(aug_imgs)
        n_test      = max(1, math.floor(total_final * TEST_RATIO))
        n_train     = total_final - n_test

        print(f"\n  Split: {n_train} train | {n_test} test  ({n_train/total_final*100:.1f}% / {n_test/total_final*100:.1f}%)")

        # Mezclar originales; testing solo con originales
        random.shuffle(buenas)
        test_paths  = buenas[:n_test]
        train_paths = buenas[n_test:]

        # ── Copiar archivos ────────────────────────
        cnt_train = cnt_test = 0

        for p in test_paths:
            shutil.copy2(p, OUTPUT_DIR / "testing" / f"{clase}_{ts()}.jpg")
            cnt_test += 1

        for p in train_paths:
            shutil.copy2(p, OUTPUT_DIR / "training" / f"{clase}_{ts()}.jpg")
            cnt_train += 1

        for aug in aug_imgs:
            cv2.imwrite(
                str(OUTPUT_DIR / "training" / f"{clase}_{ts()}_aug.jpg"),
                aug,
                [cv2.IMWRITE_JPEG_QUALITY, 90]
            )
            cnt_train += 1

        resumen[clase] = {
            "originales" : len(todas),
            "descartadas": len(descartadas),
            "aumentadas" : len(aug_imgs),
            "train"      : cnt_train,
            "test"       : cnt_test,
            "total"      : cnt_train + cnt_test,
        }
        print(f"  Guardadas -> train: {cnt_train}  |  test: {cnt_test}")

    # ── Resumen global ─────────────────────────
    print("\n" + "=" * 62)
    print("   RESUMEN FINAL")
    print("=" * 62)
    hdr = f"{'CLASE':<10} {'ORIG':>6} {'DESC':>6} {'AUG':>6} {'TRAIN':>7} {'TEST':>6} {'TOTAL':>7} {'RATIO':>10}"
    print(hdr)
    print("-" * 62)

    tot_tr = tot_te = tot_all = 0
    for clase, d in resumen.items():
        ratio = f"{d['train']/d['total']*100:.1f}/{d['test']/d['total']*100:.1f}"
        print(f"{clase:<10} {d['originales']:>6} {d['descartadas']:>6} {d['aumentadas']:>6} "
              f"{d['train']:>7} {d['test']:>6} {d['total']:>7} {ratio:>10}")
        tot_tr  += d["train"]
        tot_te  += d["test"]
        tot_all += d["total"]

    print("-" * 62)
    ratio_g = f"{tot_tr/tot_all*100:.1f}/{tot_te/tot_all*100:.1f}"
    print(f"{'TOTAL':<10} {'':>6} {'':>6} {'':>6} {tot_tr:>7} {tot_te:>6} {tot_all:>7} {ratio_g:>10}")

    print(f"\n[OK] Dataset limpio guardado en:")
    print(f"     {OUTPUT_DIR}")
    print(f"\n[INFO] Descartadas en: {DISCARDED_DIR}")
    print(f"\n[LISTO] Sube las carpetas training/ y testing/ a Edge Impulse.")


if __name__ == "__main__":
    main()
