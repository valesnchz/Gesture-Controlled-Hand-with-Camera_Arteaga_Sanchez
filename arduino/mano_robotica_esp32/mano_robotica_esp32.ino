/*
 ================================================================
  MANO ROBOTICA - ESP32 + Placa Expansion + Controlador PCA9685
 ================================================================
  Esquema de conexion:
  
    PC (Python) ──USB Serial──> ESP32 ──I2C──> PCA9685 ──PWM──> 5 Servos
  
  El PCA9685 es un controlador de 16 canales por I2C.
  Permite controlar hasta 16 servos con solo 2 cables (SDA/SCL).

  Conexion I2C del PCA9685 al ESP32:
    PCA9685  SDA  ──>  ESP32 GPIO 21  (SDA)
    PCA9685  SCL  ──>  ESP32 GPIO 22  (SCL)
    PCA9685  VCC  ──>  3.3V del ESP32 (para la logica I2C)
    PCA9685  GND  ──>  GND comun
    PCA9685  V+   ──>  5V externo (alimentacion de los servos)

  Canales de servo en el PCA9685:
    Canal 0  =  Pulgar
    Canal 1  =  Indice
    Canal 2  =  Medio
    Canal 3  =  Anular
    Canal 4  =  Menique

  Libreria necesaria (instala desde Library Manager del IDE Arduino):
    Adafruit PWM Servo Driver Library

  Notas:
    - La velocidad serial debe coincidir con Python: 9600
    - Conecta ESP32 al PC via USB (mismo cable que sube el codigo)
    - Solo desconecta el ESP32 para subir codigo, luego vuelve a conectar
 ================================================================
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ── OBJETO PCA9685 ──────────────────────────────────────────
// Direccion I2C por defecto: 0x40
// Si tu placa tiene jumpers de direccion, ajusta aqui: 0x41, 0x42, etc.
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// ── CANALES DE LOS SERVOS EN EL PCA9685 ────────────────────
#define CANAL_PULGAR   0
#define CANAL_INDICE   1
#define CANAL_MEDIO    2
#define CANAL_ANULAR   3
#define CANAL_MENIQUE  4

// ── CALIBRACION DE LOS SERVOS ───────────────────────────────
// El PCA9685 usa valores de pulso (0-4095 para 12 bits)
// Para la mayoria de servos:
//   ~150 = 0 grados  (pulso minimo ~0.5ms)
//   ~600 = 180 grados (pulso maximo ~2.5ms)
//
// Ajusta ABIERTO[] y CERRADO[] segun tu mano impresa en 3D
// Empieza con estos valores y afinalos en la calibracion

const int ABIERTO[5] = { 150, 150, 150, 150, 150 };  // 0 grados  = dedo extendido
const int CERRADO[5] = { 450, 500, 500, 500, 500 };  // ~120 grados = dedo doblado
//                        ^     ^     ^     ^     ^
//                     Pulgar Indice Medio Anular Menique

// ── FRECUENCIA PWM ──────────────────────────────────────────
// Los servos estandar funcionan a 50Hz
#define FRECUENCIA_SERVO  50

// ── VARIABLES SERIAL ────────────────────────────────────────
String inputString    = "";
bool   stringComplete = false;

// ================================================================
//  FUNCION: mover un servo a un valor de pulso
// ================================================================
void moverServo(int canal, int valorPulso) {
  // Limita el valor dentro de rango seguro
  valorPulso = constrain(valorPulso, 100, 650);
  pca.setPWM(canal, 0, valorPulso);
}

// ================================================================
//  FUNCION: convierte 0/1 a angulo y mueve el servo
// ================================================================
void actualizarDedo(int canal, int estado) {
  int pulso = (estado == 1) ? ABIERTO[canal] : CERRADO[canal];
  moverServo(canal, pulso);
}

// ================================================================
void setup() {
  Serial.begin(9600);
  inputString.reserve(20);

  // Iniciar I2C y el PCA9685
  Wire.begin();
  pca.begin();
  pca.setPWMFreq(FRECUENCIA_SERVO);

  delay(100);

  // Posicion inicial: todos los dedos abiertos
  for (int i = 0; i < 5; i++) {
    moverServo(i, ABIERTO[i]);
    delay(100);
  }

  Serial.println("ESP32 + PCA9685 listo. Esperando datos de Python...");
}

// ================================================================
void loop() {

  // Leer bytes del serial
  while (Serial.available()) {
    char c = (char)Serial.read();
    inputString += c;
    if (c == '\n') {
      stringComplete = true;
    }
  }

  // Procesar cuando llega una linea completa
  if (stringComplete) {
    inputString.trim();

    // Comando "R": Apagar PWM (relajar servos fisicamente)
    if (inputString.startsWith("R")) {
      for (int i = 0; i < 5; i++) {
        pca.setPWM(i, 0, 4096); // El bit 4096 desactiva la señal PWM por completo
      }
      Serial.println("OK: SERVOS APAGADOS (Motor Libre)");
    }
    // Formato esperado: "1,0,1,1,0"  (9 caracteres minimo)
    else if (inputString.length() >= 9) {
      int dedos[5];
      int idx = 0;
      char buf[20];
      inputString.toCharArray(buf, 20);

      char* token = strtok(buf, ",");
      while (token != NULL && idx < 5) {
        dedos[idx++] = atoi(token);
        token = strtok(NULL, ",");
      }

      if (idx == 5) {
        // Mover los 5 servos segun el estado recibido
        for (int i = 0; i < 5; i++) {
          actualizarDedo(i, dedos[i]);
        }

        // Echo de confirmacion (visible en el Monitor Serial del IDE)
        Serial.print("OK: ");
        Serial.println(inputString);
      }
    }

    inputString    = "";
    stringComplete = false;
  }
}
