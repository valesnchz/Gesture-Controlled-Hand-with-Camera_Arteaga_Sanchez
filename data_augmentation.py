import cv2
import os
import numpy as np
import time

# ---------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------
CARPETA_ORIGEN  = "dataset_fotos_final"
CARPETA_DESTINO = "dataset_aumentado_final"
CLASES          = ["open", "close", "index"]

# Cuántas versiones aumentadas generar por cada foto original
AUMENTOS_POR_IMAGEN = 5  # → de 240 originales a ~1440 en total

# ---------------------------------------------------------
# FUNCIONES DE AUGMENTATION
# ---------------------------------------------------------

def flip_horizontal(img):
    return cv2.flip(img, 1)

def ajustar_brillo(img, factor):
    """factor > 1 = más brillante, < 1 = más oscuro"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * factor, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

def rotar(img, angulo):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angulo, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)

def zoom(img, factor):
    """factor > 1 = zoom in, < 1 = zoom out"""
    h, w = img.shape[:2]
    new_h, new_w = int(h * factor), int(w * factor)
    resized = cv2.resize(img, (new_w, new_h))
    if factor > 1:
        # Recortar al centro
        start_y = (new_h - h) // 2
        start_x = (new_w - w) // 2
        return resized[start_y:start_y+h, start_x:start_x+w]
    else:
        # Rellenar con negro alrededor
        canvas = np.zeros_like(img)
        start_y = (h - new_h) // 2
        start_x = (w - new_w) // 2
        canvas[start_y:start_y+new_h, start_x:start_x+new_w] = resized
        return canvas

def agregar_ruido(img):
    ruido = np.random.normal(0, 15, img.shape).astype(np.int16)
    resultado = np.clip(img.astype(np.int16) + ruido, 0, 255).astype(np.uint8)
    return resultado

def desenfoque(img):
    return cv2.GaussianBlur(img, (3, 3), 0)

# Lista de transformaciones (nombre, función)
TRANSFORMACIONES = [
    ("flip",         flip_horizontal),
    ("brillo_alto",  lambda img: ajustar_brillo(img, 1.4)),
    ("brillo_bajo",  lambda img: ajustar_brillo(img, 0.6)),
    ("rot_pos15",    lambda img: rotar(img, 15)),
    ("rot_neg15",    lambda img: rotar(img, -15)),
    ("rot_pos30",    lambda img: rotar(img, 30)),
    ("rot_neg30",    lambda img: rotar(img, -30)),
    ("zoom_in",      lambda img: zoom(img, 1.2)),
    ("zoom_out",     lambda img: zoom(img, 0.8)),
    ("ruido",        agregar_ruido),
    ("blur",         desenfoque),
]

# ---------------------------------------------------------
# PROCESO PRINCIPAL
# ---------------------------------------------------------

total_generadas = 0

print("=" * 45)
print("      DATA AUGMENTATION - MANO ROBOTICA")
print("=" * 45)

for clase in CLASES:
    carpeta_entrada = os.path.join(CARPETA_ORIGEN, clase)
    carpeta_salida  = os.path.join(CARPETA_DESTINO, clase)
    os.makedirs(carpeta_salida, exist_ok=True)

    imagenes = [f for f in os.listdir(carpeta_entrada) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    print(f"\n[{clase.upper()}] {len(imagenes)} imágenes originales encontradas")

    generadas_clase = 0

    for nombre_img in imagenes:
        ruta_img = os.path.join(carpeta_entrada, nombre_img)
        img = cv2.imread(ruta_img)

        if img is None:
            print(f"  [SKIP] No se pudo leer: {nombre_img}")
            continue

        # Copiar la imagen original al destino también
        ruta_orig_destino = os.path.join(carpeta_salida, nombre_img)
        cv2.imwrite(ruta_orig_destino, img)

        # Aplicar N transformaciones aleatorias
        transformaciones_elegidas = np.random.choice(
            len(TRANSFORMACIONES),
            size=AUMENTOS_POR_IMAGEN,
            replace=False if AUMENTOS_POR_IMAGEN <= len(TRANSFORMACIONES) else True
        )

        for idx in transformaciones_elegidas:
            nombre_trans, funcion = TRANSFORMACIONES[idx]
            img_aug = funcion(img)

            ts = int(time.time() * 1000000)  # microsegundos para evitar colisiones
            nombre_nuevo = f"{clase}_{nombre_trans}_{ts}.jpg"
            ruta_destino = os.path.join(carpeta_salida, nombre_nuevo)
            cv2.imwrite(ruta_destino, img_aug)
            generadas_clase += 1

    total_clase = len(imagenes) + generadas_clase
    print(f"  OK Generadas: {generadas_clase} nuevas | Total en carpeta: {total_clase}")
    total_generadas += generadas_clase

print("\n" + "=" * 45)
print(f"  LISTO - {total_generadas} imágenes nuevas generadas")
print(f"  Carpeta de salida: '{CARPETA_DESTINO}/'")
print("=" * 45)
