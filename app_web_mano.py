import cv2
import time
import os
import urllib.request
import threading
import numpy as np
from flask import Flask, render_template_string, Response, request, jsonify

app = Flask(__name__)

# --- VARIABLES DE CONFIGURACIÓN GLOBAL ---
ESP32_IP = "172.23.208.178"  # IP por defecto, el usuario la puede cambiar desde la web
ultimo_estado_mano = [1, 1, 1, 1, 1]  # Estado actual de los 5 dedos
ultimo_gesto_detectado = "Esperando Captura..."
hilo_stream = None
lock_frame = threading.Lock()
frame_actual = None

# --- CARGAR EL MODELO CUSTOM DE TFLITE CON OPENCV DNN ---
MODELO_TFLITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelo_mano.tflite")

if not os.path.exists(MODELO_TFLITE):
    print(f"[ERROR CRÍTICO] No se encontró el archivo '{MODELO_TFLITE}' en el directorio.")
    print("Asegúrate de haber descargado y renombrado el archivo a 'modelo_mano.tflite'.")
else:
    print(f"[OK] Cargando modelo custom '{MODELO_TFLITE}' con OpenCV DNN...")
    try:
        net = cv2.dnn.readNet(MODELO_TFLITE)
        print("[ÉXITO] Modelo de IA custom cargado exitosamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo cargar el modelo TFLite con OpenCV: {e}")

# --- HILO DE CAPTURA DEL VIDEO STREAM DESDE EL ESP32-CAM ---
def hilo_captura_video():
    global frame_actual, ESP32_IP
    ultimo_ip = ""
    cap = None
    
    while True:
        # Si el IP cambia, reconectamos
        if ESP32_IP != ultimo_ip:
            if cap:
                cap.release()
            url = f"http://{ESP32_IP}:81/stream"
            print(f"[CAMARA] Conectando al flujo MJPEG en: {url}")
            cap = cv2.VideoCapture(url)
            ultimo_ip = ESP32_IP
            
        if cap and cap.isOpened():
            success, frame = cap.read()
            if success:
                # Espejo e información
                frame = cv2.flip(frame, 1)
                with lock_frame:
                    frame_actual = frame.copy()
            else:
                time.sleep(0.5)
        else:
            time.sleep(0.5)

# Iniciar hilo de captura en segundo plano
threading.Thread(target=hilo_captura_video, daemon=True).start()

# --- ENVIAR COMANDOS AL ESP32-CAM ---
def enviar_estado_a_esp32(estado_lista):
    global ESP32_IP
    estado_str = ",".join(map(str, estado_lista))
    url = f"http://{ESP32_IP}:80/dedos?estado={estado_str}"
    
    def send_http():
        try:
            with urllib.request.urlopen(url, timeout=0.8) as response:
                response.read()
                print(f"[WIFI] Comando '{estado_str}' enviado exitosamente a {ESP32_IP}")
        except Exception as e:
            # Silencioso si la mano no está conectada físicamente (solo cámara)
            pass
            
    threading.Thread(target=send_http, daemon=True).start()

# --- WEB SERVER ROUTES ---
@app.route('/')
def index():
    return render_template_string(HTML_INTERFAZ, ip_actual=ESP32_IP)

@app.route('/set_ip', methods=['POST'])
def set_ip():
    global ESP32_IP
    data = request.json
    nueva_ip = data.get('ip', '').strip()
    if nueva_ip:
        ESP32_IP = nueva_ip
        print(f"[IP] Servidor configurado con IP del ESP32-CAM: {ESP32_IP}")
        return jsonify({"success": True, "ip": ESP32_IP})
    return jsonify({"success": False})

