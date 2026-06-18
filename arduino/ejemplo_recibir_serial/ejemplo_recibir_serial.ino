/*
  ================================================================
   EJEMPLO: RECIBIR CLASIFICACIÓN DESDE PYTHON VIA PUERTO SERIAL
  ================================================================
   Este sketch muestra cómo recibir y procesar el resultado de
   un clasificador de gestos enviado desde Python por puerto serial.
   
   Es compatible con tu hardware:
     ESP32 + Controlador PCA9685 + 5 Servos de los dedos.
   
   Conexiones I2C del PCA9685 al ESP32:
     PCA9685 SDA  ──>  ESP32 GPIO 21
     PCA9685 SCL  ──>  ESP32 GPIO 22
     PCA9685 VCC  ──>  3.3V del ESP32
     PCA9685 GND  ──>  GND común
     PCA9685 V+   ──>  5V externo para servos
  ================================================================
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Instanciar el driver PCA9685 (dirección I2C por defecto 0x40)
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Pines de los servos en el PCA9685
#define CANAL_PULGAR   0
#define CANAL_INDICE   1
#define CANAL_MEDIO    2
#define CANAL_ANULAR   3
#define CANAL_MENIQUE  4

// Frecuencia para servos analógicos (50Hz)
#define FRECUENCIA_SERVO  50

// Calibración de pulsos para Servos (0 a 180 grados aprox. en SG90)
// Ajusta estos valores según la respuesta física de tu mano 3D
const int ABIERTO[5] = { 150, 150, 150, 150, 150 };  // Dedo extendido
const int CERRADO[5] = { 450, 500, 500, 500, 500 };  // Dedo doblado

// LED Integrado en el ESP32 (GPIO 2) para retroalimentación visual
#define LED_BUILTIN 2

// Variables para lectura serial
String entradaSerial = "";
bool datoCompleto = false;

// ================================================================
//  Función auxiliar para mover un dedo individual
// ================================================================
void moverDedo(int canal, int estado) {
  // estado = 1 (Abierto), estado = 0 (Cerrado)
  int pulso = (estado == 1) ? ABIERTO[canal] : CERRADO[canal];
  
  // Limitar el pulso dentro de un rango seguro para proteger el servo
  pulso = constrain(pulso, 100, 600);
  pca.setPWM(canal, 0, pulso);
}

// ================================================================
//  Función que ejecuta un GESTO COMPLETO (combinación de 5 dedos)
// ================================================================
void ejecutarGesto(int pulgar, int indice, int medio, int anular, int menique) {
  moverDedo(CANAL_PULGAR,  pulgar);
  moverDedo(CANAL_INDICE,  indice);
  moverDedo(CANAL_MEDIO,   medio);
  moverDedo(CANAL_ANULAR,  anular);
  moverDedo(CANAL_MENIQUE, menique);
}

// ================================================================
//  Función para procesar la clasificación recibida
// ================================================================
void procesarClasificacion(String gesto) {
  gesto.trim(); // Remover espacios o saltos de línea adicionales
  
  if (gesto.length() == 0) return;

  Serial.print("Procesando clasificación recibida: ");
  Serial.println(gesto);

  // Encender LED integrado al recibir y procesar datos válidos
  digitalWrite(LED_BUILTIN, HIGH);

  // --- Mapeo de Clasificaciones a Movimientos de Servos ---
  if (gesto == "MANO_ABIERTA") {
    // Todos los dedos abiertos: 1, 1, 1, 1, 1
    ejecutarGesto(1, 1, 1, 1, 1);
    Serial.println("Acción -> Mano Abierta");
  } 
  else if (gesto == "PUNO") {
    // Todos los dedos cerrados: 0, 0, 0, 0, 0
    ejecutarGesto(0, 0, 0, 0, 0);
    Serial.println("Acción -> Cerrar Puño");
  } 
  else if (gesto == "LIKE") {
    // Solo pulgar abierto: 1, 0, 0, 0, 0
    ejecutarGesto(1, 0, 0, 0, 0);
    Serial.println("Acción -> Like (Pulgar Arriba)");
  } 
  else if (gesto == "ROCK") {
    // Pulgar, índice y meñique abiertos: 1, 1, 0, 0, 1
    ejecutarGesto(1, 1, 0, 0, 1);
    Serial.println("Acción -> Rock and Roll");
  } 
  else if (gesto == "NUMERO_2" || gesto == "AMOR_Y_PAZ") {
    // Índice y medio abiertos: 0, 1, 1, 0, 0
    ejecutarGesto(0, 1, 1, 0, 0);
    Serial.println("Acción -> Símbolo de Paz / Número 2");
  } 
  else {
    Serial.print("Clasificación no reconocida: ");
    Serial.println(gesto);
  }

  delay(100);
  digitalWrite(LED_BUILTIN, LOW); // Apagar LED
}

// ================================================================
void setup() {
  // Inicializar comunicación serial a la velocidad configurada (9600 baudios)
  Serial.begin(9600);
  entradaSerial.reserve(50); // Reservar memoria para evitar fragmentación

  // Configurar pin del LED incorporado
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Inicializar I2C y PCA9685
  Wire.begin();
  pca.begin();
  pca.setPWMFreq(FRECUENCIA_SERVO);

  delay(200);

  // Posición inicial segura: mano abierta
  ejecutarGesto(1, 1, 1, 1, 1);

  Serial.println("ESP32 Listo. Esperando clasificaciones desde Python...");
}

// ================================================================
void loop() {
  // 1. Leer los datos entrantes del puerto serial
  while (Serial.available() > 0) {
    char caracter = (char)Serial.read();
    
    // Si encontramos el salto de línea '\n', el mensaje está completo
    if (caracter == '\n') {
      datoCompleto = true;
    } else {
      entradaSerial += caracter; // Ir acumulando los caracteres
    }
  }

  // 2. Procesar el dato cuando se reciba por completo
  if (datoCompleto) {
    procesarClasificacion(entradaSerial);
    
    // Responder a Python como confirmación de recepción (Echo)
    Serial.print("ACK:");
    Serial.println(entradaSerial);

    // Limpiar variables para la siguiente lectura
    entradaSerial = "";
    datoCompleto = false;
  }
}
