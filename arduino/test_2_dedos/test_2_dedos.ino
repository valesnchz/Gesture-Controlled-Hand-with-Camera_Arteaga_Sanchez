/*
 ================================================================
  TEST 3 DEDOS - Medio, Anular y Menique
  ESP32 + Placa Expansion + PCA9685
 ================================================================
  Mueve el Medio (canal 2), Anular (canal 3) y Menique (canal 4).
  Ignora Pulgar e Indice aunque Python los envie.

  Recibe por serial: "1,0,1,1,0\n"
                              ^ ^
                           Anular Menique

  Conexion igual que siempre:
    PCA9685 SDA -> GPIO 21
    PCA9685 SCL -> GPIO 22
    Canal 2     -> Servo Medio
    Canal 3     -> Servo Anular
    Canal 4     -> Servo Menique
    V+          -> 5V externo
 ================================================================
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ── PCA9685 ─────────────────────────────────────────────────
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// ── CANALES (3 dedos de prueba) ─────────────────────────────
#define CANAL_MEDIO    2
#define CANAL_ANULAR   3
#define CANAL_MENIQUE  4

// ── CALIBRACION ─────────────────────────────────────────────
// Ajusta estos valores segun tu mano impresa
//   ABIERTO ~= 0 grados  (dedo extendido)
//   CERRADO ~= 120 grados (dedo doblado)
const int ABIERTO_MEDIO   = 150;
const int CERRADO_MEDIO   = 500;

const int ABIERTO_ANULAR  = 150;
const int CERRADO_ANULAR  = 500;

const int ABIERTO_MENIQUE = 150;
const int CERRADO_MENIQUE = 500;

// ── SERIAL ───────────────────────────────────────────────────
String inputString    = "";
bool   stringComplete = false;

// ================================================================
void setup() {
  Serial.begin(9600);
  inputString.reserve(20);

  Wire.begin();
  pca.begin();
  pca.setPWMFreq(50);   // 50Hz para servos
  delay(100);

  // Posicion inicial: los 3 dedos abiertos
  pca.setPWM(CANAL_MEDIO,   0, ABIERTO_MEDIO);
  pca.setPWM(CANAL_ANULAR,  0, ABIERTO_ANULAR);
  pca.setPWM(CANAL_MENIQUE, 0, ABIERTO_MENIQUE);
  delay(500);

  Serial.println("TEST 3 DEDOS listo (Medio + Anular + Menique)");
  Serial.println("Esperando datos de Python...");
}

// ================================================================
void loop() {

  // Leer del serial
  while (Serial.available()) {
    char c = (char)Serial.read();
    inputString += c;
    if (c == '\n') stringComplete = true;
  }

  // Procesar cuando llega linea completa
  if (stringComplete) {
    inputString.trim();

    // Formato: "pulgar,indice,medio,anular,menique"
    //  indice:    0      1      2      3      4
    if (inputString.length() >= 9) {
      int dedos[5] = {0, 0, 0, 0, 0};
      int idx = 0;
      char buf[20];
      inputString.toCharArray(buf, 20);

      char* token = strtok(buf, ",");
      while (token != NULL && idx < 5) {
        dedos[idx++] = atoi(token);
        token = strtok(NULL, ",");
      }

      if (idx == 5) {
        // ── Medio (posicion 2) ──
        if (dedos[2] == 1) {
          pca.setPWM(CANAL_MEDIO, 0, ABIERTO_MEDIO);
          Serial.print("Medio: ABIERTO   ");
        } else {
          pca.setPWM(CANAL_MEDIO, 0, CERRADO_MEDIO);
          Serial.print("Medio: CERRADO   ");
        }

        // ── Anular (posicion 3) ──
        if (dedos[3] == 1) {
          pca.setPWM(CANAL_ANULAR, 0, ABIERTO_ANULAR);
          Serial.print("Anular: ABIERTO  ");
        } else {
          pca.setPWM(CANAL_ANULAR, 0, CERRADO_ANULAR);
          Serial.print("Anular: CERRADO  ");
        }

        // ── Menique (posicion 4) ──
        if (dedos[4] == 1) {
          pca.setPWM(CANAL_MENIQUE, 0, ABIERTO_MENIQUE);
          Serial.println("Menique: ABIERTO");
        } else {
          pca.setPWM(CANAL_MENIQUE, 0, CERRADO_MENIQUE);
          Serial.println("Menique: CERRADO");
        }
      }
    }

    inputString    = "";
    stringComplete = false;
  }
}