@app.route('/clasificar', methods=['POST'])
def clasificar():
    global frame_actual, ultimo_estado_mano, ultimo_gesto_detectado
    
    if not os.path.exists(MODELO_TFLITE):
        return jsonify({"success": False, "error": "El archivo 'modelo_mano.tflite' no está en la carpeta."})
        
    with lock_frame:
        if frame_actual is None:
            return jsonify({"success": False, "error": "No hay señal de la cámara de la ESP32-CAM. Revisa la IP y la conexión."})
        img = frame_actual.copy()
        
    try:
        # 1. Redimensionar el cuadro capturado a 96x96 como requiere tu modelo
        img_96 = cv2.resize(img, (96, 96))
        
        # 2. Crear un blob para alimentar la red neuronal. 
        # Scalefactor = 1.0/255.0 (escala a [0, 1.0]), SwapRB = True (pasa BGR de OpenCV a RGB del modelo)
        blob = cv2.dnn.blobFromImage(img_96, scalefactor=1.0/255.0, size=(96, 96), mean=(0,0,0), swapRB=True, crop=False)
        
        net.setInput(blob)
        output = net.forward() # shape: (1, 4, 12, 12)
        
        grid = output[0] # shape: (4, 12, 12)
        
        # Extraer el valor máximo de confianza para cada una de las 4 clases en la cuadrícula de 12x12
        # Clases por orden alfabético en Edge Impulse: 0 = close, 1 = fondo, 2 = index, 3 = open
        conf_close = float(np.max(grid[0, :, :]))
        conf_fondo = float(np.max(grid[1, :, :]))
        conf_index = float(np.max(grid[2, :, :]))
        conf_open  = float(np.max(grid[3, :, :]))
        
        # Convertir a porcentajes limpios para mostrar en la interfaz web
        confianzas = {
            "close": round(conf_close * 100, 1),
            "fondo": round(conf_fondo * 100, 1),
            "index": round(conf_index * 100, 1),
            "open":  round(conf_open * 100, 1)
        }
        
        # Diccionario excluyendo fondo para encontrar el gesto más fuerte
        gestos_validos = {
            "close": conf_close,
            "index": conf_index,
            "open":  conf_open
        }
        
        ganador_gesto = max(gestos_validos, key=gestos_validos.get)
        confianza_ganador = gestos_validos[ganador_gesto]
        
        # Lógica de Umbral para decidir la clasificación
        # Si la confianza del gesto ganador es superior a 0.55 y le gana al fondo en confianza
        if confianza_ganador > 0.55 and confianza_ganador > conf_fondo:
            clase_detectada = ganador_gesto
            conf_pantalla = confianza_ganador
        else:
            clase_detectada = "fondo"
            conf_pantalla = conf_fondo
            
        # Mapear la clase ganadora al estado físico de los 5 dedos (servos)
        if clase_detectada == "open":
            ultimo_estado_mano = [1, 1, 1, 1, 1]
            ultimo_gesto_detectado = f"MANO ABIERTA ✋ ({round(conf_pantalla * 100, 1)}%)"
            enviar_estado_a_esp32(ultimo_estado_mano)
            es_fondo = False
        elif clase_detectada == "close":
            ultimo_estado_mano = [0, 0, 0, 0, 0]
            ultimo_gesto_detectado = f"PUÑO CERRADO ✊ ({round(conf_pantalla * 100, 1)}%)"
            enviar_estado_a_esp32(ultimo_estado_mano)
            es_fondo = False
        elif clase_detectada == "index":
            ultimo_estado_mano = [0, 1, 0, 0, 0] # Solo dedo índice levantado
            ultimo_gesto_detectado = f"DEDO ÍNDICE ☝️ ({round(conf_pantalla * 100, 1)}%)"
            enviar_estado_a_esp32(ultimo_estado_mano)
            es_fondo = False
        else:
            clase_detectada = "fondo"
            ultimo_gesto_detectado = f"FONDO / SIN MANO 🍃 ({round(conf_pantalla * 100, 1)}%)"
            # Si es fondo, dejamos los dedos en su posición actual o relajados, y no enviamos comando
            es_fondo = True
            
        return jsonify({
            "success": True,
            "dedos": ultimo_estado_mano,
            "gesto": ultimo_gesto_detectado,
            "es_fondo": es_fondo,
            "confianzas": confianzas
        })
        
    except Exception as e:
        print(f"[ERROR INFERENCIA] {e}")
        return jsonify({"success": False, "error": f"Error al procesar con tu modelo custom: {e}"})

