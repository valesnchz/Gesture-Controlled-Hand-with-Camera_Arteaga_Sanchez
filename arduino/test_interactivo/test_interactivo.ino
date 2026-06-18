/*
 ================================================================
  TEST INTERACTIVO DEL MODELO + SERVOS (Por Serial)
 ================================================================
  Este código hace exactamente lo de la imagen:
  1. Espera a que escribas algo y des Enter.
  2. Cuenta 3, 2, 1.
  3. Toma la foto y la pasa al modelo.
  4. Te dice qué gesto vio con qué seguridad.
  5. Mueve los servos físicamente.

  ⚠️ RECUERDA CAMBIAR: <ei_fomo2_inferencing.h> por el nombre
  real de tu librería de Edge Impulse.
 ================================================================
*/

#include <ei_fomo2_inferencing.h>  // ← ¡Cambia esto por tu librería!
#include "esp_camera.h"
#include "edge-impulse-sdk/dsp/image/image.hpp"
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ── I2C y PCA9685 ────────────────────────────────────────────
#define I2C_SDA 14
#define I2C_SCL 15
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

const int ABIERTO[5] = { 150, 150, 150, 150, 150 };
const int CERRADO[5] = { 450, 500, 500, 420, 420 };

void moverServo(int canal, int pulso) {
  pca.setPWM(canal, 0, constrain(pulso, 100, 650));
}

void abrirMano() {
  for (int i = 0; i < 5; i++) moverServo(i, ABIERTO[i]);
}

void cerrarMano() {
  for (int i = 0; i < 5; i++) moverServo(i, CERRADO[i]);
}

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

static uint8_t snapshot_buf[EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT * 3];

// ================================================================
//  CAPTURA
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
    if (!fb) return false;
    bool ok = fmt2rgb888(fb->buf, fb->len, PIXFORMAT_JPEG, snapshot_buf);
    esp_camera_fb_return(fb);
    if (!ok) return false;
    ei::image::processing::crop_and_interpolate_rgb888(
        snapshot_buf, EI_CLASSIFIER_INPUT_WIDTH, EI_CLASSIFIER_INPUT_HEIGHT,
        snapshot_buf, EI_CLASSIFIER_INPUT_WIDTH, EI_CLASSIFIER_INPUT_HEIGHT);
    return true;
}

// ================================================================
//  SETUP
// ================================================================
void setup() {
    Serial.begin(115200);
    while (!Serial);

    // Servos
    Wire.begin(I2C_SDA, I2C_SCL);
    pca.begin();
    pca.setPWMFreq(50);
    abrirMano();

    // Camara
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
    config.frame_size = FRAMESIZE_96X96; // Tamaño para Edge Impulse
    config.jpeg_quality = 10;
    config.fb_count = 1;

    esp_camera_init(&config);
    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 0);
    s->set_hmirror(s, 0);

    Serial.println("\nLISTO. Escribe una letra y dale Enter para tomar una foto.");
}

// ================================================================
//  LOOP INTERACTIVO
// ================================================================
void loop() {
    if (Serial.available() > 0) {
        // Limpiar el buffer del puerto serie
        while(Serial.available() > 0) { Serial.read(); delay(5); }

        Serial.println("\nPON TU MANO FRENTE A LA CAMARA!");
        delay(1000);
        Serial.println("3...");
        delay(1000);
        Serial.println("2...");
        delay(1000);
        Serial.println("1...");
        delay(1000);
        
        Serial.println("TOMANDO FOTO Y ANALIZANDO...");
        Serial.println("============================================");

        if (!capturar_imagen()) {
            Serial.println("Error tomando foto.");
            return;
        }

        ei::signal_t signal;
        signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
        signal.get_data = &ei_camera_get_data;

        ei_impulse_result_t result = {0};
        run_classifier(&signal, &result, false);

        // Buscar el gesto con más seguridad
        String mejor_gesto = "ninguno";
        float mejor_valor = 0.0;

#if EI_CLASSIFIER_OBJECT_DETECTION == 1
        for (uint32_t i = 0; i < result.bounding_boxes_count; i++) {
            if (result.bounding_boxes[i].value > mejor_valor) {
                mejor_valor = result.bounding_boxes[i].value;
                mejor_gesto = String(result.bounding_boxes[i].label);
            }
        }
#else
        for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
            if (result.classification[i].value > mejor_valor) {
                mejor_valor = result.classification[i].value;
                mejor_gesto = String(result.classification[i].label);
            }
        }
#endif

        Serial.println("\nResultados de esta foto:");

        if (mejor_valor > 0.4) {
            Serial.printf("  -> Veo un '%s' con %.2f de seguridad\n", mejor_gesto.c_str(), mejor_valor);
            
            Serial.println("======> MOVIENDO MOTOR <======");
            if (mejor_gesto == "close") {
                Serial.println("   ¡CERRANDO LA MANO!");
                cerrarMano();
            } else if (mejor_gesto == "open") {
                Serial.println("   ¡ABRIENDO LA MANO!");
                abrirMano();
            } else {
                // Cualquier otro gesto, abrimos por seguridad
                Serial.println("   ¡ABRIENDO LA MANO!");
                abrirMano();
            }
        } else {
            Serial.println("  -> No estoy seguro de lo que veo (seguridad muy baja).");
        }

        Serial.println("\nLISTO. Escribe una letra y dale Enter para otra foto.");
    }
}
