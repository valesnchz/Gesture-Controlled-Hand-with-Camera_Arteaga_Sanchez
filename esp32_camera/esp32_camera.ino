/* ============================================================
   Mano Robotica - ESP32-CAM + Edge Impulse FOMO
   Libreria: fomo2_inferencing (89.7% accuracy)
   ============================================================ */

#include <fomo2_inferencing.h>
#include "edge-impulse-sdk/dsp/image/image.hpp"
#include "esp_camera.h"
#include <ESP32Servo.h>

/* ---- Pines camara AI Thinker -------------------------------- */
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

#define EI_CAMERA_RAW_FRAME_BUFFER_COLS   320
#define EI_CAMERA_RAW_FRAME_BUFFER_ROWS   240
#define EI_CAMERA_FRAME_BYTE_SIZE         3

/* ---- Configuracion del Servo -------------------------------- */
#define PIN_SERVO  14    // Cambia a 15 si conectaste ahi el cable amarillo
#define UMBRAL     0.50  // Minimo de confianza para mover el motor

Servo servoMano;
int estado_actual   = 0; // 0=abierta, 1=cerrada
static bool debug_nn       = false;
static bool is_initialised = false;
uint8_t *snapshot_buf;

static camera_config_t camera_config = {
    .pin_pwdn     = PWDN_GPIO_NUM,
    .pin_reset    = RESET_GPIO_NUM,
    .pin_xclk     = XCLK_GPIO_NUM,
    .pin_sscb_sda = SIOD_GPIO_NUM,
    .pin_sscb_scl = SIOC_GPIO_NUM,
    .pin_d7 = Y9_GPIO_NUM, .pin_d6 = Y8_GPIO_NUM,
    .pin_d5 = Y7_GPIO_NUM, .pin_d4 = Y6_GPIO_NUM,
    .pin_d3 = Y5_GPIO_NUM, .pin_d2 = Y4_GPIO_NUM,
    .pin_d1 = Y3_GPIO_NUM, .pin_d0 = Y2_GPIO_NUM,
    .pin_vsync    = VSYNC_GPIO_NUM,
    .pin_href     = HREF_GPIO_NUM,
    .pin_pclk     = PCLK_GPIO_NUM,
    .xclk_freq_hz = 20000000,
    .ledc_timer   = LEDC_TIMER_0,
    .ledc_channel = LEDC_CHANNEL_0,
    .pixel_format = PIXFORMAT_JPEG,
    .frame_size   = FRAMESIZE_QVGA,
    .jpeg_quality = 12,
    .fb_count     = 1,
    .fb_location  = CAMERA_FB_IN_PSRAM,
    .grab_mode    = CAMERA_GRAB_WHEN_EMPTY,
};

bool ei_camera_init(void);
bool ei_camera_capture(uint32_t img_width, uint32_t img_height, uint8_t *out_buf);
static int ei_camera_get_data(size_t offset, size_t length, float *out_ptr);

/* ============================================================
   SETUP
   ============================================================ */
void setup() {
    Serial.begin(115200);
    Serial.println("\n========================================");
    Serial.println("   MANO ROBOTICA - INICIANDO...        ");
    Serial.println("========================================");

    if (!ei_camera_init()) {
        Serial.println("[ERROR] Camara no inicio!");
    } else {
        Serial.println("[OK] Camara lista.");
    }

    ESP32PWM::allocateTimer(1);
    servoMano.setPeriodHertz(50);
    servoMano.attach(PIN_SERVO, 500, 2400);
    servoMano.write(0);
    Serial.println("[OK] Servo listo. Posicion: ABIERTA");
    Serial.println("[OK] Umbral de deteccion: " + String(UMBRAL));
    delay(2000);
}

/* ============================================================
   LOOP
   ============================================================ */
