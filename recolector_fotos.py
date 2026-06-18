import cv2
import os
import time

# ─────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────
ESP32_IP = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
CARPETA_BASE = "dataset_fotos"

# Crear carpetas si no existen
for clase in ["open", "close", "index", "fondo"]:
    os.makedirs(os.path.join(CARPETA_BASE, clase), exist_ok=True)

print(f"[INFO] Conectando a la cámara en {URL_VIDEO}...")
cap = cv2.VideoCapture(URL_VIDEO)

if not cap.isOpened():
    print("[ERROR] No se pudo conectar a la ESP32-CAM. Revisa el WiFi.")
    exit()

print("\n" + "="*30)
print("   RECOLECTOR DE FOTOS PARA IA")
print("="*30)
print("Presiona 'a' -> Mano ABIERTA")
print("Presiona 'c' -> Mano CERRADA")
print("Presiona 'i' -> Dedo INDICE")
print("Presiona 'f' -> FONDO (Sin mano)")
print("-" * 30)
print("Presiona 'q' -> SALIR Y GUARDAR")
print("="*30 + "\n")

contador = {"open": 0, "close": 0, "index": 0, "fondo": 0}

while True:
    success, frame = cap.read()
    if not success:
        print("[WARNING] Perdiendo frames...")
        continue

    # Mostrar la imagen en tiempo real
    display_frame = frame.copy()
    cv2.putText(display_frame, f"Op:{contador['open']} | Cl:{contador['close']} | In:{contador['index']} | Fo:{contador['fondo']}", 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    cv2.imshow("Captura de Dataset (ESP32-CAM)", display_frame)
    
    key = cv2.waitKey(1) & 0xFF
    
    clase_elegida = None
    if key == ord('a'): clase_elegida = "open"
    elif key == ord('c'): clase_elegida = "close"
    elif key == ord('i'): clase_elegida = "index"
    elif key == ord('f'): clase_elegida = "fondo"
    elif key == ord('q'): break
    
    if clase_elegida:
        # Generar nombre único basado en milisegundos
        timestamp = int(time.time() * 1000)
        nombre_archivo = f"{clase_elegida}_{timestamp}.jpg"
        ruta_completa = os.path.join(CARPETA_BASE, clase_elegida, nombre_archivo)
        
        # Guardar la imagen original
        # Consejo: Edge Impulse redimensionará a 96x96 o similar, 
        # pero es mejor guardar la original y dejar que la plataforma procese.
        cv2.imwrite(ruta_completa, frame)
        
        contador[clase_elegida] += 1
        print(f"[OK] {clase_elegida} guardada. Total: {contador[clase_elegida]}")

cap.release()
cv2.destroyAllWindows()
print(f"\n[FIN] Fotos guardadas en la carpeta '{CARPETA_BASE}'.")
