/* ============================================================
   TEST DE CÁMARA - ESP32-CAM AI Thinker
   
   ¿Qué hace este código?
   - Crea una red WiFi propia (Access Point) llamada "TestCamara"
   - Sirve un streaming de video en vivo en tu navegador
   - Te muestra exactamente lo que VE la cámara antes del modelo
   
   INSTRUCCIONES:
   1. Sube este sketch a la ESP32-CAM
   2. Abre tu WiFi y conéctate a la red: "TestCamara"
      Contraseña: 12345678
   3. Abre tu navegador y ve a:  http://192.168.4.1
   4. Verás el video en vivo de la cámara
   5. Ajusta luz, ángulo y distancia hasta que se vea bien
   ============================================================ */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

/* ---- Pines cámara AI Thinker -------------------------------- */
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

/* ---- Configuración WiFi ------------------------------------- */
const char* WIFI_SSID = "TestCamara";
const char* WIFI_PASS = "12345678";

/* ---- Variables ---------------------------------------------- */
httpd_handle_t stream_httpd = NULL;

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

/* ---- Página HTML de la interfaz ----------------------------- */
static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Camara ESP32</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0f0f1a;
            color: #e0e0ff;
            font-family: 'Segoe UI', sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }
        h1 {
            font-size: 1.5rem;
            margin: 20px 0 8px;
            color: #a78bfa;
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        p.sub {
            color: #6b7280;
            font-size: 0.85rem;
            margin-bottom: 20px;
        }
        .camera-box {
            border: 3px solid #7c3aed;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 0 40px #7c3aed44;
            max-width: 500px;
            width: 100%;
        }
        img#stream {
            width: 100%;
            display: block;
        }
        .badge {
            display: inline-block;
            background: #7c3aed;
            color: white;
            border-radius: 20px;
            padding: 4px 14px;
            font-size: 0.75rem;
            margin-top: 14px;
            letter-spacing: 1px;
        }
        .tip {
            background: #1e1b2e;
            border-left: 4px solid #a78bfa;
            border-radius: 8px;
            padding: 14px 18px;
            margin-top: 20px;
            max-width: 500px;
            width: 100%;
            font-size: 0.85rem;
            line-height: 1.7;
            color: #c4b5fd;
        }
        .tip strong { color: #e9d5ff; }
    </style>
</head>
<body>
    <h1>&#128247; Test de Cámara</h1>
    <p class="sub">Comprueba que la cámara ve bien tu mano antes de usar el modelo</p>

    <div class="camera-box">
        <img id="stream" src="/stream" alt="Camara en vivo">
    </div>

    <span class="badge">&#128994; STREAMING EN VIVO</span>

    <div class="tip">
        <strong>Checklist para una buena detección:</strong><br>
        &#9989; La mano se ve <strong>nítida</strong> (no borrosa)<br>
        &#9989; Hay <strong>buena luz</strong> (la mano no es solo una silueta oscura)<br>
        &#9989; La mano <strong>ocupa la mayor parte</strong> de la imagen<br>
        &#9989; El fondo es <strong>diferente</strong> al color de la mano<br>
        &#9989; La cámara está <strong>fija</strong> (no temblorosa)<br><br>
        Si todo se ve bien aquí, el modelo debería detectarte sin problema.
    </div>
</body>
</html>
)rawliteral";

/* ---- Handler de la página principal ------------------------- */
static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, INDEX_HTML, strlen(INDEX_HTML));
}

/* ---- Handler del stream de video ---------------------------- */
static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[64];

    res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[ERROR] Fallo captura de frame");
            res = ESP_FAIL;
            break;
        }

        httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        size_t hlen = snprintf(part_buf, 64, STREAM_PART, fb->len);
        httpd_resp_send_chunk(req, part_buf, hlen);
        httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);

        esp_camera_fb_return(fb);
        fb = NULL;

        if (res != ESP_OK) break;
    }
    return res;
}

/* ---- Iniciar servidor web ----------------------------------- */
void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;

    httpd_uri_t index_uri = {
        .uri      = "/",
        .method   = HTTP_GET,
        .handler  = index_handler,
        .user_ctx = NULL
    };

    httpd_uri_t stream_uri = {
        .uri      = "/stream",
        .method   = HTTP_GET,
        .handler  = stream_handler,
        .user_ctx = NULL
    };

    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &index_uri);
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.println("[OK] Servidor web iniciado.");
    }
}

/* ============================================================
   SETUP
   ============================================================ */
void setup() {
    Serial.begin(115200);
    Serial.println("\n====================================");
    Serial.println("   TEST DE CAMARA ESP32-CAM         ");
    Serial.println("====================================");

    /* ---- Iniciar cámara ---- */
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
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = FRAMESIZE_QVGA;   // 320x240 igual que el modelo
    config.jpeg_quality = 10;
    config.fb_count     = 2;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    config.grab_mode    = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[ERROR] Camara no inicio: 0x%x\n", err);
        Serial.println("Reinicia la placa e intenta de nuevo.");
        return;
    }

    // Subir brillo y contraste para ver mejor con poca luz
    sensor_t *s = esp_camera_sensor_get();
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);
    Serial.println("[OK] Camara lista.");

    /* ---- Crear red WiFi propia (Access Point) ---- */
    WiFi.softAP(WIFI_SSID, WIFI_PASS);
    IPAddress IP = WiFi.softAPIP();
    Serial.println("[OK] Red WiFi creada.");
    Serial.println("---------------------------------------");
    Serial.println("  Conectate a esta red WiFi:");
    Serial.println("  Nombre:      " + String(WIFI_SSID));
    Serial.println("  Contrasena:  " + String(WIFI_PASS));
    Serial.println("  Luego abre el navegador y ve a:");
    Serial.println("  http://" + IP.toString());
    Serial.println("---------------------------------------");

    startCameraServer();
    Serial.println("[OK] Todo listo. Abre tu navegador!");
}

/* ============================================================
   LOOP
   ============================================================ */
void loop() {
    // Nada que hacer, el servidor web corre en background
    delay(10000);
    Serial.println("[INFO] Servidor corriendo. Dispositivos conectados: "
                   + String(WiFi.softAPgetStationNum()));
}
