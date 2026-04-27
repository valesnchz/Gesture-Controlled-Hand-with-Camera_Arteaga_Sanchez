/*
 ================================================================
  ROBOTIC HAND - Espressif IDF
 ================================================================
  Hardware:
    ESP32 + Expansion Board + PCA9685 Controller

  I2C Connection:
    PCA9685 SDA  ->  GPIO 21
    PCA9685 SCL  ->  GPIO 22
    PCA9685 VCC  ->  3.3V
    PCA9685 V+   ->  External 5V (servo power)
    PCA9685 GND  ->  Common GND

  PCA9685 Channels:
    Channel 0 = Thumb
    Channel 1 = Index
    Channel 2 = Middle
    Channel 3 = Ring
    Channel 4 = Pinky
 ================================================================
*/

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/i2c.h"
#include "esp_log.h"

// ── LOG TAG ───────────────────────────────────────────────
static const char *TAG = "ROBOTIC_HAND";

// ── UART (Serial from Python) ─────────────────────────────
#define UART_NUM        UART_NUM_0   // UART0 = USB serial
#define UART_BAUD       9600
#define UART_BUF_SIZE   256

// ── I2C (PCA9685 Communication) ───────────────────────────
#define I2C_MASTER_NUM  I2C_NUM_0
#define I2C_SDA_PIN     21
#define I2C_SCL_PIN     22
#define I2C_FREQ_HZ     400000        // 400kHz (fast mode)
#define PCA9685_ADDR    0x40          // PCA9685 I2C Address

// ── PCA9685 REGISTERS ─────────────────────────────────────
#define PCA_MODE1       0x00
#define PCA_PRESCALE    0xFE
#define PCA_LED0_ON_L   0x06          // Base register for channel 0

// ── SERVO CALIBRATION ─────────────────────────────────────
// PCA9685 pulse values (0-4095)
// Adjust according to your 3D printed hand
static const int OPENED[5] = { 150, 150, 150, 150, 150 };
static const int CLOSED[5] = { 450, 500, 500, 500, 500 };

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
    // Chip reset
    pca9685_write(PCA_MODE1, 0x00);
    vTaskDelay(pdMS_TO_TICKS(10));

    // Configure PWM frequency to 50Hz for servos
    // Formula: prescale = round(25MHz / (4096 * 50Hz)) - 1 = 121
    uint8_t prescale = 121;
    uint8_t mode1_val;

    // Read current mode
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

    // Sleep mode to change prescaler
    pca9685_write(PCA_MODE1, (mode1_val & 0x7F) | 0x10);
    pca9685_write(PCA_PRESCALE, prescale);
    pca9685_write(PCA_MODE1, mode1_val);
    vTaskDelay(pdMS_TO_TICKS(5));
    pca9685_write(PCA_MODE1, mode1_val | 0xA0);  // Auto-increment enabled

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
    // Limit pulse to safe range
    if (pulse < 100) pulse = 100;
    if (pulse > 650) pulse = 650;
    pca9685_set_pwm(channel, 0, pulse);
}

static void initial_position(void)
{
    ESP_LOGI(TAG, "Moving to initial position (all opened)...");
    for (int i = 0; i < 5; i++) {
        move_servo(i, OPENED[i]);
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

// ================================================================
//  UART - Initialization
// ================================================================

static void uart_init(void)
{
    uart_config_t uart_config = {
        .baud_rate  = UART_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
    };
    uart_param_config(UART_NUM, &uart_config);
    uart_driver_install(UART_NUM, UART_BUF_SIZE * 2, 0, 0, NULL, 0);
    ESP_LOGI(TAG, "UART initialized at %d baud", UART_BAUD);
}

// ================================================================
//  MAIN TASK: read serial and move servos
// ================================================================

static void serial_task(void *arg)
{
    uint8_t buf[32];
    char    line[32];
    int     idx = 0;

    ESP_LOGI(TAG, "Waiting for Python data...");

    while (1) {
        uint8_t byte;
        int len = uart_read_bytes(UART_NUM, &byte, 1, pdMS_TO_TICKS(10));

        if (len > 0) {
            if (byte == '\n' || byte == '\r') {
                if (idx > 0) {
                    line[idx] = '\0';
                    idx = 0;

                    // Parse "1,0,1,1,0"
                    int fingers[5];
                    int n = 0;
                    char *tok = strtok(line, ",");
                    while (tok && n < 5) {
                        fingers[n++] = atoi(tok);
                        tok = strtok(NULL, ",");
                    }

                    if (n == 5) {
                        ESP_LOGI(TAG, "Received: %d,%d,%d,%d,%d",
                                 fingers[0], fingers[1], fingers[2], fingers[3], fingers[4]);

                        // Move each servo based on state
                        for (int i = 0; i < 5; i++) {
                            int pulse = (fingers[i] == 1) ? OPENED[i] : CLOSED[i];
                            move_servo((uint8_t)i, (uint16_t)pulse);
                        }

                        // Confirmation response to PC
                        printf("OK: %d,%d,%d,%d,%d\n",
                               fingers[0], fingers[1], fingers[2], fingers[3], fingers[4]);
                    }
                }
            } else if (idx < (int)sizeof(line) - 1) {
                line[idx++] = (char)byte;
            }
        }
    }
}

// ================================================================
//  ENTRY POINT
// ================================================================

void app_main(void)
{
    ESP_LOGI(TAG, "=== ROBOTIC HAND - ESP-IDF ===");

    // 1. Initialize I2C
    ESP_ERROR_CHECK(i2c_master_init());
    ESP_LOGI(TAG, "I2C initialized");

    // 2. Initialize PCA9685
    pca9685_init();

    // 3. Initial position
    initial_position();

    // 4. Initialize UART (serial)
    uart_init();

    // 5. Create FreeRTOS task to read serial
    xTaskCreate(serial_task, "serial_task", 4096, NULL, 5, NULL);

    ESP_LOGI(TAG, "System ready. Waiting for Python data...");
}
