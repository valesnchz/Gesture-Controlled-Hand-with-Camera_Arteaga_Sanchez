import cv2

def probar_opencv_dnn():
    modelo = "modelo_mano.tflite"
    print(f"[INFO] Intentando cargar '{modelo}' con OpenCV DNN...")
    try:
        net = cv2.dnn.readNet(modelo)
        print("[¡ÉXITO!] OpenCV es capaz de cargar tu modelo directamente.")
        print("Esto es genial porque no necesitaremos instalar TensorFlow.")
        return True
    except Exception as e:
        print(f"[ERROR] OpenCV no pudo cargar el modelo directamente: {e}")
        return False

if __name__ == "__main__":
    probar_opencv_dnn()
