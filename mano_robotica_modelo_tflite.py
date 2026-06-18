"""
=============================================================
 MANO ROBOTICA - MODELO FOMO DE EDGE IMPULSE (Imagen 96x96)
=============================================================
 Este script usa el modelo TFLite entrenado en Edge Impulse
 con arquitectura FOMO (Faster Objects, More Objects).

 Flujo:
  1. Lee el video de la ESP32-CAM por WiFi
  2. Recorta y redimensiona cada frame a 96x96 RGB
  3. Lo pasa al modelo FOMO → detecta OPEN / CLOSE
  4. Manda la orden a los servos por UDP
=============================================================
"""

import cv2
import time
import sys
import os
import socket
import threading
import queue
import numpy as np

# ─────────────────────────────────────────────────────────
#  1. CONFIGURACION
# ─────────────────────────────────────────────────────────
ESP32_IP  = "192.168.4.1"
URL_VIDEO = f"http://{ESP32_IP}:81/stream"
UDP_PORT  = 82

# ── Clases del modelo (en el MISMO orden que las entrenaste en Edge Impulse) ──
# Ve a tu proyecto en edgeimpulse.com → Impulse Design → Labels para verificarlos
# Normalmente están en orden alfabético. Ajusta si es necesario.
CLASES = ["close", "open"]   # índice 0 = close, índice 1 = open
# Si tu modelo tiene 4 salidas y las primeras 2 son tus clases, deja así.
# Si ves resultados al revés, intercambia: ["open", "close"]

# Comando de servo para cada gesto
COMANDO_POR_GESTO = {
    "open":  "1,1,1,1,1",   # Todos abiertos
    "close": "0,0,0,0,0",   # Todos cerrados
}

# Tamaño de entrada del modelo (96x96)
MODEL_INPUT_SIZE = 96

# Umbral mínimo de confianza para aceptar una detección (0.0 - 1.0)
CONFIDENCE_THRESHOLD = 0.3

# ─────────────────────────────────────────────────────────
#  2. ENVIO UDP (hilo de fondo, sin lag)
# ─────────────────────────────────────────────────────────
cola_udp = queue.Queue(maxsize=1)
sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def hilo_udp():
    while True:
        try:
            msg = cola_udp.get()
            sock_udp.sendto(msg.encode(), (ESP32_IP, UDP_PORT))
        except Exception as e:
            print(f"[UDP ERROR] {e}")
        finally:
            cola_udp.task_done()

threading.Thread(target=hilo_udp, daemon=True).start()

def enviar_comando(estado):
    if cola_udp.full():
        try:
            cola_udp.get_nowait()
            cola_udp.task_done()
        except queue.Empty:
            pass
    cola_udp.put(estado)

# ─────────────────────────────────────────────────────────
#  3. CARGAR MODELO TFLITE
# ─────────────────────────────────────────────────────────
MODELO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelo_mano.tflite")

if not os.path.exists(MODELO_PATH):
    print(f"[ERROR] No se encontró '{MODELO_PATH}'")
    sys.exit(1)

# Importar TFLite (compatible con Windows usando tensorflow-cpu)
try:
    import tflite_runtime.interpreter as tflite
    Interpreter = tflite.Interpreter
    print("[OK] tflite_runtime cargado.")
except ImportError:
    try:
        from tensorflow.lite.python.interpreter import Interpreter
        print("[OK] tensorflow.lite cargado.")
    except ImportError:
        try:
            import tensorflow as tf
            Interpreter = tf.lite.Interpreter
            print("[OK] tensorflow cargado.")
        except ImportError:
            print("[ERROR] Instala tensorflow:  pip install tensorflow-cpu")
            sys.exit(1)

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Silenciar warnings de TF

interpreter = Interpreter(model_path=MODELO_PATH)
interpreter.allocate_tensors()

input_details  = interpreter.get_input_details()
output_details = interpreter.get_output_details()

