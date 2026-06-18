import cv2
import numpy as np
import sys

# Intentar importar TFLite
try:
    import tensorflow.lite as tflite
except ImportError:
    try:
        import tflite_runtime.interpreter as tflite
    except ImportError:
        print("ERROR: Necesitas instalar tensorflow.")
        print("Abre tu terminal y escribe: pip install tensorflow")
        sys.exit(1)

# ARCHIVO DEL MODELO
MODELO_PATH = "modelo_nuevo.tflite.lite"

print(f"Cargando modelo '{MODELO_PATH}'...")
try:
    interpreter = tflite.Interpreter(model_path=MODELO_PATH)
    interpreter.allocate_tensors()
except Exception as e:
    print(f"Error al cargar el modelo: {e}")
    sys.exit(1)

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

height = input_details[0]['shape'][1]
width = input_details[0]['shape'][2]

print(f"Modelo cargado. Esperando imagen de tamaño {width}x{height}.")

cap = cv2.VideoCapture(0)
estado_actual = 0  # 0 = abierta, 1 = cerrada

print("Abriendo cámara web... (Presiona 'q' para salir)")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    # 1. PREPROCESAMIENTO (Redimensionar y convertir a RGB)
    img = cv2.resize(frame, (width, height))
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Normalizar si el modelo es float32 (Edge Impulse usa 0.0 a 1.0)
    if input_details[0]['dtype'] == np.float32:
        input_data = np.expand_dims(img_rgb, axis=0).astype(np.float32) / 255.0
    else:
        # Int8
        input_data = np.expand_dims(img_rgb, axis=0).astype(np.int8)
        
    # 2. INFERENCIA
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()
    output_data = interpreter.get_tensor(output_details[0]['index'])[0]
    
    clase_detectada = "Ninguna"
    confianza_maxima = 0.0
    out_shape = output_details[0]['shape']
    
    # Si es FOMO (Object Detection)
    if len(out_shape) == 4:
        num_classes = out_shape[3]
        # Ignorar clase 0 (fondo)
        for c in range(1, num_classes):
            # Buscar el puntaje más alto en la cuadrícula para esta clase
            max_c = np.max(output_data[:,:,c])
            # Si el modelo es int8, hay que de-cuantizar. Asumiremos float32 por ahora (0.0 a 1.0)
            if input_details[0]['dtype'] != np.float32:
                # Ajuste rápido para int8:
                scale, zero_point = output_details[0]['quantization']
                if scale > 0:
                    max_c = (max_c - zero_point) * scale
            
            if max_c > confianza_maxima:
                confianza_maxima = max_c
                # En Edge Impulse, el orden suele ser alfabético: 1=close, 2=open
                clase_detectada = "close" if c == 1 else "open"
                
    # Si es Clasificación de Imágenes
    elif len(out_shape) == 2:
        num_classes = out_shape[1]
        c = np.argmax(output_data)
        confianza_maxima = output_data[c]
        if input_details[0]['dtype'] != np.float32:
             scale, zero_point = output_details[0]['quantization']
             if scale > 0:
                 confianza_maxima = (confianza_maxima - zero_point) * scale
                 
        clase_detectada = "close" if c == 0 else "open"

    # 3. LÓGICA DE MANO ROBÓTICA
    if confianza_maxima > 0.65:
        if clase_detectada == "close" and estado_actual == 0:
            print("========================================")
            print(f"¡CERRANDO LA MANO! (Seguridad: {confianza_maxima:.2f})")
            print("========================================")
            estado_actual = 1
        elif clase_detectada == "open" and estado_actual == 1:
            print("========================================")
            print(f"¡ABRIENDO LA MANO! (Seguridad: {confianza_maxima:.2f})")
            print("========================================")
            estado_actual = 0
            
    # 4. DIBUJAR EN PANTALLA
    # Espejar para que te veas normal
    frame_espejo = cv2.flip(frame, 1)
    
    color = (0, 255, 0) if estado_actual == 0 else (0, 0, 255)
    texto_estado = "ESTADO: ABIERTA" if estado_actual == 0 else "ESTADO: CERRADA"
    
    cv2.putText(frame_espejo, f"Viendo: {clase_detectada} ({confianza_maxima:.2f})", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
    cv2.putText(frame_espejo, texto_estado, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)
    
    cv2.imshow("Prueba del Modelo", frame_espejo)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
        
cap.release()
cv2.destroyAllWindows()
