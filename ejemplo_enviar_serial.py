import serial
import time
import sys

def conectar_arduino(puerto_com, baud_rate=9600):
    """
    Establece la conexión serial con el Arduino/ESP32.
    Retorna el objeto serial si tiene éxito, o None si falla.
    """
    try:
        print(f"[CONEXIÓN] Intentando conectar a {puerto_com} a {baud_rate} baudios...")
        # Abrimos el puerto serial. Se incluye un timeout de 1 segundo.
        arduino = serial.Serial(port=puerto_com, baudrate=baud_rate, timeout=1)
        
        # Arduino/ESP32 se reinicia al abrir la conexión serial, 
        # esperamos 2 segundos a que se inicialice completamente.
        time.sleep(2)
        print(f"[OK] Conectado exitosamente en {puerto_com}")
        return arduino
    except Exception as e:
        print(f"[ERROR] No se pudo abrir el puerto serial en {puerto_com}.")
        print(f"Detalle del error: {e}")
        return None

def enviar_resultado_clasificacion(conexion_serial, resultado):
    """
    Envía el resultado de la clasificación al Arduino/ESP32.
    Añade un salto de línea '\\n' al final para que el Arduino sepa dónde termina el mensaje.
    """
    if conexion_serial and conexion_serial.is_open:
        try:
            # Aseguramos que el resultado sea un string y agregamos el salto de línea
            mensaje = f"{resultado}\n"
            
            # Codificamos a UTF-8 y enviamos los bytes por el puerto serial
            conexion_serial.write(mensaje.encode('utf-8'))
            
            print(f"[ENVIO] Enviado: '{resultado}'")
            
            # Opcional: Leer confirmación del Arduino (si el Arduino responde algo)
            time.sleep(0.05)
            if conexion_serial.in_waiting > 0:
                respuesta = conexion_serial.readline().decode('utf-8').strip()
                print(f"[ARDUINO] Responde: '{respuesta}'")
                
        except Exception as e:
            print(f"[ERROR] Falla al enviar datos: {e}")
    else:
        print(f"[SIMULACIÓN] Puerto serial no disponible. Clasificación '{resultado}' no enviada.")

if __name__ == "__main__":
    # --- CONFIGURACIÓN ---
    # Cambia esto al puerto COM de tu ESP32/Arduino (ejemplo: 'COM7', 'COM4')
    PUERTO = "COM7"
    BAUDIOS = 9600

    print("=========================================================")
    # 1. Intentar conectar con el Arduino
    esp32 = conectar_arduino(PUERTO, BAUDIOS)
    print("=========================================================")

    # 2. Simulación de envío de clasificaciones
    # Aquí puedes simular el envío de diferentes gestos detectados por tu modelo.
    # El Arduino recibirá estos strings y actuará en consecuencia.
    gestos_clasificados = [
        "MANO_ABIERTA",
        "PUNO",
        "LIKE",
        "ROCK",
        "NUMERO_2",
        "MANO_ABIERTA"
    ]

    try:
        print("\n[INFO] Iniciando simulación de envío de clasificaciones.")
        print("[INFO] Presiona Ctrl+C en la consola para detener.\n")
        
        for gesto in gestos_clasificados:
            print("-" * 50)
            print(f"[PROCESO] Clasificador detectó: {gesto}")
            
            # Enviamos el resultado
            enviar_resultado_clasificacion(esp32, gesto)
            
            # Esperamos 3 segundos antes del siguiente envío para ver los movimientos/LEDs
            time.sleep(3)
            
    except KeyboardInterrupt:
        print("\n[INFO] Simulación detenida por el usuario.")
    
    finally:
        # 3. Cerramos el puerto al terminar
        if esp32 and esp32.is_open:
            # Enviamos un estado por defecto/seguro antes de salir
            enviar_resultado_clasificacion(esp32, "MANO_ABIERTA")
            esp32.close()
            print("[OK] Conexión serial cerrada correctamente.")
        print("[OK] Programa terminado.")
