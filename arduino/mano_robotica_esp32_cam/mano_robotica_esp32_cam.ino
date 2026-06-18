/*
 ================================================================
  MANO ROBOTICA - ESP32-CAM + Controlador PCA9685 (WiFi)
 ================================================================
  Esquema de conexion:
  
    ESP32-CAM ──WiFi AP (Red)──> PC (Python con webcam en vivo)
    ESP32-CAM ──I2C (GPIO 14/15)──> PCA9685 ──PWM──> 5 Servos

  Conexion I2C del PCA9685 al ESP32-CAM:
    PCA9685  SDA  ──>  ESP32-CAM GPIO 14  (SDA)  <--- ¡MUY IMPORTANTE!
    PCA9685  SCL  ──>  ESP32-CAM GPIO 15  (SCL)  <--- ¡MUY IMPORTANTE!
    PCA9685  VCC  ──>  3.3V del ESP32-CAM
    PCA9685  GND  ──>  GND comun
    PCA9685  V+   ──>  5V externo (alimentacion de los servos)

  Notas:
    - En el ESP32-CAM, GPIO 21 y 22 estan ocupados por la camara,
      por eso usamos obligatoriamente GPIO 14 y 15 para I2C.
 ================================================================
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <WiFiUdp.h>

// ── CONFIGURACION AP WIFI ─────────────────────────────────────
const char* ssid     = "CamaraESP32";
const char* password = ""; // Red abierta, sin contraseña

// Servidores Web y UDP
WebServer serverStream(81);
WiFiUDP udp;
const int UDP_PORT = 82;

// Flag para saber si la camara inicio correctamente
bool camaraOK = false;

// ── PINOUT I2C PARA ESP32-CAM ──────────────────────────────────
#define I2C_SDA 14
#define I2C_SCL 15

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Calibracion de servos
const int ABIERTO[5] = { 150, 150, 150, 150, 150 };  
const int CERRADO[5] = { 450, 500, 500, 420, 420 }; // Ajustados anular y meñique a 420 para que no sufran

// ── PINOUT CAMARA AI-THINKER ─────────────────────────────────
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ================================================================
//  FUNCIONES DE SERVOS
// ================================================================
void moverServo(int canal, int valorPulso) {
  valorPulso = constrain(valorPulso, 100, 650);
  pca.setPWM(canal, 0, valorPulso);
}

void actualizarDedo(int canal, int estado) {
  int pulso = (estado == 1) ? ABIERTO[canal] : CERRADO[canal];
  moverServo(canal, pulso);
}

// ================================================================
//  PROCESAMIENTO DE COMANDOS UDP (Puerto 82)
// ================================================================
void procesarComandoUDP() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char packetBuffer[64];
    int len = udp.read(packetBuffer, 63);
    if (len > 0) {
      packetBuffer[len] = '\0';
      String estadoStr = String(packetBuffer);
      estadoStr.trim();
      
      if (estadoStr.length() >= 9) {
        int pulgar  = estadoStr.charAt(0) - '0';
        int indice  = estadoStr.charAt(2) - '0';
        int medio   = estadoStr.charAt(4) - '0';
        int anular  = estadoStr.charAt(6) - '0';
        int menique = estadoStr.charAt(8) - '0';

        actualizarDedo(0, pulgar);
        actualizarDedo(1, indice);
        actualizarDedo(2, medio);
        actualizarDedo(3, anular);
        actualizarDedo(4, menique);

        Serial.println("UDP Comando: " + estadoStr);
      }
    }
  }
}

// ================================================================
//  MANEJADOR DE VIDEO STREAM (Puerto 81)
// ================================================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

void handleStream() {
  WiFiClient client = serverStream.client();

  if (!camaraOK) {
    client.print("HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/plain\r\n\r\nCamara no inicializada.");
    Serial.println("[WARN] Cliente pidio stream pero la camara no esta lista.");
    return;
  }
  
  // Cabeceras HTTP para streaming MJPEG
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Content-Type: ");
  client.print(_STREAM_CONTENT_TYPE);
  client.print("\r\n\r\n");

  while (client.connected()) {
    camera_fb_t * fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[ERR] Error capturando imagen");
      break;
    }

    client.print(_STREAM_BOUNDARY);
    
    char buf[64];
    int len = sprintf(buf, _STREAM_PART, fb->len);
    client.write(buf, len);
    
    client.write(fb->buf, fb->len);
    client.print("\r\n");

    esp_camera_fb_return(fb);
    delay(20); // Limita aproximadamente a 25-30 FPS para estabilidad
  }
  Serial.println("Cliente stream desconectado.");
}

// ================================================================
// TAREA EN SEGUNDO PLANO (Core 0) PARA EL STREAM DE VIDEO
// ================================================================
void TaskStream(void *pvParameters) {
  for (;;) {
    serverStream.handleClient();
    delay(2); // Cede tiempo al CPU para estabilidad del sistema
  }
}

// ================================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== INICIANDO MANO ROBOTICA - DIAGNOSTICO ===");
  
  // 1. Inicializar I2C para PCA9685 en pines 14 (SDA) y 15 (SCL)
  Wire.begin(I2C_SDA, I2C_SCL);
  
  // Escaneo rápido del bus I2C para verificar comunicación con el PCA9685
  Serial.println("Escaneando bus I2C...");
  Wire.beginTransmission(0x40);
  byte error = Wire.endTransmission();
  if (error == 0) {
    Serial.println("[OK] ¡PCA9685 detectado exitosamente en la direccion I2C 0x40!");
  } else {
    Serial.println("[ERROR] No se pudo comunicar con el PCA9685 en la direccion 0x40.");
    Serial.println("        1. Revisa si SDA (GPIO 14) y SCL (GPIO 15) estan cruzados o sueltos.");
    Serial.println("        2. Asegurate de que el PCA9685 tenga alimentacion logica VCC (3.3V) y GND conectadas.");
  }
  
  pca.begin();
  pca.setPWMFreq(50);
  
  // Posicion inicial: todos abiertos
  for (int i = 0; i < 5; i++) {
    moverServo(i, ABIERTO[i]);
    delay(50);
  }
  Serial.println("PCA9685 inicializado. Intentando mover a posicion inicial...");

  // 2. Configurar Camara
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Resolucion balanceada para transmision rapida
  config.frame_size = FRAMESIZE_QVGA; // 320x240
  config.jpeg_quality = 12;
  config.fb_count = 2;

  // Iniciar la camara
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Camara no pudo iniciar: 0x%x\n", err);
    Serial.println("        Revisa: 1) Alimentacion 5V/500mA+  2) Cable flat de la camara  3) GPIO0 en LOW durante reset");
    camaraOK = false; // Continua sin camara para que el WiFi y los servos funcionen
  } else {
    camaraOK = true;
    sensor_t * s = esp_camera_sensor_get();
    s->set_vflip(s, 0);   // Imagen al derecho
    s->set_hmirror(s, 0);  // Sin espejo
    Serial.println("[OK] Camara lista.");
  }

  // 3. Crear Red WiFi AP
  Serial.print("Iniciando AP WiFi: ");
  Serial.println(ssid);
  WiFi.softAP(ssid, password);

  IPAddress IP = WiFi.softAPIP();
  Serial.print("IP del ESP32-CAM: ");
  Serial.println(IP);

  // 4. Rutas Web y UDP
  udp.begin(UDP_PORT);
  Serial.print("Servidor UDP de comandos iniciado en puerto ");
  Serial.println(UDP_PORT);

  serverStream.on("/stream", handleStream);
  serverStream.begin();
  Serial.println("Servidor de video en puerto 81 listo.");

  // 5. Iniciar la tarea del stream de video en el Core 0 (segundo plano)
  // De esta forma la transmisión de video NUNCA bloqueará los comandos de los servos.
  xTaskCreatePinnedToCore(
    TaskStream,      /* Función de la tarea */
    "TaskStream",    /* Nombre de la tarea */
    4096,            /* Stack size */
    NULL,            /* Parámetro */
    1,               /* Prioridad */
    NULL,            /* Puntero */
    0                /* Pin al Core 0 */
  );
  Serial.println("Tarea de streaming iniciada en Core 0.");
}

void loop() {
  procesarComandoUDP(); // Procesa comandos UDP entrantes en Core 1 de forma ultra rápida
  delay(2);
}