void loop() {
    // Cuenta regresiva para acomodar la mano
    Serial.println("\n----------------------------------------");
    Serial.println("Prepara tu mano...");
    Serial.println("3..."); delay(1000);
    Serial.println("2..."); delay(1000);
    Serial.println("1..."); delay(1000);
    Serial.println("FOTO!");

    // Reservar memoria
    snapshot_buf = (uint8_t*)malloc(
        EI_CAMERA_RAW_FRAME_BUFFER_COLS *
        EI_CAMERA_RAW_FRAME_BUFFER_ROWS *
        EI_CAMERA_FRAME_BYTE_SIZE
    );
    if (!snapshot_buf) {
        Serial.println("[ERROR] Sin memoria!");
        return;
    }

    // Preparar señal para el clasificador
    ei::signal_t signal;
    signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
    signal.get_data     = &ei_camera_get_data;

    // Capturar foto
    if (!ei_camera_capture(EI_CLASSIFIER_INPUT_WIDTH, EI_CLASSIFIER_INPUT_HEIGHT, snapshot_buf)) {
        Serial.println("[ERROR] Fallo la captura.");
        free(snapshot_buf);
        return;
    }

    // Correr el modelo
    ei_impulse_result_t result = { 0 };
    EI_IMPULSE_ERROR err = run_classifier(&signal, &result, debug_nn);
    if (err != EI_IMPULSE_OK) {
        Serial.printf("[ERROR] Clasificador: %d\n", err);
        free(snapshot_buf);
        return;
    }

    // Leer bounding boxes y buscar la deteccion mas alta
    float max_open  = 0.0;
    float max_close = 0.0;

    Serial.printf("Boxes encontrados: %u\n", result.bounding_boxes_count);

    for (uint32_t i = 0; i < result.bounding_boxes_count; i++) {
        ei_impulse_result_bounding_box_t bb = result.bounding_boxes[i];
        if (bb.value < 0.01) continue; // ignorar ruido

        Serial.printf("  [%s] %.0f%% en (x=%u, y=%u)\n",
                      bb.label, bb.value * 100, bb.x, bb.y);

        if (strcmp(bb.label, "open")  == 0 && bb.value > max_open)  max_open  = bb.value;
        if (strcmp(bb.label, "close") == 0 && bb.value > max_close) max_close = bb.value;
    }

    // Mostrar resultado final
    Serial.printf("RESULTADO -> OPEN: %.0f%% | CLOSE: %.0f%%\n",
                  max_open * 100, max_close * 100);

    // Decidir y mover servo
    if (max_open < UMBRAL && max_close < UMBRAL) {
        Serial.println(">> Sin deteccion. Motor quieto.");
    }
    else if (max_close >= max_open) {
        if (estado_actual == 0) {
            Serial.println(">> CERRANDO mano robotica...");
            servoMano.write(180);
            estado_actual = 1;
            delay(2500);
            Serial.println(">> Mano cerrada.");
        } else {
            Serial.println(">> (Ya estaba cerrada)");
        }
    }
    else {
        if (estado_actual == 1) {
            Serial.println(">> ABRIENDO mano robotica...");
            servoMano.write(0);
            estado_actual = 0;
            delay(2500);
            Serial.println(">> Mano abierta.");
        } else {
            Serial.println(">> (Ya estaba abierta)");
        }
    }

    free(snapshot_buf);
}

/* ============================================================
   FUNCIONES DE CAMARA
   ============================================================ */
bool ei_camera_init(void) {
    if (is_initialised) return true;

    esp_err_t err = esp_camera_init(&camera_config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed: 0x%x\n", err);
        return false;
    }

    sensor_t *s = esp_camera_sensor_get();
    if (s->id.PID == OV3660_PID) {
        s->set_vflip(s, 1);
        s->set_brightness(s, 1);
        s->set_saturation(s, 0);
    }
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);

    is_initialised = true;
    return true;
}

bool ei_camera_capture(uint32_t img_width, uint32_t img_height, uint8_t *out_buf) {
    if (!is_initialised) return false;

    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) return false;

    bool converted = fmt2rgb888(fb->buf, fb->len, PIXFORMAT_JPEG, snapshot_buf);
    esp_camera_fb_return(fb);
    if (!converted) return false;

    if ((img_width  != EI_CAMERA_RAW_FRAME_BUFFER_COLS) ||
        (img_height != EI_CAMERA_RAW_FRAME_BUFFER_ROWS)) {
        ei::image::processing::crop_and_interpolate_rgb888(
            out_buf,
            EI_CAMERA_RAW_FRAME_BUFFER_COLS,
            EI_CAMERA_RAW_FRAME_BUFFER_ROWS,
            out_buf, img_width, img_height
        );
    }
    return true;
}

static int ei_camera_get_data(size_t offset, size_t length, float *out_ptr) {
    size_t pixel_ix    = offset * 3;
    size_t pixels_left = length;
    size_t out_ptr_ix  = 0;
    while (pixels_left != 0) {
        out_ptr[out_ptr_ix] =
            (snapshot_buf[pixel_ix + 2] << 16) +
            (snapshot_buf[pixel_ix + 1] << 8)  +
             snapshot_buf[pixel_ix];
        out_ptr_ix++;
        pixel_ix += 3;
        pixels_left--;
    }
    return 0;
}

#if !defined(EI_CLASSIFIER_SENSOR) || EI_CLASSIFIER_SENSOR != EI_CLASSIFIER_SENSOR_CAMERA
#error "Invalid model for current sensor"
#endif
