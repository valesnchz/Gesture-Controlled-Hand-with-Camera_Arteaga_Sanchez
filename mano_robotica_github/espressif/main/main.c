/*
 ================================================================
  ROBOTIC HAND - Espressif IDF (WiFi + Camera + PCA9685)
 ================================================================
*/

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "esp_http_server.h"
#include "esp_camera.h"

static const char *TAG = "ROBOTIC_HAND";

// ── WIFI AP CONFIG ──────────────────────────────────────────
#define WIFI_SSID       "CamaraESP32"
#define WIFI_PASS       "12345678"
#define MAX_STA_CONN    4

// ── I2C (PCA9685 Communication) ───────────────────────────
#define I2C_MASTER_NUM  I2C_NUM_0
#define I2C_SDA_PIN     15   // Changed to 15 based on Arduino Wire.begin(15, 14)
#define I2C_SCL_PIN     14
#define I2C_FREQ_HZ     400000        // 400kHz (fast mode)
#define PCA9685_ADDR    0x40          // PCA9685 I2C Address

// ── PCA9685 REGISTERS ─────────────────────────────────────
#define PCA_MODE1       0x00
#define PCA_PRESCALE    0xFE
#define PCA_LED0_ON_L   0x06          // Base register for channel 0

// ── SERVO CALIBRATION ─────────────────────────────────────
static const int OPENED[5] = { 150, 150, 150, 150, 150 };
static const int CLOSED[5] = { 500, 500, 500, 500, 500 }; 

// ── CAMERA PINS (AI-THINKER) ───────────────────────────────
#define CAM_PIN_PWDN    32
#define CAM_PIN_RESET   -1
#define CAM_PIN_XCLK    0
#define CAM_PIN_SIOD    26
#define CAM_PIN_SIOC    27
#define CAM_PIN_Y9      35
#define CAM_PIN_Y8      34
#define CAM_PIN_Y7      39
#define CAM_PIN_Y6      36
#define CAM_PIN_Y5      21
#define CAM_PIN_Y4      19
#define CAM_PIN_Y3      18
#define CAM_PIN_Y2      5
#define CAM_PIN_VSYNC   25
#define CAM_PIN_HREF    23
#define CAM_PIN_PCLK    22

// ================================================================
//  I2C - Low level functions
// ================================================================

static esp_err_t i2c_master_init(void)
{
    i2c_config_t conf = {
        .mode             = I2C_MODE_MASTER,
        .sda_io_num       = I2C_SDA_PIN,
        .scl_io_num       = I2C_SCL_PIN,
        .sda_pullup_en    = GPIO_PULLUP_ENABLE,
        .scl_pullup_en    = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_FREQ_HZ,
    };
    i2c_param_config(I2C_MASTER_NUM, &conf);
    return i2c_driver_install(I2C_MASTER_NUM, conf.mode, 0, 0, 0);
}

static esp_err_t pca9685_write(uint8_t reg, uint8_t val)
{
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (PCA9685_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, reg, true);
    i2c_master_write_byte(cmd, val, true);
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(cmd);
    return ret;
}

// ================================================================
//  PCA9685 - Initialization and servo control
// ================================================================

static void pca9685_init(void)
{
    pca9685_write(PCA_MODE1, 0x00);
    vTaskDelay(pdMS_TO_TICKS(10));
    uint8_t prescale = 121;
    uint8_t mode1_val;

    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (PCA9685_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, PCA_MODE1, true);
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (PCA9685_ADDR << 1) | I2C_MASTER_READ, true);
    i2c_master_read_byte(cmd, &mode1_val, I2C_MASTER_NACK);
    i2c_master_stop(cmd);
    i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(cmd);

    pca9685_write(PCA_MODE1, (mode1_val & 0x7F) | 0x10);
    pca9685_write(PCA_PRESCALE, prescale);
    pca9685_write(PCA_MODE1, mode1_val);
    vTaskDelay(pdMS_TO_TICKS(5));
    pca9685_write(PCA_MODE1, mode1_val | 0xA0);
    ESP_LOGI(TAG, "PCA9685 initialized at 50Hz");
}

static void pca9685_set_pwm(uint8_t channel, uint16_t on, uint16_t off)
{
    uint8_t base = PCA_LED0_ON_L + 4 * channel;
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (PCA9685_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, base, true);
    i2c_master_write_byte(cmd, on  & 0xFF, true);
    i2c_master_write_byte(cmd, on  >> 8,   true);
    i2c_master_write_byte(cmd, off & 0xFF, true);
    i2c_master_write_byte(cmd, off >> 8,   true);
    i2c_master_stop(cmd);
    i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(cmd);
}

static void move_servo(uint8_t channel, uint16_t pulse)
{
    if (pulse < 100) pulse = 100;
    if (pulse > 650) pulse = 650;
    pca9685_set_pwm(channel, 0, pulse);
}

// ================================================================
//  HTTP SERVER (COMMANDS on PORT 82)
// ================================================================