INPUT_SHAPE = input_details[0]['shape']   # [1, 96, 96, 3]
OUTPUT_SHAPE = output_details[0]['shape'] # [1, 12, 12, N]
NUM_CLASES_MODELO = OUTPUT_SHAPE[-1]      # Número de canales de salida

print(f"[OK] Modelo FOMO cargado.")
print(f"     Entrada: {INPUT_SHAPE}  |  Salida: {OUTPUT_SHAPE}")
print(f"     Canales de salida: {NUM_CLASES_MODELO}")
print(f"     Clases configuradas: {CLASES}")

# ─────────────────────────────────────────────────────────
#  4. FUNCION: INFERENCIA FOMO
# ─────────────────────────────────────────────────────────
def preparar_imagen(frame):
    """Recorta al cuadrado central y redimensiona a 96x96 normalizado."""
    h, w = frame.shape[:2]
    lado = min(h, w)
    y0 = (h - lado) // 2
    x0 = (w - lado) // 2
    cuadrado = frame[y0:y0+lado, x0:x0+lado]
    img = cv2.resize(cuadrado, (MODEL_INPUT_SIZE, MODEL_INPUT_SIZE))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    return img.reshape(INPUT_SHAPE)   # [1, 96, 96, 3]

def inferencia_fomo(frame):
    """
    Corre el modelo FOMO y devuelve (gesto, confianza, mapa_calor).

    Salida FOMO [1, 12, 12, N]:
    - Cada celda del grid 12x12 predice la confianza de cada clase.
    - Sumamos todas las celdas por clase → la clase con mayor suma gana.
    - Canal 0 suele ser background en modelos FOMO de Edge Impulse.
    """
    entrada = preparar_imagen(frame)
    interpreter.set_tensor(input_details[0]['index'], entrada)
    interpreter.invoke()
    salida = interpreter.get_tensor(output_details[0]['index'])[0]  # [12, 12, N]

    # Sumar confianza de todas las celdas por clase (ignorar canal 0 = background)
    # Si tu modelo no tiene canal de background, empieza desde 0
    inicio_canal = 1 if NUM_CLASES_MODELO > len(CLASES) else 0
    scores = []
    for i, clase in enumerate(CLASES):
        canal = inicio_canal + i
        if canal < NUM_CLASES_MODELO:
            scores.append(salida[:, :, canal].max())  # máximo del heatmap
        else:
            scores.append(0.0)

    mejor_idx  = int(np.argmax(scores))
    confianza  = float(scores[mejor_idx])
    gesto      = CLASES[mejor_idx] if confianza >= CONFIDENCE_THRESHOLD else None

    # Mapa de calor para visualizar (canal de la clase ganadora)
    canal_vis = inicio_canal + mejor_idx
    heatmap = salida[:, :, canal_vis] if canal_vis < NUM_CLASES_MODELO else salida[:, :, 0]

    return gesto, confianza, heatmap, scores