# Generador de Video para el streaming local en la interfaz web
def gen_frames():
    global frame_actual
    while True:
        with lock_frame:
            if frame_actual is not None:
                # Dibujamos un recuadro de alineación en el medio del frame como guía
                h, w, _ = frame_actual.shape
                recuadro = frame_actual.copy()
                
                # Coordenadas del recuadro
                x1, y1 = int(w * 0.15), int(h * 0.15)
                x2, y2 = int(w * 0.85), int(h * 0.85)
                
                # Dibujar recuadro de alineación
                cv2.rectangle(recuadro, (x1, y1), (x2, y2), (210, 0, 255), 2)
                cv2.putText(recuadro, "ALINEAR MANO AQUI (96x96)", (x1 + 10, y1 + 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (210, 0, 255), 1, cv2.LINE_AA)
                
                # Mezclamos
                cv2.addWeighted(recuadro, 0.4, frame_actual, 0.6, 0, frame_actual)
                
                ret, buffer = cv2.imencode('.jpg', frame_actual)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.04) # ~25 FPS

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- DISEÑO AESTHETIC DE LA INTERFAZ WEB (Premium Glassmorphism) ---
HTML_INTERFAZ = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mano Robótica - Panel Custom IA</title>
    <!-- Fuente premium Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Plus+Jakarta+Sans:wght@300;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-glow: radial-gradient(circle at 50% 50%, #1e133c 0%, #090615 100%);
            --accent: #d200ff;
            --accent-glow: rgba(210, 0, 255, 0.4);
            --cyan: #00ffd2;
            --glass: rgba(255, 255, 255, 0.04);
            --border: rgba(255, 255, 255, 0.08);
            --card-radius: 24px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Plus Jakarta Sans', sans-serif;
            -webkit-font-smoothing: antialiased;
        }

        body {
            background: var(--bg-glow);
            color: #ffffff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: hidden;
            padding: 2rem 1rem;
        }

        header {
            text-align: center;
            margin-bottom: 2rem;
            animation: fadeInDown 0.8s ease;
        }

        h1 {
            font-family: 'Outfit', sans-serif;
            font-weight: 800;
            font-size: 2.8rem;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #ffffff 40%, var(--cyan) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 4px 20px rgba(0,255,210,0.15);
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: rgba(255, 255, 255, 0.6);
            font-size: 1.05rem;
            font-weight: 300;
        }

        /* Contenedor principal */
        .container {
            display: grid;
            grid-template-columns: 1.2fr 0.8fr;
            gap: 2.5rem;
            max-width: 1200px;
            width: 100%;
            animation: scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @media (max-width: 900px) {
            .container {
                grid-template-columns: 1fr;
            }
        }

        /* Tarjeta de Cámara */
        .camera-card {
            background: var(--glass);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 1.8rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
            position: relative;
            overflow: hidden;
        }

        .camera-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--accent), var(--cyan));
        }

        .video-box {
            width: 100%;
            aspect-ratio: 4/3;
            background: #000;
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1);
            position: relative;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
        }

        .video-feed {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        /* Configuración IP */
        .ip-setup {
            width: 100%;
            display: flex;
            gap: 10px;
            margin-top: 1.2rem;
        }

        .ip-input {
            flex: 1;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.8rem 1.2rem;
            color: #fff;
            font-size: 1rem;
            outline: none;
            transition: all 0.3s;
        }

        .ip-input:focus {
            border-color: var(--cyan);
            box-shadow: 0 0 10px rgba(0, 255, 210, 0.2);
        }

        .btn-ip {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid var(--border);
            color: #fff;
            padding: 0 1.5rem;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }

        .btn-ip:hover {
            background: #fff;
            color: #000;
        }

        /* Tarjeta de Control */
        .control-card {
            background: var(--glass);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 2rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
            min-height: 520px;
        }

        .btn-capture {
            background: linear-gradient(135deg, var(--accent) 0%, #b600ff 100%);
            color: white;
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
            font-size: 1.4rem;
            border: none;
            border-radius: 16px;
            padding: 1.2rem;
            cursor: pointer;
            box-shadow: 0 10px 25px var(--accent-glow);
            transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            width: 100%;
            margin-bottom: 1.5rem;
            position: relative;
            overflow: hidden;
        }

        .btn-capture:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 30px rgba(210, 0, 255, 0.6);
        }

        .btn-capture:active {
            transform: translateY(1px);
        }

        /* Indicador de Gesto */
        .gesture-box {
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
            margin-bottom: 1.5rem;
        }

        .gesture-label {
            font-size: 0.9rem;
            color: rgba(255,255,255,0.4);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 0.5rem;
        }

        .gesture-result {
            font-family: 'Outfit', sans-serif;
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--cyan);
            text-shadow: 0 0 15px rgba(0, 255, 210, 0.4);
        }

        /* Barras de métricas IA */
        .metrics-panel {
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.2rem;
            margin-bottom: 1.5rem;
        }

        .metric-row {
            margin-bottom: 10px;
        }

        .metric-row:last-child {
            margin-bottom: 0;
        }

        .metric-info {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            margin-bottom: 4px;
            font-weight: 500;
        }

        .bar-container {
            width: 100%;
            height: 6px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 3px;
            overflow: hidden;
        }

        .bar-fill {
            height: 100%;
            width: 0%;
            transition: width 0.4s cubic-bezier(0.1, 0.8, 0.3, 1);
        }

        /* Panel de Dedos */
        .fingers-panel {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .finger-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.6rem 1.2rem;
            transition: all 0.3s;
        }

        .finger-row.active {
            background: rgba(0, 255, 210, 0.03);
            border-color: rgba(0, 255, 210, 0.2);
        }

        .finger-name {
            font-weight: 600;
            font-size: 0.95rem;
        }

        .finger-status {
            font-size: 0.85rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            text-transform: uppercase;
        }

        .status-open {
            background: rgba(0, 255, 210, 0.15);
            color: var(--cyan);
            box-shadow: 0 0 10px rgba(0, 255, 210, 0.1);
        }

        .status-closed {
            background: rgba(210, 0, 255, 0.15);
            color: #ff52f3;
        }

        /* Mensaje flotante */
        .toast {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: rgba(9, 6, 21, 0.9);
            border: 1px solid rgba(255,255,255,0.1);
            border-left: 4px solid var(--cyan);
            padding: 1rem 1.5rem;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        /* Animaciones */
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes scaleIn {
            from { opacity: 0; transform: scale(0.95); }
            to { opacity: 1; transform: scale(1); }
        }
    </style>
</head>
<body>

    <header>
        <h1>MANO ROBÓTICA - PANEL IA CUSTOM</h1>
        <p class="subtitle">Clasificación por WiFi (Modelo Custom Edge Impulse: tflite float32)</p>
    </header>

    <div class="container">
        
        <!-- COLUMNA IZQUIERDA: CÁMARA EN VIVO -->
        <div class="camera-card">
            <div class="video-box">
                <img id="videoFeed" class="video-feed" src="{{ url_for('video_feed') }}" alt="Transmisión ESP32-CAM">
            </div>
            
            <!-- CONFIGURAR LA IP DE LA ESP32-CAM -->
            <div class="ip-setup">
                <input type="text" id="ipInput" class="ip-input" placeholder="Dirección IP de la ESP32-CAM" value="{{ ip_actual }}">
                <button onclick="actualizarIP()" class="btn-ip">Guardar IP</button>
            </div>
        </div>

        <!-- COLUMNA DERECHA: CONTROLES E IA -->
        <div class="control-card">
            <div>
                <!-- BOTÓN PRINCIPAL DE DISPARO -->
                <button onclick="tomarFotoYClasificar()" id="btnCapture" class="btn-capture">
                    CAPTURAR Y CLASIFICAR
                </button>

                <!-- RESULTADO DEL GESTO -->
                <div class="gesture-box">
                    <div class="gesture-label">Gesto Detectado</div>
                    <div id="gestureResult" class="gesture-result">Esperando Captura...</div>
                </div>

                <!-- BARRAS DE CONFIANZA IA -->
                <div class="metrics-panel">
                    <div class="gesture-label" style="font-size: 0.75rem; margin-bottom: 0.8rem;">Confianza de Clases IA</div>
                    
                    <div class="metric-row">
                        <div class="metric-info">
                            <span>✋ Mano Abierta</span>
                            <span id="bar_open_val">0%</span>
                        </div>
                        <div class="bar-container">
                            <div id="bar_open" class="bar-fill" style="background: var(--cyan);"></div>
                        </div>
                    </div>

                    <div class="metric-row">
                        <div class="metric-info">
                            <span>✊ Puño Cerrado</span>
                            <span id="bar_close_val">0%</span>
                        </div>
                        <div class="bar-container">
                            <div id="bar_close" class="bar-fill" style="background: #ff007c;"></div>
                        </div>
                    </div>

                    <div class="metric-row">
                        <div class="metric-info">
                            <span>☝️ Dedo Índice</span>
                            <span id="bar_index_val">0%</span>
                        </div>
                        <div class="bar-container">
                            <div id="bar_index" class="bar-fill" style="background: #b600ff;"></div>
                        </div>
                    </div>

                    <div class="metric-row">
                        <div class="metric-info">
                            <span>🍃 Fondo / Vacío</span>
                            <span id="bar_fondo_val">0%</span>
                        </div>
                        <div class="bar-container">
                            <div id="bar_fondo" class="bar-fill" style="background: rgba(255, 255, 255, 0.4);"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ESTADOS DE CADA DEDO -->
            <div class="fingers-panel">
                <div class="finger-row" id="row_pulgar">
                    <span class="finger-name">👍 Pulgar</span>
                    <span id="status_pulgar" class="finger-status status-open">Abierto</span>
                </div>
                <div class="finger-row" id="row_indice">
                    <span class="finger-name">☝️ Índice</span>
                    <span id="status_indice" class="finger-status status-open">Abierto</span>
                </div>
                <div class="finger-row" id="row_medio">
                    <span class="finger-name">🖕 Medio</span>
                    <span id="status_medio" class="finger-status status-open">Abierto</span>
                </div>
                <div class="finger-row" id="row_anular">
                    <span class="finger-name">💍 Anular</span>
                    <span id="status_anular" class="finger-status status-open">Abierto</span>
                </div>
                <div class="finger-row" id="row_menique">
                    <span class="finger-name">🤙 Meñique</span>
                    <span id="status_menique" class="finger-status status-open">Abierto</span>
                </div>
            </div>
        </div>

    </div>

    <!-- TOAST NOTIFICACIÓN -->
    <div id="toast" class="toast">
        <span id="toastIcon">ℹ️</span>
        <span id="toastText">Notificación</span>
    </div>

    <script>
        const nombresDedos = ['pulgar', 'indice', 'medio', 'anular', 'menique'];

        function mostrarToast(mensaje, icon="ℹ️") {
            const toast = document.getElementById('toast');
            document.getElementById('toastText').innerText = mensaje;
            document.getElementById('toastIcon').innerText = icon;
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }

        function actualizarIP() {
            const ip = document.getElementById('ipInput').value.trim();
            if (!ip) {
                mostrarToast("Ingresa una IP válida", "⚠️");
                return;
            }
            
            fetch('/set_ip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ip: ip })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    mostrarToast("IP de la Cámara guardada: " + data.ip, "✅");
                    document.getElementById('videoFeed').src = "/video_feed?t=" + new Date().getTime();
                }
            });
        }

        function tomarFotoYClasificar() {
            const btn = document.getElementById('btnCapture');
            btn.disabled = true;
            btn.innerText = "PROCESANDO IA...";
            btn.style.opacity = "0.7";

            fetch('/clasificar', {
                method: 'POST'
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Actualizar el Gesto en el HUD
                    document.getElementById('gestureResult').innerText = data.gesto;
                    
                    // Actualizar barras de confianza en tiempo real
                    if (data.confianzas) {
                        document.getElementById('bar_open').style.width = data.confianzas.open + '%';
                        document.getElementById('bar_open_val').innerText = data.confianzas.open + '%';
                        
                        document.getElementById('bar_close').style.width = data.confianzas.close + '%';
                        document.getElementById('bar_close_val').innerText = data.confianzas.close + '%';
                        
                        document.getElementById('bar_index').style.width = data.confianzas.index + '%';
                        document.getElementById('bar_index_val').innerText = data.confianzas.index + '%';
                        
                        document.getElementById('bar_fondo').style.width = data.confianzas.fondo + '%';
                        document.getElementById('bar_fondo_val').innerText = data.confianzas.fondo + '%';
                    }

                    // Actualizar estado visual de los 5 dedos (servos)
                    data.dedos.forEach((estado, idx) => {
                        const nombre = nombresDedos[idx];
                        const statusSpan = document.getElementById('status_' + nombre);
                        const rowDiv = document.getElementById('row_' + nombre);

                        if (estado === 1) {
                            statusSpan.innerText = "Abierto";
                            statusSpan.className = "finger-status status-open";
                            rowDiv.classList.add('active');
                        } else {
                            statusSpan.innerText = "Cerrado";
                            statusSpan.className = "finger-status status-closed";
                            rowDiv.classList.remove('active');
                        }
                    });

                    if (data.es_fondo) {
                        mostrarToast("Fondo detectado (sin manos). Los servos se mantienen inactivos.", "🍃");
                    } else {
                        mostrarToast("¡Gesto custom detectado y enviado por WiFi!", "🤖");
                    }
                } else {
                    mostrarToast(data.error, "❌");
                }
            })
            .catch(err => {
                mostrarToast("Error en el servidor de control", "💥");
            })
            .finally(() => {
                btn.disabled = false;
                btn.innerText = "CAPTURAR Y CLASIFICAR";
                btn.style.opacity = "1";
            });
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("=========================================================")
    print("    INICIANDO SERVIDOR WEB DE CONTROL INTELIGENTE (IA)   ")
    print("=========================================================")
    print("  1. Carga el firmware WiFi de la ESP32-CAM (puerto 80/81).")
    print("  2. Asegúrate de conectar tu PC a 'UITEY EDUCA'.")
    print("  3. Abre en tu navegador de preferencia:")
    print("         http://localhost:5000")
    print("=========================================================")
    app.run(host='0.0.0.0', port=5000, debug=False)
