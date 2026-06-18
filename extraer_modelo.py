import os
import re

def extraer_tflite_de_cpp():
    cpp_filename = "tflite_learn_997823_6_compiled.cpp"
    output_tflite = "modelo_mano.tflite"

    # Buscar el archivo en el directorio actual o en subdirectorios
    cpp_path = None
    for root, dirs, files in os.walk("."):
        if cpp_filename in files:
            cpp_path = os.path.join(root, cpp_filename)
            break

    if not cpp_path:
        print(f"[ERROR] No se encontró el archivo '{cpp_filename}' en el espacio de trabajo.")
        print("Por favor, copia los 3 archivos a la carpeta del proyecto en VS Code.")
        return False

    print(f"[INFO] Archivo encontrado en: {cpp_path}")
    print("[INFO] Extrayendo datos del modelo...")

    try:
        with open(cpp_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Los modelos exportados por Edge Impulse / TensorFlow Lite Micro suelen definir el modelo en un array:
        # const unsigned char g_trained_model_data[] = { ... };
        # o similar. Vamos a buscar un array de bytes en formato hexadecimal.
        
        # Expresión regular para encontrar el bloque del array
        # Busca algo como: unsigned char g_trained_model_data[...] = { ... };
        match = re.search(r"unsigned\s+char\s+(\w+model_data\w*)\s*\[\]\s*=\s*\{([^}]+)\}", content)
        
        if not match:
            # Intento alternativo por si no tiene 'unsigned char' exacto
            match = re.search(r"const\s+uint8_t\s+(\w+model_data\w*)\s*\[\]\s*=\s*\{([^}]+)\}", content)

        if not match:
            # Intento alternativo más genérico para cualquier array de bytes hex con llaves
            match = re.search(r"(?:char|uint8_t|unsigned\s+char)\s+(\w+)\s*\[\]\s*=\s*\{([^}]+)\}", content)

        if not match:
            print("[ERROR] No se pudo encontrar el array de bytes del modelo en el archivo .cpp")
            return False

        array_name = match.group(1)
        hex_data_raw = match.group(2)
        print(f"[OK] Se detectó el array '{array_name}' con datos del modelo.")

        # Extraer todos los valores hexadecimales (ej: 0x1c, 0x00, etc.)
        hex_values = re.findall(r"0x[0-9a-fA-F]+|[0-9]+", hex_data_raw)
        
        if not hex_values:
            print("[ERROR] No se encontraron valores hexadecimales o numéricos dentro del array.")
            return False

        print(f"[INFO] Convirtiendo {len(hex_values)} bytes...")
        
        # Convertir a bytes reales
        byte_data = bytearray()
        for val in hex_values:
            if val.startswith("0x"):
                byte_data.append(int(val, 16))
            else:
                byte_data.append(int(val, 10))

        # Escribir el archivo .tflite
        with open(output_tflite, "wb") as out_f:
            out_f.write(byte_data)

        print(f"[ÉXITO] Archivo del modelo extraído y guardado como '{output_tflite}' ({len(byte_data)} bytes).")
        return True

    except Exception as e:
        print(f"[ERROR] Ocurrió un problema durante la extracción: {e}")
        return False

if __name__ == "__main__":
    extraer_tflite_de_cpp()