def dibujar_heatmap(frame, heatmap, alpha=0.4):
    """Superpone el mapa de calor del modelo sobre el frame."""
    h, w = frame.shape[:2]
    hm_norm = (heatmap * 255).astype(np.uint8)
    hm_color = cv2.applyColorMap(hm_norm, cv2.COLORMAP_JET)
    hm_resized = cv2.resize(hm_color, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.addWeighted(frame, 1 - alpha, hm_resized, alpha, 0)

# ─────────────────────────────────────────────────────────
#  5. CONECTAR A LA CAMARA
# ─────────────────────────────────────────────────────────
print(f"\n[INFO] Conectando al stream: {URL_VIDEO}")
cap = cv2.VideoCapture(URL_VIDEO)

if not cap.isOpened():
    print("[ERROR] No se pudo abrir el stream de la ESP32-CAM.")
    print("        ¿Estás conectado al WiFi 'CamaraESP32'?")
    sys.exit(1)

cv2.namedWindow("Mano Robotica - FOMO", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Mano Robotica - FOMO", 720, 560)

# ─────────────────────────────────────────────────────────
#  6. BUCLE PRINCIPAL
# ─────────────────────────────────────────────────────────
timestamp_ms          = 0
ultimo_estado_enviado = ""
last_send_time        = 0
SEND_INTERVAL         = 0.05  # 50 ms

# Historial para suavizar predicciones
HISTORIAL_MAX  = 5
historial      = []
mostrar_heatmap = False
pausado         = False

print("\n=== SISTEMA LISTO ===")
print("SPACE  → pausar/reanudar")
print("H      → mostrar/ocultar mapa de calor del modelo")
print("Q      → salir")
print("====================\n")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]

    gesto     = None
    confianza = 0.0
    scores    = []

    if not pausado:
        gesto, confianza, heatmap, scores = inferencia_fomo(frame)

        # Historial para suavizar
        if gesto:
            historial.append(gesto)
        if len(historial) > HISTORIAL_MAX:
            historial.pop(0)

        gesto_final = max(set(historial), key=historial.count) if historial else None
    else:
        gesto_final = None

    # Superponer heatmap si está activado
    if mostrar_heatmap and not pausado and heatmap is not None:
        frame = dibujar_heatmap(frame, heatmap)

    # Determinar comando de servo
    if pausado:
        comando = "1,1,1,1,1"
    elif gesto_final:
        comando = COMANDO_POR_GESTO.get(gesto_final, "1,1,1,1,1")
    else:
        comando = "1,1,1,1,1"  # Sin detección → mano abierta

    # Enviar por UDP si cambió
    now = time.time()
    if comando != ultimo_estado_enviado and (now - last_send_time) > SEND_INTERVAL:
        enviar_comando(comando)
        ultimo_estado_enviado = comando
        last_send_time = now

    # ── HUD ──────────────────────────────────────────────
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 90), (15, 15, 35), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    if pausado:
        cv2.putText(frame, "SISTEMA PAUSADO  (SPACE = reanudar)", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (50, 50, 255), 2)
    elif gesto_final:
        color = (0, 255, 100) if gesto_final == "open" else (0, 80, 255)
        label = gesto_final.upper()
        cv2.putText(frame, f"Gesto: {label}  ({confianza*100:.0f}%)", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 2)
        # Mini barras de confianza por clase
        for i, (cls, sc) in enumerate(zip(CLASES, scores)):
            bar_w = int(sc * 200)
            bar_color = (0, 200, 80) if cls == gesto_final else (100, 100, 100)
            cv2.rectangle(frame, (10, 60 + i*16), (10 + bar_w, 74 + i*16), bar_color, -1)
            cv2.putText(frame, f"{cls}: {sc*100:.0f}%", (220, 72 + i*16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
    else:
        cv2.putText(frame, "Sin deteccion  (mano fuera o umbral bajo)", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

    # Indicador heatmap
    if mostrar_heatmap:
        cv2.putText(frame, "[H] heatmap ON", (w - 160, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 80), 1)

    cv2.imshow("Mano Robotica - FOMO", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):
        pausado = not pausado
        historial.clear()
        print(f"[INFO] {'PAUSADO' if pausado else 'REANUDADO'}")
    elif key == ord('h'):
        mostrar_heatmap = not mostrar_heatmap
        print(f"[INFO] Heatmap {'ON' if mostrar_heatmap else 'OFF'}")

# ─────────────────────────────────────────────────────────
#  7. CERRAR
# ─────────────────────────────────────────────────────────
print("\n[INFO] Cerrando... enviando mano abierta final.")
try:
    sock_udp.sendto("1,1,1,1,1".encode(), (ESP32_IP, UDP_PORT))
except Exception:
    pass
time.sleep(0.3)
cap.release()
sock_udp.close()
cv2.destroyAllWindows()
print("[OK] Programa cerrado.")
