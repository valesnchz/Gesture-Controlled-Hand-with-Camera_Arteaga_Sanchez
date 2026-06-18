import os

def renombrar_y_probar():
    original = "ei-biomecanica_project_2clases-object-detection-tensorflow-lite-float32-model.6.lite"
    destino = "modelo_mano.tflite"

    # 1. Renombrar el archivo
    if os.path.exists(original):
        if os.path.exists(destino):
            os.remove(destino)
        os.rename(original, destino)
        print(f"[OK] Archivo renombrado exitosamente a '{destino}'")
    elif not os.path.exists(destino):
        print(f"[ERROR] No se encontró el archivo '{original}' ni '{destino}'")
        return

    # 2. Cargar e inspeccionar con TensorFlow o TFLite
    print("\n[INFO] Intentando cargar el modelo para inspeccionar tensores...")
    
    # Intentar importar tflite_runtime o tensorflow
    try:
        import tflite_runtime.interpreter as tflite
        print("[OK] tflite_runtime importado correctamente.")
    except ImportError:
        try:
            import tensorflow.lite as tflite
            print("[OK] tensorflow.lite importado correctamente.")
        except ImportError:
            print("[ERROR] No se pudo importar 'tflite_runtime' ni 'tensorflow'.")
            print("Vamos a intentar instalar tflite-runtime para poder usar tu modelo...")
            return False

    try:
        interpreter = tflite.Interpreter(model_path=destino)
        interpreter.allocate_tensors()

        # Obtener detalles de entrada y salida
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        print("\n" + "="*40)
        print("          DETALLES DEL MODELO TFLITE")
        print("="*40)
        print("PROPIEDADES DE ENTRADA:")
        for idx, details in enumerate(input_details):
            print(f"  Entrada {idx}:")
            print(f"    Nombre: {details['name']}")
            print(f"    Forma (Shape): {details['shape']}")
            print(f"    Tipo de dato: {details['dtype']}")
            print(f"    Cuantización: {details['quantization']}")
            
        print("\nPROPIEDADES DE SALIDA:")
        for idx, details in enumerate(output_details):
            print(f"  Salida {idx}:")
            print(f"    Nombre: {details['name']}")
            print(f"    Forma (Shape): {details['shape']}")
            print(f"    Tipo de dato: {details['dtype']}")
            print(f"    Cuantización: {details['quantization']}")
        print("="*40 + "\n")

    except Exception as e:
        print(f"[ERROR] No se pudo analizar el modelo: {e}")

if __name__ == "__main__":
    renombrar_y_probar()