static esp_err_t cmd_handler(httpd_req_t *req)
{
    size_t buf_len = httpd_req_get_url_query_len(req) + 1;
    if (buf_len > 1) {
        char *buf = malloc(buf_len);
        if (httpd_req_get_url_query_str(req, buf, buf_len) == ESP_OK) {
            char param[32];
            if (httpd_query_key_value(buf, "estado", param, sizeof(param)) == ESP_OK) {
                // Expected format "1,0,1,1,0"
                if (strlen(param) >= 9) {
                    int pulgar  = (param[0] == '1') ? OPENED[0] : CLOSED[0];
                    int indice  = (param[2] == '1') ? OPENED[1] : CLOSED[1];
                    int medio   = (param[4] == '1') ? OPENED[2] : CLOSED[2];
                    int anular  = (param[6] == '1') ? OPENED[3] : CLOSED[3];
                    int menique = (param[8] == '1') ? OPENED[4] : CLOSED[4];

                    move_servo(0, pulgar);
                    move_servo(1, indice);
                    move_servo(2, medio);
                    move_servo(3, anular);
                    move_servo(4, menique);
                }
            }
        }
        free(buf);
    }
    
    httpd_resp_sendstr(req, "OK");
    return ESP_OK;
}

static void start_command_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 82;
    config.ctrl_port = 32768; // distinct from other servers

    httpd_handle_t server = NULL;
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t cmd_uri = {
            .uri       = "/dedos",
            .method    = HTTP_GET,
            .handler   = cmd_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(server, &cmd_uri);
        ESP_LOGI(TAG, "Command server started on port 82");
    }
}

// ================================================================
//  HTTP SERVER (CAMERA STREAM on PORT 81)
// ================================================================

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t stream_handler(httpd_req_t *req)
{
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    char *part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            res = ESP_FAIL;
        } else {
            size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, fb->len);
            res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
            if (res == ESP_OK) {
                res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
            }
            if (res == ESP_OK) {
                res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
            }
            esp_camera_fb_return(fb);
        }
        if (res != ESP_OK) break;
    }
    return res;
}

static void start_camera_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 81;
    config.ctrl_port = 32769;

    httpd_handle_t server = NULL;
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t stream_uri = {
            .uri       = "/stream",
            .method    = HTTP_GET,
            .handler   = stream_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(server, &stream_uri);
        ESP_LOGI(TAG, "Camera stream server started on port 81");
    }
}

// ================================================================
//  WIFI AP INIT
// ================================================================
static void wifi_init_softap(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_t *ap_netif = esp_netif_create_default_wifi_ap();
    
    // We can explicitly set the IP to 192.168.4.1 (which is the default, but just to be sure)
    esp_netif_ip_info_t ip_info;
    esp_netif_get_ip_info(ap_netif, &ip_info);
    esp_netif_set_ip4_addr(&ip_info.ip, 192, 168, 4, 1);
    esp_netif_set_ip4_addr(&ip_info.gw, 192, 168, 4, 1);
    esp_netif_set_ip4_addr(&ip_info.netmask, 255, 255, 255, 0);
    esp_netif_dhcps_stop(ap_netif);
    esp_netif_set_ip_info(ap_netif, &ip_info);
    esp_netif_dhcps_start(ap_netif);

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid = WIFI_SSID,
            .ssid_len = strlen(WIFI_SSID),
            .channel = 1,
            .password = WIFI_PASS,
            .max_connection = MAX_STA_CONN,
            .authmode = WIFI_AUTH_WPA2_PSK
        },
    };
    if (strlen(WIFI_PASS) == 0) {
        wifi_config.ap.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "WiFi AP initialized. SSID:%s password:%s", WIFI_SSID, WIFI_PASS);
}

// ================================================================
//  CAMERA INIT
// ================================================================
static void camera_init(void)
{
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = CAM_PIN_Y2;
    config.pin_d1 = CAM_PIN_Y3;
    config.pin_d2 = CAM_PIN_Y4;
    config.pin_d3 = CAM_PIN_Y5;
    config.pin_d4 = CAM_PIN_Y6;
    config.pin_d5 = CAM_PIN_Y7;
    config.pin_d6 = CAM_PIN_Y8;
    config.pin_d7 = CAM_PIN_Y9;
    config.pin_xclk = CAM_PIN_XCLK;
    config.pin_pclk = CAM_PIN_PCLK;
    config.pin_vsync = CAM_PIN_VSYNC;
    config.pin_href = CAM_PIN_HREF;
    config.pin_sccb_sda = CAM_PIN_SIOD;
    config.pin_sccb_scl = CAM_PIN_SIOC;
    config.pin_pwdn = CAM_PIN_PWDN;
    config.pin_reset = CAM_PIN_RESET;
    config.xclk_freq_hz = 20000000;
    config.frame_size = FRAMESIZE_UXGA;
    config.pixel_format = PIXFORMAT_JPEG; 
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.jpeg_quality = 12;
    config.fb_count = 1;

    // Default to lower resolution for stream
    config.frame_size = FRAMESIZE_QVGA; // QVGA for fast streaming
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.jpeg_quality = 10;
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed with error 0x%x", err);
        return;
    }
    
    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 1); // User had flip
    
    ESP_LOGI(TAG, "Camera initialized");
}

// ================================================================
//  ENTRY POINT
// ================================================================
void app_main(void)
{
    ESP_LOGI(TAG, "=== ROBOTIC HAND - ESP-IDF (WIFI & CAMERA) ===");

    // 0. Init NVS (needed for WiFi)
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // 1. Initialize I2C and PCA9685
    ESP_ERROR_CHECK(i2c_master_init());
    pca9685_init();
    
    // Initial position
    for (int i = 0; i < 5; i++) {
        move_servo(i, OPENED[i]);
    }

    // 2. Initialize Camera
    camera_init();

    // 3. Initialize WiFi AP
    wifi_init_softap();

    // 4. Start HTTP Servers
    start_camera_server();
    start_command_server();

    ESP_LOGI(TAG, "System ready. Connect to WiFi 'CamaraESP32' and open streams.");
}
