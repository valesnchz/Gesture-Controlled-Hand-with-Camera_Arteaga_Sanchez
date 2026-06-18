import cv2
import numpy as np

def probar_inferencia():
    modelo = "modelo_mano.tflite"
    print(f"[INFO] Cargando modelo '{modelo}' con OpenCV DNN...")
    try:
        net = cv2.dnn.readNet(modelo)
        print("[OK] Modelo cargado.")

        # Obtener los nombres de los tensores de salida
        out_names = net.getUnconnectedOutLayersNames()
        print(f"[INFO] Capas de salida detectadas: {out_names}")

        # Crear una imagen de prueba dummy de 96x96 RGB (llena de ceros / color negro)
        # El modelo de Edge Impulse suele esperar valores flotantes entre 0 y 1 o entre -1 y 1.
        # Crearemos una imagen flotante y la convertiremos en un blob para OpenCV.
        dummy_img = np.zeros((96, 96, 3), dtype=np.float32)
        
        # Crear un blob:
        # cv2.dnn.blobFromImage toma la imagen, escala (1/255.0 para normalizar de [0,255] a [0,1]),
        # tamaño (96, 96), y swapRB=True porque OpenCV lee BGR y Edge Impulse fue entrenado en RGB.
        blob = cv2.dnn.blobFromImage(dummy_img, scalefactor=1.0, size=(96, 96), mean=(0,0,0), swapRB=True, crop=False)
        print(f"[INFO] Blob de entrada creado con forma (shape): {blob.shape}")

        net.setInput(blob)
        output = net.forward()
        
        print("\n" + "="*40)
        print("      INFERENCIA CON OPENCV DNN - EXITOSA")
        print("="*40)
        print(f"Forma de la predicción de salida (Output Shape): {output.shape}")
        print("Valores de salida (primeros elementos):")
        # Mostrar una pequeña porción del output para ver si es float y sus rangos
        print(output[0, :2, :2, :])
        print("="*40 + "\n")
        return True
    except Exception as e:
        print(f"[ERROR] Error al realizar la inferencia de prueba: {e}")
        return False

if __name__ == "__main__":
    probar_inferencia()
