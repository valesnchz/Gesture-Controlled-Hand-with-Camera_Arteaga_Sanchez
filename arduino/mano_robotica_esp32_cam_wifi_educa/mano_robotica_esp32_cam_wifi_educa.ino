/*
  ================================================================
   ESP32-CAM - CONEXIÓN A RED ABIERTA "UITEY EDUCA"
  ================================================================
   Este sketch conecta el ESP32-CAM a la red WiFi abierta:
     SSID: "UITEY EDUCA" (Sin contraseña)
   
   Esquema:
     ESP32-CAM ──WiFi "UITEY EDUCA" ──> Servidor MJPEG (Puerto 81)
     ESP32-CAM ──I2C (GPIO 14/15) ──> PCA9685 ──> 5 Servos
   
   Conexiones del PCA9685 al ESP32-CAM:
     PCA9685 SDA  ──>  ESP32-CAM GPIO 14
     PCA9685 SCL  ──>  ESP32-CAM GPIO 15
     PCA9685 VCC  ──>  3.3V del ESP32-CAM
     PCA9685 GND  ──>  GND común
     PCA9685 V+   ──>  5V externo para servos
  ================================================================
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ── CONFIGURACIÓN DE RED WIFI ──────────────────────────────────
// Nombre de la red inalámbrica de tu institución
const char* ssid = "UITEY EDUCA";

// Servidor Web para el Stream de Video (Puerto 81)
WebServer serverStream(81);
// Servidor Web para Comandos de Movimiento (Puerto 80)
WebServer serverControl(80);

// ── PINOUT I2C PARA ESP32-CAM ──────────────────────────────────
#define I2C_SDA 14
#define I2C_SCL 15

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Calibración de servos (ajustada para proteger los servos)
const int ABIERTO[5] = { 150, 150, 150, 150, 150 };  
const int CERRADO[5] = { 450, 500, 500, 420, 420 };

// ── PINOUT CÁMARA AI-THINKER ─────────────────────────────────
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
//  FUNCIONES DE CONTROL DE SERVOS
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
//  MANEJADOR DE COMANDOS HTTP (Puerto 80 /dedos?estado=1,0,1,1,0)
// ================================================================
void handleDedos() {
  if (serverControl.hasArg("estado")) {
    String estadoStr = serverControl.arg("estado");
    estadoStr.trim();
    
    // Esperamos formato "1,0,1,1,0" (mínimo 9 caracteres)
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

      Serial.println("[HTTP] Servos movidos a: " + estadoStr);
      serverControl.send(200, "text/plain", "OK: Servos movidos");
      return;
    }
  }
  serverControl.send(400, "text/plain", "Falta estado o formato incorrecto");
}

// ================================================================
//  MANEJADOR DE VIDEO STREAM (Puerto 81 /stream)
// ================================================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

void handleStream() {
  WiFiClient client = serverStream.client();
  
  // Cabeceras HTTP para streaming MJPEG (compatible con navegadores)
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Content-Type: ");
  client.print(_STREAM_CONTENT_TYPE);
  client.print("\r\n\r\n");

  while (client.connected()) {
    camera_fb_t * fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[STREAM] Error capturando imagen");
      break;
    }

    client.print(_STREAM_BOUNDARY);
    
    char buf[64];
    int len = sprintf(buf, _STREAM_PART, fb->len);
    client.write(buf, len);
    
    client.write(fb->buf, fb->len);
    client.print("\r\n");

    esp_camera_fb_return(fb);
    delay(30); // Limita a ~25 FPS para estabilidad en redes escolares
  }
  Serial.println("[STREAM] Cliente desconectado.");
}

// Tarea del Stream en Core 0
void TaskStream(void *pvParameters) {
  for (;;) {
    serverStream.handleClient();
    delay(2);
  }
}

// ================================================================
//  SETUP
// ================================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== INICIANDO MANO ROBOTICA EN RED 'UITEY EDUCA' ===");

  // 1. Inicializar I2C para PCA9685
  Wire.begin(I2C_SDA, I2C_SCL);
  pca.begin();
  pca.setPWMFreq(50);
  
  // Posición inicial: mano abierta
  for (int i = 0; i < 5; i++) {
    moverServo(i, ABIERTO[i]);
    delay(50);
  }
  Serial.println("[OK] Servos en posicion inicial abierta.");

  // 2. Configurar Cámara AI-Thinker
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

  config.frame_size = FRAMESIZE_QVGA; // 320x240 ideal para streaming y redes escolares
  config.jpeg_quality = 12;
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Error al iniciar camara: 0x%x\n", err);
    return;
  }
  
  sensor_t * s = esp_camera_sensor_get();
  s->set_vflip(s, 0);   
  s->set_hmirror(s, 0); 
  Serial.println("[OK] Camara lista.");

  // 3. Crear punto de acceso propio "CamaraESP32"
  // NOTA: La red UITEY EDUCA tiene aislamiento de clientes, por eso usamos
  //       modo AP (Access Point) directamente — la PC se conecta a la ESP32
  Serial.println("[WIFI] Iniciando modo Access Point...");
  WiFi.softAP("CamaraESP32", ""); // Sin contraseña
  Serial.println("[WIFI] ¡Red 'CamaraESP32' creada exitosamente!");
  Serial.print("[WIFI] Conecta tu PC a 'CamaraESP32' y abre: http://");
  Serial.print(WiFi.softAPIP());
  Serial.println(":81/stream");


  // 4. Iniciar servidores
  serverControl.on("/dedos", handleDedos);
  serverControl.begin();
  Serial.println("[OK] Servidor de comandos en puerto 80.");

  serverStream.on("/stream", handleStream);
  serverStream.begin();
  Serial.println("[OK] Servidor de video en puerto 81.");

  // 5. Iniciar Tarea Stream en Core 0 para que no bloquee comandos
  xTaskCreatePinnedToCore(
    TaskStream,      
    "TaskStream",    
    4096,            
    NULL,            
    1,               
    NULL,            
    0                
  );
}

void loop() {
  serverControl.handleClient(); // Procesa comandos de movimiento en puerto 80 de forma fluida
  delay(5);
}
