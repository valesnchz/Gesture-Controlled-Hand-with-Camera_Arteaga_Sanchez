import serial
import time

# =================================================================
#  DICCIONARIO DE MAPEO DE GESTOS A ESTADOS DE DEDOS
# =================================================================
# Tu Arduino ya tiene el código cargado y espera recibir un string
# en formato "Pulgar,Indice,Medio,Anular,Menique" (ej. "1,0,1,1,0\n").
#
# Aquí definimos qué significa cada gesto clasificado por tu modelo:
MAPA_GESTOS = {
    # Gesto          : "Pulgar,Indice,Medio,Anular,Menique"
    "MANO_ABIERTA"   : "1,1,1,1,1",  # Todos los dedos extendidos
    "PUNO"           : "0,0,0,0,0",  # Todos los dedos doblados
    "LIKE"           : "1,0,0,0,0",  # Solo pulgar abierto
    "ROCK"           : "0,1,0,0,1",  # Índice y meñique abiertos
    "AMOR_Y_PAZ"     : "0,1,1,0,0",  # Índice y medio abiertos (Número 2)
    "NUMERO_1"       : "0,1,0,0,0",  # Solo índice abierto
    "NUMERO_3"       : "0,1,1,1,0",  # Índice, medio y anular abiertos
    "NUMERO_4"       : "0,1,1,1,1",  # Todos menos el pulgar
}

def conectar_arduino(puerto_com, baud_rate=9600):
    """
    Establece la conexión serial con tu ESP32/Arduino.
    """
    try:
        print(f"[CONEXIÓN] Conectando a {puerto_com} a {baud_rate} baudios...")
        arduino = serial.Serial(port=puerto_com, baudrate=baud_rate, timeout=1)
        time.sleep(2)  # Espera para que el Arduino se inicialice
        print("[OK] Conectado exitosamente.")
        return arduino
    except Exception as e:
        print(f"[ERROR] No se pudo abrir el puerto {puerto_com}: {e}")
        return None

def enviar_gesto_clasificado(conexion_serial, gesto_detectado):
    """
    Traduce el nombre del gesto (clasificación) al formato
    de dedos "1,0,1,1,0" y lo envía al Arduino.
    """
    # 1. Buscamos el gesto en nuestro diccionario de mapeo
    if gesto_detectado in MAPA_GESTOS:
        dedos_string = MAPA_GESTOS[gesto_detectado]
        print(f"[MAPEO] Gesto '{gesto_detectado}' traducido a -> '{dedos_string}'")
    else:
        # Si el gesto no está registrado, abrimos la mano por seguridad
        dedos_string = "1,1,1,1,1"
        print(f"[ADVERTENCIA] Gesto '{gesto_detectado}' no reconocido. Enviando estado seguro: '{dedos_string}'")

    # 2. Enviamos el comando serial al Arduino
    if conexion_serial and conexion_serial.is_open:
        try:
            # Agregamos el salto de línea obligatorio '\n'
            mensaje = f"{dedos_string}\n"
            conexion_serial.write(mensaje.encode('utf-8'))
            print(f"[SERIAL] Enviado a Arduino: '{dedos_string}'")
            
            # Esperamos brevemente y leemos la confirmación (ACK) que envía tu Arduino
            time.sleep(0.05)
            if conexion_serial.in_waiting > 0:
                respuesta = conexion_serial.readline().decode('utf-8').strip()
                print(f"[ARDUINO] Confirmación: '{respuesta}'")
        except Exception as e:
            print(f"[ERROR] No se pudo enviar por serial: {e}")
    else:
        print(f"[SIMULACIÓN] No conectado. Se hubiese enviado: '{dedos_string}'")

if __name__ == "__main__":
    # --- CONFIGURACIÓN ---
    PUERTO = "COM7"  # <- Cambia esto al puerto COM de tu ESP32/Arduino
    BAUDIOS = 9600

    print("=========================================================")
    esp32 = conectar_arduino(PUERTO, BAUDIOS)
    print("=========================================================")

    # Simulación de tu clasificador en Python detectando gestos
    gestos_simulados = [
        "MANO_ABIERTA",
        "PUNO",
        "LIKE",
        "ROCK",
        "AMOR_Y_PAZ",
        "NUMERO_1",
        "MANO_ABIERTA"
    ]

    try:
        for gesto in gestos_simulados:
            print("-" * 50)
            print(f"[CLASIFICACIÓN] El modelo predijo: {gesto}")
            
            # Enviamos el gesto mapeado al Arduino con el código ya cargado
            enviar_gesto_clasificado(esp32, gesto)
            
            # Espera 3 segundos entre gestos para ver el movimiento
            time.sleep(3)

    except KeyboardInterrupt:
        print("\n[INFO] Detenido por el usuario.")
    finally:
        if esp32 and esp32.is_open:
            enviar_gesto_clasificado(esp32, "MANO_ABIERTA")
            esp32.close()
            print("[OK] Conexión serial cerrada.")
