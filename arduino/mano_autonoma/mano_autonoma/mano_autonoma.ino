/*
 ================================================================
  MANO ROBOTICA AUTONOMA - ESP32-CAM + Modelo Edge Impulse FOMO
 ================================================================
  Todo corre en el ESP32-CAM, sin Python, sin WiFi.

  ANTES DE COMPILAR:
  1. En Arduino IDE: Sketch → Include Library → Add .ZIP Library
     Selecciona: ei-fomo2-arduino-1.0.8-impulse-#3.zip
  2. Cambia el #include de abajo al nombre correcto de tu librería.
     Para saberlo: abre el .zip y busca el archivo .h en la raíz,
     ese nombre es el que va aquí.

  Conexiones del PCA9685 al ESP32-CAM:
    PCA9685 SDA  →  GPIO 14
    PCA9685 SCL  →  GPIO 15
    PCA9685 VCC  →  3.3V
    PCA9685 GND  →  GND
    PCA9685 V+   →  5V externo (para los servos)
 ================================================================
*/

// ── IMPORTANTE: cambia este nombre por el de tu librería ─────
// Abre el .zip → busca la carpeta → verifica el .h principal
#include <ei_fomo2_inferencing.h>        // ← nombre de tu librería EI
// ─────────────────────────────────────────────────────────────

#include "esp_camera.h"
#include "edge-impulse-sdk/dsp/image/image.hpp"
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ── I2C y PCA9685 ────────────────────────────────────────────
#define I2C_SDA 14
#define I2C_SCL 15
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Calibración de servos
const int ABIERTO[5] = { 150, 150, 150, 150, 150 };
const int CERRADO[5] = { 450, 500, 500, 420, 420 };

// ── Pinout cámara AI-Thinker ──────────────────────────────────
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

// ── Buffer de imagen para la inferencia ──────────────────────
// El modelo FOMO espera EI_CLASSIFIER_INPUT_WIDTH x HEIGHT píxeles RGB
static uint8_t snapshot_buf[EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT * 3];

// ================================================================
//  SERVOS
// ================================================================
void moverServo(int canal, int pulso) {
  pca.setPWM(canal, 0, constrain(pulso, 100, 650));
}

void abrirMano() {
  for (int i = 0; i < 5; i++) moverServo(i, ABIERTO[i]);
}

void cerrarMano() {
  for (int i = 0; i < 5; i++) moverServo(i, CERRADO[i]);
}

// ================================================================
//  CAPTURA DE IMAGEN PARA EL MODELO
// ================================================================
// Esta función la necesita Edge Impulse internamente para leer píxeles
static int ei_camera_get_data(size_t offset, size_t length, float *out_ptr) {
  size_t pixel_ix  = offset * 3;
  size_t pixels_left = length;
  size_t out_ptr_ix = 0;

  while (pixels_left != 0) {
    out_ptr[out_ptr_ix] = (snapshot_buf[pixel_ix]     << 16)
                        + (snapshot_buf[pixel_ix + 1] <<  8)
                        +  snapshot_buf[pixel_ix + 2];
    out_ptr_ix++;
    pixel_ix += 3;
    pixels_left--;
  }
  return 0;
}

bool capturarImagen() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[ERROR] Fallo captura de frame.");
    return false;
  }

  // Convertir el frame JPEG → RGB888 a 96x96
  bool ok = fmt2rgb888(fb->buf, fb->len, PIXFORMAT_JPEG, snapshot_buf);
  esp_camera_fb_return(fb);

  if (!ok) {
    Serial.println("[ERROR] Fallo conversion a RGB888.");
    return false;
  }

  // Redimensionar a 96x96 si el frame es mas grande
  // (ei::image::processing::crop_and_interpolate_rgb888 hace resize in-place)
  ei::image::processing::crop_and_interpolate_rgb888(
    snapshot_buf,
    EI_CLASSIFIER_INPUT_WIDTH,   // ancho real del frame (lo detecta sólo)
    EI_CLASSIFIER_INPUT_HEIGHT,
    snapshot_buf,
    EI_CLASSIFIER_INPUT_WIDTH,   // ancho destino = 96
    EI_CLASSIFIER_INPUT_HEIGHT   // alto destino  = 96
  );

  return true;
}

// ================================================================
//  SETUP
// ================================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== MANO ROBOTICA AUTONOMA ===");

  // 1. PCA9685
  Wire.begin(I2C_SDA, I2C_SCL);
  pca.begin();
  pca.setPWMFreq(50);
  abrirMano();
  Serial.println("[OK] Servos listos (posicion abierta).");

  // 2. Cámara — configurada para captura a 96x96 RGB565
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;    // captura JPEG → convertimos a RGB
  config.frame_size   = FRAMESIZE_96X96;   // tamaño exacto del modelo
  config.jpeg_quality = 10;
  config.fb_count     = 1;                 // 1 buffer es suficiente para inferencia
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Camara no inicio: 0x%x\n", err);
    Serial.println("        Revisa: alimentacion, cable flat, GPIO0.");
    return;
  }

  sensor_t* s = esp_camera_sensor_get();
  s->set_vflip(s, 0);
  s->set_hmirror(s, 0);
  s->set_brightness(s, 1);  // un poco de brillo extra
  Serial.println("[OK] Camara lista en 96x96.");

  Serial.println("[OK] Todo listo. Iniciando inferencia...\n");
}

// ================================================================
//  LOOP - Captura → Inferencia → Servos
// ================================================================
void loop() {
  // 1. Capturar imagen
  if (!capturarImagen()) {
    delay(100);
    return;
  }

  // 2. Preparar señal para Edge Impulse
  ei::signal_t signal;
  signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
  signal.get_data     = &ei_camera_get_data;

  // 3. Correr inferencia
  ei_impulse_result_t result = { 0 };
  EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);

  if (err != EI_IMPULSE_OK) {
    Serial.printf("[ERROR] Inferencia fallida: %d\n", err);
    return;
  }

  // 4. Interpretar resultado FOMO
  // FOMO detecta objetos en un grid. Buscamos cuál clase tiene
  // la mayor confianza máxima en todo el grid.
  float max_open  = 0.0f;
  float max_close = 0.0f;

#if EI_CLASSIFIER_OBJECT_DETECTION == 1
  // Recorrer todas las detecciones del grid
  for (uint32_t i = 0; i < result.bounding_boxes_count; i++) {
    ei_impulse_result_bounding_box_t bb = result.bounding_boxes[i];
    if (bb.value == 0) continue;  // sin deteccion en esta celda

    String label = String(bb.label);
    label.toLowerCase();

    if (label == "open"  && bb.value > max_open)  max_open  = bb.value;
    if (label == "close" && bb.value > max_close) max_close = bb.value;
  }
#endif

  // 5. Decidir gesto y mover servos
  float UMBRAL = 0.5f;  // confianza mínima para actuar (ajusta si es necesario)

  if (max_open > UMBRAL || (max_open == 0 && max_close == 0)) {
    // OPEN o sin deteccion → mano abierta
    abrirMano();
    Serial.printf("[GESTO] OPEN   (conf: %.2f)\n", max_open);
  } else if (max_close > max_open) {
    // CLOSE → mano cerrada
    cerrarMano();
    Serial.printf("[GESTO] CLOSE  (conf: %.2f)\n", max_close);
  } else {
    // OPEN gana
    abrirMano();
    Serial.printf("[GESTO] OPEN   (conf: %.2f)\n", max_open);
  }

  // Pausa breve entre inferencias (ajusta velocidad de respuesta)
  delay(100);
}
