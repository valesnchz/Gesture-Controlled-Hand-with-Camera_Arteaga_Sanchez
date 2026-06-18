"""
==============================================================
  CAPTURADOR DE DATASET BALANCEADO - ESP32-CAM
  Para reentrenar el modelo en Edge Impulse
==============================================================
  Cómo usar:
  1. Ejecuta este script: python capturar_dataset.py
  2. Presiona las teclas indicadas para capturar gestos
  3. Las fotos se guardan en carpetas por clase
  4. Sube las carpetas a Edge Impulse → Data Acquisition
==============================================================
"""

import cv2
import os
import time

# ── CONFIGURACIÓN ──────────────────────────────────────────────
ESP32_IP = "192.168.4.1"           # IP fija de la ESP32-CAM en modo AP (CamaraESP32)
URL_STREAM = f"http://{ESP32_IP}:81/stream"

# Carpeta donde se guardarán las fotos nuevas (usando ruta absoluta para evitar errores de directorio)
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_SALIDA = os.path.join(BASE_DIR, "nuevo_dataset")

# Las 3 clases del modelo — igual que en tu proyecto de Edge Impulse
# NOTA: "fondo/background" lo agrega FOMO automáticamente, no lo debes etiquetar
CLASES = {
    "o": "open",    # ✋ Mano abierta
    "c": "close",   # ✊ Puño cerrado
    "i": "index",   # ☝️ Dedo índice
}

# Cuántas fotos capturar por clase (para tener balance)
META_FOTOS = 80

# ── CREAR CARPETAS ─────────────────────────────────────────────
for clase in CLASES.values():
    carpeta = os.path.join(CARPETA_SALIDA, clase)
    os.makedirs(carpeta, exist_ok=True)

def contar_fotos(clase):
    carpeta = os.path.join(CARPETA_SALIDA, clase)
    return len([f for f in os.listdir(carpeta) if f.endswith(".jpg")])

def guardar_foto(frame, clase):
    carpeta = os.path.join(CARPETA_SALIDA, clase)
    timestamp = int(time.time() * 1000)
    nombre = f"{clase}_{timestamp}.jpg"
    ruta = os.path.join(carpeta, nombre)
    # Redimensionar a 96x96 para Edge Impulse (mismo tamaño del modelo)
    img_96 = cv2.resize(frame, (96, 96))
    cv2.imwrite(ruta, img_96)
    return nombre

# ── CONEXIÓN AL STREAM ─────────────────────────────────────────
print("\n" + "="*55)
print("  CAPTURADOR DE DATASET BALANCEADO - ESP32-CAM")
print("="*55)
print(f"\n  Conectando a: {URL_STREAM}")
print("  Espera un momento...\n")

cap = cv2.VideoCapture(URL_STREAM)

if not cap.isOpened():
    print(f"[ERROR] No se pudo conectar a la cámara en {URL_STREAM}")
    print("  Verifica que la IP sea correcta y que estés en la red 'CamaraESP32'")
    exit(1)

print("  [OK] Cámara conectada exitosamente.\n")
print("─"*55)
print("  TECLAS PARA CAPTURAR:")
print("  [O] → ✋ Mano Abierta  (open)")
print("  [C] → ✊ Puño Cerrado  (close)")
print("  [I] → ☝️  Dedo Índice   (index)")
print("  [Q] → Salir")
print("─"*55)
print(f"  Meta: {META_FOTOS} fotos por clase")
print("  NOTA: El fondo lo aprende FOMO automáticamente\n")

ultima_clase = None
ultimo_tiempo = 0
DELAY_ENTRE_FOTOS = 0.3  # segundos mínimos entre capturas

