# Mano Robótica — Versión Espressif IDF

## ¿Qué es Espressif IDF?

**ESP-IDF** (Espressif IoT Development Framework) es el framework **oficial** de Espressif para programar el ESP32. A diferencia de Arduino IDE que simplifica todo, ESP-IDF usa C puro con FreeRTOS y acceso directo al hardware.

---

## Estructura del proyecto

```
espressif/
├── CMakeLists.txt          ← Archivo de construccion del proyecto
├── main/
│   ├── CMakeLists.txt      ← Archivos del componente principal
│   └── main.c              ← Codigo principal (equivale al .ino)
└── README.md               ← Este archivo
```

---

## Comparación Arduino vs ESP-IDF

| Función          | Arduino                        | ESP-IDF (este archivo)          |
|------------------|--------------------------------|---------------------------------|
| Leer serial      | `Serial.read()`                | `uart_read_bytes()`             |
| Enviar serial    | `Serial.println()`             | `printf()`                      |
| I2C iniciar      | `Wire.begin()`                 | `i2c_param_config()` + `i2c_driver_install()` |
| I2C escribir     | `Wire.write()`                 | `i2c_master_cmd_begin()`        |
| Delay            | `delay(ms)`                    | `vTaskDelay(pdMS_TO_TICKS(ms))` |
| Tareas paralelas | No tiene                       | `xTaskCreate()` (FreeRTOS)      |
| Logs debug       | `Serial.print()`               | `ESP_LOGI(TAG, "...")`          |

---

## Cómo instalar ESP-IDF

### Opción 1: VS Code (recomendado)
1. Abre VS Code
2. Instala la extensión: **Espressif IDF**
3. Presiona `Ctrl+Shift+P` → `ESP-IDF: Configure ESP-IDF Extension`
4. Selecciona **Express** y deja que instale todo automáticamente

### Opción 2: Manual
```
winget install Espressif.EspIdf
```

---

## Cómo compilar y subir

### Desde VS Code con extensión ESP-IDF:
1. Abre la carpeta `espressif/` en VS Code
2. En la barra inferior selecciona tu puerto COM
3. Presiona el botón **Build** 🔨
4. Luego **Flash** ⚡
5. Luego **Monitor** 🔍 para ver los logs

### Desde terminal:
```bash
# Activar entorno ESP-IDF
. %IDF_PATH%\export.bat         # Windows

# Compilar
idf.py build

# Subir al ESP32
idf.py -p COM4 flash

# Ver logs en tiempo real
idf.py -p COM4 monitor

# Todo junto:
idf.py -p COM4 flash monitor
```

---

## Diferencias en el comportamiento

### Arduino
- Setup → Loop (simple, lineal)
- Todo en un solo hilo

### ESP-IDF
- `app_main()` → inicia tareas FreeRTOS
- `tarea_serial()` → corre en paralelo permanentemente
- Más eficiente, más control del hardware

---

## Conexiones (igual que la versión Arduino)

```
PCA9685 SDA  →  GPIO 21
PCA9685 SCL  →  GPIO 22
PCA9685 VCC  →  3.3V
PCA9685 V+   →  5V externo (servos)
PCA9685 GND  →  GND común

Canal 0 → Pulgar
Canal 1 → Índice
Canal 2 → Medio
Canal 3 → Anular
Canal 4 → Meñique
```

---

## El script Python NO cambia

`mano_robotica.py` funciona igual con ambas versiones.  
Solo activa el serial cuando tengas el ESP32 conectado:

```python
USAR_SERIAL   = True
PUERTO_SERIAL = 'COM4'   # tu puerto
```
