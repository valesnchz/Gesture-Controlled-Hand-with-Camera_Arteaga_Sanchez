/*
 ================================================================
  TEST DE MODELO EDGE IMPULSE EN ESP32-CAM (SIN SERVOS)
 ================================================================
  Este código SOLO prueba el modelo cargado en el ESP32-CAM.
  Hace un conteo de 3, 2, 1, toma la foto, corre el modelo
  y muestra el % de precisión (accuracy) de cada gesto detectado.

  RECUERDA: Cambia <ei_fomo2_inferencing.h> por el nombre 
  real de la librería .zip que descargaste de Edge Impulse.
 ================================================================
*/

#include <fomo2_inferencing.h>  // ← ¡Cambia esto al nombre de tu librería!
#include "esp_camera.h"
#include "edge-impulse-sdk/dsp/image/image.hpp"

// ── Pinout cámara AI-Thinker ──────────────────────────────────
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

// Buffer de imagen para el modelo (96x96 RGB)
static uint8_t snapshot_buf[EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT * 3];

// ================================================================
//  CAPTURA DE IMAGEN
// ================================================================
static int ei_camera_get_data(size_t offset, size_t length, float *out_ptr) {
    size_t pixel_ix = offset * 3;
    size_t pixels_left = length;
    size_t out_ptr_ix = 0;

    while (pixels_left != 0) {
        out_ptr[out_ptr_ix] = (snapshot_buf[pixel_ix] << 16) + (snapshot_buf[pixel_ix + 1] << 8) + snapshot_buf[pixel_ix + 2];
        out_ptr_ix++;
        pixel_ix += 3;
        pixels_left--;
    }
    return 0;
}

bool capturar_imagen() {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[ERROR] Fallo al capturar la imagen");
        return false;
    }

    bool converted = fmt2rgb888(fb->buf, fb->len, PIXFORMAT_JPEG, snapshot_buf);
    esp_camera_fb_return(fb);

    if (!converted) {
        Serial.println("[ERROR] Fallo la conversion a RGB888");
        return false;
    }

    // Redimensionar al tamaño que necesita el modelo (ej. 96x96)
    ei::image::processing::crop_and_interpolate_rgb888(
        snapshot_buf,
        EI_CLASSIFIER_INPUT_WIDTH,
        EI_CLASSIFIER_INPUT_HEIGHT,
        snapshot_buf,
        EI_CLASSIFIER_INPUT_WIDTH,
        EI_CLASSIFIER_INPUT_HEIGHT);

    return true;
}

// ================================================================
//  SETUP
// ================================================================
void setup() {
    Serial.begin(115200);
    while (!Serial);
    Serial.println("\n=== TEST DE MODELO EDGE IMPULSE (ESP32-CAM) ===");

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
    config.frame_size = FRAMESIZE_96X96;
    config.jpeg_quality = 10;
    config.fb_count = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[ERROR] Fallo al iniciar camara: 0x%x\n", err);
        return;
    }

    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 0);
    s->set_hmirror(s, 0);

    Serial.println("[OK] Camara lista.");
    Serial.println("Comenzando deteccion en 3 segundos...\n");
    delay(3000);
}

// ================================================================
//  LOOP
// ================================================================
void loop() {
    // Conteo 3, 2, 1
    Serial.println("Tomando foto en...");
    for (int i = 3; i > 0; i--) {
        Serial.printf("%d...\n", i);
        delay(1000);
    }
    Serial.println("¡Capturando!");

    if (!capturar_imagen()) {
        return;
    }

    ei::signal_t signal;
    signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
    signal.get_data = &ei_camera_get_data;

    ei_impulse_result_t result = {0};
    EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);

    if (err != EI_IMPULSE_OK) {
        Serial.printf("[ERROR] Fallo el clasificador (%d)\n", err);
        return;
    }

    Serial.printf("\n=== RESULTADOS DE INFERENCIA (%.2f ms) ===\n", result.timing.classification);
    
#if EI_CLASSIFIER_OBJECT_DETECTION == 1
    // Modelo FOMO (Detección de objetos)
    bool objeto_detectado = false;
    for (uint32_t i = 0; i < result.bounding_boxes_count; i++) {
        ei_impulse_result_bounding_box_t bb = result.bounding_boxes[i];
        if (bb.value == 0) continue;
        
        Serial.printf("  -> %s: %.2f%% (x: %d, y: %d, w: %d, h: %d)\n", 
            bb.label, bb.value * 100.0, bb.x, bb.y, bb.width, bb.height);
        objeto_detectado = true;
    }
    
    if (!objeto_detectado) {
        Serial.println("  -> Ningun gesto detectado (Fondo)");
    }
#else
    // Modelo de Clasificación normal
    for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
        Serial.printf("  -> %s: %.2f%%\n", result.classification[i].label, result.classification[i].value * 100.0);
    }
#endif
    
    Serial.println("==========================================\n");
    delay(2000); // Pausa antes del siguiente ciclo
}