while True:
    ret, frame = cap.read()
    if not ret:
        print("[AVISO] Error leyendo frame. Reconectando...")
        time.sleep(0.5)
        continue

    # Voltear horizontalmente (espejo)
    frame = cv2.flip(frame, 1)

    # ── DIBUJAR HUD EN LA PANTALLA ─────────────────────────────
    pantalla = frame.copy()
    h, w = pantalla.shape[:2]

    # Recuadro de alineación (zona que se guardará)
    cx, cy = w // 2, h // 2
    tam = min(w, h) - 20
    x1 = cx - tam // 2
    y1 = cy - tam // 2
    x2 = cx + tam // 2
    y2 = cy + tam // 2
    cv2.rectangle(pantalla, (x1, y1), (x2, y2), (0, 255, 200), 2)
    cv2.putText(pantalla, "ALINEA TU MANO AQUI", (x1 + 5, y1 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1)

    # Fondo semitransparente para el texto de estado
    overlay = pantalla.copy()
    cv2.rectangle(overlay, (0, 0), (w, 110), (10, 10, 30), -1)
    cv2.addWeighted(overlay, 0.7, pantalla, 0.3, 0, pantalla)

    # Contadores de cada clase
    conteos = {c: contar_fotos(c) for c in CLASES.values()}
    textos = [
        f"[O] open:  {conteos['open']:3d}/{META_FOTOS}",
        f"[C] close: {conteos['close']:3d}/{META_FOTOS}",
        f"[I] index: {conteos['index']:3d}/{META_FOTOS}",
    ]

    for idx, texto in enumerate(textos):
        clase_key = list(CLASES.values())[idx]
        count = conteos[clase_key]
        color = (0, 255, 100) if count >= META_FOTOS else (200, 200, 200)
        cv2.putText(pantalla, texto, (10, 22 + idx * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)

    # Título
    cv2.putText(pantalla, "[Q]=Salir", (w - 130, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 200, 255), 1)

    # Flash verde cuando se captura
    ahora = time.time()
    if ultima_clase and (ahora - ultimo_tiempo) < 0.15:
        flash = pantalla.copy()
        cv2.rectangle(flash, (0, 0), (w, h), (0, 255, 0), -1)
        cv2.addWeighted(flash, 0.2, pantalla, 0.8, 0, pantalla)
        cv2.putText(pantalla, f"¡GUARDADO! → {ultima_clase}", (w//2 - 130, h//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

    cv2.imshow("Capturador de Dataset - ESP32-CAM", pantalla)

    # ── LEER TECLAS ────────────────────────────────────────────
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q') or key == ord('Q'):
        break

    ahora = time.time()
    clase_capturar = None

    if key == ord('o') or key == ord('O'):
        clase_capturar = "open"
    elif key == ord('c') or key == ord('C'):
        clase_capturar = "close"
    elif key == ord('i') or key == ord('I'):
        clase_capturar = "index"

    if clase_capturar and (ahora - ultimo_tiempo) > DELAY_ENTRE_FOTOS:
        count_actual = contar_fotos(clase_capturar)
        if count_actual < META_FOTOS:
            nombre = guardar_foto(frame, clase_capturar)
            print(f"  [✓] {clase_capturar:6s} → {nombre}  ({count_actual + 1}/{META_FOTOS})")
            ultima_clase = clase_capturar
            ultimo_tiempo = ahora
        else:
            print(f"  [META ALCANZADA] Ya tienes {META_FOTOS} fotos de '{clase_capturar}' ✅")
            ultima_clase = None

# ── RESUMEN FINAL ──────────────────────────────────────────────
cap.release()
cv2.destroyAllWindows()

print("\n" + "="*55)
print("  RESUMEN FINAL DE CAPTURAS:")
print("─"*55)
total = 0
for clase in CLASES.values():
    count = contar_fotos(clase)
    total += count
    estado = "✅" if count >= META_FOTOS else f"⚠️  Faltan {META_FOTOS - count}"
    print(f"  {clase:8s}: {count:3d} fotos  {estado}")
print("─"*55)
print(f"  TOTAL: {total} fotos capturadas")
print("="*55)
print(f"\n  Las fotos están en: ./{CARPETA_SALIDA}/")
print("  Súbelas a Edge Impulse → Data Acquisition → Upload data")
print()
